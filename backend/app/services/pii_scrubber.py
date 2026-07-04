"""
PII Scrubbing Service
Upgraded to use Microsoft Presidio + Custom Indian Banking recognizers.
Falls back to Regex if Presidio encounters any issues.
"""

import re
import logging
from typing import Tuple

logger = logging.getLogger(__name__)

# ── Regex patterns (Fallback) ──────────────────────────────────────────────────
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

def _regex_mask_pii(text: str) -> Tuple[str, list]:
    detected = []
    masked = text
    for entity_type, pattern in PATTERNS.items():
        flags = re.IGNORECASE if entity_type == "NAME_SALUTATION" else 0
        matches = re.findall(pattern, masked, flags=flags)
        if matches:
            if entity_type not in detected:
                detected.append(entity_type)
            masked = re.sub(pattern, REPLACEMENT[entity_type], masked, flags=flags)
    return masked, detected

# ── Microsoft Presidio Setup ───────────────────────────────────────────────────
_presidio_ready = False
analyzer = None
anonymizer = None

try:
    from presidio_analyzer import AnalyzerEngine, PatternRecognizer, Pattern
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig

    analyzer = AnalyzerEngine()
    anonymizer = AnonymizerEngine()

    # Define custom banking recognizers
    pan_pattern = Pattern(name="pan_pattern", regex=r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", score=0.95)
    pan_recognizer = PatternRecognizer(supported_entity="PAN", patterns=[pan_pattern])
    analyzer.registry.add_recognizer(pan_recognizer)

    aadhaar_pattern = Pattern(name="aadhaar_pattern", regex=r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b", score=0.95)
    aadhaar_recognizer = PatternRecognizer(supported_entity="AADHAAR", patterns=[aadhaar_pattern])
    analyzer.registry.add_recognizer(aadhaar_recognizer)

    ifsc_pattern = Pattern(name="ifsc_pattern", regex=r"\b[A-Z]{4}0[A-Z0-9]{6}\b", score=0.95)
    ifsc_recognizer = PatternRecognizer(supported_entity="IFSC", patterns=[ifsc_pattern])
    analyzer.registry.add_recognizer(ifsc_recognizer)

    card_pattern = Pattern(name="card_pattern", regex=r"\b(?:\d[ -]?){15,16}\b", score=0.95)
    card_recognizer = PatternRecognizer(supported_entity="CARD_NUMBER", patterns=[card_pattern])
    analyzer.registry.add_recognizer(card_recognizer)

    account_pattern = Pattern(name="account_pattern", regex=r"\b\d{9,18}\b", score=0.90)
    account_recognizer = PatternRecognizer(supported_entity="ACCOUNT_NUMBER", patterns=[account_pattern])
    analyzer.registry.add_recognizer(account_recognizer)

    _presidio_ready = True
    logger.info("Microsoft Presidio PII Scrubber initialized successfully.")
except Exception as e:
    logger.warning(f"Presidio initialization failed: {e}. Falling back to Regex PII masking.")
    _presidio_ready = False

# Mapping from Presidio Entity Names to internal entity tags
ENTITY_MAPPING = {
    "PAN": "PAN",
    "AADHAAR": "AADHAAR",
    "IFSC": "IFSC",
    "CARD_NUMBER": "CARD_NUMBER",
    "ACCOUNT_NUMBER": "ACCOUNT_NUMBER",
    "EMAIL_ADDRESS": "EMAIL",
    "PHONE_NUMBER": "MOBILE",
    "PERSON": "NAME_SALUTATION",
}

OPERATORS = {
    "PAN": OperatorConfig("replace", {"new_value": "[PAN_XXXX]"}),
    "AADHAAR": OperatorConfig("replace", {"new_value": "[AADHAAR_XXXX]"}),
    "IFSC": OperatorConfig("replace", {"new_value": "[IFSC_XXXX]"}),
    "CARD_NUMBER": OperatorConfig("replace", {"new_value": "[CARD_XXXX]"}),
    "ACCOUNT_NUMBER": OperatorConfig("replace", {"new_value": "[ACCOUNT_XXXX]"}),
    "EMAIL_ADDRESS": OperatorConfig("replace", {"new_value": "[EMAIL_XXXX]"}),
    "PHONE_NUMBER": OperatorConfig("replace", {"new_value": "[MOBILE_XXXX]"}),
    "PERSON": OperatorConfig("replace", {"new_value": "[NAME_XXXX]"}),
}

def mask_pii(text: str) -> Tuple[str, list]:
    if not _presidio_ready:
        return _regex_mask_pii(text)

    try:
        results = analyzer.analyze(
            text=text,
            language="en",
            entities=["PAN", "AADHAAR", "IFSC", "CARD_NUMBER", "ACCOUNT_NUMBER", "EMAIL_ADDRESS", "PHONE_NUMBER", "PERSON"]
        )
        anonymized = anonymizer.anonymize(
            text=text,
            analyzer_results=results,
            operators=OPERATORS
        )
        detected = list(set(ENTITY_MAPPING.get(r.entity_type, r.entity_type) for r in results))
        return anonymized.text, detected
    except Exception as e:
        logger.warning(f"Presidio masking failed at runtime: {e}. Running regex fallback.")
        return _regex_mask_pii(text)

def is_safe(text: str) -> bool:
    _, detected = mask_pii(text)
    return len(detected) == 0
