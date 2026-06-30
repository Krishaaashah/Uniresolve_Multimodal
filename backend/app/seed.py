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
    dup_cluster = str(uuid4())
    rows = [
        # Hindi vernacular complaints
        ("मेरा यूपीआई ट्रांसफर फेल हो गया है लेकिन मेरे बैंक खाते से 5000 रुपये कट गए हैं। कृपया वापस करें।", Channel.APP, Category.UPI, Severity.CRITICAL, ComplaintStatus.PENDING, 0, Sentiment.ANGRY, None, None, "CUST-HIN1", None, None, "UBI Subsidiary", "TXN-HIN1-F1"),

        # PII-heavy complaints
        ("Dear Union Bank, this is Aarav Sharma. Fraud transaction on my Debit Card 4532-7102-8394-1025. Please block it immediately. My Aadhaar is 8293-1029-4820 and Mobile is +91-9820192837. Account number 9102837465.", Channel.WEB, Category.CREDIT_CARD, Severity.CRITICAL, ComplaintStatus.PENDING, 2, Sentiment.ANGRY, None, None, "CUST-30482", None, None, "Union Bank", "TXN-30482-F1"),
        
        # 31+ days old complaints (for 30-day regulatory clock check)
        ("I have been waiting for my home loan foreclosure letter since May 1st. It has been more than 35 days. No response from Branch Manager.", Channel.BRANCH, Category.LOAN, Severity.HIGH, ComplaintStatus.PENDING, 35, Sentiment.FRUSTRATED, None, None, "CUST-OLD1", None, None, "Union Bank", "TXN-OLD1-S1"),
        ("Insurance policy activation is pending for 45 days. My mobile number is 9876543210. Reference claim is 98765.", Channel.EMAIL, Category.INSURANCE, Severity.MEDIUM, ComplaintStatus.PENDING, 45, Sentiment.FRUSTRATED, None, None, "CUST-OLD2", None, None, "Union Bank", "TXN-OLD2-F1"),
        
        # Legacy rows
        ("Fraudulent credit card charge of Rs 18,500 appeared today. I did not authorise this transaction.", Channel.WEB, Category.CREDIT_CARD, Severity.CRITICAL, ComplaintStatus.ESCALATED, 1, Sentiment.ANGRY, None, None, "CUST-30482", None, None, "Union Bank", "TXN-30482-F1"),
        ("My mobile banking app shows a successful transfer but the beneficiary has not received money.", Channel.APP, Category.MOBILE_BANKING, Severity.CRITICAL, ComplaintStatus.PENDING, 0, Sentiment.ANGRY, dup_cluster, None, "CUST-10245", "app_error.png", "image/png", "Union Bank", "TXN-10245-F1"),
        ("Mobile banking transfer succeeded on screen but beneficiary did not receive the amount.", Channel.APP, Category.MOBILE_BANKING, Severity.HIGH, ComplaintStatus.PENDING, 0, Sentiment.FRUSTRATED, dup_cluster, "seed-duplicate", "CUST-10245", None, None, "Union Bank", "TXN-10245-F1"),
        ("Home loan EMI was debited twice this month and I need a refund urgently.", Channel.EMAIL, Category.LOAN, Severity.HIGH, ComplaintStatus.PENDING, 2, Sentiment.ANGRY, None, None, "CUST-20591", None, None, "Union Bank", "TXN-20591-F1"),
        ("Credit card reward points vanished after statement generation.", Channel.SOCIAL, Category.CREDIT_CARD, Severity.HIGH, ComplaintStatus.PENDING, 3, Sentiment.FRUSTRATED, None, None, "CUST-20591", None, None, "Union Bank", "TXN-20591-F2"),
        ("Branch staff could not update my nominee details despite two visits.", Channel.BRANCH, Category.ACCOUNT, Severity.HIGH, ComplaintStatus.ESCALATED, 4, Sentiment.FRUSTRATED, None, None, "CUST-30482", None, None, "Union Bank", "TXN-30482-F2"),
        ("Insurance claim has been pending for 20 days with no clear update.", Channel.EMAIL, Category.INSURANCE, Severity.HIGH, ComplaintStatus.PENDING, 5, Sentiment.FRUSTRATED, None, None, "CUST-OLD2", None, None, "Union Bank", "TXN-OLD2-F2"),
        ("Account statement download fails from web portal every time.", Channel.WEB, Category.ACCOUNT, Severity.MEDIUM, ComplaintStatus.PENDING, 6, Sentiment.NEUTRAL, None, None, "CUST-HIN1", None, None, "Union Bank", "TXN-HIN1-F2"),
        ("Investment portfolio value is not refreshing in the app.", Channel.APP, Category.INVESTMENT, Severity.MEDIUM, ComplaintStatus.PENDING, 7, Sentiment.NEUTRAL, None, None, "CUST-10245", None, None, "Union Bank", "TXN-10245-F2"),
        ("Transcribed Audio: IVR disconnected me three times before connecting to an agent.", Channel.IVR, Category.ACCOUNT, Severity.MEDIUM, ComplaintStatus.PENDING, 8, Sentiment.FRUSTRATED, None, None, "CUST-OLD1", "voice_note.wav", "audio/wav", "Union Bank", "TXN-OLD1-S2"),
        ("Credit card annual fee waiver request has no response.", Channel.EMAIL, Category.CREDIT_CARD, Severity.MEDIUM, ComplaintStatus.RESOLVED, 9, Sentiment.NEUTRAL, None, None, "CUST-30482", None, None, "Union Bank", "TXN-30482-F3"),
        ("Loan foreclosure letter not available at branch.", Channel.BRANCH, Category.LOAN, Severity.MEDIUM, ComplaintStatus.RESOLVED, 10, Sentiment.NEUTRAL, None, None, "CUST-OLD1", None, None, "Union Bank", "TXN-OLD1-S3"),
        ("Insurance premium receipt is missing from email.", Channel.WEB, Category.INSURANCE, Severity.MEDIUM, ComplaintStatus.RESOLVED, 11, Sentiment.NEUTRAL, None, None, "CUST-OLD2", None, None, "Union Bank", "TXN-OLD2-F3"),
        ("Mobile banking fingerprint login stopped working after update.", Channel.APP, Category.MOBILE_BANKING, Severity.MEDIUM, ComplaintStatus.ESCALATED, 12, Sentiment.FRUSTRATED, None, None, "CUST-10245", None, None, "Union Bank", "TXN-10245-F3"),
        ("Mutual fund SIP date change request is still pending.", Channel.BRANCH, Category.INVESTMENT, Severity.MEDIUM, ComplaintStatus.PENDING, 13, Sentiment.NEUTRAL, None, None, "CUST-20591", None, None, "Union Bank", "TXN-20591-F3"),
        ("Please update my email address for account alerts.", Channel.BRANCH, Category.ACCOUNT, Severity.LOW, ComplaintStatus.RESOLVED, 3, Sentiment.NEUTRAL, None, None, "CUST-30482", None, None, "Union Bank", "TXN-30482-F4"),
        ("Need information about personal loan part payment charges.", Channel.IVR, Category.LOAN, Severity.LOW, ComplaintStatus.RESOLVED, 4, Sentiment.NEUTRAL, None, None, "CUST-OLD1", None, None, "Union Bank", "TXN-OLD1-S4"),
        ("Credit card PIN generation instructions are confusing.", Channel.WEB, Category.CREDIT_CARD, Severity.LOW, ComplaintStatus.PENDING, 5, Sentiment.NEUTRAL, None, None, "CUST-30482", None, None, "Union Bank", "TXN-30482-F5"),
        ("Insurance policy document download link expired.", Channel.EMAIL, Category.INSURANCE, Severity.LOW, ComplaintStatus.RESOLVED, 6, Sentiment.NEUTRAL, None, None, "CUST-OLD2", None, None, "Union Bank", "TXN-OLD2-F4"),
        ("Investment tax statement needs clearer labels.", Channel.SOCIAL, Category.INVESTMENT, Severity.LOW, ComplaintStatus.ESCALATED, 7, Sentiment.NEUTRAL, None, None, "CUST-10245", None, None, "Union Bank", "TXN-10245-F4"),
    ]
    saved = []
    for idx, row in enumerate(rows):
        c = build_complaint(*row)
        if row[7] == dup_cluster and row[8] is None:
            saved_dup_id = c.id
        if row[8] == "seed-duplicate":
            c.cluster.duplicate_of = saved_dup_id
        saved.append(store.save(c))

    print(f"Seeded {len(saved)} complaints into database")

    # Seed transactions
    transactions = []
    known_customers = ["CUST-HIN1", "CUST-30482", "CUST-OLD1", "CUST-OLD2", "CUST-20591", "CUST-10245"]
    channels = ["upi", "atm", "netbanking", "branch", "app"]
    descriptions = {
        "upi": ["UPI/GPay/Failed", "UPI/PhonePe/Transfer", "UPI/Zomato/Order", "UPI/AmazonPay/Refund"],
        "atm": ["ATM/Cash Withdrawal", "ATM/Failed Dispense", "ATM/Balance Enquiry"],
        "netbanking": ["IMPS/Transfer", "NEFT/Salary", "RTGS/Vendor Pay"],
        "branch": ["Branch Deposit", "Branch Withdrawal", "DD Issue"],
        "app": ["App Transfer/Self", "App/Recharge", "App/Bill Pay"]
    }
    
    # Specific transactions for test verification
    transactions.append({
        "transaction_id": "TXN-HIN1-F1",
        "customer_id": "CUST-HIN1",
        "amount": "₹5,000.00",
        "status": "failed",
        "date": "2026-06-29",
        "channel": "upi",
        "description": "UPI/GPay/Failed/Rent"
    })
    transactions.append({
        "transaction_id": "TXN-30482-F1",
        "customer_id": "CUST-30482",
        "amount": "₹18,500.00",
        "status": "failed",
        "date": "2026-06-28",
        "channel": "app",
        "description": "Card/Blocked Alert/Wrong PIN"
    })
    transactions.append({
        "transaction_id": "TXN-OLD1-S1",
        "customer_id": "CUST-OLD1",
        "amount": "₹25,000.00",
        "status": "success",
        "date": "2026-05-01",
        "channel": "branch",
        "description": "Home Loan foreclosure processing fee"
    })
    transactions.append({
        "transaction_id": "TXN-OLD2-F1",
        "customer_id": "CUST-OLD2",
        "amount": "₹3,000.00",
        "status": "failed",
        "date": "2026-05-15",
        "channel": "app",
        "description": "Insurance claim processing payment"
    })
    transactions.append({
        "transaction_id": "TXN-10245-F1",
        "customer_id": "CUST-10245",
        "amount": "₹3,000.00",
        "status": "failed",
        "date": "2026-06-30",
        "channel": "app",
        "description": "UPI/Transfer/Friend"
    })
    transactions.append({
        "transaction_id": "TXN-20591-F1",
        "customer_id": "CUST-20591",
        "amount": "₹12,000.00",
        "status": "failed",
        "date": "2026-06-28",
        "channel": "app",
        "description": "EMI Auto-debit retry"
    })
    transactions.append({
        "transaction_id": "TXN-20591-F2",
        "customer_id": "CUST-20591",
        "amount": "₹500.00",
        "status": "success",
        "date": "2026-06-27",
        "channel": "app",
        "description": "Credit card point redemption fee"
    })
    transactions.append({
        "transaction_id": "TXN-30482-F2",
        "customer_id": "CUST-30482",
        "amount": "₹10,000.00",
        "status": "success",
        "date": "2026-06-26",
        "channel": "branch",
        "description": "Nominee update processing"
    })
    transactions.append({
        "transaction_id": "TXN-OLD2-F2",
        "customer_id": "CUST-OLD2",
        "amount": "₹5,000.00",
        "status": "failed",
        "date": "2026-06-25",
        "channel": "email",
        "description": "Premium deposit check"
    })
    transactions.append({
        "transaction_id": "TXN-HIN1-F2",
        "customer_id": "CUST-HIN1",
        "amount": "₹100.00",
        "status": "success",
        "date": "2026-06-24",
        "channel": "web",
        "description": "Statement download processing fee"
    })
    transactions.append({
        "transaction_id": "TXN-10245-F2",
        "customer_id": "CUST-10245",
        "amount": "₹1,500.00",
        "status": "pending",
        "date": "2026-06-23",
        "channel": "app",
        "description": "Mutual fund SIP installment"
    })
    transactions.append({
        "transaction_id": "TXN-OLD1-S2",
        "customer_id": "CUST-OLD1",
        "amount": "₹250.00",
        "status": "success",
        "date": "2026-06-22",
        "channel": "ivr",
        "description": "IVR service query fee"
    })
    transactions.append({
        "transaction_id": "TXN-30482-F3",
        "customer_id": "CUST-30482",
        "amount": "₹0.00",
        "status": "success",
        "date": "2026-06-21",
        "channel": "email",
        "description": "Credit card annual fee check"
    })
    transactions.append({
        "transaction_id": "TXN-OLD1-S3",
        "customer_id": "CUST-OLD1",
        "amount": "₹15,000.00",
        "status": "success",
        "date": "2026-06-20",
        "channel": "branch",
        "description": "Loan document verification fee"
    })
    transactions.append({
        "transaction_id": "TXN-OLD2-F3",
        "customer_id": "CUST-OLD2",
        "amount": "₹2,500.00",
        "status": "success",
        "date": "2026-06-19",
        "channel": "web",
        "description": "Premium receipt processing"
    })
    transactions.append({
        "transaction_id": "TXN-10245-F3",
        "customer_id": "CUST-10245",
        "amount": "₹0.00",
        "status": "success",
        "date": "2026-06-18",
        "channel": "app",
        "description": "App biometric update"
    })
    transactions.append({
        "transaction_id": "TXN-20591-F3",
        "customer_id": "CUST-20591",
        "amount": "₹1,000.00",
        "status": "pending",
        "date": "2026-06-17",
        "channel": "branch",
        "description": "SIP modify request processing"
    })
    transactions.append({
        "transaction_id": "TXN-30482-F4",
        "customer_id": "CUST-30482",
        "amount": "₹0.00",
        "status": "success",
        "date": "2026-06-16",
        "channel": "branch",
        "description": "Nominee details lookup"
    })
    transactions.append({
        "transaction_id": "TXN-OLD1-S4",
        "customer_id": "CUST-OLD1",
        "amount": "₹0.00",
        "status": "success",
        "date": "2026-06-15",
        "channel": "ivr",
        "description": "Personal loan info call charge"
    })
    transactions.append({
        "transaction_id": "TXN-30482-F5",
        "customer_id": "CUST-30482",
        "amount": "₹100.00",
        "status": "success",
        "date": "2026-06-14",
        "channel": "web",
        "description": "PIN generation OTP SMS fee"
    })
    transactions.append({
        "transaction_id": "TXN-OLD2-F4",
        "customer_id": "CUST-OLD2",
        "amount": "₹0.00",
        "status": "success",
        "date": "2026-06-13",
        "channel": "email",
        "description": "Policy document check"
    })
    transactions.append({
        "transaction_id": "TXN-10245-F4",
        "customer_id": "CUST-10245",
        "amount": "₹0.00",
        "status": "success",
        "date": "2026-06-12",
        "channel": "social",
        "description": "Tax statement query logging"
    })
    
    # Generate random rows to total ~75 rows
    import random
    random.seed(42)
    for i in range(1, 71):
        cust = random.choice(known_customers)
        channel = random.choice(channels)
        status = random.choice(["success", "failed", "pending"])
        amount_val = random.randint(100, 50000)
        desc = random.choice(descriptions[channel])
        dt_str = (datetime.utcnow() - timedelta(days=random.randint(0, 30))).date().isoformat()
        
        transactions.append({
            "transaction_id": f"TXN-RAND-{i:03d}",
            "customer_id": cust,
            "amount": f"₹{amount_val:,.2f}",
            "status": status,
            "date": dt_str,
            "channel": channel,
            "description": f"{desc}/{i}"
        })
        
    for tx in transactions:
        store.save_transaction(tx)
        
    print(f"Seeded {len(transactions)} transactions into database")


if __name__ == "__main__":
    main()
