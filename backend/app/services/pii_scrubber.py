"""
PII Scrubbing Service
Masks: Account numbers, mobile numbers, email addresses,
       customer names (via pattern), Aadhaar, PAN, card numbers.
Hybrid regex + spaCy NER.
"""

import re
import spacy
from typing import Tuple

try:
    nlp = spacy.load("en_core_web_sm")
except Exception:
    nlp = None

# ── Regex patterns ──────────────────────────────────────────────────────────────
# Ordered from most specific/long to more general patterns
PATTERNS = {
    "CARD_NUMBER":    r"\b(?:\d[ -]?){15,16}\b",
    "AADHAAR":        r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b",
    "IFSC":           r"\b[A-Z]{4}0[A-Z0-9]{6}\b",
    "PAN":            r"\b[A-Z]{5}[0-9]{4}[A-Z]\b",
    "EMAIL":          r"\b[\w.+-]+@[\w-]+\.[a-zA-Z]{2,}\b",
    "MOBILE":         r"\b[6-9]\d{9}\b",
    "ACCOUNT_NUMBER": r"\b\d{9,18}\b",
    "NAME_SALUTATION": r"\b(Mr|Mrs|Ms|Dr|Prof)\.?\s+[A-Z][a-z]+(?: [A-Z][a-z]+)*",
}

REPLACEMENT = {
    "CARD_NUMBER":     "[CARD_XXXX]",
    "AADHAAR":         "[AADHAAR_XXXX]",
    "IFSC":            "[IFSC_XXXX]",
    "PAN":             "[PAN_XXXX]",
    "EMAIL":           "[EMAIL_XXXX]",
    "MOBILE":          "[MOBILE_XXXX]",
    "ACCOUNT_NUMBER":  "[ACCOUNT_XXXX]",
    "NAME_SALUTATION": "[NAME_XXXX]",
}


def mask_pii(text: str) -> Tuple[str, list]:
    """
    Returns (masked_text, list_of_detected_entity_types).
    Runs regex patterns first, then spaCy NER for PERSON entities on the result.
    """
    detected: list[str] = []
    masked = text

    # 1. Regex masking
    for entity_type, pattern in PATTERNS.items():
        flags = re.IGNORECASE if entity_type == "NAME_SALUTATION" else 0
        matches = re.findall(pattern, masked, flags=flags)
        if matches:
            if entity_type not in detected:
                detected.append(entity_type)
            masked = re.sub(pattern, REPLACEMENT[entity_type], masked, flags=flags)

    # 2. spaCy NER for bare names (PERSON entities) without salutation
    if nlp:
        try:
            doc = nlp(masked)
            ents = sorted([ent for ent in doc.ents if ent.label_ == "PERSON"], key=lambda e: e.start_char, reverse=True)
            for ent in ents:
                # Avoid touching placeholders that might contain brackets
                if "[" in ent.text or "]" in ent.text:
                    continue
                start, end = ent.start_char, ent.end_char
                masked = masked[:start] + "[NAME_XXXX]" + masked[end:]
                if "NAME_SALUTATION" not in detected:
                    detected.append("NAME_SALUTATION")
        except Exception:
            pass

    return masked, detected


def is_safe(text: str) -> bool:
    """Quick check — True if no PII detected."""
    _, detected = mask_pii(text)
    return len(detected) == 0

