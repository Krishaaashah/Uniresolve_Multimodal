"""
Qdrant Vector Database Connector Service
Performs distributed vector storage and semantic search via Qdrant's REST API.
"""

import os
import logging
import httpx
from typing import Optional, List, Dict, Any

logger = logging.getLogger(__name__)

# Qdrant configuration from environment variables
QDRANT_URL = os.getenv("QDRANT_URL", "http://localhost:6333")
QDRANT_API_KEY = os.getenv("QDRANT_API_KEY", "")
COLLECTION_NAME = "complaints"
VECTOR_DIM = 384  # SentenceTransformers all-MiniLM-L6-v2 dimension

def get_headers() -> Dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if QDRANT_API_KEY:
        headers["api-key"] = QDRANT_API_KEY
    return headers

def init_qdrant_collection() -> bool:
    """Creates the complaints collection in Qdrant if it does not exist."""
    if not QDRANT_URL:
        return False
    try:
        url = f"{QDRANT_URL}/collections/{COLLECTION_NAME}"
        # Check if collection exists
        res = httpx.get(url, headers=get_headers(), timeout=5.0)
        if res.status_code == 200:
            return True
            
        # Create collection
        payload = {
            "vectors": {
                "size": VECTOR_DIM,
                "distance": "Cosine"
            }
        }
        create_res = httpx.put(url, json=payload, headers=get_headers(), timeout=5.0)
        if create_res.status_code == 200:
            logger.info(f"Created Qdrant collection: {COLLECTION_NAME}")
            return True
        else:
            logger.warning(f"Failed to create Qdrant collection: {create_res.text}")
            return False
    except Exception as e:
        logger.warning(f"Could not connect to Qdrant at {QDRANT_URL}: {e}")
        return False

def upsert_vector(complaint_id: str, vector: List[float], payload: Dict[str, Any]) -> bool:
    """Inserts or updates a complaint's vector and payload in Qdrant."""
    if not QDRANT_URL:
        return False
    try:
        url = f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points?wait=true"
        body = {
            "points": [
                {
                    "id": complaint_id,
                    "vector": vector,
                    "payload": payload
                }
            ]
        }
        res = httpx.put(url, json=body, headers=get_headers(), timeout=5.0)
        return res.status_code == 200
    except Exception as e:
        logger.warning(f"Failed to upsert vector to Qdrant: {e}")
        return False

def search_similar(vector: List[float], limit: int = 5, score_threshold: float = 0.88) -> List[Dict[str, Any]]:
    """Searches for similar complaints in Qdrant based on vector similarity."""
    if not QDRANT_URL:
        return []
    try:
        url = f"{QDRANT_URL}/collections/{COLLECTION_NAME}/points/search"
        body = {
            "vector": vector,
            "limit": limit,
            "score_threshold": score_threshold,
            "with_payload": True,
            "with_vector": False
        }
        res = httpx.post(url, json=body, headers=get_headers(), timeout=5.0)
        if res.status_code == 200:
            return res.json().get("result", [])
        return []
    except Exception as e:
        logger.warning(f"Failed to search similar vectors in Qdrant: {e}")
        return []
