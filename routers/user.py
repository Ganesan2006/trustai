# routers/user.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional
from dependencies import get_db, get_current_user
from model import User, Department

router = APIRouter(prefix="/api/user", tags=["user"])

class UserProfileUpdate(BaseModel):
    department_id: Optional[int] = None

@router.get("/profile")
def get_profile(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "role": current_user.role,
        "department_id": current_user.department_id,
        "team_id": current_user.team_id,
        "mobile": current_user.mobile,
        "designation": current_user.designation
    }

@router.put("/profile")
def update_profile(
    data: UserProfileUpdate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    if data.department_id is not None:
        if data.department_id > 0:
            dept = db.query(Department).filter(
                Department.id == data.department_id,
                Department.organization_id == current_user.organization_id
            ).first()
            if not dept:
                raise HTTPException(status_code=400, detail="Invalid department_id")
        current_user.department_id = data.department_id if data.department_id > 0 else None
    db.commit()
    return {"message": "Profile updated"}