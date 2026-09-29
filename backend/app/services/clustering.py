"""
Semantic Duplicate Detection & Clustering Service
- Encodes complaints with Sentence-BERT (all-MiniLM-L6-v2) or resilient embedding fallback
- Stores embeddings in Qdrant (if active), FAISS Index (if local), or In-Memory Matrix
- Detects duplicates via cosine similarity threshold
- Raises systemic alert when unique customer count >= CLUSTER_ALERT_THRESHOLD
"""

import os
import uuid
import logging
import json
import re
import numpy as np
from pathlib import Path
from typing import Optional, List, Dict, Any
import threading
from app.models.complaint import DuplicateCluster

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
INDEX_PATH = BASE_DIR / "faiss_index.bin"
MAP_PATH = BASE_DIR / "cluster_map.json"
from app.config import SIMILARITY_THRESHOLD, CLUSTER_ALERT_THRESHOLD
EMBEDDING_DIM = 384              # all-MiniLM-L6-v2 output size


def _fallback_embed(text: str) -> np.ndarray:
    """Deterministic 384-dimensional normalized bag-of-words / char n-gram embedding fallback."""
    v = np.zeros(EMBEDDING_DIM, dtype=np.float32)
    clean_text = re.sub(r"[^\w\s]", "", text.lower())
    words = clean_text.split()
    if not words:
        v[0] = 1.0
        return v.reshape(1, -1)

    for word in words:
        h = hash(word) % EMBEDDING_DIM
        v[h] += 1.0
        for i in range(len(word) - 2):
            gram = word[i:i+3]
            h_gram = hash(gram) % EMBEDDING_DIM
            v[h_gram] += 0.5

    norm = np.linalg.norm(v)
    if norm > 1e-6:
        v = v / norm
    else:
        v[0] = 1.0
    return v.reshape(1, -1)


class ClusteringService:
    def __init__(self):
        self.lock = threading.Lock()
        self.encoder = None
        self.index = None
        self.id_map: list[str] = []           # position -> complaint_id
        self.cluster_map: dict[str, str] = {} # complaint_id -> cluster_id
        self.cluster_counts: dict[str, int] = {}
        self.numpy_embeddings: Optional[np.ndarray] = None
        self.healthy = True

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
        except Exception as e:
            logger.warning(f"Could not load SentenceTransformer ({e}). Using deterministic fallback embedding.")
            self.encoder = None

        if self.use_qdrant and self.qdrant_ready:
            logger.info("Semantic Search will be executed using Qdrant.")
            return

        try:
            import faiss
            self.index = faiss.IndexFlatIP(EMBEDDING_DIM)
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
            logger.warning(f"Could not load FAISS: {e}. Using in-memory cosine similarity matrix.")
            self.index = None
            self.numpy_embeddings = np.zeros((0, EMBEDDING_DIM), dtype=np.float32)

    def _save_index(self):
        if self.use_qdrant and self.qdrant_ready:
            return
        try:
            if self.index is not None:
                import faiss
                faiss.write_index(self.index, str(INDEX_PATH))
            MAP_PATH.write_text(json.dumps({
                "cluster_map": self.cluster_map,
                "cluster_counts": self.cluster_counts,
                "id_map": self.id_map
            }))
        except Exception as e:
            logger.warning(f"Could not save index: {e}")

    def _encode(self, text: str) -> np.ndarray:
        if self.encoder is not None:
            try:
                vec = self.encoder.encode([text], normalize_embeddings=True)
                return vec.astype("float32")
            except Exception:
                pass
        return _fallback_embed(text)

    def check_and_register(self, complaint_id: str, text: str, customer_id: Optional[str] = None, transaction_id: Optional[str] = None) -> DuplicateCluster:
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

            # 1. Exact transaction ID match check
            exact_match_ticket = None
            if customer_id and transaction_id:
                try:
                    all_complaints = store.all()
                    for c in all_complaints:
                        if c.customer_id == customer_id and c.transaction_id == transaction_id and c.id != complaint_id:
                            exact_match_ticket = c
                            break
                    
                    if exact_match_ticket:
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
                        logger.warning(f"Qdrant search error: {e}")
                elif self.index is not None and self.index.ntotal > 0:
                    try:
                        scores, indices = self.index.search(vec, min(10, self.index.ntotal))
                        for score, idx in zip(scores[0], indices[0]):
                            if idx >= 0 and idx < len(self.id_map) and score >= SIMILARITY_THRESHOLD:
                                candidates.append({
                                    "id": self.id_map[idx],
                                    "score": float(score)
                                })
                    except Exception as e:
                        logger.warning(f"FAISS search error: {e}")
                elif self.numpy_embeddings is not None and len(self.numpy_embeddings) > 0:
                    sims = np.dot(self.numpy_embeddings, vec.T).flatten()
                    for idx, sim in enumerate(sims):
                        if sim >= SIMILARITY_THRESHOLD and idx < len(self.id_map):
                            candidates.append({
                                "id": self.id_map[idx],
                                "score": float(sim)
                            })

            # Check exact match first
            if exact_match_ticket:
                is_duplicate = True
                matched_complaint_id = exact_match_ticket.id
                cluster_id = self.cluster_map.get(exact_match_ticket.id, exact_match_ticket.id)
                duplicate_reason = "exact_id"

            # Check same customer semantic matches first
            if not is_duplicate and candidates and customer_id:
                for cand in candidates:
                    cand_id = cand["id"]
                    if cand_id == complaint_id:
                        continue
                    cand_complaint = store.get(cand_id)
                    if not cand_complaint:
                        continue
                    if cand_complaint.customer_id == customer_id:
                        is_resolved = getattr(cand_complaint, "status", "") == "resolved"
                        days_diff = (datetime.utcnow() - getattr(cand_complaint, "created_at", datetime.utcnow())).days
                        if is_resolved and days_diff <= 30:
                            recurring = True
                            recurring_of = cand_complaint.ticket_id
                            cluster_id = self.cluster_map.get(cand_id, cand_id)
                            break
                        elif not is_resolved and days_diff <= 7:
                            is_duplicate = True
                            matched_complaint_id = cand_id
                            cluster_id = self.cluster_map.get(cand_id, cand_id)
                            duplicate_reason = "semantic_same_customer"
                            break

            # If not a same-customer duplicate/recurring, check systemic cluster across different customers
            if not is_duplicate and not recurring and not cluster_id and candidates:
                for cand in candidates:
                    cand_id = cand["id"]
                    if cand_id == complaint_id:
                        continue
                    cluster_id = self.cluster_map.get(cand_id, str(uuid.uuid4()))
                    duplicate_reason = "systemic_similarity"
                    break

            # If still no cluster assigned, generate fresh cluster_id
            if not cluster_id:
                cluster_id = str(uuid.uuid4())

            # Register embedding into index
            if vec is not None:
                if self.use_qdrant and self.qdrant_ready:
                    from app.services import qdrant_service
                    qdrant_service.upsert_embedding(complaint_id, vec.tolist()[0], payload={"cluster_id": cluster_id})
                elif self.index is not None:
                    self.index.add(vec)
                elif self.numpy_embeddings is not None:
                    self.numpy_embeddings = np.vstack([self.numpy_embeddings, vec]) if len(self.numpy_embeddings) > 0 else vec

                self.id_map.append(complaint_id)
                self.cluster_map[complaint_id] = cluster_id
                self.cluster_counts[cluster_id] = self.cluster_counts.get(cluster_id, 0) + 1
                self._save_index()

            # Compute affected customers & systemic alert
            all_in_cluster = [c for c in store.all() if self.cluster_map.get(c.id) == cluster_id or (c.cluster and c.cluster.cluster_id == cluster_id)]
            unique_customers = set(c.customer_id for c in all_in_cluster if c.customer_id)
            if customer_id:
                unique_customers.add(customer_id)

            affected_count = max(len(unique_customers), 1)
            cluster_size = self.cluster_counts.get(cluster_id, 1)
            systemic_alert = (affected_count >= CLUSTER_ALERT_THRESHOLD)

            return DuplicateCluster(
                cluster_id=cluster_id,
                is_duplicate=is_duplicate,
                duplicate_of=matched_complaint_id,
                cluster_size=cluster_size,
                affected_customers=affected_count,
                systemic_alert=systemic_alert,
                duplicate_reason=duplicate_reason,
                recurring=recurring,
                recurring_of=recurring_of
            )

    def clear(self):
        with self.lock:
            if self.index is not None:
                try:
                    import faiss
                    self.index = faiss.IndexFlatIP(EMBEDDING_DIM)
                except Exception:
                    pass
            self.numpy_embeddings = np.zeros((0, EMBEDDING_DIM), dtype=np.float32)
            self.id_map = []
            self.cluster_map = {}
            self.cluster_counts = {}
            if INDEX_PATH.exists():
                try:
                    INDEX_PATH.unlink()
                except Exception:
                    pass
            if MAP_PATH.exists():
                try:
                    MAP_PATH.unlink()
                except Exception:
                    pass


_clustering_service = None

def get_clustering_service() -> ClusteringService:
    global _clustering_service
    if _clustering_service is None:
        _clustering_service = ClusteringService()
    return _clustering_service
