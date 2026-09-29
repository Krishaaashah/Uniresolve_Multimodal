import json
import sys

# Ensure UTF-8 output on Windows terminal
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

print("=" * 75)
print("UNIRESOLVE AUDIO / IVR VOICE PROMPTS SPECIFICATION")
print("=" * 75)

print("\n### SECTION 1: Curated Demo Grievances (backend/app/seed.py)")
demo_items = [
    {
        "id": "DEMO-05",
        "category": "UPI Failure",
        "customer_id": "CUST-10005",
        "customer_name": "Vikram Joshi",
        "account_no": "401928374505",
        "transaction_id": "TXN-10005-01",
        "amount": "₹4,500.00",
        "language": "English (Indian Accent)",
        "tone": "Frustrated, urgent",
        "filename": "voice_note.wav",
        "prompt": "Hello, my name is Vikram Joshi, Customer ID CUST-10005. I tried to make a UPI payment of 4,500 rupees at a store for transaction TXN-10005-01. The payment timed out on the UPI gateway but the money was deducted from my savings account. Please reverse this transaction immediately."
    },
    {
        "id": "DEMO-23",
        "category": "Card Blocking",
        "customer_id": "CUST-10004",
        "customer_name": "Neha Gupta",
        "account_no": "301829475604",
        "transaction_id": "TXN-10004-02",
        "amount": "₹3,500.00",
        "language": "English (Indian Accent)",
        "tone": "Concerned, clear",
        "filename": "demo_ivr_card_10004.wav",
        "prompt": "Hello customer service, this is Neha Gupta, Customer ID CUST-10004. My debit card was suddenly blocked at the merchant terminal during transaction TXN-10004-02 for amount 3,500 rupees. Please unblock my card as soon as possible."
    }
]

for d in demo_items:
    print(f"\nID: {d['id']} | Category: {d['category']} | Target File: {d['filename']}")
    print(f"Customer: {d['customer_id']} ({d['customer_name']}) | Txn ID: {d['transaction_id']} | Amount: {d['amount']}")
    print(f"Language: {d['language']} | Tone: {d['tone']}")
    print(f"Voice Script / Text to speak:\n\"{d['prompt']}\"")

print("\n" + "=" * 75)
print("### SECTION 2: Evaluation Dataset Grievances (backend/eval/eval_set.jsonl)")
with open("eval/eval_set.jsonl", "r", encoding="utf-8") as f:
    records = [json.loads(line) for line in f]

ivr_count = 0
for r in records:
    if r.get("channel") == "ivr" or str(r.get("attachment_file", "")).endswith(".wav"):
        ivr_count += 1
        rec_id = r["id"]
        cat = r["gold"]["category"]
        lang = r["gold"]["language"]
        sev = r["gold"]["severity"]
        sent = r["gold"]["sentiment"]
        cust = r.get("customer_id", "N/A")
        tx = r.get("transaction_id", "N/A")
        att = r.get("attachment_file") or f"ivr_{rec_id.lower().replace('-', '_')}.wav"

        print(f"\nID: {rec_id} | Category: {cat} | Severity: {sev} | Target File: {att}")
        print(f"Customer ID: {cust} | Transaction ID: {tx} | Language: {lang} | Sentiment: {sent}")
        print(f"Voice Script / Text to speak:\n\"{r['raw_text']}\"")

print(f"\nTotal IVR / Audio Complaints: {ivr_count}")
