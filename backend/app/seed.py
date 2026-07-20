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


def build_complaint(raw, channel, category, severity, status, days_ago, sentiment=Sentiment.FRUSTRATED, cluster_id=None, duplicate_of=None, customer_id=None, attachment_file=None, attachment_type=None, tenant_id="Union Bank", transaction_id=None):
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
            upload_dir = os.path.abspath(os.path.join(connectors_dir, "..", "frontend", "public", "assets", "uploads"))
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
                
    detected_lang = "English"
    if any(ord(c) >= 0x0900 and ord(c) <= 0x097F for c in raw):
        detected_lang = "Hindi"

    from app.services.triage import generate_summary
    summary_val = generate_summary(masked)

    complaint = Complaint(
        id=complaint_id,
        channel=channel,
        channel_metadata=channel_metadata,
        raw_text=raw,
        masked_text=masked,
        masked_fields=fields,
        customer_id=customer_id,
        transaction_id=transaction_id,
        summary=summary_val,
        received_at=received_at,
        triage=TriageResult(
            category=category,
            severity=severity,
            sentiment=sentiment,
            key_issue=key_issue,
            key_issues=[key_issue],
            suggested_response="प्रिय ग्राहक, हमने आपकी शिकायत दर्ज कर ली है और हमारी टीम इस पर प्राथमिकता से विचार कर रही है। हम आपको लागू SLA के भीतर अपडेट करेंगे।" if detected_lang == "Hindi" else "Dear Customer, we have registered your complaint and our team is reviewing it on priority. We will update you within the applicable SLA.",
            confidence=0.88,
            detected_language=detected_lang,
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
        tenant_id=tenant_id,
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
    
    # 1. Seed specific transactions for the customers
    transactions = [
        {
            "transaction_id": "TXN-10001-A",
            "customer_id": "CUST-10001",
            "amount": "₹5,000.00",
            "status": "failed",
            "date": (datetime.utcnow() - timedelta(days=4)).date().isoformat(),
            "channel": "upi",
            "description": "UPI/Transfer/Failed"
        },
        {
            "transaction_id": "TXN-10001-B",
            "customer_id": "CUST-10001",
            "amount": "₹12,000.00",
            "status": "success",
            "date": (datetime.utcnow() - timedelta(days=2)).date().isoformat(),
            "channel": "app",
            "description": "Credit card annual bill payment"
        },
        {
            "transaction_id": "TXN-10002-A",
            "customer_id": "CUST-10002",
            "amount": "₹10,000.00",
            "status": "failed",
            "date": (datetime.utcnow() - timedelta(days=5)).date().isoformat(),
            "channel": "atm",
            "description": "ATM/Cash Dispense/Failed"
        },
        {
            "transaction_id": "TXN-10003-A",
            "customer_id": "CUST-10003",
            "amount": "₹8,500.00",
            "status": "success",
            "date": (datetime.utcnow() - timedelta(days=2)).date().isoformat(),
            "channel": "web",
            "description": "Online Shopping payment"
        },
        {
            "transaction_id": "TXN-10005-A",
            "customer_id": "CUST-10005",
            "amount": "₹3,000.00",
            "status": "failed",
            "date": (datetime.utcnow() - timedelta(days=2)).date().isoformat(),
            "channel": "upi",
            "description": "UPI/GPay transfer"
        }
    ]
    for tx in transactions:
        store.save_transaction(tx)
    print(f"Seeded {len(transactions)} transactions into database")

    # 2. Seed exactly 15 complaints with strict customer ID and transaction ID properties
    rows = [
        # 1. Transaction-based, App, UPI, Critical, Pending, 4 days ago, CUST-10001, TXN-10001-A
        (
            "Dear Union Bank, my UPI payment of Rs 5000 failed but amount was debited from my account. Please reverse it.",
            Channel.APP, Category.UPI, Severity.CRITICAL, ComplaintStatus.PENDING,
            4, Sentiment.ANGRY, None, None, "CUST-10001",
            None, None, "Union Bank", "TXN-10001-A"
        ),
        # 2. Transaction-based, Web, UPI, High, Pending, 3 days ago, CUST-10001, TXN-10001-A (Exact same customer + same txn ID = exact duplicate)
        (
            "Help! The UPI transfer of Rs 5000 is still failed but my account is debited. Revert ASAP.",
            Channel.WEB, Category.UPI, Severity.HIGH, ComplaintStatus.PENDING,
            3, Sentiment.ANGRY, None, None, "CUST-10001",
            None, None, "Union Bank", "TXN-10001-A"
        ),
        # 3. Transaction-based, App, Mobile Banking, High, Pending, 5 days ago, CUST-10002, TXN-10002-A (Multimodal: Image)
        (
            "I tried to transfer money but got this error screen. The recipient did not get the money.",
            Channel.APP, Category.MOBILE_BANKING, Severity.HIGH, ComplaintStatus.PENDING,
            5, Sentiment.FRUSTRATED, None, None, "CUST-10002",
            "app_error.png", "image/png", "Union Bank", "TXN-10002-A"
        ),
        # 4. Transaction-based, IVR, Account, High, Pending, 6 days ago, CUST-10002, TXN-10002-A (Multimodal: Audio, Exact same customer + same txn ID = exact duplicate of 3)
        (
            "Transcribed Audio: I was at the Airport ATM trying to withdraw cash, the machine made noise but no money came out, and my account was debited.",
            Channel.IVR, Category.ACCOUNT, Severity.HIGH, ComplaintStatus.PENDING,
            6, Sentiment.FRUSTRATED, None, None, "CUST-10002",
            "voice_note.wav", "audio/wav", "Union Bank", "TXN-10002-A"
        ),
        # 5. Transaction-based, App, UPI, Critical, Pending, 2 days ago, CUST-10005, TXN-10005-A (Systemic similarity to complaint 1 - different customer, similar UPI issue)
        (
            "My UPI transfer of Rs 3000 to my friend failed but my account was debited. Please credit back.",
            Channel.APP, Category.UPI, Severity.CRITICAL, ComplaintStatus.PENDING,
            2, Sentiment.ANGRY, None, None, "CUST-10005",
            None, None, "Union Bank", "TXN-10005-A"
        ),
        # 6. Non-transaction-based, Branch, Account, Medium, Pending, 4 days ago, CUST-10003, no txn
        (
            "I visited the branch to update my nominee details, but the branch manager was extremely rude and refused to process it.",
            Channel.BRANCH, Category.ACCOUNT, Severity.MEDIUM, ComplaintStatus.PENDING,
            4, Sentiment.FRUSTRATED, None, None, "CUST-10003",
            None, None, "Union Bank", None
        ),
        # 7. Non-transaction-based, Branch, Account, Medium, Pending, 2 days ago, CUST-10003, no txn (Semantic same customer duplicate of 6 within 7 days)
        (
            "Nominee details update request was rejected by branch staff. Why is this service so slow?",
            Channel.BRANCH, Category.ACCOUNT, Severity.MEDIUM, ComplaintStatus.PENDING,
            2, Sentiment.FRUSTRATED, None, None, "CUST-10003",
            None, None, "Union Bank", None
        ),
        # 8. Non-transaction-based, Web, Account, Medium, Pending, 3 days ago, CUST-10004, no txn (Multimodal: Image)
        (
            "Screenshot of the error when trying to update my KYC documents in the portal. It keeps loading forever.",
            Channel.WEB, Category.ACCOUNT, Severity.MEDIUM, ComplaintStatus.PENDING,
            3, Sentiment.NEUTRAL, None, None, "CUST-10004",
            "app_error.png", "image/png", "Union Bank", None
        ),
        # 9. Non-transaction-based, IVR, Account, Medium, Pending, 1 day ago, CUST-10004, no txn (Multimodal: Audio, Semantic same customer duplicate of 8 within 7 days)
        (
            "Transcribed Audio: Yes, I want to report that the KYC verification is pending for over two weeks now. I submitted all forms.",
            Channel.IVR, Category.ACCOUNT, Severity.MEDIUM, ComplaintStatus.PENDING,
            1, Sentiment.FRUSTRATED, None, None, "CUST-10004",
            "voice_note.wav", "audio/wav", "Union Bank", None
        ),
        # 10. Transaction-based, Email, Credit Card, High, Pending, 2 days ago, CUST-10001, TXN-10001-B
        (
            "My credit card bill was paid for Rs 12,000 but the transaction is showing twice in my credit card statement.",
            Channel.EMAIL, Category.CREDIT_CARD, Severity.HIGH, ComplaintStatus.PENDING,
            2, Sentiment.FRUSTRATED, None, None, "CUST-10001",
            None, None, "Union Bank", "TXN-10001-B"
        ),
        # 11. Non-transaction-based, Branch, Account, Medium, Pending, 5 days ago, CUST-10003, no txn (Hindi vernacular)
        (
            "मेरा फिक्स्ड डिपॉजिट रिन्यूअल फॉर्म शाखा में जमा करने के बाद भी प्रोसेस नहीं हुआ है। कृपया मदद करें।",
            Channel.BRANCH, Category.ACCOUNT, Severity.MEDIUM, ComplaintStatus.PENDING,
            5, Sentiment.FRUSTRATED, None, None, "CUST-10003",
            None, None, "Union Bank", None
        ),
        # 12. Non-transaction-based, App, Loan, Low, Pending, 3 days ago, CUST-10005, no txn
        (
            "I want to apply for a personal loan foreclosure letter, but the app shows error code 404 when downloading.",
            Channel.APP, Category.LOAN, Severity.LOW, ComplaintStatus.PENDING,
            3, Sentiment.NEUTRAL, None, None, "CUST-10005",
            None, None, "Union Bank", None
        ),
        # 13. Transaction-based, Web, Credit Card, Medium, Pending, 2 days ago, CUST-10003, TXN-10003-A
        (
            "I made an online shopping payment of Rs 8500. The payment was successful but I did not receive any OTP confirmation.",
            Channel.WEB, Category.CREDIT_CARD, Severity.MEDIUM, ComplaintStatus.PENDING,
            2, Sentiment.NEUTRAL, None, None, "CUST-10003",
            None, None, "Union Bank", "TXN-10003-A"
        ),
        # 14. Non-transaction-based, Email, Loan, High, Pending, 4 days ago, CUST-10002, no txn
        (
            "My home loan EMI interest rate was calculated incorrectly this month. It is higher than the agreement.",
            Channel.EMAIL, Category.LOAN, Severity.HIGH, ComplaintStatus.PENDING,
            4, Sentiment.ANGRY, None, None, "CUST-10002",
            None, None, "Union Bank", None
        ),
        # 15. Non-transaction-based, Social, Mobile Banking, Low, Pending, 1 day ago, CUST-10001, no txn
        (
            "My mobile banking password reset link is not receiving on my phone number. Please check SMS gateway.",
            Channel.SOCIAL, Category.MOBILE_BANKING, Severity.LOW, ComplaintStatus.PENDING,
            1, Sentiment.NEUTRAL, None, None, "CUST-10001",
            None, None, "Union Bank", None
        )
    ]

    saved = []
    for idx, row in enumerate(rows):
        c = build_complaint(*row)
        
        # Register in ClusteringService to correctly determine duplicate cluster metadata
        # and pre-warm/index the FAISS database!
        from app.services.clustering import get_clustering_service
        cluster_res = get_clustering_service().check_and_register(
            c.id,
            c.masked_text,
            customer_id=c.customer_id,
            transaction_id=c.transaction_id
        )
        
        c.cluster = cluster_res
        c.recurring = cluster_res.recurring
        c.recurring_of = cluster_res.recurring_of
        
        # Connect duplicate of
        if cluster_res.is_duplicate and cluster_res.duplicate_of:
            parent_c = store.get(cluster_res.duplicate_of)
            if parent_c:
                c.parent_ticket_id = parent_c.parent_ticket_id or parent_c.ticket_id
        
        saved.append(store.save(c))

    print(f"Seeded {len(saved)} complaints into database")


if __name__ == "__main__":
    main()
