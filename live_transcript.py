"""
Live transcript via Gemini Live API — adapted from testing_daddy/src/utils/gemini.js

Architecture (same as testing_daddy):
  mic → 24kHz PCM → Gemini Live (v1alpha) → inputTranscription events
  generationComplete event → transcript string → caller (orchestrator)

Key params matched from working version:
  model:       gemini-2.5-flash-native-audio-preview-09-2025
  api_version: v1alpha
  modality:    AUDIO (with inputAudioTranscription enabled)
  sample_rate: 24000 Hz, mono, int16
"""
import asyncio
import base64
import os
import queue
import threading

import numpy as np
import sounddevice as sd
from google import genai
from google.genai import types

SAMPLE_RATE = 24000          # must match testing_daddy (24000)
CHANNELS = 1
CHUNK_SECS = 0.1             # 100ms chunks
CHUNK_FRAMES = int(SAMPLE_RATE * CHUNK_SECS)
MODEL = "gemini-2.5-flash-native-audio-preview-09-2025"


def _float32_to_pcm16(data: np.ndarray) -> bytes:
    """Convert float32 mic samples to int16 PCM bytes."""
    clipped = np.clip(data, -1.0, 1.0)
    return (clipped * 32767).astype(np.int16).tobytes()


async def record_and_transcribe() -> str:
    """
    Stream mic → Gemini Live → collect inputTranscription segments.
    Stops when generationComplete fires (Gemini detected end of speech)
    OR when user presses Enter.

    Returns the full transcript string.
    """
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("GOOGLE_API_KEY not set in .env")

    client = genai.Client(
        api_key=api_key,
        http_options={"api_version": "v1alpha"},  # required for native audio models
    )

    audio_queue: queue.Queue[bytes | None] = queue.Queue()
    transcript_parts: list[str] = []
    stop_event = asyncio.Event()
    loop = asyncio.get_event_loop()

    # --- Mic callback (runs in sounddevice thread) ---
    def mic_callback(indata: np.ndarray, frames, time_info, status):
        mono = indata[:, 0] if indata.ndim == 2 else indata
        audio_queue.put(_float32_to_pcm16(mono))

    # --- Enter key watcher ---
    def wait_for_enter():
        input("  [Enter to stop recording]\n")
        loop.call_soon_threadsafe(stop_event.set)

    config = types.LiveConnectConfig(
        response_modalities=["AUDIO"],          # same as testing_daddy responseModalities: AUDIO
        input_audio_transcription=types.AudioTranscriptionConfig(),  # enables inputTranscription events
        system_instruction=types.Content(
            parts=[types.Part(text=(
                "You are a transcription assistant. "
                "Listen carefully and transcribe exactly what the user says."
            ))]
        ),
    )

    print("\n  🎤  Listening... press Enter to stop.\n")
    threading.Thread(target=wait_for_enter, daemon=True).start()

    async with client.aio.live.connect(model=MODEL, config=config) as session:

        stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype="float32",
            blocksize=CHUNK_FRAMES,
            callback=mic_callback,
        )
        stream.start()

        # Send audio chunks to Gemini
        async def sender():
            while not stop_event.is_set():
                try:
                    chunk = audio_queue.get(timeout=0.05)
                    await session.send_realtime_input(
                        audio=types.Blob(
                            data=chunk,
                            mime_type=f"audio/pcm;rate={SAMPLE_RATE}",
                        )
                    )
                except queue.Empty:
                    await asyncio.sleep(0.01)

        # Receive transcription events from Gemini
        async def receiver():
            async for response in session.receive():
                # inputTranscription: what the user said (same as testing_daddy's onmessage handler)
                sc = response.server_content
                if sc and sc.input_transcription:
                    text = sc.input_transcription.text
                    if text and text.strip():
                        print(text, end="", flush=True)
                        transcript_parts.append(text)

                # generationComplete = Gemini detected end of speech turn
                if sc and sc.generation_complete:
                    stop_event.set()
                    break

                if stop_event.is_set():
                    break

        await asyncio.gather(sender(), receiver())
        stream.stop()
        stream.close()

    print()
    return " ".join(transcript_parts).strip()
