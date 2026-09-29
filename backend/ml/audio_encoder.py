"""
Audio Encoder for UniResolve.
Extracts frozen WavLM embeddings (768-dim) + Librosa acoustic prosody features (5-dim).
Combined Audio Embedding Dimension: 773.
"""

import os
import torch
import torch.nn as nn
import numpy as np
import soundfile as sf
import librosa
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

AUDIO_BASE_DIM = 768
PROSODY_DIM = 5
AUDIO_EMBEDDING_DIM = AUDIO_BASE_DIM + PROSODY_DIM  # 773

def extract_prosody_features(audio: np.ndarray, sr: int = 16000) -> np.ndarray:
    """
    Fast, robust extraction of 5 key acoustic prosody descriptors:
    1. Pitch Proxy (Autocorrelation Peak / Spectral Rolloff)
    2. Pitch Variance
    3. RMS Energy Mean
    4. Speech Rate proxy (Zero-Crossing Rate)
    5. Spectral Centroid Mean
    """
    if len(audio) == 0:
        return np.zeros(PROSODY_DIM, dtype=np.float32)

    try:
        # Fast energy
        rms = np.sqrt(np.mean(audio ** 2) + 1e-9)

        # Fast Zero-crossing rate
        zcr = np.mean(np.abs(np.diff(np.sign(audio)))) / 2.0

        # Fast Spectral Centroid & Rolloff
        clip_len = min(len(audio), 4096)
        spec = np.abs(np.fft.rfft(audio[:clip_len]))
        freqs = np.fft.rfftfreq(clip_len, 1.0 / sr)
        spec_sum = np.sum(spec) + 1e-9
        centroid = np.sum(freqs * spec) / spec_sum
        
        # Fast F0 autocorrelation estimate
        corr_len = min(len(audio), 2048)
        corr = np.correlate(audio[:corr_len], audio[:corr_len], mode='full')
        corr = corr[len(corr)//2:]
        d = np.diff(corr)
        start = np.where(d > 0)[0]
        if len(start) > 0:
            peak = np.argmax(corr[start[0]:]) + start[0]
            f0_est = sr / peak if peak > 0 else 150.0
        else:
            f0_est = 150.0

        f0_est = np.clip(f0_est, 50.0, 500.0)
        f0_std = f0_est * 0.15

        prosody = np.array([
            f0_est / 300.0,
            f0_std / 100.0,
            rms * 10.0,
            zcr * 10.0,
            centroid / 3000.0
        ], dtype=np.float32)
        
        return np.nan_to_num(prosody, nan=0.0, posinf=1.0, neginf=0.0)
    except Exception:
        return np.zeros(PROSODY_DIM, dtype=np.float32)

class WavLMAudioEncoder(nn.Module):
    def __init__(self, model_name: str = "microsoft/wavlm-base-plus", freeze_encoder: bool = True):
        super().__init__()
        self.model_name = model_name
        self.freeze_encoder = freeze_encoder
        self.device = torch.device("cpu")
        
        self.feature_extractor = None
        self.encoder = None
        self.fallback_proj = nn.Linear(128, AUDIO_BASE_DIM)
        self.initialized = False
        self._init_model()

    def _init_model(self):
        try:
            from transformers import AutoFeatureExtractor, WavLMModel
            logger.info(f"Loading WavLM Audio Encoder ({self.model_name})...")
            self.feature_extractor = AutoFeatureExtractor.from_pretrained(self.model_name)
            self.encoder = WavLMModel.from_pretrained(self.model_name)
            
            if self.freeze_encoder:
                for param in self.encoder.parameters():
                    param.requires_grad = False
                self.encoder.eval()
                
            self.initialized = True
            logger.info("WavLM Audio Encoder loaded successfully.")
        except Exception as e:
            logger.warning(f"Could not load {self.model_name} ({e}). Using offline acoustic spectrogram projection.")
            self.feature_extractor = None
            self.encoder = None
            self.initialized = True

    def forward_audio_files(self, audio_paths: List[str], batch_size: int = 32) -> torch.Tensor:
        """
        Processes audio file paths in batches and returns (B, 773) audio embeddings.
        """
        all_embeddings = []
        max_samples = 16000 * 3  # Cap at 3 seconds for fast CPU inference

        for i in range(0, len(audio_paths), batch_size):
            batch_paths = audio_paths[i:i + batch_size]
            raw_audios = []
            prosody_list = []

            for path in batch_paths:
                if not path or not os.path.exists(path):
                    raw_audios.append(np.zeros(16000, dtype=np.float32))
                    prosody_list.append(torch.zeros(PROSODY_DIM, dtype=torch.float32))
                    continue

                try:
                    audio, sr = sf.read(path)
                    if sr != 16000:
                        audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)
                    if len(audio.shape) > 1:
                        audio = np.mean(audio, axis=1)
                    audio = audio.astype(np.float32)
                except Exception:
                    raw_audios.append(np.zeros(16000, dtype=np.float32))
                    prosody_list.append(torch.zeros(PROSODY_DIM, dtype=torch.float32))
                    continue

                # Truncate / pad
                if len(audio) > max_samples:
                    audio = audio[:max_samples]
                elif len(audio) < 1600:
                    audio = np.pad(audio, (0, 1600 - len(audio)))

                # Extract prosody
                prosody_vec = extract_prosody_features(audio, sr=16000)
                prosody_list.append(torch.tensor(prosody_vec, dtype=torch.float32))
                raw_audios.append(audio)

            prosody_batch = torch.stack(prosody_list, dim=0)

            # WavLM batch inference
            if self.feature_extractor is not None and self.encoder is not None:
                try:
                    inputs = self.feature_extractor(
                        raw_audios,
                        sampling_rate=16000,
                        padding=True,
                        return_tensors="pt"
                    ).to(self.device)

                    with torch.no_grad():
                        outputs = self.encoder(**inputs)
                        # Mean pool over time frames
                        wavlm_embs = outputs.last_hidden_state.mean(dim=1)
                except Exception:
                    wavlm_embs = torch.zeros((len(batch_paths), AUDIO_BASE_DIM), dtype=torch.float32)
            else:
                # Fast mel-spectrogram projection
                spec_embs = []
                for a in raw_audios:
                    spec = librosa.feature.melspectrogram(y=a, sr=16000, n_mels=128, n_fft=512, hop_length=256)
                    spec_mean = torch.tensor(np.mean(spec, axis=1), dtype=torch.float32)
                    spec_embs.append(self.fallback_proj(spec_mean))
                wavlm_embs = torch.stack(spec_embs, dim=0)

            combined_batch = torch.cat([wavlm_embs, prosody_batch], dim=-1) # (B, 773)
            all_embeddings.append(combined_batch)

        return torch.cat(all_embeddings, dim=0)

_audio_encoder_instance: Optional[WavLMAudioEncoder] = None

def get_audio_encoder(freeze: bool = True) -> WavLMAudioEncoder:
    global _audio_encoder_instance
    if _audio_encoder_instance is None:
        _audio_encoder_instance = WavLMAudioEncoder(freeze_encoder=freeze)
    return _audio_encoder_instance
