import json
import logging
from datetime import datetime
from app.config import GEMINI_API_KEY, ANTHROPIC_API_KEY, GEMINI_MODEL, CLAUDE_MODEL

logger = logging.getLogger(__name__)

def _claude_json(system: str, user: str, fallback: dict) -> dict:
    if GEMINI_API_KEY:
        try:
            import httpx
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [{"text": f"Instruction: {system}\n\nInput: {user}"}]
                }],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 600
                }
            }
            res = httpx.post(url, json=payload, headers=headers, timeout=15.0)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                start = text.find("{")
                end = text.rfind("}") + 1
                return json.loads(text[start:end])
        except Exception as e:
            logger.warning(f"Gemini JSON generation failed: {e}")

    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=600,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text").strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            return json.loads(text[start:end])
        except Exception as e:
            logger.warning(f"Claude JSON generation failed: {e}")

    return fallback


def _claude_text(system: str, user: str, fallback: str) -> str:
    if GEMINI_API_KEY:
        try:
            import httpx
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [{"text": f"Instruction: {system}\n\nInput: {user}"}]
                }],
                "generationConfig": {
                    "maxOutputTokens": 120
                }
            }
            res = httpx.post(url, json=payload, headers=headers, timeout=15.0)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text:
                    return text
        except Exception as e:
            logger.warning(f"Gemini Text generation failed: {e}")

    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=120,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(block.text for block in msg.content if getattr(block, "type", "") == "text").strip() or fallback
        except Exception as e:
            logger.warning(f"Claude Text generation failed: {e}")

    return fallback
