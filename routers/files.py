import os
import uuid
import hashlib
import mimetypes
import tempfile
from datetime import datetime
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request, Query
from fastapi.responses import FileResponse, StreamingResponse,RedirectResponse
from sqlalchemy.orm import Session
from werkzeug.utils import secure_filename
from fastapi.concurrency import run_in_threadpool
import io

from dependencies import get_db, get_current_user
from model import User, Conversation, ConversationFile, Department, Team, DocumentAccessLog, QueryLog, RetrievalLog,ConversationAllowedFile,Message
from action import llmProcessor
from qdrant_client import models
from processors.supabase_storage import (
    upload_file_to_supabase,
    download_file_from_supabase,
    delete_file_from_supabase,
    get_public_url
)

router = APIRouter(prefix="/api/files", tags=["files"])
DEBUG = True

# ------------------------------------------------------------------
# Helper to get upload targets
# ------------------------------------------------------------------
@router.get("/upload-targets")
async def get_upload_targets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    org_id = current_user.organization_id
    response = {"departments": [], "teams": []}

    if current_user.role == "org_admin":
        depts = db.query(Department).filter(Department.organization_id == org_id).all()
        teams = db.query(Team).filter(Team.organization_id == org_id).all()
        response["departments"] = [{"id": d.id, "name": d.name} for d in depts]
        response["teams"] = [{"id": t.id, "name": t.name, "department_id": t.department_id} for t in teams]
    elif current_user.role == "department_manager":
        if current_user.department_id:
            teams = db.query(Team).filter(
                Team.organization_id == org_id,
                Team.department_id == current_user.department_id
            ).all()
            response["teams"] = [{"id": t.id, "name": t.name} for t in teams]
    return response


# ------------------------------------------------------------------
# Upload endpoint – Supabase Storage
# ------------------------------------------------------------------
@router.post("/upload")
async def upload_file(
    request: Request,
    conversation_id: Optional[str] = Form(None),
    input_file: UploadFile = File(...),
    scope: str = Form(...),
    target_department_id: int = Form(None),
    target_team_id: int = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Validate conversation (only if provided)
    conv_id = str(conversation_id) if conversation_id else None
    if conv_id:
        conv = db.query(Conversation).filter(
            Conversation.id == conv_id,
            Conversation.user_id == current_user.id,
            Conversation.organization_id == current_user.organization_id
        ).first()
        if not conv:
            raise HTTPException(status_code=404, detail="Conversation not found")

    # 2. Get organization short ID
    org_short_id = getattr(request.state, "org_short_id", None)
    if not org_short_id:
        raise HTTPException(status_code=500, detail="Organization not resolved")

    # 3. Read file content and check duplicate
    content = await input_file.read()
    file_hash = hashlib.sha256(content).hexdigest()
    existing = db.query(ConversationFile).filter(
        ConversationFile.file_hash == file_hash,
        ConversationFile.organization_id == current_user.organization_id
    ).first()
    if existing:
        print("file is already existing")
        raise HTTPException(status_code=409, detail="Duplicate file already exists")

    # 4. Determine effective department and team names for Qdrant payload (unchanged)
    effective_dept_name = None
    effective_team_name = None

    def get_dept_by_id(dept_id):
        return db.query(Department).filter(
            Department.id == dept_id,
            Department.organization_id == current_user.organization_id
        ).first()

    def get_team_by_id(team_id):
        return db.query(Team).filter(
            Team.id == team_id,
            Team.organization_id == current_user.organization_id
        ).first()

    if scope == "company":
        pass
    elif scope == "department":
        if current_user.role == "org_admin":
            if not target_department_id:
                raise HTTPException(400, "Admin must select a department")
            dept = get_dept_by_id(target_department_id)
            if not dept:
                raise HTTPException(400, "Invalid department")
            effective_dept_name = dept.name
        else:
            if not current_user.department_id:
                raise HTTPException(400, "You are not assigned to any department")
            dept = db.query(Department).filter(Department.id == current_user.department_id).first()
            if not dept:
                raise HTTPException(400, "Assigned department not found")
            effective_dept_name = dept.name
    elif scope == "team":
        if current_user.role == "org_admin":
            if not target_team_id:
                raise HTTPException(400, "Admin must select a team")
            team = get_team_by_id(target_team_id)
            if not team:
                raise HTTPException(400, "Invalid team")
            effective_team_name = team.name
            if team.department_id:
                dept = get_dept_by_id(team.department_id)
                if dept:
                    effective_dept_name = dept.name
        elif current_user.role == "department_manager":
            if not target_team_id:
                raise HTTPException(400, "Department manager must select a team")
            team = get_team_by_id(target_team_id)
            if not team or team.department_id != current_user.department_id:
                raise HTTPException(400, "You can only upload to teams under your department")
            effective_team_name = team.name
            if team.department_id:
                dept = get_dept_by_id(team.department_id)
                if dept:
                    effective_dept_name = dept.name
        else:
            if not current_user.team_id:
                raise HTTPException(400, "You are not assigned to any team")
            team = db.query(Team).filter(Team.id == current_user.team_id).first()
            if not team:
                raise HTTPException(400, "Assigned team not found")
            effective_team_name = team.name
            if team.department_id:
                dept = get_dept_by_id(team.department_id)
                if dept:
                    effective_dept_name = dept.name
    elif scope == "private":
        pass
    else:
        raise HTTPException(400, f"Invalid scope: {scope}")

    # 5. Save file temporarily for processing (chunking needs a local path)
    with tempfile.NamedTemporaryFile(delete=False) as tmp:
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # 6. Process document into chunks (needs local file path)
        llm = llmProcessor()
        document_id = str(uuid.uuid4())
        upload_date = datetime.utcnow().isoformat()
        ext_type = os.path.splitext(input_file.filename)[1].lower().lstrip('.')

        docs = await run_in_threadpool(
            llm.load_process_from_path, tmp_path, document_id, org_short_id, input_file.filename
        )
        if not docs:
            raise HTTPException(400, "No content extracted from file")

        # Near-duplicate document detection via full_text has been removed
        # since it causes truncation issues. Exact file deduplication handles duplicates safely.

        # 8. Build metadata list for Qdrant
        metadata_list = []
        for idx, doc in enumerate(docs):
            meta = {
                "organization_id": org_short_id,
                "document_id": document_id,
                "chunk_id": str(uuid.uuid4()),
                "chunk_number": idx + 1,
                "title": input_file.filename,
                "file_name": input_file.filename,
                "page_number": doc.metadata.get("page", 0),
                "uploaded_by": str(current_user.id),
                "upload_date": upload_date,
                "source_type": ext_type,
                "access_level": scope,
            }
            if effective_dept_name:
                meta["department"] = effective_dept_name
            if effective_team_name:
                meta["team"] = effective_team_name
            metadata_list.append(meta)

        # 9. Insert into Qdrant
        await llm.add_documents_to_company_with_metadata(org_short_id, docs, metadata_list)

        # 10. Upload file to Supabase Storage
        try:
            file_key, public_url = upload_file_to_supabase(
                content,  # bytes
                input_file.filename,
                input_file.content_type
            )
        except Exception as e:
            print("error in supabase file upload")
            raise HTTPException(status_code=500, detail=f"Supabase upload failed: {str(e)}")

        # 11. Save file record in PostgreSQL
        conv_file = ConversationFile(
            organization_id=current_user.organization_id,
            conversation_id=conv_id,
            user_id=current_user.id,
            filename=os.path.basename(tmp_path),   # stored name (not used)
            original_filename=input_file.filename,
            file_path=file_key,                    # store the key for retrieval
            file_size=len(content),
            file_hash=file_hash,
            document_id=document_id,
            access_level=scope,
            department=effective_dept_name,
            team=effective_team_name,
            gdrive_file_id=public_url              # reuse column for public URL
        )
        db.add(conv_file)
        db.commit()
        db.refresh(conv_file)

        return {"message": "File uploaded successfully", "file_id": conv_file.id}

    finally:
        # Clean up temporary file
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


@router.delete("/{conv_id}")
def delete_conversation(
    conv_id: str,
    delete_files: bool = Query(True),   # default true for backward compatibility
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

    # Get associated files
    files = db.query(ConversationFile).filter(ConversationFile.conversation_id == conv_id).all()
    file_ids = [f.id for f in files]

    if delete_files:
        # Delete document access logs
        if file_ids:
            db.query(DocumentAccessLog).filter(DocumentAccessLog.file_id.in_(file_ids)).delete(synchronize_session=False)

        # Delete from Qdrant and physical storage for each file
        for f in files:
            # Remove from Qdrant
            if f.document_id:
                org_short_id = current_user.organization.org_id  # assuming relationship
                col_name = f"org_{org_short_id}"
                try:
                    llm = llmProcessor()
                    filter_cond = models.Filter(must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=f.document_id))])
                    llm.qdrant.client.delete(collection_name=col_name, points_selector=filter_cond)
                except Exception as e:
                    print(f"Qdrant deletion error for {f.document_id}: {e}")
            # Remove from Supabase
            if f.file_path:
                try:
                    delete_file_from_supabase(f.file_path)
                except Exception as e:
                    print(f"Supabase deletion error for {f.file_path}: {e}")
            db.delete(f)

        # Also delete retrieval logs and query logs
        query_log_ids = [ql.id for ql in db.query(QueryLog).filter(QueryLog.conversation_id == conv_id).all()]
        if query_log_ids:
            db.query(RetrievalLog).filter(RetrievalLog.query_log_id.in_(query_log_ids)).delete(synchronize_session=False)
        db.query(QueryLog).filter(QueryLog.conversation_id == conv_id).delete(synchronize_session=False)

        # Delete allowed files
        db.query(ConversationAllowedFile).filter(ConversationAllowedFile.conversation_id == conv_id).delete()

        # Delete messages and conversation
        db.query(Message).filter(Message.conversation_id == conv_id).delete()
        db.delete(conv)
        db.commit()
        return {"message": "Conversation and associated files deleted"}

    else:
        # Keep files: detach them from conversation (set conversation_id = NULL)
        for f in files:
            f.conversation_id = None   # assume conversation_id is nullable; if not, alter table
        # Delete messages and conversation
        db.query(Message).filter(Message.conversation_id == conv_id).delete()
        db.delete(conv)
        db.commit()
        return {"message": "Conversation deleted, files retained"}
# ------------------------------------------------------------------
# Serve file (inline) – uses Supabase public URL or redirect
# ------------------------------------------------------------------
@router.get("/serve/{user_id}/{conv_id}/{filename}")
async def serve_file(
    user_id: int,
    conv_id: str,
    filename: str,
    request: Request,
    token: str = None,
    db: Session = Depends(get_db)
):
    # Authentication (unchanged)
    current_user_id = None
    if token:
        from jose import jwt, JWTError
        from config import SECRET_KEY, ALGORITHM
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            token_user_id = payload.get("sub")
            if token_user_id is None or int(token_user_id) != user_id:
                raise HTTPException(status_code=401, detail="Unauthorized")
            current_user_id = int(token_user_id)
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")
    else:
        from dependencies import get_current_user
        current_user = await get_current_user(request, db)
        if current_user.id != user_id:
            raise HTTPException(status_code=401, detail="Unauthorized")
        current_user_id = current_user.id

    file_record = db.query(ConversationFile).filter(
        ConversationFile.filename == filename,
        ConversationFile.user_id == user_id
    ).first()
    if not file_record:
        file_record = db.query(ConversationFile).filter(
            ConversationFile.original_filename == filename,
            ConversationFile.user_id == user_id
        ).first()
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    # Use public URL if available
    if file_record.gdrive_file_id:  # stored public URL
        return RedirectResponse(url=file_record.gdrive_file_id)

    # Otherwise, fallback to streaming (if we have key)
    if file_record.file_path:
        try:
            file_content = download_file_from_supabase(file_record.file_path)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to fetch from Supabase: {str(e)}")
        mime_type, _ = mimetypes.guess_type(file_record.original_filename or filename)
        mime_type = mime_type or 'application/octet-stream'
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type=mime_type,
            headers={"Content-Disposition": f"inline; filename=\"{file_record.original_filename or filename}\""}
        )

    raise HTTPException(status_code=404, detail="File not found")


# ------------------------------------------------------------------
# List accessible files (unchanged)
# ------------------------------------------------------------------
@router.get("/accessible")
async def get_accessible_files(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    org_id = current_user.organization_id
    files = []
    user_role = current_user.role

    base_query = db.query(ConversationFile).filter(ConversationFile.organization_id == org_id)

    if user_role in ["org_admin", "super_admin"]:
        all_files = base_query.all()
        
        # Batch query user emails for private files to prevent N+1 query problem
        private_user_ids = {f.user_id for f in all_files if f.access_level == "private"}
        user_emails = {}
        if private_user_ids:
            users = db.query(User).filter(User.id.in_(private_user_ids)).all()
            user_emails = {u.id: u.email for u in users}

        for f in all_files:
            owner_email = user_emails.get(f.user_id) if f.access_level == "private" else None
            files.append({
                "id": f.id,
                "filename": f.filename,
                "original_filename": f.original_filename,
                "access_level": f.access_level,
                "department": f.department,
                "team": f.team,
                "uploaded_by": f.user_id,
                "owner_email": owner_email,
                "conversation_id": f.conversation_id,
                "uploaded_at": f.uploaded_at.isoformat(),
                "file_size": f.file_size
            })
    else:
        own_user_id = current_user.id
        own_dept_name = current_user.department.name if current_user.department else None
        own_team_name = current_user.team.name if current_user.team else None

        from sqlalchemy import or_
        conditions = [ConversationFile.access_level == "company"]
        if own_dept_name:
            conditions.append((ConversationFile.access_level == "department") & (ConversationFile.department == own_dept_name))
        if own_team_name:
            conditions.append((ConversationFile.access_level == "team") & (ConversationFile.team == own_team_name))
        conditions.append((ConversationFile.access_level == "private") & (ConversationFile.user_id == own_user_id))

        filtered_files = base_query.filter(or_(*conditions)).all()
        for f in filtered_files:
            files.append({
                "id": f.id,
                "filename": f.filename,
                "original_filename": f.original_filename,
                "access_level": f.access_level,
                "department": f.department,
                "team": f.team,
                "uploaded_by": f.user_id,
                "conversation_id": f.conversation_id,
                "file_size": f.file_size,
                "uploaded_at": f.uploaded_at.isoformat()
            })

    return files


# ------------------------------------------------------------------
# Download by file ID – uses Supabase public URL or direct download
# ------------------------------------------------------------------
@router.get("/download/{file_id}")
async def download_by_id(
    file_id: int,
    request: Request,
    token: str = None,
    inline: bool = False,
    db: Session = Depends(get_db)
):
    # Authentication
    current_user_id = None
    if token:
        from jose import jwt, JWTError
        from config import SECRET_KEY, ALGORITHM
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            token_user_id = payload.get("sub")
            if token_user_id is None:
                raise HTTPException(401, "Invalid token")
            current_user_id = int(token_user_id)
        except JWTError:
            raise HTTPException(401, "Invalid token")
    else:
        from dependencies import get_current_user
        current_user = await get_current_user(request, db)
        current_user_id = current_user.id

    file_record = db.query(ConversationFile).filter(ConversationFile.id == file_id).first()
    if not file_record:
        raise HTTPException(404, "File not found")

    # Access control
    if file_record.user_id != current_user_id:
        user = db.query(User).filter(User.id == current_user_id).first()
        if not user or user.role not in ["org_admin", "super_admin"]:
            raise HTTPException(403, "Access denied")

    # If we have a public URL, redirect (fastest)
    if file_record.gdrive_file_id:
        # Redirect to public URL
        return RedirectResponse(url=file_record.gdrive_file_id)

    # Otherwise, download from Supabase and stream
    if file_record.file_path:
        try:
            file_content = download_file_from_supabase(file_record.file_path)
        except Exception as e:
            raise HTTPException(500, f"Failed to fetch from Supabase: {str(e)}")

        mime_type, _ = mimetypes.guess_type(file_record.original_filename or file_record.filename)
        mime_type = mime_type or 'application/octet-stream'
        disposition = "inline" if inline and mime_type in ['application/pdf', 'text/plain', 'image/jpeg', 'image/png'] else "attachment"
        return StreamingResponse(
            io.BytesIO(file_content),
            media_type=mime_type,
            headers={"Content-Disposition": f"{disposition}; filename=\"{file_record.original_filename or file_record.filename}\""}
        )

    raise HTTPException(404, "File not found")