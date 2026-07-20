import os
import sys
import pytest
from datetime import datetime, timedelta

# Ensure backend folder is in Python path for test execution
sys.path.append(os.path.join(os.path.dirname(__file__), ".."))

from app.services.store import get_store
from app.services.clustering import get_clustering_service
from app.models.complaint import Complaint, Channel, RawComplaintIn, ComplaintStatus
from app.services.triage import get_triage_service

def test_systemic_clustering_scenarios():
    store = get_store()
    clustering = get_clustering_service()
    
    # 1. Clear database and FAISS index
    store.clear()
    clustering.clear()
    
    # Use the same text to ensure similarity is 1.0 (which is >= 0.88 similarity threshold)
    similar_text = "My UPI payment failed and the money was debited from my account. Please refund it immediately."
    
    # An unrelated complaint
    unrelated_text = "Credit card fee charged incorrectly on my monthly statement. Please reverse."

    # Seed similar complaints from 5 different customers
    # Complaint A
    c_a = Complaint(
        id="c-a",
        ticket_id="TKT-A",
        channel=Channel.APP,
        raw_text=similar_text,
        masked_text=similar_text,
        customer_id="cust-1",
        transaction_id="tx-1"
    )
    res_a = clustering.check_and_register("c-a", similar_text, customer_id="cust-1", transaction_id="tx-1")
    c_a.cluster = res_a
    store.save(c_a)

    # Complaint B
    c_b = Complaint(
        id="c-b",
        ticket_id="TKT-B",
        channel=Channel.APP,
        raw_text=similar_text,
        masked_text=similar_text,
        customer_id="cust-2",
        transaction_id="tx-2"
    )
    res_b = clustering.check_and_register("c-b", similar_text, customer_id="cust-2", transaction_id="tx-2")
    c_b.cluster = res_b
    store.save(c_b)

    # Assert cluster is same as c_a because of semantic match with different customer
    assert res_b.cluster_id == res_a.cluster_id
    assert res_b.is_duplicate is False
    assert res_b.duplicate_reason == "systemic_similarity"

    # Complaint C, D, E
    for i in range(3, 6):
        cid = f"c-{i}"
        cust_id = f"cust-{i}"
        tx_id = f"tx-{i}"
        c = Complaint(
            id=cid,
            ticket_id=f"TKT-{i}",
            channel=Channel.APP,
            raw_text=similar_text,
            masked_text=similar_text,
            customer_id=cust_id,
            transaction_id=tx_id
        )
        res = clustering.check_and_register(cid, similar_text, customer_id=cust_id, transaction_id=tx_id)
        c.cluster = res
        store.save(c)

    # Now verify systemic alert triggers on the 5th unique customer
    final_a = store.get("c-a")
    assert final_a.cluster.affected_customers == 5
    assert final_a.cluster.systemic_alert is True

    # Complaint F: Same customer + same transaction as A (unresolved)
    c_f = Complaint(
        id="c-f",
        ticket_id="TKT-F",
        channel=Channel.APP,
        raw_text=similar_text,
        masked_text=similar_text,
        customer_id="cust-1",
        transaction_id="tx-1"
    )
    res_f = clustering.check_and_register("c-f", similar_text, customer_id="cust-1", transaction_id="tx-1")
    assert res_f.is_duplicate is True
    assert res_f.duplicate_reason == "exact_id"
    assert res_f.cluster_id == res_a.cluster_id

    # Complaint G: Same customer, different transaction, similar text, <7 days (unresolved)
    c_g = Complaint(
        id="c-g",
        ticket_id="TKT-G",
        channel=Channel.APP,
        raw_text=similar_text,
        masked_text=similar_text,
        customer_id="cust-1",
        transaction_id="tx-other"
    )
    res_g = clustering.check_and_register("c-g", similar_text, customer_id="cust-1", transaction_id="tx-other")
    assert res_g.is_duplicate is True
    assert res_g.duplicate_reason == "semantic_same_customer"
    assert res_g.cluster_id == res_a.cluster_id

    # Complaint H: Unrelated credit card complaint -> should create new singleton cluster
    c_h = Complaint(
        id="c-h",
        ticket_id="TKT-H",
        channel=Channel.APP,
        raw_text=unrelated_text,
        masked_text=unrelated_text,
        customer_id="cust-9",
        transaction_id="tx-9"
    )
    res_h = clustering.check_and_register("c-h", unrelated_text, customer_id="cust-9", transaction_id="tx-9")
    assert res_h.cluster_id != res_a.cluster_id
    assert res_h.is_duplicate is False
    assert res_h.affected_customers == 1
    assert res_h.systemic_alert is False
