"""Seed demo data for UniResolve.

Run from backend/: python -m app.seed
"""

from datetime import datetime, timedelta
from uuid import uuid4

from app.models.complaint import (
    Category,
    Channel,
    Complaint,
    ComplaintStatus,
    DuplicateCluster,
    EscalationLevel,
    EscalationRecord,
    HistoryMessage,
    MessageAuthor,
    Sentiment,
    Severity,
    TriageResult,
)
from app.services.pii_scrubber import mask_pii
from app.services.store import get_store


def build_complaint(raw, channel, category, severity, status, days_ago, sentiment=Sentiment.FRUSTRATED, cluster_id=None, duplicate_of=None, customer_id=None, attachment_file=None, attachment_type=None):
    import os
    import shutil
    received_at = datetime.utcnow() - timedelta(days=days_ago, hours=days_ago % 5)
    masked, fields = mask_pii(raw)
    key_issue = raw.split(".")[0][:120]
    
    complaint_id = str(uuid4())
    channel_metadata = {"seed": True}
    
    if attachment_file and attachment_type:
        ext = os.path.splitext(attachment_file)[1]
        connectors_dir = os.path.dirname(os.path.abspath(__file__))
        # Resolve source path
        src_path = os.path.join(connectors_dir, "connectors", "mock_evidence", attachment_file)
        if not os.path.exists(src_path):
            src_path = os.path.join(connectors_dir, "mock_evidence", attachment_file)
            
        if os.path.exists(src_path):
            upload_dir = os.path.abspath(os.path.join(connectors_dir, "..", "frontend", "assets", "uploads"))
            os.makedirs(upload_dir, exist_ok=True)
            dst_name = f"{complaint_id}{ext}"
            dst_path = os.path.join(upload_dir, dst_name)
            try:
                shutil.copy(src_path, dst_path)
                channel_metadata["attachments"] = [{
                    "type": attachment_type,
                    "url": f"assets/uploads/{dst_name}"
                }]
            except Exception as e:
                print(f"Error copying seed attachment: {e}")
                
    complaint = Complaint(
        id=complaint_id,
        channel=channel,
        channel_metadata=channel_metadata,
        raw_text=raw,
        masked_text=masked,
        masked_fields=fields,
        customer_id=customer_id,
        received_at=received_at,
        triage=TriageResult(
            category=category,
            severity=severity,
            sentiment=sentiment,
            key_issue=key_issue,
            key_issues=[key_issue],
            suggested_response="Dear Customer, we have registered your complaint and our team is reviewing it on priority. We will update you within the applicable SLA.",
            confidence=0.88,
        ),
        cluster=DuplicateCluster(
            cluster_id=cluster_id or str(uuid4()),
            is_duplicate=bool(duplicate_of),
            duplicate_of=duplicate_of,
            cluster_size=2 if cluster_id else 1,
            systemic_alert=bool(cluster_id),
        ),
        status=status,
        escalation_level=EscalationLevel.L2_SUPERVISOR if status == ComplaintStatus.ESCALATED else EscalationLevel.L1_AGENT,
        resolved_at=(received_at + timedelta(hours=6)) if status == ComplaintStatus.RESOLVED else None,
    )
    complaint.communication_history = [
        HistoryMessage(author=MessageAuthor.CUSTOMER, author_name="Customer", content=raw, timestamp=received_at),
        HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content=f"Seed triage: {category.value} | {severity.value}", timestamp=received_at + timedelta(minutes=2)),
    ]
    if status == ComplaintStatus.ESCALATED:
        complaint.escalation_history.append(
            EscalationRecord(reason="Seeded escalation for demo SLA/compliance workflow", escalated_by="System")
        )
    return complaint


def main():
    store = get_store()
    store.clear()
    dup_cluster = str(uuid4())
    rows = [
        ("Fraudulent credit card charge of Rs 18,500 appeared today. I did not authorise this transaction.", Channel.WEB, Category.CREDIT_CARD, Severity.CRITICAL, ComplaintStatus.ESCALATED, 1, Sentiment.ANGRY, None, None, "CUST-30482", None, None),
        ("My mobile banking app shows a successful transfer but the beneficiary has not received money.", Channel.APP, Category.MOBILE_BANKING, Severity.CRITICAL, ComplaintStatus.PENDING, 0, Sentiment.ANGRY, dup_cluster, None, "CUST-10245", "app_error.png", "image/png"),
        ("Mobile banking transfer succeeded on screen but beneficiary did not receive the amount.", Channel.APP, Category.MOBILE_BANKING, Severity.HIGH, ComplaintStatus.PENDING, 0, Sentiment.FRUSTRATED, dup_cluster, "seed-duplicate", "CUST-10245", None, None),
        ("Home loan EMI was debited twice this month and I need a refund urgently.", Channel.EMAIL, Category.LOAN, Severity.HIGH, ComplaintStatus.PENDING, 2, Sentiment.ANGRY, None, None, "CUST-20591", None, None),
        ("Credit card reward points vanished after statement generation.", Channel.SOCIAL, Category.CREDIT_CARD, Severity.HIGH, ComplaintStatus.PENDING, 3, Sentiment.FRUSTRATED, None, None, None, None, None),
        ("Branch staff could not update my nominee details despite two visits.", Channel.BRANCH, Category.ACCOUNT, Severity.HIGH, ComplaintStatus.ESCALATED, 4, Sentiment.FRUSTRATED, None, None, None, None, None),
        ("Insurance claim has been pending for 20 days with no clear update.", Channel.EMAIL, Category.INSURANCE, Severity.HIGH, ComplaintStatus.PENDING, 5, Sentiment.FRUSTRATED, None, None, None, None, None),
        ("Account statement download fails from web portal every time.", Channel.WEB, Category.ACCOUNT, Severity.MEDIUM, ComplaintStatus.PENDING, 6, Sentiment.NEUTRAL, None, None, None, None, None),
        ("Investment portfolio value is not refreshing in the app.", Channel.APP, Category.INVESTMENT, Severity.MEDIUM, ComplaintStatus.PENDING, 7, Sentiment.NEUTRAL, None, None, None, None, None),
        ("Transcribed Audio: IVR disconnected me three times before connecting to an agent.", Channel.IVR, Category.ACCOUNT, Severity.MEDIUM, ComplaintStatus.PENDING, 8, Sentiment.FRUSTRATED, None, None, None, "voice_note.wav", "audio/wav"),
        ("Credit card annual fee waiver request has no response.", Channel.EMAIL, Category.CREDIT_CARD, Severity.MEDIUM, ComplaintStatus.RESOLVED, 9, Sentiment.NEUTRAL, None, None, None, None, None),
        ("Loan foreclosure letter not available at branch.", Channel.BRANCH, Category.LOAN, Severity.MEDIUM, ComplaintStatus.RESOLVED, 10, Sentiment.NEUTRAL, None, None, None, None, None),
        ("Insurance premium receipt is missing from email.", Channel.WEB, Category.INSURANCE, Severity.MEDIUM, ComplaintStatus.RESOLVED, 11, Sentiment.NEUTRAL, None, None, None, None, None),
        ("Mobile banking fingerprint login stopped working after update.", Channel.APP, Category.MOBILE_BANKING, Severity.MEDIUM, ComplaintStatus.ESCALATED, 12, Sentiment.FRUSTRATED, None, None, None, None, None),
        ("Mutual fund SIP date change request is still pending.", Channel.BRANCH, Category.INVESTMENT, Severity.MEDIUM, ComplaintStatus.PENDING, 13, Sentiment.NEUTRAL, None, None, None, None, None),
        ("Please update my email address for account alerts.", Channel.BRANCH, Category.ACCOUNT, Severity.LOW, ComplaintStatus.RESOLVED, 3, Sentiment.NEUTRAL, None, None, None, None, None),
        ("Need information about personal loan part payment charges.", Channel.IVR, Category.LOAN, Severity.LOW, ComplaintStatus.RESOLVED, 4, Sentiment.NEUTRAL, None, None, None, None, None),
        ("Credit card PIN generation instructions are confusing.", Channel.WEB, Category.CREDIT_CARD, Severity.LOW, ComplaintStatus.PENDING, 5, Sentiment.NEUTRAL, None, None, None, None, None),
        ("Insurance policy document download link expired.", Channel.EMAIL, Category.INSURANCE, Severity.LOW, ComplaintStatus.RESOLVED, 6, Sentiment.NEUTRAL, None, None, None, None, None),
        ("Investment tax statement needs clearer labels.", Channel.SOCIAL, Category.INVESTMENT, Severity.LOW, ComplaintStatus.ESCALATED, 7, Sentiment.NEUTRAL, None, None, None, None, None),
    ]
    saved = []
    for idx, row in enumerate(rows):
        c = build_complaint(*row)
        if row[7] == dup_cluster and idx == 1:
            saved_dup_id = c.id
        if row[8] == "seed-duplicate":
            c.cluster.duplicate_of = saved_dup_id
        saved.append(store.save(c))
    print(f"Seeded {len(saved)} complaints into backend/complaints.db")


if __name__ == "__main__":
    main()
