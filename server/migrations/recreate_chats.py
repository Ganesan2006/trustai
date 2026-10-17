import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import MetaData
from server.app.config import engine
from server.app.model import Base, Conversation, Message, ConversationFile, ConversationAllowedFile, QueryLog, RetrievalLog, FeedbackLog, DocumentAccessLog

def recreate_chat_tables():
    print("Dropping chat-related tables...")
    # Drop in correct order due to foreign key constraints
    DocumentAccessLog.__table__.drop(engine, checkfirst=True)
    FeedbackLog.__table__.drop(engine, checkfirst=True)
    RetrievalLog.__table__.drop(engine, checkfirst=True)
    QueryLog.__table__.drop(engine, checkfirst=True)
    ConversationAllowedFile.__table__.drop(engine, checkfirst=True)
    ConversationFile.__table__.drop(engine, checkfirst=True)
    Message.__table__.drop(engine, checkfirst=True)
    Conversation.__table__.drop(engine, checkfirst=True)
    
    print("Recreating chat-related tables with new schema...")
    Conversation.__table__.create(engine, checkfirst=True)
    Message.__table__.create(engine, checkfirst=True)
    ConversationFile.__table__.create(engine, checkfirst=True)
    DocumentAccessLog.__table__.create(engine, checkfirst=True)
    ConversationAllowedFile.__table__.create(engine, checkfirst=True)
    QueryLog.__table__.create(engine, checkfirst=True)
    RetrievalLog.__table__.create(engine, checkfirst=True)
    FeedbackLog.__table__.create(engine, checkfirst=True)
    print("Migration complete!")

if __name__ == "__main__":
    recreate_chat_tables()
