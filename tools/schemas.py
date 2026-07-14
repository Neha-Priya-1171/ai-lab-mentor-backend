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

ALL_TOOLS = [COMPATIBILITY_CHECKER_TOOL, ERROR_LOG_ANALYZER_TOOL, REPORT_GENERATOR_TOOL]
