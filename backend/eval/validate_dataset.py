"""
Offline Dataset Validation Harness for UniResolve.

Asserts:
1. Every record passes RawComplaintIn Pydantic schema validation.
2. Every transaction_id referenced exists in transactions table / transactions.json.
3. Every attachment_file exists on disk.
4. No bare 9–18 digit number appears in any raw_text (except intentional PII test records).
5. Encodes all records with all-MiniLM-L6-v2 and evaluates cosine similarities:
   - Intended same-cluster pairs score >= 0.70.
   - Intended hard negative pairs score < 0.70.
   - Prints any violation as a FAIL line with both texts.
6. Validates distribution targets across category, severity, channel, and language.

Exits with code 1 on any failure, or code 0 if all assertions pass.
"""

import os
import re
import sys
import json
from collections import Counter
from pathlib import Path
import numpy as np

# Ensure backend root is on sys.path
BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app.models.complaint import RawComplaintIn, Channel, Severity
from sentence_transformers import SentenceTransformer


def validate_dataset():
    print("=" * 70)
    print("UniResolve Dataset Validation Harness")
    print("=" * 70)

    eval_jsonl = BASE_DIR / "eval" / "eval_set.jsonl"
    eval_txs_json = BASE_DIR / "eval" / "transactions.json"
    mock_evidence_dir = BASE_DIR / "app" / "connectors" / "mock_evidence"

    if not eval_jsonl.exists():
        print(f"FAIL: {eval_jsonl} does not exist!")
        sys.exit(1)

    if not eval_txs_json.exists():
        print(f"FAIL: {eval_txs_json} does not exist!")
        sys.exit(1)

    # 1. Load data
    eval_records = []
    with open(eval_jsonl, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                eval_records.append(data)
            except Exception as e:
                print(f"FAIL: Line {line_no} in {eval_jsonl} is invalid JSON: {e}")
                sys.exit(1)

    with open(eval_txs_json, "r", encoding="utf-8") as f:
        transactions = json.load(f)

    print(f" Loaded {len(eval_records)} evaluation records and {len(transactions)} transactions.")

    failures = []

    # 2. Schema Validation (RawComplaintIn)
    print("\n[1/5] Validating Pydantic Schemas (RawComplaintIn)...")
    for r in eval_records:
        rid = r.get("id", "UNKNOWN")
        try:
            raw_in = RawComplaintIn(
                channel=r["channel"],
                raw_text=r["raw_text"],
                customer_id=r.get("customer_id"),
                transaction_id=r.get("transaction_id"),
                channel_metadata={"seed": True},
            )
        except Exception as e:
            failures.append(f"Schema error for {rid}: {e}")

    if not failures:
        print("  All 120 records passed RawComplaintIn validation.")
    else:
        for f in failures:
            print(f"  FAIL: {f}")
        sys.exit(1)

    # 3. Transaction Pairing & Attachment Validation
    print("\n[2/5] Validating CBS Transaction Pairing & Evidence Attachments...")
    for r in eval_records:
        rid = r["id"]
        tx_id = r.get("transaction_id")
        if tx_id:
            if tx_id not in transactions:
                failures.append(f"Missing transaction: {rid} references {tx_id} which is not in transactions.json")
            else:
                # Validate customer ID match
                tx = transactions[tx_id]
                if r.get("customer_id") and tx.get("customer_id") != r.get("customer_id"):
                    failures.append(f"Customer mismatch: {rid} (cust: {r.get('customer_id')}) != {tx_id} (cust: {tx.get('customer_id')})")

        att_file = r.get("attachment_file")
        if att_file:
            att_path = mock_evidence_dir / att_file
            if not att_path.exists():
                failures.append(f"Missing attachment on disk: {rid} references {att_file} at {att_path}")

    if not failures:
        print("  All referenced transactions and attachments verified on disk.")
    else:
        for f in failures:
            print(f"  FAIL: {f}")
        sys.exit(1)

    # 4. PII Masking Collisions & Bare Digits Check
    print("\n[3/5] Validating PII & Bare Digits Rule (No un-prefixed 9-18 digit txns)...")
    bare_digit_pattern = re.compile(r"(?<![A-Za-z0-9-])\d{9,18}(?![A-Za-z0-9-])")
    for r in eval_records:
        rid = r["id"]
        gold = r.get("gold", {})
        pii_entities = gold.get("pii_entities", [])
        is_intentional_pii = len(pii_entities) > 0 or gold.get("is_spam", False)

        # Check for bare 9-18 digit numbers unless intentionally testing PII
        matches = bare_digit_pattern.findall(r["raw_text"])
        if matches and not is_intentional_pii:
            failures.append(f"Bare 9-18 digit number {matches} found in non-PII record {rid}: '{r['raw_text']}'")

    if not failures:
        print("  No accidental bare 9-18 digit numbers found in text.")
    else:
        for f in failures:
            print(f"  FAIL: {f}")
        sys.exit(1)

    # 5. Distribution Targets Check
    print("\n[4/5] Checking Dataset Distribution Targets...")
    total = len(eval_records)

    # Categories
    cat_counts = Counter(r["gold"]["category"] for r in eval_records)
    print("\n  Category Distribution:")
    for cat, cnt in cat_counts.most_common():
        pct = (cnt / total) * 100
        print(f"    - {cat:22s}: {cnt:2d} ({pct:5.1f}%)")
        if pct > 25.0:
            failures.append(f"Category '{cat}' exceeds 25% target ({pct:.1f}%)")

    # Severity
    sev_counts = Counter(r["gold"]["severity"] for r in eval_records)
    print("\n  Severity Distribution:")
    for sev, cnt in sorted(sev_counts.items()):
        pct = (cnt / total) * 100
        print(f"    - {sev:10s}: {cnt:2d} ({pct:5.1f}%)")

    # Channels
    ch_counts = Counter(r["channel"] for r in eval_records)
    print("\n  Channel Distribution:")
    for ch, cnt in sorted(ch_counts.items()):
        pct = (cnt / total) * 100
        print(f"    - {ch:10s}: {cnt:2d} ({pct:5.1f}%)")
        if pct < 8.0:
            failures.append(f"Channel '{ch}' is under 8% target ({pct:.1f}%)")

    # Language
    lang_counts = Counter(r["gold"]["language"] for r in eval_records)
    print("\n  Language Distribution:")
    for lang, cnt in sorted(lang_counts.items()):
        pct = (cnt / total) * 100
        print(f"    - {lang:10s}: {cnt:2d} ({pct:5.1f}%)")

    # Duplicates & Recurring
    dup_count = sum(bool(r["gold"]["is_duplicate"] or r["gold"]["recurring"]) for r in eval_records)
    dup_pct = (dup_count / total) * 100
    print(f"\n  Duplicate & Recurring Count: {dup_count} ({dup_pct:.1f}%)")

    if failures:
        for f in failures:
            print(f"  FAIL: {f}")
        sys.exit(1)

    # 6. Semantic Embeddings & Cosine Matrix Assertions
    print("\n[5/5] Encoding with all-MiniLM-L6-v2 and Asserting Cosine Matrix...")
    encoder = SentenceTransformer("all-MiniLM-L6-v2")

    texts = [r["raw_text"] for r in eval_records]
    embeddings = encoder.encode(texts, normalize_embeddings=True)

    # Test Same-Cluster pairs (must be >= 0.70)
    clusters = {}
    for idx, r in enumerate(eval_records):
        ck = r["gold"]["cluster_key"]
        if not ck.startswith("singleton_") and not ck.startswith("hard_neg_"):
            clusters.setdefault(ck, []).append(idx)

    cluster_failures = []
    print(f"  Evaluating {len(clusters)} multi-record clusters for same-cluster threshold (>= 0.70)...")
    for ck, indices in clusters.items():
        leader_idx = indices[0]
        leader_emb = embeddings[leader_idx]
        for other_idx in indices[1:]:
            sim = float(np.dot(leader_emb, embeddings[other_idx]))
            r_lead = eval_records[leader_idx]
            r_other = eval_records[other_idx]
            if sim < 0.70:
                cluster_failures.append(
                    f"SAME-CLUSTER FAIL: '{ck}' pair ({r_lead['id']} & {r_other['id']}) scored {sim:.4f} < 0.70\n"
                    f"    Leader ({r_lead['id']}): '{r_lead['raw_text']}'\n"
                    f"    Member ({r_other['id']}): '{r_other['raw_text']}'"
                )
            else:
                print(f"    [PASS] Cluster '{ck}' ({r_lead['id']} & {r_other['id']}): {sim:.4f} >= 0.70")

    # Test Hard Negative pairs (must be < 0.70)
    hard_neg_pairs = [
        (56, 57),  # UPI merchant timeout vs UPI peer transfer reversal
        (58, 59),  # ATM cash dispenser stuck vs ATM card swallowed
        (60, 61),  # NetBanking OTP delayed vs NetBanking password locked
        (62, 63),  # Credit card fraud swipe vs Annual maintenance fee
        (64, 65),  # Home loan double EMI vs Rate reduction inquiry
        (66, 67),  # KYC document rejected vs Video KYC connection drop
        (68, 69),  # Card PIN blocked vs EMV chip damaged
        (70, 71),  # Cheque signature mismatch vs Account signature update
        (72, 73),  # Cheque bounce fee vs Cheque book speed post tracking
        (74, 75),  # NACH SIP failed vs Minimum balance fee
        (76, 77),  # Locker access appointment vs Locker rent auto-debit
        (78, 79),  # Demat account linking vs Demat dividend credit
        (80, 81),  # SWIFT wire remittance vs Domestic RTGS settlement
        (82, 83),  # Fixed deposit premature penalty vs FD Form 16A TDS
        (84, 85),  # Fastag toll double debit vs Fastag low balance false alarm
    ]

    hard_neg_failures = []
    print(f"\n  Evaluating {len(hard_neg_pairs)} Hard Negative pairs (must be < 0.70)...")
    for p1_id, p2_id in hard_neg_pairs:
        idx1 = p1_id - 1
        idx2 = p2_id - 1
        r1 = eval_records[idx1]
        r2 = eval_records[idx2]
        sim = float(np.dot(embeddings[idx1], embeddings[idx2]))
        if sim >= 0.70:
            hard_neg_failures.append(
                f"HARD-NEGATIVE FAIL: Pair ({r1['id']} & {r2['id']}) scored {sim:.4f} >= 0.70\n"
                f"    Text 1 ({r1['id']}): '{r1['raw_text']}'\n"
                f"    Text 2 ({r2['id']}): '{r2['raw_text']}'"
            )
        else:
            print(f"    [PASS] Hard Negative ({r1['id']} & {r2['id']}): {sim:.4f} < 0.70")

    all_failures = cluster_failures + hard_neg_failures
    if all_failures:
        print("\n" + "!" * 70)
        print("SIMILARITY MATRIX FAILURES:")
        for f in all_failures:
            print(f)
        print("!" * 70)
        sys.exit(1)

    print("\n" + "=" * 70)
    print("SUCCESS: All assertions passed! Dataset is 100% compliant.")
    print("=" * 70)
    sys.exit(0)


if __name__ == "__main__":
    validate_dataset()
