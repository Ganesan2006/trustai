# routers/conversations.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional, List
from dependencies import get_db, get_current_user
from model import (
    User, Conversation, Message, ConversationFile, DocumentAccessLog,
    QueryLog, RetrievalLog, ConversationAllowedFile, Department, Team
)
from pydantic import BaseModel
import os

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
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    conv = Conversation(
        organization_id=current_user.organization_id,
        user_id=current_user.id,
        name="New chat"
    )
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return {"id": conv.id, "name": conv.name}

@router.delete("/{conv_id}")
def delete_conversation(
    conv_id: int,
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

    # Delete retrieval logs
    query_log_ids = [ql.id for ql in db.query(QueryLog).filter(QueryLog.conversation_id == conv_id).all()]
    if query_log_ids:
        db.query(RetrievalLog).filter(RetrievalLog.query_log_id.in_(query_log_ids)).delete(synchronize_session=False)

    # Delete query logs
    db.query(QueryLog).filter(QueryLog.conversation_id == conv_id).delete(synchronize_session=False)

    # Delete document access logs referencing files of this conversation
    files = db.query(ConversationFile).filter(ConversationFile.conversation_id == conv_id).all()
    file_ids = [f.id for f in files]
    if file_ids:
        db.query(DocumentAccessLog).filter(DocumentAccessLog.file_id.in_(file_ids)).delete(synchronize_session=False)

    # Delete physical files and ConversationFile records
    for f in files:
        if os.path.exists(f.file_path):
            os.remove(f.file_path)
        db.delete(f)

    # Delete conversation allowed files
    db.query(ConversationAllowedFile).filter(ConversationAllowedFile.conversation_id == conv_id).delete()

    # Delete messages
    db.query(Message).filter(Message.conversation_id == conv_id).delete()

    # Delete conversation
    db.delete(conv)
    db.commit()
    return {"message": "Conversation deleted"}

@router.put("/{conv_id}")
def update_conversation_name(
    conv_id: int,
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
    conv_id: int,
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
            {"role": m.role, "content": m.content, "timestamp": m.timestamp}
            for m in msgs
        ]
    }

@router.post("/{conv_id}/messages")
def add_message(
    conv_id: int,
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
    conv_id: int,
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
    conv_id: int,
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
    conv_id: int,
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
    conv_id: int,
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