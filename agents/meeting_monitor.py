"""
Meeting Monitor — two independent agents:

  TRANSCRIPT AGENT  : Nova Sonic listens continuously, builds a rolling transcript buffer.
  ORCHESTRATOR      : Reads the buffer and fires WHO/WHAT/WHEN/CONTEXT in parallel —
                      ONLY when the user says a trigger command.

Trigger phrases (said aloud during the meeting):
  "let's bring this data up"   |  "bring the data up"
  "let's dive deeper"          |  "dive deeper"
  "i have the data with me"    |  "pull that up"
  "show me the data"           |  "let's look at the numbers"
  "check the client data"      |  "run the search"
"""
import asyncio
import json
import os
from collections import deque
from datetime import datetime
from difflib import SequenceMatcher
from typing import TYPE_CHECKING

import boto3
from strands.experimental.bidi import BidiAgent
from strands.experimental.bidi.io import BidiTextIO
from strands.experimental.bidi.models import BidiNovaSonicModel
from strands.experimental.bidi.types.events import (
    BidiConnectionCloseEvent,
    BidiOutputEvent,
    BidiTranscriptStreamEvent,
)
from strands.experimental.bidi.types.io import BidiOutput
from strands_tools import stop

from .bidi_audio_sd import SDBidiAudioIO
from .who_agent import who_agent
from .what_agent import what_agent
from .when_agent import when_agent
from .context_agent import context_agent

if TYPE_CHECKING:
    from strands.experimental.bidi.agent.agent import BidiAgent as BidiAgentType

# ── Config ────────────────────────────────────────────────────────────────────

NOVA_SONIC_REGION = "us-east-1"
EXTRACTOR_MODEL   = "us.anthropic.claude-haiku-4-5-20251001-v1:0"  # cross-region inference profile
BUFFER_MAX        = 30   # keep last 30 utterances in the rolling window

MEETING_SYSTEM_PROMPT = """
You are a silent transcription assistant monitoring a banking sales meeting.
Your ONLY job is to transcribe what is said. Do NOT speak or respond.
Stay completely silent — just transcribe faithfully.
""".strip()

# ── Trigger phrase detection ──────────────────────────────────────────────────

TRIGGER_PHRASES = [
    "let's bring this data up",
    "bring the data up",
    "bring up the data",
    "let's dive deeper",
    "dive deeper",
    "i have the data with me",
    "pull that up",
    "pull up the data",
    "show me the data",
    "let's look at the numbers",
    "check the client data",
    "run the search",
    "get the data",
    "look up the client",
    "check the file",
]

def _similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()

def is_trigger(utterance: str) -> bool:
    """Return True if utterance closely matches any trigger phrase."""
    utt = utterance.lower().strip()
    for phrase in TRIGGER_PHRASES:
        # exact substring match
        if phrase in utt:
            return True
        # fuzzy match for close pronunciations (threshold 0.75)
        if _similarity(utt, phrase) >= 0.75:
            return True
    return False

# ── Question extractor ────────────────────────────────────────────────────────

EXTRACTOR_PROMPT = """\
You are analysing a transcript of a banking sales meeting.
The user just said a trigger command to look up client data.

Recent meeting transcript (chronological):
{transcript}

Based on this transcript, identify:
1. Which client(s) are being discussed (name, ID, or description)
2. What specific data or question needs to be answered

Return ONLY valid JSON:
{{
  "question": "a clear, specific question for a banking data agent",
  "client_hint": "client name or ID if identifiable, else null",
  "data_needed": ["list", "of", "data", "types", "needed"]
}}
"""

class QuestionExtractor:
    """Uses Claude Haiku to extract the relevant question from the transcript buffer."""

    def __init__(self):
        self._client = boto3.client("bedrock-runtime", region_name="us-west-2")

    async def extract(self, buffer: list[str]) -> dict | None:
        transcript = "\n".join(f"- {u}" for u in buffer)
        prompt = EXTRACTOR_PROMPT.format(transcript=transcript)

        try:
            response = await asyncio.to_thread(
                self._client.converse,
                modelId=EXTRACTOR_MODEL,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 300, "temperature": 0.1},
            )
            text = response["output"]["message"]["content"][0]["text"].strip()
            # Strip markdown fences if present
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            print(f"\n  [extractor error] {e}")
            return None

# ── Parallel agent runner ─────────────────────────────────────────────────────

async def run_parallel_agents(question: str) -> None:
    """Fire WHO / WHAT / WHEN / CONTEXT agents in parallel and print results."""

    async def call(label, agent, q):
        try:
            result = await asyncio.to_thread(agent, q)
            return label, str(result).strip()
        except Exception as e:
            return label, f"[error: {e}]"

    tasks = [
        asyncio.create_task(call("WHO",     who_agent,     question)),
        asyncio.create_task(call("WHAT",    what_agent,    question)),
        asyncio.create_task(call("WHEN",    when_agent,    question)),
        asyncio.create_task(call("CONTEXT", context_agent, question)),
    ]

    print(f"\n  ⚡  Agents running in parallel...\n")

    # Print each result as it completes (don't wait for all)
    for coro in asyncio.as_completed(tasks):
        label, result = await coro
        if result:
            print(f"{'─'*50}")
            print(f"  [{label}]")
            print(f"{'─'*50}")
            print(result)
            print()

# ── Custom BidiOutput — the meeting monitor ───────────────────────────────────

class MeetingMonitorOutput(BidiOutput):
    """
    Intercepts transcript events from Nova Sonic.
    Builds a rolling buffer of utterances.
    When a trigger phrase is detected → extracts question → fires agents in parallel.
    """

    def __init__(self):
        self._buffer: deque[str] = deque(maxlen=BUFFER_MAX)
        self._extractor = QuestionExtractor()
        self._active_tasks: set = set()
        self._cooldown = False   # prevent double-firing on rapid re-trigger

    async def start(self, agent: "BidiAgentType") -> None:
        print("\n" + "═"*56)
        print("  🎙  TRANSCRIPT AGENT  — listening to the meeting")
        print("  📋  Building rolling transcript buffer...")
        print()
        print("  Say one of these to trigger data lookup:")
        for phrase in TRIGGER_PHRASES[:6]:
            print(f"    • \"{phrase}\"")
        print("  ...")
        print("═"*56 + "\n")

    async def stop(self) -> None:
        if self._active_tasks:
            await asyncio.gather(*self._active_tasks, return_exceptions=True)

    async def __call__(self, event: BidiOutputEvent) -> None:
        if isinstance(event, BidiTranscriptStreamEvent):
            if event.role == "user":
                if not event.is_final:
                    print(f"\r  [live] {event.text[:70]}...", end="", flush=True)
                else:
                    utterance = event.text.strip()
                    if not utterance:
                        return

                    ts = datetime.now().strftime("%H:%M:%S")
                    print(f"\r  [{ts}] \"{utterance}\"")

                    # Add to rolling buffer
                    self._buffer.append(utterance)

                    # Check for trigger phrase
                    if is_trigger(utterance) and not self._cooldown:
                        task = asyncio.create_task(self._handle_trigger())
                        self._active_tasks.add(task)
                        task.add_done_callback(self._active_tasks.discard)

        elif isinstance(event, BidiConnectionCloseEvent):
            print(f"\n  [session closed: {event.reason}]")

    async def _handle_trigger(self) -> None:
        """Extract question from buffer and fire orchestrator."""
        self._cooldown = True

        print(f"\n{'═'*56}")
        print(f"  🚀  TRIGGER DETECTED — reading transcript buffer")
        print(f"  📝  Buffer: {len(self._buffer)} utterances")
        print(f"{'═'*56}")

        buffer_snapshot = list(self._buffer)

        # Extract what question to answer
        hit = await self._extractor.extract(buffer_snapshot)

        if not hit or not hit.get("question"):
            print("  ⚠️  Could not extract a clear question from the transcript.")
            self._cooldown = False
            return

        question     = hit["question"]
        client_hint  = hit.get("client_hint") or "not identified"
        data_needed  = ", ".join(hit.get("data_needed", []))

        print(f"\n  ❓  Question : {question}")
        print(f"  👤  Client   : {client_hint}")
        print(f"  📊  Data     : {data_needed}")
        print(f"\n{'═'*56}\n")

        # Fire all 4 agents in parallel
        await run_parallel_agents(question)

        print(f"{'═'*56}")
        print(f"  ✅  Search complete — back to listening\n")

        # Cooldown: wait 5s before allowing another trigger
        await asyncio.sleep(5)
        self._cooldown = False

# ── Session entry point ───────────────────────────────────────────────────────

async def run_meeting_session() -> None:
    boto_session = boto3.Session(
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        aws_session_token=os.environ.get("AWS_SESSION_TOKEN"),
        region_name=NOVA_SONIC_REGION,
    )

    model = BidiNovaSonicModel(
        model_id="amazon.nova-sonic-v1:0",
        provider_config={
            "audio": {"voice": "tiffany"},
            "inference": {"temperature": 0.1},
        },
        client_config={"boto_session": boto_session},
    )

    # Transcript agent — silent, just listens
    agent = BidiAgent(
        model=model,
        tools=[stop],
        system_prompt=MEETING_SYSTEM_PROMPT,
    )

    audio_io    = SDBidiAudioIO()
    monitor_out = MeetingMonitorOutput()

    await agent.run(
        inputs=[audio_io.input()],
        outputs=[monitor_out],
    )
