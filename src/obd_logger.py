"""
OBD-II Data Logger
Connects to vehicle ECU via ELM327 adapter, streams sensor data.
Supports live mode (real vehicle) and simulation mode (demo/replay).
"""

import time
import csv
import json
import logging
import platform
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Callable
from dataclasses import dataclass, asdict

import obd
from obd import OBDStatus

from config import (
    DATA_DIR, OBD_PORT, OBD_BAUDRATE, OBD_TIMEOUT, 
    SENSOR_RATES, COMMON_PORTS
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)


@dataclass
class SensorReading:
    """Single sensor snapshot."""
    timestamp: float
    sensor_name: str
    value: float
    unit: str
    vehicle_id: str


class OBDDataLogger:
    """
    Streams OBD-II sensor data and persists to CSV.

    Usage:
        logger = OBDDataLogger(vehicle_id="honda-civic-2019")
        logger.connect()
        logger.start_streaming(duration=300)  # 5 minutes
    """

    # Map friendly names to python-obd command objects
    COMMANDS = {
        "RPM": obd.commands.RPM,
        "COOLANT_TEMP": obd.commands.COOLANT_TEMP,
        "INTAKE_TEMP": obd.commands.INTAKE_TEMP,
        "MAF": obd.commands.MAF,
        "THROTTLE_POS": obd.commands.THROTTLE_POS,
        "ENGINE_LOAD": obd.commands.ENGINE_LOAD,
        "TIMING_ADVANCE": obd.commands.TIMING_ADVANCE,
        "O2_B1S1": obd.commands.O2_B1S1,
        "O2_B1S2": obd.commands.O2_B1S2,
        "SHORT_FUEL_TRIM_1": obd.commands.SHORT_FUEL_TRIM_1,
        "LONG_FUEL_TRIM_1": obd.commands.LONG_FUEL_TRIM_1,
        "MAP": obd.commands.INTAKE_PRESSURE,
        "BAROMETRIC_PRESSURE": obd.commands.BAROMETRIC_PRESSURE,
        "SPEED": obd.commands.SPEED,
        "RUN_TIME": obd.commands.RUN_TIME,
        "DISTANCE_W_MIL": obd.commands.DISTANCE_W_MIL,
        "CONTROL_MODULE_VOLTAGE": obd.commands.CONTROL_MODULE_VOLTAGE,
    }

    def __init__(
        self,
        vehicle_id: str,
        port: str = OBD_PORT,
        baudrate: int = OBD_BAUDRATE,
        timeout: float = OBD_TIMEOUT,
        mode: str = "live"  # "live" or "simulate"
    ):
        self.vehicle_id = vehicle_id
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self.mode = mode

        self.connection: Optional[obd.OBD] = None
        self.is_connected = False
        self.callbacks: List[Callable[[SensorReading], None]] = []

        # Data storage
        self.session_file = DATA_DIR / f"{vehicle_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self._init_csv()

        # Simulation state (for demo mode)
        self._sim_state = self._init_simulation()

    def _init_csv(self):
        """Initialize CSV with headers."""
        with open(self.session_file, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp", "sensor_name", "value", "unit", "vehicle_id"])
            writer.writeheader()

    def _init_simulation(self) -> Dict:
        """Initialize simulation state for demo without real OBD hardware."""
        import random
        return {
            "rpm": 750,
            "coolant_temp": 90,
            "voltage": 14.2,
            "throttle": 0,
            "maf": 2.5,
            "map": 35,
            "engine_load": 15.0,
            "o2_b1s1": 0.45,
            "short_trim": 0.0,
            "long_trim": 0.0,
            "speed": 0,
            "run_time": 0,
            "intake_temp": 35,
            "timing": 5.0,
            "distance_mil": 0,
            "baro": 101.3,
            "trend": "normal",
            "trend_timer": 0,
        }

    def _find_port(self) -> str:
        """Auto-detect OBD port based on OS."""
        system = platform.system().lower()
        if system == "windows":
            ports = COMMON_PORTS["windows"]
        elif system == "linux":
            ports = COMMON_PORTS["linux"]
        elif system == "darwin":
            ports = COMMON_PORTS["darwin"]
        else:
            ports = COMMON_PORTS["linux"]

        for port in ports:
            try:
                logger.info(f"Trying port {port}...")
                test_conn = obd.OBD(port, baudrate=self.baudrate, timeout=2)
                if test_conn.status() == OBDStatus.CAR_CONNECTED:
                    test_conn.close()
                    logger.info(f"✓ Found working port: {port}")
                    return port
                test_conn.close()
            except Exception:
                continue

        logger.warning("Could not auto-detect port. Using default.")
        return ports[0] if ports else "COM3"

    def connect(self) -> bool:
        """Establish OBD-II connection or enter simulation mode."""
        if self.mode == "simulate":
            logger.info("[SIMULATE] Running in simulation mode — no OBD hardware needed")
            self.is_connected = True
            return True

        # Auto-detect port if set to "auto"
        if self.port == "auto":
            self.port = self._find_port()

        try:
            logger.info(f"Connecting to OBD on {self.port}...")
            self.connection = obd.OBD(
                self.port,
                baudrate=self.baudrate,
                timeout=self.timeout
            )

            if self.connection.status() == OBDStatus.CAR_CONNECTED:
                self.is_connected = True
                logger.info("✓ Connected to vehicle ECU")

                # Log supported commands
                supported = [cmd.name for cmd in self.connection.supported_commands if not cmd.name.startswith("_")]
                logger.info(f"Supported commands: {len(supported)}")
                return True
            else:
                logger.warning(f"OBD status: {self.connection.status()}. Switching to simulation.")
                self.mode = "simulate"
                self.is_connected = True
                return True

        except Exception as e:
            logger.error(f"Connection failed: {e}. Switching to simulation.")
            self.mode = "simulate"
            self.is_connected = True
            return True

    def disconnect(self):
        """Close OBD connection."""
        if self.connection:
            self.connection.close()
        self.is_connected = False
        logger.info("Disconnected")

    def register_callback(self, callback: Callable[[SensorReading], None]):
        """Register a callback for real-time data processing."""
        self.callbacks.append(callback)

    def _read_live(self, sensor_name: str) -> Optional[SensorReading]:
        """Read a single sensor from live OBD connection."""
        if not self.connection or sensor_name not in self.COMMANDS:
            return None

        cmd = self.COMMANDS[sensor_name]
        response = self.connection.query(cmd)

        if response.is_null():
            return None

        return SensorReading(
            timestamp=time.time(),
            sensor_name=sensor_name,
            value=float(response.value.magnitude) if hasattr(response.value, "magnitude") else float(response.value),
            unit=str(response.value.units) if hasattr(response.value, "units") else "",
            vehicle_id=self.vehicle_id
        )

    def _read_simulated(self, sensor_name: str) -> SensorReading:
        """Generate realistic simulated sensor data."""
        import random
        import math

        s = self._sim_state
        s["run_time"] += 0.1
        s["trend_timer"] += 0.1

        # Simulate a developing failure after 60 seconds
        if s["trend_timer"] > 60 and s["trend"] == "normal":
            if random.random() < 0.3:
                s["trend"] = "degrading"
                logger.info("[SIM] Vehicle entering degraded state (water pump bearing simulation)")

        if s["trend_timer"] > 120 and s["trend"] == "degrading":
            if random.random() < 0.3:
                s["trend"] = "failing"
                logger.info("[SIM] Vehicle entering failing state")

        # Update simulated physics
        if s["trend"] == "normal":
            s["rpm"] = max(600, min(800, s["rpm"] + random.gauss(0, 10)))
            s["coolant_temp"] = min(95, s["coolant_temp"] + 0.01)
            s["voltage"] = max(13.8, min(14.6, s["voltage"] + random.gauss(0, 0.05)))
            s["throttle"] = max(0, min(5, s["throttle"] + random.gauss(0, 0.5)))
            s["map"] = max(30, min(40, s["map"] + random.gauss(0, 1)))

        elif s["trend"] == "degrading":
            s["coolant_temp"] += 0.05 + random.gauss(0, 0.1)
            s["voltage"] -= 0.002 + random.gauss(0, 0.02)
            s["rpm"] += random.gauss(0, 25)
            s["throttle"] = max(0, s["throttle"] + random.gauss(0, 0.3))
            s["map"] += random.gauss(0, 2)

        elif s["trend"] == "failing":
            s["coolant_temp"] += 0.15 + random.gauss(0, 0.3)
            s["voltage"] -= 0.005 + random.gauss(0, 0.03)
            s["rpm"] += random.gauss(0, 50)
            s["throttle"] = max(0, s["throttle"] + random.gauss(0, 1.0))
            s["maf"] += random.gauss(0, 0.3)

        value_map = {
            "RPM": s["rpm"],
            "COOLANT_TEMP": s["coolant_temp"],
            "INTAKE_TEMP": s["intake_temp"] + random.gauss(0, 1),
            "MAF": s["maf"] + random.gauss(0, 0.1),
            "THROTTLE_POS": s["throttle"],
            "ENGINE_LOAD": s["engine_load"] + random.gauss(0, 2),
            "TIMING_ADVANCE": s["timing"] + random.gauss(0, 0.5),
            "O2_B1S1": s["o2_b1s1"] + random.gauss(0, 0.05),
            "O2_B1S2": s["o2_b1s1"] + random.gauss(0, 0.05) + 0.1,
            "SHORT_FUEL_TRIM_1": s["short_trim"] + random.gauss(0, 1),
            "LONG_FUEL_TRIM_1": s["long_trim"] + random.gauss(0, 0.5),
            "MAP": s["map"],
            "BAROMETRIC_PRESSURE": s["baro"],
            "SPEED": s["speed"],
            "RUN_TIME": s["run_time"],
            "DISTANCE_W_MIL": s["distance_mil"],
            "CONTROL_MODULE_VOLTAGE": s["voltage"],
        }

        return SensorReading(
            timestamp=time.time(),
            sensor_name=sensor_name,
            value=value_map.get(sensor_name, 0.0),
            unit="sim",
            vehicle_id=self.vehicle_id
        )

    def _persist(self, reading: SensorReading):
        """Write reading to CSV."""
        with open(self.session_file, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["timestamp", "sensor_name", "value", "unit", "vehicle_id"])
            writer.writerow(asdict(reading))

    def _notify(self, reading: SensorReading):
        """Notify all registered callbacks."""
        for cb in self.callbacks:
            try:
                cb(reading)
            except Exception as e:
                logger.error(f"Callback error: {e}")

    def start_streaming(self, duration: Optional[float] = None):
        """
        Start streaming sensor data.

        Args:
            duration: Stream for N seconds, or None for indefinite
        """
        if not self.is_connected:
            raise RuntimeError("Not connected. Call connect() first.")

        logger.info(f"Starting data stream... (mode={self.mode})")
        start_time = time.time()

        try:
            while True:
                for sensor_name, rate in SENSOR_RATES.items():
                    if self.mode == "live":
                        reading = self._read_live(sensor_name)
                    else:
                        reading = self._read_simulated(sensor_name)

                    if reading:
                        self._persist(reading)
                        self._notify(reading)

                if duration and (time.time() - start_time) >= duration:
                    logger.info(f"Stream complete: {duration}s elapsed")
                    break

                time.sleep(0.05)

        except KeyboardInterrupt:
            logger.info("Streaming stopped by user")

    def get_latest_readings(self, n: int = 1) -> Dict[str, List[SensorReading]]:
        """Get latest N readings per sensor from current session."""
        readings = {}
        try:
            with open(self.session_file, "r") as f:
                reader = csv.DictReader(f)
                rows = list(reader)
                for sensor in SENSOR_RATES.keys():
                    sensor_rows = [r for r in rows if r["sensor_name"] == sensor]
                    readings[sensor] = [
                        SensorReading(
                            timestamp=float(r["timestamp"]),
                            sensor_name=r["sensor_name"],
                            value=float(r["value"]),
                            unit=r["unit"],
                            vehicle_id=r["vehicle_id"]
                        )
                        for r in sensor_rows[-n:]
                    ]
        except Exception as e:
            logger.error(f"Error reading session file: {e}")

        return readings


def main():
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="OBD-II Data Logger")
    parser.add_argument("--vehicle-id", required=True, help="Vehicle identifier")
    parser.add_argument("--mode", choices=["live", "simulate"], default="simulate",
                        help="Connection mode: live (real OBD) or simulate (demo)")
    parser.add_argument("--duration", type=float, default=300, help="Stream duration in seconds")
    parser.add_argument("--port", default=OBD_PORT, help="OBD serial port (use 'auto' for detection)")

    args = parser.parse_args()

    logger.info(f"Vehicle: {args.vehicle_id} | Mode: {args.mode} | Duration: {args.duration}s")

    logger_obj = OBDDataLogger(
        vehicle_id=args.vehicle_id,
        mode=args.mode,
        port=args.port
    )

    if logger_obj.connect():
        logger_obj.start_streaming(duration=args.duration)
    else:
        logger.error("Failed to connect")


if __name__ == "__main__":
    main()
