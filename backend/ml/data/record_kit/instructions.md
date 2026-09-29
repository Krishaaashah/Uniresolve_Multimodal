# UniResolve Acoustic Recording Protocol & Test-Set Kit

## 1. Overview
This kit provides standardized instructions and prompt scripts for recording real human speech test clips to evaluate the UniResolve acoustic ASR and multimodal triage pipelines under real-world conditions.

## 2. Recording Guidelines
- **Format**: WAV, 16,000 Hz (16 kHz), 16-bit PCM, Mono channel.
- **Environment**: Record in a quiet room with minimal background echo.
- **Hardware**: Standard laptop microphone or smartphone voice recorder held 15–20 cm from mouth.
- **Variations**:
  - **Calm Tone**: Neutral pace, steady pitch, formal articulation.
  - **Frustrated Tone**: Faster pace, higher pitch variance, audible distress / urgency.

## 3. Storage Convention
Save recorded audio files to `backend/ml/data/record_kit/audio/` using the format:
`<script_id>_<tone>.wav` (e.g., `REC_001_frustrated.wav`, `REC_002_calm.wav`).

## 4. Test Evaluation
Run evaluation against human recordings using:
```powershell
python backend/ml/evaluate.py --eval-real-audio
```
