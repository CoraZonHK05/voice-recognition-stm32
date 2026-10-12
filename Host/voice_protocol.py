"""Shared parser for the STM32 MFCC serial frame."""

from __future__ import annotations

import numpy as np

HEADER = b"\xAA\x55"
TAIL = b"\x0D\x0A"
N_MFCC = 13
FRAME_BYTES = 2 + N_MFCC * 2 + 2
QUANTIZATION_SCALE = 8.0  # Firmware calls MFCC_Quantize(..., shift=3).


def decode_frame(frame: bytes) -> np.ndarray | None:
    if len(frame) != FRAME_BYTES or frame[:2] != HEADER or frame[-2:] != TAIL:
        return None
    # Return signed fixed-point integers; training and inference both scale
    # these using the same explicit preprocessing step.
    return np.frombuffer(frame[2:-2], dtype=">i2").astype(np.float32)


class FrameParser:
    """Accumulate arbitrary serial chunks and return complete MFCC frames."""

    def __init__(self) -> None:
        self._buffer = bytearray()

    def feed(self, data: bytes) -> list[np.ndarray]:
        self._buffer.extend(data)
        frames: list[np.ndarray] = []
        while True:
            start = self._buffer.find(HEADER)
            if start < 0:
                # Preserve a possible first header byte split across reads.
                keep = 1 if self._buffer[-1:] == HEADER[:1] else 0
                if keep:
                    self._buffer[:] = self._buffer[-1:]
                else:
                    self._buffer.clear()
                break
            if start:
                del self._buffer[:start]
            if len(self._buffer) < FRAME_BYTES:
                break
            candidate = bytes(self._buffer[:FRAME_BYTES])
            decoded = decode_frame(candidate)
            if decoded is None:
                # Drop one byte and resynchronize at the next possible header.
                del self._buffer[0]
                continue
            frames.append(decoded)
            del self._buffer[:FRAME_BYTES]
        return frames
