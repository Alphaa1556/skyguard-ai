import unittest
from datetime import datetime
import pandas as pd
import numpy as np
import importlib.util
from pathlib import Path

spec = importlib.util.spec_from_file_location("skyguard_backend", Path(__file__).resolve().parent / "main.py")
backend_main = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backend_main)

from generate_data import (
    generate_stations_data,
    inject_spike,
    inject_flatline,
    inject_drift,
    inject_noise_burst,
    inject_cross_sensor,
    INDIAN_STATES_TEMPLATES
)

class TestWeatherGenerator(unittest.TestCase):
    
    def setUp(self):
        # Generate small dataset using the main generator function (2 stations, 2 days)
        self.readings_list, self.labels_df = generate_stations_data(
            num_stations=2,
            duration_days=2,
            interval_minutes=5,
            fault_density=0.08,
            seed=42
        )
        
    def test_modular_fault_functions(self):
        """Test each individual fault function for output type, length, and labels."""
        series = pd.Series(np.sin(np.linspace(0, 10, 100)))
        
        # Test Spike
        corrupted, label = inject_spike(series, start_idx=10, duration=2, severity=5.0, param_name="temp")
        self.assertEqual(len(corrupted), len(series))
        self.assertAlmostEqual(corrupted.iloc[10], series.iloc[10] + 5.0)
        self.assertEqual(label["fault_type"], "spike")
        self.assertEqual(label["affected_parameter"], "temp")
        
        # Test Flatline
        corrupted, label = inject_flatline(series, start_idx=15, duration=5, severity=None, param_name="temp")
        self.assertEqual(len(corrupted), len(series))
        # Frozen at index 14 value
        self.assertEqual(corrupted.iloc[15], series.iloc[14])
        self.assertEqual(corrupted.iloc[19], series.iloc[14])
        self.assertEqual(label["fault_type"], "flatline")
        
        # Test Drift (linear)
        corrupted, label = inject_drift(series, start_idx=20, duration=10, severity=2.0, param_name="temp", drift_type="linear")
        self.assertEqual(len(corrupted), len(series))
        self.assertAlmostEqual(corrupted.iloc[30], series.iloc[30]) # post drift returns to normal (or rather, the index range is 20-29 inclusive)
        self.assertAlmostEqual(corrupted.iloc[29], series.iloc[29] + 2.0) # final index has full severity
        self.assertEqual(label["fault_type"], "drift")
        
        # Test Noise Burst
        corrupted, label = inject_noise_burst(series, start_idx=40, duration=15, severity=3.0, param_name="temp")
        self.assertEqual(len(corrupted), len(series))
        self.assertEqual(label["fault_type"], "noise")
        self.assertEqual(label["severity"], 3.0)

    def test_generated_readings_payload_format(self):
        """Assert the API ingest payload matches the required API contract structure."""
        self.assertGreater(len(self.readings_list), 0)
        
        # Check first record structure
        first_r = self.readings_list[0]
        self.assertIn("station_id", first_r)
        self.assertIn("timestamp", first_r)
        self.assertIn("location", first_r)
        self.assertIn("readings", first_r)
        
        # Check location
        self.assertIn("latitude", first_r["location"])
        self.assertIn("longitude", first_r["location"])
        
        # Check readings
        self.assertIn("temperature_c", first_r["readings"])
        self.assertIn("pressure_hpa", first_r["readings"])
        self.assertIn("humidity_pct", first_r["readings"])
        
        # Verify station ID pattern
        self.assertTrue(first_r["station_id"].startswith("AWS-IND-"))

    def test_generated_labels_csv_structure(self):
        """Verify ground truth labels dataframe matches the schema and is clean."""
        self.assertFalse(self.labels_df.empty)
        expected_cols = ["station_id", "timestamp", "fault_type", "affected_parameter", "severity"]
        self.assertEqual(list(self.labels_df.columns), expected_cols)
        
        # Verify clean rows have default values
        clean_rows = self.labels_df[self.labels_df["fault_type"] == "none"]
        self.assertTrue((clean_rows["affected_parameter"] == "none").all())
        self.assertTrue((clean_rows["severity"] == 0.0).all())
        
        # Verify anomalous rows have valid values
        anom_rows = self.labels_df[self.labels_df["fault_type"] != "none"]
        if not anom_rows.empty:
            self.assertTrue((anom_rows["fault_type"].isin(["spike", "flatline", "drift", "noise", "cross_sensor"])).all())

    def test_physical_inverse_correlation(self):
        """Verify temperature and humidity have a negative correlation during clean periods."""
        # Find clean timestamps for the first station
        station_id = self.readings_list[0]["station_id"]
        
        # Extract temp and humidity lists for clean periods
        clean_timestamps = set(
            self.labels_df[
                (self.labels_df["station_id"] == station_id) & 
                (self.labels_df["fault_type"] == "none")
            ]["timestamp"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        )
        
        temp_vals = []
        hum_vals = []
        for r in self.readings_list:
            if r["station_id"] == station_id and r["timestamp"] in clean_timestamps:
                temp_vals.append(r["readings"]["temperature_c"])
                hum_vals.append(r["readings"]["humidity_pct"])
                
        # Calculate correlation
        if len(temp_vals) > 10:
            corr = np.corrcoef(temp_vals, hum_vals)[0, 1]
            self.assertLess(corr, -0.5, f"Expected negative physical correlation between T and H, got {corr}")

    def test_seed_demo_data_populates_station_store(self):
        """Ensure the API starts with a live station inventory rather than an empty mock store."""
        backend_main._stations.clear()
        backend_main._locations.clear()

        backend_main.seed_demo_data()

        stations = backend_main.list_stations()
        self.assertGreater(len(stations), 0)
        self.assertTrue(any(s.station_id.startswith("AWS-IND-") for s in stations))

if __name__ == "__main__":
    unittest.main()
