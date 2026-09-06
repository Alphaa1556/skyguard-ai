"""
evaluate.py — SkyGuard AI
--------------------------
Runs classify_anomaly() (anomaly_classifier.py) against Bhakti's real
generated data instead of a toy example, and reports per-type accuracy —
same idea as Yash's train_and_evaluate.py for detection.

Usage:
    python evaluate.py [readings.jsonl] [labels.csv]
Defaults to backend/data/synthetic_readings.jsonl and
backend/data/synthetic_labels.csv if you don't pass paths.

Column-name assumptions (adjust load_readings_jsonl/load_labels_csv
below if these don't match Bhakti's actual output):
  readings.jsonl lines: {"station_id", "timestamp", "location": {...},
                          "readings": {...}}  (same shape as /ingest)
  labels.csv columns:   station_id, timestamp, fault_type,
                          affected_parameter, severity
"""

import json
import sys
import pandas as pd

from anomaly_classifier import classify_anomaly


def load_readings_jsonl(path: str) -> pd.DataFrame:
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            loc = obj.get("location", obj)      # falls back to flat keys
            read = obj.get("readings", obj)      # if it's not nested
            rows.append({
                "station_id": obj.get("station_id"),
                "timestamp": obj.get("timestamp"),
                "latitude": loc.get("latitude"),
                "longitude": loc.get("longitude"),
                "temperature_c": read.get("temperature_c"),
                "pressure_hpa": read.get("pressure_hpa"),
                "humidity_pct": read.get("humidity_pct"),
            })
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def load_labels_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df


def evaluate(readings_path: str, labels_path: str, enable_cross_sensor: bool = False) -> dict:
    readings = load_readings_jsonl(readings_path)
    labels = load_labels_csv(labels_path)

    # Bhakti flagged that synthetic_labels.csv and synthetic_readings.jsonl
    # aren't both tracked the same way in git — regenerating one without
    # the other silently breaks this exact join. Catch it instead of
    # trusting bad numbers.
    matched = labels.merge(readings, on=["station_id", "timestamp"], how="inner")
    match_rate = len(matched) / max(len(labels), 1)
    if match_rate < 0.95:
        print(
            f"WARNING: only {match_rate:.0%} of labeled rows found a matching reading.\n"
            f"readings and labels are probably out of sync (see Bhakti's .gitignore note) —\n"
            f"regenerate both files together before trusting these numbers.\n"
        )

    results = {"correct": 0, "total": 0, "by_type": {}}

    for station_id, group in readings.groupby("station_id"):
        group = group.sort_values("timestamp").reset_index(drop=True)
        station_labels = labels[labels["station_id"] == station_id]
        for _, lrow in station_labels.iterrows():
            hit = group.index[group["timestamp"] == lrow["timestamp"]]
            if len(hit) == 0:
                continue
            idx = hit[0]
            true_type = lrow["fault_type"]
            pred = classify_anomaly(group, idx, enable_cross_sensor=enable_cross_sensor)

            results["total"] += 1
            bucket = results["by_type"].setdefault(true_type, {"correct": 0, "total": 0})
            bucket["total"] += 1
            if pred["type"] == true_type:
                results["correct"] += 1
                bucket["correct"] += 1

    total = max(results["total"], 1)
    print(f"Overall: {results['correct']}/{results['total']} correct ({results['correct']/total:.1%})\n")
    print(f"{'type':<14}{'correct':<10}{'total':<8}accuracy")
    for t, r in sorted(results["by_type"].items()):
        t_total = max(r["total"], 1)
        print(f"{t:<14}{r['correct']:<10}{r['total']:<8}{r['correct']/t_total:.1%}")

    return results


if __name__ == "__main__":
    readings_path = sys.argv[1] if len(sys.argv) > 1 else "backend/data/synthetic_readings.jsonl"
    labels_path = sys.argv[2] if len(sys.argv) > 2 else "backend/data/synthetic_labels.csv"
    evaluate(readings_path, labels_path)