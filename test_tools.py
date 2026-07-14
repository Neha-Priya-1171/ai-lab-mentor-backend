"""
Tests the real ground-truth lookups and tool dispatcher logic, using a
fake retriever (no Cohere/Pinecone/network calls) so this runs anywhere,
same "test the architecture cheaply before spending quota" philosophy as
test_agent_loop.py.

Run: python3 test_tools.py
"""

import ground_truth as gt
from tools import dispatcher


def fake_retriever(query: str, top_k: int) -> list[str]:
    if "ams1117" in query.lower():
        return ["AMS1117 dropout voltage is 1.1V to 1.3V typical, per the AMS1117 datasheet."]
    if "brown" in query.lower() or "rtcwdt_brown_out" in query.lower():
        return ["Brownout resets usually correlate with inadequate current delivery during Wi-Fi TX bursts, per common-failures.md."]
    return []


dispatcher.set_retriever(fake_retriever)


def test_input_only_pin_lookup():
    info = gt.lookup_pin("GPIO34")
    assert info["input_only"] is True
    assert info["output_capable"] is False
    print("PASS: GPIO34 correctly identified as input-only.")


def test_source_sink_topology():
    direction, limit = gt.source_or_sink("wired between GPIO and GND")
    assert direction == "sourcing" and limit == 12, (direction, limit)
    direction, limit = gt.source_or_sink("connected to 3.3V/VCC")
    assert direction == "sinking" and limit == 20, (direction, limit)
    direction, limit = gt.source_or_sink(None)
    assert direction is None and limit is None
    print("PASS: source/sink topology resolves correctly, and refuses to guess when absent.")


def test_reset_code_parsing():
    log = "Guru Meditation Error: Core 0 panic'ed\nrst:0x0f (RTCWDT_BROWN_OUT_RESET)\n"
    matches = gt.find_reset_codes(log)
    codes = [m["code"].lower() for m in matches]
    assert "0xf" in codes, codes
    kw = gt.find_keyword_signatures(log)
    assert any(k["name"] == "Guru Meditation Error" for k in kw)
    print("PASS: reset code + keyword signature both correctly parsed from a real T7-style log line.")


def test_compatibility_tool_input_only_pin():
    result = dispatcher.check_component_compatibility("GPIO34", "relay coil", "GPIO to GND")
    assert "input-only pins cannot source/sink current at all" in result
    assert "sourcing" in result
    print("PASS: compatibility tool correctly flags input-only pin + resolves sourcing topology.")


def test_compatibility_tool_missing_topology_does_not_guess():
    result = dispatcher.check_component_compatibility("GPIO25", "buzzer", None)
    assert "do not assume source vs. sink" in result
    print("PASS: compatibility tool refuses to guess topology when not given (matches Asking-vs-Concluding rule).")


def test_compatibility_tool_rag_for_non_esp32_side():
    result = dispatcher.check_component_compatibility("AMS1117 LDO", "Li-ion battery", None)
    assert "dropout voltage is 1.1V to 1.3V" in result
    print("PASS: compatibility tool retrieves real datasheet context for the non-ESP32 side.")


def test_error_log_tool_brownout():
    result = dispatcher.analyze_error_log("rst:0x0f (RTCWDT_BROWN_OUT_RESET)")
    assert "Brownout reset" in result
    assert "inadequate current delivery" in result
    print("PASS: error log tool matches brownout code and pulls common-failures.md-style context.")


def test_error_log_tool_no_match():
    result = dispatcher.analyze_error_log("everything is fine, no errors here")
    assert "No recognized reset-code" in result
    print("PASS: error log tool says so explicitly instead of inventing a cause, when nothing matches.")


def test_report_tool_finds_terms():
    transcript = "User: ESP32 with SSD1306 OLED, blank screen. rst:0x0f brownout..."
    result = dispatcher.generate_diagnostic_report(transcript)
    assert "ESP32" in result and "SSD1306" in result
    print("PASS: report tool detects relevant component terms in transcript for supplementary retrieval.")


if __name__ == "__main__":
    test_input_only_pin_lookup()
    test_source_sink_topology()
    test_reset_code_parsing()
    test_compatibility_tool_input_only_pin()
    test_compatibility_tool_missing_topology_does_not_guess()
    test_compatibility_tool_rag_for_non_esp32_side()
    test_error_log_tool_brownout()
    test_error_log_tool_no_match()
    test_report_tool_finds_terms()
    print("\nAll ground-truth + dispatcher tests passed.")
