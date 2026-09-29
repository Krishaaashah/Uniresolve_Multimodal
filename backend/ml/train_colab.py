"""
UniResolve Multimodal Training Script for Google Colab (GPU / CPU).
Self-contained script to train and evaluate fusion models on Colab.
"""

# Colab Setup:
# !pip install torch transformers torchaudio librosa soundfile scikit-learn pandas numpy matplotlib openai-whisper

import os
import sys
import json
import torch

def run_colab_pipeline():
    print("UniResolve Multimodal Triage - Colab Pipeline Initialized")
    device = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Executing on compute device: {device}")
    
    # 1. Prepare Data
    import data.prepare_cfpb as prepare_cfpb
    prepare_cfpb.main()
    
    # 2. Synthesize Audio
    import data.synth_audio as synth_audio
    synth_audio.main()
    
    # 3. Train Models
    import train as train_module
    train_module.main()
    
    # 4. Evaluate Benchmark Suite
    import evaluate as eval_module
    eval_module.main()
    
    print("Colab Pipeline Run Finished! Metrics exported to results/ directory.")

if __name__ == "__main__":
    run_colab_pipeline()
