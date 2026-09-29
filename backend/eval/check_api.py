import httpx
import json

try:
    r = httpx.get("http://127.0.0.1:8000/complaints", timeout=5.0)
    data = r.json()
    items = data if isinstance(data, list) else data.get("items", [])
    print(f"Total complaints in API: {len(items)}")
    for i, c in enumerate(items[:10]):
        cid = c.get("id", "")[:8]
        triage = c.get("triage") or {}
        cat = triage.get("category")
        draft = triage.get("suggested_response")
        history = c.get("communication_history") or []
        print(f"\n[{i+1}] ID: {cid} | Cat: {cat} | Needs Human: {c.get('needs_human')} | Needs Info: {c.get('needs_info')}")
        print(f"    Suggested Draft: '{draft}'")
        print(f"    History Messages ({len(history)}):")
        for h in history:
            print(f"      - {h.get('author')}: '{h.get('content')}' (AI Draft: {h.get('is_ai_draft')})")
except Exception as e:
    print("API Error:", e)
