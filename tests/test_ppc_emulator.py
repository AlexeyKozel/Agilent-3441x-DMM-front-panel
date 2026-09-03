# SPDX-License-Identifier: MIT
from __future__ import annotations

from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from emulators.ppc_host import PpcHostEmulator, PpcProtocolError  # noqa: E402
from reference_model import PanelModel  # noqa: E402


class RecordingEndpoint:
    def __init__(self):
        self.panel = PanelModel()
        self.words: list[int] = []

    def receive_word(self, word: int) -> tuple[int, ...]:
        self.words.append(word)
        return self.panel.receive_word(word)


class PpcHostEmulatorTests(unittest.TestCase):
    def setUp(self):
        self.endpoint = RecordingEndpoint()
        self.host = PpcHostEmulator(self.endpoint)

    def test_revision_and_stock_ninth_bit_pattern(self):
        self.assertEqual(self.host.get_revision(), 0x0009)
        self.assertEqual(self.endpoint.words, [0x001, 0x105])

    def test_unknown_command_is_rejected_by_status_mask(self):
        result = self.host.transact((0x40,))
        self.assertEqual(result.immediate_reply, (0x81,))
        self.assertEqual(result.status, 0x81)
        self.assertFalse(result.success)

    def test_incomplete_payload_is_detected_and_can_be_resynchronized(self):
        with self.assertRaises(PpcProtocolError):
            self.host.transact((0x12,))
        self.assertEqual(self.host.status_query(), 0x00)
        self.assertEqual(self.endpoint.panel.status, 0x01)

    def test_echo_stream_and_cmmd_exit(self):
        result = self.host.echo((0x00, 0xA5, 0xFF))
        self.assertEqual(result.echoed, (0x00, 0xA5, 0xFF))
        self.assertEqual(result.exit_status, 0x00)
        self.assertEqual(self.endpoint.words, [0x034, 0x000, 0x0A5, 0x0FF, 0x105])

    def test_display_span_and_bounds(self):
        result = self.host.write_display(0x94, b"\x11\x22")
        self.assertTrue(result.success)
        self.assertEqual(bytes(self.endpoint.panel.framebuffer[0x94:0x96]), b"\x11\x22")
        for start, data in ((0, b""), (0x96, b"\x00"), (0x95, b"\x00\x01")):
            with self.subTest(start=start, data=data), self.assertRaises(ValueError):
                self.host.write_display(start, data)

    def test_empty_key_dequeue_preserves_original_failure_semantics(self):
        result = self.host.dequeue_key_event()
        self.assertEqual(result.immediate_reply, (0xFF,))
        self.assertEqual(result.status, 0x81)
        self.assertFalse(result.success)

    def test_key_irq_control_and_fifo(self):
        self.endpoint.panel.enqueue_key(2, True, startup_held=True)
        self.assertTrue(self.host.set_key_irq_enabled(True).success)
        self.assertTrue(self.endpoint.panel.srq_low)
        result = self.host.dequeue_key_event()
        self.assertEqual(result.immediate_reply, (0xC2,))
        self.assertTrue(result.success)
        self.assertFalse(self.endpoint.panel.srq_low)

    def test_direct_status_and_echo_commands_are_not_ambiguous(self):
        with self.assertRaises(ValueError):
            self.host.transact((0x05,))
        with self.assertRaises(ValueError):
            self.host.transact((0x34,))


if __name__ == "__main__":
    unittest.main()
