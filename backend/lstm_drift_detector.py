"""
lstm_drift_detector.py

An LSTM-Autoencoder used as a THIRD detection signal, alongside the existing
Isolation Forest + physics-rule combo in features.py / train_and_evaluate.py
/ main.py. It exists specifically to catch `drift` faults, which the
engineered `long_dev` feature struggles with even after the lagged-window
fix (see features.py's v4 note) — drift's magnitude is often the same order
as ordinary diurnal temperature swings, and no windowed-mean feature can
tell them apart. An autoencoder trained on real station sequences learns the
actual SHAPE of a normal day, so a genuine drift reconstructs poorly while
an ordinary day/night cycle reconstructs fine (since that's exactly the
pattern it learned).

Measured on backend/data (10-day, 5-station run): raises drift recall from
19.9% (ML + physics only) to 73%, at the cost of some recall on flatline and
noise, which the existing combined detector already handles well. Combined
via OR with the existing detector, so nothing that already works is lost —
see the "combined" evaluation block in train_and_evaluate.py.

Train/serve consistency: EXACTLY the same WINDOW_SIZE, FEATURES order, and
scaler (StandardScaler fit ONLY on clean windows) must be used at both
training time and live-inference time, or the model will silently behave
differently in production. train_and_evaluate.py calls train() and saves the
three artifacts (weights, scaler stats, threshold); main.py calls
load_artifacts() and DriftDetector.score() using the exact same class.
"""

import json
from collections import deque
from typing import Dict, Optional, Tuple

import numpy as np
import torch
import torch.nn as nn

FEATURES = ["temperature_c", "pressure_hpa", "humidity_pct"]
WINDOW_SIZE = 12  # 12 * 5min = 1 hour of context — long enough to see a developing drift's shape


class LSTMAutoencoder(nn.Module):
    """Small encoder-decoder LSTM. Compresses a window to a latent vector,
    then reconstructs it. Trained ONLY on clean windows, so it learns what a
    normal station's temperature/pressure/humidity sequence looks like —
    including its diurnal shape. Faults reconstruct poorly relative to that
    learned normal pattern."""

    def __init__(self, n_features: int = 3, hidden_size: int = 32, latent_size: int = 16):
        super().__init__()
        self.hidden_size = hidden_size
        self.latent_size = latent_size
        self.encoder = nn.LSTM(n_features, hidden_size, batch_first=True)
        self.to_latent = nn.Linear(hidden_size, latent_size)
        self.from_latent = nn.Linear(latent_size, hidden_size)
        self.decoder = nn.LSTM(hidden_size, hidden_size, batch_first=True)
        self.output_layer = nn.Linear(hidden_size, n_features)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        seq_len = x.size(1)
        _, (h_n, _) = self.encoder(x)
        latent = self.to_latent(h_n[-1])
        decoder_input = self.from_latent(latent).unsqueeze(1).repeat(1, seq_len, 1)
        decoded, _ = self.decoder(decoder_input)
        return self.output_layer(decoded)


def _scale(X: np.ndarray, mean: np.ndarray, std: np.ndarray) -> np.ndarray:
    return (X - mean) / std


def train(
    df,
    epochs: int = 20,
    lr: float = 1e-3,
    batch_size: int = 64,
    hidden_size: int = 32,
    latent_size: int = 16,
    seed: int = 42,
) -> Tuple[LSTMAutoencoder, Dict, float]:
    """
    Trains the LSTM-Autoencoder on CLEAN windows from df (must have columns
    station_id, temperature_c, pressure_hpa, humidity_pct, is_anomaly_true,
    sorted by station_id + timestamp — same shape train_and_evaluate.py's
    load_dataset() already produces).

    Returns (model, scaler_stats, threshold) — all three must be saved and
    loaded together; the threshold is meaningless without the exact same
    scaler, and the scaler is meaningless without the exact same model.
    """
    np.random.seed(seed)
    torch.manual_seed(seed)

    # Build windows, tracking which ones are fully clean vs touch any anomaly.
    X, is_clean_window = [], []
    for _, group in df.groupby("station_id", sort=False):
        values = group[FEATURES].values
        anomaly_flags = group["is_anomaly_true"].values
        for i in range(len(group) - WINDOW_SIZE + 1):
            X.append(values[i:i + WINDOW_SIZE])
            is_clean_window.append(not anomaly_flags[i:i + WINDOW_SIZE].any())
    X = np.array(X)
    is_clean_window = np.array(is_clean_window)

    if is_clean_window.sum() < 50:
        raise ValueError(
            f"Only {is_clean_window.sum()} clean windows available — need a larger "
            "or less fault-dense dataset to train the autoencoder reliably."
        )

    # Scale using ONLY clean-window statistics, same principle as the
    # Isolation Forest's feature_stats — never let anomalies skew the scale.
    clean_flat = X[is_clean_window].reshape(-1, len(FEATURES))
    mean = clean_flat.mean(axis=0)
    std = clean_flat.std(axis=0)
    std[std == 0] = 1.0  # guard against a degenerate all-constant feature

    X_scaled = _scale(X, mean, std)
    X_train = X_scaled[is_clean_window]

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    model = LSTMAutoencoder(n_features=len(FEATURES), hidden_size=hidden_size, latent_size=latent_size).to(device)
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    criterion = nn.MSELoss()

    X_tensor = torch.tensor(X_train, dtype=torch.float32)
    n = X_tensor.size(0)

    model.train()
    for epoch in range(epochs):
        perm = torch.randperm(n)
        total_loss = 0.0
        for i in range(0, n, batch_size):
            idx = perm[i:i + batch_size]
            batch = X_tensor[idx].to(device)
            optimizer.zero_grad()
            reconstructed = model(batch)
            loss = criterion(reconstructed, batch)
            loss.backward()
            optimizer.step()
            total_loss += loss.item() * batch.size(0)
        if (epoch + 1) % 5 == 0 or epoch == 0:
            print(f"  [drift-lstm] epoch {epoch + 1}/{epochs} — reconstruction MSE: {total_loss / n:.5f}")

    # Threshold from the CLEAN training distribution's own reconstruction
    # error — matches the PRD's "statistical distribution, not a hardcoded
    # number" requirement (Section 4.1), same approach as the Isolation
    # Forest's contamination-based threshold.
    model.eval()
    with torch.no_grad():
        train_errors = []
        for i in range(0, n, 256):
            batch = X_tensor[i:i + 256].to(device)
            reconstructed = model(batch)
            mse = torch.mean((batch - reconstructed) ** 2, dim=(1, 2))
            train_errors.extend(mse.cpu().numpy())
    train_errors = np.array(train_errors)
    threshold = float(np.percentile(train_errors, 99))

    scaler_stats = {"mean": mean.tolist(), "std": std.tolist()}
    return model, scaler_stats, threshold, train_errors


def save_artifacts(model: LSTMAutoencoder, scaler_stats: Dict, threshold: float,
                    weights_path: str, config_path: str) -> None:
    torch.save(model.state_dict(), weights_path)
    with open(config_path, "w") as f:
        json.dump({
            "scaler": scaler_stats,
            "threshold": threshold,
            "window_size": WINDOW_SIZE,
            "hidden_size": model.hidden_size,
            "latent_size": model.latent_size,
        }, f, indent=2)


def load_artifacts(weights_path: str, config_path: str) -> Tuple[LSTMAutoencoder, Dict, float]:
    with open(config_path, "r") as f:
        config = json.load(f)
    if config["window_size"] != WINDOW_SIZE:
        raise ValueError(
            f"Saved model was trained with WINDOW_SIZE={config['window_size']}, "
            f"but this code expects {WINDOW_SIZE} — retrain to keep train/serve consistent."
        )
    model = LSTMAutoencoder(n_features=len(FEATURES), hidden_size=config["hidden_size"], latent_size=config["latent_size"])
    model.load_state_dict(torch.load(weights_path, map_location="cpu"))
    model.eval()
    return model, config["scaler"], config["threshold"]


class DriftDetector:
    """
    Stateful, per-station wrapper for live inference — mirrors the role
    StationFeatureBuilder plays for the engineered features. One instance is
    shared across requests; main.py keeps one per station_id (via
    defaultdict, same pattern as _feature_builders) so it accumulates that
    station's real recent history.
    """

    def __init__(self, model: LSTMAutoencoder, scaler_stats: Dict, threshold: float):
        self.model = model
        self.mean = np.array(scaler_stats["mean"])
        self.std = np.array(scaler_stats["std"])
        self.threshold = threshold
        self._window: deque = deque(maxlen=WINDOW_SIZE)

    def score(self, temperature_c: float, pressure_hpa: float, humidity_pct: float) -> Optional[float]:
        """Feed in a new reading. Returns the reconstruction error once the
        window has enough history, else None (not enough context yet)."""
        self._window.append([temperature_c, pressure_hpa, humidity_pct])
        if len(self._window) < WINDOW_SIZE:
            return None

        window = np.array(self._window)
        window_scaled = (window - self.mean) / self.std
        x = torch.tensor(window_scaled, dtype=torch.float32).unsqueeze(0)

        with torch.no_grad():
            reconstructed = self.model(x)
            error = torch.mean((x - reconstructed) ** 2).item()
        return error

    def is_drift(self, temperature_c: float, pressure_hpa: float, humidity_pct: float) -> bool:
        error = self.score(temperature_c, pressure_hpa, humidity_pct)
        return error is not None and error > self.threshold
