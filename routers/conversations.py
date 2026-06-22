# routers/conversations.py
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List
from dependencies import get_db, get_current_user
from model import (
    User, Conversation, Message, ConversationFile, DocumentAccessLog,
    QueryLog, RetrievalLog, ConversationAllowedFile, Department, Team,Organization,
    FeedbackLog
)
from pydantic import BaseModel
import os
from action import llmProcessor
from qdrant_client import models
from processors.supabase_storage import delete_file_from_supabase 

router = APIRouter(prefix="/api/conversations", tags=["conversations"])

class ConversationSettingsRequest(BaseModel):
    department_id: Optional[int] = None
    team_id: Optional[int] = None
    scope: Optional[str] = None

class ConversationNameRequest(BaseModel):
    name: str

# ==================== Conversation CRUD ====================
@router.get("")
def get_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    convs = db.query(Conversation).filter(
        Conversation.user_id == current_user.id,
        Conversation.organization_id == current_user.organization_id
    ).order_by(Conversation.updated_at.desc()).all()
    return {
    "conversations": [
        {
            "id": c.id,
            "name": c.name,
            "created_at": c.created_at,
            "department_id": c.department_id,
            "team_id": c.team_id,
            "scope": c.scope
        }
        for c in convs
    ]
}

@router.post("")
def create_conversation(
    data: Optional[ConversationNameRequest] = None,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    name = data.name if data and data.name else "New chat"
    conv = Conversation(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        name=name
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {"id": conv.id, "name": conv.name}

@router.delete("/{conv_id}")
async def delete_conversation(
    conv_id: str,
    request: Request,   # ← moved before delete_files
    delete_files: bool = Query(True, description="If True, delete associated files and Qdrant vectors"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
        Conversation.organization_id == current_user.organization_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    files = db.query(ConversationFile).filter(ConversationFile.conversation_id == conv_id).all()
    file_ids = [f.id for f in files]

    if delete_files:
        # Delete document access logs
        if file_ids:
            db.query(DocumentAccessLog).filter(DocumentAccessLog.file_id.in_(file_ids)).delete(synchronize_session=False)

        # Get org_short_id (from request state or DB)
        org_short_id = getattr(request.state, "org_short_id", None)
        if not org_short_id:
            org = db.query(Organization).filter(Organization.id == current_user.organization_id).first()
            org_short_id = org.org_id if org else None

        if org_short_id:
            col_name = f"org_{org_short_id}"
            llm = llmProcessor()
            for f in files:
                if f.document_id:
                    try:
                        filter_cond = models.Filter(must=[
                            models.FieldCondition(key="document_id", match=models.MatchValue(value=f.document_id))
                        ])
                        await llm.qdrant.client.delete(collection_name=col_name, points_selector=filter_cond)
                        print(f"Deleted Qdrant vectors for document {f.document_id}")
                    except Exception as e:
                        print(f"Qdrant deletion error for {f.document_id}: {e}")

        # Delete physical files from Supabase and DB records
        for f in files:
            if f.file_path:
                try:
                    delete_file_from_supabase(f.file_path)
                except Exception as e:
                    print(f"Supabase deletion error for {f.file_path}: {e}")
            db.delete(f)

    else:
        # Keep files: detach them from conversation
        for f in files:
            f.conversation_id = None
            
    # Delete retrieval logs, feedback logs, query logs, etc.
    query_log_ids = [ql.id for ql in db.query(QueryLog).filter(QueryLog.conversation_id == conv_id).all()]
    if query_log_ids:
        db.query(RetrievalLog).filter(RetrievalLog.query_log_id.in_(query_log_ids)).delete(synchronize_session=False)
        db.query(FeedbackLog).filter(FeedbackLog.query_log_id.in_(query_log_ids)).delete(synchronize_session=False)
    db.query(QueryLog).filter(QueryLog.conversation_id == conv_id).delete(synchronize_session=False)

    db.query(ConversationAllowedFile).filter(ConversationAllowedFile.conversation_id == conv_id).delete(synchronize_session=False)
    db.query(Message).filter(Message.conversation_id == conv_id).delete(synchronize_session=False)
    db.delete(conv)
    db.commit()
    
    msg = "Conversation and all associated files (and Qdrant vectors) deleted" if delete_files else "Conversation deleted, files retained"
    return {"message": msg}
    

@router.put("/{conv_id}")
def update_conversation_name(
    conv_id: str,
    data: ConversationNameRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
        Conversation.organization_id == current_user.organization_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    conv.name = data.name
    db.commit()
    return {"id": conv.id, "name": conv.name}

# ==================== Messages ====================
@router.get("/{conv_id}/messages")
def get_messages(
    conv_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
        Conversation.organization_id == current_user.organization_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    msgs = db.query(Message).filter(Message.conversation_id == conv_id).order_by(Message.timestamp).all()
    return {
        "messages": [
            {"id": m.id, "role": m.role, "content": m.content, "timestamp": m.timestamp, "citations": m.citations}
            for m in msgs
        ]
    }

@router.post("/{conv_id}/messages")
def add_message(
    conv_id: str,
    data: dict,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
        Conversation.organization_id == current_user.organization_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    role = data.get("role")
    content = data.get("content")
    if not role or not content:
        raise HTTPException(status_code=400, detail="Missing role or content")
    msg = Message(conversation_id=conv_id, role=role, content=content)
    db.add(msg)
    conv.updated_at = datetime.utcnow()
    db.commit()
    return {"message": "Message added"}

# ==================== Files in conversation ====================
@router.get("/{conv_id}/files")
def get_conversation_files(
    conv_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
        Conversation.organization_id == current_user.organization_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    files = db.query(ConversationFile).filter(ConversationFile.conversation_id == conv_id).all()
    return {
        "files": [
            {
                "id": f.id,
                "filename": f.original_filename or f.filename,
                "stored_name": f.filename,
                "file_size": f.file_size,
                "uploaded_at": f.uploaded_at.isoformat(),
                "access_level": f.access_level
            }
            for f in files
        ]
    }

@router.post("/{conv_id}/allowed-files")
def set_allowed_files(
    conv_id: str,
    file_ids: List[str],
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
        Conversation.organization_id == current_user.organization_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    # Delete old allowed entries
    db.query(ConversationAllowedFile).filter(ConversationAllowedFile.conversation_id == conv_id).delete()
    # Insert new ones
    for doc_id in file_ids:
        allowed = ConversationAllowedFile(conversation_id=conv_id, document_id=doc_id)
        db.add(allowed)
    db.commit()
    return {"message": "Allowed files updated"}

# ==================== Conversation Settings ====================
@router.put("/{conv_id}/settings")
def update_conversation_settings(
    conv_id: str,
    data: ConversationSettingsRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
        Conversation.organization_id == current_user.organization_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")

    if data.department_id is not None:
        if data.department_id:
            dept = db.query(Department).filter(Department.id == data.department_id, Department.organization_id == current_user.organization_id).first()
            if not dept:
                raise HTTPException(status_code=400, detail="Invalid department_id")
        conv.department_id = data.department_id

    if data.team_id is not None:
        if data.team_id:
            team = db.query(Team).filter(Team.id == data.team_id, Team.organization_id == current_user.organization_id).first()
            if not team:
                raise HTTPException(status_code=400, detail="Invalid team_id")
        conv.team_id = data.team_id

    if data.scope is not None:
        if data.scope not in ["private", "team", "company"]:
            raise HTTPException(status_code=400, detail="Invalid scope")
        conv.scope = data.scope

    db.commit()
    return {"message": "Settings updated"}

@router.get("/{conv_id}")
def get_conversation(
    conv_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = db.query(Conversation).filter(
        Conversation.id == conv_id,
        Conversation.user_id == current_user.id,
        Conversation.organization_id == current_user.organization_id
    ).first()
    if not conv:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "id": conv.id,
        "name": conv.name,
        "department_id": conv.department_id,
        "team_id": conv.team_id,
        "scope": conv.scope,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at
    }