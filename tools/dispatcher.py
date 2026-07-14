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


_DISPATCH_TABLE: dict[str, Callable[..., str]] = {
    "check_component_compatibility": check_component_compatibility,
    "analyze_error_log": analyze_error_log,
    "generate_diagnostic_report": generate_diagnostic_report,
}


def dispatch(tool_name: str, arguments: dict[str, Any]) -> str:
    fn = _DISPATCH_TABLE.get(tool_name)
    if fn is None:
        return f"ERROR: unknown tool '{tool_name}'"
    try:
        return fn(**arguments)
    except TypeError as e:
        return f"ERROR: bad arguments for '{tool_name}': {e}"
