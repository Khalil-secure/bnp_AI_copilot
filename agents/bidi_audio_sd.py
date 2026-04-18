"""
BidiAudioIO replacement using sounddevice instead of pyaudio.
Implements the same BidiInput / BidiOutput protocols from strands.experimental.bidi.
Compatible with Python 3.14 (pyaudio has no 3.14 wheel).
"""
import asyncio
import base64
import logging
import queue
from typing import Any, TYPE_CHECKING

import numpy as np
import sounddevice as sd

from strands.experimental.bidi.types.events import (
    BidiAudioInputEvent,
    BidiAudioStreamEvent,
    BidiInterruptionEvent,
    BidiOutputEvent,
)
from strands.experimental.bidi.types.io import BidiInput, BidiOutput

if TYPE_CHECKING:
    from strands.experimental.bidi.agent.agent import BidiAgent

logger = logging.getLogger(__name__)


class _SDBuffer:
    """Thread-safe audio buffer shared between sounddevice callbacks and asyncio."""

    def __init__(self, max_size: int | None = None):
        self._q: queue.Queue = queue.Queue(max_size or 0)
        self._data = bytearray()

    def put(self, chunk: bytes) -> None:
        if self._q.full():
            try:
                self._q.get_nowait()
            except queue.Empty:
                pass
        self._q.put_nowait(chunk)

    def get(self, byte_count: int | None = None) -> bytes:
        if not byte_count:
            self._data.extend(self._q.get())
            byte_count = len(self._data)
        while len(self._data) < byte_count:
            try:
                self._data.extend(self._q.get_nowait())
            except queue.Empty:
                break
        pad = b"\x00" * max(byte_count - len(self._data), 0)
        self._data.extend(pad)
        data = bytes(self._data[:byte_count])
        del self._data[:byte_count]
        return data

    def clear(self) -> None:
        while True:
            try:
                self._q.get_nowait()
            except queue.Empty:
                break

    def shutdown(self) -> None:
        self._q.put_nowait(b"")


class SDAudioInput(BidiInput):
    """Mic capture via sounddevice — drop-in for strands _BidiAudioInput."""

    def __init__(self, frames_per_buffer: int = 512, device_index: int | None = None):
        self._fpb = frames_per_buffer
        self._device = device_index
        self._buffer = _SDBuffer()

    async def start(self, agent: "BidiAgent") -> None:
        self._channels = agent.model.config["audio"]["channels"]
        self._format = agent.model.config["audio"]["format"]
        self._rate = agent.model.config["audio"]["input_rate"]

        self._stream = sd.InputStream(
            samplerate=self._rate,
            channels=self._channels,
            dtype="int16",
            blocksize=self._fpb,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        logger.debug("sounddevice input stream started at %d Hz", self._rate)

    async def stop(self) -> None:
        if hasattr(self, "_stream"):
            self._stream.stop()
            self._stream.close()
        self._buffer.shutdown()
        logger.debug("sounddevice input stream stopped")

    async def __call__(self) -> BidiAudioInputEvent:
        data = await asyncio.to_thread(self._buffer.get)
        return BidiAudioInputEvent(
            audio=base64.b64encode(data).decode("utf-8"),
            channels=self._channels,
            format=self._format,
            sample_rate=self._rate,
        )

    def _callback(self, indata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        self._buffer.put(indata.tobytes())


class SDAudioOutput(BidiOutput):
    """Speaker playback via sounddevice — drop-in for strands _BidiAudioOutput."""

    def __init__(self, frames_per_buffer: int = 512, device_index: int | None = None):
        self._fpb = frames_per_buffer
        self._device = device_index
        self._buffer = _SDBuffer()

    async def start(self, agent: "BidiAgent") -> None:
        self._channels = agent.model.config["audio"]["channels"]
        self._rate = agent.model.config["audio"]["output_rate"]

        self._stream = sd.OutputStream(
            samplerate=self._rate,
            channels=self._channels,
            dtype="int16",
            blocksize=self._fpb,
            device=self._device,
            callback=self._callback,
        )
        self._stream.start()
        logger.debug("sounddevice output stream started at %d Hz", self._rate)

    async def stop(self) -> None:
        if hasattr(self, "_stream"):
            self._stream.stop()
            self._stream.close()
        logger.debug("sounddevice output stream stopped")

    async def __call__(self, event: BidiOutputEvent) -> None:
        if isinstance(event, BidiAudioStreamEvent):
            data = base64.b64decode(event["audio"])
            self._buffer.put(data)
        elif isinstance(event, BidiInterruptionEvent):
            logger.debug("interruption — clearing audio buffer")
            self._buffer.clear()

    def _callback(self, outdata: np.ndarray, frames: int, time_info: Any, status: Any) -> None:
        byte_count = frames * self._channels * 2  # int16 = 2 bytes
        data = self._buffer.get(byte_count)
        arr = np.frombuffer(data, dtype=np.int16).reshape(frames, self._channels)
        outdata[:] = arr


class SDBidiAudioIO:
    """Factory — same API as BidiAudioIO but uses sounddevice."""

    def __init__(self, frames_per_buffer: int = 512, device_index: int | None = None):
        self._fpb = frames_per_buffer
        self._device = device_index

    def input(self) -> SDAudioInput:
        return SDAudioInput(self._fpb, self._device)

    def output(self) -> SDAudioOutput:
        return SDAudioOutput(self._fpb, self._device)
