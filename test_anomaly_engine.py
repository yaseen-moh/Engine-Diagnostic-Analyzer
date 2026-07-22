"""
Unit tests for the Engine Diagnostic Analyzer.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import time
import numpy as np
import pytest

from anomaly_engine import SensorWindow, AnomalyEngine, BaselineModel
from failure_library import get_failure_mode, Severity, Trend


class TestSensorWindow:
    def test_add_and_stats(self):
        w = SensorWindow("TEST", max_size=10)
        for i in range(10):
            w.add(time.time(), float(i))
        assert w.is_ready()
        stats = w.get_stats()
        assert stats["mean"] == 4.5
        assert stats["min"] == 0.0
        assert stats["max"] == 9.0

    def test_trend_rising(self):
        w = SensorWindow("TEST", max_size=10)
        for i in range(10):
            w.add(time.time(), float(i))
        assert w.get_trend() == Trend.RISING

    def test_trend_jitter(self):
        w = SensorWindow("TEST", max_size=10)
        np.random.seed(42)
        for _ in range(10):
            w.add(time.time(), np.random.normal(100, 50))
        assert w.get_trend() == Trend.JITTER


class TestFailureModeMatching:
    def test_water_pump_signature(self):
        engine = AnomalyEngine("test", ["COOLANT_TEMP", "CONTROL_MODULE_VOLTAGE", "RPM"])

        # Simulate water pump failure pattern
        for i in range(50):
            t = time.time()
            engine.ingest("COOLANT_TEMP", t, 90 + i * 0.1)
            engine.ingest("CONTROL_MODULE_VOLTAGE", t, 14.2 - i * 0.005)
            engine.ingest("RPM", t, 750 + np.random.normal(0, 30))

        alerts = engine.get_active_alerts()
        water_pump_alerts = [a for a in alerts if a.failure_mode_id == "WATER_PUMP_BEARING"]
        assert len(water_pump_alerts) > 0

    def test_no_false_positive_on_normal(self):
        engine = AnomalyEngine("test", ["COOLANT_TEMP", "CONTROL_MODULE_VOLTAGE", "RPM"])

        for i in range(50):
            t = time.time()
            engine.ingest("COOLANT_TEMP", t, 90 + np.random.normal(0, 0.5))
            engine.ingest("CONTROL_MODULE_VOLTAGE", t, 14.2 + np.random.normal(0, 0.02))
            engine.ingest("RPM", t, 750 + np.random.normal(0, 5))

        alerts = engine.get_active_alerts()
        assert len(alerts) == 0


class TestBaselineModel:
    def test_train_and_score(self):
        model = BaselineModel("test-vehicle")

        # Generate normal-looking data
        np.random.seed(42)
        features = np.random.randn(100, 5)
        model.train(features)

        assert model.is_trained

        # Normal data should score low
        normal_score = model.score(features[0])
        assert 0 <= normal_score <= 1


class TestOBDLogger:
    def test_simulation_mode(self):
        from obd_logger import OBDDataLogger
        logger = OBDDataLogger("test", mode="simulate")
        assert logger.connect()
        assert logger.mode == "simulate"

    def test_csv_persistence(self):
        from obd_logger import OBDDataLogger
        import csv

        logger = OBDDataLogger("test-csv", mode="simulate")
        logger.connect()

        reading = logger._read_simulated("RPM")
        logger._persist(reading)

        with open(logger.session_file, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["sensor_name"] == "RPM"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
