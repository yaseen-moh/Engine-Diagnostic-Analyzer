"""
Failure Mode Library
Maps multi-sensor signatures to real-world failures based on mechanic experience.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from enum import Enum
import json


class Severity(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class Trend(Enum):
    RISING = "rising"
    FALLING = "falling"
    JITTER = "jitter"
    STABLE = "stable"
    OSCILLATING = "oscillating"


@dataclass
class SensorPattern:
    """Pattern definition for a single sensor."""
    sensor: str
    trend: Trend
    threshold: Optional[float] = None
    rate_of_change: Optional[float] = None
    variance_threshold: Optional[float] = None


@dataclass
class FailureMode:
    """Complete failure mode definition."""
    id: str
    name: str
    description: str
    signatures: List[List[SensorPattern]]
    confidence_weights: Dict[str, float]
    severity: Severity
    typical_repair: str
    early_warning_seconds: int
    related_dtcs: List[str] = field(default_factory=list)
    notes: str = ""

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "severity": self.severity.value,
            "typical_repair": self.typical_repair,
            "early_warning_seconds": self.early_warning_seconds,
            "related_dtcs": self.related_dtcs,
            "notes": self.notes,
        }


FAILURE_MODES: List[FailureMode] = [

    FailureMode(
        id="WATER_PUMP_BEARING",
        name="Water Pump Bearing Failure",
        description=(
            "Bearing in water pump is degrading, causing increased mechanical drag "
            "and reduced coolant circulation. Classic signature: coolant temp rising "
            "while voltage drops and idle RPM becomes unstable."
        ),
        signatures=[
            [
                SensorPattern("COOLANT_TEMP", Trend.RISING, rate_of_change=0.03),
                SensorPattern("CONTROL_MODULE_VOLTAGE", Trend.FALLING, rate_of_change=-0.002),
                SensorPattern("RPM", Trend.JITTER, variance_threshold=50.0),
            ],
            [
                SensorPattern("COOLANT_TEMP", Trend.RISING, threshold=105.0),
                SensorPattern("CONTROL_MODULE_VOLTAGE", Trend.FALLING, threshold=13.5),
            ]
        ],
        confidence_weights={
            "COOLANT_TEMP": 0.35,
            "CONTROL_MODULE_VOLTAGE": 0.30,
            "RPM": 0.20,
            "ENGINE_LOAD": 0.15,
        },
        severity=Severity.HIGH,
        typical_repair="Replace water pump assembly. Check drive belt tension. Inspect coolant for bearing debris.",
        early_warning_seconds=300,
        related_dtcs=["P0118", "P0480", "P0217"],
        notes="Ground strap problem origin: voltage drop masked coolant temp rise. Multi-sensor correlation essential.",
    ),

    FailureMode(
        id="CAT_DEGRADATION",
        name="Catalytic Converter Efficiency Loss",
        description=(
            "Catalyst efficiency below threshold. O2 sensors upstream and downstream "
            "begin to mirror each other instead of showing the expected lag."
        ),
        signatures=[
            [
                SensorPattern("O2_B1S1", Trend.OSCILLATING),
                SensorPattern("O2_B1S2", Trend.OSCILLATING),
                SensorPattern("SHORT_FUEL_TRIM_1", Trend.RISING, threshold=8.0),
                SensorPattern("LONG_FUEL_TRIM_1", Trend.RISING, threshold=5.0),
            ]
        ],
        confidence_weights={
            "O2_B1S1": 0.25,
            "O2_B1S2": 0.25,
            "SHORT_FUEL_TRIM_1": 0.25,
            "LONG_FUEL_TRIM_1": 0.25,
        },
        severity=Severity.MEDIUM,
        typical_repair="Replace catalytic converter. Check for upstream misfires that poisoned catalyst.",
        early_warning_seconds=1800,
        related_dtcs=["P0420", "P0430", "P2096"],
        notes="O2 sensors oscillating in phase = dead cat. Should be 180° out of phase when healthy.",
    ),

    FailureMode(
        id="INTAKE_LEAK",
        name="Intake Manifold Vacuum Leak",
        description=(
            "Unmetered air entering intake after MAF sensor. MAP pressure oscillates "
            "at idle, fuel trims go lean, and random misfires appear."
        ),
        signatures=[
            [
                SensorPattern("MAP", Trend.OSCILLATING, variance_threshold=3.0),
                SensorPattern("SHORT_FUEL_TRIM_1", Trend.RISING, threshold=5.0),
                SensorPattern("RPM", Trend.JITTER, variance_threshold=30.0),
                SensorPattern("THROTTLE_POS", Trend.STABLE),
            ]
        ],
        confidence_weights={
            "MAP": 0.30,
            "SHORT_FUEL_TRIM_1": 0.30,
            "RPM": 0.20,
            "MAF": 0.20,
        },
        severity=Severity.MEDIUM,
        typical_repair="Smoke test intake system. Replace intake manifold gasket. Inspect all vacuum hoses and PCV valve.",
        early_warning_seconds=600,
        related_dtcs=["P0171", "P0174", "P0300"],
        notes="Smoke test is definitive, but MAP oscillation + lean trim at idle is strong predictor.",
    ),

    FailureMode(
        id="THROTTLE_CARBON",
        name="Throttle Body Carbon Deposits",
        description=(
            "Carbon buildup on throttle plate restricts airflow at small openings. "
            "Throttle position sensor shows micro-jumps, idle RPM hunts."
        ),
        signatures=[
            [
                SensorPattern("THROTTLE_POS", Trend.JITTER, variance_threshold=0.5),
                SensorPattern("RPM", Trend.OSCILLATING),
                SensorPattern("ENGINE_LOAD", Trend.JITTER, variance_threshold=5.0),
            ]
        ],
        confidence_weights={
            "THROTTLE_POS": 0.40,
            "RPM": 0.30,
            "ENGINE_LOAD": 0.30,
        },
        severity=Severity.LOW,
        typical_repair="Remove throttle body. Clean with throttle body cleaner. Relearn idle position via scan tool.",
        early_warning_seconds=1200,
        related_dtcs=["P0507", "P2111"],
        notes="Very common on direct-injection engines. Idle hunt is the giveaway.",
    ),

    FailureMode(
        id="ALTERNATOR_DEGRADING",
        name="Alternator Output Degradation",
        description=(
            "Alternator diodes or brushes wearing. Voltage slowly drops under electrical "
            "load. Battery may test good but vehicle shows symptoms of weak charging."
        ),
        signatures=[
            [
                SensorPattern("CONTROL_MODULE_VOLTAGE", Trend.FALLING, rate_of_change=-0.005),
                SensorPattern("RPM", Trend.STABLE),
                SensorPattern("ENGINE_LOAD", Trend.RISING),
            ]
        ],
        confidence_weights={
            "CONTROL_MODULE_VOLTAGE": 0.60,
            "ENGINE_LOAD": 0.25,
            "RPM": 0.15,
        },
        severity=Severity.HIGH,
        typical_repair="Test alternator output under load. Replace alternator if output < 13.5V at idle with load.",
        early_warning_seconds=900,
        related_dtcs=["P0562", "P0621"],
        notes="Voltage alone is not enough — must correlate with stable RPM to rule out idle control issue.",
    ),

    FailureMode(
        id="COIL_PACK_INTERMITTENT",
        name="Ignition Coil Pack Intermittent Failure",
        description=(
            "Coil pack producing weak spark under heat/load. Causes intermittent misfires. "
            "RPM shows micro-drop events, O2 sensor spikes rich from unburned fuel."
        ),
        signatures=[
            [
                SensorPattern("RPM", Trend.JITTER, variance_threshold=40.0),
                SensorPattern("O2_B1S1", Trend.RISING, rate_of_change=0.1),
                SensorPattern("TIMING_ADVANCE", Trend.FALLING),
                SensorPattern("ENGINE_LOAD", Trend.RISING),
            ]
        ],
        confidence_weights={
            "RPM": 0.30,
            "O2_B1S1": 0.25,
            "TIMING_ADVANCE": 0.25,
            "ENGINE_LOAD": 0.20,
        },
        severity=Severity.HIGH,
        typical_repair="Replace coil pack(s). Inspect spark plugs for carbon tracking. Test coil resistance when hot.",
        early_warning_seconds=300,
        related_dtcs=["P0300", "P0301", "P0302", "P0303", "P0304"],
        notes="Heat-soak testing is key — may pass cold, fail hot. Look for RPM drop + rich O2 + timing retard triad.",
    ),

    FailureMode(
        id="HEAD_GASKET_EARLY",
        name="Head Gasket Early Stage Failure",
        description=(
            "Combustion gases beginning to leak into coolant passages. Coolant temp "
            "shows sawtooth pattern (spike then drop). White smoke from exhaust possible."
        ),
        signatures=[
            [
                SensorPattern("COOLANT_TEMP", Trend.OSCILLATING, variance_threshold=5.0),
                SensorPattern("O2_B1S1", Trend.FALLING),
                SensorPattern("MAP", Trend.OSCILLATING),
            ]
        ],
        confidence_weights={
            "COOLANT_TEMP": 0.40,
            "O2_B1S1": 0.30,
            "MAP": 0.20,
            "CONTROL_MODULE_VOLTAGE": 0.10,
        },
        severity=Severity.CRITICAL,
        typical_repair="Block test to confirm. Replace head gasket. Check head for warpage. Inspect for coolant in oil.",
        early_warning_seconds=600,
        related_dtcs=["P0118", "P0171", "P0300"],
        notes="Sawtooth coolant temp is the hallmark. Don't trust single spike — look for repeating pattern.",
    ),
]


def get_failure_mode(failure_id: str) -> Optional[FailureMode]:
    for fm in FAILURE_MODES:
        if fm.id == failure_id:
            return fm
    return None


def get_all_failure_modes() -> List[FailureMode]:
    return FAILURE_MODES.copy()


def get_failure_modes_by_severity(severity: Severity) -> List[FailureMode]:
    return [fm for fm in FAILURE_MODES if fm.severity == severity]


def export_to_json(path: str):
    data = [fm.to_dict() for fm in FAILURE_MODES]
    with open(path, "w") as f:
        json.dump(data, f, indent=2)
    return path


if __name__ != "__main__":
    try:
        from config import DATA_DIR
        export_to_json(str(DATA_DIR / "failure_library.json"))
    except ImportError:
        pass
