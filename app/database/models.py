from datetime import datetime, timezone
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from .database import Base

def now():
    return datetime.now(timezone.utc)

class GoogleAccount(Base):
    __tablename__ = "google_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True)
    display_name: Mapped[str | None] = mapped_column(String(200), nullable=True)
    token_reference: Mapped[str] = mapped_column(String(200))
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    last_scan_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    account_services: Mapped[list["AccountService"]] = relationship(back_populates="account", cascade="all, delete-orphan")

class Service(Base):
    __tablename__ = "services"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(100), default="Inconnu")
    subcategory: Mapped[str | None] = mapped_column(String(100), nullable=True)
    logo: Mapped[str | None] = mapped_column(String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    domains_json: Mapped[str] = mapped_column(Text, default="[]")
    senders_json: Mapped[str] = mapped_column(Text, default="[]")
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    account_services: Mapped[list["AccountService"]] = relationship(back_populates="service", cascade="all, delete-orphan")

class AccountService(Base):
    __tablename__ = "account_services"
    __table_args__ = (UniqueConstraint("account_id", "service_id", name="uq_account_service"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("google_accounts.id"), index=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), index=True)
    confidence_score: Mapped[float] = mapped_column(Float, default=0)
    trace_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="À vérifier")
    priority: Mapped[str] = mapped_column(String(50), default="Normale")
    destination_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    first_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_detected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    migrated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now, onupdate=now)
    account: Mapped["GoogleAccount"] = relationship(back_populates="account_services")
    service: Mapped["Service"] = relationship(back_populates="account_services")

class ScanHistory(Base):
    __tablename__ = "scan_history"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("google_accounts.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="running")
    messages_scanned: Mapped[int] = mapped_column(Integer, default=0)
    services_detected: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

class ScanServiceSnapshot(Base):
    __tablename__ = "scan_service_snapshots"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    scan_history_id: Mapped[int] = mapped_column(ForeignKey("scan_history.id"), index=True)
    service_name: Mapped[str] = mapped_column(String(200))
    category: Mapped[str] = mapped_column(String(100), default="Autre")
    confidence_score: Mapped[float] = mapped_column(Float, default=0)
    trace_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(50), default="À vérifier")
    priority: Mapped[str] = mapped_column(String(50), default="Normale")
    destination_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

class ScanTrace(Base):
    __tablename__ = "scan_traces"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_service_id: Mapped[int] = mapped_column(ForeignKey("account_services.id"), index=True)
    message_id: Mapped[str] = mapped_column(String(200), index=True)
    signal_type: Mapped[str] = mapped_column(String(50))
    signal_value: Mapped[str] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=now)
