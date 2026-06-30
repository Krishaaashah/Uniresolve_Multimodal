"""
NLP Triage Service
- LLM-based classification (Gemini primary, Anthropic fallback) with a deterministic
  keyword fallback when no API key is configured.
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
from app.services.llm import _claude_json
logger = logging.getLogger(__name__)

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


def _rule_based_triage(text: str, skip_ai_draft: bool = False, transaction_note: Optional[str] = None) -> TriageResult:
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
        suggested_response = generate_draft_response(
            text, category, sentiment, severity, fallback_response, "English", transaction_note=transaction_note
        )

    return TriageResult(
        category=category,
        severity=severity,
        sentiment=sentiment,
        key_issue=key_issue,
        key_issues=[key_issue],
        suggested_response=suggested_response,
        confidence=0.75,
        detected_language="English"
    )


def generate_draft_response(
    complaint_text: str,
    category,
    sentiment,
    severity,
    fallback: str = "",
    detected_language: str = "English",
    transaction_note: Optional[str] = None
) -> str:
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
                        f"Severity: {getattr(severity, 'value', severity)}\n"
                        + (f"Transaction Status Context: {transaction_note}\n" if transaction_note else "") +
                        f"\nWrite a professional customer service response for a financial institution. "
                        + (f"Incorporate the transaction status context in the response if applicable. " if transaction_note else "") +
                        f"The customer's language is {detected_language}. Write the response in {detected_language}. "
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
                    f"Write empathetic, concise complaint responses in the language: {detected_language}. "
                    "Do not make up policy details. Maximum 3 sentences."
                ),
                messages=[
                    {
                        "role": "user",
                        "content": (
                            f"Complaint: {complaint_text}\n"
                            f"Category: {getattr(category, 'value', category)}\n"
                            f"Sentiment: {getattr(sentiment, 'value', sentiment)}\n"
                            f"Severity: {getattr(severity, 'value', severity)}\n"
                            + (f"Transaction Status Context: {transaction_note}\n" if transaction_note else "")
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
    LLM-primary triage service with rule-based fallback.
    """

    def __init__(self):
        self._model_ready = True


    def triage(self, masked_text: str, skip_ai_draft: bool = False, transaction_note: Optional[str] = None) -> TriageResult:
        # Do NOT run LLM for seed/replay items or if no API keys are set
        if skip_ai_draft or not (GEMINI_API_KEY or ANTHROPIC_API_KEY):
            return _rule_based_triage(masked_text, skip_ai_draft=skip_ai_draft, transaction_note=transaction_note)

        try:
            system_prompt = (
                "You are an AI triage assistant for a bank's complaint system. "
                "Classify the customer complaint text into Category, Severity, and Sentiment. "
                "Extract the main key issue as a short sentence (max 100 characters), "
                "and a list of key issues (max 3 issues). "
                "Identify the language of the complaint (e.g. English, Hindi, Marathi, etc.). "
                "Respond with a strict JSON object containing these exact keys.\n\n"
                f"Allowed Categories: {[c.value for c in Category]}\n"
                f"Allowed Severities: {[s.value for s in Severity]}\n"
                f"Allowed Sentiments: {[s.value for s in Sentiment]}\n\n"
                "Expected JSON format:\n"
                "{\n"
                "  \"category\": \"string\",\n"
                "  \"severity\": \"string\",\n"
                "  \"sentiment\": \"string\",\n"
                "  \"key_issue\": \"string\",\n"
                "  \"key_issues\": [\"string\"],\n"
                "  \"confidence\": 0.95,\n"
                "  \"detected_language\": \"string\"\n"
                "}"
            )
            fallback_val = {
                "category": "general",
                "severity": "medium",
                "sentiment": "neutral",
                "key_issue": masked_text[:120],
                "key_issues": [masked_text[:120]],
                "confidence": 0.75,
                "detected_language": "English"
            }
            res = _claude_json(system_prompt, masked_text, fallback_val)

            # Validate and coerce
            category_str = res.get("category", "general").lower()
            category = Category.GENERAL
            for c in Category:
                if c.value == category_str or c.value in category_str:
                    category = c
                    break

            severity_str = res.get("severity", "medium").lower()
            severity = Severity.MEDIUM
            for s in Severity:
                if s.value == severity_str or s.value in severity_str:
                    severity = s
                    break

            sentiment_str = res.get("sentiment", "neutral").lower()
            sentiment = Sentiment.NEUTRAL
            for s in Sentiment:
                if s.value == sentiment_str or s.value in sentiment_str:
                    sentiment = s
                    break

            key_issue = res.get("key_issue", masked_text[:120])
            key_issues = res.get("key_issues", [key_issue])
            confidence = float(res.get("confidence", 0.88))
            detected_language = res.get("detected_language", "English")

            import uuid
            fallback_response = RESPONSE_TEMPLATES.get(category, RESPONSE_TEMPLATES[Category.GENERAL]).format(
                ref_id=str(uuid.uuid4())[:8].upper()
            )
            suggested_response = generate_draft_response(
                masked_text, category, sentiment, severity, fallback_response, detected_language, transaction_note=transaction_note
            )

            return TriageResult(
                category=category,
                severity=severity,
                sentiment=sentiment,
                key_issue=key_issue,
                key_issues=key_issues,
                suggested_response=suggested_response,
                confidence=confidence,
                detected_language=detected_language
            )
        except Exception as e:
            logger.error(f"LLM triage failed: {e}. Falling back to rules.")
            return _rule_based_triage(masked_text, skip_ai_draft=skip_ai_draft, transaction_note=transaction_note)



# Singleton
_triage_service: Optional[TriageService] = None


def get_triage_service() -> TriageService:
    global _triage_service
    if _triage_service is None:
        _triage_service = TriageService()
    return _triage_service
