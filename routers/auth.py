# routers/auth.py
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import jwt
from werkzeug.security import generate_password_hash, check_password_hash
from config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES, get_db
from model import Organization, User, Department, Team

router = APIRouter(prefix="/api/auth", tags=["auth"])

class LoginData(BaseModel):
    email: str
    password: str

class SignupData(BaseModel):
    name: str
    email: EmailStr
    password: str
    org_id: str
    mobile: str = None
    designation: str = None
    department_id: int = None
    model_config = {"extra": "ignore"}  # <-- IGNORE extra fields

class OrgRegistrationData(BaseModel):
    company_name: str
    company_email: EmailStr
    company_phone: str = ""
    company_website: str = ""
    industry: str = ""
    company_size: str = ""
    country: str = ""
    state: str = ""
    city: str = ""
    address: str = ""
    domain: str
    admin_name: str
    admin_email: EmailStr
    admin_mobile: str = ""
    admin_password: str
    admin_role: str = "admin"
    confirm_password: str
    departments: list = []
    teams: list = []

def create_access_token(data: dict) -> str:
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode = {"exp": expire, **data}
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

@router.post("/login")
def login(data: LoginData, db: Session = Depends(get_db)):
    domain = data.email.split('@')[-1].lower()
    org = db.query(Organization).filter(Organization.domain == domain, Organization.status == "active").first()
    if not org:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = db.query(User).filter(User.email == data.email, User.organization_id == org.id).first()
    if not user or not user.check_password(data.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    token = create_access_token({
        "sub": str(user.id),
        "org_short_id": org.org_id,
        "role": user.role
    })
    return {"access_token": token, "token_type": "bearer", "user": {"id": user.id, "name": user.name, "email": user.email, "role": user.role}}

@router.post("/signup")
def signup(data: SignupData, db: Session = Depends(get_db)):
    org = db.query(Organization).filter(Organization.org_id == data.org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    if not data.email.endswith(f"@{org.domain}"):
        raise HTTPException(status_code=403, detail=f"Email must end with @{org.domain}")
    existing = db.query(User).filter(User.email == data.email).first()
    if existing:
        raise HTTPException(status_code=409, detail="Email already registered")
    if data.department_id:
        dept = db.query(Department).filter(Department.id == data.department_id, Department.organization_id == org.id).first()
        if not dept:
            raise HTTPException(status_code=400, detail="Invalid department")
    hashed = generate_password_hash(data.password)
    new_user = User(
        organization_id=org.id,
        name=data.name,
        email=data.email,
        password_hash=hashed,
        role="employee",
        mobile=data.mobile,
        designation=data.designation,
        department_id=data.department_id
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    token = create_access_token({"sub": str(new_user.id), "org_short_id": org.org_id, "role": new_user.role})
    return {"access_token": token, "token_type": "bearer", "user": {"id": new_user.id, "name": new_user.name, "email": new_user.email, "role": new_user.role}}

# Public endpoint to fetch departments during signup
@router.get("/organizations/{org_short_id}/departments")
def get_org_departments(org_short_id: str, db: Session = Depends(get_db)):
    org = db.query(Organization).filter(Organization.org_id == org_short_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    depts = db.query(Department).filter(Department.organization_id == org.id).all()
    return [{"id": d.id, "name": d.name} for d in depts]

@router.post("/org/register")
def org_register(data: OrgRegistrationData, db: Session = Depends(get_db)):
    existing = db.query(Organization).filter((Organization.name == data.company_name) | (Organization.domain == data.domain)).first()
    if existing:
        raise HTTPException(status_code=409, detail="Organization name or domain already taken")
    org_id_str = data.domain.split('.')[0]
    counter = 1
    while db.query(Organization).filter(Organization.org_id == org_id_str).first():
        org_id_str = f"{org_id_str}{counter}"
        counter += 1
    new_org = Organization(
        org_id=org_id_str,
        name=data.company_name,
        email=data.company_email,
        phone=data.company_phone,
        website=data.company_website,
        industry=data.industry,
        size=data.company_size,
        country=data.country,
        state=data.state,
        city=data.city,
        address=data.address,
        domain=data.domain,
        status="active"
    )
    db.add(new_org)
    db.commit()
    db.refresh(new_org)

    hashed = generate_password_hash(data.admin_password)
    admin = User(
        organization_id=new_org.id,
        name=data.admin_name,
        email=data.admin_email,
        password_hash=hashed,
        role="org_admin",
        mobile=data.admin_mobile,
        designation=data.admin_role
    )
    db.add(admin)
    db.flush()

    dept_map = {}
    for d in data.departments:
        if d.get("name"):
            dept = Department(organization_id=new_org.id, name=d["name"], description=d.get("description"))
            db.add(dept)
            db.flush()
            dept_map[d["name"]] = dept.id
    for t in data.teams:
        if t.get("name") and t.get("department_name") in dept_map:
            team = Team(organization_id=new_org.id, department_id=dept_map[t["department_name"]], name=t["name"], description=t.get("description"))
            db.add(team)
    db.commit()
    db.refresh(admin)

    token = create_access_token({"sub": str(admin.id), "org_short_id": new_org.org_id, "role": admin.role})
    return {"access_token": token, "token_type": "bearer", "user": {"id": admin.id, "name": admin.name, "email": admin.email, "role": admin.role}}