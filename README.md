# Engine Diagnostic Analyzer

> Real-time OBD-II engine diagnostics with predictive failure detection. Built from hands-on mechanic experience — not just sensor thresholds, but failure *patterns*.

## What It Does

This system connects to a vehicle's OBD-II port, streams live sensor data, and identifies failure modes **before** they cascade into breakdowns. Instead of flagging "coolant temp is high," it recognizes signatures like *"coolant temp rising + voltage dropping + RPM fluctuating = failing water pump bearing."*

## Architecture

```
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│   OBD-II Port   │────▶│   Data Logger    │────▶│  Signal Store   │
│  (Live Vehicle) │     │  (obd_logger.py) │     │  (CSV/SQLite)   │
└─────────────────┘     └──────────────────┘     └─────────────────┘
                                                          │
                                                          ▼
┌─────────────────┐     ┌──────────────────┐     ┌─────────────────┐
│    Dashboard    │◀────│  Anomaly Engine  │◀────│  Baseline ML    │
│  (Flask + JS)   │     │ (anomaly_engine) │     │  (scikit-learn) │
└─────────────────┘     └──────────────────┘     └─────────────────┘
         │
         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    Failure Mode Library                              │
│   Maps sensor signatures to real-world failures from shop experience │
└─────────────────────────────────────────────────────────────────────┘
```

## Key Components

| File | Purpose |
|------|---------|
| `obd_logger.py` | Connects to OBD-II, streams sensor data |
| `anomaly_engine.py` | Detects multi-sensor pattern deviations |
| `failure_library.py` | Database of known failures mapped to sensor signatures |
| `dashboard/app.py` | Web interface showing live data, flagged anomalies, predicted failure modes |
| `train_baseline.py` | Builds normal-operation models per vehicle |

## Installation

```bash
pip install -r requirements.txt
```

For OBD-II hardware connection, you'll need an ELM327 Bluetooth/WiFi adapter.

## Usage

### 1. Train Baseline (Normal Operation)
```bash
python src/train_baseline.py --vehicle-id "honda-civic-2019" --duration 300
```

### 2. Start Live Monitoring
```bash
python src/obd_logger.py --vehicle-id "honda-civic-2019" --mode live
```

### 3. Launch Dashboard
```bash
python dashboard/app.py
# Open http://localhost:5000
```

## Failure Signatures (from shop experience)

| Signature | Predicted Failure | Confidence |
|-----------|-------------------|------------|
| Coolant temp ↑ + Voltage ↓ + RPM jitter | Water pump bearing | High |
| O2 sensor slow response + Rich trim | Catalytic converter degradation | Medium |
| MAP pressure oscillation + Misfire count ↑ | Intake manifold leak | High |
| Throttle position erratic + Idle RPM hunt | Throttle body carbon buildup | Medium |

## Tech Stack

- **Python** — data processing & ML
- **Pandas/NumPy** — signal analysis
- **scikit-learn** — anomaly detection (Isolation Forest + PCA)
- **Flask + SocketIO** — real-time dashboard
- **OBD-II (python-obd)** — vehicle data capture

## License

MIT
