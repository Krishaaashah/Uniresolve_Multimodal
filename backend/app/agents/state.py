from typing import TypedDict, Optional, List, Dict, Any

class RedressalState(TypedDict):
    complaint_text: str
    customer_id: Optional[str]
    transaction_ref: Optional[str]
    amount: Optional[float]
    category: Optional[str]
    severity: Optional[str]
    entities: Dict[str, Any]
    cbs_verdict: Optional[str]        # verified, unverified, no_customer
    matched_txn: Optional[Dict[str, Any]]
    sla_status: Optional[str]         # within_sla, approaching_breach, breached
    sla_deadline: Optional[str]       # ISO timestamp
    draft: Optional[str]
    agent_trace: List[Dict[str, Any]]
    needs_human: bool
    needs_info: bool
    detected_language: str
    missing_fields_question: Optional[str]
    priority_score: int
    linked_incident: Optional[str]
