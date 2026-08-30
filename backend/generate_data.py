#!/usr/bin/env python3
"""
generate_data.py

A synthetic weather data generator for SkyGuard AI.
Generates realistic clean temperature, pressure, and humidity time-series with physical
cross-sensor correlations, and injects common AWS sensor faults.
Includes a dynamic Indian weather station generator, playback mode, and plotting features.
"""

import argparse
import json
import os
import random
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

# Plausible templates for generating Indian weather stations dynamically
INDIAN_STATES_TEMPLATES = [
    {"state": "MH", "name": "Mumbai Coastal AWS", "lat": 19.0760, "lon": 72.8777, "temp_mean": 27.5, "temp_amp": 3.5, "press_mean": 1009.0, "hum_mean": 78.0, "hum_factor": 2.2},
    {"state": "DL", "name": "Delhi Plains AWS", "lat": 28.6139, "lon": 77.2090, "temp_mean": 31.0, "temp_amp": 9.5, "press_mean": 1005.0, "hum_mean": 45.0, "hum_factor": 2.8},
    {"state": "HP", "name": "Shimla Mountain AWS", "lat": 31.1048, "lon": 77.1734, "temp_mean": 14.5, "temp_amp": 6.0, "press_mean": 850.0, "hum_mean": 62.0, "hum_factor": 2.5},
    {"state": "KA", "name": "Bangalore Plateau AWS", "lat": 12.9716, "lon": 77.5946, "temp_mean": 23.5, "temp_amp": 5.0, "press_mean": 920.0, "hum_mean": 65.0, "hum_factor": 2.4},
    {"state": "TN", "name": "Chennai Coastal AWS", "lat": 13.0827, "lon": 80.2707, "temp_mean": 29.5, "temp_amp": 3.0, "press_mean": 1010.0, "hum_mean": 75.0, "hum_factor": 2.1},
    {"state": "WB", "name": "Kolkata Delta AWS", "lat": 22.5726, "lon": 88.3639, "temp_mean": 26.8, "temp_amp": 4.5, "press_mean": 1008.0, "hum_mean": 80.0, "hum_factor": 2.6},
    {"state": "GJ", "name": "Ahmedabad Semi-Arid AWS", "lat": 23.0225, "lon": 72.5714, "temp_mean": 28.5, "temp_amp": 8.0, "press_mean": 1007.0, "hum_mean": 52.0, "hum_factor": 2.7},
    {"state": "UP", "name": "Lucknow Central AWS", "lat": 26.8467, "lon": 80.9462, "temp_mean": 26.0, "temp_amp": 7.5, "press_mean": 1006.0, "hum_mean": 60.0, "hum_factor": 2.5},
    {"state": "KL", "name": "Trivandrum Tropical AWS", "lat": 8.5241, "lon": 76.9366, "temp_mean": 27.0, "temp_amp": 2.5, "press_mean": 1011.0, "hum_mean": 82.0, "hum_factor": 2.0},
    {"state": "RJ", "name": "Jaipur Desert AWS", "lat": 26.9124, "lon": 75.7873, "temp_mean": 33.0, "temp_amp": 11.0, "press_mean": 1004.0, "hum_mean": 30.0, "hum_factor": 3.0}
]

# ==========================================
# 1. FAULT INJECTION FUNCTIONS
# ==========================================

def inject_spike(
    series: pd.Series,
    start_idx: int,
    duration: int,
    severity: float,
    param_name: str
) -> Tuple[pd.Series, dict]:
    """
    Injects a sudden single-point (or few-point) jump in one parameter, then returns to normal.
    - severity: additive offset magnitude (positive or negative)
    """
    corrupted = series.copy()
    end_idx = min(start_idx + duration - 1, len(series) - 1)
    
    corrupted.iloc[start_idx : end_idx + 1] += severity
    
    if "humidity" in param_name.lower():
        corrupted = corrupted.clip(0.0, 100.0)
        
    label = {
        "start_idx": start_idx,
        "end_idx": end_idx,
        "fault_type": "spike",
        "affected_parameter": param_name,
        "severity": severity
    }
    return corrupted, label


def inject_flatline(
    series: pd.Series,
    start_idx: int,
    duration: int,
    severity: Optional[float],
    param_name: str
) -> Tuple[pd.Series, dict]:
    """
    Freezes a parameter at a fixed value for a configurable duration (simulating a stuck sensor).
    - severity: if provided, freezes at this exact value. If None/NaN, freezes at the last reading value.
    """
    corrupted = series.copy()
    end_idx = min(start_idx + duration - 1, len(series) - 1)
    
    if severity is not None and not np.isnan(severity):
        freeze_val = severity
    else:
        freeze_val = corrupted.iloc[start_idx - 1] if start_idx > 0 else corrupted.iloc[0]
        
    corrupted.iloc[start_idx : end_idx + 1] = freeze_val
    
    label = {
        "start_idx": start_idx,
        "end_idx": end_idx,
        "fault_type": "flatline",
        "affected_parameter": param_name,
        "severity": float(freeze_val)
    }
    return corrupted, label


def inject_drift(
    series: pd.Series,
    start_idx: int,
    duration: int,
    severity: float,
    param_name: str,
    drift_type: str = "linear"
) -> Tuple[pd.Series, dict]:
    """
    Slowly diverges a parameter from its true value over time (simulating calibration decay).
    - severity: final offset magnitude at the end of the duration
    - drift_type: 'linear' or 'exponential' (gradual exponential curve)
    """
    corrupted = series.copy()
    end_idx = min(start_idx + duration - 1, len(series) - 1)
    actual_len = end_idx - start_idx + 1
    
    if actual_len <= 0:
        label = {
            "start_idx": start_idx, "end_idx": end_idx,
            "fault_type": "drift", "affected_parameter": param_name, "severity": severity
        }
        return corrupted, label
        
    if drift_type == "linear":
        drift_profile = np.linspace(0.0, severity, actual_len)
    else:  # gradual exponential/quadratic drift
        # Starts slowly, grows quadratically to severity
        t = np.linspace(0.0, 1.0, actual_len)
        drift_profile = (t ** 2) * severity
        
    corrupted.iloc[start_idx : end_idx + 1] += drift_profile
    
    if "humidity" in param_name.lower():
        corrupted = corrupted.clip(0.0, 100.0)
        
    label = {
        "start_idx": start_idx,
        "end_idx": end_idx,
        "fault_type": "drift",
        "affected_parameter": param_name,
        "severity": severity
    }
    return corrupted, label


def inject_noise_burst(
    series: pd.Series,
    start_idx: int,
    duration: int,
    severity: float,
    param_name: str
) -> Tuple[pd.Series, dict]:
    """
    Injects a period of high-frequency jitter/variance (noise burst) added to a parameter.
    - severity: standard deviation of the Gaussian noise burst
    """
    corrupted = series.copy()
    end_idx = min(start_idx + duration - 1, len(series) - 1)
    actual_len = end_idx - start_idx + 1
    
    if actual_len > 0:
        noise = np.random.normal(0.0, severity, actual_len)
        corrupted.iloc[start_idx : end_idx + 1] += noise
        
    if "humidity" in param_name.lower():
        corrupted = corrupted.clip(0.0, 100.0)
        
    label = {
        "start_idx": start_idx,
        "end_idx": end_idx,
        "fault_type": "noise",
        "affected_parameter": param_name,
        "severity": severity
    }
    return corrupted, label


def inject_cross_sensor(
    df: pd.DataFrame,
    start_idx: int,
    duration: int,
    severity: float
) -> Tuple[pd.DataFrame, dict]:
    """
    Breaks physical correlation between parameters (humidity and temperature).
    Forces humidity to stay extremely high (saturated) even during rapid temperature rises.
    """
    corrupted_df = df.copy()
    end_idx = min(start_idx + duration - 1, len(df) - 1)
    
    # Increase temperature and simultaneously force humidity to be near 98% (which violates standard correlation)
    corrupted_df.loc[start_idx : end_idx, "temperature_c"] += severity
    corrupted_df.loc[start_idx : end_idx, "humidity_pct"] = np.clip(
        95.0 + np.random.normal(0, 1.2, end_idx - start_idx + 1), 0.0, 100.0
    )
    
    label = {
        "start_idx": start_idx,
        "end_idx": end_idx,
        "fault_type": "cross_sensor",
        "affected_parameter": "multiple",
        "severity": severity
    }
    return corrupted_df, label

# ==========================================
# 2. BASELINE DATA GENERATOR
# ==========================================

class WeatherStationSimulator:
    """Generates realistic clean baseline weather data using diurnal and physical relations."""
    
    def __init__(self, station_id: str, config: dict):
        self.station_id = station_id
        self.config = config
        
    def generate_clean_data(self, start_time: datetime, end_time: datetime, interval: timedelta) -> pd.DataFrame:
        """Generates clean physically correlated weather variables."""
        timestamps = []
        curr = start_time
        while curr < end_time:
            timestamps.append(curr)
            curr += interval
            
        df = pd.DataFrame({"timestamp": timestamps})
        df["station_id"] = self.station_id
        df["latitude"] = self.config["lat"]
        df["longitude"] = self.config["lon"]
        
        n_samples = len(df)
        time_hours = np.array([(t - start_time).total_seconds() / 3600.0 for t in df["timestamp"]])
        day_hours = np.array([t.hour + t.minute / 60.0 for t in df["timestamp"]])
        
        # 1. Pressure: smooth low frequency variation + semi-diurnal tides + small noise
        p_slow = self.config["press_mean"] + 3.0 * np.sin(2 * np.pi * time_hours / (24 * 4))
        p_tide = 0.8 * np.cos(4 * np.pi * (day_hours - 10) / 24)
        p_noise = np.random.normal(0, 0.15, n_samples)
        df["pressure_hpa"] = p_slow + p_tide + p_noise
        
        # 2. Temperature: diurnal cycle shifted by pressure + noise
        t_diurnal = self.config["temp_amp"] * np.sin(2 * np.pi * (day_hours - 9) / 24)
        t_p_influence = 0.8 * (df["pressure_hpa"] - self.config["press_mean"]) / 3.0
        t_noise = np.random.normal(0, 0.25, n_samples)
        df["temperature_c"] = self.config["temp_mean"] + t_diurnal + t_p_influence + t_noise
        
        # 3. Humidity: Inversely correlated with temperature + pressure influence + noise
        h_temp_corr = -self.config["hum_factor"] * (df["temperature_c"] - self.config["temp_mean"])
        h_press_corr = -0.2 * (df["pressure_hpa"] - self.config["press_mean"])
        h_noise = np.random.normal(0, 0.6, n_samples)
        df["humidity_pct"] = np.clip(self.config["hum_mean"] + h_temp_corr + h_press_corr + h_noise, 8.0, 98.0)
        
        return df

# ==========================================
# 3. DATA AND LABELS GENERATION ORCHESTRATOR
# ==========================================

def generate_stations_data(
    num_stations: int,
    duration_days: int,
    interval_minutes: int,
    fault_density: float,
    seed: int
) -> Tuple[List[dict], pd.DataFrame]:
    """
    Generates clean weather data, injects random toggleable faults,
    and returns readings in ingest-format API payload list + ground-truth labels dataframe.
    """
    np.random.seed(seed)
    random.seed(seed)
    
    # Calculate timestamps
    now_utc = datetime.now(timezone.utc)
    start_time = (now_utc - timedelta(days=duration_days)).replace(hour=0, minute=0, second=0, microsecond=0)
    end_time = start_time + timedelta(days=duration_days)
    interval = timedelta(minutes=interval_minutes)
    
    # Generate station configurations
    station_configs = {}
    for i in range(num_stations):
        template = INDIAN_STATES_TEMPLATES[i % len(INDIAN_STATES_TEMPLATES)]
        num_str = f"{(i // len(INDIAN_STATES_TEMPLATES)) + 1:03d}"
        station_id = f"AWS-IND-{template['state']}-{num_str}"
        
        # Add slight variations to simulate distinct geographic spots
        lat_offset = random.uniform(-0.15, 0.15)
        lon_offset = random.uniform(-0.15, 0.15)
        
        station_configs[station_id] = {
            "name": f"{template['name']} {num_str}",
            "lat": template["lat"] + lat_offset,
            "lon": template["lon"] + lon_offset,
            "temp_mean": template["temp_mean"] + random.uniform(-1.0, 1.0),
            "temp_amp": template["temp_amp"] + random.uniform(-0.5, 0.5),
            "press_mean": template["press_mean"] + random.uniform(-2.0, 2.0),
            "hum_mean": template["hum_mean"] + random.uniform(-3.0, 3.0),
            "hum_factor": template["hum_factor"] + random.uniform(-0.1, 0.1)
        }
        
    readings_list = []
    labels_records = []
    
    for station_id, config in station_configs.items():
        simulator = WeatherStationSimulator(station_id, config)
        df = simulator.generate_clean_data(start_time, end_time, interval)
        n_samples = len(df)
        
        # Initialize row-by-row ground truth labels
        df_labels = pd.DataFrame({
            "station_id": station_id,
            "timestamp": df["timestamp"],
            "fault_type": "none",
            "affected_parameter": "none",
            "severity": 0.0
        })
        
        # Determine number of fault events to inject, split into a fair PER-FAULT-TYPE
        # budget rather than one shared pool. This prevents short-duration faults
        # (spike/flatline) from crowding out longer ones (drift/noise/cross_sensor)
        # before the attempt budget runs out.
        target_anom_points = int(n_samples * fault_density)
        
        fault_types = ["spike", "flatline", "drift", "noise", "cross_sensor"]
        parameters = ["temperature_c", "pressure_hpa", "humidity_pct"]
        
        # Each fault type gets an equal slice of the total point budget.
        per_type_target = max(1, target_anom_points // len(fault_types))
        max_attempts_per_type = 150
        
        # Randomize the order fault types are injected in, so no type is
        # systematically favored just by going first.
        shuffled_fault_types = fault_types.copy()
        random.shuffle(shuffled_fault_types)
        
        current_anom_points = 0
        
        for f_type in shuffled_fault_types:
            type_points = 0
            attempts = 0
            
            while type_points < per_type_target and attempts < max_attempts_per_type:
                attempts += 1
                param = random.choice(parameters)

                # Determine random duration
                if f_type == "spike":
                    duration = random.randint(1, 3)
                elif f_type in ["flatline", "noise"]:
                    duration = random.randint(12, 48)  # 1 to 4 hours
                elif f_type == "drift":
                    duration = random.randint(36, 120)  # 3 to 10 hours
                elif f_type == "cross_sensor":
                    duration = random.randint(24, 72)  # 2 to 6 hours
                    param = "multiple"

                if n_samples - duration - 10 <= 0:
                    continue

                # Find a start index with buffering
                start_idx = random.randint(10, n_samples - duration - 10)
                target_indices = range(start_idx, start_idx + duration)

                # Check for overlaps
                if any(df_labels.loc[idx, "fault_type"] != "none" for idx in target_indices):
                    continue

                # Apply Fault
                label = {}
                if f_type == "spike":
                    severity = random.choice([-1.0, 1.0]) * (
                        random.uniform(7.0, 14.0) if param == "temperature_c"
                        else random.uniform(20.0, 45.0) if param == "pressure_hpa"
                        else random.uniform(25.0, 45.0)
                    )
                    df[param], label = inject_spike(df[param], start_idx, duration, severity, param)

                elif f_type == "flatline":
                    severity = None  # Freeze at last value
                    df[param], label = inject_flatline(df[param], start_idx, duration, severity, param)

                elif f_type == "drift":
                    severity = random.choice([-1.0, 1.0]) * (
                        random.uniform(3.5, 7.0) if param == "temperature_c"
                        else random.uniform(15.0, 25.0) if param == "pressure_hpa"
                        else random.uniform(20.0, 40.0)
                    )
                    dtype = random.choice(["linear", "exponential"])
                    df[param], label = inject_drift(df[param], start_idx, duration, severity, param, drift_type=dtype)

                elif f_type == "noise":
                    severity = (
                        random.uniform(1.5, 3.0) if param == "temperature_c"
                        else random.uniform(3.0, 6.0) if param == "pressure_hpa"
                        else random.uniform(10.0, 20.0)
                    )
                    df[param], label = inject_noise_burst(df[param], start_idx, duration, severity, param)

                elif f_type == "cross_sensor":
                    severity = random.uniform(4.0, 8.0)
                    df, label = inject_cross_sensor(df, start_idx, duration, severity)

                # Populate ground truth labels
                for idx in target_indices:
                    df_labels.loc[idx, "fault_type"] = label["fault_type"]
                    df_labels.loc[idx, "affected_parameter"] = label["affected_parameter"]
                    df_labels.loc[idx, "severity"] = label["severity"]

                type_points += duration
                current_anom_points += duration
                attempts = 0  # reset attempts on success within this fault type

        labels_records.append(df_labels)
        
        # Build API ingest payloads
        for _, row in df.iterrows():
            payload = {
                "station_id": station_id,
                "timestamp": row["timestamp"].isoformat().replace("+00:00", "Z"),
                "location": {
                    "latitude": round(row["latitude"], 5),
                    "longitude": round(row["longitude"], 5)
                },
                "readings": {
                    "temperature_c": round(row["temperature_c"], 2),
                    "pressure_hpa": round(row["pressure_hpa"], 2),
                    "humidity_pct": round(row["humidity_pct"], 2)
                }
            }
            readings_list.append(payload)
            
    final_labels_df = pd.concat(labels_records, ignore_index=True)
    return readings_list, final_labels_df

# ==========================================
# 4. PLOBACK (REPLAY) LOGIC
# ==========================================

def playback_readings(readings_path: str, url: str, speedup: float):
    """Replays weather readings against a live ingest endpoint at accelerated speed."""
    import requests
    
    print(f"Loading readings from {readings_path} for playback...")
    if not os.path.exists(readings_path):
        print(f"Error: readings file {readings_path} does not exist.")
        return
        
    readings = []
    with open(readings_path, "r") as f:
        for line in f:
            if line.strip():
                readings.append(json.loads(line))
                
    # Sort chronologically
    readings.sort(key=lambda x: x["timestamp"])
    print(f"Replaying {len(readings)} readings to {url} with a speedup of {speedup}x...")
    
    last_timestamp = None
    
    for i, payload in enumerate(readings):
        curr_timestamp = datetime.fromisoformat(payload["timestamp"].replace("Z", "+00:00"))
        
        if last_timestamp is not None:
            time_diff_sec = (curr_timestamp - last_timestamp).total_seconds()
            if time_diff_sec > 0:
                sleep_duration = time_diff_sec / speedup
                # Limit sleep time to prevent huge gaps if there is a data discontinuity
                sleep_duration = min(sleep_duration, 10.0)
                if sleep_duration > 0.01:
                    time.sleep(sleep_duration)
                    
        # Send POST request
        try:
            r = requests.post(url, json=payload, headers={"Content-Type": "application/json"}, timeout=5.0)
            if r.status_code in [200, 201]:
                print(f"[{i+1}/{len(readings)}] Ingested {payload['station_id']} at {payload['timestamp']} -> OK")
            else:
                print(f"[{i+1}/{len(readings)}] Failed to ingest {payload['station_id']}. Code: {r.status_code}, Resp: {r.text}")
        except Exception as e:
            print(f"[{i+1}/{len(readings)}] Connection error replaying reading: {e}")
            
        last_timestamp = curr_timestamp
        
    print("Playback complete!")

# ==========================================
# 5. VISUAL SANITY CHECK PLOTTER
# ==========================================

def plot_station_faults(readings_path: str, labels_path: str, station_id: str, plot_out_path: str):
    """Generates a visualization of temperature, pressure, and humidity with highlighted faults."""
    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Warning: matplotlib not installed. Skipping sanity plot.")
        return
        
    if not os.path.exists(readings_path) or not os.path.exists(labels_path):
        print("Error: Readings or labels file missing. Plotting skipped.")
        return
        
    # Read files
    readings = []
    with open(readings_path, "r") as f:
        for line in f:
            if line.strip():
                readings.append(json.loads(line))
                
    df_readings_all = pd.DataFrame([
        {
            "station_id": r["station_id"],
            "timestamp": pd.to_datetime(r["timestamp"]),
            "temperature_c": r["readings"]["temperature_c"],
            "pressure_hpa": r["readings"]["pressure_hpa"],
            "humidity_pct": r["readings"]["humidity_pct"]
        }
        for r in readings
    ])
    
    df_labels_all = pd.read_csv(labels_path)
    df_labels_all["timestamp"] = pd.to_datetime(df_labels_all["timestamp"])
    
    # Filter for station
    df_r = df_readings_all[df_readings_all["station_id"] == station_id].sort_values("timestamp").reset_index(drop=True)
    df_l = df_labels_all[df_labels_all["station_id"] == station_id].sort_values("timestamp").reset_index(drop=True)
    
    if len(df_r) == 0:
        print(f"No records found for station {station_id} to plot.")
        return
        
    # Merge for plotting ease
    df_plot = pd.merge(df_r, df_l, on=["station_id", "timestamp"], how="inner")
    
    # Limit to first 4 days to keep the graph readable
    if len(df_plot) > 1152: # 4 days at 5-min intervals
        df_plot = df_plot.iloc[:1152]
        
    fig, axes = plt.subplots(3, 1, figsize=(14, 10), sharex=True)
    fig.suptitle(f"AWS Unit Sanity Check - Injected Faults ({station_id})", fontsize=15, fontweight="bold", y=0.98)
    
    params = [
        ("temperature_c", "Temperature (°C)", "#ff7f0e"),
        ("pressure_hpa", "Pressure (hPa)", "#1f77b4"),
        ("humidity_pct", "Humidity (%)", "#2ca02c")
    ]
    
    for i, (col, label_name, color) in enumerate(params):
        axes[i].plot(df_plot["timestamp"], df_plot[col], label=label_name, color=color, alpha=0.9)
        axes[i].set_ylabel(label_name, fontweight="bold")
        axes[i].grid(True, linestyle="--", alpha=0.5)
        
        # Overlay fault regions
        is_anom = (df_plot["fault_type"] != "none").values
        diff = np.diff(is_anom.astype(int))
        starts = np.where(diff == 1)[0] + 1
        ends = np.where(diff == -1)[0] + 1
        
        if is_anom[0]:
            starts = np.insert(starts, 0, 0)
        if is_anom[-1]:
            ends = np.append(ends, len(is_anom) - 1)
            
        for s, e in zip(starts, ends):
            e = min(e, len(df_plot) - 1)
            t_start = df_plot.loc[s, "timestamp"]
            t_end = df_plot.loc[e, "timestamp"]
            f_type = df_plot.loc[s, "fault_type"]
            f_param = df_plot.loc[s, "affected_parameter"]
            
            # Show anomaly region background
            axes[i].axvspan(t_start, t_end, color="#ff4d4d", alpha=0.15)
            
            # Add text indicator on the graph for the anomaly block (on first plot or the affected parameter's plot)
            if i == 0 or f_param == col or (f_param == "multiple" and i == 2):
                t_mid = t_start + (t_end - t_start) / 2
                axes[i].text(
                    t_mid, axes[i].get_ylim()[1] * 0.94, f"{f_type} ({f_param})",
                    color="darkred", fontsize=8.5, horizontalalignment="center",
                    bbox=dict(facecolor="white", alpha=0.8, boxstyle="round,pad=0.2")
                )
                
    plt.xticks(rotation=15)
    plt.tight_layout()
    
    out_dir = os.path.dirname(plot_out_path)
    if out_dir:
        os.makedirs(out_dir, exist_ok=True)
    plt.savefig(plot_out_path, dpi=150)
    print(f"Validation sanity check plot saved to: {plot_out_path}")

# ==========================================
# 6. MAIN CLI IMPLEMENTATION
# ==========================================

def main():
    parser = argparse.ArgumentParser(description="SkyGuard AI Weather Data & Fault Simulator")
    parser.add_argument("--num-stations", type=int, default=3, help="Number of weather stations to simulate (default: 3)")
    parser.add_argument("--duration-days", type=int, default=7, help="Duration of timeseries in days (default: 7)")
    parser.add_argument("--interval-minutes", type=int, default=5, help="Time step between observations in minutes (default: 5)")
    parser.add_argument("--fault-density", type=float, default=0.05, help="Fraction of dataset covered by faults (default: 0.05)")
    parser.add_argument("--output-dir", type=str, default="backend/data", help="Output directory (default: backend/data)")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility (default: 42)")
    
    # Playback options
    parser.add_argument("--playback", type=str, help="URL of live SkyGuard /ingest endpoint to replay generated readings against")
    parser.add_argument("--speedup", type=float, default=60.0, help="Accelerated playback rate multiplier (default: 60.0)")
    
    # Visual options
    parser.add_argument("--plot", action="store_true", help="Generate a validation sanity plot showing fault regions")
    parser.add_argument("--plot-station", type=str, help="Station ID to highlight in the sanity plot")
    
    args = parser.parse_args()
    
    # Input validation
    if args.num_stations <= 0:
        parser.error("--num-stations must be a positive integer greater than 0")
    if args.duration_days <= 0:
        parser.error("--duration-days must be a positive integer greater than 0")
    if args.interval_minutes <= 0:
        parser.error("--interval-minutes must be a positive integer greater than 0")
    if not (0.0 <= args.fault_density <= 1.0):
        parser.error("--fault-density must be a float between 0.0 and 1.0 (inclusive)")
        
    # Check if playback mode was triggered on an existing file
    if args.playback and not args.plot:
        # Just run playback if a reading file already exists
        readings_path = os.path.join(args.output_dir, "synthetic_readings.jsonl")
        if os.path.exists(readings_path):
            playback_readings(readings_path, args.playback, args.speedup)
            return
            
    # Regular generation workflow
    os.makedirs(args.output_dir, exist_ok=True)
    readings_path = os.path.join(args.output_dir, "synthetic_readings.jsonl")
    labels_path = os.path.join(args.output_dir, "synthetic_labels.csv")
    plot_path = os.path.join(args.output_dir, "anomaly_check.png")
    
    print(f"Generating synthetic weather dataset...")
    print(f" - Stations count: {args.num_stations}")
    print(f" - Duration: {args.duration_days} days")
    print(f" - Interval: {args.interval_minutes} minutes")
    print(f" - Fault Density: {args.fault_density * 100:.1f}%")
    print(f" - Random Seed: {args.seed}")
    
    readings_list, labels_df = generate_stations_data(
        num_stations=args.num_stations,
        duration_days=args.duration_days,
        interval_minutes=args.interval_minutes,
        fault_density=args.fault_density,
        seed=args.seed
    )
    
    # 1. Save readings to JSON Lines format (.jsonl)
    with open(readings_path, "w") as f:
        for r in readings_list:
            f.write(json.dumps(r) + "\n")
            
    print(f"Saved weather readings to: {readings_path}")
    
    # 2. Save ground truth labels to CSV
    labels_df.to_csv(labels_path, index=False)
    print(f"Saved ground-truth labels to: {labels_path}")
    
    # Print a summary of generated data
    print("\nGeneration Statistics:")
    print(f" - Total readings: {len(readings_list)}")
    print(f" - Faulty readings: {len(labels_df[labels_df['fault_type'] != 'none'])}")
    print("\nFault type breakdowns:")
    print(labels_df[labels_df['fault_type'] != 'none']['fault_type'].value_counts())
    
    # 3. Optional plotting
    if args.plot:
        plot_station = args.plot_station
        if not plot_station:
            plot_station = labels_df["station_id"].iloc[0]
        plot_station_faults(readings_path, labels_path, plot_station, plot_path)
        
    # 4. Trigger playback if url is given
    if args.playback:
        playback_readings(readings_path, args.playback, args.speedup)


if __name__ == "__main__":
    main()
