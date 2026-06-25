"""Complaint API routes for UniResolve."""

import csv
import io
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request
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
from app.security import check_api_key
from app.services.clustering import get_clustering_service
from app.services.pii_scrubber import mask_pii
from app.services.store import get_store
from app.services.triage import get_triage_service
from app.config import (
    GEMINI_API_KEY, ANTHROPIC_API_KEY, GEMINI_MODEL, CLAUDE_MODEL
)

router = APIRouter(prefix="/complaints", tags=["complaints"])
limiter = Limiter(key_func=get_remote_address)
_root_cause_cache: dict[str, tuple[datetime, dict]] = {}


def _claude_json(system: str, user: str, fallback: dict) -> dict:
    if GEMINI_API_KEY:
        try:
            import httpx
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [{"text": f"Instruction: {system}\n\nInput: {user}"}]
                }],
                "generationConfig": {
                    "responseMimeType": "application/json",
                    "maxOutputTokens": 600
                }
            }
            res = httpx.post(url, json=payload, headers=headers, timeout=15.0)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                start = text.find("{")
                end = text.rfind("}") + 1
                return json.loads(text[start:end])
        except Exception:
            pass

    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=600,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            text = "".join(block.text for block in msg.content if getattr(block, "type", "") == "text").strip()
            start = text.find("{")
            end = text.rfind("}") + 1
            return json.loads(text[start:end])
        except Exception:
            pass

    return fallback


def _claude_text(system: str, user: str, fallback: str) -> str:
    if GEMINI_API_KEY:
        try:
            import httpx
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
            headers = {"Content-Type": "application/json"}
            payload = {
                "contents": [{
                    "parts": [{"text": f"Instruction: {system}\n\nInput: {user}"}]
                }],
                "generationConfig": {
                    "maxOutputTokens": 120
                }
            }
            res = httpx.post(url, json=payload, headers=headers, timeout=15.0)
            if res.status_code == 200:
                data = res.json()
                text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
                if text:
                    return text
        except Exception:
            pass

    if ANTHROPIC_API_KEY:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
            msg = client.messages.create(
                model=CLAUDE_MODEL,
                max_tokens=120,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
            return "".join(block.text for block in msg.content if getattr(block, "type", "") == "text").strip() or fallback
        except Exception:
            pass

    return fallback


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
                media_desc = "[Simulated Audio Transcription]: Yes, hello. I was trying to withdraw 10,000 rupees from the Delhi Airport ATM. The machine failed to dispense cash but debited my account. Please reverse it."
            else:
                media_desc = "[Simulated Image Analysis]: Visual screenshot of a failed mobile banking app transaction. Customer Aarav Sharma, Account 9102837465, Rs 3,000.00 failed UPI transfer with reference UPI657483."
        else:
            from app.services.multimodal import process_multimodal_attachment
            media_desc = process_multimodal_attachment(payload.media_file, payload.media_type)

        if payload.raw_text:
            payload.raw_text = f"{payload.raw_text}\n\n[Media Attachment Analysis ({payload.media_type})]:\n{media_desc}"
        else:
            payload.raw_text = media_desc

    masked_text, masked_fields = mask_pii(payload.raw_text)
    
    # Conserve rate limits for background loops/seeding
    is_seed = payload.channel_metadata.get("seed") is True
    is_replay = payload.source_ref and payload.source_ref.startswith("replay-")
    skip_ai_draft = is_seed or is_replay
    
    triage_result = get_triage_service().triage(masked_text, skip_ai_draft=skip_ai_draft)
    received_at = payload.received_at or datetime.utcnow()
    
    complaint = Complaint(
        channel=payload.channel,
        channel_metadata=payload.channel_metadata,
        raw_text=payload.raw_text,
        masked_text=masked_text,
        masked_fields=masked_fields,
        customer_id=payload.customer_id,
        source_ref=payload.source_ref,
        received_at=received_at,
        triage=triage_result,
    )
    
    # Save the file using the complaint's unique ID to avoid namespace collisions
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

    complaint.communication_history.extend(
        [
            HistoryMessage(author=MessageAuthor.CUSTOMER, author_name="Customer", content=payload.raw_text, timestamp=received_at),
            HistoryMessage(
                author=MessageAuthor.SYSTEM,
                author_name="System",
                content=f"Auto-triaged: {triage_result.category.value} | {triage_result.severity.value} | {triage_result.sentiment.value}",
            ),
            HistoryMessage(author=MessageAuthor.AGENT, author_name="AI Assistant", content=triage_result.suggested_response, is_ai_draft=True),
        ]
    )
    complaint.cluster = get_clustering_service().check_and_register(complaint.id, masked_text)
    store.save(complaint)
    return ComplaintResponse(complaint=complaint, message="Complaint ingested and triaged successfully.")


@router.get("/stats", response_model=DashboardStats)
async def get_stats():
    return get_store().get_stats()


@router.get("/alerts")
async def get_alerts():
    alerts = [c for c in get_store().all() if c.cluster and c.cluster.systemic_alert]
    return {"alerts": alerts, "count": len(alerts)}


@router.get("/sla-breached", response_model=list[Complaint])
async def sla_breached():
    return get_store().get_sla_breached()


@router.get("/root-cause")
async def root_cause(category: Optional[str] = None, days: int = Query(7, ge=1, le=90)):
    cache_key = f"{category or 'all'}:{days}"
    cached = _root_cause_cache.get(cache_key)
    if cached and datetime.utcnow() - cached[0] < timedelta(minutes=10):
        return cached[1]
    since = datetime.utcnow() - timedelta(days=days)
    complaints = [c for c in get_store().all() if c.received_at >= since]
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
):
    complaints = get_store().all()
    start = datetime.fromisoformat(from_date) if from_date else datetime.utcnow() - timedelta(days=30)
    end = datetime.fromisoformat(to_date) if to_date else datetime.utcnow()
    complaints = [c for c in complaints if start <= c.received_at <= end]
    total = len(complaints)
    resolved = [c for c in complaints if c.status == ComplaintStatus.RESOLVED]
    top_issues = Counter(issue for c in complaints if c.triage for issue in (c.triage.key_issues or [c.triage.key_issue]) if issue)
    sla_counts = Counter(c.sla_status.value for c in complaints)
    res_hours = [(c.resolved_at - c.received_at).total_seconds() / 3600 for c in resolved if c.resolved_at]
    report = {
        "report_period": {"from": start.isoformat(), "to": end.isoformat()},
        "total_complaints": total,
        "by_channel": dict(Counter(c.channel.value for c in complaints)),
        "by_category": dict(Counter(c.triage.category.value for c in complaints if c.triage)),
        "by_severity": dict(Counter(c.triage.severity.value for c in complaints if c.triage)),
        "resolution_stats": {
            "resolved": len(resolved),
            "pending": sum(c.status == ComplaintStatus.PENDING for c in complaints),
            "escalated": sum(c.status == ComplaintStatus.ESCALATED for c in complaints),
            "avg_resolution_hours": round(sum(res_hours) / len(res_hours), 2) if res_hours else 0.0,
        },
        "sla_compliance": {
            "on_track": sla_counts.get("on_track", 0),
            "at_risk": sla_counts.get("at_risk", 0),
            "breached": sla_counts.get("breached", 0),
            "compliance_rate_percent": round((total - sla_counts.get("breached", 0)) / total * 100 if total else 100, 1),
        },
        "top_issues": [{"issue": k, "count": v} for k, v in top_issues.most_common(5)],
    }
    if format == "json":
        return report
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["section", "metric", "value"])
    writer.writerow(["period", "from", report["report_period"]["from"]])
    writer.writerow(["period", "to", report["report_period"]["to"]])
    writer.writerow(["summary", "total_complaints", total])
    for section in ("by_channel", "by_category", "by_severity"):
        for key, value in report[section].items():
            writer.writerow([section, key, value])
    for key, value in report["resolution_stats"].items():
        writer.writerow(["resolution_stats", key, value])
    for key, value in report["sla_compliance"].items():
        writer.writerow(["sla_compliance", key, value])
    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=uniresolve-regulatory-report.csv"},
    )


@router.get("/trends")
async def trends(
    group_by: str = Query("category", pattern="^(category|channel|severity|sentiment)$"),
    window: str = Query("7d", pattern="^(1d|7d|30d)$"),
):
    days = int(window[:-1])
    now = datetime.utcnow()
    start = now - timedelta(days=days)
    prior_start = start - timedelta(days=days)
    complaints = get_store().all()
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
async def regulatory_report_legacy():
    return get_store().get_regulatory_report()


@router.get("", response_model=list[Complaint])
async def list_complaints(
    status: Optional[ComplaintStatus] = Query(None),
    channel: Optional[Channel] = Query(None),
    severity: Optional[Severity] = Query(None),
    category: Optional[Category] = Query(None),
    search: Optional[str] = Query(None),
    limit: int = Query(100, le=500),
):
    complaints = get_store().all()
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
    complaints.sort(key=lambda c: c.received_at, reverse=True)
    return complaints[:limit]


@router.get("/{complaint_id}", response_model=Complaint)
async def get_complaint(complaint_id: str):
    c = get_store().get(complaint_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    return c


@router.get("/{complaint_id}/explain", dependencies=[Depends(check_api_key)])
async def explain_triage(complaint_id: str):
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


@router.post("/{complaint_id}/action", dependencies=[Depends(check_api_key)])
async def agent_action(complaint_id: str, action: AgentAction):
    store = get_store()
    if not store.get(complaint_id):
        raise HTTPException(status_code=404, detail="Complaint not found")
    status_map = {"approve": ComplaintStatus.RESOLVED, "escalate": ComplaintStatus.ESCALATED, "reject": ComplaintStatus.IN_REVIEW}
    new_status = status_map.get(action.action)
    if not new_status:
        raise HTTPException(status_code=400, detail=f"Unknown action: {action.action}")
    updated = store.update_status(complaint_id, new_status, agent_note=action.custom_response)
    return {"complaint_id": complaint_id, "new_status": new_status, "complaint": updated}


@router.post("/{complaint_id}/escalate", dependencies=[Depends(check_api_key)])
async def escalate_complaint(complaint_id: str, action: EscalationAction):
    store = get_store()
    c = store.get(complaint_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    note = action.agent_note or action.note
    if not (note or action.reason):
        raise HTTPException(status_code=422, detail="agent_note is required")
    record = EscalationRecord(from_level=c.escalation_level, to_level=action.to_level, reason=action.reason or note, escalated_by=action.agent_id, note=note)
    updated = store.escalate(complaint_id, record, action.to_level)
    return {"complaint_id": complaint_id, "escalated_to": action.to_level, "complaint": updated}


@router.post("/{complaint_id}/reply", dependencies=[Depends(check_api_key)])
async def add_reply(complaint_id: str, msg: ReplyMessage):
    store = get_store()
    if not store.get(complaint_id):
        raise HTTPException(status_code=404, detail="Complaint not found")
    new_msg = HistoryMessage(author=msg.author, author_name=msg.author_name, content=msg.content, is_ai_draft=msg.is_ai_draft)
    updated = store.add_message(complaint_id, new_msg)
    return {"complaint_id": complaint_id, "message": new_msg, "complaint": updated}


@router.post("/{complaint_id}/link-customer", dependencies=[Depends(check_api_key)])
async def link_customer(complaint_id: str, payload: dict):
    store = get_store()
    c = store.get(complaint_id)
    if not c:
        raise HTTPException(status_code=404, detail="Complaint not found")
    c.customer_id = payload.get("customer_id")
    store.save(c)
    return {"success": True, "complaint": c}
