"""
Tool schemas — the actual "agent, not workflow" milestone.

Phase 4/5 built these three capabilities (Compatibility Checker, Error Log
Analyzer, Report Generator) as *modes* selected by a hardcoded "Step 0"
instruction inside one giant prompt. Phase 6's job is to expose them as
real callable tools instead, so the model decides which to invoke based
on conversation context — genuine tool-calling, not a routing instruction.

Schema shape follows OpenAI's function-calling JSON schema convention
(name/description/parameters), since that's what Groq consumes directly
and what providers/gemini_provider.py translates into Gemini's
functionDeclarations shape.

IMPORTANT — wiring note for whoever integrates this:
The `description` fields below are the ONLY signal the model uses to
decide *when* to call each tool. Per the project's own established
finding ("few-shot WRONG/RIGHT examples reliably outperform prose for
behavioral constraints on this stack"), if tool-selection turns out to be
unreliable in testing, the fix is almost certainly sharpening these
descriptions with concrete trigger phrases — not rewriting the tool
logic itself. Test tool *selection* and tool *execution* as two separate
concerns.
"""

from __future__ import annotations

COMPATIBILITY_CHECKER_TOOL = {
    "name": "check_component_compatibility",
    "description": (
        "Check whether two hardware components (e.g. a GPIO pin and a relay, "
        "a battery and an LDO regulator, a sensor and a microcontroller pin) "
        "are electrically compatible — voltage, current, and logic-level "
        "matching. Call this when the user asks 'can I connect X to Y', "
        "'is X compatible with Y', or describes a wiring plan before it's "
        "built, as opposed to describing a fault in something already wired."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "component_a": {"type": "string", "description": "First component or pin, e.g. 'ESP32 GPIO34' or '12V relay coil'"},
            "component_b": {"type": "string", "description": "Second component, e.g. 'AMS1117 3.3V LDO' or 'Li-ion battery direct'"},
            "connection_topology": {
                "type": "string",
                "description": "How they're wired, if known/relevant, e.g. 'GPIO to GND (sourcing)' vs 'GPIO to VCC (sinking)'. Omit if not yet known — the tool should then ask for it rather than guess.",
            },
        },
        "required": ["component_a", "component_b"],
    },
}

ERROR_LOG_ANALYZER_TOOL = {
    "name": "analyze_error_log",
    "description": (
        "Analyze an ESP32 error/reset log — reset reason codes (rst:0x..), "
        "Guru Meditation / panic traces, stack canary messages, backtraces, "
        "or Wi-Fi error prefixes — and identify the likely cause. Call this "
        "when the user pastes raw serial monitor output or a crash log, as "
        "opposed to describing symptoms in their own words."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "log_text": {"type": "string", "description": "The raw log/serial output pasted by the user"},
        },
        "required": ["log_text"],
    },
}

REPORT_GENERATOR_TOOL = {
    "name": "generate_diagnostic_report",
    "description": (
        "Synthesize a completed diagnostic session (chat transcript and/or "
        "JSON state) into a professional Markdown report with the required "
        "10 sections plus a Learning Resources appendix. Call this only "
        "when the user explicitly asks for a report/summary/writeup of a "
        "diagnostic session that has already reached (or is close to) a "
        "conclusion — not mid-diagnosis."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_transcript": {"type": "string", "description": "Raw transcript and/or JSON state dump of the diagnostic session"},
        },
        "required": ["session_transcript"],
    },
}

POWER_BUDGET_TOOL = {
    "name": "calculate_power_budget",
    "description": (
        "Compute total current draw vs. a supply's current budget for "
        "components on one voltage rail (Ohm's Law + current summation). "
        "Call when asked if a supply (USB/wall adapter/battery) can power "
        "given components, or for current-budget math. Always call this for "
        "the arithmetic itself, never estimate margin yourself. Needs "
        "current_ma or resistance_ohms per component; omit both rather than "
        "guessing — flagged as missing data."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "supply_voltage_v": {
                "type": "number",
                "description": "Rail voltage, e.g. 5.0 or 3.3.",
            },
            "supply_current_limit_ma": {
                "type": "number",
                "description": "Supply's rated mA (e.g. 500=USB 2.0, 900=USB 3.0, 2000=5V/2A adapter). Ask if unstated, don't guess.",
            },
            "components": {
                "type": "array",
                "description": "Loads sharing the rail.",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "quantity": {"type": "integer", "default": 1},
                        "current_ma": {"type": "number", "description": "Known steady-state draw in mA."},
                        "resistance_ohms": {"type": "number", "description": "Used to derive current via Ohm's Law if current_ma unknown."},
                        "peak_current_ma": {"type": "number", "description": "Peak/stall current if different from steady-state."},
                        "note": {"type": "string"},
                    },
                    "required": ["name"],
                },
            },
        },
        "required": ["supply_voltage_v", "supply_current_limit_ma", "components"],
    },
}

MULTIMETER_ASSISTANT_TOOL = {
    "name": "guide_multimeter_measurement",
    "description": (
        "Guide a multimeter measurement (DC voltage/resistance/continuity/"
        "current) and/or interpret a reading already taken. Call when "
        "diagnosis calls for a real measurement over speculation — the "
        "structured version of 'measurement before speculation.' Call once "
        "to request the measurement (measured_value omitted), again once "
        "reported (measured_value provided) for grounded interpretation."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "measurement_type": {
                "type": "string",
                "enum": ["voltage_dc", "resistance", "continuity", "current_dc"],
                "description": "Which kind of measurement.",
            },
            "test_point": {
                "type": "string",
                "description": "What's being measured, e.g. '3.3V rail', 'I2C SDA/SCL pull-up', 'GPIO2 output state'.",
            },
            "component_or_pin": {
                "type": "string",
                "description": "Optional GPIO (e.g. 'GPIO34') or named component if the measurement targets one directly.",
            },
            "measured_value": {
                "type": "number",
                "description": "Numeric reading, if already taken. Omit when just requesting a measurement.",
            },
            "unit": {
                "type": "string",
                "description": "Unit of measured_value, e.g. 'V' or 'ohm'. Needed with voltage readings for HIGH/LOW interpretation.",
            },
            "meter_beeped": {
                "type": "boolean",
                "description": "For continuity, whether the beep sounded, if reported that way instead of a raw ohms value.",
            },
        },
        "required": ["measurement_type", "test_point"],
    },
}

SYMPTOM_MAP_TOOL = {
    "name": "map_symptom_to_root_cause",
    "description": (
        "Browse known failure categories or look up likely root causes for a "
        "described symptom, grounded in the failure library (common-"
        "failures.md) plus retrieved context. Call with no args to browse. "
        "Call with symptom_description when the user describes a fault in "
        "their own words (e.g. 'display is blank', 'keeps resetting') early "
        "in a session, to surface documented patterns fast."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "symptom_description": {
                "type": "string",
                "description": "Symptom in the user's own words. Omit to browse categories.",
            },
            "category_hint": {
                "type": "string",
                "description": "Known category, e.g. 'i2c_communication', 'power_brownout', 'firmware_crash', 'output_driver_mismatch', 'sensor_erratic'.",
            },
        },
        "required": [],
    },
}

ALL_TOOLS = [
    COMPATIBILITY_CHECKER_TOOL,
    ERROR_LOG_ANALYZER_TOOL,
    REPORT_GENERATOR_TOOL,
    POWER_BUDGET_TOOL,
    MULTIMETER_ASSISTANT_TOOL,
    SYMPTOM_MAP_TOOL,
]

# ---------------------------------------------------------------------------
# Per-turn tool filtering (Phase 7 TPM mitigation)
# ---------------------------------------------------------------------------
# Groq's free-tier TPM limit (12,000) reserves the full tool-schema list
# against every single request. Sending all 6 tools every turn is real,
# measured overhead (~1,932 tokens). This trims that -- but deliberately
# does NOT try to guess "the one tool" the model needs, since a live test
# proved check_component_compatibility, analyze_error_log,
# calculate_power_budget, and guide_multimeter_measurement genuinely chain
# together within a single troubleshooting flow (multimeter reading fed a
# power-budget check fed another multimeter reading in the same session).
# Those four are always sent together as one cluster.
#
# Only generate_diagnostic_report and map_symptom_to_root_cause are ever
# excluded, and only when there's a clear, safe signal to do so. Bias is
# deliberately toward INCLUSION on any ambiguity -- a false inclusion only
# costs tokens, a false exclusion breaks a real capability. This is a
# genuine trade-off, not a routing rule reintroducing Phase 4's hardcoded
# Step-0 mode detection: the model still freely picks among whatever's
# offered each turn.

CORE_TOOL_CLUSTER = [
    COMPATIBILITY_CHECKER_TOOL,
    ERROR_LOG_ANALYZER_TOOL,
    POWER_BUDGET_TOOL,
    MULTIMETER_ASSISTANT_TOOL,
]

_SYMPTOM_KEYWORDS = (
    "what's usually", "whats usually", "why does", "why is", "common cause",
    "common failure", "browse", "categories", "category", "what causes",
    "usual cause", "known issues",
)


def get_relevant_tools(messages: list[dict]) -> list[dict]:
    """
    messages: the conversation history agent.py is about to send (before the
    system prompt is prepended), same list run_agent_turn already has.

    Returns the tool list to actually send this turn. Always includes the
    4-tool core cluster. Conditionally adds Report Generator (once there's
    real history to report on -- mirrors static/index.html's own
    reportBtn disabled-until-first-exchange rule) and Symptom Mapping
    (early in a session, or on a clear symptom-browsing phrase).
    """
    tools = list(CORE_TOOL_CLUSTER)

    latest_user_text = ""
    for m in reversed(messages):
        if m.get("role") == "user":
            latest_user_text = str(m.get("content") or "").lower()
            break

    if len(messages) > 1:
        tools.append(REPORT_GENERATOR_TOOL)

    early_session = len(messages) <= 4
    symptom_signal = any(kw in latest_user_text for kw in _SYMPTOM_KEYWORDS)
    if early_session or symptom_signal:
        tools.append(SYMPTOM_MAP_TOOL)

    return tools
