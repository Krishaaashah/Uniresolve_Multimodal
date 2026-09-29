"""
Multimodal Fusion Modules & Classification Heads for UniResolve.
Implements:
1. EarlyConcat
2. LateWeighted
3. GatedCrossAttention
Includes modality dropout (p=0.3) and modality masking for text-only inputs.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F
from typing import Tuple, Dict, Optional

TEXT_DIM = 384
AUDIO_DIM = 773
HIDDEN_DIM = 256
NUM_CATEGORIES = 6
NUM_SEVERITIES = 3

class MultiTaskClassificationHeads(nn.Module):
    """Category (6 classes) and Severity (3 classes) output heads."""
    def __init__(self, input_dim: int):
        super().__init__()
        self.category_head = nn.Sequential(
            nn.Linear(input_dim, 128),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(128, NUM_CATEGORIES)
        )
        self.severity_head = nn.Sequential(
            nn.Linear(input_dim, 64),
            nn.ReLU(),
            nn.Dropout(0.2),
            nn.Linear(64, NUM_SEVERITIES)
        )

    def forward(self, fused_features: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        cat_logits = self.category_head(fused_features)
        sev_logits = self.severity_head(fused_features)
        return cat_logits, sev_logits


class EarlyConcatFusion(nn.Module):
    """Concatenates raw text and audio embeddings, passed through a deep MLP."""
    def __init__(self, text_dim: int = TEXT_DIM, audio_dim: int = AUDIO_DIM, hidden_dim: int = HIDDEN_DIM):
        super().__init__()
        self.fusion_mlp = nn.Sequential(
            nn.Linear(text_dim + audio_dim, hidden_dim * 2),
            nn.BatchNorm1d(hidden_dim * 2),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.BatchNorm1d(hidden_dim),
            nn.ReLU()
        )
        self.heads = MultiTaskClassificationHeads(hidden_dim)

    def forward(
        self,
        text_emb: torch.Tensor,
        audio_emb: torch.Tensor,
        audio_mask: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        # Apply audio mask if provided (0 = missing audio)
        if audio_mask is not None:
            audio_emb = audio_emb * audio_mask.unsqueeze(-1)
            
        combined = torch.cat([text_emb, audio_emb], dim=-1)
        fused = self.fusion_mlp(combined)
        cat_logits, sev_logits = self.heads(fused)
        
        return {
            "category_logits": cat_logits,
            "severity_logits": sev_logits,
            "fused_features": fused,
            "modality_weights": {"text": 0.5, "audio": 0.5}
        }


class LateWeightedFusion(nn.Module):
    """Independent unimodal projections combined with learned softmax attention gating."""
    def __init__(self, text_dim: int = TEXT_DIM, audio_dim: int = AUDIO_DIM, hidden_dim: int = HIDDEN_DIM):
        super().__init__()
        self.text_proj = nn.Sequential(
            nn.Linear(text_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2)
        )
        self.audio_proj = nn.Sequential(
            nn.Linear(audio_dim, hidden_dim),
            nn.ReLU(),
            nn.Dropout(0.2)
        )
        # Gating network
        self.gate = nn.Sequential(
            nn.Linear(text_dim + audio_dim, 64),
            nn.ReLU(),
            nn.Linear(64, 2)
        )
        self.heads = MultiTaskClassificationHeads(hidden_dim)

    def forward(
        self,
        text_emb: torch.Tensor,
        audio_emb: torch.Tensor,
        audio_mask: Optional[torch.Tensor] = None
    ) -> Dict[str, torch.Tensor]:
        h_text = self.text_proj(text_emb)
        
        if audio_mask is not None:
            audio_emb = audio_emb * audio_mask.unsqueeze(-1)
            
        h_audio = self.audio_proj(audio_emb)

        # Compute modality weights
        gate_logits = self.gate(torch.cat([text_emb, audio_emb], dim=-1))
        
        if audio_mask is not None:
            # Force audio gate weight to near zero if audio is missing
            gate_logits[:, 1] = gate_logits[:, 1] + (audio_mask - 1.0) * 1e4
            
        weights = F.softmax(gate_logits, dim=-1) # (B, 2)
        w_text = weights[:, 0].unsqueeze(-1)
        w_audio = weights[:, 1].unsqueeze(-1)

        fused = w_text * h_text + w_audio * h_audio
        cat_logits, sev_logits = self.heads(fused)

        return {
            "category_logits": cat_logits,
            "severity_logits": sev_logits,
            "fused_features": fused,
            "modality_weights": {
                "text": float(weights[:, 0].mean().item()),
                "audio": float(weights[:, 1].mean().item())
            }
        }


class GatedCrossAttentionFusion(nn.Module):
    """
    Cross-Attention between Text queries and Audio keys/values with
    a residual sigmoid gate and modality dropout support.
    """
    def __init__(self, text_dim: int = TEXT_DIM, audio_dim: int = AUDIO_DIM, hidden_dim: int = HIDDEN_DIM):
        super().__init__()
        self.hidden_dim = hidden_dim
        self.q_proj = nn.Linear(text_dim, hidden_dim)
        self.k_proj = nn.Linear(audio_dim, hidden_dim)
        self.v_proj = nn.Linear(audio_dim, hidden_dim)
        
        self.cross_attn = nn.MultiheadAttention(embed_dim=hidden_dim, num_heads=4, batch_first=True)
        
        self.gate = nn.Sequential(
            nn.Linear(hidden_dim * 2, hidden_dim),
            nn.ReLU(),
            nn.Linear(hidden_dim, 1),
            nn.Sigmoid()
        )
        self.post_norm = nn.LayerNorm(hidden_dim)
        self.heads = MultiTaskClassificationHeads(hidden_dim)

    def forward(
        self,
        text_emb: torch.Tensor,
        audio_emb: torch.Tensor,
        audio_mask: Optional[torch.Tensor] = None,
        modality_dropout_p: float = 0.0
    ) -> Dict[str, torch.Tensor]:
        # Modality dropout during training on audio branch
        if self.training and modality_dropout_p > 0.0:
            drop_mask = (torch.rand(text_emb.size(0), device=text_emb.device) > modality_dropout_p).float()
            if audio_mask is not None:
                audio_mask = audio_mask * drop_mask
            else:
                audio_mask = drop_mask

        if audio_mask is not None:
            audio_emb = audio_emb * audio_mask.unsqueeze(-1)

        # Projections
        Q = self.q_proj(text_emb).unsqueeze(1)    # (B, 1, hidden_dim)
        K = self.k_proj(audio_emb).unsqueeze(1)   # (B, 1, hidden_dim)
        V = self.v_proj(audio_emb).unsqueeze(1)   # (B, 1, hidden_dim)

        attn_out, _ = self.cross_attn(Q, K, V)     # (B, 1, hidden_dim)
        h_cross = attn_out.squeeze(1)
        h_text = Q.squeeze(1)

        # Gated fusion
        gate_input = torch.cat([h_text, h_cross], dim=-1)
        g = self.gate(gate_input) # (B, 1)

        if audio_mask is not None:
            g = g * audio_mask.unsqueeze(-1)

        fused = self.post_norm((1.0 - g) * h_text + g * h_cross)
        cat_logits, sev_logits = self.heads(fused)

        audio_weight = float(g.mean().item())
        return {
            "category_logits": cat_logits,
            "severity_logits": sev_logits,
            "fused_features": fused,
            "modality_weights": {
                "text": round(1.0 - audio_weight, 3),
                "audio": round(audio_weight, 3)
            }
        }
