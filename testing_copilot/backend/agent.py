"""
Sales Copilot Backend — merged with AI_as_busness_bnp
Modes: Keywords quick-fire | Voice transcript | Classic prompt | Meeting monitor
"""
import asyncio, os, re, sys, json, requests, concurrent.futures
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from strands import Agent, tool
from strands.models import BedrockModel
from collections import deque

# ── Path ──────────────────────────────────────────────────────────────────────
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, PROJECT_ROOT)

def load_env(path):
    if not os.path.exists(path): return
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"): continue
            ps = re.match(r'\$Env:([^=]+)="([^"]*)"', line)
            if ps: os.environ.setdefault(ps.group(1), ps.group(2)); continue
            if "=" in line:
                k, _, v = line.partition("=")
                os.environ.setdefault(k.strip(), v.strip().strip('"'))

load_env(os.path.join(PROJECT_ROOT, ".env"))

GITHUB_TOKEN        = os.getenv("GITHUB_TOKEN", "")
GITHUB_DEFAULT_REPO = os.getenv("GITHUB_DEFAULT_REPO", "")

# ── Banking tools ─────────────────────────────────────────────────────────────
from agents.who_agent     import get_client_profile, get_household, get_projects
from agents.what_agent    import get_contracts, get_product_features, get_securities
from agents.when_agent    import get_contract_valuation, get_security_prices, get_market_indices
from agents.context_agent import get_financial_flows, get_events
from agents.trigger import is_trigger, QuestionExtractor

# ── GitHub tool ───────────────────────────────────────────────────────────────
@tool
def get_repo_status(repo: str = "") -> str:
    """Fetch GitHub repo status: PRs, commits, branches. Args: repo (owner/repo)."""
    target = repo.strip() or GITHUB_DEFAULT_REPO
    if not target: return "No repo specified."
    headers = {"Accept": "application/vnd.github.v3+json", "User-Agent": "SalesCopilot/1.0"}
    if GITHUB_TOKEN: headers["Authorization"] = f"Bearer {GITHUB_TOKEN}"
    if "/" not in target:
        res = requests.get(f"https://api.github.com/search/repositories?q={target}&per_page=1", headers=headers, timeout=10)
        if res.ok and res.json().get("items"): target = res.json()["items"][0]["full_name"]
        else: return f"Repo '{target}' not found."
    owner, rname = target.split("/", 1)
    base = f"https://api.github.com/repos/{owner}/{rname}"
    with concurrent.futures.ThreadPoolExecutor() as ex:
        f_r = ex.submit(requests.get, base, headers=headers, timeout=10)
        f_p = ex.submit(requests.get, f"{base}/pulls?state=open&per_page=5", headers=headers, timeout=10)
        f_c = ex.submit(requests.get, f"{base}/commits?per_page=5", headers=headers, timeout=10)
    rd = f_r.result().json(); prs = f_p.result().json() if f_p.result().ok else []; commits = f_c.result().json() if f_c.result().ok else []
    lines = [f"## {owner}/{rname}", f"Branch: {rd.get('default_branch')} | Stars: {rd.get('stargazers_count',0)}", f"Open PRs: {len(prs)}"]
    for pr in prs: lines.append(f"- #{pr['number']}: {pr['title']}")
    lines.append("Recent commits:")
    for c in commits[:3]: lines.append(f"- {c['commit']['message'].split(chr(10))[0][:60]}")
    return "\n".join(lines)

# ── Concise agent ─────────────────────────────────────────────────────────────
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
        get_repo_status,
    ],
    system_prompt=SYSTEM_PROMPT,
)

# ── Keywords catalog ──────────────────────────────────────────────────────────
KEYWORDS = [
    {"id": "portfolio",    "label": "Portfolio",     "icon": "💼", "template": "Give me a 3-bullet portfolio snapshot for {client}. Total value, biggest asset, risk profile."},
    {"id": "contracts",    "label": "Contracts",     "icon": "📋", "template": "List contracts for {client} in one line each. Product name and current value only."},
    {"id": "risk",         "label": "Risk Profile",  "icon": "⚡", "template": "What is {client}'s risk profile and market sensitivity? One sentence."},
    {"id": "goals",        "label": "Goals",         "icon": "🎯", "template": "What are {client}'s top financial goals and timeline? Max 3 bullets."},
    {"id": "recent",       "label": "Recent Events", "icon": "📅", "template": "What happened recently with {client}? Last 3 interactions or life events only."},
    {"id": "cashflow",     "label": "Cash Flow",     "icon": "💰", "template": "Quick cash flow summary for {client}: monthly income, expenses, savings capacity. 2 sentences."},
    {"id": "performance",  "label": "Performance",   "icon": "📈", "template": "How has {client}'s portfolio performed over time? Give trend in 2 sentences."},
    {"id": "profile",      "label": "Who is",        "icon": "👤", "template": "Who is {client}? Age, job, family, city, how long with the bank. 3 bullets max."},
    {"id": "securities",   "label": "Securities",    "icon": "📊", "template": "What funds and securities does {client} hold? Top 3 positions only."},
    {"id": "household",    "label": "Household",     "icon": "🏠", "template": "Family situation of {client}: spouse, children, property. 2 sentences."},
]

# ── Clients list ──────────────────────────────────────────────────────────────
def get_clients_list():
    from agents.shared import get_records
    records = get_records("01_Profil_Client")
    return [{"id": r["client_id"], "name": f"{r['prenom']} {r['nom']}", "archetype": r.get("archetype","")} for r in records]

# ── Meeting buffer ────────────────────────────────────────────────────────────
transcript_buffer: deque[str] = deque(maxlen=30)
extractor = QuestionExtractor()
_last_search: dict = {}

def _extract_text(result) -> str:
    """Extract plain text from a Strands AgentResult."""
    try:
        content = result.message["content"]
        if isinstance(content, list):
            return " ".join(b.get("text","") for b in content if isinstance(b,dict) and "text" in b).strip()
        return str(content).strip()
    except Exception:
        return str(result).strip()

async def _run_search(question: str):
    global _last_search
    try:
        result = await asyncio.to_thread(agent, question)
        _last_search = {"question": question, "response": _extract_text(result), "status": "done"}
    except Exception as e:
        _last_search = {"question": question, "error": str(e), "status": "error"}

# ── FastAPI ───────────────────────────────────────────────────────────────────
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

class Q(BaseModel): prompt: str
class Utterance(BaseModel): text: str
class QuickRequest(BaseModel): keyword_id: int; client_id: str = ""; client_name: str = ""

@app.get("/health")
def health(): return {"status": "ok"}

@app.get("/clients")
def clients():
    try: return JSONResponse(get_clients_list())
    except Exception as e: return JSONResponse({"error": str(e)}, status_code=500)

@app.get("/keywords")
def keywords(): return JSONResponse(KEYWORDS)

@app.post("/quick")
def quick(req: QuickRequest):
    """Keyword quick-fire with optional client context."""
    kw = next((k for k in KEYWORDS if k["id"] == req.keyword_id), None)
    if not kw: return JSONResponse({"error": "Unknown keyword"}, status_code=400)
    client = req.client_name or req.client_id or "the client"
    question = kw["template"].replace("{client}", client)
    if req.client_id: question += f" (client_id: {req.client_id})"
    try:
        result = agent(question)
        return JSONResponse({"response": _extract_text(result)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/ask")
def ask(req: Q):
    """Classic prompt — direct question."""
    try:
        result = agent(req.prompt)
        return JSONResponse({"response": _extract_text(result)})
    except Exception as e:
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/meeting/utterance")
async def utterance(req: Utterance):
    utt = req.text.strip()
    if not utt: return JSONResponse({"triggered": False})
    transcript_buffer.append(utt)
    if is_trigger(utt):
        snap = list(transcript_buffer)
        hit = await extractor.extract(snap)
        if hit and hit.get("question"):
            _last_search["status"] = "running"
            asyncio.create_task(_run_search(hit["question"]))
            return JSONResponse({"triggered": True, "question": hit["question"], "client_hint": hit.get("client_hint")})
    return JSONResponse({"triggered": False, "buffer_size": len(transcript_buffer)})

@app.get("/meeting/buffer")
def buffer(): return JSONResponse({"buffer": list(transcript_buffer), "size": len(transcript_buffer)})

@app.delete("/meeting/buffer")
def clear_buffer(): transcript_buffer.clear(); return JSONResponse({"status": "cleared"})

@app.get("/meeting/result")
def meeting_result(): return JSONResponse(_last_search)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 7799))
    host = "0.0.0.0" if os.getenv("PORT") else "127.0.0.1"
    print(f"[Sales Copilot] http://{host}:{port}")
    uvicorn.run(app, host=host, port=port, log_level="warning")
