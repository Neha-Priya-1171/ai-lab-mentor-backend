"""
Multimeter Assistant reference data (Phase 7).

Design note: split the same way Phase 4/6 already split board-profile facts
from datasheet-specific facts (see dispatcher.py's docstring). This module
holds ONLY universal multimeter-usage facts and basic digital-logic
threshold conventions -- true regardless of which board or component is
being measured, so safe to hardcode and unit-test without any dependency
on ground_truth.py or the RAG retriever.

What does NOT live here: anything component/datasheet-specific (e.g. "this
relay's coil should read 70-90 ohms"). That requires a real, verified
number from an actual datasheet -- per the project's own Hard Rule against
inventing unsourced numbers, those come from dispatcher.py's existing
_retrieve() call against the real Cohere/Pinecone corpus, exactly like
check_component_compatibility already does for component-side specs.
"""

from __future__ import annotations

MEASUREMENT_TYPES: dict[str, dict[str, str]] = {
    "voltage_dc": {
        "label": "DC Voltage",
        "meter_setting": "DCV (V with a straight/dashed line), auto-range or 20V range if manual",
        "probe_placement": "Red probe on the point being measured, black probe on a common ground/GND reference. Meter must be in parallel with the circuit (across the two points), never in series.",
        "safety_note": "Confirm the circuit is powered as expected before measuring -- an unexpected 0V reading on a supposedly-live rail is itself diagnostic information, not a meter error.",
    },
    "resistance": {
        "label": "Resistance",
        "meter_setting": "\u03a9 (ohms), auto-range or select a range above the expected value",
        "probe_placement": "Probes across the two points of the component/path being measured, in either polarity (resistance measurement is non-directional). Meter must be in parallel with the component, same as voltage.",
        "safety_note": "CIRCUIT MUST BE POWERED OFF and, for components still wired to a larger circuit, ideally isolated (one leg desoldered/disconnected) -- other parallel paths in a live circuit will skew a resistance reading, and measuring resistance on a powered circuit can damage the meter or give a meaningless result.",
    },
    "continuity": {
        "label": "Continuity",
        "meter_setting": "Continuity mode (diode/speaker symbol, often shared with the ohms dial position)",
        "probe_placement": "Probes on the two ends of the path being tested (e.g. both ends of a wire, or a trace between two pads).",
        "safety_note": "CIRCUIT MUST BE POWERED OFF, same reason as resistance measurement -- continuity mode is a specialized low-resistance reading.",
    },
    "current_dc": {
        "label": "DC Current",
        "meter_setting": "DCA (A with a straight/dashed line) -- start on the highest current range available (often a separate 10A/unfused jack) and step down, since an underestimated current can blow the meter's internal fuse",
        "probe_placement": "Meter must be placed IN SERIES with the circuit -- break the circuit path and insert the meter inline, never in parallel. This is the opposite placement from voltage/resistance.",
        "safety_note": "Highest-risk measurement type for both the meter (fuse) and the circuit (briefly opening a live path). Confirm probe placement in the correct current jack on the meter itself before connecting -- the most common multimeter mistake is leaving probes in the current jack and then measuring voltage, which shorts the circuit through the meter's fuse.",
    },
}


def get_measurement_setup(measurement_type: str) -> dict[str, str] | None:
    """Returns None if measurement_type isn't recognized -- caller should
    list valid options rather than guess which one was meant."""
    return MEASUREMENT_TYPES.get(measurement_type)


def interpret_digital_logic_reading(measured_value: float, unit: str, vcc: float = 3.3) -> str:
    """
    Basic CMOS/TTL-style logic-level interpretation using a simple
    midpoint-of-VCC rule of thumb (not a specific chip's real VIH/VIL
    spec, which varies by part and would need a real datasheet number).
    Explicitly labeled as a rule of thumb in the returned text so the
    model doesn't present it as a verified threshold.
    """
    if unit.lower() not in ("v", "volt", "volts", "dcv"):
        return f"(interpret_digital_logic_reading expects a voltage unit, got '{unit}' -- skipping logic-level interpretation)"

    high_threshold = 0.7 * vcc
    low_threshold = 0.3 * vcc

    if measured_value >= high_threshold:
        state = "HIGH"
    elif measured_value <= low_threshold:
        state = "LOW"
    else:
        state = "INDETERMINATE (floating, partial drive, or a bus in an intermediate state)"

    return (
        f"{measured_value}V against a {vcc}V logic rail -> reads as {state} "
        f"(rule of thumb: >={high_threshold:.2f}V is HIGH, <={low_threshold:.2f}V is LOW, "
        f"this is a general 70%/30%-of-VCC convention, NOT this specific chip's real VIH/VIL "
        f"datasheet spec -- flag accordingly if the exact threshold matters for this diagnosis)"
    )


def interpret_continuity_reading(measured_ohms: float | None, meter_beeped: bool | None = None) -> str:
    """
    Standard continuity convention: most multimeters beep somewhere under
    ~20-50 ohms depending on the model. If the user reports a beep, trust
    that directly (it's the meter's own built-in threshold, not ours).
    If only a numeric ohms reading is given, apply a conservative rule of
    thumb and flag it as such.
    """
    if meter_beeped is not None:
        return (
            "Meter beeped -> closed circuit / continuity present (very low resistance path)."
            if meter_beeped
            else "Meter did not beep -> open circuit / no continuity (or resistance above the meter's own beep threshold)."
        )

    if measured_ohms is None:
        return "No ohms reading or beep result given -- cannot interpret continuity."

    if measured_ohms < 20:
        return (
            f"{measured_ohms} ohms -> reads as continuous/closed circuit "
            f"(rule of thumb: most meters beep under ~20-50 ohms; exact threshold varies by meter model)."
        )
    return (
        f"{measured_ohms} ohms -> reads as open circuit / no continuity "
        f"(above the typical ~20-50 ohm continuity-beep threshold; if this is meant to be a "
        f"direct short or solid connection, this reading suggests it isn't one)."
    )
