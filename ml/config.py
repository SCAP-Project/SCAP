"""Configuracao explicita do experimento; sem credenciais ou banco."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
ARTIFACTS = ROOT / "ml/artifacts"
REPORTS = ROOT / "ml/reports"
SEED = 42
TRAIN_END = "2024-12-31"
VALIDATION_END = "2025-06-30"
TEST_END = "2025-12-31"
MODEL_NAMES = ["Desvio historico", "Isolation Forest", "Autoencoder"]
