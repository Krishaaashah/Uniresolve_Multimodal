# UniResolve Evaluation Dataset & Validation Harness

This directory contains the ground-truth labeled evaluation harness and validation scripts for **UniResolve** (PS5: Unified Omnichannel Customer Grievance Ingestion and AI Triage System).

---

## 1. Overview & Contents

- **`eval_set.jsonl`**: 120 curated grievances with granular ground-truth labels across categories, severities, sentiments, languages, clustering keys, PII entities, and spam indicators.
- **`transactions.json`**: Ground-truth Core Banking System (CBS) transaction records matching all transactional grievance references in `eval_set.jsonl`.
- **`validate_dataset.py`**: Offline assertion script that validates schema conformity, transaction integrity, disk attachment existence, PII masking compliance, and embedding cosine similarities against `all-MiniLM-L6-v2`.
- **`build_eval_dataset.py`**: Generator script to build the evaluation dataset and CBS transactions.

---

## 2. Running the Validation Harness

To run the full validation suite offline without starting the FastAPI web server:

```powershell
cd backend
.\venv\Scripts\python eval/validate_dataset.py
```

### Validation Checks Performed:
1. **Schema Validation**: Every record strictly conforms to `RawComplaintIn` Pydantic models.
2. **CBS Transaction Pairing**: Every `transaction_id` referenced in the dataset exists in `transactions.json` with matching `customer_id`.
3. **Evidence Attachments**: Every multimodal evidence file (`.png`, `.wav`) referenced exists on disk in `app/connectors/mock_evidence/`.
4. **PII Masking Safety**: Zero un-prefixed 9–18 digit numbers in text (preventing PII scrubber collision with 12-digit transaction identifiers).
5. **Distribution Bounds**: Asserts no category exceeds 25%, all 6 channels $\ge 8\%$, and balanced severity distributions.
6. **Cosine Matrix Assertions**:
   - Encodes with `all-MiniLM-L6-v2` (`EMBEDDING_DIM = 384`).
   - Asserts all intended same-cluster pairs score $\ge 0.70$.
   - Asserts all 15 intended hard negative pairs score $< 0.70$.

---

## 3. Schema & Field Definitions (`eval_set.jsonl`)

Each line in `eval_set.jsonl` is a JSON object with the following structure:

```json
{
  "id": "EVAL-001",
  "raw_text": "UPI payment of Rs 2500 failed at merchant store but amount debited from my account. Please reverse it ref TXN-20001-A.",
  "channel": "app",
  "customer_id": "CUST-20001",
  "transaction_id": "TXN-20001-A",
  "days_ago": 2,
  "attachment_file": null,
  "gold": {
    "category": "UPI Failure",
    "severity": "high",
    "sentiment": "frustrated",
    "language": "English",
    "is_duplicate": false,
    "duplicate_of": null,
    "recurring": false,
    "systemic_member": true,
    "cluster_key": "upi_outage_eval_a",
    "pii_entities": [],
    "is_spam": false
  }
}
```

### Field Reference:
- **`id`**: Unique evaluation identifier (`EVAL-001` .. `EVAL-120`).
- **`raw_text`**: Unmasked grievance text in authentic Indian banking vocabulary.
- **`channel`**: Ingestion channel (`app`, `web`, `email`, `ivr`, `branch`, `social`).
- **`customer_id`**: Customer identifier formatted as `CUST-XXXXX`.
- **`transaction_id`**: Transaction identifier formatted as `TXN-XXXXX` (or `null` for non-transactional grievances).
- **`days_ago`**: Grievance age in days for SLA calculation and 7-day semantic duplicate window evaluation.
- **`gold.category`**: Human-readable triage category (e.g. `UPI Failure`, `ATM Failure`, `Fraud`, `Double Deduction`, `KYC Verification`, `Card Blocking`, `NetBanking`, `Account Services`, `Loan Foreclosure`, `Staff Misconduct`).
- **`gold.severity`**: Target severity level (`critical`, `high`, `medium`, `low`).
- **`gold.sentiment`**: Customer sentiment (`angry`, `frustrated`, `neutral`, `satisfied`).
- **`gold.language`**: Primary language (`English`, `Hindi`, `Marathi`, `Hinglish`).
- **`gold.is_duplicate`**: Boolean indicating if this is an unresolved duplicate.
- **`gold.duplicate_of`**: Reference to the parent `id` if duplicate.
- **`gold.recurring`**: Boolean indicating if this issue recurred after parent resolution.
- **`gold.systemic_member`**: Boolean indicating if complaint is part of an anomaly cluster.
- **`gold.cluster_key`**: Ground-truth clustering group label for computing duplicate clustering precision/recall/F1.
- **`gold.pii_entities`**: List of expected PII entities masked by Presidio/Regex (e.g. `["AADHAAR", "PAN", "MOBILE"]`).
- **`gold.is_spam`**: Boolean flag indicating spam/promotional noise rejected by the filter.

---

## 4. Ground-Truth Distribution Metrics

| Metric Group | Category / Class | Count | Percentage |
| :--- | :--- | :--- | :--- |
| **Category** | Account Services | 28 | 23.3% |
| | UPI Failure | 14 | 11.7% |
| | Fraud & Security | 12 | 10.0% |
| | Double Deduction | 12 | 10.0% |
| | Card Blocking & POS | 11 | 9.2% |
| | NetBanking & Login | 10 | 8.3% |
| | ATM Failure | 10 | 8.3% |
| | KYC Verification | 10 | 8.3% |
| | Loan Foreclosure & NOC | 8 | 6.7% |
| | Staff Misconduct | 3 | 2.5% |
| | General Support | 2 | 1.7% |
| **Severity** | Critical | 15 | 12.5% |
| | High | 40 | 33.3% |
| | Medium | 40 | 33.3% |
| | Low | 25 | 20.8% |
| **Channel** | Mobile App | 23 | 19.2% |
| | Branch Visit | 25 | 20.8% |
| | Web Portal | 23 | 19.2% |
| | Email | 21 | 17.5% |
| | Social Media | 16 | 13.3% |
| | IVR / Voice | 12 | 10.0% |
| **Language** | English | 90 | 75.0% |
| | Hindi | 18 | 15.0% |
| | Marathi | 8 | 6.7% |
| | Hinglish | 4 | 3.3% |
| **Duplication** | Duplicate & Recurring | 21 | 17.5% |
