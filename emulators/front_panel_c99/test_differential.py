"""C/reference_model differential checks for deterministic 9-bit traces.

The compiler can be selected explicitly with ``FP_C_COMPILER`` (as used for
the reproducible TinyCC host check).  If no compiler is available, only the
source-level checks run and the executable differential class is skipped; the
test never downloads dependencies or touches hardware.
"""

from __future__ import annotations

import random
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
MODEL_ROOT = HERE.parents[1]
sys.path.insert(0, str(MODEL_ROOT))
from reference_model import PanelModel  # noqa: E402


def _compiler() -> str | None:
    configured = os.environ.get("FP_C_COMPILER")
    if configured:
        candidate = Path(configured)
        if candidate.is_file():
            return str(candidate)
    for name in ("cc", "gcc", "clang", "cl", "tcc"):
        found = shutil.which(name)
        if found:
            return found
    return None


def _model_trace(words: list[int]) -> list[tuple[int, int, list[tuple[int, int]]]]:
    model = PanelModel()
    result = []
    for word in words:
        replies = model.receive_word_reply_words(word)
        result.append((model.status, int(model.srq_low),
                       [(reply.byte, int(reply.ninth_bit)) for reply in replies]))
    return result


class SourceContractTests(unittest.TestCase):
    def test_core_is_target_neutral_and_has_required_surface(self):
        header = (HERE / "mcu_core.h").read_text(encoding="utf-8")
        source = (HERE / "mcu_core.c").read_text(encoding="utf-8")
        for symbol in (
            "fp_mcu_receive", "fp_mcu_receive_word", "fp_mcu_tick",
            "fp_mcu_enqueue_event", "fp_mcu_set_cell", "fp_mcu_raw_to_ppc_event",
            "fp_mcu_sequence", "fp_mcu_tone_reload",
        ):
            self.assertIn(symbol, header)
            self.assertIn(symbol, source)
        self.assertIn("FP_MCU_FRAMEBUFFER_BYTES 150u", header)
        self.assertIn("FP_MCU_CELL_COUNT 600u", header)
        self.assertIn("FP_MCU_KEY_FIFO_CAPACITY 4u", header)
        self.assertIn("mcu->srq_low = true", source)
        self.assertIn("word.ninth_bit = false", source)
        self.assertNotIn("malloc(", source)
        self.assertNotIn("UART", source)

    def test_deterministic_vectors_are_defined(self):
        self.assertEqual(_model_trace([0x101]), [(1, 1, [(0, 0), (9, 0)])])
        self.assertEqual(_model_trace([0x34, 0xA5, 0x105]), [
            (0, 1, []), (0, 1, [(0xA5, 0)]), (1, 1, [(0, 0)])
        ])


class DifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = _compiler()
        if compiler is None:
            raise unittest.SkipTest("C99 compiler is unavailable; source checks remain active")
        cls.tmp = tempfile.TemporaryDirectory()
        exe = Path(cls.tmp.name) / "trace_runner"
        if Path(compiler).name.lower() == "cl.exe":
            command = [compiler, "/nologo", "/W4", "/std:c11",
                       str(HERE / "mcu_core.c"), str(HERE / "trace_runner.c"),
                       "/Fe:" + str(exe.with_suffix(".exe"))]
            exe = exe.with_suffix(".exe")
        else:
            command = [compiler, "-std=c99", "-Wall", "-Wextra", "-Werror",
                       str(HERE / "mcu_core.c"), str(HERE / "trace_runner.c"),
                       "-o", str(exe)]
        try:
            subprocess.run(command, check=True, capture_output=True, text=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            cls.tmp.cleanup()
            raise unittest.SkipTest("C99 compilation failed: %s" % exc)
        cls.exe = exe

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "tmp"):
            cls.tmp.cleanup()

    def compare(self, words: list[int]):
        expected = _model_trace(words)
        process = subprocess.run([str(self.exe)], input="".join(f"{w:x}\n" for w in words),
                                 text=True, capture_output=True, check=True)
        actual = []
        for line in process.stdout.splitlines():
            fields = line.split()
            state, srq, count = int(fields[0], 16), int(fields[1]), int(fields[2])
            replies = [(int(value.split(":")[0], 16), int(value.split(":")[1]))
                       for value in fields[3:]]
            self.assertEqual(len(replies), count, line)
            actual.append((state, srq, replies))
        self.assertEqual(actual, expected)

    def test_deterministic_protocol_vectors(self):
        self.compare([0x101, 0x003, 0x112, 0x005, 0x134, 0x0A5, 0x105])

    def test_bounded_fuzzed_word_sequences(self):
        rng = random.Random(0x34410A)
        for _ in range(24):
            words = [rng.randrange(0x200) for _ in range(80)]
            self.compare(words)


if __name__ == "__main__":
    unittest.main()
