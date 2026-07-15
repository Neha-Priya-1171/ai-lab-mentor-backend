"""
Symptom -> Root Cause Mapping reference data (Phase 7).

Per V2_ROADMAP.md: "a browsable, queryable version of the existing
common-failures.md knowledge base; mostly a new tool wrapping content that
already exists." The actual failure-pattern prose lives in common-failures.md,
already indexed in your shared Pinecone corpus since Phase 3 -- this module
does NOT duplicate that content. It only holds a small browsable category
index so a user (or the model) can navigate by symptom type before/instead
of needing an exact query, with retrieval filling in the documented detail.

Every category and "known_signature" line below is taken directly from
signatures already established and tested in this project's own phase logs
(error-signatures-plaintext.txt, common-failures.md's brownout/Wi-Fi
correlation finding from Phase 4, the source/sink topology rule from Phase 4,
the I2C pull-up root cause validated across Phases 1-4) -- nothing here is
invented. If your actual common-failures.md covers additional categories,
extend SYMPTOM_CATEGORIES to match; this is meant to be a thin index over
real content, not a fixed taxonomy.
"""

from __future__ import annotations

SYMPTOM_CATEGORIES: dict[str, dict[str, object]] = {
    "i2c_communication": {
        "label": "I2C Communication Issues",
        "example_symptoms": [
            "OLED/display blank or garbled",
            "I2C device not detected / no ACK",
            "intermittent I2C errors",
        ],
        "known_signature": (
            "Missing or insufficient I2C pull-up resistors on SDA/SCL is the "
            "documented root cause for this project's flagship blank-OLED "
            "scenario (T7) -- validated against the real SSD1306 datasheet."
        ),
        "related_tool": "guide_multimeter_measurement (check SDA/SCL idle voltage) or check_component_compatibility",
    },
    "power_brownout": {
        "label": "Power / Brownout Resets",
        "example_symptoms": [
            "random/unexplained resets",
            "resets correlated with Wi-Fi activity (connect, TX burst)",
            "resets under load or when adding a new peripheral",
        ],
        "known_signature": (
            "rst:0x0f (RTCWDT_BROWN_OUT_RESET) documented root cause: inadequate "
            "current delivery, not voltage regulation -- correlates with Wi-Fi TX "
            "current spikes per common-failures.md's own reasoning (Phase 4/6)."
        ),
        "related_tool": "analyze_error_log (paste the actual rst:0x line) or calculate_power_budget",
    },
    "firmware_crash": {
        "label": "Firmware Crash / Panic",
        "example_symptoms": [
            "Guru Meditation Error",
            "LoadProhibited / StoreProhibited exception",
            "stack canary watchpoint triggered",
        ],
        "known_signature": (
            "Structured reset-reason and exception-keyword matching already "
            "exists -- this category should usually route to analyze_error_log "
            "directly if the user has the actual log/serial text."
        ),
        "related_tool": "analyze_error_log",
    },
    "output_driver_mismatch": {
        "label": "GPIO / Output Driver Mismatch",
        "example_symptoms": [
            "relay/buzzer doesn't trigger",
            "output pin can't seem to drive the load",
            "component works intermittently or not at all when wired to a GPIO",
        ],
        "known_signature": (
            "Documented, safety-relevant bug from Phase 4: source-vs-sink current "
            "limit confusion (GPIO-to-GND = sourcing/12mA, GPIO-to-VCC = "
            "sinking/20mA) produced a false 'Compatible' verdict on an unsafe "
            "connection before the board-profile fix. Also check for an "
            "input-only pin (GPIO34-39) wired where output was needed."
        ),
        "related_tool": "check_component_compatibility",
    },
    "sensor_erratic": {
        "label": "Sensor Erratic / No Reading",
        "example_symptoms": [
            "DHT22 returns NaN or garbage values",
            "sensor reading is noisy, stuck, or flatlined",
            "sensor not responding at all",
        ],
        "known_signature": None,  # not yet a documented signature in this project -- retrieval/general reasoning only
        "related_tool": None,
    },
}


def list_categories() -> str:
    """Pure browsing entry point -- no retrieval needed. Call this when the
    user wants to browse known failure categories rather than describe a
    specific symptom yet."""
    lines = ["Known symptom categories (browsable):"]
    for key, info in SYMPTOM_CATEGORIES.items():
        lines.append(f"\n[{key}] {info['label']}")
        for ex in info["example_symptoms"]:
            lines.append(f"  - {ex}")
    return "\n".join(lines)


def get_category(category_hint: str) -> dict[str, object] | None:
    """Case/whitespace-tolerant lookup by key or label fragment. Returns
    None if nothing matches -- caller should fall back to retrieval-only
    or show the full browsable list rather than guess."""
    if not category_hint:
        return None
    key = category_hint.strip().lower().replace(" ", "_").replace("-", "_")
    if key in SYMPTOM_CATEGORIES:
        return SYMPTOM_CATEGORIES[key]
    # fall back to a loose substring match against labels
    hint_lower = category_hint.strip().lower()
    for info in SYMPTOM_CATEGORIES.values():
        if hint_lower in str(info["label"]).lower():
            return info
    return None


def format_category_info(info: dict[str, object]) -> str:
    lines = [f"Category: {info['label']}"]
    lines.append("Example symptoms:")
    for ex in info["example_symptoms"]:
        lines.append(f"  - {ex}")
    if info.get("known_signature"):
        lines.append(f"Documented signature (from this project's own validated findings): {info['known_signature']}")
    else:
        lines.append("No documented signature for this category yet in this project -- rely on retrieval and general reasoning, flagged as such.")
    if info.get("related_tool"):
        lines.append(f"Related tool to consider: {info['related_tool']}")
    return "\n".join(lines)
