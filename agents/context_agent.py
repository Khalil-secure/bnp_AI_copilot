"""
CONTEXT Agent — sheets 10, 11
Handles: Financial Flows, Events & Interactions
Granularity: 1 row per client per month / 1 row per event
"""
from strands import Agent, tool
from .shared import get_records, to_json


@tool
def get_financial_flows(client_id: str = None, date_from: str = None, date_to: str = None) -> str:
    """
    Get monthly financial flow data: income, salary, bonuses, expenses (sheet 10).

    Args:
        client_id: Optional filter by client.
        date_from: Optional start date filter 'YYYY-MM-DD'.
        date_to: Optional end date filter 'YYYY-MM-DD'.
    """
    records = get_records("10_Flux_Financiers", "client_id", client_id) if client_id else get_records("10_Flux_Financiers")
    if date_from:
        records = [r for r in records if str(r.get("date", "")) >= date_from]
    if date_to:
        records = [r for r in records if str(r.get("date", "")) <= date_to]
    return to_json(records)


@tool
def get_events(client_id: str = None, event_type: str = None,
               category: str = None, date_from: str = None, date_to: str = None) -> str:
    """
    Get client interaction and life events (sheet 11 — e.g. advisor meetings, complaints, life changes).

    Args:
        client_id: Optional filter by client.
        event_type: Optional filter by event type (e.g. 'Rendez-vous', 'Réclamation').
        category: Optional filter by category.
        date_from: Optional start date filter 'YYYY-MM-DD'.
        date_to: Optional end date filter 'YYYY-MM-DD'.
    """
    records = get_records("11_Evenements_Interact", "client_id", client_id) if client_id else get_records("11_Evenements_Interact")
    if event_type:
        records = [r for r in records if event_type.lower() in str(r.get("type", "")).lower()]
    if category:
        records = [r for r in records if category.lower() in str(r.get("categorie", "")).lower()]
    if date_from:
        records = [r for r in records if str(r.get("date", "")) >= date_from]
    if date_to:
        records = [r for r in records if str(r.get("date", "")) <= date_to]
    return to_json(records)


context_agent = Agent(
    system_prompt=(
        "You are a CONTEXT specialist. You answer questions about the financial and relational context "
        "around banking clients: their monthly income and expense flows, and their interaction history "
        "with the bank (meetings, complaints, life events, digital activity). "
        "You have access to 2 sheets: financial flows (10) and events/interactions (11). "
        "Always respond concisely in the same language as the question."
    ),
    tools=[get_financial_flows, get_events],
)
