#!/usr/bin/env python3
"""
explain_shap.py

Standalone, OFFLINE SHAP explainability demo for SkyGuard AI's anomaly model.

This is intentionally NOT wired into main.py / the live /ingest path — with
Round 2 close, adding a live SHAP dependency to the production request path
is a real risk (SHAP on Isolation Forest is finicky, and it can be slow).
Instead, this script runs standalone against your already-trained model and
produces real SHAP explanations you can screenshot for the PPT or pull up
live if a judge asks "show me the SHAP output" — backing up the
explainability claim in your PPT without touching the working demo.

Usage:
    python explain_shap.py
    python explain_shap.py --data-dir data --model model.joblib

Requires: pip install shap matplotlib
"""

import argparse
import json
import os

import joblib
import numpy as np
import pandas as pd

from features import FEATURE_NAMES, StationFeatureBuilder


def load_dataset(data_dir: str) -> pd.DataFrame:
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


def build_features(df: pd.DataFrame) -> np.ndarray:
    """Same feature-building logic as training/live inference (features.py)."""
    feature_rows = []
    for station_id, group in df.groupby("station_id", sort=False):
        builder = StationFeatureBuilder()
        for _, row in group.iterrows():
            vec = builder.update_and_build(row["temperature_c"], row["pressure_hpa"], row["humidity_pct"])
            feature_rows.append(vec)
    return np.array(feature_rows)


def main():
    parser = argparse.ArgumentParser(description="Offline SHAP explainability demo")
    parser.add_argument("--data-dir", type=str, default="data")
    parser.add_argument("--model", type=str, default="model.joblib")
    parser.add_argument("--output-dir", type=str, default="shap_output")
    parser.add_argument("--background-size", type=int, default=100, help="Number of clean samples used as SHAP background")
    args = parser.parse_args()

    try:
        import shap
        import matplotlib
        matplotlib.use("Agg")  # no display needed, just save files
        import matplotlib.pyplot as plt
    except ImportError:
        print("Missing dependencies. Run: pip install shap matplotlib")
        return

    print(f"Loading dataset from {args.data_dir}...")
    df = load_dataset(args.data_dir)
    print(f"Loaded {len(df)} readings.")

    print("Building features (same pipeline as training/live inference)...")
    X = build_features(df)
    X_df = pd.DataFrame(X, columns=FEATURE_NAMES)

    print(f"Loading model from {args.model}...")
    model = joblib.load(args.model)

    os.makedirs(args.output_dir, exist_ok=True)

    # Background sample from CLEAN readings only — SHAP needs a reference
    # distribution of "normal" to measure deviation against.
    clean_idx = df.index[~df["is_anomaly_true"]].tolist()
    background_idx = np.random.RandomState(42).choice(
        clean_idx, size=min(args.background_size, len(clean_idx)), replace=False
    )
    background = X_df.iloc[background_idx]

    print("Building SHAP explainer (TreeExplainer for Isolation Forest)...")
    try:
        explainer = shap.TreeExplainer(model)
        shap_values = explainer.shap_values(X_df)
    except Exception as e:
        print(f"TreeExplainer failed ({e}), falling back to KernelExplainer on a small sample "
              f"(slower, but robust to any model type).")
        sample = X_df.sample(n=min(30, len(X_df)), random_state=42)
        explainer = shap.KernelExplainer(model.decision_function, background)
        shap_values = explainer.shap_values(sample)
        X_df = sample  # align for plotting below

    # 1. Summary plot — which features matter most overall
    print("Generating summary plot...")
    plt.figure()
    shap.summary_plot(shap_values, X_df, show=False)
    plt.tight_layout()
    plt.savefig(os.path.join(args.output_dir, "shap_summary.png"), dpi=150)
    plt.close()

    # 2. Print feature importance as text too — usable even without opening images
    mean_abs_shap = np.abs(shap_values).mean(axis=0)
    importance = sorted(zip(FEATURE_NAMES, mean_abs_shap), key=lambda x: -x[1])
    print("\nFeature importance (mean |SHAP value|):")
    for name, val in importance:
        print(f"  {name:30s} {val:.4f}")

    # 3. A specific example — pick one real cross_sensor-labeled reading if available
    cross_sensor_rows = df.index[df["fault_type"] == "cross_sensor"].tolist()
    if cross_sensor_rows:
        example_idx = cross_sensor_rows[0]
        print(f"\nGenerating example explanation for a cross_sensor reading (row {example_idx})...")
        plt.figure()
        shap.force_plot(
            explainer.expected_value, shap_values[example_idx], X_df.iloc[example_idx],
            matplotlib=True, show=False,
        )
        plt.tight_layout()
        plt.savefig(os.path.join(args.output_dir, "shap_example_cross_sensor.png"), dpi=150)
        plt.close()

    print(f"\nDone. Charts saved to {args.output_dir}/ — use these in your PPT or pull up "
          f"'shap_summary.png' live if asked to demonstrate SHAP explainability.")


if __name__ == "__main__":
    main()