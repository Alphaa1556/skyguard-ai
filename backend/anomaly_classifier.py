"""
anomaly_classifier.py — SkyGuard AI
------------------------------------
Rule-based anomaly TYPE classification.

Scope: this does NOT decide whether a reading is anomalous — that's
Yash's detection model (Isolation Forest + temporal features). This
assumes a point has already been flagged (is_anomaly: true) and
answers the next question: which of the five types is it?

    none | spike | flatline | drift | noise | cross_sensor

Output matches the `anomaly` object in the API contract:
    {
      "type": "spike",
      "confidence": 0.87,
      "explanation": "...",
      "affected_parameter": "temperature_c"
    }

TO USE WITH REAL DATA: load Bhakti's generator output (or her
ground-truth CSV) into a DataFrame with columns timestamp,
temperature_c, pressure_hpa, humidity_pct, then call
classify_anomaly(df, i) for each row index her labels mark anomalous.
Compare result["type"] against her fault_type column to get real
precision/recall per type, same as Yash did for detection.
"""

from __future__ import annotations
import math
import numpy as np
import pandas as pd

PARAMETERS = ["temperature_c", "pressure_hpa", "humidity_pct"]


# ---------------------------------------------------------------------------
# Individual fault-type scorers.
# Each returns {"confidence": 0..1, "parameter": str, "explanation": str}
# ---------------------------------------------------------------------------

def _score_flatline(w: pd.DataFrame, i: int, lookback: int = 6, eps: float = 1e-3) -> dict:
    """Frozen sensor: a parameter hasn't moved in `lookback` readings.
    Real sensors always have tiny noise, so std ~ 0 over several
    readings in a row is a strong 'stuck' signal."""
    start = max(0, i - lookback + 1)
    best = {"confidence": 0.0, "parameter": "none", "explanation": "No flatline pattern."}
    for p in PARAMETERS:
        seg = w[p].iloc[start:i + 1]
        if len(seg) >= 4 and seg.std() < eps:
            conf = min(0.97, 0.55 + 0.07 * len(seg))
            if conf > best["confidence"]:
                best = {
                    "confidence": conf,
                    "parameter": p,
                    "explanation": (
                        f"{p} has not changed across the last {len(seg)} readings "
                        f"(std={seg.std():.4f}) — consistent with a stuck sensor."
                    ),
                }
    return best


def _score_spike(w: pd.DataFrame, i: int, baseline: int = 12) -> dict:
    """Sudden, isolated deviation that doesn't persist — the classic
    'single bad reading' pattern, same idea as the 4.2 std-dev example
    in the API contract."""
    start = max(0, i - baseline)
    best = {"confidence": 0.0, "parameter": "none", "explanation": "No spike pattern."}
    for p in PARAMETERS:
        hist = w[p].iloc[start:i]  # excludes the flagged point itself
        if len(hist) < 5:
            continue
        mu, sigma = hist.mean(), (hist.std() or 1e-6)
        z = abs(w[p].iloc[i] - mu) / sigma

        has_next = i + 1 < len(w)
        recovers = True
        if has_next:
            after = w[p].iloc[i + 1]
            recovers = abs(after - mu) / sigma < z * 0.6

        if z > 3 and recovers:
            conf = min(0.98, 0.5 + z / 12)
            if not has_next:
                # Live/streaming case: this is the newest reading, so
                # there's no next point yet to confirm it snaps back
                # rather than being the start of a genuine shift. Still
                # alert (real-time capability matters), just hedge the
                # confidence instead of claiming certainty we don't have.
                conf *= 0.7
            if conf > best["confidence"]:
                best = {
                    "confidence": conf,
                    "parameter": p,
                    "explanation": (
                        f"{p} deviates {z:.1f} std-dev from its recent baseline in a single "
                        f"reading" + (
                            ", with neighboring points back near normal."
                            if has_next else
                            " — this is the latest reading, so confidence is provisional "
                            "until the next point confirms it wasn't a genuine shift."
                        )
                    ),
                }
    return best


def _elapsed_minutes(w: pd.DataFrame, start: int, end: int) -> np.ndarray:
    """Real elapsed time in minutes since the window start. Using row
    position instead of this would treat a 12-hour comms dropout the
    same as a normal 5-minute gap, and hand np.polyfit a fake straight
    line across the missing time — hallucinating drift that isn't
    there, or hiding drift that is. Falls back to row spacing only if
    no timestamp column is available."""
    if "timestamp" not in w.columns:
        return np.arange(end - start, dtype=float)
    ts = pd.to_datetime(w["timestamp"].iloc[start:end])
    t0 = ts.iloc[0]
    return ((ts - t0).dt.total_seconds() / 60.0).to_numpy()


def _score_drift(w: pd.DataFrame, i: int, window: int = 30) -> dict:
    """Slow, sustained deviation over a longer window — a trend, not a
    one-off. Distinguishes itself from noise by having a consistent
    direction (non-zero slope), not just elevated variance."""
    start = max(0, i - window + 1)
    best = {"confidence": 0.0, "parameter": "none", "explanation": "No drift pattern."}
    x = _elapsed_minutes(w, start, i + 1)
    span = max(x[-1] - x[0], 1e-6) if len(x) else 1e-6
    for p in PARAMETERS:
        seg = w[p].iloc[start:i + 1].to_numpy()
        if len(seg) < 10:
            continue
        slope, intercept = np.polyfit(x, seg, 1)  # units per minute now, not per row
        residual_std = (seg - (slope * x + intercept)).std() or 1e-6
        drift_magnitude = abs(slope) * span / residual_std
        if drift_magnitude > 4:
            conf = min(0.9, 0.4 + drift_magnitude / 20)
            if conf > best["confidence"]:
                best = {
                    "confidence": conf,
                    "parameter": p,
                    "explanation": (
                        f"{p} has moved steadily by about {slope * span:.2f} units over the "
                        f"last {span:.0f} minutes — a sustained trend, not a single bad reading."
                    ),
                }
    return best


def _score_noise(w: pd.DataFrame, i: int, window: int = 15,
                  normal_std: dict | None = None) -> dict:
    """Erratic fluctuation: variance well above normal, but with no
    consistent direction (rules out drift) and not a single isolated
    point (rules out spike)."""
    start = max(0, i - window + 1)
    best = {"confidence": 0.0, "parameter": "none", "explanation": "No noise pattern."}
    normal_std = normal_std or {"temperature_c": 0.5, "pressure_hpa": 1.0, "humidity_pct": 2.0}
    x = _elapsed_minutes(w, start, i + 1)
    span = max(x[-1] - x[0], 1e-6) if len(x) else 1e-6
    for p in PARAMETERS:
        seg = w[p].iloc[start:i + 1]
        if len(seg) < 8:
            continue
        ratio = seg.std() / normal_std.get(p, 1.0)
        slope = np.polyfit(x, seg, 1)[0]
        trendiness = abs(slope) * span / (seg.std() + 1e-6)
        if ratio > 3 and trendiness < 1.5:
            conf = min(0.9, 0.4 + ratio / 10)
            if conf > best["confidence"]:
                best = {
                    "confidence": conf,
                    "parameter": p,
                    "explanation": (
                        f"{p} is fluctuating about {ratio:.1f}x more than its normal noise level "
                        f"over the last {len(seg)} readings, with no consistent direction."
                    ),
                }
    return best


def _dew_point_c(temp_c: float, rh_pct: float) -> float:
    """Magnus-Tetens approximation. By definition, dew point can never
    exceed air temperature when RH <= 100% — if our estimate says it
    does, the temperature/humidity pair is lying to us."""
    a, b = 17.27, 237.7
    rh = max(rh_pct, 0.1)
    gamma = (a * temp_c) / (b + temp_c) + math.log(rh / 100.0)
    return (b * gamma) / (a - gamma)


def _score_cross_sensor(w: pd.DataFrame, i: int) -> dict:
    """Physics check: temperature and humidity individually plausible,
    but disagree with each other. This is the 'multivariate consistency'
    objective from the PS, made concrete."""
    row = w.iloc[i]
    dp = _dew_point_c(row["temperature_c"], row["humidity_pct"])
    violation = dp - row["temperature_c"]
    if violation > 1.0:  # ~1C slack for approximation error
        conf = min(0.95, 0.5 + violation / 10)
        return {
            "confidence": conf,
            "parameter": "temperature_c+humidity_pct",
            "explanation": (
                f"Implied dew point ({dp:.1f}°C) exceeds the reported air temperature "
                f"({row['temperature_c']:.1f}°C) — physically impossible, so temperature "
                f"and humidity disagree even though neither looks extreme alone."
            ),
        }
    return {"confidence": 0.0, "parameter": "none", "explanation": "No cross-sensor conflict."}


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

def classify_anomaly(window: pd.DataFrame, flagged_index: int, enable_cross_sensor: bool = True) -> dict:
    """A physics-law violation is much rarer, stronger evidence than a
    purely statistical outlier, so cross_sensor gets checked — and
    trusted — first, even if a z-score-based rule on the same point
    would also fire.

    enable_cross_sensor=False: use this if Bhakti's check_cross_sensor_rule()
    on the backend is the team's agreed source of truth for that type —
    that function already does its own physics check server-side, so this
    classifier doesn't need to duplicate it. Confirm with the team which
    one owns cross_sensor before merging this in."""
    cross = _score_cross_sensor(window, flagged_index) if enable_cross_sensor else {"confidence": 0.0}
    if cross.get("confidence", 0.0) > 0.4:
        return {
            "type": "cross_sensor",
            "confidence": round(cross["confidence"], 2),
            "explanation": cross["explanation"],
            "affected_parameter": cross["parameter"],
        }

    scores = {
        "flatline": _score_flatline(window, flagged_index),
        "spike": _score_spike(window, flagged_index),
        "drift": _score_drift(window, flagged_index),
        "noise": _score_noise(window, flagged_index),
    }
    best_type = max(scores, key=lambda t: scores[t]["confidence"])
    best = scores[best_type]
    if best["confidence"] == 0.0:
        return {"type": "none", "confidence": 0.0,
                "explanation": "No specific fault pattern matched.", "affected_parameter": "none"}
    return {
        "type": best_type,
        "confidence": round(best["confidence"], 2),
        "explanation": best["explanation"],
        "affected_parameter": best["parameter"],
    }


# ---------------------------------------------------------------------------
# Demo: a tiny synthetic series with one injected fault of each type,
# well-separated so you can see each rule work in isolation before
# wiring this to Bhakti's real generator output.
# ---------------------------------------------------------------------------

def _demo():
    rng = np.random.default_rng(7)
    n = 140
    timestamps = pd.date_range("2026-09-05T00:00:00Z", periods=n, freq="5min")
    t = pd.DataFrame({
        "timestamp": timestamps,
        "temperature_c": 28 + rng.normal(0, 0.3, n),
        "pressure_hpa": 1008 + rng.normal(0, 0.5, n),
        "humidity_pct": 80 + rng.normal(0, 1.0, n),
    })

    injected = {}

    t.loc[20, "temperature_c"] = 55.0
    injected[20] = "spike"

    t.loc[45:53, "humidity_pct"] = t.loc[45, "humidity_pct"]
    injected[53] = "flatline"

    t.loc[75:95, "pressure_hpa"] += np.linspace(0, 12, 21)
    injected[95] = "drift"

    t.loc[110:118, "temperature_c"] += rng.normal(0, 4, 9)
    injected[118] = "noise"

    t.loc[130, "humidity_pct"] = 108.0  # sensor over-reading, temp untouched
    injected[130] = "cross_sensor"

    # Gap-robustness case: a 12-hour comms dropout, ordinary readings on
    # both sides. Row-index math would treat this like a normal 5-minute
    # step and could hallucinate a huge "drift"; using real elapsed time
    # should correctly see nothing unusual.
    gap_rows = pd.DataFrame({
        "timestamp": pd.date_range(t["timestamp"].iloc[-1] + pd.Timedelta(hours=12), periods=10, freq="5min"),
        "temperature_c": 28 + rng.normal(0, 0.3, 10),
        "pressure_hpa": 1008 + rng.normal(0, 0.5, 10),
        "humidity_pct": 80 + rng.normal(0, 1.0, 10),
    })
    t = pd.concat([t, gap_rows], ignore_index=True)
    gap_check_idx = len(t) - 1
    injected[gap_check_idx] = "none"  # the real point of this case

    print(f"{'idx':>4}  {'true':<12} {'predicted':<12} {'conf':<5}  explanation")
    correct = 0
    for idx, true_type in injected.items():
        result = classify_anomaly(t, idx)
        ok = result["type"] == true_type
        correct += ok
        mark = "correct" if ok else "MISS"
        print(f"{idx:>4}  {true_type:<12} {result['type']:<12} {result['confidence']:<5}  [{mark}] {result['explanation']}")
    print(f"\n{correct}/{len(injected)} correct on this toy example.")


if __name__ == "__main__":
    _demo()