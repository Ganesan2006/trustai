# routers/files.py
import os
import uuid
import hashlib
import mimetypes
from datetime import datetime
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Request
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from werkzeug.utils import secure_filename
from fastapi.concurrency import run_in_threadpool

from dependencies import get_db, get_current_user
from model import User, Conversation, ConversationFile, Department, Team, DocumentAccessLog
from action import llmProcessor
from qdrant_client import models

router = APIRouter(prefix="/api/files", tags=["files"])
DEBUG = True
# ------------------------------------------------------------------
# Helper to get upload targets based on user role (for frontend dropdowns)
# ------------------------------------------------------------------
@router.get("/upload-targets")
async def get_upload_targets(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Returns departments/teams that the current user can upload to, based on role.
    - Admin: all departments + all teams
    - Department Manager: only teams under their own department (for team scope)
    - Others: empty lists (they use their own department/team, no selection needed)
    """
    org_id = current_user.organization_id
    response = {"departments": [], "teams": []}

    if current_user.role == "org_admin":
        # Admin sees all departments and all teams
        depts = db.query(Department).filter(Department.organization_id == org_id).all()
        teams = db.query(Team).filter(Team.organization_id == org_id).all()
        response["departments"] = [{"id": d.id, "name": d.name} for d in depts]
        response["teams"] = [{"id": t.id, "name": t.name, "department_id": t.department_id} for t in teams]

    elif current_user.role == "department_manager":
        # Manager sees only teams under their own department (for team scope)
        if current_user.department_id:
            teams = db.query(Team).filter(
                Team.organization_id == org_id,
                Team.department_id == current_user.department_id
            ).all()
            response["teams"] = [{"id": t.id, "name": t.name} for t in teams]
        # No department list needed (they use their own department automatically)

    # For team_lead and employee: return empty lists – frontend will not show dropdowns

    return response


# ------------------------------------------------------------------
# Upload endpoint (new logic)
# ------------------------------------------------------------------
@router.post("/upload")
async def upload_file(
    request: Request,
    conversation_id: str = Form(...),
    input_file: UploadFile = File(...),
    scope: str = Form(...),
    target_department_id: int = Form(None),
    target_team_id: int = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # 1. Validate conversation
    conv_id = int(conversation_id)
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
        raise HTTPException(status_code=409, detail="Duplicate file already exists")

    # 4. Determine effective department name and team name for Qdrant payload
    effective_dept_name = None
    effective_team_name = None

    # Helper to fetch department or team by ID (with org check)
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
                raise HTTPException(400, "Admin must select a department for department scope")
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
                raise HTTPException(400, "Admin must select a team for team scope")
            team = get_team_by_id(target_team_id)
            if not team:
                raise HTTPException(400, "Invalid team")
            effective_team_name = team.name
            # Optionally store the department name of the team as well (for context)
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

        else:  # Team lead or employee
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

    # 5. Save physical file
    org_dir = f"uploads/org_{org_short_id}"
    files_dir = os.path.join(org_dir, "files")
    os.makedirs(files_dir, exist_ok=True)

    safe_name = secure_filename(input_file.filename)
    base, ext = os.path.splitext(safe_name)
    file_path = os.path.join(files_dir, safe_name)
    counter = 1
    while os.path.exists(file_path):
        file_path = os.path.join(files_dir, f"{base}_{counter}{ext}")
        counter += 1
    original_path = os.path.abspath(file_path)
    with open(original_path, "wb") as f:
        f.write(content)

    # 6. Process document into chunks
    llm = llmProcessor()
    document_id = str(uuid.uuid4())
    upload_date = datetime.utcnow().isoformat()
    ext_type = os.path.splitext(input_file.filename)[1].lower().lstrip('.')

    docs = await run_in_threadpool(
        llm.load_process_from_path, original_path, document_id, org_short_id, input_file.filename
    )
    if not docs:
        os.remove(original_path)
        raise HTTPException(400, "No content extracted from file")

    # 7. Near‑duplicate detection
    full_text = " ".join([d.page_content for d in docs])[:2048]
    if full_text:
        embedding = llm.embedding_model.embed_query(full_text)
        similar = llm.qdrant.search_by_vector(org_short_id, embedding, limit=5, threshold=0.95)
        if similar:
            os.remove(original_path)
            raise HTTPException(409, "Near‑duplicate document detected")

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
    await run_in_threadpool(llm.add_documents_to_company_with_metadata, org_short_id, docs, metadata_list)

    # 10. Save file record in PostgreSQL
    conv_file = ConversationFile(
        organization_id=current_user.organization_id,
        conversation_id=conv_id,
        user_id=current_user.id,
        filename=os.path.basename(original_path),
        original_filename=input_file.filename,
        file_path=original_path,
        file_size=os.path.getsize(original_path),
        file_hash=file_hash,
        document_id=document_id,
        access_level=scope,
        department=effective_dept_name,
        team=effective_team_name
    )
    db.add(conv_file)
    db.commit()
    db.refresh(conv_file)

    return {"message": "File uploaded successfully", "file_id": conv_file.id}

@router.delete("/document/{document_id}")
async def delete_document(document_id: str, request: Request, current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    files = db.query(ConversationFile).filter(ConversationFile.document_id == document_id, ConversationFile.organization_id == current_user.organization_id).all()
    if not files:
        raise HTTPException(status_code=404)
    if any(f.user_id != current_user.id and current_user.role != "org_admin" for f in files):
        raise HTTPException(status_code=403)

    org_short_id = getattr(request.state, "org_short_id", None)
    if org_short_id:
        col_name = f"org_{org_short_id}"
        filter_cond = models.Filter(must=[models.FieldCondition(key="document_id", match=models.MatchValue(value=document_id))])
        try:
            llm = llmProcessor()
            llm.qdrant.client.delete(collection_name=col_name, points_selector=filter_cond)
        except Exception as e:
            print(f"Qdrant deletion error: {e}")

    for f in files:
        if os.path.exists(f.file_path):
            os.remove(f.file_path)
        db.delete(f)
    db.commit()
    return {"message": "Deleted"}

@router.get("/serve/{user_id}/{conv_id}/{filename}")
async def serve_file(
    user_id: int,
    conv_id: int,
    filename: str,
    request: Request,
    token: str = None,
    db: Session = Depends(get_db)
):
    # Auth logic (unchanged)
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

    # ✅ Find file by document_id (more reliable)
    # First, find the ConversationFile that matches the filename (or original_filename)
    # But since filename may be the stored name, try both.
    file_record = db.query(ConversationFile).filter(
        ConversationFile.filename == filename,
        ConversationFile.user_id == user_id
    ).first()
    
    if not file_record:
        # Fallback: try by original_filename (less secure, but works for legacy)
        file_record = db.query(ConversationFile).filter(
            ConversationFile.original_filename == filename,
            ConversationFile.user_id == user_id
        ).first()
    
    if not file_record:
        raise HTTPException(status_code=404, detail="File not found")

    if not os.path.exists(file_record.file_path):
        raise HTTPException(status_code=404, detail="File missing on disk")

    # Log access (with organization_id)
    try:
        access_log = DocumentAccessLog(
            organization_id=file_record.organization_id,
            file_id=file_record.id,
            user_id=current_user_id,
            action='view',
            ip_address=request.client.host,
            user_agent=request.headers.get('user-agent', '')
        )
        db.add(access_log)
        db.commit()
    except Exception as e:
        db.rollback()
        print(f"Logging error: {e}")

    mime_type, _ = mimetypes.guess_type(file_record.original_filename or filename)
    if not mime_type:
        mime_type = 'application/octet-stream'
    return FileResponse(
        file_record.file_path,
        media_type=mime_type,
        filename=file_record.original_filename or filename,
        headers={"Content-Disposition": f"inline; filename=\"{file_record.original_filename or filename}\""}
    )


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
        for f in all_files:
            owner_email = None
            if f.access_level == "private":
                owner = db.query(User).filter(User.id == f.user_id).first()
                owner_email = owner.email if owner else None
            files.append({
                "id": f.id,
                "filename": f.filename,                       # stored name
                "original_filename": f.original_filename,
                "access_level": f.access_level,
                "department": f.department,
                "team": f.team,
                "uploaded_by": f.user_id,
                "owner_email": owner_email,
                "conversation_id": f.conversation_id,         # ✅ ADD THIS
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
                "conversation_id": f.conversation_id,         # ✅ ALREADY THERE
                "file_size": f.file_size,
                "uploaded_at": f.uploaded_at.isoformat()
            })

    return files
@router.get("/download/{file_id}")
async def download_by_id(
    file_id: int,
    request: Request,
    token: str = None,
    inline: bool = False,
    db: Session = Depends(get_db)
):
    # Authentication (same as serve_file)
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
    if file_record.user_id != current_user_id:
        user = db.query(User).filter(User.id == current_user_id).first()
        if user.role not in ["org_admin", "super_admin"]:
            raise HTTPException(403, "Access denied")

    if not os.path.exists(file_record.file_path):
        raise HTTPException(404, "File missing on disk")

    mime_type, _ = mimetypes.guess_type(file_record.original_filename or file_record.filename)
    if not mime_type:
        mime_type = 'application/octet-stream'
    disposition = "inline" if inline and mime_type in ['application/pdf', 'text/plain', 'image/jpeg', 'image/png'] else "attachment"
    
    return FileResponse(
        file_record.file_path,
        media_type=mime_type,
        filename=file_record.original_filename or file_record.filename,
        headers={"Content-Disposition": f"{disposition}; filename=\"{file_record.original_filename or file_record.filename}\""}
    )