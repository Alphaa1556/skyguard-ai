#!/usr/bin/env python3
"""
train_and_evaluate.py

Retrains the Isolation Forest anomaly detector on Bhakti's real synthetic
dataset (backend/data/synthetic_readings.jsonl + synthetic_labels.csv), using
temporal features (see features.py) instead of raw readings alone.

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
from sklearn.ensemble import IsolationForest
from sklearn.metrics import confusion_matrix, f1_score, precision_score, recall_score

from features import FEATURE_NAMES, RAW_FEATURE_NAMES, StationFeatureBuilder


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


def build_temporal_features(df: pd.DataFrame) -> np.ndarray:
    """
    Feeds each station's readings through StationFeatureBuilder in chronological
    order — the SAME class main.py uses at inference time — so training features
    and live features are computed identically.
    """
    feature_rows = []
    for station_id, group in df.groupby("station_id", sort=False):
        builder = StationFeatureBuilder()
        for _, row in group.iterrows():
            vec = builder.update_and_build(row["temperature_c"], row["pressure_hpa"], row["humidity_pct"])
            feature_rows.append(vec)
    return np.array(feature_rows)


def train_model(df: pd.DataFrame, X: np.ndarray) -> tuple[IsolationForest, dict]:
    """Trains Isolation Forest on CLEAN rows only, so it learns what 'normal' looks like."""
    clean_mask = ~df["is_anomaly_true"].values
    X_train = X[clean_mask]

    contamination = float(df["is_anomaly_true"].mean())
    contamination = min(max(contamination, 0.01), 0.5)  # keep it in a sane range

    model = IsolationForest(n_estimators=200, contamination=contamination, random_state=42)
    model.fit(X_train)

    # Save raw-feature mean/std separately for the explanation layer in main.py
    # (identifies which physical parameter deviates most, in plain language).
    clean_df = df[~df["is_anomaly_true"]]
    feature_stats = {
        name: {"mean": float(clean_df[name].mean()), "std": float(clean_df[name].std())}
        for name in RAW_FEATURE_NAMES
    }
    return model, feature_stats


def evaluate_model(model: IsolationForest, df: pd.DataFrame, X: np.ndarray) -> None:
    """Prints precision/recall/F1, false-positive rate, and per-fault-type recall."""
    y_true = df["is_anomaly_true"].values
    predictions = model.predict(X)  # -1 = anomaly, 1 = normal
    y_pred = predictions == -1

    precision = precision_score(y_true, y_pred, zero_division=0)
    recall = recall_score(y_true, y_pred, zero_division=0)
    f1 = f1_score(y_true, y_pred, zero_division=0)

    tn, fp, fn, tp = confusion_matrix(y_true, y_pred).ravel()
    false_positive_rate = fp / (fp + tn) if (fp + tn) > 0 else 0.0

    print("\n" + "=" * 50)
    print("EVALUATION — Isolation Forest + temporal features vs. ground truth")
    print("=" * 50)
    print(f"Total readings:        {len(df)}")
    print(f"True anomalies:        {int(y_true.sum())} ({y_true.mean() * 100:.1f}%)")
    print(f"Flagged as anomalies:  {int(y_pred.sum())} ({y_pred.mean() * 100:.1f}%)")
    print()
    print(f"Precision:             {precision:.3f}")
    print(f"Recall:                {recall:.3f}")
    print(f"F1 score:              {f1:.3f}")
    print(f"False positive rate:   {false_positive_rate:.3f}")
    print(f"(TP={tp}, FP={fp}, FN={fn}, TN={tn})")

    print("\nRecall by fault type (of the injected faults, how many did the model catch?):")
    for fault_type in df.loc[df["is_anomaly_true"], "fault_type"].unique():
        mask = (df["fault_type"] == fault_type).values
        type_recall = y_pred[mask].mean() if mask.sum() > 0 else 0.0
        print(f"  {fault_type:15s} {type_recall * 100:5.1f}%  ({mask.sum()} readings)")
    print("=" * 50 + "\n")


def main():
    parser = argparse.ArgumentParser(description="Retrain and evaluate the anomaly model with temporal features")
    parser.add_argument("--data-dir", type=str, default="data", help="Directory with synthetic_readings.jsonl and synthetic_labels.csv")
    parser.add_argument("--output-dir", type=str, default=".", help="Where to save model.joblib and feature_stats.json")
    args = parser.parse_args()

    print(f"Loading dataset from {args.data_dir}...")
    df = load_dataset(args.data_dir)
    print(f"Loaded {len(df)} readings across {df['station_id'].nunique()} stations.")

    print("Building temporal features (same logic main.py will use live)...")
    X = build_temporal_features(df)
    print(f"Feature matrix shape: {X.shape} ({len(FEATURE_NAMES)} features)")

    print("Training Isolation Forest on clean readings...")
    model, feature_stats = train_model(df, X)

    evaluate_model(model, df, X)

    model_path = os.path.join(args.output_dir, "model.joblib")
    stats_path = os.path.join(args.output_dir, "feature_stats.json")
    joblib.dump(model, model_path)
    with open(stats_path, "w") as f:
        json.dump(feature_stats, f, indent=2)

    print(f"Saved trained model to: {model_path}")
    print(f"Saved feature stats to: {stats_path}")


if __name__ == "__main__":
    main()