"""
Spam Classifier Service
Uses pretrained HuggingFace BERT Transformer model ('mrm8488/bert-tiny-finetuned-sms-spam-detection')
with rule-based fallback for structural keyboard mashing and non-alphanumeric noise.
"""

import re
import logging
from typing import Optional
from collections import Counter

logger = logging.getLogger(__name__)

MODEL_NAME = "mrm8488/bert-tiny-finetuned-sms-spam-detection"


class SpamClassifierService:
    def __init__(self):
        self._pipeline = None
        self._load_attempted = False

    def _get_pipeline(self):
        if not self._load_attempted:
            self._load_attempted = True
            try:
                from transformers import pipeline
                self._pipeline = pipeline("text-classification", model=MODEL_NAME)
                logger.info(f"Loaded pretrained NLP spam classification model: {MODEL_NAME}")
            except Exception as e:
                logger.warning(f"Could not load pretrained NLP spam classifier ({MODEL_NAME}): {e}. Using fallback.")
        return self._pipeline

    def is_spam(self, text: str) -> bool:
        cleaned = text.strip()
        if not cleaned:
            return True
        if len(cleaned) < 15:
            return True

        # Rule check for raw structural keyboard mashing & repeated noise
        if any(len(w) > 25 for w in cleaned.split()):
            return True
        alphas = sum(1 for c in cleaned if c.isalpha())
        if (alphas / len(cleaned)) < 0.35:
            return True
        if re.search(r"([a-zA-Z0-9])\1{4,}", cleaned):
            return True
        words = cleaned.lower().split()
        if len(words) > 8:
            word_counts = Counter(words)
            most_common_word, count = word_counts.most_common(1)[0]
            if count / len(words) > 0.5:
                return True

        # Pretrained NLP Transformer classification pass
        classifier = self._get_pipeline()
        if classifier:
            try:
                res = classifier(cleaned[:512])
                if res and isinstance(res, list) and len(res) > 0:
                    label = res[0].get("label", "")
                    score = res[0].get("score", 0.0)
                    # LABEL_1 is SPAM in mrm8488/bert-tiny-finetuned-sms-spam-detection
                    if label == "LABEL_1" and score >= 0.70:
                        return True
            except Exception as e:
                logger.warning(f"Transformer spam classification inference error: {e}")

        return False


_spam_service: Optional[SpamClassifierService] = None


def get_spam_classifier() -> SpamClassifierService:
    global _spam_service
    if _spam_service is None:
        _spam_service = SpamClassifierService()
    return _spam_service
