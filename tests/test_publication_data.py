# SPDX-License-Identifier: MIT
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from emulators.front_panel_python import PanelModel  # noqa: E402


class PublicationDataTests(unittest.TestCase):
    def test_transaction_examples_match_python_front_panel_emulator(self):
        source = json.loads((ROOT / "examples/transactions.json").read_text(encoding="utf-8"))
        for example in source["examples"]:
            panel = PanelModel()
            replies: list[int] = []
            for encoded in example["tx_words"]:
                replies.extend(panel.receive_word(int(encoded, 16)))
            expected = [int(value, 16) for value in example["rx_bytes"]]
            self.assertEqual(replies, expected, example["name"])

    def test_command_csv_is_exact_implemented_set(self):
        with (ROOT / "data/commands.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual({int(row["opcode"], 16) for row in rows}, set(PanelModel.IMPLEMENTED))

    def test_j1102_is_complete_twelve_pin_table(self):
        with (ROOT / "data/j1102_pinout.csv").open(encoding="utf-8", newline="") as stream:
            rows = list(csv.DictReader(stream))
        self.assertEqual([int(row["pin"]) for row in rows], list(range(1, 13)))
        self.assertEqual(rows[3]["net"], "+3.3V_ER")
        self.assertEqual(rows[4]["net"], "+12V_UNREG")

    def test_original_firmware_image_is_bound_to_both_ppc_apps(self):
        source = json.loads((ROOT / "data/original_firmware_update.json").read_text(encoding="utf-8"))
        image = source["firmware_image"]
        self.assertEqual(image["length"], 4162)
        self.assertEqual(image["revision"], "0x0009")
        self.assertEqual(image["sha256"], "55779328f8d9de6675ac3a145f846cfc3f86aaa346136698ef4df31edc15c4dd")
        self.assertEqual({row["model"] for row in source["ppc_embeddings"]}, {"34410A", "34411A"})
        self.assertTrue(all(row["slice_identical"] for row in source["ppc_embeddings"]))
        self.assertEqual([row["target"] for row in source["rom_isp_calls_in_panel_image"]], ["0xFF03", "0xFF03"])

    def test_included_original_firmware_binary_identity(self):
        path = ROOT / "firmware" / "34410A_front_panel_firmware.bin"
        image = path.read_bytes()
        self.assertEqual(len(image), 4162)
        self.assertEqual(
            hashlib.sha256(image).hexdigest(),
            "55779328f8d9de6675ac3a145f846cfc3f86aaa346136698ef4df31edc15c4dd",
        )
        self.assertEqual(image[0x1000:0x100E].hex(), "000960001e010000000000000000")
        self.assertEqual(image.count(b"\x12\xff\x03"), 2)

    def test_original_isp_record_families_are_complete(self):
        source = json.loads((ROOT / "data/original_firmware_update.json").read_text(encoding="utf-8"))
        records = {row["operation"]: row for row in source["records"]}
        self.assertEqual(records["program_data"]["type"], "0x00")
        self.assertEqual(records["read_device_id_1"]["data"], "11")
        self.assertEqual(records["read_device_id_2"]["data"], "12")
        self.assertEqual(records["erase_sector"]["type"], "0x04")
        self.assertEqual(source["data_read_generator"], "stub_returns_zero")


    def test_original_mcu_architecture_and_closure_traces(self):
        mcu = json.loads((ROOT / "data/original_mcu_architecture.json").read_text(encoding="utf-8"))
        self.assertEqual(mcu["image"]["code_range"], "0x0000..0x1041")
        self.assertEqual(mcu["image"]["recovered_function_count"], 71)
        self.assertEqual(mcu["startup"]["xram_cleared_bytes"], 512)
        self.assertEqual(mcu["subsystems"]["uart"]["dispatch_entries"], 64)
        self.assertEqual(mcu["subsystems"]["display"]["cells"], 600)
        self.assertEqual(mcu["subsystems"]["keypad"]["fifo_capacity"], 4)
        self.assertEqual(mcu["subsystems"]["sound"]["tone_reload_pairs"], 85)
        self.assertEqual(mcu["edge_cases"]["display_count_zero_store_count"], 256)
        with (ROOT / "data/original_mcu_function_map.csv").open(encoding="utf-8", newline="") as stream:
            functions = list(csv.DictReader(stream))
        self.assertEqual(len(functions), 71)
        self.assertEqual(len({row["address"] for row in functions}), 71)
        traces = json.loads((ROOT / "derived/original_mcu_trace_results.json").read_text(encoding="utf-8"))
        self.assertEqual({row["name"] for row in traces}, {"startup", "command_21_count_zero", "reply_tb8"})

    def test_protocol_extract_contains_complete_mcu_tables(self):
        source = json.loads((ROOT / "derived/front_panel_protocol_extract.json").read_text(encoding="utf-8"))
        self.assertEqual(source["command_table"]["entry_count"], 64)
        self.assertEqual(source["tone_reload_table"]["entry_count"], 85)
        self.assertEqual([row["pair_count"] for row in source["sound_sequences"]["layouts"]], [13, 8, 24, 31, 37])
        self.assertEqual(len(source["raw_key_to_ppc_event"]["physical_keys"]), 17)

if __name__ == "__main__":
    unittest.main()