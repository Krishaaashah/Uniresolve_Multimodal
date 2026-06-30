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


def _rule_based_triage(
    text: str,
    skip_ai_draft: bool = False,
    transaction_note: Optional[str] = None,
    customer_id: Optional[str] = None,
    transaction_id: Optional[str] = None
) -> TriageResult:
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
    severity_reason = "Classified as medium by default rule-based mapping."
    for sev, keywords in SEVERITY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            severity = sev
            severity_reason = f"Classified as {sev.value} based on keyword match."
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
            text, category, sentiment, severity, fallback_response, "English",
            transaction_note=transaction_note, customer_id=customer_id, transaction_id=transaction_id
        )

    return TriageResult(
        category=category,
        severity=severity,
        sentiment=sentiment,
        key_issue=key_issue,
        key_issues=[key_issue],
        suggested_response=suggested_response,
        confidence=0.75,
        detected_language="English",
        severity_reason=severity_reason
    )


def generate_draft_response(
    complaint_text: str,
    category,
    sentiment,
    severity,
    fallback: str = "",
    detected_language: str = "English",
    transaction_note: Optional[str] = None,
    customer_id: Optional[str] = None,
    transaction_id: Optional[str] = None
) -> str:
    # Run tools locally to get offline context/fallback
    local_details = []
    if transaction_id:
        from app.services.store import get_store
        tx = get_store().get_transaction(transaction_id)
        if tx:
            local_details.append(f"Transaction {transaction_id} Details: Status is {tx.get('status')}, amount is {tx.get('amount')}, date is {tx.get('created_at')}.")
    if customer_id:
        from app.services.store import get_store
        txs = get_store().get_transactions_for_customer(customer_id)
        if txs:
            local_details.append(f"Customer {customer_id} Transactions: {txs}")
    
    if local_details:
        local_context = "\n".join(local_details)
        if not transaction_note:
            transaction_note = local_context
        else:
            transaction_note = f"{transaction_note}\n{local_context}"

    if GEMINI_API_KEY:
        try:
            import httpx
            tools = [{
                "functionDeclarations": [
                    {
                        "name": "check_transaction_status",
                        "description": "Retrieve the current status, amount, and timestamp of a specific transaction by transaction_id.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "transaction_id": {
                                    "type": "STRING",
                                    "description": "The unique transaction identifier, e.g. TXN-HIN1-F1."
                                }
                            },
                            "required": ["transaction_id"]
                        }
                    },
                    {
                        "name": "get_customer_transactions",
                        "description": "Retrieve all transaction records associated with a specific customer_id.",
                        "parameters": {
                            "type": "OBJECT",
                            "properties": {
                                "customer_id": {
                                    "type": "STRING",
                                    "description": "The unique customer identifier, e.g. CUST-10245."
                                }
                            },
                            "required": ["customer_id"]
                        }
                    }
                ]
            }]

            prompt_text = (
                f"Complaint: {complaint_text}\n"
                f"Category: {getattr(category, 'value', category)}\n"
                f"Sentiment: {getattr(sentiment, 'value', sentiment)}\n"
                f"Severity: {getattr(severity, 'value', severity)}\n"
                f"Customer ID: {customer_id or 'unknown'}\n"
                f"Linked Transaction ID: {transaction_id or 'unknown'}\n\n"
                "You are a professional customer service agent. You have access to tools to lookup customer transactions or transaction status. "
                "If a customer customer_id or transaction_id is provided, invoke the appropriate tools to retrieve live context before replying. "
                "After you receive tool responses, incorporate the transaction details (amounts, date, status) in your reply draft. "
                f"Write the final customer response empathetically, concisely, and in the language: {detected_language}. Max 3 sentences."
            )

            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            
            # Send initial message with tools
            contents = [{
                "role": "user",
                "parts": [{"text": prompt_text}]
            }]
            payload = {
                "contents": contents,
                "tools": tools,
                "generationConfig": {"maxOutputTokens": 300}
            }

            res = httpx.post(url, json=payload, headers=headers, timeout=15.0)
            if res.status_code == 200:
                data = res.json()
                candidate = data["candidates"][0]
                content = candidate.get("content", {})
                parts = content.get("parts", [])
                
                # Check for tool call requests
                function_calls = [p["functionCall"] for p in parts if "functionCall" in p]
                if function_calls:
                    # Model requested a tool call!
                    contents.append(content)
                    response_parts = []
                    
                    for call in function_calls:
                        name = call["name"]
                        args = call["args"]
                        result = {}
                        if name == "check_transaction_status":
                            tx_id = args.get("transaction_id")
                            if tx_id:
                                from app.services.store import get_store
                                tx = get_store().get_transaction(tx_id)
                                result = tx or {"error": f"Transaction {tx_id} not found"}
                        elif name == "get_customer_transactions":
                            c_id = args.get("customer_id")
                            if c_id:
                                from app.services.store import get_store
                                result = get_store().get_transactions_for_customer(c_id)
                        
                        response_parts.append({
                            "functionResponse": {
                                "name": name,
                                "response": {"output": result}
                            }
                        })
                    
                    contents.append({
                        "role": "user",
                        "parts": response_parts
                    })
                    
                    payload = {
                        "contents": contents,
                        "tools": tools,
                        "generationConfig": {"maxOutputTokens": 300}
                    }
                    res2 = httpx.post(url, json=payload, headers=headers, timeout=15.0)
                    if res2.status_code == 200:
                        data2 = res2.json()
                        text = data2["candidates"][0]["content"]["parts"][0]["text"].strip()
                        if text:
                            return text
                else:
                    text = parts[0]["text"].strip()
                    if text:
                        return text
            else:
                logger.warning(f"Gemini tool call initiation returned: {res.status_code}")
        except Exception as e:
            logger.warning(f"Gemini tool calling failed: {e}. Falling back.")

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


    def triage(
        self,
        masked_text: str,
        skip_ai_draft: bool = False,
        transaction_note: Optional[str] = None,
        customer_id: Optional[str] = None,
        transaction_id: Optional[str] = None
    ) -> TriageResult:
        # Do NOT run LLM for seed/replay items or if no API keys are set
        if skip_ai_draft or not (GEMINI_API_KEY or ANTHROPIC_API_KEY):
            return _rule_based_triage(
                masked_text, skip_ai_draft=skip_ai_draft,
                transaction_note=transaction_note,
                customer_id=customer_id, transaction_id=transaction_id
            )

        try:
            system_prompt = (
                "You are an AI triage assistant for a bank's complaint system. "
                "Classify the customer complaint text into Category, Severity, and Sentiment.\n"
                "To determine the Severity, enforce these guidelines:\n"
                " - critical: Fraud, theft, data breaches, or loss of large sums (> Rs. 10,000)\n"
                " - high: Login issues, failed transactions where money was debited, blocked cards, or EMI double deduction\n"
                " - medium: ATM swallowing card, KYC delays, app bugs, and general account updates\n"
                " - low: General queries, interest rate requests, branch feedback\n\n"
                "Extract the main key issue as a short sentence (max 100 characters), "
                "and a list of key issues (max 3 issues). "
                "Identify the language of the complaint (e.g. English, Hindi, Marathi, etc.).\n"
                "Provide a brief 'severity_reason' explaining your severity classification choice (max 150 characters).\n"
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
                "  \"detected_language\": \"string\",\n"
                "  \"severity_reason\": \"string\"\n"
                "}"
            )
            fallback_val = {
                "category": "general",
                "severity": "medium",
                "sentiment": "neutral",
                "key_issue": masked_text[:120],
                "key_issues": [masked_text[:120]],
                "confidence": 0.75,
                "detected_language": "English",
                "severity_reason": "Fallback default medium triage classification."
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
            severity_reason = res.get("severity_reason", "Classified via LLM triage engine.")

            import uuid
            fallback_response = RESPONSE_TEMPLATES.get(category, RESPONSE_TEMPLATES[Category.GENERAL]).format(
                ref_id=str(uuid.uuid4())[:8].upper()
            )
            suggested_response = generate_draft_response(
                masked_text, category, sentiment, severity, fallback_response, detected_language,
                transaction_note=transaction_note, customer_id=customer_id, transaction_id=transaction_id
            )

            return TriageResult(
                category=category,
                severity=severity,
                sentiment=sentiment,
                key_issue=key_issue,
                key_issues=key_issues,
                suggested_response=suggested_response,
                confidence=confidence,
                detected_language=detected_language,
                severity_reason=severity_reason
            )
        except Exception as e:
            logger.error(f"LLM triage failed: {e}. Falling back to rules.")
            return _rule_based_triage(
                masked_text, skip_ai_draft=skip_ai_draft,
                transaction_note=transaction_note,
                customer_id=customer_id, transaction_id=transaction_id
            )



# Singleton
_triage_service: Optional[TriageService] = None


def get_triage_service() -> TriageService:
    global _triage_service
    if _triage_service is None:
        _triage_service = TriageService()
    return _triage_service


def generate_summary(text: str) -> str:
    # Rule-based fallback:
    sentences = re.split(r"[.!?]", text.strip())
    fallback = ". ".join(s.strip() for s in sentences[:2] if s.strip()) + "."
    if len(fallback) > 150:
        fallback = fallback[:147] + "..."

    if not (GEMINI_API_KEY or ANTHROPIC_API_KEY):
        return fallback

    if GEMINI_API_KEY:
        try:
            import httpx
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [{"text": (
                        f"Complaint text: {text}\n\n"
                        f"Summarize this complaint in 1 or 2 clear, direct sentences for a dashboard overview. "
                        f"Do not include introductory phrasing, meta-commentary, or greetings. Just return the raw summary."
                    )}]
                }],
                "generationConfig": {
                    "maxOutputTokens": 100
                }
            }
            res = httpx.post(url, json=payload, headers=headers, timeout=10.0)
            if res.status_code == 200:
                data = res.json()
                summary_text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if summary_text:
                    return summary_text
        except Exception as e:
            logger.warning(f"Gemini summary generation failed: {e}")

    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            message = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=100,
                system="Summarize the user complaint in 1-2 direct sentences. Avoid greetings or introductory remarks.",
                messages=[{"role": "user", "content": text}],
            )
            summary_text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text").strip()
            return summary_text or fallback
        except Exception as e:
            logger.warning(f"Claude summary generation failed: {e}")
            return fallback

    return fallback
