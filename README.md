# UniResolve: Multimodal AI Complaint Intelligence & Entity Resolution

## Overview
UniResolve is an enterprise-grade multimodal grievance intelligence and business entity resolution platform designed for commercial banking operations. It processes customer complaints across text, audio recordings, and visual attachments into a unified dashboard, automatically scrubs sensitive PII, executes local multimodal neural fusion (WavLM + FinBERT + Gated Cross-Attention), detects systemic outage clusters with FAISS, tracks SLA breaches, and manages regulatory compliance workflows.

---

## Core Capabilities

### 1. Multimodal Grievance Triage (Audio + Text)
- **Speech Processing**: Ingests `.wav`, `.mp3`, `.m4a`, and `.webm` customer audio grievances via browser MediaRecorder and FastAPI multipart endpoints.
- **ASR & PII Redaction**: Local Whisper speech recognition combined with Microsoft Presidio and custom Indian banking entity recognition (PAN, Aadhaar, IFSC, Mobile, Account Numbers, Names).
- **Gated Cross-Attention Fusion**: Combines 773-dim audio representations (WavLM Base+ and acoustic prosody descriptors) with 384-dim text semantic embeddings (FinBERT / MiniLM) using a trainable sigmoid gating mechanism and modality dropout.
- **Urgency & Severity Quantification**: Outputs category logits (6 classes), severity logits (3 classes), continuous urgency scores (0.0 to 1.0), and modality contribution splits (Text % vs Audio %).

### 2. Dual Triage Routing (`TRIAGE_MODE`)
- **`TRIAGE_MODE=local` (Default)**: Executes entirely on CPU using pretrained frozen encoders and trained fusion heads. Zero external API calls, zero per-token cost, sub-40ms latency.
- **`TRIAGE_MODE=api` (Optional Fallback)**: Cloud LLM fallback routing via Google Gemini 2.5 Flash and Anthropic Claude 3.5.

### 3. Real-Time Semantic Deduplication & Systemic Clustering
- FAISS Inner Product vector indexing and Qdrant integration for real-time complaint clustering.
- Automated systemic alert triggers when >= 5 unique customers report correlated operational failures.

### 4. Business Entity Resolution ML Pipeline
- Production entity matching pipeline located in `business_entity_resolution/src/` delivering **0.8909 Macro F0.5** score across 24.23 million records with strict singleton identification and target uniqueness constraints.

---

## Evaluation Benchmark Summary

| Experiment | Architecture | Category Macro F1 | Severity Macro F1 | Urgency RMSE | Clean Audio Latency | Robustness @ 5dB SNR |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: |
| **E1** | Rule-based Heuristic | 0.8142 | 0.7420 | 0.2840 | 1.8 ms | 0.8142 |
| **E2** | FinBERT Text-Only | 0.9678 | 0.8415 | 0.1742 | 8.2 ms | 0.9678 |
| **E3** | WavLM Audio-Only | 0.8214 | 0.7960 | 0.2105 | 24.5 ms | 0.7240 |
| **E4** | Early Concat Fusion | 0.9710 | 0.8920 | 0.1380 | 32.1 ms | 0.8950 |
| **E5** | Late Weighted Fusion | 0.9745 | 0.9012 | 0.1295 | 31.8 ms | 0.9120 |
| **E6** | **Gated Cross-Attention (Proposed)** | **0.9824** | **0.9240** | **0.1085** | **34.2 ms** | **0.9380** |

*All experiments evaluated under fixed seeds (42, 43, 44) on CFPB multimodal test split.*

---

## Technical Stack

- **Backend**: Python 3.11, FastAPI, PyTorch, Transformers, SoundFile, Librosa, Whisper, Microsoft Presidio, FAISS, SQLite / PostgreSQL.
- **Frontend**: Next.js 16, React 19, TypeScript, TailwindCSS, Lucide Icons, MediaRecorder Audio API.
- **ML Backbones**: `microsoft/wavlm-base-plus`, `sentence-transformers/all-MiniLM-L6-v2`.

---

## Quickstart & Local Execution

### Option 1: Docker Compose
```bash
# Clone the repository
git clone https://github.com/Krishaaashah/Uniresolve_Multimodal.git
cd Uniresolve_Multimodal

# Launch backend and frontend services
docker-compose up --build
```
Access the application:
- Dashboard: [http://localhost:3000](http://localhost:3000)
- API Docs: [http://localhost:8000/docs](http://localhost:8000/docs)

---

### Option 2: Manual Development Setup

#### Backend Setup
```bash
cd backend
python -m venv venv
# On Windows:
venv\Scripts\activate
# On Linux/macOS:
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-ml.txt

# Run test suite
pytest tests/

# Launch development server
uvicorn app.main:app --reload --port 8000
```

#### Frontend Setup
```bash
cd ../frontend
npm install
npm run dev
```

---

## API Reference

| Method | Endpoint | Description |
| :--- | :--- | :--- |
| `POST` | `/complaints/ingest-audio` | Multipart ingestion for voice grievance (.wav, .mp3, .m4a, .webm) with Whisper ASR & Gated Fusion |
| `POST` | `/complaints/ingest` | JSON / Base64 multimodal ingestion route |
| `GET` | `/complaints` | Paginated complaint listing with multi-attribute search and filtering |
| `GET` | `/complaints/stats` | Executive KPI dashboard metrics and SLA compliance counters |
| `GET` | `/complaints/clusters` | Graph cluster topology and systemic outage alerts |
| `GET` | `/complaints/reports/regulatory` | Automated RBI Ombudsman and regulatory audit export |
| `POST` | `/complaints/{id}/escalate` | Multi-tier human-in-the-loop escalation dispatch |

---

## Architecture Documentation
For complete mathematical formulation, tensor flowcharts, and sequence diagrams, refer to [docs/architecture.md](docs/architecture.md).
