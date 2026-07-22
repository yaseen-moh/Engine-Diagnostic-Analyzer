"""
Configuration for Engine Diagnostic Analyzer.
All tunable parameters in one place.
"""

import os
from pathlib import Path

# Project paths
BASE_DIR = Path(__file__).parent.parent
DATA_DIR = BASE_DIR / "data"
MODELS_DIR = BASE_DIR / "models"
DASHBOARD_DIR = BASE_DIR / "dashboard"

# Ensure directories exist
for d in [DATA_DIR, MODELS_DIR]:
    d.mkdir(exist_ok=True)

# ═══════════════════════════════════════════════════════════════
# OBD-II CONNECTION SETTINGS
# ═══════════════════════════════════════════════════════════════

# Auto-detect port if not specified (tries common ports)
OBD_PORT = os.getenv("OBD_PORT", "auto")
OBD_BAUDRATE = int(os.getenv("OBD_BAUDRATE", "38400"))
OBD_TIMEOUT = float(os.getenv("OBD_TIMEOUT", "3.0"))

# Common OBD ports by OS (for auto-detection)
COMMON_PORTS = {
    "windows": ["COM3", "COM4", "COM5", "COM6", "COM7"],
    "linux": ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/rfcomm0", "/dev/rfcomm1"],
    "darwin": ["/dev/tty.usbserial", "/dev/tty.OBD-II-SPP"]
}

# Sensor polling rates (Hz) — don't overwhelm the ECU
SENSOR_RATES = {
    "RPM": 10,
    "COOLANT_TEMP": 2,
    "INTAKE_TEMP": 2,
    "MAF": 5,
    "THROTTLE_POS": 5,
    "ENGINE_LOAD": 5,
    "TIMING_ADVANCE": 5,
    "O2_B1S1": 2,
    "O2_B1S2": 2,
    "SHORT_FUEL_TRIM_1": 2,
    "LONG_FUEL_TRIM_1": 1,
    "MAP": 5,
    "BAROMETRIC_PRESSURE": 1,
    "SPEED": 5,
    "RUN_TIME": 1,
    "DISTANCE_W_MIL": 1,
    "CONTROL_MODULE_VOLTAGE": 5,
}

# Anomaly Detection Settings
ANOMALY_WINDOW_SIZE = 30
ANOMALY_CONTAMINATION = 0.05
ANOMALY_N_ESTIMATORS = 100

# Failure Prediction Thresholds
FAILURE_CONFIDENCE_HIGH = 0.70
FAILURE_CONFIDENCE_MEDIUM = 0.45
FAILURE_CONFIDENCE_LOW = 0.25

# Alert cooldown (seconds)
ALERT_COOLDOWN = 30

# Dashboard
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "0.0.0.0")
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "5000"))
DASHBOARD_UPDATE_INTERVAL = 1.0
