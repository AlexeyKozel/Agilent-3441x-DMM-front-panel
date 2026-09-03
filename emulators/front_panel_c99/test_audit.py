"""Deterministic contract and safety-boundary checks for the C99 core.

These checks do not replace sanitizer or target-ABI validation. They inspect
source and independent Python-model boundary cases; test_differential.py
performs executable differential checks.
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path


HERE = Path(__file__).resolve().parent
MODEL_ROOT = HERE.parents[1]
sys.path.insert(0, str(MODEL_ROOT))
from reference_model import PanelModel, raw_to_ppc_event  # noqa: E402


class SourceSafetyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.header = (HERE / "mcu_core.h").read_text(encoding="utf-8")
        cls.source = (HERE / "mcu_core.c").read_text(encoding="utf-8")

    def test_c99_guards_cover_wire_sizes_and_zero_count_buffers(self):
        self.assertIn("fp_mcu_assert_uint8_is_octet", self.source)
        self.assertIn("fp_mcu_assert_uint16_holds_9bit", self.source)
        self.assertIn("FP_MCU_FRAMEBUFFER_BYTES * 4u == FP_MCU_CELL_COUNT", self.source)
        self.assertIn("FP_MCU_STOCK_XRAM_BYTES >= 0x200u", self.source)
        self.assertIn("FP_MCU_MAX_PAYLOAD >= 258u", self.source)

    def test_zero_count_path_uses_bounded_16_bit_address(self):
        self.assertIn("mcu->expected_payload = count == 0 ? 258u", self.source)
        self.assertIn("uint16_t address = (uint16_t)start + (uint16_t)i", self.source)
        self.assertIn("mcu->stock_xram[address]", self.source)
        self.assertIn("if (address < FP_MCU_FRAMEBUFFER_BYTES)", self.source)

    def test_invalid_sequence_is_noop_without_null_callback_payload(self):
        self.assertIn("if (n != 0u && mcu->platform.sound_sequence != NULL)", self.source)

    def test_callbacks_are_null_checked(self):
        self.assertIn("mcu->platform.set_srq_low != NULL", self.source)
        self.assertIn("mcu->platform.reply == NULL", self.source)
        self.assertIn("mcu->platform.sound != NULL", self.source)
        self.assertIn("mcu->platform.sound_sequence != NULL", self.source)

    def test_no_dynamic_allocation_or_unbounded_wire_index(self):
        self.assertNotIn("malloc(", self.source)
        self.assertNotIn("calloc(", self.source)
        self.assertNotIn("realloc(", self.source)
        self.assertNotIn("free(", self.source)
        self.assertIn("if (mcu->payload_len >= FP_MCU_MAX_PAYLOAD)", self.source)
        self.assertIn("if (word > 0x1FFu)", self.source)


class DeterministicModelBoundaryTests(unittest.TestCase):
    def test_zero_count_0x21_reaches_exact_xram_end(self):
        panel = PanelModel()
        packet = [0x21, 0x00, 0xFF] + list(range(256))
        replies = []
        for byte in packet:
            replies.extend(panel.receive(byte))
        self.assertEqual(replies, [0x01])
        self.assertEqual(panel.last_stock_display_write, (0xFF, 256))
        self.assertEqual(panel.stock_xram[0xFF], 0)
        self.assertEqual(panel.stock_xram[0x1FE], 0xFF)

    def test_truncated_payload_status_and_echo_resync(self):
        panel = PanelModel()
        self.assertEqual(panel.receive(0x12), ())
        self.assertEqual(panel.receive(0x05, ninth_bit=True), (0x00,))
        self.assertEqual(panel.status, 0x01)
        self.assertEqual(panel.receive(0x34), ())
        self.assertEqual(panel.receive(0xA5), (0xA5,))
        self.assertEqual(panel.receive(0x05, ninth_bit=True), (0x00,))
        self.assertFalse(panel.echo_mode)

    def test_fifo_ring_irq_gate_and_reset_callback_state(self):
        panel = PanelModel()
        self.assertTrue(panel.srq_low)
        for event in range(4):
            self.assertTrue(panel.enqueue_event(event))
        self.assertFalse(panel.irq_enabled)
        self.assertEqual(panel.fifo_occupancy, 4)
        self.assertEqual(panel.receive(0x38), ())
        self.assertEqual(panel.receive(0x01), (0x01,))
        self.assertTrue(panel.srq_low)
        self.assertEqual(panel.receive(0x15), (0x00,))
        self.assertEqual(panel.receive(0x15), (0x01,))
        self.assertEqual(panel.receive(0x15), (0x02,))
        self.assertEqual(panel.receive(0x15), (0x03,))
        self.assertFalse(panel.srq_low)
        panel.reset()
        self.assertTrue(panel.srq_low)
        self.assertEqual(panel.status, 0x01)

    def test_sound_and_raw_id_boundaries(self):
        panel = PanelModel()
        self.assertEqual(panel.receive(0x12), ())
        self.assertEqual(panel.receive(0xFF), ())
        self.assertEqual(panel.receive(0xFF), (0x01,))
        self.assertEqual(panel.last_sound["duration_selector"], 2)
        self.assertEqual(panel.last_sound["repeat_count"], 252)
        self.assertEqual(panel.last_sound["tone_index"], 0x54)
        self.assertEqual(raw_to_ppc_event(0x3F), 0x3F)
        with self.assertRaises(ValueError):
            raw_to_ppc_event(0xFF)


if __name__ == "__main__":
    unittest.main()
