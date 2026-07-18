"""
Structural tests for grounding_guard.py -- no network, no API quota.
Run: python -m pytest test_grounding_guard.py -v
"""

from grounding_guard import strip_unverified_locators, build_grounded_text


def test_strips_fabricated_version_not_in_grounded_text():
    reply = "Source: ESP32 Series Datasheet v5.2 (for operating voltage)."
    grounded = "No relevant chunks retrieved this turn."
    out = strip_unverified_locators(reply, grounded)
    assert "v5.2" not in out
    assert "ESP32 Series Datasheet" in out  # name itself untouched


def test_strips_fabricated_section_not_in_grounded_text():
    reply = "Per the SSD1306 Datasheet Section 8, pull-ups are required."
    grounded = "some unrelated retrieved chunk about I2C addressing"
    out = strip_unverified_locators(reply, grounded)
    assert "Section 8" not in out
    assert "SSD1306 Datasheet" in out


def test_leaves_locator_that_is_genuinely_grounded():
    reply = "Per the SSD1306 Datasheet Rev 1.1, the reset pin is active-low."
    grounded = "Retrieved chunk: '...see SSD1306 Datasheet Rev 1.1, section on reset behavior...'"
    out = strip_unverified_locators(reply, grounded)
    assert "Rev 1.1" in out  # genuinely present in grounded_text -> keep


def test_leaves_bare_document_reference_untouched():
    reply = "As general knowledge, per the ESP32 datasheet, GPIOs are 3.3V logic."
    grounded = "no retrieval this turn"
    out = strip_unverified_locators(reply, grounded)
    assert out == reply  # no locator attached at all -> nothing to strip


def test_case_insensitive_match_against_grounded_text():
    reply = "Per the AMS1117 Datasheet REV. 2, dropout is 1.2V."
    grounded = "retrieved: AMS1117 datasheet rev. 2 dropout specifications"
    out = strip_unverified_locators(reply, grounded)
    assert "REV. 2" in out


def test_multiple_locators_in_one_reply_handled_independently():
    reply = (
        "Per the ESP32 Series Datasheet v5.2 for current limits, and the "
        "SSD1306 Datasheet Rev 1.1 for reset timing."
    )
    grounded = "retrieved chunk mentions SSD1306 Datasheet Rev 1.1 explicitly"
    out = strip_unverified_locators(reply, grounded)
    assert "v5.2" not in out
    assert "Rev 1.1" in out


def test_empty_reply_is_safe():
    assert strip_unverified_locators("", "anything") == ""
    assert strip_unverified_locators(None, "anything") is None


def test_build_grounded_text_concatenates_tool_messages_and_system_prompt():
    full_messages = [
        {"role": "system", "content": "should not appear via this path"},
        {"role": "user", "content": "user text"},
        {"role": "tool", "name": "check_component_compatibility", "content": "Retrieved: SRD-05VDC Datasheet Rev 2"},
        {"role": "assistant", "content": "reply text"},
    ]
    grounded = build_grounded_text(full_messages, system_prompt="Context: some retrieved chunk here")
    assert "SRD-05VDC Datasheet Rev 2" in grounded
    assert "some retrieved chunk here" in grounded
    assert "user text" not in grounded  # only tool content + system_prompt, not the whole convo
