"""
Trigger detection + question extraction — no bidi/sounddevice deps.
Imported by the FastAPI backend. The full meeting_monitor.py (bidi session)
imports this too, so there's no duplication.
"""
import asyncio, json, os
from difflib import SequenceMatcher

import boto3

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

def is_trigger(utterance: str) -> bool:
    utt = utterance.lower().strip()
    for phrase in TRIGGER_PHRASES:
        if phrase in utt:
            return True
        if SequenceMatcher(None, utt, phrase).ratio() >= 0.75:
            return True
    return False

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

EXTRACTOR_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"

class QuestionExtractor:
    def __init__(self):
        self._client = boto3.client(
            "bedrock-runtime",
            region_name=os.getenv("AWS_DEFAULT_REGION", "us-west-2"),
        )

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
            if "```" in text:
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
            return json.loads(text.strip())
        except Exception as e:
            print(f"[extractor error] {e}")
            return None
