#!/usr/bin/env python3
"""
train_and_evaluate.py

Retrains the Isolation Forest anomaly detector on Bhakti's real synthetic
dataset (backend/data/synthetic_readings.jsonl + synthetic_labels.csv), using
temporal features (see features.py) instead of raw readings alone, combined
with a physics-informed rule for cross_sensor faults.

Evaluates detection quality against ground truth — precision, recall, F1,
false-positive rate, and a per-fault-type breakdown — and saves the trained
model + feature stats to disk so main.py can load them at startup instead of
retraining on placeholder data every time.

Usage:
    python train_and_evaluate.py
    python train_and_evaluate.py --data-dir data --output-dir .
"""

import argparse
import json
import os

import joblib
import numpy as np
import pandas as pd
import torch
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

from features import FEATURE_NAMES, RAW_FEATURE_NAMES, StationFeatureBuilder
import lstm_drift_detector


def load_dataset(data_dir: str) -> pd.DataFrame:
    """Loads readings.jsonl + labels.csv and joins them into one dataframe."""
    readings_path = os.path.join(data_dir, "synthetic_readings.jsonl")
    labels_path = os.path.join(data_dir, "synthetic_labels.csv")

    readings = []
    with open(readings_path, "r") as f:
        for line in f:
            if line.strip():
                r = json.loads(line)
                readings.append({
                    "station_id": r["station_id"],
                    "timestamp": r["timestamp"],
                    "temperature_c": r["readings"]["temperature_c"],
                    "pressure_hpa": r["readings"]["pressure_hpa"],
                    "humidity_pct": r["readings"]["humidity_pct"],
                })
    df_readings = pd.DataFrame(readings)
    df_readings["timestamp"] = pd.to_datetime(df_readings["timestamp"])

    df_labels = pd.read_csv(labels_path)
    df_labels["timestamp"] = pd.to_datetime(df_labels["timestamp"])

    df = pd.merge(df_readings, df_labels, on=["station_id", "timestamp"], how="inner")
    df["is_anomaly_true"] = df["fault_type"] != "none"
    return df.sort_values(["station_id", "timestamp"]).reset_index(drop=True)


def build_features_and_physics_flags(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """
    Feeds each station's readings through StationFeatureBuilder in chronological
    order — the SAME class main.py uses at inference time — so training features
    and live features are computed identically. Also collects the physics-rule
    cross_sensor flag alongside each row's feature vector.
    """
    feature_rows = []
    physics_flags = []
    for station_id, group in df.groupby("station_id", sort=False):
        builder = StationFeatureBuilder()
        for _, row in group.iterrows():
            vec = builder.update_and_build(row["temperature_c"], row["pressure_hpa"], row["humidity_pct"])
            feature_rows.append(vec)
            physics_flags.append(builder.check_cross_sensor_rule())
    return np.array(feature_rows), np.array(physics_flags)


def build_lstm_errors(df: pd.DataFrame, model, scaler_stats: dict) -> np.ndarray:
    """
    Computes a per-row LSTM reconstruction error, aligned to df's row order.
    Each window's error is attached to the row where the window ENDS (the
    "current" reading) — matching how live inference works in main.py, since
    a station needs WINDOW_SIZE readings of history before the LSTM has
    anything to say. Rows without enough history yet (the first
    WINDOW_SIZE - 1 per station) get 0.0, same cold-start behavior as
    DriftDetector.score() returning None early on.
    """
    from lstm_drift_detector import FEATURES, WINDOW_SIZE

    errors = np.zeros(len(df))
    mean = np.array(scaler_stats["mean"])
    std = np.array(scaler_stats["std"])

    for _, group in df.groupby("station_id", sort=False):
        values = group[FEATURES].values
        idx = group.index.values
        if len(group) < WINDOW_SIZE:
            continue

        windows = np.array([values[i:i + WINDOW_SIZE] for i in range(len(group) - WINDOW_SIZE + 1)])
        windows_scaled = (windows - mean) / std
        x = torch.tensor(windows_scaled, dtype=torch.float32)

        model.eval()
        with torch.no_grad():
            reconstructed = model(x)
            mse = torch.mean((x - reconstructed) ** 2, dim=(1, 2)).numpy()

        # window i ends at position i + WINDOW_SIZE - 1 within this station's group
        end_positions = np.arange(WINDOW_SIZE - 1, len(group))
        errors[idx[end_positions]] = mse

    return errors


def train_model(df: pd.DataFrame, X: np.ndarray) -> tuple[IsolationForest, dict]:
    """Trains Isolation Forest on CLEAN rows only, so it learns what 'normal' looks like."""
    clean_mask = ~df["is_anomaly_true"].values
    X_train = X[clean_mask]

    contamination = float(df["is_anomaly_true"].mean())
    contamination = min(max(contamination, 0.01), 0.5)  # keep it in a sane range

    model = IsolationForest(n_estimators=200, contamination=contamination, random_state=42)
    model.fit(X_train)

    clean_df = df[~df["is_anomaly_true"]]
    feature_stats = {
        name: {"mean": float(clean_df[name].mean()), "std": float(clean_df[name].std())}
        for name in RAW_FEATURE_NAMES
    }
    return model, feature_stats


def evaluate_model(model: IsolationForest, df: pd.DataFrame, X: np.ndarray, physics_flags: np.ndarray,
                    lstm_flags: np.ndarray) -> None:
    """Prints precision/recall/F1, false-positive rate, and per-fault-type recall,
    for the ML model alone, ML + physics rule, and the final ML + physics + LSTM
    combined detector (LSTM specifically targets drift — see lstm_drift_detector.py)."""
    y_true = df["is_anomaly_true"].values
    ml_pred = model.predict(X) == -1  # -1 = anomaly, 1 = normal
    ml_physics_pred = ml_pred | physics_flags
    full_combined_pred = ml_pred | physics_flags | lstm_flags

    def _report(y_pred: np.ndarray, label: str) -> None:
        precision = precision_score(y_true, y_pred, zero_division=0)
        recall = recall_score(y_true, y_pred, zero_division=0)
        f1 = f1_score(y_true, y_pred, zero_division=0)
        tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0

        print(f"\n--- {label} ---")
        print(f"Precision: {precision:.3f}  Recall: {recall:.3f}  F1: {f1:.3f}  FPR: {fpr:.3f}")
        print(f"(TP={tp}, FP={fp}, FN={fn}, TN={tn})")
        print("Recall by fault type:")
        for fault_type in df.loc[y_true, "fault_type"].unique():
            mask = (df["fault_type"] == fault_type).values
            type_recall = y_pred[mask].mean() if mask.sum() > 0 else 0.0
            print(f"  {fault_type:15s} {type_recall * 100:5.1f}%  ({mask.sum()} readings)")

    print("\n" + "=" * 60)
    print("EVALUATION — vs. ground truth")
    print("=" * 60)
    print(f"Total readings: {len(df)} | True anomalies: {int(y_true.sum())} ({y_true.mean() * 100:.1f}%)")

    _report(ml_pred, "ML model only (Isolation Forest)")
    _report(ml_physics_pred, "ML model + physics rule")
    _report(full_combined_pred, "ML + physics + LSTM drift detector (FINAL combined detector)")
    print("=" * 60 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Retrain and evaluate the anomaly model with temporal features + physics rule")
    parser.add_argument("--data-dir", type=str, default="data", help="Directory with synthetic_readings.jsonl and synthetic_labels.csv")
    parser.add_argument("--output-dir", type=str, default=".", help="Where to save model.joblib and feature_stats.json")
    args = parser.parse_args()

    print(f"Loading dataset from {args.data_dir}...")
    df = load_dataset(args.data_dir)
    print(f"Loaded {len(df)} readings across {df['station_id'].nunique()} stations.")

    print("Building temporal features + physics-rule flags (same logic main.py will use live)...")
    X, physics_flags = build_features_and_physics_flags(df)
    print(f"Feature matrix shape: {X.shape} ({len(FEATURE_NAMES)} features)")

    print("Training Isolation Forest on clean readings...")
    model, feature_stats = train_model(df, X)

    print("Training LSTM-Autoencoder drift detector on clean windows...")
    lstm_model, lstm_scaler_stats, lstm_threshold, lstm_train_errors = lstm_drift_detector.train(df)
    lstm_errors = build_lstm_errors(df, lstm_model, lstm_scaler_stats)
    lstm_flags = lstm_errors > lstm_threshold

    evaluate_model(model, df, X, physics_flags, lstm_flags)

    model_path = os.path.join(args.output_dir, "model.joblib")
    stats_path = os.path.join(args.output_dir, "feature_stats.json")
    lstm_weights_path = os.path.join(args.output_dir, "lstm_drift_model.pt")
    lstm_config_path = os.path.join(args.output_dir, "lstm_drift_config.json")

    joblib.dump(model, model_path)
    with open(stats_path, "w") as f:
        json.dump(feature_stats, f, indent=2)
    lstm_drift_detector.save_artifacts(lstm_model, lstm_scaler_stats, lstm_threshold,
                                        lstm_weights_path, lstm_config_path)

    print(f"Saved trained model to: {model_path}")
    print(f"Saved feature stats to: {stats_path}")
    print(f"Saved LSTM drift detector to: {lstm_weights_path}, {lstm_config_path}")


if __name__ == "__main__":
    main()