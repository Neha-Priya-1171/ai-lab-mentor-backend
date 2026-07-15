import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from tools.symptom_map import SYMPTOM_CATEGORIES, list_categories, get_category, format_category_info


def test_all_five_categories_present():
    assert set(SYMPTOM_CATEGORIES.keys()) == {
        "i2c_communication", "power_brownout", "firmware_crash",
        "output_driver_mismatch", "sensor_erratic",
    }


def test_every_category_has_required_fields():
    for key, info in SYMPTOM_CATEGORIES.items():
        assert "label" in info
        assert "example_symptoms" in info and len(info["example_symptoms"]) > 0
        assert "known_signature" in info  # may be None, but key must exist


def test_list_categories_includes_all_labels():
    out = list_categories()
    for info in SYMPTOM_CATEGORIES.values():
        assert info["label"] in out


def test_get_category_by_exact_key():
    info = get_category("i2c_communication")
    assert info is not None
    assert info["label"] == "I2C Communication Issues"


def test_get_category_case_and_space_tolerant():
    info = get_category("Power Brownout")
    assert info is not None
    assert info["label"] == "Power / Brownout Resets"


def test_get_category_loose_label_match():
    info = get_category("firmware crash")
    assert info is not None
    assert info["label"] == "Firmware Crash / Panic"


def test_get_category_unknown_returns_none():
    assert get_category("bluetooth pairing failure") is None


def test_get_category_empty_returns_none():
    assert get_category("") is None
    assert get_category(None) is None


def test_format_category_info_with_known_signature():
    info = get_category("i2c_communication")
    out = format_category_info(info)
    assert "Documented signature" in out
    assert "pull-up" in out.lower()


def test_format_category_info_without_known_signature():
    info = get_category("sensor_erratic")
    out = format_category_info(info)
    assert "No documented signature" in out


def test_format_category_info_includes_related_tool_when_present():
    info = get_category("output_driver_mismatch")
    out = format_category_info(info)
    assert "check_component_compatibility" in out


def test_format_category_info_omits_related_tool_when_absent():
    info = get_category("sensor_erratic")
    out = format_category_info(info)
    assert "Related tool" not in out
