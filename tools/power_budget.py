"""
Power Budget Calculator tool (Phase 7).

Follows the Phase 6 tool design rule from PHASE6_LOG.md section 2:
tools return grounded FACTS, never a final Verdict. The model still writes
Verdict/Reasoning/Fix, governed by system_prompt.md's Shared Rules
(Engineering Reasoning Is Mandatory, unsourced-number flagging, etc).

This tool's whole job is to be the one place in the app doing real
arithmetic, so a current budget is never LLM-guessed. Ohm's Law and
current-summation only -- no engineering judgment happens in this file.
"""

from dataclasses import dataclass, field


# 80% is the standard engineering derating convention for continuous loads
# on a supply rail (mirrors common practice for USB/regulator continuous
# draw, distinct from a rail's absolute max). Kept as a named constant so
# the model's "flag" is traceable to one place, not a magic number.
DERATING_FACTOR = 0.8


@dataclass
class ComponentLoad:
    name: str
    quantity: int = 1
    # Provide EITHER current_ma directly OR resistance_ohms (+ rail voltage
    # from the request) to derive current via Ohm's Law.
    current_ma: float | None = None
    resistance_ohms: float | None = None
    # Optional: for peak/inrush components (e.g. servos, motors) so the
    # tool can report steady-state vs peak separately instead of the model
    # having to guess which number matters.
    peak_current_ma: float | None = None
    note: str = ""


@dataclass
class ComponentResult:
    name: str
    quantity: int
    unit_current_ma: float
    total_current_ma: float
    unit_peak_current_ma: float | None
    total_peak_current_ma: float | None
    derivation: str  # "given" or "ohms_law (V / R)"
    note: str = ""


def calculate_power_budget(
    supply_voltage_v: float,
    supply_current_limit_ma: float,
    components: list[dict],
) -> dict:
    """
    Pure arithmetic. No hedging, no invented numbers -- every current value
    either came from the caller (component current_ma) or was derived by
    Ohm's Law from a caller-supplied resistance at the given rail voltage.

    Args:
        supply_voltage_v: rail voltage the components share (e.g. 5.0, 3.3)
        supply_current_limit_ma: rated/continuous current budget of the
            supply for this rail (e.g. USB 2.0 port = 500, USB 3.0 = 900,
            a specific 5V/2A wall adapter = 2000)
        components: list of dicts, each with:
            name (str, required)
            quantity (int, default 1)
            current_ma (float, optional)
            resistance_ohms (float, optional -- used only if current_ma absent)
            peak_current_ma (float, optional)
            note (str, optional)

    Returns:
        dict of computed facts -- see structure below. Contains no
        engineering verdict language ("safe"/"unsafe"/"compatible") by
        design; that judgment belongs to the model, per the Phase 6
        tool-output convention.
    """
    if supply_voltage_v <= 0:
        raise ValueError("supply_voltage_v must be positive")
    if supply_current_limit_ma <= 0:
        raise ValueError("supply_current_limit_ma must be positive")

    results: list[ComponentResult] = []
    total_steady_ma = 0.0
    total_peak_ma = 0.0
    missing_data: list[str] = []

    for c in components:
        name = c.get("name", "unnamed component")
        qty = int(c.get("quantity", 1))
        current_ma = c.get("current_ma")
        resistance_ohms = c.get("resistance_ohms")
        peak_current_ma = c.get("peak_current_ma")
        note = c.get("note", "")

        if current_ma is not None:
            unit_current = float(current_ma)
            derivation = "given"
        elif resistance_ohms is not None:
            if resistance_ohms <= 0:
                missing_data.append(
                    f"{name}: resistance_ohms must be positive, got {resistance_ohms}"
                )
                continue
            # Ohm's Law: I = V / R, converted to mA
            unit_current = (supply_voltage_v / float(resistance_ohms)) * 1000
            derivation = "ohms_law (V / R)"
        else:
            missing_data.append(
                f"{name}: no current_ma or resistance_ohms provided -- "
                f"cannot compute, do not guess a figure for this component"
            )
            continue

        total_unit = unit_current * qty
        total_steady_ma += total_unit

        unit_peak = float(peak_current_ma) if peak_current_ma is not None else None
        total_peak = unit_peak * qty if unit_peak is not None else None
        if total_peak is not None:
            total_peak_ma += total_peak
        else:
            total_peak_ma += total_unit  # no peak given -> steady value is the only known ceiling

        results.append(
            ComponentResult(
                name=name,
                quantity=qty,
                unit_current_ma=round(unit_current, 2),
                total_current_ma=round(total_unit, 2),
                unit_peak_current_ma=round(unit_peak, 2) if unit_peak is not None else None,
                total_peak_current_ma=round(total_peak, 2) if total_peak is not None else None,
                derivation=derivation,
                note=note,
            )
        )

    derated_budget_ma = supply_current_limit_ma * DERATING_FACTOR
    margin_steady_ma = supply_current_limit_ma - total_steady_ma
    margin_peak_ma = supply_current_limit_ma - total_peak_ma

    return {
        "supply_voltage_v": supply_voltage_v,
        "supply_current_limit_ma": supply_current_limit_ma,
        "derating_factor": DERATING_FACTOR,
        "derated_continuous_budget_ma": round(derated_budget_ma, 2),
        "components": [c.__dict__ for c in results],
        "total_steady_current_ma": round(total_steady_ma, 2),
        "total_peak_current_ma": round(total_peak_ma, 2),
        "margin_vs_rated_limit_steady_ma": round(margin_steady_ma, 2),
        "margin_vs_rated_limit_peak_ma": round(margin_peak_ma, 2),
        "exceeds_rated_limit_steady": total_steady_ma > supply_current_limit_ma,
        "exceeds_rated_limit_peak": total_peak_ma > supply_current_limit_ma,
        "exceeds_derated_continuous_budget": total_steady_ma > derated_budget_ma,
        "missing_data": missing_data,
    }


# ---------------------------------------------------------------------------
# Dispatcher-facing wrapper. dispatcher.py's _DISPATCH_TABLE calls each tool
# function with fn(**arguments) and expects a str back (it gets appended
# directly as a "tool" message's content) -- same contract as
# check_component_compatibility / analyze_error_log / generate_diagnostic_report,
# all of which build a `lines` list and return "\n".join(lines) rather than
# raw JSON. This wrapper follows that exact convention so the model sees
# power-budget facts in the same readable, note-annotated style as every
# other tool's output.
# ---------------------------------------------------------------------------

def format_power_budget_result(
    supply_voltage_v: float,
    supply_current_limit_ma: float,
    components: list[dict],
) -> str:
    try:
        r = calculate_power_budget(supply_voltage_v, supply_current_limit_ma, components)
    except ValueError as e:
        return f"ERROR: {e}"

    lines: list[str] = [
        f"Power budget: {r['supply_voltage_v']}V rail, "
        f"{r['supply_current_limit_ma']}mA rated supply limit."
    ]

    if not r["components"]:
        lines.append("\nNo components could be computed -- see missing data below.")
    else:
        lines.append("\nPer-component draw:")
        for c in r["components"]:
            peak_str = (
                f", peak {c['total_peak_current_ma']}mA total" if c["total_peak_current_ma"] is not None
                and c["total_peak_current_ma"] != c["total_current_ma"] else ""
            )
            qty_str = f" x{c['quantity']}" if c["quantity"] != 1 else ""
            lines.append(
                f"  - {c['name']}{qty_str}: {c['unit_current_ma']}mA each, "
                f"{c['total_current_ma']}mA total{peak_str} "
                f"[{c['derivation']}]"
            )
            if c["note"]:
                lines.append(f"    note: {c['note']}")

    lines.append(f"\nTotal steady-state current: {r['total_steady_current_ma']}mA")
    lines.append(f"Total peak current (worst case, if any peaks given): {r['total_peak_current_ma']}mA")
    lines.append(
        f"Margin vs. rated limit: {r['margin_vs_rated_limit_steady_ma']}mA steady, "
        f"{r['margin_vs_rated_limit_peak_ma']}mA peak"
    )
    lines.append(
        f"Standard 80% continuous-derating budget for this supply: "
        f"{r['derated_continuous_budget_ma']}mA (this is a separate, stricter "
        f"threshold than the rated limit -- a load can sit under the rated max "
        f"and still exceed this convention for continuous/always-on draw)."
    )

    flags = []
    if r["exceeds_rated_limit_steady"]:
        flags.append("EXCEEDS RATED SUPPLY LIMIT (steady-state) -- this is a hard problem, not a margin note.")
    if r["exceeds_rated_limit_peak"]:
        flags.append("EXCEEDS RATED SUPPLY LIMIT (peak/inrush) -- likely brownout/reset risk under load spikes.")
    if r["exceeds_derated_continuous_budget"] and not r["exceeds_rated_limit_steady"]:
        flags.append("Exceeds the 80% continuous-derating budget, though under the rated max -- flag as a margin/reliability concern, not a hard failure.")
    if flags:
        lines.append("\nFlags:")
        for f in flags:
            lines.append(f"  - {f}")
    else:
        lines.append("\nNo flags -- steady and peak draw both sit within the rated limit and the derated continuous budget.")

    if r["missing_data"]:
        lines.append(
            "\nMissing data (excluded from totals above -- do not guess a figure "
            "for these, ask the user or flag as unverified general knowledge):"
        )
        for m in r["missing_data"]:
            lines.append(f"  - {m}")

    return "\n".join(lines)
