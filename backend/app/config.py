import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("API_KEY", "uniresolve-dev-secret-key")

ALLOWED_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "ALLOWED_ORIGINS",
        "http://localhost:3000,http://localhost:5000,http://localhost:8000,"
        "http://127.0.0.1:3000,http://127.0.0.1:5000,http://127.0.0.1:8000"
    ).split(",")
    if origin.strip()
]

# Triage mode: 'local' (multimodal fusion with WavLM + FinBERT) or 'api' (Gemini/Claude LLM)
TRIAGE_MODE = os.getenv("TRIAGE_MODE", "local").lower()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
CLAUDE_MODEL = os.getenv("CLAUDE_MODEL", "claude-haiku-4-5")

CONNECTOR_POLL_INTERVAL = int(os.getenv("CONNECTOR_POLL_INTERVAL", "30"))
EMAIL_USERNAME = os.getenv("EMAIL_USERNAME")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
REDDIT_USER_AGENT = os.getenv("REDDIT_USER_AGENT", "uniresolve")

SLA_HOURS = {
    "critical": 2,
    "high": 8,
    "medium": 24,
    "low": 72,
}

DEFAULT_TENANT_NAME = os.getenv("TENANT_NAME", "Union Bank")
SIMILARITY_THRESHOLD = float(os.getenv("SIMILARITY_THRESHOLD", "0.70"))
CLUSTER_ALERT_THRESHOLD = int(os.getenv("CLUSTER_ALERT_THRESHOLD", "5"))

SLA_HOURS_TABLE = {
    "Fraud": int(os.getenv("SLA_HOURS_FRAUD", "24")),
    "UPI Failure": int(os.getenv("SLA_HOURS_UPI", "48")),
    "ATM Failure": int(os.getenv("SLA_HOURS_ATM", "48")),
    "Card Blocking": int(os.getenv("SLA_HOURS_CARD", "24")),
    "KYC Verification": int(os.getenv("SLA_HOURS_KYC", "120")),
    "Double Deduction": int(os.getenv("SLA_HOURS_DOUBLE_DEDUCTION", "72")),
    "general": int(os.getenv("SLA_HOURS_GENERAL", "240"))
}

AUDIO_UPLOAD_DIR = os.getenv(
    "AUDIO_UPLOAD_DIR",
    os.path.abspath(
        os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "public", "assets", "uploads", "audio")
    )
)
os.makedirs(AUDIO_UPLOAD_DIR, exist_ok=True)
