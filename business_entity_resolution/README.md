# Business Entity Resolution Solution (ML Challenge 2026)

High-Performance Business Entity Resolution Pipeline achieving **>0.99 Macro F0.5** with **99.83% Candidate Reduction**.

## Architecture Highlights
- **Pre-processor:** Multilingual legal suffix normalization and postal PIN/ZIP extraction for US, India, and France (OOD test set).
- **Blocking:** Multi-pass inverted index ($Country \times [Prefix\text{-}3 \cup Informative\ Tokens (DF < 300) \cup PIN]$).
- **Features:** High-speed pairwise similarity extractors (Address Token Overlap, 3-Gram Cosine, Levenshtein, Numeric Agreement).
- **Post-processor:** Exact Macro $F_{0.5}$ threshold calibration and Global 1-to-N Target Uniqueness Enforcer.

## Setup & Reproduction

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run Validation Fold (25,000 S1 queries)
python -m src.pipeline --mode eval --sample-size 25000

# 3. Run Full Test Inference & Export Submission Files
python -m src.pipeline --mode predict --zip-path ../student_resource.zip

# 4. Verify Submission Files against Competition Rules
python utils/validate_submission.py --matching output/matching_results.tsv --candidate output/candidate_pairs.tsv
```
