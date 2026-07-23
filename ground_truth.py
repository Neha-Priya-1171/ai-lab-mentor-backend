"""
Ground truth data — ported directly from the authoritative blocks in
combined-system-prompt-v2.md ("ESP32 BOARD PROFILE" and "ESP32 ERROR
SIGNATURE REFERENCE"). Kept as real Python data here (not prose re-fed
to the model every turn) so tools/dispatcher.py can look facts up
deterministically — matching the project's own established principle:
"Ground truth files over full-document RAG for small, fixed,
safety-relevant facts" (CLAUDE_CODE_PREREQUISITES.md).

If you ever edit the board profile or error table, this is the one file
to change — dispatcher.py and (if you choose to keep a text copy in the
system prompt for the plain-conversation diagnostic loop) system_prompt.md
should both trace back to this source rather than drifting independently.
"""

from __future__ import annotations

import re

# ---------------------------------------------------------------------------
# ESP32 BOARD PROFILE
# ---------------------------------------------------------------------------

INPUT_ONLY_PINS = {"GPIO34", "GPIO35", "GPIO36", "GPIO39"}
FLASH_RESERVED_PINS = {"GPIO6", "GPIO7", "GPIO8", "GPIO9", "GPIO10", "GPIO11"}
ADC1_PINS = {"GPIO32", "GPIO33", "GPIO34", "GPIO35", "GPIO36", "GPIO39"}
ADC2_PINS = {"GPIO0", "GPIO2", "GPIO4", "GPIO12", "GPIO13", "GPIO14", "GPIO15", "GPIO25", "GPIO26", "GPIO27"}

STRAPPING_PINS = {
    "GPIO0": "Must be HIGH for normal boot, LOW to enter flashing mode. Avoid external pull-downs or active-low devices here.",
    "GPIO2": "Must be LOW or floating at boot on most modules. Onboard LEDs here are usually fine; external pull-ups can prevent boot.",
    "GPIO12": "MTDI / flash voltage select — if pulled HIGH at boot, the chip selects 1.8V flash voltage, causing boot failure on most 3.3V-flash modules. Avoid external pull-ups on GPIO12. Well-known gotcha.",
    "GPIO15": "Must not be pulled LOW at boot on some modules. Lower risk than 0/2/12 but worth flagging for reset-loop diagnosis.",
}

BUS_DEFAULTS = {
    "I2C": {"SDA": "GPIO21", "SCL": "GPIO22", "note": "Arduino/ESP-IDF default, reassignable in software but assume unless user states otherwise."},
    "SPI": {"MOSI": "GPIO23", "MISO": "GPIO19", "SCK": "GPIO18", "CS": "GPIO5", "note": "VSPI default."},
    "UART0": {"TX": "GPIO1", "RX": "GPIO3", "note": "Shared with USB serial console — using these for other peripherals interferes with flashing/serial monitor."},
}

GPIO_SOURCE_LIMIT_MA = 12   # component wired GPIO -> GND (GPIO driven HIGH to turn on)
GPIO_SINK_LIMIT_MA = 20     # component wired 3.3V/VCC -> GPIO (GPIO driven LOW to turn on)
TOTAL_CHIP_GPIO_BUDGET_MA = 1200

LOGIC_LEVEL_V = 3.3
LOGIC_LEVEL_NOTE = (
    "ESP32 GPIO operates at 3.3V logic and is NOT 5V tolerant. Directly connecting a "
    "5V-output sensor or module to a GPIO can damage the pin or the chip. Requires a "
    "voltage divider or logic-level shifter on the signal line(s)."
)

_GPIO_PATTERN = re.compile(r"\bGPIO\s?(\d{1,2})\b", re.IGNORECASE)


def normalize_gpio(text: str) -> str | None:
    """Extract a canonical 'GPIOnn' token from free text like 'gpio 34' or 'GPIO34'."""
    m = _GPIO_PATTERN.search(text)
    if not m:
        return None
    return f"GPIO{int(m.group(1))}"


def lookup_pin(pin: str) -> dict:
    """Return everything the board profile knows about a specific GPIO pin."""
    pin = pin.upper().replace(" ", "")
    info: dict = {"pin": pin}
    info["input_only"] = pin in INPUT_ONLY_PINS
    info["flash_reserved"] = pin in FLASH_RESERVED_PINS
    info["output_capable"] = not info["input_only"] and not info["flash_reserved"]
    info["adc1"] = pin in ADC1_PINS
    info["adc2"] = pin in ADC2_PINS
    info["strapping_note"] = STRAPPING_PINS.get(pin)
    return info


def source_or_sink(connection_topology: str | None) -> tuple[str | None, int | None]:
    """Given a free-text description of wiring topology, decide which
    current limit applies. Mirrors the board profile's explicit rule:
    GPIO->GND = sourcing (12mA), 3.3V/VCC->GPIO = sinking (20mA).
    Returns (direction, limit_ma) or (None, None) if not determinable —
    callers MUST treat that as 'ask the user', never guess.
    """
    if not connection_topology:
        return None, None
    t = connection_topology.lower()
    if "gnd" in t or "ground" in t:
        return "sourcing", GPIO_SOURCE_LIMIT_MA
    if "vcc" in t or "3.3v" in t or "3v3" in t or "supply" in t:
        return "sinking", GPIO_SINK_LIMIT_MA
    return None, None


# ---------------------------------------------------------------------------
# ESP32 ERROR SIGNATURE REFERENCE
# ---------------------------------------------------------------------------
# Source: ESP-IDF reset reason enum (esp_reset_reason_t / ROM rtc.h).

RESET_REASON_CODES = {
    "0x1": {"name": "POWERON_RESET", "meaning": "Normal power-on reset (Vbat power on). Expected on every fresh power-up. Not itself a fault.", "is_fault": False},
    "0x3": {"name": "SW_RESET", "meaning": "Software-triggered reset (e.g. esp_restart() called in code, or ESP.restart() in Arduino).", "is_fault": False},
    "0x4": {"name": "OWDT_RESET", "meaning": "Legacy watchdog reset, digital core.", "is_fault": True},
    "0x5": {"name": "DEEPSLEEP_RESET", "meaning": "Woke from deep sleep. Expected behavior if the project intentionally uses deep sleep.", "is_fault": False},
    "0x6": {"name": "SDIO_RESET", "meaning": "Reset via SDIO interface.", "is_fault": True},
    "0x7": {"name": "TG0WDT_SYS_RESET", "meaning": "Timer Group 0 Watchdog reset (digital core). Code execution blocked/hung long enough to trigger the hardware watchdog — usually an infinite loop, a blocking call that never returns, or a task that never yields.", "is_fault": True},
    "0x8": {"name": "TG1WDT_SYS_RESET", "meaning": "Timer Group 1 Watchdog reset (digital core). Same root cause family as TG0WDT — code hung past the watchdog timeout.", "is_fault": True},
    "0x9": {"name": "RTCWDT_SYS_RESET", "meaning": "RTC Watchdog reset, digital core.", "is_fault": True},
    "0xA": {"name": "INTRUSION_RESET", "meaning": "Intrusion detection reset (security feature).", "is_fault": True},
    "0xB": {"name": "TG0WDT_CPU_RESET", "meaning": "Timer Group 0 Watchdog reset, CPU only.", "is_fault": True},
    "0xC": {"name": "SW_CPU_RESET", "meaning": "Software reset, CPU only.", "is_fault": False},
    "0xD": {"name": "RTCWDT_CPU_RESET", "meaning": "RTC Watchdog reset, CPU only.", "is_fault": True},
    "0xE": {"name": "EXT_CPU_RESET", "meaning": "One CPU core reset by the other (common on dual-core reset sequences, often not itself the root fault).", "is_fault": False},
    "0xF": {"name": "RTCWDT_BROWN_OUT_RESET", "meaning": "Brownout reset. Supply voltage dropped below the chip's minimum threshold during operation. The single most common ESP32 fault reported by makers — usually inadequate power supply current, not voltage regulation.", "is_fault": True},
    "0x10": {"name": "RTCWDT_RTC_RESET", "meaning": "RTC Watchdog reset, digital core and RTC module.", "is_fault": True},
}

_RESET_CODE_PATTERN = re.compile(r"rst:\s*(0x[0-9a-fA-F]+)\s*\(([A-Z0-9_]+)\)")

# Non-reset-code signatures that still matter (exception types, not in the
# reset reason table per the combined prompt's own note).
KEYWORD_SIGNATURES = {
    "guru meditation": {
        "name": "Guru Meditation Error",
        "meaning": "CPU exception (e.g. LoadProhibited, StoreProhibited, InstrFetchProhibited) — not a reset reason code, an exception type.",
        "is_fault": True,
        "firmware_or_hardware": "Firmware (in the overwhelming majority of cases)",
    },
    "loadprohibited": {
        "name": "LoadProhibited exception",
        "meaning": "Code attempted to read from a memory address not mapped to valid RAM/flash — most commonly dereferencing a NULL or uninitialized pointer.",
        "is_fault": True,
        "firmware_or_hardware": "Firmware",
    },
    "stack canary": {
        "name": "Stack canary watchpoint trigger",
        "meaning": "Stack overflow protection tripped — a task's stack was overrun.",
        "is_fault": True,
        "firmware_or_hardware": "Firmware",
    },
}


def _normalize_hex_code(code: str) -> str:
    """'0x0f' and '0xF' both normalize to '0xF' to match RESET_REASON_CODES keys
    (which use uppercase hex letters, e.g. '0xA'..'0xF'). Bug fixed here: this
    previously lowercased the result, so every code from 0xA-0xF -- including
    0xF (brownout) -- never matched the dict and silently fell through to
    'not in the known reference table', even though the code was recognized."""
    digits = code[2:].lstrip("0").upper()
    return "0x" + (digits if digits else "0")


def find_reset_codes(log_text: str) -> list[dict]:
    """Find all 'rst:0xN (NAME)' occurrences and resolve them against the table.
    Serial logs often zero-pad the hex code (e.g. '0x0f'); table keys don't, so
    normalize before lookup while preserving the originally-seen code for display.
    """
    matches = []
    for m in _RESET_CODE_PATTERN.finditer(log_text):
        raw_code, name = m.group(1), m.group(2)
        lookup_key = _normalize_hex_code(raw_code)
        entry = RESET_REASON_CODES.get(lookup_key)
        if entry:
            matches.append({"code": lookup_key, "raw_code": raw_code, "matched_name": name, **entry})
        else:
            matches.append({"code": lookup_key, "raw_code": raw_code, "matched_name": name, "meaning": "Not in the known reference table.", "is_fault": None})
    return matches


def find_keyword_signatures(log_text: str) -> list[dict]:
    lower = log_text.lower()
    found = []
    for kw, entry in KEYWORD_SIGNATURES.items():
        if kw in lower:
            found.append(entry)
    return found
