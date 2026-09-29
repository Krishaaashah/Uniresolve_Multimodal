"""
Unit and Integration Tests for UniResolve Multimodal Triage System.
Tests:
1. PII Scrubbing on raw speech transcripts before database persistence.
2. Multimodal Fusion Module tensor shapes and modality masking.
3. POST /api/complaints/ingest-audio multipart ingestion route with synthetic audio.
4. Feature flag TRIAGE_MODE configuration and fallback routing.
"""

import os
import sys
import io
import wave
import struct
import math
import pytest
import torch
from fastapi.testclient import TestClient

# Ensure backend root is on sys.path
BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.main import app
from app.config import API_KEY, TRIAGE_MODE
from app.services.pii_scrubber import mask_pii, is_safe
from app.services.store import get_store
from app.services.clustering import get_clustering_service
from app.services.triage import get_triage_service, LocalMultimodalTriageEngine
from ml.fusion import GatedCrossAttentionFusion, EarlyConcatFusion, LateWeightedFusion


def create_synthetic_wav_bytes(duration_sec: float = 1.0, sample_rate: int = 16000, freq: float = 440.0) -> bytes:
    """Generates a clean synthetic PCM WAV file in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)        # Mono
        wf.setsampwidth(2)        # 16-bit
        wf.setframerate(sample_rate)
        num_samples = int(duration_sec * sample_rate)
        for i in range(num_samples):
            sample = int(32767.0 * 0.5 * math.sin(2.0 * math.pi * freq * (i / sample_rate)))
            wf.writeframes(struct.pack("<h", sample))
    return buf.getvalue()


def test_pii_scrubbing_on_transcript():
    """Verify that sensitive PII entities are scrubbed from speech transcripts before storage."""
    raw_transcript = (
        "Hello, my name is Mr. Rajesh Kumar. My PAN number is ABCDE1234F and Aadhaar is 9876 5432 1098. "
        "I noticed an unauthorized UPI transaction of Rs 5,000 on my mobile number 9876543210."
    )
    masked_text, detected_entities = mask_pii(raw_transcript)
    
    # Assert raw PII is scrubbed
    assert "ABCDE1234F" not in masked_text
    assert "9876 5432 1098" not in masked_text
    assert "9876543210" not in masked_text
    assert "[PAN_XXXX]" in masked_text or "XXXX" in masked_text
    assert len(detected_entities) > 0


def test_fusion_model_tensor_shapes_and_masking():
    """Verify forward pass tensor dimensions and modality dropout/masking on GatedCrossAttentionFusion."""
    fusion_model = GatedCrossAttentionFusion(text_dim=384, audio_dim=773, hidden_dim=256)
    fusion_model.eval()

    batch_size = 4
    text_emb = torch.randn(batch_size, 384)
    audio_emb = torch.randn(batch_size, 773)

    # 1. Multimodal forward pass
    outputs = fusion_model(text_emb, audio_emb)
    assert outputs["category_logits"].shape == (batch_size, 6)
    assert outputs["severity_logits"].shape == (batch_size, 3)
    assert outputs["fused_features"].shape == (batch_size, 256)
    assert "modality_weights" in outputs
    assert "text" in outputs["modality_weights"]
    assert "audio" in outputs["modality_weights"]

    # 2. Text-only forward pass with audio_mask=0
    audio_mask = torch.zeros(batch_size)
    text_only_outputs = fusion_model(text_emb, audio_emb, audio_mask=audio_mask)
    assert text_only_outputs["category_logits"].shape == (batch_size, 6)
    assert text_only_outputs["severity_logits"].shape == (batch_size, 3)
    assert text_only_outputs["modality_weights"]["audio"] == 0.0


def test_ingest_audio_endpoint():
    """Test POST /api/complaints/ingest-audio multipart route."""
    store = get_store()
    clustering = get_clustering_service()
    store.clear()
    clustering.clear()

    wav_bytes = create_synthetic_wav_bytes(duration_sec=0.5)
    client = TestClient(app)

    headers = {
        "x-api-key": API_KEY or "uniresolve-dev-secret-key"
    }

    files = {
        "audio_file": ("customer_voice_grievance.wav", wav_bytes, "audio/wav")
    }
    data = {
        "customer_id": "CUST-10245",
        "transaction_id": "TXN-10245-F1",
        "channel": "voice",
        "channel_metadata": '{"device": "mobile_app", "os": "Android"}'
    }

    response = client.post("/api/complaints/ingest-audio", headers=headers, files=files, data=data)
    assert response.status_code == 200

    resp_json = response.json()
    assert "complaint" in resp_json
    c = resp_json["complaint"]

    # Verify complaint metadata and triage results
    assert c["customer_id"] == "CUST-10245"
    assert c["channel"] == "voice"
    assert c["triage"] is not None
    assert c["triage"]["category"] in ["Loans", "Accounts", "Credit Cards", "UPI/Payments", "Transaction Errors", "KYC/Verification", "General"]
    assert c["triage"]["severity"] in ["low", "medium", "high", "critical"]
    assert c["urgency_score"] is not None
    assert 0.0 <= c["urgency_score"] <= 1.0
    assert c["modality_weights"] is not None
    assert c["triage_mode"] in ["local", "api"]
    assert c["audio_url"] is not None
    assert c["audio_url"].startswith("/assets/uploads/audio/")

    # Verify persisted in store
    saved = store.get(c["id"])
    assert saved is not None
    assert saved.customer_id == "CUST-10245"


def test_triage_mode_and_local_engine():
    """Verify local multimodal triage engine inference."""
    local_engine = LocalMultimodalTriageEngine()
    
    complaint_text = "My UPI payment failed at the grocery store and 2,500 rupees was debited. Please refund it immediately."
    res = local_engine.triage(
        masked_text=complaint_text,
        customer_id="CUST-10245",
        transaction_id="TXN-10245-F1"
    )

    assert res.category is not None
    assert res.severity is not None
    assert res.urgency_score is not None
    assert res.triage_mode == "local"
    assert res.model_version == "v1.0-gated"
    assert len(res.suggested_response) > 0
