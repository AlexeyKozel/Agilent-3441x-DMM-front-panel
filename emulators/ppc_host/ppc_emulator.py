# SPDX-License-Identifier: MIT
"""Offline model of the stock PPC-side front-panel transaction logic.

This module models protocol decisions only. It does not open a serial port,
configure a UART, drive reset, or access an instrument.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, Sequence


class WordEndpoint(Protocol):
    """Endpoint accepting one packed 9-bit word and returning reply bytes."""

    def receive_word(self, word: int) -> tuple[int, ...]: ...


class PpcProtocolError(RuntimeError):
    """Raised when an offline endpoint violates the reconstructed contract."""


@dataclass(frozen=True)
class TransactionResult:
    packet: tuple[int, ...]
    immediate_reply: tuple[int, ...]
    status: int
    success: bool


@dataclass(frozen=True)
class EchoResult:
    payload: tuple[int, ...]
    echoed: tuple[int, ...]
    exit_status: int


class PpcHostEmulator:
    """Deterministic offline emulator of the stock PPC transaction wrapper."""

    STATUS_COMMAND_WORD = 0x105
    SUCCESS_MASK = 0x85
    SUCCESS_VALUE = 0x01
    EXPECTED_REPLY_LENGTH = {
        0x01: 2,
        0x03: 1,
        0x12: 1,
        0x13: 1,
        0x14: 1,
        0x15: 1,
        0x21: 1,
        0x31: 1,
        0x32: 1,
        0x33: 1,
        0x36: 1,
        0x38: 1,
        0x3A: 1,
    }

    def __init__(self, endpoint: WordEndpoint):
        self.endpoint = endpoint

    @staticmethod
    def _bytes(values: Sequence[int]) -> tuple[int, ...]:
        result = tuple(values)
        if any(not isinstance(value, int) or not 0 <= value <= 0xFF for value in result):
            raise ValueError("all packet values must be bytes")
        return result

    def _send_data(self, byte: int) -> tuple[int, ...]:
        return tuple(self.endpoint.receive_word(byte))

    def status_query(self) -> int:
        """Send CMMD GET_STATUS and require exactly one reply byte."""
        reply = tuple(self.endpoint.receive_word(self.STATUS_COMMAND_WORD))
        if len(reply) != 1:
            raise PpcProtocolError(f"GET_STATUS returned {len(reply)} bytes, expected 1")
        return reply[0]

    def transact(self, packet: Sequence[int]) -> TransactionResult:
        """Run one stock DATA packet followed by the CMMD status query.

        The echo command has streaming semantics and must be used through
        :meth:`echo`. Direct GET_STATUS is reserved for :meth:`status_query`.
        """
        values = self._bytes(packet)
        if not values:
            raise ValueError("packet cannot be empty")
        command = values[0]
        if command == 0x34:
            raise ValueError("use echo() for command 0x34")
        if command == 0x05:
            raise ValueError("use status_query() for command 0x05")

        immediate: list[int] = []
        for value in values:
            immediate.extend(self._send_data(value))

        expected = self.EXPECTED_REPLY_LENGTH.get(command, 1)
        if len(immediate) != expected:
            raise PpcProtocolError(
                f"command 0x{command:02X} returned {len(immediate)} immediate bytes, "
                f"expected {expected}"
            )
        status = self.status_query()
        return TransactionResult(
            values,
            tuple(immediate),
            status,
            (status & self.SUCCESS_MASK) == self.SUCCESS_VALUE,
        )

    def echo(self, payload: Sequence[int]) -> EchoResult:
        """Run the stock streaming echo mode and leave it through CMMD 0x05."""
        values = self._bytes(payload)
        if self._send_data(0x34):
            raise PpcProtocolError("echo command produced an unexpected initial reply")
        echoed: list[int] = []
        for value in values:
            reply = self._send_data(value)
            if reply != (value,):
                raise PpcProtocolError(
                    f"echo mismatch for 0x{value:02X}: {reply!r}"
                )
            echoed.append(reply[0])
        return EchoResult(values, tuple(echoed), self.status_query())

    def get_revision(self) -> int:
        result = self.transact((0x01,))
        if not result.success:
            raise PpcProtocolError(f"GET_REVISION failed with status 0x{result.status:02X}")
        return (result.immediate_reply[0] << 8) | result.immediate_reply[1]

    def write_display(self, start: int, data: bytes | bytearray) -> TransactionResult:
        """Send a stock-valid non-empty display span."""
        if not isinstance(start, int) or not 0 <= start <= 0x95:
            raise ValueError("display start must be in 0x00..0x95")
        values = bytes(data)
        if not values:
            raise ValueError("stock PPC display writes are non-empty")
        if len(values) > 0x96 or start + len(values) > 0x96:
            raise ValueError("display span exceeds the 150-byte framebuffer")
        return self.transact((0x21, len(values), start, *values))

    def set_key_irq_enabled(self, enabled: bool) -> TransactionResult:
        return self.transact((0x38, int(bool(enabled))))

    def dequeue_key_event(self) -> TransactionResult:
        return self.transact((0x15,))
