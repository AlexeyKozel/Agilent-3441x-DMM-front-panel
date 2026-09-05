"""Bounded, independent opcode oracle for a user-supplied original 8051 image.

No firmware is bundled or downloaded. This is not a full 8051/peripheral emulator.
It executes C startup, selected command windows, and the diagnostic FIFO path.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path

FIRMWARE_SHA256 = "55779328f8d9de6675ac3a145f846cfc3f86aaa346136698ef4df31edc15c4dd"


def load_firmware(path: str | Path) -> bytes:
    image = Path(path).read_bytes()
    validate_image(image)
    return image


def validate_image(image: bytes) -> None:
    if len(image) != 4162 or hashlib.sha256(image).hexdigest() != FIRMWARE_SHA256:
        raise ValueError("Original firmware length/SHA-256 mismatch")


def firmware_from_environment() -> bytes | None:
    """Absent optional input returns None; a supplied invalid input always fails."""
    path = os.environ.get("FP_ORIGINAL_FIRMWARE")
    if path:
        return load_firmware(path)
    if os.environ.get("FP_REQUIRE_ORIGINAL_FIRMWARE") == "1":
        raise ValueError("FP_REQUIRE_ORIGINAL_FIRMWARE=1 requires FP_ORIGINAL_FIRMWARE")
    return None


@dataclass(frozen=True)
class StartupState:
    iram: bytes
    xram: bytes
    irq_enabled: bool
    srq_low: bool
    state: int
    instruction_count: int


class _Machine:
    """Only instructions reached by the explicitly bounded windows below."""

    def __init__(self, image: bytes):
        self.image = image
        self.iram = bytearray(256)
        self.sfr = bytearray(128)
        self.xram = bytearray(512)
        self.a = self.cy = self.steps = 0
        self.replies: list[int] = []
        self.fifo_events: list[int] = []

    def read(self, address: int) -> int:
        if address == 0xe0:
            return self.a
        return self.iram[address] if address < 128 else self.sfr[address-128]

    def write(self, address: int, value: int) -> None:
        value &= 255
        if address == 0xe0:
            self.a = value
        elif address < 128:
            self.iram[address] = value
        else:
            self.sfr[address-128] = value
        if address == 0x99:
            self.replies.append(value)

    def bit(self, bit: int) -> int:
        address = 0x20+(bit>>3) if bit < 128 else bit & 0xf8
        return (self.read(address) >> (bit & 7)) & 1

    def set_bit(self, bit: int, value: int) -> None:
        address = 0x20+(bit>>3) if bit < 128 else bit & 0xf8
        mask = 1 << (bit & 7)
        self.write(address, (self.read(address) & ~mask) | (mask if value else 0))

    def dptr(self) -> int:
        return self.read(0x83)*256 + self.read(0x82)

    def set_dptr(self, value: int) -> None:
        self.write(0x82, value)
        self.write(0x83, value >> 8)

    def run(self, pc: int, stop: int, limit: int = 200) -> None:
        calls: list[int] = []
        initial_steps = self.steps
        while pc != stop:
            if self.steps - initial_steps >= limit:
                raise ValueError("Opcode window exceeded instruction bound")
            if not 0 <= pc < len(self.image):
                raise ValueError("Opcode window left supplied application image")
            at = pc
            op = self.image[pc]
            pc += 1
            self.steps += 1

            def byte() -> int:
                nonlocal pc
                value = self.image[pc]
                pc += 1
                return value

            def rel() -> int:
                value = byte()
                return value if value < 128 else value - 256

            if op in (0x02, 0x12):
                target = byte()*256 + byte()
                if op == 0x12:
                    calls.append(pc)
                pc = target
            elif op == 0x22:
                pc = calls.pop() if calls else stop
            elif op == 0x00:
                pass
            elif op == 0xe4:
                self.a = 0
            elif op == 0x74:
                self.a = byte()
            elif 0x78 <= op <= 0x7f:
                self.iram[op-0x78] = byte()
            elif op in (0xf6, 0xa6):
                value = self.a if op == 0xf6 else self.read(byte())
                address = self.iram[0]
                self.iram[address] = value
                if 0x30 <= address <= 0x33 and at == 0xe19:
                    self.fifo_events.append(value)
            elif 0xd8 <= op <= 0xdf:
                reg = op-0xd8
                self.iram[reg] = (self.iram[reg]-1)&255
                offset = rel()
                if self.iram[reg]:
                    pc += offset
            elif op == 0xd5:
                address, offset = byte(), rel()
                self.write(address, self.read(address)-1)
                if self.read(address):
                    pc += offset
            elif op == 0x90:
                self.set_dptr(byte()*256 + byte())
            elif op == 0xf0:
                self.xram[self.dptr()] = self.a
            elif op == 0xa3:
                self.set_dptr((self.dptr()+1)&65535)
            elif op == 0x75:
                address, value = byte(), byte()
                self.write(address, value)
            elif op == 0x85:
                source, target = byte(), byte()
                self.write(target, self.read(source))
            elif op == 0x93:
                self.a = self.image[(self.dptr()+self.a)&65535]
            elif 0xf8 <= op <= 0xff:
                self.iram[op-0xf8] = self.a
            elif 0xe8 <= op <= 0xef:
                self.a = self.iram[op-0xe8]
            elif 0xa8 <= op <= 0xaf:
                self.iram[op-0xa8] = self.read(byte())
            elif 0x88 <= op <= 0x8f:
                self.write(byte(), self.iram[op-0x88])
            elif op in (0x40, 0x50, 0x60, 0x70, 0x80):
                offset = rel()
                branch = (op == 0x80 or op == 0x40 and self.cy or
                          op == 0x50 and not self.cy or op == 0x60 and not self.a or
                          op == 0x70 and self.a)
                if branch:
                    pc += offset
            elif 0x08 <= op <= 0x0f:
                reg = op-8
                self.iram[reg] = (self.iram[reg]+1)&255
            elif op == 0x05:
                address = byte()
                self.write(address, self.read(address)+1)
            elif op == 0x14:
                self.a = (self.a-1)&255
            elif op == 0x54:
                self.a &= byte()
            elif op in (0x24, 0x25, 0x2f, 0x34):
                value = self.iram[7] if op == 0x2f else byte()
                if op == 0x25:
                    value = self.read(value)
                self.cy, self.a = divmod(self.a+value+(self.cy if op == 0x34 else 0), 256)
            elif op in (0x94, 0x95):
                value = byte()
                if op == 0x95:
                    value = self.read(value)
                result = self.a-value-self.cy
                self.cy, self.a = int(result < 0), result & 255
            elif op == 0x64:
                self.a ^= byte()
            elif op == 0x65:
                self.a ^= self.read(byte())
            elif 0xc8 <= op <= 0xcf:
                reg = op-0xc8
                self.a, self.iram[reg] = self.iram[reg], self.a
            elif op == 0xc3:
                self.cy = 0
            elif op == 0x33:
                self.cy, self.a = self.a >> 7, ((self.a << 1)|self.cy)&255
            elif op == 0xc4:
                self.a = ((self.a << 4) | (self.a >> 4))&255
            elif op == 0x44:
                self.a |= byte()
            elif op == 0x83:
                self.a = self.image[(pc+self.a)&65535]
            elif op == 0xf4:
                self.a ^= 255
            elif op == 0x56:
                self.a &= self.iram[self.iram[0]]
            elif op == 0x46:
                self.a |= self.iram[self.iram[0]]
            elif op == 0x30:
                bit, offset = byte(), rel()
                if not self.bit(bit):
                    pc += offset
            elif op == 0xb4:
                value, offset = byte(), rel()
                self.cy = int(self.a < value)
                if self.a != value:
                    pc += offset
            elif op == 0xc5:
                address = byte()
                value = self.read(address)
                self.write(address, self.a)
                self.a = value
            elif op == 0xe5:
                self.a = self.read(byte())
            elif op == 0xf5:
                self.write(byte(), self.a)
            elif op in (0xc2, 0xd2):
                self.set_bit(byte(), int(op == 0xd2))
            else:
                raise ValueError(f"Unsupported opcode {op:02x} at {at:04x}")


class FirmwareOracle:
    def __init__(self, image: bytes):
        validate_image(image)
        self.image = image

    def startup(self) -> StartupState:
        machine = self._startup_machine()
        return StartupState(bytes(machine.iram), bytes(machine.xram),
                            bool(machine.iram[0x36]), not machine.bit(0x96),
                            machine.iram[0x3c], machine.steps)

    def _startup_machine(self) -> _Machine:
        machine = _Machine(self.image)
        machine.run(0, 0xa3b, limit=6000)
        # Ordinary P1.4=1 runtime branch skips the opaque ROM FF03 calls.
        # The post-C-startup call order and the sole XDATA-writing initializer
        # are pinned to small opcode windows. The remaining hardware setup is
        # NOT executed. It does not write IRAM36 or XDATA0..95 in this image.
        checked = {
            0xa3b: "120c25c2af209406120c0a43a208120d80120e24120d2f120b84120cdd120eed12005e120f84d2af",
            0xeed: "c296e4ff7f149000967482f0a3dffce4f52f12005222",
            0x52: "22",
            0xf84: "c2ae43b74053b8bf120f56120fdc22",
            0xf56: "e4f5d175d21275d34f43d10243d10122",
            0xfdc: "e4f5a775c11643a70422",
        }
        for address, expected in checked.items():
            raw = bytes.fromhex(expected)
            if self.image[address:address+len(raw)] != raw:
                raise ValueError(f"Post-startup opcode assertion failed at {address:04x}")
        # Execute debounce initialization/CLR P1.6 itself. This is a checked
        # effect of later runtime initialization, not a full main-loop replay.
        machine.run(0xeed, 0xf03)
        return machine

    def runtime(self) -> RuntimeWindows:
        return RuntimeWindows(self)


class RuntimeWindows:
    def __init__(self, oracle: FirmwareOracle):
        self.machine = oracle._startup_machine()

    @property
    def xram(self) -> bytearray:
        return self.machine.xram

    @property
    def iram(self) -> bytearray:
        return self.machine.iram

    @property
    def replies(self) -> list[int]:
        return self.machine.replies

    @property
    def state(self) -> int:
        return self.iram[0x3c]

    @property
    def srq_low(self) -> bool:
        return not self.machine.bit(0x96)

    def _input(self, value: int) -> None:
        if not isinstance(value, int) or not 0 <= value <= 255:
            raise ValueError("Input must be a byte")
        self.machine.sfr[0x99-128] = value  # RX input is not a transmitted reply.

    def display_begin(self, count: int, start: int) -> None:
        self.iram[0x37], self.iram[0x38] = 0x21, 0
        for byte in (0x21, count, start):
            self._input(byte)
            self.machine.run(0x638, 0x692)

    def display_byte(self, value: int) -> tuple[int, ...]:
        if self.state != 0:
            raise ValueError("Display window is not awaiting payload")
        self._input(value)
        previous = len(self.replies)
        self.machine.run(0x638, 0x692)
        return tuple(self.replies[previous:])

    def status_resync(self) -> int:
        self.machine.run(0xfef, 0xff8)
        return self.replies[-1]

    def diagnostic_enable(self, value: int) -> None:
        self._input(value)
        self.machine.run(0xe85, 0xe91)

    def diagnostic_tick(self, iterations: int = 1) -> tuple[int, ...]:
        if not isinstance(iterations, int) or iterations < 0:
            raise ValueError("Iterations must be nonnegative")
        before = len(self.machine.fifo_events)
        for _ in range(iterations):
            self.machine.run(0xa74, 0xa87)
        return tuple(self.machine.fifo_events[before:])


def trace_document(image: bytes) -> dict:
    oracle = FirmwareOracle(image)
    startup = oracle.startup()
    cases = {}
    for name, count, start, values in (
        ("partial_valid", 2, 0, [0xaa]),
        ("partial_zero", 0, 0x20, [0xa5]),
        ("nonzero_outside_framebuffer", 2, 0x95, [0xaa, 0xbb]),
    ):
        runtime = oracle.runtime()
        runtime.display_begin(count, start)
        for byte in values:
            runtime.display_byte(byte)
        cases[name] = {"xdata": list(runtime.xram[start:start+len(values)]),
                       "state_before_resync": runtime.state,
                       "replies_before_resync": runtime.replies[:],
                       "resync_reply": runtime.status_resync()}
    diagnostic = []
    for disabled, enable, enabled in ((29, 1, 1), (0, 30, 1), (0, 255, 1), (0, 1, 30)):
        runtime = oracle.runtime()
        runtime.diagnostic_tick(disabled)
        runtime.diagnostic_enable(enable)
        events = runtime.diagnostic_tick(enabled)
        diagnostic.append({"disabled_ticks": disabled, "enable": enable,
                           "enabled_ticks": enabled, "events": list(events),
                           "counter": runtime.iram[0x43]})
    return {"firmware_sha256": FIRMWARE_SHA256,
            "scope": "bounded startup/selected runtime opcode windows; no ROM/peripherals",
            "startup": {"irq_enabled": startup.irq_enabled, "srq_low": startup.srq_low,
                        "state": startup.state, "framebuffer_hex": startup.xram[:150].hex(),
                        "instruction_count_including_debounce_initializer": startup.instruction_count},
            "display": cases, "diagnostic": diagnostic}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--firmware", required=True, type=Path,
                        help="Explicit path to the original 4162-byte image (never downloaded)")
    args = parser.parse_args()
    print(json.dumps(trace_document(load_firmware(args.firmware)), indent=2))


if __name__ == "__main__":
    main()
