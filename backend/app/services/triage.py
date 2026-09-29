"""
NLP & Multimodal Triage Service for UniResolve.
- Local Multimodal Fusion mode: WavLM + FinBERT + Gated Cross-Attention (TRIAGE_MODE=local)
- LLM API fallback mode: Gemini/Claude API (TRIAGE_MODE=api)
- Deterministic rule fallback when offline or during exceptions
"""

import os
import re
import json
import uuid
import logging
import threading
from pathlib import Path
from typing import Optional, Dict, Any, List

import torch
import torch.nn.functional as F

from app.models.complaint import (
    TriageResult, Category, Severity, Sentiment
)
from app.config import (
    GEMINI_API_KEY, ANTHROPIC_API_KEY, GEMINI_MODEL, CLAUDE_MODEL, TRIAGE_MODE
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
    Category.LOAN: ["loan", "emi", "interest", "repayment", "mortgage", "foreclosure"],
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
    Category.ACCOUNT: "Dear Customer, your account service query has been registered. Our team will review the details and update you at the earliest. Reference ID: {ref_id}",
    Category.LOAN: "Dear Customer, we have received your query regarding your loan/EMI. Our loans team will review your account and contact you within 2 business days. Reference ID: {ref_id}",
    Category.CREDIT_CARD: "Dear Customer, we are sorry to hear about your card issue. If your card is compromised, please call our helpline immediately to block it while our team reviews your complaint. Reference ID: {ref_id}",
    Category.INSURANCE: "Dear Customer, we have registered your insurance complaint and will route it to the concerned team for review. Reference ID: {ref_id}",
    Category.INVESTMENT: "Dear Customer, we have received your investment-related concern and will have the specialist team review it. Reference ID: {ref_id}",
    Category.FRAUD:      "URGENT: Dear Customer, we take fraud reports extremely seriously. Your account has been flagged for immediate review. Please call our fraud helpline 1800-XXX-XXXX (24x7) immediately. Do NOT share any OTP or credentials. Reference ID: {ref_id}",
    Category.GENERAL:    "Dear Customer, thank you for reaching out to UniResolve. Your complaint has been registered and will be addressed by our support team within 48 hours. Reference ID: {ref_id}",
    Category.UPI:        "Dear Customer, we have registered your complaint regarding the UPI transaction failure. As per RBI guidelines, we are processing the status check and reversal. Reference ID: {ref_id}",
    Category.NETBANKING: "Dear Customer, we are looking into the net banking login/service issue. Our support team will review and resolve it at the earliest. Reference ID: {ref_id}",
    Category.ATM:        "Dear Customer, we acknowledge your ATM-related grievance. If cash was not dispensed but debited, a reversal will be processed as per RBI timelines. Reference ID: {ref_id}",
    Category.KYC:        "Dear Customer, your KYC update request is being reviewed by our compliance team. Reference ID: {ref_id}"
}

TARGET_CATEGORIES = [
    "Loans",
    "Accounts",
    "Credit Cards",
    "UPI/Payments",
    "Transaction Errors",
    "KYC/Verification"
]

CATEGORY_TO_ENUM = {
    "Loans": Category.LOAN,
    "Accounts": Category.ACCOUNT,
    "Credit Cards": Category.CREDIT_CARD,
    "UPI/Payments": Category.UPI,
    "Transaction Errors": Category.ATM,
    "KYC/Verification": Category.KYC,
}


def normalize_category(cat_str: str) -> str:
    if not cat_str:
        return "General"
    cat_str = cat_str.strip()
    lower = cat_str.lower()
    
    if any(x in lower for x in ["upi failure", "upi transaction failed", "upi transaction failure", "upi fail", "upi transfer failed"]):
        return "UPI Failure"
    if lower == "upi":
        return "UPI Failure"
    if any(x in lower for x in ["card block", "debit card blocked", "card blocked", "card block request", "block card"]):
        return "Card Blocking"
    if any(x in lower for x in ["home loan foreclosure", "loan foreclosure", "foreclosure letter", "foreclosure fee"]):
        return "Loan Foreclosure"
    if any(x in lower for x in ["double debit", "charged twice", "double deduction", "emi debited twice"]):
        return "Double Deduction"
    if any(x in lower for x in ["kyc update", "kyc pending", "kyc verification", "kyc pending for"]):
        return "KYC Verification"

    words = re.split(r'[\s_]+', cat_str)
    cleaned_words = []
    for w in words:
        if not w:
            continue
        wl = w.lower()
        if wl in ["upi", "kyc", "atm", "emi", "ivr", "sip"]:
            cleaned_words.append(w.upper())
        else:
            cleaned_words.append(w.capitalize())
            
    return " ".join(cleaned_words)


class LocalMultimodalTriageEngine:
    """
    Local Multimodal inference engine powered by WavLM + FinBERT + GatedCrossAttentionFusion.
    Runs strictly on CPU with frozen feature extraction backbones.
    """
    def __init__(self):
        self.lock = threading.Lock()
        self.fusion_model = None
        self.text_encoder = None
        self.audio_encoder = None
        self.device = torch.device("cpu")
        self._load_models()

    def _load_models(self):
        try:
            import sys
            from pathlib import Path
            backend_root = Path(__file__).resolve().parents[2]
            if str(backend_root) not in sys.path:
                sys.path.insert(0, str(backend_root))

            from ml.text_encoder import get_text_encoder
            from ml.audio_encoder import get_audio_encoder
            from ml.fusion import GatedCrossAttentionFusion

            self.text_encoder = get_text_encoder(freeze=True)
            self.audio_encoder = get_audio_encoder(freeze=True)
            self.fusion_model = GatedCrossAttentionFusion()

            ckpt_path = backend_root / "ml" / "checkpoints" / "gated_fusion_seed42.pt"
            if ckpt_path.exists():
                try:
                    state_dict = torch.load(str(ckpt_path), map_location=self.device)
                    self.fusion_model.load_state_dict(state_dict)
                    logger.info("Loaded trained GatedCrossAttentionFusion weights from checkpoint.")
                except Exception as e:
                    logger.warning(f"Failed to load checkpoint state dict: {e}. Using initialized model.")
            else:
                logger.info("No checkpoint file found at gated_fusion_seed42.pt; using initialized fusion model.")

            self.fusion_model.eval()
        except Exception as e:
            logger.warning(f"Could not load local ML pipeline: {e}. Local engine fallback enabled.")

    def triage(
        self,
        masked_text: str,
        audio_path: Optional[str] = None,
        skip_ai_draft: bool = False,
        transaction_note: Optional[str] = None,
        customer_id: Optional[str] = None,
        transaction_id: Optional[str] = None
    ) -> TriageResult:
        with self.lock:
            if self.fusion_model is None or self.text_encoder is None:
                return _rule_based_triage(
                    masked_text, skip_ai_draft=skip_ai_draft,
                    transaction_note=transaction_note,
                    customer_id=customer_id, transaction_id=transaction_id
                )

            try:
                # 1. Text embedding
                text_emb = self.text_encoder([masked_text])

                # 2. Audio embedding
                if audio_path and os.path.exists(audio_path):
                    audio_emb = self.audio_encoder.forward_audio_files([audio_path], batch_size=1)
                    audio_mask = torch.tensor([1.0], dtype=torch.float32)
                else:
                    audio_emb = torch.zeros((1, 773), dtype=torch.float32)
                    audio_mask = torch.tensor([0.0], dtype=torch.float32)

                # 3. Gated Fusion Forward Pass
                with torch.no_grad():
                    outputs = self.fusion_model(text_emb, audio_emb, audio_mask=audio_mask)

                cat_logits = outputs["category_logits"]
                sev_logits = outputs["severity_logits"]
                modality_weights = outputs.get("modality_weights", {"text": 1.0, "audio": 0.0})

                cat_idx = int(torch.argmax(cat_logits, dim=-1)[0].item())
                cat_idx = min(max(cat_idx, 0), len(TARGET_CATEGORIES) - 1)
                predicted_category = TARGET_CATEGORIES[cat_idx]

                sev_probs = F.softmax(sev_logits, dim=-1)[0]
                prob_low = float(sev_probs[0].item())
                prob_med = float(sev_probs[1].item())
                prob_high = float(sev_probs[2].item())

                urgency_score = round(0.15 * prob_low + 0.55 * prob_med + 0.95 * prob_high, 2)

                lower_text = masked_text.lower()
                is_critical = any(kw in lower_text for kw in SEVERITY_KEYWORDS[Severity.CRITICAL])
                
                if is_critical or urgency_score >= 0.88:
                    severity = Severity.CRITICAL
                    severity_reason = "Classified as CRITICAL due to urgent security/fraud indicators."
                elif prob_high >= prob_med and prob_high >= prob_low:
                    severity = Severity.HIGH
                    severity_reason = "Classified as HIGH severity due to elevated multimodal grievance signals."
                elif prob_med >= prob_low:
                    severity = Severity.MEDIUM
                    severity_reason = "Classified as MEDIUM severity standard operational issue."
                else:
                    severity = Severity.LOW
                    severity_reason = "Classified as LOW severity routine query."

                sentiment = Sentiment.NEUTRAL
                for s, keywords in SENTIMENT_KEYWORDS.items():
                    if any(kw in lower_text for kw in keywords):
                        sentiment = s
                        break
                if sentiment == Sentiment.NEUTRAL and urgency_score >= 0.70:
                    sentiment = Sentiment.FRUSTRATED

                first_sentence = masked_text.split(".")[0].strip()
                key_issue = f"{predicted_category}: {first_sentence[:100]}"
                key_issues = [f"{predicted_category} grievance", first_sentence[:90]]

                base_cat_enum = CATEGORY_TO_ENUM.get(predicted_category, Category.GENERAL)
                ref_id = str(uuid.uuid4())[:8].upper()
                template = RESPONSE_TEMPLATES.get(base_cat_enum, RESPONSE_TEMPLATES[Category.GENERAL])
                suggested_response = template.format(ref_id=ref_id)

                if transaction_note:
                    suggested_response += f" (Note: {transaction_note})"

                return TriageResult(
                    category=predicted_category,
                    severity=severity,
                    sentiment=sentiment,
                    key_issue=key_issue,
                    key_issues=key_issues,
                    suggested_response=suggested_response,
                    confidence=round(float(torch.max(F.softmax(cat_logits, dim=-1)).item()), 2),
                    detected_language="English",
                    severity_reason=severity_reason,
                    urgency_score=urgency_score,
                    modality_weights=modality_weights,
                    triage_mode="local",
                    model_version="v1.0-gated"
                )
            except Exception as e:
                logger.error(f"Error in local multimodal triage: {e}. Running rule fallback.")
                return _rule_based_triage(
                    masked_text, skip_ai_draft=skip_ai_draft,
                    transaction_note=transaction_note,
                    customer_id=customer_id, transaction_id=transaction_id
                )


def _rule_based_triage(
    text: str,
    skip_ai_draft: bool = False,
    transaction_note: Optional[str] = None,
    customer_id: Optional[str] = None,
    transaction_id: Optional[str] = None
) -> TriageResult:
    lower = text.lower()

    base_category = Category.GENERAL
    for cat, keywords in CATEGORY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            base_category = cat
            break

    severity = Severity.MEDIUM
    severity_reason = "Default medium severity classification."
    for sev, keywords in SEVERITY_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            severity = sev
            severity_reason = f"Keyword match for {sev.value} severity."
            break

    sentiment = Sentiment.NEUTRAL
    for sent, keywords in SENTIMENT_KEYWORDS.items():
        if any(kw in lower for kw in keywords):
            sentiment = sent
            break

    first_sentence = text.split(".")[0].strip()
    key_issue = f"{base_category.value.capitalize()}: {first_sentence[:100]}"
    key_issues = [f"{base_category.value.capitalize()} issue", first_sentence[:90]]

    ref_id = str(uuid.uuid4())[:8].upper()
    template = RESPONSE_TEMPLATES.get(base_category, RESPONSE_TEMPLATES[Category.GENERAL])
    suggested_response = template.format(ref_id=ref_id)
    if transaction_note:
        suggested_response += f" (Note: {transaction_note})"

    urgency_map = {
        Severity.CRITICAL: 0.95,
        Severity.HIGH: 0.75,
        Severity.MEDIUM: 0.50,
        Severity.LOW: 0.20,
    }

    return TriageResult(
        category=base_category.value.capitalize(),
        severity=severity,
        sentiment=sentiment,
        key_issue=key_issue,
        key_issues=key_issues,
        suggested_response=suggested_response,
        confidence=0.85,
        detected_language="English",
        severity_reason=severity_reason,
        urgency_score=urgency_map.get(severity, 0.50),
        modality_weights={"text": 1.0, "audio": 0.0},
        triage_mode="local",
        model_version="v1.0-rules"
    )


class TriageService:
    def __init__(self):
        self.local_engine = LocalMultimodalTriageEngine()

    def triage_complaint(
        self,
        masked_text: str,
        audio_path: Optional[str] = None,
        skip_ai_draft: bool = False,
        transaction_note: Optional[str] = None,
        customer_id: Optional[str] = None,
        transaction_id: Optional[str] = None
    ) -> TriageResult:
        if TRIAGE_MODE == "local":
            return self.local_engine.triage(
                masked_text=masked_text,
                audio_path=audio_path,
                skip_ai_draft=skip_ai_draft,
                transaction_note=transaction_note,
                customer_id=customer_id,
                transaction_id=transaction_id
            )

        if not (GEMINI_API_KEY or ANTHROPIC_API_KEY):
            return self.local_engine.triage(
                masked_text=masked_text,
                audio_path=audio_path,
                skip_ai_draft=skip_ai_draft,
                transaction_note=transaction_note,
                customer_id=customer_id,
                transaction_id=transaction_id
            )

        try:
            system_prompt = (
                "You are an expert banking complaint triage AI for UniResolve. "
                "Classify the customer complaint and identify key issues.\n"
                "Respond with a strict JSON object containing keys: category, severity, sentiment, key_issue, key_issues, confidence, detected_language, severity_reason.\n"
                f"Allowed Severities: {[s.value for s in Severity]}\n"
                f"Allowed Sentiments: {[s.value for s in Sentiment]}\n"
            )
            fallback_val = {
                "category": "General",
                "severity": "medium",
                "sentiment": "neutral",
                "key_issue": masked_text[:120],
                "key_issues": [masked_text[:120]],
                "confidence": 0.85,
                "detected_language": "English",
                "severity_reason": "LLM API triage classification."
            }
            res = _claude_json(system_prompt, masked_text, fallback_val)
            category_str = normalize_category(res.get("category", "General"))

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

            ref_id = str(uuid.uuid4())[:8].upper()
            suggested_response = RESPONSE_TEMPLATES.get(Category.GENERAL).format(ref_id=ref_id)

            return TriageResult(
                category=category_str,
                severity=severity,
                sentiment=sentiment,
                key_issue=res.get("key_issue", masked_text[:120]),
                key_issues=res.get("key_issues", [masked_text[:120]]),
                suggested_response=suggested_response,
                confidence=float(res.get("confidence", 0.88)),
                detected_language=res.get("detected_language", "English"),
                severity_reason=res.get("severity_reason", "Classified via Cloud LLM triage engine."),
                urgency_score=0.75 if severity == Severity.HIGH else (0.95 if severity == Severity.CRITICAL else 0.45),
                modality_weights={"text": 1.0, "audio": 0.0},
                triage_mode="api",
                model_version="v1.0-cloud-api"
            )
        except Exception as e:
            logger.error(f"API triage failed: {e}. Falling back to local engine.")
            return self.local_engine.triage(
                masked_text=masked_text,
                audio_path=audio_path,
                skip_ai_draft=skip_ai_draft,
                transaction_note=transaction_note,
                customer_id=customer_id,
                transaction_id=transaction_id
            )


_triage_service: Optional[TriageService] = None

def get_triage_service() -> TriageService:
    global _triage_service
    if _triage_service is None:
        _triage_service = TriageService()
    return _triage_service

def generate_summary(text: str) -> str:
    sentences = re.split(r"[.!?]", text.strip())
    fallback = ". ".join(s.strip() for s in sentences[:2] if s.strip()) + "."
    if len(fallback) > 150:
        fallback = fallback[:147] + "..."
    return fallback
