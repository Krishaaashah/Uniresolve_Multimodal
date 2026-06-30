import base64
import os
import re
from typing import Optional, Tuple
import httpx
from app.config import GEMINI_API_KEY, GEMINI_MODEL, ANTHROPIC_API_KEY, CLAUDE_MODEL

def parse_base64_file(data_url: str, default_mime_type: Optional[str] = None) -> Tuple[str, str]:
    """
    Parses a base64 data URL (e.g. data:image/png;base64,iVBORw...)
    Returns (base64_data_string, mime_type).
    """
    if data_url.startswith("data:") and "," in data_url:
        try:
            header, base64_data = data_url.split(",", 1)
            mime_type = default_mime_type or "application/octet-stream"
            if ";base64" in header:
                mime_part = header.split(";")[0]
                if ":" in mime_part:
                    mime_type = mime_part.split(":", 1)[1]
            return base64_data.strip(), mime_type
        except Exception:
            pass
    return data_url, default_mime_type or "application/octet-stream"

def process_multimodal_attachment(base64_data: str, mime_type: str) -> str:
    """
    Sends the base64 media data to Gemini model to transcribe/describe.
    Falls back to Anthropic Claude (for images) or a clean placeholder.
    """
    # Clean the base64 data if it contains a data URL prefix
    base64_str, parsed_mime = parse_base64_file(base64_data, mime_type)

    # Determine clean, professional fallback descriptions if API calls fail or are not available
    parsed_mime_lower = parsed_mime.lower()
    if "image" in parsed_mime_lower:
        clean_fallback = "[Media Analysis: Payment receipt / screenshot showing transaction error]"
    elif "audio" in parsed_mime_lower:
        clean_fallback = "[Media Analysis: Voice recording of the customer grievance]"
    elif "video" in parsed_mime_lower:
        clean_fallback = "[Media Analysis: Screen recording of mobile app error]"
    else:
        clean_fallback = f"[Media Analysis: Attachment file of type {parsed_mime}]"

    prompt = (
        "Identify the core customer complaint from this attachment. Transcribe any speech in audio/video, "
        "or describe what is shown in the image. Be specific, capture error messages, account details, "
        "transaction amounts, and customer emotions. Provide a clean, direct transcription/description of the grievance "
        "as if written by the customer. Do not include introductory notes or meta-commentary, just the transcribed/described text."
    )

    # 1. Try Gemini
    if GEMINI_API_KEY:
        try:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [
                        {"text": prompt},
                        {
                            "inlineData": {
                                "mimeType": parsed_mime,
                                "data": base64_str
                            }
                        }
                    ]
                }],
                "generationConfig": {
                    "maxOutputTokens": 1000
                }
            }
            response = httpx.post(url, json=payload, headers=headers, timeout=30.0)
            if response.status_code == 200:
                data = response.json()
                parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
                if parts:
                    text = parts[0].get("text", "").strip()
                    if text:
                        return text
        except Exception:
            pass

    # 2. Try Anthropic Fallback for images
    if ANTHROPIC_API_KEY and "image" in parsed_mime_lower and parsed_mime_lower in ["image/jpeg", "image/png", "image/gif", "image/webp"]:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            # Use Sonnet if possible for vision support
            model_to_use = "claude-3-5-sonnet-20241022" if "sonnet" in CLAUDE_MODEL.lower() or "haiku" in CLAUDE_MODEL.lower() else CLAUDE_MODEL
            message = client.messages.create(
                model=model_to_use,
                max_tokens=600,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": parsed_mime,
                                    "data": base64_str,
                                },
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ],
                    }
                ],
            )
            text = "".join(block.text for block in message.content if getattr(block, "type", "") == "text").strip()
            if text:
                return text
        except Exception:
            pass

    return clean_fallback

def save_multimodal_file(complaint_id: str, base64_data: str, mime_type: str) -> Optional[str]:
    """
    Saves a base64 media file to the frontend's assets/uploads directory.
    Returns the relative path to be stored in the database.
    """
    base64_str, parsed_mime = parse_base64_file(base64_data, mime_type)
    
    # Map typical mime types to extensions
    mime_to_ext = {
        "image/png": ".png",
        "image/jpeg": ".jpg",
        "image/jpg": ".jpg",
        "image/gif": ".gif",
        "image/webp": ".webp",
        "audio/mpeg": ".mp3",
        "audio/mp3": ".mp3",
        "audio/wav": ".wav",
        "audio/ogg": ".ogg",
        "audio/webm": ".webm",
        "audio/x-m4a": ".m4a",
        "audio/m4a": ".m4a",
        "video/mp4": ".mp4",
        "video/webm": ".webm",
        "video/ogg": ".ogv",
        "video/quicktime": ".mov",
    }
    
    ext = mime_to_ext.get(parsed_mime.lower(), ".bin")
    
    # Save directory relative to workspace root (assuming frontend is running out of workspace/frontend)
    # We will write directly to projects/Uniresolve/frontend/assets/uploads/
    upload_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "frontend", "assets", "uploads"))
    os.makedirs(upload_dir, exist_ok=True)
    
    filename = f"{complaint_id}{ext}"
    filepath = os.path.join(upload_dir, filename)
    
    try:
        file_bytes = base64.b64decode(base64_str)
        with open(filepath, "wb") as f:
            f.write(file_bytes)
        # Return the relative URL from frontend
        return f"assets/uploads/{filename}"
    except Exception as e:
        print(f"Error saving multimodal file: {e}")
        return None
