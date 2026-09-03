from __future__ import annotations

import json
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from emulators.front_panel_python import (  # noqa: E402
    ANNUNCIATORS,
    CellState,
    PanelModel,
    decode_key_event,
    encode_key_event,
    raw_to_ppc_event,
)
from emulators.front_panel_python.model import ReplyWord  # noqa: E402


class FrontPanelPythonEmulatorTests(unittest.TestCase):
    def test_reset_startup_irq_disabled_srq_low_and_empty_dequeue(self):
        panel = PanelModel()
        self.assertFalse(panel.irq_enabled)
        self.assertTrue(panel.srq_low)
        self.assertEqual(panel.receive(0x15), (0xFF,))
        self.assertEqual(panel.status, 0x81)
        self.assertEqual(panel.receive(0x05, ninth_bit=True), (0x81,))
        self.assertFalse(panel.srq_low)
        self.assertEqual(panel.status, 0x01)

    def test_status_idle_and_partial_resynchronization(self):
        panel = PanelModel()
        self.assertEqual(panel.status_query(), 0x01)
        self.assertEqual(panel.receive(0x12), ())
        self.assertEqual(panel.status_query(), 0x00)
        self.assertEqual(panel.status, 0x01)

    def test_ninth_bit_forces_dispatch_from_every_parser_state(self):
        panel = PanelModel()
        # A DATA byte is payload while GENERATE_SOUND is incomplete.
        self.assertEqual(panel.receive(0x12), ())
        self.assertEqual(panel.status, 0x00)
        self.assertEqual(panel.receive(0x05, ninth_bit=True), (0x00,))
        self.assertEqual(panel.status, 0x01)
        # The same CMMD rule also abandons an incomplete variable display write.
        self.assertEqual(panel.receive(0x21), ())
        self.assertEqual(panel.receive(0x02), ())
        self.assertEqual(panel.receive(0x05, ninth_bit=True), (0x00,))
        self.assertEqual(panel.status, 0x01)

    def test_parser_state_transitions_success_reject_and_resync(self):
        panel = PanelModel()
        self.assertEqual(panel.status, 0x01)
        self.assertEqual(panel.receive(0x12), ())
        self.assertEqual(panel.status, 0x00)
        self.assertEqual(panel.receive(0x01), ())
        self.assertEqual(panel.receive(0x02), (0x01,))
        self.assertEqual(panel.status, 0x01)
        self.assertEqual(panel.receive(0x40), (0x81,))
        self.assertEqual(panel.status, 0x81)
        self.assertEqual(panel.status_query(), 0x81)
        self.assertEqual(panel.status, 0x01)

    def test_all_unknown_opcodes_reject(self):
        implemented = set(PanelModel.IMPLEMENTED)
        for opcode in range(0x100):
            panel = PanelModel()
            replies = panel.receive(opcode & 0xFF, ninth_bit=opcode >= 0x100)
            # All ordinary opcodes are one-byte commands; >=0x40 is rejected.
            if (opcode & 0xFF) not in implemented:
                self.assertEqual(replies, (0x81,), hex(opcode))
                self.assertEqual(panel.status, 0x81)

    def test_command_round_trips(self):
        cases = [
            ([0x01], (0x00, 0x09, 0x01)),
            ([0x03], (0x1A, 0x01)),
            ([0x12, 0x05, 0x54], (0x01, 0x01)),
            ([0x13], (0x01, 0x01)),
            ([0x14], (0x01, 0x01)),
            ([0x31, 0x01], (0x01, 0x01)),
            ([0x32], (0x01, 0x01)),
            ([0x33], (0x01, 0x01)),
            ([0x36, 0x01], (0x01, 0x01)),
            ([0x38, 0x01], (0x01, 0x01)),
            ([0x3A], (0x01, 0x01)),
        ]
        for packet, expected in cases:
            with self.subTest(packet=packet):
                self.assertEqual(PanelModel().exchange(packet), expected)

    def test_display_round_trip_boundaries_and_2bit_cells(self):
        panel = PanelModel()
        self.assertEqual(panel.exchange([0x21, 0x01, 0x95, 0xA5]), (0x01, 0x01))
        self.assertEqual(panel.framebuffer[0x95], 0xA5)
        for index in range(600):
            panel.set_cell(index, index & 3)
            self.assertEqual(panel.cell(index), index & 3)
        self.assertEqual(panel.cell(0), CellState.OFF)
        self.assertEqual(panel.cell(1), CellState.DIM)
        self.assertEqual(panel.cell(2), CellState.FLASH)
        self.assertEqual(panel.cell(3), CellState.FULL)

    def test_display_zero_count_replays_stock_256_byte_xram_write(self):
        panel = PanelModel()
        self.assertEqual(panel.receive(0x21), ())
        self.assertEqual(panel.receive(0x00), ())
        self.assertEqual(panel.status, 0x00)
        self.assertEqual(panel.receive(0xFF), ())
        payload = bytes(range(0x100))
        for value in payload[:-1]:
            self.assertEqual(panel.receive(value), ())
        self.assertEqual(panel.receive(payload[-1]), (0x01,))
        self.assertEqual(panel.status, 0x01)
        self.assertEqual(panel.last_stock_display_write, (0xFF, 0x100))
        self.assertEqual(panel.stock_xram[0xFF:0x1FF], payload)

    def test_display_zero_count_truncated_stream_stays_busy_until_cmmd(self):
        panel = PanelModel()
        for value in (0x21, 0x00, 0x20, 0xA5):
            self.assertEqual(panel.receive(value), ())
        self.assertEqual(panel.status, 0x00)
        self.assertEqual(panel.status_query(), 0x00)
        self.assertEqual(panel.status, 0x01)

    def test_reply_word_api_makes_stock_tb8_zero_explicit(self):
        panel = PanelModel()
        self.assertEqual(
            panel.receive_reply_words(0x01, ninth_bit=True),
            (ReplyWord(0x00, False), ReplyWord(0x09, False)),
        )
        # Existing byte-only callers retain their exact public return type.
        self.assertEqual(panel.receive(0x03, ninth_bit=True), (0x1A,))
        self.assertEqual(
            PanelModel().receive_word_reply_words(0x103),
            (ReplyWord(0x1A, False),),
        )

    def test_display_invalid_nonzero_span_is_model_rejection(self):
        panel = PanelModel()
        panel.reset()
        self.assertEqual(panel.exchange([0x21, 0x02, 0x95, 0xAA, 0xBB]), (0x81, 0x81))

    def test_display_variable_length_boundaries_and_invalid_spans(self):
        panel = PanelModel()
        self.assertEqual(panel.exchange([0x21, 0x01, 0x00, 0xA5]), (0x01, 0x01))
        self.assertEqual(panel.framebuffer[0], 0xA5)
        self.assertEqual(panel.exchange([0x21, 0x02, 0x94, 0x11, 0x22]), (0x01, 0x01))
        self.assertEqual(bytes(panel.framebuffer[0x94:0x96]), b"\x11\x22")
        for packet in ([0x21, 0x01, 0x96, 0xAA], [0x21, 0x02, 0x95, 0xAA, 0xBB]):
            with self.subTest(packet=packet):
                self.assertEqual(PanelModel().exchange(packet), (0x81, 0x81))

    def test_echo_stream_and_cmmd_exit(self):
        panel = PanelModel()
        self.assertEqual(panel.receive(0x34), ())
        self.assertEqual(panel.receive(0xA5), (0xA5,))
        self.assertEqual(panel.receive(0x05, ninth_bit=True), (0x00,))
        self.assertFalse(panel.echo_mode)

    def test_echo_keeps_state_zero_until_cmmd_exit(self):
        panel = PanelModel()
        self.assertEqual(panel.receive(0x34), ())
        self.assertEqual(panel.status, 0x00)
        self.assertEqual(panel.receive(0x00), (0x00,))
        self.assertEqual(panel.status, 0x00)
        self.assertEqual(panel.receive(0x05, ninth_bit=True), (0x00,))
        self.assertEqual(panel.status, 0x01)

    def test_fifo_overflow_irq_and_startup_bit7(self):
        panel = PanelModel()
        self.assertTrue(panel.enqueue_key(2, True, startup_held=True))
        self.assertEqual(panel.key_fifo[0], 0xC2)
        self.assertTrue(panel.srq_low)  # IRQ disabled leaves startup level unchanged.
        self.assertEqual(panel.exchange([0x38, 0x01]), (0x01, 0x01))
        self.assertTrue(panel.srq_low)
        for raw in (3, 4, 5):
            self.assertTrue(panel.enqueue_key(raw, True))
        self.assertFalse(panel.enqueue_key(6, True))
        self.assertEqual(panel.fifo_occupancy, 4)
        self.assertEqual(decode_key_event(panel.key_fifo[0]).startup_held, True)
        self.assertEqual(panel.receive(0x15), (0xC2,))

    def test_fifo_irq_transitions_and_flush(self):
        panel = PanelModel()
        self.assertTrue(panel.srq_low)  # reset-startup phase; see the MCU-internals evidence
        panel.enqueue_key(1, True)
        self.assertTrue(panel.srq_low)  # IRQ remains disabled
        self.assertEqual(panel.exchange([0x38, 0x01]), (0x01, 0x01))
        self.assertTrue(panel.srq_low)
        self.assertEqual(panel.receive(0x15), (0x41,))
        self.assertFalse(panel.srq_low)
        self.assertEqual(panel.exchange([0x3A]), (0x01, 0x01))
        self.assertFalse(panel.srq_low)
        self.assertEqual(panel.exchange([0x38, 0x00]), (0x01, 0x01))
        self.assertFalse(panel.srq_low)

    def test_sound_selector_and_tone_bounds(self):
        panel = PanelModel()
        self.assertEqual(panel.exchange([0x12, 0x02, 0x00]), (0x01, 0x01))
        self.assertEqual(panel.last_sound["duration_selector"], 2)
        self.assertEqual(panel.last_sound["repeat_count"], 0)
        self.assertEqual(panel.last_sound["tone_index"], 0)
        self.assertEqual(panel.exchange([0x12, 0xFF, 0xFF]), (0x01, 0x01))
        self.assertEqual(panel.last_sound["duration_selector"], 2)
        self.assertEqual(panel.last_sound["repeat_count"], 252)
        self.assertEqual(panel.last_sound["tone_index"], 0x54)

    def test_raw_mapping_and_round_trip(self):
        expected = {0x00: 0x04, 0x01: 0x06, 0x02: 0x1A, 0x03: 0x10,
                    0x04: 0x0E, 0x05: 0x08, 0x06: 0x0B, 0x07: 0x15,
                    0x08: 0x11, 0x09: 0x0D, 0x0A: 0x05, 0x0B: 0x13,
                    0x0C: 0x0C, 0x0D: 0x0F, 0x0F: 0x09, 0x10: 0x19,
                    0x11: 0x0A, 0x14: 0x3F, 0x3F: 0x3F}
        for raw, event in expected.items():
            self.assertEqual(raw_to_ppc_event(raw), event)
        for raw in (0x0E, 0x12, 0x13):
            self.assertIsNone(raw_to_ppc_event(raw))
        for raw in range(20):
            encoded = encode_key_event(raw, True, startup_held=True)
            decoded = decode_key_event(encoded)
            self.assertEqual(decoded.raw_id, raw)
            self.assertTrue(decoded.pressed)
            self.assertTrue(decoded.startup_held)

    def test_annunciators_and_character_cells(self):
        self.assertEqual(len(ANNUNCIATORS), 19)
        self.assertEqual(ANNUNCIATORS["HI_Z"].cell, 0)
        self.assertEqual(ANNUNCIATORS["RIGHT"].cell, 599)
        panel = PanelModel()
        self.assertEqual(panel.character_cell("main", 0, 0), 5)
        self.assertEqual(panel.character_cell("secondary", 17, 16), 598)

    def test_deterministic_fixture_trace(self):
        fixture = ROOT / "emulators" / "front_panel_python" / "fixtures" / "traces.json"
        data = json.loads(fixture.read_text(encoding="utf-8"))
        panel = PanelModel()
        words = [int(word, 16) for word in data["echo_resync"]["words"]]
        trace = panel.trace(words)
        replies = [value for step in trace for value in step.replies]
        self.assertEqual(replies, [int(value, 16) for value in data["echo_resync"]["replies"]])


if __name__ == "__main__":
    unittest.main()
