# routers/admin_analytics.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, desc, and_
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from dependencies import get_db, get_current_user
from model import (
    User, Organization, Department, Team, ConversationFile,
    QueryLog, RetrievalLog, FeedbackLog, DocumentAccessLog,
    ApiKey, UserModelAssignment, ProviderEnum, KnowledgeGap
)

router = APIRouter(prefix="/admin/analytics", tags=["admin analytics"])

def require_admin(current_user: User = Depends(get_current_user)):
    if current_user.role not in ["org_admin", "super_admin"]:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user

# ==================== Overview (Home) ====================
@router.get("/overview")
def get_overview(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    period: str = Query("today", pattern="^(today|week|month)$")
):
    org_id = admin.organization_id
    now = datetime.utcnow()
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
    elif period == "week":
        start_date = now - timedelta(days=7)
    else:
        start_date = now - timedelta(days=30)

    total_users = db.query(User).filter(User.organization_id == org_id).count()
    total_docs = db.query(ConversationFile).filter(ConversationFile.organization_id == org_id).count()
    total_conversations = db.query(QueryLog).filter(QueryLog.organization_id == org_id).distinct(QueryLog.conversation_id).count()
    queries_today = db.query(QueryLog).filter(QueryLog.organization_id == org_id, QueryLog.created_at >= start_date).count()
    active_users = db.query(User).join(QueryLog).filter(
        User.organization_id == org_id,
        QueryLog.created_at >= start_date
    ).distinct().count()
    avg_confidence = db.query(func.avg(QueryLog.confidence_score)).filter(QueryLog.organization_id == org_id).scalar() or 0
    total_cost = db.query(func.sum(QueryLog.estimated_cost_usd)).filter(QueryLog.organization_id == org_id).scalar() or 0
    storage_used = db.query(func.sum(ConversationFile.file_size)).filter(ConversationFile.organization_id == org_id).scalar() or 0
    storage_mb = storage_used / (1024 * 1024)

    # Query trend (last 7 days)
    trend = []
    for i in range(6, -1, -1):
        day = now - timedelta(days=i)
        day_start = day.replace(hour=0, minute=0, second=0)
        day_end = day_start + timedelta(days=1)
        count = db.query(QueryLog).filter(
            QueryLog.organization_id == org_id,
            QueryLog.created_at >= day_start,
            QueryLog.created_at < day_end
        ).count()
        trend.append({"date": day.strftime("%a"), "count": count})

    # Cost by provider – unavailable, return empty list
    cost_by_provider = []

    return {
        "total_users": total_users,
        "total_documents": total_docs,
        "total_conversations": total_conversations,
        "queries_today": queries_today,
        "active_users": active_users,
        "avg_confidence": round(avg_confidence, 2),
        "total_cost": round(total_cost, 2),
        "storage_gb": round(storage_mb / 1024, 2),
        "trend": trend,
        "cost_by_provider": cost_by_provider
    }

# ==================== Users Dashboard ====================
@router.get("/users")
def get_users_analytics(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    department_id: Optional[int] = None,
    team_id: Optional[int] = None,
    role: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 50
):
    org_id = admin.organization_id
    query = db.query(User).filter(User.organization_id == org_id)
    if department_id:
        query = query.filter(User.department_id == department_id)
    if team_id:
        query = query.filter(User.team_id == team_id)
    if role:
        query = query.filter(User.role == role)
    if search:
        query = query.filter(User.name.ilike(f"%{search}%") | User.email.ilike(f"%{search}%"))

    total = query.count()
    users = query.limit(limit).all()

    user_list = []
    for u in users:
        query_count = db.query(QueryLog).filter(QueryLog.user_id == u.id).count()
        last_login = None
        user_list.append({
            "id": u.id,
            "name": u.name,
            "email": u.email,
            "department": u.department.name if u.department else None,
            "team": u.team.name if u.team else None,
            "role": u.role,
            "queries": query_count,
            "last_login": last_login,
            "status": "active"
        })

    # Department wise counts
    dept_counts = db.query(
        Department.name,
        func.count(User.id).label("count")
    ).outerjoin(User, User.department_id == Department.id).filter(
        Department.organization_id == org_id
    ).group_by(Department.name).all()
    dept_wise = [{"name": d[0], "count": d[1]} for d in dept_counts]

    # Most active users (by query count)
    active_users = db.query(
        User.id, User.name, func.count(QueryLog.id).label("qcount")
    ).join(QueryLog).filter(User.organization_id == org_id).group_by(User.id).order_by(desc("qcount")).limit(5).all()
    most_active = [{"name": u[1], "queries": u[2]} for u in active_users]

    return {
        "total": total,
        "users": user_list,
        "department_wise": dept_wise,
        "most_active": most_active,
        "roles": {"admins": db.query(User).filter(User.organization_id == org_id, User.role == "org_admin").count(),
                  "employees": db.query(User).filter(User.organization_id == org_id, User.role == "employee").count()}
    }

# ==================== Documents Dashboard ====================
@router.get("/documents")
def get_documents_analytics(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    department_id: Optional[int] = None,
    team_id: Optional[int] = None
):
    org_id = admin.organization_id
    query = db.query(ConversationFile).filter(ConversationFile.organization_id == org_id)

    total_docs = query.count()
    total_chunks = db.query(func.sum(ConversationFile.file_size)).filter(ConversationFile.organization_id == org_id).scalar() or 0
    storage_mb = total_chunks / (1024 * 1024)
    duplicates = db.query(ConversationFile.file_hash).filter(ConversationFile.organization_id == org_id).group_by(ConversationFile.file_hash).having(func.count() > 1).count()

    private = query.filter(ConversationFile.access_level == "private").count()
    department_files = query.filter(ConversationFile.access_level == "department").count()
    team_files = query.filter(ConversationFile.access_level == "team").count()
    company_files = query.filter(ConversationFile.access_level == "company").count()

    recent = query.order_by(desc(ConversationFile.uploaded_at)).limit(10).all()
    recent_uploads = [{"name": f.original_filename or f.filename, "department": f.department, "team": f.team, "uploaded_at": f.uploaded_at.isoformat()} for f in recent]

    # File type breakdown
    file_types = db.query(func.split_part(ConversationFile.original_filename, '.', -1).label("ext"), func.count()).filter(ConversationFile.organization_id == org_id).group_by("ext").all()
    file_type_counts = [{"type": t[0].upper(), "count": t[1]} for t in file_types]

    # Department wise file counts (by department name from metadata)
    dept_files_count = db.query(
        ConversationFile.department,
        func.count(ConversationFile.id).label("count")
    ).filter(ConversationFile.organization_id == org_id, ConversationFile.department.isnot(None)).group_by(ConversationFile.department).all()
    dept_wise_files = [{"department": d[0], "count": d[1]} for d in dept_files_count]

    # Largest files
    largest = query.order_by(desc(ConversationFile.file_size)).limit(5).all()
    largest_files = [{"name": f.original_filename or f.filename, "size_mb": round(f.file_size/(1024*1024), 2)} for f in largest]

    missing_dept = query.filter(ConversationFile.access_level == "department", ConversationFile.department == None).count()
    missing_team = query.filter(ConversationFile.access_level == "team", ConversationFile.team == None).count()

    return {
        "total_documents": total_docs,
        "storage_gb": round(storage_mb / 1024, 2),
        "duplicate_files": duplicates,
        "private_files": private,
        "department_files": department_files,
        "team_files": team_files,
        "company_files": company_files,
        "recent_uploads": recent_uploads,
        "file_types": file_type_counts,
        "department_wise": dept_wise_files,
        "largest_files": largest_files,
        "missing_metadata": {"no_department": missing_dept, "no_team": missing_team, "no_description": 0}
    }

# ==================== AI Usage Dashboard ====================
@router.get("/ai-usage")
def get_ai_usage(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db),
    period: str = Query("today", pattern="^(today|week|month)$")
):
    org_id = admin.organization_id
    now = datetime.utcnow()
    if period == "today":
        start_date = now.replace(hour=0, minute=0, second=0)
    elif period == "week":
        start_date = now - timedelta(days=7)
    else:
        start_date = now - timedelta(days=30)

    queries = db.query(QueryLog).filter(QueryLog.organization_id == org_id, QueryLog.created_at >= start_date)
    total_queries = queries.count()
    avg_response_time = queries.with_entities(func.avg(QueryLog.total_time_ms)).scalar() or 0
    avg_confidence = queries.with_entities(func.avg(QueryLog.confidence_score)).scalar() or 0
    total_cost = queries.with_entities(func.sum(QueryLog.estimated_cost_usd)).scalar() or 0

    hourly = []
    for hour in range(0, 24):
        h_start = now.replace(hour=hour, minute=0, second=0)
        h_end = h_start + timedelta(hours=1)
        count = db.query(QueryLog).filter(
            QueryLog.organization_id == org_id,
            QueryLog.created_at >= h_start,
            QueryLog.created_at < h_end
        ).count()
        hourly.append({"hour": hour, "count": count})

    top_questions = db.query(
        QueryLog.question,
        func.count().label("count")
    ).filter(QueryLog.organization_id == org_id).group_by(QueryLog.question).order_by(desc("count")).limit(10).all()
    top_q = [{"question": q[0], "count": q[1]} for q in top_questions]

    top_depts = db.query(
        Department.name,
        func.count(QueryLog.id).label("count")
    ).join(User, User.department_id == Department.id).join(QueryLog, QueryLog.user_id == User.id).filter(
        Department.organization_id == org_id
    ).group_by(Department.name).order_by(desc("count")).limit(5).all()
    dept_queries = [{"department": d[0], "queries": d[1]} for d in top_depts]

    input_tokens = queries.with_entities(func.sum(QueryLog.input_tokens)).scalar() or 0
    output_tokens = queries.with_entities(func.sum(QueryLog.output_tokens)).scalar() or 0

    # cost_by_provider removed
    provider_costs = []

    return {
        "total_queries": total_queries,
        "avg_response_time_ms": round(avg_response_time, 2),
        "avg_confidence": round(avg_confidence, 2),
        "total_cost": round(total_cost, 2),
        "hourly_queries": hourly,
        "top_questions": top_q,
        "top_departments": dept_queries,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_by_provider": provider_costs
    }

# ==================== Retrieval Dashboard ====================
@router.get("/retrieval")
def get_retrieval_analytics(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    org_id = admin.organization_id
    avg_chunks = db.query(func.avg(QueryLog.retrieved_chunks)).filter(QueryLog.organization_id == org_id).scalar() or 0
    avg_sim = db.query(func.avg(RetrievalLog.similarity_score)).join(QueryLog).filter(QueryLog.organization_id == org_id).scalar() or 0
    failed = db.query(QueryLog).filter(QueryLog.organization_id == org_id, QueryLog.retrieved_chunks == 0).count()
    total_queries = db.query(QueryLog).filter(QueryLog.organization_id == org_id).count()
    coverage = round((total_queries - failed) / total_queries * 100, 1) if total_queries else 0

    sim_buckets = [(0, 0.7), (0.7, 0.8), (0.8, 0.9), (0.9, 1.0)]
    sim_dist = []
    for low, high in sim_buckets:
        count = db.query(RetrievalLog).join(QueryLog).filter(
            QueryLog.organization_id == org_id,
            RetrievalLog.similarity_score >= low,
            RetrievalLog.similarity_score < high
        ).count()
        sim_dist.append({"range": f"{low}-{high}", "count": count})

    top_docs = db.query(
        RetrievalLog.document_id,
        func.count().label("count")
    ).join(QueryLog).filter(QueryLog.organization_id == org_id).group_by(RetrievalLog.document_id).order_by(desc("count")).limit(10).all()
    doc_names = {}
    for doc_id, _ in top_docs:
        f = db.query(ConversationFile).filter(ConversationFile.document_id == doc_id).first()
        if f:
            doc_names[doc_id] = f.original_filename or f.filename
    top_retrieved = [{"document": doc_names.get(d[0], d[0]), "count": d[1]} for d in top_docs]

    chunk_counts = db.query(
        ConversationFile.document_id,
        ConversationFile.original_filename,
        func.count(RetrievalLog.id).label("chunks_retrieved")
    ).outerjoin(RetrievalLog, RetrievalLog.document_id == ConversationFile.document_id).filter(
        ConversationFile.organization_id == org_id
    ).group_by(ConversationFile.document_id, ConversationFile.original_filename).order_by(desc("chunks_retrieved")).limit(5).all()
    chunk_dist = [{"document": c[1] or c[0], "chunks": c[2]} for c in chunk_counts]

    latencies = db.query(QueryLog.retrieval_time_ms).filter(QueryLog.organization_id == org_id, QueryLog.retrieval_time_ms.isnot(None)).all()
    if latencies:
        vals = sorted([l[0] for l in latencies])
        p95 = vals[int(len(vals)*0.95)] if vals else 0
        p99 = vals[int(len(vals)*0.99)] if vals else 0
        avg_lat = sum(vals)/len(vals) if vals else 0
    else:
        avg_lat = p95 = p99 = 0

    return {
        "avg_retrieved_chunks": round(avg_chunks, 1),
        "avg_similarity": round(avg_sim, 2),
        "failed_retrievals": failed,
        "knowledge_coverage": coverage,
        "similarity_distribution": sim_dist,
        "top_retrieved_documents": top_retrieved,
        "chunk_distribution": chunk_dist,
        "retrieval_latency_ms": {"avg": round(avg_lat, 2), "p95": round(p95, 2), "p99": round(p99, 2)}
    }

# ==================== Knowledge Gap Dashboard ====================
@router.get("/knowledge-gaps")
def get_knowledge_gaps(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    org_id = admin.organization_id
    gaps = db.query(KnowledgeGap).filter(KnowledgeGap.organization_id == org_id).order_by(desc(KnowledgeGap.occurred_count)).all()
    unresolved = [g for g in gaps if not g.resolved]
    resolved = [g for g in gaps if g.resolved]

    top_missing = [{"question": g.question, "occurred": g.occurred_count} for g in unresolved[:5]]

    return {
        "total_gaps": len(gaps),
        "resolved": len(resolved),
        "pending": len(unresolved),
        "top_missing_topics": top_missing,
        "gaps": [{"question": g.question, "occurred": g.occurred_count, "resolved": g.resolved, "last_seen": g.last_occurred.isoformat()} for g in gaps]
    }

# ==================== Feedback Dashboard ====================
@router.get("/feedback")
def get_feedback_analytics(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    org_id = admin.organization_id
    feedbacks = db.query(FeedbackLog).join(QueryLog).filter(QueryLog.organization_id == org_id).all()
    pos = len([f for f in feedbacks if f.rating == "helpful"])
    neg = len([f for f in feedbacks if f.rating == "not_helpful"])
    avg_rating = (pos / (pos+neg) * 5) if (pos+neg) else 0

    worst = db.query(QueryLog).filter(
        QueryLog.organization_id == org_id,
        QueryLog.user_feedback == "not_helpful"
    ).order_by(QueryLog.confidence_score).limit(10).all()
    worst_queries = [{"question": q.question, "confidence": q.confidence_score, "rating": q.user_feedback} for q in worst]

    complaint_counts = db.query(
        QueryLog.question,
        func.count().label("count")
    ).filter(
        QueryLog.organization_id == org_id,
        QueryLog.user_feedback == "not_helpful"
    ).group_by(QueryLog.question).order_by(desc("count")).limit(5).all()
    top_complaints = [{"question": q[0], "count": q[1]} for q in complaint_counts]

    trend = []
    for i in range(5, -1, -1):
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0) - timedelta(days=30*i)
        month_end = month_start + timedelta(days=32)
        helpful = db.query(FeedbackLog).join(QueryLog).filter(
            QueryLog.organization_id == org_id,
            FeedbackLog.rating == "helpful",
            FeedbackLog.created_at >= month_start,
            FeedbackLog.created_at < month_end
        ).count()
        not_helpful = db.query(FeedbackLog).join(QueryLog).filter(
            QueryLog.organization_id == org_id,
            FeedbackLog.rating == "not_helpful",
            FeedbackLog.created_at >= month_start,
            FeedbackLog.created_at < month_end
        ).count()
        trend.append({"month": month_start.strftime("%b"), "helpful": helpful, "not_helpful": not_helpful})

    return {
        "positive": pos,
        "negative": neg,
        "average_rating": round(avg_rating, 2),
        "worst_queries": worst_queries,
        "top_complaints": top_complaints,
        "trend": trend
    }

# ==================== Security Dashboard ====================
@router.get("/security")
def get_security_analytics(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    org_id = admin.organization_id
    accesses = db.query(DocumentAccessLog).join(ConversationFile).filter(ConversationFile.organization_id == org_id).order_by(desc(DocumentAccessLog.created_at)).limit(100).all()
    access_logs = [{
        "user": db.query(User).get(log.user_id).name if log.user_id else "Unknown",
        "file": db.query(ConversationFile).get(log.file_id).original_filename if log.file_id else "Unknown",
        "action": log.action,
        "ip": log.ip_address,
        "timestamp": log.created_at.isoformat()
    } for log in accesses]

    most_accessed = db.query(
        ConversationFile.original_filename,
        func.count(DocumentAccessLog.id).label("access_count")
    ).join(DocumentAccessLog, DocumentAccessLog.file_id == ConversationFile.id).filter(
        ConversationFile.organization_id == org_id
    ).group_by(ConversationFile.original_filename).order_by(desc("access_count")).limit(10).all()
    top_accessed = [{"file": f[0], "count": f[1]} for f in most_accessed]

    failed_access = 0
    private_access = db.query(
        ConversationFile.original_filename,
        func.count(DocumentAccessLog.id).label("access_count")
    ).join(DocumentAccessLog, DocumentAccessLog.file_id == ConversationFile.id).filter(
        ConversationFile.organization_id == org_id,
        ConversationFile.access_level == "private"
    ).group_by(ConversationFile.original_filename).order_by(desc("access_count")).all()
    private_stats = [{"file": f[0], "access_count": f[1]} for f in private_access]

    return {
        "recent_access_logs": access_logs[:50],
        "most_accessed_documents": top_accessed,
        "failed_access_attempts": failed_access,
        "private_documents_access": private_stats
    }

# ==================== Organization Dashboard ====================
@router.get("/organization")
def get_organization_analytics(
    admin: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    org = db.query(Organization).filter(Organization.id == admin.organization_id).first()
    if not org:
        raise HTTPException(404, "Organization not found")

    dept_count = db.query(Department).filter(Department.organization_id == org.id).count()
    team_count = db.query(Team).filter(Team.organization_id == org.id).count()
    user_count = db.query(User).filter(User.organization_id == org.id).count()

    api_keys = db.query(ApiKey).filter(ApiKey.organization_id == org.id).all()
    api_status = [{"provider": k.provider.value, "active": k.is_active} for k in api_keys]

    assignments = db.query(UserModelAssignment).join(User).filter(User.organization_id == org.id).all()
    assigned_models = {}
    for a in assignments:
        if a.provider.value not in assigned_models:
            assigned_models[a.provider.value] = set()
        assigned_models[a.provider.value].add(a.model_name)
    model_list = [{"provider": p, "models": list(m)} for p, m in assigned_models.items()]

    return {
        "name": org.name,
        "industry": org.industry,
        "employees": user_count,
        "departments": dept_count,
        "teams": team_count,
        "api_providers": api_status,
        "assigned_models": model_list
    }