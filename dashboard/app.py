"""
Engine Diagnostic Dashboard

Real-time web interface showing:
- Live sensor gauges
- Anomaly timeline
- Failure mode predictions with confidence scores
- Historical trend charts

Stack: Flask + Flask-SocketIO + Plotly.js
"""

import json
import logging
import threading
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, render_template, jsonify
from flask_socketio import SocketIO, emit

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from config import (
    DASHBOARD_HOST, DASHBOARD_PORT, DASHBOARD_UPDATE_INTERVAL,
    SENSOR_RATES, DATA_DIR
)
from obd_logger import OBDDataLogger, SensorReading
from anomaly_engine import AnomalyEngine, AnomalyAlert
from failure_library import get_all_failure_modes, Severity

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.config["SECRET_KEY"] = "engine-diagnostic-secret"
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")

# ═══════════════════════════════════════════════════════════════
# GLOBAL STATE
# ═══════════════════════════════════════════════════════════════

class DashboardState:
    def __init__(self):
        self.logger: OBDDataLogger = None
        self.engine: AnomalyEngine = None
        self.is_streaming = False
        self.latest_readings: dict = {}
        self.alert_history: list = []
        self.sensor_history: dict = {s: [] for s in SENSOR_RATES.keys()}
        self.max_history = 300
        self._lock = threading.Lock()

    def on_sensor_reading(self, reading: SensorReading):
        """Callback from OBD logger."""
        with self._lock:
            self.latest_readings[reading.sensor_name] = {
                "value": round(reading.value, 2),
                "timestamp": reading.timestamp,
                "unit": reading.unit,
            }

            self.sensor_history[reading.sensor_name].append({
                "x": datetime.fromtimestamp(reading.timestamp).strftime("%H:%M:%S"),
                "y": round(reading.value, 2)
            })
            if len(self.sensor_history[reading.sensor_name]) > self.max_history:
                self.sensor_history[reading.sensor_name].pop(0)

        if self.engine:
            self.engine.ingest(reading.sensor_name, reading.timestamp, reading.value)

    def on_anomaly_alert(self, alert: AnomalyAlert):
        """Callback from anomaly engine."""
        with self._lock:
            self.alert_history.insert(0, {
                "timestamp": datetime.fromtimestamp(alert.timestamp).strftime("%H:%M:%S"),
                "failure_name": alert.failure_name,
                "severity": alert.severity,
                "confidence": alert.confidence,
                "description": alert.description,
                "action": alert.recommended_action,
                "sensors": alert.triggered_sensors,
                "snapshot": alert.sensor_snapshot,
            })

        socketio.emit("new_alert", self.alert_history[0])

    def start_streaming(self, vehicle_id: str, mode: str = "simulate"):
        if self.is_streaming:
            return False

        self.logger = OBDDataLogger(vehicle_id=vehicle_id, mode=mode)
        self.engine = AnomalyEngine(vehicle_id=vehicle_id, sensors=list(SENSOR_RATES.keys()))

        self.logger.register_callback(self.on_sensor_reading)
        self.engine.register_alert_callback(self.on_anomaly_alert)

        if not self.logger.connect():
            return False

        self.is_streaming = True

        def stream():
            try:
                self.logger.start_streaming()
            except Exception as e:
                logger.error(f"Stream error: {e}")
            finally:
                self.is_streaming = False

        thread = threading.Thread(target=stream, daemon=True)
        thread.start()

        def broadcast():
            while self.is_streaming:
                with self._lock:
                    socketio.emit("sensor_update", {
                        "readings": self.latest_readings,
                        "history": {k: v[-50:] for k, v in self.sensor_history.items()}
                    })
                time.sleep(DASHBOARD_UPDATE_INTERVAL)

        broadcast_thread = threading.Thread(target=broadcast, daemon=True)
        broadcast_thread.start()

        return True

    def stop_streaming(self):
        if self.logger:
            self.logger.disconnect()
        self.is_streaming = False

state = DashboardState()

# ═══════════════════════════════════════════════════════════════
# FLASK ROUTES
# ═══════════════════════════════════════════════════════════════

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/failure-modes")
def api_failure_modes():
    modes = get_all_failure_modes()
    return jsonify([{
        "id": m.id,
        "name": m.name,
        "severity": m.severity.value,
        "description": m.description,
        "repair": m.typical_repair,
        "early_warning": m.early_warning_seconds,
        "dtcs": m.related_dtcs,
    } for m in modes])

@app.route("/api/alerts")
def api_alerts():
    return jsonify(state.alert_history[:50])

@app.route("/api/sensors")
def api_sensors():
    return jsonify(state.latest_readings)

# ═══════════════════════════════════════════════════════════════
# SOCKET.IO EVENTS
# ═══════════════════════════════════════════════════════════════

@socketio.on("connect")
def handle_connect():
    logger.info("Client connected")
    emit("init", {
        "sensors": list(SENSOR_RATES.keys()),
        "failure_modes": len(get_all_failure_modes()),
        "streaming": state.is_streaming,
    })

@socketio.on("disconnect")
def handle_disconnect():
    logger.info("Client disconnected")

@socketio.on("start_stream")
def handle_start_stream(data):
    vehicle_id = data.get("vehicle_id", "demo-vehicle")
    mode = data.get("mode", "simulate")

    if state.start_streaming(vehicle_id, mode):
        emit("stream_status", {"status": "started", "vehicle_id": vehicle_id, "mode": mode})
    else:
        emit("stream_status", {"status": "error", "message": "Failed to start stream"})

@socketio.on("stop_stream")
def handle_stop_stream():
    state.stop_streaming()
    emit("stream_status", {"status": "stopped"})

# ═══════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════

if __name__ == "__main__":
    logger.info(f"Starting dashboard on http://{DASHBOARD_HOST}:{DASHBOARD_PORT}")
    socketio.run(app, host=DASHBOARD_HOST, port=DASHBOARD_PORT, debug=False, use_reloader=False)
