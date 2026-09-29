"""Complaint API routes for UniResolve."""

import csv
import io
import json
import os
import logging
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

logger = logging.getLogger(__name__)

from fastapi import APIRouter, Depends, HTTPException, Query, Request, UploadFile, File, Form
from fastapi.responses import Response, StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.models.complaint import (
    AgentAction,
    Category,
    Channel,
    Complaint,
    ComplaintResponse,
    ComplaintStatus,
    DashboardStats,
    EscalationAction,
    EscalationRecord,
    HistoryMessage,
    MessageAuthor,
    RawComplaintIn,
    RegulatoryReport,
    ReplyMessage,
    Severity,
)
from app.security import check_api_key, get_current_user, require_role
from pydantic import BaseModel
from app.services.clustering import get_clustering_service
from app.services.pii_scrubber import mask_pii
from app.services.store import get_store
from app.services.triage import get_triage_service
from app.config import (
    GEMINI_API_KEY, ANTHROPIC_API_KEY, GEMINI_MODEL, CLAUDE_MODEL, AUDIO_UPLOAD_DIR, TRIAGE_MODE
)

router = APIRouter(prefix="/complaints", tags=["complaints"])
limiter = Limiter(key_func=get_remote_address)
_root_cause_cache: dict[str, tuple[datetime, dict]] = {}
from app.services.llm import _claude_json, _claude_text

class LoginIn(BaseModel):
    username: str
    password: str

@router.post("/auth/login", tags=["auth"])
async def auth_login(payload: LoginIn):
    store = get_store()
    user = store.verify_user(payload.username, payload.password)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password")
    
    from app.security import create_access_token
    token = create_access_token(payload.username, user["role"], user["tenant_id"])
    
    # Audit log
    store.log_audit(payload.username, user["role"], "login")
    
    return {
        "access_token": token,
        "role": user["role"],
        "username": payload.username,
        "tenant_id": user["tenant_id"]
    }

def is_spam_query(text: str) -> bool:
    from app.services.spam_classifier import get_spam_classifier
    return get_spam_classifier().is_spam(text)

@router.post("/ingest", response_model=ComplaintResponse, dependencies=[Depends(check_api_key)])
@limiter.limit("60/minute")
async def ingest_complaint(request: Request, payload: RawComplaintIn):
    store = get_store()
    
    # Process multimodal attachment if present
    if payload.media_file and payload.media_type:
        is_seed = payload.channel_metadata.get("seed") is True
        is_replay = payload.source_ref and payload.source_ref.startswith("replay-")
        if is_seed or is_replay:
            if "voice_note" in payload.media_file or "audio" in payload.media_type:
                media_desc = "[Simulated Audio Transcription]: Yes, hello. I was trying to withdraw 10,000 rupees from the Delhi Airport ATM. The machine failed to dispense cash but debited my account. Please reverse it.\n[Extracted ID: Customer=CUST-30482, Transaction=TXN-30482-F1]"
            else:
                media_desc = "[Simulated Image Analysis]: Visual screenshot of a failed mobile banking app transaction. Customer Aarav Sharma, Account 9102837465, Rs 3,000.00 failed UPI transfer with reference UPI657483.\n[Extracted ID: Customer=CUST-10245, Transaction=TXN-10245-F1]"
        else:
            from app.services.multimodal import process_multimodal_attachment
            media_desc = process_multimodal_attachment(payload.media_file, payload.media_type)

        # Parse extracted IDs from multimodal description
        import re
        match = re.search(r"\[Extracted ID:\s*Customer=([^,\n\]]+),\s*Transaction=([^,\n\]]+)\]", media_desc)
        if match:
            c_val = match.group(1).strip()
            t_val = match.group(2).strip()
            if not payload.customer_id and c_val != "None":
                payload.customer_id = c_val
            if not payload.transaction_id and t_val != "None":
                payload.transaction_id = t_val

        if payload.raw_text:
            payload.raw_text = f"{payload.raw_text}\n\n[Media Attachment Analysis ({payload.media_type})]:\n{media_desc}"
        else:
            payload.raw_text = media_desc

    masked_text, masked_fields = mask_pii(payload.raw_text)

    is_seed = payload.channel_metadata.get("seed") is True
    is_replay = payload.source_ref and payload.source_ref.startswith("replay-")

    # Validate Customer ID presence for manual submissions (transaction_id is optional)
    if not (is_seed or is_replay):
        if not payload.customer_id:
            if payload.media_file:
                raise HTTPException(status_code=422, detail="Customer ID not detected — please enter manually")
            else:
                raise HTTPException(status_code=422, detail="Customer ID is required")

    # Validate Transaction ID belongs to customer
    tx_note = None
    if payload.transaction_id:
        tx = store.get_transaction(payload.transaction_id)
        if not (is_seed or is_replay):
            if not tx:
                raise HTTPException(status_code=422, detail="Unknown Transaction ID")
            if tx.get("customer_id") != payload.customer_id:
                logger.warning(f"Transaction owner mismatch: transaction={payload.transaction_id} (owner={tx.get('customer_id')}), submitted customer_id={payload.customer_id}")
                raise HTTPException(status_code=422, detail="Transaction does not belong to this customer")
        if tx:
            tx_status = tx.get("status")
            tx_date = tx.get("date") or tx.get("created_at") or "unknown date"
            tx_amount = tx.get("amount") or "0"
            if tx_status == "completed":
                tx_note = f"Transaction {payload.transaction_id} was successfully completed on {tx_date}."
            elif tx_status == "refunded":
                tx_note = f"Refund of Rs {tx_amount} was processed on {tx_date} for transaction {payload.transaction_id}."
            elif tx_status == "failed":
                tx_note = f"Transaction {payload.transaction_id} of Rs {tx_amount} failed on {tx_date}."
            elif tx_status == "pending":
                tx_note = f"Transaction {payload.transaction_id} of Rs {tx_amount} is currently pending as of {tx_date}."
            
            if tx_note:
                payload.raw_text = f"{payload.raw_text}\n\n[Transaction Status Context]: {tx_note}"
                masked_text = f"{masked_text}\n\n[Transaction Status Context]: {tx_note}"

    # Route request to LangGraph Multi-Agent pipeline
    from app.agents.graph import run_pipeline
    import re
    amt = None
    amt_match = re.search(r"(?:Rs\.?|INR)\s*([\d,]+(?:\.\d{2})?)", payload.raw_text, re.IGNORECASE)
    if amt_match:
        try:
            amt = float(amt_match.group(1).replace(",", ""))
        except ValueError:
            pass

    pipeline_res = run_pipeline(
        complaint_text=masked_text,
        customer_id=payload.customer_id,
        transaction_ref=payload.transaction_id,
        amount=amt
    )
    
    thread_id = pipeline_res["thread_id"]
    state = pipeline_res["state"]
    
    from app.models.complaint import TriageResult, Sentiment, Severity, SLAStatus
    triage_result = TriageResult(
        category=state.get("category") or "general",
        severity=Severity(state.get("severity") or "medium"),
        sentiment=Sentiment(state.get("entities", {}).get("sentiment") or "neutral"),
        key_issue=(state.get("category") or "General") + " issue detected",
        key_issues=[(state.get("category") or "General") + " issue"],
        suggested_response=state.get("draft") or "",
        confidence=0.90,
        detected_language=state.get("detected_language") or "English",
        severity_reason=f"CBS Verdict: {state.get('cbs_verdict')}. SLA Status: {state.get('sla_status')}"
    )

    received_at = payload.received_at or datetime.utcnow()
    
    complaint = Complaint(
        channel=payload.channel,
        channel_metadata=payload.channel_metadata,
        raw_text=payload.raw_text,
        masked_text=masked_text,
        masked_fields=masked_fields,
        customer_id=payload.customer_id,
        transaction_id=payload.transaction_id,
        source_ref=payload.source_ref,
        received_at=received_at,
        triage=triage_result,
        needs_human=state.get("needs_human", False),
        needs_info=state.get("needs_info", False),
        agent_trace=state.get("agent_trace", []),
        thread_id=thread_id,
        linked_incident=state.get("linked_incident"),
        priority_score=state.get("priority_score", 0),
        detected_language=state.get("detected_language", "English"),
        missing_fields_question=state.get("missing_fields_question")
    )
    
    from app.services.triage import generate_summary
    complaint.summary = generate_summary(masked_text)
    
    if payload.media_file and payload.media_type:
        from app.services.multimodal import save_multimodal_file
        saved_path = save_multimodal_file(complaint.id, payload.media_file, payload.media_type)
        if saved_path:
            if "attachments" not in complaint.channel_metadata:
                complaint.channel_metadata["attachments"] = []
            complaint.channel_metadata["attachments"].append({
                "type": payload.media_type,
                "url": saved_path
            })

    # Historical Messages Setup
    complaint.communication_history.append(
        HistoryMessage(author=MessageAuthor.CUSTOMER, author_name="Customer", content=payload.raw_text, timestamp=received_at)
    )
    
    if state.get("linked_incident"):
        complaint.communication_history.append(
            HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content=f"Intercepted by Systemic Outage Interceptor for Incident #{state['linked_incident'][:8]}")
        )
        complaint.status = ComplaintStatus.PENDING
    elif state.get("needs_info"):
        complaint.communication_history.append(
            HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content=f"Pipeline paused: missing required details for {triage_result.category.value}.")
        )
        complaint.communication_history.append(
            HistoryMessage(author=MessageAuthor.AGENT, author_name="AI Assistant", content=state.get("missing_fields_question"), is_ai_draft=False)
        )
        complaint.status = ComplaintStatus.PENDING
    elif state.get("needs_human"):
        complaint.communication_history.append(
            HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content="Pipeline paused: high severity/risk detected, awaiting Supervisor approval.")
        )
        complaint.status = ComplaintStatus.PENDING
    else:
        complaint.communication_history.extend([
            HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content=f"Auto-triaged: {triage_result.category.value} | {triage_result.severity.value} | {triage_result.sentiment.value}"),
            HistoryMessage(author=MessageAuthor.AGENT, author_name="AI Assistant", content=triage_result.suggested_response, is_ai_draft=True)
        ])

    # Incident cluster mapping checks
    if state.get("linked_incident"):
        from app.models.complaint import DuplicateCluster
        complaint.cluster = DuplicateCluster(
            cluster_id=state["linked_incident"],
            is_duplicate=True,
            duplicate_of=None,
            cluster_size=5,
            systemic_alert=True,
            duplicate_reason="outage_incident"
        )
    else:
        cluster_result = get_clustering_service().check_and_register(
            complaint.id,
            masked_text,
            customer_id=complaint.customer_id,
            transaction_id=complaint.transaction_id
        )
        complaint.cluster = cluster_result
        complaint.recurring = cluster_result.recurring
        complaint.recurring_of = cluster_result.recurring_of

    store.save(complaint)
    
    # Audit log
    store.log_audit("system", "system", "ingest", complaint.id)
    
    # Chained hashes in ledger
    store.log_ledger_event(complaint.id, "created", "customer")
    store.log_ledger_event(complaint.id, "triaged", "system")
    if state.get("cbs_verdict"):
        store.log_ledger_event(complaint.id, f"verified: {state.get('cbs_verdict')}", "system")
        
    return ComplaintResponse(complaint=complaint, message="Complaint ingested and triaged successfully.")


@router.post("/ingest-audio", response_model=ComplaintResponse, dependencies=[Depends(check_api_key)])
@limiter.limit("60/minute")
async def ingest_audio_complaint(
    request: Request,
    audio_file: UploadFile = File(...),
    customer_id: Optional[str] = Form(None),
    transaction_id: Optional[str] = Form(None),
    channel: str = Form("voice"),
    channel_metadata: Optional[str] = Form(None)
):
    """
    Ingests raw audio grievance (.wav, .mp3, .m4a, .webm, .ogg).
    Pipeline: Whisper ASR -> Presidio PII Masking -> Multimodal Fusion (WavLM + FinBERT) -> FAISS/Clustering -> Store.
    """
    import uuid
    import re
    store = get_store()
    c_id = str(uuid.uuid4())
    
    filename = audio_file.filename or "recording.wav"
    ext = os.path.splitext(filename)[1].lower()
    if not ext or ext not in [".wav", ".mp3", ".m4a", ".webm", ".ogg"]:
        ext = ".wav"
        
    audio_filename = f"{c_id}{ext}"
    audio_save_path = os.path.join(AUDIO_UPLOAD_DIR, audio_filename)
    
    # Save audio to disk
    audio_bytes = await audio_file.read()
    with open(audio_save_path, "wb") as f:
        f.write(audio_bytes)
        
    audio_url = f"/assets/uploads/audio/{audio_filename}"

    # 1. Transcribe audio with Whisper ASR
    from ml.asr import transcribe_audio
    raw_transcript = transcribe_audio(audio_save_path)
    if not raw_transcript or not raw_transcript.strip():
        raw_transcript = "Customer voice grievance recorded for banking transaction resolution."

    # 2. Extract spoken customer / transaction ID if not explicitly passed
    if not customer_id:
        cust_match = re.search(r"\b(CUST-[\w-]+)\b", raw_transcript, re.IGNORECASE)
        if cust_match:
            customer_id = cust_match.group(1).upper()
        else:
            cust_num = re.search(r"customer\s+(?:id|number)?\s*(?:is)?\s*(\d{4,8})", raw_transcript, re.IGNORECASE)
            if cust_num:
                customer_id = f"CUST-{cust_num.group(1)}"
            else:
                customer_id = "CUST-99999"

    if not transaction_id:
        txn_match = re.search(r"\b(TXN-[\w-]+|\d{12})\b", raw_transcript, re.IGNORECASE)
        if txn_match:
            transaction_id = txn_match.group(1).upper()

    # 3. PII Scrubbing on transcript before database storage
    masked_text, masked_fields = mask_pii(raw_transcript)

    # 4. Check transaction context
    tx_note = None
    if transaction_id:
        tx = store.get_transaction(transaction_id)
        if tx:
            tx_status = tx.get("status")
            tx_date = tx.get("date") or tx.get("created_at") or "recent date"
            tx_amount = tx.get("amount") or "0"
            tx_note = f"Transaction {transaction_id} (Rs {tx_amount}) is {tx_status} on {tx_date}."
            masked_text += f"\n\n[Transaction Status Context]: {tx_note}"

    # 5. Local Multimodal Triage with WavLM + FinBERT + Gated Fusion
    triage_service = get_triage_service()
    triage_res = triage_service.triage_complaint(
        masked_text=masked_text,
        audio_path=audio_save_path,
        transaction_note=tx_note,
        customer_id=customer_id,
        transaction_id=transaction_id
    )

    # 6. FAISS / Semantic duplicate detection and systemic clustering
    clustering_service = get_clustering_service()
    cluster_res = clustering_service.check_and_register(
        c_id, masked_text, customer_id=customer_id, transaction_id=transaction_id
    )

    # 7. SLA calculation
    from app.models.complaint import compute_sla, compute_rbi_status
    received_at = datetime.utcnow()
    sla_info = compute_sla(received_at, triage_res.severity.value)

    meta_dict = {}
    if channel_metadata:
        try:
            meta_dict = json.loads(channel_metadata) if isinstance(channel_metadata, str) else channel_metadata
        except Exception:
            meta_dict = {}
    meta_dict["audio_ingest"] = True
    meta_dict["audio_filename"] = audio_filename

    complaint = Complaint(
        id=c_id,
        channel=Channel.VOICE,
        channel_metadata=meta_dict,
        raw_text=raw_transcript,
        masked_text=masked_text,
        masked_fields=masked_fields,
        customer_id=customer_id,
        transaction_id=transaction_id,
        received_at=received_at,
        triage=triage_res,
        cluster=cluster_res,
        sla=sla_info,
        sla_status=sla_info.status,
        sla_breached=sla_info.breached,
        rbi_status=compute_rbi_status(received_at),
        urgency_score=triage_res.urgency_score,
        modality_weights=triage_res.modality_weights,
        triage_mode=triage_res.triage_mode,
        transcript=masked_text,
        audio_url=audio_url,
        model_version=triage_res.model_version
    )

    # Summary
    from app.services.triage import generate_summary
    complaint.summary = generate_summary(masked_text)

    # Communication History
    complaint.communication_history.append(
        HistoryMessage(author=MessageAuthor.CUSTOMER, author_name="Customer (Voice Grievance)", content=masked_text, timestamp=received_at)
    )
    complaint.communication_history.append(
        HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content=f"Auto-triaged via {triage_res.triage_mode.upper()} Multimodal Fusion: {triage_res.category} | {triage_res.severity.value} | Urgency: {int((triage_res.urgency_score or 0.5)*100)}%")
    )
    complaint.communication_history.append(
        HistoryMessage(author=MessageAuthor.AGENT, author_name="AI Assistant", content=triage_res.suggested_response, is_ai_draft=True)
    )

    store.save(complaint)
    store.log_audit("system", "system", "ingest_audio", complaint.id)
    store.log_ledger_event(complaint.id, "created", "customer_voice")
    store.log_ledger_event(complaint.id, "triaged_multimodal", "system")

    return ComplaintResponse(
        complaint=complaint,
        message=f"Audio grievance ingested and triaged via {triage_res.triage_mode} multimodal pipeline."
    )




@router.get("/stats", response_model=DashboardStats)
async def get_stats(current_user: dict = Depends(get_current_user)):
    tenant = current_user.get("tenant_id", "Union Bank")
    return get_store().get_stats(tenant_id=tenant)


_cluster_desc_cache = {}

def generate_cluster_description(complaints_in_cluster: list[Complaint]) -> str:
    """Generate a short, specific root-cause line via LLM with a deterministic fallback."""
    if not complaints_in_cluster:
        return "Unknown systemic issue"

    # Get dominant category and key issues
    categories = [str(c.triage.category) for c in complaints_in_cluster if c.triage and c.triage.category]
    key_issues = [c.triage.key_issue for c in complaints_in_cluster if c.triage and c.triage.key_issue]
    
    dominant_category = Counter(categories).most_common(1)[0][0] if categories else "General"
    dominant_key_issue = Counter(key_issues).most_common(1)[0][0] if key_issues else "similar issues reported"
    
    fallback = f"{dominant_category}: {dominant_key_issue}"
    
    if not (GEMINI_API_KEY or ANTHROPIC_API_KEY):
        return fallback

    # Prepare texts to summarize
    texts = "\n".join(f"- {c.masked_text[:150]}" for c in complaints_in_cluster[:5])
    
    prompt = (
        "Identify the single most specific core technical issue / root cause common to these bank complaints. "
        "Be extremely brief and direct (max 8-10 words, e.g. 'Failed fund transfers in mobile banking', 'Unauthorized credit card transactions'). "
        "Do not use generic sentences. Just return the raw short noun phrase."
    )
    
    try:
        desc = _claude_text(prompt, texts, fallback)
        if desc and len(desc) < 100:
            return desc.strip().strip('"').strip("'")
    except Exception as e:
        logger.warning(f"Error generating cluster root cause via LLM: {e}")
        
    return fallback

def get_cached_cluster_description(cluster_id: str, complaints_in_cluster: list[Complaint]) -> str:
    now = datetime.utcnow()
    cached = _cluster_desc_cache.get(cluster_id)
    if cached and now - cached[0] < timedelta(minutes=15):
        return cached[1]
    
    desc = generate_cluster_description(complaints_in_cluster)
    _cluster_desc_cache[cluster_id] = (now, desc)
    return desc


@router.get("/alerts")
async def get_alerts(current_user: dict = Depends(get_current_user)):
    tenant = current_user.get("tenant_id", "Union Bank")
    all_complaints = get_store().all()
    tenant_complaints = [c for c in all_complaints if c.tenant_id == tenant]
    
    # Group tenant complaints by cluster_id
    cluster_groups = defaultdict(list)
    for c in tenant_complaints:
        if c.cluster and c.cluster.cluster_id:
            cluster_groups[c.cluster.cluster_id].append(c)
            
    alerts = []
    for c in tenant_complaints:
        if c.cluster and c.cluster.systemic_alert:
            cl_id = c.cluster.cluster_id
            cluster_size = len(cluster_groups[cl_id])
            
            # Check unique customer count
            unique_customers = {x.customer_id for x in cluster_groups[cl_id] if x.customer_id}
            c.cluster.cluster_size = cluster_size
            c.cluster.systemic_alert = len(unique_customers) >= 5
            
            if c.cluster.systemic_alert:
                desc = get_cached_cluster_description(cl_id, cluster_groups[cl_id])
                c.cluster.cluster_description = desc
                # Avoid duplicate clusters in output list
                if not any(a.cluster.cluster_id == cl_id for a in alerts):
                    alerts.append(c)
                
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/systemic-alerts")
async def get_systemic_alerts(current_user: dict = Depends(get_current_user)):
    store = get_store()
    tenant = current_user.get("tenant_id", "Union Bank")
    complaints = store.all()
    if tenant:
        complaints = [c for c in complaints if c.tenant_id == tenant]

    clusters = defaultdict(list)
    for c in complaints:
        if c.cluster and c.cluster.cluster_id:
            clusters[c.cluster.cluster_id].append(c)

    result = []
    for cl_id, members in clusters.items():
        unique_customers = {m.customer_id for m in members if m.customer_id}
        affected_customers = len(unique_customers)
        if affected_customers >= 5:
            categories = [
                m.triage.category.value if (m.triage and hasattr(m.triage.category, 'value')) else str(m.triage.category)
                for m in members if m.triage
            ]
            dominant_category = Counter(categories).most_common(1)[0][0] if categories else "General"
            
            timestamps = [m.received_at for m in members]
            first_raised = min(timestamps).isoformat() if timestamps else None
            last_raised = max(timestamps).isoformat() if timestamps else None
            
            sample_texts = [m.masked_text for m in members if m.masked_text][:3]
            
            result.append({
                "cluster_id": cl_id,
                "affected_customers": affected_customers,
                "cluster_size": len(members),
                "dominant_category": dominant_category,
                "first_raised": first_raised,
                "last_raised": last_raised,
                "sample_texts": sample_texts,
                "members": [
                    {
                        "id": m.id,
                        "ticket_id": m.ticket_id,
                        "masked_text": m.masked_text[:120] + ("..." if len(m.masked_text) > 120 else "") if m.masked_text else "",
                        "customer_id": m.customer_id,
                        "status": m.status.value if hasattr(m.status, 'value') else str(m.status),
                        "relationship_tag": m.cluster.duplicate_reason if m.cluster else None
                    }
                    for m in members
                ]
            })
            
    result.sort(key=lambda x: (x["affected_customers"], x["cluster_size"]), reverse=True)
    return result


@router.get("/semantic-clusters")
async def get_semantic_clusters(current_user: dict = Depends(get_current_user)):
    store = get_store()
    tenant = current_user.get("tenant_id", "Union Bank")
    complaints = store.all()
    if tenant:
        complaints = [c for c in complaints if c.tenant_id == tenant]

    clusters = defaultdict(list)
    for c in complaints:
        if c.cluster and c.cluster.cluster_id:
            clusters[c.cluster.cluster_id].append(c)

    result = []
    for cl_id, members in clusters.items():
        unique_customers = {m.customer_id for m in members if m.customer_id}
        affected_customers = len(unique_customers)
        
        categories = [
            m.triage.category.value if (m.triage and hasattr(m.triage.category, 'value')) else str(m.triage.category)
            for m in members if m.triage
        ]
        dominant_category = Counter(categories).most_common(1)[0][0] if categories else "General"
        
        timestamps = [m.received_at for m in members]
        first_raised = min(timestamps).isoformat() if timestamps else None
        last_raised = max(timestamps).isoformat() if timestamps else None
        
        sample_texts = [m.masked_text for m in members if m.masked_text][:3]
        
        result.append({
            "cluster_id": cl_id,
            "affected_customers": affected_customers,
            "cluster_size": len(members),
            "dominant_category": dominant_category,
            "first_raised": first_raised,
            "last_raised": last_raised,
            "sample_texts": sample_texts,
            "members": [
                {
                    "id": m.id,
                    "ticket_id": m.ticket_id,
                    "masked_text": m.masked_text[:120] + ("..." if len(m.masked_text) > 120 else "") if m.masked_text else "",
                    "customer_id": m.customer_id,
                    "status": m.status.value if hasattr(m.status, 'value') else str(m.status),
                    "relationship_tag": m.cluster.duplicate_reason if m.cluster else None
                }
                for m in members
            ]
        })
        
    result.sort(key=lambda x: (x["affected_customers"], x["cluster_size"]), reverse=True)
    return result


@router.get("/groups")
async def get_complaint_groups(current_user: dict = Depends(get_current_user)):
    from datetime import timedelta
    store = get_store()
    tenant = current_user.get("tenant_id", "Union Bank")
    complaints = store.all()
    if tenant:
        complaints = [c for c in complaints if c.tenant_id == tenant]

    # Branch 1: Transaction-based exact groups — keyed by (customer_id, transaction_id)
    # Recurring tickets get their OWN group, not folded into the resolved prior group
    exact_map: dict = defaultdict(list)
    # Branch 2: Non-transaction semantic groups — keyed by (customer_id, cluster_id)
    # Only include complaints that were filed within 7 days of each other (sliding window)
    semantic_raw: dict = defaultdict(list)
    singletons = []

    for c in complaints:
        if not c.customer_id:
            singletons.append(c)
            continue

        # A recurring ticket is its own primary — never fold into the old resolved group
        if c.recurring:
            singletons.append(c)
            continue

        if c.transaction_id:
            # Branch 1: deterministic grouping by customer + transaction
            key = (c.customer_id, c.transaction_id)
            exact_map[key].append(c)
        else:
            cluster_id = c.cluster.cluster_id if (c.cluster and c.cluster.cluster_id) else None
            if cluster_id:
                key = (c.customer_id, cluster_id)
                semantic_raw[key].append(c)
            else:
                singletons.append(c)

    groups = []

    # Build Branch 1 groups
    for (cust_id, tx_id), member_tickets in exact_map.items():
        member_tickets.sort(key=lambda x: x.received_at)
        first_raised = member_tickets[0].received_at.isoformat()
        last_raised = member_tickets[-1].received_at.isoformat()
        channels = list(dict.fromkeys(c.channel.value.title() for c in member_tickets))

        if len(member_tickets) > 1:
            reason = "Same customer and same transaction identifier."
        else:
            reason = f"Customer complaint for transaction {tx_id}."

        group_id = f"grp_exact_{cust_id}_{tx_id}"
        groups.append({
            "group_id": group_id,
            "customer_id": cust_id,
            "transaction_id": tx_id,
            "count": len(member_tickets),
            "channels": channels,
            "first_raised": first_raised,
            "last_raised": last_raised,
            "tickets": [
                {
                    "id": c.id,
                    "ticket_id": c.ticket_id,
                    "channel": c.channel.value.title(),
                    "timestamp": c.received_at.isoformat()
                }
                for c in member_tickets
            ],
            "grouping_reason": reason
        })

    # Build Branch 2 groups: apply 7-day chronological sliding window
    for (cust_id, cl_id), member_tickets in semantic_raw.items():
        member_tickets.sort(key=lambda x: x.received_at)
        # Split cluster into windows: if gap between consecutive tickets > 7 days, start a new sub-group
        sub_groups: list[list] = []
        current_window: list = []
        for ticket in member_tickets:
            if not current_window:
                current_window.append(ticket)
            else:
                gap = ticket.received_at - current_window[-1].received_at
                if gap > timedelta(days=7):
                    sub_groups.append(current_window)
                    current_window = [ticket]
                else:
                    current_window.append(ticket)
        if current_window:
            sub_groups.append(current_window)

        for sub_idx, window_tickets in enumerate(sub_groups):
            window_tickets.sort(key=lambda x: x.received_at)
            first_raised = window_tickets[0].received_at.isoformat()
            last_raised = window_tickets[-1].received_at.isoformat()
            channels = list(dict.fromkeys(c.channel.value.title() for c in window_tickets))

            if len(window_tickets) > 1:
                reason = "Same customer reporting a semantically similar issue within a 7-day period."
            else:
                reason = "Customer unique issue (no semantic duplicates found)."

            group_id = f"grp_semantic_{cust_id}_{cl_id}_{sub_idx}"
            groups.append({
                "group_id": group_id,
                "customer_id": cust_id,
                "transaction_id": None,
                "count": len(window_tickets),
                "channels": channels,
                "first_raised": first_raised,
                "last_raised": last_raised,
                "tickets": [
                    {
                        "id": c.id,
                        "ticket_id": c.ticket_id,
                        "channel": c.channel.value.title(),
                        "timestamp": c.received_at.isoformat()
                    }
                    for c in window_tickets
                ],
                "grouping_reason": reason
            })

    # Singletons and recurring tickets (each as their own group)
    for c in singletons:
        recurring_note = ""
        if c.recurring and c.recurring_of:
            recurring_note = f" Recurring — previously resolved as {c.recurring_of}."

        groups.append({
            "group_id": f"grp_single_{c.id}",
            "customer_id": c.customer_id,
            "transaction_id": c.transaction_id,
            "count": 1,
            "channels": [c.channel.value.title()],
            "first_raised": c.received_at.isoformat(),
            "last_raised": c.received_at.isoformat(),
            "tickets": [
                {
                    "id": c.id,
                    "ticket_id": c.ticket_id,
                    "channel": c.channel.value.title(),
                    "timestamp": c.received_at.isoformat()
                }
            ],
            "grouping_reason": ("Recurring issue for same customer (previous ticket resolved)." + recurring_note) if c.recurring else "Single isolated complaint"
        })

    # Sort: multi-ticket groups first, then by most recent
    groups.sort(key=lambda x: (x["count"] > 1, x["last_raised"]), reverse=True)
    return groups


@router.get("/clusters")
async def get_complaint_clusters(current_user: dict = Depends(get_current_user)):
    store = get_store()
    tenant = current_user.get("tenant_id", "Union Bank")
    complaints = store.all()
    if tenant:
        complaints = [c for c in complaints if c.tenant_id == tenant]

    cluster_map = defaultdict(lambda: {
        "complaint_count": 0,
        "customers": set(),
        "severity_breakdown": defaultdict(int)
    })

    from app.services.triage import normalize_category
    for c in complaints:
        category_str = "General"
        if hasattr(c, "triage") and c.triage and getattr(c.triage, "category", None):
            category_str = normalize_category(str(c.triage.category))
            
        data = cluster_map[category_str]
        data["complaint_count"] += 1
        if c.customer_id:
            data["customers"].add(c.customer_id)
            
        if hasattr(c, "triage") and c.triage and getattr(c.triage, "severity", None):
            sev = c.triage.severity
            sev_val = str(sev.value) if hasattr(sev, "value") else str(sev)
            data["severity_breakdown"][sev_val] += 1
        else:
            data["severity_breakdown"]["medium"] += 1

    result = []
    for cat, info in cluster_map.items():
        result.append({
            "category": cat,
            "complaint_count": info["complaint_count"],
            "customer_count": len(info["customers"]),
            "severity_breakdown": dict(info["severity_breakdown"])
        })

    result.sort(key=lambda x: x["customer_count"], reverse=True)
    return result


@router.get("/sla-breached", response_model=list[Complaint])
async def sla_breached(current_user: dict = Depends(get_current_user)):
    tenant = current_user.get("tenant_id", "Union Bank")
    return [c for c in get_store().get_sla_breached() if c.tenant_id == tenant]


@router.get("/{ticket_id}/duplicates")
async def get_duplicates(ticket_id: str, current_user: dict = Depends(get_current_user)):
    store = get_store()
    tenant = current_user.get("tenant_id", "Union Bank")
    complaints = store.all()
    if tenant:
        complaints = [c for c in complaints if c.tenant_id == tenant]
        
    dups = [c for c in complaints if c.parent_ticket_id == ticket_id]
    dups.sort(key=lambda x: x.received_at)
    
    distinct_channels = list(dict.fromkeys(c.channel.value.title() for c in dups))
    tickets_data = [
        {
            "id": c.id,
            "ticket_id": c.ticket_id,
            "channel": c.channel.value.title(),
            "timestamp": c.received_at.isoformat()
        }
        for c in dups
    ]
    return {
        "count": len(dups),
        "channels": distinct_channels,
        "tickets": tickets_data
    }


@router.get("/{ticket_id}/timeline")
async def get_complaint_timeline(ticket_id: str, current_user: dict = Depends(get_current_user)):
    from sqlalchemy import text as sa_text
    store = get_store()
    with store._connect() as conn:
        row = conn.execute(
            sa_text("SELECT * FROM complaints WHERE ticket_id = :id OR id = :id"),
            {"id": ticket_id}
        ).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="Complaint not found")
        
    c = store._row_to_complaint(row)
    if c.parent_ticket_id:
        with store._connect() as conn:
            parent_row = conn.execute(
                sa_text("SELECT * FROM complaints WHERE ticket_id = :parent_id OR id = :parent_id"),
                {"parent_id": c.parent_ticket_id}
            ).fetchone()
        if parent_row:
            c = store._row_to_complaint(parent_row)

    complaint_id = c.id
    
    audit_logs = store.get_audit_logs(complaint_id=complaint_id)
    audit_logs.sort(key=lambda x: x["timestamp"])
    
    steps = []
    
    # 1. Raised
    steps.append({
        "stage": "Raised",
        "timestamp": c.received_at.isoformat(),
        "actor": "Customer",
        "completed": True
    })
    
    # 2. Seen
    seen_event = None
    for log in audit_logs:
        if log["action"] in ["view", "seen"]:
            seen_event = log
            break
    if not seen_event:
        for log in audit_logs:
            if log["action"] not in ["ingest"]:
                seen_event = log
                break
    if seen_event:
        steps.append({
            "stage": "Seen",
            "timestamp": seen_event["timestamp"],
            "actor": seen_event["actor"],
            "completed": True
        })
    else:
        steps.append({
            "stage": "Seen",
            "timestamp": None,
            "actor": None,
            "completed": False
        })
        
    # 3. In Progress / Escalated
    in_progress_event = None
    for log in audit_logs:
        if "escalate" in log["action"] or log["action"] in ["action: escalate", "action: reject"]:
            in_progress_event = log
            break
    if in_progress_event:
        steps.append({
            "stage": "In Progress / Escalated",
            "timestamp": in_progress_event["timestamp"],
            "actor": in_progress_event["actor"],
            "completed": True
        })
    elif c.status in [ComplaintStatus.ESCALATED, ComplaintStatus.IN_REVIEW]:
        steps.append({
            "stage": "In Progress / Escalated",
            "timestamp": c.updated_at.isoformat(),
            "actor": "Agent",
            "completed": True
        })
    else:
        steps.append({
            "stage": "In Progress / Escalated",
            "timestamp": None,
            "actor": None,
            "completed": False
        })
        
    # 4. Resolved
    if c.status == ComplaintStatus.RESOLVED and c.resolved_at:
        resolved_actor = "Agent"
        for log in audit_logs:
            if log["action"] in ["action: approve", "resolve"]:
                resolved_actor = log["actor"]
                break
        steps.append({
            "stage": "Resolved",
            "timestamp": c.resolved_at.isoformat(),
            "actor": resolved_actor,
            "completed": True
        })
    else:
        steps.append({
            "stage": "Resolved",
            "timestamp": None,
            "actor": None,
            "completed": False
        })
        
    current_stage = "Raised"
    for s in steps:
        if s["completed"]:
            current_stage = s["stage"]
            
    end_time = c.resolved_at or datetime.utcnow()
    elapsed = end_time - c.received_at
    hours = int(elapsed.total_seconds() // 3600)
    minutes = int((elapsed.total_seconds() % 3600) // 60)
    elapsed_str = f"{hours}h {minutes}m"
    
    return {
        "ticket_id": c.ticket_id,
        "current_stage": current_stage,
        "elapsed_time": elapsed_str,
        "steps": steps
    }


@router.get("/root-cause")
async def root_cause(category: Optional[str] = None, days: int = Query(7, ge=1, le=90), current_user: dict = Depends(get_current_user)):
    cache_key = f"{category or 'all'}:{days}"
    cached = _root_cause_cache.get(cache_key)
    if cached and datetime.utcnow() - cached[0] < timedelta(minutes=10):
        return cached[1]
    since = datetime.utcnow() - timedelta(days=days)
    tenant = current_user.get("tenant_id", "Union Bank")
    complaints = [c for c in get_store().all() if c.received_at >= since and c.tenant_id == tenant]

    if category:
        complaints = [c for c in complaints if c.triage and c.triage.category.value == category]
    if len(complaints) < 3:
        return {"message": "insufficient data", "count": len(complaints)}
    texts = "\n".join(f"- {c.masked_text[:200]}" for c in complaints[:10])
    issue_counts = Counter(c.triage.key_issue for c in complaints if c.triage and c.triage.key_issue)
    fallback = {
        "root_causes": [
            {"cause": cause, "count_estimate": count, "example_complaint": next(c.masked_text for c in complaints if c.triage and c.triage.key_issue == cause)[:200]}
            for cause, count in issue_counts.most_common(3)
        ]
    }
    result = _claude_json(
        "You are a complaint analytics expert. Identify the top 3 root causes from these customer complaints. Be specific and concise. Return JSON: {root_causes: [{cause, count_estimate, example_complaint}]}",
        texts,
        fallback,
    )
    _root_cause_cache[cache_key] = (datetime.utcnow(), result)
    return result


@router.get("/reports/regulatory")
async def regulatory_report_new(
    from_date: Optional[str] = None,
    to_date: Optional[str] = None,
    format: str = Query("json", pattern="^(json|csv)$"),
    current_user: dict = Depends(require_role(["supervisor", "admin"]))
):
    complaints = get_store().all()
    tenant = current_user.get("tenant_id", "Union Bank")
    complaints = [c for c in complaints if c.tenant_id == tenant]
    start = datetime.fromisoformat(from_date) if from_date else datetime.utcnow() - timedelta(days=30)

    end = datetime.fromisoformat(to_date) if to_date else datetime.utcnow()

    # CMS Ledger math:
    opening = [c for c in complaints if c.received_at < start and (c.resolved_at is None or c.resolved_at >= start)]
    opening_balance = len(opening)

    received = [c for c in complaints if start <= c.received_at <= end]
    received_count = len(received)

    disposed = [c for c in complaints if c.resolved_at and start <= c.resolved_at <= end]
    disposed_count = len(disposed)

    closed_within_30 = 0
    closed_beyond_30 = 0
    for c in disposed:
        delta_days = (c.resolved_at - c.received_at).days
        if delta_days <= 30:
            closed_within_30 += 1
        else:
            closed_beyond_30 += 1

    closing = [c for c in complaints if c.received_at <= end and (c.resolved_at is None or c.resolved_at > end)]
    closing_balance = len(closing)

    total_active = opening_balance + received_count
    disposed_rate_percent = round(disposed_count / total_active * 100, 1) if total_active else 100.0

    # Calculate real systemic issues (clusters with affected_customers >= 5)
    clusters = defaultdict(list)
    for c in complaints:
        if c.cluster and c.cluster.cluster_id:
            clusters[c.cluster.cluster_id].append(c)
    systemic_issues_count = sum(1 for members in clusters.values() if len({m.customer_id for m in members if m.customer_id}) >= 5)

    # Normalize category / severity lists
    category_counts = Counter()
    for c in received:
        cat = c.triage.category.value if (c.triage and hasattr(c.triage.category, 'value')) else (str(c.triage.category) if (c.triage and c.triage.category) else "General")
        category_counts[cat] += 1

    severity_counts = Counter()
    for c in received:
        sev = c.triage.severity.value if (c.triage and hasattr(c.triage.severity, 'value')) else (str(c.triage.severity) if (c.triage and c.triage.severity) else "medium")
        severity_counts[sev] += 1

    report = {
        "period": "Last 30 Days",
        "generated_at": datetime.utcnow().isoformat(),
        "report_period": {"from": start.isoformat(), "to": end.isoformat()},
        "opening_balance": opening_balance,
        "received": received_count,
        "disposed_within_30": closed_within_30,
        "disposed_beyond_30": closed_beyond_30,
        "disposed_total": disposed_count,
        "closing_balance": closing_balance,
        "disposed_rate_percent": disposed_rate_percent,
        "total_complaints": received_count,
        "systemic_issues": systemic_issues_count,
        "by_channel": dict(Counter(c.channel.value for c in received)),
        "by_category": dict(category_counts),
        "by_severity": dict(severity_counts),
    }

    if format == "json":
        return report

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["section", "metric", "value"])
    writer.writerow(["period", "from", report["report_period"]["from"]])
    writer.writerow(["period", "to", report["report_period"]["to"]])
    writer.writerow(["cms_summary", "opening_balance", report["opening_balance"]])
    writer.writerow(["cms_summary", "received", report["received"]])
    writer.writerow(["cms_summary", "disposed_within_30", report["disposed_within_30"]])
    writer.writerow(["cms_summary", "disposed_beyond_30", report["disposed_beyond_30"]])
    writer.writerow(["cms_summary", "disposed_total", report["disposed_total"]])
    writer.writerow(["cms_summary", "closing_balance", report["closing_balance"]])
    writer.writerow(["cms_summary", "disposed_rate_percent", report["disposed_rate_percent"]])
    writer.writerow(["cms_summary", "systemic_issues", report["systemic_issues"]])
    
    for section in ("by_channel", "by_category", "by_severity"):
        for key, value in report[section].items():
            writer.writerow([section, key, value])
            
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=uniresolve-regulatory-report.csv"},
    )



@router.get("/trends")
async def trends(
    group_by: str = Query("category", pattern="^(category|channel|severity|sentiment)$"),
    window: str = Query("7d", pattern="^(1d|7d|30d)$"),
    current_user: dict = Depends(get_current_user)
):
    days = int(window[:-1])
    now = datetime.utcnow()
    start = now - timedelta(days=days)
    prior_start = start - timedelta(days=days)
    complaints = get_store().all()
    tenant = current_user.get("tenant_id", "Union Bank")
    complaints = [c for c in complaints if c.tenant_id == tenant]
    current = [c for c in complaints if c.received_at >= start]
    prior = [c for c in complaints if prior_start <= c.received_at < start]


    def label(c: Complaint) -> str:
        if group_by == "channel":
            return c.channel.value
        if group_by == "severity":
            return c.triage.severity.value if c.triage else "unknown"
        if group_by == "sentiment":
            return c.triage.sentiment.value if c.triage else "unknown"
        return c.triage.category.value if c.triage else "unknown"

    buckets: dict[tuple[str, str], int] = defaultdict(int)
    for c in current:
        buckets[(c.received_at.date().isoformat(), label(c))] += 1
    data = [{"date": date, "label": lab, "count": count} for (date, lab), count in sorted(buckets.items())]
    change = round((len(current) - len(prior)) / len(prior) * 100, 1) if prior else (100.0 if current else 0.0)
    fallback = f"{group_by.replace('_', ' ').title()} complaints {'up' if change >= 0 else 'down'} {abs(change)}% vs prior period."
    summary = _claude_text(
        "Write one concise sentence comparing complaint trends in the current window vs the prior window.",
        f"group_by={group_by}, window={window}, current_count={len(current)}, prior_count={len(prior)}, grouped_data={data[:30]}",
        fallback,
    )
    return {"window": window, "group_by": group_by, "data": data, "summary": summary}


@router.get("/regulatory-report", response_model=RegulatoryReport)
async def regulatory_report_legacy(current_user: dict = Depends(require_role(["supervisor", "admin"]))):
    tenant = current_user.get("tenant_id", "Union Bank")
    return get_store().get_regulatory_report(tenant_id=tenant)



@router.get("", response_model=list[Complaint])
async def list_complaints(
    status: Optional[ComplaintStatus] = Query(None),
    channel: Optional[Channel] = Query(None),
    severity: Optional[Severity] = Query(None),
    category: Optional[Category] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
    current_user: dict = Depends(get_current_user)
):
    complaints = get_store().all()
    tenant = current_user.get("tenant_id", "Union Bank")
    complaints = [c for c in complaints if c.tenant_id == tenant]

    if status:
        complaints = [c for c in complaints if c.status == status]
    if channel:
        complaints = [c for c in complaints if c.channel == channel]
    if severity:
        complaints = [c for c in complaints if c.triage and c.triage.severity == severity]
    if category:
        complaints = [c for c in complaints if c.triage and c.triage.category == category]
    if search:
        s = search.lower()
        complaints = [
            c for c in complaints if
            s in (c.masked_text or "").lower() or
            (bool(c.triage) and s in (c.triage.key_issue or "").lower()) or
            (bool(c.triage) and s in c.triage.category.value.lower()) or
            s in c.channel.value.lower()
        ]
    # Build mapping of parent_ticket_id -> list of child complaints across all tenant complaints
    parent_map = defaultdict(list)
    for c in complaints:
        if c.parent_ticket_id:
            parent_map[c.parent_ticket_id].append(c)
            
    for c in complaints:
        if not c.parent_ticket_id and c.ticket_id in parent_map:
            children = parent_map[c.ticket_id]
            c.duplicate_count = len(children)
            c.duplicate_channels = list(dict.fromkeys(ch.channel.value.title() for ch in children))

    complaints.sort(key=lambda c: c.received_at, reverse=True)
    return complaints[:limit]


@router.get("/audit", tags=["audit"])
async def get_audit(
    complaint_id: Optional[str] = Query(None),
    current_user: dict = Depends(require_role(["admin"]))
):
    store = get_store()
    return store.get_audit_logs(complaint_id=complaint_id)


@router.get("/{complaint_id}/audit", tags=["audit"])
async def get_complaint_audit(complaint_id: str, current_user: dict = Depends(get_current_user)):
    store = get_store()
    return store.get_audit_logs(complaint_id=complaint_id)


@router.get("/{complaint_id}", response_model=Complaint)
async def get_complaint(complaint_id: str, current_user: dict = Depends(get_current_user)):
    c = get_store().get(complaint_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
        
    # Populate duplicate fields
    tenant = current_user.get("tenant_id", "Union Bank")
    all_tenant = [x for x in get_store().all() if x.tenant_id == tenant]
    children = [x for x in all_tenant if x.parent_ticket_id == c.ticket_id]
    c.duplicate_count = len(children)
    c.duplicate_channels = list(dict.fromkeys(ch.channel.value.title() for ch in children))
    
    # Log audit event for view
    get_store().log_audit(current_user.get("username", "agent"), current_user.get("role", "agent"), "view", complaint_id)
    return c


@router.get("/{complaint_id}/explain")
async def explain_triage(complaint_id: str, current_user: dict = Depends(get_current_user)):
    c = get_store().get(complaint_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if not c.triage:
        return {"explanation": "No triage data available for this complaint.", "complaint_id": complaint_id}
    explanation = _claude_text(
        "You are an AI audit assistant for a banking complaint system. "
        "Explain in exactly 2 sentences why this complaint was classified with the given "
        "category, severity and sentiment. Reference specific words or phrases from the complaint text that drove the decision.",
        f"Complaint: {c.masked_text}\nCategory: {c.triage.category.value}\n"
        f"Severity: {c.triage.severity.value}\nSentiment: {c.triage.sentiment.value}\n"
        f"Key issue: {c.triage.key_issue}",
        f"Classified as {c.triage.category.value} / {c.triage.severity.value} based on complaint keywords and pattern matching."
    )
    return {"explanation": explanation, "complaint_id": complaint_id, "triage": {
        "category": c.triage.category.value,
        "severity": c.triage.severity.value,
        "sentiment": c.triage.sentiment.value,
        "confidence": c.triage.confidence
    }}


@router.post("/{complaint_id}/action")
async def agent_action(complaint_id: str, action: AgentAction, current_user: dict = Depends(get_current_user)):
    store = get_store()
    c = store.get(complaint_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    status_map = {"approve": ComplaintStatus.RESOLVED, "escalate": ComplaintStatus.ESCALATED, "reject": ComplaintStatus.IN_REVIEW}
    new_status = status_map.get(action.action)
    if not new_status:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")
    updated = store.update_status(complaint_id, new_status, agent_note=action.custom_response)
    
    # Audit log
    store.log_audit(current_user["username"], current_user["role"], f"action: {action.action}", complaint_id)
    
    # Ledger and resolution precedent indexing
    if new_status == ComplaintStatus.RESOLVED:
        store.log_ledger_event(complaint_id, "resolved", current_user["username"])
        from app.services.clustering import get_clustering_service
        encoder_service = get_clustering_service()
        if encoder_service and encoder_service.healthy:
            vec = encoder_service._encode(c.masked_text)
            if vec is not None:
                vec_list = vec.tolist()[0]
                from app.services import qdrant_service
                qdrant_service.upsert_resolved_precedent(
                    complaint_id=c.id,
                    vector=vec_list,
                    payload={
                        "complaint_text": c.masked_text,
                        "category": c.triage.category.value if c.triage else "general",
                        "final_resolution": action.custom_response or (c.triage.suggested_response if c.triage else "")
                    }
                )
    else:
        store.log_ledger_event(complaint_id, f"action: {action.action}", current_user["username"])
        
    return {"complaint_id": complaint_id, "new_status": new_status, "complaint": updated}


@router.post("/{complaint_id}/escalate")
async def escalate_complaint(complaint_id: str, action: EscalationAction, current_user: dict = Depends(get_current_user)):
    # Role check: L4 Regulatory requires supervisor+
    from app.models.complaint import EscalationLevel
    if action.to_level == EscalationLevel.L4_REGULATORY:
        if current_user.get("role") not in ["supervisor", "admin"]:
            raise HTTPException(
                status_code=403,
                detail="Action requires supervisor or admin role."
            )
            
    store = get_store()
    c = store.get(complaint_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    note = action.agent_note or action.note
    if not (note or action.reason):
        raise HTTPException(status_code=422, detail="agent_note is required")
    record = EscalationRecord(from_level=c.escalation_level, to_level=action.to_level, reason=action.reason or note, escalated_by=action.agent_id, note=note)
    updated = store.escalate(complaint_id, record, action.to_level)
    
    # Audit log
    store.log_audit(current_user["username"], current_user["role"], f"escalate to {action.to_level.value}", complaint_id)
    return {"complaint_id": complaint_id, "escalated_to": action.to_level, "complaint": updated}


@router.post("/{complaint_id}/reply")
async def add_reply(complaint_id: str, msg: ReplyMessage, current_user: dict = Depends(get_current_user)):
    store = get_store()
    if not store.get(complaint_id):
        raise HTTPException(status_code=404, detail="Complaint not found")
    new_msg = HistoryMessage(author=msg.author, author_name=msg.author_name, content=msg.content, is_ai_draft=msg.is_ai_draft)
    updated = store.add_message(complaint_id, new_msg)
    
    # Audit log
    store.log_audit(current_user["username"], current_user["role"], "reply", complaint_id)
    return {"complaint_id": complaint_id, "message": new_msg, "complaint": updated}


@router.post("/{complaint_id}/link-customer")
async def link_customer(complaint_id: str, payload: dict, current_user: dict = Depends(get_current_user)):
    store = get_store()
    c = store.get(complaint_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    c.customer_id = payload.get("customer_id")
    store.save(c)
    
    # Audit log
    store.log_audit(current_user["username"], current_user["role"], f"link customer: {c.customer_id}", complaint_id)
    return {"success": True, "complaint": c}


@router.get("/{complaint_id}/trace")
async def get_complaint_trace(complaint_id: str, current_user: dict = Depends(get_current_user)):
    store = get_store()
    c = store.get(complaint_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return {"complaint_id": complaint_id, "agent_trace": c.agent_trace}


@router.post("/{complaint_id}/approve")
async def approve_complaint_draft(complaint_id: str, current_user: dict = Depends(get_current_user)):
    store = get_store()
    c = store.get(complaint_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if not c.needs_human or not c.thread_id:
        raise HTTPException(status_code=400, detail="Complaint does not require approval or is not paused")
        
    from app.agents.graph import resume_pipeline
    res = resume_pipeline(c.thread_id, decision="approved")
    state = res["state"]
    
    c.needs_human = False
    c.triage.suggested_response = state.get("draft") or ""
    
    # Add messages to history
    c.communication_history.append(
        HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content="Supervisor approved the draft.")
    )
    c.communication_history.append(
        HistoryMessage(author=MessageAuthor.AGENT, author_name="AI Assistant", content=c.triage.suggested_response, is_ai_draft=True)
    )
    
    store.save(c)
    store.log_ledger_event(c.id, "approved", current_user["username"])
    store.log_audit(current_user["username"], current_user["role"], "approve_draft", c.id)
    
    return {"success": True, "complaint": c}


class ProvideInfoIn(BaseModel):
    transaction_ref: Optional[str] = None
    amount: Optional[float] = None

@router.post("/{complaint_id}/provide-info")
async def provide_complaint_info(complaint_id: str, payload: ProvideInfoIn):
    store = get_store()
    c = store.get(complaint_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    if not c.needs_info or not c.thread_id:
        raise HTTPException(status_code=400, detail="Complaint is not awaiting info")
        
    provided_info = {}
    if payload.transaction_ref:
        provided_info["transaction_ref"] = payload.transaction_ref
        c.transaction_id = payload.transaction_ref
    if payload.amount:
        provided_info["amount"] = payload.amount
        
    from app.agents.graph import resume_pipeline
    res = resume_pipeline(c.thread_id, decision="info_provided", provided_info=provided_info)
    state = res["state"]
    
    c.needs_info = False
    c.needs_human = state.get("needs_human", False)
    c.missing_fields_question = None
    
    # Update triage suggested response draft
    c.triage.suggested_response = state.get("draft") or ""
    
    # Append customer answer to history
    info_text = f"Customer provided info: Ref={payload.transaction_ref}, Amount={payload.amount}"
    c.communication_history.append(
        HistoryMessage(author=MessageAuthor.CUSTOMER, author_name="Customer", content=info_text)
    )
    
    if c.needs_human:
        c.communication_history.append(
            HistoryMessage(author=MessageAuthor.SYSTEM, author_name="System", content="Supervisor approval pending after info submission.")
        )
    else:
        c.communication_history.append(
            HistoryMessage(author=MessageAuthor.AGENT, author_name="AI Assistant", content=c.triage.suggested_response, is_ai_draft=True)
        )
        
    store.save(c)
    store.log_ledger_event(c.id, "info_provided", "customer")
    
    return {"success": True, "complaint": c}


@router.get("/{complaint_id}/ledger/verify")
async def verify_complaint_ledger(complaint_id: str, current_user: dict = Depends(get_current_user)):
    store = get_store()
    valid = store.verify_ledger_chain(complaint_id)
    return {"complaint_id": complaint_id, "valid": valid}


@router.get("/incidents/all")
async def get_all_active_incidents(current_user: dict = Depends(get_current_user)):
    return get_store().all_incidents()



