"""
WHO Agent — sheets 01, 02, 03
Handles: Client Profile, Household, Projects & Goals
Granularity: 1 row per client / 1 row per project
"""
from strands import Agent, tool
from .shared import get_records, to_json


@tool
def get_client_profile(client_id: str = None) -> str:
    """
    Get client profile data (sheet 01). Returns all clients or one if client_id given.

    Args:
        client_id: Optional — e.g. 'CLI00001'. Omit to get all clients.
    """
    records = get_records("01_Profil_Client", "client_id", client_id) if client_id else get_records("01_Profil_Client")
    return to_json(records)


@tool
def get_household(client_id: str = None) -> str:
    """
    Get household / family situation data (sheet 02).

    Args:
        client_id: Optional — e.g. 'CLI00001'. Omit to get all.
    """
    records = get_records("02_Foyer", "client_id", client_id) if client_id else get_records("02_Foyer")
    return to_json(records)


@tool
def get_projects(client_id: str = None) -> str:
    """
    Get client projects and financial goals (sheet 03).

    Args:
        client_id: Optional — e.g. 'CLI00001'. Omit to get all.
    """
    records = get_records("03_Projets_Objectifs", "client_id", client_id) if client_id else get_records("03_Projets_Objectifs")
    return to_json(records)


who_agent = Agent(
    system_prompt=(
        "You are a WHO specialist. You answer questions about banking clients' identity, "
        "demographics, family situation, and financial goals. "
        "You have access to 3 sheets: client profiles (01), household data (02), and projects/goals (03). "
        "Always respond concisely in the same language as the question."
    ),
    tools=[get_client_profile, get_household, get_projects],
)
