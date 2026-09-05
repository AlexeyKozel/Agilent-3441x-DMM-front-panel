"""Deterministic model of the original front-panel MCU digital behavior.

The model does not open a UART, model electrical levels, or execute 8051 instructions.
Reply-word APIs expose the confirmed ninth bit explicitly.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Iterable, NamedTuple


ROOT = Path(__file__).resolve().parents[2]
EXTRACT = ROOT / "derived" / "front_panel_protocol_extract.json"

FRAMEBUFFER_BYTES = 150
CELL_COUNT = 600
KEY_FIFO_CAPACITY = 4
REVISION = 0x0009
PANEL_ID = 0x1A


class CellState:
    OFF = 0
    DIM = 1
    FLASH = 2
    FULL = 3


@dataclass(frozen=True)
class Annunciator:
    name: str
    cell: int
    object_id: int


@dataclass(frozen=True)
class KeyEvent:
    raw_id: int
    pressed: bool
    startup_held: bool = False
    ppc_event: int | None = None

    @property
    def value(self) -> int:
        return encode_key_event(self.raw_id, self.pressed, self.startup_held)


class TraceStep(NamedTuple):
    byte: int
    ninth_bit: bool
    replies: tuple[int, ...]
    state: int


class ReplyWord(NamedTuple):
    """One UART reply word with an explicit ninth bit."""

    byte: int
    ninth_bit: bool = False

    @property
    def word(self) -> int:
        """Return the conventional packed nine-bit value (0x000..0x1ff)."""
        return self.byte | (0x100 if self.ninth_bit else 0)


def _load_extract() -> dict:
    with EXTRACT.open(encoding="utf-8") as stream:
        return json.load(stream)


_EXTRACT = _load_extract()
_TABLE = _EXTRACT["raw_key_to_ppc_event"]
_RAW_EVENTS = tuple(_TABLE["events_by_raw_id_0x00_through_0x14"])

ANNUNCIATORS: dict[str, Annunciator] = {}
for _entry in _EXTRACT["display_object_map"]["entries"]:
    if _entry.get("name") is not None:
        _name = str(_entry["name"])
        ANNUNCIATORS[_name] = Annunciator(
            _name, int(_entry["cell"]), int(_entry["object_id"], 0)
        )

TONE_RELOAD_TABLE: tuple[tuple[int, int], ...] = tuple(
    (int(x["reload_hi"], 0), int(x["reload_lo"], 0))
    for x in _EXTRACT["tone_reload_table"]["pairs"]
)
SOUND_SEQUENCES: dict[int, tuple[tuple[int, int], ...]] = {
    int(key): tuple(
        (int(pair["duration_selector"], 0), int(pair["tone_index"], 0))
        for pair in value
    )
    for key, value in _EXTRACT["sound_sequences"]["pairs"].items()
}


def raw_to_ppc_event(raw_id: int) -> int | None:
    """Return the PPC event for a RAW ID, or ``None`` for unused table slots."""
    if not isinstance(raw_id, int) or not 0 <= raw_id <= 0x3F:
        raise ValueError("raw_id must be an integer in 0..0x3f")
    if raw_id == 0x3F:
        return 0x3F
    if raw_id > 0x14:
        return None
    value = _RAW_EVENTS[raw_id]
    return value or None


def encode_key_event(raw_id: int, pressed: bool, startup_held: bool = False) -> int:
    """Encode the 8051 FIFO event byte."""
    if not isinstance(raw_id, int) or not 0 <= raw_id <= 0x3F:
        raise ValueError("raw_id must be an integer in 0..0x3f")
    if startup_held and not pressed:
        raise ValueError("startup_held is meaningful only on a press")
    return (0x80 if startup_held else 0) | (0x40 if pressed else 0) | raw_id


def decode_key_event(value: int) -> KeyEvent:
    """Decode one FIFO byte and attach the PPC table translation."""
    if not isinstance(value, int) or not 0 <= value <= 0xFF:
        raise ValueError("event must be a byte")
    raw_id = value & 0x3F
    pressed = bool(value & 0x40)
    startup_held = bool(value & 0x80)
    if not pressed:
        startup_held = False
    return KeyEvent(raw_id, pressed, startup_held, raw_to_ppc_event(raw_id))


class PanelModel:
    """Reference state machine for the application-layer panel protocol."""

    IMPLEMENTED = {
        0x01: ("get_revision", 0), 0x03: ("get_id", 0),
        0x05: ("get_status", 0), 0x12: ("generate_sound", 2),
        0x13: ("beep", 0), 0x14: ("click", 0),
        0x15: ("dequeue_key_event", 0), 0x21: ("write_display", None),
        0x31: ("play_sound_sequence", 1), 0x32: ("enable_break_detect", 0),
        0x33: ("disable_break_detect", 0), 0x34: ("protocol_echo", None),
        0x36: ("diagnostic_key_traffic", 1), 0x38: ("set_key_irq_enable", 1),
        0x3A: ("flush_key_fifo", 0),
    }

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        # The table-driven initializer runs after RAM clear: CODE:0500
        # fills XRAM:0000..0095 with FF and CODE:05B9 enables key IRQ.
        self.framebuffer = bytearray([0xFF]) * FRAMEBUFFER_BYTES
        # Every 0x21 write targets XRAM directly, including spans outside
        # the framebuffer. The largest start/count reaches address 0x01fe.
        self.stock_xram = bytearray(0x200)
        self.stock_xram[:FRAMEBUFFER_BYTES] = self.framebuffer
        # The later startup routine at CODE:0EED initializes keypad state.
        self.stock_xram[0x96:0xAA] = bytes([0x82]) * 20
        self.key_fifo: list[int] = []
        self.state = 0x01
        self.command: int | None = None
        self.payload = bytearray()
        self.expected_payload: int | None = None
        self._status_previous = 0x01
        self.echo_mode = False
        self.irq_enabled = True
        # Reset startup calls 0x0EED, which explicitly clears P1.6.
        self.srq_low = True
        self.break_detect_enabled = False
        self.diagnostic_key_traffic = False
        self.diagnostic_counter = 0
        self.diagnostic_key_id = 0
        self.main_loop_count = 0
        self.last_sound: dict[str, object] | None = None
        self.last_sequence: tuple[tuple[int, int], ...] = ()
        self.last_stock_display_write: tuple[int, int] | None = None

    @property
    def fifo_occupancy(self) -> int:
        return len(self.key_fifo)

    @property
    def status(self) -> int:
        return self.state

    def _set_srq_for_fifo(self) -> None:
        if self.irq_enabled:
            self.srq_low = bool(self.key_fifo)
        else:
            self.srq_low = False

    def enqueue_event(self, event: int) -> bool:
        if not 0 <= event <= 0xFF:
            raise ValueError("event must be a byte")
        if len(self.key_fifo) >= KEY_FIFO_CAPACITY:
            return False
        self.key_fifo.append(event)
        # The 8051 enqueue path only drives P1.6 low when key IRQ signaling
        # is enabled; with IRQ disabled it leaves the startup/output level
        # untouched (see FUN_CODE_0E06 in the direct replay).
        if self.irq_enabled:
            self._set_srq_for_fifo()
        return True

    def enqueue_key(self, raw_id: int, pressed: bool, startup_held: bool = False) -> bool:
        return self.enqueue_event(encode_key_event(raw_id, pressed, startup_held))

    def tick(self, iterations: int = 1) -> tuple[int, ...]:
        """Advance deterministic main-loop iterations and emit diagnostic events."""
        if iterations < 0:
            raise ValueError("iterations must be non-negative")
        emitted: list[int] = []
        for _ in range(iterations):
            self.main_loop_count += 1
            previous = self.diagnostic_counter
            if previous == 0:
                continue
            # CODE:0A74..0A84 compares the old IRAM:43 value, then resets
            # it to 1 after an event pair. Disabled passes do not count.
            self.diagnostic_counter = (previous + 1) & 0xFF
            if previous >= 30:
                key = self.diagnostic_key_id % 20
                for event in (encode_key_event(key, True), encode_key_event(key, False)):
                    if self.enqueue_event(event):
                        emitted.append(event)
                self.diagnostic_key_id = (self.diagnostic_key_id + 1) % 20
                self.diagnostic_counter = 1
        return tuple(emitted)

    def cell(self, index: int) -> int:
        if not 0 <= index < CELL_COUNT:
            raise IndexError("cell index must be in 0..599")
        byte_index, shift = index >> 2, 6 - 2 * (index & 3)
        return (self.framebuffer[byte_index] >> shift) & 0x03

    def set_cell(self, index: int, value: int) -> None:
        if not 0 <= index < CELL_COUNT or not 0 <= value <= 3:
            raise ValueError("cell must be 0..599 and value must be 0..3")
        byte_index, shift = index >> 2, 6 - 2 * (index & 3)
        self.framebuffer[byte_index] = (
            self.framebuffer[byte_index] & ~(0x03 << shift)
        ) | (value << shift)
        self.stock_xram[byte_index] = self.framebuffer[byte_index]

    def write_display(self, start: int, data: Iterable[int]) -> None:
        values = bytes(data)
        if not 0 <= start < FRAMEBUFFER_BYTES or not values:
            raise ValueError("display write must be a non-empty in-range span")
        if start + len(values) > FRAMEBUFFER_BYTES:
            raise ValueError("display write exceeds 150-byte framebuffer")
        self.framebuffer[start:start + len(values)] = values
        self.stock_xram[start:start + len(values)] = values

    def annunciator_cell(self, name: str) -> int:
        try:
            return ANNUNCIATORS[name].cell
        except KeyError as exc:
            raise KeyError(f"unknown annunciator: {name}") from exc

    def character_cell(self, row: str, position: int, segment: int) -> int:
        if row not in ("main", "secondary"):
            raise ValueError("row must be 'main' or 'secondary'")
        limit = 12 if row == "main" else 18
        if not 0 <= position < limit or not 0 <= segment < 17:
            raise ValueError("character position/segment out of range")
        base = 5 if row == "main" else 245
        return base + 40 * (position // 2) + (position & 1) + 2 * segment

    def _complete(self, reply: Iterable[int], state: int = 0x01) -> list[int]:
        self.state = state
        self.command = None
        self.payload.clear()
        self.expected_payload = None
        self.echo_mode = False
        return list(reply)

    def _reject(self) -> list[int]:
        return self._complete((0x81,), 0x81)

    def _start_command(self, command: int) -> list[int]:
        previous_state = self.state
        self.state = 0x00
        self.command = command
        self.payload.clear()
        self.echo_mode = False
        self._status_previous = previous_state
        if command not in self.IMPLEMENTED:
            return self._reject()
        name, count = self.IMPLEMENTED[command]
        if command == 0x34:
            self.echo_mode = True
            return []
        if count == 0:
            return self._handle_payload()
        self.expected_payload = count
        return []

    def _handle_payload(self) -> list[int]:
        command, payload = self.command, bytes(self.payload)
        if command == 0x01:
            return self._complete((REVISION >> 8, REVISION & 0xFF))
        if command == 0x03:
            return self._complete((PANEL_ID,))
        if command == 0x05:
            previous = self._status_previous
            return self._complete((previous,))
        if command == 0x12:
            duration, tone = payload
            active = min(duration, 2)
            repeat = duration - 3 if duration >= 3 else 0
            tone = min(tone, 0x54)
            self.last_sound = {
                "duration_selector": active, "repeat_count": repeat,
                "tone_index": tone, "reload": TONE_RELOAD_TABLE[tone],
            }
            return self._complete((0x01,))
        if command in (0x13, 0x14):
            self.last_sound = {"kind": "beep" if command == 0x13 else "click"}
            return self._complete((0x01,))
        if command == 0x15:
            if self.key_fifo:
                event = self.key_fifo.pop(0)
                self._set_srq_for_fifo()
                return self._complete((event,), 0x01)
            self.srq_low = False
            return self._complete((0xFF,), 0x81)
        if command == 0x21:
            # Data bytes have already been stored by the receive path.
            return self._complete((0x01,))
        if command == 0x31:
            sequence_id = payload[0]
            self.last_sequence = SOUND_SEQUENCES.get(sequence_id, ())
            return self._complete((0x01,))
        if command == 0x32:
            self.break_detect_enabled = True
            return self._complete((0x01,))
        if command == 0x33:
            self.break_detect_enabled = False
            return self._complete((0x01,))
        if command == 0x36:
            # CODE:0E85 stores the raw payload byte in IRAM:43.
            self.diagnostic_counter = payload[0]
            self.diagnostic_key_traffic = self.diagnostic_counter != 0
            return self._complete((0x01,))
        if command == 0x38:
            self.irq_enabled = payload[0] != 0
            self._set_srq_for_fifo()
            return self._complete((0x01,))
        if command == 0x3A:
            self.key_fifo.clear()
            self.srq_low = False
            return self._complete((0x01,))
        return self._reject()

    def receive(self, byte: int, ninth_bit: bool = False) -> tuple[int, ...]:
        """Consume one 9-bit UART word and return immediate reply bytes."""
        if not isinstance(byte, int) or not 0 <= byte <= 0xFF:
            raise ValueError("byte must be in 0..255")
        if ninth_bit:
            return tuple(self._start_command(byte))
        if self.echo_mode:
            return (byte,)
        if self.command is None:
            return tuple(self._start_command(byte))
        self.payload.append(byte)
        if self.command == 0x21:
            if len(self.payload) == 1:
                # DJNZ decrements zero to FF, so count=0 consumes 256 bytes.
                self.expected_payload = (self.payload[0] or 0x100) + 2
            elif len(self.payload) == 2:
                self.last_stock_display_write = (self.payload[1], 0)
            else:
                start = self.payload[1]
                offset = len(self.payload) - 3
                address = start + offset
                # CODE:067D executes MOVX for every received data byte,
                # before DJNZ decides whether to acknowledge completion.
                # A later CMMD abandons parsing, never these prior stores.
                self.stock_xram[address] = byte
                if address < FRAMEBUFFER_BYTES:
                    self.framebuffer[address] = byte
                self.last_stock_display_write = (start, offset + 1)
        if self.expected_payload is not None and len(self.payload) >= self.expected_payload:
            return tuple(self._handle_payload())
        return ()

    def receive_word(self, word: int) -> tuple[int, ...]:
        if not isinstance(word, int) or not 0 <= word <= 0x1FF:
            raise ValueError("word must be a 9-bit integer")
        return self.receive(word & 0xFF, bool(word & 0x100))

    def receive_reply_words(self, byte: int, ninth_bit: bool = False) -> tuple[ReplyWord, ...]:
        """Consume one input word and return explicit nine-bit reply words.

        Stock startup clears TB8 and the image never sets it, so every emitted
        reply has ``ninth_bit=False``.  ``receive`` remains byte-only for
        existing callers.
        """
        return tuple(ReplyWord(reply, False) for reply in self.receive(byte, ninth_bit))

    def receive_word_reply_words(self, word: int) -> tuple[ReplyWord, ...]:
        """Nine-bit input counterpart of :meth:`receive_reply_words`."""
        if not isinstance(word, int) or not 0 <= word <= 0x1FF:
            raise ValueError("word must be a 9-bit integer")
        return self.receive_reply_words(word & 0xFF, bool(word & 0x100))

    def status_query(self) -> int:
        """Issue the normal CMMD ``0x05`` resynchronization query."""
        reply = self.receive(0x05, ninth_bit=True)
        if len(reply) != 1:
            raise RuntimeError("GET_STATUS did not return one byte")
        return reply[0]

    def exchange(self, packet: Iterable[int], command_ninth_bit: bool = False) -> tuple[int, ...]:
        """Send a complete packet and append the stock CMMD status query."""
        values = list(packet)
        if not values:
            raise ValueError("packet cannot be empty")
        replies: list[int] = []
        for index, value in enumerate(values):
            replies.extend(self.receive(value, ninth_bit=command_ninth_bit and index == 0))
        replies.append(self.status_query())
        return tuple(replies)

    def trace(self, words: Iterable[tuple[int, bool] | int]) -> tuple[TraceStep, ...]:
        result: list[TraceStep] = []
        for item in words:
            if isinstance(item, tuple):
                byte, ninth = item
                replies = self.receive(byte, ninth)
            else:
                byte, ninth = item & 0xFF, bool(item & 0x100)
                replies = self.receive_word(item)
            result.append(TraceStep(byte, ninth, tuple(replies), self.state))
        return tuple(result)
