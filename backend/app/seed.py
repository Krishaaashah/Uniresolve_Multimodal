"""
Curated Synthetic Dataset for UniResolve Demo.

Contains an expanded, highly realistic enterprise dataset covering all product permutations:
1. Systemic Outage Anomaly Cluster (exactly 5 unique customers triggering systemic outage alert on UPI)
2. Second Sub-Threshold Cluster (3 unique customers on NetBanking OTP login, does NOT trigger alert)
3. Exact Omnichannel Duplicate (Mobile App + Web Portal with identical Customer ID & Txn ID)
4. Semantic Duplicate (<7 days without Txn ID, same customer)
5. Near-Miss Pair (similar topic >7 days apart, tests 7-day cutoff)
6. Recurring Grievance (referencing previously resolved ticket on same Txn ID)
7. High-Value Fraud grievance pausing for Supervisor HITL approval (needs_human=True, priority_score=15)
8. Missing Information Dispute triggering interactive customer follow-up (needs_info=True)
9. Vernacular Grievances (2 Hindi, 2 Marathi, 1 Code-mixed Hinglish)
10. Multimodal Evidence (Image OCR receipt screenshot + IVR voice note audio)
11. Non-Transactional Service Grievances (Branch signature update, staff misconduct, locker access)
12. SLA & Statutory RBI Aging (28-day approaching breach, 33-day ombudsman-eligible)
13. PII-Heavy Masking Test (Aadhaar, PAN, Card, Mobile numbers)
14. Low-Severity Happy Path (Resolved, satisfied customer)
15. CBS Ledger (100 full transaction records across 10 database customers)
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
        upload_dir = os.path.abspath(os.path.join(connectors_dir, "..", "..", "frontend", "public", "assets", "uploads"))
        os.makedirs(upload_dir, exist_ok=True)
        ext = os.path.splitext(attachment_file)[1]
        dst_name = f"{complaint_id}{ext}"
        dst_path = os.path.join(upload_dir, dst_name)
        try:
            shutil.copy(src_path, dst_path)
            return {
                "type": attachment_type,
                "url": f"/assets/uploads/{dst_name}"
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
        suggested_draft = f"प्रिय ग्राहक, आपकी {category} संबंधी शिकायत दर्ज कर ली गई है। हमारी तकनीकी टीम समस्या का निवारण कर रही है। संदर्भ आईडी: {complaint_id[:8].upper()}"
    elif detected_lang == "Marathi":
        suggested_draft = f"प्रिय ग्राहक, तुमची {category} बाबतची तक्रार नोंदवली गेली आहे. आमची सपोर्ट टीम लवकरच याचे निवारण करेल. संदर्भ क्रमांक: {complaint_id[:8].upper()}"
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
        severity_reason=f"Auto-classified as {severity.value} priority with {confidence_score(severity)} confidence." if 'confidence_score' in globals() else f"Auto-classified as {severity.value} priority."
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
            HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content="Pipeline paused: High-value transaction requires Supervisor authorization.")
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


def generate_cbs_transactions():
    """Generates exactly 100 CBS transactions for 10 database customers (10 txns each)."""
    now = datetime.utcnow()
    
    customers_meta = [
        {"id": "CUST-10001", "name": "Aarav Sharma"},
        {"id": "CUST-10002", "name": "Priya Patel"},
        {"id": "CUST-10003", "name": "Amit Verma"},
        {"id": "CUST-10004", "name": "Neha Gupta"},
        {"id": "CUST-10005", "name": "Vikram Joshi"},
        {"id": "CUST-10006", "name": "Ananya Deshmukh"},
        {"id": "CUST-10007", "name": "Rohan Mehta"},
        {"id": "CUST-10008", "name": "Pooja Iyer"},
        {"id": "CUST-10009", "name": "Karan Singhania"},
        {"id": "CUST-10010", "name": "Meera Nair"},
    ]
    
    # Pre-defined templates for transactions per customer to guarantee all referenced IDs exist
    tx_definitions = {
        "CUST-10001": [
            ("01", "₹2,500.00", "failed", 2, "upi", "UPI/GPay Transfer to Merchant VPA"),
            ("02", "₹1,200.00", "success", 4, "upi", "UPI/PhonePe Grocery Payment"),
            ("03", "₹10,000.00", "success", 7, "atm", "ATM Cash Withdrawal Andheri"),
            ("04", "₹15,000.00", "failed", 2, "branch", "Cheque Inward Clearing Return"),
            ("05", "₹75,000.00", "success", 12, "netbanking", "NEFT Salary Credit UnionCorp"),
            ("06", "₹4,300.00", "success", 15, "card", "POS Swiped Supermarket Mumbai"),
            ("07", "₹850.00", "success", 18, "upi", "UPI Quick Pay Swiggy"),
            ("08", "₹25,000.00", "success", 21, "netbanking", "IMPS Fund Transfer to Relative"),
            ("09", "₹5,000.00", "success", 24, "atm", "ATM Cash Withdrawal Bandra"),
            ("10", "₹1,100.00", "success", 27, "upi", "UPI Mobile Recharge Utility"),
        ],
        "CUST-10002": [
            ("01", "₹3,200.00", "failed", 2, "upi", "UPI/PhonePe Merchant Gateway Timeout"),
            ("02", "₹5,000.00", "failed", 10, "atm", "ATM Cash Dispense Machine Error"),
            ("03", "₹18,450.00", "success", 14, "emi", "Home Loan EMI Regular Auto-Debit"),
            ("04", "₹2,100.00", "success", 6, "card", "Card Fuel Station Surcharge"),
            ("05", "₹50,000.00", "success", 19, "netbanking", "RTGS Transfer Property Token"),
            ("06", "₹950.00", "success", 22, "upi", "UPI Transfer Utility Bill"),
            ("07", "₹12,000.00", "success", 25, "atm", "ATM Cash Withdrawal Navrangpura"),
            ("08", "₹3,400.00", "success", 26, "card", "POS Retail Purchase Cloth Store"),
            ("09", "₹1,800.00", "success", 28, "upi", "UPI Quick Payment Zomato"),
            ("10", "₹45,000.00", "success", 30, "netbanking", "IMPS Business Vendor Payment"),
        ],
        "CUST-10003": [
            ("01", "₹4,200.00", "failed", 1, "netbanking", "NetBanking Vendor IMPS Failed"),
            ("02", "₹8,500.00", "success", 5, "atm", "ATM Cash Withdrawal CP New Delhi"),
            ("03", "₹35,000.00", "success", 8, "netbanking", "NEFT Client Inward Remittance"),
            ("04", "₹1,450.00", "success", 11, "upi", "UPI Coffee Shop Payment"),
            ("05", "₹12,800.00", "success", 16, "card", "Card Online Amazon India"),
            ("06", "₹2,500.00", "success", 20, "upi", "UPI Electricity Bill Discom"),
            ("07", "₹20,000.00", "success", 23, "branch", "Cash Deposit Counter Slip"),
            ("08", "₹6,000.00", "success", 25, "atm", "ATM Cash Withdrawal Delhi"),
            ("09", "₹780.00", "success", 28, "upi", "UPI Fastag Auto Recharge"),
            ("10", "₹90,000.00", "success", 30, "netbanking", "RTGS Current Account Transfer"),
        ],
        "CUST-10004": [
            ("01", "₹1,800.00", "failed", 2, "upi", "UPI/Merchant Payment Failed QuickMart"),
            ("02", "₹3,500.00", "failed", 2, "card", "Card POS Debit Card Swipe Blocked"),
            ("03", "₹12,000.00", "pending", 1, "netbanking", "IMPS Transfer Pending Interbank"),
            ("04", "₹65,000.00", "success", 5, "netbanking", "Salary Inward Credit Infosys Corp"),
            ("05", "₹8,000.00", "success", 9, "atm", "ATM Cash Withdrawal MG Road"),
            ("06", "₹1,250.00", "success", 13, "upi", "UPI Restaurant Dine Out"),
            ("07", "₹4,999.00", "success", 17, "card", "Online Flipkart Appliance Purchase"),
            ("08", "₹550.00", "success", 21, "upi", "UPI Metro Smart Card Recharge"),
            ("09", "₹15,000.00", "success", 24, "netbanking", "Mutual Fund SIP Auto-Debit"),
            ("10", "₹3,000.00", "success", 29, "atm", "ATM Cash Dispense Bengaluru"),
        ],
        "CUST-10005": [
            ("01", "₹4,500.00", "failed", 1, "upi", "UPI/Store Merchant Debit Failed"),
            ("02", "₹10,000.00", "success", 3, "atm", "ATM Cash Withdrawal FC Road"),
            ("03", "₹28,000.00", "success", 6, "netbanking", "Fixed Deposit Interest Credit"),
            ("04", "₹2,300.00", "success", 10, "card", "POS Dining Marriott Pune"),
            ("05", "₹1,500.00", "success", 14, "upi", "UPI Grocery Kirana Store"),
            ("06", "₹50,000.00", "success", 18, "netbanking", "NEFT Investment Portfolio"),
            ("07", "₹8,500.00", "success", 21, "atm", "ATM Withdrawal Deccan Pune"),
            ("08", "₹3,100.00", "success", 24, "card", "Card Fuel Petrol Pump"),
            ("09", "₹1,200.00", "success", 27, "upi", "UPI Water Utility Bill"),
            ("10", "₹20,000.00", "success", 30, "branch", "Self Cheque Withdrawal Counter"),
        ],
        "CUST-10006": [
            ("01", "₹2,100.00", "failed", 1, "upi", "UPI Server Timeout Transfer"),
            ("02", "₹45,000.00", "success", 4, "netbanking", "GST Inward Tax Refund Credit"),
            ("03", "₹15,000.00", "success", 7, "atm", "ATM Cash Dispense Current Acct"),
            ("04", "₹3,800.00", "success", 11, "card", "POS Hardware Supplies Swiped"),
            ("05", "₹1,100.00", "success", 15, "upi", "UPI Office Refreshments"),
            ("06", "₹85,000.00", "success", 19, "netbanking", "RTGS Vendor Raw Materials"),
            ("07", "₹6,400.00", "success", 22, "card", "Card Travel Flight Booking"),
            ("08", "₹2,500.00", "success", 25, "upi", "UPI Broadband Internet Bill"),
            ("09", "₹10,000.00", "success", 28, "atm", "ATM Cash Withdrawal Pune"),
            ("10", "₹1,25,000.00", "success", 30, "netbanking", "NEFT Contract Payment Inward"),
        ],
        "CUST-10007": [
            ("01", "₹45,000.00", "failed", 1, "card", "Card POS International Charge London"),
            ("02", "₹8,900.00", "failed", 2, "card", "Card Online Luxury Retail Disputed"),
            ("03", "₹15,000.00", "success", 5, "atm", "ATM Cash Withdrawal BKC Mumbai"),
            ("04", "₹3,200.00", "success", 9, "upi", "UPI Restaurant Dinner Bandra"),
            ("05", "₹1,20,000.00", "success", 12, "netbanking", "NEFT Consulting Fee Received"),
            ("06", "₹25,000.00", "success", 16, "card", "Card Annual Club Membership"),
            ("07", "₹4,500.00", "success", 20, "upi", "UPI Shopping Retail Payment"),
            ("08", "₹10,000.00", "success", 23, "atm", "ATM Cash Withdrawal Airport"),
            ("09", "₹1,850.00", "success", 27, "card", "Card OTT & Cloud Subscriptions"),
            ("10", "₹60,000.00", "success", 30, "netbanking", "IMPS International Wire Outward"),
        ],
        "CUST-10008": [
            ("01", "₹5,400.00", "failed", 1, "card", "Card Payment Decline Local Store"),
            ("02", "₹1,50,000.00", "success", 3, "netbanking", "FCNR Remittance Foreign Inward"),
            ("03", "₹10,000.00", "success", 8, "atm", "ATM Cash Withdrawal Chennai T.Nagar"),
            ("04", "₹2,200.00", "success", 12, "upi", "UPI Taxi & Airport Ride"),
            ("05", "₹18,000.00", "success", 15, "card", "Card POS Departmental Store"),
            ("06", "₹45,000.00", "success", 19, "netbanking", "NRO to NRE Fund Transfer"),
            ("07", "₹1,250.00", "success", 22, "upi", "UPI Pharmacy Medicine Purchase"),
            ("08", "₹8,000.00", "success", 26, "atm", "ATM Cash Dispense Chennai"),
            ("09", "₹3,600.00", "success", 28, "card", "Card Online Hotel Booking"),
            ("10", "₹75,000.00", "success", 30, "netbanking", "NEFT Property Maintenance Fee"),
        ],
        "CUST-10009": [
            ("01", "₹5,00,000.00", "success", 4, "branch", "FD Term Deposit Booking 1 Year"),
            ("02", "₹12,500.00", "success", 7, "netbanking", "Quarterly FD Interest Payout"),
            ("03", "₹10,000.00", "success", 10, "atm", "ATM Cash Withdrawal Chandigarh 17"),
            ("04", "₹1,800.00", "success", 14, "upi", "UPI Fuel Payment Chandigarh"),
            ("05", "₹6,200.00", "success", 17, "card", "POS Retail Store Swiped"),
            ("06", "₹80,000.00", "success", 21, "netbanking", "NEFT Business Dividend Received"),
            ("07", "₹2,400.00", "success", 24, "upi", "UPI Grocery Mart Payment"),
            ("08", "₹5,000.00", "success", 27, "atm", "ATM Cash Withdrawal Sector 35"),
            ("09", "₹950.00", "success", 29, "card", "Online Streaming Service Fee"),
            ("10", "₹35,000.00", "success", 30, "netbanking", "IMPS Advance Tax Govt Payment"),
        ],
        "CUST-10010": [
            ("01", "₹18,450.00", "failed", 2, "app", "EMI/Home Loan Double Debit Duplicate"),
            ("02", "₹18,450.00", "success", 2, "app", "EMI/Home Loan Primary Monthly Debit"),
            ("03", "₹8,000.00", "success", 6, "atm", "ATM Cash Withdrawal Marine Drive"),
            ("04", "₹3,100.00", "success", 9, "card", "POS Seafood Supplies Kochi"),
            ("05", "₹1,450.00", "success", 13, "upi", "UPI Merchant Local Transfer"),
            ("06", "₹40,000.00", "success", 17, "netbanking", "NEFT Wholesale Invoice Settlement"),
            ("07", "₹5,500.00", "success", 21, "atm", "ATM Withdrawal Ernakulam"),
            ("08", "₹2,200.00", "success", 25, "card", "Card Fuel Surcharge Swiped"),
            ("09", "₹800.00", "success", 28, "upi", "UPI Quick Snack Restaurant"),
            ("10", "₹65,000.00", "success", 30, "netbanking", "IMPS Business Current Credit"),
        ],
    }
    
    transactions = []
    for cust in customers_meta:
        cid = cust["id"]
        defs = tx_definitions.get(cid, [])
        for seq, amt, status, days, ch, desc in defs:
            t_date = (now - timedelta(days=days)).date().isoformat()
            tx_id = f"TXN-{cid.split('-')[1]}-{seq}"
            transactions.append({
                "transaction_id": tx_id,
                "customer_id": cid,
                "amount": amt,
                "status": status,
                "date": t_date,
                "channel": ch,
                "description": desc,
            })
            
    return transactions


def seed_demo_dataset():
    """
    Seeds an expanded 28-complaint curated dataset and 100 CBS transactions.
    Hits every row of the 15-item enterprise coverage matrix.
    """
    store = get_store()
    clustering = get_clustering_service()

    # 1. Seed 100 Core Banking System (CBS) transaction records
    mock_transactions = generate_cbs_transactions()
    for tx in mock_transactions:
        store.save_transaction(tx)

    # 2. 28 Curated Demo Grievances (Sequenced Parent -> Child)
    grievances = [
        # ── (1) Systemic UPI Outage Cluster (5 Unique Customers) ───────────────
        # Leader 1
        {
            "raw_text": "UPI payment of Rs 2500 failed at merchant store but amount debited from my account. Please reverse it ref TXN-10001-01.",
            "channel": Channel.APP, "category": "UPI Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10001", "transaction_id": "TXN-10001-01",
        },
        # Exact Omnichannel Duplicate of 1 (on Web Portal)
        {
            "raw_text": "UPI transfer of Rs 2500 failed but amount was debited from account. Revert ASAP ref TXN-10001-01.",
            "channel": Channel.WEB, "category": "UPI Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10001", "transaction_id": "TXN-10001-01",
        },
        # Outage Member 2
        {
            "raw_text": "UPI payment to merchant timed out on UPI gateway but Rs 3200 was deducted from my savings account ref TXN-10002-01.",
            "channel": Channel.EMAIL, "category": "UPI Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10002", "transaction_id": "TXN-10002-01",
        },
        # Outage Member 3 (Multimodal Image OCR Attachment)
        {
            "raw_text": "UPI payment failed error screen attached. The recipient store did not get money but account was debited ref TXN-10004-01.",
            "channel": Channel.APP, "category": "UPI Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10004", "transaction_id": "TXN-10004-01",
            "attachment_file": "upi_failure_receipt.png", "attachment_type": "image/png"
        },
        # Outage Member 4 (Multimodal Voice Note)
        {
            "raw_text": "UPI payment of Rs 4500 failed at store but amount debited from my account. Please reverse it ref TXN-10005-01. Transcribed IVR voice note.",
            "channel": Channel.IVR, "category": "UPI Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10005", "transaction_id": "TXN-10005-01",
            "attachment_file": "voice_note.wav", "attachment_type": "audio/wav"
        },
        # Outage Member 5 (5th Unique Customer -> Triggers Systemic Outage Alert!)
        {
            "raw_text": "UPI server timeout during payment transfer, amount was debited from my account ref TXN-10006-01.",
            "channel": Channel.SOCIAL, "category": "UPI Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10006", "transaction_id": "TXN-10006-01",
        },

        # ── (2) Sub-Threshold Systemic Cluster (3 Customers - Does NOT Alert) ──
        {
            "raw_text": "NetBanking portal login failed because OTP was not received on my registered mobile number.",
            "channel": Channel.WEB, "category": "NetBanking", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10001",
        },
        {
            "raw_text": "Unable to login to NetBanking web portal, SMS OTP is timing out and not arriving on phone.",
            "channel": Channel.APP, "category": "NetBanking", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10003",
        },
        {
            "raw_text": "NetBanking login authentication error, OTP SMS not delivered to my registered phone number.",
            "channel": Channel.EMAIL, "category": "NetBanking", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10008",
        },

        # ── (3) Recurring Grievance (ATM Cash Dispense) ─────────────────────────
        # Base Resolved Ticket
        {
            "raw_text": "ATM dispensed Rs 0 but Rs 5000 was debited from my savings account during cash withdrawal ref TXN-10002-02.",
            "channel": Channel.BRANCH, "category": "ATM Failure", "severity": Severity.HIGH, "status": ComplaintStatus.RESOLVED,
            "days_ago": 10, "customer_id": "CUST-10002", "transaction_id": "TXN-10002-02",
            "attachment_file": "atm_slip.png", "attachment_type": "image/png"
        },
        # Recurring Complaint (Reversal pulled back after resolution)
        {
            "raw_text": "ATM cash dispense error recurred on transaction TXN-10002-02. The reversal previously approved was reversed back.",
            "channel": Channel.APP, "category": "ATM Failure", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10002", "transaction_id": "TXN-10002-02",
        },

        # ── (4) Semantic Duplicate (<7 Days, Same Customer, No Txn ID) ──────────
        # Base
        {
            "raw_text": "I visited the Andheri West branch to update my signature, but branch staff refused to process my request.",
            "channel": Channel.BRANCH, "category": "Signature Update", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 3, "customer_id": "CUST-10003",
        },
        # Follow-up (<7 days -> Flagged as semantic duplicate)
        {
            "raw_text": "Signature update request was rejected by branch staff without explanation. Service is very slow.",
            "channel": Channel.WEB, "category": "Signature Update", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10003",
        },

        # ── (5) Near-Miss Pair (Similar Topic, 9 Days Apart -> NOT Flagged) ────
        # Parent (11 days ago)
        {
            "raw_text": "I visited the branch today to update passbook, but the passbook printing kiosk machine was out of order.",
            "channel": Channel.WEB, "category": "Passbook", "severity": Severity.LOW, "status": ComplaintStatus.RESOLVED,
            "days_ago": 11, "customer_id": "CUST-10005",
        },
        # Child (2 days ago -> 9 days difference, tests 7-day cutoff rule)
        {
            "raw_text": "Branch visit for passbook update failed because the passbook printing machine at counter was out of order.",
            "channel": Channel.BRANCH, "category": "Passbook", "severity": Severity.LOW, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10005",
        },

        # ── (6) High-Value Fraud (Pauses for Supervisor HITL Approval) ─────────
        {
            "raw_text": "URGENT: Unauthorized international transaction of Rs 45,000 detected on my credit card! I did not authorize this payment ref TXN-10007-01.",
            "channel": Channel.EMAIL, "category": "Fraud", "severity": Severity.CRITICAL, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10007", "transaction_id": "TXN-10007-01",
            "needs_human": True, "priority_score": 15,
            "attachment_file": "card_fraud_alert.png", "attachment_type": "image/png"
        },

        # ── (7) Missing Information Dispute (Interactive AI Follow-up) ─────────
        {
            "raw_text": "My debit card payment failed at a local store but money was deducted. Please refund my money.",
            "channel": Channel.WEB, "category": "Card Payment Decline", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10008",
            "needs_info": True,
            "missing_fields_q": "We noticed that some details are missing. To investigate this dispute, could you please provide the transaction reference ID (e.g. TXN-10008-01) and the exact amount debited?",
        },

        # ── (8) Vernacular Grievances ──────────────────────────────────────────
        # Hindi 1: FD Renewal
        {
            "raw_text": "मेरा फिक्स्ड डिपॉजिट रिन्यूअल फॉर्म शाखा में जमा करने के बाद भी प्रोसेस नहीं हुआ है। कृपया मेरी मदद करें।",
            "channel": Channel.BRANCH, "category": "Fixed Deposit", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 4, "customer_id": "CUST-10009", "detected_lang": "Hindi",
        },
        # Hindi 2: Cheque Return
        {
            "raw_text": "शाखा में जमा किया गया चेक बिना किसी ठोस कारण के वापस कर दिया गया है। संदर्भ TXN-10001-04। कृपया जांच करें।",
            "channel": Channel.BRANCH, "category": "Cheque Return", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10001", "transaction_id": "TXN-10001-04", "detected_lang": "Hindi",
        },
        # Marathi 1: Double EMI Deduction
        {
            "raw_text": "माझ्या खात्यातून गृहकर्जाचा ईएमआय १८,४५० रुपये दोनदा कापला गेला आहे. संदर्भ TXN-10010-01. कृपया त्वरित परतावा द्या.",
            "channel": Channel.APP, "category": "Double Deduction", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10010", "transaction_id": "TXN-10010-01", "detected_lang": "Marathi",
        },
        # Marathi 2: Locker Access Delay
        {
            "raw_text": "शाखेतील बँक लॉकर उघडण्यासाठी कर्मचारी सहकार्य करत नाहीत आणि वारंवार फेऱ्या मारायला लावतात.",
            "channel": Channel.BRANCH, "category": "Locker Services", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 3, "customer_id": "CUST-10006", "detected_lang": "Marathi",
        },
        # Hinglish: IMPS Delay
        {
            "raw_text": "Bhai mera IMPS transfer pending show ho raha hai aur account se Rs 12000 cut ho gaye ref TXN-10004-03. Please jaldi reverse karo.",
            "channel": Channel.SOCIAL, "category": "IMPS Transfer", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 1, "customer_id": "CUST-10004", "transaction_id": "TXN-10004-03", "detected_lang": "Hinglish",
        },

        # ── (9) Additional Multimodal IVR Audio (Card Block) ───────────────────
        {
            "raw_text": "Transcribed Audio: My debit card was suddenly blocked at the merchant terminal during transaction TXN-10004-02 for customer CUST-10004.",
            "channel": Channel.IVR, "category": "Card Blocking", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10004", "transaction_id": "TXN-10004-02",
            "attachment_file": "demo_ivr_card_10004.wav", "attachment_type": "audio/wav"
        },

        # ── (10) Non-Transactional Branch Service (Staff Misconduct) ───────────
        {
            "raw_text": "I experienced severe rudeness and unprofessional conduct from the branch operations manager during my KYC document submission.",
            "channel": Channel.BRANCH, "category": "Staff Misconduct", "severity": Severity.MEDIUM, "status": ComplaintStatus.PENDING,
            "days_ago": 5, "customer_id": "CUST-10006",
        },

        # ── (11) SLA & Statutory RBI Aging ─────────────────────────────────────
        # 28-day aging (Approaching 30-day statutory threshold)
        {
            "raw_text": "I submitted a formal request for home loan foreclosure statement 28 days ago. Still awaiting response from the nodal officer.",
            "channel": Channel.BRANCH, "category": "Loan Foreclosure", "severity": Severity.HIGH, "status": ComplaintStatus.ESCALATED,
            "days_ago": 28, "customer_id": "CUST-10010",
        },
        # 33-day aging (Past 30-day threshold -> Ombudsman Eligible)
        {
            "raw_text": "Formal grievance for senior citizen interest rate credit submitted 33 days ago remains unresolved by principal nodal desk.",
            "channel": Channel.EMAIL, "category": "Interest Dispute", "severity": Severity.HIGH, "status": ComplaintStatus.ESCALATED,
            "days_ago": 33, "customer_id": "CUST-10009",
        },

        # ── (12) PII-Heavy Masking Test ────────────────────────────────────────
        {
            "raw_text": "Dispute on card charge TXN-10007-02. My Aadhaar is 4532 8901 2345, PAN is ABCDE1234F, and phone is 9876543210. Please contact me.",
            "channel": Channel.WEB, "category": "Card Dispute", "severity": Severity.HIGH, "status": ComplaintStatus.PENDING,
            "days_ago": 2, "customer_id": "CUST-10007", "transaction_id": "TXN-10007-02",
        },

        # ── (13) Low-Severity Happy-Path ───────────────────────────────────────
        {
            "raw_text": "Thank you for promptly unfreezing my NetBanking profile yesterday. Service was resolved smoothly.",
            "channel": Channel.APP, "category": "Account Services", "severity": Severity.LOW, "status": ComplaintStatus.RESOLVED,
            "days_ago": 0, "customer_id": "CUST-10005", "sentiment": Sentiment.SATISFIED,
        },
    ]

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

    print(f"Auto-Seeded {len(saved_complaints)} curated demo complaints and {len(mock_transactions)} CBS transactions.")
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
    upload_dir = os.path.abspath(os.path.join(connectors_dir, "..", "..", "frontend", "public", "assets", "uploads"))
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
