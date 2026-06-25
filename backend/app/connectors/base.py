from abc import ABC, abstractmethod
import logging
import httpx
from app.config import API_KEY

logger = logging.getLogger(__name__)

INGEST_URL = "http://127.0.0.1:8000/complaints/ingest"

class BaseConnector(ABC):
    channel: str

    @abstractmethod
    def fetch(self) -> list[dict]:
        """Pull raw complaint payloads from the external source."""
        pass

    @abstractmethod
    def normalize(self, raw: dict) -> dict:
        """
        Normalize raw data into the schema expected by /complaints/ingest:
        Returns: {
            "raw_text": str,
            "customer_id": str | None,
            "source_ref": str | None,
            "channel_metadata": dict
        }
        """
        pass

    def run(self):
        """Fetch, normalize, and ingest all complaints."""
        try:
            raw_items = self.fetch()
        except Exception as e:
            logger.error(f"Error fetching raw items for connector {self.channel}: {e}")
            return

        if not raw_items:
            return

        headers = {"X-Api-Key": API_KEY, "Content-Type": "application/json"}
        
        with httpx.Client() as client:
            for raw in raw_items:
                try:
                    payload = self.normalize(raw)
                    response = client.post(
                        INGEST_URL,
                        headers=headers,
                        json={
                            "channel": self.channel,
                            **payload
                        },
                        timeout=60.0
                    )
                    if response.status_code == 200:
                        logger.info(f"Ingested complaint from {self.channel}: {response.json().get('complaint', {}).get('id')}")
                    else:
                        logger.error(f"Failed to ingest: {response.status_code} - {response.text}")
                except Exception as e:
                    logger.error(f"Error executing normalization/ingestion for {self.channel}: {e}")
