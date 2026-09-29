"""
Text Encoder for UniResolve.
Encodes text complaints using SentenceTransformer / FinBERT embeddings (384-dim).
"""

import torch
import torch.nn as nn
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

TEXT_EMBEDDING_DIM = 384

class FinBertTextEncoder(nn.Module):
    def __init__(self, model_name: str = "sentence-transformers/all-MiniLM-L6-v2", freeze_encoder: bool = True):
        super().__init__()
        self.model_name = model_name
        self.freeze_encoder = freeze_encoder
        self.device = torch.device("cpu")
        self.sentence_model = None
        self._init_model()

    def _init_model(self):
        try:
            from sentence_transformers import SentenceTransformer
            self.sentence_model = SentenceTransformer("all-MiniLM-L6-v2")
            logger.info("Text Encoder initialized with all-MiniLM-L6-v2 backbone.")
        except Exception as e:
            logger.warning(f"Could not load SentenceTransformer: {e}")

    def forward(self, texts: List[str]) -> torch.Tensor:
        """
        Encodes a batch of texts into (B, 384) normalized embeddings.
        """
        if self.sentence_model is not None:
            embs = self.sentence_model.encode(
                texts,
                convert_to_tensor=True,
                normalize_embeddings=True,
                device="cpu",
                show_progress_bar=False
            )
            return embs.float()

        B = len(texts)
        return torch.zeros((B, TEXT_EMBEDDING_DIM), dtype=torch.float32)

_text_encoder_instance: Optional[FinBertTextEncoder] = None

def get_text_encoder(freeze: bool = True) -> FinBertTextEncoder:
    global _text_encoder_instance
    if _text_encoder_instance is None:
        _text_encoder_instance = FinBertTextEncoder(freeze_encoder=freeze)
    return _text_encoder_instance
