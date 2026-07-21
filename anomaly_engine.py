"""
Anomaly Detection Engine

Uses scikit-learn Isolation Forest for baseline deviation detection,
plus custom pattern matching against the Failure Mode Library.

Key insight: A single sensor going out of range is noise.
Three sensors moving in a correlated pattern is a signature.
"""

import time
import json
import logging
from collections import deque, defaultdict
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.decomposition import PCA
import joblib

from config import (
    MODELS_DIR, ANOMALY_WINDOW_SIZE, ANOMALY_CONTAMINATION,
    ANOMALY_N_ESTIMATORS, ALERT_COOLDOWN, FAILURE_CONFIDENCE_HIGH,
    FAILURE_CONFIDENCE_MEDIUM, FAILURE_CONFIDENCE_LOW
)
from failure_library import (
    FailureMode, SensorPattern, Trend, Severity,
    get_all_failure_modes, get_failure_mode
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class AnomalyAlert:
    """Structured alert output."""
    timestamp: float
    vehicle_id: str
    failure_mode_id: str
    failure_name: str
    severity: str
    confidence: float
    triggered_sensors: List[str]
    description: str
    recommended_action: str
    sensor_snapshot: Dict[str, float]


class SensorWindow:
    """Rolling window of sensor readings with trend analysis."""

    def __init__(self, sensor_name: str, max_size: int = ANOMALY_WINDOW_SIZE):
        self.sensor_name = sensor_name
        self.max_size = max_size
        self.readings: deque = deque(maxlen=max_size)
        self.timestamps: deque = deque(maxlen=max_size)

    def add(self, timestamp: float, value: float):
        self.readings.append(value)
        self.timestamps.append(timestamp)

    def is_ready(self) -> bool:
        return len(self.readings) >= self.max_size // 2

    def get_trend(self) -> Optional[Trend]:
        """Determine trend from window data."""
        if not self.is_ready():
            return None

        arr = np.array(self.readings)

        # Linear regression slope
        x = np.arange(len(arr))
        slope = np.polyfit(x, arr, 1)[0]

        # Variance
        variance = np.var(arr)

        # Coefficient of variation (normalized variance)
        mean_val = np.mean(arr)
        cv = variance / abs(mean_val) if mean_val != 0 else 0

        # Oscillation detection: count direction changes
        diffs = np.diff(arr)
        sign_changes = np.sum(diffs[:-1] * diffs[1:] < 0)
        oscillation_ratio = sign_changes / len(diffs) if len(diffs) > 0 else 0

        # Classify
        if oscillation_ratio > 0.4 and variance > 1.0:
            return Trend.OSCILLATING
        elif cv > 0.15 and variance > 10:  # High relative variance
            return Trend.JITTER
        elif slope > 0.1:
            return Trend.RISING
        elif slope < -0.1:
            return Trend.FALLING
        else:
            return Trend.STABLE

    def get_stats(self) -> Dict:
        """Get statistical summary of window."""
        if not self.is_ready():
            return {}
        arr = np.array(self.readings)
        return {
            "mean": float(np.mean(arr)),
            "std": float(np.std(arr)),
            "min": float(np.min(arr)),
            "max": float(np.max(arr)),
            "variance": float(np.var(arr)),
            "rate_of_change": float(np.polyfit(np.arange(len(arr)), arr, 1)[0]),
        }

    def to_feature_vector(self) -> np.ndarray:
        """Convert window to feature vector for ML."""
        stats = self.get_stats()
        if not stats:
            return np.zeros(5)
        return np.array([
            stats["mean"],
            stats["std"],
            stats["min"],
            stats["max"],
            stats["rate_of_change"],
        ])


class BaselineModel:
    """
    Per-vehicle baseline model trained on normal operation data.
    Uses Isolation Forest to detect when current behavior deviates from learned normal.
    """

    def __init__(self, vehicle_id: str):
        self.vehicle_id = vehicle_id
        self.model_path = MODELS_DIR / f"{vehicle_id}_baseline.pkl"
        self.scaler_path = MODELS_DIR / f"{vehicle_id}_scaler.pkl"

        self.model: Optional[IsolationForest] = None
        self.scaler: Optional[StandardScaler] = None
        self.is_trained = False

        self._load()

    def _load(self):
        """Load existing model if available."""
        if self.model_path.exists() and self.scaler_path.exists():
            try:
                self.model = joblib.load(self.model_path)
                self.scaler = joblib.load(self.scaler_path)
                self.is_trained = True
                logger.info(f"Loaded baseline model for {self.vehicle_id}")
            except Exception as e:
                logger.error(f"Failed to load model: {e}")

    def train(self, features: np.ndarray):
        """Train baseline on normal operation features."""
        if len(features) < 50:
            logger.warning("Insufficient data for baseline training (< 50 samples)")
            return

        self.scaler = StandardScaler()
        scaled = self.scaler.fit_transform(features)

        self.model = IsolationForest(
            n_estimators=ANOMALY_N_ESTIMATORS,
            contamination=ANOMALY_CONTAMINATION,
            random_state=42,
            n_jobs=-1
        )
        self.model.fit(scaled)
        self.is_trained = True

        # Persist
        joblib.dump(self.model, self.model_path)
        joblib.dump(self.scaler, self.scaler_path)
        logger.info(f"Trained and saved baseline model for {self.vehicle_id}")

    def score(self, features: np.ndarray) -> float:
        """
        Returns anomaly score.
        Negative = anomaly. Positive = normal.
        We normalize to 0-1 where 1 = highly anomalous.
        """
        if not self.is_trained:
            return 0.0

        scaled = self.scaler.transform(features.reshape(1, -1))
        score = self.model.score_samples(scaled)[0]
        # Isolation Forest: lower score = more anomalous
        # Normalize: typical range is -0.5 to 0.0
        normalized = max(0, min(1, (-score - 0.3) / 0.3))
        return float(normalized)


class AnomalyEngine:
    """
    Real-time anomaly detection engine.

    Combines:
    1. ML baseline deviation (Isolation Forest)
    2. Rule-based pattern matching against Failure Mode Library
    3. Confidence scoring based on sensor correlation strength
    """

    def __init__(self, vehicle_id: str, sensors: List[str]):
        self.vehicle_id = vehicle_id
        self.sensors = sensors

        # Rolling windows per sensor
        self.windows: Dict[str, SensorWindow] = {
            s: SensorWindow(s) for s in sensors
        }

        # Baseline ML model
        self.baseline = BaselineModel(vehicle_id)

        # Failure mode library
        self.failure_modes = get_all_failure_modes()

        # Alert state
        self.last_alert_time: Dict[str, float] = {}
        self.active_alerts: List[AnomalyAlert] = []

        # Callbacks for real-time notifications
        self.alert_callbacks: List[Callable[[AnomalyAlert], None]] = []

    def register_alert_callback(self, callback):
        self.alert_callbacks.append(callback)

    def ingest(self, sensor_name: str, timestamp: float, value: float):
        """Feed a new sensor reading into the engine."""
        if sensor_name not in self.windows:
            return

        self.windows[sensor_name].add(timestamp, value)

        # Check if enough data to evaluate
        ready_sensors = [s for s in self.sensors if self.windows[s].is_ready()]
        if len(ready_sensors) >= 3:
            self._evaluate()

    def _evaluate(self):
        """Run full anomaly evaluation cycle."""
        # 1. Build feature vector from all sensor windows
        feature_vector = np.concatenate([
            self.windows[s].to_feature_vector() for s in self.sensors
        ])

        # 2. Get ML anomaly score
        ml_score = self.baseline.score(feature_vector)

        # 3. Pattern match against failure modes
        for failure_mode in self.failure_modes:
            confidence = self._match_failure_mode(failure_mode)

            if confidence >= FAILURE_CONFIDENCE_LOW:
                self._maybe_alert(failure_mode, confidence, ml_score)

    def _match_failure_mode(self, fm: FailureMode) -> float:
        """
        Match current sensor state against a failure mode's signatures.
        Returns confidence score 0-1.

        Signature logic: OR groups of AND patterns.
        Within a group, all patterns must match. Any group matching triggers the signature.
        """
        if not fm.signatures:
            return 0.0

        best_group_score = 0.0

        for group in fm.signatures:
            group_matches = 0
            group_weight = 0

            for pattern in group:
                window = self.windows.get(pattern.sensor)
                if not window or not window.is_ready():
                    continue

                stats = window.get_stats()
                current_trend = window.get_trend()

                matched = self._pattern_matches(pattern, stats, current_trend)
                weight = fm.confidence_weights.get(pattern.sensor, 0.1)

                if matched:
                    group_matches += weight
                group_weight += weight

            if group_weight > 0:
                group_score = group_matches / group_weight
                best_group_score = max(best_group_score, group_score)

        return best_group_score

    def _pattern_matches(self, pattern: SensorPattern, stats: Dict, current_trend: Trend) -> bool:
        """Check if a single sensor pattern matches current state."""
        if current_trend != pattern.trend:
            return False

        if pattern.threshold is not None:
            if pattern.trend == Trend.RISING and stats.get("max", 0) < pattern.threshold:
                return False
            if pattern.trend == Trend.FALLING and stats.get("min", 0) > pattern.threshold:
                return False

        if pattern.rate_of_change is not None:
            roc = stats.get("rate_of_change", 0)
            if pattern.trend == Trend.RISING and roc < pattern.rate_of_change:
                return False
            if pattern.trend == Trend.FALLING and roc > pattern.rate_of_change:
                return False

        if pattern.variance_threshold is not None:
            if stats.get("variance", 0) < pattern.variance_threshold:
                return False

        return True

    def _maybe_alert(self, fm: FailureMode, confidence: float, ml_score: float):
        """Generate alert if confidence exceeds threshold and cooldown passed."""
        now = time.time()

        # Cooldown check
        last_time = self.last_alert_time.get(fm.id, 0)
        if now - last_time < ALERT_COOLDOWN:
            return

        # Combine pattern confidence with ML anomaly score
        combined_confidence = (confidence * 0.7) + (ml_score * 0.3)

        # Determine severity escalation
        if combined_confidence >= FAILURE_CONFIDENCE_HIGH:
            severity = fm.severity.value
        elif combined_confidence >= FAILURE_CONFIDENCE_MEDIUM:
            severity = Severity.MEDIUM.value
        else:
            severity = Severity.LOW.value

        # Build sensor snapshot
        snapshot = {}
        for sensor in fm.confidence_weights.keys():
            w = self.windows.get(sensor)
            if w and w.is_ready():
                snapshot[sensor] = w.get_stats().get("mean", 0)

        alert = AnomalyAlert(
            timestamp=now,
            vehicle_id=self.vehicle_id,
            failure_mode_id=fm.id,
            failure_name=fm.name,
            severity=severity,
            confidence=round(combined_confidence, 3),
            triggered_sensors=list(fm.confidence_weights.keys()),
            description=fm.description,
            recommended_action=fm.typical_repair,
            sensor_snapshot=snapshot
        )

        self.active_alerts.append(alert)
        self.last_alert_time[fm.id] = now

        # Notify callbacks
        for cb in self.alert_callbacks:
            try:
                cb(alert)
            except Exception as e:
                logger.error(f"Alert callback error: {e}")

        logger.warning(
            f"🚨 ALERT [{severity.upper()}] {fm.name} "
            f"(confidence: {combined_confidence:.2f}) — {fm.typical_repair[:60]}..."
        )

    def get_active_alerts(self, min_confidence: float = 0.0) -> List[AnomalyAlert]:
        """Get current active alerts, optionally filtered by confidence."""
        return [a for a in self.active_alerts if a.confidence >= min_confidence]

    def clear_alerts(self):
        """Clear all active alerts."""
        self.active_alerts = []

    def export_alerts(self, path: str):
        """Export alerts to JSON."""
        data = [asdict(a) for a in self.active_alerts]
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return path


# ═══════════════════════════════════════════════════════════════
# TRAINING SCRIPT (separate file also available)
# ═══════════════════════════════════════════════════════════════

def train_baseline_from_csv(vehicle_id: str, csv_path: str) -> BaselineModel:
    """Train baseline model from historical normal-operation CSV data."""
    logger.info(f"Training baseline for {vehicle_id} from {csv_path}")

    df = pd.read_csv(csv_path)

    # Pivot to wide format: each row = timestamp, columns = sensors
    df_pivot = df.pivot_table(
        index="timestamp",
        columns="sensor_name",
        values="value",
        aggfunc="mean"
    ).fillna(method="ffill").fillna(method="bfill")

    # Build feature vectors from rolling windows
    from config import SENSOR_RATES
    sensors = list(SENSOR_RATES.keys())

    features = []
    window_size = ANOMALY_WINDOW_SIZE

    for i in range(window_size, len(df_pivot)):
        window = df_pivot.iloc[i-window_size:i]
        feature = []
        for sensor in sensors:
            if sensor in window.columns:
                arr = window[sensor].values
                feature.extend([
                    np.mean(arr),
                    np.std(arr),
                    np.min(arr),
                    np.max(arr),
                    np.polyfit(np.arange(len(arr)), arr, 1)[0],
                ])
            else:
                feature.extend([0, 0, 0, 0, 0])
        features.append(feature)

    features = np.array(features)

    baseline = BaselineModel(vehicle_id)
    baseline.train(features)

    return baseline


if __name__ == "__main__":
    # Quick test
    engine = AnomalyEngine("test-vehicle", ["RPM", "COOLANT_TEMP", "CONTROL_MODULE_VOLTAGE"])

    # Simulate some data
    for i in range(100):
        engine.ingest("RPM", time.time(), 750 + np.random.normal(0, 10))
        engine.ingest("COOLANT_TEMP", time.time(), 90 + i * 0.1)
        engine.ingest("CONTROL_MODULE_VOLTAGE", time.time(), 14.2 - i * 0.005)
        time.sleep(0.01)

    alerts = engine.get_active_alerts()
    print(f"Generated {len(alerts)} alerts")
    for a in alerts:
        print(f"  - {a.failure_name}: {a.confidence}")
