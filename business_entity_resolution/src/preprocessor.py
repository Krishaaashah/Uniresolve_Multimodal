"""High-speed text normalization and record representation generator."""
import re
from typing import Dict, List, Set, Tuple, Any

LEGAL_SUFFIXES_PATTERN = re.compile(
    r'\b('
    r'the|a|an|and|of|in|for|'
    r'inc|incorporated|corp|corporation|co|company|llc|ltd|limited|'
    r'pvt\s+ltd|private\s+limited|pvt|llp|gmbh|'
    r'sarl|sa|sas|sasu|eurl|snc|sci|gie|sca|selarl|scp|'
    r'prop|proprietor|m/s|shree|shri|dr|doctor'
    r')\b',
    re.IGNORECASE
)

PUNCTUATION_PATTERN = re.compile(r'[^a-zA-Z0-9\s]')
WHITESPACE_PATTERN = re.compile(r'\s+')
DIGITS_PATTERN = re.compile(r'\b\d+\b')

def normalize_text(text: str) -> str:
    if not text:
        return ""
    t = text.lower()
    t = LEGAL_SUFFIXES_PATTERN.sub(' ', t)
    t = PUNCTUATION_PATTERN.sub(' ', t)
    t = WHITESPACE_PATTERN.sub(' ', t)
    return t.strip()

def normalize_address(text: str) -> str:
    if not text:
        return ""
    t = text.lower()
    t = PUNCTUATION_PATTERN.sub(' ', t)
    t = WHITESPACE_PATTERN.sub(' ', t)
    return t.strip()

def extract_postal_code(text: str, country: str) -> str:
    if not text:
        return ""
    c = (country or "").upper()
    if c == "INDIA":
        m = re.findall(r'\b[1-9][0-9]{5}\b', text)
        return m[0] if m else ""
    elif c in ("US", "FRANCE"):
        m = re.findall(r'\b[0-9]{5}\b', text)
        return m[0] if m else ""
    return ""

def build_record(entity_id: str, name: str, address: str, country: str) -> Dict[str, Any]:
    """Pre-compute all normalized strings, tokens, and n-grams for O(1) set ops."""
    c = (country or "").strip().upper()
    norm_name = normalize_text(name)
    norm_addr = normalize_address(address)
    
    # Tokens
    name_tokens = set(tok for tok in norm_name.split() if len(tok) >= 3 and not tok.isdigit())
    addr_tokens = set(tok for tok in norm_addr.split() if len(tok) >= 2)
    
    # Character 3-grams
    if len(norm_name) < 3:
        name_ngrams = {norm_name} if norm_name else set()
    else:
        name_ngrams = {norm_name[i:i+3] for i in range(len(norm_name) - 2)}
        
    if len(norm_addr) < 3:
        addr_ngrams = {norm_addr} if norm_addr else set()
    else:
        addr_ngrams = {norm_addr[i:i+3] for i in range(len(norm_addr) - 2)}
        
    nums = set(DIGITS_PATTERN.findall(address or ""))
    pin = extract_postal_code(address, c)
    
    return {
        'id': entity_id,
        'name': name,
        'addr': address,
        'country': c,
        'norm_name': norm_name,
        'norm_addr': norm_addr,
        'name_tokens': name_tokens,
        'addr_tokens': addr_tokens,
        'name_ngrams': name_ngrams,
        'addr_ngrams': addr_ngrams,
        'nums': nums,
        'pin': pin
    }
