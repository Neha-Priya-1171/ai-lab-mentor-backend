"""
Structural tests for tools/multimeter_reference.py. Pure functions, no
ground_truth.py dependency, no retriever, no network -- run before any
live Groq/Gemini test, same convention as test_power_budget.py.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tools.multimeter_reference import (
    MEASUREMENT_TYPES,
    get_measurement_setup,
    interpret_digital_logic_reading,
    interpret_continuity_reading,
)


def test_all_four_measurement_types_present():
    assert set(MEASUREMENT_TYPES.keys()) == {"voltage_dc", "resistance", "continuity", "current_dc"}


def test_get_measurement_setup_returns_expected_fields():
    setup = get_measurement_setup("voltage_dc")
    assert setup is not None
    assert "meter_setting" in setup
    assert "probe_placement" in setup
    assert "safety_note" in setup


def test_get_measurement_setup_unknown_type_returns_none():
    assert get_measurement_setup("frequency") is None


def test_current_measurement_flags_series_placement():
    """The single most common real-world multimeter mistake (parallel vs
    series for current) needs to be unambiguous in the guidance text."""
    setup = get_measurement_setup("current_dc")
    assert "SERIES" in setup["probe_placement"]


def test_resistance_and_continuity_require_power_off():
    for t in ("resistance", "continuity"):
        setup = get_measurement_setup(t)
        assert "POWERED OFF" in setup["safety_note"]


def test_logic_reading_high():
    out = interpret_digital_logic_reading(3.28, "V", vcc=3.3)
    assert "HIGH" in out
    assert "LOW" not in out.split("rule of thumb")[0]  # HIGH classification itself, not just mentioned in caveat text


def test_logic_reading_low():
    out = interpret_digital_logic_reading(0.05, "V", vcc=3.3)
    assert out.startswith("0.05V") and "-> reads as LOW" in out


def test_logic_reading_indeterminate():
    out = interpret_digital_logic_reading(1.6, "V", vcc=3.3)
    assert "INDETERMINATE" in out


def test_logic_reading_always_labels_as_rule_of_thumb():
    """Never let this read as a verified datasheet spec -- it's a generic
    convention, and the text must say so every time."""
    out = interpret_digital_logic_reading(3.3, "V")
    assert "rule of thumb" in out
    assert "NOT this specific chip's real VIH/VIL" in out


def test_logic_reading_wrong_unit_skips_gracefully():
    out = interpret_digital_logic_reading(50, "ohm")
    assert "skipping logic-level interpretation" in out


def test_continuity_beep_true():
    out = interpret_continuity_reading(None, meter_beeped=True)
    assert "closed circuit" in out


def test_continuity_beep_false():
    out = interpret_continuity_reading(None, meter_beeped=False)
    assert "open circuit" in out


def test_continuity_low_ohms_reads_as_continuous():
    out = interpret_continuity_reading(5.0)
    assert "continuous/closed circuit" in out


def test_continuity_high_ohms_reads_as_open():
    out = interpret_continuity_reading(50_000.0)
    assert "open circuit" in out


def test_continuity_no_data_at_all():
    out = interpret_continuity_reading(None)
    assert "cannot interpret" in out
