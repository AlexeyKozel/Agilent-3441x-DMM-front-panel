"""Executable C/Python comparisons after every word, tick, and helper operation.

FP_C_COMPILER selects an executable explicitly. An invalid selection or build
failure is an error; only an absent optional compiler skips executable tests.
Set FP_REQUIRE_C_COMPILER=1 to make a missing compiler an error in CI.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

HERE = Path(__file__).resolve().parent
MODEL_ROOT = HERE.parents[1]
sys.path.insert(0, str(MODEL_ROOT))
from emulators.front_panel_python import PanelModel  # noqa: E402

Action = int | tuple[str] | tuple[str, int] | tuple[str, int, int]


def _compiler() -> str | None:
    configured = os.environ.get("FP_C_COMPILER")
    if configured:
        candidate = Path(configured)
        found = str(candidate.resolve()) if candidate.is_file() else shutil.which(configured)
        if found:
            return found
        raise RuntimeError(f"Configured FP_C_COMPILER is unavailable: {configured}")
    for name in ("cc", "gcc", "clang", "cl", "tcc"):
        found = shutil.which(name)
        if found:
            return found
    if os.environ.get("FP_REQUIRE_C_COMPILER") == "1":
        raise RuntimeError("FP_REQUIRE_C_COMPILER=1 but no C compiler is available")
    return None


def _build(compiler: str, runner: str, directory: Path) -> Path:
    exe = directory / (runner + (".exe" if os.name == "nt" else ""))
    if Path(compiler).name.lower() in ("cl", "cl.exe"):
        command = [compiler, "/nologo", "/W4", "/WX", "/std:c11",
                   str(HERE / "mcu_core.c"), str(HERE / f"{runner}.c"),
                   "/Fe:" + str(exe)]
    else:
        command = [compiler, "-std=c99", "-Wall", "-Wextra", "-Werror",
                   str(HERE / "mcu_core.c"), str(HERE / f"{runner}.c"),
                   "-o", str(exe)]
    try:
        # MSVC also creates .obj files: keep all compiler output in the temp dir.
        subprocess.run(command, cwd=directory, check=True, capture_output=True, text=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        diagnostic = getattr(exc, "stderr", "") or getattr(exc, "stdout", "") or str(exc)
        raise RuntimeError(f"C compilation failed ({compiler}): {diagnostic}") from exc
    return exe


def _snapshot(model: PanelModel, replies=()) -> dict:
    return {
        "status": model.status,
        "srq_low": int(model.srq_low),
        "irq_enabled": int(model.irq_enabled),
        "echo_mode": int(model.echo_mode),
        "break_detect_enabled": int(model.break_detect_enabled),
        "diagnostic_counter": model.diagnostic_counter,
        "diagnostic_key_traffic": int(model.diagnostic_key_traffic),
        "diagnostic_key_id": model.diagnostic_key_id,
        "main_loop_count": model.main_loop_count,
        "last_stock_display_write": list(model.last_stock_display_write or (0, 0)),
        "replies": [[reply.byte, int(reply.ninth_bit)] for reply in replies],
        "key_fifo": list(model.key_fifo),
        "framebuffer": model.framebuffer.hex(),
        "stock_xram": model.stock_xram.hex(),
    }


def _model_trace(actions: list[Action]) -> list[dict]:
    model = PanelModel()
    result = []
    for action in actions:
        replies = ()
        if isinstance(action, int):
            replies = model.receive_word_reply_words(action)
        elif action[0] == "tick":
            model.tick(action[1])
        elif action[0] == "key":
            model.enqueue_event(action[1])
        elif action[0] == "cell":
            model.set_cell(action[1], action[2])
        elif action[0] == "reset":
            model.reset()
        else:
            raise ValueError(f"Unknown trace action: {action}")
        result.append(_snapshot(model, replies))
    return result


def _action_line(action: Action) -> str:
    if isinstance(action, int):
        return f"W {action:x}\n"
    if action[0] == "tick":
        return f"T {action[1]}\n"
    if action[0] == "key":
        return f"K {action[1]:x}\n"
    if action[0] == "cell":
        return f"C {action[1]} {action[2]}\n"
    if action[0] == "reset":
        return "R\n"
    raise ValueError(f"Unknown trace action: {action}")


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
        self.assertNotIn("malloc(", source)
        self.assertNotIn("UART", source)


class CompilerPolicyTests(unittest.TestCase):
    def test_invalid_explicit_compiler_does_not_fall_back_or_skip(self):
        with mock.patch.dict(os.environ, {"FP_C_COMPILER": "missing-explicit-compiler"}):
            with mock.patch.object(Path, "is_file", return_value=False):
                with mock.patch.object(shutil, "which", return_value=None) as which:
                    with self.assertRaisesRegex(RuntimeError, "Configured FP_C_COMPILER"):
                        _compiler()
                    which.assert_called_once_with("missing-explicit-compiler")

    def test_optional_missing_compiler_and_strict_ci(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with mock.patch.object(shutil, "which", return_value=None):
                self.assertIsNone(_compiler())
                with mock.patch.dict(os.environ, {"FP_REQUIRE_C_COMPILER": "1"}):
                    with self.assertRaisesRegex(RuntimeError, "FP_REQUIRE_C_COMPILER=1"):
                        _compiler()

    def test_compilation_error_is_failure_with_diagnostics(self):
        failure = subprocess.CalledProcessError(1, ["cc"], stderr="syntax error fixture")
        with mock.patch.object(subprocess, "run", side_effect=failure):
            with self.assertRaisesRegex(RuntimeError, "syntax error fixture"):
                _build("cc", "trace_runner", HERE)


class DifferentialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler = _compiler()
        if compiler is None:
            raise unittest.SkipTest("C99 compiler is unavailable; source checks remain active")
        cls.tmp = tempfile.TemporaryDirectory(prefix="front-panel-c99-")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.exe = _build(compiler, "trace_runner", Path(cls.tmp.name))
        cls.host_exe = _build(compiler, "test_host", Path(cls.tmp.name))

    def c_trace(self, actions: list[Action]) -> list[dict]:
        process = subprocess.run([str(self.exe)],
                                 input="".join(_action_line(action) for action in actions),
                                 text=True, capture_output=True, check=True)
        result = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(len(result), len(actions), process.stdout)
        return result

    def compare(self, actions: list[Action]) -> list[dict]:
        actual = self.c_trace(actions)
        expected = _model_trace(actions)
        for index, (c_state, py_state) in enumerate(zip(actual, expected)):
            self.assertEqual(c_state, py_state, f"operation {index}: {actions[index]}")
        return actual

    def test_standalone_c_host_regressions(self):
        result = subprocess.run([str(self.host_exe)], text=True, capture_output=True, check=True)
        self.assertIn("mcu_core host tests: OK", result.stdout)

    def firmware_oracle(self):
        from tools.firmware_oracle import FirmwareOracle, firmware_from_environment
        image = firmware_from_environment()
        if image is None:
            self.skipTest("Set FP_ORIGINAL_FIRMWARE for independent opcode comparisons")
        return FirmwareOracle(image)

    def test_c_startup_against_external_firmware_opcodes(self):
        startup = self.firmware_oracle().startup()
        state = self.c_trace([("reset",)])[0]
        self.assertEqual(state["stock_xram"], startup.xram.hex())
        self.assertEqual(state["framebuffer"], startup.xram[:150].hex())
        self.assertEqual(state["irq_enabled"], int(startup.irq_enabled))
        self.assertEqual(state["srq_low"], int(startup.srq_low))
        self.assertEqual(state["status"], startup.state)

    def test_c_display_against_external_firmware_opcodes(self):
        oracle = self.firmware_oracle()
        for count, start, data in (
            (2, 0, [0xAA]),
            (0, 0x20, [0xA5]),
            (2, 0x95, [0xAA, 0xBB]),
            (1, 0xFF, [0xA5]),
            (255, 0xFF, list(range(255))),
            (0, 0xFF, list(range(256))),
        ):
            with self.subTest(count=count, start=start, length=len(data)):
                runtime = oracle.runtime()
                runtime.display_begin(count, start)
                trace = self.c_trace([0x121, count, start] + data + [0x105])
                for index, value in enumerate(data):
                    replies = runtime.display_byte(value)
                    state = trace[3 + index]
                    self.assertEqual(state["stock_xram"], runtime.xram.hex())
                    self.assertEqual(state["framebuffer"], runtime.xram[:150].hex())
                    self.assertEqual(state["status"], runtime.state)
                    self.assertEqual(state["replies"], [[value, 0] for value in replies])
                old_state = runtime.status_resync()
                self.assertEqual(trace[-1]["stock_xram"], runtime.xram.hex())
                self.assertEqual(trace[-1]["status"], runtime.state)
                self.assertEqual(trace[-1]["replies"], [[old_state, 0]])

    def test_c_diagnostic_against_external_firmware_opcodes(self):
        oracle = self.firmware_oracle()
        steps = [1, 1, 28, 1, 30, 600]
        for raw in (0, 1, 2, 29, 30, 31, 255):
            with self.subTest(raw=raw):
                runtime = oracle.runtime()
                runtime.diagnostic_tick(29)
                runtime.diagnostic_enable(raw)
                actions = [("tick", 29), 0x136, raw] + [("tick", step) for step in steps]
                trace = self.c_trace(actions)
                fifo = []
                for index, step in enumerate(steps):
                    fifo.extend(runtime.diagnostic_tick(step))
                    self.assertEqual(trace[3 + index]["diagnostic_counter"], runtime.iram[0x43])
                    self.assertEqual(trace[3 + index]["key_fifo"], fifo)
                    self.assertEqual(trace[3 + index]["srq_low"], int(runtime.srq_low))

    def test_deterministic_protocol_vectors(self):
        self.compare([0x101, 0x003, 0x112, 0x005, 0x134, 0x0A5, 0x105])

    def test_reset_irq_fifo_and_helper_coherence(self):
        trace = self.compare([("reset",), 0x15, ("key", 0xC0), 0x15,
                              ("cell", 0, 0), ("cell", 599, 1), ("reset",)])
        self.assertEqual(trace[0]["framebuffer"], "ff" * 150)
        self.assertEqual(trace[0]["stock_xram"][300:340], "82" * 20)
        self.assertEqual([trace[i]["srq_low"] for i in range(4)], [1, 0, 1, 0])
        self.assertEqual(trace[4]["stock_xram"][:2], "3f")
        self.assertEqual(trace[5]["stock_xram"][298:300], "fd")

    def test_every_display_byte_and_resynchronization(self):
        for count in (0, 1, 2, 150, 255):
            for start in (0, 0x95, 0x96, 0xFF):
                length = count or 256
                data = [(offset * 17 + 0xA5) & 0xFF for offset in range(length)]
                with self.subTest(count=count, start=start):
                    trace = self.compare([0x121, count, start] + data + [0x105])
                    self.assertEqual(trace[3]["stock_xram"][start * 2:start * 2 + 2], "a5")
                    self.assertEqual(trace[-2]["replies"], [[1, 0]])
                    self.assertEqual(trace[-2]["last_stock_display_write"], [start, length])
        for count in (0, 2):
            trace = self.compare([0x121, count, 0x95, 0xA5, 0x105])
            self.assertEqual(trace[-1]["replies"], [[0, 0]])
            self.assertEqual(trace[-1]["framebuffer"][-2:], "a5")
            self.assertEqual(trace[-1]["last_stock_display_write"], [0x95, 1])

    def test_raw_diagnostic_counter_and_disabled_phase(self):
        for raw in (0, 1, 2, 29, 30, 31, 255):
            with self.subTest(raw=raw):
                trace = self.compare([("tick", 29), 0x136, raw, ("tick", 1),
                                      ("tick", 29), 0x115, 0x115,
                                      0x136, 0, ("tick", 60), 0x136, 1,
                                      ("tick", 1), ("tick", 29)])
                self.assertEqual(trace[3]["diagnostic_counter"],
                                 0 if raw == 0 else 1 if raw >= 30 else raw + 1)
                self.assertEqual(trace[3]["key_fifo"], [0x40, 0] if raw >= 30 else [])

    def test_fifo_overflow_ring_wrap_and_diagnostic_key_wrap(self):
        actions: list[Action] = [0x136, 30]
        for _ in range(23):
            actions += [("tick", 30), 0x115, 0x115]
        actions += [("key", i) for i in range(6)]
        actions += [0x115, 0x115, ("key", 0xC1), ("key", 0xC2), 0x13A]
        self.compare(actions)

    def test_bounded_fuzzed_word_sequences(self):
        rng = random.Random(0x34410A)
        for _ in range(24):
            actions: list[Action] = []
            for _ in range(80):
                selector = rng.randrange(8)
                if selector == 0:
                    actions.append(("tick", rng.randrange(65)))
                elif selector == 1:
                    actions.append(("key", rng.randrange(256)))
                elif selector == 2:
                    actions.append(("cell", rng.randrange(600), rng.randrange(4)))
                else:
                    actions.append(rng.randrange(0x200))
            self.compare(actions)


if __name__ == "__main__":
    unittest.main()
