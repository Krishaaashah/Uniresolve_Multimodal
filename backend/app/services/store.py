"""SQLite-backed complaint store for the hackathon demo."""

from __future__ import annotations

import json
import sqlite3
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from app.models.complaint import (
    Category,
    Channel,
    Complaint,
    ComplaintStatus,
    DashboardStats,
    DuplicateCluster,
    EscalationLevel,
    EscalationRecord,
    HistoryMessage,
    MessageAuthor,
    RegulatoryReport,
    SLAStatus,
    Sentiment,
    Severity,
    TriageResult,
    compute_sla,
    compute_rbi_status,
)

DB_PATH = Path(__file__).resolve().parents[2] / "complaints.db"


def _dt(value: str | None) -> datetime | None:
    if not value:
        return None
    return datetime.fromisoformat(value)


def _json(value: Any) -> str:
    return json.dumps(value, default=str)


def _loads(value: str | None, default: Any):
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return default


class ComplaintStore:
    def __init__(self, db_path: Path = DB_PATH):
        self.db_path = db_path
        self._init_db()

    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS complaints (
                    id TEXT PRIMARY KEY,
                    channel TEXT,
                    channel_metadata TEXT,
                    complaint_text TEXT,
                    masked_text TEXT,
                    masked_fields TEXT,
                    category TEXT,
                    severity TEXT,
                    sentiment TEXT,
                    key_issues TEXT,
                    draft_response TEXT,
                    status TEXT DEFAULT 'pending',
                    assigned_agent TEXT,
                    sla_deadline TEXT,
                    sla_breached INTEGER DEFAULT 0,
                    duplicate_of TEXT,
                    cluster_id TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    resolved_at TEXT,
                    customer_id TEXT,
                    source_ref TEXT,
                    received_at TEXT,
                    confidence REAL,
                    cluster_size INTEGER DEFAULT 1,
                    systemic_alert INTEGER DEFAULT 0,
                    escalation_level TEXT,
                    escalation_history TEXT,
                    communication_history TEXT,
                    agent_note TEXT,
                    detected_language TEXT DEFAULT 'English',
                    tenant_id TEXT DEFAULT 'Union Bank'
                )
                """
            )
            # Safe table alterations in case database already existed
            try:
                conn.execute("ALTER TABLE complaints ADD COLUMN detected_language TEXT DEFAULT 'English'")
            except sqlite3.OperationalError:
                pass
            try:
                conn.execute("ALTER TABLE complaints ADD COLUMN tenant_id TEXT DEFAULT 'Union Bank'")
            except sqlite3.OperationalError:
                pass

            # Create users and audit_log tables
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT,
                    role TEXT,
                    tenant_id TEXT DEFAULT 'Union Bank'
                )
                """
            )
            try:
                conn.execute("ALTER TABLE users ADD COLUMN tenant_id TEXT DEFAULT 'Union Bank'")
            except sqlite3.OperationalError:
                pass

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    actor TEXT,
                    role TEXT,
                    action TEXT,
                    complaint_id TEXT,
                    timestamp TEXT
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    amount TEXT,
                    status TEXT,
                    date TEXT,
                    channel TEXT,
                    description TEXT
                )
                """
            )
            # Auto-seed users if empty
            import hashlib
            def hash_pw(password: str) -> str:
                return hashlib.sha256(password.encode()).hexdigest()

            cursor = conn.execute("SELECT COUNT(*) FROM users")
            if cursor.fetchone()[0] == 0:
                conn.execute("INSERT INTO users VALUES (?, ?, ?, ?)", ("agent", hash_pw("agent123"), "agent", "Union Bank"))
                conn.execute("INSERT INTO users VALUES (?, ?, ?, ?)", ("supervisor", hash_pw("supervisor123"), "supervisor", "Union Bank"))
                conn.execute("INSERT INTO users VALUES (?, ?, ?, ?)", ("admin", hash_pw("admin123"), "admin", "Union Bank"))
                conn.execute("INSERT INTO users VALUES (?, ?, ?, ?)", ("sub_agent", hash_pw("sub_agent123"), "agent", "UBI Subsidiary"))
            
            conn.commit()




    def _row_to_complaint(self, row: sqlite3.Row) -> Complaint:
        key_issues = _loads(row["key_issues"], [])
        received_at = _dt(row["received_at"]) or _dt(row["created_at"]) or datetime.utcnow()
        severity = Severity(row["severity"] or "medium")
        deadline = _dt(row["sla_deadline"])
        sla = None if row["status"] == ComplaintStatus.RESOLVED.value else compute_sla(received_at, severity.value, deadline)
        
        try:
            detected_lang = row["detected_language"] or "English"
        except Exception:
            detected_lang = "English"
            
        try:
            tenant_id = row["tenant_id"] or "Union Bank"
        except Exception:
            tenant_id = "Union Bank"

        triage = TriageResult(
            category=Category(row["category"] or "general"),
            severity=severity,
            sentiment=Sentiment(row["sentiment"] or "neutral"),
            key_issue=key_issues[0] if key_issues else "",
            key_issues=key_issues,
            suggested_response=row["draft_response"] or "",
            confidence=float(row["confidence"] or 0.75),
            detected_language=detected_lang
        )
        cluster = DuplicateCluster(
            cluster_id=row["cluster_id"] or "",
            is_duplicate=bool(row["duplicate_of"]),
            duplicate_of=row["duplicate_of"],
            cluster_size=int(row["cluster_size"] or 1),
            systemic_alert=bool(row["systemic_alert"]),
        )
        history = [HistoryMessage.model_validate(item) for item in _loads(row["communication_history"], [])]
        escalations = [EscalationRecord.model_validate(item) for item in _loads(row["escalation_history"], [])]
        sla_status = sla.status if sla else (SLAStatus.BREACHED if row["sla_breached"] else SLAStatus.ON_TRACK)
        return Complaint(
            id=row["id"],
            channel=Channel(row["channel"]),
            channel_metadata=_loads(row["channel_metadata"], {}),
            raw_text=row["complaint_text"] or "",
            masked_text=row["masked_text"] or "",
            masked_fields=_loads(row["masked_fields"], []),
            customer_id=row["customer_id"],
            source_ref=row["source_ref"],
            received_at=received_at,
            triage=triage,
            cluster=cluster,
            status=ComplaintStatus(row["status"] or "pending"),
            assigned_agent=row["assigned_agent"],
            agent_note=row["agent_note"],
            escalation_level=EscalationLevel(row["escalation_level"] or "L1 Agent"),
            escalation_history=escalations,
            communication_history=history,
            sla=sla,
            sla_status=sla_status,
            sla_breached=bool(row["sla_breached"] or (sla.breached if sla else False)),
            resolved_at=_dt(row["resolved_at"]),
            created_at=_dt(row["created_at"]) or received_at,
            updated_at=_dt(row["updated_at"]) or received_at,
            tenant_id=tenant_id,
            rbi_status=compute_rbi_status(received_at, _dt(row["resolved_at"]))
        )


    def save(self, complaint: Complaint) -> Complaint:
        now = datetime.utcnow()
        complaint.updated_at = now
        complaint.rbi_status = compute_rbi_status(complaint.received_at, complaint.resolved_at)
        if complaint.triage and not complaint.sla:
            complaint.sla = compute_sla(complaint.received_at, complaint.triage.severity.value)
        complaint.sla_status = complaint.sla.status if complaint.sla else SLAStatus.ON_TRACK
        complaint.sla_breached = bool(complaint.sla and complaint.sla.breached)

        key_issues = complaint.triage.key_issues if complaint.triage and complaint.triage.key_issues else []
        if complaint.triage and complaint.triage.key_issue and complaint.triage.key_issue not in key_issues:
            key_issues = [complaint.triage.key_issue, *key_issues]
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO complaints (
                    id, channel, channel_metadata, complaint_text, masked_text, masked_fields,
                    category, severity, sentiment, key_issues, draft_response, status,
                    assigned_agent, sla_deadline, sla_breached, duplicate_of, cluster_id,
                    created_at, updated_at, resolved_at, customer_id, source_ref, received_at,
                    confidence, cluster_size, systemic_alert, escalation_level,
                    escalation_history, communication_history, agent_note,
                    detected_language, tenant_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    complaint.id,
                    complaint.channel.value,
                    _json(complaint.channel_metadata),
                    complaint.raw_text,
                    complaint.masked_text,
                    _json(complaint.masked_fields),
                    complaint.triage.category.value if complaint.triage else Category.GENERAL.value,
                    complaint.triage.severity.value if complaint.triage else Severity.MEDIUM.value,
                    complaint.triage.sentiment.value if complaint.triage else Sentiment.NEUTRAL.value,
                    _json(key_issues),
                    complaint.triage.suggested_response if complaint.triage else "",
                    complaint.status.value,
                    complaint.assigned_agent,
                    complaint.sla.deadline.isoformat() if complaint.sla else None,
                    int(complaint.sla_breached),
                    complaint.cluster.duplicate_of if complaint.cluster else None,
                    complaint.cluster.cluster_id if complaint.cluster else None,
                    complaint.created_at.isoformat(),
                    complaint.updated_at.isoformat(),
                    complaint.resolved_at.isoformat() if complaint.resolved_at else None,
                    complaint.customer_id,
                    complaint.source_ref,
                    complaint.received_at.isoformat(),
                    complaint.triage.confidence if complaint.triage else 0.75,
                    complaint.cluster.cluster_size if complaint.cluster else 1,
                    int(complaint.cluster.systemic_alert) if complaint.cluster else 0,
                    complaint.escalation_level.value,
                    _json([e.model_dump(mode="json") for e in complaint.escalation_history]),
                    _json([h.model_dump(mode="json") for h in complaint.communication_history]),
                    complaint.agent_note,
                    complaint.triage.detected_language if complaint.triage else "English",
                    complaint.tenant_id,
                ),
            )
            conn.commit()

        return complaint

    def get(self, complaint_id: str) -> Optional[Complaint]:
        with self._connect() as conn:
            row = conn.execute("SELECT * FROM complaints WHERE id = ?", (complaint_id,)).fetchone()
        return self._row_to_complaint(row) if row else None

    def all(self) -> list[Complaint]:
        with self._connect() as conn:
            rows = conn.execute("SELECT * FROM complaints").fetchall()
        return [self._row_to_complaint(row) for row in rows]

    def update_status(self, complaint_id: str, status: ComplaintStatus, agent_note: Optional[str] = None) -> Optional[Complaint]:
        c = self.get(complaint_id)
        if not c:
            return None
        c.status = status
        c.updated_at = datetime.utcnow()
        if agent_note:
            c.agent_note = agent_note
            c.communication_history.append(HistoryMessage(author=MessageAuthor.AGENT, author_name="Agent", content=agent_note))
        c.communication_history.append(HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content=f"Status changed to {status.value}."))
        if status == ComplaintStatus.RESOLVED:
            c.resolved_at = datetime.utcnow()
        return self.save(c)

    def add_message(self, complaint_id: str, msg: HistoryMessage) -> Optional[Complaint]:
        c = self.get(complaint_id)
        if not c:
            return None
        c.communication_history.append(msg)
        return self.save(c)

    def escalate(self, complaint_id: str, record: EscalationRecord, to_level: EscalationLevel) -> Optional[Complaint]:
        c = self.get(complaint_id)
        if not c:
            return None
        c.escalation_history.append(record)
        c.escalation_level = to_level
        c.status = ComplaintStatus.ESCALATED
        c.updated_at = datetime.utcnow()
        c.communication_history.append(HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content=f"Escalated to {to_level.value}: {record.reason}"))
        return self.save(c)

    def mark_sla_breaches(self) -> int:
        now = datetime.utcnow()
        count = 0
        for c in self.all():
            if c.status == ComplaintStatus.RESOLVED or not c.sla:
                continue
            if c.sla.deadline < now and not c.sla_breached:
                c.sla_breached = True
                c.status = ComplaintStatus.ESCALATED
                c.sla_status = SLAStatus.BREACHED
                c.communication_history.append(HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content="SLA breached. Complaint auto-escalated."))
                self.save(c)
                count += 1
        return count

    def get_sla_breached(self) -> list[Complaint]:
        return [c for c in self.all() if c.sla_breached or c.sla_status == SLAStatus.BREACHED]

    def get_stats(self, tenant_id: Optional[str] = None) -> DashboardStats:
        complaints = self.all()
        if tenant_id:
            complaints = [c for c in complaints if c.tenant_id == tenant_id]
        by_category = Counter(c.triage.category.value for c in complaints if c.triage)
        by_severity = Counter(c.triage.severity.value for c in complaints if c.triage)
        by_channel = Counter(c.channel.value for c in complaints)
        today = datetime.utcnow().date()
        res_times = [(c.resolved_at - c.received_at).total_seconds() / 60 for c in complaints if c.resolved_at]
        daily_trend = []
        for i in range(6, -1, -1):
            day = datetime.utcnow() - timedelta(days=i)
            daily_trend.append({"date": day.strftime("%b %d"), "count": sum(1 for c in complaints if c.received_at.date() == day.date())})
        return DashboardStats(
            total=len(complaints),
            pending=sum(c.status == ComplaintStatus.PENDING for c in complaints),
            resolved=sum(c.status == ComplaintStatus.RESOLVED for c in complaints),
            escalated=sum(c.status == ComplaintStatus.ESCALATED for c in complaints),
            systemic_alerts=sum(bool(c.cluster and c.cluster.systemic_alert) for c in complaints),
            sla_breached=sum(c.sla_status == SLAStatus.BREACHED for c in complaints),
            sla_at_risk=sum(c.sla_status == SLAStatus.AT_RISK for c in complaints),
            resolved_today=sum(bool(c.resolved_at and c.resolved_at.date() == today) for c in complaints),
            by_category=dict(by_category),
            by_severity=dict(by_severity),
            by_channel=dict(by_channel),
            daily_trend=daily_trend,
            avg_resolution_minutes=round(sum(res_times) / len(res_times), 2) if res_times else 0.0,
        )

    def get_regulatory_report(self, tenant_id: Optional[str] = None) -> RegulatoryReport:
        complaints = self.all()
        if tenant_id:
            complaints = [c for c in complaints if c.tenant_id == tenant_id]
        resolved = [c for c in complaints if c.status == ComplaintStatus.RESOLVED]
        res_hours = [(c.resolved_at - c.received_at).total_seconds() / 3600 for c in resolved if c.resolved_at]
        total = len(complaints)
        breached = sum(c.sla_status == SLAStatus.BREACHED for c in complaints)

        return RegulatoryReport(
            total_complaints=total,
            resolved=len(resolved),
            pending=sum(c.status == ComplaintStatus.PENDING for c in complaints),
            escalated=sum(c.status == ComplaintStatus.ESCALATED for c in complaints),
            resolution_rate_pct=round(len(resolved) / total * 100 if total else 0, 1),
            sla_breach_count=breached,
            sla_compliance_pct=round((total - breached) / total * 100 if total else 100, 1),
            avg_resolution_hours=round(sum(res_hours) / len(res_hours), 2) if res_hours else 0.0,
            by_category=dict(Counter(c.triage.category.value for c in complaints if c.triage)),
            by_channel=dict(Counter(c.channel.value for c in complaints)),
            by_severity=dict(Counter(c.triage.severity.value for c in complaints if c.triage)),
            critical_unresolved=sum(c.triage and c.triage.severity == Severity.CRITICAL and c.status != ComplaintStatus.RESOLVED for c in complaints),
            escalated_to_regulatory=sum(c.escalation_level == EscalationLevel.L4_REGULATORY for c in complaints),
        )

    def log_audit(self, actor: str, role: str, action: str, complaint_id: Optional[str] = None):
        import uuid
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO audit_log (id, actor, role, action, complaint_id, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
                (str(uuid.uuid4()), actor, role, action, complaint_id, datetime.utcnow().isoformat())
            )
            conn.commit()

    def get_audit_logs(self, complaint_id: Optional[str] = None) -> list[dict]:
        with self._connect() as conn:
            if complaint_id:
                cursor = conn.execute(
                    "SELECT * FROM audit_log WHERE complaint_id = ? ORDER BY timestamp DESC",
                    (complaint_id,)
                )
            else:
                cursor = conn.execute("SELECT * FROM audit_log ORDER BY timestamp DESC")
            return [dict(row) for row in cursor.fetchall()]

    def verify_user(self, username: str, password_plain: str) -> Optional[dict]:
        import hashlib
        def hash_pw(password: str) -> str:
            return hashlib.sha256(password.encode()).hexdigest()

        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM users WHERE username = ? AND password_hash = ?",
                (username, hash_pw(password_plain))
            ).fetchone()
            if row:
                return dict(row)
        return None

    def get_transaction(self, transaction_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM transactions WHERE transaction_id = ?",
                (transaction_id,)
            ).fetchone()
            if row:
                return dict(row)
        return None

    def get_transactions_for_customer(self, customer_id: str) -> list[dict]:
        with self._connect() as conn:
            cursor = conn.execute(
                "SELECT * FROM transactions WHERE customer_id = ? ORDER BY date DESC",
                (customer_id,)
            )
            return [dict(row) for row in cursor.fetchall()]

    def save_transaction(self, tx: dict):
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO transactions (
                    transaction_id, customer_id, amount, status, date, channel, description
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (tx["transaction_id"], tx["customer_id"], tx["amount"], tx["status"], tx["date"], tx["channel"], tx["description"])
            )
            conn.commit()

    def clear(self):
        with self._connect() as conn:
            conn.execute("DELETE FROM complaints")
            conn.execute("DELETE FROM transactions")
            conn.commit()



_store: Optional[ComplaintStore] = None


def get_store() -> ComplaintStore:
    global _store
    if _store is None:
        _store = ComplaintStore()
    return _store
