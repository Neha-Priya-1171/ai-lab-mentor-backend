"""
Grounding guard — a deterministic backstop for one specific, narrow
fabrication pattern: the model attaching an invented version/section/
page locator to a real document name (e.g. "ESP32 Series Datasheet
v5.2", "SSD1306 Datasheet Section 8") when that exact locator was not
actually present in anything retrieved this turn.

Why code instead of another prompt patch: the corresponding Hard Rule in
system_prompt.md has now failed live testing twice on this exact sub-
pattern (once before the literal example string was de-referenced from
the prompt, once after) -- per this project's own bounded-patching
principle, that's the signal to stop iterating in English on this one
narrow thing and add a mechanical check instead.

Scope, stated explicitly so it isn't mistaken for more than it is: this
only catches a document name immediately followed by a version/section/
page-style locator. It does NOT catch the broader pattern of a plausible
spec *value* (a voltage, a percentage, a current rating) being attributed
to "the datasheet" without a locator -- that's a semantic judgment call,
not a string-matching one, and is left to the existing prompt-level
grounding rules (CONCLUSION-STAGE GROUNDING, the Viva Mode bright-line
rule, etc.). If those also show recurring failures on a *value* rather
than a *locator*, that's a separate, harder problem to solve in code.

Known scope gap (documented, not yet fixed): build_grounded_text() below
only pulls from this turn's "tool"-role messages plus the system prompt
-- it does not include earlier assistant turns in the session history.
So a locator that was legitimately established several turns ago (which
the Viva Mode prompt rule explicitly permits reusing) can still get
stripped here if referenced again later, since it isn't part of *this*
turn's tool output. This makes the guard stricter than the prompt rule
intends, but the failure direction is safe (over-cautious, not under-
cautious) -- flagged for a future pass rather than blocking on it now.
"""

from __future__ import annotations

import re

# Matches: <Document-ish Name> <Datasheet|Specification|Spec|Reference Manual> <locator>
# "Document-ish Name" is kept loose (up to 5 capitalized/alnum tokens) since
# real component/chip names vary a lot (ESP32, SSD1306, AMS1117, SRD-05VDC...).
_LOCATOR_PATTERN = re.compile(
    r"""
    (?P<name>
        (?:[A-Z][\w\-\+/]*\s+){0,4}[A-Z][\w\-\+/]*\s*
        (?:Datasheet|Specification|Spec|Reference\s+Manual)
    )
    \s*
    (?P<locator>
        (?:v|ver\.?|version)\s?\d+(?:\.\d+)?
        | Rev(?:ision)?\.?\s?\d+(?:\.\d+)?
        | Section\s?\d+(?:\.\d+)?
        | Chapter\s?\d+
        | p(?:age|g)\.?\s?\d+
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


def strip_unverified_locators(reply_text: str, grounded_text: str) -> str:
    """
    reply_text: the model's final reply for this turn, before returning it.
    grounded_text: everything actually retrieved/available this turn --
        concatenation of every "tool"-role message's content plus the
        plain-conversation Context block (already inside system_prompt).
        The only place a genuine locator could legitimately come from.

    If a matched locator's exact text doesn't appear verbatim (case-
    insensitive) in grounded_text, strip just the locator and leave the
    document name -- "per the ESP32 datasheet" is fine on its own; only
    the invented specificity is removed. If it DOES appear (a real
    retrieved chunk actually contained that version/section tag), leave
    the whole match untouched.
    """
    if not reply_text:
        return reply_text

    grounded_lower = grounded_text.lower()

    def _replace(m: re.Match) -> str:
        locator = m.group("locator")
        if locator.lower() in grounded_lower:
            return m.group(0)
        return m.group("name").rstrip()

    return _LOCATOR_PATTERN.sub(_replace, reply_text)


def build_grounded_text(full_messages: list[dict], system_prompt: str) -> str:
    """Concatenate every tool-result message from this turn plus the system
    prompt (which carries the plain-conversation Context block) into one
    string to check locators against."""
    tool_contents = [
        str(m.get("content") or "")
        for m in full_messages
        if m.get("role") == "tool"
    ]
    return "\n".join(tool_contents) + "\n" + system_prompt
