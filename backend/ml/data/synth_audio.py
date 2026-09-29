"""
Synthetic Audio Generator for UniResolve.
Generates 16 kHz mono WAV audio with randomized speaking rates, pitches,
and creates acoustic noise copies at SNR 20, 10, and 5 dB.
"""

import os
import json
import random
import numpy as np
import soundfile as sf
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
AUDIO_DIR = BASE_DIR / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

SAMPLE_RATE = 16000  # 16 kHz requirement

# Voice synthesis engine
_tts_engine = None

def init_tts():
    global _tts_engine
    if _tts_engine is None:
        try:
            import pyttsx3
            _tts_engine = pyttsx3.init()
        except Exception:
            _tts_engine = None
    return _tts_engine

def add_noise(audio: np.ndarray, target_snr_db: float) -> np.ndarray:
    """Adds white Gaussian noise to achieve specified Signal-to-Noise Ratio (SNR)."""
    sig_power = np.mean(audio ** 2)
    if sig_power == 0:
        return audio
    
    snr_linear = 10 ** (target_snr_db / 10.0)
    noise_power = sig_power / snr_linear
    noise = np.random.normal(0, np.sqrt(noise_power), audio.shape)
    
    noisy_audio = audio + noise
    # Normalize to avoid clipping
    max_val = np.max(np.abs(noisy_audio))
    if max_val > 1.0:
        noisy_audio = noisy_audio / max_val
    return noisy_audio.astype(np.float32)

def generate_procedural_speech(text: str, rate: int = 150, pitch_shift: float = 1.0) -> np.ndarray:
    """
    Generates procedural vocal acoustic audio representing speech formants.
    Used for instant, reproducible, 100% offline 16 kHz audio generation.
    """
    words = text.split()
    duration_per_word = 60.0 / max(rate, 60) # seconds per word
    total_duration = max(1.0, len(words) * duration_per_word)
    num_samples = int(total_duration * SAMPLE_RATE)
    
    t = np.linspace(0, total_duration, num_samples, endpoint=False)
    
    # Formant frequency modulation
    f0 = 130.0 * pitch_shift  # fundamental frequency
    f1 = 500.0 * pitch_shift  # first formant
    f2 = 1500.0 * pitch_shift # second formant
    f3 = 2500.0 * pitch_shift # third formant
    
    # Pitch contour modulation based on sentence length
    pitch_contour = f0 * (1.0 + 0.15 * np.sin(2 * np.pi * 0.8 * t) + 0.05 * np.sin(2 * np.pi * 2.5 * t))
    phase = 2 * np.pi * np.cumsum(pitch_contour) / SAMPLE_RATE
    
    # Glottal source approximation + vocal tract resonances
    glottal = 0.5 * np.sin(phase) + 0.25 * np.sin(2 * phase) + 0.12 * np.sin(3 * phase)
    vocal_tract = (
        0.4 * np.sin(2 * np.pi * f1 * t) * np.exp(-t % 0.1 * 10) +
        0.3 * np.sin(2 * np.pi * f2 * t) * np.exp(-t % 0.08 * 12) +
        0.2 * np.sin(2 * np.pi * f3 * t) * np.exp(-t % 0.05 * 15)
    )
    
    # Syllable envelope modulation
    syllable_rate = 4.5 * (rate / 150.0) # ~4.5 syllables per sec
    envelope = 0.5 * (1.0 + np.sin(2 * np.pi * syllable_rate * t - np.pi/2))
    envelope = np.clip(envelope, 0.05, 1.0)
    
    signal = (glottal * 0.4 + vocal_tract * 0.6) * envelope
    # Soft fade in/out
    fade_len = min(1600, num_samples // 10)
    signal[:fade_len] *= np.linspace(0, 1, fade_len)
    signal[-fade_len:] *= np.linspace(1, 0, fade_len)
    
    signal = signal / (np.max(np.abs(signal)) + 1e-6) * 0.85
    return signal.astype(np.float32)

def synthesize_record_audio(rec_id: str, text: str, output_dir: Path) -> dict:
    """
    Synthesizes clean audio and noise augmented copies at SNR 20, 10, 5 dB.
    Returns dictionary of generated audio paths.
    """
    # Deterministic randomization keyed by rec_id
    rng = random.Random(rec_id)
    rate = rng.randint(130, 190)        # words per minute
    pitch_factor = rng.uniform(0.85, 1.25)
    
    clean_audio = generate_procedural_speech(text, rate=rate, pitch_shift=pitch_factor)
    
    clean_path = output_dir / f"{rec_id}_clean.wav"
    sf.write(str(clean_path), clean_audio, SAMPLE_RATE, subtype='PCM_16')
    
    # Generate noisy copies at SNR 20, 10, 5 dB
    noisy_paths = {}
    for snr in [20, 10, 5]:
        noisy_audio = add_noise(clean_audio, target_snr_db=float(snr))
        p = output_dir / f"{rec_id}_snr{snr}.wav"
        sf.write(str(p), noisy_audio, SAMPLE_RATE, subtype='PCM_16')
        noisy_paths[f"snr_{snr}"] = str(p)
        
    return {
        "clean": str(clean_path),
        **noisy_paths
    }

def main():
    splits_dir = BASE_DIR / "splits"
    print("Generating 16 kHz synthetic audio and SNR augmentations (20, 10, 5 dB)...")
    
    total_generated = 0
    for split_name in ["train", "val", "test"]:
        split_file = splits_dir / f"{split_name}.jsonl"
        if not split_file.exists():
            continue
            
        with open(split_file, "r", encoding="utf-8") as f:
            records = [json.loads(line) for line in f]
            
        split_audio_dir = AUDIO_DIR / split_name
        split_audio_dir.mkdir(parents=True, exist_ok=True)
        
        for r in records:
            audio_meta = synthesize_record_audio(r["id"], r["raw_text"], split_audio_dir)
            r["audio_paths"] = audio_meta
            total_generated += 1
            
        # Update JSONL with audio paths
        with open(split_file, "w", encoding="utf-8") as f:
            for r in records:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
                
        print(f"Processed {len(records):4d} records for {split_name} split.")

    print(f"\nCompleted! Generated {total_generated} audio files + 3x SNR augmentations.")

if __name__ == "__main__":
    main()
