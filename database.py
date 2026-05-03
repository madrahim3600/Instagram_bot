from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime, Text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime

DATABASE_URL = "sqlite:///./sql_app.db"

engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

class InstagramAccount(Base):
    __tablename__ = "instagram_accounts"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    password = Column(String)
    session_data = Column(Text, nullable=True) # JSON string of session data
    status = Column(String, default="inactive") # active, inactive, banned, challenge_required
    last_checked = Column(DateTime, default=datetime.utcnow)
    is_admin_account = Column(Boolean, default=False)

class InstagramTask(Base):
    __tablename__ = "instagram_tasks"

    id = Column(Integer, primary_key=True, index=True)
    reel_url = Column(String, index=True)
    comments = Column(Text, nullable=True) # JSON string of comments
    likes_enabled = Column(Boolean, default=True)
    views_enabled = Column(Boolean, default=True)
    status = Column(String, default="pending") # pending, in_progress, completed, failed
    created_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime, nullable=True)

class TaskAccount(Base):
    __tablename__ = "task_accounts"

    id = Column(Integer, primary_key=True, index=True)
    task_id = Column(Integer, index=True)
    account_id = Column(Integer, index=True)
    status = Column(String, default="pending") # pending, completed, failed
    comment_text = Column(String, nullable=True) # Specific comment for this account on this task

def init_db():
    Base.metadata.create_all(bind=engine)

# Dependency to get the database session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
