"""
Structural tests for ground_truth.py's reset-code lookup.
No network, no API quota.

Covers a real bug found during Phase 8 cleanup: _normalize_hex_code()
lowercased hex letters, but RESET_REASON_CODES uses uppercase keys
(0xA-0xF). Every code from 0xA to 0xF -- including 0xF, the brownout
reset (the single most commonly cited fault in this project's own phase
logs) -- silently failed to match and fell through to "not in the known
reference table," even though the code was genuinely recognized.
"""

import ground_truth as gt


def test_all_hex_letter_codes_normalize_and_match_the_table():
    # Before the fix, only 0x1-0x9 worked; 0xA-0xF (6 of 16 codes) were
    # silently broken. Covering every single-hex-digit code here so this
    # can't regress on a subset again.
    for raw in ["0x1", "0x3", "0x4", "0x5", "0x6", "0x7", "0x8", "0x9",
                "0xa", "0xA", "0xb", "0xB", "0xc", "0xC", "0xd", "0xD",
                "0xe", "0xE", "0xf", "0xF"]:
        normalized = gt._normalize_hex_code(raw)
        assert normalized in gt.RESET_REASON_CODES, f"{raw} -> {normalized} not found in table"


def test_zero_padded_variant_normalizes_same_as_bare():
    assert gt._normalize_hex_code("0x0f") == gt._normalize_hex_code("0xF")
    assert gt._normalize_hex_code("0x0a") == gt._normalize_hex_code("0xA")


def test_brownout_reset_is_correctly_identified_from_a_real_serial_log_line():
    # This exact log line is used across multiple phase logs
    # (PHASE4_LOG.md's T7 retest, PHASE6_LOG.md's live testing) as the
    # canonical brownout scenario -- it must resolve correctly.
    matches = gt.find_reset_codes("rst:0x0f (RTCWDT_BROWN_OUT_RESET)")
    assert len(matches) == 1
    assert matches[0]["name"] == "RTCWDT_BROWN_OUT_RESET"
    assert matches[0]["is_fault"] is True
    assert "brownout" in matches[0]["meaning"].lower()


def test_0x10_is_not_confused_with_0x1(): 
    # A regression guard for a different possible failure mode: 0x10 must
    # resolve to RTCWDT_RTC_RESET, not accidentally collapse to "0x1"
    # (POWERON_RESET) through overly aggressive digit stripping.
    normalized = gt._normalize_hex_code("0x10")
    assert normalized == "0x10"
    assert gt.RESET_REASON_CODES[normalized]["name"] == "RTCWDT_RTC_RESET"


def test_unrecognized_code_still_reported_not_silently_dropped():
    matches = gt.find_reset_codes("rst:0x99 (SOME_UNKNOWN_CODE)")
    assert len(matches) == 1
    assert matches[0]["is_fault"] is None
    assert "not in the known reference table" in matches[0]["meaning"].lower()
