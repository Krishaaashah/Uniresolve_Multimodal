import logging
from app.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

MOCK_EMAILS = [
    {
        "subject": "URGENT: Blocked Joint Account access",
        "sender": "priya.patel@email.com",
        "body": "Dear Customer Care, my joint savings account with my mother is locked and we are unable to make any online transfers. The bank branch staff has been unhelpful so far. This is critical for us to pay bills.",
        "customer_id": "CUST-20591"
    },
    {
        "subject": "Unauthorized transaction dispute",
        "sender": "amit.verma@email.com",
        "body": "I noticed an unauthorized payment of Rs 10,000 on my account statement. Please dispute this charge and block my card immediately to prevent further fraud.",
        "customer_id": "CUST-30482"
    },
    {
        "subject": "KYC upload status check",
        "sender": "aarav.sharma@email.com",
        "body": "Hi, I uploaded my re-verification KYC documents on the portal 10 days ago but my account dashboard still shows KYC pending. Can you please check and approve it?",
        "customer_id": "CUST-10245"
    },
    {
        "subject": "Unable to login to Netbanking",
        "sender": "rahul.gupta@email.com",
        "body": "Hello, I am trying to login to my internet banking account but it keeps saying invalid credentials. I tried resetting my password but the OTP is not arriving. Please help.",
        "customer_id": None
    },
    {
        "subject": "Home Loan interest rate clarification",
        "sender": "priya.patel@email.com",
        "body": "Dear team, I need a detailed amortization schedule for my home loan account. The interest rate listed in the app seems higher than what was agreed. Please clarify.",
        "customer_id": "CUST-20591"
    }
]

class EmailIMAPConnector(BaseConnector):
    channel = "email"

    def __init__(self):
        self.mock_index = 0

    def fetch(self) -> list[dict]:
        logger.info("Running Synthetic Email Connector.")
        # Cycle through mock list infinitely using modulo
        mock_email = MOCK_EMAILS[self.mock_index % len(MOCK_EMAILS)]
        self.mock_index += 1
        
        # Add a running count to make the source reference unique per cycle
        ref_id = f"sim-email-{self.mock_index}"
        return [{"data": mock_email, "ref": ref_id}]

    def normalize(self, raw: dict) -> dict:
        mock_data = raw["data"]
        return {
            "raw_text": f"Subject: {mock_data['subject']}\n\n{mock_data['body']}",
            "customer_id": mock_data["customer_id"],
            "source_ref": raw["ref"],
            "channel_metadata": {
                "sender": mock_data["sender"],
                "subject": mock_data["subject"],
                "simulated": True
            }
        }
