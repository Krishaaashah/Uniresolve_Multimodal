import logging
from app.connectors.base import BaseConnector

logger = logging.getLogger(__name__)

MOCK_POSTS = [
    {
        "title": "UPI transaction failed but money debited! Anyone else experiencing issues today?",
        "author": "anxious_user_99",
        "body": "I tried paying at a grocery shop using GPay UPI. The app says failed, but my account balance got debited. I am on the phone with customer care and their line is busy. Extremely frustrating!",
        "url": "https://reddit.com/r/UnionBank/comments/upi_fail"
    },
    {
        "title": "Fraudulent transactions on my savings account - urgent advice needed",
        "author": "finance_geek_india",
        "body": "I woke up to three messages showing transaction debits of Rs 5,000 each from an ATM in Mumbai, but I have my card here in Delhi. I did not share any OTP. Is my card cloned? I need help blocking it right now!",
        "url": "https://reddit.com/r/UnionBank/comments/fraud_alert"
    },
    {
        "title": "Netbanking login page loading extremely slowly since morning",
        "author": "mumbai_dev_9",
        "body": "Is the Union Bank net banking server down? I try to login to pay my bills but it keeps loading forever and then gives connection timed out. Please advise.",
        "url": "https://reddit.com/r/UnionBank/comments/netbanking_down"
    },
    {
        "title": "ATM card swallowed by machine at Andheri station!",
        "author": "mumbaikar_local",
        "body": "I entered my PIN to withdraw cash. The screen froze, transaction cancelled, but the machine did not return my card! How do I block this card urgently?",
        "url": "https://reddit.com/r/UnionBank/comments/atm_card_swallowed"
    }
]

class RedditAPIConnector(BaseConnector):
    channel = "social"

    def __init__(self):
        self.mock_index = 0

    def fetch(self) -> list[dict]:
        logger.info("Running Synthetic Social/Reddit Connector.")
        mock_post = MOCK_POSTS[self.mock_index % len(MOCK_POSTS)]
        self.mock_index += 1
        
        ref_id = f"sim-social-{self.mock_index}"
        return [{"data": mock_post, "ref": ref_id}]

    def normalize(self, raw: dict) -> dict:
        data = raw["data"]
        return {
            "raw_text": f"Social Media Post: {data['title']}\n\n{data['body']}",
            "customer_id": None,
            "source_ref": raw["ref"],
            "channel_metadata": {
                "author": data["author"],
                "url": data["url"],
                "simulated": True
            }
        }
