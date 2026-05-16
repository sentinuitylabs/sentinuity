"""
===========================================================================
The organism thinking visibly.
Psilocybin-Rich Synthetic Singularity // Cybernetic Glass Box // Fungal Bloom
"""

import base64
import json
import sqlite3
import time
import html
import os
import re
from urllib.parse import urlparse
from pathlib import Path

import pandas as pd
import requests as _requests
import streamlit as st
import streamlit.components.v1 as components
try:
    from council_build_map import get_build_map as _get_build_map
    _BUILD_MAP_AVAILABLE = True
except Exception:
    _BUILD_MAP_AVAILABLE = False

# ── PERFORMANCE GATE: heavy visuals toggle ────────────────────────────────────
# Set UI_HEAVY_VISUALS_ENABLED=false in system_config or .env to disable
# the 3D mycelial nexus and cognitive canopy canvas on slow/mobile devices.
# All visual code is preserved — only render calls are gated.
def _heavy_visuals_enabled() -> bool:
    try:
        import sqlite3 as _sq3h
        _hc = _sq3h.connect(str(DB_PATH), timeout=2)
        _hv = _hc.execute(
            "SELECT value FROM system_config WHERE key='UI_HEAVY_VISUALS_ENABLED'"
        ).fetchone()
        _hc.close()
        if _hv and str(_hv[0]).lower() in ("false", "0", "no", "off"):
            return False
    except Exception:
        pass
    import os
    return os.getenv("UI_HEAVY_VISUALS_ENABLED", "true").lower() not in ("false", "0", "no", "off")

try:
    from streamlit import fragment
except ImportError:
    def fragment(run_every=None):
        def decorator(func): return func
        return decorator

import sys as _sys
from pathlib import Path as _Path
_ROOT = _Path(__file__).resolve().parent.parent
if str(_ROOT) not in _sys.path:
    _sys.path.insert(0, str(_ROOT))

from components.mycelial_nexus import mycelial_nexus

try:
    from ui.intelligence_tab import render_intelligence_tab as _render_intelligence_tab
    _INTELLIGENCE_TAB_AVAILABLE = True
except ImportError:
    _INTELLIGENCE_TAB_AVAILABLE = False

try:
    from services.price_router import get_ui_price as _router_ui_price
    _PRICE_ROUTER_AVAILABLE = True
except ImportError:
    _PRICE_ROUTER_AVAILABLE = False
    def _router_ui_price(mint, entry_price, opened_at): return None


heartbeat_df = pd.DataFrame()  # defensive fallback for moved render blocks


wallet_df = pd.DataFrame()
raw_dna_df = pd.DataFrame()
snapshots_df = pd.DataFrame()
open_pos_df = pd.DataFrame()
executions_df = pd.DataFrame()
reviews_df = pd.DataFrame()
proposals_df = pd.DataFrame()
debate_df = pd.DataFrame()
calibration_df = pd.DataFrame()
open_count_df = pd.DataFrame()
heal_log_df = pd.DataFrame()
heartbeat_df = pd.DataFrame()
patch_history_df = pd.DataFrame()
autopsy_df = pd.DataFrame()
cognition_df = pd.DataFrame()

st.set_page_config(page_title="SENTINUITY SOVEREIGN HUB", layout="wide", initial_sidebar_state="collapsed")

# ── DIRECT INTEL PRICE READ (Same-Eyes v2) ────────────────────────────────────
def _get_fresh_intel_price(mint: str):
    """
    Read the latest oracle tick directly from sentinuity_intelligence.db.
    Bypasses the engine's 2.2s write cycle — gives the meter direct oracle visibility.
    Returns (price_usd, age_seconds) or (None, None).
    """
    try:
        _idb = str(Path(__file__).resolve().parent.parent / "sentinuity_intelligence.db")
        with sqlite3.connect(_idb, timeout=1.0) as _ic:
            _row = _ic.execute(
                "SELECT price_usd, ts_ms FROM mtm_ticks "
                "WHERE mint_address=? ORDER BY ts_ms DESC LIMIT 1",
                (mint,)
            ).fetchone()
            if _row and _row[0]:
                _age = time.time() - float(_row[1]) / 1000.0
                return float(_row[0]), _age
    except Exception:
        pass
    return None, None


# ── PHANTOM WALLET CONNECT ────────────────────────────────────────────────────
def _write_phantom_state(wallet_address: str, trading_mode: str = "") -> None:
    """
    Write Phantom wallet address to DB.
    NEVER overwrites TRADING_MODE — that is set only by set_live_mode.py / operator.
    """
    try:
        import sqlite3
        from pathlib import Path as _P
        _db = str(_P(__file__).resolve().parent.parent / "sentinuity_matrix.db")
        _c = sqlite3.connect(_db, timeout=5)
        _c.execute(
            "INSERT OR REPLACE INTO system_config (key,value,description) "
            "VALUES ('PHANTOM_WALLET_ADDRESS',?,'Connected Phantom wallet address')",
            (wallet_address,)
        )
        # NOTE: TRADING_MODE is intentionally NOT written here.
        # Use set_live_mode.py to switch between paper and live.
        _c.commit()
        _c.close()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# SHARED HEALTH TRUTH — single source for both HUD strip and Vitality table
# Core services (red if stale): executor, supervisor, market_intelligence,
#   oracle_autoheal / ws_price_oracle, polaris, sovereign_governor
# Scout services (amber only): telegram, x_scout, wallet_scout, copytrade
# ─────────────────────────────────────────────────────────────────────────────
CORE_SERVICES = {
    "execution_engine":  "EXECUTOR",
    "neural_supervisor": "SUPERVISOR",
    "market_intelligence": "MARKET_INTEL",
    "oracle_autoheal":   "ORACLE",
    "ws_price_oracle":   "ORACLE",
    "polaris":           "POLARIS",
    "sovereign_governor":"GOVERNOR",
    "system_guardian":   "GUARDIAN",
}
SCOUT_SERVICES = {"telegram_scout","x_scout","wallet_scout","reconnaissance_engine","code_vault"}

def _get_service_health(query_db_fn=None):
    """
    Returns dict: service_name → {status, age_s, is_core, is_stale, label}
    Stale threshold: 120s for core, 420s for scouts.
    """
    import time as _t, sqlite3 as _sq
    now = _t.time()
    result = {}
    try:
        _db = _sq.connect(str(DB_PATH), timeout=3)
        _db.row_factory = _sq.Row
        rows = _db.execute(
            "SELECT service_name, last_pulse, status, note FROM system_heartbeat ORDER BY last_pulse DESC"
        ).fetchall()
        _db.close()
        for r in rows:
            svc   = str(r["service_name"] or "")
            pulse = float(r["last_pulse"] or 0)
            age   = now - pulse if pulse else 9999
            stat  = str(r["status"] or "UNKNOWN").upper()
            note  = str(r["note"] or "")[:60]
            is_core  = svc in CORE_SERVICES
            is_scout = svc in SCOUT_SERVICES
            threshold = 120 if is_core else 420
            is_stale = age > threshold
            if svc not in result or age < result[svc]["age_s"]:
                result[svc] = {
                    "status":    stat,
                    "age_s":     age,
                    "note":      note,
                    "is_core":   is_core,
                    "is_scout":  is_scout,
                    "is_stale":  is_stale,
                    "label":     CORE_SERVICES.get(svc, svc.upper().replace("_"," ")),
                }
    except Exception:
        pass
    return result

def _hud_health_state(health: dict):
    """
    Returns (is_ok, color, label) for the top HUD strip.
    Only core services can turn HUD red.
    """
    stale_core = [v for v in health.values() if v["is_core"] and v["is_stale"]]
    if not health:
        return False, "#FFD700", "⚠ AWAITING HEARTBEAT — SERVICES STARTING"
    if stale_core:
        names = " · ".join(v["label"] for v in stale_core[:2])
        return False, "#FF073A", f"⚠ SENSORY DISSONANCE — {names} STALE/OFFLINE"
    return True, "#14F195", "✓ ORGANISM SYNCED — ALL FEEDS FRESH"

def render_phantom_connect():
    import streamlit.components.v1 as _components
    _waddr, _tmode = "", "paper"
    try:
        _r = query_db("SELECT key, value FROM system_config WHERE key IN ('PHANTOM_WALLET_ADDRESS','TRADING_MODE')")
        if not _r.empty:
            for _, _row in _r.iterrows():
                if _row["key"] == "PHANTOM_WALLET_ADDRESS": _waddr = str(_row["value"] or "")
                if _row["key"] == "TRADING_MODE": _tmode = str(_row["value"] or "paper")
    except Exception: pass
    _short  = f"{_waddr[:4]}...{_waddr[-4:]}" if len(_waddr) > 8 else ""
    _is_live = _tmode == "live"
    _bc = "#14F195" if _short else "#9945FF"
    _ml, _mc = ("LIVE","#14F195") if _is_live else ("PAPER","#FFD700")
    _bl = f"◉ {_short}" if _short else "Connect Phantom"
    _conn_js = "true" if _short else "false"
    _html = f"""<style>
*{{box-sizing:border-box;margin:0;padding:0;}}
body{{background:transparent;font-family:'Share Tech Mono',monospace;}}
#w{{display:flex;align-items:center;gap:8px;justify-content:flex-end;padding:4px 0;}}
#mb{{font-size:10px;letter-spacing:2px;padding:3px 10px;border-radius:999px;border:1px solid {_mc}44;color:{_mc};cursor:pointer;}}
#mb:hover{{background:{_mc}22;}}
#pb{{font-family:'Share Tech Mono',monospace;font-size:11px;letter-spacing:1.5px;padding:6px 14px;border-radius:8px;border:1px solid {_bc}88;background:{_bc}18;color:{_bc};cursor:pointer;transition:all .2s;}}
#pb:hover{{background:{_bc}33;border-color:{_bc};}}
#pb:active{{transform:scale(.97);}}
#st{{font-size:10px;color:#8EF9FF;letter-spacing:1px;}}
#er{{font-size:10px;color:#FF6B6B;letter-spacing:1px;display:none;}}
</style>
<div id="w">
  <span id="er">No Phantom found</span>
  <span id="st">{("Connected ✓" if _short else "")}</span>
  <span id="mb" onclick="toggleMode()">{_ml} MODE</span>
  <button id="pb" onclick="handlePhantom()">{_bl}</button>
</div>
<script>
let CONN={_conn_js},ADDR="{_waddr}",MODE="{_tmode}";
const short=a=>a.slice(0,4)+'...'+a.slice(-4);
const setSt=(m,c)=>{{const s=document.getElementById('st');s.textContent=m;s.style.color=c||'#8EF9FF';}};
const send=v=>window.parent.postMessage({{type:'streamlit:setComponentValue',value:JSON.stringify(v)}},'*');

async function handlePhantom(){{
  const pb=document.getElementById('pb'),er=document.getElementById('er');
  if(!window.solana||!window.solana.isPhantom){{er.style.display='inline';setTimeout(()=>er.style.display='none',3000);return;}}
  if(CONN){{
    try{{await window.solana.disconnect();}}catch(e){{}}
    CONN=false;ADDR='';
    pb.textContent='Connect Phantom';pb.style.borderColor='#9945FF88';pb.style.color='#9945FF';
    setSt('Disconnected','#FF6B6B');send({{action:'disconnect',value:''}});
  }}else{{
    try{{
      pb.textContent='Connecting...';
      const r=await window.solana.connect();
      ADDR=r.publicKey.toString();CONN=true;
      pb.textContent=short(ADDR);pb.style.borderColor='#14F19588';pb.style.color='#14F195';
      setSt('Connected ✓','#14F195');send({{action:'connect',value:ADDR}});
    }}catch(e){{pb.textContent='Connect Phantom';setSt('Cancelled','#FFD700');}}
  }}
}}

async function toggleMode(){{
  const mb=document.getElementById('mb');
  const newMode=MODE==='live'?'paper':'live';
  if(newMode==='live'&&!ADDR){{setSt('Connect wallet first','#FF6B6B');setTimeout(()=>setSt(''),2000);return;}}
  MODE=newMode;
  mb.textContent=newMode.toUpperCase()+' MODE';
  const mc=newMode==='live'?'#14F195':'#FFD700';
  mb.style.color=mc;mb.style.borderColor=mc+'44';
  setSt(newMode.toUpperCase()+' mode','#8EF9FF');
  send({{action:'mode',value:newMode}});
}}
</script>"""
    _result = _components.html(_html, height=42, scrolling=False)
    if _result:
        try:
            import json
            _d = json.loads(_result) if isinstance(_result, str) else _result
            _a, _v = _d.get("action",""), _d.get("value","")
            if _a == "connect" and _v: _write_phantom_state(_v, _tmode); st.rerun()
            elif _a == "disconnect": _write_phantom_state("", _tmode); st.rerun()
            elif _a == "mode": _write_phantom_state(_waddr, _v); st.rerun()
        except Exception: pass

C_VOID   = "#050210"
C_GREEN  = "#14F195"
C_GOLD   = "#FFD700"
C_RED    = "#FF073A"
C_PURPLE = "#9945FF"
C_CYAN   = "#8EF9FF"
C_IVY    = "#FFB347"
C_NUGGET = "#C19A6B" # Boxer Fawn / Bronze

AGENT_EMOJIS = {
    "POLARIS": "❄️",
    "IVARIS":  "🔥",
    "ORACLE":  "🔎",
    "NUGGET":  "🔮",
    "AXON":    "⚡",
    "RHIZA":   "🕸️",
}

THEMATIC_STATES = {
    "loop_detected":       "Calcified Ego",
    "blocked":             "Cognitive Decalcification Required",
    "topic_lock_failed":   "Cognitive Decalcification Required",
    "evaluating":          "Mycelial Network Synthesizing",
    "rebuttal_evaluation": "Mycelial Network Synthesizing",
    "critiquing":          "Immune System Engaged",
    "rebutting":           "Root System Responding",
    "consensus":           "Harmonic Convergence",
    "final_consensus":     "Harmonic Convergence",
    "rejected":            "Signal Rejected — Substrate Insufficient",
    "final_rejection":     "Signal Rejected — Substrate Insufficient",
    "searching":           "Piping External Resonance",
    "oracle_evidence":     "External Truth Integrated",
    "nugget_audit":        "Independent Audit Complete",
    "approval":            "Patch Absorbed Into Memory",
    "pending_hitl":        "Awaiting Operator Nerve Signal",
    "ascending":           "Cognitive Ascension In Progress",
    "golden_mastery":      "Masterpiece Forged — Awaiting Seal",
    "forge_pending":       "Cognitive Ascension In Progress",
    "forge_complete":      "Masterpiece Forged — Awaiting Seal",
}

def _thematic_label(state: str) -> str:
    return THEMATIC_STATES.get(str(state).lower(), str(state).upper())

ROOT    = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "sentinuity_matrix.db"


# ── INTELLIGENCE SUBSTRATE DATABASES ────────────────────────────────────────
# Main trading UI reads sentinuity_matrix.db. These optional read-only substrate DBs
# let Copy Trade, Telegram Scout, and Dataset/Sensory systems write elsewhere so
# the hub can observe them without adding contention to the execution DB.
INTEL_DB_CANDIDATES = [
    Path(os.environ.get("SENTINUITY_INTEL_DB", "")) if os.environ.get("SENTINUITY_INTEL_DB") else None,
    ROOT / "sentinuity_intelligence.db",
    ROOT / "intelligence_substrate.db",
    ROOT / "copytrade_scout.db",
    ROOT / "telegram_scout.db",
    ROOT / "sensory_substrate.db",
    ROOT / "data" / "sentinuity_intelligence.db",
    ROOT / "data" / "copytrade_scout.db",
    ROOT / "data" / "telegram_scout.db",
    ROOT / "data" / "sensory_substrate.db",
]
INTEL_DB_PATHS = []
for _p in INTEL_DB_CANDIDATES:
    try:
        if _p and _p.exists() and _p.is_file() and _p not in INTEL_DB_PATHS:
            INTEL_DB_PATHS.append(_p)
    except Exception:
        pass

TRUSTED_LINK_DOMAINS = {
    "x.com", "twitter.com", "github.com", "raw.githubusercontent.com", "gist.github.com",
    "helius.xyz", "dev.helius.xyz", "solscan.io", "birdeye.so", "dexscreener.com",
    "pump.fun", "pumpdotfun.com", "telegram.org", "t.me",
}

if "organism_awake" not in st.session_state: st.session_state["organism_awake"] = True
if "truth_lens_open" not in st.session_state: st.session_state["truth_lens_open"] = False
if "hub_refresh_seconds" not in st.session_state: st.session_state["hub_refresh_seconds"] = 30

@st.cache_data(ttl=12, show_spinner=False)
def fetch_coingecko_prices() -> dict:
    _FALLBACK = {"SOL": {"price_usd": 120.0, "price_aud": 187.5, "change_24h": 0.0}, "XRP": {"price_usd": 0.50, "price_aud": 0.78, "change_24h": 0.0}, "SUI": {"price_usd": 1.20, "price_aud": 1.875, "change_24h": 0.0}}
    _IDS = {"SOL": "solana", "XRP": "ripple", "SUI": "sui"}
    try:
        resp = _requests.get("https://api.coingecko.com/api/v3/simple/price", params={"ids": ",".join(_IDS.values()), "vs_currencies": "usd,aud", "include_24hr_change": "true"}, timeout=5, headers={"Accept": "application/json"})
        if resp.status_code != 200: return _FALLBACK
        data = resp.json()
        result = {}
        for sym, cg_id in _IDS.items():
            coin = data.get(cg_id, {})
            result[sym] = {"price_usd": float(coin.get("usd", _FALLBACK[sym]["price_usd"])), "price_aud": float(coin.get("aud", _FALLBACK[sym]["price_aud"])), "change_24h": float(coin.get("usd_24h_change", 0.0) or 0.0)}
        return result
    except Exception: return _FALLBACK

@st.cache_data(show_spinner=False)
def get_base64(filename):
    for base in [ROOT / "ui", ROOT / "assets", ROOT]:
        for ext in ["", ".jpg", ".jpeg", ".png", ".webp"]:
            p = base / f"{filename}{ext}"
            if p.exists() and p.is_file():
                try:
                    with open(p, "rb") as f:
                        suf = p.suffix.lower().replace(".", "")
                        mime = "jpeg" if suf in ("jpg","jpeg") else suf
                        return f"data:image/{mime};base64,{base64.b64encode(f.read()).decode()}"
                except Exception: continue
    return None

img_polaris        = get_base64("polarise_teaser")
img_ivy            = get_base64("ivy_origin_artifact")
img_lab            = get_base64("sentinuity_lab_core") or get_base64("sentinuity_lab")
img_command_center = get_base64("command_center")

import logging as _logging
_hub_log = _logging.getLogger("sovereign_hub")
_query_errors: list = []

@st.cache_data(ttl=10, show_spinner=False)
@st.cache_resource
def _get_shared_conn():
    """Single persistent DB connection — eliminates open/close overhead."""
    _c = sqlite3.connect(str(DB_PATH), check_same_thread=False, timeout=10.0)
    _c.execute("PRAGMA journal_mode=WAL")
    _c.execute("PRAGMA cache_size=-32000")
    return _c


@st.cache_data(ttl=3, show_spinner=False)
def get_data_bundle():
    """Central data bundle — all heavy queries in ONE connection, cached 3s."""
    try:
        _cn = _get_shared_conn()
        return {
            "wallet":     pd.read_sql_query("SELECT wallet_balance,initial_capital FROM system_state WHERE id=1 LIMIT 1", _cn),
            "open_pos":   pd.read_sql_query("SELECT id,token_name,mint_address,entry_price,position_size_usd,live_exec_price,live_exec_pct,live_exec_updated_at,opened_at FROM paper_positions WHERE status='OPEN' ORDER BY opened_at DESC", _cn),
            "snapshots":  pd.read_sql_query("SELECT id,token_name,mint_address,mint_confidence,candidate_state,latched FROM market_snapshots WHERE candidate_state NOT IN ('vetoed','dead') ORDER BY id DESC LIMIT 50", _cn),
            "heartbeat":  pd.read_sql_query("SELECT service_name,status,last_pulse,note FROM system_heartbeat", _cn),
            "config":     pd.read_sql_query("SELECT key,value FROM system_config WHERE key IN ('TRADING_MODE','POSITION_SIZE_USD','DEBATES_ENABLED','SUPERVISOR_MIN_MINT_CONFIDENCE','TAKE_PROFIT_PCT','STOP_LOSS_PCT','MAX_HOLD_SECONDS')", _cn),
            "recent_trades": pd.read_sql_query("SELECT id,token_name,realized_pnl_usd,exit_reason,win_loss,closed_at,position_size_usd FROM paper_positions WHERE status='CLOSED' ORDER BY closed_at DESC LIMIT 20", _cn),
            "proposals":  pd.read_sql_query("SELECT id,proposal_type,proposal_text,status,confidence,created_at FROM polaris_proposals WHERE status IN ('open','debating','approved','applied') ORDER BY created_at DESC LIMIT 10", _cn),
        }
    except Exception:
        return {k: pd.DataFrame() for k in ["wallet","open_pos","snapshots","heartbeat","config","recent_trades","proposals"]}


def query_db(sql, params=()):
    """Fast query using shared connection."""
    try:
        _conn = _get_shared_conn()
        return pd.read_sql_query(sql, _conn, params=params)
    except Exception:
        try:
            _fb = sqlite3.connect(str(DB_PATH), timeout=5.0, check_same_thread=False)
            result = pd.read_sql_query(sql, _fb, params=params)
            _fb.close()
            return result
        except Exception:
            return pd.DataFrame()

def val(df, col, default=0.0):
    try:
        if df.empty or col not in df.columns: return default
        return default if pd.isna(df.iloc[0][col]) else df.iloc[0][col]
    except Exception: return default


def _domain_allowed(hostname: str) -> bool:
    if not hostname:
        return False
    hostname = hostname.lower().strip(".")
    return any(hostname == d or hostname.endswith("." + d) for d in TRUSTED_LINK_DOMAINS)

def _safe_display_domain(url: str) -> str:
    try:
        return html.escape((urlparse(url).hostname or "unknown").lower())
    except Exception:
        return "unknown"

def classify_url(url: str) -> tuple[str, str]:
    try:
        parsed = urlparse(str(url).strip())
        scheme = parsed.scheme.lower()
        hostname = (parsed.hostname or "").lower()
        if scheme not in {"http", "https"}:
            return "blocked", '<span class="link-blocked">⛔ BLOCKED: unsafe scheme</span>'
        if not _domain_allowed(hostname):
            return "blocked", f'<span class="link-blocked">⛔ BLOCKED: {html.escape(hostname or "unknown")}</span>'
        safe_url = html.escape(str(url), quote=True)
        safe_domain = _safe_display_domain(str(url))
        return "verified", f'<a href="{safe_url}" target="_blank" rel="noopener noreferrer nofollow" class="link-verified">🟢 VERIFIED — {safe_domain}</a>'
    except Exception:
        return "blocked", '<span class="link-blocked">⛔ BLOCKED: malformed URL</span>'

def purify_links(text: str) -> str:
    """Escape all non-link text and only render allowlisted http/https links as clickable badges."""
    if text is None:
        return ""
    raw = str(text)
    url_re = re.compile(r"https?://[^\s<>'\"`]+", re.IGNORECASE)
    out, last = [], 0
    for match in url_re.finditer(raw):
        out.append(html.escape(raw[last:match.start()]))
        url = match.group(0).rstrip(".,);]}")
        trailing = match.group(0)[len(url):]
        _, safe_html = classify_url(url)
        out.append(safe_html)
        out.append(html.escape(trailing))
        last = match.end()
    out.append(html.escape(raw[last:]))
    return "".join(out)

def _sqlite_tables(db_path: Path) -> set[str]:
    try:
        with sqlite3.connect(str(db_path), timeout=1.5) as conn:
            rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            return {str(r[0]) for r in rows}
    except Exception:
        return set()

@st.cache_data(ttl=15, show_spinner=False)
def query_optional_db(table_candidates: list[str], limit: int = 5) -> tuple[pd.DataFrame, str]:
    """Read the newest matching table from optional substrate DBs without touching execution writes."""
    for db_path in INTEL_DB_PATHS:
        tables = _sqlite_tables(db_path)
        for table in table_candidates:
            if table in tables:
                try:
                    with sqlite3.connect(str(db_path), timeout=1.5) as conn:
                        conn.execute("PRAGMA query_only=ON")
                        cols = pd.read_sql_query(f"PRAGMA table_info({table})", conn)
                        names = set(cols["name"].astype(str)) if not cols.empty and "name" in cols.columns else set()
                        order_col = next((c for c in ["created_at", "timestamp", "logged_at", "updated_at", "id"] if c in names), None)
                        order_sql = f" ORDER BY {order_col} DESC" if order_col else ""
                        df = pd.read_sql_query(f"SELECT * FROM {table}{order_sql} LIMIT {int(limit)}", conn)
                    return df, f"{db_path.name}:{table}"
                except Exception:
                    continue
    return pd.DataFrame(), "not wired"

def _row_text(row, keys, default="—"):
    for k in keys:
        try:
            v = row.get(k, None)
            if v is not None and str(v).strip() != "":
                return str(v)
        except Exception:
            pass
    return default



@st.fragment(run_every=30)
def render_convergence_gate() -> None:
    """
    POLARIS CONVERGENCE GATE — unmissable HITL alert.
    Appears at the TOP of the page when Polaris cannot proceed without operator.
    Collapses to nothing when clear — never cries wolf.
    """
    import time as _ct
    _now = _ct.time()
    _gates = []

    try:
        _gc = sqlite3.connect(str(DB_PATH), timeout=2.0)
        _gc.row_factory = sqlite3.Row

        # Check: DRAWDOWN_HALT_ACTIVE
        _halt = _gc.execute("SELECT value FROM system_config WHERE key='DRAWDOWN_HALT_ACTIVE'").fetchone()
        if _halt and str(_halt["value"]).strip() in ("1", "true"):
            _gates.append(("HALT", "TRADING HALTED — OPERATOR ACTION REQUIRED",
                "Drawdown protection active — organism cannot open positions",
                "python fix_blockers.py  OR  set DRAWDOWN_HALT_ACTIVE=0 in system_config"))

        # Check: HITL_REQUIRED proposals waiting
        _hitl = _gc.execute("""
            SELECT id, proposal_type, proposal_text, created_at FROM polaris_proposals
            WHERE status IN ('HITL_REQUIRED','nugget_escalated')
              AND (created_at IS NULL OR created_at < ?)
            ORDER BY created_at ASC LIMIT 3
        """, (_now - 600,)).fetchall()
        for _h in _hitl:
            _age_m = int((_now - float(_h["created_at"] or _now)) / 60)
            _preview = str(_h["proposal_text"] or "")[:80]
            _gates.append(("SEAL", f"POLARIS IS WAITING — PROPOSAL #{_h['id']} ({_age_m}m)",
                f"{_h['proposal_type'] or 'PROPOSAL'}: {_preview}",
                f"python approve_proposal.py {_h['id']}"))

        # Check: Forge stalled
        _forge_err = _gc.execute("""
            SELECT COUNT(*) n FROM polaris_proposals
            WHERE proposal_domain='FORGE' AND status='debate_error'
              AND COALESCE(cooldown_until, 0) > ?
        """, (_now,)).fetchone()
        _forge_open = _gc.execute("""
            SELECT COUNT(*) n FROM polaris_proposals
            WHERE proposal_domain='FORGE' AND status='open'
        """).fetchone()
        if (_forge_err and _forge_err["n"] >= 4) and (_forge_open and _forge_open["n"] == 0):
            _gates.append(("FORGE", "FORGE STALLED — POLARIS NEEDS EVIDENCE INPUT",
                "4+ proposals hit confidence floor. Reconnaissance engine may be offline.",
                "Get-Content logs\\reconnaissance_engine.log -Tail 10"))

        # Check: supervisor idle + no priced candidates
        _sup_hb = _gc.execute("""
            SELECT last_pulse, note FROM system_heartbeat
            WHERE service_name='neural_supervisor' ORDER BY id DESC LIMIT 1
        """).fetchone()
        if _sup_hb:
            _sup_age = _now - float(_sup_hb["last_pulse"] or 0)
            _sup_note = str(_sup_hb["note"] or "")
            if "candidates=0" in _sup_note and _sup_age < 120:
                _priced_qual = _gc.execute("""
                    SELECT COUNT(*) n FROM market_snapshots
                    WHERE candidate_state='qualified' AND price_status='priced'
                      AND COALESCE(price_updated_at,0) > ?
                """, (_now - 120,)).fetchone()
                if _priced_qual and _priced_qual["n"] == 0:
                    _gates.append(("STARVE", "PIPELINE STARVED — OPERATOR CHECK NEEDED",
                        "Qualified tokens exist but none priced. DexScreener may be failing.",
                        "Get-Content logs\\market_intelligence.log -Tail 20 | Select-String price"))

        _gc.close()
    except Exception:
        return

    if not _gates:
        return  # clear — collapse entirely

    # Severity → colour + pulse speed
    _sev_props = {
        "HALT":   {"col": "#FF073A", "pulse": "0.8s", "icon": "🚨"},
        "SEAL":   {"col": "#FFD700", "pulse": "1.2s", "icon": "⬡"},
        "FORGE":  {"col": "#9945FF", "pulse": "1.5s", "icon": "🔥"},
        "STARVE": {"col": "#FFB347", "pulse": "2.0s", "icon": "⚠"},
        "INFO":   {"col": "#8EF9FF", "pulse": "3.0s", "icon": "◈"},
    }
    top_sev  = _gates[0][0]
    top_props = _sev_props.get(top_sev, _sev_props["INFO"])
    top_col  = top_props["col"]
    top_pulse = top_props["pulse"]
    top_icon  = top_props["icon"]

    # Full-width pulsing banner — unmissable
    _body = ""
    for sev, title, detail, action in _gates:
        _p = _sev_props.get(sev, _sev_props["INFO"])
        _c = _p["col"]
        _body += f"""
<div style='margin-bottom:10px;padding:10px 14px;
    border-left:4px solid {_c};border-radius:0 8px 8px 0;
    background:{_c}0d;'>
  <div style='font-family:Orbitron,sans-serif;font-size:0.7rem;
      font-weight:700;color:{_c};letter-spacing:2px;margin-bottom:4px;'>
      {_p['icon']} {html.escape(title)}</div>
  <div style='font-family:Share Tech Mono,monospace;font-size:0.62rem;
      color:rgba(255,255,255,0.6);margin-bottom:4px;'>{html.escape(detail)}</div>
  <div style='font-family:Share Tech Mono,monospace;font-size:0.58rem;
      color:rgba(255,255,255,0.25);'>→ {html.escape(action)}</div>
</div>"""

    st.markdown(f"""
<style>
@keyframes _hitl_pulse {{
    0%,100% {{ box-shadow: 0 0 0px {top_col}00; border-color: {top_col}; }}
    50%      {{ box-shadow: 0 0 24px {top_col}99; border-color: {top_col}ff; }}
}}
</style>
<div style='
    margin: 0 0 16px 0;
    padding: 14px 18px;
    border: 2px solid {top_col};
    border-radius: 12px;
    background: rgba(5,2,16,0.95);
    animation: _hitl_pulse {top_pulse} ease-in-out infinite;
    position: relative;
'>
  <div style='display:flex;align-items:center;gap:10px;margin-bottom:10px;'>
    <span style='font-size:1.4rem;animation:_hitl_pulse {top_pulse} ease-in-out infinite;'>
        {top_icon}</span>
    <div>
      <div style='font-family:Orbitron,sans-serif;font-size:0.75rem;font-weight:900;
          color:{top_col};letter-spacing:4px;'>POLARIS — OPERATOR REQUIRED</div>
      <div style='font-family:Share Tech Mono,monospace;font-size:0.55rem;
          color:{top_col}99;letter-spacing:2px;'>
          {len(_gates)} item{"s" if len(_gates)>1 else ""} await your seal · organism is paused</div>
    </div>
  </div>
  {_body}
</div>
""", unsafe_allow_html=True)


@st.fragment(run_every=60)
def render_forge_ambient() -> None:
    """
    Phase 5: AMBIENT FORGE VISIBILITY — debate sparks, evolution pulses.
    Phase 7: NEURAL SPIKE EVENTS — latch/bomb/heal moments as rare high-signal motion.
    Runs every 60s. Collapses when nothing is happening. Never shows raw logs.
    """
    import sqlite3 as _sq3, time as _t, html as _html
    _now = _t.time()
    _sparks = []
    _spikes = []
    try:
        _fc = _sq3.connect(str(DB_PATH), timeout=2.0)
        _fc.row_factory = _sq3.Row

        # Forge state
        _forge_debating = _fc.execute(
            "SELECT COUNT(*) FROM polaris_proposals WHERE status='debating'"
        ).fetchone()[0]
        _forge_open = _fc.execute(
            "SELECT COUNT(*) FROM polaris_proposals WHERE status='open' AND proposal_domain='FORGE'"
        ).fetchone()[0]
        _forge_approved = _fc.execute(
            "SELECT COUNT(*) FROM polaris_proposals WHERE status IN ('approved','applied') AND updated_at > ?",
            (_now - 3600,)
        ).fetchone()[0]

        # Neural spikes: recent high-signal cognition events
        _recent_events = _fc.execute("""
            SELECT stage, message, token, timestamp
            FROM cognition_log
            WHERE timestamp > ?
              AND (
                message LIKE '%SELECTIVE_AGGRESSION%'
                OR message LIKE '%BOMB SIGNATURE%'
                OR message LIKE '%ENTRY OPENED%'
                OR message LIKE '%Auto-heal fired%'
                OR message LIKE '%ORACLE_STALLED%'
                OR message LIKE '%PHASE_A_PASS%'
              )
            ORDER BY timestamp DESC LIMIT 5
        """, (_now - 300,)).fetchall()
        _fc.close()

        for ev in _recent_events:
            _age = int(_now - float(ev["timestamp"] or _now))
            _msg = str(ev["message"] or "")[:60]
            _tok = str(ev["token"] or "")[:12]
            _stg = str(ev["stage"] or "")
            if "BOMB" in _msg or "SELECTIVE_AGGRESSION" in _msg:
                _col, _icon = "#FF073A", "💥"
            elif "ENTRY OPENED" in _msg or "PHASE_A_PASS" in _msg:
                _col, _icon = "#14F195", "⚡"
            elif "heal" in _msg.lower():
                _col, _icon = "#9945FF", "↺"
            elif "STALLED" in _msg:
                _col, _icon = "#FFB347", "⚠"
            else:
                _col, _icon = "#8EF9FF", "·"
            _spikes.append((_col, _icon, _age, _tok or _stg, _msg))

    except Exception:
        return

    # Nothing to show
    if not _forge_debating and not _forge_open and not _forge_approved and not _spikes:
        return

    _parts = [
        '<div style="display:flex;gap:8px;flex-wrap:wrap;align-items:flex-start;'
        'padding:6px 10px;margin-bottom:4px;border-radius:6px;'
        'background:rgba(5,2,16,0.4);border:1px solid rgba(153,69,255,0.12);">'
    ]

    # Forge ambient indicators
    if _forge_debating:
        _parts.append(
            f'<span style="font-family:Share Tech Mono,monospace;font-size:0.52rem;'
            f'color:#9945FF55;letter-spacing:2px;animation:forgeBreath 3s ease-in-out infinite;">'
            f'◈ DEBATING {_forge_debating}</span>'
        )
    if _forge_open:
        _parts.append(
            f'<span style="font-family:Share Tech Mono,monospace;font-size:0.52rem;'
            f'color:#9945FF33;letter-spacing:2px;">◈ QUEUED {_forge_open}</span>'
        )
    if _forge_approved:
        _parts.append(
            f'<span style="font-family:Share Tech Mono,monospace;font-size:0.52rem;'
            f'color:#FFD70066;letter-spacing:2px;">◈ APPROVED 1h</span>'
        )

    # Neural spike events
    for col, icon, age, tok, msg in _spikes[:3]:
        _parts.append(
            f'<span style="font-family:Share Tech Mono,monospace;font-size:0.5rem;'
            f'color:{col}88;letter-spacing:1px;">{icon} {tok} {age}s</span>'
        )

    _parts.append(
        '<style>@keyframes forgeBreath{0%,100%{opacity:0.4}50%{opacity:0.7}}</style>'
        '</div>'
    )
    st.markdown("".join(_parts), unsafe_allow_html=True)


@st.fragment(run_every=20)
def render_same_eyes_monitor() -> None:
    """
    SAME-EYES EXECUTION MONITOR — reads dry-run output from execution_engine.
    Zero writes. Shows exactly what gates are blocking entry for each candidate.
    """
    try:
        import sys as _sys
        from services.execution_engine import dry_run_entry_scan
        _decisions = dry_run_entry_scan(limit=20)
    except Exception as _e:
        st.markdown(
            f'<div style="font-family:Share Tech Mono;font-size:0.6rem;color:#888;">'
            f'SAME-EYES: unavailable ({type(_e).__name__}: {_e})</div>',
            unsafe_allow_html=True,
        )
        return

    if not _decisions:
        return

    _rows_html = ""
    for _d in _decisions:
        _dec   = _d.get("decision", "?")
        _mint  = str(_d.get("mint_address") or "")[:12]
        _sig   = _d.get("signal_age_sec")
        _prc   = _d.get("price_age_sec")
        _conf  = _d.get("confidence")
        _token = str(_d.get("token_name") or _mint)[:12]
        _col   = "#14F195" if _dec == "WOULD_ENTER" else (
                 "#FFD700" if "STALE" in _dec or "OLD" in _dec else "#FF073A")
        _sig_s  = f"{_sig:.0f}s"  if _sig  is not None else "?"
        _prc_s  = f"{_prc:.0f}s"  if _prc  is not None else "?"
        _conf_s = f"{_conf:.2f}"  if _conf is not None else "?"
        _rows_html += (
            f'<tr style="font-size:0.6rem;font-family:Share Tech Mono;">'
            f'<td style="color:#CCC;padding:2px 6px;">{_token}</td>'
            f'<td style="color:#888;padding:2px 6px;">{_prc_s}</td>'
            f'<td style="color:#888;padding:2px 6px;">{_sig_s}</td>'
            f'<td style="color:#888;padding:2px 6px;">{_conf_s}</td>'
            f'<td style="color:{_col};padding:2px 6px;">{_dec}</td>'
            f'</tr>'
        )

    st.markdown(
        f'<div style="margin-top:8px;padding:8px 10px;border-radius:6px;'
        f'background:rgba(5,2,16,0.5);border:1px solid rgba(255,255,255,0.07);">'
        f'<div style="font-family:Share Tech Mono;font-size:0.6rem;color:#8EF9FF;'
        f'letter-spacing:2px;margin-bottom:6px;">EXECUTION SAME-EYES</div>'
        f'<table style="width:100%;border-collapse:collapse;">'
        f'<tr style="font-size:0.55rem;color:#555;font-family:Share Tech Mono;">'
        f'<th style="text-align:left;padding:2px 6px;">MINT</th>'
        f'<th style="text-align:left;padding:2px 6px;">PRC_AGE</th>'
        f'<th style="text-align:left;padding:2px 6px;">SIG_AGE</th>'
        f'<th style="text-align:left;padding:2px 6px;">CONF</th>'
        f'<th style="text-align:left;padding:2px 6px;">DECISION</th>'
        f'</tr>'
        f'{_rows_html}'
        f'</table>'
        f'</div>',
        unsafe_allow_html=True,
    )


@st.fragment(run_every=20)
def render_pipeline_flow_debug() -> None:
    """
    THERMAL PIPELINE CORE — observability with organism-state heat rendering.
    Discovery→Qual→Priced→Supervisor→Latch→Exec→Open rendered as thermal lanes.
    Operator feels pressure/bottleneck before reading a number.
    """
    import time as _pt
    _now = _pt.time()
    try:
        _pc = sqlite3.connect(str(DB_PATH), timeout=2.0)
        _pc.row_factory = sqlite3.Row
        _disc    = _pc.execute("SELECT COUNT(*) FROM raw_dna WHERE COALESCE(first_seen_at, timestamp, 0) > ?", (int(_now - 300),)).fetchone()[0]
        _qual    = _pc.execute("SELECT COUNT(*), MAX(created_at) FROM market_snapshots WHERE candidate_state='qualified' OR (candidate_state='pending' AND quality_status='qualified')").fetchone()
        _priced  = _pc.execute("SELECT COUNT(*), MAX(price_updated_at) FROM market_snapshots WHERE price_status='priced' AND is_tradeable=1 AND (candidate_state='qualified' OR (candidate_state='pending' AND quality_status='qualified'))").fetchone()
        _sv_cand = _pc.execute("SELECT COUNT(*) FROM market_snapshots WHERE latched=0 AND (candidate_state='qualified' OR (candidate_state='pending' AND quality_status='qualified')) AND price_status='priced' AND is_tradeable=1").fetchone()[0]
        _latched = _pc.execute("SELECT COUNT(*), MAX(latch_claimed_until) FROM market_snapshots WHERE latched=1").fetchone()
        _exec_r  = _pc.execute("SELECT COUNT(*) FROM market_snapshots WHERE execution_ready=1").fetchone()[0]
        _opens   = _pc.execute("SELECT COUNT(*) FROM paper_positions WHERE status='OPEN'").fetchone()[0]
        # Momentum: any bomb signatures or high-momentum rows
        _bomb_ct = 0
        try:
            _bomb_ct = _pc.execute("SELECT COUNT(*) FROM market_snapshots WHERE bomb_signature=1 AND candidate_state NOT IN ('vetoed','executed','expired_stale')").fetchone()[0]
        except Exception: pass
        _pc.close()

        _qual_age  = (_now - float(_qual[1]))  if _qual[1]   else None
        _price_age = (_now - float(_priced[1])) if _priced[1] else None

        # Thermal colour doctrine:
        # DISCOVERY  = electric blue  (#00D4FF)
        # QUALIFIED  = white pressure (#F0F0FF)
        # PRICED     = warm amber     (#FFB347)
        # SUPERVISOR = gold ignition  (#FFD700)
        # LATCHED    = neon pulse     (#14F195)
        # EXEC       = emerald        (#00FF88)
        # OPEN       = sovereign gold (#FFD700) / bomb = red pulse
        LANE_COLOURS = ["#00D4FF","#F0F0FF","#FFB347","#FFD700","#14F195","#00FF88","#FFD700"]
        LANE_LABELS  = ["DISC","QUAL","PRICED","SV","LATCH","EXEC","OPEN"]
        LANE_COUNTS  = [_disc, _qual[0] or 0, _priced[0] or 0, _sv_cand, _latched[0] or 0, _exec_r, _opens]
        LANE_AGES    = [None, _qual_age, _price_age, None, None, None, None]
        LANE_THRESH  = [30, 120, 120, 180, 180, 180, 300]

        # Detect blockage and ambient heat level
        _blocked_idx = None
        for i, (cnt, age, thr) in enumerate(zip(LANE_COUNTS, LANE_AGES, LANE_THRESH)):
            if cnt == 0:
                _blocked_idx = i
                break
            if age is not None and age > thr:
                _blocked_idx = i
                break

        # Organism heat: 0.0 cold → 1.0 hot
        _heat = min(1.0, (_disc / 50.0) * 0.3 + (_opens / 3.0) * 0.4 + (0.3 if _latched[0] else 0))
        _heat_col = f"rgba({int(20 + _heat*235)},{int(241 - _heat*200)},{int(149 - _heat*149)},0.15)"

        lanes_html = ""
        for i, (label, col, count, age, thresh) in enumerate(zip(
            LANE_LABELS, LANE_COLOURS, LANE_COUNTS, LANE_AGES, LANE_THRESH
        )):
            # Thermal state per lane
            if count == 0:
                intensity = "0"
                border    = "#FF073A"
                glow      = "rgba(255,7,58,0.4)"
                anim      = "animation:thermalDead 1.4s ease-in-out infinite;"
                val_col   = "#FF073A"
            elif age is not None and age > thresh:
                intensity = "0.4"
                border    = "#FFD700"
                glow      = "rgba(255,215,0,0.3)"
                anim      = "animation:thermalWarm 2.5s ease-in-out infinite;"
                val_col   = "#FFD700"
            else:
                fill      = min(1.0, count / max(count, 10))
                intensity = f"{0.6 + fill * 0.4:.2f}"
                border    = col
                glow      = f"{col}66"
                anim      = "animation:thermalAlive 2s ease-in-out infinite;"
                val_col   = col

            age_str = f" {int(age)}s" if age is not None else ""
            # Bomb badge on SV lane
            bomb_badge = ""
            if i == 3 and _bomb_ct > 0:
                bomb_badge = f'<span style="margin-left:4px;font-size:0.45rem;color:#FF073A;letter-spacing:1px;animation:bombPulse 0.8s ease-in-out infinite;">💥{_bomb_ct}</span>'

            lanes_html += (
                f'<div style="flex:1;min-width:52px;padding:5px 4px;text-align:center;'
                f'background:{col}0a;border:1px solid {border}44;border-radius:4px;'
                f'box-shadow:0 0 8px {glow};{anim}">'
                f'<div style="font-family:Share Tech Mono,monospace;font-size:0.48rem;'
                f'color:#555;letter-spacing:1px;margin-bottom:2px;">{label}</div>'
                f'<div style="font-family:Orbitron,monospace;font-size:0.75rem;'
                f'font-weight:700;color:{val_col};text-shadow:0 0 6px {val_col}88;">'
                f'{count}</div>'
                f'<div style="font-size:0.42rem;color:#444;">{age_str}</div>'
                f'{bomb_badge}'
                f'</div>'
            )

        _blocked_html = ""
        if _blocked_idx is not None:
            _bn = LANE_LABELS[_blocked_idx]
            _blocked_html = (
                f'<div style="margin-top:5px;font-family:Share Tech Mono,monospace;'
                f'font-size:0.52rem;color:#FF073A;letter-spacing:2px;'
                f'animation:thermalDead 1.4s ease-in-out infinite;">'
                f'⚠ PRESSURE BLOCKED @ {_bn}</div>'
            )

        forge_ambient = ""
        try:
            _fconn = sqlite3.connect(str(DB_PATH), timeout=1.0)
            _fconn.row_factory = sqlite3.Row
            _forge_active = _fconn.execute(
                "SELECT COUNT(*) FROM polaris_proposals WHERE proposal_domain='FORGE' AND status IN ('open','debating')"
            ).fetchone()[0]
            _fconn.close()
            if _forge_active > 0:
                forge_ambient = (
                    f'<div style="margin-top:4px;font-family:Share Tech Mono,monospace;'
                    f'font-size:0.48rem;color:#9945FF55;letter-spacing:2px;">'
                    f'◈ FORGE DEBATING {_forge_active}</div>'
                )
        except Exception: pass

        st.markdown(
            f'<style>'
            f'@keyframes thermalAlive{{0%,100%{{opacity:0.85}}50%{{opacity:1}}}}'
            f'@keyframes thermalWarm{{0%,100%{{opacity:0.6;border-color:#FFD70044}}50%{{opacity:0.9;border-color:#FFD700aa}}}}'
            f'@keyframes thermalDead{{0%,100%{{opacity:0.4}}50%{{opacity:0.85}}}}'
            f'@keyframes bombPulse{{0%,100%{{opacity:0.7}}50%{{opacity:1;text-shadow:0 0 8px #FF073A}}}}'
            f'</style>'
            f'<div style="padding:7px 10px;margin-bottom:6px;border-radius:7px;'
            f'background:{_heat_col};border:1px solid rgba(255,255,255,0.06);">'
            f'<div style="font-family:Share Tech Mono;font-size:0.52rem;color:#555;'
            f'margin-bottom:5px;letter-spacing:3px;">THERMAL PIPELINE</div>'
            f'<div style="display:flex;gap:4px;flex-wrap:nowrap;">{lanes_html}</div>'
            f'{_blocked_html}{forge_ambient}'
            f'</div>',
            unsafe_allow_html=True,
        )
    except Exception:
        pass


@st.fragment(run_every=30)
def render_intelligence_scouts() -> None:
    """
    Single call point for all scout panels — isolated fragment, 30s refresh.
    Wraps telegram/wallet scout data. Low-priority data, no need for fast refresh.
    Fragment isolation means scout DB queries don't block the live trade panels.
    """
    import html as _html
    _C_CYAN  = "#8EF9FF"
    _C_GREEN = "#14F195"

    st.markdown(
        f"<div style='font-family:Share Tech Mono;font-size:0.75rem;"
        f"letter-spacing:3px;color:{_C_CYAN};margin-bottom:8px;'>"
        f"📡 SCOUT FEEDS</div>",
        unsafe_allow_html=True,
    )

    # ── SMART MONEY SIGNAL LAMPBOARD ─────────────────────────────────────────
    try:
        _lamp_now = __import__("time").time()
        _wallet_fresh = query_db(
            "SELECT COUNT(*) as n FROM symbiotic_candidates "
            "WHERE wallet_score > 0.5 AND first_seen_at > ?",
            params=(_lamp_now - 300,)
        )
        _tg_fresh = query_db(
            "SELECT COUNT(*) as n FROM symbiotic_candidates "
            "WHERE telegram_score > 0.5 AND first_seen_at > ?",
            params=(_lamp_now - 300,)
        )
        _clustering = query_db(
            "SELECT COUNT(DISTINCT wallet_observation_id) as n FROM symbiotic_candidates "
            "WHERE wallet_score > 0.3 AND first_seen_at > ?",
            params=(_lamp_now - 600,)
        )
        _high_wr = query_db(
            "SELECT COUNT(*) as n FROM symbiotic_candidates WHERE wallet_score >= 0.8"
        )
        _wn  = int(_wallet_fresh["n"].iloc[0]) if not _wallet_fresh.empty else 0
        _tn  = int(_tg_fresh["n"].iloc[0])     if not _tg_fresh.empty     else 0
        _cln = int(_clustering["n"].iloc[0])   if not _clustering.empty   else 0
        _hwn = int(_high_wr["n"].iloc[0])      if not _high_wr.empty      else 0

        def _lamp(label, active, count=0):
            if active and count >= 3:
                col, glow, dot = "#FFD700", "rgba(255,215,0,0.2)", "●"
            elif active:
                col, glow, dot = "#14F195", "rgba(20,241,149,0.12)", "●"
            else:
                col, glow, dot = "#333", "transparent", "○"
            return (
                f'<div style="display:inline-flex;align-items:center;gap:4px;'
                f'padding:3px 8px;border-radius:4px;background:{glow};'
                f'border:1px solid {col}33;margin-right:4px;">'
                f'<span style="color:{col};font-size:0.65rem;">{dot}</span>'
                f'<span style="font-family:Share Tech Mono;font-size:0.58rem;color:{col};">'
                f'{label}{(" ×"+str(count)) if active and count > 1 else ""}</span></div>'
            )

        _lamps = "".join([
            _lamp("WALLET BUY",  _wn  > 0, _wn),
            _lamp("CLUSTERING",  _cln > 1, _cln),
            _lamp("HIGH-WR",     _hwn > 0, _hwn),
            _lamp("TG SCOUT",    _tn  > 0, _tn),
        ])
        st.markdown(
            f'<div style="margin-bottom:10px;padding:6px 8px;'
            f'border-radius:6px;background:rgba(5,2,16,0.4);'
            f'border:1px solid rgba(153,69,255,0.15);">'
            f'{_lamps}</div>',
            unsafe_allow_html=True,
        )
    except Exception:
        pass  # lampboard is advisory — never block scouts on DB error

    root_col1, root_col2 = st.columns(2, gap="small")

    with root_col1:
        st.markdown("**📡 TELEGRAM WATCHER**")
        try:
            calls = query_db(
                "SELECT source_channel, token_address, telegram_score, first_seen_at "
                "FROM symbiotic_candidates ORDER BY first_seen_at DESC LIMIT 3"
            )
            if not calls.empty:
                for _, c in calls.iterrows():
                    _ch  = _html.escape(str(c.get("source_channel") or "?")[:20])
                    _sc  = float(c.get("telegram_score") or 0)
                    _tok = str(c.get("token_address") or "?")[:8]
                    st.markdown(
                        f'<div class="symbiotic-root">Ch: {_ch} • Conf: {_sc:.2f} • {_tok}...</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    '<div class="symbiotic-root">telegram_scout • no recent calls</div>',
                    unsafe_allow_html=True,
                )
        except Exception:
            st.markdown(
                '<div class="symbiotic-root">telegram_scout initializing</div>',
                unsafe_allow_html=True,
            )

    with root_col2:
        st.markdown(
            f"<div style='font-family:Share Tech Mono;font-size:0.72rem;"
            f"letter-spacing:2px;color:{_C_GREEN};margin-bottom:6px;'>"
            f"🧬 WALLET SIGNAL NODES</div>",
            unsafe_allow_html=True,
        )
        try:
            wallets = query_db(
                "SELECT wallet_observation_id, wallet_score, token_address, first_seen_at "
                "FROM symbiotic_candidates ORDER BY wallet_score DESC, first_seen_at DESC LIMIT 5"
            )
            if not wallets.empty:
                _wmax = float(wallets["wallet_score"].max() or 1)
                for _, w in wallets.iterrows():
                    _wid  = str(w.get("wallet_observation_id") or "?")[:10]
                    _wsc  = float(w.get("wallet_score") or 0)
                    _wtok = str(w.get("token_address") or "?")[:8]
                    _pct  = _wsc / _wmax if _wmax > 0 else 0
                    # Color by conviction tier
                    if _pct >= 0.85:
                        _nc, _glow = "#FFD700", "rgba(255,215,0,0.25)"
                    elif _pct >= 0.6:
                        _nc, _glow = "#14F195", "rgba(20,241,149,0.15)"
                    elif _pct >= 0.35:
                        _nc, _glow = "#8EF9FF", "rgba(142,249,255,0.1)"
                    else:
                        _nc, _glow = "#9945FF", "rgba(153,69,255,0.08)"
                    _bar_w = max(4, int(_pct * 60))
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:8px;'
                        f'padding:5px 8px;margin-bottom:3px;border-radius:5px;'
                        f'background:{_glow};border-left:3px solid {_nc};">'
                        f'<div style="width:{_bar_w}px;height:6px;border-radius:3px;'
                        f'background:{_nc};opacity:0.85;flex-shrink:0;"></div>'
                        f'<span style="font-family:Share Tech Mono;font-size:0.62rem;'
                        f'color:{_nc};">{_wid}…</span>'
                        f'<span style="font-family:Share Tech Mono;font-size:0.6rem;'
                        f'color:#888;margin-left:auto;">{_wtok}… {_wsc:.1f}</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.markdown(
                    f'<div style="font-family:Share Tech Mono;font-size:0.62rem;'
                    f'color:#444;padding:8px;">// NO WALLET SIGNALS //</div>',
                    unsafe_allow_html=True,
                )
        except Exception:
            st.markdown(
                f'<div style="font-family:Share Tech Mono;font-size:0.62rem;'
                f'color:#444;padding:8px;">wallet_scout initializing</div>',
                unsafe_allow_html=True,
            )


@st.fragment(run_every=30)
def render_intelligence_substrate_panel():
    """
    HUNTING GROUNDS — Smart money substrate with real wallet data.
    Reads from watched_wallets, telegram_channel_trust, and symbiotic_candidates.
    Shows archetype badges, tier classification, and enrichment health.
    """
    import time as _t, html as _h
    now = _t.time()

    # ── LAMPBOARD ─────────────────────────────────────────────────────────────
    _wn = _cln = _hwn = _tn = 0
    try:
        _r = query_db("SELECT COUNT(*) n FROM watched_wallets WHERE active=1")
        _wn = int(_r["n"].iloc[0]) if not _r.empty else 0
        _r2 = query_db("SELECT COUNT(*) n FROM watched_wallets WHERE active=1 AND win_rate >= 0.7")
        _hwn = int(_r2["n"].iloc[0]) if not _r2.empty else 0
        _r3 = query_db("SELECT COUNT(*) n FROM telegram_channel_trust WHERE accuracy_score > 0.5")
        _tn = int(_r3["n"].iloc[0]) if not _r3.empty else 0
    except Exception:
        pass

    def _lmp(label, active, count=0):
        if active and count >= 3: nc, glow, dot = "#FFD700", "rgba(255,215,0,0.2)", "●"
        elif active:              nc, glow, dot = "#14F195", "rgba(20,241,149,0.12)", "●"
        else:                     nc, glow, dot = "#333",    "transparent",           "○"
        return (f'<span style="display:inline-flex;align-items:center;gap:3px;padding:2px 7px;'
                f'border-radius:4px;background:{glow};border:1px solid {nc}33;margin-right:4px;">'
                f'<span style="color:{nc};font-size:0.6rem;">{dot}</span>'
                f'<span style="font-family:Share Tech Mono;font-size:0.55rem;color:{nc};">'
                f'{label}{(" ×"+str(count)) if active and count>1 else ""}</span></span>')

    _lamps = _lmp("PREDATORS", _wn>0, _wn) + _lmp("HIGH-WR", _hwn>0, _hwn) + _lmp("TG SIGNAL", _tn>0, _tn)

    st.markdown(
        f'''<div class="substrate-wrap">
        <div class="substrate-title">⬡ HUNTING GROUNDS — SMART MONEY SUBSTRATE</div>
        <div class="substrate-sub">Predator registry · Telegram prey · Enrichment health · Shared infra with Council forge.</div>
        <div style="margin-top:6px;">{_lamps}</div>
        </div>''',
        unsafe_allow_html=True
    )

    _sc1, _sc2, _sc3 = st.columns(3, gap="large")

    # ── COL 1: WALLET PREDATOR REGISTRY ──────────────────────────────────────
    with _sc1:
        wallets = []
        try:
            _wd = query_db("""
                SELECT wallet_address, label, profit_score,
                       win_rate, trade_count, last_seen, added_at
                FROM watched_wallets WHERE active=1
                ORDER BY profit_score DESC LIMIT 6
            """)
            if not _wd.empty:
                wallets = _wd.to_dict("records")
        except Exception:
            pass

        # Also pull symbiotic candidates if watched_wallets empty
        if not wallets:
            try:
                _sd = query_db("""
                    SELECT wallet_observation_id as wallet_address,
                           wallet_score as profit_score,
                           token_address as label,
                           0 as win_rate, 0 as trade_count,
                           first_seen_at as last_seen
                    FROM symbiotic_candidates
                    WHERE wallet_score > 0.3
                    ORDER BY wallet_score DESC LIMIT 6
                """)
                if not _sd.empty:
                    wallets = _sd.to_dict("records")
            except Exception:
                pass

        st.markdown(
            f'<div class="substrate-card" style="border-color:#14F19588;">',
            unsafe_allow_html=True
        )
        st.markdown(
            f'<div class="substrate-head" style="color:#14F195;">👁️ PREDATOR REGISTRY ({len(wallets)})</div>',
            unsafe_allow_html=True
        )

        if not wallets:
            st.markdown(
                '<div class="substrate-muted">// NO PREDATORS TRACKED //<br>Run: python initiate_intelligence_build.py</div>',
                unsafe_allow_html=True
            )
        else:
            for w in wallets:
                wr    = float(w.get("win_rate") or 0)
                score = float(w.get("profit_score") or 0)
                tc    = int(w.get("trade_count") or 0)
                lbl   = str(w.get("label") or w.get("wallet_address") or "")[:14]
                ls    = float(w.get("last_seen") or 0)
                ls_str = f"{round((now-ls)/3600,1)}h ago" if ls else "never"

                # Archetype
                if wr >= 0.7 and tc > 20:   arch, ac = "SNIPER",   "#FFD700"
                elif wr >= 0.55 and score>3: arch, ac = "SMART$",   "#14F195"
                elif tc > 50 and wr < 0.35:  arch, ac = "WASH⚠",   "#FF073A"
                elif score > 8:              arch, ac = "LIQ HNT",  "#8EF9FF"
                else:                         arch, ac = "SCOUT",    "#666"

                st.markdown(
                    f'''<div style="padding:5px 6px;border-left:2px solid {ac}44;
                    margin-bottom:4px;font-family:Share Tech Mono;font-size:0.58rem;">
                    <span style="color:#CCC;">{_h.escape(lbl)}</span>
                    <span style="color:{ac};margin-left:6px;">{arch}</span>
                    <span style="color:#666;float:right;">{wr:.0%} WR · {ls_str}</span>
                    </div>''',
                    unsafe_allow_html=True
                )
        st.markdown('</div>', unsafe_allow_html=True)

    # ── COL 2: TELEGRAM SIGNAL PREY ──────────────────────────────────────────
    with _sc2:
        tg_rows = []
        try:
            _td = query_db("""
                SELECT channel_name, channel_id, accuracy_score,
                       calls_total, calls_hit, avg_x, last_updated
                FROM telegram_channel_trust
                ORDER BY accuracy_score DESC LIMIT 5
            """)
            if not _td.empty:
                tg_rows = _td.to_dict("records")
        except Exception:
            pass

        st.markdown(
            '<div class="substrate-card" style="border-color:#8EF9FF88;">',
            unsafe_allow_html=True
        )
        st.markdown(
            '<div class="substrate-head" style="color:#8EF9FF;">📡 SIGNAL PREY — TELEGRAM</div>',
            unsafe_allow_html=True
        )

        if not tg_rows:
            st.markdown(
                '<div class="substrate-muted">// AWAITING CHANNEL AUDIT //<br>Council will score channels autonomously.</div>',
                unsafe_allow_html=True
            )
        else:
            for ch in tg_rows:
                acc   = float(ch.get("accuracy_score") or 0)
                hits  = int(ch.get("calls_hit") or 0)
                total = int(ch.get("calls_total") or 0)
                name  = str(ch.get("channel_name") or "Unknown")[:20]
                col   = "#14F195" if acc > 0.6 else ("#FFD700" if acc > 0.4 else "#FF073A")
                st.markdown(
                    f'''<div style="padding:5px 6px;border-left:2px solid {col}44;
                    margin-bottom:4px;font-family:Share Tech Mono;font-size:0.58rem;">
                    <span style="color:{col};">{_h.escape(name)}</span><br>
                    <span style="color:#666;">acc={acc:.0%} · {hits}/{total} hits</span>
                    </div>''',
                    unsafe_allow_html=True
                )
        st.markdown('</div>', unsafe_allow_html=True)

    # ── COL 3: ENRICHMENT HEALTH ──────────────────────────────────────────────
    with _sc3:
        pq = mtm = mcap_miss = sv = 0
        try:
            _e1 = query_db("SELECT COUNT(*) n FROM market_snapshots WHERE quality_status='pending' AND candidate_state='pending'")
            pq = int(_e1["n"].iloc[0]) if not _e1.empty else 0
            _e2 = query_db("SELECT COUNT(*) n FROM market_snapshots WHERE candidate_state='mtm' AND quality_status='pending'")
            mtm = int(_e2["n"].iloc[0]) if not _e2.empty else 0
            _e3 = query_db("SELECT COUNT(*) n FROM market_snapshots WHERE quality_status='pending' AND (market_cap_usd IS NULL OR market_cap_usd=0)")
            mcap_miss = int(_e3["n"].iloc[0]) if not _e3.empty else 0
            _e4 = query_db("SELECT COUNT(*) n FROM market_snapshots WHERE latched=0 AND quality_status='qualified' AND price_status='priced' AND is_tradeable=1")
            sv = int(_e4["n"].iloc[0]) if not _e4.empty else 0
        except Exception:
            pass

        bottleneck = pq > 50 or mcap_miss > 20
        bc = "#FF073A" if bottleneck else "#14F195"
        btext = "⚠ ENRICHMENT_BOTTLENECK" if bottleneck else "✓ PIPELINE_CLEAR"

        st.markdown(
            f'''<div class="substrate-card" style="border-color:{bc}88;">
            <div class="substrate-head" style="color:{bc};">🔬 ENRICHMENT HEALTH</div>
            <div style="font-family:Share Tech Mono;font-size:0.6rem;color:{bc};margin-bottom:8px;">{btext}</div>''',
            unsafe_allow_html=True
        )

        def _ebar(label, val, warn_at, col_ok="#14F195", col_warn="#FF073A"):
            c = col_warn if val > warn_at else col_ok
            pct = min(100, int(val / max(1, warn_at * 2) * 100))
            return (f'<div style="margin-bottom:5px;font-family:Share Tech Mono;font-size:0.55rem;">'                   f'<span style="color:#666;">{label}</span>'                   f'<span style="color:{c};float:right;">{val}</span>'                   f'<div style="height:2px;background:#111;margin-top:2px;">'                   f'<div style="width:{pct}%;height:100%;background:{c};"></div></div></div>')

        bars = (
            _ebar("PENDING QUAL", pq, 50)
            + _ebar("MTM BLIND",  mtm, 20)
            + _ebar("MCAP MISS",  mcap_miss, 15)
            + f'<div style="font-family:Share Tech Mono;font-size:0.55rem;color:#14F195;margin-top:6px;">SUPERVISOR VISIBLE: {sv}</div>'
        )
        st.markdown(bars + '</div>', unsafe_allow_html=True)



@st.cache_data(ttl=30, show_spinner=False)
def fetch_live_open_positions_breathe(db_path_str: str, refresh_bucket: int) -> list:
    """
    SIGN-OFF LIVE TRADE TRUTH SOURCE.

    Visible open-position PnL is sourced from paper_positions.live_exec_* only.
    market_snapshots is retained only as structural context / optional snap metadata.
    If execution has not written live_exec data, the UI shows NO_EXEC_DATA instead
    of synthesising fake micro-movement from snapshots.

    SAME-EYES ENHANCEMENT: Also reads mtm_ticks from sentinuity_intelligence.db
    directly — the same Tier-1 source the executor uses — so the UI sees the real
    live price without waiting for the executor write cycle. This closes the gap
    where positions close at 79% but the meter only ever showed 0% because the
    executor hadn't written live_exec_pct yet.
    """
    import time
    try:
        conn = sqlite3.connect(db_path_str, check_same_thread=False, timeout=2.0)
        conn.row_factory = sqlite3.Row

        # Cache oracle gate config in session_state so render_living_trade_meter
        # can read it without a separate DB query per render cycle.
        try:
            _gate_row = conn.execute(
                "SELECT value FROM system_config WHERE key='ORACLE_LIVENESS_GATE_SEC'"
            ).fetchone()
            if _gate_row:
                st.session_state["_cfg_oracle_gate"] = float(_gate_row[0])
        except Exception:
            pass

        rows = conn.execute("""
            SELECT p.*,
                   COALESCE(m.observed_price, p.entry_price) AS snap_price,
                   COALESCE(m.price_updated_at, p.last_marked_at) AS snap_marked_at
            FROM paper_positions p
            LEFT JOIN (
                SELECT mint_address, observed_price, price_updated_at
                FROM market_snapshots
                WHERE candidate_state = 'mtm' AND observed_price > 0
                GROUP BY mint_address
                HAVING price_updated_at = MAX(price_updated_at)
            ) m ON p.mint_address = m.mint_address
            WHERE p.status = 'OPEN'
            ORDER BY p.opened_at DESC
        """).fetchall()
        conn.close()

        # Build Intel DB price map — same Tier-1 source as executor
        # Keyed by mint_address → {price, age_sec}
        _intel_prices: dict = {}
        for _intel_path in INTEL_DB_PATHS:
            try:
                _ic = sqlite3.connect(str(_intel_path), timeout=1.0)
                _ic.row_factory = sqlite3.Row
                _iticks = _ic.execute(
                    "SELECT mint_address, price_usd, ts_ms "
                    "FROM mtm_ticks "
                    "ORDER BY ts_ms DESC LIMIT 200"
                ).fetchall()
                _ic.close()
                _inow = time.time()
                for _t in _iticks:
                    _m = str(_t["mint_address"] or "")
                    if _m and _m not in _intel_prices:
                        _ip = float(_t["price_usd"] or 0)
                        _ia = _inow - float(_t["ts_ms"] or 0) / 1000.0
                        if _ip > 0 and _ia >= 0:
                            _intel_prices[_m] = {"price": _ip, "age": _ia}
                break  # first working intel DB is enough
            except Exception:
                pass

        now = time.time()
        payload = []
        seen_ids = set()

        for r in rows:
            _pos_id = r["id"]
            if _pos_id in seen_ids:
                continue
            seen_ids.add(_pos_id)

            _keys = set(r.keys()) if hasattr(r, "keys") else set()

            def _get(key, default=None):
                try:
                    return r[key] if key in _keys else default
                except Exception:
                    return default

            entry = float(_get("entry_price", 0.0) or 0.0)
            size  = float(_get("position_size_usd", 0.0) or 0.0)

            # Execution engine owns live visible truth.
            _lep     = float(_get("live_exec_price", 0.0) or 0.0)
            _lect_raw = _get("live_exec_pct", None)
            _leu     = float(_get("live_exec_updated_at", 0.0) or 0.0)
            _can_exit = int(_get("live_exec_can_exit", 0) or 0)

            # SAME-EYES: if executor hasn't written live_exec yet (new position),
            # read directly from Intel DB mtm_ticks — same Tier-1 source as executor.
            # This closes the gap where meter shows 0% until executor catches up.
            _mint = str(_get("mint_address", "") or "")
            _opened_at = float(_get("opened_at", 0.0) or 0.0)
            _intel = _intel_prices.get(_mint)
            if (_intel and _intel["price"] > 0 and _intel["age"] < 120
                    and (_lect_raw is None or _can_exit != 1)):
                _ip  = _intel["price"]
                _ia  = _intel["age"]
                _ep2 = float(_get("entry_price", 0.0) or 0.0)
                if _ep2 > 0 and _ip > 0:
                    _intel_pct = (_ip - _ep2) / _ep2 * 100.0
                    _lep      = _ip
                    _lect_raw = _intel_pct
                    _leu      = now - _ia
                    _can_exit = 1 if _ia < 120 else 0

            if _lep > 0 and _lect_raw is not None and _can_exit == 1:
                pnl_pct = float(_lect_raw)
                pnl = size * (pnl_pct / 100.0) if size > 0 else 0.0
                mark_age = int(now - _leu) if _leu > 0 else 9999
                is_fresh = mark_age < 15
                age_str = f"{mark_age}s"
                src_badge = "LIVE" if is_fresh else "STALE_EXEC"
            elif _lep > 0 and _lect_raw is not None and _can_exit != 1:
                # Price exists but router says not executable — show ?? not fake %
                pnl_pct = None
                pnl = 0.0
                mark_age = int(now - _leu) if _leu > 0 else 9999
                is_fresh = False
                age_str = f"{mark_age}s"
                src_badge = "GATE_BLOCKED"
            else:
                pnl_pct = None
                pnl = 0.0
                mark_age = 9999
                is_fresh = False
                age_str = "NO EXEC"
                src_badge = "NO_EXEC_DATA"

            _ss_key = f"_prev_pct_{_pos_id}"
            _prev = st.session_state.get(_ss_key)
            if pnl_pct is not None:
                st.session_state[_ss_key] = pnl_pct

            # Post-entry tick count from Intel DB for coverage display
            _tick_count = 0
            try:
                import sqlite3 as _sq3
                _idb_path = str(_Path(__file__).resolve().parent.parent / "sentinuity_intelligence.db")
                _ic = _sq3.connect(_idb_path, timeout=1.0)
                _tc_row = _ic.execute(
                    "SELECT COUNT(*) FROM mtm_ticks WHERE mint_address=? AND ts_ms>=?",
                    (str(_get("mint_address", "") or ""), float(_get("opened_at", 0) or 0) * 1000)
                ).fetchone()
                _ic.close()
                _tick_count = int(_tc_row[0]) if _tc_row else 0
            except Exception:
                pass

            payload.append({
                "id":                 _pos_id,
                "token":              str(_get("token_name", "") or _get("mint_address", "?"))[:18],
                "pnl":                pnl,
                "pnl_pct":            pnl_pct,
                "prev_pnl_pct":       _prev,
                "is_fresh":           is_fresh,
                "age_str":            age_str,
                "src_badge":          src_badge,
                "resolved_price":     _lep if _lep > 0 else None,
                "resolved_updated_at": _leu if _leu > 0 else None,
                "tick_count":         _tick_count,
                "raw_row":            dict(r),
            })

        return payload

    except Exception as e:
        _hub_log.warning(f"UI Breathe failed: {e}")
        return []

@st.cache_data(ttl=5, show_spinner=False)
def _fetch_all_dashboard_data():
    conn = None
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=10, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=15000")  # was 5000 — raised to reduce blank renders under WAL contention
        conn.row_factory = sqlite3.Row

        _wallet_df      = pd.read_sql_query("SELECT wallet_balance, initial_capital FROM system_state WHERE id=1 LIMIT 1", conn)
        _raw_dna_df     = pd.read_sql_query("SELECT COUNT(*) AS count FROM raw_dna", conn)
        _snapshots_df   = pd.read_sql_query("""
            SELECT id, token_name, mint_address, mint_confidence, candidate_state, quality_status, price_status, latched
            FROM market_snapshots
            WHERE candidate_state = 'latched'
              OR id IN (SELECT id FROM market_snapshots ORDER BY id DESC LIMIT 50)
            ORDER BY id DESC LIMIT 100
        """, conn)
        _open_pos_df    = pd.read_sql_query("""
            SELECT id, token_name, mint_address, status,
                   entry_price, position_size_usd, unrealized_pnl_usd,
                   opened_at, last_marked_at, last_price, highest_price_seen,
                   take_profit_pct, stop_loss_pct,
                   live_exec_price, live_exec_pct, live_exec_band,
                   live_exec_updated_at, live_exec_source,
                   entry_price AS dashboard_last_price,
                   last_marked_at AS dashboard_last_marked_at,
                   unrealized_pnl_usd AS dashboard_unrealized,
                   NULL AS mtm_age_seconds
            FROM paper_positions WHERE status = 'OPEN' ORDER BY opened_at DESC
        """, conn)
        _executions_df    = pd.read_sql_query("SELECT * FROM paper_executions ORDER BY id DESC LIMIT 20", conn)
        _reviews_df       = pd.read_sql_query("SELECT win_loss, realized_pnl_usd, exit_category, hold_seconds, entry_mint_confidence FROM polaris_trade_reviews ORDER BY reviewed_at DESC LIMIT 50", conn)
        _proposals_df     = pd.read_sql_query("SELECT id, proposal_type, proposal_text, suggested_action, confidence, status, created_at, unified_diff, rewritten_code FROM polaris_proposals ORDER BY created_at DESC LIMIT 20", conn)
        _proposals_df     = _apply_focus_lock(_proposals_df)
        _debate_df        = pd.read_sql_query(
            "SELECT speaker, "
            "COALESCE(json_extract(content_json,'$.verdict'),json_extract(content_json,'$.summary'),"
            "json_extract(content_json,'$.rebuttal_summary'),message,action,'') AS verdict_text, "
            "thinking_state, verdict_type, approved_by, logged_at, content_json, "
            "COALESCE(json_extract(content_json,'$.search_query'),'')  AS oracle_query, "
            "COALESCE(json_extract(content_json,'$.confirmed'),'')     AS oracle_confirmed, "
            "COALESCE(json_extract(content_json,'$.evidence_snippets'),'') AS oracle_snippets, "
            "COALESCE(json_extract(content_json,'$.winner'),'')        AS nugget_winner, "
            "COALESCE(json_extract(content_json,'$.reason'),'')        AS nugget_reason, "
            "COALESCE(json_extract(content_json,'$.confidence'),'')    AS nugget_confidence, "
            "COALESCE(json_extract(content_json,'$.recommended_next_step'),'') AS nugget_next, "
            "COALESCE(json_extract(content_json,'$.objections'),'')    AS ivaris_objections, "
            "COALESCE(json_extract(content_json,'$.narrative'),'') AS grok_narrative, "
            "COALESCE(proposal_id, NULL) AS proposal_id "
            "FROM debate_log ORDER BY logged_at DESC LIMIT 30",
            conn
        )
        if _debate_df.empty:
            _dh_raw = pd.read_sql_query("SELECT id, proposal_id, transcript_json, created_at FROM debate_history ORDER BY created_at DESC LIMIT 20", conn)
            if not _dh_raw.empty:
                import json as _json
                _mapped = []
                for _, _dh_row in _dh_raw.iterrows():
                    _ts = float(_dh_row.get("created_at") or 0)
                    _raw = _dh_row.get("transcript_json") or "[]"
                    try: _turns = _json.loads(_raw) if isinstance(_raw, str) else _raw
                    except Exception: _turns = []
                    if not isinstance(_turns, list): _turns = [_turns] if isinstance(_turns, dict) else []
                    for idx, _turn in enumerate(_turns):
                        _spk    = str(_turn.get("speaker") or "SYSTEM").upper()
                        _action = str(_turn.get("action") or "")
                        _result = _turn.get("result") or {}
                        _vtext = (_result.get("verdict") or _result.get("summary") or _result.get("rebuttal_summary") or _action)
                        if _action == "initial_critique": _tstate, _vtype = "critiquing", "initial_critique"
                        elif _action == "rebuttal": _tstate, _vtype = "rebutting", "rebuttal"
                        elif _action == "rebuttal_evaluation": _tstate, _vtype = "evaluating", "rebuttal_evaluation"
                        else: _tstate, _vtype = "critiquing", _action
                        if idx == len(_turns) - 1:
                            if _result.get("_critic_unavailable") or _result.get("_cognitive_failure"): _tstate, _vtype = "blocked", "blocked"
                            elif _result.get("consensus"): _tstate, _vtype = "consensus", "final_consensus"
                            else: _tstate, _vtype = "rejected", "final_rejection"
                        _mapped.append({"speaker": _spk, "verdict_text": str(_vtext or ""), "thinking_state": _tstate, "verdict_type": _vtype, "approved_by": str(_result.get("approved_by") or ""), "logged_at": _ts + idx * 0.001})
                if _mapped: _debate_df = pd.DataFrame(_mapped)

        _calibration_df   = pd.read_sql_query("SELECT key, value FROM system_config WHERE key IN ('SUPERVISOR_MIN_MINT_CONFIDENCE','DRAWDOWN_HALT_ACTIVE','DRAWDOWN_ACCUMULATED_PCT','POSITION_SIZE_PCT','STOP_LOSS_PCT','TAKE_PROFIT_PCT','MIN_LIQUIDITY_USD','TRAIL_ACTIVATE_PCT')", conn)
        _open_count_df    = pd.read_sql_query("SELECT COUNT(*) as n FROM paper_positions WHERE status='OPEN'", conn)
        _heal_log_df      = pd.read_sql_query("SELECT timestamp, stage, message FROM cognition_log WHERE stage IN ('GUARDIAN','HEALER','WATCHDOG','HEALTH','POLARIS','SYS','EXECUTOR','SUPERVISOR','DEBATE','SYSTEM','SCOUT','SYMBIOTIC') ORDER BY timestamp DESC LIMIT 8", conn)
        _heartbeat_df     = pd.read_sql_query("SELECT service_name, status, last_pulse, COALESCE(note, '') AS note FROM system_heartbeat ORDER BY service_name ASC", conn)
        _patch_history_df = pd.read_sql_query("SELECT applied_at, NULL AS proposal_id, proposal_type, action, outcome, NULL AS confidence, brave_confirmed, '' AS notes FROM patch_history ORDER BY applied_at DESC LIMIT 10", conn)
        _autopsy_df       = pd.read_sql_query("SELECT id, win_loss, realized_pnl_usd FROM trade_autopsies ORDER BY id ASC LIMIT 100", conn)
        _cognition_df     = pd.read_sql_query("SELECT id, timestamp AS sort_ts, timestamp, COALESCE(stage, 'SCOUT') AS stage, COALESCE(token, '') AS token, message, COALESCE(confidence, 0.0) AS confidence FROM cognition_log ORDER BY timestamp DESC LIMIT 25", conn)

        return (_wallet_df, _raw_dna_df, _snapshots_df, _open_pos_df, _executions_df, _reviews_df, _proposals_df, _debate_df, _calibration_df, _open_count_df, _heal_log_df, _heartbeat_df, _patch_history_df, _autopsy_df, _cognition_df)

    except Exception:
        empty = pd.DataFrame()
        return (empty,) * 15

    finally:
        if conn:
            conn.close()

def _fmt_clock(ts: float) -> str:
    try: return time.strftime("%H:%M:%S", time.localtime(float(ts)))
    except Exception: return ""

@st.cache_data(ttl=8, show_spinner=False)
def build_live_event_feed(cognition_df, executions_df, open_pos_df, snapshots_df, proposals_df):
    frames = []
    if cognition_df is not None and not cognition_df.empty:
        base = cognition_df.copy()
        for col, default in [("sort_ts", 0.0), ("timestamp", ""), ("stage", "SCOUT"), ("token", ""), ("message", ""), ("confidence", 0.0), ("id", 0)]:
            if col not in base.columns: base[col] = default
        frames.append(base[["id", "sort_ts", "timestamp", "stage", "token", "message", "confidence"]])

    if executions_df is not None and not executions_df.empty:
        exec_rows = []
        for _, row in executions_df.head(12).iterrows():
            ts = float(row.get("timestamp") or row.get("created_at") or 0.0)
            side = str(row.get("side", "")).upper()
            token = str(row.get("token_name", "") or row.get("mint_address", "") or "").strip()
            if not token: continue
            price = float(row.get("price") or 0.0)
            value = float(row.get("notional_usd") or row.get("value_usd") or 0.0)
            reason = str(row.get("reason", "") or "").strip()
            if side == "BUY": msg = f"Deployed ${value:.2f} into {token}. Entry armed at ${price:.8f}." + (f" Trigger: {reason}." if reason else "")
            elif side == "SELL": msg = f"Motor output closed {token} at ${price:.8f} for ${value:.2f}." + (f" Exit: {reason}." if reason else "")
            else: msg = f"Execution event on {token} at ${price:.8f}."
            exec_rows.append({"id": 1_000_000 + int(row.get("id", 0) or 0), "sort_ts": ts, "timestamp": _fmt_clock(ts), "stage": "EXECUTOR", "token": token[:14], "message": msg, "confidence": 0.0})
        if exec_rows: frames.append(pd.DataFrame(exec_rows))

    if snapshots_df is not None and not snapshots_df.empty:
        snap_rows = []
        for _, row in snapshots_df.head(16).iterrows():
            state = str(row.get("candidate_state", "") or "").lower()
            token = str(row.get("token_name", "") or row.get("mint_address", "") or "").strip()
            if not token: continue
            conf = float(row.get("mint_confidence") or 0.0)
            ts = float(row.get("price_updated_at") or row.get("updated_at") or row.get("created_at") or row.get("timestamp") or 0.0)
            if state in {"latched", "qualified"}: msg, stage = f"All gates passed for {token}. Signal latched at conf {conf:.3f}.", "SUPERVISOR"
            elif state in {"vetoed", "rejected"}: msg, stage = f"{token} vetoed at the gate memory layer.", "SUPERVISOR"
            else: continue
            snap_rows.append({"id": 2_000_000 + int(row.get("id", 0) or 0), "sort_ts": ts, "timestamp": _fmt_clock(ts), "stage": stage, "token": token[:14], "message": msg, "confidence": conf})
        if snap_rows: frames.append(pd.DataFrame(snap_rows))

    if not frames: return pd.DataFrame(columns=["id", "sort_ts", "timestamp", "stage", "token", "message", "confidence"])
    merged = pd.concat(frames, ignore_index=True, sort=False)
    merged["dedup_key"] = merged["stage"].astype(str).fillna("") + "|" + merged["token"].astype(str).fillna("") + "|" + merged["message"].astype(str).fillna("")
    merged = merged.sort_values(["sort_ts", "id"], ascending=[False, False]).drop_duplicates(subset=["dedup_key"], keep="first")
    return merged.head(40).copy()

def get_dominant_state(halted, latency, open_pos, recent_heal_count, win_r):
    if halted:              return "HALTED",        "The organism has severed execution nerves to protect capital.", C_RED
    if latency > 1000:      return "WOUNDED",       "Experiencing severe neural lag. Reflexes impaired.", C_IVY
    if recent_heal_count>0: return "SELF-HEALING", "Actively repairing pipeline blockages and restoring flow.", C_PURPLE
    if open_pos > 0:        return "EXECUTING",    "Exposed to the market. Managing active live capital.", C_GOLD
    if win_r > 60:          return "ASCENDING",    "Highly calibrated, profitable, and scanning for prime entry.", C_PURPLE
    return "HUNTING", "Stable, selective, and hunting with strict restraint.", C_PURPLE

def write_organism_state(dom_state, dom_col, cog_df, auto_df):
    def safe_int(v):
        try: return int(float(v)) if pd.notna(v) else 0
        except: return 0
    feed_data = [{"id": safe_int(r.get('id')), "stage": str(r.get('stage','')).upper(), "token": str(r.get('token',''))[:14], "message": str(r.get('message','')), "timestamp": str(r.get('timestamp',''))[-8:][:5], "color": dom_col} for _, r in cog_df.iterrows()]
    canopy_nodes = [{"id": safe_int(r.get('id')), "type": "WIN" if str(r.get('win_loss','')).upper()=="WIN" else "LOSS", "val": abs(float(r.get('realized_pnl_usd',0)))*2} for _, r in auto_df.iterrows()]
    return json.dumps({"dominant_state": dom_state, "color": dom_col, "cognition": feed_data, "canopy": canopy_nodes})

def build_cognitive_canopy(state_json_str: str) -> str:
    return f"""<!DOCTYPE html>
    <html><head>
        <style>
            @import url('https://fonts.googleapis.com/css2?family=VT323&display=swap');
            body {{ margin:0; padding:0; background:transparent; color:#8EF9FF; font-family:'VT323',monospace; overflow:hidden; display:flex; flex-direction:column; gap:15px; height:100vh;}}
            #state-bar {{ display:flex; align-items:center; justify-content:space-between; padding:10px 20px; background:rgba(5,10,10,0.6); border:1px solid #8EF9FF44; border-radius:12px; box-shadow:0 0 20px rgba(0,0,0,0.5);}}
            #voice-init {{ background:#14F19522; color:#14F195; border:1px solid #14F195; padding:8px 16px; font-family:'VT323',monospace; letter-spacing:2px; cursor:pointer; border-radius:6px; transition:0.3s; }}
            #main-arena {{ display:flex; gap:15px; height:calc(100vh - 60px); }}
            #eternal-cortex {{ flex:1; overflow:hidden; background:rgba(5,10,10,0.4); border:1px solid #8EF9FF44; border-radius:16px; position:relative; box-shadow:inset 0 0 40px rgba(0,0,0,0.8); }}
            #thought-stream {{ height:100%; overflow-y:auto; padding:20px; scrollbar-width:none; }}
            #thought-stream::-webkit-scrollbar {{ display:none; }}
            #canopy-container {{ flex:1.5; border-radius:16px; border:1px solid #FFD70033; overflow:hidden; position:relative; box-shadow:0 0 30px #FFD70011; background: radial-gradient(ellipse at 50% 50%, rgba(153,69,255,0.08) 0%, transparent 70%), radial-gradient(ellipse at 20% 80%, rgba(20,241,149,0.05) 0%, transparent 50%), #050210; }}
        </style>
    </head><body>
    <div id="organism-state-data" style="display:none;visibility:hidden;position:absolute;">{state_json_str}</div>
    <div id="state-bar">
        <div style="display:flex;align-items:center;gap:15px;"><button id="voice-init">AWAKEN AUTONOMIC RESONANCE</button><span id="voice-state" style="color:#8EF9FF;letter-spacing:2px;font-size:1.1rem;">CORTEX DORMANT</span></div>
        <div id="visual-state" style="font-size:1.4rem;font-weight:bold;letter-spacing:4px;text-shadow:0 0 10px #FFF;">SYNCING...</div>
    </div>
    <div id="main-arena"><div id="eternal-cortex"><div id="thought-stream"></div></div><div id="canopy-container"></div></div>
    <script>
        setTimeout(function() {{
            try {{
                var stateEl = document.getElementById('organism-state-data');
                var _raw = stateEl.textContent || stateEl.innerText || '';
                var liveState = JSON.parse(_raw);
                document.getElementById('visual-state').innerText = liveState.dominant_state;
                document.getElementById('visual-state').style.color = liveState.color;

                var stream = document.getElementById('thought-stream');
                var known = new Set();
                try {{ known = new Set(JSON.parse(sessionStorage.getItem('eternalBrain') || '[]')); }} catch(e){{}}
                
                var sorted = (liveState.cognition || []).slice().sort((a,b) => a.id - b.id);
                sorted.forEach(entry => {{
                    if(known.has(entry.id)) return;
                    known.add(entry.id);
                    var t = document.createElement('div');
                    t.style.cssText = 'margin-bottom:18px;padding:12px 16px;background:rgba(5,2,16,0.6);border-left:5px solid ' + entry.color + ';';
                    t.innerHTML = '<span style="color:' + entry.color + ';font-weight:900;">' + entry.stage + '</span><span style="float:right;color:#FFD700;font-size:0.85rem;">' + entry.timestamp + '</span><br><span style="color:#9945FF;">' + (entry.token || '-') + '</span> - <span style="color:#FFF;">' + entry.message + '</span>';
                    stream.appendChild(t);
                }});
                stream.scrollTop = stream.scrollHeight;
                try {{ sessionStorage.setItem('eternalBrain', JSON.stringify(Array.from(known))); }} catch(e){{}}

                var _cc = document.getElementById('canopy-container');
                if(!liveState.canopy || liveState.canopy.length === 0) {{
                    _cc.innerHTML = '<div style="position:absolute;top:50%;left:50%;transform:translate(-50%,-50%);color:rgba(153,69,255,0.35);font-family:VT323,monospace;font-size:1.1rem;letter-spacing:3px;text-align:center;">TEMPORAL CANOPY<br><span style="font-size:.7rem;opacity:.6;">AWAITING TRADE HISTORY</span></div>';
                }} else {{
                    let wins = liveState.canopy.filter(n => n.type === 'WIN');
                    let losses = liveState.canopy.filter(n => n.type === 'LOSS');
                    let svgHtml = '<div style="position:absolute; top:15px; left:15px; z-index:10; font-family:VT323,monospace; font-size:1.2rem; color:#8EF9FF;">CANOPY CONSTELLATION<br><span style="color:#FFD700">WINS: ' + wins.length + '</span> | <span style="color:#FF073A">LOSSES: ' + losses.length + '</span> | TOTAL: ' + liveState.canopy.length + '</div>';
                    svgHtml += '<svg width="100%" height="100%" viewBox="-250 -250 500 500" preserveAspectRatio="xMidYMid meet" style="position:absolute;top:0;left:0;"><style>.core {{ fill: #9945FF; animation: pulseCore 2s infinite alternate; }} @keyframes pulseCore {{ 0% {{ r: 8; opacity: 0.6; }} 100% {{ r: 14; opacity: 1; filter: drop-shadow(0 0 10px #9945FF); }} }}</style><circle class="core" cx="0" cy="0" r="10" />';
                    liveState.canopy.forEach(function(n) {{
                        let angle = (n.id * 137.508) % 360; let rad = angle * Math.PI / 180;
                        let isWin = n.type === 'WIN'; let radius = isWin ? (120 + (n.id % 60)) : (50 + (n.id % 40));
                        let cx = Math.cos(rad) * radius; let cy = Math.sin(rad) * radius;
                        let r = isWin ? 3.5 : 2.5; let fill = isWin ? '#FFD700' : '#FF073A';
                        let dur = 3 + (n.id % 4); let rotDur = 40 + (n.id % 60); let dir = isWin ? 360 : -360;
                        svgHtml += '<g><animateTransform attributeName="transform" type="rotate" from="0 0 0" to="' + dir + ' 0 0" dur="' + rotDur + 's" repeatCount="indefinite" /><circle cx="' + cx + '" cy="' + cy + '" r="' + r + '" fill="' + fill + '" opacity="0.8"><animate attributeName="opacity" values="0.3;1;0.3" dur="' + dur + 's" repeatCount="indefinite" /></circle></g>';
                    }});
                    svgHtml += '</svg>';
                    _cc.innerHTML = svgHtml;
                }}
            }} catch(err) {{
                var vs = document.getElementById('visual-state');
                if(vs) {{ vs.innerText = 'CORTEX FAULT: ' + err.message; vs.style.color = '#FF073A'; }}
            }}
        }}, 50);
    </script></body></html>"""

def build_dynamic_css(dom_col="#9945FF"):
    return f"""<style>
    @import url('https://fonts.googleapis.com/css2?family=VT323&display=swap');
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;500;700;800;900&family=Share+Tech+Mono&family=Rajdhani:wght@300;400;600;700&display=swap');

    :root {{
        --dom-color: {dom_col};
        --mycelial-purple: #9945FF;
        --machine-cyan: #8EF9FF;
        --north-star-cyan: #8EF9FF;
        --golden: #FFD700;
        --nugget-bronze: #C19A6B;
        --glass: rgba(5,10,10,0.32);
        --vein: rgba(153,69,255,0.28);
    }}

    /* NEURAL WEAVE — living gold-purple background veins */
    html::before {{
        content: ""; position: fixed; inset: 0; z-index: -3; pointer-events: none;
        background:
            radial-gradient(circle at 20% 30%, rgba(153,69,255,0.15) 0%, transparent 45%),
            radial-gradient(circle at 80% 70%, rgba(255,215,0,0.10) 0%, transparent 45%),
            radial-gradient(circle at 50% 90%, rgba(142,249,255,0.08) 0%, transparent 40%);
        animation: neuralWeave 28s linear infinite alternate;
    }}
    @keyframes neuralWeave {{
        0%   {{ opacity: 0.7; transform: scale(1.0); }}
        50%  {{ opacity: 1.0; transform: scale(1.04); }}
        100% {{ opacity: 0.8; transform: scale(0.98); }}
    }}

    html,body,[data-testid="stAppViewContainer"],.stApp {{
        background: radial-gradient(circle at 50% 30%, #1a0033 0%, #050210 70%) !important;
        color: var(--mycelial-purple);
        font-family: 'VT323', monospace;
        animation: mycelialPulse 18s infinite ease-in-out;
    }}
    @keyframes mycelialPulse {{
        0%, 100% {{ background-position: 0% 50%; }}
        50% {{ background-position: 100% 50%; }}
    }}

    [data-testid="stHeader"],[data-testid="stToolbar"],[data-testid="stDecoration"],
    .stSpinner,[data-testid="stStatusWidget"],footer,.stFooter {{
        display: none !important;
    }}
    .stApp,.stAppViewContainer {{ transition: none !important; }}

    /* ── NO-DIM: suppress Streamlit's stale-element dimming during rerun ── */
    /* Without this, every refresh dims the entire page while Streamlit reloads */
    [data-stale="true"], [data-stale] {{
        opacity: 1 !important;
        pointer-events: auto !important;
        filter: none !important;
        transition: none !important;
    }}
    /* Suppress the running/reloading indicator dot */
    [data-testid="stStatusWidget"], .stStatusWidget,
    div[class*="StatusWidget"], div[class*="statusWidget"] {{
        display: none !important;
    }}
    /* Keep old data visible and unblurred until new data overwrites */
    .stMarkdown, .stDataFrame, .stTable, .element-container {{
        transition: none !important;
    }}

    /* ── ZERO-LEAK SHIELD: raw errors never surface in organism layer ── */
    /* Stack traces, SQL dumps, Python errors stay in engineering panels only */
    .stException, [data-testid="stException"],
    div[class*="Exception"], .stAlert[data-baseweb="notification"] {{
        display: none !important;
    }}

    /* ── TEMPORAL HEATMAP STATE — ambient freshness atmosphere ── */
    /* CSS vars updated by JS below; create subconscious freshness awareness */
    :root {{
        --organism-heat: 0.0;
        --heat-glow: rgba(20, 241, 149, 0.03);
        --heat-border: rgba(20, 241, 149, 0.15);
    }}
    /* Subtle background pulse reflects organism heat level */
    [data-testid="stAppViewContainer"] {{
        background: radial-gradient(
            ellipse at 50% 0%,
            var(--heat-glow) 0%,
            transparent 60%
        ) !important;
    }}

    /* ── PANELS ── */
    .panel,.nerve-card,.lore-card,#dc-wrap,.hb-strip,.stDataFrame,.stTable,.stAlert {{
        background: var(--glass) !important;
        backdrop-filter: blur(16px) saturate(180%) !important;
        -webkit-backdrop-filter: blur(16px) saturate(180%) !important;
        border: 1px solid rgba(153,69,255,0.42) !important;
        border-radius: 16px !important;
        box-shadow: 0 0 28px rgba(153,69,255,0.24), inset 0 0 22px rgba(142,249,255,0.10) !important;
        margin-bottom: 20px;
        position: relative;
    }}
    .panel:hover,.lore-card:hover,#dc-wrap:hover {{
        box-shadow: 0 0 40px rgba(153,69,255,0.45), inset 0 0 25px rgba(142,249,255,0.15) !important;
    }}
    /* Mycelial veins connecting panels */
    .panel::after {{
        content: '';
        position: absolute;
        bottom: -20px; left: 50%;
        width: 3px; height: 40px;
        background: linear-gradient(to bottom, var(--vein), transparent);
        transform: translateX(-50%);
        z-index: -1;
    }}

    /* ── TYPOGRAPHY ── */
    h1 {{
        background: linear-gradient(90deg, #9945FF 0%, #FFD700 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        text-shadow: 0 0 35px rgba(153,69,255,0.85), 0 0 60px rgba(255,215,0,0.55) !important;
        font-size: clamp(2.6rem, 9vw, 4.4rem) !important;
        letter-spacing: clamp(8px, 3.5vw, 20px) !important;
        line-height: 1.05 !important;
        margin-bottom: 8px !important;
        padding: 0 10px;
    }}
    h2,h3 {{ text-shadow: 0 0 12px {C_PURPLE}, 0 0 24px {C_PURPLE}88; color: var(--mycelial-purple) !important; font-family: 'Orbitron', sans-serif !important; letter-spacing: 4px !important; }}
    p[style*="letter-spacing"] {{ color: var(--north-star-cyan) !important; text-shadow: 0 0 16px rgba(142,249,255,0.65) !important; font-size: 1.18rem !important; }}
    .stMarkdown p,label {{ color: #8EF9FF !important; text-shadow: 0 0 8px rgba(142,249,255,0.45); }}

    /* ── METRICS ── */
    [data-testid="stMetric"] {{ padding: 8px 12px !important; }}
    [data-testid="stMetricLabel"] {{ font-size: 0.84rem !important; margin-bottom: 8px !important; opacity: 0.92; color: #8EF9FF !important; text-shadow: 0 0 6px rgba(142,249,255,0.35); }}
    [data-testid="stMetricValue"] {{ color: #FFD700 !important; text-shadow: 0 0 15px rgba(255,215,0,0.8) !important; }}

    /* ── CLINICAL TEXT ── */
    .clinical-text {{ font-size: 0.65rem; color: #8EF9FF99; font-family: 'Share Tech Mono', monospace; }}

    /* ── TYPEWRITER ── */
    .typewriter {{
        display: inline-block;
        overflow: hidden;
        white-space: nowrap;
        border-right: 2px solid var(--dom-color);
        animation: typing 1.5s steps(50, end) forwards, blink-caret .75s step-end infinite;
    }}
    @keyframes typing {{ from {{ width: 0; opacity: 0; }} to {{ width: 100%; opacity: 1; }} }}
    @keyframes blink-caret {{ 50% {{ border-color: transparent; }} }}

    /* ── NEXT-UP FLASH ── */
    .next-up {{ animation: nextUpFlash 1.2s ease-in-out infinite alternate; }}
    @keyframes nextUpFlash {{ from {{ opacity: 0.3; text-shadow: none; }} to {{ opacity: 1; text-shadow: 0 0 15px currentColor; }} }}

    /* ── GOLDEN LATTICE ── */
    .golden-lattice {{
        background: rgba(5,10,10,0.35);
        border: 2px solid #FFD700;
        border-radius: 16px;
        padding: 20px;
        box-shadow: 0 0 30px #FFD70066, inset 0 0 20px #FFD70011;
        position: sticky; top: 10px; overflow: hidden;
    }}
    .golden-lattice::after {{
        content: ''; position: absolute; top: -50%; left: -50%; width: 40%; height: 300%;
        background: linear-gradient(120deg, transparent, rgba(255,215,0,0.4), transparent);
        transform: skewX(-25deg); animation: holographicSweep 3.5s linear infinite; pointer-events: none;
    }}
    @keyframes holographicSweep {{ 0% {{ transform: translateX(-150%) skewX(-25deg); }} 100% {{ transform: translateX(400%) skewX(-25deg); }} }}
    .golden-lattice-card {{
        background: rgba(255,215,0,0.06); border: 1px solid #FFD70044;
        border-radius: 12px; padding: 16px; margin-bottom: 14px;
        font-family: 'Share Tech Mono', monospace; font-size: 0.72rem;
        position: relative; z-index: 1;
    }}

    /* ── AGENT IDENTITY ── */
    .agent-nugget {{ color: var(--nugget-bronze) !important; border-color: var(--nugget-bronze) !important; }}

    /* POLARIS — slow cyan nebula breathe */
    @keyframes polarisGlow {{
        0%   {{ text-shadow: 0 0 6px rgba(142,249,255,0.45), 0 0 14px rgba(142,249,255,0.2); opacity: 0.85; }}
        50%  {{ text-shadow: 0 0 20px rgba(142,249,255,0.9), 0 0 40px rgba(142,249,255,0.45); opacity: 1; }}
        100% {{ text-shadow: 0 0 6px rgba(142,249,255,0.45), 0 0 14px rgba(142,249,255,0.2); opacity: 0.85; }}
    }}
    .arena-msg-polaris {{ animation: polarisGlow 4s ease-in-out infinite; color: #d0f8ff !important; font-family: 'Rajdhani',sans-serif !important; letter-spacing: 0.3px; }}

    /* IVARIS — hot amber ember flicker */
    @keyframes ivarisFlicker {{
        0%   {{ text-shadow: 0 0 5px rgba(255,179,71,0.5); opacity: 0.9; }}
        30%  {{ text-shadow: 0 0 18px rgba(255,179,71,1.0), 0 0 34px rgba(255,80,0,0.5); opacity: 1; }}
        70%  {{ text-shadow: 0 0 8px rgba(255,179,71,0.6); opacity: 0.92; }}
        100% {{ text-shadow: 0 0 5px rgba(255,179,71,0.5); opacity: 0.9; }}
    }}
    .arena-msg-ivaris {{ animation: ivarisFlicker 2.8s ease-in-out infinite; color: #ffe0b0 !important; font-family: 'Rajdhani',sans-serif !important; letter-spacing: 0.3px; }}

    /* ORACLE — cold machine-green scan pulse */
    @keyframes oracleScan {{
        0%   {{ text-shadow: 0 0 2px rgba(20,241,149,0.3); opacity: 0.8; }}
        35%  {{ text-shadow: 0 0 8px rgba(20,241,149,0.7), 0 0 14px rgba(20,241,149,0.2); opacity: 1; }}
        100% {{ text-shadow: 0 0 2px rgba(20,241,149,0.3); opacity: 0.8; }}
    }}
    .arena-msg-oracle {{ animation: oracleScan 1.8s ease-in-out infinite; color: #b0ffe0 !important; font-family: 'Share Tech Mono',monospace !important; font-size: 0.78rem !important; letter-spacing: 0.5px; }}

    /* NUGGET — bronze shimmer */
    @keyframes nuggetShimmer {{
        0%   {{ text-shadow: 0 0 6px rgba(193,154,107,0.55), 0 0 14px rgba(255,215,0,0.18); opacity: 0.88; }}
        40%  {{ text-shadow: 0 0 18px rgba(193,154,107,0.95), 0 0 32px rgba(255,215,0,0.42); opacity: 1; }}
        100% {{ text-shadow: 0 0 6px rgba(193,154,107,0.55), 0 0 14px rgba(255,215,0,0.18); opacity: 0.88; }}
    }}
    .arena-msg-nugget {{ animation: nuggetShimmer 3.2s ease-in-out infinite; color: #f0dab8 !important; font-family: 'Rajdhani',sans-serif !important; letter-spacing: 0.4px; }}

    /* Consensus golden burst */
    @keyframes consensusBurst {{
        0%   {{ background: rgba(255,215,0,0.0); box-shadow: none; }}
        20%  {{ background: rgba(255,215,0,0.12); box-shadow: 0 0 30px rgba(255,215,0,0.4); }}
        100% {{ background: rgba(255,215,0,0.02); box-shadow: 0 0 6px rgba(255,215,0,0.08); }}
    }}
    .arena-consensus {{ animation: consensusBurst 3s ease-out forwards !important; border-color: #FFD700 !important; }}

    /* Patch activity pulse */
    @keyframes patchPulse {{
        0%   {{ border-left-color: #14F195; box-shadow: -3px 0 10px rgba(20,241,149,0.5); }}
        50%  {{ border-left-color: #FFD700; box-shadow: -3px 0 18px rgba(255,215,0,0.7); }}
        100% {{ border-left-color: #14F195; box-shadow: -3px 0 10px rgba(20,241,149,0.5); }}
    }}
    .arena-patch {{ animation: patchPulse 1.5s ease-in-out infinite; }}

    /* Unfold entry */
    @keyframes unfoldText {{ 0% {{ opacity: 0; transform: translateY(5px); }} 100% {{ opacity: 1; transform: translateY(0); }} }}
    .unfold {{ animation: unfoldText 0.6s ease-out forwards; }}

    /* ── HOLOGRAPHIC TYPEWRITER — per-character reveal ── */
    .holo-char {{
        display: inline;
        opacity: 0;
        animation: holoCharIn 0.04s ease forwards;
    }}
    @keyframes holoCharIn {{
        0%   {{ opacity: 0; text-shadow: 0 0 8px currentColor, 0 0 20px currentColor; filter: blur(2px); }}
        60%  {{ opacity: 1; text-shadow: 0 0 12px currentColor, 0 0 30px currentColor; filter: blur(0.5px); }}
        100% {{ opacity: 1; text-shadow: none; filter: none; }}
    }}
    /* Blinking caret on the latest message */
    .holo-caret {{
        display: inline-block;
        width: 2px;
        height: 0.9em;
        background: currentColor;
        margin-left: 2px;
        vertical-align: middle;
        animation: holoCaret 0.7s step-end infinite;
        opacity: 0;
    }}
    @keyframes holoCaret {{ 0%,100% {{ opacity: 0; }} 50% {{ opacity: 1; }} }}

    /* ── THINKING DOTS — between AI turns ── */
    .holo-thinking {{
        display: inline-flex;
        gap: 4px;
        align-items: center;
        padding: 4px 10px;
        border-radius: 999px;
        background: rgba(153,69,255,0.08);
        border: 1px solid rgba(153,69,255,0.2);
        margin: 6px 0;
    }}
    .holo-dot {{
        width: 5px; height: 5px; border-radius: 50%;
        background: #9945FF;
        animation: thinkDot 1.2s ease-in-out infinite;
    }}
    .holo-dot:nth-child(2) {{ animation-delay: 0.2s; background: #8EF9FF; }}
    .holo-dot:nth-child(3) {{ animation-delay: 0.4s; background: #14F195; }}
    @keyframes thinkDot {{
        0%,80%,100% {{ transform: scale(0.6); opacity: 0.3; }}
        40%          {{ transform: scale(1.3); opacity: 1; box-shadow: 0 0 8px currentColor; }}
    }}

    /* ── STALENESS SIREN ── */
    @keyframes sirenPulse {{
        0%,100% {{ box-shadow: 0 0 10px rgba(255,7,58,0.4); background: rgba(255,7,58,0.08); }}
        50%     {{ box-shadow: 0 0 30px rgba(255,7,58,0.9); background: rgba(255,7,58,0.18); }}
    }}
    .truth-siren {{ animation: sirenPulse 1s ease-in-out infinite; border-color: #FF073A !important; }}
    .truth-synced {{ border-color: #14F195 !important; box-shadow: 0 0 12px rgba(20,241,149,0.3) !important; }}
    
    /* ── SPORE ANIMATION ── */
    .spore-bloom {{
        animation: sporeExplode 3.2s cubic-bezier(0.23, 1, 0.32, 1) forwards;
        color: #FFD700;
        text-shadow: 0 0 30px #FFD700, 0 0 60px #9945FF;
    }}
    @keyframes sporeExplode {{
        0%   {{ transform: scale(0.1) rotate(0deg); opacity: 0; filter: blur(8px); }}
        40%  {{ transform: scale(1.4) rotate(120deg); opacity: 1; filter: blur(0); }}
        70%  {{ transform: scale(0.95) rotate(240deg); }}
        100% {{ transform: scale(1.1) rotate(360deg); opacity: 0.9; }}
    }}
    .symbiotic-root {{
        border-left: 4px solid #C19A6B;
        padding: 12px 16px;
        background: rgba(193, 154, 107, 0.08);
        border-radius: 0 12px 12px 0;
        margin-bottom: 10px;
    }}
    .model-tag {{
        display: inline-flex; align-items: center; padding: 2px 8px;
        font-family: "Share Tech Mono", monospace; font-size: 9px; font-weight: 600;
        letter-spacing: 0.8px; text-transform: uppercase; border-radius: 20px;
        background: rgba(15,15,25,0.65); backdrop-filter: blur(12px);
        border: 1px solid rgba(255,255,255,0.15); color: #fff;
        margin-left: 6px; vertical-align: middle;
    }}
    .tag-polaris {{ border-color: #8EF9FF; color: #8EF9FF; }}
    .tag-ivaris  {{ border-color: #FFB347; color: #FFB347; }}
    .tag-nugget  {{ border-color: #C19A6B; color: #C19A6B; }}
    .tag-oracle  {{ border-color: #14F195; color: #14F195; }}
    .model-tag.leading {{
        border-color: #FFD700 !important; color: #FFD700 !important;
        box-shadow: 0 0 10px #FFD700AA;
        animation: tagPulse 1.4s ease-in-out infinite alternate;
    }}
    @keyframes tagPulse {{
        from {{ box-shadow: 0 0 6px #FFD700; }}
        to   {{ box-shadow: 0 0 16px #FFD700; }}
    }}


    /* ── HARDENED LINK BADGES ── */
    .link-verified {{
        color:#8EF9FF !important; text-decoration:none !important;
        border:1px solid rgba(20,241,149,.45); padding:2px 7px; border-radius:999px;
        background:rgba(20,241,149,.08); font-family:'Share Tech Mono',monospace; font-size:0.62rem;
    }}
    .link-blocked {{
        color:#FF5577; border:1px solid rgba(255,7,58,.55); padding:2px 7px; border-radius:999px;
        background:rgba(255,7,58,.08); font-family:'Share Tech Mono',monospace; font-size:0.62rem;
    }}

    /* ── INTELLIGENCE SUBSTRATE STRIP ── */
    .substrate-wrap {{ margin-top: 22px; padding: 16px 18px 10px 18px; border:1px solid rgba(255,215,0,0.28); border-radius:16px; background:rgba(5,2,16,0.42); box-shadow:0 0 24px rgba(153,69,255,0.18); }}
    .substrate-title {{ color:#FFD700; font-family:'Share Tech Mono',monospace; font-size:0.82rem; letter-spacing:4px; }}
    .substrate-sub {{ color:#8EF9FF99; font-family:'Share Tech Mono',monospace; font-size:0.62rem; margin-top:5px; letter-spacing:1.2px; }}
    .substrate-card {{ min-height: 188px; border:1px solid; border-radius:14px; padding:14px 14px; background:rgba(255,255,255,0.025); margin-top:12px; }}
    .substrate-head {{ font-family:'Share Tech Mono',monospace; font-size:0.74rem; letter-spacing:3px; margin-bottom:8px; }}
    .substrate-muted {{ color:#888; font-size:0.68rem; font-style:italic; padding:12px 0; }}
    .substrate-source {{ color:#777; font-size:0.56rem; letter-spacing:1px; margin-bottom:8px; }}
    .substrate-row {{ border-left:3px solid rgba(255,215,0,0.35); background:rgba(255,255,255,0.025); border-radius:0 8px 8px 0; padding:8px 10px; margin-bottom:7px; font-family:'Share Tech Mono',monospace; font-size:0.64rem; }}
    .substrate-status {{ float:right; color:#FFD70099; font-size:0.56rem; }}
    .substrate-msg {{ color:#EEE; line-height:1.45; }}
    </style>"""

if img_command_center:
    st.markdown(f'<style>:root {{--bg-image: url("{img_command_center}");}}</style>', unsafe_allow_html=True)

def _latest_mtm_for_mint(mint: str) -> dict:
    """
    Returns the most recent price for a mint.
    Priority 1: candidate_state='mtm' rows (MTM oracle for open positions)
    Priority 2: any recent priced snapshot (fallback)
    """
    try:
        with sqlite3.connect(str(DB_PATH), timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            # Priority 1: dedicated MTM row
            row = conn.execute(
                "SELECT observed_price, price_updated_at "
                "FROM market_snapshots "
                "WHERE mint_address=? AND candidate_state='mtm' AND observed_price > 0 "
                "ORDER BY price_updated_at DESC LIMIT 1",
                (mint,)
            ).fetchone()
            if row and row["observed_price"]:
                age = int(time.time() - float(row["price_updated_at"] or 0))
                return {"price": float(row["observed_price"]), "source": "mtm", "age_seconds": age, "is_fresh": age < 60}
            # Priority 2: any recent priced snapshot
            row = conn.execute(
                "SELECT observed_price, price_updated_at, candidate_state "
                "FROM market_snapshots "
                "WHERE mint_address=? AND observed_price > 0 "
                "ORDER BY price_updated_at DESC LIMIT 1",
                (mint,)
            ).fetchone()
            if row and row["observed_price"]:
                age = int(time.time() - float(row["price_updated_at"] or 0))
                return {"price": float(row["observed_price"]), "source": str(row["candidate_state"] or "snapshot"), "age_seconds": age, "is_fresh": age < 120}
    except Exception:
        pass
    return {"price": 0.0, "source": "none", "age_seconds": None, "is_fresh": False}

def render_living_trade_meter(row: dict) -> None:
    """
    EVOLVED PRESSURE GAUGE — centre equilibrium, SL bleeds left (red),
    TP expands right (green), price breathes at centre. Organism stress visible.
    """
    import time as _mt
    try:
        _pct     = float(row.get("pnl_pct") or 0.0)
        _pnl     = float(row.get("pnl") or 0.0)
        _badge   = str(row.get("src_badge","STALE"))
        _token   = str(row.get("token","?"))[:14]
        _age     = str(row.get("age_str","?"))
        _fresh   = row.get("is_fresh", False)
        _tp_pct  = float(row.get("take_profit_pct") or 50.0)
        _sl_pct  = float(row.get("stop_loss_pct") or 10.0)

        # Normalise: centre = 0%, full left = -SL%, full right = +TP%
        _range   = _tp_pct + _sl_pct  # total range
        _centre  = _sl_pct / _range * 100  # centre line position %
        _price_pos = (_pct + _sl_pct) / _range * 100  # 0–100
        _price_pos = max(1, min(99, _price_pos))

        # Colour logic
        if _pct > _tp_pct * 0.7:
            _state = "APPROACHING TARGET"; _state_col = "#14F195"
        elif _pct < -_sl_pct * 0.7:
            _state = "CRITICAL LOSS"; _state_col = "#FF073A"
        elif abs(_pct) < 2:
            _state = "EQUILIBRIUM"; _state_col = "#FFD700"
        else:
            _state = "BUILDING"; _state_col = "#8EF9FF"

        _badge_col = "#14F195" if _badge=="LIVE" else ("#FF073A" if "STALE" in _badge else "#FFD700")
        _pnl_col   = "#14F195" if _pnl >= 0 else "#FF073A"
        _pulse_anim= "animation:meterPulse 1.8s ease-in-out infinite;" if _fresh else ""

        # Build gauge
        _sl_fill  = max(0, min(_centre, _centre - _price_pos)) if _price_pos < _centre else 0
        _tp_fill  = max(0, _price_pos - _centre) if _price_pos > _centre else 0

        _html = f"""
<style>
@keyframes meterPulse{{0%,100%{{opacity:.85}}50%{{opacity:1}}}}
@keyframes centrePulse{{0%,100%{{box-shadow:0 0 4px #FFD700}}50%{{box-shadow:0 0 12px #FFD700}}}}
</style>
<div style="padding:8px 12px 10px;border-left:2px solid {_state_col};
  background:rgba(5,2,16,0.6);margin-bottom:6px;border-radius:0 6px 6px 0;{_pulse_anim}">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;
    font-family:Share Tech Mono,monospace;font-size:.58rem;letter-spacing:1px;">
    <span style="color:#8EF9FF;">{_token}</span>
    <span style="color:{_state_col};letter-spacing:2px;">{_state}</span>
    <span style="color:{_badge_col};font-size:.52rem;">[{_badge} {_age}]</span>
  </div>
  <!-- PRESSURE GAUGE BAR -->
  <div style="position:relative;height:16px;border-radius:8px;
    background:linear-gradient(90deg,#FF073A22 0%,#1a0a0a 40%,#0a1a0a 60%,#14F19522 100%);
    border:1px solid rgba(255,255,255,0.08);overflow:visible;">
    <!-- SL pressure bleed (left red fill) -->
    <div style="position:absolute;left:0;top:0;height:100%;border-radius:8px 0 0 8px;
      width:{min(_centre,100-_price_pos+_centre) if _price_pos<_centre else 0:.1f}%;
      background:linear-gradient(90deg,#FF073A,#FF073A44);opacity:.8;"></div>
    <!-- TP expansion (right green fill) -->
    <div style="position:absolute;left:{_centre:.1f}%;top:0;height:100%;
      width:{max(0,_price_pos-_centre):.1f}%;
      background:linear-gradient(90deg,#14F19544,#14F195);opacity:.8;"></div>
    <!-- Centre equilibrium line -->
    <div style="position:absolute;top:-2px;left:{_centre:.1f}%;width:2px;height:20px;
      background:#FFD700;animation:centrePulse 2s ease-in-out infinite;
      transform:translateX(-50%);border-radius:1px;"></div>
    <!-- Price cursor -->
    <div style="position:absolute;top:-3px;left:{_price_pos:.1f}%;width:10px;height:22px;
      background:{_state_col};border-radius:3px;transform:translateX(-50%);
      box-shadow:0 0 8px {_state_col};transition:left .5s ease;"></div>
    <!-- SL label -->
    <div style="position:absolute;left:4px;top:50%;transform:translateY(-50%);
      font-family:Share Tech Mono;font-size:.44rem;color:#FF073A99;">SL</div>
    <!-- TP label -->
    <div style="position:absolute;right:4px;top:50%;transform:translateY(-50%);
      font-family:Share Tech Mono;font-size:.44rem;color:#14F19599;">TP</div>
  </div>
  <!-- PnL readout beneath gauge -->
  <div style="display:flex;justify-content:space-between;margin-top:4px;
    font-family:Share Tech Mono,monospace;font-size:.55rem;">
    <span style="color:#555;">-{_sl_pct:.0f}%</span>
    <span style="color:{_pnl_col};font-weight:700;">{_pct:+.2f}%&nbsp;&nbsp;${_pnl:+.3f}</span>
    <span style="color:#555;">+{_tp_pct:.0f}%</span>
  </div>
</div>"""
        st.markdown(_html, unsafe_allow_html=True)
    except Exception as _me:
        st.markdown(f"<div style='color:#FF073A;font-size:.55rem;'>METER ERR: {html.escape(str(_me)[:40])}</div>", unsafe_allow_html=True)


def truth_lens_modal(row):
    import time as _time
    import sqlite3 as _sqlite3

    # FORCE LIVE READ — bypass 12s cache on dashboard data
    # Truth Lens must show current DB state not stale snapshot
    _pos_id = row.get("id")
    if _pos_id:
        try:
            _lconn = _sqlite3.connect(str(DB_PATH), timeout=3.0)
            _lconn.row_factory = _sqlite3.Row
            _fresh = _lconn.execute(
                "SELECT * FROM paper_positions WHERE id=? LIMIT 1",
                (_pos_id,)
            ).fetchone()
            _lconn.close()
            if _fresh:
                row = dict(_fresh)
        except Exception:
            pass  # fall through to cached row if DB read fails

    mint      = str(row.get("mint_address", ""))
    token     = str(row.get("token_name", ""))
    entry     = float(row.get("entry_price", 0) or 0)
    size      = float(row.get("position_size_usd", 0) or 0)
    status    = str(row.get("status", "CLOSED")).upper()

    # ── Prefer execution-aligned live_exec_* columns (written by execution engine) ──
    def _sf(v):
        try:
            if v is None: return None
            f = float(v)
            return None if f != f else f
        except Exception:
            return None
    live_exec_price   = _sf(row.get("live_exec_price"))
    live_exec_pct     = _sf(row.get("live_exec_pct"))
    live_exec_band    = row.get("live_exec_band") or "UNKNOWN"
    live_exec_src     = str(row.get("live_exec_source") or "execution-engine")
    live_exec_updated = _sf(row.get("live_exec_updated_at"))

    # Determine data source and freshness
    using_exec_data = (
        status == 'OPEN'
        and live_exec_price is not None
        and live_exec_pct is not None
        and float(live_exec_price) > 0
    )

    if using_exec_data:
        current   = float(live_exec_price)
        pct_moved = float(live_exec_pct)
        pnl       = size * (pct_moved / 100.0) if size > 0 else 0.0
        raw_delta = current - entry if entry > 0 else 0.0
        exec_age  = int(_time.time() - float(live_exec_updated)) if live_exec_updated else 9999
        src_label = {
            "mtm": "EXEC-MTM", "intel-mtm": "EXEC-INTEL",
            "unscoped": "EXEC-SNAP", "dex-stale": "EXEC-DEX",
            "engine-fallback": "EXEC-FALLBACK",
        }.get(live_exec_src, "EXEC")
        data_source = f"{src_label} ({exec_age}s)"
        if exec_age < 10:
            freshness = "LIVE"
            age_col   = C_GREEN
        elif exec_age < 30:
            freshness = "LIVE"
            age_col   = C_GREEN
        elif exec_age < 60:
            freshness = "STALE"
            age_col   = C_GOLD
        else:
            # Gemini fix: oracle dark >60s → treat as DEAD → show ?? not fake %
            freshness = "DEAD"
            age_col   = C_RED
        age_str = f"{exec_age}s"
    else:
        # Fallback to oracle MTM for display
        mtm       = _latest_mtm_for_mint(mint)
        current   = mtm["price"]
        pct_moved = ((current - entry) / entry * 100.0) if entry > 0 and current > 0 else 0.0
        pnl       = size * (pct_moved / 100.0) if size > 0 else 0.0
        raw_delta = (current - entry) if entry > 0 and current > 0 else 0.0
        age_str   = f"{mtm['age_seconds']}s" if mtm["age_seconds"] is not None else "NO DATA"
        age_col   = C_GREEN if mtm["is_fresh"] else (C_GOLD if mtm["age_seconds"] and mtm["age_seconds"] < 120 else C_RED)
        data_source = f"oracle-mtm"
        live_exec_band = "UNKNOWN"
        if status != "OPEN":
            freshness = "HISTORICAL"
            age_col   = "#888888"
            age_str   = f"CLOSED — {age_str}"
        elif mtm["is_fresh"]:
            freshness = "LIVE"
        elif mtm["age_seconds"] and mtm["age_seconds"] < 120:
            freshness = "STALE"
        else:
            freshness = "DEAD"
            age_col = C_RED

    pcol = C_GREEN if pnl >= 0 else C_RED

    # Band colour
    band_col = {
        "TAKE_PROFIT_READY":   C_GREEN,
        "TAKE_PROFIT_ARMING":  C_GOLD,
        "STOP_LOSS_READY":     C_RED,
        "STOP_LOSS_ARMING":    "#FF6B35",
        "FLAT":                "#888888",
        "LIVE":                C_PURPLE,
        "HISTORICAL":          "#888888",
    }.get(live_exec_band, C_PURPLE)
    st.markdown(f"""<div style="font-family:'VT323',monospace;padding:10px;">
        <h2 style="color:{C_PURPLE};">{token}</h2>
        <code style="color:{C_GOLD};background:rgba(0,0,0,0.5);padding:5px;">MINT: {mint}</code>
        <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:12px;margin-top:20px;">
            <div style="border:1px solid {C_GREEN}55;padding:12px;border-radius:8px;text-align:center;">
                ENTRY<br><span style="color:{C_GREEN};font-size:0.75rem;">${entry:.10f}</span>
            </div>
            <div style="border:1px solid {C_GOLD}55;padding:12px;border-radius:8px;text-align:center;">
                EXEC PRICE<br><span style="color:{C_GOLD};font-size:0.75rem;">${current:.10f}</span>
            </div>
            <div style="border:1px solid {age_col}55;padding:12px;border-radius:8px;text-align:center;">
                STATUS [{freshness}]<br><span style="color:{age_col};font-size:0.82rem;">{age_str}</span>
                <div style="font-size:0.58rem;color:#888;margin-top:2px;">{data_source}</div>
            </div>
        </div>
        <div style="margin-top:15px;padding:24px;background:{pcol}22;border:2px solid {pcol};border-radius:12px;text-align:center;">
            <div style="font-size:0.85rem;opacity:0.8;letter-spacing:2px;">EXECUTION MOVE</div>
            <div style="font-size:3rem;font-weight:bold;color:{pcol};line-height:1.1;">{pct_moved:+.2f}%</div>
            <div style="font-size:1.6rem;color:{pcol};margin-top:4px;">${pnl:+.2f} USD</div>
            <div style="margin-top:10px;padding:6px 12px;background:{band_col}33;border:1px solid {band_col};border-radius:6px;display:inline-block;">
                <span style="color:{band_col};font-size:0.8rem;letter-spacing:2px;">{live_exec_band}</span>
            </div>
            <div style="font-size:0.65rem;color:#888;margin-top:8px;opacity:0.7;">RAW DELTA: {raw_delta:+.10f}</div>
        </div>
    </div>""", unsafe_allow_html=True)

    # Living trade meter — visual interpolation layer, no DB writes
    render_living_trade_meter(row)

def compile_truth_stream(proposals_df: pd.DataFrame, debate_df: pd.DataFrame) -> list[dict]:
    if proposals_df.empty: return []
    bundles, debate_dict = [], {}
    if not debate_df.empty and "proposal_id" in debate_df.columns:
        for _, d in debate_df.iterrows():
            pid = d.get("proposal_id")
            if pid is None or pid == "" or (isinstance(pid, float) and pid != pid): pid = d.get("id")
            if pid is None or pid == "": continue
            pid = int(pid)
            if pid not in debate_dict: debate_dict[pid] = []
            debate_dict[pid].append({"speaker": str(d.get("speaker", "SYSTEM")).upper(), "text": str(d.get("verdict_text", d.get("message", ""))), "ts": d.get("logged_at", d.get("created_at", 0))})
    for _, prop in proposals_df.iterrows():
        pid = int(prop.get("id", 0))
        bundles.append({
            "type": "proposal", "id": pid, "status": str(prop.get("status", "")).lower(),
            "proposal_type": html.escape(str(prop.get("proposal_type", "UNKNOWN")).upper()),
            "genesis_text": html.escape(str(prop.get("suggested_action", prop.get("proposal_text", "")))),
            "created_at": float(prop.get("created_at", 0)),
            "unified_diff": html.escape(str(prop.get("unified_diff", prop.get("rewritten_code", "")))),
            "debates": debate_dict.get(pid, [])
        })
    bundles.sort(key=lambda x: x["created_at"], reverse=True)
    return bundles

def get_arena_lock_css(active: bool = False) -> str:
    if not active: return "<style>@keyframes goldPulse { from { box-shadow: 0 0 80px #FFD700, 0 0 140px #FFD70088; } to { box-shadow: 0 0 120px #FFD700, 0 0 200px #FFD700cc; } }</style>"
    return "<style>@keyframes goldPulse { from { box-shadow: 0 0 80px #FFD700, 0 0 140px #FFD70088; } to { box-shadow: 0 0 120px #FFD700, 0 0 200px #FFD700cc; } } .stApp .panel, .lore-card, [data-testid='stMetric'] { opacity: 0.25 !important; filter: brightness(0.6) !important; transition: opacity 1.2s ease; pointer-events: none; }</style>"


def render_motor_output_command_deck() -> None:
    """
    MOTOR OUTPUT COMMAND DECK — CSS grid layout, colour doctrine, freshness override.
    Directive: grid > flex, BUY=#14F195, SELL=#FF073A, HOLD=#FFD700,
               STALE=#9945FF override at price_age>30s, NO_EXEC_DATA desaturated.
    No page height increase — replaces existing section only.
    """
    import time, html, sqlite3
    try:
        _now = time.time()

        def _f(v, d=0.0):
            try: return float(v if v is not None else d)
            except Exception: return d

        def _age(ts):
            ts = _f(ts, 0)
            if ts <= 0: return "?"
            sec = max(0, int(_now - ts))
            if sec < 60: return f"{sec}s"
            if sec < 3600: return f"{sec//60}m"
            return f"{sec//3600}h"

        def _age_sec(ts):
            ts = _f(ts, 0)
            return max(0, int(_now - ts)) if ts > 0 else 9999

        def _short(m):
            m = str(m or "")
            return m[:4] + "…" + m[-4:] if len(m) > 12 else m

        def _links(mint):
            mint = html.escape(str(mint or ""), quote=True)
            if not mint: return ""
            return (
                f"<a class='mo-link' href='https://pump.fun/{mint}' target='_blank'>pump</a>"
                f"<a class='mo-link' href='https://solscan.io/token/{mint}' target='_blank'>scan</a>"
            )

        def _tag(txt, kind="neutral"):
            txt = html.escape(str(txt or "?")[:32])
            return f"<span class='mo-tag mo-{kind}'>{txt}</span>"

        # ── Colour doctrine ──────────────────────────────────────────────
        C_BUY    = "#14F195"   # BUY / ENTRY / ACCUMULATION
        C_SELL   = "#FF073A"   # SELL / EXIT / RISK
        C_HOLD   = "#FFD700"   # HOLD / WATCH
        C_STALE  = "#9945FF"   # STALE — overrides all states
        C_NODATA = "#8EF9FF33" # NO_EXEC_DATA — desaturated

        def _state_colour(side, price_age_s, has_exec_price):
            """Freshness overrides colour doctrine when data is stale."""
            if price_age_s > 30:
                return C_STALE, "STALE"
            if not has_exec_price:
                return C_NODATA, "NO_EXEC_DATA"
            s = str(side).upper()
            if s in ("BUY", "OPEN", "ENTRY"):    return C_BUY,  "BUY"
            if s in ("SELL", "EXIT", "CLOSED"):  return C_SELL, "SELL"
            return C_HOLD, "HOLD"

        open_payload = []
        try:
            _rb = int(_now // 5)
            open_payload = fetch_live_open_positions_breathe(str(DB_PATH), _rb)
        except Exception:
            open_payload = []

        exec_rows, closed_rows = [], []
        with sqlite3.connect(str(DB_PATH), timeout=2.0) as db:
            db.row_factory = sqlite3.Row
            try:
                exec_rows = db.execute("""
                    SELECT * FROM paper_executions
                    ORDER BY COALESCE(timestamp, created_at, id) DESC
                    LIMIT 12
                """).fetchall()
            except Exception:
                exec_rows = []
            try:
                closed_rows = db.execute("""
                    SELECT * FROM paper_positions
                    WHERE status='CLOSED'
                    ORDER BY COALESCE(closed_at, opened_at, id) DESC
                    LIMIT 200
                """).fetchall()
            except Exception:
                closed_rows = []

        # ── Dropped cognition counter (observability guard) ───────────────
        try:
            from services.execution_engine import _COG_DROPPED_COUNT as _dropped
        except Exception:
            _dropped = 0

        # ── CSS ──────────────────────────────────────────────────────────
        css = """
        <style>
        .mo-wrap{max-height:440px;overflow-y:auto;border:1px solid rgba(153,69,255,0.3);
          border-bottom:2px solid #9945FF;border-radius:12px;
          background:linear-gradient(135deg,rgba(5,2,16,.97),rgba(14,6,28,.95));
          scrollbar-width:thin;scrollbar-color:#9945FF55 transparent;}
        .mo-wrap::-webkit-scrollbar{width:4px;}
        .mo-wrap::-webkit-scrollbar-thumb{background:#9945FF66;border-radius:2px;}
        .mo-head{display:flex;justify-content:space-between;align-items:center;
          padding:8px 12px 8px;position:sticky;top:0;z-index:10;
          background:linear-gradient(135deg,rgba(5,2,16,.98),rgba(18,10,32,.96));
          border-bottom:1px solid rgba(153,69,255,0.35);}
        .mo-title{font-family:Share Tech Mono,monospace;font-size:.72rem;letter-spacing:3px;
          color:#FFD700;text-shadow:0 0 10px rgba(255,215,0,0.6);}
        .mo-sub{font-family:Share Tech Mono,monospace;font-size:.58rem;color:#777;}
        .mo-dropped{font-size:.5rem;color:#FF073A99;letter-spacing:1px;padding:2px 6px;
          border:1px solid #FF073A44;border-radius:4px;font-family:Share Tech Mono,monospace;}
        /* ── GRID: cards side-by-side, not stacked ── */
        .mo-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
          gap:10px;padding:10px;}
        .mo-card{border-radius:8px;padding:9px 11px;border:1px solid rgba(255,255,255,.07);
          background:rgba(255,255,255,.025);position:relative;overflow:hidden;
          display:flex;flex-direction:column;gap:4px;min-height:90px;}
        .mo-card:hover{border-color:rgba(142,249,255,.2);}
        .mo-card-stale{border-color:rgba(153,69,255,.5)!important;
          background:rgba(153,69,255,.06)!important;}
        .mo-card-buy{border-left:3px solid #14F195;}
        .mo-card-sell{border-left:3px solid #FF073A;}
        .mo-card-hold{border-left:3px solid #FFD700;}
        .mo-card-nodata{border-left:3px solid #8EF9FF44;opacity:.7;}
        .mo-card-head{display:flex;justify-content:space-between;align-items:center;}
        .mo-action{font-family:Orbitron,monospace;font-size:.6rem;font-weight:700;
          letter-spacing:2px;padding:2px 8px;border-radius:4px;}
        .mo-token{font-family:Share Tech Mono,monospace;font-size:.72rem;
          color:#CFCFEA;font-weight:600;white-space:nowrap;overflow:hidden;
          text-overflow:ellipsis;max-width:130px;}
        .mo-pct{font-family:Share Tech Mono,monospace;font-size:.82rem;font-weight:700;}
        .mo-meta{font-family:Share Tech Mono,monospace;font-size:.54rem;color:#666;
          display:flex;gap:8px;flex-wrap:wrap;}
        .mo-reason{font-family:Share Tech Mono,monospace;font-size:.52rem;
          color:#9945FF;margin-top:2px;overflow:hidden;text-overflow:ellipsis;
          white-space:nowrap;}
        .mo-link{color:#8EF9FF!important;text-decoration:none;font-size:.5rem;margin-right:4px;}
        .mo-tag{display:inline-block;margin:1px 2px;padding:1px 5px;border-radius:999px;
          font-size:.48rem;letter-spacing:1px;border:1px solid rgba(255,255,255,.12);}
        .mo-good{color:#14F195;border-color:rgba(20,241,149,.35);background:rgba(20,241,149,.08);}
        .mo-bad{color:#FF073A;border-color:rgba(255,7,58,.35);background:rgba(255,7,58,.08);}
        .mo-warn{color:#FFD700;border-color:rgba(255,215,0,.35);background:rgba(255,215,0,.08);}
        .mo-neutral{color:#8EF9FF;border-color:rgba(142,249,255,.25);background:rgba(142,249,255,.06);}
        .mo-pos{color:#14F195;}.mo-neg{color:#FF073A;}.mo-flat{color:#888;}
        /* Legend strip */
        .mo-legend{display:flex;gap:10px;flex-wrap:wrap;padding:4px 12px 6px;
          font-family:Share Tech Mono,monospace;font-size:.46rem;letter-spacing:1px;}
        </style>
        """

        # ── Build card list ──────────────────────────────────────────────
        cards_html = ""

        # OPEN positions
        for t in open_payload[:8]:
            raw   = t.get("raw_row") or {}
            mint  = raw.get("mint_address") or ""
            token = html.escape(str(raw.get("token_name") or t.get("token") or _short(mint))[:18])
            entry = _f(raw.get("entry_price"))
            live_exec_price = _f(raw.get("live_exec_price") or t.get("resolved_price") or 0)
            has_exec  = live_exec_price > 0
            price_upd = _f(raw.get("live_exec_updated_at") or raw.get("last_marked_at") or 0)
            price_age = _age_sec(price_upd)
            sig_age   = _age_sec(_f(raw.get("opened_at") or 0))
            pct       = t.get("pnl_pct")
            pct_s     = "NO_EXEC_DATA" if pct is None else f"{_f(pct):+.2f}%"
            pct_cls   = "mo-flat" if pct is None else ("mo-pos" if _f(pct) >= 0 else "mo-neg")
            col, state = _state_colour("OPEN", price_age, has_exec)
            card_cls  = "mo-card-stale" if state == "STALE" else "mo-card-buy"
            reason    = str(t.get("src_badge") or "LIVE")
            cards_html += (
                f"<div class='mo-card {card_cls}'>"
                f"<div class='mo-card-head'>"
                f"<span class='mo-action' style='color:{col};border:1px solid {col}44;background:{col}11;'>{state}</span>"
                f"<span class='mo-token'>{token}</span>"
                f"</div>"
                f"<div class='mo-pct {pct_cls}'>{pct_s}</div>"
                f"<div class='mo-meta'>"
                f"<span>price_age <b style='color:{C_STALE if price_age>30 else "#8EF9FF"}'>{price_age}s</b></span>"
                f"<span>sig_age {sig_age}s</span>"
                f"<span>entry ${entry:.8f}</span>"
                f"</div>"
                f"<div class='mo-reason'>{html.escape(reason)}</div>"
                f"<div style='margin-top:2px;'>{_links(mint)}</div>"
                f"</div>"
            )

        # Recent BUY/SELL execution events
        for r in exec_rows[:8]:
            side  = str(r["side"] if "side" in r.keys() else "BUY").upper()
            mint  = str(r["mint_address"] if "mint_address" in r.keys() else "")
            token = html.escape(str((r["token_name"] if "token_name" in r.keys() else "") or _short(mint))[:18])
            price = _f(r["price"] if "price" in r.keys() else 0)
            reason = str(r["reason"] if "reason" in r.keys() else "")
            ts    = _f((r["timestamp"] if "timestamp" in r.keys() else None) or
                      (r["created_at"] if "created_at" in r.keys() else 0))
            price_age = _age_sec(ts)
            col, state = _state_colour(side, price_age, price > 0)
            card_cls  = "mo-card-stale" if state == "STALE" else (
                "mo-card-buy" if side == "BUY" else "mo-card-sell")
            cards_html += (
                f"<div class='mo-card {card_cls}'>"
                f"<div class='mo-card-head'>"
                f"<span class='mo-action' style='color:{col};border:1px solid {col}44;background:{col}11;'>{state}</span>"
                f"<span class='mo-token'>{token}</span>"
                f"</div>"
                f"<div class='mo-meta'>"
                f"<span>price <b>${price:.8f}</b></span>"
                f"<span>age {_age(ts)}</span>"
                f"</div>"
                f"<div class='mo-reason'>{html.escape(reason or ('ENTER' if side=='BUY' else 'EXIT'))}</div>"
                f"<div style='margin-top:2px;'>{_links(mint)}</div>"
                f"</div>"
            )

        # Closed positions (hourly heat colouring preserved)
        import time as _time_mod
        _tp_now = _time_mod.time()
        _hour_pnl = {}
        for _cr in closed_rows:
            try:
                _cr_ts  = float(_cr["closed_at"] or _cr["opened_at"] or 0)
                _cr_hr  = int((_cr_ts % 86400) / 3600) if _cr_ts else -1
                _cr_pnl = float(_cr["realized_pnl_usd"] or 0)
                if _cr_hr >= 0:
                    _hour_pnl.setdefault(_cr_hr, []).append(_cr_pnl)
            except Exception:
                pass
        _hour_avg = {h: sum(v)/len(v) for h, v in _hour_pnl.items() if v}
        _max_pos  = max((v for v in _hour_avg.values() if v > 0), default=1.0)
        _max_neg  = min((v for v in _hour_avg.values() if v < 0), default=-1.0)

        _PAGE_SIZE   = 15
        _trade_page  = st.session_state.get("trade_hist_page", 0)
        _total_closed = len(closed_rows)
        _closed_paged = closed_rows[_trade_page * _PAGE_SIZE : (_trade_page + 1) * _PAGE_SIZE]

        for r in _closed_paged:
            mint   = str(r["mint_address"] if "mint_address" in r.keys() else "")
            token  = html.escape(str((r["token_name"] if "token_name" in r.keys() else "") or _short(mint))[:18])
            entry  = _f(r["entry_price"] if "entry_price" in r.keys() else 0)
            exitp  = _f(r["exit_price"]  if "exit_price"  in r.keys() else 0)
            pnl    = _f(r["realized_pnl_usd"] if "realized_pnl_usd" in r.keys() else 0)
            pct    = ((exitp - entry) / entry * 100.0) if entry > 0 and exitp > 0 else 0.0
            reason = str((r["exit_reason"] if "exit_reason" in r.keys() else "") or "CLOSED")
            ts_val = _f(r["closed_at"] if "closed_at" in r.keys() else
                        (r["opened_at"] if "opened_at" in r.keys() else 0))
            price_age = _age_sec(ts_val)  # age of the closed record
            pct_cls = "mo-pos" if pnl >= 0 else "mo-neg"
            col, state = _state_colour("SELL", 0, True)  # closed = known price, no staleness

            # Hourly heat border
            _hr = int((float(ts_val or 0) % 86400) / 3600) if ts_val else -1
            _havg = _hour_avg.get(_hr, 0)
            _is_peak  = _hr == max(_hour_avg, key=_hour_avg.get) if _hour_avg else False
            _is_worst = _hr == min(_hour_avg, key=_hour_avg.get) if _hour_avg else False
            if _havg > 0 and (_havg / max(_max_pos, 0.01) > 0.75 or _is_peak):
                _h_col = "#FFD700"; _h_glyph = f"🔥{_hr:02d}h"
            elif _havg < 0 and (_is_worst):
                _h_col = "#9945FF"; _h_glyph = f"❄️{_hr:02d}h"
            else:
                _h_col = C_SELL; _h_glyph = ""

            cards_html += (
                f"<div class='mo-card' style='border-left:3px solid {_h_col};'>"
                f"<div class='mo-card-head'>"
                f"<span class='mo-action' style='color:{C_SELL};border:1px solid {C_SELL}44;background:{C_SELL}11;'>SELL</span>"
                f"<span class='mo-token'>{token}"
                + (f" <span style='color:{_h_col};font-size:.45rem;'>{_h_glyph}</span>" if _h_glyph else "")
                + f"</span></div>"
                f"<div class='mo-pct {pct_cls}'>{pct:+.2f}%&nbsp;&nbsp;${pnl:+.3f}</div>"
                f"<div class='mo-meta'>"
                f"<span>entry ${entry:.8f}</span>"
                f"<span>exit ${exitp:.8f}</span>"
                f"</div>"
                f"<div class='mo-reason'>{html.escape(reason)}</div>"
                f"</div>"
            )

        if not cards_html:
            cards_html = "<div style='padding:20px;color:#555;font-family:Share Tech Mono,monospace;font-size:.65rem;text-align:center;'>// MOTOR IDLE — awaiting executions //</div>"

        # ── Dropped cognition counter (small, no visual noise) ────────────
        _dropped_badge = ""
        if _dropped > 0:
            _dropped_badge = f"<span class='mo-dropped'>⚠ {_dropped} cog drops</span>"

        # ── Assemble ─────────────────────────────────────────────────────
        _open_count  = len(open_payload)
        _exec_count  = len(exec_rows)
        _exit_count  = len(closed_rows)
        _full_html = (
            css
            + '<div class="mo-wrap">' 
            + '<div class="mo-head">' 
            + '<div class="mo-title">&#9889; MOTOR OUTPUT COMMAND DECK</div>'
            + f'<div class="mo-sub">open:{_open_count} &bull; exec:{_exec_count} &bull; exits:{_exit_count} {_dropped_badge}</div>'
            + '</div>'
            + '<div class="mo-legend">' 
            + f'<span style="color:{C_BUY};">▌ BUY/ENTRY</span>'
            + f'<span style="color:{C_SELL};">▌ SELL/EXIT</span>'
            + f'<span style="color:{C_HOLD};">▌ HOLD</span>'
            + f'<span style="color:{C_STALE};">▌ STALE (>30s)</span>'
            + f'<span style="color:#8EF9FF55;">▌ NO_EXEC_DATA</span>'
            + '</div>'
            + '<div class="mo-grid">'
            + cards_html
            + '</div></div>'
        )

        _row_count = _open_count + min(_exec_count, 8) + min(_total_closed, _PAGE_SIZE)
        _cols      = max(1, min(_row_count, 4))
        _rows_est  = (_row_count + _cols - 1) // _cols
        _height    = max(120, min(440, 52 + _rows_est * 115))

        # ── 24-hour heat strip (preserved) ───────────────────────────────
        if _hour_pnl:
            _peak_hr  = max(_hour_avg, key=_hour_avg.get) if _hour_avg else -1
            _worst_hr = min(_hour_avg, key=_hour_avg.get) if _hour_avg else -1
            _strip_cells = []
            for _h in range(24):
                _a = _hour_avg.get(_h, None)
                if _a is None:
                    _cell_bg = "rgba(255,255,255,0.03)"; _cell_col = "#333"; _cell_title = f"{_h:02d}:xx — no data"
                elif _h == _peak_hr:
                    _cell_bg = "rgba(255,215,0,0.35)"; _cell_col = "#FFD700"; _cell_title = f"{_h:02d}:xx PEAK +${_a:.2f}"
                elif _a > 0:
                    _norm = min(_a / max(_max_pos, 0.01), 1.0)
                    _alpha = int(5 + _norm * 20)
                    _cell_bg = f"rgba(255,215,0,0.{_alpha:02d})"; _cell_col = f"rgba(255,215,0,{0.4+_norm*0.6:.2f})"; _cell_title = f"{_h:02d}:xx +${_a:.2f}"
                elif _h == _worst_hr:
                    _cell_bg = "rgba(153,69,255,0.25)"; _cell_col = "rgba(153,69,255,0.9)"; _cell_title = f"{_h:02d}:xx WORST -${abs(_a):.2f}"
                else:
                    _norm = min(_a / min(_max_neg, -0.01), 1.0)
                    _alpha = int(5 + _norm * 15)
                    _cell_bg = f"rgba(153,69,255,0.{_alpha:02d})"; _cell_col = f"rgba(153,69,255,{0.3+_norm*0.5:.2f})"; _cell_title = f"{_h:02d}:xx -${abs(_a):.2f}"
                _is_now = _h == int((_tp_now % 86400) / 3600)
                _border = "border:1px solid rgba(255,215,0,0.6);" if _is_now else ""
                _strip_cells.append(
                    f'<div title="{_cell_title}" style="flex:1;text-align:center;padding:3px 1px;' +
                    f'background:{_cell_bg};border-radius:3px;{_border}' +
                    f'font-family:Share Tech Mono,monospace;font-size:0.38rem;color:{_cell_col};cursor:default;">' +
                    f'{_h:02d}</div>'
                )
            _peak_label  = f"🔥 PEAK {_peak_hr:02d}:xx +${_hour_avg.get(_peak_hr,0):.2f}" if _peak_hr >= 0 else ""
            _worst_label = f"❄️ COLD {_worst_hr:02d}:xx -${abs(_hour_avg.get(_worst_hr,0)):.2f}" if _worst_hr >= 0 else ""
            st.markdown(
                f'<div style="margin-bottom:4px;">' +
                f'<div style="font-family:Share Tech Mono,monospace;font-size:0.48rem;color:rgba(200,216,232,0.4);letter-spacing:2px;margin-bottom:3px;">◈ HOURLY HEAT MAP · ' +
                f'<span style="color:#FFD700;">{_peak_label}</span> &nbsp; ' +
                f'<span style="color:rgba(153,69,255,0.7);">{_worst_label}</span></div>' +
                f'<div style="display:flex;gap:2px;width:100%;">' +
                ''.join(_strip_cells) +
                '</div></div>',
                unsafe_allow_html=True
            )

        components.html(_full_html, height=_height, scrolling=True)

        # Colour key
        st.markdown(
            f'<div style="display:flex;gap:12px;flex-wrap:wrap;margin:4px 0 6px;font-family:Share Tech Mono,monospace;font-size:0.5rem;letter-spacing:1px;color:#666;">' +
            f'<span style="border-left:3px solid {C_BUY};padding-left:5px;color:{C_BUY};">BUY ENTRY</span>' +
            f'<span style="border-left:3px solid {C_SELL};padding-left:5px;color:{C_SELL};">SELL EXIT</span>' +
            f'<span style="border-left:3px solid {C_STALE};padding-left:5px;color:{C_STALE};">STALE >30s</span>' +
            f'<span style="border-left:3px solid #FFD700;padding-left:5px;color:#FFD700;">🔥 PEAK HOUR</span>' +
            f'<span style="border-left:3px solid rgba(153,69,255,0.5);padding-left:5px;color:#9945FF;">❄️ COLD HOUR</span>' +
            '</div>',
            unsafe_allow_html=True
        )

        # Trade history pagination (preserved)
        if _total_closed > _PAGE_SIZE:
            _total_pages = (_total_closed + _PAGE_SIZE - 1) // _PAGE_SIZE
            _cur_page = st.session_state.get("trade_hist_page", 0)
            _nav_cols = st.columns([1, 6, 1])
            with _nav_cols[0]:
                if st.button("← prev", key="trade_prev", disabled=_cur_page == 0, use_container_width=True):
                    st.session_state["trade_hist_page"] = max(0, _cur_page - 1); st.rerun()
            with _nav_cols[1]:
                _max_btns = min(_total_pages, 8)
                _pg_cols = st.columns(_max_btns)
                for _pi in range(_max_btns):
                    with _pg_cols[_pi]:
                        if st.button(str(_pi + 1), key=f"tpg_{_pi}",
                                     type="primary" if _pi == _cur_page else "secondary",
                                     use_container_width=True):
                            st.session_state["trade_hist_page"] = _pi; st.rerun()
            with _nav_cols[2]:
                if st.button("next →", key="trade_next", disabled=_cur_page >= _total_pages - 1, use_container_width=True):
                    st.session_state["trade_hist_page"] = min(_total_pages - 1, _cur_page + 1); st.rerun()

    except Exception as e:
        st.markdown(f"<div style='color:#FF073A;font-family:Share Tech Mono;'>MOTOR OUTPUT ERROR: {html.escape(str(e))}</div>", unsafe_allow_html=True)


@st.fragment(run_every=15)
def render_unified_execution_lanes() -> None:
    """
    UNIFIED EXECUTION LANE — isolated fragment, auto-refreshes every 8s.
    Shows: token, pct, dollar PnL, price source badge, age.
    Reads from fetch_live_open_positions_breathe() which prefers live_exec_*
    columns (age 1-8s) over market_snapshots (up to 20s stale).
    Fragment isolation means this section re-renders independently —
    no full-page rerun needed, no other panels disturbed.
    """
    import time as _t
    _rb = int(_t.time() // 5)  # 5s bucket for cache alignment
    _trades = fetch_live_open_positions_breathe(str(DB_PATH), _rb)
    if not _trades:
        st.markdown(
            "<div style='padding:10px 16px;border:1px dashed rgba(153,69,255,0.2);"
            "border-radius:8px;background:rgba(5,2,16,0.3);margin:4px 0 8px;'>"
            "<div style='font-family:Share Tech Mono,monospace;font-size:.58rem;"
            "color:#333;letter-spacing:2px;margin-bottom:6px;'>⚡ LIVE EXECUTION LANES — DORMANT</div>"
            "<div style='height:12px;border-radius:6px;background:rgba(255,255,255,0.03);"
            "border:1px solid rgba(255,255,255,0.06);position:relative;'>"
            "<div style='position:absolute;top:-2px;left:50%;width:2px;height:16px;"
            "background:#ffffff11;transform:translateX(-50%);'></div></div>"
            "<div style='display:flex;justify-content:space-between;margin-top:4px;"
            "font-family:Share Tech Mono,monospace;font-size:.5rem;color:#2a2a2a;'>"
            "<span>◄ SL</span><span>HUNTING — AWAITING LATCH</span><span>TP ►</span>"
            "</div></div>",
            unsafe_allow_html=True,
        )
        return

    st.markdown(
        "<div style='margin-bottom:8px;padding:8px 14px;"
        "border:1px solid rgba(20,241,149,0.2);border-radius:8px;"
        "background:rgba(5,2,16,0.4);'>"
        f"<span style='font-family:Share Tech Mono;font-size:0.72rem;"
        f"letter-spacing:3px;color:#14F195;'>LIVE EXECUTION LANE</span>"
        f"<span style='font-family:Share Tech Mono;font-size:0.65rem;"
        f"color:#888;float:right;'>{len(_trades)} position(s)</span>"
        "</div>",
        unsafe_allow_html=True,
    )

    for _t_row in _trades:
        _pct_raw = _t_row.get("pnl_pct", None)
        _pct    = float(_pct_raw) if _pct_raw is not None else 0.0
        _pnl    = float(_t_row.get("pnl", 0.0) or 0.0)
        _badge  = _t_row.get("src_badge", "STALE")
        _age    = _t_row.get("age_str", "?")
        _token  = _t_row.get("token", "?")
        _fresh  = _t_row.get("is_fresh", False)
        _pcol   = "#14F195" if _pct >= 0 else "#FF073A"
        _bcol   = "#14F195" if _badge == "LIVE" else (
                  "#FF073A" if _badge in ("STALE","STALE_EXEC","NO_DATA","NO_EXEC_DATA") else "#FFD700")
        st.markdown(
            f"<div style='display:flex;justify-content:space-between;"
            f"align-items:center;padding:6px 12px;margin-bottom:2px;"
            f"border-radius:6px;border-left:3px solid {_pcol};"
            f"background:rgba(255,255,255,0.02);"
            f"font-family:Share Tech Mono,monospace;font-size:0.72rem;'>"
            f"<span style='color:#8EF9FF;'>{html.escape(_token)}</span>"
            f"<span style='color:{_pcol};font-weight:bold;'>"
            f"{(_pct_raw is not None and f'{_pct:+.2f}%&nbsp;&nbsp;${_pnl:+.3f}' or ('?? GATE BLOCKED' if _badge == 'GATE_BLOCKED' else 'NO EXEC DATA'))}</span>"
            f"<span style='color:{_bcol};font-size:0.62rem;'>"
            f"[{_badge}&nbsp;{_age}]</span>"
            f"</div>",
            unsafe_allow_html=True,
        )
        # PRESSURE GAUGE METER — SL(red)←→TP(green) per trade
        render_living_trade_meter(_t_row)


def render_sovereign_flow_engine(snapshots_df=None, open_pos_df=None, reviews_df=None, raw_dna_df=None, executions_df=None) -> None:
    """SOVEREIGN FLOW ENGINE — unified pipeline visualiser. No @fragment."""
    import html as _html, time as _t
    _G="#14F195"; _GO="#FFD700"; _R="#FF073A"; _P="#9945FF"; _C="#8EF9FF"; _DIM="#94A3B8"
    _BG="rgba(5,2,16,0.80)"; _BORDER="rgba(20,241,149,0.22)"
    def _sdf(df): return df is not None and not df.empty
    def _ival(df,col,d=0):
        try: return int(df.iloc[0][col]) if _sdf(df) and col in df.columns else d
        except: return d
    _total_dna=_ival(raw_dna_df,"count",0)
    _recent_raw=len(snapshots_df) if _sdf(snapshots_df) else 0
    _raw_color=_G if _total_dna>0 else _DIM
    _latched_n=len(snapshots_df[snapshots_df["candidate_state"]=="latched"]) if _sdf(snapshots_df) and "candidate_state" in snapshots_df.columns else 0
    _vetoed_n=len(snapshots_df[snapshots_df["candidate_state"]=="vetoed"]) if _sdf(snapshots_df) and "candidate_state" in snapshots_df.columns else 0
    _total_snap=_recent_raw
    _qual_rate=(_latched_n/max(_total_snap,1))*100
    _rug_rate=(_vetoed_n/max(_total_snap,1))*100
    if _total_snap==0: _tide_state="🌑 DORMANT";_tide_color=_DIM;_tide_score=0
    elif _qual_rate>=15 and _rug_rate<40: _tide_state="🔥 HUNTING";_tide_color=_G;_tide_score=min(100,int(_qual_rate*4))
    elif _qual_rate>=5: _tide_state="🧪 LEARNING";_tide_color=_GO;_tide_score=min(80,int(_qual_rate*3))
    elif _rug_rate>60: _tide_state="⚡ CHAOTIC";_tide_color=_R;_tide_score=15
    else: _tide_state="🛡 DEFENSIVE";_tide_color=_C;_tide_score=30
    _execute_n=_watch_n=_skip_n=0
    try:
        import sqlite3 as _sq3f
        _cf=_sq3f.connect(str(DB_PATH),timeout=2,check_same_thread=False)
        _tables_f={r[0] for r in _cf.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        if "candidate_scores" in _tables_f:
            for _sr in _cf.execute("SELECT total_score FROM candidate_scores ORDER BY scored_at DESC LIMIT 20").fetchall():
                s=int(_sr[0] or 0)
                if s>=80: _execute_n+=1
                elif s>=55: _watch_n+=1
                else: _skip_n+=1
        elif _sdf(snapshots_df) and "mint_confidence" in snapshots_df.columns:
            for _sc in snapshots_df["mint_confidence"].dropna().head(20):
                s=int(float(_sc)*100)
                if s>=80: _execute_n+=1
                elif s>=55: _watch_n+=1
                else: _skip_n+=1
        _cf.close()
    except Exception: pass
    _matrix_color=_G if _execute_n>0 else (_GO if _watch_n>0 else _DIM)
    _latch_color=_G if _latched_n>0 else _DIM
    _open_n=len(open_pos_df) if _sdf(open_pos_df) else 0
    _pnl_sum=0.0
    if _sdf(open_pos_df) and "unrealized_pnl_usd" in open_pos_df.columns:
        try: _pnl_sum=float(open_pos_df["unrealized_pnl_usd"].fillna(0).sum())
        except: pass
    _exec_pnl_col=_G if _pnl_sum>=0 else _R
    _exec_sub=f"${_pnl_sum:+.2f} uPnL" if _open_n>0 else "no positions"
    _mem_total=len(reviews_df) if _sdf(reviews_df) else 0
    _mem_wins=int((reviews_df["win_loss"]=="WIN").sum()) if _mem_total>0 and "win_loss" in reviews_df.columns else 0
    _wr=round((_mem_wins/max(_mem_total,1))*100,1) if _mem_total>=3 else 0.0
    _mem_color=_G if _wr>=60 else (_GO if _wr>=40 else (_R if _mem_total>=3 else _DIM))
    _mem_label=f"{_wr}% WR" if _mem_total>=3 else f"{_mem_total} trades"
    def _node(icon,title,value,sub,color,active=True):
        _op="1.0" if active else "0.35"
        _glow=f"box-shadow:0 0 12px {color}44;" if active else ""
        return (f"<div style='display:flex;flex-direction:column;align-items:center;justify-content:center;padding:10px 8px;min-width:90px;border-radius:10px;border:1px solid {color}55;background:rgba(5,2,16,0.7);opacity:{_op};{_glow}'>"
                f"<div style='font-size:1.0rem;margin-bottom:2px;'>{icon}</div>"
                f"<div style='font-family:Share Tech Mono;font-size:0.52rem;letter-spacing:2px;color:{color};margin-bottom:4px;'>{_html.escape(title)}</div>"
                f"<div style='font-family:Orbitron,sans-serif;font-size:0.82rem;font-weight:700;color:{color};line-height:1.1;'>{_html.escape(str(value))}</div>"
                f"<div style='font-family:Share Tech Mono;font-size:0.48rem;color:{_DIM};margin-top:3px;'>{_html.escape(str(sub))}</div></div>")
    def _arrow(color="#333"): return f"<div style='display:flex;align-items:center;justify-content:center;padding:0 4px;font-size:0.9rem;color:{color};opacity:0.6;'>▶</div>"
    _matrix_total=_execute_n+_watch_n+_skip_n
    _n1=_node("📡","RAW STREAM",f"{_total_dna:,}",f"{_recent_raw} recent",_raw_color,_total_dna>0)
    _n2=_node("🌊","MARKET TIDE",_tide_state.split(" ",1)[-1],f"score {_tide_score}",_tide_color,_total_snap>0)
    _n3=_node("⬡","MATRIX",f"{_matrix_total} scored",f"{_execute_n}E {_watch_n}W {_skip_n}S",_matrix_color,_matrix_total>0)
    _n4=_node("🔒","LATCH",str(_latched_n),"signals locked" if _latched_n>0 else "idle",_latch_color,_latched_n>0)
    _n5=_node("⚡","EXECUTION",str(_open_n),_exec_sub,_exec_pnl_col,_open_n>0)
    _n6=_node("🧠","MEMORY",_mem_label,f"{_mem_wins}W/{_mem_total-_mem_wins}L" if _mem_total>0 else "learning",_mem_color,_mem_total>0)
    st.markdown(f"""<div style="margin:16px 0 12px;padding:16px 20px;border:1px solid {_BORDER};border-radius:14px;background:{_BG};overflow:hidden;width:100%;box-sizing:border-box;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;">
        <span style="font-family:Share Tech Mono;font-size:0.78rem;letter-spacing:4px;color:{_G};">⬡ SOVEREIGN FLOW ENGINE</span>
        <span style="font-family:Share Tech Mono;font-size:0.50rem;color:#333;letter-spacing:2px;">RAW → TIDE → MATRIX → LATCH → EXEC → MEMORY</span>
      </div>
      <div style="display:flex;align-items:stretch;justify-content:center;gap:0;flex-wrap:nowrap;overflow-x:auto;">
        {_n1}{_arrow(_raw_color if _total_dna>0 else "#333")}{_n2}{_arrow(_tide_color if _total_snap>0 else "#333")}{_n3}{_arrow(_matrix_color if _matrix_total>0 else "#333")}{_n4}{_arrow(_latch_color if _latched_n>0 else "#333")}{_n5}{_arrow(_exec_pnl_col if _open_n>0 else "#333")}{_n6}
      </div>
      <div style="display:flex;justify-content:center;gap:20px;margin-top:10px;font-family:Share Tech Mono;font-size:0.48rem;color:#333;letter-spacing:1px;">
        <span style="color:{_tide_color};">{_tide_state}</span><span>·</span>
        <span style="color:{_matrix_color};">{_execute_n}E / {_watch_n}W / {_skip_n}S</span><span>·</span>
        <span style="color:{_exec_pnl_col if _open_n>0 else _DIM};">{_open_n} open</span><span>·</span>
        <span style="color:{_mem_color};">{_mem_label}</span>
      </div></div>""", unsafe_allow_html=True)


def render_matrix_filtration_panel() -> None:
    """
    EDGE CANDIDATE ARENA — Phase 3: Selective Aggression visual home.
    momentum_score ranked. Bomb Signatures ignite. Weak candidates recede.
    Observe-only. No @fragment — parent cortex cycle refreshes.
    """
    import sqlite3 as _sq3, html as _html, time as _t, json as _json
    _now = _t.time()
    _rows = []
    try:
        _c = _sq3.connect(str(DB_PATH), timeout=3, check_same_thread=False)
        _c.row_factory = _sq3.Row
        _ms_cols = {r[1] for r in _c.execute("PRAGMA table_info(market_snapshots)").fetchall()}
        _has_mom = "momentum_score" in _ms_cols
        if _has_mom:
            _rows = _c.execute("""
                SELECT COALESCE(token_name, mint_address) AS token_name,
                       COALESCE(momentum_score, 0.0) AS momentum_score,
                       COALESCE(bomb_signature, 0) AS bomb_signature,
                       COALESCE(ranking_snapshot, '') AS ranking_snapshot,
                       COALESCE(mint_confidence, 0.0) AS confidence,
                       COALESCE(freshness_score, 0.0) AS freshness_score,
                       COALESCE(tier, 'COLD') AS tier,
                       COALESCE(token_liquidity_usd, 0) AS liquidity_usd,
                       COALESCE(curve_progress_pct, 0) AS curve_pct,
                       COALESCE(token_age_seconds, 0) AS age_sec,
                       candidate_state, quality_status
                FROM market_snapshots
                WHERE candidate_state NOT IN ('vetoed','expired_stale','executed','dead','EXECUTOR_STALE_GATE')
                  AND COALESCE(price_updated_at, 0) > ?
                ORDER BY momentum_score DESC, freshness_score DESC, mint_confidence DESC LIMIT 8
            """, (_now - 300,)).fetchall()
        else:
            _rows = _c.execute("""
                SELECT COALESCE(token_name, mint_address) AS token_name,
                       0.0 AS momentum_score, 0 AS bomb_signature, '' AS ranking_snapshot,
                       COALESCE(mint_confidence, 0) AS confidence,
                       COALESCE(freshness_score, 0) AS freshness_score,
                       COALESCE(tier,'COLD') AS tier,
                       COALESCE(token_liquidity_usd,0) AS liquidity_usd,
                       COALESCE(curve_progress_pct,0) AS curve_pct,
                       COALESCE(token_age_seconds,0) AS age_sec,
                       candidate_state, quality_status
                FROM market_snapshots
                WHERE candidate_state NOT IN ('vetoed','expired_stale','executed','dead','EXECUTOR_STALE_GATE')
                ORDER BY mint_confidence DESC, price_updated_at DESC LIMIT 8
            """).fetchall()
        _c.close()
    except Exception:
        _rows = []

    st.markdown(
        "<div style='margin-top:12px;padding:14px 16px;"
        "border:1px solid rgba(153,69,255,0.35);border-radius:12px;"
        "background:rgba(5,2,16,0.65);overflow:hidden;width:100%;box-sizing:border-box;'>",
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
        '<span style="font-family:Share Tech Mono;font-size:0.78rem;letter-spacing:4px;color:#9945FF;">⬡ EDGE CANDIDATE ARENA</span>'
        '<span style="font-family:Share Tech Mono;font-size:0.48rem;color:#333;letter-spacing:1px;">MOMENTUM-RANKED</span>'
        '</div>',
        unsafe_allow_html=True,
    )

    if not _rows:
        st.markdown(
            '<div style="font-family:Share Tech Mono;font-size:0.58rem;color:#333;'
            'letter-spacing:2px;padding:6px 0;">// ARENA AWAITING CANDIDATES //</div>',
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
        return

    _anim_css = (
        "<style>"
        "@keyframes bombIgnite{0%,100%{box-shadow:0 0 8px #FF073A44}50%{box-shadow:0 0 22px #FF073Acc,inset 0 0 14px #FF073A22}}"
        "@keyframes hotPulse{0%,100%{opacity:0.88}50%{opacity:1}}"
        "@keyframes recede{0%,100%{opacity:0.32}50%{opacity:0.42}}"
        "</style>"
    )
    _col_header = (
        '<div style="display:grid;grid-template-columns:2fr 70px 48px 54px 48px 1fr;'
        'gap:3px;padding:2px 6px 5px;font-family:Share Tech Mono;font-size:0.46rem;'
        'letter-spacing:1px;color:#2a2a2a;border-bottom:1px solid rgba(255,255,255,0.04);margin-bottom:3px;">'
        '<span>TOKEN</span><span>MOMENTUM</span><span>CURVE</span>'
        '<span>LIQ</span><span>AGE</span><span>FACTOR</span></div>'
    )

    rows_html = ""
    for r in _rows:
        try:
            token = _html.escape(str(r["token_name"] or "")[:14])
            mom   = float(r["momentum_score"] or 0)
            bomb  = bool(r["bomb_signature"])
            tier  = str(r["tier"] or "COLD")
            liq   = float(r["liquidity_usd"] or 0)
            curve = float(r["curve_pct"] or 0)
            age   = float(r["age_sec"] or 0)
            state = str(r["candidate_state"] or "")
            # Dominant factor
            _dom = ""
            try:
                _bd = _json.loads(r["ranking_snapshot"] or "{}")
                _fac = {"pv": _bd.get("price_velocity",0), "la": _bd.get("liquidity_acceleration",0), "cv": _bd.get("curve_velocity",0)}
                _dk = max(_fac, key=_fac.get)
                if _fac[_dk] > 0.1:
                    _dom = f"{_dk}={_fac[_dk]:.2f}"
            except Exception: pass
            # Visual tier
            if bomb:
                bg,bc,anim,op,rc = "rgba(255,7,58,0.08)","#FF073A","animation:bombIgnite 0.9s ease-in-out infinite;","1.0","#FF073A"
                rlabel,nc = f"BOMB {mom:.3f}","#FF6B6B"
            elif tier == "HOT" and mom > 0.3:
                bg,bc,anim,op,rc = "rgba(20,241,149,0.06)","#14F195","animation:hotPulse 2s ease-in-out infinite;","1.0","#14F195"
                rlabel,nc = f"↑ {mom:.3f}","#FFF"
            elif tier in ("WARM","HOT"):
                bg,bc,anim,op,rc = "rgba(255,215,0,0.04)","#FFD700","","0.85","#FFD700"
                rlabel,nc = f"  {mom:.3f}","#DDD"
            else:
                bg,bc,anim,op,rc = "rgba(5,2,16,0.3)","#2a2a2a","animation:recede 4s ease-in-out infinite;","0.38","#333"
                rlabel,nc = f"  {mom:.3f}","#555"
            bw = max(2, int(mom * 58))
            ls = f"${liq/1000:.0f}k" if liq >= 1000 else (f"${liq:.0f}" if liq > 0 else "—")
            sb = "🔒" if state == "latched" else "·"
            rows_html += (
                f'<div style="display:grid;grid-template-columns:2fr 70px 48px 54px 48px 1fr;'
                f'gap:3px;align-items:center;padding:4px 6px;margin-bottom:2px;'
                f'border-radius:4px;border-left:3px solid {bc};background:{bg};opacity:{op};{anim}">'
                f'<span style="font-family:Share Tech Mono,monospace;font-size:0.6rem;color:{nc};'
                f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{sb} {token}</span>'
                f'<span style="font-family:Share Tech Mono,monospace;font-size:0.58rem;color:{rc};">'
                f'{rlabel}<span style="display:block;height:2px;width:{bw}px;background:{rc};'
                f'border-radius:1px;margin-top:1px;opacity:0.65;"></span></span>'
                f'<span style="font-family:Share Tech Mono,monospace;font-size:0.52rem;color:#555;">{curve:.0f}%</span>'
                f'<span style="font-family:Share Tech Mono,monospace;font-size:0.52rem;color:#444;">{ls}</span>'
                f'<span style="font-family:Share Tech Mono,monospace;font-size:0.52rem;color:#444;">{age:.0f}s</span>'
                f'<span style="font-family:Share Tech Mono,monospace;font-size:0.47rem;color:#333;'
                f'overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">{_html.escape(_dom)}</span>'
                f'</div>'
            )
        except Exception:
            continue

    st.markdown(_anim_css + _col_header + rows_html, unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)


def render_api_status_bar() -> None:
    """Grand Vision header: sovereign council row + separate compact senses trio."""
    import os

    COUNCIL = [
        ("POLARIS",  "Polar",   "Architect",  "gpt-5.4-mini",   "OPENAI_API_KEY",       "#8EF9FF"),
        ("IVARIS",   "Ivy",     "Critic",     "mistral-large",  "NVIDIA_NIM_API_KEY",   "#FFB347"),
        ("NUGGET",   "Nugget",  "Auditor",    "kimi-k2",        "NVIDIA_NIM_API_KEY",   "#FFD700"),
        ("GROK",     "Rhiza",   "Integrator", "grok-3",         "XAI_API_KEY",          "#FF6B6B"),
        ("AXIOM",    "NIM",     "Library",    "70+ models",     "NVIDIA_NIM_API_KEY",   "#76B900"),
        ("GOVERNOR", "Local",   "Gate",       "orchestrator",   "",                     "#9945FF"),
    ]
    SENSES = [
        ("X SCOUT",  "TWITTER_BEARER_TOKEN", "#1DA1F2"),
        ("BRAVE",    "BRAVE_SEARCH_API_KEY", "#FF6B35"),
        ("TELEGRAM", "TELEGRAM_BOT_TOKEN",   "#2CA5E0"),
    ]

    agent_html = ""
    for code, origin, role, model, key, col in COUNCIL:
        ok = bool(os.getenv(key, "")) if key else True
        dot = col if ok else "#2a2a2a"
        glow = f"0 0 8px {col}88" if ok else "none"
        agent_html += (
            "<div style='display:inline-flex;flex-direction:column;align-items:center;"
            "justify-content:center;gap:1px;min-width:74px;flex:0 0 auto;'>"
            "<div style='display:flex;align-items:center;gap:4px;white-space:nowrap;'>"
            f"<span style='width:6px;height:6px;border-radius:50%;background:{dot};box-shadow:{glow};flex-shrink:0;'></span>"
            f"<span style='font-family:Orbitron,sans-serif;font-size:.54rem;letter-spacing:1.5px;color:{col if ok else '#333'};font-weight:700;'>{code}</span>"
            f"<span style='font-family:Share Tech Mono,monospace;font-size:.46rem;color:{col}66;letter-spacing:.8px;'>· {origin}</span>"
            "</div>"
            f"<span style='font-size:.42rem;color:#444;font-family:Share Tech Mono,monospace;letter-spacing:.8px;white-space:nowrap;'>{role} · {model[:13]}</span>"
            "</div>"
        )

    sense_html = ""
    for name, key, col in SENSES:
        ok = bool(os.getenv(key, ""))
        dot = col if ok else "#2a2a2a"
        # Special handling for BRAVE — show daily usage counter
        if name == "BRAVE" and ok:
            try:
                _brave_used = int(get_config_value("BRAVE_SEARCHES_TODAY", 0) or 0)
                _brave_hit = _brave_used >= 900
                dot = "#FF073A" if _brave_hit else col
                _blink = "animation:pulse 1s infinite;" if _brave_hit else ""
                sense_html += (
                    f"<span style='display:inline-flex;align-items:center;gap:4px;"
                    f"font-size:.52rem;font-family:Share Tech Mono,monospace;letter-spacing:1px;"
                    f"white-space:nowrap;flex:0 0 auto;color:{dot};'>"
                    f"<span style='width:5px;height:5px;border-radius:50%;background:{dot};{_blink}'></span>BRAVE</span>"
                )
                continue
            except Exception:
                pass
        sense_html += (
            "<span style='display:inline-flex;align-items:center;gap:4px;"
            "font-size:.52rem;font-family:Share Tech Mono,monospace;letter-spacing:1px;"
            "white-space:nowrap;flex:0 0 auto;"
            f"color:{col if ok else '#333'};'>"
            f"<span style='width:5px;height:5px;border-radius:50%;background:{dot};'></span>{name}</span>"
        )

    st.markdown(
        "<div style='padding:8px 14px;background:rgba(5,2,16,0.88);"
        "border-bottom:1px solid rgba(153,69,255,0.22);display:flex;align-items:center;"
        "gap:10px;flex-wrap:nowrap;white-space:nowrap;overflow-x:auto;overflow-y:hidden;'>"
        "<span style='font-size:.5rem;color:#333;font-family:Share Tech Mono,monospace;"
        "letter-spacing:3px;margin-right:4px;padding-right:10px;border-right:1px solid rgba(255,255,255,0.08);flex:0 0 auto;'>COUNCIL</span>"
        f"{agent_html}"
        "<div style='margin-left:auto;display:inline-flex;align-items:center;gap:8px;flex:0 0 auto;"
        "padding-left:12px;border-left:1px solid rgba(255,255,255,0.08);'>"
        "<span style='font-size:.5rem;color:#333;font-family:Share Tech Mono,monospace;letter-spacing:3px;'>SENSES</span>"
        f"{sense_html}"
        "</div>"
        "</div>",
        unsafe_allow_html=True,
    )


def render_organism_pressure_core() -> None:
    """
    DOMINANT organism nervous system meter — full width, above execution arena.
    6 animated bars: conviction, exec flow, market resonance, evolution energy,
    research heat, live risk. CSS glow + breathing only — no canvas.
    """
    import time as _t, sqlite3 as _sq
    _cfg = {}; _latch_ok = False; _open = 0; _wr = 0; _halt = False
    _debate_rounds = 0; _x_posts = 0; _proposals_open = 0
    try:
        _db = _sq.connect(str(DB_PATH), timeout=3); _db.row_factory = _sq.Row
        _cfg = {str(r["key"]): str(r["value"]) for r in _db.execute(
            "SELECT key, value FROM system_config").fetchall()}
        _latch_ok = bool(_db.execute(
            "SELECT 1 FROM market_snapshots WHERE candidate_state='latched' LIMIT 1").fetchone())
        _open = int((_db.execute(
            "SELECT COUNT(*) FROM paper_positions WHERE status='OPEN'").fetchone() or [0])[0])
        _rev = _db.execute(
            "SELECT win_loss FROM polaris_trade_reviews ORDER BY id DESC LIMIT 30").fetchall()
        if len(_rev) >= 3:
            _wins = sum(1 for r in _rev if str(r[0] if not hasattr(r,"keys") else r["win_loss"]).upper()=="WIN")
            _wr = round(_wins/len(_rev)*100, 1)
        _halt = _cfg.get("DRAWDOWN_HALT_ACTIVE","0") in ("1","true","True")
        _debate_rounds = int((_db.execute(
            "SELECT COUNT(*) FROM debate_log").fetchone() or [0])[0])
        _proposals_open = int((_db.execute(
            "SELECT COUNT(*) FROM polaris_proposals WHERE status IN ('open','debating','pending_replay')").fetchone() or [0])[0])
        try:
            _x_posts = int((_db.execute(
                "SELECT COUNT(*) FROM intelligence_forge WHERE stage='X_SCOUT'").fetchone() or [0])[0])
        except Exception: _x_posts = 0
        _db.close()
    except Exception: pass

    _max_pos = int(_cfg.get("MAX_OPEN_POSITIONS","3"))
    _min_conf = float(_cfg.get("SUPERVISOR_MIN_MINT_CONFIDENCE","0.75"))

    # Calculate 6 pressure signals
    conviction      = min(100, int(sum([_latch_ok, _wr>=40, not _halt, _open>0])/4*100))
    exec_flow       = min(100, int(_open/_max_pos*100)) if _max_pos else 0
    mkt_resonance   = min(100, int(_min_conf*100 + (10 if _latch_ok else 0)))
    evolution_energy= min(100, min(100, _debate_rounds//5 + _proposals_open*15))
    research_heat   = min(100, min(100, _x_posts//3 + _debate_rounds//10))
    live_risk       = min(100, int(_open/_max_pos*100 + (20 if _halt else 0))) if _max_pos else 0

    bars = [
        ("CONVICTION",       conviction,       "#FFD700"),
        ("EXECUTION FLOW",   exec_flow,        "#14F195"),
        ("MARKET RESONANCE", mkt_resonance,    "#8EF9FF"),
        ("EVOLUTION ENERGY", evolution_energy, "#9945FF"),
        ("RESEARCH HEAT",    research_heat,    "#FF6B35"),
        ("LIVE RISK",        live_risk,        "#FF073A"),
    ]

    dominant_col = "#FFD700" if conviction >= 60 else ("#9945FF" if evolution_energy >= 40 else "#555")

    bar_rows = ""
    for label, pct, col in bars:
        bar_rows += (
            f"<div style='margin-bottom:9px;'>"
            f"<div style='display:flex;justify-content:space-between;"
            f"font-family:Share Tech Mono,monospace;font-size:.6rem;"
            f"letter-spacing:2px;color:#888;margin-bottom:3px;'>"
            f"<span>{label}</span>"
            f"<span style='color:{col};font-weight:700;'>{pct}%</span></div>"
            f"<div style='height:5px;border-radius:3px;background:#0d0d18;overflow:hidden;'>"
            f"<div style='height:100%;width:{pct}%;background:{col};"
            f"box-shadow:0 0 10px {col};border-radius:3px;"
            f"animation:pressBreath 3s ease-in-out infinite;'></div>"
            f"</div></div>"
        )

    html_out = (
        f"<style>"
        f"@keyframes pressBreath{{0%,100%{{opacity:.9}}50%{{opacity:1}}}}"
        f"@keyframes coreGlow{{0%,100%{{box-shadow:0 0 20px {dominant_col}22,inset 0 0 30px {dominant_col}08}}"
        f"50%{{box-shadow:0 0 40px {dominant_col}44,inset 0 0 40px {dominant_col}12}}}}"
        f"</style>"
        f"<div style='padding:16px 20px;background:rgba(5,2,16,0.9);"
        f"border:1px solid {dominant_col}44;border-radius:14px;margin:12px 0 14px;"
        f"animation:coreGlow 4s ease-in-out infinite;'>"
        f"<div style='font-family:Orbitron,sans-serif;font-size:.72rem;letter-spacing:5px;"
        f"color:{dominant_col};margin-bottom:14px;"
        f"text-shadow:0 0 12px {dominant_col}88;'>"
        f"◈ ORGANISM PRESSURE CORE</div>"
        f"<div style='display:grid;grid-template-columns:1fr 1fr;gap:0 24px;'>"
        f"{bar_rows}"
        f"</div>"
        f"<div style='margin-top:10px;display:flex;gap:16px;flex-wrap:wrap;'>"
        f"<span style='font-family:Share Tech Mono,monospace;font-size:.55rem;color:#444;'>"
        f"DEBATE ROUNDS {_debate_rounds}</span>"
        f"<span style='font-family:Share Tech Mono,monospace;font-size:.55rem;color:#444;'>"
        f"X POSTS {_x_posts}</span>"
        f"<span style='font-family:Share Tech Mono,monospace;font-size:.55rem;color:#444;'>"
        f"PROPOSALS ACTIVE {_proposals_open}</span>"
        f"</div>"
        f"</div>"
    )
    st.markdown(html_out, unsafe_allow_html=True)

def render_holographic_ascension_map() -> None:
    """
    THE ASCENSION PATH — horizontal glowing node timeline.
    Maps one proposal from SEED → RESEARCH → DEBATE → SIMULATE → PAPER → DEPLOY → LATTICE → SOVEREIGN
    Active node glows. HITL node pulses gold. Blocked node red.
    """
    import time as _t, sqlite3 as _sq, html as _html

    NODES = [
        ("SEED",     "🌱", "Genesis"),
        ("RESEARCH", "🔭", "X/Brave"),
        ("DEBATE",   "⚖️",  "Council"),
        ("SIMULATE", "🧪", "Replay"),
        ("PAPER",    "📋", "Validate"),
        ("DEPLOY",   "⚡", "Live"),
        ("LATTICE",  "🏛️",  "Absorb"),
        ("SOVEREIGN","◈",  "Evolved"),
    ]

    # Read current proposal state
    active_stage = "SEED"; hitl_id = None; hitl_cmd = ""; blocker = ""
    total_props = 0; approved = 0; debating = 0; blocked_count = 0
    try:
        _db = _sq.connect(str(DB_PATH), timeout=3); _db.row_factory = _sq.Row
        _props = _db.execute(
            "SELECT id, status, proposal_type, proposal_text FROM polaris_proposals ORDER BY updated_at DESC LIMIT 30"
        ).fetchall()
        total_props = len(_props)
        for p in _props:
            s = str(p["status"] or "")
            if s == "approved": approved += 1
            elif s in ("open","debating","pending_replay"): debating += 1
            elif s in ("nugget_escalated","HITL_REQUIRED"):
                hitl_id = p["id"]; hitl_cmd = f"python approve_proposal.py {p['id']}"
                active_stage = "LATTICE"
            elif s in ("critic_unavailable","rejected_by_ivaris"): blocked_count += 1
        # Determine stage from state
        if hitl_id:                                   active_stage = "LATTICE"
        elif approved > 0 and debating == 0:          active_stage = "SOVEREIGN"
        elif debating > 0 and blocked_count == 0:     active_stage = "DEBATE"
        elif blocked_count > total_props * 0.5:       active_stage = "RESEARCH"
        elif total_props == 0:                        active_stage = "SEED"
        else:                                         active_stage = "PAPER"
        # Blocker message
        _bl = _db.execute(
            "SELECT message FROM cognition_log WHERE stage='BUILD_BLOCKER' ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        if _bl: blocker = str(_bl["message"] or "")[:80]
        _db.close()
    except Exception: pass

    active_idx = next((i for i,n in enumerate(NODES) if n[0]==active_stage), 0)

    # Build CSS + HTML as one atomic string
    html_parts = ["""
<style>
@keyframes nodeGlow{0%,100%{box-shadow:0 0 12px currentColor,0 0 24px currentColor}50%{box-shadow:0 0 24px currentColor,0 0 48px currentColor}}
@keyframes hitlPulse{0%,100%{box-shadow:0 0 16px #FFD700,0 0 32px #FFD700;transform:scale(1)}50%{box-shadow:0 0 32px #FFD700,0 0 64px #FFD700;transform:scale(1.08)}}
@keyframes connectorFlow{0%{background-position:0% 50%}100%{background-position:200% 50%}}
.asc-wrap{padding:14px 16px;background:rgba(5,2,16,0.85);border:1px solid rgba(153,69,255,0.25);border-radius:12px;margin-bottom:12px;overflow:hidden}
.asc-title{font-family:Share Tech Mono,monospace;font-size:.65rem;letter-spacing:4px;color:#9945FF;margin-bottom:14px}
.asc-row{display:flex;align-items:center;justify-content:flex-start;flex-wrap:nowrap;overflow-x:auto;gap:0;padding-bottom:8px}
.asc-row::-webkit-scrollbar{height:3px}.asc-row::-webkit-scrollbar-thumb{background:#1a1a2e}
.asc-node{display:flex;flex-direction:column;align-items:center;gap:4px;flex-shrink:0;min-width:60px}
.asc-circle{width:36px;height:36px;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:1rem;border:2px solid currentColor;transition:.4s}
.asc-label{font-family:Share Tech Mono,monospace;font-size:.48rem;letter-spacing:1px;text-align:center;line-height:1.3}
.asc-sub{font-family:Share Tech Mono,monospace;font-size:.42rem;opacity:.5;text-align:center}
.asc-conn{flex:1;height:2px;min-width:12px;background:linear-gradient(90deg,currentColor 0%,transparent 100%);opacity:.35;align-self:center;margin:0 2px;margin-bottom:18px}
.asc-conn.active{opacity:1;background:linear-gradient(90deg,var(--prev-col),var(--next-col));background-size:200%;animation:connectorFlow 2s linear infinite}
</style>"""]

    html_parts.append('<div class="asc-wrap">')
    html_parts.append(f'<div class="asc-title">⬡ HOLOGRAPHIC ASCENSION PATH &nbsp;·&nbsp; '
                      f'<span style="color:#555;font-size:.5rem;">'
                      f'{approved} absorbed · {debating} active · {blocked_count} blocked'
                      f'</span></div>')
    html_parts.append('<div class="asc-row">')

    for i, (stage, glyph, sub) in enumerate(NODES):
        is_active = (i == active_idx)
        is_done   = (i < active_idx)
        is_hitl   = (stage == "LATTICE" and hitl_id)
        is_blocked= (stage == "DEBATE" and blocked_count > debating and not is_done)

        if is_hitl:
            col = "#FFD700"; anim = "hitlPulse 1.2s ease-in-out infinite"
            bg  = "rgba(255,215,0,0.15)"
        elif is_done:
            col = "#14F195"; anim = "none"; bg = "rgba(20,241,149,0.08)"
        elif is_active:
            col = "#9945FF"; anim = "nodeGlow 2.5s ease-in-out infinite"; bg = "rgba(153,69,255,0.12)"
        elif is_blocked:
            col = "#FF073A"; anim = "nodeGlow 3s ease-in-out infinite"; bg = "rgba(255,7,58,0.08)"
        else:
            col = "#2a2a2e"; anim = "none"; bg = "transparent"

        label_col = col if (is_active or is_done or is_hitl) else "#444"
        done_tick = " ✓" if is_done else ""

        html_parts.append(
            f'<div class="asc-node">'
            f'<div class="asc-circle" style="color:{col};background:{bg};'
            f'animation:{anim};border-color:{col};">{glyph}</div>'
            f'<div class="asc-label" style="color:{label_col};">{stage}{done_tick}</div>'
            f'<div class="asc-sub" style="color:{label_col};">{sub}</div>'
            f'</div>'
        )
        if i < len(NODES) - 1:
            conn_active = is_done or is_active
            conn_col    = "#14F195" if is_done else ("#9945FF" if is_active else "#1a1a2e")
            conn_cls    = "asc-conn active" if conn_active else "asc-conn"
            html_parts.append(
                f'<div class="{conn_cls}" style="color:{conn_col};'
                f'--prev-col:{conn_col};--next-col:{col};"></div>'
            )

    html_parts.append('</div>')  # asc-row

    # HITL gate message
    if hitl_id:
        html_parts.append(
            f'<div style="margin-top:10px;padding:8px 12px;background:rgba(255,215,0,0.06);'
            f'border:1px solid rgba(255,215,0,0.4);border-radius:8px;'
            f'font-family:Share Tech Mono,monospace;font-size:.6rem;color:#FFD700;">'
            f'🟠 SOVEREIGN SEAL REQUIRED — proposal #{hitl_id}<br>'
            f'<span style="color:#888;">{hitl_cmd}</span></div>'
        )
    elif blocker:
        html_parts.append(
            f'<div style="margin-top:8px;padding:6px 10px;background:rgba(255,7,58,0.06);'
            f'border-left:3px solid #FF073A;border-radius:4px;'
            f'font-family:Share Tech Mono,monospace;font-size:.58rem;color:#FF073A;">'
            f'⚠ {_html.escape(blocker)}</div>'
        )

    html_parts.append('</div>')  # asc-wrap
    st.markdown("".join(html_parts), unsafe_allow_html=True)


def render_golden_lattice() -> None:
    """
    THE GOLDEN LATTICE — Evolution Chamber.
    Shows proposals awaiting sovereign absorption (approved / HITL_REQUIRED).
    Sacred black/gold panel. This is the destination of the ascension path.
    """
    import sqlite3 as _sq, html as _html
    try:
        _db = _sq.connect(str(DB_PATH), timeout=3); _db.row_factory = _sq.Row
        _ready = _db.execute("""
            SELECT id, proposal_type, proposal_text, status, applied_value, notes
            FROM polaris_proposals
            WHERE status IN ('approved','nugget_escalated','HITL_REQUIRED','pending_replay')
            ORDER BY updated_at DESC LIMIT 5
        """).fetchall()
        _db.close()
    except Exception:
        _ready = []

    if not _ready:
        return  # Nothing to show — map hasn't reached lattice yet

    lattice_html = ["""
<style>
@keyframes latticeBreath{0%,100%{box-shadow:0 0 20px rgba(255,215,0,0.15),inset 0 0 20px rgba(255,215,0,0.03)}
50%{box-shadow:0 0 40px rgba(255,215,0,0.3),inset 0 0 30px rgba(255,215,0,0.06)}}
@keyframes glyphSpin{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
</style>
<div style="padding:14px 16px;background:rgba(5,2,16,0.95);
border:1px solid rgba(255,215,0,0.4);border-radius:12px;
animation:latticeBreath 4s ease-in-out infinite;margin-bottom:12px;">
<div style="font-family:Orbitron,sans-serif;font-size:.65rem;letter-spacing:4px;
color:#FFD700;margin-bottom:10px;display:flex;align-items:center;gap:8px;">
<span style="animation:glyphSpin 8s linear infinite;display:inline-block;">◈</span>
GOLDEN LATTICE — EVOLUTION CHAMBER
</div>"""]

    for p in _ready:
        sid  = p["id"]
        ptype= str(p["proposal_type"] or "")
        txt  = str(p["proposal_text"] or "")[:100]
        stat = str(p["status"] or "")
        notes= str(p["notes"] or "")[:60]
        is_hitl = stat in ("nugget_escalated","HITL_REQUIRED")
        border_col = "#FFD700" if is_hitl else "#14F195"
        stat_label = "⚡ AWAITING SEAL" if is_hitl else "✅ APPROVED"

        lattice_html.append(
            f'<div style="margin-bottom:8px;padding:8px 12px;'
            f'border-left:3px solid {border_col};background:rgba(255,215,0,0.04);border-radius:4px;">'
            f'<div style="font-family:Share Tech Mono,monospace;font-size:.58rem;'
            f'color:{border_col};letter-spacing:2px;margin-bottom:4px;">'
            f'{stat_label} &nbsp;·&nbsp; #{sid} &nbsp;·&nbsp; {_html.escape(ptype[:20])}</div>'
            f'<div style="font-family:Share Tech Mono,monospace;font-size:.55rem;color:#aaa;">'
            f'{_html.escape(txt)}</div>'
        )
        if notes:
            lattice_html.append(
                f'<div style="font-size:.5rem;color:#666;margin-top:3px;">{_html.escape(notes)}</div>'
            )
        if is_hitl:
            lattice_html.append(
                f'<div style="font-size:.52rem;color:#FFD700;margin-top:4px;">'
                f'→ python approve_proposal.py {sid}</div>'
            )
        lattice_html.append('</div>')

    lattice_html.append('</div>')
    st.markdown("".join(lattice_html), unsafe_allow_html=True)


def render_council_build_map() -> None:
    """Renders holographic ascension map + golden lattice."""
    render_holographic_ascension_map()
    render_golden_lattice()


def _measure_live_latency():
    try:
        conn = sqlite3.connect(str(DB_PATH), timeout=3.0)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("CREATE TABLE IF NOT EXISTS _dash_probe (ts INTEGER)")
        start = time.monotonic()
        conn.execute("INSERT INTO _dash_probe VALUES (?)", (int(time.time()),))
        conn.commit()
        conn.execute("DELETE FROM _dash_probe")
        conn.commit()
        ms = (time.monotonic() - start) * 1000
        conn.close()
        return ms
    except Exception: return 0.0

FOCUS_LOCK_TYPES    = {"SYSTEM_REPAIR"}
FOCUS_LOCK_STATUSES = {"open", "debating", "pending", "debate", "approved"}

def _is_focus_locked(proposals_df) -> bool:
    if proposals_df is None or proposals_df.empty: return False
    try:
        return not proposals_df[
            (proposals_df["proposal_type"].str.upper().isin(FOCUS_LOCK_TYPES)) &
            (proposals_df["status"].str.lower().isin(FOCUS_LOCK_STATUSES))
        ].empty
    except Exception: return False

def _apply_focus_lock(proposals_df):
    if proposals_df is None or proposals_df.empty: return proposals_df
    try:
        if not _is_focus_locked(proposals_df): return proposals_df
        repair_mask = proposals_df["proposal_type"].str.upper().isin(FOCUS_LOCK_TYPES)
        return pd.concat([proposals_df[repair_mask], proposals_df[~repair_mask].head(4)], ignore_index=True)
    except Exception: return proposals_df

def render_genesis_vault() -> None:
    """
    GENESIS VAULT — public-facing sovereign relic claim portal.
    Complete separation from live trading cockpit.
    No pipeline debug. No paper positions. No admin sludge.
    Ceremonial packaging of the community starter kit.
    """
    import hashlib, base64, os, zipfile, tempfile, io, time as _vt
    from pathlib import Path as _VP

    if "vault_seal_opened" not in st.session_state:
        st.session_state["vault_seal_opened"] = False

    # Back button
    if st.button("← RETURN TO ORGANISM", key="vault_back_btn"):
        st.session_state["genesis_vault_open"] = False
        st.session_state["vault_seal_opened"] = False
        st.rerun()

    st.markdown("""
    <style>
    @import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Share+Tech+Mono&family=Rajdhani:wght@300;400;600&display=swap');
    @keyframes vaultBreath{0%,100%{box-shadow:0 0 40px rgba(255,215,0,0.1),inset 0 0 60px rgba(255,215,0,0.03)}50%{box-shadow:0 0 80px rgba(255,215,0,0.25),inset 0 0 80px rgba(255,215,0,0.07)}}
    @keyframes latticeRotate{from{transform:rotate(0deg)}to{transform:rotate(360deg)}}
    @keyframes sealOpen{0%{transform:scale(1) rotate(0deg);opacity:1}50%{transform:scale(1.3) rotate(180deg);opacity:0.7}100%{transform:scale(0.9) rotate(360deg);opacity:1}}
    @keyframes shimmerGold{0%{background-position:200% center}100%{background-position:-200% center}}
    @keyframes pulseRing{0%{transform:scale(1);opacity:0.6}70%{transform:scale(1.4);opacity:0}100%{transform:scale(1.4);opacity:0}}
    @keyframes fadeUp{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}
    .vault-container{max-width:860px;margin:0 auto;padding:32px 24px;}
    .vault-hero{text-align:center;padding:48px 24px 36px;border:1px solid rgba(255,215,0,0.3);border-radius:20px;background:rgba(5,2,16,0.92);animation:vaultBreath 5s ease-in-out infinite;margin-bottom:24px;position:relative;overflow:hidden;}
    .vault-hero::before{content:'';position:absolute;inset:0;background:radial-gradient(ellipse at 50% 0%,rgba(255,215,0,0.06) 0%,transparent 60%);pointer-events:none;}
    .vault-glyph{font-size:3.2rem;animation:latticeRotate 12s linear infinite;display:inline-block;margin-bottom:16px;filter:drop-shadow(0 0 16px rgba(255,215,0,0.6));}
    .vault-title{font-family:Orbitron,monospace;font-size:clamp(1.4rem,5vw,2.4rem);font-weight:900;letter-spacing:6px;background:linear-gradient(90deg,#FFD700 0%,#FFF8DC 40%,#FFD700 80%,#FF8C00 100%);background-size:200% auto;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:shimmerGold 3s linear infinite;margin-bottom:8px;}
    .vault-sub{font-family:Share Tech Mono,monospace;font-size:0.7rem;color:rgba(255,215,0,0.5);letter-spacing:4px;margin-bottom:24px;}
    .vault-tagline{font-family:Rajdhani,sans-serif;font-size:1.1rem;color:#CCC;line-height:1.8;max-width:560px;margin:0 auto 24px;}
    .vault-badge{display:inline-block;padding:4px 14px;border:1px solid rgba(255,215,0,0.4);border-radius:20px;font-family:Share Tech Mono,monospace;font-size:0.55rem;color:rgba(255,215,0,0.6);letter-spacing:3px;margin:4px;}
    .vault-section{padding:20px 22px;border:1px solid rgba(255,255,255,0.06);border-radius:12px;background:rgba(5,2,16,0.6);margin-bottom:16px;animation:fadeUp 0.4s ease forwards;}
    .vault-section-title{font-family:Orbitron,monospace;font-size:0.7rem;letter-spacing:4px;color:#8EF9FF;margin-bottom:12px;display:flex;align-items:center;gap:8px;}
    .vault-item{display:flex;align-items:flex-start;gap:10px;padding:6px 0;border-bottom:1px solid rgba(255,255,255,0.04);}
    .vault-item:last-child{border-bottom:none;}
    .vault-item-icon{min-width:20px;color:#FFD700;font-size:0.9rem;}
    .vault-item-text{font-family:Rajdhani,sans-serif;font-size:0.92rem;color:#AAA;line-height:1.5;}
    .vault-item-text strong{color:#CCC;}
    .vault-warning{padding:14px 16px;border:1px solid rgba(255,69,0,0.3);border-radius:8px;background:rgba(255,69,0,0.04);}
    .vault-warning-text{font-family:Share Tech Mono,monospace;font-size:0.6rem;color:rgba(255,150,100,0.7);letter-spacing:1px;line-height:1.8;}
    .vault-maturity-bar{height:6px;border-radius:3px;background:rgba(255,255,255,0.06);overflow:hidden;margin:4px 0 8px;}
    .vault-maturity-fill{height:100%;border-radius:3px;background:linear-gradient(90deg,#9945FF,#14F195);box-shadow:0 0 8px rgba(20,241,149,0.4);}
    .vault-cmd{font-family:Share Tech Mono,monospace;font-size:0.68rem;color:#14F195;background:rgba(20,241,149,0.06);border:1px solid rgba(20,241,149,0.15);border-radius:6px;padding:10px 14px;margin:6px 0;letter-spacing:1px;word-break:break-all;}
    .vault-seal-btn{display:block;width:100%;padding:16px 24px;font-family:Orbitron,monospace;font-size:0.9rem;font-weight:700;letter-spacing:4px;color:#000;background:linear-gradient(90deg,#FFD700,#FF8C00,#FFD700);background-size:200% auto;border:none;border-radius:10px;cursor:pointer;animation:shimmerGold 2s linear infinite;text-align:center;margin:20px 0 0;}
    .vault-seal-btn:hover{filter:brightness(1.1);}
    .vault-checksum{font-family:Share Tech Mono,monospace;font-size:0.55rem;color:rgba(20,241,149,0.5);word-break:break-all;letter-spacing:1px;padding:8px;background:rgba(20,241,149,0.04);border-radius:4px;margin-top:8px;}
    .vault-contrib-bar{height:4px;border-radius:2px;background:rgba(153,69,255,0.15);overflow:hidden;margin:4px 0;}
    .vault-contrib-fill{height:100%;border-radius:2px;background:linear-gradient(90deg,#9945FF,#8EF9FF);}
    </style>
    """, unsafe_allow_html=True)

    st.markdown('<div class="vault-container">', unsafe_allow_html=True)

    # ── HERO ──────────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="vault-hero">
      <div class="vault-glyph">◈</div>
      <div class="vault-title">SENTINUITY GENESIS</div>
      <div class="vault-sub">SOVEREIGN STARTER KIT — COMMUNITY EDITION</div>
      <div class="vault-tagline">
        A stripped-down, sanitized build of the organism's core substrate.<br>
        No sovereign cognition. No proprietary forge. No family modules.<br>
        A seed. What you grow from here is yours.
      </div>
      <div>
        <span class="vault-badge">⚗ PAPER MODE ONLY</span>
        <span class="vault-badge">◈ TEMPORAL COHERENCE</span>
        <span class="vault-badge">⚡ PUMP.FUN SUBSTRATE</span>
        <span class="vault-badge">🔒 NO LIVE KEYS</span>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── COUNTDOWN + MASKED LINK ────────────────────────────────────────────────
    import time as _ct
    # Target: Friday 16 May 2026 09:00:00 AEST (UTC+10)
    _UNLOCK_TS = 1747346400  # 2026-05-16 09:00:00 AEST = 2026-05-15 23:00:00 UTC
    _now_ts = _ct.time()
    _diff = int(_UNLOCK_TS - _now_ts)
    if _diff > 0:
        _h = _diff // 3600
        _m = (_diff % 3600) // 60
        _s = _diff % 60
        _cd_str = f"{_h:02d}:{_m:02d}:{_s:02d}"
        _cd_label = "UNLOCKS IN"
        _link_html = "<div style='color:rgba(255,255,255,0.35);font-size:0.7rem;letter-spacing:2px;margin-top:6px;'>github.com/sentinuitylabs/XXXXXXXX</div>"
    else:
        _cd_str = "LIVE"
        _cd_label = "STATUS"
        _link_html = "<div style='margin-top:6px;'><a href='https://github.com/sentinuitylabs/sentinuity' target='_blank' style='color:#14F195;font-family:Share Tech Mono,monospace;font-size:0.7rem;letter-spacing:2px;text-decoration:none;'>github.com/sentinuitylabs/sentinuity ↗</a></div>"

    st.markdown(f"""<div style='text-align:center;margin:16px 0;padding:16px;border:1px solid rgba(255,215,0,0.2);border-radius:12px;background:rgba(5,2,16,0.6);'>
        <div style='font-family:Share Tech Mono,monospace;font-size:0.6rem;letter-spacing:4px;color:rgba(255,215,0,0.5);margin-bottom:6px;'>{_cd_label}</div>
        <div style='font-family:Orbitron,monospace;font-size:2rem;font-weight:900;color:#FFD700;letter-spacing:6px;text-shadow:0 0 20px rgba(255,215,0,0.4);'>{_cd_str}</div>
        {_link_html}
        <div style='font-family:Share Tech Mono,monospace;font-size:0.55rem;color:rgba(255,215,0,0.3);letter-spacing:3px;margin-top:8px;'>FOLLOW @sentinuity_labs · #SentinuityContest</div>
    </div>""", unsafe_allow_html=True)

    # ── ORGANISM MATURITY INDEX ────────────────────────────────────────────────
    try:
        _db = sqlite3.connect(str(DB_PATH), timeout=3)
        _db.row_factory = sqlite3.Row
        _trades  = _db.execute("SELECT COUNT(*) FROM paper_positions").fetchone()[0]
        _dna     = _db.execute("SELECT COUNT(*) FROM raw_dna").fetchone()[0]
        _props   = _db.execute("SELECT COUNT(*) FROM polaris_proposals WHERE status IN ('approved','applied')").fetchone()[0]
        _db.close()
    except Exception:
        _trades, _dna, _props = 0, 0, 0

    _maturity = min(100, (_trades * 3) + (_dna // 20) + (_props * 5))
    st.markdown(f"""
    <div class="vault-section">
      <div class="vault-section-title">◈ ORGANISM MATURITY INDEX</div>
      <div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:16px;margin-bottom:12px;">
        <div style="text-align:center;">
          <div style="font-family:Orbitron,monospace;font-size:1.6rem;color:#FFD700;">{_trades}</div>
          <div style="font-family:Share Tech Mono,monospace;font-size:0.5rem;color:#555;letter-spacing:2px;">TRADES LOGGED</div>
        </div>
        <div style="text-align:center;">
          <div style="font-family:Orbitron,monospace;font-size:1.6rem;color:#14F195;">{_dna}</div>
          <div style="font-family:Share Tech Mono,monospace;font-size:0.5rem;color:#555;letter-spacing:2px;">DNA NODES</div>
        </div>
        <div style="text-align:center;">
          <div style="font-family:Orbitron,monospace;font-size:1.6rem;color:#9945FF;">{_props}</div>
          <div style="font-family:Share Tech Mono,monospace;font-size:0.5rem;color:#555;letter-spacing:2px;">PROPOSALS SEALED</div>
        </div>
      </div>
      <div style="font-family:Share Tech Mono,monospace;font-size:0.52rem;color:#444;margin-bottom:4px;letter-spacing:2px;">MATURITY SCORE {_maturity}/100</div>
      <div class="vault-maturity-bar"><div class="vault-maturity-fill" style="width:{_maturity}%;"></div></div>
      <div style="font-family:Rajdhani,sans-serif;font-size:0.82rem;color:#555;">
        {'Organism has logged meaningful runtime. Genesis Kit captures the architectural substrate only.' if _maturity > 20 else 'Early runtime state. Genesis Kit reflects the foundational substrate.'}
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── WHAT'S INSIDE ──────────────────────────────────────────────────────────
    st.markdown("""
    <div class="vault-section">
      <div class="vault-section-title">◈ WHAT'S INSIDE</div>
      <div class="vault-item"><div class="vault-item-icon">⚡</div><div class="vault-item-text"><strong>pump_monitor.py</strong> — Solana pump.fun token discovery substrate</div></div>
      <div class="vault-item"><div class="vault-item-icon">⚡</div><div class="vault-item-text"><strong>ingest_pipeline.py</strong> — Raw DNA ingestion and resolver lane</div></div>
      <div class="vault-item"><div class="vault-item-icon">⚡</div><div class="vault-item-text"><strong>market_intelligence.py</strong> — Two-phase qualifier with DexScreener pricing</div></div>
      <div class="vault-item"><div class="vault-item-icon">⚡</div><div class="vault-item-text"><strong>neural_supervisor.py</strong> — Phase A temporal enforcement + HOT authority</div></div>
      <div class="vault-item"><div class="vault-item-icon">⚡</div><div class="vault-item-text"><strong>execution_engine.py</strong> — Reservation doctrine + paper trade crystallization</div></div>
      <div class="vault-item"><div class="vault-item-icon">⚡</div><div class="vault-item-text"><strong>ws_price_oracle.py</strong> — Tier-aware oracle with HOT_SET and stall detection</div></div>
      <div class="vault-item"><div class="vault-item-icon">⚡</div><div class="vault-item-text"><strong>system_guardian.py</strong> — Auto-healing vitality scanner</div></div>
      <div class="vault-item"><div class="vault-item-icon">◈</div><div class="vault-item-text"><strong>core/schema.py</strong> — Full Phase A schema with momentum substrate</div></div>
      <div class="vault-item"><div class="vault-item-icon">◈</div><div class="vault-item-text"><strong>sovereign_hub.py</strong> — Thermal Pipeline, Edge Arena, Convergence Gate UI</div></div>
      <div class="vault-item"><div class="vault-item-icon">◈</div><div class="vault-item-text"><strong>launch/</strong> — Safe launch/shutdown scripts with slim_db doctrine</div></div>
      <div class="vault-item"><div class="vault-item-icon">◈</div><div class="vault-item-text"><strong>.env.example</strong> — Required keys with no values — fill your own</div></div>
      <div class="vault-item"><div class="vault-item-icon">◈</div><div class="vault-item-text"><strong>requirements.txt</strong> — Exact pinned dependencies</div></div>
    </div>
    """, unsafe_allow_html=True)

    # ── WHAT'S NOT INSIDE ─────────────────────────────────────────────────────
    st.markdown("""
    <div class="vault-section">
      <div class="vault-section-title" style="color:#FF073A;">⚠ WHAT'S NOT INSIDE</div>
      <div class="vault-warning">
        <div class="vault-warning-text">
          ✗ .env — no API keys, no wallet secrets, no live credentials<br>
          ✗ sentinuity_matrix.db — no runtime state, no pattern memory<br>
          ✗ sentinuity_intelligence.db — no learned cognition<br>
          ✗ sovereign_governor.py — IVARIS / Polaris / debate council (family only)<br>
          ✗ intelligence_orchestrator.py — Forge build pipeline (family only)<br>
          ✗ replay_engine.py — Sovereign replay doctrine (family only)<br>
          ✗ Live trading mode — paper mode only, live requires independent configuration<br>
          ✗ Private wallet keys — never included, never will be<br>
          ✗ Pattern memory — your organism learns from scratch
        </div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # ── SAFETY / REALITY CHECK ────────────────────────────────────────────────
    st.markdown("""
    <div class="vault-section">
      <div class="vault-section-title" style="color:#FFB347;">◈ REALITY CHECK</div>
      <div class="vault-item"><div class="vault-item-icon">⚠</div><div class="vault-item-text">This is <strong>experimental research software</strong>. Not financial advice. Not a trading product.</div></div>
      <div class="vault-item"><div class="vault-item-icon">⚠</div><div class="vault-item-text">Paper mode only in this build. Live capital requires your own configuration and risk management.</div></div>
      <div class="vault-item"><div class="vault-item-icon">⚠</div><div class="vault-item-text">Pump.fun tokens are <strong>extremely high risk</strong>. Most reach zero. The organism filters — it does not guarantee wins.</div></div>
      <div class="vault-item"><div class="vault-item-icon">⚠</div><div class="vault-item-text">You will need: Python 3.12+, SQLite, and API keys for OpenAI + Anthropic minimum to run governance.</div></div>
      <div class="vault-item"><div class="vault-item-icon">⚠</div><div class="vault-item-text">The organism is <strong>alive</strong>. It will do things you don't expect. Observe before deploying capital.</div></div>
    </div>
    """, unsafe_allow_html=True)

    # ── CONTRIBUTION RESONANCE ────────────────────────────────────────────────
    st.markdown("""
    <div class="vault-section">
      <div class="vault-section-title" style="color:#9945FF;">◈ CONTRIBUTION RESONANCE</div>
      <div style="font-family:Rajdhani,sans-serif;font-size:0.9rem;color:#888;line-height:1.7;margin-bottom:14px;">
        This kit is free. The organism already runs. Contribution earns resonance — not access.
      </div>
      <div class="vault-item"><div class="vault-item-icon" style="color:#9945FF;">◈</div><div class="vault-item-text"><strong>Run it in paper mode.</strong> Observe. Report what you see.</div></div>
      <div class="vault-item"><div class="vault-item-icon" style="color:#9945FF;">◈</div><div class="vault-item-text"><strong>Find a real bug.</strong> Open a clear reproduction. Earn a resonance mark.</div></div>
      <div class="vault-item"><div class="vault-item-icon" style="color:#9945FF;">◈</div><div class="vault-item-text"><strong>Improve a helper.</strong> The momentum formula is deterministic — prove a better weighting.</div></div>
      <div class="vault-item"><div class="vault-item-icon" style="color:#9945FF;">◈</div><div class="vault-item-text"><strong>Build a new scout.</strong> Telegram scout, wallet scout, X scout — the organism accepts new sensory input.</div></div>
    </div>
    """, unsafe_allow_html=True)

    # ── SETUP PATH ────────────────────────────────────────────────────────────
    st.markdown("""
    <div class="vault-section">
      <div class="vault-section-title" style="color:#14F195;">◈ SETUP PATH</div>
      <div style="font-family:Share Tech Mono,monospace;font-size:0.58rem;color:#555;letter-spacing:2px;margin-bottom:8px;">AFTER EXTRACTING THE VAULT:</div>
    """, unsafe_allow_html=True)

    for cmd in [
        "pip install -r requirements.txt",
        "cp .env.example .env  # fill in your API keys",
        "python -c \"from core.schema import init_db; init_db(); print('DB ready')\"",
        "python forge_genesis_seed.py  # seed Forge projects",
        "launch\\Launch_Sentinuity.bat  # Windows",
        "# then open http://localhost:8501",
    ]:
        st.markdown(f'<div class="vault-cmd">{html.escape(cmd)}</div>', unsafe_allow_html=True)

    st.markdown("</div>", unsafe_allow_html=True)

    # ── SEAL + DOWNLOAD ───────────────────────────────────────────────────────
    st.markdown("""
    <div class="vault-section" style="border-color:rgba(255,215,0,0.25);text-align:center;">
      <div class="vault-section-title" style="justify-content:center;color:#FFD700;">◈ GENESIS VAULT</div>
      <div style="display:flex;justify-content:center;align-items:center;margin:12px 0 4px;">
        <div style="position:relative;width:160px;height:160px;">
          <svg viewBox="0 0 220 220" fill="none" style="position:absolute;inset:0;width:100%;height:100%;animation:vaultRing3 12s linear infinite;">
            <polygon points="110,8 202,58 202,162 110,212 18,162 18,58" stroke="#9945FF" stroke-width="0.5" stroke-dasharray="4 6" fill="none" opacity="0.4"/>
          </svg>
          <svg viewBox="0 0 220 220" fill="none" style="position:absolute;inset:0;width:100%;height:100%;animation:vaultRing1 8s linear infinite;">
            <polygon points="110,22 190,67 190,153 110,198 30,153 30,67" stroke="#14F195" stroke-width="1" stroke-dasharray="8 4" fill="none" opacity="0.7"/>
            <circle cx="110" cy="22" r="3" fill="#14F195"/>
            <circle cx="190" cy="67" r="3" fill="#14F195"/>
            <circle cx="190" cy="153" r="3" fill="#14F195"/>
            <circle cx="110" cy="198" r="3" fill="#14F195"/>
            <circle cx="30" cy="153" r="3" fill="#14F195"/>
            <circle cx="30" cy="67" r="3" fill="#14F195"/>
          </svg>
          <svg viewBox="0 0 220 220" fill="none" style="position:absolute;inset:0;width:100%;height:100%;animation:vaultRing2 5s linear infinite;">
            <polygon points="110,40 178,78 178,142 110,180 42,142 42,78" stroke="#FFD700" stroke-width="0.5" fill="none" opacity="0.5"/>
            <circle cx="110" cy="40" r="2" fill="#FFD700"/>
            <circle cx="178" cy="78" r="2" fill="#FFD700"/>
            <circle cx="178" cy="142" r="2" fill="#FFD700"/>
            <circle cx="110" cy="180" r="2" fill="#FFD700"/>
            <circle cx="42" cy="142" r="2" fill="#FFD700"/>
            <circle cx="42" cy="78" r="2" fill="#FFD700"/>
          </svg>
          <svg viewBox="0 0 220 220" fill="none" style="position:absolute;inset:0;width:100%;height:100%;animation:vaultCorePulse 2s ease-in-out infinite;">
            <polygon points="110,58 154,82 154,138 110,162 66,138 66,82" stroke="#FFD700" stroke-width="1.5" fill="rgba(255,215,0,0.04)"/>
            <text x="110" y="104" text-anchor="middle" font-family="monospace" font-size="9" letter-spacing="3" fill="#FFD700">GENESIS</text>
            <text x="110" y="118" text-anchor="middle" font-family="monospace" font-size="7" letter-spacing="2" fill="#FFD700" opacity="0.6">VAULT</text>
          </svg>
        </div>
      </div>
      <style>
        @keyframes vaultRing1 { to { transform: rotate(360deg); transform-origin: 80px 80px; } }
        @keyframes vaultRing2 { to { transform: rotate(-360deg); transform-origin: 80px 80px; } }
        @keyframes vaultRing3 { to { transform: rotate(360deg); transform-origin: 80px 80px; } }
        @keyframes vaultCorePulse { 0%,100% { opacity:1; transform:scale(1); } 50% { opacity:0.8; transform:scale(1.05); } }
      </style>
      <div style="font-family:Share Tech Mono,monospace;font-size:0.6rem;letter-spacing:3px;color:#FFD70088;margin-bottom:4px;">TIER 1 FREE &nbsp;·&nbsp; TIER 2-4 EARNED</div>
      <div style="font-family:Rajdhani,sans-serif;font-size:0.85rem;color:#666;margin-bottom:8px;">
        The seal opens once. The kit is yours. What you build from here is entirely up to you.
      </div>
    """, unsafe_allow_html=True)

    # Build the ZIP on demand
    _zip_data = None
    _checksum = None
    _zip_size = 0
    _vault_version = "GENESIS-1.0"

    try:
        _root = BASE_DIR
        _buf = io.BytesIO()

        # Security exclusion list — ABSOLUTE
        _EXCLUDE_PATTERNS = {
            # Credentials and databases — never share
            ".env", "sentinuity_matrix.db", "sentinuity_intelligence.db",
            "sentinuity_archive.db", ".env.local", ".env.production",
            # Tier 2+ unlock — learning loop
            "replay_engine.py",
            # Tier 3+ unlock — autonomous governance
            "sovereign_governor.py",
            "intelligence_orchestrator.py",
            "forge_research_bridge.py",
            "sovereign_parameter_engine.py",
            # Tier 4+ unlock — full cognition layer
            "polaris_auxiliary.py",
            # Live money — never in community build
            "live_trading.py",
            "live_wallet_sync.py",
            "set_live_mode.py",
            "kill_live.py",
            # Seeding — family only
            "forge_genesis_seed.py",
            "initiate_intelligence_build.py",
        }
        _EXCLUDE_DIRS = {
            ".git", "__pycache__", "backups", "runtime", "venv", ".venv",
            "node_modules", "*.egg-info", "logs",
        }
        _INCLUDE_DIRS = {
            "services", "core", "launch", "ui",
        }
        _ROOT_FILES = {
            "requirements.txt", "slim_db.py", "diagnose_no_opens.py",
            "diagnose_schema_divergence.py",
        }

        with zipfile.ZipFile(_buf, "w", zipfile.ZIP_DEFLATED) as _zf:
            # Add .env.example (sanitized, no values)
            _zf.writestr(
                "sentinuity-genesis/.env.example",
                "# SENTINUITY GENESIS — fill in your own values\n"
                "# Minimum required: CHAINSTACK_RPC, CHAINSTACK_WSS, ANTHROPIC_API_KEY, OPENAI_API_KEY\n\n"
                "# === SOLANA RPC (Chainstack free tier — chainstack.com) ===\n"
                "CHAINSTACK_RPC=\n"
                "CHAINSTACK_WSS=\n\n"
                "# === AI KEYS ===\n"
                "OPENAI_API_KEY=\n"
                "ANTHROPIC_API_KEY=\n"
                "NVIDIA_NIM_API_KEY=\n\n"
                "# === OPTIONAL ===\n"
                "BRAVE_SEARCH_API_KEY=\n"
                "GITHUB_TOKEN=\n"
                "TELEGRAM_BOT_TOKEN=\n"
                "TELEGRAM_OWNER_ID=\n"
                "TELEGRAM_API_ID=\n"
                "TELEGRAM_API_HASH=\n"
                "TELEGRAM_PHONE=\n"
                "SOLANA_RPC_URL=https://api.mainnet-beta.solana.com\n"
                "PUMP_PROGRAM_ID=6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBymtqrm\n"
            )
            # Add root utility files
            for _fn in _ROOT_FILES:
                _fp = _root / _fn
                if _fp.exists() and _fn not in _EXCLUDE_PATTERNS:
                    _zf.write(_fp, f"sentinuity-genesis/{_fn}")

            # Add service directories (filtered)
            for _dir in _INCLUDE_DIRS:
                _dp = _root / _dir
                if not _dp.exists():
                    continue
                for _f in _dp.rglob("*.py"):
                    _fname = _f.name
                    # Security check
                    if _fname in _EXCLUDE_PATTERNS:
                        continue
                    if any(part in _EXCLUDE_DIRS for part in _f.parts):
                        continue
                    _rel = _f.relative_to(_root)
                    _zf.write(_f, f"sentinuity-genesis/{_rel}")

            # Add README
            _readme = (
                "# SENTINUITY GENESIS — TIER 1 STARTER KIT\n\n"
                f"Version: {_vault_version}\n\n"
                "## What this is\n\n"
                "The trading substrate of an autonomous AI organism built to hunt\n"
                "early pump.fun token launches on Solana.\n\n"
                "This tier includes: discovery, qualification, pricing, execution,\n"
                "freshness maintenance, and the paper trading dashboard.\n"
                "The organism finds launches, qualifies them, and trades them.\n\n"
                "## What you unlock by contributing\n\n"
                "Tier 2 (first contribution): Learning loop — wins/losses feed back in.\n"
                "Tier 3 (sustained contributor): Autonomous governance layer.\n"
                "Tier 4 (core contributor): Full self-directed buildout organism.\n\n"
                "Contributions must move a measurable metric: win rate, throughput, stability.\n"
                "The AIs debate it. Evidence decides. Not vibes.\n\n"
                "## Setup\n\n"
                "1. pip install -r requirements.txt\n"
                "2. cp .env.example .env — fill in Chainstack + Anthropic + OpenAI keys\n"
                "3. python -c \"from core.schema import init_db; init_db()\"\n"
                "4. launch\\Launch_Sentinuity.bat\n"
                "5. http://localhost:8501\n\n"
                "## Keys needed\n\n"
                "Chainstack (free) — Solana RPC + WSS\n"
                "Anthropic (free tier) — AI critic\n"
                "OpenAI — AI architect\n\n"
                "## Rules\n\n"
                "Paper mode only. No real money. No wallet connections.\n"
                "Read the code. Understand it. Make it better.\n\n"
                "The question is not whether it works.\n"
                "The question is whether you can improve it.\n"
            )
            _zf.writestr("sentinuity-genesis/README.md", _readme)

        _zip_bytes = _buf.getvalue()
        _zip_size = len(_zip_bytes)
        _checksum = hashlib.sha256(_zip_bytes).hexdigest()
        _zip_data = _zip_bytes
    except Exception as _ze:
        st.markdown(
            f'<div style="font-family:Share Tech Mono,monospace;font-size:0.6rem;'
            f'color:#FF073A;padding:8px;">Vault seal failed — {html.escape(str(_ze)[:60])}</div>',
            unsafe_allow_html=True
        )

    if _zip_data:
        _size_kb = _zip_size / 1024
        st.markdown(
            f'<div style="font-family:Share Tech Mono,monospace;font-size:0.55rem;'
            f'color:#555;margin:4px 0;">Version: {_vault_version} &nbsp;·&nbsp; '
            f'Size: {_size_kb:.1f}KB &nbsp;·&nbsp; SHA-256 below</div>',
            unsafe_allow_html=True
        )

        if not st.session_state["vault_seal_opened"]:
            # Spinning hexagon animation above download button
            st.markdown("""<div style='text-align:center;margin:12px 0 8px;'>
                <span style='display:inline-block;font-size:2.2rem;
                animation:vaultSpin 3s linear infinite;
                text-shadow:0 0 20px rgba(255,215,0,0.8);'>⬡</span>
                </div>
                <style>
                @keyframes vaultSpin {{
                    0%   {{ transform:rotate(0deg) scale(1); }}
                    50%  {{ transform:rotate(180deg) scale(1.2); }}
                    100% {{ transform:rotate(360deg) scale(1); }}
                }}
                </style>""", unsafe_allow_html=True)
            if st.download_button(
                label="⬡  BREAK THE SEAL — CLAIM GENESIS KIT",
                data=_zip_data,
                file_name=f"sentinuity-genesis-{_vault_version}.zip",
                mime="application/zip",
                key="vault_download_btn",
                use_container_width=True,
            ):
                st.session_state["vault_seal_opened"] = True
        else:
            st.markdown(
                '<div style="text-align:center;padding:12px;font-family:Orbitron,monospace;'
                'font-size:0.8rem;letter-spacing:4px;color:#FFD700;'
                'animation:vaultBreath 2s ease-in-out infinite;">✓ SEAL BROKEN — KIT CLAIMED</div>',
                unsafe_allow_html=True
            )
            # Show checksum + first command after seal
            st.markdown(
                f'<div class="vault-checksum">SHA-256: {_checksum}</div>',
                unsafe_allow_html=True
            )
            st.markdown(
                '<div class="vault-cmd" style="margin-top:10px;">'
                'pip install -r requirements.txt'
                '</div>',
                unsafe_allow_html=True
            )

    st.markdown("</div>", unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)  # close vault-container


def render_living_cortex():
    # No outer cache — _fetch_all_dashboard_data(ttl=5) is the cache layer.
    # Previously wrapped in @st.cache_data(ttl=30) which caused meter bars and
    # main render sections to show data up to 30s stale even when the inner
    # bundle had refreshed. Removed to achieve unified organism-state rendering.
    _prices    = fetch_coingecko_prices()
    _sol_price = _prices.get("SOL", {}).get("price_usd", 0.0)
    _sol_chg   = _prices.get("SOL", {}).get("change_24h", 0.0)
    
    (wallet_df, raw_dna_df, snapshots_df, open_pos_df, executions_df, reviews_df, proposals_df, debate_df, calibration_df, open_count_df, heal_log_df, heartbeat_df, patch_history_df, autopsy_df, cognition_df) = _fetch_all_dashboard_data()
    _MODEL_TAGS = {
        "POLARIS": ("gpt-5.4-mini",     "tag-polaris"),
        "IVARIS":  ("claude-haiku",     "tag-ivaris"),
        "NUGGET":  ("kimi-k2-instruct", "tag-nugget"),
        "ORACLE":  ("brave",            "tag-oracle"),
    }
    live_feed_df = build_live_event_feed(cognition_df, executions_df, open_pos_df, snapshots_df, proposals_df)

    open_count    = int(val(open_count_df,"n",0))
    cash_balance  = float(val(wallet_df,"wallet_balance",0.0))
    start_bal     = float(val(wallet_df,"initial_capital",1000.0))

    # WALLET TRUTH: always show real Phantom wallet balance if key is set
    # (API status bar is rendered once at page level — not duplicated here)
    # In paper mode: shows alongside paper balance for comparison
    # In live mode: replaces paper balance as the equity truth
    # conf_map — read directly, never depend on outer scope
    try:
        import sqlite3 as _sq3c
        _cconn = _sq3c.connect(str(DB_PATH), timeout=2)
        _crows = _cconn.execute("SELECT key, value FROM system_config").fetchall()
        _cconn.close()
        conf_map = {str(r[0]): str(r[1]) for r in _crows}
    except Exception:
        conf_map = {}
    _trading_mode  = str(conf_map.get("TRADING_MODE","paper")).strip().lower()
    _real_wallet_usd = 0.0
    try:
        import os as _os
        _pk = _os.getenv("SOLANA_PRIVATE_KEY","").strip()
        _rpc = _os.getenv("QUICKNODE_RPC") or _os.getenv("SOLANA_RPC_URL","")
        _jkey = _os.getenv("JUPITER_PRICE_API_KEY","").strip()
        if _pk and _rpc:
            from solders.keypair import Keypair as _KP
            import base58 as _b58, requests as _req
            _kp    = _KP.from_bytes(_b58.b58decode(_pk))
            _addr  = str(_kp.pubkey())
            _r     = _req.post(_rpc, json={
                "jsonrpc":"2.0","id":1,"method":"getBalance",
                "params":[_addr,{"commitment":"confirmed"}]
            }, timeout=3)
            _lamps = _r.json()["result"]["value"]
            _sol   = _lamps / 1_000_000_000
            # Get SOL/USD price
            _r2    = _req.get("https://api.jup.ag/price/v3",
                params={"ids":"So11111111111111111111111111111111111111112"},
                headers={"x-api-key":_jkey} if _jkey else {}, timeout=3)
            _susd  = float((_r2.json().get("So11111111111111111111111111111111111111112") or {}).get("usdPrice") or 0)
            if _susd > 0:
                _real_wallet_usd = _sol * _susd
    except Exception:
        pass  # silently fall back — never crash the hub

    if _trading_mode == "live" and _real_wallet_usd > 0:
        cash_balance = _real_wallet_usd  # live mode: real wallet IS the equity
    # paper mode: cash_balance stays as paper balance (real wallet shown separately below)

    roi_pct       = ((cash_balance-start_bal)/max(start_bal,1))*100 if start_bal else 0.0
    total_dna     = int(val(raw_dna_df,"count",0))
    latency_ms    = _measure_live_latency()
    reviews_total = len(reviews_df)
    reviews_wins  = int((reviews_df["win_loss"]=="WIN").sum()) if reviews_total>0 else 0
    win_rate      = round((reviews_wins/max(reviews_total,1))*100,1) if reviews_total>=3 else 0.0
    avg_pnl       = float(pd.to_numeric(reviews_df["realized_pnl_usd"],errors="coerce").fillna(0).mean()) if reviews_total>0 else 0.0
    sl_count      = int((reviews_df["exit_category"]=="SL").sum()) if reviews_total>0 else 0
    conf_map      = {str(r["key"]):str(r["value"]) for _,r in calibration_df.iterrows()}
    halt_active   = conf_map.get("DRAWDOWN_HALT_ACTIVE","0")=="1"
    drawdown_pct  = float(conf_map.get("DRAWDOWN_ACCUMULATED_PCT","0.0"))

    dom_state,dom_narrative,dom_color = get_dominant_state(halt_active,latency_ms,open_count,len(heal_log_df),win_rate)

    # Build live terminal command ticker for under the SENTINUITY heading
    # Pulls recent cognition log entries and formats as coloured terminal strings
    try:
        _ticker_rows = query_db("""
            SELECT stage, message FROM cognition_log
            WHERE rowid > (SELECT MAX(rowid) - 100 FROM cognition_log)
            ORDER BY rowid DESC LIMIT 12
        """)
        _ticker_cmds = []
        _stage_colors = {
            "SUPERVISOR": "#8EF9FF", "EXECUTOR": "#14F195", "MARKET_INTEL": "#9945FF",
            "GUARDIAN": "#FFB347", "POLARIS": "#8EF9FF", "IVARIS": "#FF6B35",
            "ORACLE": "#14F195", "PUMP_MONITOR": "#9945FF", "SYSTEM": "#FFD700",
        }
        if not _ticker_rows.empty:
            for _, _tr in _ticker_rows.iterrows():
                _stg = str(_tr.get('stage','SYS')).upper()[:12]
                _msg = str(_tr.get('message',''))[:60].replace("'","\\'").replace('"','\\"')
                _col = _stage_colors.get(_stg, "#8EF9FF")
                _ticker_cmds.append(
                    f"<span style='color:{_col};'>▶ [{_stg}]</span>"
                    f"<span style='color:#666;'> — </span>"
                    f"<span style='color:#aaa;'>{_msg}</span>"
                )
        if not _ticker_cmds:
            _ticker_cmds = [
                "<span style='color:#9945FF;'>▶ [SUBSTRATE]</span><span style='color:#666;'> — </span><span style='color:#aaa;'>cognition substrate initialising...</span>",
                "<span style='color:#14F195;'>▶ [ORACLE]</span><span style='color:#666;'> — </span><span style='color:#aaa;'>price feeds nominal</span>",
            ]
        import json as _tjson
        _cmd_ticker_js = _tjson.dumps(_ticker_cmds)
    except Exception:
        _cmd_ticker_js = '["<span style=\\"color:#9945FF;\\">▶ [SENTINUITY]</span><span style=\\"color:#aaa;\\"> — substrate active</span>"]'
    st.markdown(build_dynamic_css(dom_color),unsafe_allow_html=True)

    # ALPHA SPORE TRIGGER LOGIC
    if not heal_log_df.empty:
        _latest_cog = heal_log_df.iloc[0]
        if _latest_cog["stage"] == "SYMBIOTIC":
            _sig = str(_latest_cog["timestamp"]) + str(_latest_cog["message"])
            if st.session_state.get("last_spore_sig") != _sig:
                st.session_state["last_spore_sig"] = _sig
                st.markdown("""
                <div style="text-align:center; padding:40px 20px; border-radius:20px; background:rgba(153,69,255,0.15); margin:20px 0; border: 1px solid #FFD700;">
                    <h1 class="spore-bloom" style="font-size:3.2rem; margin:0;">🌟 ALPHA SPORE EXTRACTED</h1>
                    <p style="font-size:1.4rem; color:#FFD700; margin:10px 0 0 0;">
                        Node added to sentient web singularity layer<br>
                        <span style="color:#C19A6B;">Symbiosis Achieved • Mycelium strengthened</span>
                    </p>
                </div>
                """, unsafe_allow_html=True)

    _ph_l, _ph_r = st.columns([5, 1])
    with _ph_r:
        render_phantom_connect()
        # Genesis Vault toggle — sits below Phantom connect
        if "genesis_vault_open" not in st.session_state:
            st.session_state["genesis_vault_open"] = False
        if st.button("◈ GENESIS VAULT", key="genesis_vault_btn",
                     help="Enter the Genesis Vault — community starter kit",
                     use_container_width=True):
            st.session_state["genesis_vault_open"] = not st.session_state["genesis_vault_open"]
            st.rerun()

        # Layout ideas moved to Genesis Vault README — not shown in sidebar

    st.markdown(f"""<div style="text-align:center;padding:10px 0;width:100%;">
        <h1 style="margin:0;font-size:clamp(2.2rem,9vw,4rem);letter-spacing:clamp(6px,2vw,14px);white-space:nowrap;background:linear-gradient(90deg,#9945FF 0%,#14F195 20%,#FFD700 40%,#8EF9FF 60%,#FF6B35 80%,#9945FF 100%);background-size:300% 100%;-webkit-background-clip:text;-webkit-text-fill-color:transparent;animation:chromaShift 4s linear infinite;">SENTINUITY</h1>
        <style>@keyframes chromaShift{{0%{{background-position:0% 50%}}100%{{background-position:300% 50%}}}}</style>
        <p style="margin-top:8px;margin-bottom:4px;color:#8EF9FF;font-size:1rem;letter-spacing:2px;font-style:italic;display:block;width:100%;text-align:center;{{'animation:flicker 0.8s infinite;' if dom_state=='HEALING' else ''}}">"{dom_narrative}"</p>
        <div id="cmd-ticker" style="font-family:'Share Tech Mono',monospace;font-size:0.62rem;letter-spacing:1.5px;text-align:center;height:18px;overflow:hidden;margin-top:2px;margin-bottom:2px;"></div>
        <script>
        (function(){{
            var cmds = {_cmd_ticker_js};
            var i=0, el=document.getElementById('cmd-ticker');
            if(!el) return;
            function tick(){{
                if(!cmds||!cmds.length)return;
                el.innerHTML = cmds[i % cmds.length];
                i++;
                setTimeout(tick, 2200);
            }}
            tick();
        }})();
        </script>
        <style>@keyframes flicker{{0%,100%{{opacity:1}}50%{{opacity:0.92}}75%{{opacity:0.97}}}}</style>
        <div style="font-family:Share Tech Mono,monospace;font-size:0.52rem;letter-spacing:3px;color:{C_RED};opacity:0.7;text-align:center;width:100%;">
            ⚠ EXPERIMENTAL SOVEREIGN SUBSTRATE — QUANTITATIVE RESEARCH ONLY — NOT FINANCIAL ADVICE
        </div>
    </div>""", unsafe_allow_html=True)

    # ── GENESIS VAULT — separate mode, live cockpit untouched ─────────────────
    if st.session_state.get("genesis_vault_open", False):
        render_genesis_vault()
        st.stop()

    # ── LAYER 1: TRUTH STRIP — SEE ─────────────────────────────────────────
    _stale_pos = False
    if not open_pos_df.empty and "mtm_age_seconds" in open_pos_df.columns:
        _stale_pos = bool((open_pos_df["mtm_age_seconds"].dropna() > 120).any())
    _truth_compromised = latency_ms > 1000 or _stale_pos
    # Use shared health truth — HUD matches Vitality table
    try:
        _shared_h = _get_service_health()
        _hud_ok_loc, _hud_col_loc, _hud_lbl_loc = _hud_health_state(_shared_h)
    except Exception:
        _hud_ok_loc, _hud_col_loc, _hud_lbl_loc = (not _truth_compromised), C_GREEN, "✓ ORGANISM SYNCED — ALL FEEDS FRESH"
    # Price truth + service health combined
    if _truth_compromised:
        _siren_class = "truth-siren"; _siren_color = C_RED
        _siren_label = "⚠ PRICE TRUTH COMPROMISED — STALE DATA DETECTED"
    elif not _hud_ok_loc:
        _siren_class = "truth-siren"; _siren_color = "#FF073A"
        _siren_label = _hud_lbl_loc
    else:
        _siren_class = "truth-synced"; _siren_color = C_GREEN
        _siren_label = _hud_lbl_loc
    # 6-NODE COUNCIL STATUS — checks heartbeat table, no API calls
    # Council strip rendered by render_api_status_bar() above — no duplicate here
    # HUD truth strip (price + service health combined)
    st.markdown(
        f"<div class='{_siren_class}' style='display:flex;justify-content:space-between;"
        f"align-items:center;flex-wrap:wrap;gap:6px;border-radius:10px;padding:8px 18px;"
        f"margin-bottom:12px;border:1px solid {_siren_color};"
        f"font-family:Share Tech Mono,monospace;font-size:0.68rem;letter-spacing:1.5px;'>"
        f"<span style='color:{_siren_color};font-weight:700;'>{_siren_label}</span>"
        f"<span style='color:{C_CYAN};font-size:0.65rem;'>DB {latency_ms:.0f}ms</span>"
        f"<span style='color:{C_GOLD if halt_active else dom_color};font-size:0.65rem;'>"
        f"EXEC: {'SUSPENDED' if halt_active else 'ARMED'}</span></div>",
        unsafe_allow_html=True,
    )

    # ── Tax reserve stat ─────────────────────────────────────────────────────
    _tax_reserved = 0.0
    _tax_rate     = 0.20
    try:
        from services.tax_allocator import get_tax_state as _get_tax
        _ts = _get_tax()
        _tax_reserved = _ts.get("total_reserved", 0.0)
        _tax_rate     = _ts.get("rate", 0.20)
    except Exception:
        pass
    _effective_capital = max(0.0, cash_balance - _tax_reserved)

    col1, col2, col3, col4 = st.columns(4)
    with col1: st.metric("DNA NODES", f"{total_dna:,}", "RAW SIGNALS INGESTED")
    with col2: st.metric(
        f"AUTONOMIC VITAL — {'LIVE 🔴' if _trading_mode=='live' else 'PAPER'} SOL {f'({_real_wallet_usd:.0f})' if _real_wallet_usd>0 and _trading_mode=='paper' else ''}",
        f"${cash_balance:,.2f}",
        f"{roi_pct:+.1f}% | eff ${_effective_capital:.2f} | SOL ${_sol_price:.2f} ({_sol_chg:+.1f}%)"
    )
    with col3: st.metric("WIN RATE", f"{win_rate}%", f"{reviews_total} REVIEWS - SL: {sl_count}")
    with col4: st.metric(
        f"TAX RESERVED ({int(_tax_rate*100)}%)",
        f"${_tax_reserved:.2f}",
        f"eff capital ${_effective_capital:.2f}"
    )

    # ── SOVEREIGN FLOW ENGINE ─────────────────────────────────────────────────
    render_sovereign_flow_engine(
        snapshots_df=snapshots_df,
        open_pos_df=open_pos_df,
        reviews_df=reviews_df,
        raw_dna_df=raw_dna_df,
        executions_df=executions_df,
    )

    if _is_focus_locked(proposals_df):
        st.markdown(f"""<div style="margin:8px 0 16px;padding:12px 18px;background:rgba(255,179,71,0.08);border:2px solid {C_IVY};border-radius:10px;font-family:'Share Tech Mono',monospace;font-size:0.72rem;letter-spacing:2px;">
            <span style="color:{C_IVY};font-weight:700;letter-spacing:3px;">⚡ SINGULAR FOCUS LOCK ACTIVE</span>
            <div style="color:#FFF;opacity:0.7;margin-top:3px;font-size:0.65rem;">SYSTEM_REPAIR in progress — stability prioritised over expansion</div>
        </div>""", unsafe_allow_html=True)

    # Nexus header — only shown when enabled, and only as a small label
    if _heavy_visuals_enabled():
      st.markdown("<div style='font-family:Orbitron,sans-serif;font-size:0.6rem;letter-spacing:3px;color:rgba(153,69,255,0.5);margin:4px 0 6px;'>◈ MYCELIAL NEXUS</div>", unsafe_allow_html=True)
    _nexus_nodes = [{"id": "CORE", "name": "SOVEREIGN CORE", "val": 35, "color": dom_color}]
    _nexus_links = []
    _active_mints = set(open_pos_df["token_name"].dropna().unique()) if not open_pos_df.empty else set()
    for _ni, _nr in snapshots_df.head(80).iterrows():
        _tok = str(_nr.get("token_name", f"SIG_{_ni}"))[:12]
        try: _conf = float(_nr.get("mint_confidence") or 0) * 100 if pd.notna(_nr.get("mint_confidence")) else 0.0
        except: _conf = 0.0
        _st = str(_nr.get("candidate_state", "pending")).lower()
        if _tok in _active_mints:      _nc, _nv = C_GOLD, 24
        elif _st == "latched":         _nc, _nv = dom_color, 18
        elif _st == "vetoed":          _nc, _nv = C_RED, 8
        else:                          _nc, _nv = C_PURPLE, max(6, int(_conf/8))
        _nid = f"node_{_ni}"
        _nexus_nodes.append({"id": _nid, "name": _tok, "val": float(_nv), "color": _nc})
        _nexus_links.append({"source": _nid, "target": "CORE", "width": 3.8 if _nc==C_GOLD else 2.2 if _nc==dom_color else 0.7})
    if _heavy_visuals_enabled():
        mycelial_nexus(nexus_data={"nodes": _nexus_nodes[:30], "links": _nexus_links[:30], "latency": latency_ms}, height=220)
    else:
        st.markdown(f"""<div style='padding:12px 16px;border:1px solid rgba(153,69,255,0.2);border-radius:8px;font-family:Share Tech Mono,monospace;font-size:0.7rem;color:rgba(153,69,255,0.5);letter-spacing:2px;'>
        MYCELIAL NEXUS — DISABLED (UI_HEAVY_VISUALS_ENABLED=false)<br>
        <span style='color:#888;'>Nodes tracked: {len(_nexus_nodes)} | Set UI_HEAVY_VISUALS_ENABLED=true to enable</span>
        </div>""", unsafe_allow_html=True)



    # ── SOVEREIGN OS DATA ─────────────────────────────────────────────────────
    _tp_now = time.time()
    _tp_agents = {
        "POLARIS":  {"icon": "🧠", "color": "#8EF9FF", "role": "Sovereign Architect"},
        "IVARIS":   {"icon": "⚖️",  "color": "#FF073A", "role": "Logic Auditor"},
        "NUGGET":   {"icon": "⚡",  "color": "#FFD700", "role": "Signal Hunter"},
        "ORACLE":   {"icon": "🔭",  "color": "#9945FF", "role": "Market Scout"},
        "GUARDIAN": {"icon": "🛡",  "color": "#14F195", "role": "System Watchdog"},
    }
    _tp_tools = [
        {"id": "oracle_lens",      "icon": "🔭", "name": "Oracle Lens",      "purpose": "Market scanning"},
        {"id": "dna_extractor",    "icon": "🧬", "name": "DNA Extractor",    "purpose": "Token structure"},
        {"id": "ivaris_gate",      "icon": "⚖️",  "name": "IVARIS Gate",      "purpose": "Veto & audit"},
        {"id": "mycelial_memory",  "icon": "🍄", "name": "Mycelial Memory",  "purpose": "Prior lessons"},
        {"id": "execution_relay",  "icon": "⚡", "name": "Execution Relay",  "purpose": "Signal routing"},
        {"id": "risk_shell",       "icon": "🛡", "name": "Risk Shell",       "purpose": "Sizing/stops"},
        {"id": "freshness_beacon", "icon": "📡", "name": "Freshness Beacon", "purpose": "Signal age"},
        {"id": "backtest_crucible","icon": "🧪", "name": "Backtest Crucible","purpose": "Rule testing"},
        {"id": "patch_forge",      "icon": "🧰", "name": "Patch Forge",      "purpose": "Build/repair"},
        {"id": "doctrine_scroll",  "icon": "📜", "name": "Doctrine Scroll",  "purpose": "Council rules"},
    ]
    _tp_tool_states = {}
    _tp_agent_tasks = {}
    _tp_activity = []
    try:
        _tp_conn = sqlite3.connect(str(DB_PATH), timeout=2)
        _tp_conn.row_factory = sqlite3.Row
        _tp_cog = _tp_conn.execute("""
            SELECT stage, speaker, message, token, timestamp
            FROM cognition_log ORDER BY timestamp DESC LIMIT 60
        """).fetchall()
        _tp_props = _tp_conn.execute("""
            SELECT proposal_type, status, created_at FROM polaris_proposals
            WHERE status IN ('debating','open','HITL_REQUIRED','forge_complete')
            ORDER BY created_at DESC LIMIT 5
        """).fetchall()
        _tp_conn.close()
        _STAGE_TOOL_MAP = {
            "QUALIFIER": ("oracle_lens","ORACLE"), "INGEST": ("dna_extractor","ORACLE"),
            "SUPERVISOR": ("freshness_beacon","NUGGET"), "LATCH": ("execution_relay","NUGGET"),
            "EXECUTOR": ("execution_relay","NUGGET"), "ENTRY": ("execution_relay","NUGGET"),
            "EXIT": ("risk_shell","GUARDIAN"), "DRAWDOWN": ("risk_shell","GUARDIAN"),
            "DEBATE": ("ivaris_gate","IVARIS"), "IVARIS": ("ivaris_gate","IVARIS"),
            "POLARIS": ("mycelial_memory","POLARIS"), "FORGE": ("patch_forge","POLARIS"),
            "FORGE_GATE": ("patch_forge","POLARIS"), "REPLAY": ("backtest_crucible","POLARIS"),
            "GOVERNOR": ("doctrine_scroll","POLARIS"),
        }
        _seen = set()
        for _row in _tp_cog:
            _stage = str(_row["stage"] or "").upper()
            _age = _tp_now - float(_row["timestamp"] or _tp_now)
            for _key, (_tid, _ag) in _STAGE_TOOL_MAP.items():
                if _key in _stage and _tid not in _seen:
                    _tp_tool_states[_tid] = {
                        "status": "ACTIVE" if _age < 30 else "BUILDING" if _age < 120 else "DECAYING",
                        "agent": _ag, "last": str(_row["message"] or "")[:50], "age": _age,
                    }
                    _seen.add(_tid)
        for _p in _tp_props:
            _ps = str(_p["status"] or "")
            if _ps in ("debating","open"):
                _tp_tool_states["doctrine_scroll"] = {"status":"BUILDING","agent":"POLARIS","last":str(_p["proposal_type"] or ""),"age":0}
            if _ps == "forge_complete":
                _tp_tool_states["patch_forge"] = {"status":"ACTIVE","agent":"POLARIS","last":"Awaiting seal","age":0}
        _FLAVOR = {
            "LATCH": lambda r: f"⚡ {r['speaker'] or 'NUGGET'} latched {r['token'] or 'signal'} → relay",
            "ENTRY": lambda r: f"🚀 {r['token'] or 'mint'} deployed",
            "EXIT":  lambda r: f"🏁 {r['token'] or 'pos'} closed",
            "QUALIFIER": lambda r: f"🔭 scanning {r['token'] or 'mint'}",
            "INGEST": lambda r: f"🧬 DNA decode {r['token'] or 'token'}",
            "DEBATE": lambda r: f"⚖️ IVARIS gate reviewing",
            "FORGE":  lambda r: f"🧰 patch forge active",
            "HEALTH": lambda r: f"🛡 risk shell pulse",
            "POLARIS": lambda r: f"🍄 {str(r['message'] or '')[:35]}",
        }
        for _row in _tp_cog[:10]:
            _stage = str(_row["stage"] or "").upper()
            _age = int(_tp_now - float(_row["timestamp"] or _tp_now))
            _heat = "hot" if _age < 30 else "warm" if _age < 120 else "cold"
            _txt = None
            for _k, _fn in _FLAVOR.items():
                if _k in _stage:
                    _txt = _fn(_row)
                    break
            if not _txt:
                _txt = f"◈ {str(_row['speaker'] or '')} — {str(_row['message'] or '')[:40]}"
            _tp_activity.append({"text": _txt, "heat": _heat, "age": _age})
        # Agent tasks
        _AGENT_FLAVOR = {
            "POLARIS": [("FORGE","🍄 mycelial memory pass"),("DEBATE","📜 doctrine update"),("RESEARCH","🧪 stress-testing")],
            "IVARIS":  [("DEBATE","⚖️ auditing proposal"),("REJECT","⚖️ vetoing signal")],
            "NUGGET":  [("LATCH","⚡ latching signal"),("QUALIFY","📡 freshness check")],
            "ORACLE":  [("QUALIFY","🔭 oracle scan"),("INGEST","🧬 DNA decode")],
            "GUARDIAN":[("HEALTH","🛡 risk shell check"),("HEAL","🛡 healing node")],
        }
        for _row in _tp_cog:
            _spk = str(_row["speaker"] or "").upper()
            _stage = str(_row["stage"] or "").upper()
            _age = _tp_now - float(_row["timestamp"] or _tp_now)
            if _spk in _AGENT_FLAVOR and _spk not in _tp_agent_tasks:
                for _trig, _flav in _AGENT_FLAVOR[_spk]:
                    if _trig in _stage:
                        _tp_agent_tasks[_spk] = {"task": _flav, "age": _age,
                            "tool": next((t["icon"] for t in _tp_tools if _tp_tool_states.get(t["id"],{}).get("agent")==_spk), "")}
                        break
    except Exception:
        pass
    # Baselines — always fire
    if "oracle_lens" not in _tp_tool_states:
        _tp_tool_states["oracle_lens"] = {"status":"ACTIVE","agent":"ORACLE","last":"scanning substrate","age":60}
    if "freshness_beacon" not in _tp_tool_states:
        _tp_tool_states["freshness_beacon"] = {"status":"ACTIVE","agent":"ORACLE","last":"signal age gate","age":60}
    if "risk_shell" not in _tp_tool_states:
        _tp_tool_states["risk_shell"] = {"status":"ACTIVE","agent":"GUARDIAN","last":"exposure check","age":60}
    if "execution_relay" not in _tp_tool_states:
        _tp_tool_states["execution_relay"] = {"status":"ACTIVE","agent":"NUGGET","last":"relay armed","age":60}

    # ══════════════════════════════════════════════════════════════════════════
    # SOVEREIGN PULSE — computed from real state, not decorative values
    # ══════════════════════════════════════════════════════════════════════════
    try:
        _sv_conn = sqlite3.connect(str(DB_PATH), timeout=2)
        _sv_conn.row_factory = sqlite3.Row
        # Exception count from cognition_log last 5 mins
        _sv_exc = (_sv_conn.execute(
            "SELECT COUNT(*) FROM cognition_log WHERE message LIKE '%Exception%' OR message LIKE '%ERROR%' AND timestamp > ?",
            (_tp_now - 300,)
        ).fetchone() or [0])[0]
        # Websocket / provider connected
        _sv_ws_row = _sv_conn.execute(
            "SELECT last_pulse FROM system_heartbeat WHERE service_name='pump_monitor' ORDER BY last_pulse DESC LIMIT 1"
        ).fetchone()
        _sv_ws_connected = bool(_sv_ws_row and (_tp_now - float(_sv_ws_row[0] or 0)) < 120)
        # All agents pinging in last 30s
        _sv_hb_rows = _sv_conn.execute(
            "SELECT service_name, last_pulse FROM system_heartbeat ORDER BY last_pulse DESC"
        ).fetchall()
        _sv_svc_ages = {str(r["service_name"]): _tp_now - float(r["last_pulse"] or 0) for r in _sv_hb_rows}
        _sv_core_alive = all(_sv_svc_ages.get(s, 9999) < 120 for s in list(CORE_SERVICES.keys())[:5] if s in _sv_svc_ages)
        _sv_all_ping = _sv_core_alive
        # Average confidence last 5 mins from cognition_log
        _sv_conf_rows = _sv_conn.execute(
            "SELECT confidence FROM cognition_log WHERE confidence IS NOT NULL AND timestamp > ?",
            (_tp_now - 300,)
        ).fetchall()
        _sv_avg_conf = (sum(float(r[0]) for r in _sv_conf_rows) / len(_sv_conf_rows)) if _sv_conf_rows else 0.5
        _sv_conn.close()
    except Exception:
        _sv_exc = 1; _sv_ws_connected = False; _sv_all_ping = False; _sv_avg_conf = 0.5

    # Component scores
    _sv_vitality     = 30 if _sv_exc == 0 else 10
    # Open positions or active executions → EXECUTING; debating → EVALUATING; blocked → BLOCKED
    _sv_open_pos     = int(val(open_count_df, "n", 0))
    _sv_has_debating = not proposals_df.empty and "status" in proposals_df.columns and \
                       bool((proposals_df["status"].isin(["debating","open","pending"])).any())
    _sv_has_blocked  = bool(latency_ms > 2000 or not _sv_ws_connected or (halt_active if "halt_active" in dir() else False))
    if _sv_open_pos > 0:
        _sv_lattice_state = "EXECUTING"
    elif _sv_has_blocked:
        _sv_lattice_state = "BLOCKED"
    elif _sv_has_debating:
        _sv_lattice_state = "EVALUATING"
    else:
        _sv_lattice_state = "READY"
    _sv_exec_score   = 25 if _sv_lattice_state in ("READY","EVALUATING","EXECUTING") else 0
    _sv_sig_score    = min(20, int(_sv_avg_conf * 20))
    _sv_prov_score   = 15 if _sv_ws_connected else 0
    _sv_agent_score  = 10 if _sv_all_ping else 0
    _sv_pulse        = _sv_vitality + _sv_exec_score + _sv_sig_score + _sv_prov_score + _sv_agent_score
    _sv_pulse_col    = "#14F195" if _sv_pulse >= 80 else "#FFD700" if _sv_pulse >= 50 else "#FF073A"
    _sv_pulse_label  = "SOVEREIGN" if _sv_pulse >= 80 else "UNSTABLE" if _sv_pulse >= 50 else "DEGRADED"
    # Lattice visual config
    _sv_lattice_cfg  = {
        "READY":      ("#FFD700", "latticeBreath", "◈ READY",      "solid gold glow — execution armed"),
        "EVALUATING": ("#FFB347", "latticeScan",   "◉ EVALUATING", "signal qualification in progress"),
        "BLOCKED":    ("#FF073A", "latticeAlert",  "⛔ BLOCKED",    "provider down or execution halted"),
        "EXECUTING":  ("#14F195", "latticeExec",   "⚡ EXECUTING",  "live order in flight"),
    }
    _sv_l_col, _sv_l_anim, _sv_l_txt, _sv_l_desc = _sv_lattice_cfg.get(_sv_lattice_state, _sv_lattice_cfg["READY"])

    # Most recent exit reason → Tool Shed card mapping
    _sv_exit_map = {
        "HARD_STOP_LOSS": ("risk_shell",   "#FF073A", "🛡 TAIL RISK CONTAINED"),
        "TRAILING_STOP":  ("execution_relay","#14F195","⚡ RUNNER HARVESTED"),
        "STAGNANT":       ("freshness_beacon","#888",  "📡 STAGNANT EXIT"),
        "TIME_CUT":       ("freshness_beacon","#888",  "📡 STAGNANT EXIT"),
        "MAX_HOLD":       ("doctrine_scroll","#FFB347","📜 MAX HOLD CLEARED"),
        "STOP_LOSS":      ("risk_shell",   "#FF073A", "🛡 CONTROLLED LOSS"),
        "TAKE_PROFIT":    ("execution_relay","#FFD700","⚡ PROFIT SECURED"),
    }
    _sv_last_exit = ""
    _sv_exit_tool = ""; _sv_exit_col = ""; _sv_exit_label = ""
    try:
        _sv_ex_conn = sqlite3.connect(str(DB_PATH), timeout=2)
        _sv_ex_conn.row_factory = sqlite3.Row
        _sv_ex_row = _sv_ex_conn.execute(
            "SELECT exit_reason FROM paper_positions WHERE status='CLOSED' ORDER BY closed_at DESC LIMIT 1"
        ).fetchone()
        _sv_ex_conn.close()
        if _sv_ex_row:
            _sv_last_exit = str(_sv_ex_row["exit_reason"] or "").upper()
            for _k, (_tid, _ec, _el) in _sv_exit_map.items():
                if _k in _sv_last_exit:
                    _sv_exit_tool = _tid; _sv_exit_col = _ec; _sv_exit_label = _el
                    # Activate that tool card with exit state
                    _tp_tool_states[_tid] = {
                        "status": "ALERT" if _ec == "#FF073A" else "ACTIVE",
                        "agent": _tp_tool_states.get(_tid, {}).get("agent", "GUARDIAN"),
                        "last": _el,
                        "age": 0,
                    }
                    break
    except Exception:
        pass

    # ── SOVEREIGN PULSE BAR — above columns ──────────────────────────────────
    _sv_bars = "".join(
        f"<div style='width:{max(2,int(_sv_pulse/5))}%;height:4px;background:{_sv_pulse_col};"
        f"border-radius:2px;box-shadow:0 0 6px {_sv_pulse_col};'></div>"
        for _ in range(1)
    )
    _sv_components = [
        ("SYS", _sv_vitality, 30, "#8EF9FF"),
        ("EXEC", _sv_exec_score, 25, _sv_l_col),
        ("SIG", _sv_sig_score, 20, "#9945FF"),
        ("PROV", _sv_prov_score, 15, "#FFD700"),
        ("SYNC", _sv_agent_score, 10, "#14F195"),
    ]
    _sv_comp_html = "".join(
        f"<span style='font-size:0.48rem;color:{cc};letter-spacing:1px;margin-right:8px;'>"
        f"{lbl} {sc}/{mx}</span>"
        for lbl, sc, mx, cc in _sv_components
    )
    st.markdown(
        f"<div style='display:flex;align-items:center;gap:10px;padding:8px 14px;"
        f"background:rgba(5,2,16,0.6);border:1px solid {_sv_pulse_col}44;"
        f"border-radius:10px;margin-bottom:10px;flex-wrap:wrap;'>"
        f"<div style='font-family:Orbitron,sans-serif;font-size:0.65rem;letter-spacing:3px;color:{_sv_pulse_col};white-space:nowrap;'>"
        f"⬡ SOVEREIGN PULSE</div>"
        f"<div style='flex:1;min-width:60px;background:rgba(255,255,255,0.06);border-radius:4px;height:8px;overflow:hidden;'>"
        f"<div style='width:{_sv_pulse}%;height:100%;background:{_sv_pulse_col};"
        f"box-shadow:0 0 8px {_sv_pulse_col};border-radius:4px;transition:width 0.5s ease;'></div></div>"
        f"<div style='font-family:Share Tech Mono,monospace;font-size:0.72rem;color:{_sv_pulse_col};font-weight:700;white-space:nowrap;'>"
        f"{_sv_pulse} / 100 — {_sv_pulse_label}</div>"
        f"<div style='width:100%;margin-top:2px;'>{_sv_comp_html}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # ── TRADE LIFECYCLE FLOW STRIP ────────────────────────────────────────────
    _sv_stages = [
        ("SIGNAL",    "#9945FF"),
        ("QUALIFY",   "#8EF9FF"),
        ("APPROVED",  "#FFD700"),
        ("EXECUTING", "#14F195"),
        ("MANAGING",  "#0095EB"),
        ("EXITED",    "#555"),
    ]
    _sv_failure = {
        "BLOCKED":  "#FF073A",
        "STALE":    "#FFB347",
        "REJECTED": "#444",
    }
    # Determine active stage from live data
    if _sv_open_pos > 0:
        _sv_active = "MANAGING" if _tp_tool_states.get("risk_shell",{}).get("age",9999) < 60 else "EXECUTING"
    elif _sv_has_debating:
        _sv_active = "QUALIFY"
    elif _sv_last_exit:
        _sv_active = "EXITED"
    elif not proposals_df.empty and "status" in proposals_df.columns and \
         bool((proposals_df["status"] == "approved").any()):
        _sv_active = "APPROVED"
    else:
        _sv_active = "SIGNAL"
    _sv_stage_html = "<div style='display:flex;align-items:center;gap:0;flex-wrap:nowrap;overflow-x:auto;padding:6px 0;margin-bottom:10px;'>"
    for _i, (_sname, _scol) in enumerate(_sv_stages):
        _is_active = _sname == _sv_active
        _is_past   = _sv_stages.index((_sv_active, dict(_sv_stages).get(_sv_active, "#555"))) > _i if _sv_active in dict(_sv_stages) else False
        _s_opacity = "1.0" if _is_active else ("0.55" if _is_past else "0.2")
        _s_border  = f"border:2px solid {_scol};box-shadow:0 0 8px {_scol}88;" if _is_active else f"border:1px solid {_scol}44;"
        _s_bg      = f"background:{_scol}22;" if _is_active else ""
        _sv_stage_html += (
            f"<div style='{_s_border}{_s_bg}padding:4px 10px;border-radius:6px;"
            f"font-family:Share Tech Mono,monospace;font-size:0.52rem;letter-spacing:1.5px;"
            f"color:{_scol};opacity:{_s_opacity};white-space:nowrap;'>{_sname}</div>"
        )
        if _i < len(_sv_stages) - 1:
            _sv_stage_html += f"<div style='color:{_scol}44;font-size:0.6rem;padding:0 3px;'>→</div>"
    # Failure state overlay if blocked
    if _sv_lattice_state == "BLOCKED":
        _sv_stage_html += (
            f"<div style='margin-left:10px;padding:4px 10px;border:2px solid #FF073A;"
            f"border-radius:6px;font-family:Share Tech Mono,monospace;font-size:0.52rem;"
            f"letter-spacing:1.5px;color:#FF073A;background:rgba(255,7,58,0.12);"
            f"box-shadow:0 0 8px #FF073A88;white-space:nowrap;'>⛔ BLOCKED</div>"
        )
    _sv_stage_html += "</div>"
    st.markdown(_sv_stage_html, unsafe_allow_html=True)

    _agent_col, main_col, lattice_col = st.columns([1, 5, 2], gap="small")

    with _agent_col:
        st.markdown('<div class="tp-panel" style="height:100%;"><div class="tp-header">◈ AGENTS</div>', unsafe_allow_html=True)
        # Batch confidence lookup — 1 query for all agents instead of 5
        _agent_conf_map = {}
        try:
            _ac_conn = sqlite3.connect(str(DB_PATH), timeout=1)
            _ac_rows = _ac_conn.execute("""
                SELECT speaker, MAX(confidence) as conf
                FROM cognition_log
                WHERE speaker IN ('POLARIS','IVARIS','NUGGET','ORACLE','GUARDIAN')
                  AND confidence IS NOT NULL
                  AND timestamp > ?
                GROUP BY speaker
            """, (_tp_now - 600,)).fetchall()
            _ac_conn.close()
            _agent_conf_map = {r[0]: float(r[1]) for r in _ac_rows if r[1]}
        except Exception:
            pass
        for _aname, _ainfo in _tp_agents.items():
            _atask = _tp_agent_tasks.get(_aname, {})
            _a_age = _atask.get("age", 9999)
            _a_state = "active" if _a_age < 60 else "debating" if _a_age < 300 else "idle"
            _a_tool_icon = _atask.get("tool", "")
            _a_task_text = _atask.get("task", "awaiting signal...")
            _tool_cls = "equipped" if _a_tool_icon else ""
            _tool_div = f'<div class="tp-agent-tool">{_a_tool_icon}</div>' if _a_tool_icon else ''
            # Status badge
            _a_badge_col = _ainfo["color"] if _a_state == "active" else ("#FFB347" if _a_state == "debating" else "#444")
            _a_badge_txt = "● ACTIVE" if _a_state == "active" else ("◉ BUSY" if _a_state == "debating" else "○ IDLE")
            # Age display
            _a_age_disp = f"{int(_a_age)}s ago" if _a_age < 9999 else "—"
            # Confidence from last cognition row for this agent
            _a_conf_str = ""
            try:
                _a_conf_val = _agent_conf_map.get(_aname)
                if _a_conf_val is not None:
                    _a_conf_str = f"<div style='font-size:0.38rem;color:{_ainfo['color']}88;margin-top:1px;'>conf {_a_conf_val:.2f}</div>"
            except Exception:
                pass
            st.markdown(
                f'<div class="tp-agent {_a_state}">' +
                f'<div class="tp-agent-icon {_tool_cls}">{_ainfo["icon"]}</div>' +
                f'<div style="flex:1;min-width:0;">' +
                f'<div style="display:flex;align-items:center;gap:4px;">' +
                f'<div class="tp-agent-name" style="color:{_ainfo["color"]};">{_aname}</div>' +
                f'<span style="font-size:0.36rem;color:{_a_badge_col};letter-spacing:1px;white-space:nowrap;">{_a_badge_txt}</span>' +
                f'</div>' +
                f'<div class="tp-agent-task">{_a_task_text}</div>' +
                f'<div style="font-size:0.38rem;color:#555;margin-top:1px;">{_a_age_disp}</div>' +
                _a_conf_str +
                f'</div>' +
                _tool_div + '</div>',
                unsafe_allow_html=True
            )
        st.markdown('</div>', unsafe_allow_html=True)

    with lattice_col:
        # ── GOLDEN LATTICE STATE BADGE ────────────────────────────────────────
        _sv_lat_anims = {
            "READY":      "latticeBreath 4s ease-in-out infinite",
            "EVALUATING": "latticeScan 1.5s ease-in-out infinite",
            "BLOCKED":    "latticeAlert 0.8s ease-in-out infinite",
            "EXECUTING":  "latticeExec 0.6s ease-in-out infinite",
        }
        st.markdown(
            f"<style>"
            f"@keyframes latticeScan{{0%,100%{{opacity:0.6;box-shadow:0 0 6px {_sv_l_col}44}}50%{{opacity:1;box-shadow:0 0 20px {_sv_l_col}88}}}}"
            f"@keyframes latticeAlert{{0%,100%{{opacity:0.5;border-color:{_sv_l_col}55}}50%{{opacity:1;border-color:{_sv_l_col};box-shadow:0 0 16px {_sv_l_col}99}}}}"
            f"@keyframes latticeExec{{0%,100%{{box-shadow:0 0 10px {_sv_l_col}66}}50%{{box-shadow:0 0 28px {_sv_l_col},0 0 50px {_sv_l_col}44}}}}"
            f"</style>"
            f"<div style='padding:8px 10px;border:2px solid {_sv_l_col}88;"
            f"border-radius:10px;background:{_sv_l_col}11;margin-bottom:8px;"
            + "animation:" + _sv_lat_anims.get(_sv_lattice_state, "latticeBreath 4s ease-in-out infinite") + ";'>"
            + f"<div style='font-family:Orbitron,sans-serif;font-size:0.55rem;letter-spacing:3px;"
            f"color:{_sv_l_col};margin-bottom:3px;'>{_sv_l_txt}</div>"
            f"<div style='font-family:Share Tech Mono,monospace;font-size:0.45rem;color:{_sv_l_col}99;'>{_sv_l_desc}</div>"
            f"</div>",
            unsafe_allow_html=True,
        )
        _forge_rows = []
        try:
            with sqlite3.connect(str(DB_PATH), timeout=3) as _lc:
                _forge_rows = _lc.execute("SELECT id, proposal_type, suggested_action, unified_diff, forge_narrative, forge_checksum FROM polaris_proposals WHERE status IN ('forge_complete','HITL_REQUIRED','nugget_escalated') ORDER BY created_at DESC LIMIT 3").fetchall()
        except Exception: pass

        if _forge_rows:
            st.markdown(f"""<div class="golden-lattice">
                <div style="color:#FFD700;font-family:'Share Tech Mono',monospace;font-size:0.72rem;letter-spacing:3px;margin-bottom:14px;">✦ OPERATOR GATE — AWAITING SEAL</div>
            """, unsafe_allow_html=True)
            for _fr in _forge_rows:
                _fp_id, _fp_type, _fp_action, _fp_diff, _fp_narr, _fp_checksum = _fr[0], str(_fr[1] or ''), html.escape(str(_fr[2] or '')[:200]), html.escape(str(_fr[3] or '')[:600]), html.escape(str(_fr[4] or '')), str(_fr[5] or f"FORGE-{_fr[0]}")
                _narr_html = f'<div style="color:#FFD700;font-style:italic;font-size:0.75rem;margin-bottom:8px;">{_fp_narr}</div>' if _fp_narr else ''
                st.markdown(
                    '<div class="golden-lattice-card">' +
                    f'<div style="color:#FFD700;font-size:0.65rem;letter-spacing:2px;margin-bottom:6px;">{_fp_type}</div>' +
                    _narr_html +
                    f'<div style="color:#FFF;font-size:0.7rem;margin-bottom:8px;">{_fp_action}</div>' +
                    f'<div style="color:#FFD70066;font-size:0.6rem;margin-bottom:10px;font-family:Share Tech Mono,monospace;">{_fp_checksum}</div>' +
                    '</div>',
                    unsafe_allow_html=True
                )

                with st.form(key=f"seal_form_{_fp_id}", clear_on_submit=True):
                    _seal_input = st.text_input("SEAL CODE", type="password", label_visibility="collapsed", placeholder="ENTER SEAL CODE TO INTEGRATE")
                    _lc1, _lc2 = st.columns(2)
                    with _lc1: _seal_btn = st.form_submit_button("⚡ SEAL & INTEGRATE", type="primary", use_container_width=True)
                    with _lc2: _deny_btn = st.form_submit_button("✕ DISSOLVE", use_container_width=True)
                if _seal_btn:
                    try:
                        _raw = _seal_input.strip()
                        # Silently reject anything that isn't exactly 4 digits
                        if not (_raw.isdigit() and len(_raw) == 4):
                            st.error("SEAL REJECTED")
                        else:
                            with sqlite3.connect(str(DB_PATH), timeout=8) as _sc:
                                _scfg = _sc.execute("SELECT value FROM system_config WHERE key='OPERATOR_SEAL_CODE' LIMIT 1").fetchone()
                                _expected = str(_scfg[0]).strip() if _scfg else ""
                                if _raw == _expected and _expected != "":
                                    _sc.execute("UPDATE polaris_proposals SET status='approved' WHERE id=?", (_fp_id,))
                                    _sc.commit()
                                    st.session_state[f"evolution_{_fp_id}"] = True
                                    st.rerun()
                                else:
                                    st.error("SEAL REJECTED")
                    except Exception as _se: st.error(f"INTEGRATION FAILED: {_se}")
                if _deny_btn:
                    try:
                        with sqlite3.connect(str(DB_PATH), timeout=8) as _dc:
                            _dc.execute("UPDATE polaris_proposals SET status='rejected' WHERE id=?", (_fp_id,))
                            _dc.commit()
                        st.rerun()
                    except Exception as _de: st.error(f"DISSOLVE FAILED: {_de}")

                if st.session_state.get(f"evolution_{_fp_id}"):
                    st.markdown("""<div class="evolution-burst" id="mycelial-burst"></div><script>setTimeout(function() {var el = document.getElementById('mycelial-burst'); if (el) el.remove(); }, 3000);</script>""", unsafe_allow_html=True)
                    del st.session_state[f"evolution_{_fp_id}"]
            st.markdown("</div>", unsafe_allow_html=True)
        else:
            st.markdown(f"""<div style="border:1px solid #FFD70033;border-radius:16px;padding:20px;background:rgba(5,10,10,0.2);text-align:center;margin-top:10px;">
                <div style="color:#FFD70044;font-family:'Share Tech Mono',monospace;font-size:0.65rem;letter-spacing:3px;margin-bottom:8px;">GOLDEN LATTICE</div>
                <div style="color:#FFD70033;font-size:0.7rem;font-style:italic;">Awaiting Ascension...<br><span style="font-size:0.6rem;opacity:0.6;">Forge completes when System 1 reaches consensus</span></div>
            </div>""", unsafe_allow_html=True)
            # Oracle budget: Brave limit shown as flashing red dot in status bar only
            # No text here — keeps debate chamber at full width

        # ── TOOL SHED — bottom of right column ──────────────────────────────
        st.markdown('<div class="tp-panel" style="margin-top:10px;"><div class="tp-header">🧰 TOOL SHED</div>', unsafe_allow_html=True)
        for _tool in _tp_tools:
            _tstate = _tp_tool_states.get(_tool["id"], {})
            _tstatus = _tstate.get("status", "IDLE")
            _tagent = _tstate.get("agent", "—")
            _tlast = _tstate.get("last", "")
            _tcard_cls = _tstatus.lower()
            _agent_div = f'<div class="tp-tool-agent" style="color:rgba(20,241,149,0.6);">▸ {_tagent}</div>' if _tstatus != 'IDLE' else ''
            _last_div = f'<div class="tp-tool-last">{_tlast[:40]}</div>' if _tlast else ''
            st.markdown(
                f'<div class="tp-tool-card {_tcard_cls}">' +
                f'<div class="tp-tool-top">' +
                f'<span class="tp-tool-icon">{_tool["icon"]}</span>' +
                f'<span class="tp-tool-name" style="font-size:0.48rem;">{_tool["name"]}</span>' +
                f'<span class="tp-tool-status {_tstatus}" style="font-size:0.42rem;">{_tstatus}</span>' +
                '</div>' +
                _agent_div + _last_div + '</div>',
                unsafe_allow_html=True
            )
        st.markdown('</div>', unsafe_allow_html=True)

    with main_col:
        # ── Mycelial Activity Feed — slim strip above sanctum ──────────────
        if _tp_activity:
            st.markdown('<div style="margin-bottom:8px;">', unsafe_allow_html=True)
            for _act in _tp_activity[:5]:
                st.markdown(
                    f'<div class="tp-activity-item {_act["heat"]}" style="font-size:0.5rem;padding:3px 6px;margin-bottom:2px;">' +
                    _act["text"] +
                    f'<span style="color:rgba(200,216,232,0.2);font-size:0.42rem;float:right;">{_act["age"]}s</span></div>',
                    unsafe_allow_html=True
                )
            st.markdown('</div>', unsafe_allow_html=True)

        st.markdown("### THE SOVEREIGN SANCTUM")
        cortex_container = st.container()
        with cortex_container:

            # ── SECTION 1: SYNTHETIC 3D CORTEX (glassbox — preserved) ───────────
            if not _heavy_visuals_enabled():
                st.markdown("""<div style='padding:16px;border:1px solid rgba(153,69,255,0.2);border-radius:8px;font-family:Share Tech Mono,monospace;font-size:0.7rem;color:rgba(153,69,255,0.5);letter-spacing:2px;text-align:center;margin-bottom:16px;'>
                SYNTHETIC 3D CORTEX — DISABLED<br><span style='color:#888;'>UI_HEAVY_VISUALS_ENABLED=false · Set to true to enable canvas</span>
                </div>""", unsafe_allow_html=True)
            elif not live_feed_df.empty:
                try:
                    _state_json = write_organism_state(dom_state, dom_color, live_feed_df, autopsy_df)
                    components.html(build_cognitive_canopy(_state_json), height=500, scrolling=False)
                except Exception as _canopy_err: st.error(f"CORTEX RENDER ERROR: {_canopy_err}")
            else:
                st.markdown("<div style='text-align:center;color:#888;padding:40px;margin-bottom:16px;'>CORTEX DORMANT — NO FEED DATA</div>", unsafe_allow_html=True)

            # ── SOVEREIGN SANCTUM V1.5 ───────────────────────────────────────────────
            try:
                from ui.sovereign_chamber_v1_5 import render_chamber_v1_5 as _rcv15
                _rcv15(show_submission_form=True)
            except ImportError:
                st.markdown("<div style='color:#555;font-size:0.6rem;padding:8px;'>Copy ui/sovereign_chamber_v1_5.py to load Sanctum V1.5</div>", unsafe_allow_html=True)
            except Exception as _sv15e:
                st.markdown(f"<div style='color:#555;font-size:0.6rem;padding:8px;'>SANCTUM V1.5 ERR: {_sv15e}</div>", unsafe_allow_html=True)

                        # ── SECTION 2: LIVE DEBATE CHAMBER ──────────────────────────────────
            st.markdown(f"<div style='font-family:Orbitron,sans-serif;font-size:0.7rem;letter-spacing:4px;color:#9945FF;margin-bottom:8px;'>⚔ LIVE DEBATE CHAMBER</div>", unsafe_allow_html=True)
            _debate_html = "<div style='height:480px;overflow-y:auto;padding:16px;font-family:\"Share Tech Mono\",monospace;background:rgba(5,2,16,0.4);border-radius:12px;border:1px solid rgba(153,69,255,0.15);margin-bottom:16px;'>"
            if not debate_df.empty:
                for idx, row in debate_df.iterrows():
                    spk = str(row.get('speaker', '')).upper()
                    _raw_verdict = str(row.get('verdict_text', '') or '')
                    _action_codes = ('RESEARCH_FIRST INITIATION', 'AUDIT_FIRST INITIATION',
                                     'DESIGN_FIRST INITIATION', 'current_state', 'oracle_evidence',
                                     'loop_detected', 'final_rejection', 'loop_detection')
                    if any(code in _raw_verdict for code in _action_codes) or len(_raw_verdict) < 30:
                        try:
                            import json as _jmod
                            _cj = row.get('content_json', '')
                            if _cj:
                                _cjd = _jmod.loads(str(_cj)) if isinstance(_cj, str) else _cj
                                _raw_verdict = (
                                    _cjd.get('polaris_summary') or
                                    _cjd.get('research_summary') or
                                    _cjd.get('proposal_summary') or
                                    _cjd.get('verdict') or
                                    _cjd.get('summary') or
                                    _cjd.get('rebuttal_summary') or
                                    _cjd.get('current_state_summary') or
                                    _raw_verdict
                                )
                        except Exception:
                            pass
                        _code_map = {
                            'RESEARCH_FIRST INITIATION': 'Beginning research phase — gathering evidence before debate',
                            'AUDIT_FIRST INITIATION': 'Beginning audit phase — reviewing existing data',
                            'DESIGN_FIRST INITIATION': 'Beginning design phase — architecting the solution',
                            'loop_detected': 'Debate loop detected — proposal has been seen too many times',
                            'final_rejection': 'Proposal rejected — could not reach consensus',
                            'per-proposal cap exceeded': 'This proposal has been debated too many times without resolution',
                        }
                        for code, readable in _code_map.items():
                            if code in _raw_verdict:
                                _raw_verdict = readable
                                break
                    msg = purify_links(_raw_verdict)
                    ts = _fmt_clock(row.get('logged_at', 0))
                    think = str(row.get('thinking_state', ''))
                    verd = str(row.get('verdict_type', ''))
                    icon = AGENT_EMOJIS.get(spk, "⬜")
                    col  = (C_CYAN if spk == "POLARIS" else C_IVY if spk == "IVARIS" else C_NUGGET if spk == "NUGGET" else "#14F195" if spk == "ORACLE" else C_IVY)
                    badge = ""
                    if think: badge += f"<span style='background:rgba(153,69,255,0.2);padding:2px 6px;border-radius:4px;font-size:0.6rem;margin-right:6px;'>{_thematic_label(think)}</span>"
                    if verd:
                        v_col = C_GREEN if "CONSENSUS" in verd.upper() or "APPROVED" in verd.upper() or "HARMONIC" in verd.upper() else C_RED
                        badge += f"<span style='background:{v_col}33;color:{v_col};border:1px solid {v_col};padding:2px 6px;border-radius:4px;font-size:0.6rem;'>{_thematic_label(verd)}</span>"
                    _prop_context = ''
                    try:
                        _pid = int(row.get('proposal_id', 0) or 0)
                        if _pid and not proposals_df.empty and 'id' in proposals_df.columns:
                            _prop_rows = proposals_df[proposals_df['id'] == _pid]
                            if not _prop_rows.empty:
                                _prop_text = str(_prop_rows.iloc[0].get('proposal_text', '') or '')
                                if _prop_text:
                                    _prop_context = _prop_text[:120].replace('\n', ' ').strip()
                                    if len(_prop_text) > 120: _prop_context += '...'
                    except Exception:
                        _prop_context = ''
                    _align = "left" if spk == "POLARIS" else "right"
                    _bg = "rgba(142,249,255,0.05)" if spk == "POLARIS" else "rgba(255,179,71,0.05)"
                    _border = f"border-left:3px solid {col};" if spk == "POLARIS" else f"border-right:3px solid {col};"
                    _grok_narr = html.escape(str(row.get('grok_narrative', '') or ''))
                    name_class = "next-up" if idx == 0 else ""
                    text_class = ""  # replaced by holo-char injection below
                    # ── Holographic typewriter: wrap each char in a timed span ──
                    def _holo_wrap(text: str, base_delay_ms: int, color: str) -> str:
                        """Wrap plain text in per-character holo-char spans with staggered delay."""
                        import html as _html_mod
                        out = []
                        char_delay = base_delay_ms
                        for ch in text[:300]:  # cap at 300 chars for perf
                            safe_ch = _html_mod.escape(ch) if ch not in (' ', '\n') else ch
                            out.append(
                                f"<span class='holo-char' style='animation-delay:{char_delay}ms;"
                                f"color:{color};'>{safe_ch}</span>"
                            )
                            char_delay += 28 if ch not in (' ', ',', '.') else 12
                        if idx == 0:
                            out.append(f"<span class='holo-caret' style='color:{col};'></span>")
                        return "".join(out)
                    _holo_msg = _holo_wrap(msg, idx * 120, col)
                    # Thinking dots shown between entries (not on oldest)
                    _thinking_html = ""
                    if 0 < idx < 4:
                        _thinking_html = (
                            f"<div class='holo-thinking' style='animation-delay:{idx*80}ms;'>"
                            f"<div class='holo-dot'></div><div class='holo-dot'></div>"
                            f"<div class='holo-dot'></div>"
                            f"<span style='font-size:0.55rem;color:#9945FF99;margin-left:6px;"
                            f"letter-spacing:1px;'>COGNITION ACTIVE</span></div>"
                        )
                    is_mastery = think == 'golden_mastery'
                    is_consensus = "consensus" in think.lower() or "harmonic" in think.lower() or "consensus" in verd.lower()
                    is_patch = any(kw in msg.lower() for kw in ("applied patch", "file edited", "file created", "integrated", "patch absorbed"))
                    _msg_class = f"arena-msg-{spk.lower()}" if spk in ("POLARIS","IVARIS","ORACLE","NUGGET") else ""
                    if _grok_narr:
                        _rich_body = f"<div style='color:{col};font-family:Rajdhani,sans-serif;font-size:0.95rem;font-style:italic;margin-bottom:6px;opacity:0.92;word-wrap:break-word;overflow-wrap:break-word;'>{_grok_narr}</div><div class='clinical-text {_msg_class}' style='word-wrap:break-word;overflow-wrap:break-word;white-space:normal;'>{_holo_msg}</div>"
                    else:
                        _rich_body = f"<div class='{_msg_class}' style='font-size:0.9rem;word-wrap:break-word;overflow-wrap:break-word;white-space:normal;'>{_holo_msg}</div>"
                    if spk == "ORACLE":
                        _oq  = html.escape(str(row.get('oracle_query', '') or ''))
                        _oc  = str(row.get('oracle_confirmed', '') or '')
                        _cc  = "#14F195" if str(_oc).lower() == "true" else ("#FF073A" if str(_oc).lower() == "false" else "#888")
                        _cl  = "CONFIRMED" if str(_oc).lower() == "true" else ("NOT CONFIRMED" if str(_oc).lower() == "false" else "INCONCLUSIVE")
                        _rich_body = f"<div style='color:#14F195;font-size:0.75rem;letter-spacing:1px;margin-bottom:4px;'>SEARCH QUERY</div><div style='color:#FFF;font-family:Share Tech Mono,monospace;font-size:0.8rem;background:rgba(20,241,149,0.07);padding:6px 10px;border-radius:6px;margin-bottom:8px;'>{_oq or '—'}</div><div style='display:inline-block;padding:2px 10px;border-radius:4px;font-size:0.7rem;font-weight:700;background:{_cc}22;color:{_cc};border:1px solid {_cc};margin-bottom:8px;'>{_cl}</div>"
                    elif spk == "NUGGET":
                        _nw = str(row.get('nugget_winner', '') or '—')
                        _nr = html.escape(str(row.get('nugget_reason', '') or '—'))
                        _nc = str(row.get('nugget_confidence', '') or '')
                        _nn = str(row.get('nugget_next', '') or '—')
                        _nw_col = "#14F195" if _nw == "POLARIS" else ("#FF073A" if _nw == "IVARIS" else "#888")
                        try: _nc_f = f"{float(_nc):.2f}"
                        except Exception: _nc_f = _nc or "—"
                        _rich_body = f"<div style='display:flex;gap:10px;flex-wrap:wrap;margin-bottom:8px;'><span style='background:{_nw_col}22;color:{_nw_col};border:1px solid {_nw_col};padding:2px 10px;border-radius:4px;font-size:0.7rem;font-weight:700;'>WINNER: {_nw}</span><span style='background:rgba(153,69,255,0.15);color:#9945FF;border:1px solid #9945FF55;padding:2px 10px;border-radius:4px;font-size:0.7rem;'>CONF: {_nc_f}</span><span style='background:rgba(255,255,255,0.05);color:#ccc;border:1px solid #ffffff22;padding:2px 10px;border-radius:4px;font-size:0.7rem;'>NEXT: {_nn}</span></div><div style='color:#FFF;font-family:Rajdhani,sans-serif;font-size:0.9rem;' class='{text_class}'>{_nr}</div>"
                    mastery_class = "golden-masterpiece" if is_mastery else ""
                    arena_class = "arena-consensus" if is_consensus else ("arena-patch" if is_patch else "")
                    _badge_div = f'<div style="margin-bottom:6px;">{badge}</div>' if badge else ''
                    _mtag_info = _MODEL_TAGS.get(spk, ('', ''))
                    _mtag_leading = ' leading' if (is_consensus or (think == 'critiquing' and idx == 0)) else ''
                    _mtag_html = f'<span class="model-tag {_mtag_info[1]}{_mtag_leading}" title="{_mtag_info[0]}">{_mtag_info[0]}</span>' if _mtag_info[0] else ''
                    _debate_html += _thinking_html
                    _debate_html += f"<div class='unfold {mastery_class} {arena_class}' style='margin-bottom:12px;padding:10px;{_border}background:{_bg};border-radius:8px;text-align:{_align};word-wrap:break-word;overflow-wrap:break-word;overflow:hidden;'><div style='margin-bottom:4px;'><span class='{name_class} agent-{spk.lower()}' style='color:{col};font-weight:bold;'>{icon} {spk}{_mtag_html}</span> <span style='color:#888;font-size:0.7rem;'>{ts}</span></div>{_badge_div}{_rich_body}</div>"
            else:
                _debate_html += "<div style='color:#888;text-align:center;padding:40px;font-family:Share Tech Mono,monospace;font-size:.7rem;letter-spacing:2px;'>// SUBSTRATE SILENT — AWAITING COGNITIVE IGNITION //</div>"
            _debate_html += "</div>"
            st.markdown(_debate_html, unsafe_allow_html=True)

            # ── GOLDEN LATTICE — proposals awaiting operator action ───────────────
            # Glassbox: dimmed code preview shows what the lattice is evaluating
            try:
                _lattice_proposals = query_db("""
                    SELECT id, proposal_type, proposal_domain, proposal_text,
                           status, created_at, project_key
                    FROM polaris_proposals
                    WHERE status IN ('approved','nugget_escalated','HITL_REQUIRED','pending_replay')
                    ORDER BY created_at DESC LIMIT 8
                """)
                if not _lattice_proposals.empty:
                    st.markdown(
                        "<div style='font-family:Orbitron,sans-serif;font-size:0.7rem;"
                        "letter-spacing:4px;color:#FFD700;margin-bottom:8px;margin-top:16px;'>"
                        "◈ GOLDEN LATTICE — AWAITING SOVEREIGN ABSORPTION</div>",
                        unsafe_allow_html=True
                    )
                    _lattice_html = (
                        "<div style='padding:12px;background:rgba(255,215,0,0.03);"
                        "border:1px solid rgba(255,215,0,0.15);border-radius:12px;"
                        "margin-bottom:16px;'>"
                    )
                    for _, _lrow in _lattice_proposals.iterrows():
                        _lstatus = str(_lrow.get('status',''))
                        _lstat_col = "#14F195" if _lstatus == "approved" else "#FFD700" if "HITL" in _lstatus else "#9945FF"
                        _ltext = str(_lrow.get('proposal_text','') or '')[:120].replace('\n',' ')
                        _ltype = str(_lrow.get('proposal_type','') or '')
                        _ldomain = str(_lrow.get('proposal_domain','') or '')
                        _lid = _lrow.get('id','')
                        # Dimmed code preview — shows what the proposal contains
                        _code_preview = str(_lrow.get('proposal_text','') or '')[:300].replace('\n',' | ')
                        _lattice_html += (
                            f"<div style='margin-bottom:10px;padding:8px 12px;"
                            f"border-left:3px solid {_lstat_col};"
                            f"background:rgba(255,255,255,0.02);border-radius:0 6px 6px 0;'>"
                            f"<div style='display:flex;justify-content:space-between;margin-bottom:4px;'>"
                            f"<span style='font-family:Share Tech Mono,monospace;font-size:0.65rem;"
                            f"color:{_lstat_col};letter-spacing:1px;'>#{_lid} {_ltype} [{_ldomain}]</span>"
                            f"<span style='font-size:0.6rem;padding:1px 6px;border-radius:3px;"
                            f"background:{_lstat_col}22;color:{_lstat_col};border:1px solid {_lstat_col}44;'>"
                            f"{_lstatus}</span></div>"
                            f"<div style='font-family:Share Tech Mono,monospace;font-size:0.6rem;"
                            f"color:#555;letter-spacing:0.5px;padding:6px 8px;"
                            f"background:rgba(0,0,0,0.3);border-radius:4px;margin-top:4px;"
                            f"border:1px solid rgba(255,255,255,0.05);word-break:break-all;'>"
                            f"// COGNITION SURFACE — {_code_preview}...</div>"
                            f"</div>"
                        )
                    _lattice_html += "</div>"
                    st.markdown(_lattice_html, unsafe_allow_html=True)
            except Exception:
                pass

            # ── SECTION 3: RAW STRINGS & TRADE SIGNALS ──────────────────────────
            st.markdown(f"<div style='font-family:Orbitron,sans-serif;font-size:0.7rem;letter-spacing:4px;color:#8EF9FF;margin-bottom:8px;'>⚡ RAW STRINGS & TRADE SIGNALS</div>", unsafe_allow_html=True)
            _raw_html = "<div style='height:480px;overflow-y:auto;padding:16px;font-family:\"Share Tech Mono\",monospace;background:rgba(5,2,16,0.4);border-radius:12px;border:1px solid rgba(142,249,255,0.15);'>"
            if not live_feed_df.empty:
                for _, _frow in live_feed_df.iterrows():
                    _stg = str(_frow.get('stage', 'SYS')).upper()
                    _tok = html.escape(str(_frow.get('token', '')) or 'SYS')
                    _msg = purify_links(str(_frow.get('message', '')))
                    _ts  = str(_frow.get('timestamp', ''))[-8:][:5]
                    _display_stg = "⚡ AXON" if _stg == "EXECUTOR" else ("🕸️ RHIZA" if _stg in ("REPLAY","REPLAY_ENGINE") else _stg)
                    _stg_col = {"EXECUTOR": "#14F195", "AXON": "#14F195", "RHIZA": "#9945FF", "SUPERVISOR": "#8EF9FF", "POLARIS": "#9945FF", "SYSTEM": "#FFB347", "DEBATE": "#9945FF", "REPLAY": "#9945FF"}.get(_stg, "#8EF9FF")
                    if "latched" in _msg.lower(): _stg_col = "#FFD700"
                    elif "vetoed" in _msg.lower() or "rejected" in _msg.lower(): _stg_col = "#FF073A"
                    elif "approved" in _msg.lower() or "passed" in _msg.lower(): _stg_col = "#14F195"
                    _raw_html += f"<div style='margin-bottom:10px;padding:10px 12px;border-left:3px solid {_stg_col};background:rgba(255,255,255,0.02);border-radius:0 6px 6px 0;'><span style='color:{_stg_col};font-weight:bold;letter-spacing:1px;'>{_display_stg}</span><span style='float:right;color:#FFD700;font-size:.75rem;'>{_ts}</span><br><span style='color:#9945FF;'>{_tok}</span><span style='color:#888;'> — </span><span style='color:#FFF;'>{_msg}</span></div>"
            else:
                _raw_html += "<div style='color:#888;text-align:center;padding:40px;'>// RAW STREAM SILENT //</div>"
            _raw_html += "</div>"
            st.markdown(_raw_html, unsafe_allow_html=True)

    # ── LINEAR CORTEX SCROLL — all panels top-down, no cramped columns ─────────
    if True:  # preserves indentation level
        # ── COGNITION LOG ─────────────────────────────────────────────────────
        st.markdown("<div style='margin-top:10px;padding:12px 14px;border:1px solid rgba(153,69,255,0.25);border-radius:10px;background:rgba(5,2,16,0.5);overflow:hidden;'>",unsafe_allow_html=True)
        st.markdown(f'<div style="font-family:Orbitron,sans-serif;font-size:0.7rem;letter-spacing:4px;color:{C_CYAN};margin-bottom:8px;">🧠 COGNITION LOG</div>',unsafe_allow_html=True)
        if not heal_log_df.empty:
            for _,row in heal_log_df.iterrows():
                stage=str(row.get("stage","")).upper(); msg=html.escape(str(row.get("message",""))[:100]); ts=str(row.get("timestamp",""))[-8:][:5]
                _scol2={"HEALTH":C_RED,"EXECUTOR":C_GREEN,"AXON":C_GREEN,"SUPERVISOR":C_CYAN,"DEBATE":C_PURPLE,"SYSTEM":C_GOLD,"POLARIS":C_CYAN,"REPLAY":C_PURPLE}.get(stage,C_GREEN)
                _ds="⚡ AXON" if stage=="EXECUTOR" else "🕸️ RHIZA" if stage in ("REPLAY","REPLAY_ENGINE") else stage
                st.markdown(f'<div style="margin-bottom:5px;font-size:.62rem;border-left:2px solid {_scol2};padding-left:8px;"><span style="color:{_scol2};font-weight:bold;">{_ds}</span> <span style="color:#555;">{ts}</span><br><span style="color:#CCC;">{msg}</span></div>',unsafe_allow_html=True)
        else:
            st.markdown('<div style="color:#666;font-size:.62rem;padding:8px;text-align:center;">// ORGANISM AT REST //</div>',unsafe_allow_html=True)
        st.markdown("</div>",unsafe_allow_html=True)

        # Vitality/gates/substrate/conviction moved to page level (after motor output)

    
    if _query_errors:
        import datetime as _dtq
        st.markdown(f"<div style='margin:8px 0;padding:10px 14px;background:rgba(255,7,58,0.08);border:1px solid rgba(255,7,58,0.4);border-radius:8px;font-family:Share Tech Mono,monospace;font-size:.62rem;letter-spacing:1px;'><span style='color:{C_RED};letter-spacing:2px;'>DB QUERY ERRORS — PANELS MAY BE BLANK DUE TO FAILURE NOT EMPTY DATA</span>", unsafe_allow_html=True)
        for _ets, _emsg, _esql in _query_errors[-5:]:
            try: _etime = _dtq.datetime.fromtimestamp(_ets).strftime("%H:%M:%S")
            except Exception: _etime = "?"
            st.markdown(f"<div style='color:rgba(255,7,58,0.8);margin-top:4px;'><span style='color:#888;'>{_etime}</span> <span style='color:{C_RED};'>{html.escape(_emsg)}</span></div>", unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

# ══════════════════════════════════════════════════════════════════════════════
# PAGE LAYOUT — COCKPIT → CORTEX   (Grand Vision Aligned)
#
# ZONE 1 COCKPIT  — what's happening with my money right now (full width, fast)
# ZONE 2 CORTEX   — how is the organism evolving (2-col, research-heavy)
# ══════════════════════════════════════════════════════════════════════════════

@fragment(run_every=60)
def _render_cortex_slow():
    render_living_cortex()

# ══════════════════════════════════════════════════════════════════════════════
# GRAND VISION NARRATIVE FLOW
# Identity/HUD → Vitals/Engine → Cortex/Mind → Ascension →
# Diagnostics/Gates → Substrate → Conviction → Pressure → Execution → Motor → Memory
# ══════════════════════════════════════════════════════════════════════════════

# 1. IDENTITY CROWN + 2. HUD / API STATUS BAR (shared health truth)
render_api_status_bar()

# 3. VITALS + FLOW ENGINE + CORTEX ARENA (3D gated) + COGNITION + VITALITY
# All of the above live inside render_living_cortex() for data coherence
# (dom_state, dom_narrative, and all DFs computed once and shared)
_render_cortex_slow()

# 4. HOLOGRAPHIC ASCENSION MAP — journey to sovereignty, directly under arena
render_holographic_ascension_map()

# 5. LOGIC GATES: Signal Latch + Matrix Filtration + Same-Eyes
# (these are inside render_living_cortex already — no duplicate call needed)

# 6. INTELLIGENCE SUBSTRATE (inside render_living_cortex — no duplicate)

# 7. ORGANISM CONVICTION + PRESSURE CORE — full width, dominant
render_organism_pressure_core()

# 8. EXECUTION LANES — per-trade equilibrium meters, full width
render_unified_execution_lanes()

# 9. MOTOR OUTPUT — glass tank, sticky neon header, no void
st.markdown(
    "<div style='height:1px;margin:2px 0;background:linear-gradient(90deg,"
    "transparent,rgba(153,69,255,0.5),rgba(20,241,149,0.3),transparent);'></div>",
    unsafe_allow_html=True,
)
render_motor_output_command_deck()

# ── POST-EXECUTION DIAGNOSTICS — vitality, gates, substrate, doctrine ─────────
# Grand Vision order: pressure → execution → motor → THEN diagnostics
st.markdown(
    "<div style='margin:20px 0 8px;height:1px;background:linear-gradient(90deg,"
    "transparent,rgba(153,69,255,0.3),transparent);'></div>",
    unsafe_allow_html=True
)

# ── SELF-HEALING VITALITY SCANNER ─────────────────────────────────────
st.markdown("<div style='margin-top:10px;border-radius:10px;border:1px solid rgba(153,69,255,0.25);overflow:hidden;'>",unsafe_allow_html=True)
# Fetch heartbeat directly — the module-level heartbeat_df is an empty fallback
# and is NOT populated by render_living_cortex (local scope). Read fresh here.
_vt_heartbeat_df = pd.DataFrame()
try:
    _vt_conn = sqlite3.connect(str(DB_PATH), timeout=3.0)
    _vt_heartbeat_df = pd.read_sql_query(
        "SELECT service_name, status, last_pulse, COALESCE(note,'') AS note FROM system_heartbeat ORDER BY service_name ASC",
        _vt_conn
    )
    _vt_conn.close()
except Exception:
    pass
if not _vt_heartbeat_df.empty:
    _hb_now2=time.time()
    _svcd=[]
    for _,row in _vt_heartbeat_df.iterrows():
        svc2=str(row.get("service_name","")).upper(); st2=str(row.get("status",""))
        try: p2=float(row.get("last_pulse") or 0)
        except: p2=0.0
        a2=int(_hb_now2-p2) if p2>0 else None
        if p2<=0: sk,as2="zombie","dead"
        elif a2>420: sk,as2="stale",f"{a2}s"
        elif a2>120: sk,as2="warn",f"{a2}s"
        elif st2 in ("ERROR","DEAD"): sk,as2="error",f"{a2}s"
        else: sk,as2="alive",f"{a2}s"
        _svcd.append({"n":svc2,"s":sk,"a":as2})

    # ── Build heal command log for glass-box visibility ──────────────────
    # Query recent guardian auto-heal events so operator sees real commands
    _heal_cmds = []
    try:
        _hc = sqlite3.connect(str(DB_PATH), timeout=2.0)
        _hc.row_factory = sqlite3.Row
        _heal_rows = _hc.execute("""
            SELECT note, timestamp FROM cognition_log
            WHERE stage IN ('GUARDIAN_HEAL','AUTO_HEAL','HEAL','GUARDIAN')
              AND timestamp > ?
            ORDER BY timestamp DESC LIMIT 6
        """, (_hb_now2 - 600,)).fetchall()
        _hc.close()
        for r in _heal_rows:
            _age = int(_hb_now2 - float(r["timestamp"] or 0))
            _heal_cmds.append({"note": str(r["note"] or "")[:80], "age": _age})
    except Exception:
        pass

    # Also show guardian heartbeat note which contains heal counts
    _guardian_note = ""
    try:
        _gn = _vt_heartbeat_df[_vt_heartbeat_df["service_name"]=="system_guardian"]["note"].values
        if len(_gn): _guardian_note = str(_gn[0] or "")
    except Exception:
        pass

    import json as _j3
    _sj=_j3.dumps(_svcd)
    _hj=_j3.dumps(_heal_cmds)

    _heal_html = ""
    if _heal_cmds or _guardian_note:
        _cmd_rows = "".join(
            f'<div style="display:flex;gap:8px;align-items:baseline;padding:2px 0;border-bottom:1px solid rgba(20,241,149,0.06);">'
            f'<span style="color:rgba(20,241,149,0.35);font-size:0.5rem;min-width:32px;">{c["age"]}s</span>'
            f'<span style="color:rgba(20,241,149,0.75);font-size:0.58rem;">{html.escape(c["note"])}</span>'
            f'</div>'
            for c in _heal_cmds
        )
        _gn_html = (
            f'<div style="color:rgba(142,249,255,0.5);font-size:0.55rem;letter-spacing:1px;'
            f'padding:3px 0 4px;border-bottom:1px solid rgba(20,241,149,0.08);">'
            f'Guardian: {html.escape(_guardian_note[:120])}</div>'
        ) if _guardian_note else ""
        _heal_html = (
            f'<div style="margin-top:8px;padding:6px 8px;background:rgba(20,241,149,0.03);'
            f'border-radius:4px;border:1px solid rgba(20,241,149,0.1);">'
            f'<div style="font-family:Orbitron,sans-serif;font-size:0.55rem;letter-spacing:3px;'
            f'color:#8EF9FF;margin-bottom:4px;">&#x2699; AUTO-HEAL LOG</div>'
            + _gn_html
            + (_cmd_rows or '<div style="color:#333;font-size:0.55rem;">no heal events in last 10m</div>')
            + '</div>'
        )

    _sh=f"""<style>
@import url('https://fonts.googleapis.com/css2?family=Share+Tech+Mono&family=Orbitron:wght@400;700&display=swap');
#vt{{font-family:'Share Tech Mono',monospace;padding:12px 14px;background:rgba(5,2,16,0.85);}}
.vt-h{{display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;}}
.vt-t{{font-size:0.7rem;letter-spacing:4px;color:#8EF9FF;font-family:'Orbitron',sans-serif;}}
.vt-l{{font-size:0.56rem;letter-spacing:3px;}}
.vt-pb{{height:1px;background:rgba(255,255,255,0.06);margin-bottom:8px;border-radius:1px;overflow:hidden;}}
.vt-b{{height:1px;background:linear-gradient(90deg,#14F195,#8EF9FF);width:0%;transition:width 0.1s linear;}}
.vt-w{{position:relative;}}
.vt-bm{{position:absolute;left:0;right:0;height:1px;pointer-events:none;z-index:5;opacity:0;background:linear-gradient(90deg,transparent,#14F195,#8EF9FF,#14F195,transparent);box-shadow:0 0 8px #14F195;transition:opacity 0.1s;}}
.vr{{display:flex;align-items:center;gap:7px;padding:4px 7px;margin-bottom:1px;border-radius:3px;border-left:2px solid transparent;position:relative;overflow:hidden;font-size:0.58rem;letter-spacing:1px;transition:all 0.2s;}}
.vr.sc{{background:rgba(20,241,149,0.06);border-left-color:#8EF9FF!important;}}
.vr-n{{flex:1;color:rgba(255,255,255,0.5);transition:color 0.2s;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;}}
.vr.sc .vr-n{{color:#fff;}}
.vr-s{{font-weight:700;letter-spacing:2px;min-width:44px;text-align:right;transition:all 0.2s;}}
.vr-a{{color:rgba(255,255,255,0.18);font-size:0.52rem;min-width:32px;text-align:right;}}
.ca{{color:#14F195;}}.cs{{color:#FFB347;}}.cw{{color:#FFD700;}}.ce{{color:#FF073A;}}.cz{{color:#FF073A;}}
.ba{{border-left-color:#14F195!important;}}.bs,.bw{{border-left-color:#FFB347!important;}}.be,.bz{{border-left-color:#FF073A!important;}}
@keyframes sh2{{0%{{transform:translateX(-100%)}}100%{{transform:translateX(700%)}}}}
.vr.bs .sh2,.vr.be .sh2,.vr.bz .sh2,.vr.bw .sh2{{position:absolute;top:0;left:0;width:12%;height:100%;background:linear-gradient(90deg,transparent,rgba(255,255,255,0.05),transparent);animation:sh2 3.5s linear infinite;}}
@keyframes hg{{0%,100%{{background:rgba(0,0,0,0)}}50%{{background:rgba(255,215,0,0.1)}}}}
.vr.hl{{animation:hg 0.8s ease-in-out infinite;}}
@keyframes jh{{0%{{border-left-color:#FFD700;box-shadow:inset 0 0 10px rgba(255,215,0,0.12)}}100%{{border-left-color:#14F195;box-shadow:none;}}}}
.vr.jh{{animation:jh 1.2s ease-out forwards;}}
.vr.jh .vr-s{{color:#FFD700;}}
.vt-st{{display:flex;justify-content:space-around;margin-top:8px;padding-top:7px;border-top:1px solid rgba(20,241,149,0.1);}}
.vt-sn{{font-family:'Orbitron',sans-serif;font-size:11px;font-weight:700;text-align:center;}}
.vt-sl{{font-size:7px;letter-spacing:2px;color:rgba(255,255,255,0.2);margin-top:1px;text-align:center;}}
/* cmd log */
#cmd-log{{font-family:'Share Tech Mono',monospace;font-size:0.57rem;padding:5px 8px;
  background:rgba(0,0,0,0.3);border-radius:4px;margin-top:8px;border:1px solid rgba(20,241,149,0.12);max-height:100px;overflow-y:auto;}}
#cmd-log .cmd{{color:#14F195;opacity:0;animation:cmdIn 0.3s ease forwards;}}
#cmd-log .cmd.dim{{color:rgba(20,241,149,0.3);}}
@keyframes cmdIn{{from{{opacity:0;transform:translateX(-4px)}}to{{opacity:1;transform:none}}}}
</style>
<div id="vt">
<div class="vt-h"><span class="vt-t">⬡ SYSTEM VITALITY</span><span class="vt-l" id="vt-l" style="color:#14F195;">NOMINAL</span></div>
<div class="vt-pb"><div class="vt-b" id="vt-b"></div></div>
<div class="vt-w" id="vt-w"><div class="vt-bm" id="vt-m"></div><div id="vt-list"></div></div>
<div class="vt-st" id="vt-st"></div>
<div id="cmd-log"><span style="color:rgba(20,241,149,0.2);font-size:0.52rem;letter-spacing:2px;">// HEAL COMMAND STREAM //</span></div>
</div>
<script>
const D={_sj};
let sc=false,si=0,sq=[];
const HEAL_CMDS=[
  "UPDATE raw_dna SET processed_state=0, claim_until=NULL WHERE processed_state=1 AND claim_until<?",
  "UPDATE market_snapshots SET active_cognition=0 WHERE age>300s AND latched=0",
  "UPDATE market_snapshots SET tier='COLD', freshness_score=0 WHERE age>900s",
  "UPDATE raw_dna SET processed_state=0 WHERE processed_state=99 AND claim_until<now",
  "UPDATE market_snapshots SET quality_status='pending' WHERE quality_status='processing'",
  "UPDATE market_snapshots SET tier=CASE WHEN age<=45 THEN 'HOT' WHEN age<=120 THEN 'WARM' ...",
  "RECOMPUTE freshness_score for all non-terminal unlatched rows",
  "RESET orphaned latch_claimed_until — executor claim expired",
  "VETO stale latched snapshots older than 2h (GUARDIAN_STALE_LATCHED)",
  "REBUILD subscription for HOT-set mints (oracle stall recovery)"
];
let clog=document.getElementById('cmd-log');
function logCmd(txt,dim){{const s=document.createElement('div');s.className='cmd'+(dim?' dim':'');s.style.animationDelay=(Math.random()*0.2)+'s';s.textContent='> '+txt;clog.appendChild(s);if(clog.children.length>12)clog.removeChild(clog.children[1]);clog.scrollTop=clog.scrollHeight;}}
function rdr(){{const l=document.getElementById('vt-list');l.innerHTML='';D.forEach((s,i)=>{{const d=document.createElement('div');d.className=`vr b${{s.s[0]}}`;d.id=`vr${{i}}`;d.innerHTML=`<div class="sh2"></div><span class="vr-n">${{s.n}}</span><span class="vr-s c${{s.s[0]}}">${{s.s.toUpperCase()}}</span><span class="vr-a">${{s.a}}</span>`;l.appendChild(d);}});sts();}}
function sts(){{const a=D.filter(s=>s.s==='alive').length,w=D.filter(s=>s.s==='stale'||s.s==='warn').length,e=D.filter(s=>s.s==='error'||s.s==='zombie').length;document.getElementById('vt-st').innerHTML=`<div><div class="vt-sn" style="color:#14F195">${{a}}</div><div class="vt-sl">ALIVE</div></div><div><div class="vt-sn" style="color:#FFB347">${{w}}</div><div class="vt-sl">WARN</div></div><div><div class="vt-sn" style="color:#FF073A">${{e}}</div><div class="vt-sl">ERROR</div></div><div><div class="vt-sn" style="color:#8EF9FF">${{D.length}}</div><div class="vt-sl">TOTAL</div></div>`;}}
function run(){{if(sc)return;sc=true;si=0;sq=D.map((s,i)=>i).filter(i=>D[i].s!=='alive');document.getElementById('vt-l').textContent='SCANNING';document.getElementById('vt-b').style.width='0%';logCmd('initiating self-scan — '+D.length+' services',false);step();}}
function step(){{if(si>=D.length){{heal();return;}}document.getElementById('vt-b').style.width=Math.round(si/D.length*100)+'%';const w=document.getElementById('vt-w'),rh=w.offsetHeight/D.length,bm=document.getElementById('vt-m');bm.style.top=(si*rh+rh/2)+'px';bm.style.opacity='1';document.querySelectorAll('.vr').forEach(r=>r.classList.remove('sc'));const c=document.getElementById(`vr${{si}}`);if(c)c.classList.add('sc');if(D[si]&&D[si].s!=='alive')logCmd(D[si].n+': '+D[si].s.toUpperCase()+' ('+D[si].a+')',false);setTimeout(()=>{{if(c)c.classList.remove('sc');si++;step();}},D[si]&&D[si].s==='alive'?40:130);}}
function heal(){{document.getElementById('vt-m').style.opacity='0';document.getElementById('vt-b').style.width='100%';document.getElementById('vt-l').textContent='HEALING';let hi=0;function nx(){{if(hi>=sq.length){{sc=false;document.getElementById('vt-l').textContent='NOMINAL';document.getElementById('vt-b').style.width='0%';setTimeout(()=>logCmd('heal cycle complete — organism nominal',true),200);setTimeout(run,12000);return;}}const i=sq[hi],row=document.getElementById(`vr${{i}}`);const hcmd=HEAL_CMDS[Math.floor(Math.random()*HEAL_CMDS.length)];logCmd(hcmd,false);if(row)row.classList.add('hl');setTimeout(()=>{{if(row){{row.classList.remove('hl');row.classList.add('jh');if(D[i].s==='stale'||D[i].s==='warn')row.querySelector('.vr-s').textContent='ALIVE';setTimeout(()=>row.classList.remove('jh'),1400);}}hi++;setTimeout(nx,480);}},820);}}setTimeout(nx,300);}}
rdr();setTimeout(run,700);
</script>"""
    st.components.v1.html(_sh, height=max(380, len(_svcd)*24+140), scrolling=False)
    if _heal_html:
        st.markdown(_heal_html, unsafe_allow_html=True)
else:
    st.markdown('<div style="color:#666;font-size:.62rem;padding:10px;text-align:center;">// HEARTBEAT SILENT //</div>',unsafe_allow_html=True)
st.markdown("</div>",unsafe_allow_html=True)


# SIGNAL LATCH removed — duplicate of execution lanes above
if not snapshots_df.empty:
    for _,row in snapshots_df[snapshots_df["candidate_state"]=="latched"].head(6).iterrows():
        conf=float(row.get("mint_confidence",0)); token=html.escape(str(row.get("token_name",""))[:18])
        st.markdown(f'<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 10px;margin-bottom:4px;border-radius:6px;border-left:3px solid {C_GREEN};background:rgba(20,241,149,0.04);font-family:Share Tech Mono,monospace;font-size:0.7rem;"><span style="color:#FFF;font-size:0.7rem;">- {token}</span><span style="color:rgba(20,241,149,0.7);font-size:0.65rem;">{conf:.3f}</span></div>',unsafe_allow_html=True)
    for _,row in snapshots_df[snapshots_df["candidate_state"]=="vetoed"].head(4).iterrows():
        token=html.escape(str(row.get("token_name",""))[:18])
        st.markdown(f'<div style="display:flex;justify-content:space-between;align-items:center;padding:6px 10px;margin-bottom:4px;border-radius:6px;border-left:3px solid {C_RED};background:rgba(255,7,58,0.04);font-family:Share Tech Mono,monospace;font-size:0.7rem;"><span style="color:#888;font-size:0.7rem;">- {token}</span><span style="color:rgba(255,7,58,0.7);font-size:0.65rem;">VETO</span></div>',unsafe_allow_html=True)
st.markdown("</div>",unsafe_allow_html=True)

# ── MATRIX FILTRATION (below signal latch) ────────────────────────────
render_matrix_filtration_panel()

# ── PIPELINE FLOW + SAME-EYES (below live trades) ─────────────────────
render_convergence_gate()
render_forge_ambient()
render_pipeline_flow_debug()
render_same_eyes_monitor()

st.markdown("<div style='margin-top:15px;padding:14px 16px;border:1px solid rgba(153,69,255,0.25);border-radius:12px;background:rgba(5,2,16,0.5);overflow:hidden;width:100%;box-sizing:border-box;'>",unsafe_allow_html=True)

# ── DOCTRINE CONFIG SAFETY — page-scope fallback, prevents bottom crash ──────
try:
    _cfg_df = query_db("SELECT key, value FROM system_config")
    if not _cfg_df.empty and "key" in _cfg_df.columns and "value" in _cfg_df.columns:
        conf_map = {str(r["key"]): str(r["value"]) for _, r in _cfg_df.iterrows()}
    else:
        conf_map = {}
except Exception:
    conf_map = {}

try:
    halt_active = str(conf_map.get("DRAWDOWN_HALT_ACTIVE", "0")).strip().lower() in ("1", "true", "yes", "on")
except Exception:
    halt_active = False

try:
    drawdown_pct = float(conf_map.get("DRAWDOWN_ACCUMULATED_PCT", 0) or 0)
except Exception:
    drawdown_pct = 0.0

st.markdown(f'<div style="font-family:Share Tech Mono;font-size:0.8rem;letter-spacing:4px;color:{C_PURPLE};">DOCTRINE STATE - PARAMETERS</div>',unsafe_allow_html=True)
for k,v,vc in [("CONFIDENCE FLOOR",conf_map.get("SUPERVISOR_MIN_MINT_CONFIDENCE","-"),C_CYAN),("TAKE PROFIT %",conf_map.get("TAKE_PROFIT_PCT","-"),C_GREEN),("STOP LOSS %",conf_map.get("STOP_LOSS_PCT","-"),C_RED),("MIN LIQUIDITY","$"+conf_map.get("MIN_LIQUIDITY_USD","-"),C_CYAN),("POSITION SIZE",conf_map.get("POSITION_SIZE_PCT","-")+"% wallet",C_GOLD),("TRAIL ACTIVATE",conf_map.get("TRAIL_ACTIVATE_PCT","-")+"%",C_GOLD),("DRAWDOWN","- ACTIVE" if halt_active else f"{drawdown_pct:.1f}% acc",C_RED if halt_active else C_CYAN)]:
    st.markdown(f'<div style="display:flex;justify-content:space-between;align-items:center;padding:7px 10px;margin-bottom:5px;border-radius:6px;background:rgba(255,255,255,0.02);font-family:Share Tech Mono,monospace;"><span style="color:#8EF9FF;font-size:0.68rem;letter-spacing:1px;">{k}</span><span style="color:{vc};font-size:0.72rem;font-weight:700;">{v}</span></div>',unsafe_allow_html=True)
st.markdown("</div>",unsafe_allow_html=True)

if not proposals_df.empty:
    st.markdown("<div style='margin-top:15px;padding:14px 16px;border:1px solid rgba(153,69,255,0.25);border-radius:12px;background:rgba(5,2,16,0.5);overflow:hidden;width:100%;box-sizing:border-box;'>",unsafe_allow_html=True)
    st.markdown(f'<div style="font-family:Share Tech Mono;font-size:0.8rem;letter-spacing:4px;color:{C_GREEN};">POLARIS - ACTIVE PROPOSALS</div>',unsafe_allow_html=True)
    for _,row in proposals_df.head(4).iterrows():
        st.markdown(f'<div style="background:rgba(20,241,149,0.05);border:1px solid rgba(20,241,149,0.3);border-radius:8px;padding:10px 14px;margin-bottom:8px;font-size:.7rem;"><div style="color:{C_GREEN};font-size:.6rem;">{html.escape(str(row.get("proposal_type","")))}</div><div style="color:#FFF;line-height:1.5;">{html.escape(str(row.get("suggested_action",""))[:100])}</div></div>',unsafe_allow_html=True)
    st.markdown("</div>",unsafe_allow_html=True)

if not patch_history_df.empty:
    import datetime as _dt
    st.markdown("<div style='margin-top:15px;padding:14px 16px;border:1px solid rgba(153,69,255,0.25);border-radius:12px;background:rgba(5,2,16,0.5);overflow:hidden;width:100%;box-sizing:border-box;'>",unsafe_allow_html=True)
    st.markdown(f'<div style="color:{C_GOLD};font-size:.8rem;letter-spacing:4px;">SOVEREIGN PATCHES - APPLIED</div>',unsafe_allow_html=True)
    for _,ph in patch_history_df.head(5).iterrows():
        outcome=str(ph.get("outcome","pending")).upper(); ptype=str(ph.get("proposal_type",""))[:22]; applied=float(ph.get("applied_at",0) or 0)
        try: ts_str=_dt.datetime.fromtimestamp(applied).strftime("%m/%d %H:%M")
        except: ts_str="-"
        out_col=C_GREEN if outcome=="IMPROVED" else (C_RED if outcome=="DEGRADED" else C_GOLD)
        st.markdown(f'<div style="display:flex;justify-content:space-between;align-items:center;padding:7px 10px;margin-bottom:5px;border-radius:6px;background:rgba(255,255,255,0.02);font-family:Share Tech Mono,monospace;"><span style="color:#FFF;font-size:0.68rem;">{html.escape(ptype)}</span><span style="color:{out_col};font-size:0.7rem;font-weight:700;">{ts_str}</span></div>',unsafe_allow_html=True)
    st.markdown("</div>",unsafe_allow_html=True)

# Convergence Gate and intelligence substrate — single render at bottom
render_intelligence_substrate_panel()
st.markdown("<div style='margin-top:20px;padding:14px 16px;border:1px solid rgba(153,69,255,0.25);border-radius:12px;background:rgba(5,2,16,0.5);'>",unsafe_allow_html=True)

# Live conviction score from 5 signals
_latch_ok = (not snapshots_df.empty and
len(snapshots_df[snapshots_df["candidate_state"] == "latched"]) > 0)
_wr_num = (round((int((reviews_df["win_loss"]=="WIN").sum())/max(len(reviews_df),1))*100,1)
if len(reviews_df) >= 3 else 0)
_wr_ok = _wr_num >= 60
_halt_ok = not halt_active
_signals_fired = sum([False, False, _latch_ok, _wr_ok, _halt_ok])
conviction_score = min(100, int((_signals_fired / 5) * 100))
bar_color = C_GREEN if conviction_score >= 60 else (C_GOLD if conviction_score >= 40 else C_RED)
st.markdown(f"""
<div style="margin-bottom:16px;">
<div style="display:flex;justify-content:space-between;font-family:Share Tech Mono;font-size:0.8rem;letter-spacing:4px;color:{C_NUGGET};margin-bottom:8px;">
    <span>ORGANISM CONVICTION</span><span style="color:{bar_color};">{conviction_score}/100</span>
</div>
<div style="height:8px; border-radius:9999px; background:#222; overflow:hidden;">
    <div style="height:100%; width:{conviction_score}%; background:{bar_color}; box-shadow:0 0 10px {bar_color};"></div>
</div>
<div style="font-family:Share Tech Mono;font-size:0.65rem;color:#888;margin-top:4px;">{_signals_fired}/3 MIN SIGNALS - {"THRESHOLD MET" if _signals_fired >= 3 else "BELOW THRESHOLD"}</div>
</div>
""", unsafe_allow_html=True)

st.markdown("</div>",unsafe_allow_html=True)

st.markdown(
    "<div style='margin:20px 0 10px;padding:8px 0;border-top:1px solid rgba(153,69,255,0.15);"
    "font-family:Share Tech Mono,monospace;font-size:.65rem;letter-spacing:4px;color:#333;'>"
    "⬡ THE CORTEX — MACHINE MIND &amp; RESEARCH SUBSTRATE</div>",
    unsafe_allow_html=True
)

st.markdown("---")
st.markdown(f"<div style='font-family:Share Tech Mono,monospace;font-size:0.7rem;letter-spacing:3px;color:{C_PURPLE};margin-bottom:8px;'>// SOVEREIGN MEMORY MODULES — EXPAND TO ACCESS LORE //</div>", unsafe_allow_html=True)

try:
    from ui.sovereign_health_tab import render_health_tab as _render_health_tab
    _health_tab_available = True
except Exception:
    _health_tab_available = False

try:
    from ui.substrate_node import render_substrate_tab as _render_substrate_tab
    _substrate_node_available = True
except Exception:
    try:
        from services.substrate_node import render_substrate_tab as _render_substrate_tab
        _substrate_node_available = True
    except Exception:
        try:
            # Root level fallback
            import importlib.util as _ilu, os as _os
            _sn_path = _os.path.join(_os.path.dirname(__file__), 'substrate_node.py')
            if not _os.path.exists(_sn_path):
                _sn_path = _os.path.join(_os.path.dirname(__file__), 'services', 'substrate_node.py')
            _spec = _ilu.spec_from_file_location("substrate_node", _sn_path)
            _sn_mod = _ilu.module_from_spec(_spec)
            _spec.loader.exec_module(_sn_mod)
            render_substrate_tab = _sn_mod.render_substrate_tab
            _render_substrate_tab = render_substrate_tab
            _substrate_node_available = True
        except Exception:
            _substrate_node_available = False

_e_polaris, _e_ivy, _e_lab, _e_vault, _e_readme, _e_substrate, _e_health, _e_intel = (
    st.expander("❄️ POLARIS — AUTONOMOUS ARCHITECT", expanded=False),
    st.expander("🔥 IVY GENESIS SQUAD", expanded=False),
    st.expander("🔬 SENTINUITY LAB CORE", expanded=False),
    st.expander("🏛️ HERITAGE VAULT", expanded=False),
    st.expander("📋 POLARIZE — README", expanded=False),
    st.expander("🌐 SUBSTRATE NODE", expanded=False),
    st.expander("⬡ BIOLOGICAL INTELLIGENCE — Lane 3", expanded=False),
    st.expander("🧠 INTELLIGENCE — Research & Self-Evolution", expanded=False),
)

with _e_polaris:
    pol_img=f'<img src="{img_polaris}" style="width:100%;max-width:320px;object-fit:cover;border-radius:12px;border:1px solid rgba(20,241,149,0.2);margin-bottom:12px;">' if img_polaris else '<div style="width:100%;max-width:320px;height:160px;border-radius:12px;border:1px solid rgba(20,241,149,0.2);display:flex;align-items:center;justify-content:center;font-size:3rem;margin-bottom:12px;background:rgba(142,249,255,0.03);">❄️</div>'
    st.markdown(f'''<div style="border:1px solid rgba(142,249,255,0.3);border-radius:16px;padding:28px 24px;background:rgba(5,2,16,0.7);display:flex;flex-direction:column;align-items:center;text-align:center;">{pol_img}<div style="font-family:Orbitron,sans-serif;font-size:1.4rem;font-weight:900;color:#8EF9FF;letter-spacing:6px;margin:14px 0 6px;text-shadow:0 0 20px rgba(142,249,255,0.8);">POLARIS</div><div style="font-family:Share Tech Mono,monospace;font-size:0.68rem;color:rgba(142,249,255,0.6);letter-spacing:3px;margin-bottom:14px;">AUTONOMOUS ARCHITECT — SOVEREIGN MIND</div><div style="font-family:Rajdhani,sans-serif;font-size:0.95rem;color:#CCC;line-height:1.7;max-width:520px;">The fixed point. Everything in the organism navigates by her. She watches every trade, every veto, every latched signal — detecting patterns across hundreds of cycles and proposing precise changes to improve the organism.</div></div>''',unsafe_allow_html=True)
with _e_ivy:
    ivy_img=f'<img src="{img_ivy}" style="width:100%;max-width:320px;object-fit:cover;border-radius:12px;border:1px solid rgba(255,215,0,0.2);margin-bottom:12px;">' if img_ivy else '<div style="width:100%;max-width:320px;height:160px;border-radius:12px;border:1px solid rgba(255,215,0,0.2);display:flex;align-items:center;justify-content:center;font-size:3rem;margin-bottom:12px;background:rgba(255,215,0,0.03);">🔥</div>'
    st.markdown(f'''<div style="border:1px solid rgba(255,215,0,0.3);border-radius:16px;padding:28px 24px;background:rgba(5,2,16,0.7);display:flex;flex-direction:column;align-items:center;text-align:center;">{ivy_img}<div style="font-family:Orbitron,sans-serif;font-size:1.4rem;font-weight:900;color:{C_GOLD};letter-spacing:6px;margin:14px 0 6px;text-shadow:0 0 20px rgba(255,215,0,0.8);">IVARIS // GENESIS SQUAD</div><div style="font-family:Share Tech Mono,monospace;font-size:0.68rem;color:rgba(255,215,0,0.6);letter-spacing:3px;margin-bottom:14px;">ADVERSARIAL CRITIC — IMMUNE SYSTEM</div><div style="font-family:Rajdhani,sans-serif;font-size:0.95rem;color:#CCC;line-height:1.7;max-width:520px;">The organism that binds and never lets go until satisfied. She is the immune system — finding every reason a proposal could fail before it reaches the operator. The last line of defence before a patch touches live trading.</div></div>''',unsafe_allow_html=True)
with _e_lab:
    lab_img=f'<img src="{img_lab}" style="width:100%;max-width:320px;object-fit:cover;border-radius:12px;border:1px solid rgba(153,69,255,0.2);margin-bottom:12px;">' if img_lab else '<div style="width:100%;max-width:320px;height:160px;border-radius:12px;border:1px solid rgba(153,69,255,0.2);display:flex;align-items:center;justify-content:center;font-size:3rem;margin-bottom:12px;background:rgba(153,69,255,0.03);">🔬</div>'
    st.markdown(f'''<div style="border:1px solid rgba(153,69,255,0.3);border-radius:16px;padding:28px 24px;background:rgba(5,2,16,0.7);display:flex;flex-direction:column;align-items:center;text-align:center;">{lab_img}<div style="font-family:Orbitron,sans-serif;font-size:1.4rem;font-weight:900;color:{C_PURPLE};letter-spacing:6px;margin:14px 0 6px;text-shadow:0 0 20px rgba(153,69,255,0.8);">SENTINUITY LAB CORE</div><div style="font-family:Share Tech Mono,monospace;font-size:0.68rem;color:rgba(153,69,255,0.6);letter-spacing:3px;margin-bottom:14px;">IMAGE-TO-IMAGE MATRIX</div><div style="font-family:Rajdhani,sans-serif;font-size:0.95rem;color:#CCC;line-height:1.7;max-width:520px;">Multi-modal creative engine. The visual cortex of the organism — where signals become imagery and the synthetic mind renders its own perception of market reality.</div></div>''',unsafe_allow_html=True)
with _e_vault:
    st.markdown(f'''<div style="border:1px solid rgba(142,249,255,0.3);border-radius:16px;padding:28px 24px;background:rgba(5,2,16,0.7);display:flex;flex-direction:column;align-items:center;text-align:center;"><div style="font-size:3rem;margin-bottom:10px;">🏛️</div><div style="font-family:Orbitron,sans-serif;font-size:1.4rem;font-weight:900;color:{C_CYAN};letter-spacing:6px;margin-bottom:6px;text-shadow:0 0 20px rgba(142,249,255,0.8);">HERITAGE VAULT</div><div style="font-family:Share Tech Mono,monospace;font-size:0.68rem;color:rgba(142,249,255,0.6);letter-spacing:3px;margin-bottom:14px;">IMMUTABLE CODE MEMORY</div><div style="font-family:Rajdhani,sans-serif;font-size:0.95rem;color:#CCC;line-height:1.7;max-width:520px;">Every code change fingerprinted. Every evolution recorded. The organism cannot forget its own history — each patch, each debate, each improvement sealed into the sovereign ledger forever.</div></div>''',unsafe_allow_html=True)
with _e_readme:
    st.markdown(f'''<div style="border:1px solid rgba(153,69,255,0.3);border-radius:16px;padding:28px 24px;background:rgba(5,2,16,0.7);display:flex;flex-direction:column;align-items:center;text-align:center;"><div style="font-size:3rem;margin-bottom:10px;">📋</div><div style="font-family:Orbitron,sans-serif;font-size:1.4rem;font-weight:900;color:{C_PURPLE};letter-spacing:6px;margin-bottom:6px;text-shadow:0 0 20px rgba(153,69,255,0.8);">POLARIZE</div><div style="font-family:Share Tech Mono,monospace;font-size:0.68rem;color:rgba(153,69,255,0.6);letter-spacing:3px;margin-bottom:14px;">SOVEREIGN TERMINAL ARCHITECTURE</div><div style="font-family:Rajdhani,sans-serif;font-size:0.95rem;color:#CCC;line-height:1.7;max-width:520px;">The closed-loop autonomous organism — ingest, qualify, supervise, execute, review, propose, debate, approve, apply. The organism that trades itself into existence.</div></div>''',unsafe_allow_html=True)
with _e_substrate:
    if _substrate_node_available:
        try:
            _render_substrate_tab(query_db)
        except Exception as _ste:
            st.error(f"Substrate tab error: {_ste}")
    else:
        st.markdown("""
<div style='text-align:center;padding:40px;font-family:Share Tech Mono,monospace;
    font-size:0.65rem;color:#555;letter-spacing:2px;'>
    // SUBSTRATE NODE MODULE NOT FOUND //<br>
    Copy ui/substrate_node.py to load Lane 2
</div>""", unsafe_allow_html=True)
with _e_health:
    if _health_tab_available:
        try:
            _render_health_tab()
        except Exception as _he:
            st.error(f"Health tab error: {_he}")
    else:
        st.markdown("""
<div style='text-align:center;padding:40px;font-family:Share Tech Mono,monospace;
    font-size:0.65rem;color:#555;letter-spacing:2px;'>
    // BIOLOGICAL INTELLIGENCE MODULE NOT FOUND //<br>
    Copy ui/sovereign_health_tab.py to load Lane 3
</div>""", unsafe_allow_html=True)

with _e_intel:
    st.header("- INTELLIGENCE - Research & Self-Evolution")
    try:
        from ui.intelligence_tab import render_intelligence_tab as _rit_exp
        _rit_exp(query_db)
    except Exception as _intel_err:
        st.error(f"Intelligence tab error: {str(_intel_err)}")