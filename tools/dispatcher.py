"""
Tool dispatcher — Phase 6, wired to real logic.

Design decision worth stating explicitly: these tools do NOT try to
produce a final Verdict / Signature / Report by themselves. They do the
grounded lookup — board profile facts, error signature matches, RAG
context — and hand structured findings back to the model. The model,
guided by the Shared Rules already validated in Phase 4/5
(Engineering Reasoning Is Mandatory, Asking vs. Concluding Are Mutually
Exclusive, Hard Rules) and re-stated in system_prompt.md, is still what
turns grounded facts into a labeled Verdict/Fix/Source or a
Signature/Meaning/Likely Cause block.

Why split it this way: the Phase 4/5 prompt work (few-shot WRONG/RIGHT
examples, the source/sink topology fix, the Asking-vs-Concluding mutual
exclusivity rule) is real, tested prompt engineering. Re-deriving that
reasoning in Python would throw away validated work and require
re-testing everything from scratch. Instead, Phase 6 changes *how the
model decides to reach for domain knowledge* (tool call vs. hardcoded
Step-0 routing) without discarding *what it does with that knowledge*
(the Shared Rules).
"""

from __future__ import annotations

from typing import Any, Callable

import ground_truth as gt
from tools.power_budget import format_power_budget_result
from tools.multimeter_reference import (
    get_measurement_setup,
    interpret_digital_logic_reading,
    interpret_continuity_reading,
)
from tools.symptom_map import list_categories, get_category, format_category_info

RetrieverFn = Callable[[str, int], list[str]]
_retriever: RetrieverFn | None = None


def set_retriever(fn: RetrieverFn) -> None:
    """Injected once at startup by main.py — wraps the existing
    Cohere-embed + Pinecone-query pipeline. Kept as a hook so this module
    has no direct Cohere/Pinecone dependency."""
    global _retriever
    _retriever = fn


def _retrieve(query: str, top_k: int = 3) -> list[str]:
    if _retriever is None:
        return []
    try:
        return _retriever(query, top_k)
    except Exception as e:  # retrieval failure shouldn't crash the tool call
        return [f"(retrieval error, proceeding without it: {e})"]


# ---------------------------------------------------------------------------
# Compatibility Checker
# ---------------------------------------------------------------------------

def check_component_compatibility(component_a: str, component_b: str, connection_topology: str | None = None) -> str:
    lines: list[str] = [f"Compatibility lookup: '{component_a}' <-> '{component_b}'"]
    if connection_topology:
        lines.append(f"Stated topology: {connection_topology}")

    for label, comp in (("A", component_a), ("B", component_b)):
        pin = gt.normalize_gpio(comp)
        if pin:
            info = gt.lookup_pin(pin)
            lines.append(f"\nBoard profile — {label} ({pin}):")
            lines.append(f"  input_only={info['input_only']}, flash_reserved={info['flash_reserved']}, "
                          f"output_capable={info['output_capable']}, adc1={info['adc1']}, adc2={info['adc2']}")
            if info["strapping_note"]:
                lines.append(f"  STRAPPING PIN WARNING: {info['strapping_note']}")
            if info["input_only"]:
                lines.append("  NOTE: input-only pins cannot source/sink current at all — "
                              "any incompatibility here is 'wrong pin', never 'needs a driver stage'.")
            if info["flash_reserved"]:
                lines.append("  NOTE: this pin is reserved for internal flash — do not use for anything.")

    direction, limit_ma = gt.source_or_sink(connection_topology)
    if connection_topology and direction is None:
        lines.append(
            "\nTopology stated but not recognized as clearly GND-side or VCC-side — "
            "the model should ask for clarification rather than assume a limit."
        )
    elif direction:
        lines.append(f"\nTopology resolves to: {direction} current, GPIO limit = {limit_ma} mA per pin "
                      f"(chip-wide GPIO budget: {gt.TOTAL_CHIP_GPIO_BUDGET_MA} mA).")
    else:
        lines.append(
            "\nNo connection topology given yet — per the Asking-vs-Concluding rule, "
            "do not assume source vs. sink; ask which side is GND and which is 3.3V/VCC "
            "before applying a current limit."
        )

    lines.append(f"\nLogic level reference: {gt.LOGIC_LEVEL_NOTE}")

    for label, comp in (("A", component_a), ("B", component_b)):
        if gt.normalize_gpio(comp):
            continue
        chunks = _retrieve(f"{comp} voltage current specifications datasheet", top_k=3)
        if chunks:
            lines.append(f"\nRetrieved datasheet context for {label} ('{comp}'):")
            for c in chunks:
                lines.append(f"  - {c[:500]}")
        else:
            lines.append(f"\nNo datasheet context retrieved for {label} ('{comp}'). "
                          f"If a numeric spec is needed and not already known, ask the user "
                          f"or flag as general engineering knowledge — never invent a number.")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Error Log Analyzer
# ---------------------------------------------------------------------------

def analyze_error_log(log_text: str) -> str:
    reset_matches = gt.find_reset_codes(log_text)
    keyword_matches = gt.find_keyword_signatures(log_text)

    if not reset_matches and not keyword_matches:
        return (
            "No recognized reset-code (rst:0xN) or known exception keyword "
            "(Guru Meditation, LoadProhibited, stack canary) found in the pasted text. "
            "Say so explicitly to the user rather than inventing a plausible-sounding cause — "
            "ask them to paste the specific error/reset line if they have one."
        )

    lines: list[str] = []
    for m in reset_matches:
        lines.append(f"Reset code {m['code']} ({m['matched_name']}): {m['meaning']}")
        if m.get("is_fault") is False:
            lines.append("  -> Not itself a fault; expected under normal operation.")
        chunks = _retrieve(f"{m['matched_name']} ESP32 root cause", top_k=2)
        for c in chunks:
            lines.append(f"  Retrieved context: {c[:500]}")

    for k in keyword_matches:
        lines.append(f"\nSignature: {k['name']}")
        lines.append(f"Meaning: {k['meaning']}")
        lines.append(f"Firmware or Hardware: {k['firmware_or_hardware']}")
        chunks = _retrieve(f"{k['name']} ESP32 cause explanation", top_k=2)
        for c in chunks:
            lines.append(f"  Retrieved context: {c[:500]}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Report Generator
# ---------------------------------------------------------------------------

def generate_diagnostic_report(session_transcript: str) -> str:
    candidate_terms = ["ESP32", "SSD1306", "DHT22", "relay", "AMS1117", "I2C", "brownout"]
    found_terms = [t for t in candidate_terms if t.lower() in session_transcript.lower()]

    context_blocks: list[str] = []
    for term in found_terms:
        chunks = _retrieve(f"{term} datasheet reference", top_k=1)
        print(f"DEBUG retrieval for '{term}': {chunks}")   # <-- temporary, remove after checking
        for c in chunks:
            context_blocks.append(f"{term}: {c[:400]}")

    result = [
        "Session transcript received for report generation "
        f"({len(session_transcript)} chars). Supplementary retrieved context "
        f"for terms found in the transcript ({', '.join(found_terms) or 'none detected'}):",
    ]
    result.extend(context_blocks or ["(no supplementary context retrieved)"])
    result.append(
        "\nReminder to the model: follow the 10-section Report Generator format exactly "
        "as specified in the system prompt (Problem Statement through Documentation "
        "References, plus the unnumbered Learning Resources appendix). Do not invent "
        "citations not present in the transcript or the retrieved context above."
    )
    return "\n".join(result)


# ---------------------------------------------------------------------------
# Multimeter Assistant (Phase 7)
# ---------------------------------------------------------------------------
# Same combined-source pattern as check_component_compatibility: universal
# meter-usage facts and basic digital-logic threshold conventions come from
# tools/multimeter_reference.py (true regardless of board/component, safe to
# hardcode). Anything board-specific reuses the existing GPIO board profile
# (gt.normalize_gpio / gt.lookup_pin). Anything datasheet-specific (a real
# component's expected resistance/voltage) comes from _retrieve() against
# the real corpus -- never guessed here.
#
# This tool is also the structured hook for the project's own Rule 4
# ("measurement before speculation", established Phase 1) -- calling it is
# how the model requests/interprets a real reading instead of just asking
# in prose.

def guide_multimeter_measurement(
    measurement_type: str,
    test_point: str,
    component_or_pin: str | None = None,
    measured_value: float | None = None,
    unit: str | None = None,
    meter_beeped: bool | None = None,
) -> str:
    setup = get_measurement_setup(measurement_type)
    if setup is None:
        return (
            f"ERROR: unrecognized measurement_type '{measurement_type}'. "
            f"Valid options: voltage_dc, resistance, continuity, current_dc."
        )

    lines: list[str] = [
        f"Multimeter guidance — {setup['label']} measurement at: {test_point}",
        f"Meter setting: {setup['meter_setting']}",
        f"Probe placement: {setup['probe_placement']}",
        f"Safety note: {setup['safety_note']}",
    ]

    if component_or_pin:
        pin = gt.normalize_gpio(component_or_pin)
        if pin:
            info = gt.lookup_pin(pin)
            lines.append(f"\nBoard profile — {pin}:")
            lines.append(
                f"  input_only={info['input_only']}, output_capable={info['output_capable']}, "
                f"adc1={info['adc1']}, adc2={info['adc2']}"
            )
            if info["input_only"]:
                lines.append(
                    "  NOTE: input-only pin — a HIGH/LOW reading here reflects an external "
                    "signal being fed IN, not anything this pin is driving out."
                )
            if info["strapping_note"]:
                lines.append(f"  STRAPPING PIN WARNING: {info['strapping_note']} "
                              f"(relevant if measuring during/right after power-up or reset).")
            lines.append(f"  Logic level reference: {gt.LOGIC_LEVEL_NOTE}")
        else:
            chunks = _retrieve(f"{component_or_pin} {test_point} expected voltage resistance value", top_k=2)
            if chunks:
                lines.append(f"\nRetrieved datasheet context for '{component_or_pin}':")
                for c in chunks:
                    lines.append(f"  - {c[:500]}")
            else:
                lines.append(
                    f"\nNo datasheet context retrieved for '{component_or_pin}'. If an expected "
                    f"value is needed here and isn't already known, ask the user or flag as "
                    f"general engineering knowledge — never invent a specific figure."
                )

    if measured_value is not None:
        lines.append(f"\nReported reading: {measured_value}{' ' + unit if unit else ''}")
        if measurement_type == "voltage_dc" and unit:
            lines.append(f"Interpretation: {interpret_digital_logic_reading(measured_value, unit)}")
        elif measurement_type == "continuity":
            lines.append(f"Interpretation: {interpret_continuity_reading(measured_value, meter_beeped)}")
    elif meter_beeped is not None:
        lines.append(f"\nInterpretation: {interpret_continuity_reading(None, meter_beeped)}")

    lines.append(
        "\nReminder to the model: this tool supplies meter setup and structural "
        "interpretation only. Any specific expected value for THIS component (e.g. "
        "'this relay's coil should read X ohms') must come from the retrieved context "
        "above, not be invented — flag as unverified general knowledge if no context "
        "was retrieved and a number is still needed."
    )

    return "\n".join(lines)

# ---------------------------------------------------------------------------
# Symptom -> Root Cause Mapping (Phase 7)
# ---------------------------------------------------------------------------
# Per V2_ROADMAP.md: "a browsable, queryable version of the existing
# common-failures.md knowledge base." The category index in
# tools/symptom_map.py is browsable on its own (no retrieval needed, and
# built only from signatures already validated in this project's phase
# logs). Retrieval against the existing shared corpus (which already
# includes common-failures.md, per Phase 3) fills in whatever the category
# index doesn't cover -- same _retrieve() hook every other tool here uses,
# no new Cohere/Pinecone wiring needed.

def map_symptom_to_root_cause(symptom_description: str | None = None, category_hint: str | None = None) -> str:
    category_info = get_category(category_hint) if category_hint else None

    # Pure browse mode: no symptom text and no resolvable category -- hand
    # back the index rather than guessing what the user meant.
    if not symptom_description and category_info is None:
        if category_hint:
            return f"'{category_hint}' didn't match a known category.\n\n{list_categories()}"
        return list_categories()

    lines: list[str] = []

    if category_info:
        lines.append(format_category_info(category_info))

    if symptom_description:
        chunks = _retrieve(f"{symptom_description} ESP32 common failure root cause", top_k=3)
        if chunks:
            lines.append(f"\nRetrieved failure-library context for '{symptom_description}':")
            for c in chunks:
                lines.append(f"  - {c[:500]}")
        else:
            lines.append(
                f"\nNo failure-library context retrieved for '{symptom_description}'. "
                f"Reason from general engineering knowledge if needed, flagged as unverified, "
                f"or ask a clarifying question rather than asserting a specific documented cause."
            )

    lines.append(
        "\nReminder to the model: only state a root cause as 'documented' if it came from "
        "the category info or retrieved context above. Never invent a citation to "
        "common-failures.md or a datasheet that wasn't actually retrieved this turn."
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Power Budget Calculator (Phase 7)
# ---------------------------------------------------------------------------

# (Ohm's Law, current summation) in Python rather than grounded-lookup +
# RAG -- per V2_ROADMAP.md's Phase 7 scoping ("mostly deterministic math...
# can be implemented as a real function tool the model calls with parsed
# values, not just LLM-guessed arithmetic"). No retrieval call here; there's
# no datasheet prose to ground, just numbers the model already extracted
# from the conversation into structured arguments.

def calculate_power_budget(supply_voltage_v: float, supply_current_limit_ma: float, components: list[dict]) -> str:
    return format_power_budget_result(supply_voltage_v, supply_current_limit_ma, components)


_DISPATCH_TABLE: dict[str, Callable[..., str]] = {
    "check_component_compatibility": check_component_compatibility,
    "analyze_error_log": analyze_error_log,
    "generate_diagnostic_report": generate_diagnostic_report,
    "calculate_power_budget": calculate_power_budget,
    "guide_multimeter_measurement": guide_multimeter_measurement,
    "map_symptom_to_root_cause": map_symptom_to_root_cause,
}


def dispatch(tool_name: str, arguments: dict[str, Any]) -> str:
    fn = _DISPATCH_TABLE.get(tool_name)
    if fn is None:
        return f"ERROR: unknown tool '{tool_name}'"
    try:
        return fn(**arguments)
    except TypeError as e:
        return f"ERROR: bad arguments for '{tool_name}': {e}"
