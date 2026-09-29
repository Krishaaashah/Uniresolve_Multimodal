"""Ultra-Fast Multi-Pass Inverted Index."""
from collections import defaultdict, Counter
from typing import Dict, List, Set, Tuple, Any
from src.preprocessor import build_record
from src import config

class FastMultiPassBlocking:
    def __init__(self, max_doc_freq: int = config.MAX_DOC_FREQ_THRESHOLD):
        self.max_doc_freq = max_doc_freq
        self.idx_prefix3 = defaultdict(list)
        self.idx_token = defaultdict(list)
        self.idx_pin = defaultdict(list)
        self.token_freq = Counter()
        self.records = {}
        
    def add_target_record(self, rec: Dict[str, Any]):
        eid = rec['id']
        c = rec['country']
        norm_name = rec['norm_name']
        pin = rec['pin']
        tokens = rec['name_tokens']
        
        self.records[eid] = rec
        
        # Pass 1: Prefix-3
        if len(norm_name) >= 3:
            self.idx_prefix3[(c, norm_name[:3])].append(eid)
            
        # Pass 2: Informative Tokens
        for tok in tokens:
            self.idx_token[(c, tok)].append(eid)
            self.token_freq[(c, tok)] += 1
            
        # Pass 3: Postal Code / PIN
        if pin:
            self.idx_pin[(c, pin)].append(eid)
            
    def query_candidates(self, q_rec: Dict[str, Any], max_candidates: int = config.MAX_CANDIDATES_PER_ENTITY) -> List[str]:
        c = q_rec['country']
        norm_name = q_rec['norm_name']
        pin = q_rec['pin']
        tokens = q_rec['name_tokens']
        
        cand_score = Counter()
        
        # Pass 1: Prefix-3 (weight: 3)
        if len(norm_name) >= 3:
            for tid in self.idx_prefix3.get((c, norm_name[:3]), []):
                cand_score[tid] += 3
                
        # Pass 2: Informative Tokens (weight: 2)
        for tok in tokens:
            freq = self.token_freq.get((c, tok), 0)
            if 0 < freq <= self.max_doc_freq:
                for tid in self.idx_token.get((c, tok), []):
                    cand_score[tid] += 2
                    
        # Pass 3: PIN (weight: 2)
        if pin:
            for tid in self.idx_pin.get((c, pin), []):
                cand_score[tid] += 2
                
        if not cand_score:
            return []
            
        return [tid for tid, _ in cand_score.most_common(max_candidates)]
