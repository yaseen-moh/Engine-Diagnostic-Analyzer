"""
Unit tests for the Anomaly Detection Engine.
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import time
import numpy as np
import pytest

from anomaly_engine import (
    SensorWindow, AnomalyEngine, BaselineModel, train_baseline_from_csv
)
from failure_library import (
    FailureMode, SensorPattern, Trend, Severity, get_failure_mode
)
from obd_logger import OBDDataLogger, SensorReading


class TestSensorWindow:
    def test_add_and_stats(self):
        w = SensorWindow("RPM", max_size=10)
        for i in range(10):
            w.add(time.time(), 750 + i * 10)

        assert w.is_ready()
        stats = w.get_stats()
        assert stats["mean"] == 795.0
        assert stats["rate_of_change"] > 0

    def test_trend_rising(self):
        w = SensorWindow("COOLANT_TEMP", max_size=20)
        for i in range(20):
            w.add(time.time(), 90 + i * 0.5)

        trend = w.get_trend()
        assert trend == Trend.RISING

    def test_trend_jitter(self):
        w = SensorWindow("RPM", max_size=20)
        np.random.seed(42)
        for i in range(20):
            w.add(time.time(), 750 + np.random.normal(0, 60))

        trend = w.get_trend()
        assert trend == Trend.JITTER


class TestFailureModeMatching:
    def test_water_pump_signature(self):
        """Simulate the classic water pump bearing failure signature."""
        engine = AnomalyEngine("test-vehicle", ["RPM", "COOLANT_TEMP", "CONTROL_MODULE_VOLTAGE"])

        # Inject simulated failing data
        for i in range(100):
            engine.ingest("RPM", time.time(), 750 + np.random.normal(0, 40))
            engine.ingest("COOLANT_TEMP", time.time(), 90 + i * 0.15)
            engine.ingest("CONTROL_MODULE_VOLTAGE", time.time(), 14.2 - i * 0.008)
            time.sleep(0.01)

        alerts = engine.get_active_alerts(min_confidence=0.5)

        # Should detect water pump bearing failure
        wp_alerts = [a for a in alerts if a.failure_mode_id == "WATER_PUMP_BEARING"]
        assert len(wp_alerts) > 0
        assert wp_alerts[0].confidence > 0.5

    def test_no_false_positive_on_normal(self):
        """Normal operation should not trigger alerts."""
        engine = AnomalyEngine("test-vehicle", ["RPM", "COOLANT_TEMP", "CONTROL_MODULE_VOLTAGE"])

        # Stable normal data
        np.random.seed(42)
        for i in range(100):
            engine.ingest("RPM", time.time(), 750 + np.random.normal(0, 8))
            engine.ingest("COOLANT_TEMP", time.time(), 90 + np.random.normal(0, 1))
            engine.ingest("CONTROL_MODULE_VOLTAGE", time.time(), 14.2 + np.random.normal(0, 0.05))
            time.sleep(0.01)

        alerts = engine.get_active_alerts(min_confidence=0.6)
        assert len(alerts) == 0


class TestBaselineModel:
    def test_train_and_score(self):
        model = BaselineModel("test-vehicle-temp")

        # Generate normal data
        np.random.seed(42)
        features = np.random.randn(100, 5) * 0.5 + 2.0

        model.train(features)
        assert model.is_trained

        # Normal sample should score low
        normal = np.array([2.0, 2.0, 2.0, 2.0, 0.1])
        score_normal = model.score(normal)

        # Anomalous sample should score higher
        anomaly = np.array([8.0, -5.0, 10.0, 0.0, 5.0])
        score_anomaly = model.score(anomaly)

        assert score_anomaly > score_normal


class TestOBDLogger:
    def test_simulation_mode(self):
        logger = OBDDataLogger(vehicle_id="test", mode="simulate")
        assert logger.connect()

        readings = []
        logger.register_callback(lambda r: readings.append(r))

        logger.start_streaming(duration=2)

        assert len(readings) > 0
        assert all(isinstance(r, SensorReading) for r in readings)
        assert all(r.vehicle_id == "test" for r in readings)

    def test_csv_persistence(self):
        logger = OBDDataLogger(vehicle_id="test-csv", mode="simulate")
        logger.connect()
        logger.start_streaming(duration=1)

        assert logger.session_file.exists()

        import csv
        with open(logger.session_file) as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) > 0
            assert "timestamp" in rows[0]
            assert "sensor_name" in rows[0]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
