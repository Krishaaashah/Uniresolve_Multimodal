"""
Curated Synthetic Dataset for UniResolve Demo.

Contains a compact, realistic dataset covering all product permutations:
- Exact Omnichannel Duplicates (App + Web + Email)
- Semantic Duplicates (<7 days)
- Recurring Complaints (referencing previously resolved tickets)
- Systemic Outage Anomaly Cluster (>= 5 unique customers triggering outage alerts)
- High-Value / Fraud grievances requiring Supervisor HITL approval (needs_human)
- Missing detail transactions prompting interactive customer follow-up (needs_info)
- Vernacular Hindi and Marathi grievances
- Approaching statutory SLA breach (28-day aging)
- Multimodal evidence (OCR receipt image + IVR voice note audio)
- Real Core Banking System (CBS) transaction records
"""

import os
import shutil
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
    SLAStatus,
)
from app.services.pii_scrubber import mask_pii
from app.services.store import get_store
from app.services.clustering import get_clustering_service


def _copy_mock_attachment(complaint_id: str, attachment_file: str, attachment_type: str) -> dict:
    connectors_dir = os.path.dirname(os.path.abspath(__file__))
    src_path = os.path.join(connectors_dir, "connectors", "mock_evidence", attachment_file)
    if not os.path.exists(src_path):
        src_path = os.path.join(connectors_dir, "mock_evidence", attachment_file)

    if os.path.exists(src_path):
        upload_dir = os.path.abspath(os.path.join(connectors_dir, "..", "frontend", "public", "assets", "uploads"))
        os.makedirs(upload_dir, exist_ok=True)
        ext = os.path.splitext(attachment_file)[1]
        dst_name = f"{complaint_id}{ext}"
        dst_path = os.path.join(upload_dir, dst_name)
        try:
            shutil.copy(src_path, dst_path)
            return {
                "type": attachment_type,
                "url": f"assets/uploads/{dst_name}"
            }
        except Exception:
            pass
    return {}


def build_seed_complaint(
    raw_text: str,
    channel: Channel,
    category: str,
    severity: Severity,
    status: ComplaintStatus,
    days_ago: int,
    sentiment: Sentiment = Sentiment.FRUSTRATED,
    customer_id: str = None,
    transaction_id: str = None,
    attachment_file: str = None,
    attachment_type: str = None,
    needs_human: bool = False,
    needs_info: bool = False,
    missing_fields_q: str = None,
    detected_lang: str = "English",
    priority_score: int = 0,
    tenant_id: str = "Union Bank",
) -> Complaint:
    complaint_id = str(uuid4())
    received_at = datetime.utcnow() - timedelta(days=days_ago, hours=days_ago % 4)
    masked_text, masked_fields = mask_pii(raw_text)

    channel_metadata = {"seed": True}
    if attachment_file and attachment_type:
        attachment_obj = _copy_mock_attachment(complaint_id, attachment_file, attachment_type)
        if attachment_obj:
            channel_metadata["attachments"] = [attachment_obj]

    # Vernacular draft responses
    if detected_lang == "Hindi":
        suggested_draft = "प्रिय ग्राहक, आपकी शिकायत दर्ज कर ली गई है। हमारी तकनीकी टीम समस्या का समाधान कर रही है। संदर्भ आईडी: " + complaint_id[:8].upper()
    elif detected_lang == "Marathi":
        suggested_draft = "प्रिय ग्राहक, तुमची तक्रार नोंदवली गेली आहे. आमची टीम लवकरात लवकर याचे निवारण करेल. संदर्भ क्रमांक: " + complaint_id[:8].upper()
    else:
        suggested_draft = f"Dear Customer, we have registered your {category} grievance. Our support team is actively reviewing your request under reference #{complaint_id[:8].upper()}."

    key_issue = raw_text.split(".")[0][:120]

    # Pre-populate agent execution trace for demo visualization
    agent_trace = [
        {"node": "outage_check_node", "timestamp": received_at.isoformat(), "result": {"is_outage": False, "linked_incident": None}},
        {"node": "language_node", "timestamp": received_at.isoformat(), "result": {"detected_language": detected_lang, "translated_text": masked_text}},
        {"node": "triage_node", "timestamp": received_at.isoformat(), "result": {"category": category, "severity": severity.value, "priority_score": priority_score}},
        {"node": "info_check_node", "timestamp": received_at.isoformat(), "result": {"needs_info": needs_info, "question": missing_fields_q}},
        {"node": "cbs_verification_node", "timestamp": received_at.isoformat(), "result": {"cbs_verdict": "verified" if customer_id else "no_customer"}},
        {"node": "compliance_node", "timestamp": received_at.isoformat(), "result": {"sla_status": "breached" if days_ago >= 25 else "within_sla"}},
    ]
    if needs_human:
        agent_trace.append({"node": "human_approval_node", "timestamp": received_at.isoformat(), "result": "Paused for Supervisor approval."})
    else:
        agent_trace.append({"node": "drafting_node", "timestamp": received_at.isoformat(), "result": {"draft_generated": True}})

    triage_result = TriageResult(
        category=category,
        severity=severity,
        sentiment=sentiment,
        key_issue=key_issue,
        key_issues=[key_issue],
        suggested_response=suggested_draft,
        confidence=0.92,
        detected_language=detected_lang,
        severity_reason=f"Auto-classified as {severity.value} priority."
    )

    complaint = Complaint(
        id=complaint_id,
        channel=channel,
        channel_metadata=channel_metadata,
        raw_text=raw_text,
        masked_text=masked_text,
        masked_fields=masked_fields,
        customer_id=customer_id,
        transaction_id=transaction_id,
        summary=f"{category}: {key_issue}",
        received_at=received_at,
        triage=triage_result,
        status=status,
        escalation_level=EscalationLevel.L2_SUPERVISOR if (needs_human or status == ComplaintStatus.ESCALATED) else EscalationLevel.L1_AGENT,
        resolved_at=(received_at + timedelta(hours=8)) if status == ComplaintStatus.RESOLVED else None,
        tenant_id=tenant_id,
        needs_human=needs_human,
        needs_info=needs_info,
        missing_fields_question=missing_fields_q,
        detected_language=detected_lang,
        priority_score=priority_score,
        agent_trace=agent_trace,
    )

    complaint.communication_history = [
        HistoryMessage(author=MessageAuthor.CUSTOMER, author_name="Customer", content=raw_text, timestamp=received_at),
        HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content=f"Auto-triaged: {category} | {severity.value} | {sentiment.value}", timestamp=received_at + timedelta(minutes=1)),
    ]
    if needs_human:
        complaint.communication_history.append(
            HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content="Pipeline paused: High value transaction requires Supervisor authorization.")
        )
    elif needs_info:
        complaint.communication_history.append(
            HistoryMessage(author=MessageAuthor.AGENT, author_name="AI Assistant", content=missing_fields_q)
        )
    else:
        complaint.communication_history.append(
            HistoryMessage(author=MessageAuthor.AGENT, author_name="AI Assistant", content=suggested_draft, is_ai_draft=True)
        )

    return complaint


def seed_demo_dataset():
    """
    Seeds a high-impact, compact dataset demonstrating all core product features:
    1. Systemic Outage Anomaly Cluster (5 unique customers reporting UPI timeout)
    2. Exact Omnichannel Duplicate (App + Web with identical Txn ID)
    3. Semantic Duplicate (<7 days without Txn ID)
    4. Recurring Complaint (referencing prior resolved ticket)
    5. High-Value Fraud grievance pausing for Supervisor HITL Approval
    6. Missing Information Dispute triggering interactive customer prompt
    7. Vernacular Hindi & Marathi grievances
    8. Statutory SLA Breach & At-Risk Timelines
    9. Multimodal Evidence (Image OCR receipt + Voice note)
    10. CBS Real-time Transaction Ledger
    """
    store = get_store()

    # 1. Seed Core Banking System (CBS) transaction records
    mock_transactions = [
        {"transaction_id": "TXN-10001-A", "customer_id": "CUST-10001", "amount": "₹2,500.00", "status": "failed", "date": (datetime.utcnow() - timedelta(days=2)).date().isoformat(), "channel": "upi", "description": "UPI/GPay Transfer Failed"},
        {"transaction_id": "TXN-10002-A", "customer_id": "CUST-10002", "amount": "₹3,200.00", "status": "failed", "date": (datetime.utcnow() - timedelta(days=2)).date().isoformat(), "channel": "upi", "description": "UPI/PhonePe Gateway Timeout"},
        {"transaction_id": "TXN-10002-B", "customer_id": "CUST-10002", "amount": "₹5,000.00", "status": "failed", "date": (datetime.utcnow() - timedelta(days=10)).date().isoformat(), "channel": "atm", "description": "ATM/Cash Dispense Error"},
        {"transaction_id": "TXN-10004-A", "customer_id": "CUST-10004", "amount": "₹1,800.00", "status": "failed", "date": (datetime.utcnow() - timedelta(days=2)).date().isoformat(), "channel": "upi", "description": "UPI/Merchant Payment Failed"},
        {"transaction_id": "TXN-10005-A", "customer_id": "CUST-10005", "amount": "₹4,500.00", "status": "failed", "date": (datetime.utcnow() - timedelta(days=1)).date().isoformat(), "channel": "upi", "description": "UPI/Zomato Debit Failed"},
        {"transaction_id": "TXN-10006-A", "customer_id": "CUST-10006", "amount": "₹2,100.00", "status": "failed", "date": (datetime.utcnow() - timedelta(days=1)).date().isoformat(), "channel": "upi", "description": "UPI/Swiggy Order Timeout"},
        {"transaction_id": "TXN-10007-F", "customer_id": "CUST-10007", "amount": "₹45,000.00", "status": "failed", "date": (datetime.utcnow() - timedelta(days=1)).date().isoformat(), "channel": "card", "description": "Card/POS International Charge"},
        {"transaction_id": "TXN-10010-D", "customer_id": "CUST-10010", "amount": "₹18,450.00", "status": "success", "date": (datetime.utcnow() - timedelta(days=3)).date().isoformat(), "channel": "app", "description": "EMI/Home Loan Double Debit"},
    ]
    for tx in mock_transactions:
        store.save_transaction(tx)

    # 2. Curated Seed Grievances
    grievances = [
        # (1) Base Resolved Ticket for Recurrence Testing
        {
            "raw_text": "ATM dispensed Rs 0 but Rs 5000 debited from my account during cash withdrawal.",
            "channel": Channel.BRANCH, "category": "ATM Failure", "severity": Severity.HIGH, "status": ComplaintStatus.RESOLVED,
            "days_ago": 10, "customer_id": "CUST-10002", "transaction_id": "TXN-10002-B",
        },
        # (2) Recurring Complaint (Customer reports issue recurred after resolution)
        {
            "raw_text": "ATM cash dispense failed again for transaction TXN-10002-B. The reversal previously approved was reversed back.",
            "channel": Channel.APP, "category": "ATM Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10002", "transaction_id": "TXN-10002-B",
        },

        # (3) Systemic Outage Cluster Member 1 (Leader)
        {
            "raw_text": "UPI transfer of Rs 2500 failed but amount was debited from my account. Please reverse it.",
            "channel": Channel.APP, "category": "UPI Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10001", "transaction_id": "TXN-10001-A",
        },
        # (4) Exact Omnichannel Duplicate of (3) on Web
        {
            "raw_text": "Help! The UPI transfer of Rs 2500 is still failed but my account is debited. Revert ASAP.",
            "channel": Channel.WEB, "category": "UPI Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10001", "transaction_id": "TXN-10001-A",
        },
        # (5) Outage Member 2 (Different Customer, Similar UPI failure)
        {
            "raw_text": "UPI payment to merchant timed out but Rs 3200 was deducted from my savings account.",
            "channel": Channel.EMAIL, "category": "UPI Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10002", "transaction_id": "TXN-10002-A",
        },
        # (6) Outage Member 3 (Multimodal Image OCR Attachment)
        {
            "raw_text": "UPI payment failed error screen attached. The recipient did not get the money but account was debited.",
            "channel": Channel.APP, "category": "UPI Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10004", "transaction_id": "TXN-10004-A",
            "attachment_file": "app_error.png", "attachment_type": "image/png"
        },
        # (7) Outage Member 4 (Multimodal Voice Note Audio)
        {
            "raw_text": "Transcribed Audio: Yes, I tried to make a UPI payment at a store, the app froze and debited my money.",
            "channel": Channel.IVR, "category": "UPI Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10005", "transaction_id": "TXN-10005-A",
            "attachment_file": "voice_note.wav", "attachment_type": "audio/wav"
        },
        # (8) Outage Member 5 (5th Unique Customer -> Triggers Systemic Outage Alert!)
        {
            "raw_text": "UPI server timeout during payment transfer, amount was debited but status shows pending.",
            "channel": Channel.SOCIAL, "category": "UPI Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10006", "transaction_id": "TXN-10006-A",
        },

        # (9) Non-Transaction Branch Grievance
        {
            "raw_text": "I visited the Andheri West branch to update my signature, but branch staff refused to process my request.",
            "channel": Channel.BRANCH, "category": "Signature Update", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 3, "customer_id": "CUST-10003",
        },
        # (10) Semantic Duplicate of (9) within 7 days
        {
            "raw_text": "Signature update request was rejected by branch staff without explanation. Service is very slow.",
            "channel": Channel.WEB, "category": "Signature Update", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10003",
        },

        # (11) High-Value Fraud Case (Pauses for Supervisor HITL Approval)
        {
            "raw_text": "URGENT: Unauthorized international transaction of Rs 45,000 detected on my credit card! I did not authorize this payment.",
            "channel": Channel.EMAIL, "category": "Fraud", "severity": Severity.CRITICAL, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10007", "transaction_id": "TXN-10007-F",
            "needs_human": True, "priority_score": 15,
        },

        # (12) Missing Information Dispute (Interactive Customer Prompt)
        {
            "raw_text": "My debit card payment failed at a local store but money was deducted. Please refund my money.",
            "channel": Channel.WEB, "category": "Card Payment Decline", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10008",
            "needs_info": True,
            "missing_fields_q": "We noticed that some details are missing. To investigate this dispute, could you please provide the transaction reference ID (e.g. TXN-XXXXX) and the exact amount debited?",
        },

        # (13) Vernacular Hindi Grievance
        {
            "raw_text": "मेरा फिक्स्ड डिपॉजिट रिन्यूअल फॉर्म शाखा में जमा करने के बाद भी प्रोसेस नहीं हुआ है। कृपया मेरी मदद करें।",
            "channel": Channel.BRANCH, "category": "Fixed Deposit", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 4, "customer_id": "CUST-10009", "detected_lang": "Hindi",
        },

        # (14) Vernacular Marathi Grievance (Double Deduction)
        {
            "raw_text": "माझ्या खात्यातून गृहकर्जाचा ईएमआय १८,४५० रुपये दोनदा कापला गेला आहे. कृपया त्वरित परतावा द्या.",
            "channel": Channel.APP, "category": "Double Deduction", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10010", "transaction_id": "TXN-10010-D", "detected_lang": "Marathi",
        },

        # (15) Approaching Statutory 30-day SLA Breach (Aging 28 Days)
        {
            "raw_text": "I submitted a formal request for home loan foreclosure statement 28 days ago. Still awaiting response from the nodal officer.",
            "channel": Channel.BRANCH, "category": "Loan Foreclosure", "severity": Severity.HIGH, "status": ComplaintStatus.ESCALATED,
            "days_ago": 28, "customer_id": "CUST-10011",
        },
    ]

    clustering = get_clustering_service()
    saved_complaints = []

    for item in grievances:
        complaint = build_seed_complaint(**item)

        # Register in ClusteringService to build embeddings and evaluate duplicates
        cluster_res = clustering.check_and_register(
            complaint.id,
            complaint.masked_text,
            customer_id=complaint.customer_id,
            transaction_id=complaint.transaction_id
        )

        complaint.cluster = cluster_res
        complaint.recurring = cluster_res.recurring
        complaint.recurring_of = cluster_res.recurring_of

        # Link parent ticket if identified as duplicate
        if cluster_res.is_duplicate and cluster_res.duplicate_of:
            parent = store.get(cluster_res.duplicate_of)
            if parent:
                complaint.parent_ticket_id = parent.parent_ticket_id or parent.ticket_id

        store.save(complaint)
        store.log_ledger_event(complaint.id, "created", "customer")
        store.log_ledger_event(complaint.id, "triaged", "system")
        saved_complaints.append(complaint)

    print(f"Auto-Seeded {len(saved_complaints)} curated demo complaints into database.")
    return saved_complaints


def clear_demo_dataset():
    """
    Cleans up all seeded complaints, transactions, ledger, and FAISS indices
    when the server stops running, keeping the database completely clean.
    """
    store = get_store()
    store.clear()

    clustering = get_clustering_service()
    clustering.clear()

    # Clean frontend upload files
    connectors_dir = os.path.dirname(os.path.abspath(__file__))
    upload_dir = os.path.abspath(os.path.join(connectors_dir, "..", "frontend", "public", "assets", "uploads"))
    if os.path.exists(upload_dir):
        import glob
        for f in glob.glob(os.path.join(upload_dir, "*")):
            try:
                os.remove(f)
            except Exception:
                pass

    print("Auto-Cleaned synthetic demo dataset on server shutdown.")


if __name__ == "__main__":
    seed_demo_dataset()
