"""Mock Core Banking System (CBS) service for UniResolve.

Provides simulated account lookup and transaction histories for demo and verification.
"""

from typing import Optional

MOCK_CUSTOMERS = {
    "CUST-10001": {
        "id": "CUST-10001",
        "name": "Aarav Sharma",
        "phone": "+91 98765 91001",
        "email": "aarav.sharma@email.com",
        "account_no": "910283746501",
        "account_type": "Savings Account",
        "balance": "₹1,42,500.00",
        "kyc_status": "Verified",
        "risk_tier": "Low Risk",
        "branch": "Andheri West, Mumbai",
    },
    "CUST-10002": {
        "id": "CUST-10002",
        "name": "Priya Patel",
        "phone": "+91 91234 91002",
        "email": "priya.patel@email.com",
        "account_no": "100293847502",
        "account_type": "Home Loan Account",
        "balance": "₹24,50,000.00",
        "kyc_status": "Verified",
        "risk_tier": "Low Risk",
        "branch": "Navrangpura, Ahmedabad",
    },
    "CUST-10003": {
        "id": "CUST-10003",
        "name": "Amit Verma",
        "phone": "+91 88990 91003",
        "email": "amit.verma@email.com",
        "account_no": "201938475603",
        "account_type": "Current Account",
        "balance": "₹82,100.00",
        "kyc_status": "Verified",
        "risk_tier": "Medium Risk",
        "branch": "Connaught Place, New Delhi",
    },
    "CUST-10004": {
        "id": "CUST-10004",
        "name": "Neha Gupta",
        "phone": "+91 98112 91004",
        "email": "neha.gupta@email.com",
        "account_no": "301829475604",
        "account_type": "Salary Account",
        "balance": "₹65,400.00",
        "kyc_status": "Verified",
        "risk_tier": "Low Risk",
        "branch": "MG Road, Bengaluru",
    },
    "CUST-10005": {
        "id": "CUST-10005",
        "name": "Vikram Joshi",
        "phone": "+91 97654 91005",
        "email": "vikram.joshi@email.com",
        "account_no": "401928374505",
        "account_type": "Premium Savings",
        "balance": "₹3,15,000.00",
        "kyc_status": "Verified",
        "risk_tier": "Low Risk",
        "branch": "FC Road, Pune",
    },
    "CUST-10006": {
        "id": "CUST-10006",
        "name": "Ananya Deshmukh",
        "phone": "+91 98220 91006",
        "email": "ananya.deshmukh@email.com",
        "account_no": "501827364506",
        "account_type": "Business Current",
        "balance": "₹5,80,000.00",
        "kyc_status": "Verified",
        "risk_tier": "Medium Risk",
        "branch": "Deccan Gymkhana, Pune",
    },
    "CUST-10007": {
        "id": "CUST-10007",
        "name": "Rohan Mehta",
        "phone": "+91 99887 91007",
        "email": "rohan.mehta@email.com",
        "account_no": "601728394507",
        "account_type": "Privilege Credit Card",
        "balance": "₹1,95,000.00",
        "kyc_status": "Verified",
        "risk_tier": "High Risk",
        "branch": "Bandra Kurla Complex, Mumbai",
    },
    "CUST-10008": {
        "id": "CUST-10008",
        "name": "Pooja Iyer",
        "phone": "+91 98331 91008",
        "email": "pooja.iyer@email.com",
        "account_no": "701829384508",
        "account_type": "NRE/NRO Savings",
        "balance": "₹8,40,000.00",
        "kyc_status": "Verified",
        "risk_tier": "Low Risk",
        "branch": "T. Nagar, Chennai",
    },
    "CUST-10009": {
        "id": "CUST-10009",
        "name": "Karan Singhania",
        "phone": "+91 98450 91009",
        "email": "karan.singhania@email.com",
        "account_no": "801928374509",
        "account_type": "Wealth Fixed Deposit",
        "balance": "₹12,50,000.00",
        "kyc_status": "Verified",
        "risk_tier": "Low Risk",
        "branch": "Sector 17, Chandigarh",
    },
    "CUST-10010": {
        "id": "CUST-10010",
        "name": "Meera Nair",
        "phone": "+91 98901 91010",
        "email": "meera.nair@email.com",
        "account_no": "901827364510",
        "account_type": "Micro-Enterprise Current",
        "balance": "₹48,200.00",
        "kyc_status": "Verified",
        "risk_tier": "Low Risk",
        "branch": "Marine Drive, Kochi",
    },
}

# Add 8-digit numeric aliases (e.g. 10010001 -> CUST-10001)
for i in range(1, 11):
    k_cust = f"CUST-100{i:02d}"
    k_num = f"100100{i:02d}"
    if k_cust in MOCK_CUSTOMERS:
        MOCK_CUSTOMERS[k_num] = MOCK_CUSTOMERS[k_cust]


def generate_dynamic_profile(customer_id: str) -> dict:
    import hashlib
    h = hashlib.sha256(customer_id.encode()).hexdigest()
    val = int(h[:8], 16)
    
    first_names = ["Rohan", "Siddharth", "Neha", "Ananya", "Vikram", "Meera", "Karan", "Pooja", "Aarav", "Priya"]
    last_names = ["Mehta", "Joshi", "Gupta", "Deshmukh", "Singhania", "Iyer", "Nair", "Rao", "Sharma", "Patel"]
    fn = first_names[val % len(first_names)]
    ln = last_names[(val // len(first_names)) % len(last_names)]
    
    acct_types = ["Savings Account", "Current Account", "Salary Account", "Home Loan Account", "Premium Savings"]
    acct_type = acct_types[val % len(acct_types)]
    
    bal_val = 25000 + (val % 475000)
    bal_str = f"₹{bal_val:,.2f}"
    
    phone_suffix = str(10000 + (val % 89999))
    phone = f"+91 98765 {phone_suffix}"
    email = f"{fn.lower()}.{ln.lower()}{val % 99}@email.com"
    acct_no = str(9000000000 + (val % 999999999))
    
    return {
        "id": customer_id,
        "name": f"{fn} {ln}",
        "phone": phone,
        "email": email,
        "account_no": acct_no,
        "account_type": acct_type,
        "balance": bal_str,
        "kyc_status": "Verified",
        "risk_tier": "Low Risk" if val % 2 == 0 else "Medium Risk",
        "branch": "Main Branch, Mumbai",
    }


def get_customer_profile(customer_id: str) -> Optional[dict]:
    """Returns the mock customer profile enriched with transactions from database store."""
    if not customer_id:
        return None
        
    profile_base = None
    if customer_id in MOCK_CUSTOMERS:
        profile_base = dict(MOCK_CUSTOMERS[customer_id])
    elif (customer_id.isdigit() and len(customer_id) == 8) or customer_id.startswith("CUST-"):
        profile_base = generate_dynamic_profile(customer_id)
        
    if not profile_base:
        return None

    # Enrich with transactions from store
    try:
        from app.services.store import get_store
        store = get_store()
        db_txs = store.get_transactions_for_customer(customer_id)
        if not db_txs and profile_base.get("id") != customer_id:
            db_txs = store.get_transactions_for_customer(profile_base["id"])
        
        formatted_txs = []
        for tx in db_txs:
            formatted_txs.append({
                "date": tx.get("date", ""),
                "desc": tx.get("description", ""),
                "ref": tx.get("transaction_id", ""),
                "amount": tx.get("amount", ""),
                "status": "Success" if tx.get("status", "").lower() == "success" else "Failed"
            })
        profile_base["transactions"] = formatted_txs
    except Exception:
        profile_base["transactions"] = []

    return profile_base
