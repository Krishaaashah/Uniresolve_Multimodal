"""
Training Harness for UniResolve Fusion Models.
Trains:
- E2: text-only
- E3: audio-only
- E4: early_fusion (EarlyConcat)
- E5: late_fusion (LateWeighted)
- E6: gated_fusion (GatedCrossAttention with modality dropout)

Runs on CPU with frozen encoders across 3 fixed seeds (42, 43, 44).
"""

import os
import json
import time
import random
import numpy as np
import torch
import torch.nn as nn
from torch.utils.data import Dataset, DataLoader
from pathlib import Path
from typing import Dict, List, Any, Tuple

from text_encoder import get_text_encoder
from audio_encoder import get_audio_encoder
from fusion import EarlyConcatFusion, LateWeightedFusion, GatedCrossAttentionFusion

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "splits"
CACHE_DIR = BASE_DIR / "data" / "cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)

CKPT_DIR = BASE_DIR / "checkpoints"
CKPT_DIR.mkdir(parents=True, exist_ok=True)

CATEGORIES = ["Loans", "Accounts", "Credit Cards", "UPI/Payments", "Transaction Errors", "KYC/Verification"]
SEVERITIES = ["low", "medium", "high"]

CAT_TO_IDX = {cat: i for i, cat in enumerate(CATEGORIES)}
SEV_TO_IDX = {sev: i for i, sev in enumerate(SEVERITIES)}

class ComplaintDataset(Dataset):
    def __init__(self, split_name: str, records: List[Dict[str, Any]], text_encoder, audio_encoder):
        self.records = records
        self.texts = [r["raw_text"] for r in records]
        self.audio_paths = [r.get("audio_paths", {}).get("clean", "") for r in records]
        
        self.cat_labels = torch.tensor([CAT_TO_IDX[r["category"]] for r in records], dtype=torch.long)
        self.sev_labels = torch.tensor([SEV_TO_IDX[r["severity"]] for r in records], dtype=torch.long)
        
        cache_path = CACHE_DIR / f"{split_name}_embeddings.pt"
        if cache_path.exists():
            print(f"Loading cached precomputed embeddings from {cache_path.name}...")
            cached = torch.load(str(cache_path))
            self.text_embeddings = cached["text"]
            self.audio_embeddings = cached["audio"]
        else:
            print(f"Precomputing embeddings for {len(records)} records ({split_name}) on CPU...")
            with torch.no_grad():
                self.text_embeddings = text_encoder(self.texts)
                self.audio_embeddings = audio_encoder.forward_audio_files(self.audio_paths, batch_size=32)
            torch.save({
                "text": self.text_embeddings,
                "audio": self.audio_embeddings
            }, str(cache_path))
            print(f"Saved precomputed embeddings to {cache_path.name}")

    def __len__(self):
        return len(self.records)

    def __getitem__(self, idx):
        return {
            "text_emb": self.text_embeddings[idx],
            "audio_emb": self.audio_embeddings[idx],
            "cat_label": self.cat_labels[idx],
            "sev_label": self.sev_labels[idx]
        }

def load_jsonl(path: Path) -> List[Dict[str, Any]]:
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                records.append(json.loads(line))
    return records

def set_seed(seed: int):
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(seed)

def create_model(model_type: str) -> nn.Module:
    if model_type in ["text_only", "audio_only", "early_fusion"]:
        return EarlyConcatFusion()
    elif model_type == "late_fusion":
        return LateWeightedFusion()
    elif model_type == "gated_fusion":
        return GatedCrossAttentionFusion()
    else:
        raise ValueError(f"Unknown model_type: {model_type}")

def train_epoch(model, dataloader, optimizer, criterion_cat, criterion_sev, model_type: str) -> float:
    model.train()
    total_loss = 0.0
    for batch in dataloader:
        text_emb = batch["text_emb"]
        audio_emb = batch["audio_emb"]
        cat_labels = batch["cat_label"]
        sev_labels = batch["sev_label"]

        if model_type == "text_only":
            audio_emb = torch.zeros_like(audio_emb)
        elif model_type == "audio_only":
            text_emb = torch.zeros_like(text_emb)

        optimizer.zero_grad()
        
        if isinstance(model, GatedCrossAttentionFusion):
            out = model(text_emb, audio_emb, modality_dropout_p=0.3)
        else:
            out = model(text_emb, audio_emb)

        loss_cat = criterion_cat(out["category_logits"], cat_labels)
        loss_sev = criterion_sev(out["severity_logits"], sev_labels)
        loss = loss_cat + 0.8 * loss_sev

        loss.backward()
        optimizer.step()
        total_loss += loss.item()

    return total_loss / len(dataloader)

def evaluate_loss(model, dataloader, criterion_cat, criterion_sev, model_type: str) -> Tuple[float, float, float]:
    model.eval()
    total_loss = 0.0
    cat_correct = 0
    sev_correct = 0
    total = 0

    with torch.no_grad():
        for batch in dataloader:
            text_emb = batch["text_emb"]
            audio_emb = batch["audio_emb"]
            cat_labels = batch["cat_label"]
            sev_labels = batch["sev_label"]

            if model_type == "text_only":
                audio_emb = torch.zeros_like(audio_emb)
            elif model_type == "audio_only":
                text_emb = torch.zeros_like(text_emb)

            out = model(text_emb, audio_emb)
            loss_cat = criterion_cat(out["category_logits"], cat_labels)
            loss_sev = criterion_sev(out["severity_logits"], sev_labels)
            loss = loss_cat + 0.8 * loss_sev
            total_loss += loss.item()

            cat_preds = out["category_logits"].argmax(dim=-1)
            sev_preds = out["severity_logits"].argmax(dim=-1)

            cat_correct += (cat_preds == cat_labels).sum().item()
            sev_correct += (sev_preds == sev_labels).sum().item()
            total += cat_labels.size(0)

    avg_loss = total_loss / len(dataloader)
    cat_acc = cat_correct / total
    sev_acc = sev_correct / total
    return avg_loss, cat_acc, sev_acc

def train_model_experiment(
    model_type: str,
    train_dataset: ComplaintDataset,
    val_dataset: ComplaintDataset,
    seed: int,
    epochs: int = 15,
    batch_size: int = 32
) -> Dict[str, Any]:
    set_seed(seed)
    
    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    model = create_model(model_type)
    optimizer = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    criterion_cat = nn.CrossEntropyLoss()
    criterion_sev = nn.CrossEntropyLoss()

    best_val_loss = float("inf")
    best_model_path = CKPT_DIR / f"{model_type}_seed{seed}.pt"

    for epoch in range(1, epochs + 1):
        train_loss = train_epoch(model, train_loader, optimizer, criterion_cat, criterion_sev, model_type)
        val_loss, val_cat_acc, val_sev_acc = evaluate_loss(model, val_loader, criterion_cat, criterion_sev, model_type)

        if val_loss < best_val_loss:
            best_val_loss = val_loss
            torch.save(model.state_dict(), str(best_model_path))

    model.load_state_dict(torch.load(str(best_model_path)))
    return {
        "model": model,
        "best_val_loss": best_val_loss,
        "checkpoint_path": str(best_model_path)
    }

def main():
    print("=" * 60)
    print("UniResolve ML Model Training Pipeline (CPU/Frozen Encoders)")
    print("=" * 60)

    train_records = load_jsonl(DATA_DIR / "train.jsonl")
    val_records = load_jsonl(DATA_DIR / "val.jsonl")

    text_encoder = get_text_encoder(freeze=True)
    audio_encoder = get_audio_encoder(freeze=True)

    train_dataset = ComplaintDataset("train", train_records, text_encoder, audio_encoder)
    val_dataset = ComplaintDataset("val", val_records, text_encoder, audio_encoder)

    model_types = ["text_only", "audio_only", "early_fusion", "late_fusion", "gated_fusion"]
    seeds = [42, 43, 44]

    trained_checkpoints = {}
    for mt in model_types:
        print(f"\nTraining Model: {mt} across seeds {seeds}...")
        trained_checkpoints[mt] = []
        for s in seeds:
            res = train_model_experiment(mt, train_dataset, val_dataset, seed=s, epochs=20)
            trained_checkpoints[mt].append(res["checkpoint_path"])
            print(f"  [Seed {s}] Saved best checkpoint: {res['checkpoint_path']} (Val Loss: {res['best_val_loss']:.4f})")

    print("\nTraining completed successfully for all model variants and seeds.")

if __name__ == "__main__":
    main()
