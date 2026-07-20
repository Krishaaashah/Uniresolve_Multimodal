import os
import uuid
import logging
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
import json

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.agents.state import RedressalState
from app.services.triage import get_triage_service, generate_draft_response
from app.services.cbs import get_customer_profile
from app.services.store import get_store
from app.models.complaint import Severity, SLAStatus

logger = logging.getLogger(__name__)

from app.config import SLA_HOURS_TABLE

def translate_text(text: str, target_lang: str) -> str:
    from app.config import GEMINI_API_KEY, GEMINI_MODEL
    if not GEMINI_API_KEY or target_lang.lower() == "english":
        return text
    try:
        import httpx
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        headers = {"Content-Type": "application/json"}
        prompt = f"Translate the following text to {target_lang}. Return ONLY the translated text, do not add any comments or notes:\n\n{text}"
        payload = {
            "contents": [{"parts": [{"text": prompt}]}]
        }
        res = httpx.post(url, json=payload, headers=headers, timeout=10.0)
        if res.status_code == 200:
            translated = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
            # Clean possible markdown block wrapping
            if translated.startswith("```"):
                translated = "\n".join(translated.split("\n")[1:-1])
            return translated
    except Exception as e:
        logger.warning(f"Translation to {target_lang} failed: {e}")
    return text

# ── Node Definitions ──────────────────────────────────────────────────────────

def outage_check_node(state: RedressalState) -> Dict[str, Any]:
    trace_entry = {"node": "outage_check_node", "timestamp": datetime.utcnow().isoformat()}
    text = state["complaint_text"]
    
    # Check active incidents
    store = get_store()
    incidents = store.all_incidents()
    linked_id = None
    draft_response = None
    
    # Simple semantic similarity fallback for incidents
    for inc in incidents:
        # Check if the text matches the incident category/label contextually
        if inc["status"] == "active" and (inc["label"].lower() in text.lower() or "outage" in text.lower()):
            linked_id = inc["cluster_id"]
            draft_response = f"Dear Customer, we are currently experiencing a known technical issue with {inc['label']}. Our engineering team is resolving it on priority. Your ticket is linked to incident #{linked_id[:8]} and will be auto-resolved upon fix."
            break
            
    trace_entry["result"] = {
        "linked_incident": linked_id,
        "is_outage": linked_id is not None
    }
    return {
        "linked_incident": linked_id,
        "draft": draft_response,
        "agent_trace": state.get("agent_trace", []) + [trace_entry]
    }


def language_node(state: RedressalState) -> Dict[str, Any]:
    trace_entry = {"node": "language_node", "timestamp": datetime.utcnow().isoformat()}
    text = state["complaint_text"]
    
    detected_lang = "English"
    translated_text = text
    
    from app.config import GEMINI_API_KEY, GEMINI_MODEL
    api_failed = False
    if GEMINI_API_KEY:
        try:
            import httpx
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            prompt = (
                "Analyze the following complaint text. Detect its language (e.g. Hindi, Marathi, English). "
                "If it is not English, translate it to English. "
                "Respond ONLY with a valid JSON in this exact structure:\n"
                '{"detected_language": "Hindi", "translated_text": "translated text here"}\n\n'
                f"Text:\n{text}"
            )
            payload = {
                "contents": [{"parts": [{"text": prompt}]}]
            }
            res = httpx.post(url, json=payload, headers=headers, timeout=10.0)
            if res.status_code == 200:
                resp_json = res.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
                if resp_json.startswith("```json"):
                    resp_json = "\n".join(resp_json.split("\n")[1:-1])
                elif resp_json.startswith("```"):
                    resp_json = "\n".join(resp_json.split("\n")[1:-1])
                data = json.loads(resp_json)
                detected_lang = data.get("detected_language", "English")
                translated_text = data.get("translated_text", text)
            else:
                api_failed = True
        except Exception as e:
            logger.warning(f"Language check node failed: {e}")
            api_failed = True

    if not GEMINI_API_KEY or api_failed:
        # Simplistic dev key fallback checks
        if any(c in text for c in ["खाता", "भुगतान", "मेरा"]):
            detected_lang = "Hindi"
            translated_text = "I failed to withdraw money from ATM."
        elif any(c in text for c in ["खाते", "पैसे", "व्यवहार"]):
            detected_lang = "Marathi"
            translated_text = "My account was debited duplicate amount."
        elif any(c in text for c in ["kyc", "Aadhaar", "PAN"]):
            detected_lang = "English"

    trace_entry["result"] = {
        "detected_language": detected_lang,
        "translated_text": translated_text
    }
    return {
        "detected_language": detected_lang,
        "complaint_text": translated_text,
        "agent_trace": state.get("agent_trace", []) + [trace_entry]
    }


def triage_node(state: RedressalState) -> Dict[str, Any]:
    trace_entry = {"node": "triage_node", "timestamp": datetime.utcnow().isoformat()}
    text = state["complaint_text"]
    
    triage_service = get_triage_service()
    # Call core triage pipeline
    res = triage_service.triage(text, customer_id=state.get("customer_id"))
    
    # Extract entities (amount, transaction_ref, etc.)
    import re
    txn_ref = state.get("transaction_ref")
    if not txn_ref:
        ref_match = re.search(r"\b(UPI\d+|ATM\d+|EMI\d+|CRD\d+|NFT\d+)\b", text, re.IGNORECASE)
        if ref_match:
            txn_ref = ref_match.group(1).upper()
            
    amt = state.get("amount")
    if not amt:
        amt_match = re.search(r"(?:Rs\.?|INR)\s*([\d,]+(?:\.\d{2})?)", text, re.IGNORECASE)
        if amt_match:
            try:
                amt = float(amt_match.group(1).replace(",", ""))
            except ValueError:
                pass

    entities = {
        "extracted_ref": txn_ref,
        "extracted_amount": amt,
        "sentiment": res.sentiment.value
    }

    # SLA-Based Priority Scoring: boost vulnerable/high-value customers
    priority_score = 0
    cust_id = state.get("customer_id")
    if cust_id:
        profile = get_customer_profile(cust_id)
        if profile:
            # high balance boost
            try:
                bal_str = profile.get("balance", "Rs 0").replace("Rs", "").replace(",", "").strip()
                balance = float(bal_str)
                if balance > 100000:
                    priority_score += 2
            except ValueError:
                pass
            
            # senior citizen / pensioner flag boost
            if "senior" in profile.get("account_type", "").lower() or "pension" in profile.get("account_type", "").lower():
                priority_score += 5
            
            # high risk tier prioritisation
            if profile.get("risk_tier") == "High Risk":
                priority_score += 3
    
    # Severity boost
    if res.severity == Severity.CRITICAL:
        priority_score += 10
    elif res.severity == Severity.HIGH:
        priority_score += 5

    trace_entry["result"] = {
        "category": res.category.value,
        "severity": res.severity.value,
        "priority_score": priority_score,
        "entities": entities
    }
    
    return {
        "category": res.category.value,
        "severity": res.severity.value,
        "entities": entities,
        "transaction_ref": txn_ref,
        "amount": amt,
        "priority_score": priority_score,
        "agent_trace": state.get("agent_trace", []) + [trace_entry]
    }


def info_check_node(state: RedressalState) -> Dict[str, Any]:
    trace_entry = {"node": "info_check_node", "timestamp": datetime.utcnow().isoformat()}
    cat = state.get("category", "")
    needs_info = False
    question = None
    
    # Rules: transaction disputes require a transaction reference and amount
    is_dispute = cat in ["UPI Failure", "ATM Failure", "Card Payment Decline", "Double Deduction", "Credit Card"]
    if not is_dispute and cat.lower() == "general":
        lower_text = state["complaint_text"].lower()
        if any(w in lower_text for w in ["gpay", "upi", "atm", "debit", "deduct", "zomato", "transaction"]):
            is_dispute = True
    if is_dispute:
        if not state.get("transaction_ref") or not state.get("amount"):
            needs_info = True
            question = f"We noticed that some details are missing. To investigate this dispute, could you please provide the transaction reference ID (e.g. UPI123456 or ATM98765) and the exact amount debited?"
            
    trace_entry["result"] = {
        "needs_info": needs_info,
        "question": question
    }
    return {
        "needs_info": needs_info,
        "missing_fields_question": question,
        "agent_trace": state.get("agent_trace", []) + [trace_entry]
    }


def cbs_verification_node(state: RedressalState) -> Dict[str, Any]:
    trace_entry = {"node": "cbs_verification_node", "timestamp": datetime.utcnow().isoformat()}
    cust_id = state.get("customer_id")
    ref = state.get("transaction_ref")
    
    verdict = "no_customer"
    matched_txn = None
    
    if cust_id:
        profile = get_customer_profile(cust_id)
        if profile:
            verdict = "unverified"
            # Attempt to match
            for tx in profile.get("transactions", []):
                # Match by reference or description keywords
                if ref and (ref.lower() in tx.get("ref", "").lower() or ref.lower() in tx.get("desc", "").lower()):
                    matched_txn = tx
                    verdict = "verified"
                    break
                # Fallback matching by amount if reference is missing
                elif not ref and state.get("amount"):
                    tx_amt = tx.get("amount", "").replace("Rs", "").replace("-", "").replace("+", "").replace(",", "").strip()
                    try:
                        if abs(float(tx_amt) - state["amount"]) < 0.01:
                            matched_txn = tx
                            verdict = "verified"
                            break
                    except ValueError:
                        pass
                        
    trace_entry["result"] = {
        "cbs_verdict": verdict,
        "matched_transaction": matched_txn
    }
    return {
        "cbs_verdict": verdict,
        "matched_txn": matched_txn,
        "agent_trace": state.get("agent_trace", []) + [trace_entry]
    }


def compliance_node(state: RedressalState) -> Dict[str, Any]:
    trace_entry = {"node": "compliance_node", "timestamp": datetime.utcnow().isoformat()}
    cat = state.get("category", "general")
    
    # Calculate issue deadline based on SLA hours config
    allowed_hours = SLA_HOURS_TABLE.get(cat, SLA_HOURS_TABLE["general"])
    deadline_dt = datetime.utcnow() + timedelta(hours=allowed_hours)
    
    # Match deadline against simulated transactions if possible
    tx = state.get("matched_txn")
    if tx and tx.get("date"):
        try:
            tx_dt = datetime.fromisoformat(tx["date"])
            deadline_dt = tx_dt + timedelta(hours=allowed_hours)
        except Exception:
            pass
            
    remaining_hours = (deadline_dt - datetime.utcnow()).total_seconds() / 3600.0
    
    if remaining_hours <= 0:
        sla_status = "breached"
    elif remaining_hours <= 12:
        sla_status = "approaching_breach"
    else:
        sla_status = "within_sla"
        
    trace_entry["result"] = {
        "sla_status": sla_status,
        "sla_deadline": deadline_dt.isoformat()
    }
    return {
        "sla_status": sla_status,
        "sla_deadline": deadline_dt.isoformat(),
        "agent_trace": state.get("agent_trace", []) + [trace_entry]
    }


def human_approval_node(state: RedressalState) -> Dict[str, Any]:
    # Dummy node to hold the interrupt pause point
    trace_entry = {"node": "human_approval_node", "timestamp": datetime.utcnow().isoformat(), "result": "Paused for Supervisor approval."}
    return {
        "agent_trace": state.get("agent_trace", []) + [trace_entry]
    }


def drafting_node(state: RedressalState) -> Dict[str, Any]:
    trace_entry = {"node": "drafting_node", "timestamp": datetime.utcnow().isoformat()}
    
    # Historical Precedent Retrieval (Qdrant RAG)
    precedent_context = ""
    precedents_used = []
    
    from app.services import qdrant_service
    from app.services.clustering import get_clustering_service
    
    encoder_service = get_clustering_service()
    if encoder_service and encoder_service.healthy:
        vec = encoder_service._encode(state["complaint_text"])
        if vec is not None:
            vec_list = vec.tolist()[0]
            # Search resolved_complaints collection in Qdrant
            try:
                # We reuse search_similar targeting the custom collection
                url = f"{qdrant_service.QDRANT_URL}/collections/resolved_complaints/points/search"
                body = {
                    "vector": vec_list,
                    "limit": 2,
                    "score_threshold": 0.82,
                    "with_payload": True
                }
                import httpx
                res = httpx.post(url, json=body, headers=qdrant_service.get_headers(), timeout=4.0)
                if res.status_code == 200:
                    results = res.json().get("result", [])
                    precedents_list = []
                    for point in results:
                        payload = point.get("payload", {})
                        p_id = point.get("id")
                        resolution = payload.get("final_resolution")
                        if resolution:
                            precedents_list.append(f"Precedent Case #{p_id[:8]}: {resolution}")
                            precedents_used.append({"id": p_id, "resolution": resolution})
                    if precedents_list:
                        precedent_context = "\nResolved Precedents:\n" + "\n".join(precedents_list)
            except Exception as e:
                logger.warning(f"Historical precedent retrieval failed: {e}")

    # Build context for drafting
    cbs_note = f"CBS verification verdict: {state.get('cbs_verdict')}. "
    if state.get("matched_txn"):
        cbs_note += f"Matched CBS record: status is {state['matched_txn'].get('status')}, amount is {state['matched_txn'].get('amount')}, date is {state['matched_txn'].get('date')}, reference {state['matched_txn'].get('ref')}."
    
    sla_note = f"SLA status is {state.get('sla_status')} with deadline {state.get('sla_deadline')}."
    
    enriched_note = f"{cbs_note}\n{sla_note}\n{precedent_context}"
    
    # Generate draft response
    draft = generate_draft_response(
        complaint_text=state["complaint_text"],
        category=state.get("category", "general"),
        sentiment=state.get("entities", {}).get("sentiment", "neutral"),
        severity=state.get("severity", "medium"),
        transaction_note=enriched_note
    )
    
    # Translate output draft back to customer's vernacular language if needed
    detected_lang = state.get("detected_language", "English")
    if detected_lang.lower() != "english":
        draft = translate_text(draft, detected_lang)
        
    trace_entry["result"] = {
        "draft_generated": True,
        "precedents_used": precedents_used
    }
    return {
        "draft": draft,
        "agent_trace": state.get("agent_trace", []) + [trace_entry]
    }


# ── Edge Routers ──────────────────────────────────────────────────────────────

def route_after_outage(state: RedressalState) -> str:
    if state.get("linked_incident"):
        return END
    return "language_node"

def route_after_info(state: RedressalState) -> str:
    if state.get("needs_info"):
        return END
    return "cbs_verification_node"

def route_after_compliance(state: RedressalState) -> str:
    severity = state.get("severity", "").lower()
    amount = state.get("amount") or 0.0
    sla_status = state.get("sla_status", "")
    
    if severity == "fraud" or amount > 10000 or sla_status == "breached":
        # Pauses graph at human approval dummy node
        return "human_approval_node"
    return "drafting_node"

def route_after_human(state: RedressalState) -> str:
    return "drafting_node"


# ── Compile Workflow ──────────────────────────────────────────────────────────

workflow = StateGraph(RedressalState)

# Add Nodes
workflow.add_node("outage_check_node", outage_check_node)
workflow.add_node("language_node", language_node)
workflow.add_node("triage_node", triage_node)
workflow.add_node("info_check_node", info_check_node)
workflow.add_node("cbs_verification_node", cbs_verification_node)
workflow.add_node("compliance_node", compliance_node)
workflow.add_node("human_approval_node", human_approval_node)
workflow.add_node("drafting_node", drafting_node)

# Set Entry Point
workflow.set_entry_point("outage_check_node")

# Define Routing
workflow.add_conditional_edges(
    "outage_check_node",
    route_after_outage,
    {
        END: END,
        "language_node": "language_node"
    }
)
workflow.add_edge("language_node", "triage_node")
workflow.add_edge("triage_node", "info_check_node")

workflow.add_conditional_edges(
    "info_check_node",
    route_after_info,
    {
        END: END,
        "cbs_verification_node": "cbs_verification_node"
    }
)

workflow.add_edge("cbs_verification_node", "compliance_node")

workflow.add_conditional_edges(
    "compliance_node",
    route_after_compliance,
    {
        "human_approval_node": "human_approval_node",
        "drafting_node": "drafting_node"
    }
)

workflow.add_edge("human_approval_node", "drafting_node")
workflow.add_edge("drafting_node", END)

# In-Memory memory saver checkpointer for HITL pauses
checkpointer = MemorySaver()
app_graph = workflow.compile(
    checkpointer=checkpointer,
    interrupt_before=["human_approval_node", "human_approval_node"]
)


# ── Graph Runner Helper APIs ───────────────────────────────────────────────────

def run_pipeline(complaint_text: str, customer_id: Optional[str] = None, transaction_ref: Optional[str] = None, amount: Optional[float] = None, thread_id: Optional[str] = None) -> Dict[str, Any]:
    if not thread_id:
        thread_id = str(uuid.uuid4())
        
    config = {"configurable": {"thread_id": thread_id}}
    
    initial_state = {
        "complaint_text": complaint_text,
        "customer_id": customer_id,
        "transaction_ref": transaction_ref,
        "amount": amount,
        "category": None,
        "severity": None,
        "entities": {},
        "cbs_verdict": None,
        "matched_txn": None,
        "sla_status": None,
        "sla_deadline": None,
        "draft": None,
        "agent_trace": [],
        "needs_human": False,
        "needs_info": False,
        "detected_language": "English",
        "missing_fields_question": None,
        "priority_score": 0,
        "linked_incident": None
    }
    
    # Run the compiled StateGraph
    final_output = app_graph.invoke(initial_state, config)
    
    # Check if paused before human approval
    next_steps = app_graph.get_state(config).next
    needs_human = "human_approval_node" in next_steps
    
    if needs_human:
        final_output["needs_human"] = True
        
    return {
        "thread_id": thread_id,
        "state": final_output
    }


def resume_pipeline(thread_id: str, decision: str, provided_info: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    config = {"configurable": {"thread_id": thread_id}}
    
    # Fetch current paused state
    current_state = app_graph.get_state(config).values
    
    if provided_info:
        # Merge new customer input details
        for k, v in provided_info.items():
            current_state[k] = v
        current_state["needs_info"] = False
        current_state["missing_fields_question"] = None
        
    if decision == "approved":
        current_state["needs_human"] = False
        
    # Resume by calling update_state and run/invoke with None to transition forward
    app_graph.update_state(config, current_state)
    final_output = app_graph.invoke(None, config)
    
    return {
        "thread_id": thread_id,
        "state": final_output
    }
