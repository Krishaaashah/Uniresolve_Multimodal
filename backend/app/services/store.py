"""SQLAlchemy-backed complaint store — works with Postgres or SQLite.

If DATABASE_URL is set in the environment the store connects to Postgres;
otherwise it falls back to a local SQLite file (complaints.db) with no
additional configuration required.
"""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional

from sqlalchemy import text as sa_text
from app.db import engine as _sa_engine

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
    def __init__(self):
        self._init_db()

    # ── Internal helpers ──────────────────────────────────────────────────────
    def _connect(self):
        """Return a raw DBAPI connection from the SQLAlchemy engine."""
        return _sa_engine.connect()

    def _init_db(self):
        from sqlalchemy.exc import OperationalError as SAOperationalError
        
        with self._connect() as conn:
            conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS complaints (
                    id TEXT PRIMARY KEY,
                    ticket_id TEXT UNIQUE,
                    parent_ticket_id TEXT,
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
                    duplicate_reason TEXT,
                    severity_reason TEXT,
                    summary TEXT,
                    created_at TEXT,
                    updated_at TEXT,
                    resolved_at TEXT,
                    customer_id TEXT,
                    transaction_id TEXT,
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
                    tenant_id TEXT DEFAULT 'Union Bank',
                    recurring INTEGER DEFAULT 0,
                    recurring_of TEXT
                )
            """))

            # Safe column additions for pre-existing databases
            _optional_cols = [
                "ALTER TABLE complaints ADD COLUMN transaction_id TEXT",
                "ALTER TABLE complaints ADD COLUMN duplicate_reason TEXT",
                "ALTER TABLE complaints ADD COLUMN severity_reason TEXT",
                "ALTER TABLE complaints ADD COLUMN summary TEXT",
                "ALTER TABLE complaints ADD COLUMN detected_language TEXT DEFAULT 'English'",
                "ALTER TABLE complaints ADD COLUMN tenant_id TEXT DEFAULT 'Union Bank'",
                "ALTER TABLE complaints ADD COLUMN ticket_id TEXT",
                "ALTER TABLE complaints ADD COLUMN parent_ticket_id TEXT",
                "ALTER TABLE complaints ADD COLUMN recurring INTEGER DEFAULT 0",
                "ALTER TABLE complaints ADD COLUMN recurring_of TEXT",
            ]
            for sql in _optional_cols:
                try:
                    conn.execute(sa_text(sql))
                except SAOperationalError:
                    pass  # column already exists

            conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT,
                    role TEXT,
                    tenant_id TEXT DEFAULT 'Union Bank'
                )
            """))
            try:
                conn.execute(sa_text("ALTER TABLE users ADD COLUMN tenant_id TEXT DEFAULT 'Union Bank'"))
            except SAOperationalError:
                pass

            conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS audit_log (
                    id TEXT PRIMARY KEY,
                    actor TEXT,
                    role TEXT,
                    action TEXT,
                    complaint_id TEXT,
                    timestamp TEXT
                )
            """))

            conn.execute(sa_text("""
                CREATE TABLE IF NOT EXISTS transactions (
                    transaction_id TEXT PRIMARY KEY,
                    customer_id TEXT,
                    amount TEXT,
                    status TEXT,
                    date TEXT,
                    channel TEXT,
                    description TEXT
                )
            """))

            # Auto-seed users if empty
            import hashlib
            def hash_pw(password: str) -> str:
                return hashlib.sha256(password.encode()).hexdigest()

            cursor = conn.execute(sa_text("SELECT COUNT(*) FROM users"))
            if cursor.fetchone()[0] == 0:
                _users = [
                    ("agent",      hash_pw("agent123"),      "agent",      "Union Bank"),
                    ("supervisor", hash_pw("supervisor123"), "supervisor", "Union Bank"),
                    ("admin",      hash_pw("admin123"),      "admin",      "Union Bank"),
                    ("sub_agent",  hash_pw("sub_agent123"),  "agent",      "UBI Subsidiary"),
                ]
                for u in _users:
                    conn.execute(
                        sa_text("INSERT INTO users VALUES (:u, :p, :r, :t)"),
                        {"u": u[0], "p": u[1], "r": u[2], "t": u[3]}
                    )
            conn.commit()


    def _row_to_complaint(self, row) -> Complaint:
        # Convert SQLAlchemy Row to a plain dict for uniform key access
        if not isinstance(row, dict):
            row = dict(row._mapping)
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

        try:
            sev_reason = row["severity_reason"]
        except Exception:
            sev_reason = None

        triage = TriageResult(
            category=row["category"] or "general",
            severity=severity,
            sentiment=Sentiment(row["sentiment"] or "neutral"),
            key_issue=key_issues[0] if key_issues else "",
            key_issues=key_issues,
            suggested_response=row["draft_response"] or "",
            confidence=float(row["confidence"] or 0.75),
            detected_language=detected_lang,
            severity_reason=sev_reason
        )
        try:
            dup_reason = row["duplicate_reason"]
        except Exception:
            dup_reason = None

        cluster = DuplicateCluster(
            cluster_id=row["cluster_id"] or "",
            is_duplicate=bool(row["duplicate_of"]),
            duplicate_of=row["duplicate_of"],
            cluster_size=int(row["cluster_size"] or 1),
            systemic_alert=bool(row["systemic_alert"]),
            duplicate_reason=dup_reason,
        )
        history = [HistoryMessage.model_validate(item) for item in _loads(row["communication_history"], [])]
        escalations = [EscalationRecord.model_validate(item) for item in _loads(row["escalation_history"], [])]
        sla_status = sla.status if sla else (SLAStatus.BREACHED if row["sla_breached"] else SLAStatus.ON_TRACK)
        try:
            tx_id = row["transaction_id"]
        except Exception:
            tx_id = None

        try:
            sum_val = row["summary"]
        except Exception:
            sum_val = None

        try:
            tkt_id = row["ticket_id"]
        except Exception:
            tkt_id = None

        try:
            p_tkt_id = row["parent_ticket_id"]
        except Exception:
            p_tkt_id = None

        try:
            rec_val = bool(row["recurring"])
        except Exception:
            rec_val = False

        try:
            rec_of_val = row["recurring_of"]
        except Exception:
            rec_of_val = None

        import random

        return Complaint(
            id=row["id"],
            ticket_id=tkt_id or f"TKT-{random.randint(100000, 999999)}",
            parent_ticket_id=p_tkt_id,
            channel=Channel(row["channel"]),
            channel_metadata=_loads(row["channel_metadata"], {}),
            raw_text=row["complaint_text"] or "",
            masked_text=row["masked_text"] or "",
            masked_fields=_loads(row["masked_fields"], []),
            customer_id=row["customer_id"],
            transaction_id=tx_id,
            source_ref=row["source_ref"],
            summary=sum_val,
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
            rbi_status=compute_rbi_status(received_at, _dt(row["resolved_at"])),
            recurring=rec_val,
            recurring_of=rec_of_val
        )


    def save(self, complaint: Complaint) -> Complaint:
        now = datetime.utcnow()
        complaint.updated_at = now
        complaint.rbi_status = compute_rbi_status(complaint.received_at, complaint.resolved_at)
        if complaint.triage and not complaint.sla:
            complaint.sla = compute_sla(complaint.received_at, complaint.triage.severity.value)
        complaint.sla_status = complaint.sla.status if complaint.sla else SLAStatus.ON_TRACK
        complaint.sla_breached = bool(complaint.sla and complaint.sla.breached)

        # Resolve parent_ticket_id
        if not complaint.parent_ticket_id:
            if complaint.cluster and complaint.cluster.is_duplicate and complaint.cluster.duplicate_of:
                matched = self.get(complaint.cluster.duplicate_of)
                if matched:
                    if getattr(matched, "parent_ticket_id", None):
                        complaint.parent_ticket_id = matched.parent_ticket_id
                    else:
                        complaint.parent_ticket_id = matched.ticket_id

        key_issues = complaint.triage.key_issues if complaint.triage and complaint.triage.key_issues else []
        if complaint.triage and complaint.triage.key_issue and complaint.triage.key_issue not in key_issues:
            key_issues = [complaint.triage.key_issue, *key_issues]
        with self._connect() as conn:
            _is_sqlite = "sqlite" in str(_sa_engine.url)
            if _is_sqlite:
                upsert_sql = sa_text("""
                INSERT OR REPLACE INTO complaints (
                    id, ticket_id, parent_ticket_id, channel, channel_metadata, complaint_text, masked_text, masked_fields,
                    category, severity, sentiment, key_issues, draft_response, status,
                    assigned_agent, sla_deadline, sla_breached, duplicate_of, cluster_id,
                    duplicate_reason, severity_reason, summary, created_at, updated_at, resolved_at, customer_id, transaction_id, source_ref, received_at,
                    confidence, cluster_size, systemic_alert, escalation_level,
                    escalation_history, communication_history, agent_note,
                    detected_language, tenant_id, recurring, recurring_of
                ) VALUES (:id,:ticket_id,:parent_ticket_id,:channel,:channel_metadata,:complaint_text,:masked_text,:masked_fields,
                    :category,:severity,:sentiment,:key_issues,:draft_response,:status,
                    :assigned_agent,:sla_deadline,:sla_breached,:duplicate_of,:cluster_id,
                    :duplicate_reason,:severity_reason,:summary,:created_at,:updated_at,:resolved_at,:customer_id,:transaction_id,:source_ref,:received_at,
                    :confidence,:cluster_size,:systemic_alert,:escalation_level,
                    :escalation_history,:communication_history,:agent_note,
                    :detected_language,:tenant_id,:recurring,:recurring_of)
                """)
            else:
                upsert_sql = sa_text("""
                INSERT INTO complaints (
                    id, ticket_id, parent_ticket_id, channel, channel_metadata, complaint_text, masked_text, masked_fields,
                    category, severity, sentiment, key_issues, draft_response, status,
                    assigned_agent, sla_deadline, sla_breached, duplicate_of, cluster_id,
                    duplicate_reason, severity_reason, summary, created_at, updated_at, resolved_at, customer_id, transaction_id, source_ref, received_at,
                    confidence, cluster_size, systemic_alert, escalation_level,
                    escalation_history, communication_history, agent_note,
                    detected_language, tenant_id, recurring, recurring_of
                ) VALUES (:id,:ticket_id,:parent_ticket_id,:channel,:channel_metadata,:complaint_text,:masked_text,:masked_fields,
                    :category,:severity,:sentiment,:key_issues,:draft_response,:status,
                    :assigned_agent,:sla_deadline,:sla_breached,:duplicate_of,:cluster_id,
                    :duplicate_reason,:severity_reason,:summary,:created_at,:updated_at,:resolved_at,:customer_id,:transaction_id,:source_ref,:received_at,
                    :confidence,:cluster_size,:systemic_alert,:escalation_level,
                    :escalation_history,:communication_history,:agent_note,
                    :detected_language,:tenant_id,:recurring,:recurring_of)
                ON CONFLICT (id) DO UPDATE SET
                    parent_ticket_id=EXCLUDED.parent_ticket_id,
                    channel=EXCLUDED.channel, channel_metadata=EXCLUDED.channel_metadata,
                    complaint_text=EXCLUDED.complaint_text, masked_text=EXCLUDED.masked_text,
                    masked_fields=EXCLUDED.masked_fields, category=EXCLUDED.category,
                    severity=EXCLUDED.severity, sentiment=EXCLUDED.sentiment,
                    key_issues=EXCLUDED.key_issues, draft_response=EXCLUDED.draft_response,
                    status=EXCLUDED.status, assigned_agent=EXCLUDED.assigned_agent,
                    sla_deadline=EXCLUDED.sla_deadline, sla_breached=EXCLUDED.sla_breached,
                    duplicate_of=EXCLUDED.duplicate_of, cluster_id=EXCLUDED.cluster_id,
                    duplicate_reason=EXCLUDED.duplicate_reason, severity_reason=EXCLUDED.severity_reason,
                    summary=EXCLUDED.summary, updated_at=EXCLUDED.updated_at,
                    resolved_at=EXCLUDED.resolved_at, customer_id=EXCLUDED.customer_id,
                    transaction_id=EXCLUDED.transaction_id, confidence=EXCLUDED.confidence,
                    cluster_size=EXCLUDED.cluster_size, systemic_alert=EXCLUDED.systemic_alert,
                    escalation_level=EXCLUDED.escalation_level,
                    escalation_history=EXCLUDED.escalation_history,
                    communication_history=EXCLUDED.communication_history,
                    agent_note=EXCLUDED.agent_note, detected_language=EXCLUDED.detected_language,
                    tenant_id=EXCLUDED.tenant_id,
                    recurring=EXCLUDED.recurring,
                    recurring_of=EXCLUDED.recurring_of
                """)
            conn.execute(upsert_sql, {
                    "id": complaint.id,
                    "ticket_id": complaint.ticket_id,
                    "parent_ticket_id": complaint.parent_ticket_id,
                    "channel": complaint.channel.value,
                    "channel_metadata": _json(complaint.channel_metadata),
                    "complaint_text": complaint.raw_text,
                    "masked_text": complaint.masked_text,
                    "masked_fields": _json(complaint.masked_fields),
                    "category": complaint.triage.category.value if complaint.triage else Category.GENERAL.value,
                    "severity": complaint.triage.severity.value if complaint.triage else Severity.MEDIUM.value,
                    "sentiment": complaint.triage.sentiment.value if complaint.triage else Sentiment.NEUTRAL.value,
                    "key_issues": _json(key_issues),
                    "draft_response": complaint.triage.suggested_response if complaint.triage else "",
                    "status": complaint.status.value,
                    "assigned_agent": complaint.assigned_agent,
                    "sla_deadline": complaint.sla.deadline.isoformat() if complaint.sla else None,
                    "sla_breached": int(complaint.sla_breached),
                    "duplicate_of": complaint.cluster.duplicate_of if complaint.cluster else None,
                    "cluster_id": complaint.cluster.cluster_id if complaint.cluster else None,
                    "duplicate_reason": complaint.cluster.duplicate_reason if complaint.cluster else None,
                    "severity_reason": complaint.triage.severity_reason if complaint.triage else None,
                    "summary": complaint.summary,
                    "created_at": complaint.created_at.isoformat(),
                    "updated_at": complaint.updated_at.isoformat(),
                    "resolved_at": complaint.resolved_at.isoformat() if complaint.resolved_at else None,
                    "customer_id": complaint.customer_id,
                    "transaction_id": complaint.transaction_id,
                    "source_ref": complaint.source_ref,
                    "received_at": complaint.received_at.isoformat(),
                    "confidence": complaint.triage.confidence if complaint.triage else 0.75,
                    "cluster_size": complaint.cluster.cluster_size if complaint.cluster else 1,
                    "systemic_alert": int(complaint.cluster.systemic_alert) if complaint.cluster else 0,
                    "escalation_level": complaint.escalation_level.value,
                    "escalation_history": _json([e.model_dump(mode="json") for e in complaint.escalation_history]),
                    "communication_history": _json([h.model_dump(mode="json") for h in complaint.communication_history]),
                    "agent_note": complaint.agent_note,
                    "detected_language": complaint.triage.detected_language if complaint.triage else "English",
                    "tenant_id": complaint.tenant_id,
                    "recurring": int(complaint.recurring),
                    "recurring_of": complaint.recurring_of,
                },
            )
            conn.commit()

            if complaint.cluster and complaint.cluster.cluster_id:
                cl_id = complaint.cluster.cluster_id
                cursor_size = conn.execute(
                    sa_text("SELECT COUNT(DISTINCT id) FROM complaints WHERE cluster_id = :cl_id"),
                    {"cl_id": cl_id}
                )
                real_size = cursor_size.fetchone()[0]
                
                cursor_cust = conn.execute(
                    sa_text("SELECT COUNT(DISTINCT customer_id) FROM complaints WHERE cluster_id = :cl_id AND customer_id IS NOT NULL AND customer_id != ''"),
                    {"cl_id": cl_id}
                )
                distinct_customers = cursor_cust.fetchone()[0]
                is_systemic = int(distinct_customers >= 5)
                
                conn.execute(
                    sa_text("""
                        UPDATE complaints
                        SET cluster_size = :size,
                            systemic_alert = :alert
                        WHERE cluster_id = :cl_id
                    """),
                    {"size": real_size, "alert": is_systemic, "cl_id": cl_id}
                )
                conn.commit()

        return complaint

    def get(self, complaint_id: str) -> Optional[Complaint]:
        with self._connect() as conn:
            row = conn.execute(
                sa_text("SELECT * FROM complaints WHERE id = :id"),
                {"id": complaint_id}
            ).fetchone()
        return self._row_to_complaint(row) if row else None

    def get_by_cluster(self, cluster_id: str) -> list[Complaint]:
        with self._connect() as conn:
            rows = conn.execute(
                sa_text("SELECT * FROM complaints WHERE cluster_id = :cluster_id"),
                {"cluster_id": cluster_id}
            ).fetchall()
        return [self._row_to_complaint(row) for row in rows]

    def all(self) -> list[Complaint]:
        with self._connect() as conn:
            rows = conn.execute(sa_text("SELECT * FROM complaints")).fetchall()
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
            
        saved_c = self.save(c)
        
        # If resolving, propagate status to duplicates / master
        if status == ComplaintStatus.RESOLVED:
            parent_uuid = None
            parent_tkt_id = None
            
            # Determine parent identifiers
            if c.cluster and c.cluster.duplicate_of:
                parent_uuid = c.cluster.duplicate_of
            if c.parent_ticket_id:
                parent_tkt_id = c.parent_ticket_id
                
            # If we only have one identifier, look up the other to ensure full coverage
            if parent_uuid and not parent_tkt_id:
                parent_complaint = self.get(parent_uuid)
                if parent_complaint:
                    parent_tkt_id = parent_complaint.ticket_id
            elif parent_tkt_id and not parent_uuid:
                for ticket in self.all():
                    if ticket.ticket_id == parent_tkt_id:
                        parent_uuid = ticket.id
                        break
            
            # If neither is set, c itself is the parent
            if not parent_uuid and not parent_tkt_id:
                parent_uuid = c.id
                parent_tkt_id = c.ticket_id
                
            parent_identifiers = {pid for pid in (parent_uuid, parent_tkt_id) if pid}
            
            if parent_identifiers:
                for ticket in self.all():
                    if ticket.id == c.id:
                        continue
                    # It is the parent if its UUID or ticket_id matches
                    is_parent = (ticket.id in parent_identifiers) or (ticket.ticket_id in parent_identifiers)
                    # It is a duplicate if its duplicate_of matches or parent_ticket_id matches
                    is_duplicate = (
                        (ticket.cluster and ticket.cluster.duplicate_of in parent_identifiers) or
                        (ticket.parent_ticket_id in parent_identifiers)
                    )
                    
                    if is_parent or is_duplicate:
                        if ticket.status != ComplaintStatus.RESOLVED:
                            ticket.status = ComplaintStatus.RESOLVED
                            ticket.updated_at = datetime.utcnow()
                            ticket.resolved_at = datetime.utcnow()
                            if agent_note:
                                ticket.agent_note = f"[Auto-closed as duplicate of {c.ticket_id}]: {agent_note}"
                                ticket.communication_history.append(HistoryMessage(
                                    author=MessageAuthor.AGENT, 
                                    author_name="Agent (Auto-close)", 
                                    content=f"[Auto-closed as duplicate of {c.ticket_id}]: {agent_note}"
                                ))
                            ticket.communication_history.append(HistoryMessage(
                                author=MessageAuthor.SYSTEM, 
                                author_name="System", 
                                content=f"Auto-resolved because duplicate/parent ticket {c.ticket_id} was resolved."
                            ))
                            self.save(ticket)
        return saved_c

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
                sa_text("INSERT INTO audit_log (id, actor, role, action, complaint_id, timestamp) VALUES (:id,:actor,:role,:action,:complaint_id,:ts)"),
                {"id": str(uuid.uuid4()), "actor": actor, "role": role, "action": action, "complaint_id": complaint_id, "ts": datetime.utcnow().isoformat()}
            )
            conn.commit()

    def get_audit_logs(self, complaint_id: Optional[str] = None) -> list[dict]:
        with self._connect() as conn:
            if complaint_id:
                cursor = conn.execute(
                    sa_text("SELECT * FROM audit_log WHERE complaint_id = :id ORDER BY timestamp DESC"),
                    {"id": complaint_id}
                )
            else:
                cursor = conn.execute(sa_text("SELECT * FROM audit_log ORDER BY timestamp DESC"))
            return [dict(row._mapping) for row in cursor.fetchall()]

    def verify_user(self, username: str, password_plain: str) -> Optional[dict]:
        import hashlib
        def hash_pw(password: str) -> str:
            return hashlib.sha256(password.encode()).hexdigest()

        with self._connect() as conn:
            row = conn.execute(
                sa_text("SELECT * FROM users WHERE username = :u AND password_hash = :p"),
                {"u": username, "p": hash_pw(password_plain)}
            ).fetchone()
            if row:
                return dict(row._mapping)
        return None

    def get_transaction(self, transaction_id: str) -> Optional[dict]:
        with self._connect() as conn:
            row = conn.execute(
                sa_text("SELECT * FROM transactions WHERE transaction_id = :tid"),
                {"tid": transaction_id}
            ).fetchone()
            if row:
                return dict(row._mapping)
        return None

    def get_transactions_for_customer(self, customer_id: str) -> list[dict]:
        with self._connect() as conn:
            cursor = conn.execute(
                sa_text("SELECT * FROM transactions WHERE customer_id = :cid ORDER BY date DESC"),
                {"cid": customer_id}
            )
            return [dict(row._mapping) for row in cursor.fetchall()]

    def save_transaction(self, tx: dict):
        with self._connect() as conn:
            _is_sqlite = "sqlite" in str(_sa_engine.url)
            params = {
                "transaction_id": tx["transaction_id"],
                "customer_id": tx["customer_id"],
                "amount": tx["amount"],
                "status": tx["status"],
                "date": tx["date"],
                "channel": tx["channel"],
                "description": tx["description"],
            }
            if _is_sqlite:
                conn.execute(sa_text("""
                    INSERT OR REPLACE INTO transactions (
                        transaction_id, customer_id, amount, status, date, channel, description
                    ) VALUES (:transaction_id,:customer_id,:amount,:status,:date,:channel,:description)
                """), params)
            else:
                conn.execute(sa_text("""
                    INSERT INTO transactions (
                        transaction_id, customer_id, amount, status, date, channel, description
                    ) VALUES (:transaction_id,:customer_id,:amount,:status,:date,:channel,:description)
                    ON CONFLICT (transaction_id) DO UPDATE SET
                        customer_id=EXCLUDED.customer_id, amount=EXCLUDED.amount,
                        status=EXCLUDED.status, date=EXCLUDED.date,
                        channel=EXCLUDED.channel, description=EXCLUDED.description
                """), params)
            conn.commit()

    def clear(self):
        with self._connect() as conn:
            conn.execute(sa_text("DELETE FROM complaints"))
            conn.execute(sa_text("DELETE FROM transactions"))
            conn.commit()
        from app.services.clustering import get_clustering_service
        try:
            get_clustering_service().clear()
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(f"Error resetting clustering in store.clear: {e}")



_store: Optional[ComplaintStore] = None


def get_store() -> ComplaintStore:
    global _store
    if _store is None:
        _store = ComplaintStore()
    return _store
