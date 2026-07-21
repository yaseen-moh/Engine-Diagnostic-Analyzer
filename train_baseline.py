"""
Train Baseline Model

Captures normal operation data from a vehicle and trains an Isolation Forest
model to recognize "healthy" behavior. This becomes the reference for anomaly detection.

Usage:
    python train_baseline.py --vehicle-id "honda-civic-2019" --duration 300 --mode simulate
"""

import argparse
import time
import logging
from pathlib import Path

import numpy as np

from config import DATA_DIR, MODELS_DIR, SENSOR_RATES
from obd_logger import OBDDataLogger
from anomaly_engine import BaselineModel, SensorWindow

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def capture_and_train(
    vehicle_id: str,
    duration: float = 300,
    mode: str = "simulate",
    port: str = None
):
    """
    Capture normal operation data and train baseline model.

    Args:
        vehicle_id: Unique vehicle identifier
        duration: Seconds of normal data to capture
        mode: "live" or "simulate"
        port: OBD port (optional)
    """
    logger.info(f"═" * 60)
    logger.info(f"BASELINE TRAINING: {vehicle_id}")
    logger.info(f"Duration: {duration}s | Mode: {mode}")
    logger.info(f"═" * 60)

    # Initialize logger
    kwargs = {"vehicle_id": vehicle_id, "mode": mode}
    if port:
        kwargs["port"] = port

    logger_obj = OBDDataLogger(**kwargs)

    if not logger_obj.connect():
        logger.error("Failed to connect")
        return None

    # Collect data
    logger.info("Capturing normal operation data...")
    logger.info("Ensure vehicle is at normal operating temperature and idling smoothly.")

    # Buffer for feature extraction
    sensor_buffers = {s: [] for s in SENSOR_RATES.keys()}
    start_time = time.time()

    def on_reading(reading):
        sensor_buffers[reading.sensor_name].append((reading.timestamp, reading.value))

    logger_obj.register_callback(on_reading)

    try:
        logger_obj.start_streaming(duration=duration)
    except KeyboardInterrupt:
        logger.info("Training interrupted by user")

    # Build feature vectors from buffered data
    logger.info("Building feature vectors...")

    from anomaly_engine import train_baseline_from_csv
    baseline = train_baseline_from_csv(vehicle_id, str(logger_obj.session_file))

    logger.info(f"✓ Baseline model saved to {MODELS_DIR / f'{vehicle_id}_baseline.pkl'}")
    logger.info(f"✓ Training data saved to {logger_obj.session_file}")

    return baseline


def main():
    parser = argparse.ArgumentParser(description="Train vehicle baseline model")
    parser.add_argument("--vehicle-id", required=True, help="Vehicle identifier")
    parser.add_argument("--duration", type=float, default=300,
                        help="Capture duration in seconds (default: 300)")
    parser.add_argument("--mode", choices=["live", "simulate"], default="simulate")
    parser.add_argument("--port", default=None, help="OBD serial port")

    args = parser.parse_args()

    capture_and_train(
        vehicle_id=args.vehicle_id,
        duration=args.duration,
        mode=args.mode,
        port=args.port
    )


if __name__ == "__main__":
    main()
