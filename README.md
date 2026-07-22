# Engine Diagnostic Analyzer

Predictive failure detection for vehicles using OBD-II sensor data. Identifies failure modes before they cascade — the ground strap problem, but algorithmic.

## What It Does

Takes raw OBD-II sensor data from a car and identifies failure modes before they cascade. Directly connects to mechanic work and demonstrates systems thinking (symptom → cause, not symptom → replacement).

## Hardware Required

- **ELM327 USB/Bluetooth/WiFi adapter** (~$10–$25)
- **OBD-II extension cable** (optional, for easier laptop placement)
- Computer with Python 3.9+

## Quick Start

### 1. Install Dependencies

```bash
cd engine-diagnostic-analyzer
pip install -r requirements.txt
```

### 2. Connect to Your Car

1. Locate your car's OBD-II port (usually under the steering column, within 3 feet of the driver)
2. Plug in the ELM327 adapter
3. Connect the adapter to your computer:
   - **USB**: Plug cable directly, check Device Manager for COM port
   - **Bluetooth**: Pair the device (PIN usually 0000, 1234, or 5678)
   - **WiFi**: Connect to the adapter's network (SSID/password in manual)

### 3. Start the Dashboard

```bash
python dashboard/app.py
```

Open http://localhost:5000 in your browser.

### 4. Start Streaming

Click **"▶ Start Stream"** → select **"Live OBD-II"** mode → enter your vehicle ID → Start Streaming.

The system will auto-detect the correct COM port. If auto-detection fails, specify it manually:

```bash
# Windows
python dashboard/app.py
# Or set environment variable:
set OBD_PORT=COM3

# Linux
export OBD_PORT=/dev/ttyUSB0
python dashboard/app.py

# macOS
export OBD_PORT=/dev/tty.usbserial
python dashboard/app.py
```

## Training a Baseline

Before anomaly detection works well, train a baseline model on your specific vehicle's normal behavior:

```bash
python src/train_baseline.py --vehicle-id "honda-civic-2019" --mode live --duration 300
```

This captures 5 minutes of normal driving data and builds a per-vehicle "healthy" profile.

## Project Structure

```
engine-diagnostic-analyzer/
├── README.md
├── requirements.txt
├── src/
│   ├── config.py              # All tunable parameters
│   ├── obd_logger.py          # OBD-II data capture + simulation mode
│   ├── anomaly_engine.py      # ML + pattern-based failure detection
│   ├── failure_library.py     # 7 real failure signatures from shop experience
│   └── train_baseline.py      # CLI to train "normal" per-vehicle models
├── dashboard/
│   ├── app.py                 # Flask + SocketIO backend
│   └── templates/
│       └── index.html         # Real-time dark-mode dashboard
├── data/                      # Session CSVs + failure library JSON
├── models/                    # Trained Isolation Forest baselines
└── tests/
    └── test_anomaly_engine.py # Unit tests
```

## Failure Modes Detected

| Failure | Sensors | Severity |
|---------|---------|----------|
| Water Pump Bearing | Coolant ↑, Voltage ↓, RPM jitter | HIGH |
| Catalytic Converter | O2 sensors oscillating in phase | MEDIUM |
| Intake Vacuum Leak | MAP oscillation, lean trim | MEDIUM |
| Throttle Carbon | TPS micro-jumps, idle hunt | LOW |
| Alternator Degradation | Voltage drift under load | HIGH |
| Coil Pack Intermittent | RPM drops + rich O2 + timing retard | HIGH |
| Early Head Gasket | Sawtooth coolant temp | CRITICAL |

## Troubleshooting

| Problem | Fix |
|---------|-----|
| `ModuleNotFoundError: obd` | `pip install obd pyserial` |
| "No response from ECU" | Ensure ignition is ON (engine running or accessory mode) |
| "Cannot find port" | Check Device Manager (Windows) or `ls /dev/tty*` (Linux/macOS) |
| Address already in use | `lsof -ti:5000 \| xargs kill -9` |
| Dashboard blank | Check browser console for JS errors |

## What Makes This Stand Out

The failure signatures are built from actual shop experience, not textbook thresholds:
- **Water pump bearing**: Coolant temp ↑ + Voltage ↓ + RPM jitter (the ground strap lesson — voltage drop masked the real problem)
- **Coil pack intermittent**: RPM micro-drops + O2 rich spikes + timing retard (heat-soak failure pattern)
- **Early head gasket**: Sawtooth coolant temp + MAP oscillation (catches it before coolant in oil)

The system detects **patterns across sensors**, not single-value thresholds. That's the systems-thinking differentiator.
