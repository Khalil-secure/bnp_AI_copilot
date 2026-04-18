"""
WHAT Agent — sheets 04, 05, 06
Handles: Contracts & Products, Product Features, Securities Held
Granularity: 1 row per contract / 1 row per position
"""
from strands import Agent, tool
from .shared import get_records, to_json


@tool
def get_contracts(client_id: str = None, product_family: str = None) -> str:
    """
    Get contracts and products held by clients (sheet 04).

    Args:
        client_id: Optional filter by client, e.g. 'CLI00001'.
        product_family: Optional filter by family e.g. 'Assurance-vie', 'Livret', 'PEA'.
    """
    records = get_records("04_Contrats_Produits", "client_id", client_id) if client_id else get_records("04_Contrats_Produits")
    if product_family:
        records = [r for r in records if product_family.lower() in str(r.get("famille_produit", "")).lower()]
    return to_json(records)


@tool
def get_product_features(client_id: str = None, contrat_id: str = None) -> str:
    """
    Get product characteristics and rates (sheet 05).

    Args:
        client_id: Optional filter by client.
        contrat_id: Optional filter by specific contract ID.
    """
    records = get_records("05_Caracteristiques", "client_id", client_id) if client_id else get_records("05_Caracteristiques")
    if contrat_id:
        records = [r for r in records if str(r.get("contrat_id", "")) == contrat_id]
    return to_json(records)


@tool
def get_securities(client_id: str = None, isin: str = None) -> str:
    """
    Get securities / fund positions held by clients (sheet 06).

    Args:
        client_id: Optional filter by client.
        isin: Optional filter by ISIN code.
    """
    records = get_records("06_Supports_Detenus", "client_id", client_id) if client_id else get_records("06_Supports_Detenus")
    if isin:
        records = [r for r in records if str(r.get("isin", "")) == isin]
    return to_json(records)


what_agent = Agent(
    system_prompt=(
        "You are a WHAT specialist. You answer questions about banking products, contracts, "
        "product features, rates, and securities/fund positions held by clients. "
        "You have access to 3 sheets: contracts (04), product features (05), and securities held (06). "
        "Always respond concisely in the same language as the question."
    ),
    tools=[get_contracts, get_product_features, get_securities],
)
