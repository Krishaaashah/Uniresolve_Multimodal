"""Mock Core Banking System (CBS) service for UniResolve.

Provides simulated account lookup and transaction histories for demo and verification.
"""

MOCK_CUSTOMERS = {
    "10010245": {
        "id": "10010245",
        "name": "Aarav Sharma",
        "phone": "+91 98765 43210",
        "email": "aarav.sharma@email.com",
        "account_no": "9102837465",
        "account_type": "Savings Account",
        "balance": "Rs 1,42,500.00",
        "kyc_status": "Verified",
        "risk_tier": "Low Risk",
        "transactions": [
            {"date": "2026-06-23", "desc": "UPI/Failed/GPay/Zomato", "ref": "UPI657483", "amount": "- Rs 3,000.00", "status": "Failed"},
            {"date": "2026-06-22", "desc": "ATM/Cash Withdrawal/Mumbai", "ref": "ATM298471", "amount": "- Rs 5,000.00", "status": "Success"},
            {"date": "2026-06-20", "desc": "NEFT/Salary/UnionCorp", "ref": "NFT882736", "amount": "+ Rs 75,000.00", "status": "Success"},
            {"date": "2026-06-19", "desc": "UPI/Transfer/Friend", "ref": "UPI229384", "amount": "- Rs 2,000.00", "status": "Success"},
            {"date": "2026-06-15", "desc": "Card/POS/Petrol Pump", "ref": "CRD982736", "amount": "- Rs 1,500.00", "status": "Success"}
        ]
    },
    "20020591": {
        "id": "20020591",
        "name": "Priya Patel",
        "phone": "+91 91234 56789",
        "email": "priya.patel@email.com",
        "account_no": "1002938475",
        "account_type": "Home Loan Account",
        "balance": "Rs 24,50,000.00",
        "kyc_status": "Verified",
        "risk_tier": "Low Risk",
        "transactions": [
            {"date": "2026-06-21", "desc": "EMI/Home Loan Debit/Double", "ref": "EMI987654", "amount": "- Rs 18,450.00", "status": "Success"},
            {"date": "2026-06-21", "desc": "EMI/Home Loan Debit/Duplicate", "ref": "EMI987655", "amount": "- Rs 18,450.00", "status": "Success"},
            {"date": "2026-05-21", "desc": "EMI/Home Loan Debit/Regular", "ref": "EMI776251", "amount": "- Rs 18,450.00", "status": "Success"}
        ]
    },
    "30030482": {
        "id": "30030482",
        "name": "Amit Verma",
        "phone": "+91 88990 11223",
        "email": "amit.verma@email.com",
        "account_no": "2019384756",
        "account_type": "Current Account",
        "balance": "Rs 82,100.00",
        "kyc_status": "Verified",
        "risk_tier": "Medium Risk",
        "transactions": [
            {"date": "2026-06-18", "desc": "ATM swallowed card / cash fail", "ref": "ATM112233", "amount": "- Rs 10,000.00", "status": "Failed"},
            {"date": "2026-06-17", "desc": "Card/Blocked Alert/Wrong PIN", "ref": "CRD228833", "amount": "Rs 0.00", "status": "Success"},
            {"date": "2026-06-14", "desc": "Online Shopping/Amazon", "ref": "ONL992837", "amount": "- Rs 4,320.00", "status": "Success"}
        ]
    }
}


def get_customer_profile(customer_id: str) -> dict:
    """Returns the mock customer profile or None if not found."""
    return MOCK_CUSTOMERS.get(customer_id)
