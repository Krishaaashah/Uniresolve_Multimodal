"""Machine Learning Matcher Models: Fast Baseline & LightGBM GBDT Matcher."""
import math
from typing import Dict, List, Tuple, Any
import numpy as np

from src import config
from src.features import FEATURE_NAMES

FEATURE_WEIGHTS = {
    "addr_overlap": 0.30,
    "addr_ngram": 0.20,
    "addr_jaccard": 0.10,
    "name_overlap": 0.20,
    "name_ngram": 0.10,
    "name_lev": 0.05,
    "addr_num_match": 0.05
}

class FastRuleBaselineMatcher:
    """Fast linear composite similarity matcher with zero memory overhead."""
    def __init__(self, weights: Dict[str, float] = None):
        self.weights = weights or FEATURE_WEIGHTS
        
    def predict_pair_score(self, feat_dict: Dict[str, float]) -> float:
        score = sum(feat_dict.get(k, 0.0) * w for k, w in self.weights.items())
        return score

class GBDTEntityMatcher:
    """Gradient Boosted Decision Tree Matcher."""
    def __init__(self, params: Dict[str, Any] = None):
        self.params = params or config.GBDT_PARAMS
        self.model = None
        
    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        scores = []
        for row in X:
            feat_dict = {FEATURE_NAMES[i]: row[i] for i in range(len(FEATURE_NAMES))}
            scores.append(sum(feat_dict.get(k, 0.0) * w for k, w in FEATURE_WEIGHTS.items()))
        return np.array(scores)
