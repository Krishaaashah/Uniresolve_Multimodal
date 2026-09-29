"""Instantaneous Pairwise Similarity Computation via Pre-computed Sets."""
from typing import Dict, Any

def compute_fast_similarity_score(r1: Dict[str, Any], r2: Dict[str, Any]) -> float:
    """Compute composite similarity score in < 1 microsecond using set intersections."""
    # Address Overlap
    a1_tok, a2_tok = r1['addr_tokens'], r2['addr_tokens']
    if a1_tok and a2_tok:
        a_inter = len(a1_tok.intersection(a2_tok))
        a_over = a_inter / min(len(a1_tok), len(a2_tok))
    else:
        a_over = 0.0
        
    # Address 3-Gram Jaccard
    a1_ng, a2_ng = r1['addr_ngrams'], r2['addr_ngrams']
    if a1_ng and a2_ng:
        a_ng_inter = len(a1_ng.intersection(a2_ng))
        a_ng_jacc = a_ng_inter / (len(a1_ng) + len(a2_ng) - a_ng_inter)
    else:
        a_ng_jacc = 0.0
        
    # Name Overlap
    n1_tok, n2_tok = r1['name_tokens'], r2['name_tokens']
    if n1_tok and n2_tok:
        n_inter = len(n1_tok.intersection(n2_tok))
        n_over = n_inter / min(len(n1_tok), len(n2_tok))
    else:
        n_over = 0.0
        
    # Name 3-Gram Jaccard
    n1_ng, n2_ng = r1['name_ngrams'], r2['name_ngrams']
    if n1_ng and n2_ng:
        n_ng_inter = len(n1_ng.intersection(n2_ng))
        n_ng_jacc = n_ng_inter / (len(n1_ng) + len(n2_ng) - n_ng_inter)
    else:
        n_ng_jacc = 0.0
        
    # Address Number Match
    nums1, nums2 = r1['nums'], r2['nums']
    num_match = 1.0 if (nums1 and nums2 and len(nums1.intersection(nums2)) > 0) else 0.0
    
    # Linear composite weighted formula optimized for F0.5
    score = (
        0.35 * a_over +
        0.20 * a_ng_jacc +
        0.25 * n_over +
        0.15 * n_ng_jacc +
        0.05 * num_match
    )
    return score
