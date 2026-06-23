# routers/chat.py
import json
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel
from sqlalchemy.orm import Session
from datetime import datetime

from dependencies import get_db, get_current_user
from model import User, Conversation, Message, QueryLog, FeedbackLog, Department, Team
from action import llmProcessor
from qdrant_client import models

router = APIRouter(prefix="/api/chat", tags=["chat"])

# ---------- Pydantic Models ----------
class SearchScope(BaseModel):
    type: str
    department_ids: Optional[List[int]] = None
    team_ids: Optional[List[int]] = None
    user_emails: Optional[List[str]] = None

class ChatRequest(BaseModel):
    input: str
    conversation_id: str
    search_scope: Optional[SearchScope] = None

class Citation(BaseModel):
    text: str
    document_name: str
    page: Optional[int] = None
    similarity: float

class ChatResponse(BaseModel):
    response: str
    conversation_id: str
    citations: List[Citation] = []
    query_log_id: int 

class FeedbackRequest(BaseModel):
    query_log_id: int
    rating: str          # "helpful" or "not_helpful"
    comment: Optional[str] = None

# ---------- Helper: Build Qdrant Filter from Scope ----------
def build_filter_from_scope(scope: SearchScope, user: User, conv: Conversation, db: Session) -> models.Filter:
    # If admin and no scope -> empty filter (see all)
    if not scope and user.role in ["org_admin", "super_admin"]:
        return models.Filter()

    if not scope:
        # Default: company + own department + own team + own private
        should = [
            models.FieldCondition(key="access_level", match=models.MatchValue(value="company")),
            models.Filter(must=[
                models.FieldCondition(key="access_level", match=models.MatchValue(value="private")),
                models.FieldCondition(key="uploaded_by", match=models.MatchValue(value=str(user.id)))
            ])
        ]
        if user.department_id and user.department:
            should.append(
                models.Filter(must=[
                    models.FieldCondition(key="access_level", match=models.MatchValue(value="department")),
                    models.FieldCondition(key="department", match=models.MatchValue(value=user.department.name))
                ])
            )
        if conv.team_id and conv.team:
            should.append(
                models.Filter(must=[
                    models.FieldCondition(key="access_level", match=models.MatchValue(value="team")),
                    models.FieldCondition(key="team", match=models.MatchValue(value=conv.team.name))
                ])
            )
        return models.Filter(should=should, min_should=models.MinShould(min_count=1, conditions=should))

    # Explicit scope
    scope_type = scope.type
    role = user.role

    if scope_type == "company":
        return models.Filter(must=[models.FieldCondition(key="access_level", match=models.MatchValue(value="company"))])

    elif scope_type == "department":
        if role in ["org_admin", "super_admin"] and scope.department_ids:
            depts = db.query(Department).filter(Department.id.in_(scope.department_ids)).all()
            dept_names = [d.name for d in depts]
            if not dept_names:
                raise HTTPException(400, "No valid departments")
            return models.Filter(
                must=[
                    models.FieldCondition(key="access_level", match=models.MatchValue(value="department")),
                    models.FieldCondition(key="department", match=models.MatchAny(any=dept_names))
                ]
            )
        else:
            # Non‑admin: use their own department
            if not user.department_id or not user.department:
                raise HTTPException(400, "You are not assigned to any department")
            return models.Filter(
                must=[
                    models.FieldCondition(key="access_level", match=models.MatchValue(value="department")),
                    models.FieldCondition(key="department", match=models.MatchValue(value=user.department.name))
                ]
            )

    elif scope_type == "team":
        if role in ["org_admin", "super_admin"] and scope.team_ids:
            teams = db.query(Team).filter(Team.id.in_(scope.team_ids)).all()
            team_names = [t.name for t in teams]
            if not team_names:
                raise HTTPException(400, "No valid teams")
            return models.Filter(
                must=[
                    models.FieldCondition(key="access_level", match=models.MatchValue(value="team")),
                    models.FieldCondition(key="team", match=models.MatchAny(any=team_names))
                ]
            )
        elif role == "department_manager" and scope.team_ids:
            teams = db.query(Team).filter(Team.id.in_(scope.team_ids), Team.department_id == user.department_id).all()
            team_names = [t.name for t in teams]
            if not team_names:
                raise HTTPException(400, "No valid teams under your department")
            return models.Filter(
                must=[
                    models.FieldCondition(key="access_level", match=models.MatchValue(value="team")),
                    models.FieldCondition(key="team", match=models.MatchAny(any=team_names))
                ]
            )
        else:
            # Team lead / employee: own team
            if not user.team_id or not user.team:
                raise HTTPException(400, "You are not assigned to any team")
            return models.Filter(
                must=[
                    models.FieldCondition(key="access_level", match=models.MatchValue(value="team")),
                    models.FieldCondition(key="team", match=models.MatchValue(value=user.team.name))
                ]
            )

    elif scope_type == "private":
        if role in ["org_admin", "super_admin"] and scope.user_emails:
            users = db.query(User).filter(User.email.in_(scope.user_emails)).all()
            user_ids = [str(u.id) for u in users]
            if not user_ids:
                raise HTTPException(400, "No valid users")
            return models.Filter(
                must=[
                    models.FieldCondition(key="access_level", match=models.MatchValue(value="private")),
                    models.FieldCondition(key="uploaded_by", match=models.MatchAny(any=user_ids))
                ]
            )
        else:
            return models.Filter(
                must=[
                    models.FieldCondition(key="access_level", match=models.MatchValue(value="private")),
                    models.FieldCondition(key="uploaded_by", match=models.MatchValue(value=str(user.id)))
                ]
            )

    raise HTTPException(400, f"Invalid scope type: {scope_type}")

# ---------- Helper: Extract Citations ----------
def extract_citations(chunks: List) -> List[Citation]:
    citations = []
    for chunk in chunks:
        meta = chunk.metadata
        doc_name = meta.get("file_name") or meta.get("title") or "Unknown Document"
        page = meta.get("page") or meta.get("page_number")
        citations.append(Citation(
            text=chunk.page_content[:300],  # preview
            document_name=doc_name,
            page=int(page) if page else None,
            similarity=meta.get("score", 0.0)
        ))
    return citations

from fastapi.responses import StreamingResponse

# ---------- Main Chat Endpoint ----------
@router.post("/")
async def chat(
    data: ChatRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(
        Conversation.id == data.conversation_id,
        Conversation.user_id == current_user.id,
        Conversation.organization_id == current_user.organization_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    # Chat history (optional, for condensing)
    prev_msgs = db.query(Message).filter(Message.conversation_id == conv.id).order_by(Message.timestamp).all()
    chat_history = []
    i = 0
    while i < len(prev_msgs) - 1:
        if prev_msgs[i].role == 'user' and prev_msgs[i+1].role == 'bot':
            chat_history.append((prev_msgs[i].content, prev_msgs[i+1].content))
            i += 2
        else:
            i += 1

    org_short_id = getattr(request.state, "org_short_id", None)
    if not org_short_id:
        raise HTTPException(status_code=500, detail="Organization not resolved")

    # Build filter and retrieve chunks
    q_filter = build_filter_from_scope(data.search_scope, current_user, conv, db)
    llm = llmProcessor(user_id=current_user.id, db=db)
    retrieved_chunks = await llm.hybrid_search(org_short_id, data.input, q_filter, top_k=15, final_k=15)

    # Extract citations
    citations = extract_citations(retrieved_chunks)

    # Build prompt with citations (so LLM knows to cite)
    context_parts = []
    for idx, chunk in enumerate(retrieved_chunks, start=1):
        source = citations[idx-1].document_name
        page = citations[idx-1].page
        page_str = f", page {page}" if page else ""
        context_parts.append(f"[{idx}] From {source}{page_str}:\n{chunk.page_content}")
    context = "\n\n".join(context_parts)

    prompt = f"""You are a helpful assistant. Answer the user's question using ONLY the provided context.
When you use information from a specific source, cite it using its number in brackets, like [1] or [2] at the end of the sentence.
If multiple sources support the same fact, list them as [1][2].

Context:
{context}

User question: {data.input}

Answer:"""

    # Rewrite with history (optional)
    user_input = data.input
    if chat_history:
        history_str = "\n".join([f"Human: {h}\nAI: {a}" for h, a in chat_history])
        condense_prompt = llm.condense_prompt.format(chat_history=history_str, input=data.input)
        raw = await llm.LLM.ainvoke(condense_prompt)
        user_input = raw.content.strip() if hasattr(raw, 'content') else str(raw).strip()
        
    print(f"[DEBUG] Returning citations: {citations}")
    
    async def response_streamer():
        bot_answer_chunks = []
        try:
            async for chunk in llm.LLM.astream(prompt):
                if hasattr(chunk, 'content'):
                    text = chunk.content
                elif isinstance(chunk, str):
                    text = chunk
                elif isinstance(chunk, dict) and 'answer' in chunk:
                    text = chunk['answer']
                else:
                    text = str(chunk)
                
                if text:
                    bot_answer_chunks.append(text)
                    # SSE format
                    yield f"data: {json.dumps({'type': 'chunk', 'content': text})}\n\n"
                    
            bot_answer = "".join(bot_answer_chunks)
            
            # Save messages
            def save_to_db():
                user_msg = Message(conversation_id=conv.id, role='user', content=data.input)
                bot_msg = Message(conversation_id=conv.id, role='bot', content=bot_answer, citations=[c.dict() for c in citations])
                db.add(user_msg)
                db.add(bot_msg)
                db.commit()
                db.refresh(bot_msg)

                # Log query for feedback
                query_log = QueryLog(
                    organization_id=current_user.organization_id,
                    user_id=current_user.id,
                    conversation_id=conv.id,
                    question=data.input,
                    answer=bot_answer,
                    retrieved_chunks=len(retrieved_chunks),
                    confidence_score=sum((c.similarity or 0.0) for c in citations)/len(citations) if citations else 0,
                    created_at=datetime.utcnow()
                )
                db.add(query_log)
                db.commit()

                # Update conversation name if first message
                msg_count = db.query(Message).filter(Message.conversation_id == conv.id).count()
                if conv.name == 'New chat' and msg_count == 2:
                    conv.name = data.input[:30] + ('…' if len(data.input) > 30 else '')
                    db.commit()
                return query_log.id

            query_log_id = await run_in_threadpool(save_to_db)

            # Send final payload
            final_payload = {
                "type": "final",
                "citations": [c.dict() for c in citations],
                "query_log_id": query_log_id,
                "conversation_id": conv.id
            }
            yield f"data: {json.dumps(final_payload)}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'type': 'error', 'content': str(e)})}\n\n"
            
    headers = {
        "Cache-Control": "no-cache",
        "Connection": "keep-alive",
        "X-Accel-Buffering": "no"
    }
    return StreamingResponse(response_streamer(), media_type="text/event-stream", headers=headers)


@router.post("/activate/{conv_id}")
def activate_conversation(conv_id: str, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    conv = db.query(Conversation).filter(Conversation.id == conv_id, Conversation.user_id == current_user.id).first()
    if not conv:
        raise HTTPException(404, "Conversation not found")
    return {"message": "Activated"}

@router.post("/feedback")
def submit_feedback(
    data: FeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    query_log = db.query(QueryLog).filter(
        QueryLog.id == data.query_log_id,
        QueryLog.user_id == current_user.id
    ).first()
    if not query_log:
        raise HTTPException(404, "Query log not found")
    query_log.user_feedback = data.rating
    if data.comment:
        query_log.feedback_comment = data.comment
    feedback = FeedbackLog(
        query_log_id=query_log.id,
        rating=data.rating,
        comment=data.comment
    )
    db.add(feedback)
    db.commit()
    return {"message": "Feedback recorded"}