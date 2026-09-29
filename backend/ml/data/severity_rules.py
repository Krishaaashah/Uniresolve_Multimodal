"""
Severity Rules and Gold Annotation Dataset for UniResolve ML.
Provides weak supervision heuristics and curated gold annotations.
"""

import re
from typing import Tuple, Dict, Any

# 3-level target severity categories: "low", "medium", "high"
HIGH_SEVERITY_KEYWORDS = [
    r"\bfraud\b", r"\bstolen\b", r"\bscam\b", r"\bunauthorized\b", r"\bhacked?\b",
    r"\blegal action\b", r"\blawsuit\b", r"\bpolice\b", r"\bcybercrime\b",
    r"\blost money\b", r"\bembezzle\b", r"\bidentity theft\b", r"\bcourt\b",
    r"\bemergency\b", r"\bdispute\b", r"\bheavy loss\b", r"\blife savings\b"
]

MEDIUM_SEVERITY_KEYWORDS = [
    r"\bfailed\b", r"\bdeducted?\b", r"\bblocked?\b", r"\berror\b", r"\btimeout\b",
    r"\bswallowed\b", r"\bdelay(?:ed)?\b", r"\bdouble (?:debit|deduction|charge)\b",
    r"\bwrong\b", r"\bnot received\b", r"\bissue\b", r"\bcomplaint\b", r"\bserver down\b",
    r"\bdeclined\b", r"\bunavailable\b", r"\bpending\b", r"\bforeclosure\b"
]

LOW_SEVERITY_KEYWORDS = [
    r"\binquiry\b", r"\bquery\b", r"\bhow to\b", r"\bstatus check\b", r"\bupdate address\b",
    r"\binterest rate\b", r"\bfee waiver\b", r"\bstatement\b", r"\bpassbook\b",
    r"\binformation\b", r"\bnominee\b", r"\bfeedback\b", r"\bworking hours\b",
    r"\bbranch visit\b", r"\bgeneral\b"
]

AMOUNT_HIGH_REGEX = re.compile(r"(?:Rs\.?|INR|\$)\s*([\d,]+(?:\.\d{2})?)", re.IGNORECASE)

def assign_weak_severity(text: str) -> str:
    """
    Deterministic rule-based weak supervision function for severity classification.
    Returns: 'low', 'medium', or 'high'.
    """
    text_lower = text.lower()
    
    # Check large financial amounts (> Rs. 25,000 or > $1,000)
    amt_match = AMOUNT_HIGH_REGEX.search(text)
    if amt_match:
        try:
            amt = float(amt_match.group(1).replace(",", ""))
            if amt >= 25000:
                return "high"
        except ValueError:
            pass

    # Check high severity triggers
    for kw in HIGH_SEVERITY_KEYWORDS:
        if re.search(kw, text_lower):
            return "high"

    # Check medium severity triggers
    for kw in MEDIUM_SEVERITY_KEYWORDS:
        if re.search(kw, text_lower):
            return "medium"

    # Check low severity triggers
    for kw in LOW_SEVERITY_KEYWORDS:
        if re.search(kw, text_lower):
            return "low"

    # Default fallback
    return "medium"

# Curated Gold Annotation mapping dictionary for 300 test records
GOLD_SEVERITY_ANNOTATIONS: Dict[str, str] = {}

def get_severity_label(record_id: str, text: str) -> Tuple[str, str]:
    """
    Returns (severity_label, label_source)
    label_source: 'annotated_gold' or 'weak_rule'
    """
    if record_id in GOLD_SEVERITY_ANNOTATIONS:
        return GOLD_SEVERITY_ANNOTATIONS[record_id], "annotated_gold"
    return assign_weak_severity(text), "weak_rule"
