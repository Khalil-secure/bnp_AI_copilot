"""
WHEN Agent — sheets 07, 08, 09
Handles: Contract Valuation History, Security Price History, Market Indices
Granularity: 1 row per contract/ISIN/index per month
"""
from strands import Agent, tool
from .shared import get_records, to_json


@tool
def get_contract_valuation(client_id: str = None, contrat_id: str = None,
                            date_from: str = None, date_to: str = None) -> str:
    """
    Get monthly contract valuation history (sheet 07).

    Args:
        client_id: Optional filter by client.
        contrat_id: Optional filter by contract ID.
        date_from: Optional start date filter 'YYYY-MM-DD'.
        date_to: Optional end date filter 'YYYY-MM-DD'.
    """
    records = get_records("07_Histo_Valo_Contrats", "client_id", client_id) if client_id else get_records("07_Histo_Valo_Contrats")
    if contrat_id:
        records = [r for r in records if str(r.get("contrat_id", "")) == contrat_id]
    if date_from:
        records = [r for r in records if str(r.get("date", "")) >= date_from]
    if date_to:
        records = [r for r in records if str(r.get("date", "")) <= date_to]
    return to_json(records)


@tool
def get_security_prices(isin: str = None, date_from: str = None, date_to: str = None) -> str:
    """
    Get monthly NAV / price history per ISIN (sheet 08).

    Args:
        isin: Optional filter by ISIN code.
        date_from: Optional start date filter 'YYYY-MM-DD'.
        date_to: Optional end date filter 'YYYY-MM-DD'.
    """
    records = get_records("08_Histo_VL_Supports", "isin", isin) if isin else get_records("08_Histo_VL_Supports")
    if date_from:
        records = [r for r in records if str(r.get("date", "")) >= date_from]
    if date_to:
        records = [r for r in records if str(r.get("date", "")) <= date_to]
    return to_json(records)


@tool
def get_market_indices(index_code: str = None, date_from: str = None, date_to: str = None) -> str:
    """
    Get monthly market index values (sheet 09 — e.g. CAC40, MSCI World).

    Args:
        index_code: Optional filter by index code.
        date_from: Optional start date filter 'YYYY-MM-DD'.
        date_to: Optional end date filter 'YYYY-MM-DD'.
    """
    records = get_records("09_Indices_Marche", "code_indice", index_code) if index_code else get_records("09_Indices_Marche")
    if date_from:
        records = [r for r in records if str(r.get("date", "")) >= date_from]
    if date_to:
        records = [r for r in records if str(r.get("date", "")) <= date_to]
    return to_json(records)


when_agent = Agent(
    system_prompt=(
        "You are a WHEN specialist. You answer questions about time-series financial data: "
        "contract valuations over time, security/fund price histories, and market index evolution. "
        "You have access to 3 sheets: contract valuation history (07), security price history (08), "
        "and market indices (09). "
        "When analyzing trends, compare earliest vs latest values and highlight key movements. "
        "Always respond concisely in the same language as the question."
    ),
    tools=[get_contract_valuation, get_security_prices, get_market_indices],
)
