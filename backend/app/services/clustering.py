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
from app.config import SIMILARITY_THRESHOLD, CLUSTER_ALERT_THRESHOLD
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

            # Compute embedding once
            vec = self._encode(text)
            candidates = []

            # 1. Exact transaction ID match check (as a prioritized check if customer_id and transaction_id are present)
            exact_match_ticket = None
            if customer_id and transaction_id:
                try:
                    all_complaints = store.all()
                    for c in all_complaints:
                        if c.customer_id == customer_id and c.transaction_id == transaction_id and c.id != complaint_id:
                            exact_match_ticket = c
                            break
                    
                    if exact_match_ticket:
                        # Resolve matched ticket to primary parent if it is a duplicate
                        if exact_match_ticket.parent_ticket_id:
                            for c in all_complaints:
                                if c.ticket_id == exact_match_ticket.parent_ticket_id:
                                    exact_match_ticket = c
                                    break
                except Exception as e:
                    logger.warning(f"Error checking exact transaction ID duplicate: {e}")

            # 2. Retrieve semantic search candidates
            if vec is not None:
                if self.use_qdrant and self.qdrant_ready:
                    try:
                        vec_list = vec.tolist()[0]
                        from app.services import qdrant_service
                        results = qdrant_service.search_similar(vec_list, limit=10, score_threshold=SIMILARITY_THRESHOLD)
                        for point in results:
                            candidates.append({
                                "id": point["id"],
                                "score": point["score"]
                            })
                    except Exception as e:
                        logger.warning(f"Error searching Qdrant: {e}")
                else:
                    if self.index is not None and self.healthy and len(self.id_map) > 0:
                        try:
                            distances, indices = self.index.search(vec, k=min(10, len(self.id_map)))
                            for rank in range(min(10, len(self.id_map))):
                                score = float(distances[0][rank])
                                idx = int(indices[0][rank])
                                if idx >= 0 and idx < len(self.id_map) and score >= SIMILARITY_THRESHOLD:
                                    candidates.append({
                                        "id": self.id_map[idx],
                                        "score": score
                                    })
                        except Exception as e:
                            logger.warning(f"Error searching FAISS: {e}")

            # 3. Classify relation
            from app.models.complaint import ComplaintStatus
            seven_days_ago = datetime.utcnow() - timedelta(days=7)

            if exact_match_ticket:
                # Rule 1 & 2: Same customer + same transaction
                cluster_id = exact_match_ticket.cluster.cluster_id if exact_match_ticket.cluster else None
                if exact_match_ticket.status == ComplaintStatus.RESOLVED:
                    recurring = True
                    recurring_of = exact_match_ticket.ticket_id
                    duplicate_reason = "exact_id"
                else:
                    is_duplicate = True
                    matched_complaint_id = exact_match_ticket.id
                    duplicate_reason = "exact_id"
            else:
                same_cust_match = None
                diff_cust_match = None
                
                for cand in candidates:
                    matched_ticket = store.get(cand["id"])
                    if not matched_ticket or matched_ticket.id == complaint_id:
                        continue
                    
                    # Resolve matched ticket to primary parent if it is a duplicate
                    if matched_ticket.parent_ticket_id:
                        for c in store.all():
                            if c.ticket_id == matched_ticket.parent_ticket_id:
                                matched_ticket = c
                                break

                    is_same_customer = (customer_id is not None and matched_ticket.customer_id == customer_id)

                    if is_same_customer:
                        if matched_ticket.received_at >= seven_days_ago:
                            same_cust_match = matched_ticket
                            break
                    else:
                        if not diff_cust_match:
                            diff_cust_match = matched_ticket

                if same_cust_match:
                    cluster_id = same_cust_match.cluster.cluster_id if same_cust_match.cluster else None
                    if same_cust_match.status == ComplaintStatus.RESOLVED:
                        recurring = True
                        recurring_of = same_cust_match.ticket_id
                        duplicate_reason = "semantic_same_customer"
                    else:
                        is_duplicate = True
                        matched_complaint_id = same_cust_match.id
                        duplicate_reason = "semantic_same_customer"
                elif diff_cust_match:
                    cluster_id = diff_cust_match.cluster.cluster_id if diff_cust_match.cluster else None
                    is_duplicate = False
                    duplicate_reason = "systemic_similarity"

            if not cluster_id:
                cluster_id = str(uuid.uuid4())

            # Register embedding in Qdrant (if active) or FAISS index (if healthy)
            if vec is not None:
                if self.use_qdrant and self.qdrant_ready:
                    try:
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
                    except Exception as e:
                        logger.warning(f"Error registering vector in Qdrant: {e}")
                else:
                    if self.index is not None and self.healthy:
                        try:
                            self.index.add(vec)
                            self.id_map.append(complaint_id)
                            self.cluster_map[complaint_id] = cluster_id
                            self._save_index()
                        except Exception as e:
                            logger.warning(f"Error registering vector in FAISS: {e}")
                    else:
                        self.cluster_map[complaint_id] = cluster_id

            # Retrieve all registered complaints belonging to this cluster
            cluster_complaints = [c for c in store.all() if c.cluster and c.cluster.cluster_id == cluster_id]
            unique_customers = {c.customer_id for c in cluster_complaints if c.customer_id}
            if customer_id:
                unique_customers.add(customer_id)

            cluster_size = len(cluster_complaints) + 1
            affected_customers = len(unique_customers)
            self.cluster_counts[cluster_id] = cluster_size

            # Alert is only systemic if it affects 5 or more unique customers
            systemic_alert = affected_customers >= CLUSTER_ALERT_THRESHOLD

            if systemic_alert:
                logger.warning(f"SYSTEMIC ALERT: Cluster {cluster_id[:8]} has {cluster_size} similar complaints representing {affected_customers} distinct customers!")
                from collections import Counter
                cats = [c.triage.category.value for c in cluster_complaints if c.triage]
                dominant_cat = Counter(cats).most_common(1)[0][0] if cats else "General Issue"
                issues = [c.triage.key_issue for c in cluster_complaints if c.triage and c.triage.key_issue]
                dominant_issue = Counter(issues).most_common(1)[0][0] if issues else "Multiple related failures"
                label = f"{dominant_cat} outage: {dominant_issue}"
                store.save_incident(cluster_id, label, affected_customers, cluster_size)

            return DuplicateCluster(
                cluster_id=cluster_id,
                is_duplicate=is_duplicate,
                duplicate_of=matched_complaint_id,
                cluster_size=cluster_size,
                affected_customers=affected_customers,
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
