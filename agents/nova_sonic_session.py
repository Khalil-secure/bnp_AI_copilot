"""
Nova Sonic voice session — BidiAgent wired with our 4 banking specialist agents.
Uses SDBidiAudioIO (sounddevice) instead of pyaudio (no Python 3.14 wheel).

Nova Sonic is only available in: us-east-1 | eu-north-1 | ap-northeast-1
"""
import asyncio
import os
import sys

import boto3
from strands.experimental.bidi import BidiAgent
from strands.experimental.bidi.io import BidiTextIO
from strands.experimental.bidi.models import BidiNovaSonicModel
from strands_tools import stop

from .bidi_audio_sd import SDBidiAudioIO
from .who_agent import get_client_profile, get_household, get_projects
from .what_agent import get_contracts, get_product_features, get_securities
from .when_agent import get_contract_valuation, get_security_prices, get_market_indices
from .context_agent import get_financial_flows, get_events

NOVA_SONIC_REGION = "us-east-1"   # Nova Sonic not available in us-west-2

SYSTEM_PROMPT = """
You are a voice-enabled banking intelligence assistant for BNP Paribas.
You have access to a complete banking customer database with 10 clients.

Your tools cover 4 data domains:
- WHO: client profiles, household info, financial goals
- WHAT: contracts, product features, securities held
- WHEN: valuation history, price history, market indices
- CONTEXT: financial flows, interaction events

Answer in the same language the user speaks. Be concise and speak naturally
since your response will be read aloud. Avoid markdown formatting in voice responses.
""".strip()


async def run_nova_sonic_session() -> None:
    """Launch full voice session: mic → Nova Sonic → tools → speaker."""

    # Build boto3 session pointing to us-east-1 (required for Nova Sonic)
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
            "inference": {"temperature": 0.7, "top_p": 0.9},
        },
        client_config={"boto_session": boto_session},
    )

    # All 11 sheet tools + stop (lets user say "stop" to end)
    all_tools = [
        get_client_profile, get_household, get_projects,
        get_contracts, get_product_features, get_securities,
        get_contract_valuation, get_security_prices, get_market_indices,
        get_financial_flows, get_events,
        stop,
    ]

    agent = BidiAgent(
        model=model,
        tools=all_tools,
        system_prompt=SYSTEM_PROMPT,
    )

    audio_io = SDBidiAudioIO()
    text_io = BidiTextIO()

    print("\n  🎙  Nova Sonic session started — speak now.")
    print("  Say 'stop' to end the session.\n")

    await agent.run(
        inputs=[audio_io.input()],
        outputs=[audio_io.output(), text_io.output()],
    )
