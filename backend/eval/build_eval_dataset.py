"""
Script to generate the 120-item Evaluation Dataset (eval_set.jsonl)
and matching ground-truth transactions (transactions.json) for UniResolve.
"""

import json
import os
from datetime import datetime, timedelta

def build_eval_dataset():
    eval_records = []
    transactions = {}

    def add_tx(tx_id, cust_id, amount, status, days_ago, ch, desc):
        t_date = (datetime(2026, 9, 3) - timedelta(days=days_ago)).date().isoformat()
        transactions[tx_id] = {
            "transaction_id": tx_id,
            "customer_id": cust_id,
            "amount": amount,
            "status": status,
            "date": t_date,
            "channel": ch,
            "description": desc,
        }

    # Helper to add an eval record
    def add_rec(
        rec_id, text, ch, cust_id, tx_id, days_ago,
        cat, sev, sent, lang="English",
        is_dup=False, dup_of=None, recurring=False,
        systemic=False, cluster_key=None,
        pii=None, is_spam=False, att_file=None
    ):
        rec = {
            "id": f"EVAL-{rec_id:03d}",
            "raw_text": text,
            "channel": ch,
            "customer_id": cust_id,
            "transaction_id": tx_id,
            "days_ago": days_ago,
            "gold": {
                "category": cat,
                "severity": sev,
                "sentiment": sent,
                "language": lang,
                "is_duplicate": is_dup,
                "duplicate_of": dup_of,
                "recurring": recurring,
                "systemic_member": systemic,
                "cluster_key": cluster_key or f"singleton_{rec_id:03d}",
                "pii_entities": pii or [],
                "is_spam": is_spam,
            }
        }
        if att_file:
            rec["attachment_file"] = att_file
        eval_records.append(rec)

    # ─────────────────────────────────────────────────────────────────────────────
    # 1. Cluster: upi_outage_eval_a (5 distinct customers -> Systemic Outage)
    # ─────────────────────────────────────────────────────────────────────────────
    add_tx("TXN-20001-A", "CUST-20001", "₹2,500.00", "failed", 2, "upi", "UPI/GPay Transfer Failed")
    add_rec(1, "UPI payment of Rs 2500 failed at merchant store but amount debited from my account ref TXN-20001-A.",
            "app", "CUST-20001", "TXN-20001-A", 2, "UPI Failure", "high", "frustrated", systemic=True, cluster_key="upi_outage_eval_a")

    add_rec(2, "UPI transfer of Rs 2500 failed but amount was debited from account ref TXN-20001-A.",
            "web", "CUST-20001", "TXN-20001-A", 1, "UPI Failure", "high", "frustrated", is_dup=True, dup_of="EVAL-001", systemic=True, cluster_key="upi_outage_eval_a")

    add_tx("TXN-20002-A", "CUST-20002", "₹3,200.00", "failed", 2, "upi", "UPI/PhonePe Gateway Timeout")
    add_rec(3, "UPI payment to merchant timed out on UPI gateway but Rs 3200 was deducted from my savings account ref TXN-20002-A.",
            "email", "CUST-20002", "TXN-20002-A", 2, "UPI Failure", "high", "frustrated", systemic=True, cluster_key="upi_outage_eval_a")

    add_tx("TXN-20003-A", "CUST-20003", "₹1,800.00", "failed", 2, "upi", "UPI QuickMart Merchant Timeout")
    add_rec(4, "UPI payment failed error screen attached. The recipient store did not get money but account was debited ref TXN-20003-A.",
            "app", "CUST-20003", "TXN-20003-A", 2, "UPI Failure", "high", "frustrated", systemic=True, cluster_key="upi_outage_eval_a", att_file="upi_failure_receipt.png")

    add_tx("TXN-20004-A", "CUST-20004", "₹4,500.00", "failed", 1, "upi", "UPI Retail Store Failed")
    add_rec(5, "UPI payment of Rs 4500 failed at store but amount debited from my account ref TXN-20004-A. Transcribed IVR voice note.",
            "ivr", "CUST-20004", "TXN-20004-A", 1, "UPI Failure", "high", "frustrated", systemic=True, cluster_key="upi_outage_eval_a", att_file="voice_note.wav")

    add_tx("TXN-20005-A", "CUST-20005", "₹2,100.00", "failed", 1, "upi", "UPI Transfer Timeout")
    add_rec(6, "UPI server timeout during payment transfer, amount was debited from my account ref TXN-20005-A.",
            "social", "CUST-20005", "TXN-20005-A", 1, "UPI Failure", "high", "frustrated", systemic=True, cluster_key="upi_outage_eval_a")

    # ─────────────────────────────────────────────────────────────────────────────
    # 2. Cluster: netbanking_otp_eval (3 distinct customers -> Sub-threshold)
    # ─────────────────────────────────────────────────────────────────────────────
    add_rec(7, "NetBanking portal login failed because OTP was not received on my registered mobile number.",
            "web", "CUST-20001", None, 1, "NetBanking", "medium", "frustrated", systemic=True, cluster_key="netbanking_otp_eval")
    add_rec(8, "Unable to login to NetBanking web portal, SMS OTP is timing out and not arriving on phone.",
            "app", "CUST-20006", None, 1, "NetBanking", "medium", "frustrated", systemic=True, cluster_key="netbanking_otp_eval")
    add_rec(9, "NetBanking login authentication error, OTP SMS not delivered to my registered phone number.",
            "social", "CUST-20007", None, 1, "NetBanking", "medium", "frustrated", systemic=True, cluster_key="netbanking_otp_eval")

    # ─────────────────────────────────────────────────────────────────────────────
    # 3. Cluster: atm_cash_jam_eval (Recurring & Duplicate)
    # ─────────────────────────────────────────────────────────────────────────────
    add_tx("TXN-20002-B", "CUST-20002", "₹5,000.00", "failed", 10, "atm", "ATM Cash Dispense Machine Error")
    add_rec(10, "ATM dispensed Rs 0 but Rs 5000 was debited from my savings account during cash withdrawal ref TXN-20002-B.",
            "branch", "CUST-20002", "TXN-20002-B", 10, "ATM Failure", "high", "frustrated", cluster_key="atm_cash_jam_eval", att_file="atm_slip.png")
    add_rec(11, "ATM dispensed Rs 0 on cash withdrawal and debited my savings account ref TXN-20002-B. The reversal previously approved was reversed back.",
            "app", "CUST-20002", "TXN-20002-B", 2, "ATM Failure", "high", "frustrated", recurring=True, dup_of="EVAL-010", cluster_key="atm_cash_jam_eval")
    add_rec(12, "ATM machine cash error on TXN-20002-B. Reversal of Rs 5000 cancelled again.",
            "web", "CUST-20002", "TXN-20002-B", 1, "ATM Failure", "high", "frustrated", is_dup=True, dup_of="EVAL-010", cluster_key="atm_cash_jam_eval")

    # ─────────────────────────────────────────────────────────────────────────────
    # 4. Cluster: sig_update_eval (Semantic Duplicate, same customer <7 days)
    # ─────────────────────────────────────────────────────────────────────────────
    add_rec(13, "I visited the Andheri West branch to update my signature, but branch staff refused to process my request.",
            "branch", "CUST-20008", None, 3, "Account Services", "medium", "frustrated", cluster_key="sig_update_eval")
    add_rec(14, "Signature update request was rejected by branch staff without explanation. Service is very slow.",
            "web", "CUST-20008", None, 1, "Account Services", "medium", "frustrated", is_dup=True, dup_of="EVAL-013", cluster_key="sig_update_eval")

    # ─────────────────────────────────────────────────────────────────────────────
    # 5. Near-Miss Pair: passbook printer (>7 days apart -> NOT duplicate)
    # ─────────────────────────────────────────────────────────────────────────────
    add_rec(15, "I visited the branch today to update passbook, but the passbook printing kiosk machine was out of order.",
            "web", "CUST-20009", None, 11, "Account Services", "low", "neutral", cluster_key="passbook_near_miss_old")
    add_rec(16, "Branch visit for passbook update failed because the passbook printing machine at counter was out of order.",
            "branch", "CUST-20009", None, 2, "Account Services", "low", "frustrated", cluster_key="passbook_near_miss_new")

    # ─────────────────────────────────────────────────────────────────────────────
    # 6. Cluster: fraud_card_eval (High-Value Fraud HITL)
    # ─────────────────────────────────────────────────────────────────────────────
    add_tx("TXN-20010-F", "CUST-20010", "₹45,000.00", "failed", 1, "card", "Card POS International Charge Disputed")
    add_rec(17, "URGENT: Unauthorized international transaction of Rs 45,000 detected on my credit card! I did not authorize this payment ref TXN-20010-F.",
            "email", "CUST-20010", "TXN-20010-F", 1, "Fraud", "critical", "angry", cluster_key="fraud_card_eval", att_file="card_fraud_alert.png")
    add_rec(18, "Fraudulent international swipe of Rs 45,000 ref TXN-20010-F on my credit card. Immediate chargeback requested.",
            "app", "CUST-20010", "TXN-20010-F", 1, "Fraud", "critical", "angry", is_dup=True, dup_of="EVAL-017", cluster_key="fraud_card_eval")

    # ─────────────────────────────────────────────────────────────────────────────
    # 7. Cluster: double_deduct_emi_eval (Double EMI deduction)
    # ─────────────────────────────────────────────────────────────────────────────
    add_tx("TXN-20011-E", "CUST-20011", "₹18,450.00", "failed", 2, "app", "EMI/Home Loan Double Debit Duplicate")
    add_rec(19, "Home loan EMI of Rs 18,450 was debited twice from my account this month ref TXN-20011-E.",
            "app", "CUST-20011", "TXN-20011-E", 2, "Double Deduction", "high", "frustrated", cluster_key="double_deduct_emi_eval")
    add_rec(20, "Double deduction of home loan EMI Rs 18,450 on ref TXN-20011-E. Please reverse the second installment.",
            "web", "CUST-20011", "TXN-20011-E", 1, "Double Deduction", "high", "frustrated", is_dup=True, dup_of="EVAL-019", cluster_key="double_deduct_emi_eval")

    # ─────────────────────────────────────────────────────────────────────────────
    # 8. Cluster: kyc_delay_eval (KYC Verification Delays)
    # ─────────────────────────────────────────────────────────────────────────────
    add_rec(21, "Submitted physical KYC documents at branch 15 days ago but account remains frozen and restricted.",
            "branch", "CUST-20012", None, 5, "KYC Verification", "medium", "frustrated", systemic=True, cluster_key="kyc_delay_eval")
    add_rec(22, "My savings account is locked because KYC verification submitted at branch two weeks ago is still pending.",
            "email", "CUST-20013", None, 4, "KYC Verification", "medium", "frustrated", systemic=True, cluster_key="kyc_delay_eval")
    add_rec(23, "Account debit freeze active despite submitting physical KYC verification form at branch over 14 days ago.",
            "web", "CUST-20014", None, 3, "KYC Verification", "medium", "frustrated", systemic=True, cluster_key="kyc_delay_eval")

    # ─────────────────────────────────────────────────────────────────────────────
    # 9. Cluster: card_pos_decline_eval (Card swipe declines)
    # ─────────────────────────────────────────────────────────────────────────────
    add_tx("TXN-20015-C", "CUST-20015", "₹3,500.00", "failed", 2, "card", "Card POS Debit Swipe Blocked")
    add_rec(24, "Debit card swipe failed at shopping mall POS terminal but money was deducted from balance ref TXN-20015-C.",
            "app", "CUST-20015", "TXN-20015-C", 2, "Card Blocking", "high", "frustrated", cluster_key="card_pos_decline_eval")
    add_rec(25, "Debit card swipe failed at POS terminal and money was deducted from balance ref TXN-20015-C.",
            "ivr", "CUST-20015", "TXN-20015-C", 1, "Card Blocking", "high", "frustrated", is_dup=True, dup_of="EVAL-024", cluster_key="card_pos_decline_eval")

    # ─────────────────────────────────────────────────────────────────────────────
    # 10. Vernacular Records (Hindi 18, Marathi 8, Hinglish 4)
    # ─────────────────────────────────────────────────────────────────────────────
    # Hindi (18)
    add_rec(26, "मेरा फिक्स्ड डिपॉजिट रिन्यूअल फॉर्म शाखा में जमा करने के बाद भी प्रोसेस नहीं हुआ है। कृपया मेरी मदद करें।",
            "branch", "CUST-20016", None, 4, "Account Services", "medium", "frustrated", lang="Hindi", cluster_key="hindi_fd_01")
    add_tx("TXN-20017-H", "CUST-20017", "₹15,000.00", "failed", 2, "branch", "Cheque Inward Clearing Return")
    add_rec(27, "शाखा में जमा किया गया चेक बिना किसी कारण के वापस कर दिया गया है। संदर्भ TXN-20017-H। कृपया जांच करें।",
            "branch", "CUST-20017", "TXN-20017-H", 2, "Account Services", "high", "frustrated", lang="Hindi", cluster_key="hindi_cheque_01")
    add_tx("TXN-20018-H", "CUST-20018", "₹2,000.00", "failed", 1, "upi", "UPI Transfer Failed Hindi")
    add_rec(28, "यूपीआई से पैसे कट गए लेकिन दुकानदार को नहीं मिले। संदर्भ TXN-20018-H तुरंत पैसे वापस करें।",
            "app", "CUST-20018", "TXN-20018-H", 1, "UPI Failure", "high", "angry", lang="Hindi", cluster_key="hindi_upi_01")
    add_rec(29, "एटीएम मशीन से पैसे नहीं निकले लेकिन खाते से 4000 रुपये कट गए। कृपया समाधान करें।",
            "ivr", "CUST-20019", None, 2, "ATM Failure", "high", "frustrated", lang="Hindi", cluster_key="hindi_atm_01")
    add_rec(30, "इंटरनेट बैंकिंग का पासवर्ड रीसेट करने का ओटीपी मोबाइल पर नहीं आ रहा है।",
            "web", "CUST-20020", None, 1, "NetBanking", "medium", "frustrated", lang="Hindi", cluster_key="hindi_nb_01")
    add_rec(31, "शाखा प्रबंधक का व्यवहार ग्राहकों के साथ बहुत अशोभनीय और असभ्य था।",
            "branch", "CUST-20021", None, 3, "Staff Misconduct", "medium", "angry", lang="Hindi", cluster_key="hindi_staff_01")
    add_rec(32, "केवाईसी दस्तावेज शाखा में जमा किए थे परंतु खाता अभी भी ब्लॉक है।",
            "branch", "CUST-20022", None, 6, "KYC Verification", "medium", "frustrated", lang="Hindi", cluster_key="hindi_kyc_01")
    add_tx("TXN-20023-H", "CUST-20023", "₹25,000.00", "failed", 1, "card", "Unauthorized Card Charge Hindi")
    add_rec(33, "क्रेडिट कार्ड से बिना ओटीपी के 25000 रुपये का अनधिकृत लेनदेन हुआ है। संदर्भ TXN-20023-H। कार्ड ब्लॉक करें।",
            "email", "CUST-20023", "TXN-20023-H", 1, "Fraud", "critical", "angry", lang="Hindi", cluster_key="hindi_fraud_01")
    # Duplicate for Hindi fraud
    add_rec(34, "क्रेडिट कार्ड पर बिना ओटीपी 25000 रुपये का गलत लेनदेन हुआ है संदर्भ TXN-20023-H।",
            "social", "CUST-20023", "TXN-20023-H", 1, "Fraud", "critical", "angry", lang="Hindi", is_dup=True, dup_of="EVAL-033", cluster_key="hindi_fraud_01")
    add_rec(35, "पेंशन खाते में इस माह की पेंशन अभी तक जमा नहीं की गई है। कृपया तुरंत देखें।",
            "ivr", "CUST-20025", None, 3, "Account Services", "high", "frustrated", lang="Hindi", cluster_key="hindi_pension_01")
    add_rec(36, "डेबिट कार्ड गुम हो गया है परंतु कस्टमर केयर नंबर पर कॉल कनेक्ट नहीं हो रही है।",
            "ivr", "CUST-20026", None, 1, "Card Blocking", "critical", "angry", lang="Hindi", cluster_key="hindi_cardblock_01")
    add_rec(37, "गृह ऋण का ब्याज प्रमाण पत्र शाखा द्वारा समय पर जारी नहीं किया गया।",
            "email", "CUST-20027", None, 8, "Loan Foreclosure", "medium", "frustrated", lang="Hindi", cluster_key="hindi_loan_01")
    add_rec(38, "पासबुक प्रिंटिंग मशीन हमेशा खराब रहती है और शाखा कर्मचारी एंट्री करने से मना करते हैं।",
            "branch", "CUST-20028", None, 4, "Account Services", "low", "frustrated", lang="Hindi", cluster_key="hindi_passbook_01")
    add_tx("TXN-20029-H", "CUST-20029", "₹12,000.00", "failed", 2, "app", "EMI Double Deduction Hindi")
    add_rec(39, "कार लोन की ईएमआई 12000 रुपये दो बार काट ली गई है संदर्भ TXN-20029-H। अतिरिक्त राशि वापस करें।",
            "app", "CUST-20029", "TXN-20029-H", 2, "Double Deduction", "high", "frustrated", lang="Hindi", cluster_key="hindi_doublededuct_01")
    add_rec(40, "मोबाइल बैंकिंग ऐप अपडेट के बाद बार-बार क्रैश हो रहा है और खुल नहीं रहा।",
            "social", "CUST-20030", None, 1, "NetBanking", "low", "frustrated", lang="Hindi", cluster_key="hindi_appcrash_01")
    add_rec(41, "वरिष्ठ नागरिक बचत योजना पर मिलने वाला अतिरिक्त ब्याज खाते में नहीं जुड़ा।",
            "branch", "CUST-20031", None, 12, "Account Services", "medium", "frustrated", lang="Hindi", cluster_key="hindi_sr_citizen_01")
    add_rec(42, "शाखा में काउंटर पर कैशियर का रवैया बहुत धीमा और असहयोगी है।",
            "branch", "CUST-20032", None, 2, "Staff Misconduct", "low", "frustrated", lang="Hindi", cluster_key="hindi_cashier_01")
    add_rec(43, "फास्टैग वॉलेट में 500 रुपये डाले थे लेकिन बैलेंस अपडेट नहीं हुआ।",
            "social", "CUST-20033", None, 2, "Account Services", "low", "neutral", lang="Hindi", cluster_key="hindi_fastag_01")

    # Marathi (8)
    add_tx("TXN-20034-M", "CUST-20034", "₹18,450.00", "failed", 2, "app", "Home Loan EMI Marathi")
    add_rec(44, "माझ्या खात्यातून गृहकर्जाचा ईएमआय १८,४५० रुपये दोनदा कापला गेला आहे. संदर्भ TXN-20034-M. कृपया त्वरित परतावा द्या.",
            "app", "CUST-20034", "TXN-20034-M", 2, "Double Deduction", "high", "frustrated", lang="Marathi", cluster_key="marathi_emi_01")
    add_rec(45, "गृहकर्ज ईएमआय १८,४५० रुपये खात्यातून दोनदा वजा झाला आहे संदर्भ TXN-20034-M.",
            "social", "CUST-20034", "TXN-20034-M", 1, "Double Deduction", "high", "frustrated", lang="Marathi", is_dup=True, dup_of="EVAL-044", cluster_key="marathi_emi_01")
    add_tx("TXN-20036-M", "CUST-20036", "₹3,000.00", "failed", 1, "upi", "UPI Failure Marathi")
    add_rec(46, "युपीआय ट्रान्सफर अयशस्वी झाले पण खात्यातून ३००० रुपये वजा झाले. संदर्भ TXN-20036-M.",
            "social", "CUST-20036", "TXN-20036-M", 1, "UPI Failure", "high", "frustrated", lang="Marathi", cluster_key="marathi_upi_01")
    add_rec(47, "एटीएम मधून पैसे निघाले नाहीत पण खात्यातून ५००० रुपये कमी झाले. त्वरित मदत करा.",
            "ivr", "CUST-20037", None, 2, "ATM Failure", "high", "frustrated", lang="Marathi", cluster_key="marathi_atm_01")
    add_rec(48, "माझे पॅन कार्ड बँक खात्याशी लिंक केले होते तरीही टीडीएस जास्त कापला गेला आहे.",
            "email", "CUST-20038", None, 7, "Account Services", "medium", "frustrated", lang="Marathi", cluster_key="marathi_tds_01")
    add_rec(49, "शाखा व्यवस्थापकांचे ग्राहकांशी बोलणे अत्यंत उद्धट आणि अपमानास्पद होते.",
            "branch", "CUST-20039", None, 4, "Staff Misconduct", "medium", "angry", lang="Marathi", cluster_key="marathi_manager_01")
    add_rec(50, "नवीन चेकबुकची विनंती करून महिना उलटला तरी चेकबुक घरी पोहोचले नाही.",
            "web", "CUST-20040", None, 15, "Account Services", "low", "neutral", lang="Marathi", cluster_key="marathi_chequebook_01")
    add_tx("TXN-20041-M", "CUST-20041", "₹35,000.00", "failed", 1, "card", "Credit Card Fraud Marathi")
    add_rec(51, "क्रेडिट कार्डवरून ३५००० रुपयांचा संशयास्पद व्यवहार झाला आहे. संदर्भ TXN-20041-M. कार्ड तात्काळ ब्लॉक करा.",
            "social", "CUST-20041", "TXN-20041-M", 1, "Fraud", "critical", "angry", lang="Marathi", cluster_key="marathi_fraud_01")

    # Hinglish (4)
    add_tx("TXN-20042-HG", "CUST-20042", "₹12,000.00", "failed", 1, "netbanking", "IMPS Transfer Pending Hinglish")
    add_rec(52, "Bhai mera IMPS transfer pending show ho raha hai aur account se Rs 12000 cut ho gaye ref TXN-20042-HG. Please jaldi reverse karo.",
            "social", "CUST-20042", "TXN-20042-HG", 1, "UPI Failure", "medium", "frustrated", lang="Hinglish", cluster_key="hinglish_imps_01")
    add_rec(53, "NetBanking app me login karte time OTP nahi aa raha phone pe. Server issue fix karo please.",
            "social", "CUST-20043", None, 1, "NetBanking", "low", "frustrated", lang="Hinglish", cluster_key="hinglish_nb_01")
    add_tx("TXN-20044-HG", "CUST-20044", "₹4,000.00", "failed", 2, "atm", "ATM Cash Stuck Hinglish")
    add_rec(54, "ATM machine me cash atak gaya aur receipt me transaction failed aaya but Rs 4000 debit ho gaya ref TXN-20044-HG.",
            "ivr", "CUST-20044", "TXN-20044-HG", 2, "ATM Failure", "high", "frustrated", lang="Hinglish", cluster_key="hinglish_atm_01")
    add_rec(55, "Branch staff ne KYC form submit karne ke baad bhi account unfreeze nahi kiya. Super bad service.",
            "social", "CUST-20045", None, 3, "KYC Verification", "medium", "frustrated", lang="Hinglish", cluster_key="hinglish_kyc_01")

    # ─────────────────────────────────────────────────────────────────────────────
    # 11. Hard Negatives (15 Pairs = 30 distinct complaints)
    # ─────────────────────────────────────────────────────────────────────────────
    # Pair 1: UPI Merchant payment vs UPI Peer-to-Peer refund
    add_tx("TXN-20050-HN1A", "CUST-20050", "₹1,500.00", "failed", 2, "upi", "UPI Swiggy Food Merchant")
    add_rec(56, "UPI payment to Swiggy merchant failed at billing checkout ref TXN-20050-HN1A.",
            "app", "CUST-20050", "TXN-20050-HN1A", 2, "UPI Failure", "medium", "frustrated", cluster_key="hard_neg_01a")
    add_tx("TXN-20051-HN1B", "CUST-20051", "₹1,500.00", "success", 2, "upi", "UPI Peer Transfer Reversal")
    add_rec(57, "UPI peer transfer sent to friend was reversed back to bank ledger successfully ref TXN-20051-HN1B.",
            "app", "CUST-20051", "TXN-20051-HN1B", 2, "UPI Failure", "low", "satisfied", cluster_key="hard_neg_01b")

    # Pair 2: ATM cash dispensing jam vs ATM swallowed card
    add_tx("TXN-20052-HN2A", "CUST-20052", "₹8,000.00", "failed", 3, "atm", "ATM Cash Dispenser Stuck")
    add_rec(58, "ATM cash dispensing shutter did not open during cash withdrawal ref TXN-20052-HN2A.",
            "branch", "CUST-20052", "TXN-20052-HN2A", 3, "ATM Failure", "high", "frustrated", cluster_key="hard_neg_02a")
    add_rec(59, "ATM machine card reader retained and swallowed my debit card without returning it.",
            "branch", "CUST-20053", None, 3, "ATM Failure", "high", "angry", cluster_key="hard_neg_02b")

    # Pair 3: NetBanking login OTP delayed vs NetBanking password change lockout
    add_rec(60, "NetBanking SMS verification code arrived 45 minutes late during login attempt.",
            "web", "CUST-20054", None, 1, "NetBanking", "medium", "frustrated", cluster_key="hard_neg_03a")
    add_rec(61, "NetBanking user ID got permanently locked after three incorrect profile password entries.",
            "web", "CUST-20055", None, 1, "NetBanking", "medium", "frustrated", cluster_key="hard_neg_03b")

    # Pair 4: Credit card unauthorized international charge vs Annual card maintenance fee dispute
    add_tx("TXN-20056-HN4A", "CUST-20056", "₹55,000.00", "failed", 1, "card", "Unauthorized POS Tokyo")
    add_rec(62, "Unauthorized international POS transaction in Tokyo detected on credit card ref TXN-20056-HN4A.",
            "email", "CUST-20056", "TXN-20056-HN4A", 1, "Fraud", "critical", "angry", cluster_key="hard_neg_04a")
    add_rec(63, "Credit card annual renewal fee of Rs 1,500 was levied despite lifetime free card promise.",
            "email", "CUST-20057", None, 4, "Card Blocking", "low", "frustrated", cluster_key="hard_neg_04b")

    # Pair 5: Home loan double EMI debit vs Home loan interest rate reduction inquiry
    add_tx("TXN-20058-HN5A", "CUST-20058", "₹22,000.00", "failed", 2, "app", "Home Loan EMI Duplicate")
    add_rec(64, "Home loan monthly installment deducted twice in single billing cycle ref TXN-20058-HN5A.",
            "app", "CUST-20058", "TXN-20058-HN5A", 2, "Double Deduction", "high", "frustrated", cluster_key="hard_neg_05a")
    add_rec(65, "Requesting home loan interest rate switch to current external benchmark repo linked rate.",
            "email", "CUST-20059", None, 10, "Loan Foreclosure", "low", "neutral", cluster_key="hard_neg_05b")

    # Pair 6: KYC physical document rejected vs KYC video call reconnection drop
    add_rec(66, "Branch compliance officer rejected physical utility bill electricity copy for address proof.",
            "branch", "CUST-20060", None, 5, "KYC Verification", "medium", "frustrated", cluster_key="hard_neg_06a")
    add_rec(67, "Video KYC call with bank verification officer got repeatedly disconnected due to app server glitch.",
            "app", "CUST-20061", None, 2, "KYC Verification", "medium", "frustrated", cluster_key="hard_neg_06b")

    # Pair 7: Debit card PIN blocked vs Debit card chip hardware read failure
    add_rec(68, "Debit card ATM PIN blocked due to consecutive incorrect attempts by customer.",
            "ivr", "CUST-20062", None, 1, "Card Blocking", "medium", "neutral", cluster_key="hard_neg_07a")
    add_rec(69, "EMV chip on new platinum debit card is damaged and unreadable across all POS terminals.",
            "branch", "CUST-20063", None, 4, "Card Blocking", "low", "frustrated", cluster_key="hard_neg_07b")

    # Pair 8: Signature mismatch on cheque vs Signature update on savings account
    add_tx("TXN-20064-HN8A", "CUST-20064", "₹50,000.00", "failed", 2, "branch", "Cheque Signature Mismatch")
    add_rec(70, "Cheque returned due to signature mismatch on clearing portal ref TXN-20064-HN8A.",
            "branch", "CUST-20064", "TXN-20064-HN8A", 2, "Account Services", "high", "frustrated", cluster_key="hard_neg_08a")
    add_rec(71, "Submitted signature modification mandate form with gazetted officer attestation at branch.",
            "branch", "CUST-20065", None, 6, "Account Services", "low", "neutral", cluster_key="hard_neg_08b")

    # Pair 9: Cheque clearance bounce vs Cheque book delivery dispatch tracking
    add_tx("TXN-20066-HN9A", "CUST-20066", "₹30,000.00", "failed", 2, "branch", "Inward Cheque Return Insufficient Funds")
    add_rec(72, "Inward clearing cheque returned unpaid with Rs 590 penal penalty fee ref TXN-20066-HN9A.",
            "email", "CUST-20066", "TXN-20066-HN9A", 2, "Account Services", "high", "angry", cluster_key="hard_neg_09a")
    add_rec(73, "Cheque book ordered via mobile app has invalid Speed Post consignment tracking number.",
            "app", "CUST-20067", None, 9, "Account Services", "low", "neutral", cluster_key="hard_neg_09b")

    # Pair 10: Savings account auto-debit NACH failure vs Minimum balance penalty charge
    add_tx("TXN-20068-HN10A", "CUST-20068", "₹5,000.00", "failed", 3, "netbanking", "NACH Mandate Mutual Fund Failed")
    add_rec(74, "Mutual fund SIP NACH mandate failed to debit despite sufficient account balance ref TXN-20068-HN10A.",
            "web", "CUST-20068", "TXN-20068-HN10A", 3, "Account Services", "medium", "frustrated", cluster_key="hard_neg_10a")
    add_rec(75, "Unfair quarterly average minimum balance penalty of Rs 354 deducted from student savings account.",
            "email", "CUST-20069", None, 5, "Account Services", "low", "angry", cluster_key="hard_neg_10b")

    # Pair 11: Safe deposit locker access appointment vs Locker annual rent auto-debit
    add_rec(76, "Branch custodian refused entry to safe deposit locker vault without prior branch appointment.",
            "branch", "CUST-20070", None, 2, "Account Services", "medium", "frustrated", cluster_key="hard_neg_11a")
    add_rec(77, "Locker annual rent of Rs 4,500 auto-debited twice in single financial year from savings account.",
            "email", "CUST-20071", None, 8, "Double Deduction", "medium", "frustrated", cluster_key="hard_neg_11b")

    # Pair 12: Demat account linking delay vs Demat dividend credit delay
    add_rec(78, "3-in-1 Demat and trading account linking request pending with operations desk for three weeks.",
            "web", "CUST-20072", None, 14, "Account Services", "medium", "neutral", cluster_key="hard_neg_12a")
    add_rec(79, "TCS company equity dividend declared on Demat account not credited to linked bank savings account.",
            "web", "CUST-20073", None, 6, "Account Services", "low", "neutral", cluster_key="hard_neg_12b")

    # Pair 13: Foreign inward remittance pending vs Domestic RTGS delayed credit
    add_tx("TXN-20074-HN13A", "CUST-20074", "₹1,25,000.00", "pending", 4, "netbanking", "FCNR Foreign Inward Wire")
    add_rec(80, "USD inward SWIFT remittance wire transfer pending at central forex treasury desk ref TXN-20074-HN13A.",
            "email", "CUST-20074", "TXN-20074-HN13A", 4, "Account Services", "high", "frustrated", cluster_key="hard_neg_13a")
    add_tx("TXN-20075-HN13B", "CUST-20075", "₹2,50,000.00", "failed", 1, "netbanking", "RTGS Real Time Settlement Delayed")
    add_rec(81, "High-value RTGS interbank transfer of Rs 2,50,000 not credited to beneficiary bank ref TXN-20075-HN13B.",
            "branch", "CUST-20075", "TXN-20075-HN13B", 1, "Account Services", "high", "angry", cluster_key="hard_neg_13b")

    # Pair 14: Fixed deposit pre-mature closure penalty vs Fixed deposit TDS tax certificate
    add_rec(82, "Unjust 1% pre-mature penalty deduction levied during emergency fixed deposit liquidation.",
            "branch", "CUST-20076", None, 7, "Account Services", "medium", "frustrated", cluster_key="hard_neg_14a")
    add_rec(83, "Form 16A TDS interest tax deduction certificate for fixed deposit has incorrect PAN mapped.",
            "web", "CUST-20077", None, 12, "Account Services", "low", "neutral", cluster_key="hard_neg_14b")

    # Pair 15: Fastag toll plaza double deduction vs Fastag wallet low balance false alarm
    add_tx("TXN-20078-HN15A", "CUST-20078", "₹450.00", "failed", 2, "upi", "Fastag Toll Double Deduction")
    add_rec(84, "Khed-Shivapur toll plaza RFID scanner debited Fastag wallet twice for single crossing ref TXN-20078-HN15A.",
            "app", "CUST-20078", "TXN-20078-HN15A", 2, "Double Deduction", "low", "frustrated", cluster_key="hard_neg_15a")
    add_rec(85, "Continuous SMS warning for Fastag low balance received despite wallet balance exceeding Rs 1,500.",
            "social", "CUST-20079", None, 3, "Account Services", "low", "neutral", cluster_key="hard_neg_15b")

    # ─────────────────────────────────────────────────────────────────────────────
    # 12. PII-Heavy Masking Test Records (3 Records)
    # ─────────────────────────────────────────────────────────────────────────────
    add_tx("TXN-20080-PII", "CUST-20080", "₹12,400.00", "failed", 2, "card", "Disputed Card Transaction PII")
    add_rec(86, "Dispute on card charge ref TXN-20080-PII. My Aadhaar is 4532 8901 2345, PAN is ABCDE1234F, and phone is 9876543210.",
            "web", "CUST-20080", "TXN-20080-PII", 2, "Fraud", "high", "frustrated", pii=["AADHAAR", "PAN", "MOBILE"], cluster_key="pii_rec_01")
    add_tx("TXN-20081-PII", "CUST-20081", "₹7,500.00", "failed", 1, "card", "Card Fraud Online POS")
    add_rec(87, "Unauthorized card transaction ref TXN-20081-PII. Card number is 4532-7589-1234-5678, registered email is customer.test@email.com.",
            "email", "CUST-20081", "TXN-20081-PII", 1, "Fraud", "high", "angry", pii=["CARD_NUMBER", "EMAIL"], cluster_key="pii_rec_02")
    add_rec(88, "Please update my mobile number 9123456789 and PAN number PQRST9876A in bank records for customer profile CUST-20082.",
            "branch", "CUST-20082", None, 3, "KYC Verification", "medium", "neutral", pii=["PAN", "MOBILE"], cluster_key="pii_rec_03")

    # ─────────────────────────────────────────────────────────────────────────────
    # 13. Spam / Non-Grievance Noise Records (2 Records)
    # ─────────────────────────────────────────────────────────────────────────────
    add_rec(89, "CONGRATULATIONS! You have won Rs 50,00,000 in the International Reserve Bank Lottery. Click here to claim your cash reward immediately.",
            "email", "CUST-20083", None, 1, "General Support", "low", "satisfied", is_spam=True, cluster_key="spam_lottery_01")
    add_rec(90, "Earn 500% daily guaranteed profit on crypto binary trading platform with automated trading signals. WhatsApp on 9988776655.",
            "social", "CUST-20084", None, 1, "General Support", "low", "satisfied", is_spam=True, cluster_key="spam_crypto_02")

    # ─────────────────────────────────────────────────────────────────────────────
    # 14. SLA Aging Records (28d Escalated & 33d Ombudsman Eligible)
    # ─────────────────────────────────────────────────────────────────────────────
    add_rec(91, "Formal home loan foreclosure certificate request submitted 28 days ago still pending nodal officer approval.",
            "branch", "CUST-20085", None, 28, "Loan Foreclosure", "high", "frustrated", cluster_key="aging_foreclosure_28d")
    add_rec(92, "Formal complaint regarding senior citizen fixed deposit rate submitted 33 days ago without resolution from principal nodal officer.",
            "email", "CUST-20086", None, 33, "Account Services", "high", "frustrated", cluster_key="aging_fd_ombudsman_33d")

    # ─────────────────────────────────────────────────────────────────────────────
    # 15. Balanced Enterprise Banking Clusters & Duplicates (93 to 120 = 28 records)
    # Ensuring ~21-22 total duplicate & recurring count across the 120 records
    # ─────────────────────────────────────────────────────────────────────────────
    # 93: Loan Title Deeds Parent
    add_rec(93, "Home loan original property title deed documents not returned after complete loan closure 45 days ago.",
            "branch", "CUST-20087", None, 15, "Loan Foreclosure", "critical", "angry", cluster_key="loan_title_deeds_01")
    # 94: Loan Title Deeds Duplicate
    add_rec(94, "Bank has not returned my original house property title deeds despite full loan foreclosure clearance.",
            "email", "CUST-20087", None, 14, "Loan Foreclosure", "critical", "angry", is_dup=True, dup_of="EVAL-093", cluster_key="loan_title_deeds_01")
    
    # 95: Fraud UPI Phishing Parent
    add_tx("TXN-20088-F", "CUST-20088", "₹75,000.00", "failed", 1, "upi", "Phishing VPA Collect Request")
    add_rec(95, "Phishing collect request approved accidentally on UPI app, Rs 75,000 drained ref TXN-20088-F. Freeze account.",
            "ivr", "CUST-20088", "TXN-20088-F", 1, "Fraud", "critical", "angry", cluster_key="fraud_phishing_01")
    # 96: Fraud UPI Phishing Duplicate
    add_rec(96, "Phishing collect request approved accidentally on UPI app, Rs 75,000 drained ref TXN-20088-F.",
            "app", "CUST-20088", "TXN-20088-F", 1, "Fraud", "critical", "angry", is_dup=True, dup_of="EVAL-095", cluster_key="fraud_phishing_01")

    # 97: ATM Dispense Error Parent
    add_tx("TXN-20089-A", "CUST-20089", "₹10,000.00", "failed", 4, "atm", "ATM Cash Shortage Dispense")
    add_rec(97, "ATM dispensed only Rs 2000 cash but debited Rs 10,000 from account ref TXN-20089-A.",
            "branch", "CUST-20089", "TXN-20089-A", 4, "ATM Failure", "high", "frustrated", cluster_key="atm_short_dispense_01")
    # 98: ATM Dispense Error Duplicate
    add_rec(98, "ATM dispensed only Rs 2000 cash and debited Rs 10,000 from account ref TXN-20089-A.",
            "ivr", "CUST-20089", "TXN-20089-A", 3, "ATM Failure", "high", "frustrated", is_dup=True, dup_of="EVAL-097", cluster_key="atm_short_dispense_01")

    # 99: Double Deduction POS Parent
    add_tx("TXN-20091-DD", "CUST-20091", "₹6,400.00", "failed", 3, "card", "POS Double Debit Electronics")
    add_rec(99, "Electronics store POS swipe deducted Rs 6,400 twice on single purchase invoice ref TXN-20091-DD.",
            "web", "CUST-20091", "TXN-20091-DD", 3, "Double Deduction", "high", "frustrated", cluster_key="dd_pos_electronics_01")
    # 100: Double Deduction Duplicate
    add_rec(100, "Two debits of Rs 6,400 for single electronics POS payment on ref TXN-20091-DD.",
            "email", "CUST-20091", "TXN-20091-DD", 2, "Double Deduction", "high", "frustrated", is_dup=True, dup_of="EVAL-099", cluster_key="dd_pos_electronics_01")

    # 101: KYC NRI Document Parent
    add_rec(101, "NRE account KYC re-verification documents submitted via Indian Embassy attestation not processed.",
            "email", "CUST-20092", None, 18, "KYC Verification", "medium", "neutral", cluster_key="kyc_nre_embassy_01")
    # 102: KYC NRI Document Duplicate
    add_rec(102, "NRE account KYC re-verification documents submitted via embassy attestation are still not processed.",
            "web", "CUST-20092", None, 17, "KYC Verification", "medium", "frustrated", is_dup=True, dup_of="EVAL-101", cluster_key="kyc_nre_embassy_01")

    # 103: Mobile App Biometric Crash Parent
    add_rec(103, "Mobile banking application crashes continuously on biometric fingerprint sensor scan.",
            "app", "CUST-20094", None, 1, "NetBanking", "medium", "frustrated", cluster_key="app_biometric_crash_01")
    # 104: Mobile App Biometric Crash Duplicate
    add_rec(104, "Fingerprint login crashes the mobile banking app on launch every single time.",
            "social", "CUST-20094", None, 1, "NetBanking", "medium", "frustrated", is_dup=True, dup_of="EVAL-103", cluster_key="app_biometric_crash_01")

    # 105: Loan Foreclosure NOC Parent
    add_rec(105, "Car loan closure No Objection Certificate (NOC) and RTO Form 35 not provided by loan branch.",
            "web", "CUST-20095", None, 20, "Loan Foreclosure", "medium", "frustrated", cluster_key="loan_noc_car_01")
    # 106: Loan Foreclosure NOC Duplicate
    add_rec(106, "Car loan closure No Objection Certificate and Form 35 not released by the loan branch.",
            "email", "CUST-20095", None, 19, "Loan Foreclosure", "medium", "frustrated", is_dup=True, dup_of="EVAL-105", cluster_key="loan_noc_car_01")

    # 107: UPI QR Code Failure Parent
    add_tx("TXN-20097-U", "CUST-20097", "₹850.00", "failed", 1, "upi", "UPI Static QR Scanner Failed")
    add_rec(107, "Static BharatQR code scan failed at pharmacy store but amount deducted ref TXN-20097-U.",
            "app", "CUST-20097", "TXN-20097-U", 1, "UPI Failure", "medium", "frustrated", cluster_key="upi_static_qr_01")
    # 108: UPI QR Code Failure Duplicate
    add_rec(108, "BharatQR code scan payment failed at pharmacy store but amount was debited ref TXN-20097-U.",
            "social", "CUST-20097", "TXN-20097-U", 1, "UPI Failure", "medium", "frustrated", is_dup=True, dup_of="EVAL-107", cluster_key="upi_static_qr_01")

    # 109: Double Deduction EMI Car Loan Parent
    add_tx("TXN-20105-DD", "CUST-20105", "₹14,500.00", "failed", 3, "netbanking", "Car Loan EMI Duplicate Auto Debit")
    add_rec(109, "Car loan EMI of Rs 14,500 deducted twice in current calendar month ref TXN-20105-DD.",
            "web", "CUST-20105", "TXN-20105-DD", 3, "Double Deduction", "high", "frustrated", cluster_key="dd_car_loan_01")
    # 110: Double Deduction EMI Car Loan Duplicate
    add_rec(110, "Two deductions of Rs 14,500 for single car loan EMI on ref TXN-20105-DD.",
            "app", "CUST-20105", "TXN-20105-DD", 2, "Double Deduction", "high", "frustrated", is_dup=True, dup_of="EVAL-109", cluster_key="dd_car_loan_01")

    # 111: Card Blocking Urgent Parent
    add_rec(111, "Lost wallet with platinum credit card and debit card. Need immediate blocking of all cards.",
            "ivr", "CUST-20090", None, 0, "Card Blocking", "critical", "angry", cluster_key="card_lost_urgent_01")
    # 112: Card Blocking Urgent Duplicate
    add_rec(112, "Lost wallet with credit card and debit card. Please block both cards immediately.",
            "app", "CUST-20090", None, 0, "Card Blocking", "critical", "angry", is_dup=True, dup_of="EVAL-111", cluster_key="card_lost_urgent_01")

    # 113: Card International Surcharge Dispute Parent
    add_tx("TXN-20098-C", "CUST-20098", "₹1,200.00", "failed", 5, "card", "Foreign Currency Markup Dispute")
    add_rec(113, "Excessive 5% foreign markup fee charged on international software subscription ref TXN-20098-C.",
            "email", "CUST-20098", "TXN-20098-C", 5, "Card Blocking", "medium", "neutral", cluster_key="card_markup_dispute_01")
    # 114: Card International Surcharge Dispute Duplicate
    add_rec(114, "Excessive 5 percent foreign currency markup fee charged on international subscription ref TXN-20098-C.",
            "web", "CUST-20098", "TXN-20098-C", 4, "Card Blocking", "medium", "frustrated", is_dup=True, dup_of="EVAL-113", cluster_key="card_markup_dispute_01")

    # 115: Happy Path Loan Disbursal
    add_rec(115, "Personal loan sanction and disbursement process was completed within 24 hours. Excellent support.",
            "web", "CUST-20101", None, 0, "Loan Foreclosure", "low", "satisfied", cluster_key="happy_loan_disbursal_01")
    # 116: Happy Path UPI Instant Refund
    add_rec(116, "UPI dispute auto-refunded to savings bank account within 2 hours. Appreciate the fast turnaround.",
            "app", "CUST-20102", None, 0, "UPI Failure", "low", "satisfied", cluster_key="happy_upi_refund_01")
    # 117: Happy Path NetBanking Fixed Deposit
    add_rec(117, "Online term deposit receipt downloaded instantly without visiting branch. Very smooth web interface.",
            "web", "CUST-20103", None, 0, "Account Services", "low", "satisfied", cluster_key="happy_fd_online_01")
    # 118: ATM PIN Generation
    add_rec(118, "Green PIN generation through SMS and IVR banking system worked perfectly on first attempt.",
            "ivr", "CUST-20104", None, 0, "Card Blocking", "low", "satisfied", cluster_key="happy_green_pin_01")

    # 119: Fraud UPI QR Malicious Parent
    add_tx("TXN-20107-F", "CUST-20107", "₹15,000.00", "failed", 1, "upi", "Malicious UPI QR Phishing")
    add_rec(119, "Scam QR code scanned at parking lot transferred Rs 15,000 to fraudster VPA ref TXN-20107-F.",
            "social", "CUST-20107", "TXN-20107-F", 1, "Fraud", "critical", "angry", cluster_key="fraud_scam_qr_01")
    # 120: Fraud UPI QR Malicious Duplicate
    add_rec(120, "Scam QR code scanned at parking lot transferred Rs 15,000 to fraudster VPA ref TXN-20107-F.",
            "app", "CUST-20107", "TXN-20107-F", 1, "Fraud", "critical", "angry", is_dup=True, dup_of="EVAL-119", cluster_key="fraud_scam_qr_01")

    # Write files
    eval_dir = os.path.join("eval")
    os.makedirs(eval_dir, exist_ok=True)

    jsonl_path = os.path.join(eval_dir, "eval_set.jsonl")
    with open(jsonl_path, "w", encoding="utf-8") as f:
        for r in eval_records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    tx_path = os.path.join(eval_dir, "transactions.json")
    with open(tx_path, "w", encoding="utf-8") as f:
        json.dump(transactions, f, indent=2, ensure_ascii=False)

    print(f"Generated {len(eval_records)} evaluation records in {jsonl_path}")
    print(f"Generated {len(transactions)} transactions in {tx_path}")

if __name__ == "__main__":
    build_eval_dataset()
