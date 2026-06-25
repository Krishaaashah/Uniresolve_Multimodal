"""
NLP Triage Service
- Uses FLAN-T5-Base for category, severity, sentiment, key issue extraction
- Falls back to rule-based classification when model is unavailable
- Returns TriageResult with a suggested response draft
"""

import re
import json
import logging
import os
import threading
from typing import Optional

from app.models.complaint import (
    TriageResult, Category, Severity, Sentiment
)
from app.config import (
    GEMINI_API_KEY, ANTHROPIC_API_KEY, GEMINI_MODEL, CLAUDE_MODEL
)

logger = logging.getLogger(__name__)

# ── Keyword maps for rule-based fallback ───────────────────────────────────────
CATEGORY_KEYWORDS = {
    Category.MOBILE_BANKING: ["mobile banking", "app transfer", "mobile app", "beneficiary add", "fingerprint login"],
    Category.UPI: ["upi", "gpay", "phonepe", "paytm", "bhim", "upi pin", "transaction fail"],
    Category.ACCOUNT: ["account", "nominee", "joint account", "balance update"],
    Category.NETBANKING: ["net banking", "netbanking", "login", "password", "otp", "internet banking", "online banking"],
    Category.ATM: ["atm", "cash withdrawal", "atm card", "swallowed", "dispense"],
    Category.CREDIT_CARD: ["card", "debit card", "credit card", "swipe", "blocked card"],
    Category.LOAN: ["loan", "emi", "interest", "repayment", "mortgage"],
    Category.INSURANCE: ["insurance", "claim", "premium", "policy"],
    Category.INVESTMENT: ["investment", "mutual fund", "portfolio", "demat", "shares"],
    Category.FRAUD: ["fraud", "scam", "unauthorized", "stolen", "phishing", "hack", "cheat"],
}

SEVERITY_KEYWORDS = {
    Severity.CRITICAL: ["fraud", "stolen", "unauthorized", "scam", "hacked", "money gone", "lost money"],
    Severity.HIGH:     ["urgent", "immediately", "cannot access", "not working", "failed", "blocked", "emergency"],
    Severity.MEDIUM:   ["issue", "problem", "error", "complaint", "not able"],
    Severity.LOW:      ["inquiry", "request", "information", "update", "query"],
}

SENTIMENT_KEYWORDS = {
    Sentiment.ANGRY:      ["furious", "outraged", "disgusting", "terrible", "pathetic", "useless", "worst"],
    Sentiment.FRUSTRATED: ["frustrated", "annoyed", "fed up", "unhappy", "disappointed", "again", "still not"],
    Sentiment.SATISFIED:  ["happy", "thank", "resolved", "great", "good", "appreciate"],
}

RESPONSE_TEMPLATES = {
    Category.MOBILE_BANKING: "Dear Customer, we acknowledge your concern regarding your digital banking transaction. Our team is investigating the issue on priority. You will receive an update within 24 hours. Reference ID: {ref_id}",
    Category.ACCOUNT: "Dear Customer, your account service query has been registered. Our team will review the details and update you at the earliest.",
    Category.LOAN: "Dear Customer, we have received your query regarding your loan/EMI. Our loans team will review your account and contact you within 2 business days.",
    Category.CREDIT_CARD: "Dear Customer, we are sorry to hear about your card issue. If your card is compromised, please call our helpline immediately to block it while our team reviews your complaint.",
    Category.INSURANCE: "Dear Customer, we have registered your insurance complaint and will route it to the concerned team for review.",
    Category.INVESTMENT: "Dear Customer, we have received your investment-related concern and will have the specialist team review it.",
    Category.FRAUD:      "URGENT: Dear Customer, we take fraud reports extremely seriously. Your account has been flagged for immediate review. Please call our fraud helpline 1800-XXX-XXXX (24x7) immediately. Do NOT share any OTP or credentials.",
    Category.GENERAL:    "Dear Customer, thank you for reaching out to UniResolve. Your complaint has been registered and will be addressed by our support team within 48 hours.",
    Category.UPI:        "Dear Customer, we have registered your complaint regarding the UPI transaction failure. As per RBI guidelines, we are processing the status check and reversal. Reference ID: {ref_id}.",
    Category.NETBANKING: "Dear Customer, we are looking into the net banking login/service issue. Our support team will review and resolve it at the earliest.",
    Category.ATM:        "Dear Customer, we acknowledge your ATM-related grievance. If cash was not dispensed but debited, a reversal will be processed as per RBI timelines. Reference ID: {ref_id}.",
    Category.KYC:        "Dear Customer, your KYC update request is being reviewed by our compliance team. Reference ID: {ref_id}."
}


def _rule_based_triage(text: str, skip_ai_draft: bool = False) -> TriageResult:
    """Deterministic fallback when the ML model is not loaded."""
    lower = text.lower()

    # Category
    category = Category.GENERAL
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            category = cat
            break

    # Severity
    severity = Severity.MEDIUM
    for sev, keywords in SEVERITY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            severity = sev
            break

    # Sentiment
    sentiment = Sentiment.NEUTRAL
    for sent, keywords in SENTIMENT_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            sentiment = sent
            break

    # Key issue: first sentence, trimmed
    sentences = re.split(r"[.!?]", text.strip())
    key_issue = sentences[0].strip()[:120] if sentences else text[:120]

    import uuid
    fallback_response = RESPONSE_TEMPLATES.get(category, RESPONSE_TEMPLATES[Category.GENERAL]).format(
        ref_id=str(uuid.uuid4())[:8].upper()
    )
    if skip_ai_draft:
        suggested_response = fallback_response
    else:
        suggested_response = generate_draft_response(text, category, sentiment, severity, fallback_response)

    return TriageResult(
        category=category,
        severity=severity,
        sentiment=sentiment,
        key_issue=key_issue,
        key_issues=[key_issue],
        suggested_response=suggested_response,
        confidence=0.75,
    )


def generate_draft_response(complaint_text: str, category, sentiment, severity, fallback: str = "") -> str:
    if GEMINI_API_KEY:
        try:
            import httpx
            # Call Gemini API
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [{"text": (
                        f"Complaint: {complaint_text}\n"
                        f"Category: {getattr(category, 'value', category)}\n"
                        f"Sentiment: {getattr(sentiment, 'value', sentiment)}\n"
                        f"Severity: {getattr(severity, 'value', severity)}\n\n"
                        f"Write a professional customer service response for a financial institution. "
                        f"Write empathetically and concisely. Do not make up policy details. Max 3 sentences."
                    )}]
                }],
                "generationConfig": {
                    "maxOutputTokens": 180
                }
            }
            res = httpx.post(url, json=payload, headers=headers, timeout=10.0)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text:
                    return text
            else:
                logger.warning(f"Gemini API returned status {res.status_code}: {res.text}")
        except Exception as e:
            logger.warning(f"Gemini draft generation failed: {e}. Falling back.")

    if ANTHROPIC_API_KEY:
        try:
            import anthropic

            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=180,
                system=(
                    "You are a professional customer service agent for a financial institution. "
                    "Write empathetic, concise complaint responses. Do not make up policy details. Maximum 3 sentences."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Complaint: {complaint_text}\n"
                            f"Category: {getattr(category, 'value', category)}\n"
                            f"Sentiment: {getattr(sentiment, 'value', sentiment)}\n"
                            f"Severity: {getattr(severity, 'value', severity)}"
                        ),
                    }
                ],
            )
            text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text").strip()
            return text or fallback
        except Exception as e:
            logger.warning(f"Claude draft generation failed: {e}. Using fallback.")
            return fallback

    return fallback or RESPONSE_TEMPLATES.get(category, RESPONSE_TEMPLATES[Category.GENERAL]).format(ref_id="DEMO")


class TriageService:
    """
    Wraps FLAN-T5 for inference.
    Falls back to rule-based on import error or model unavailability.
    """

    def __init__(self):
        self.model = None
        self.tokenizer = None
        self._model_ready = False
        threading.Thread(target=self._load_model, daemon=True).start()

    def _load_model(self):
        try:
            from transformers import T5ForConditionalGeneration, T5Tokenizer
            logger.info("Loading FLAN-T5-Base — this may take a minute...")
            model_name = "google/flan-t5-base"
            self.tokenizer = T5Tokenizer.from_pretrained(model_name)
            self.model = T5ForConditionalGeneration.from_pretrained(model_name)
            self._model_ready = True
            logger.info("FLAN-T5-Base loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load FLAN-T5 model: {e}. Using rule-based fallback.")

    def _prompt_classify(self, text: str, field: str, options: list[str]) -> str:
        """Ask the model to classify a single field."""
        prompt = (
            f"Classify the following banking customer complaint.\n"
            f"Field: {field}\n"
            f"Options: {', '.join(options)}\n"
            f"Complaint: {text}\n"
            f"Answer with only one option from the list."
        )
        inputs = self.tokenizer(prompt, return_tensors="pt", max_length=512, truncation=True)
        outputs = self.model.generate(**inputs, max_new_tokens=20)
        return self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip().lower()

    def _extract_key_issue(self, text: str) -> str:
        prompt = (
            f"Summarize the core issue in this banking complaint in one short sentence:\n{text}"
        )
        inputs = self.tokenizer(prompt, return_tensors="pt", max_length=512, truncation=True)
        outputs = self.model.generate(**inputs, max_new_tokens=50)
        return self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip()

    def triage(self, masked_text: str, skip_ai_draft: bool = False) -> TriageResult:
        if not self._model_ready or self.model is None:
            return _rule_based_triage(masked_text, skip_ai_draft=skip_ai_draft)

        try:
            # Category
            cat_str = self._prompt_classify(
                masked_text, "category",
                [c.value for c in Category]
            )
            category = next(
                (c for c in Category if c.value.lower() in cat_str),
                Category.GENERAL
            )

            # Severity
            sev_str = self._prompt_classify(
                masked_text, "severity",
                [s.value for s in Severity]
            )
            severity = next(
                (s for s in Severity if s.value in sev_str),
                Severity.MEDIUM
            )

            # Sentiment
            sent_str = self._prompt_classify(
                masked_text, "sentiment",
                [s.value for s in Sentiment]
            )
            sentiment = next(
                (s for s in Sentiment if s.value in sent_str),
                Sentiment.NEUTRAL
            )

            key_issue = self._extract_key_issue(masked_text)

            import uuid
            fallback_response = RESPONSE_TEMPLATES.get(category, RESPONSE_TEMPLATES[Category.GENERAL]).format(
                ref_id=str(uuid.uuid4())[:8].upper()
            )
            if skip_ai_draft:
                suggested_response = fallback_response
            else:
                suggested_response = generate_draft_response(masked_text, category, sentiment, severity, fallback_response)

            return TriageResult(
                category=category,
                severity=severity,
                sentiment=sentiment,
                key_issue=key_issue,
                key_issues=[key_issue],
                suggested_response=suggested_response,
                confidence=0.88,
            )

        except Exception as e:
            logger.error(f"Model inference failed: {e}. Falling back to rules.")
            return _rule_based_triage(masked_text, skip_ai_draft=skip_ai_draft)


# Singleton
_triage_service: Optional[TriageService] = None


def get_triage_service() -> TriageService:
    global _triage_service
    if _triage_service is None:
        _triage_service = TriageService()
    return _triage_service
