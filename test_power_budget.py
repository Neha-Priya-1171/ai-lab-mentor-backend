"""
Structural tests for calculate_power_budget. Pure arithmetic, no network,
no API keys needed -- run these before ever calling this tool through a
real Groq/Gemini session, per the project's standing "test before spending
real API quota" convention (CLAUDE_CODE_PREREQUISITES.md).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import pytest
from tools.power_budget import calculate_power_budget, format_power_budget_result, DERATING_FACTOR


def test_simple_current_ma_sum():
    """ESP32 (~160mA active WiFi TX) + SSD1306 OLED (~20mA) on USB 500mA."""
    result = calculate_power_budget(
        supply_voltage_v=5.0,
        supply_current_limit_ma=500,
        components=[
            {"name": "ESP32 DevKit", "current_ma": 160},
            {"name": "SSD1306 OLED", "current_ma": 20},
        ],
    )
    assert result["total_steady_current_ma"] == 180
    assert result["exceeds_rated_limit_steady"] is False
    assert result["exceeds_derated_continuous_budget"] is False
    assert result["margin_vs_rated_limit_steady_ma"] == 320


def test_ohms_law_derivation():
    """A pure resistive load specified only by resistance."""
    result = calculate_power_budget(
        supply_voltage_v=5.0,
        supply_current_limit_ma=1000,
        components=[{"name": "Pull-up resistor pair", "resistance_ohms": 10_000}],
    )
    # I = V/R = 5/10000 = 0.5 mA
    comp = result["components"][0]
    assert comp["derivation"] == "ohms_law (V / R)"
    assert comp["unit_current_ma"] == pytest.approx(0.5)


def test_quantity_multiplies_correctly():
    result = calculate_power_budget(
        supply_voltage_v=5.0,
        supply_current_limit_ma=2000,
        components=[{"name": "WS2812 LED", "current_ma": 60, "quantity": 30}],
    )
    comp = result["components"][0]
    assert comp["total_current_ma"] == 1800
    assert result["total_steady_current_ma"] == 1800


def test_exceeds_derated_budget_but_not_rated_limit():
    """The core reason this tool exists: a load can sit under the rated
    max while still exceeding the 80% continuous-derating convention --
    the model shouldn't have to know that distinction exists, the tool
    should just surface it as a fact."""
    result = calculate_power_budget(
        supply_voltage_v=5.0,
        supply_current_limit_ma=500,  # derated budget = 400mA
        components=[{"name": "Servo bank", "current_ma": 420}],
    )
    assert result["exceeds_rated_limit_steady"] is False
    assert result["exceeds_derated_continuous_budget"] is True
    assert result["derated_continuous_budget_ma"] == 400


def test_peak_vs_steady_separated_for_servo():
    """Servo stall current spikes far above steady-state draw -- this is
    the scenario the peak_current_ma field exists for."""
    result = calculate_power_budget(
        supply_voltage_v=5.0,
        supply_current_limit_ma=2000,
        components=[
            {
                "name": "SG90 servo",
                "current_ma": 100,      # steady, moving
                "peak_current_ma": 650,  # stall current
                "quantity": 3,
            }
        ],
    )
    assert result["total_steady_current_ma"] == 300
    assert result["total_peak_current_ma"] == 1950
    assert result["exceeds_rated_limit_steady"] is False
    assert result["exceeds_rated_limit_peak"] is False


def test_clearly_exceeds_supply():
    result = calculate_power_budget(
        supply_voltage_v=5.0,
        supply_current_limit_ma=500,
        components=[{"name": "3x NEMA17 stepper", "current_ma": 800, "quantity": 3}],
    )
    assert result["exceeds_rated_limit_steady"] is True
    assert result["margin_vs_rated_limit_steady_ma"] < 0


def test_missing_data_is_flagged_not_guessed():
    """A component with neither current_ma nor resistance_ohms must be
    reported as missing data, never silently assigned a made-up current."""
    result = calculate_power_budget(
        supply_voltage_v=5.0,
        supply_current_limit_ma=500,
        components=[
            {"name": "ESP32 DevKit", "current_ma": 160},
            {"name": "Mystery sensor"},  # no current_ma, no resistance_ohms
        ],
    )
    assert len(result["components"]) == 1  # only the known one got computed
    assert result["total_steady_current_ma"] == 160
    assert len(result["missing_data"]) == 1
    assert "Mystery sensor" in result["missing_data"][0]


def test_invalid_supply_voltage_raises():
    with pytest.raises(ValueError):
        calculate_power_budget(
            supply_voltage_v=0,
            supply_current_limit_ma=500,
            components=[{"name": "x", "current_ma": 10}],
        )


def test_invalid_supply_current_raises():
    with pytest.raises(ValueError):
        calculate_power_budget(
            supply_voltage_v=5.0,
            supply_current_limit_ma=-100,
            components=[{"name": "x", "current_ma": 10}],
        )


def test_derating_factor_is_the_documented_80_percent():
    # Locks in the 0.8 convention referenced in the tool's docstring/schema
    # description -- if this ever changes, it should be a deliberate edit,
    # not a silent regression.
    assert DERATING_FACTOR == 0.8


# ---------------------------------------------------------------------------
# format_power_budget_result -- this is what dispatcher.py actually calls
# (fn(**arguments) -> str, same contract as check_component_compatibility /
# analyze_error_log / generate_diagnostic_report). Test the real integration
# point, not just the pure-math function above.
# ---------------------------------------------------------------------------

def test_formatted_output_is_a_string_not_a_dict():
    out = format_power_budget_result(5.0, 500, [{"name": "ESP32", "current_ma": 160}])
    assert isinstance(out, str)


def test_formatted_output_flags_peak_overload():
    out = format_power_budget_result(
        5.0, 500,
        [{"name": "SG90 servo", "current_ma": 100, "peak_current_ma": 650}],
    )
    assert "EXCEEDS RATED SUPPLY LIMIT (peak" in out


def test_formatted_output_includes_missing_data_warning():
    out = format_power_budget_result(
        5.0, 500,
        [{"name": "ESP32", "current_ma": 160}, {"name": "Mystery sensor"}],
    )
    assert "Missing data" in out
    assert "Mystery sensor" in out
    assert "do not guess" in out


def test_formatted_output_no_flags_when_within_budget():
    out = format_power_budget_result(
        5.0, 2000,
        [{"name": "ESP32", "current_ma": 160}, {"name": "OLED", "current_ma": 20}],
    )
    assert "No flags" in out


def test_formatted_output_invalid_input_returns_error_string_not_raise():
    """dispatcher.dispatch() only catches TypeError from bad arguments --
    a ValueError from bad *values* (e.g. voltage=0) must be handled inside
    the formatter and returned as a string, not raised, or it would crash
    the agent loop instead of surfacing as a readable tool result."""
    out = format_power_budget_result(0, 500, [{"name": "x", "current_ma": 10}])
    assert isinstance(out, str)
    assert out.startswith("ERROR:")
