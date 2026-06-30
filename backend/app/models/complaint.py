"""Pydantic schemas for UniResolve complaints."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Optional

from pydantic import AliasChoices, BaseModel, Field, field_validator, model_validator


class Channel(str, Enum):
    EMAIL = "email"
    WEB = "web"
    SOCIAL = "social"
    IVR = "ivr"
    BRANCH = "branch"
    APP = "app"


class Severity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Category(str, Enum):
    LOAN = "loan"
    CREDIT_CARD = "credit_card"
    ACCOUNT = "account"
    INSURANCE = "insurance"
    INVESTMENT = "investment"
    MOBILE_BANKING = "mobile_banking"
    UPI = "upi"
    NETBANKING = "netbanking"
    ATM = "atm"
    KYC = "kyc"
    FRAUD = "fraud"
    GENERAL = "general"


class Sentiment(str, Enum):
    ANGRY = "angry"
    FRUSTRATED = "frustrated"
    NEUTRAL = "neutral"
    SATISFIED = "satisfied"


class ComplaintStatus(str, Enum):
    PENDING = "pending"
    IN_REVIEW = "in_review"
    RESOLVED = "resolved"
    ESCALATED = "escalated"


class SLAStatus(str, Enum):
    ON_TRACK = "on_track"
    AT_RISK = "at_risk"
    BREACHED = "breached"


class EscalationLevel(str, Enum):
    L1_AGENT = "L1 Agent"
    L2_SUPERVISOR = "L2 Supervisor"
    L3_MANAGER = "L3 Manager"
    L4_REGULATORY = "L4 Regulatory"


class MessageAuthor(str, Enum):
    CUSTOMER = "customer"
    AGENT = "agent"
    SYSTEM = "system"


class RawComplaintIn(BaseModel):
    channel: Channel
    raw_text: Optional[str] = Field(default="", max_length=5000, validation_alias=AliasChoices("raw_text", "complaint_text"))
    channel_metadata: dict[str, Any] = Field(default_factory=dict)
    customer_id: Optional[str] = None
    transaction_id: Optional[str] = None
    source_ref: Optional[str] = None
    received_at: Optional[datetime] = None
    media_file: Optional[str] = None
    media_type: Optional[str] = None

    @field_validator("raw_text")
    @classmethod
    def strip_and_validate_text(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return ""
        return value.strip()

    @model_validator(mode="after")
    def validate_content_present(self) -> RawComplaintIn:
        if not self.raw_text and not self.media_file:
            raise ValueError("Either raw_text (complaint_text) or media_file must be provided.")
        # Manual submissions require customer_id
        is_seed = self.channel_metadata.get("seed") is True
        is_replay = self.source_ref and self.source_ref.startswith("replay-")
        if not (is_seed or is_replay) and not self.customer_id:
            raise ValueError("Customer ID is required")
        return self


class TriageResult(BaseModel):
    category: Category = Category.GENERAL
    severity: Severity = Severity.MEDIUM
    sentiment: Sentiment = Sentiment.NEUTRAL
    key_issue: str = ""
    key_issues: list[str] = Field(default_factory=list)
    suggested_response: str = ""
    confidence: float = 0.75
    detected_language: str = "English"


class DuplicateCluster(BaseModel):
    cluster_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    is_duplicate: bool = False
    duplicate_of: Optional[str] = None
    cluster_size: int = 1
    systemic_alert: bool = False
    duplicate_reason: Optional[str] = None


class SLAInfo(BaseModel):
    deadline: datetime
    hours_allowed: int
    hours_elapsed: float
    hours_remaining: float
    percent_used: float
    status: SLAStatus
    breached: bool


class HistoryMessage(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    author: MessageAuthor
    author_name: str
    content: str
    is_ai_draft: bool = False
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class EscalationRecord(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    from_level: EscalationLevel = EscalationLevel.L1_AGENT
    to_level: EscalationLevel = EscalationLevel.L2_SUPERVISOR
    reason: str
    escalated_by: str = "System"
    note: Optional[str] = None
    escalated_at: datetime = Field(default_factory=datetime.utcnow)


class Complaint(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    channel: Channel
    channel_metadata: dict[str, Any] = Field(default_factory=dict)
    raw_text: str
    masked_text: str
    masked_fields: list[str] = Field(default_factory=list)
    customer_id: Optional[str] = None
    transaction_id: Optional[str] = None
    source_ref: Optional[str] = None
    received_at: datetime = Field(default_factory=datetime.utcnow)
    triage: Optional[TriageResult] = None
    cluster: Optional[DuplicateCluster] = None
    status: ComplaintStatus = ComplaintStatus.PENDING
    assigned_agent: Optional[str] = None
    agent_note: Optional[str] = None
    escalation_level: EscalationLevel = EscalationLevel.L1_AGENT
    escalation_history: list[EscalationRecord] = Field(default_factory=list)
    communication_history: list[HistoryMessage] = Field(default_factory=list)
    sla: Optional[SLAInfo] = None
    sla_status: SLAStatus = SLAStatus.ON_TRACK
    sla_breached: bool = False
    resolved_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    tenant_id: str = "Union Bank"
    rbi_status: str = "within"


def compute_rbi_status(received_at: datetime, resolved_at: Optional[datetime] = None) -> str:
    end_time = resolved_at or datetime.utcnow()
    elapsed_days = (end_time - received_at).days
    if elapsed_days <= 20:
        return "within"
    elif elapsed_days <= 30:
        return "approaching"
    else:
        return "ombudsman_eligible"


class ComplaintResponse(BaseModel):
    complaint: Complaint
    message: str


class AgentAction(BaseModel):
    action: str
    custom_response: Optional[str] = None
    agent_id: str = "agent"


class EscalationAction(BaseModel):
    complaint_id: Optional[str] = None
    to_level: EscalationLevel = EscalationLevel.L2_SUPERVISOR
    reason: str = "Manual escalation"
    agent_id: str = "agent"
    note: Optional[str] = None
    agent_note: Optional[str] = None


class ReplyMessage(BaseModel):
    complaint_id: Optional[str] = None
    content: str
    author: MessageAuthor = MessageAuthor.AGENT
    author_name: str = "Agent"
    is_ai_draft: bool = False


class DashboardStats(BaseModel):
    total: int = 0
    pending: int = 0
    resolved: int = 0
    escalated: int = 0
    systemic_alerts: int = 0
    sla_breached: int = 0
    sla_at_risk: int = 0
    resolved_today: int = 0
    by_category: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
    by_channel: dict[str, int] = Field(default_factory=dict)
    daily_trend: list[dict[str, Any]] = Field(default_factory=list)
    avg_resolution_minutes: float = 0.0


class RegulatoryReport(BaseModel):
    generated_at: datetime = Field(default_factory=datetime.utcnow)
    period: str = "Last 30 Days"
    total_complaints: int = 0
    resolved: int = 0
    pending: int = 0
    escalated: int = 0
    resolution_rate_pct: float = 0.0
    sla_breach_count: int = 0
    sla_compliance_pct: float = 100.0
    avg_resolution_hours: float = 0.0
    by_category: dict[str, int] = Field(default_factory=dict)
    by_channel: dict[str, int] = Field(default_factory=dict)
    by_severity: dict[str, int] = Field(default_factory=dict)
    critical_unresolved: int = 0
    escalated_to_regulatory: int = 0


def compute_sla(received_at: datetime, severity: str, deadline: Optional[datetime] = None) -> SLAInfo:
    from app.config import SLA_HOURS

    hours_allowed = SLA_HOURS.get(severity, SLA_HOURS["medium"])
    deadline = deadline or received_at + timedelta(hours=hours_allowed)
    now = datetime.utcnow()
    elapsed = max((now - received_at).total_seconds() / 3600, 0)
    remaining = max((deadline - now).total_seconds() / 3600, 0)
    breached = now > deadline
    percent_used = min((elapsed / hours_allowed) * 100, 100) if hours_allowed else 100
    if breached:
        status = SLAStatus.BREACHED
    elif remaining <= hours_allowed * 0.2:
        status = SLAStatus.AT_RISK
    else:
        status = SLAStatus.ON_TRACK
    return SLAInfo(
        deadline=deadline,
        hours_allowed=hours_allowed,
        hours_elapsed=round(elapsed, 2),
        hours_remaining=round(remaining, 2),
        percent_used=round(percent_used, 2),
        status=status,
        breached=breached,
    )
