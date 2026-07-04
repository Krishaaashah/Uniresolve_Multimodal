"""
Semantic Duplicate Detection & Clustering Service
- Encodes complaints with Sentence-BERT (all-MiniLM-L6-v2)
- Stores embeddings in Qdrant (if active) or FAISS Index (if local)
- Detects duplicates via cosine similarity threshold
- Raises systemic alert when unique customer count >= CLUSTER_ALERT_THRESHOLD
"""

import os
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
SIMILARITY_THRESHOLD = 0.88      # cosine similarity to be considered duplicate
CLUSTER_ALERT_THRESHOLD = 5      # unique customers in a cluster → systemic alert
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

        # Qdrant configuration check
        from app.services import qdrant_service
        self.use_qdrant = bool(os.getenv("QDRANT_URL"))
        if self.use_qdrant:
            self.qdrant_ready = qdrant_service.init_qdrant_collection()
            logger.info(f"Qdrant integration check: use_qdrant={self.use_qdrant}, qdrant_ready={self.qdrant_ready}")
        else:
            self.qdrant_ready = False

        self._load()

    def _load(self):
        try:
            from sentence_transformers import SentenceTransformer
            logger.info("Loading SentenceTransformer (all-MiniLM-L6-v2)...")
            self.encoder = SentenceTransformer("all-MiniLM-L6-v2")
            self.healthy = True
            
            # If Qdrant is configured, skip loading local FAISS binary
            if self.use_qdrant and self.qdrant_ready:
                logger.info("Semantic Search will be executed using Qdrant.")
                return

            import faiss
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
        except Exception as e:
            logger.warning(f"Could not load FAISS/SentenceTransformer: {e}. Duplicate detection disabled.")
            self.healthy = False


    def _save_index(self):
        if self.use_qdrant and self.qdrant_ready:
            return
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

    def check_and_register(self, complaint_id: str, text: str, customer_id: Optional[str] = None, transaction_id: Optional[str] = None) -> DuplicateCluster:
        """
        Check if `text` is semantically similar to any existing complaint.
        Or check if exact ID duplicate (customer_id, transaction_id) exists,
        or if same customer has a complaint in the same semantic cluster within 7 days.
        Register the embedding regardless.
        Returns a DuplicateCluster describing the relationship.
        """
        from datetime import datetime, timedelta
        from app.services.store import get_store
        store = get_store()

        with self.lock:
            is_duplicate = False
            matched_complaint_id = None
            duplicate_reason = None
            cluster_id = None
            recurring = False
            recurring_of = None

            # Branch 1: Transaction-Based
            if customer_id and transaction_id:
                try:
                    all_complaints = store.all()
                    matched_ticket = None
                    for c in all_complaints:
                        if c.customer_id == customer_id and c.transaction_id == transaction_id and c.id != complaint_id:
                            matched_ticket = c
                            break
                    
                    if matched_ticket:
                        # If matched ticket is a duplicate, resolve to its primary parent ticket
                        if matched_ticket.parent_ticket_id:
                            for c in all_complaints:
                                if c.ticket_id == matched_ticket.parent_ticket_id:
                                    matched_ticket = c
                                    break

                        # Recurrence Guard: check if the matched ticket is resolved
                        from app.models.complaint import ComplaintStatus
                        if matched_ticket.status == ComplaintStatus.RESOLVED:
                            recurring = True
                            recurring_of = matched_ticket.ticket_id
                            duplicate_reason = "Re-reported transaction after resolution."
                            cluster_id = str(uuid.uuid4())
                        else:
                            is_duplicate = True
                            matched_complaint_id = matched_ticket.id
                            duplicate_reason = "exact_id"
                            cluster_id = matched_ticket.cluster.cluster_id if matched_ticket.cluster else None
                except Exception as e:
                    logger.warning(f"Error checking exact transaction ID duplicate: {e}")
                
                if not cluster_id:
                    cluster_id = str(uuid.uuid4())

            # Branch 2: Non-Transaction-Based
            else:
                # Option A: Qdrant Search
                if self.use_qdrant and self.qdrant_ready:
                    vec = self._encode(text)
                    if vec is not None:
                        vec_list = vec.tolist()[0]
                        from app.services import qdrant_service
                        results = qdrant_service.search_similar(vec_list, limit=10, score_threshold=SIMILARITY_THRESHOLD)
                        seven_days_ago = datetime.utcnow() - timedelta(days=7)
                        
                        for point in results:
                            potential_duplicate_id = point["id"]
                            payload = point.get("payload", {})
                            potential_cluster_id = payload.get("cluster_id")
                            
                            matched_ticket = store.get(potential_duplicate_id)
                            if matched_ticket:
                                if matched_ticket.parent_ticket_id:
                                    for c in store.all():
                                        if c.ticket_id == matched_ticket.parent_ticket_id:
                                            matched_ticket = c
                                            potential_cluster_id = matched_ticket.cluster.cluster_id if matched_ticket.cluster else None
                                            break

                                if (matched_ticket.customer_id == customer_id and 
                                    matched_ticket.received_at >= seven_days_ago and 
                                    matched_ticket.id != complaint_id):
                                    from app.models.complaint import ComplaintStatus
                                    if matched_ticket.status == ComplaintStatus.RESOLVED:
                                        recurring = True
                                        recurring_of = matched_ticket.ticket_id
                                        duplicate_reason = "Recurring issue for same customer (previous ticket resolved)."
                                        cluster_id = str(uuid.uuid4())
                                    else:
                                        is_duplicate = True
                                        matched_complaint_id = matched_ticket.id
                                        duplicate_reason = "semantic"
                                        cluster_id = potential_cluster_id
                                    break
                
                # Option B: FAISS Fallback
                else:
                    if self.index is not None and self.healthy and len(self.id_map) > 0:
                        vec = self._encode(text)
                        if vec is not None:
                            # Search up to 10 neighbors to find if any meet criteria
                            distances, indices = self.index.search(vec, k=min(10, len(self.id_map)))
                            seven_days_ago = datetime.utcnow() - timedelta(days=7)
                            
                            for rank in range(min(10, len(self.id_map))):
                                score = float(distances[0][rank])
                                idx = int(indices[0][rank])
                                if idx < 0 or idx >= len(self.id_map):
                                    continue
                                    
                                if score >= SIMILARITY_THRESHOLD:
                                    potential_duplicate_id = self.id_map[idx]
                                    potential_cluster_id = self.cluster_map.get(potential_duplicate_id)
                                    
                                    matched_ticket = store.get(potential_duplicate_id)
                                    if matched_ticket:
                                        # If matched ticket is a duplicate, resolve to its primary parent ticket
                                        if matched_ticket.parent_ticket_id:
                                            for c in store.all():
                                                if c.ticket_id == matched_ticket.parent_ticket_id:
                                                    matched_ticket = c
                                                    potential_cluster_id = matched_ticket.cluster.cluster_id if matched_ticket.cluster else None
                                                    break

                                        if (matched_ticket.customer_id == customer_id and 
                                            matched_ticket.received_at >= seven_days_ago and 
                                            matched_ticket.id != complaint_id):
                                            # Recurrence Guard: check if matched ticket is resolved
                                            from app.models.complaint import ComplaintStatus
                                            if matched_ticket.status == ComplaintStatus.RESOLVED:
                                                recurring = True
                                                recurring_of = matched_ticket.ticket_id
                                                duplicate_reason = "Recurring issue for same customer (previous ticket resolved)."
                                                cluster_id = str(uuid.uuid4())
                                            else:
                                                is_duplicate = True
                                                matched_complaint_id = matched_ticket.id
                                                duplicate_reason = "semantic"
                                                cluster_id = potential_cluster_id
                                            break
                                            
            if not cluster_id:
                cluster_id = str(uuid.uuid4())

            # Register embedding in Qdrant (if active) or FAISS index (if healthy)
            if self.use_qdrant and self.qdrant_ready:
                vec = self._encode(text)
                if vec is not None:
                    vec_list = vec.tolist()[0]
                    from app.services import qdrant_service
                    qdrant_service.upsert_vector(
                        complaint_id=complaint_id,
                        vector=vec_list,
                        payload={
                            "cluster_id": cluster_id,
                            "customer_id": customer_id
                        }
                    )
                    self.cluster_map[complaint_id] = cluster_id
                    self.cluster_counts[cluster_id] = self.cluster_counts.get(cluster_id, 0) + 1
            else:
                if self.index is not None and self.healthy:
                    vec = self._encode(text)
                    if vec is not None:
                        self.index.add(vec)
                        self.id_map.append(complaint_id)
                        self.cluster_map[complaint_id] = cluster_id
                        self.cluster_counts[cluster_id] = self.cluster_counts.get(cluster_id, 0) + 1
                        self._save_index()
                else:
                    self.cluster_map[complaint_id] = cluster_id
                    self.cluster_counts[cluster_id] = self.cluster_counts.get(cluster_id, 0) + 1

            # Retrieve all registered complaints belonging to this cluster
            cluster_complaints = [c for c in store.all() if c.cluster and c.cluster.cluster_id == cluster_id]
            unique_customers = {c.customer_id for c in cluster_complaints if c.customer_id}
            if customer_id:
                unique_customers.add(customer_id)

            cluster_size = self.cluster_counts[cluster_id]
            # Alert is only systemic if it affects 5 or more unique customers
            systemic_alert = len(unique_customers) >= CLUSTER_ALERT_THRESHOLD

            if systemic_alert:
                logger.warning(f"SYSTEMIC ALERT: Cluster {cluster_id[:8]} has {cluster_size} similar complaints representing {len(unique_customers)} distinct customers!")

            return DuplicateCluster(
                cluster_id=cluster_id,
                is_duplicate=is_duplicate,
                duplicate_of=matched_complaint_id,
                cluster_size=cluster_size,
                systemic_alert=systemic_alert,
                duplicate_reason=duplicate_reason,
                recurring=recurring,
                recurring_of=recurring_of
            )

    def get_cluster_complaints(self, cluster_id: str) -> list[str]:
        """Return all complaint IDs in a given cluster."""
        return [cid for cid, clid in self.cluster_map.items() if clid == cluster_id]

    def clear(self):
        """Reset the FAISS index and local metadata maps, and delete local cache files."""
        with self.lock:
            if self.use_qdrant and self.qdrant_ready:
                # In Qdrant, we could clear the collection, but here we just clear local cache
                self.cluster_map = {}
                self.cluster_counts = {}
                return
                
            import faiss
            self.index = faiss.IndexFlatIP(EMBEDDING_DIM)
            self.id_map = []
            self.cluster_map = {}
            self.cluster_counts = {}
            
            if INDEX_PATH.exists():
                try:
                    INDEX_PATH.unlink()
                except Exception as e:
                    logger.warning(f"Error deleting INDEX_PATH: {e}")
            if MAP_PATH.exists():
                try:
                    MAP_PATH.unlink()
                except Exception as e:
                    logger.warning(f"Error deleting MAP_PATH: {e}")
            logger.info("Semantic duplicate detection index cleared.")


# Singleton
_clustering_service: Optional[ClusteringService] = None


def get_clustering_service() -> ClusteringService:
    global _clustering_service
    if _clustering_service is None:
        _clustering_service = ClusteringService()
    return _clustering_service
