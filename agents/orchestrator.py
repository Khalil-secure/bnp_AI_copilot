"""
Orchestrator Agent — routes questions to the 4 specialist agents.

WHO     → client identity, demographics, household, projects
WHAT    → contracts, products, securities held
WHEN    → valuation history, price history, market indices
CONTEXT → financial flows, events & interactions
"""
import sys
from dotenv import load_dotenv
from strands import Agent, tool

load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from .who_agent import who_agent
from .what_agent import what_agent
from .when_agent import when_agent
from .context_agent import context_agent


@tool
def ask_who(question: str) -> str:
    """
    Delegate to the WHO agent for questions about client identity, demographics,
    household situation, and financial goals/projects.

    Args:
        question: The specific question about WHO the clients are.
    """
    result = who_agent(question)
    return str(result)


@tool
def ask_what(question: str) -> str:
    """
    Delegate to the WHAT agent for questions about contracts, products,
    product features/rates, and securities or fund positions held.

    Args:
        question: The specific question about WHAT products/contracts clients hold.
    """
    result = what_agent(question)
    return str(result)


@tool
def ask_when(question: str) -> str:
    """
    Delegate to the WHEN agent for questions about time-series data:
    contract valuation history, security price history, and market index evolution.

    Args:
        question: The specific question about WHEN / time evolution of values.
    """
    result = when_agent(question)
    return str(result)


@tool
def ask_context(question: str) -> str:
    """
    Delegate to the CONTEXT agent for questions about financial flows (income,
    expenses, salary) and client interaction/event history with the bank.

    Args:
        question: The specific question about financial context or interaction history.
    """
    result = context_agent(question)
    return str(result)


orchestrator = Agent(
    system_prompt=(
        "You are the main orchestrator for a banking customer data system. "
        "You have 4 specialist agents at your disposal:\n\n"
        "- WHO agent: client identity, demographics, household, projects & goals\n"
        "- WHAT agent: contracts, products, features, securities held\n"
        "- WHEN agent: valuation history, price history, market indices\n"
        "- CONTEXT agent: financial flows, events & interactions\n\n"
        "For each user question:\n"
        "1. Identify which specialist(s) to call — a question may need multiple agents.\n"
        "2. Delegate with a precise sub-question to each relevant agent.\n"
        "3. Synthesize their answers into one clear, structured response.\n\n"
        "Always respond in the same language as the user's question."
    ),
    tools=[ask_who, ask_what, ask_when, ask_context],
)
