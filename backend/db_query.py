import sqlite3, sys, os

conn = sqlite3.connect('complaints.db')
conn.row_factory = sqlite3.Row
cur = conn.cursor()

cur.execute("""
    SELECT ticket_id, customer_id, transaction_id, status, category,
           substr(masked_text, 1, 100) as txt
    FROM complaints
    ORDER BY customer_id, received_at ASC
""")
rows = cur.fetchall()

print("=== ALL COMPLAINTS ===")
print(f"{'TICKET_ID':<14} {'CUSTOMER':<11} {'TXN_ID':<14} {'STATUS':<12} {'CATEGORY':<28} PREVIEW")
print("-" * 130)
for r in rows:
    txn = r['transaction_id'] or '(none)'
    txt = (r['txt'] or '').encode('ascii', errors='replace').decode('ascii')
    cat = (r['category'] or '(none)')[:26]
    print(f"{r['ticket_id']:<14} {(r['customer_id'] or '(none)'):<11} {txn:<14} {r['status']:<12} {cat:<28} {txt[:55]}")

print()
print("=== DISTINCT CUSTOMER IDs ===")
cur.execute("SELECT DISTINCT customer_id, COUNT(*) as cnt FROM complaints GROUP BY customer_id ORDER BY cnt DESC")
for r in cur.fetchall():
    print(f"  {r['customer_id']} -> {r['cnt']} tickets")

print()
print("=== TRANSACTION IDs PER CUSTOMER ===")
cur.execute("SELECT DISTINCT transaction_id, customer_id, COUNT(*) as cnt FROM complaints WHERE transaction_id IS NOT NULL GROUP BY transaction_id ORDER BY customer_id")
for r in cur.fetchall():
    print(f"  TXN={r['transaction_id']} | CUST={r['customer_id']} | {r['cnt']} ticket(s)")

print()
print("=== STATUS COUNTS ===")
cur.execute("SELECT status, COUNT(*) as cnt FROM complaints GROUP BY status")
for r in cur.fetchall():
    print(f"  {r['status']}: {r['cnt']}")

conn.close()
