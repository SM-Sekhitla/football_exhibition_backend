from sqlalchemy import JSON, Boolean, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = 'users'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(254), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    password_hash: Mapped[str] = mapped_column(Text)
    role: Mapped[str] = mapped_column(String(20), default='admin')
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    must_change_password: Mapped[bool] = mapped_column(Boolean, default=True)

class Session(Base):
    __tablename__ = 'sessions'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), index=True)
    csrf_hash: Mapped[str] = mapped_column(String(64))
    expires: Mapped[float] = mapped_column(Float)

class PasswordReset(Base):
    __tablename__ = 'password_resets'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36))
    expires: Mapped[float] = mapped_column(Float)

class Document(Base):
    __tablename__ = 'documents'
    key: Mapped[str] = mapped_column(String(40), primary_key=True)
    value: Mapped[dict | list] = mapped_column(JSON)
    revision: Mapped[int] = mapped_column(Integer, default=0)

class Record(Base):
    __tablename__ = 'records'
    __table_args__ = (UniqueConstraint('collection', 'identity'),)
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    collection: Mapped[str] = mapped_column(String(30), index=True)
    identity: Mapped[str | None] = mapped_column(String(350), nullable=True)
    value: Mapped[dict] = mapped_column(JSON)

class Upload(Base):
    __tablename__ = 'uploads'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    mime: Mapped[str] = mapped_column(String(100))
    private: Mapped[bool] = mapped_column(Boolean)
    owner_record: Mapped[str | None] = mapped_column(String(80), nullable=True)

class Audit(Base):
    __tablename__ = 'audit_logs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created: Mapped[float] = mapped_column(Float, index=True)
    category: Mapped[str] = mapped_column(String(40), index=True)
    level: Mapped[str] = mapped_column(String(10), default='INFO')
    message: Mapped[str] = mapped_column(String(500))
    actor: Mapped[str | None] = mapped_column(String(36), nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

class EmailJob(Base):
    __tablename__ = 'email_jobs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    recipient: Mapped[str] = mapped_column(String(254))
    subject: Mapped[str] = mapped_column(String(200))
    body: Mapped[str] = mapped_column(Text)
    html_body: Mapped[str | None] = mapped_column(Text,nullable=True)
    status: Mapped[str] = mapped_column(String(20), default='pending')
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    next_attempt: Mapped[float] = mapped_column(Float, default=0)
    last_error: Mapped[str | None] = mapped_column(String(200), nullable=True)
    provider_id: Mapped[str | None] = mapped_column(String(200), nullable=True)

class StaffInvitation(Base):
    __tablename__ = 'staff_invitations'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), unique=True)
    expires: Mapped[float] = mapped_column(Float)
    email_job_id: Mapped[str] = mapped_column(String(36))
