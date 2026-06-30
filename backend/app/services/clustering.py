"""
Semantic Duplicate Detection & Clustering Service
- Encodes complaints with Sentence-BERT (all-MiniLM-L6-v2)
- Stores embeddings in FAISS FlatL2 index
- Detects duplicates via cosine similarity threshold
- Raises systemic alert when cluster size >= CLUSTER_ALERT_THRESHOLD
"""

import uuid
import logging
import json
import numpy as np
from pathlib import Path
from typing import Optional
import threading
from app.models.complaint import DuplicateCluster

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
INDEX_PATH = BASE_DIR / "faiss_index.bin"
MAP_PATH = BASE_DIR / "cluster_map.json"
SIMILARITY_THRESHOLD = 0.80      # cosine similarity to be considered duplicate
CLUSTER_ALERT_THRESHOLD = 5      # complaints in a cluster → systemic alert
EMBEDDING_DIM = 384              # all-MiniLM-L6-v2 output size


class ClusteringService:
    def __init__(self):
        self.lock = threading.Lock()
        self.encoder = None
        self.index = None
        self.id_map: list[str] = []           # position → complaint_id
        self.cluster_map: dict[str, str] = {} # complaint_id → cluster_id
        self.cluster_counts: dict[str, int] = {}
        self.healthy = False
        self._load()

    def _load(self):
        try:
            import faiss
            from sentence_transformers import SentenceTransformer
            logger.info("Loading SentenceTransformer (all-MiniLM-L6-v2)...")
            self.encoder = SentenceTransformer("all-MiniLM-L6-v2")
            self.index = faiss.IndexFlatIP(EMBEDDING_DIM)   # Inner Product ≈ cosine after normalization
            if INDEX_PATH.exists() and MAP_PATH.exists():
                try:
                    self.index = faiss.read_index(str(INDEX_PATH))
                    saved = json.loads(MAP_PATH.read_text())
                    self.cluster_map = saved.get("cluster_map", {})
                    self.cluster_counts = saved.get("cluster_counts", {})
                    self.id_map = saved.get("id_map", [])
                    logger.info(f"Loaded FAISS index with {len(self.id_map)} embeddings.")
                except Exception as e:
                    logger.warning(f"Could not load saved index: {e}. Starting fresh.")
            logger.info("FAISS index ready.")
            self.healthy = True
        except Exception as e:
            logger.warning(f"Could not load FAISS/SentenceTransformer: {e}. Duplicate detection disabled.")
            self.healthy = False


    def _save_index(self):
        try:
            import faiss

            faiss.write_index(self.index, str(INDEX_PATH))
            MAP_PATH.write_text(json.dumps({
                "cluster_map": self.cluster_map,
                "cluster_counts": self.cluster_counts,
                "id_map": self.id_map
            }))
        except Exception as e:
            logger.warning(f"Could not save FAISS index: {e}")

    def _encode(self, text: str) -> Optional[np.ndarray]:
        if self.encoder is None:
            return None
        vec = self.encoder.encode([text], normalize_embeddings=True)
        return vec.astype("float32")

    def check_and_register(self, complaint_id: str, text: str) -> DuplicateCluster:
        """
        Check if `text` is semantically similar to any existing complaint.
        Register the embedding regardless.
        Returns a DuplicateCluster describing the relationship.
        """
        with self.lock:
            if self.index is None or not self.healthy:
                # No model — every complaint is its own cluster

                new_cluster_id = str(uuid.uuid4())
                self.cluster_map[complaint_id] = new_cluster_id
                self.cluster_counts[new_cluster_id] = 1
                return DuplicateCluster(
                    cluster_id=new_cluster_id,
                    is_duplicate=False,
                    cluster_size=1,
                    systemic_alert=False,
                )

            vec = self._encode(text)
            is_duplicate = False
            matched_complaint_id = None
            cluster_id = str(uuid.uuid4())

            if len(self.id_map) > 0:
                # Search for nearest neighbour
                distances, indices = self.index.search(vec, k=min(5, len(self.id_map)))
                best_score = float(distances[0][0])
                best_idx = int(indices[0][0])

                if best_score >= SIMILARITY_THRESHOLD:
                    is_duplicate = True
                    matched_complaint_id = self.id_map[best_idx]
                    # Inherit cluster from the matched complaint
                    cluster_id = self.cluster_map.get(matched_complaint_id, str(uuid.uuid4()))

            # Register
            self.index.add(vec)
            self.id_map.append(complaint_id)
            self.cluster_map[complaint_id] = cluster_id
            self.cluster_counts[cluster_id] = self.cluster_counts.get(cluster_id, 0) + 1
            if self.index is not None:
                self._save_index()

            cluster_size = self.cluster_counts[cluster_id]
            systemic_alert = cluster_size >= CLUSTER_ALERT_THRESHOLD

            if systemic_alert:
                logger.warning(f"SYSTEMIC ALERT: Cluster {cluster_id[:8]} has {cluster_size} similar complaints!")

            return DuplicateCluster(
                cluster_id=cluster_id,
                is_duplicate=is_duplicate,
                duplicate_of=matched_complaint_id,
                cluster_size=cluster_size,
                systemic_alert=systemic_alert,
            )
    def get_cluster_complaints(self, cluster_id: str) -> list[str]:
        """Return all complaint IDs in a given cluster."""
        return [cid for cid, clid in self.cluster_map.items() if clid == cluster_id]


# Singleton
_clustering_service: Optional[ClusteringService] = None


def get_clustering_service() -> ClusteringService:
    global _clustering_service
    if _clustering_service is None:
        _clustering_service = ClusteringService()
    return _clustering_service
