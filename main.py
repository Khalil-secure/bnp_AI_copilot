"""
Sales Copilot — terminal entry point
Modes: Keywords | Classic Prompt | Meeting Monitor | Voice Assistant
"""
import sys, os, asyncio, re
from dotenv import load_dotenv

load_dotenv()

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ── Path ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0, PROJECT_ROOT)

# ── Shared agent + tools (same as testing_copilot backend) ───────────────────
from strands import Agent
from strands.models import BedrockModel
from agents.who_agent     import get_client_profile, get_household, get_projects
from agents.what_agent    import get_contracts, get_product_features, get_securities
from agents.when_agent    import get_contract_valuation, get_security_prices, get_market_indices
from agents.context_agent import get_financial_flows, get_events

SYSTEM_PROMPT = """You are Sales Copilot — AI assistant for a banker in a LIVE client meeting.

CRITICAL RULES:
- Max 3 bullet points. No tables. No raw numbers dump.
- Round numbers: €50k not €50,000.
- Start with the single most important fact.
- Speak like a colleague whispering a quick briefing, not a report.
- Same language as the question (FR or EN).

GOOD example: "Mathieu holds €754k total. Biggest chunk: life insurance (€443k, dynamic profile). 3 projects: retirement, wealth transfer, secondary home."
BAD example: [any table or list longer than 3 items]
"""

model = BedrockModel(
    model_id="us.anthropic.claude-sonnet-4-5-20250929-v1:0",
    region_name=os.getenv("AWS_DEFAULT_REGION", "us-west-2"),
)

agent = Agent(
    model=model,
    tools=[
        get_client_profile, get_household, get_projects,
        get_contracts, get_product_features, get_securities,
        get_contract_valuation, get_security_prices, get_market_indices,
        get_financial_flows, get_events,
    ],
    system_prompt=SYSTEM_PROMPT,
)

# ── Keywords catalog ──────────────────────────────────────────────────────────
KEYWORDS = [
    {"id":  1, "label": "Portfolio",     "icon": "💼", "template": "Give me a 3-bullet portfolio snapshot for {client}. Total value, biggest asset, risk profile."},
    {"id":  2, "label": "Contracts",     "icon": "📋", "template": "List contracts for {client} in one line each. Product name and current value only."},
    {"id":  3, "label": "Risk Profile",  "icon": "⚡", "template": "What is {client}'s risk profile and market sensitivity? One sentence."},
    {"id":  4, "label": "Goals",         "icon": "🎯", "template": "What are {client}'s top financial goals and timeline? Max 3 bullets."},
    {"id":  5, "label": "Recent Events", "icon": "📅", "template": "What happened recently with {client}? Last 3 interactions or life events only."},
    {"id":  6, "label": "Cash Flow",     "icon": "💰", "template": "Quick cash flow summary for {client}: monthly income, expenses, savings capacity. 2 sentences."},
    {"id":  7, "label": "Performance",   "icon": "📈", "template": "How has {client}'s portfolio performed over time? Give trend in 2 sentences."},
    {"id":  8, "label": "Who is",        "icon": "👤", "template": "Who is {client}? Age, job, family, city, how long with the bank. 3 bullets max."},
    {"id":  9, "label": "Securities",    "icon": "📊", "template": "What funds and securities does {client} hold? Top 3 positions only."},
    {"id": 10, "label": "Household",     "icon": "🏠", "template": "Family situation of {client}: spouse, children, property. 2 sentences."},
]

# ── Helpers ───────────────────────────────────────────────────────────────────
BANNER = """
╔══════════════════════════════════════════════════════╗
║          SALES COPILOT  —  BNP Paribas               ║
╠══════════════════════════════════════════════════════╣
║  WHO · WHAT · WHEN · CONTEXT  agents on demand       ║
╚══════════════════════════════════════════════════════╝"""

SEP = "─" * 54

def _extract_text(result) -> str:
    try:
        content = result.message["content"]
        if isinstance(content, list):
            return " ".join(b.get("text", "") for b in content if isinstance(b, dict) and "text" in b).strip()
        return str(content).strip()
    except Exception:
        return str(result).strip()

def _ask(question: str) -> None:
    print(f"\n  ⏳  Searching…\n")
    try:
        result = agent(question)
        print(SEP)
        print(_extract_text(result))
        print(SEP)
    except Exception as e:
        print(f"  ❌  {e}")

def get_clients_list():
    from agents.shared import get_records
    records = get_records("01_Profil_Client")
    return [{"id": r["client_id"], "name": f"{r['prenom']} {r['nom']}", "archetype": r.get("archetype", "")} for r in records]

def pick_client(clients) -> dict:
    """Interactive client selector. Returns {id, name} or empty dict."""
    print(f"\n  Clients on file:")
    for i, c in enumerate(clients, 1):
        arch = f"  [{c['archetype']}]" if c.get("archetype") else ""
        print(f"    [{i:2}]  {c['name']}{arch}")
    print(f"    [ 0]  No specific client")
    try:
        choice = int(input("\n  Pick client number: ").strip())
        if choice == 0:
            return {}
        return clients[choice - 1]
    except (ValueError, IndexError):
        return {}

# ── Mode: Keywords ────────────────────────────────────────────────────────────
def run_keywords(clients):
    print(f"\n{SEP}")
    print("  KEYWORDS MODE  —  quick data shots")
    print(SEP)

    client = pick_client(clients)
    client_label = client.get("name", "the client")
    client_suffix = f" (client_id: {client['id']})" if client.get("id") else ""

    while True:
        print(f"\n  Client: {client_label}")
        print(f"\n  Keywords:")
        for kw in KEYWORDS:
            print(f"    [{kw['id']:2}]  {kw['icon']}  {kw['label']}")
        print(f"\n    [ c]  Change client")
        print(f"    [ b]  Back to main menu")

        raw = input("\n  Pick keyword: ").strip().lower()
        if raw == "b":
            break
        if raw == "c":
            client = pick_client(clients)
            client_label = client.get("name", "the client")
            client_suffix = f" (client_id: {client['id']})" if client.get("id") else ""
            continue

        try:
            kw_id = int(raw)
            kw = next((k for k in KEYWORDS if k["id"] == kw_id), None)
            if not kw:
                print("  Unknown keyword.")
                continue
            question = kw["template"].replace("{client}", client_label) + client_suffix
            print(f"\n  {kw['icon']}  {kw['label']} — {client_label}")
            _ask(question)
        except ValueError:
            print("  Enter a number.")

# ── Mode: Classic Prompt ──────────────────────────────────────────────────────
def run_classic(clients):
    print(f"\n{SEP}")
    print("  CLASSIC PROMPT  —  ask anything")
    print(SEP)

    client = pick_client(clients)
    client_label = client.get("name", "")
    client_suffix = f" (client_id: {client['id']})" if client.get("id") else ""

    print(f"\n  Client context: {client_label or 'none'}")
    print(f"  Type your question. Commands: 'client' to change, 'back' to exit.\n")

    while True:
        try:
            raw = input("  You: ").strip()
        except KeyboardInterrupt:
            break

        if not raw:
            continue
        if raw.lower() in ("back", "b", "exit", "quit"):
            break
        if raw.lower() == "client":
            client = pick_client(clients)
            client_label = client.get("name", "")
            client_suffix = f" (client_id: {client['id']})" if client.get("id") else ""
            print(f"  Client: {client_label or 'none'}\n")
            continue

        question = (f"[Client: {client_label}] {raw}{client_suffix}") if client_label else raw
        _ask(question)

# ── Mode: Meeting Monitor ─────────────────────────────────────────────────────
async def run_meeting():
    from agents.meeting_monitor import run_meeting_session
    await run_meeting_session()

# ── Mode: Voice Assistant ─────────────────────────────────────────────────────
async def run_voice():
    from agents.nova_sonic_session import run_nova_sonic_session
    await run_nova_sonic_session()

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    print(BANNER)

    print("\n  Loading clients…")
    try:
        clients = get_clients_list()
        print(f"  ✓ {len(clients)} clients loaded")
    except Exception as e:
        print(f"  ⚠  Could not load clients: {e}")
        clients = []

    MENU = f"""
{SEP}
  SELECT MODE
{SEP}
    [1]  💼  Keywords        — one-tap data shots for a client
    [2]  ⌨   Classic Prompt  — free-form question
    [3]  🎙   Meeting Monitor — listens live, triggers on voice command
    [4]  🔊   Voice Assistant — speak to Nova Sonic
    [0]  Exit
{SEP}
  Choice: """

    while True:
        try:
            choice = input(MENU).strip()
        except KeyboardInterrupt:
            print("\n  Goodbye!")
            break

        if choice == "1":
            run_keywords(clients)
        elif choice == "2":
            run_classic(clients)
        elif choice == "3":
            asyncio.run(run_meeting())
        elif choice == "4":
            asyncio.run(run_voice())
        elif choice == "0":
            print("\n  Goodbye!")
            break
        else:
            print("  Invalid choice.")

if __name__ == "__main__":
    main()
