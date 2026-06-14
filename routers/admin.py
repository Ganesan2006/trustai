# routers/admin.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from dependencies import get_db, get_current_user
from model import User, ApiKey, UserModelAssignment, ProviderEnum, ConversationFile, Department, Team
from utils.encryption import encrypt_api_key

router = APIRouter(prefix="/admin", tags=["admin"])

def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in ["org_admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# ---------- Pydantic Models ----------
class UserUpdateRequest(BaseModel):
    role: Optional[str] = None
    department_id: Optional[int] = None
    team_id: Optional[int] = None

class ApiKeyCreate(BaseModel):
    provider: ProviderEnum
    api_key: str
    description: str = ""

class ModelAssignmentCreate(BaseModel):
    user_id: int
    provider: ProviderEnum
    model_name: str

# ==================== USERS ====================
@router.get("/users")
def get_users(admin: User = Depends(require_admin), db: Session = Depends(get_db)):
    users = db.query(User).filter(User.organization_id == admin.organization_id).all()
    return {
        "users": [{
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "role": u.role,
            "department_id": u.department_id,
            "team_id": u.team_id,
            "mobile": u.mobile,
            "designation": u.designation
        } for u in users]
    }

@router.put("/users/{user_id}")
def update_user(
    user_id: int,
    data: UserUpdateRequest,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == user_id, User.organization_id == admin.organization_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.role is not None:
        user.role = data.role
    if data.department_id is not None:
        if data.department_id:
            dept = db.query(Department).filter(Department.id == data.department_id, Department.organization_id == admin.organization_id).first()
            if not dept:
                raise HTTPException(status_code=400, detail="Invalid department")
        user.department_id = data.department_id
    if data.team_id is not None:
        if data.team_id:
            team = db.query(Team).filter(Team.id == data.team_id, Team.organization_id == admin.organization_id).first()
            if not team:
                raise HTTPException(status_code=400, detail="Invalid team")
        user.team_id = data.team_id
    db.commit()
    return {"message": "User updated"}

# ==================== DEPARTMENTS ====================
@router.get("/departments")
def get_departments(current_user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    depts = db.query(Department).filter(Department.organization_id == current_user.organization_id).all()
    return [{"id": d.id, "name": d.name, "description": d.description} for d in depts]

@router.post("/departments")
def create_department(
    data: dict,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    name = data.get("name")
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    existing = db.query(Department).filter(Department.organization_id == admin.organization_id, Department.name == name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Department already exists")
    dept = Department(organization_id=admin.organization_id, name=name, description=data.get("description"))
    db.add(dept)
    db.commit()
    db.refresh(dept)
    return {"id": dept.id, "name": dept.name, "description": dept.description}

@router.put("/departments/{dept_id}")
def update_department(
    dept_id: int,
    data: dict,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    dept = db.query(Department).filter(Department.id == dept_id, Department.organization_id == admin.organization_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    dept.name = data.get("name", dept.name)
    dept.description = data.get("description", dept.description)
    db.commit()
    return {"message": "Department updated"}

@router.delete("/departments/{dept_id}")
def delete_department(
    dept_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    dept = db.query(Department).filter(Department.id == dept_id, Department.organization_id == admin.organization_id).first()
    if not dept:
        raise HTTPException(status_code=404, detail="Department not found")
    db.delete(dept)
    db.commit()
    return {"message": "Department deleted"}

# ==================== TEAMS ====================
@router.get("/teams")
def get_teams(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
    department_id: Optional[int] = None
):
    q = db.query(Team).filter(Team.organization_id == current_user.organization_id)
    if department_id:
        q = q.filter(Team.department_id == department_id)
    teams = q.all()
    return [{"id": t.id, "name": t.name, "department_id": t.department_id, "description": t.description} for t in teams]

@router.post("/teams")
def create_team(
    data: dict,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    name = data.get("name")
    dept_id = data.get("department_id")
    if not name:
        raise HTTPException(status_code=400, detail="Name required")
    if dept_id:
        dept = db.query(Department).filter(Department.id == dept_id, Department.organization_id == admin.organization_id).first()
        if not dept:
            raise HTTPException(status_code=400, detail="Invalid department")
    existing = db.query(Team).filter(Team.organization_id == admin.organization_id, Team.name == name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Team already exists")
    team = Team(organization_id=admin.organization_id, department_id=dept_id, name=name, description=data.get("description"))
    db.add(team)
    db.commit()
    db.refresh(team)
    return {"id": team.id, "name": team.name, "department_id": team.department_id, "description": team.description}

@router.put("/teams/{team_id}")
def update_team(
    team_id: int,
    data: dict,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id, Team.organization_id == admin.organization_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    team.name = data.get("name", team.name)
    team.description = data.get("description", team.description)
    if "department_id" in data:
        dept_id = data["department_id"]
        if dept_id:
            dept = db.query(Department).filter(Department.id == dept_id, Department.organization_id == admin.organization_id).first()
            if not dept:
                raise HTTPException(status_code=400, detail="Invalid department")
        team.department_id = dept_id
    db.commit()
    return {"message": "Team updated"}

@router.delete("/teams/{team_id}")
def delete_team(
    team_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    team = db.query(Team).filter(Team.id == team_id, Team.organization_id == admin.organization_id).first()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    db.delete(team)
    db.commit()
    return {"message": "Team deleted"}

# ==================== API KEYS ====================
@router.post("/api-keys")
def add_api_key(
    data: ApiKeyCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    encrypted = encrypt_api_key(data.api_key)
    key = ApiKey(
        organization_id=admin.organization_id,
        provider=data.provider,
        api_key_encrypted=encrypted,
        description=data.description,
        is_active=True
    )
    db.add(key)
    db.commit()
    return {"message": "API key added", "id": key.id}

@router.get("/api-keys")
def list_api_keys(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    keys = db.query(ApiKey).filter(ApiKey.organization_id == admin.organization_id).all()
    return {
        "keys": [{
            "id": k.id,
            "provider": k.provider.value,
            "description": k.description,
            "is_active": k.is_active,
            "created_at": k.created_at.isoformat()
        } for k in keys]
    }

@router.delete("/api-keys/{key_id}")
def delete_api_key(
    key_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    key = db.query(ApiKey).filter(ApiKey.id == key_id, ApiKey.organization_id == admin.organization_id).first()
    if not key:
        raise HTTPException(status_code=404, detail="API key not found")
    db.delete(key)
    db.commit()
    return {"message": "API key deleted"}

# ==================== MODEL ASSIGNMENTS ====================
@router.post("/model-assignments")
def assign_model(
    data: ModelAssignmentCreate,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.id == data.user_id, User.organization_id == admin.organization_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    existing = db.query(UserModelAssignment).filter(
        UserModelAssignment.user_id == data.user_id,
        UserModelAssignment.provider == data.provider
    ).first()
    if existing:
        existing.model_name = data.model_name
        existing.is_active = True
    else:
        db.add(UserModelAssignment(user_id=data.user_id, provider=data.provider, model_name=data.model_name))
    db.commit()
    return {"message": "Model assigned"}

@router.get("/model-assignments")
def list_assignments(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    assigns = db.query(UserModelAssignment).join(User).filter(User.organization_id == admin.organization_id).all()
    return {
        "assignments": [{
            "id": a.id,
            "user_id": a.user_id,
            "user_name": a.user.name,
            "provider": a.provider.value,
            "model_name": a.model_name,
            "is_active": a.is_active
        } for a in assigns]
    }

@router.delete("/model-assignments/{assign_id}")
def delete_assignment(
    assign_id: int,
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    assign = db.query(UserModelAssignment).filter(
        UserModelAssignment.id == assign_id
    ).join(User).filter(User.organization_id == admin.organization_id).first()
    if not assign:
        raise HTTPException(status_code=404, detail="Assignment not found")
    db.delete(assign)
    db.commit()
    return {"message": "Assignment deleted"}

# ==================== FILES ====================
@router.get("/files")
def get_all_files(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    user_id: Optional[int] = None
):
    q = db.query(ConversationFile).filter(ConversationFile.organization_id == admin.organization_id)
    if user_id:
        q = q.filter(ConversationFile.user_id == user_id)
    files = q.all()
    return {
        "files": [{
            "id": f.id,
            "filename": f.original_filename or f.filename,
            "uploaded_by": f.user_id,
            "uploaded_at": f.uploaded_at.isoformat(),
            "file_size": f.file_size,
            "access_level": f.access_level
        } for f in files]
    }