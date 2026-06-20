# model.py
from sqlalchemy import Column, Integer, String, DateTime, Text, Boolean, Float, ForeignKey, Enum, Index, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship
from datetime import datetime
import enum

Base = declarative_base()

class ProviderEnum(str, enum.Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"
    GOOGLE = "google"
    OLLAMA = "ollama"

class Organization(Base):
    __tablename__ = "organizations"
    id = Column(Integer, primary_key=True)
    org_id = Column(String(50), unique=True, nullable=False)
    name = Column(String(100), nullable=False)
    email = Column(String(100), nullable=False)
    phone = Column(String(20))
    website = Column(String(200))
    industry = Column(String(100))
    size = Column(String(20))
    country = Column(String(100))
    state = Column(String(100))
    city = Column(String(100))
    address = Column(Text)
    domain = Column(String(100), unique=True, nullable=False)
    status = Column(String(20), default="active")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    deleted_at = Column(DateTime, nullable=True)

class Department(Base):
    __tablename__ = "departments"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_org_dept"),)

class Team(Base):
    __tablename__ = "teams"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(100), nullable=False)
    description = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("organization_id", "name", name="uq_org_team"),)

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    email = Column(String(100), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    password_hash = Column(String(256), nullable=False)
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    role = Column(String(50), default="employee")
    mobile = Column(String(20))
    designation = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    department = relationship("Department", foreign_keys=[department_id])
    team = relationship("Team", foreign_keys=[team_id])

    def set_password(self, password: str):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        from werkzeug.security import check_password_hash
        return check_password_hash(self.password_hash, password)

class Conversation(Base):
    __tablename__ = "conversations"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(100), default="New chat")
    department_id = Column(Integer, ForeignKey("departments.id", ondelete="SET NULL"), nullable=True)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="SET NULL"), nullable=True)
    scope = Column(String(50), default="private")
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    department = relationship("Department", foreign_keys=[department_id])
    team = relationship("Team", foreign_keys=[team_id])
    __table_args__ = (Index("idx_conv_user", "user_id"), Index("idx_conv_org", "organization_id"))

class Message(Base):
    __tablename__ = "messages"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    role = Column(String(20), nullable=False)
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=datetime.utcnow, index=True)

class ConversationFile(Base):
    __tablename__ = "conversation_files"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    filename = Column(String(255), nullable=False)
    original_filename = Column(String(255))
    access_level = Column(String(20), default="private")
    file_path = Column(String(512), nullable=False)
    file_size = Column(Integer)
    file_hash = Column(String(64))
    department = Column(String(100), nullable=True)   # department name
    team = Column(String(100), nullable=True)
    gdrive_file_id = Column(String(255), nullable=True)   
    document_id = Column(String(50), index=True)
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("idx_file_org", "organization_id"),)

class ApiKey(Base):
    __tablename__ = "api_keys"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    provider = Column(Enum(ProviderEnum), nullable=False)
    api_key_encrypted = Column(String(500), nullable=False)
    description = Column(String(200))
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

class UserModelAssignment(Base):
    __tablename__ = "user_model_assignments"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    provider = Column(Enum(ProviderEnum), nullable=False)
    model_name = Column(String(100), nullable=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (UniqueConstraint("user_id", "provider", name="uq_user_provider"),)

class QueryLog(Base):
    __tablename__ = "query_logs"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    conversation_id = Column(Integer, ForeignKey("conversations.id"), nullable=False)
    question = Column(Text, nullable=False)
    rewritten_question = Column(Text)
    answer = Column(Text)
    retrieved_chunks = Column(Integer, default=0)
    retrieval_time_ms = Column(Float)
    generation_time_ms = Column(Float)
    total_time_ms = Column(Float)
    confidence_score = Column(Float)
    input_tokens = Column(Integer)
    output_tokens = Column(Integer)
    estimated_cost_usd = Column(Float)
    user_feedback = Column(String(10))
    feedback_comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow, index=True)
    __table_args__ = (Index("idx_query_org", "organization_id"), Index("idx_query_user", "user_id"))

class RetrievalLog(Base):
    __tablename__ = "retrieval_logs"
    id = Column(Integer, primary_key=True)
    query_log_id = Column(Integer, ForeignKey("query_logs.id", ondelete="CASCADE"), nullable=False)
    chunk_id = Column(String(100))
    document_id = Column(String(50))
    similarity_score = Column(Float)
    chunk_text_preview = Column(Text)

class DocumentAccessLog(Base):
    __tablename__ = "document_access_logs"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    file_id = Column(Integer, ForeignKey("conversation_files.id", ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    action = Column(String(50))
    ip_address = Column(String(45))
    user_agent = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)
    __table_args__ = (Index("idx_doc_access_org", "organization_id"),)

class FeedbackLog(Base):
    __tablename__ = "feedback_logs"
    id = Column(Integer, primary_key=True)
    query_log_id = Column(Integer, ForeignKey("query_logs.id", ondelete="CASCADE"), nullable=False)
    rating = Column(String(10))
    comment = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

class KnowledgeGap(Base):
    __tablename__ = "knowledge_gaps"
    id = Column(Integer, primary_key=True)
    organization_id = Column(Integer, ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False)
    question = Column(Text, nullable=False)
    occurred_count = Column(Integer, default=1)
    last_occurred = Column(DateTime, default=datetime.utcnow)
    resolved = Column(Boolean, default=False)
    resolved_at = Column(DateTime)
    resolved_by = Column(Integer, ForeignKey("users.id"))

class ConversationAllowedFile(Base):
    __tablename__ = "conversation_allowed_files"
    id = Column(Integer, primary_key=True)
    conversation_id = Column(Integer, ForeignKey("conversations.id", ondelete="CASCADE"), nullable=False)
    document_id = Column(String(50), nullable=False)
    __table_args__ = (UniqueConstraint("conversation_id", "document_id", name="uq_conv_allowed"),)