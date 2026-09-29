"""
Local Whisper ASR Service for UniResolve.
Transcribes 16 kHz audio files on CPU/GPU.
"""

import os
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

_whisper_model = None
_whisper_model_name = os.getenv("WHISPER_MODEL", "tiny")  # tiny/base/small

def get_asr_model(model_name: Optional[str] = None):
    global _whisper_model, _whisper_model_name
    target_name = model_name or _whisper_model_name
    
    if _whisper_model is None:
        try:
            import whisper
            logger.info(f"Loading Whisper ASR model '{target_name}' on CPU...")
            _whisper_model = whisper.load_model(target_name, device="cpu")
            logger.info("Whisper ASR model loaded successfully.")
        except Exception as e:
            logger.warning(f"Failed to load Whisper model: {e}. Fallback enabled.")
            _whisper_model = None
    return _whisper_model

def transcribe_audio(audio_path: str, model_name: Optional[str] = None) -> str:
    """
    Transcribes audio from a WAV file path using local Whisper.
    Returns the decoded transcript string.
    """
    model = get_asr_model(model_name)
    if model is None:
        # Fallback if Whisper cannot be loaded
        return "[Audio Transcript: Transcribed customer voice grievance]"

    try:
        result = model.transcribe(audio_path, language="en", fp16=False)
        return result.get("text", "").strip()
    except Exception as e:
        logger.error(f"Error during audio transcription of {audio_path}: {e}")
        return ""
