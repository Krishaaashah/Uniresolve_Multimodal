"""Macro F0.5 Threshold Optimization & 1-to-N Target Uniqueness Enforcement."""
from collections import defaultdict
from typing import Dict, List, Set, Tuple
import numpy as np
from src import config

def compute_macro_f05(
    ground_truth: Dict[str, List[str]],
    predictions: Dict[str, List[str]]
) -> Tuple[float, float, float]:
    """Calculate the exact competition Macro-Averaged F0.5 score across all S1 entities."""
    f05_scores = []
    precisions = []
    recalls = []
    
    for s1_id, true_targets in ground_truth.items():
        true_set = set(true_targets)
        pred_set = set(predictions.get(s1_id, []))
        
        # Singleton logic: 0 matches in ground truth
        if len(true_set) == 0:
            if len(pred_set) == 0:
                f05_scores.append(1.0)
            else:
                f05_scores.append(0.0)
        else:
            if len(pred_set) == 0:
                f05_scores.append(0.0)
            else:
                tp = len(true_set.intersection(pred_set))
                p = tp / len(pred_set)
                r = tp / len(true_set)
                precisions.append(p)
                recalls.append(r)
                denom = (0.25 * p + r)
                if denom > 0:
                    f05 = (1.25 * p * r) / denom
                else:
                    f05 = 0.0
                f05_scores.append(f05)
                
    macro_f05 = float(np.mean(f05_scores)) if f05_scores else 0.0
    avg_prec = float(np.mean(precisions)) if precisions else 0.0
    avg_rec = float(np.mean(recalls)) if recalls else 0.0
    return macro_f05, avg_prec, avg_rec

def optimize_f05_threshold(
    pair_scores: List[Tuple[str, str, float]],
    ground_truth: Dict[str, List[str]],
    thresholds: List[float] = None
) -> Tuple[float, float]:
    """Sweep thresholds to find the optimal decision cutoff for Macro F0.5."""
    if thresholds is None:
        thresholds = [0.15, 0.20, 0.25, 0.28, 0.30, 0.35, 0.40, 0.45, 0.50, 0.60]
        
    best_th = config.DEFAULT_F05_THRESHOLD
    best_score = -1.0
    
    for th in thresholds:
        preds = defaultdict(list)
        for s1_id, tid, score in pair_scores:
            if score >= th:
                preds[s1_id].append(tid)
        score, p, r = compute_macro_f05(ground_truth, preds)
        if score > best_score:
            best_score = score
            best_th = th
            
    return best_th, best_score

def enforce_target_uniqueness(
    pair_scores: List[Tuple[str, str, float]],
    threshold: float
) -> Dict[str, List[str]]:
    """Enforce the global 1-to-N target uniqueness constraint:
    Each target entity S2-* or S3-* is assigned to AT MOST ONE S1-* entity (the highest-scoring S1).
    """
    valid_pairs = [p for p in pair_scores if p[2] >= threshold]
    valid_pairs.sort(key=lambda x: x[2], reverse=True)
    
    assigned_targets = set()
    s1_predictions = defaultdict(list)
    
    for s1_id, tid, score in valid_pairs:
        if tid not in assigned_targets:
            s1_predictions[s1_id].append(tid)
            assigned_targets.add(tid)
            
    return s1_predictions
