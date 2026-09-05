"""Optional firmware-backed regressions; never substitute synthetic firmware."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from emulators.front_panel_python import PanelModel
from tools.firmware_oracle import (
    FirmwareOracle, firmware_from_environment, validate_image,
)


class FirmwareInputTests(unittest.TestCase):
    def test_optional_missing_firmware_is_explicitly_unavailable(self):
        with patch.dict(os.environ, {}, clear=True):
            self.assertIsNone(firmware_from_environment())

    def test_required_missing_firmware_fails(self):
        with patch.dict(os.environ, {"FP_REQUIRE_ORIGINAL_FIRMWARE": "1"}, clear=True):
            with self.assertRaisesRegex(ValueError, "requires FP_ORIGINAL_FIRMWARE"):
                firmware_from_environment()

    def test_invalid_firmware_is_rejected_without_assert_dependency(self):
        for image in (b"", b"\x00" * 4162):
            with self.subTest(length=len(image)), self.assertRaisesRegex(ValueError, "SHA-256"):
                validate_image(image)

    def test_supplied_bad_image_is_an_error_even_when_optional(self):
        with patch.dict(os.environ, {"FP_ORIGINAL_FIRMWARE": "external-image.bin"}, clear=True):
            with patch.object(Path, "read_bytes", return_value=b"\x00" * 4162):
                with self.assertRaisesRegex(ValueError, "SHA-256"):
                    firmware_from_environment()


class OriginalFirmwareRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        image = firmware_from_environment()
        if image is None:
            raise unittest.SkipTest(
                "Original firmware not redistributed: set FP_ORIGINAL_FIRMWARE for opcode-backed regressions"
            )
        cls.oracle = FirmwareOracle(image)

    def test_reset_matches_executed_firmware_initializers(self):
        actual = self.oracle.startup()
        model = PanelModel()
        self.assertEqual(model.irq_enabled, actual.irq_enabled)
        self.assertEqual(model.srq_low, actual.srq_low)
        self.assertEqual(model.state, actual.state)
        self.assertEqual(model.framebuffer, actual.xram[:150])
        self.assertEqual(model.stock_xram, actual.xram)

    def _display_case(self, count, start, payload, resync=False):
        original = self.oracle.runtime()
        model = PanelModel()
        original.display_begin(count, start)
        header_replies = []
        for byte in (0x21, count, start):
            header_replies.extend(model.receive(byte))
        self.assertEqual(header_replies, original.replies)
        self.assertEqual(model.state, original.state)
        for index, byte in enumerate(payload):
            with self.subTest(count=count, start=start, payload_index=index):
                self.assertEqual(model.receive(byte), original.display_byte(byte))
                self.assertEqual(model.state, original.state)
                self.assertEqual(model.stock_xram, original.xram)
                self.assertEqual(model.framebuffer, original.xram[:150])
        if resync:
            self.assertEqual(model.status_query(), original.status_resync())
            self.assertEqual(model.state, original.state)
            self.assertEqual(model.stock_xram, original.xram)
            self.assertEqual(model.framebuffer, original.xram[:150])

    def test_partial_valid_write_survives_resync(self):
        self._display_case(3, 0, [0xaa], resync=True)

    def test_partial_zero_count_write_survives_resync(self):
        self._display_case(0, 0x20, [0xa5, 0x5a], resync=True)

    def test_complete_display_boundary_span(self):
        self._display_case(2, 148, [0xab, 0xcd])

    def test_nonzero_write_crosses_framebuffer_boundary(self):
        self._display_case(2, 149, [0xaa, 0xbb])

    def test_maximum_nonzero_count_and_start(self):
        self._display_case(255, 255, range(255))

    def test_zero_count_consumes_256_bytes_at_maximum_start(self):
        self._display_case(0, 255, range(256))

    def test_diagnostic_counter_and_fifo_match_executed_windows(self):
        for disabled_ticks, enable, ticks in (
            (29, 1, 1), (0, 30, 1), (0, 255, 1), (0, 1, 65), (17, 0, 100),
        ):
            with self.subTest(disabled_ticks=disabled_ticks, enable=enable, ticks=ticks):
                original = self.oracle.runtime()
                model = PanelModel()
                self.assertEqual(model.tick(disabled_ticks), original.diagnostic_tick(disabled_ticks))
                model.receive(0x36)
                original.diagnostic_enable(enable)
                self.assertEqual(model.receive(enable), tuple(original.replies))
                self.assertEqual(model.diagnostic_counter, original.iram[0x43])
                for _ in range(ticks):
                    self.assertEqual(model.tick(), original.diagnostic_tick())
                    self.assertEqual(model.diagnostic_counter, original.iram[0x43])
                    read, write = original.iram[0x35], original.iram[0x34]
                    occupancy = (write-read) & 255
                    expected_fifo = [original.iram[0x30+((read+n)&3)] for n in range(occupancy)]
                    self.assertEqual(model.key_fifo, expected_fifo)
                    self.assertEqual(model.srq_low, original.srq_low)


if __name__ == "__main__":
    unittest.main()
