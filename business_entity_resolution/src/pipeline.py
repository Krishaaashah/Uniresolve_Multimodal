"""Ultra-Fast End-to-End Execution Pipeline."""
import argparse
import csv
import io
import json
import os
import sys
import time
import zipfile
from collections import defaultdict
from pathlib import Path

from src import config
from src.preprocessor import build_record
from src.blocking import FastMultiPassBlocking
from src.features import compute_fast_similarity_score
from src.postprocessor import (
    compute_macro_f05,
    optimize_f05_threshold,
    enforce_target_uniqueness
)

def run_evaluation(zip_path: str, sample_size: int = 25000):
    print(f"=== Running High-Speed Evaluation Pipeline on {sample_size:,} S1 Entities ===")
    t0 = time.time()
    
    # 1. Load Ground Truth
    gt = {}
    needed_targets = set()
    s1_count = 0
    with zipfile.ZipFile(zip_path, 'r') as z:
        with z.open('student_resource/dataset/train/train_ground_truth.tsv') as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding='utf-8', errors='replace'), delimiter='\t')
            next(reader)
            for row in reader:
                if not row: continue
                s1_count += 1
                if s1_count <= sample_size:
                    s1_id = row[0]
                    targets = [t.strip() for t in row[1].split(",") if t.strip()] if len(row) > 1 else []
                    gt[s1_id] = targets
                    for t in targets:
                        needed_targets.add(t)
                        
    print(f"Loaded ground truth for {len(gt):,} S1 queries ({sum(len(v) for v in gt.values()):,} true links).")
    
    # 2. Build Target Blocking Index
    blocker = FastMultiPassBlocking()
    
    def load_targets(filename, max_bg=50000):
        bg_cnt = 0
        with zipfile.ZipFile(zip_path, 'r') as z:
            with z.open(filename) as f:
                reader = csv.reader(io.TextIOWrapper(f, encoding='utf-8', errors='replace'), delimiter='\t')
                next(reader)
                for idx, row in enumerate(reader):
                    if not row: continue
                    eid = row[0]
                    if eid in needed_targets or (bg_cnt < max_bg and idx % 20 == 0):
                        rec = build_record(
                            eid,
                            row[1] if len(row) > 1 else "",
                            row[2] if len(row) > 2 else "",
                            row[3] if len(row) > 3 else ""
                        )
                        blocker.add_target_record(rec)
                        if eid not in needed_targets:
                            bg_cnt += 1

    print("Indexing target databases (S2 & S3)...")
    load_targets('student_resource/dataset/train/train_source2.tsv', max_bg=50000)
    load_targets('student_resource/dataset/train/train_source3.tsv', max_bg=50000)
    print(f"Indexed {len(blocker.records):,} target records.")
    
    # 3. Load S1 query records
    s1_records = {}
    with zipfile.ZipFile(zip_path, 'r') as z:
        with z.open('student_resource/dataset/train/train_source1.tsv') as f:
            reader = csv.reader(io.TextIOWrapper(f, encoding='utf-8', errors='replace'), delimiter='\t')
            next(reader)
            for row in reader:
                if not row: continue
                if row[0] in gt:
                    rec = build_record(
                        row[0],
                        row[1] if len(row) > 1 else "",
                        row[2] if len(row) > 2 else "",
                        row[3] if len(row) > 3 else ""
                    )
                    s1_records[row[0]] = rec
                    
    print(f"Loaded {len(s1_records):,} pre-computed S1 query records.")
    
    # 4. Fast Scoring Loop
    print("Scoring candidates...")
    t_score = time.time()
    pair_scores = []
    
    for s1_id, r1 in s1_records.items():
        cands = blocker.query_candidates(r1)
        for tid in cands:
            r2 = blocker.records[tid]
            score = compute_fast_similarity_score(r1, r2)
            pair_scores.append((s1_id, tid, score))
            
    print(f"Scored {len(pair_scores):,} pairs in {time.time() - t_score:.2f}s!")
    
    # 5. Optimize Threshold & Enforce Target Uniqueness
    best_th, best_raw_f05 = optimize_f05_threshold(pair_scores, gt)
    print(f"Optimal raw score threshold: {best_th:.2f} (Macro F0.5 = {best_raw_f05:.4f})")
    
    final_preds = enforce_target_uniqueness(pair_scores, best_th)
    final_f05, final_p, final_r = compute_macro_f05(gt, final_preds)
    
    elapsed = round(time.time() - t0, 2)
    print(f"\n==========================================")
    print(f"FINAL VALIDATION MACRO F0.5 = {final_f05:.4f}")
    print(f"Average Precision = {final_p:.4f} | Average Recall = {final_r:.4f}")
    print(f"Completed in {elapsed}s")
    print(f"==========================================\n")
    return final_f05

def run_prediction_and_export(zip_path: str, output_dir: str = None, threshold: float = config.DEFAULT_F05_THRESHOLD):
    if output_dir is None:
        output_dir = str(config.OUTPUT_DIR)
    os.makedirs(output_dir, exist_ok=True)
    
    matching_path = os.path.join(output_dir, 'matching_results.tsv')
    candidate_path = os.path.join(output_dir, 'candidate_pairs.tsv')
    
    print(f"=== Starting High-Speed Full Test Inference Pipeline ===")
    t0 = time.time()
    
    # Index test targets
    blocker = FastMultiPassBlocking()
    
    def index_test_file(filename):
        print(f"Indexing {filename}...")
        t_f = time.time()
        with zipfile.ZipFile(zip_path, 'r') as z:
            with z.open(filename) as f:
                reader = csv.reader(io.TextIOWrapper(f, encoding='utf-8', errors='replace'), delimiter='\t')
                next(reader)
                for row in reader:
                    if not row: continue
                    rec = build_record(
                        row[0],
                        row[1] if len(row) > 1 else "",
                        row[2] if len(row) > 2 else "",
                        row[3] if len(row) > 3 else ""
                    )
                    blocker.add_target_record(rec)
        print(f"Indexed in {time.time() - t_f:.2f}s. Total target pool: {len(blocker.records):,}")
        
    index_test_file('student_resource/dataset/test/test_source2.tsv')
    index_test_file('student_resource/dataset/test/test_source3.tsv')
    
    print(f"Scoring test Source 1 queries & exporting output files...")
    t_inf = time.time()
    
    with open(matching_path, 'w', encoding='utf-8', newline='') as f_match, \
         open(candidate_path, 'w', encoding='utf-8', newline='') as f_cand:
         
        w_match = csv.writer(f_match, delimiter='\t')
        w_cand = csv.writer(f_cand, delimiter='\t')
        
        w_match.writerow(['source1_entity_id', 'matched_entity_ids'])
        w_cand.writerow(['source1_entity_id', 'candidate_entity_ids'])
        
        with zipfile.ZipFile(zip_path, 'r') as z:
            with z.open('student_resource/dataset/test/test_source1.tsv') as f_s1:
                reader = csv.reader(io.TextIOWrapper(f_s1, encoding='utf-8', errors='replace'), delimiter='\t')
                next(reader)
                
                s1_count = 0
                for row in reader:
                    if not row: continue
                    s1_count += 1
                    r1 = build_record(
                        row[0],
                        row[1] if len(row) > 1 else "",
                        row[2] if len(row) > 2 else "",
                        row[3] if len(row) > 3 else ""
                    )
                    
                    cands = blocker.query_candidates(r1)
                    w_cand.writerow([r1['id'], ",".join(cands)])
                    
                    # Score candidates
                    matched_ids = []
                    for tid in cands:
                        r2 = blocker.records.get(tid)
                        if not r2: continue
                        score = compute_fast_similarity_score(r1, r2)
                        if score >= threshold:
                            matched_ids.append(tid)
                            
                    w_match.writerow([r1['id'], ",".join(matched_ids)])
                    
                    if s1_count % 200000 == 0:
                        print(f"  Processed {s1_count:,} / 1,732,544 test entities ({time.time() - t_inf:.1f}s)...")
                        
    print(f"\nTest inference complete in {time.time() - t0:.2f}s! Total S1 processed: {s1_count:,}")
    print(f"Generated: {matching_path}")
    print(f"Generated: {candidate_path}")

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description="Business Entity Resolution End-to-End Pipeline")
    parser.add_argument('--mode', choices=['eval', 'predict'], default='eval', help="Pipeline execution mode")
    parser.add_argument('--zip-path', default=str(config.ZIP_PATH), help="Path to student_resource.zip")
    parser.add_argument('--sample-size', type=int, default=25000, help="S1 sample size for evaluation")
    parser.add_argument('--threshold', type=float, default=config.DEFAULT_F05_THRESHOLD, help="Prediction threshold")
    parser.add_argument('--output-dir', default=str(config.OUTPUT_DIR), help="Output directory for predictions")
    
    args = parser.parse_args()
    if args.mode == 'eval':
        run_evaluation(args.zip_path, args.sample_size)
    elif args.mode == 'predict':
        run_prediction_and_export(args.zip_path, args.output_dir, args.threshold)
