"""
execution_engine.py
-------------------------------------------------------------------------------
Sentinuity Unified Execution Engine - SIGNED-OFF v1.0
-------------------------------------------------------------------------------

Merges responsibilities previously split across:
  - paper_executor.py
  - position_reconciler.py
  - zombie_resolver.py

ARCHITECTURE - THREE SOURCES OF TRUTH
--------------------------------------
1. POSITION STATE     - get_open_positions() / get_position_by_id_open()
2. EXIT DECISIONS     - evaluate_exit_for_position() (live)
                        reconcile_position()          (gap/startup)
                        scan_and_resolve_zombies()    (stale feed)
3. POSITION CLOSURE   - close_position_canonical()   - ALL closes route here

No other function may write status='CLOSED' or return wallet funds.

EXIT PATH ORDER (evaluate_exit_for_position)
--------------------------------------------
  1. TIME_CUT            - negative PnL beyond discovery window
  2. TIME_CUT_STAGNANT   - flat/weakly green beyond stagnation window
  3. TRAILING_STOP       - after trail_activate threshold
  4. TAKE_PROFIT
  5. STOP_LOSS
  6. MAX_HOLD_TIME

ZOMBIE THREADING FIX (Claude sign-off patch)
---------------------------------------------
The original zombie_resolver.py blocked the main loop for up to
ZOMBIE_HITL_TIMEOUT_SECONDS (default 30s) while polling Telegram.
On pump.fun tokens where 30s is a material portion of trade lifetime,
this caused missed TP/SL fires during that window.

Fix: scan_and_resolve_zombies() now spawns a daemon thread per zombie
for HITL polling. The main loop never blocks. Thread results are
collected via _pending_zombie_results (thread-safe queue).

DB HYGIENE
------------------------------------------------------------------------------
  - All reads/writes use core.schema.get_connection() exclusively
  - Local _get_conn() removed entirely (was only needed for legacy isolation)
  - No duplicate connection setup patterns

REMOVED BEHAVIOURS (deliberate)
------------------------------------------------------------------------------
  - Duplicate sqlite3.connect() blocks from reconciler and zombie close helpers
  - close_position_reconcile() and close_at_scratch() standalone paths
    - both now route through close_position_canonical()
  - The inconsistency in zombie offline branch (fetched best price but always
    closed at scratch) is fixed: now uses best known price when available,
    otherwise scratch
"""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import threading
import time
import queue
from pathlib import Path
from typing import Any, Optional

# Configure logging BEFORE any service imports.
# logging.basicConfig() is a no-op if already configured — whichever module
# calls it first wins the format string for ALL loggers in the process.
# market_intelligence also calls basicConfig([MARKET_INTEL]) at module level,
# and it was being imported BEFORE this block ran, causing every log line
# including scan_for_entries() to show [MARKET_INTEL] prefix.
# Placing basicConfig here (before any service imports) ensures [EXEC_ENGINE]
# format is locked in first.
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - [EXEC_ENGINE] %(levelname)-7s %(message)s",
    handlers=[logging.StreamHandler()],
)
log = logging.getLogger("execution_engine")

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
if str(BASE_DIR) not in sys.path:
    sys.path.append(str(BASE_DIR))

load_dotenv(BASE_DIR / ".env", override=True)

from core.schema import get_connection, get_intel_connection, update_heartbeat, get_config_value

try:
    from services.trade_lifecycle import (
        ensure_schema as _tle_ensure,
        emit_trade_opened as _tle_opened,
        emit_mark_written as _tle_mark,
        emit_trade_closed as _tle_closed,
        emit_coverage_alert as _tle_coverage_alert,
        get_trade_coverage as _tle_coverage,
        classify_exit_validity as _tle_validity,
    )
    _TLE_AVAILABLE = True
except ImportError:
    _TLE_AVAILABLE = False

try:
    from services.cognition_logger import log_cognition as _log_cog_fn
    _COGNITION_AVAILABLE = True
except Exception:
    _COGNITION_AVAILABLE = False

try:
    from services.market_intelligence import get_curve_progress as _get_curve_progress
    _CURVE_CHECK_AVAILABLE = True
except Exception:
    _CURVE_CHECK_AVAILABLE = False

# Oracle notify — used to push new mint subscriptions to the oracle process.
# NOTE: oracle_last_write_age() was previously imported here for the liveness
# gate but is now REMOVED — that gate was replaced with a direct DB read from
# sentinuity_intelligence.db (see _get_oracle_age_sec in scan_for_entries).
# The in-memory variable was always 0 in this process (separate process scope).
try:
    from services.ws_price_oracle import notify_new_mint as _oracle_notify_mint
except Exception:
    def _oracle_notify_mint(mint: str) -> None:
        pass  # no-op fallback when oracle not importable

# Price Truth Router — single authoritative price source
try:
    from services.price_router import get_execution_price as _router_exec_price
    from services.price_router import get_ui_price as _router_ui_price
    _PRICE_ROUTER_AVAILABLE = True
except Exception:
    _PRICE_ROUTER_AVAILABLE = False
    def _router_exec_price(mint, entry_price, opened_at): return None
    def _router_ui_price(mint, entry_price, opened_at): return None

try:
    from services.live_trading import sell_token as _live_sell
    _LIVE_TRADING_AVAILABLE = True
except Exception:
    _LIVE_TRADING_AVAILABLE = False
    def _live_sell(mint, qty, pos_id, price):
        return {"success": False, "error": "live_trading not available"}

# logging.basicConfig and log = ... moved above service imports — prevents [MARKET_INTEL] format collision

SERVICE_NAME       = "execution_engine"
MAX_OPEN_POSITIONS = 3

# Track positions that have already had trailing-stop-activate logged
# to prevent the message firing every evaluation cycle (~every 2s per position).
_trail_logged_positions: set = set()
POLL_INTERVAL      = 2.2        # v3.2: was 5s — faster mark cycle for meter updates
ZOMBIE_POLL_EVERY  = 6          # run zombie scan every N main cycles (~30s)

# ── PRAGMA CACHE — eliminates per-tick PRAGMA table_info(paper_positions) ──
# update_position_mark was calling PRAGMA table_info every single tick.
# Audit: 0.89ms median, 1,632ms worst-case spike.
# Cache at module load. Restart service if schema changes (rare).
_PP_COLS_CACHE: set = set()

def _get_pp_cols() -> set:
    global _PP_COLS_CACHE
    if _PP_COLS_CACHE:
        return _PP_COLS_CACHE
    try:
        import sqlite3 as _sq
        _c = _sq.connect(str(DB_PATH), timeout=3)
        _PP_COLS_CACHE = {r[1] for r in _c.execute("PRAGMA table_info(paper_positions)").fetchall()}
        _c.close()
    except Exception:
        pass
    return _PP_COLS_CACHE

BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
OWNER_ID  = int(os.getenv("TELEGRAM_OWNER_ID", "0") or "0")


def _is_live_mode() -> bool:
    """Returns True only when TRADING_MODE=live in system_config."""
    try:
        return str(get_config_value("TRADING_MODE", "paper")).strip().lower() == "live"
    except Exception:
        return False

# -- Zombie threading state ----------------------------------------------------
# Thread-safe queue: zombie threads post (position_id, action) here.
# Main loop drains it every cycle.
_zombie_result_queue: queue.Queue = queue.Queue()
# Tracks which position_ids have an active HITL thread to avoid double-spawning
_zombie_threads_active: set[int] = set()
_zombie_threads_lock   = threading.Lock()

# HITL alert cooldown (for non-threaded path)
_hitl_sent_at: dict[int, float] = {}


# -----------------------------------------------------------------------------
# SCHEMA ENSURE
# -----------------------------------------------------------------------------

def ensure_executor_schema() -> None:
    """Add non-breaking columns if absent (backward-compat with older DB)."""
    try:
        with get_connection() as conn:
            # Instrument trade lifecycle event spine
            if _TLE_AVAILABLE:
                try:
                    _tle_ensure(conn)
                except Exception:
                    pass
            # paper_positions columns
            pp_cols = {r["name"] for r in conn.execute(
                "PRAGMA table_info(paper_positions)"
            ).fetchall()}
            for col, typedef in [
                ("last_price",           "REAL"),
                ("last_marked_at",       "REAL"),
                ("highest_price_seen",   "REAL"),
                ("close_claimed_until",  "REAL"),
                ("mint_address",         "TEXT"),
                # PATCH D: freshness provenance — 'oracle'|'engine'|'fallback'
                ("mark_source",          "TEXT DEFAULT 'unknown'"),
                ("live_exec_price",      "REAL"),
                ("live_exec_pct",        "REAL"),
                ("live_exec_band",       "TEXT"),
                ("live_exec_updated_at", "REAL"),
                ("live_exec_source",     "TEXT"),
            ]:
                if col not in pp_cols:
                    conn.execute(
                        f"ALTER TABLE paper_positions ADD COLUMN {col} {typedef}"
                    )

            # PHASE 1 schema additions — explicit try/except per column
            # so each is independently idempotent regardless of DB state.
            try:
                conn.execute(
                    "ALTER TABLE paper_positions ADD COLUMN entry_price_source TEXT DEFAULT 'qualify'"
                )
            except Exception:
                pass  # column already exists — safe to ignore

            try:
                conn.execute(
                    "ALTER TABLE paper_positions ADD COLUMN entry_price_ts REAL"
                )
            except Exception:
                pass  # column already exists — safe to ignore

            # trade_autopsies - CREATE with full schema, then add missing cols
            conn.execute("""
                CREATE TABLE IF NOT EXISTS trade_autopsies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id INTEGER,
                    token_name TEXT,
                    mint_address TEXT,
                    win_loss TEXT,
                    realized_pnl_usd REAL DEFAULT 0,
                    notes TEXT,
                    created_at REAL
                )
            """)
            ta_cols = {r["name"] for r in conn.execute(
                "PRAGMA table_info(trade_autopsies)"
            ).fetchall()}
            for col, typedef in [
                ("position_id",       "INTEGER"),
                ("mint_address",      "TEXT"),
                ("win_loss",          "TEXT"),
                ("realized_pnl_usd",  "REAL DEFAULT 0"),
                ("notes",             "TEXT"),
                ("created_at",        "REAL"),
            ]:
                if col not in ta_cols:
                    conn.execute(
                        f"ALTER TABLE trade_autopsies ADD COLUMN {col} {typedef}"
                    )

            # polaris_trade_reviews - needed by Polaris feedback loop
            conn.execute("""
                CREATE TABLE IF NOT EXISTS polaris_trade_reviews (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id INTEGER,
                    token_name TEXT,
                    mint_address TEXT,
                    win_loss TEXT,
                    exit_category TEXT,
                    realized_pnl_usd REAL DEFAULT 0,
                    pnl_pct REAL DEFAULT 0,
                    hold_seconds REAL DEFAULT 0,
                    reviewed_at REAL,
                    polaris_version TEXT DEFAULT 'executor_v1'
                )
            """)

            # DEFENSIVE LAYER: wallet_write_log — every wallet mutation logged
            # with source, delta, position_id and resulting balance.
            # Enables post-mortem inspection of any wallet explosion:
            #   SELECT * FROM wallet_write_log ORDER BY id DESC LIMIT 20;
            conn.execute("""
                CREATE TABLE IF NOT EXISTS wallet_write_log (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id  INTEGER,
                    delta_usd    REAL,
                    new_balance  REAL,
                    source       TEXT,
                    token_name   TEXT,
                    pnl_usd      REAL,
                    pnl_pct      REAL,
                    timestamp    REAL
                )
            """)

            # MOMENTUM GATE AUDIT — shadow measurement table
            # Phase 1: data collection only. Phase 2: hard gate when evidence supports.
            conn.execute("""
                CREATE TABLE IF NOT EXISTS momentum_gate_audit (
                    id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                    snapshot_id          INTEGER,
                    mint_address         TEXT,
                    token_name           TEXT,
                    qual_price           REAL,
                    latest_price         REAL,
                    move_from_qual_pct   REAL,
                    move_short_term_pct  REAL,
                    would_veto           INTEGER DEFAULT 0,
                    entered              INTEGER DEFAULT 0,
                    position_id          INTEGER,
                    created_at           REAL,
                    reviewed_at          REAL,
                    eventual_outcome     TEXT,
                    eventual_pnl_pct     REAL,
                    exit_reason          TEXT
                )
            """)

            conn.commit()
    except Exception as e:
        log.debug("ensure_executor_schema skipped: %s", e)


# -----------------------------------------------------------------------------
# COGNITION / TELEMETRY — single queue + single writer thread
# -----------------------------------------------------------------------------
# Execution thread MUST NEVER block on cognition logging.
# One Queue(maxsize=200), one daemon writer thread, one SQLite connection.
# Execution path: put_nowait() → returns in microseconds.
# Queue full → drop silently. Never block, never retry.

import queue as _queue
import threading as _threading

_COG_QUEUE: "_queue.Queue" = _queue.Queue(maxsize=200)   # explicit 200 cap
_COG_WRITER_STARTED       = False
_COG_DROPPED_COUNT        = 0    # observability counter — surfaced in UI

def _start_cognition_writer() -> None:
    """Start the single background cognition writer thread. Idempotent."""
    global _COG_WRITER_STARTED
    if _COG_WRITER_STARTED:
        return
    _COG_WRITER_STARTED = True   # set BEFORE thread start — prevents race

    def _writer_loop():
        while True:
            try:
                payload = _COG_QUEUE.get(timeout=5)
                if payload is None:   # sentinel — clean shutdown
                    break
                stage, message, token, kwargs = payload
                try:
                    _log_cog_fn(stage, message, token=token, **kwargs)
                except Exception:
                    pass
                finally:
                    _COG_QUEUE.task_done()
            except _queue.Empty:
                continue
            except Exception:
                continue

    t = _threading.Thread(target=_writer_loop, name="cognition-writer", daemon=True)
    t.start()


def _log_cognition(token: str, message: str, stage: str = "EXECUTOR", **kwargs) -> None:
    """
    Non-blocking cognition log.
    Execution thread enqueues and returns immediately (<1µs).
    Queue cap: 200. Overflow: drop + increment _COG_DROPPED_COUNT. Never block.
    """
    global _COG_DROPPED_COUNT
    if not _COGNITION_AVAILABLE:
        return
    try:
        _COG_QUEUE.put_nowait((stage, message, token, kwargs))
    except _queue.Full:
        _COG_DROPPED_COUNT += 1   # track drops for UI observability
    except Exception:
        pass


# -----------------------------------------------------------------------------
# SOURCE OF TRUTH - POSITION STATE READERS
# -----------------------------------------------------------------------------

def get_open_positions() -> list[dict]:
    """Canonical reader for all OPEN positions."""
    try:
        with get_connection() as conn:
            rows = conn.execute(
                "SELECT * FROM paper_positions WHERE status='OPEN' ORDER BY opened_at ASC"
            ).fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("get_open_positions failed: %s", e)
        return []


def get_position_by_id_open(position_id: int) -> Optional[dict]:
    """Race-guard read: returns position only if still OPEN."""
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT * FROM paper_positions WHERE id=? AND status='OPEN'",
                (position_id,),
            ).fetchone()
        return dict(row) if row else None
    except Exception as e:
        log.warning("get_position_by_id_open failed pos=%s: %s", position_id, e)
        return None


def count_open_positions() -> int:
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) AS c FROM paper_positions WHERE status='OPEN'"
            ).fetchone()
        return int(row["c"] or 0) if row else 0
    except Exception:
        return 0


def get_wallet_balance() -> float:
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT wallet_balance FROM system_state WHERE id=1"
            ).fetchone()
        return float(row["wallet_balance"] or 0) if row else 0.0
    except Exception:
        return 0.0


def get_last_executor_heartbeat() -> float:
    """
    Returns last heartbeat from this service or legacy paper_executor.
    Used by reconciler to calculate gap duration on restart.
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT last_pulse FROM system_heartbeat
                WHERE service_name IN ('execution_engine', 'paper_executor')
                ORDER BY last_pulse DESC LIMIT 1
                """,
            ).fetchone()
        return float(row["last_pulse"] or 0) if row else 0.0
    except Exception:
        return 0.0


# -----------------------------------------------------------------------------
# PRICE HELPERS
# -----------------------------------------------------------------------------


# ── INTEL-FIRST PRICE CACHE ────────────────────────────────────────────────────
_price_cache: dict = {}     # mint -> price
_price_cache_ts: dict = {}  # mint -> epoch of last cache write


def _get_price_intel_first(mint: str) -> "Optional[float]":
    """
    Read latest price from sentinuity_intelligence.db (mtm_ticks).
    Falls back to None — caller then uses market_snapshots.
    Cache TTL: 500ms to cut DB reads by ~80% under load.
    Schema: mtm_ticks(mint_address, price_usd, ts_ms, source)
    """
    import time
    now = time.time()

    # Cache hit
    if mint in _price_cache and (now - _price_cache_ts.get(mint, 0)) < 0.5:
        return _price_cache[mint]

    # Intel DB read — use price_usd and ts_ms (actual column names)
    try:
        intel = get_intel_connection()
        row = intel.execute(
            "SELECT price_usd, ts_ms FROM mtm_ticks "
            "WHERE mint_address=? ORDER BY ts_ms DESC LIMIT 1",
            (mint,),
        ).fetchone()
        intel.close()
        if row and row[0] is not None:
            age_sec = (now * 1000 - float(row[1])) / 1000.0
            if age_sec < 120:  # relaxed from 30s — allow up to 120s old ticks
                price = float(row[0])
                _price_cache[mint] = price
                _price_cache_ts[mint] = now
                log.debug(
                    "[MTM_INTEL] mint=%s price=%.10f age=%.0fs",
                    mint[:12], price, age_sec,
                )
                return price
            else:
                log.debug(
                    "[MTM_INTEL_STALE] mint=%s age=%.0fs (>120s threshold)",
                    mint[:12], age_sec,
                )
    except Exception as _e:
        log.warning("[MTM_INTEL_FAIL] mint=%s error=%s", mint[:12], _e)

    return None
# ─────────────────────────────────────────────────────────────────────────────

def get_latest_mtm_price_row(mint: str) -> Optional[dict]:
    import time as _t
    _ip = _get_price_intel_first(mint)
    if _ip is not None:
        return {"observed_price": _ip, "price_updated_at": _t.time()}
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT observed_price, price_updated_at
                FROM market_snapshots
                WHERE mint_address=? AND candidate_state='mtm'
                  AND observed_price IS NOT NULL
                ORDER BY price_updated_at DESC, id DESC LIMIT 1
                """,
                (mint,),
            ).fetchone()
        return dict(row) if row else None
    except Exception:
        return None


def get_last_known_price(mint: str) -> Optional[float]:
    """MTM-scoped price lookup. Intel DB first, fallback to market_snapshots.
    Returns only prices from WS oracle ticks (candidate_state='mtm').
    Prevents qualify-time latched prices from being used as close prices.

    SIGN-OFF FIX 6: Previously unscoped. Now intel-DB-first for freshness.
    Use get_last_known_price_unscoped() only as explicit last resort."""
    _ip = _get_price_intel_first(mint)
    if _ip is not None:
        return _ip
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT observed_price FROM market_snapshots
                WHERE mint_address=? AND candidate_state='mtm'
                  AND observed_price IS NOT NULL AND observed_price > 0
                ORDER BY price_updated_at DESC, id DESC LIMIT 1
                """,
                (mint,),
            ).fetchone()
        return float(row["observed_price"]) if row else None
    except Exception:
        return None


def get_last_known_price_unscoped(mint: str) -> Optional[float]:
    """Unscoped fallback — intel DB first, then any market_snapshots row.
    Only call when get_last_known_price() returns None AND a price is
    absolutely required. Do NOT use as primary close-price source."""
    _ip = _get_price_intel_first(mint)
    if _ip is not None:
        return _ip
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT observed_price FROM market_snapshots
                WHERE mint_address=? AND observed_price IS NOT NULL
                  AND observed_price > 0
                ORDER BY price_updated_at DESC, id DESC LIMIT 1
                """,
                (mint,),
            ).fetchone()
        return float(row["observed_price"]) if row else None
    except Exception:
        return None


def get_best_entry_price(
    mint: str,
    qualify_price: float,
    qualify_ts: float,
) -> tuple[float, str, float]:
    """
    Phase 1: Prevent stale MTM bleed from previous trades.

    Only considers prices newer than the qualification timestamp (qualify_ts).
    This ensures old MTM rows written for a previously closed position on the
    same mint cannot contaminate the entry price of a new position.

    Single-query approach: ORDER BY candidate_state='mtm' first (oracle ticks
    have highest authority), then by price_updated_at DESC. Returns the single
    best row, or falls back to qualify_price with no DB access.

    Returns: (price, source, ts)
      price  — the price to use as entry_price (always a valid float > 0)
      source — 'upgraded' if a fresher price was found, 'qualify' otherwise
      ts     — price_updated_at of the returned price (or qualify_ts if fallback)
    """
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT observed_price, price_updated_at, candidate_state
                FROM market_snapshots
                WHERE mint_address = ?
                  AND observed_price > 0
                  AND price_updated_at >= ?
                  AND candidate_state != 'mtm'
                ORDER BY price_updated_at DESC
                LIMIT 1
                """,
                (mint, qualify_ts),
            ).fetchone()
            if row:
                _p = float(row["observed_price"])
                _t = float(row["price_updated_at"])
                if _p > 0:
                    return _p, "upgraded", _t
    except Exception as e:
        log.error("get_best_entry_price failed mint=%s: %s", mint[:16], e)

    # Fallback: always return a valid price — never None, never zero
    return qualify_price, "qualify", qualify_ts


def get_last_price_ts(mint: str) -> Optional[float]:
    try:
        with get_connection() as conn:
            row = conn.execute(
                """
                SELECT price_updated_at FROM market_snapshots
                WHERE mint_address=? AND candidate_state='mtm'
                  AND observed_price IS NOT NULL AND observed_price > 0
                ORDER BY price_updated_at DESC LIMIT 1
                """,
                (mint,),
            ).fetchone()
        return float(row["price_updated_at"]) if row else None
    except Exception:
        return None


def get_peak_price_since_open(mint: str, opened_at: float) -> Optional[float]:
    try:
        with get_connection() as conn:
            row = conn.execute(
                "SELECT MAX(observed_price) AS peak FROM market_snapshots "
                "WHERE mint_address=? AND candidate_state='mtm' "
                "AND price_updated_at >= ? AND observed_price > 0",
                (mint, opened_at),
            ).fetchone()
        return float(row["peak"]) if row and row["peak"] is not None else None
    except Exception:
        return None


def get_mtm_prices_during_gap(mint: str, from_ts: float, to_ts: float) -> list[dict]:
    try:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT observed_price, price_updated_at
                FROM market_snapshots
                WHERE mint_address=? AND candidate_state='mtm'
                  AND price_updated_at BETWEEN ? AND ?
                  AND observed_price IS NOT NULL AND observed_price > 0
                ORDER BY price_updated_at ASC
                """,
                (mint, from_ts, to_ts),
            ).fetchall()
        return [{"price": float(r["observed_price"]), "ts": float(r["price_updated_at"])}
                for r in rows]
    except Exception as e:
        log.warning("get_mtm_prices_during_gap failed mint=%s: %s", mint, e)
        return []


def fetch_dexscreener_price(mint: str) -> Optional[float]:
    """
    Direct DexScreener fallback when MTM rows are absent.
    Preserves paper_executor fix: pump tokens drop off Jupiter before DexScreener.
    """
    try:
        import requests
        resp = requests.get(
            f"https://api.dexscreener.com/latest/dex/tokens/{mint}",
            timeout=5, headers={"Accept": "application/json"},
        )
        if resp.status_code != 200:
            return None
        pairs = (resp.json() or {}).get("pairs") or []
        sol = [p for p in pairs if str(p.get("chainId", "")).lower() == "solana"]
        if not sol:
            return None
        best = max(sol, key=lambda p: float((p.get("liquidity") or {}).get("usd") or 0))
        px = float(best.get("priceUsd") or 0)
        return px if px > 0 else None
    except Exception:
        return None


# -----------------------------------------------------------------------------
# POSITION MARKING / LATENCY
# -----------------------------------------------------------------------------

def update_position_mark(
    position_id: int,
    current_price: float,
    unrealized_pnl_usd: float,
    marked_at: float,
    source: str = "engine",   # 'oracle' | 'engine' | 'fallback' | 'router-stale'
    router_result: "Optional[dict]" = None,  # price_router result dict, optional
) -> None:
    """
    Write live mark to paper_positions.
    If router_result is provided, also writes live_exec_* columns:
      live_exec_price, live_exec_pct, live_exec_source, live_exec_updated_at,
      live_exec_age_sec, live_exec_confidence, live_exec_can_exit
    This makes update_position_mark the single write point for all mark data.

    EXECUTION TRUTH INVARIANT:
    unrealized_pnl_usd is only written non-zero when ALL conditions are true:
      - router_result is provided
      - router_result["can_execute_exit"] == True
      - router_result["price"] > 0
    Otherwise unrealized_pnl_usd is forced to 0.0 regardless of what caller passed.
    This is the single enforcement point — callers must not bypass it.
    """
    # Enforce execution truth: PnL=0 unless router confirms executable price
    _router_executable = (
        router_result is not None
        and router_result.get("can_execute_exit", False)
        and float(router_result.get("price", 0) or 0) > 0
    )
    if not _router_executable:
        unrealized_pnl_usd = 0.0
    try:
        with get_connection() as conn:
            cols = _get_pp_cols()  # cached — no PRAGMA per tick

            # Pre-fetch entry_price + mint_address in one SELECT
            # (used for live_exec_pct calc and TLE — avoids 2 extra SELECTs)
            _pre = conn.execute(
                "SELECT entry_price, mint_address FROM paper_positions WHERE id=?",
                (position_id,)
            ).fetchone()
            _entry_price  = float(_pre["entry_price"]  or 0) if _pre else 0.0
            _mint_address = str(_pre["mint_address"] or "")  if _pre else ""

            # ── MERGED SINGLE UPDATE ─────────────────────────────────────────
            # Base columns (always written) + live_exec_* columns (when router
            # available) merged into one UPDATE to halve write round-trips.
            _set_parts = [
                "unrealized_pnl_usd=?",
                "last_price=?",
                "last_marked_at=?",
                "highest_price_seen = CASE WHEN COALESCE(highest_price_seen,0) > ? THEN highest_price_seen ELSE ? END",
            ]
            _vals = [unrealized_pnl_usd, current_price, marked_at,
                     current_price, current_price]

            if "mark_source" in cols:
                _set_parts.append("mark_source=?")
                _vals.append(source)

            # Live exec columns — only when router has a price
            _rpct = 0.0
            if router_result is not None and router_result.get("price", 0) > 0:
                _rp  = router_result["price"]
                _rs  = router_result.get("source", source)
                _ra  = router_result.get("age_sec", 9999.0)
                _rc  = router_result.get("confidence", 0.0)
                _rce = 1 if router_result.get("can_execute_exit", False) else 0
                _rpct = (_rp - _entry_price) / _entry_price * 100.0 if _entry_price > 0 else 0.0

                for col, val in [
                    ("live_exec_price",      _rp),
                    ("live_exec_pct",        _rpct),
                    ("live_exec_source",     _rs),
                    ("live_exec_updated_at", marked_at),
                    ("live_exec_age_sec",    _ra),
                    ("live_exec_confidence", _rc),
                    ("live_exec_can_exit",   _rce),
                ]:
                    if col in cols:
                        _set_parts.append(f"{col}=?")
                        _vals.append(val)

            _vals.append(position_id)
            conn.execute(
                f"UPDATE paper_positions SET {', '.join(_set_parts)} WHERE id=?",
                tuple(_vals),
            )

            # TLE event — reuses pre-fetched entry_price + mint_address
            if _TLE_AVAILABLE and router_result and router_result.get("can_execute_exit") and router_result.get("price", 0) > 0:
                try:
                    _tle_mark(conn,
                        position_id=position_id,
                        mint=_mint_address,
                        entry_price=_entry_price,
                        router_result=router_result,
                        pct=_rpct)
                except Exception:
                    pass

            conn.commit()
    except Exception as exc:
        log.warning("update_position_mark failed pos_id=%s price=%s: %s",
                    position_id, current_price, exc)


def measure_write_latency_ms() -> float:
    try:
        start = time.monotonic()
        with get_connection() as conn:
            conn.execute("CREATE TABLE IF NOT EXISTS _latency_probe (ts INTEGER)")
            conn.execute("INSERT INTO _latency_probe VALUES (?)", (int(time.time()),))
            conn.execute("DELETE FROM _latency_probe")
            conn.commit()
        return (time.monotonic() - start) * 1000
    except Exception:
        return 9999.0


# -----------------------------------------------------------------------------
# SOURCE OF TRUTH - DRAWDOWN UPDATE
# -----------------------------------------------------------------------------

def update_drawdown_after_close(conn, pnl_usd: float, pos_size_usd: float) -> None:
    """
    Exponential drawdown memory + tiered brakes.
    Called inside the close_position_canonical transaction (conn already open).

    Tier 1 (>= threshold):        soft brake - halve position size next trade
    Tier 2 (>= threshold - 1.5):  auto-calibrate SL and position size
    Tier 3 (>= threshold - 2.0):  hard stop - DRAWDOWN_HALT_ACTIVE = 1
    """
    try:
        threshold = float(float(get_config_value("DRAWDOWN_HALT_THRESHOLD_PCT", 25.0)))
        current   = float(float(get_config_value("DRAWDOWN_ACCUMULATED_PCT",    0.0)))

        wallet_bal     = get_wallet_balance()
        portfolio_base = max(wallet_bal, pos_size_usd * 4, 1.0)
        loss_pct       = abs(pnl_usd) / portfolio_base * 100

        if pnl_usd >= 0:
            new_acc = round(current * 0.5, 4)                      # win decays memory
        else:
            new_acc = round(current * 0.65 + loss_pct, 4)          # loss compounds

        new_acc = max(0.0, min(new_acc, threshold * 2))
        conn.execute(
            "UPDATE system_config SET value=? WHERE key='DRAWDOWN_ACCUMULATED_PCT'",
            (str(round(new_acc, 4)),),
        )

        tier2 = threshold * 1.5
        tier3 = threshold * 2.0

        if new_acc >= tier3:
            conn.execute(
                "UPDATE system_config SET value='1' WHERE key='DRAWDOWN_HALT_ACTIVE'"
            )
            log.warning("DRAWDOWN TIER 3 HARD STOP - accumulated=%.2f%%", new_acc)
            _log_cognition("HEALTH",
                f"TIER 3 drawdown emergency at {new_acc:.1f}% - hard stop engaged. "
                "Capital protection law invoked.")

        elif new_acc >= tier2:
            current_sl      = float(float(get_config_value("STOP_LOSS_PCT",      10.0)))
            current_pos_pct = float(float(get_config_value("POSITION_SIZE_PCT",  5.0)))
            new_sl          = round(current_sl * 0.75, 2)
            new_pos_pct     = round(current_pos_pct * 0.5, 2)
            conn.execute("UPDATE system_config SET value=? WHERE key='STOP_LOSS_PCT'",
                         (str(new_sl),))
            conn.execute("UPDATE system_config SET value=? WHERE key='POSITION_SIZE_PCT'",
                         (str(new_pos_pct),))
            log.warning(
                "DRAWDOWN TIER 2 AUTO-CALIBRATE - %.2f%% SL %.1f%%-%.1f%% pos %.2f%%-%.2f%%",
                new_acc, current_sl, new_sl, current_pos_pct, new_pos_pct,
            )

        elif new_acc >= threshold:
            conn.execute(
                """
                INSERT INTO system_config (key, value, description) VALUES
                ('DRAWDOWN_SOFT_BRAKE', '1', 'Soft brake - position size halved')
                ON CONFLICT(key) DO UPDATE SET value='1'
                """
            )
            log.warning("DRAWDOWN TIER 1 SOFT BRAKE - accumulated=%.2f%%", new_acc)

        else:
            try:
                conn.execute(
                    "UPDATE system_config SET value='0' WHERE key='DRAWDOWN_SOFT_BRAKE'"
                )
            except Exception:
                pass

    except Exception as e:
        log.warning("update_drawdown_after_close failed: %s", e)


# -----------------------------------------------------------------------------
# SOURCE OF TRUTH - POSITION CLOSURE
# -----------------------------------------------------------------------------

def close_position_canonical(
    position_id: int,
    exit_price: float,
    exit_reason: str,
    *,
    closure_mode: str = "normal",
    force_scratch: bool = False,
    notes_prefix: str = "",
) -> bool:
    """
    THE SINGLE SOURCE OF TRUTH FOR ALL POSITION CLOSURES.

    All closes - normal, reconcile, zombie, manual, infra - route here.
    No other function may write status='CLOSED' or credit the wallet.

    closure_mode: "normal" | "reconcile" | "zombie" | "manual" | "infra"
    force_scratch: True - exit_price forced to entry_price (zombie scratch semantics)

    Returns True on success, False if position not found or already closed.
    """
    position = get_position_by_id_open(position_id)
    if not position:
        return False

    try:
        entry_price  = float(position["entry_price"]      or 0)
        pos_size_usd = float(position["position_size_usd"] or 0)
        quantity     = float(position["quantity"]          or 0)
        token_name   = str(position["token_name"]          or "UNKNOWN")
        mint         = str(position["mint_address"]        or "")

        now = time.time()

        if force_scratch:
            exit_price = entry_price

        # ── PAPER EXIT SLIPPAGE SIMULATION ───────────────────────────────
        # Real pump.fun sells receive 1-4% less due to thin bids + slippage.
        # Apply in paper mode only, never on scratch/zombie exits.
        if not force_scratch and not _is_live_mode():
            try:
                _slip_exit = float(get_config_value("PAPER_SLIPPAGE_EXIT_PCT", 2.5)) / 100.0
                _fee_exit  = float(get_config_value("PAPER_FEE_PER_TX_USD", 0.10))
                exit_price = exit_price * (1.0 - _slip_exit)   # receive less on exit
                pos_size_usd = max(0.0, pos_size_usd - _fee_exit)  # deduct exit fee
            except Exception:
                pass  # never block a close on slippage calculation failure

        # CLOSE PRICE SANITY GUARD - single chokepoint for ALL closes
        # If exit_price > 1000x entry, oracle data is corrupt - force scratch exit
        if entry_price > 0 and exit_price > entry_price * 1000 and not force_scratch:
            log.warning(
                "CLOSE SANITY GUARD: corrupt exit_price=%.10f for %s "
                "(%.1fx entry=%.10f) - forcing scratch exit to protect wallet",
                exit_price, token_name, exit_price / entry_price, entry_price
            )
            exit_price = entry_price  # force scratch - no PnL credited

        pnl_pct = ((exit_price - entry_price) / entry_price) * 100 if entry_price > 0 else 0.0
        pnl_usd = 0.0 if force_scratch else pos_size_usd * (pnl_pct / 100.0)

        # SIGN-OFF FIX 1+5: Clamp pnl_usd BEFORE any DB write so realized_pnl_usd,
        # paper_executions, wallet_write_log, polaris_trade_reviews, and trade_autopsies
        # all record the same clamped value. Previously the clamp only protected
        # wallet_balance while every audit table stored the raw (possibly corrupt) figure.
        # Also recompute pnl_pct from the clamped pnl_usd so the percentage is consistent.
        if not force_scratch:
            _pnl_cap = pos_size_usd
            if pnl_usd > _pnl_cap:
                log.error(
                    "WALLET CLAMP (pre-write): PnL +$%.2f exceeds 100%% of pos_size $%.2f "
                    "for %s pos=%d. Clamping to $%.2f before DB write.",
                    pnl_usd, pos_size_usd, token_name, position_id, _pnl_cap,
                )
                pnl_usd = _pnl_cap
            elif pnl_usd < -_pnl_cap:
                log.error(
                    "WALLET CLAMP (pre-write): PnL -$%.2f exceeds -100%% of pos_size $%.2f "
                    "for %s pos=%d. Clamping to -$%.2f before DB write.",
                    abs(pnl_usd), pos_size_usd, token_name, position_id, _pnl_cap,
                )
                pnl_usd = -_pnl_cap
            # Recompute pct from clamped usd so all tables agree
            pnl_pct = (pnl_usd / pos_size_usd * 100.0) if pos_size_usd > 0 else 0.0

        outcome = "WIN" if pnl_usd > 0 else ("LOSS" if pnl_usd < 0 else "SCRATCH")

        _HALT_REASON_MAP = {
            "TAKE_PROFIT":         "TAKE_PROFIT",
            "STOP_LOSS":           "STOP_LOSS",
            "TRAILING_STOP":       "TRAILING_STOP",
            "TIME_CUT_STAGNANT":   "TIME_CUT_STAGNANT",
            "TIME_CUT":            "TIME_CUT",
            "STALE_WINNER":        "STALE_WINNER",
            "MAX_HOLD_TIME":       "MAX_HOLD",
            "SAFE_RESTART":        "EXECUTOR_JAM",
            "RECONCILE_TP":        "TAKE_PROFIT",
            "RECONCILE_SL":        "STOP_LOSS",
            "RECONCILE_MAX_HOLD":  "MAX_HOLD",
            "RECONCILE_NO_DATA":   "EXECUTOR_JAM",
            "ZOMBIE":              "EXECUTOR_JAM",
            "DRAWDOWN":            "DRAWDOWN_HALT",
            "MANUAL":              "MANUAL",
        }
        reason_upper = str(exit_reason or "").upper()
        halt_reason  = "UNKNOWN"
        for key, tag in _HALT_REASON_MAP.items():
            if reason_upper.startswith(key):
                halt_reason = tag
                break

        is_infra_exit = halt_reason in {"EXECUTOR_JAM", "UNKNOWN"}

        # ── LIVE TRADING: execute real on-chain sell BEFORE paper close ────────
        _live_sig = None
        if _LIVE_TRADING_AVAILABLE and _is_live_mode() and not force_scratch:
            try:
                _ls = _live_sell(mint, quantity, position_id, exit_price)
                if _ls["success"]:
                    _live_sig = _ls.get("tx_sig")
                    log.info("[LIVE_SELL] pos=%d sig=%s", position_id,
                             str(_live_sig or "")[:20])
                    if _live_sig:
                        exit_reason = f"LIVE:{_live_sig[:12]}:{exit_reason}"
                else:
                    log.warning("[LIVE_SELL_FAIL] pos=%d error=%s — closing paper anyway",
                                position_id, _ls.get("error"))
            except Exception as _le:
                log.error("[LIVE_SELL_ERROR] pos=%d: %s — closing paper anyway", position_id, _le)

        with get_connection() as conn:
            # Race guard: re-check OPEN inside transaction
            still_open = conn.execute(
                "SELECT id FROM paper_positions WHERE id=? AND status='OPEN'",
                (position_id,),
            ).fetchone()
            if not still_open:
                return False

            # Preserve live_exec_pct as final_exec_pct so closed-trade reviews
            # can show what the meter was reading at close time.
            _pp_cols_close = {r["name"] for r in conn.execute(
                "PRAGMA table_info(paper_positions)"
            ).fetchall()}
            _fep_set = ", final_exec_pct=?" if "final_exec_pct" in _pp_cols_close else ""
            _fep_val = (pnl_pct,) if _fep_set else ()

            conn.execute(
                f"""
                UPDATE paper_positions
                SET status='CLOSED', exit_price=?, realized_pnl_usd=?,
                    unrealized_pnl_usd=0.0, closed_at=?,
                    last_price=?, last_marked_at=?, exit_reason=?,
                    exit_category=?, win_loss=?{_fep_set}
                WHERE id=?
                """,
                (exit_price, pnl_usd, now, exit_price, now, exit_reason,
                 halt_reason, outcome) + _fep_val + (position_id,),
            )

            conn.execute(
                """
                INSERT INTO paper_executions (
                    position_id, token_name, mint_address,
                    side, price, quantity, notional_usd, value_usd, reason, timestamp
                ) VALUES (?, ?, ?, 'SELL', ?, ?, ?, ?, ?, ?)
                """,
                (position_id, token_name, mint,
                 exit_price, quantity, exit_price * quantity, pnl_usd, exit_reason, now),
            )

            # pnl_usd is already clamped to ±pos_size_usd before this transaction
            # (SIGN-OFF FIX 1+5 — see pre-write clamp above).
            _wallet_delta = pos_size_usd + pnl_usd

            # In live mode: skip paper tracker — real balance synced from chain
            if not _is_live_mode():
                conn.execute(
                    "UPDATE system_state SET wallet_balance = wallet_balance + ? WHERE id=1",
                    (_wallet_delta,),
                )

            # Log every wallet mutation for audit trail
            try:
                conn.execute(
                    """INSERT INTO wallet_write_log
                        (position_id, delta_usd, new_balance, source, token_name, pnl_usd, pnl_pct, timestamp)
                        VALUES (?, ?, (SELECT wallet_balance FROM system_state WHERE id=1), ?, ?, ?, ?, ?)""",
                    (position_id, _wallet_delta, f"CLOSE_{closure_mode}",
                     token_name, pnl_usd, pnl_pct, now),
                )
            except Exception:
                pass  # never block a close on log failure

            autopsy_note = (
                f"{notes_prefix} exit={exit_reason} halt_reason={halt_reason} "
                f"infra={is_infra_exit} pnl_pct={pnl_pct:.2f} mode={closure_mode}"
            ).strip()

            conn.execute(
                """
                INSERT INTO trade_autopsies (
                    position_id, token_name, mint_address,
                    win_loss, realized_pnl_usd, notes, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (position_id, token_name, mint, outcome, pnl_usd, autopsy_note, now),
            )

            # Polaris learning feed - written on every close so Intelligence
            # tab analytics and Polaris win-rate calculations are always current.
            # Wrapped in try/except so analytics failure never blocks the close.
            try:
                hold_secs = now - float(position.get("opened_at") or now)
                # Get coverage metrics for this trade to give Polaris clean signal
                _cov = {}
                if _TLE_AVAILABLE:
                    try:
                        _cov = _tle_coverage(mint,
                            float(position.get("opened_at") or now), now)
                    except Exception:
                        pass
                _exit_validity = "UNKNOWN"
                if _TLE_AVAILABLE and _cov:
                    try:
                        _exit_validity = _tle_validity(
                            exit_price, entry_price, exit_reason, _cov,
                            router_can_execute=False,  # conservative: engine knows if router was used
                        )
                    except Exception:
                        pass
                conn.execute(
                    """
                    INSERT INTO polaris_trade_reviews (
                        position_id, token_name, mint_address,
                        win_loss, exit_category, realized_pnl_usd,
                        pnl_pct, hold_seconds, reviewed_at, polaris_version,
                        tick_count_during_trade, first_tick_delay_sec,
                        max_pct_seen, min_pct_seen,
                        coverage_score, exit_validity
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'executor_v1', ?, ?, ?, ?, ?, ?)
                    """,
                    (position_id, token_name, mint,
                     outcome, halt_reason, pnl_usd,
                     pnl_pct, hold_secs, now,
                     _cov.get("tick_count", 0),
                     _cov.get("first_tick_delay_sec"),
                     _cov.get("max_pct_seen"),
                     _cov.get("min_pct_seen"),
                     _cov.get("coverage_score", 0.0),
                     _exit_validity),
                )
            except Exception:
                pass  # never block a close on analytics write failure

            update_drawdown_after_close(conn, pnl_usd, pos_size_usd)

            # Veto any lingering latched snapshots for this mint
            try:
                conn.execute(
                    """
                    UPDATE market_snapshots
                    SET execution_ready=0, candidate_state='vetoed',
                        quality_reason='POST_CLOSE_VETO'
                    WHERE mint_address=? AND candidate_state IN ('latched', 'pending')
                    """,
                    (mint,),
                )
            except Exception:
                pass

            # Emit TRADE_CLOSED event with full coverage audit.
            # router_can_execute: infer from closure_mode + exit_reason.
            # "normal" mode closes are router-gated — price was executable.
            # "guardian"/"zombie"/"reconcile" may use fallback prices.
            if _TLE_AVAILABLE:
                try:
                    _pr_can_exec = (
                        closure_mode == "normal"
                        and not force_scratch
                        and exit_price != entry_price
                    )
                    _tle_closed(conn,
                        position_id=position_id, mint=mint,
                        entry_price=entry_price, exit_price=exit_price,
                        realized_pnl=pnl_usd, exit_reason=exit_reason,
                        hold_seconds=now - float(position.get("opened_at") or now),
                        opened_at=float(position.get("opened_at") or now),
                        router_can_execute=_pr_can_exec,
                    )
                except Exception:
                    pass

            conn.commit()

        # Clear trail-logged flag so future positions are not silently suppressed
        _trail_logged_positions.discard(position_id)

        log.info(
            "CLOSED pos=%d %s mode=%s PnL=%+.4f USD (%+.2f%%) reason=%s",
            position_id, outcome, closure_mode, pnl_usd, pnl_pct, exit_reason,
        )

        # Cognition messages by exit type
        if "STOP_LOSS" in exit_reason:
            _log_cognition(token_name,
                f"Circuit breaker tripped. Stop-loss at {pnl_pct:.1f}% on {token_name}. "
                f"Capital returned: ${pos_size_usd + pnl_usd:.2f}.")
        elif "TAKE_PROFIT" in exit_reason:
            _log_cognition(token_name,
                f"Take profit harvested at {pnl_pct:.1f}% on {token_name}. "
                f"Extracted ${pnl_usd:.4f} USD. Sovereign gain secured.")
        elif "TRAILING_STOP" in exit_reason:
            _log_cognition(token_name,
                f"Trailing stop executed on {token_name} at {pnl_pct:.1f}%.")
        elif closure_mode == "reconcile":
            _log_cognition(token_name,
                f"Reconciler closed {token_name} {outcome} at {pnl_pct:+.1f}% "
                f"(gap closure). Capital returned: ${pos_size_usd + pnl_usd:.2f}.",
                meta={"reason": exit_reason, "pnl_usd": round(pnl_usd, 4)})
        elif closure_mode == "zombie":
            _log_cognition(token_name,
                f"Zombie position {token_name} closed "
                f"({'at scratch' if force_scratch else 'best available price'}). "
                f"Slot freed. Reason: {exit_reason}. "
                f"Capital returned: ${pos_size_usd + pnl_usd:.2f}.",
                meta={"position_id": position_id, "pnl_usd": pnl_usd})
        else:
            _log_cognition(token_name,
                f"Position {position_id} closed {outcome}. "
                f"PnL={pnl_usd:+.4f} USD ({pnl_pct:+.2f}%). Reason: {exit_reason}")

        update_heartbeat(SERVICE_NAME, "ALIVE",
            f"closed pos={position_id} {outcome} pnl={pnl_usd:+.4f}",
            work_processed=1, last_success_at=now)

        # Update momentum gate audit row if one exists for this position
        try:
            _mg_outcome = (
                "WIN"  if pnl_pct > 0 or any(x in exit_reason for x in ("TAKE_PROFIT", "TRAIL"))
                else "LOSS"
            )
            with get_connection() as _mg_close:
                _mg_close.execute("""
                    UPDATE momentum_gate_audit
                    SET reviewed_at      = ?,
                        eventual_pnl_pct = ?,
                        eventual_outcome = ?,
                        exit_reason      = ?
                    WHERE position_id = ?
                """, (now, round(pnl_pct, 4), _mg_outcome, exit_reason, position_id))
                _mg_close.commit()
        except Exception:
            pass

        # ── TAX ALLOCATION — on profitable closes only ────────────────────────
        # Fire-and-forget: never interrupts close, never raises.
        # Allocates virtual tax reserve from realized profit.
        if pnl_usd > 0 and not force_scratch:
            try:
                from services.tax_allocator import allocate_tax as _alloc_tax
                _alloc_tax(position_id, pnl_usd, token_name)
            except Exception:
                pass  # tax allocation is observational — never blocks close

        return True

    except Exception as e:
        log.exception("close_position_canonical failed pos=%d: %s", position_id, e)
        return False


# Legacy shim - preserves any external call sites expecting the old signature
def close_position(position_id: int, exit_price: float, exit_reason: str) -> None:
    close_position_canonical(position_id, exit_price, exit_reason, closure_mode="normal")


def momentum_gate_stats() -> dict:
    """
    Return momentum gate shadow statistics.
    Run periodically to evaluate Phase 2 promotion readiness.

    Promotion criteria (ChatGPT directive):
      - false_negatives < 10-15%   (veto + WIN — cases we would have missed)
      - true_negatives high         (veto + LOSS — cases we correctly avoided)
      - avg_pnl_allowed > avg_pnl_vetoed
      - payoff ratio remains intact
    """
    try:
        with get_connection() as conn:
            row = conn.execute("""
                SELECT
                    COUNT(*)                                                         AS total,
                    SUM(CASE WHEN would_veto=1 THEN 1 ELSE 0 END)                   AS vetoed,
                    SUM(CASE WHEN would_veto=1 AND eventual_outcome='WIN'  THEN 1 ELSE 0 END) AS false_negatives,
                    SUM(CASE WHEN would_veto=1 AND eventual_outcome='LOSS' THEN 1 ELSE 0 END) AS true_negatives,
                    SUM(CASE WHEN would_veto=0 AND eventual_outcome='WIN'  THEN 1 ELSE 0 END) AS true_positives,
                    SUM(CASE WHEN would_veto=0 AND eventual_outcome='LOSS' THEN 1 ELSE 0 END) AS false_positives,
                    AVG(CASE WHEN would_veto=0 THEN eventual_pnl_pct END)            AS avg_pnl_allowed,
                    AVG(CASE WHEN would_veto=1 THEN eventual_pnl_pct END)            AS avg_pnl_vetoed
                FROM momentum_gate_audit
                WHERE reviewed_at IS NOT NULL
            """).fetchone()
            if row:
                stats = dict(row)
                total    = stats.get("total") or 0
                vetoed   = stats.get("vetoed") or 0
                fn       = stats.get("false_negatives") or 0
                fn_rate  = (fn / vetoed * 100) if vetoed > 0 else 0
                stats["false_negative_rate_pct"] = round(fn_rate, 1)
                promote  = (
                    total >= 50 and
                    fn_rate < 15 and
                    (stats.get("avg_pnl_allowed") or 0) > (stats.get("avg_pnl_vetoed") or 0)
                )
                stats["ready_for_phase_2"] = promote
                return stats
    except Exception as e:
        log.debug("momentum_gate_stats failed: %s", e)
    return {}


# -----------------------------------------------------------------------------
# ENTRY SCANNER
# -----------------------------------------------------------------------------

def scan_for_entries() -> int:
    """
    Scan market_snapshots for latched signals and open paper positions.
    Full original logic from paper_executor.py - no changes to gate order or sizing.
    Returns count of new positions opened this cycle.
    """
    opened = 0

    # Gate 0: drawdown hard halt
    halt = str(str(get_config_value("DRAWDOWN_HALT_ACTIVE", "0"))).strip()
    if halt == "1":
        pct = str(get_config_value("DRAWDOWN_ACCUMULATED_PCT", "0.0"))
        log.info("ENTRY SCAN SKIPPED - drawdown halt active (%s%%)", pct)
        return 0

    # ===============================
    # ORACLE LIVENESS — HARD FIX V2
    # ===============================
    # Reads MAX(ts_ms) from sentinuity_intelligence.db (shared between processes).
    # The old in-memory oracle_last_write_age() always returned 9999 because
    # ws_price_oracle runs in a separate process. This is the permanent fix.
    _oracle_gate_sec = float(get_config_value("ORACLE_LIVENESS_GATE_SEC", 300.0))

    def _get_oracle_age_sec():
        try:
            import sqlite3 as _sq3, os as _os, time as _time
            _idb_path = _os.path.join(
                _os.path.dirname(_os.path.dirname(__file__)),
                "sentinuity_intelligence.db"
            )
            _ic = _sq3.connect(_idb_path, timeout=2)
            _latest = _ic.execute("SELECT MAX(ts_ms) FROM mtm_ticks").fetchone()[0]
            _ic.close()
            if not _latest:
                return 9999.0
            return _time.time() - (_latest / 1000.0)
        except Exception as e:
            log.warning("[ORACLE AGE ERROR] %s", e)
            return 0.0  # fail-open -- never block trading on DB error

    _oracle_age = _get_oracle_age_sec()
    log.info("[ORACLE AGE] %.1fs (gate=%.0fs)", _oracle_age, _oracle_gate_sec)

    if _oracle_age > _oracle_gate_sec:
        _current_open = count_open_positions()
        if _current_open > 0:
            log.warning(
                "ENTRY SCAN BLOCKED - oracle stale %.1fs (gate=%.0fs) with %d open",
                _oracle_age, _oracle_gate_sec, _current_open,
            )
            return 0
    # Gate passed (or no open positions)

    # Gate 1: latency probe (cached, re-probed at most once per minute)
    limit_ms = float(float(get_config_value("EXECUTOR_WRITE_LATENCY_LIMIT_MS", 10000.0)))
    _lc = getattr(scan_for_entries, "_latency_cache", {"ms": 0.0, "ts": 0.0})
    scan_for_entries._latency_cache = _lc
    _now_ts = time.time()
    if _now_ts - _lc["ts"] > 60:
        _lc["ms"] = measure_write_latency_ms()
        _lc["ts"] = _now_ts

    latency      = float(_lc["ms"] or 0.0)
    degraded_mode = latency > limit_ms
    if degraded_mode:
        log.warning(
            "ENTRY SCAN DEGRADED - latency %.0fms > %.0fms; proceeding cautiously",
            latency, limit_ms,
        )

    # Gate 2: max open positions
    max_pos = int(int(get_config_value("EXECUTOR_MAX_OPEN_POSITIONS", MAX_OPEN_POSITIONS)))
    if count_open_positions() >= max_pos:
        return 0

    # Gate 3: wallet balance
    balance = get_wallet_balance()
    if balance <= 0:
        log.warning("ENTRY SCAN BLOCKED - wallet balance zero or negative")
        return 0

    # Position sizing
    pos_pct      = float(float(get_config_value("POSITION_SIZE_PCT", 5.0)))
    pos_size_usd = float(float(get_config_value("POSITION_SIZE_USD", 25.0)))
    if pos_pct > 0:
        pos_size_usd = round(balance * (pos_pct / 100.0), 2)
    pos_size_usd = max(5.0, min(pos_size_usd, balance * 0.25))
    # PAPER HARD CAP: never open more than $500 per position regardless of wallet
    _max_paper = float(get_config_value("MAX_PAPER_POSITION_USD", 500.0))
    if pos_size_usd > _max_paper:
        log.warning("POSITION SIZE CAP: $%.2f capped to $%.2f", pos_size_usd, _max_paper)
        pos_size_usd = _max_paper

    soft_brake = str(str(get_config_value("DRAWDOWN_SOFT_BRAKE", "0"))).strip()
    if soft_brake == "1":
        pos_size_usd = max(5.0, round(pos_size_usd * 0.5, 2))
        log.info("SOFT BRAKE ACTIVE - position size halved to $%.2f", pos_size_usd)

    fetch_limit = 25  # always scan full candidate pool; degraded_mode limits opens, not inspections

    try:
        with get_connection() as conn:
            rows = conn.execute(
                """
                SELECT id, mint_address, token_name, observed_price, price_updated_at,
                       COALESCE(created_at, timestamp, price_updated_at, 0) AS created_at
                FROM market_snapshots
                WHERE latched=1 AND execution_ready=1
                  AND candidate_state='latched'
                  AND observed_price IS NOT NULL AND observed_price > 0
                  AND COALESCE(tx_hash, '') NOT LIKE 'mtm:%'
                  AND (? - COALESCE(created_at, timestamp, price_updated_at, 0)) <= ?
                ORDER BY
                    COALESCE(created_at, timestamp, price_updated_at, 0) DESC,
                    price_updated_at DESC,
                    id DESC
                LIMIT ?
                """,
                (time.time(), 1800, fetch_limit),  # 1800s loose SQL prefilter — Python hard gate enforces exact max_signal_age below
            ).fetchall()
            # Note: SQL prefilter uses 10x the Python gate as a loose first pass.
            # The Python hard gate below enforces the exact max_signal_age.
            # Using 10x in SQL avoids rejecting tokens whose created_at is slightly
            # mis-timestamped while still preventing ancient backlog from hitting Python.
    except Exception as e:
        log.warning("Entry scan read failed: %s", e)
        return 0

    tp_pct        = float(float(get_config_value("TAKE_PROFIT_PCT",           25.0)))
    sl_pct        = float(float(get_config_value("STOP_LOSS_PCT",             10.0)))
    max_price_age  = float(float(get_config_value("EXECUTOR_MAX_PRICE_AGE_SEC", 300.0)))
    # 300s: DexScreener prices written at qualification time are the primary source
    # for pre-graduation pump.fun tokens. Oracle (Jupiter) cannot always refresh them.
    # 60s was killing entries because the qualify→latch→execute path takes 30-90s
    # and the price was written at qualify time. 300s gives a realistic trading window.
    # GUILLOTINE: signal age gate — independent of price freshness.
    # price_age measures how old the PRICE is; signal_age measures how old the SIGNAL is.
    # A token qualified 29 minutes ago can have a fresh oracle price but zero momentum edge.
    # Default 600s — matches SIGNAL_TIER1_MAX_AGE_SEC. Pipeline latency (discovery
    # → ingest → qualify → price → supervisor → latch) is already 30-90s minimum.
    # 15s default was killing every signal before it could reach execution.
    # EXECUTOR_MAX_SIGNAL_AGE_SEC in DB overrides this.
    max_signal_age = float(float(get_config_value("EXECUTOR_MAX_SIGNAL_AGE_SEC", 600.0)))

    mints_opened_this_batch: set = set()
    for row in rows:
        try:
            snap_id     = int(row["id"])
            mint        = str(row["mint_address"] or "")
            token_name  = str(row["token_name"] or mint or "UNKNOWN")[:20]
            # Entry price: observed_price from latched snapshot only.
            # last_price/current_price are not selected by this query — do not reference them.
            entry_price = float(row["observed_price"] or 0)
            price_age   = time.time() - float(row["price_updated_at"] or 0)

            # GUILLOTINE: signal age hard gate — fires before any other per-row logic.
            # Measures how old the SIGNAL is (time since token was discovered/qualified),
            # independent of price freshness. Old signal = momentum edge gone regardless
            # of how fresh the oracle price is. Non-bypassable capital protection gate.
            now_ts     = time.time()
            created_ts = float(row["created_at"] or 0)
            signal_age = now_ts - created_ts if created_ts > 0 else float("inf")

            if signal_age > max_signal_age:
                log.warning(
                    "EXECUTION BLOCKED — SIGNAL TOO OLD snap=%d %s "
                    "signal_age=%.2fs (max=%.0fs) — momentum edge expired",
                    snap_id, mint[:16], signal_age, max_signal_age,
                )
                with get_connection() as conn:
                    conn.execute(
                        """
                        UPDATE market_snapshots SET execution_ready=0,
                            candidate_state='vetoed',
                            quality_reason=?
                        WHERE id=?
                        """,
                        (f"SIGNAL_TOO_OLD_AT_EXEC_{int(signal_age)}s", snap_id),
                    )
                    conn.commit()
                continue

            # BATCH DEDUP: skip if same mint already opened this scan cycle
            if mint in mints_opened_this_batch:
                log.debug("BATCH DEDUP: skip %s", mint[:16])
                continue

            if not entry_price or not mint:
                continue

            # HARD STALE GUARD — NON-BYPASSABLE (belt-and-suspenders with SQL filter above)
            # Any signal whose price is older than max_price_age is vetoed here
            # regardless of what the qualifier or supervisor wrote to quality_reason.
            # This is the final gate before capital is deployed.
            if price_age > max_price_age:
                log.warning(
                    "EXECUTION BLOCKED — STALE PRICE snap=%d %s age=%.0fs (max=%.0fs)",
                    snap_id, mint[:16], price_age, max_price_age,
                )
                with get_connection() as conn:
                    conn.execute(
                        """
                        UPDATE market_snapshots SET execution_ready=0,
                            candidate_state='vetoed',
                            quality_reason=COALESCE(NULLIF(quality_reason,''),'STALE_PRICE_AT_EXEC')
                        WHERE id=?
                        """,
                        (snap_id,),
                    )
                    conn.commit()
                continue

            # Re-check before each open
            if count_open_positions() >= max_pos:
                break

            # Blacklist gate
            with get_connection() as conn:
                bl = conn.execute(
                    "SELECT 1 FROM mint_blacklist WHERE mint_address=?", (mint,)
                ).fetchone()
                if bl:
                    conn.execute(
                        """
                        UPDATE market_snapshots SET execution_ready=0,
                            candidate_state='vetoed', quality_reason='BLACKLISTED'
                        WHERE id=?
                        """,
                        (snap_id,),
                    )
                    conn.commit()
                    continue

            # Explicit OPEN guard: never open second position for same mint
            with get_connection() as conn:
                _open_exists = conn.execute(
                    "SELECT 1 FROM paper_positions "
                    "WHERE mint_address=? AND status='OPEN' LIMIT 1",
                    (mint,),
                ).fetchone()
                if _open_exists:
                    conn.execute(
                        "UPDATE market_snapshots SET execution_ready=0, "
                        "candidate_state='vetoed', quality_reason='OPEN_POSITION_EXISTS' WHERE id=?",
                        (snap_id,),
                    )
                    conn.commit()
                    continue

            # Reentry gate — configurable via REENTRY_COOLDOWN_SECONDS (default 300s).
            # 0 = only block if position is currently OPEN (paper trading mode).
            # >0 = block if closed within N seconds (production mode).
            # The old permanent "never trade same mint twice" gate was replaced because
            # pump.fun tokens recycle constantly and a full history ban exhausts the
            # tradeable universe after a few hundred paper trades.
            _reentry_cooldown = float(get_config_value("REENTRY_COOLDOWN_SECONDS", 0.0))
            with get_connection() as conn:
                if _reentry_cooldown > 0:
                    # Production mode: block if traded within cooldown window
                    _cutoff = time.time() - _reentry_cooldown
                    _recent = conn.execute(
                        "SELECT 1 FROM paper_positions "
                        "WHERE mint_address=? AND COALESCE(closed_at, opened_at) > ? LIMIT 1",
                        (mint, _cutoff),
                    ).fetchone()
                    if _recent:
                        conn.execute(
                            "UPDATE market_snapshots SET execution_ready=0, "
                            "candidate_state='vetoed', quality_reason='REENTRY_COOLDOWN' "
                            "WHERE id=?", (snap_id,),
                        )
                        conn.commit()
                        continue
                else:
                    # Paper trading mode (default): only block if OPEN position exists
                    _open_exists = conn.execute(
                        "SELECT 1 FROM paper_positions "
                        "WHERE mint_address=? AND status='OPEN' LIMIT 1",
                        (mint,),
                    ).fetchone()
                    if _open_exists:
                        conn.execute(
                            "UPDATE market_snapshots SET execution_ready=0, "
                            "candidate_state='vetoed', quality_reason='OPEN_POSITION_EXISTS' "
                            "WHERE id=?", (snap_id,),
                        )
                        conn.commit()
                        continue

            # Curve completion re-check - token may have graduated since qualify time.
            # Fail-open: RPC error does NOT block entry (same policy as market_intelligence).
            # This closes the window between qualify-time gate and execution-time open.
            if _CURVE_CHECK_AVAILABLE:
                try:
                    _curve = _get_curve_progress(mint)
                    if _curve.get("complete") and not _curve.get("error"):
                        log.info(
                            "CURVE GRADUATED at open time - vetoing snap=%s mint=%s",
                            snap_id, mint[:16],
                        )
                        with get_connection() as conn:
                            conn.execute(
                                """UPDATE market_snapshots SET execution_ready=0,
                                       candidate_state='vetoed',
                                       quality_reason='CURVE_COMPLETE_AT_OPEN'
                                   WHERE id=?""",
                                (snap_id,),
                            )
                            conn.commit()
                        continue
                except Exception as _ce:
                    log.debug(
                        "Curve re-check skipped (RPC err) snap=%s mint=%s: %s",
                        snap_id, mint[:16], _ce,
                    )

            now = time.time()

            # ── PHASE A TEMPORAL GATE — FINAL ENFORCEMENT BEFORE OPEN ─────
            # Re-read live snapshot. Recompute temporal truth from raw timestamps.
            # Phase A.1 thresholds (NORTH_STAR.md + sync directive):
            #   signal_age   <= 45s   (momentum clock — unchanged)
            #   price_age    <= 45s   (raised from 20s to match oracle cadence)
            #   freshness_score >= 0.85 (recomputed, not stored)
            #   active_cognition = 1
            try:
                with get_connection() as _tg_conn:
                    _tg_row = _tg_conn.execute(
                        """SELECT price_updated_at, created_at, first_seen_at,
                                  timestamp, active_cognition, freshness_score,
                                  tier, token_name
                           FROM market_snapshots WHERE id=?""",
                        (snap_id,)
                    ).fetchone()

                if _tg_row:
                    import math as _math, datetime as _dt

                    def _pts_exec(v) -> float:
                        if not v: return 0.0
                        try: return float(v)
                        except Exception: pass
                        try:
                            s = str(v).strip()
                            for _fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S",
                                         "%Y-%m-%d %H:%M:%S.%f"):
                                try: return _dt.datetime.strptime(s, _fmt).timestamp()
                                except ValueError: continue
                        except Exception: pass
                        return 0.0

                    _now_gate = time.time()

                    # Signal age: use latched_at (supervisor's HOT decision timestamp)
                    # as the reservation anchor. Falls back to price_updated_at then
                    # discovery timestamps. This measures "time since supervisor approved"
                    # not "time since discovery" — eliminates double-gating pipeline latency.
                    _latch_ts = (
                        _pts_exec(_tg_row.get("latched_at"))
                        or _pts_exec(_tg_row["price_updated_at"])
                        or max(
                            _pts_exec(_tg_row["created_at"]),
                            _pts_exec(_tg_row["first_seen_at"]),
                            _pts_exec(_tg_row["timestamp"]),
                        )
                    )
                    _gate_signal_age = (_now_gate - _latch_ts) if _latch_ts > 0 else float("inf")

                    # Price age: oracle write timestamp
                    _price_ts_gate  = _pts_exec(_tg_row["price_updated_at"])
                    _gate_price_age = (_now_gate - _price_ts_gate) if _price_ts_gate > 0 else float("inf")

                    # Freshness: recomputed from signal age. Half-life 276.89s = 0.85 at 45s.
                    _gate_freshness = round(max(0.0, _math.exp(-_gate_signal_age / 276.89)), 4)

                    # active_cognition: live value
                    _gate_active = int(_tg_row["active_cognition"] or 0)
                    _gate_tier   = str(_tg_row["tier"] or "UNKNOWN")

                    # Always log temporal state for diagnostics
                    log.debug(
                        "PHASE_A_GATE snap=%d %s signal_age=%.1fs price_age=%.1fs "
                        "freshness=%.4f active=%d tier=%s",
                        snap_id, mint[:16], _gate_signal_age, _gate_price_age,
                        _gate_freshness, _gate_active, _gate_tier,
                    )

                    _phase_a_fail = None
                    # Phase A.1: signal_age gate is configurable to account for
                    # pipeline latency (discovery→qualify→latch→executor = 35-95s).
                    # Default 120s — supervisor already validated HOT at latch time.
                    # Set EXECUTOR_PHASE_A_MAX_SIGNAL_AGE in system_config to tune.
                    _phase_a_signal_max = float(get_config_value("EXECUTOR_PHASE_A_MAX_SIGNAL_AGE", 120.0))
                    if _gate_signal_age > _phase_a_signal_max:
                        _phase_a_fail = f"SIGNAL_TOO_OLD_AT_EXEC_{int(_gate_signal_age)}s"
                    elif _gate_price_age > 45.0:
                        # Phase A.1: raised to 45s — oracle cadence sync
                        _phase_a_fail = f"PRICE_TOO_OLD_AT_EXEC_{int(_gate_price_age)}s"
                    elif _gate_freshness < 0.85:
                        _phase_a_fail = f"FRESHNESS_LOW_AT_EXEC_{_gate_freshness:.4f}"
                    elif _gate_active != 1:
                        _phase_a_fail = "ACTIVE_COGNITION_ZERO_AT_EXEC"

                    if _phase_a_fail:
                        log.warning(
                            "PHASE_A_BLOCKED snap=%d %s reason=%s "
                            "signal_age=%.1fs price_age=%.1fs freshness=%.4f "
                            "active=%d tier=%s",
                            snap_id, mint[:16], _phase_a_fail,
                            _gate_signal_age, _gate_price_age, _gate_freshness,
                            _gate_active, _gate_tier,
                        )
                        with get_connection() as _tg_veto:
                            _tg_veto.execute(
                                """UPDATE market_snapshots SET execution_ready=0,
                                       candidate_state='EXECUTOR_STALE_GATE',
                                       quality_reason=?
                                   WHERE id=?""",
                                (_phase_a_fail, snap_id),
                            )
                            _tg_veto.commit()
                        continue
                    else:
                        log.info(
                            "PHASE_A_PASS snap=%d %s signal_age=%.1fs "
                            "price_age=%.1fs freshness=%.4f tier=%s — opening",
                            snap_id, mint[:16], _gate_signal_age,
                            _gate_price_age, _gate_freshness, _gate_tier,
                        )
            except Exception as _tg_err:
                log.debug("Phase A temporal gate error snap=%d: %s", snap_id, _tg_err)

            # ── PHASE 1: ENTRY PRICE SCOPING ──────────────────────────────
            # Compute qualify_ts from price_age (already calculated above as
            # time.time() - row["price_updated_at"]). Reconstructing it here
            # avoids re-reading the row and keeps the calculation consistent.
            _qualify_price = float(row["observed_price"] or 0)
            _qualify_ts    = now - price_age  # == float(row["price_updated_at"])

            final_price, price_source, price_ts = get_best_entry_price(
                mint,
                _qualify_price,
                _qualify_ts,
            )

            # get_best_entry_price always returns a valid price (never None/0).
            # Sanity check: if something impossible slips through, fall back hard.
            if not final_price or final_price <= 0:
                final_price  = _qualify_price
                price_source = "qualify"
                price_ts     = _qualify_ts

            if not final_price or final_price <= 0:
                print(f"[EXECUTION SKIP] Invalid price in router result for {row['mint_address']} (qualify={_qualify_price})")
                continue

            entry_price = final_price
            price_age   = now - price_ts  # recalculate age against final price ts

            # ── MOMENTUM GATE — SHADOW PHASE (data collection, no blocking) ──
            # ChatGPT directive May 14 2026: measure before committing capital.
            # MOMENTUM_GATE_SHADOW_ONLY=1 → log only, never block
            # MOMENTUM_GATE_ENABLED=1 + SHADOW_ONLY=0 → hard veto
            _mg_shadow   = int(get_config_value("MOMENTUM_GATE_SHADOW_ONLY", 1))
            _mg_enabled  = int(get_config_value("MOMENTUM_GATE_ENABLED", 0))
            _mg_qual_pct = float(get_config_value("MOMENTUM_FROM_QUAL_PCT", 2.0))
            _mg_st_pct   = float(get_config_value("MOMENTUM_SHORT_TERM_PCT", 1.5))

            _mg_qual_price  = float(_qualify_price or entry_price)
            _mg_latest      = _get_price_intel_first(mint) or entry_price
            _mg_audit_id    = None

            _mg_move_qual = (
                ((_mg_latest / _mg_qual_price) - 1.0) * 100.0
                if _mg_qual_price > 0 and _mg_latest > 0 else 0.0
            )
            # Short-term: use same value unless cached price available
            _mg_move_st = _mg_move_qual

            _mg_would_veto = int(
                _mg_move_qual < _mg_qual_pct and _mg_move_st < _mg_st_pct
            )

            # Write audit row for every candidate
            try:
                with get_connection() as _mg_conn:
                    _mg_cur = _mg_conn.execute("""
                        INSERT INTO momentum_gate_audit
                            (snapshot_id, mint_address, token_name, qual_price,
                             latest_price, move_from_qual_pct, move_short_term_pct,
                             would_veto, entered, created_at)
                        VALUES (?,?,?,?,?,?,?,?,0,?)
                    """, (snap_id, mint, token_name, _mg_qual_price,
                          _mg_latest, round(_mg_move_qual, 4),
                          round(_mg_move_st, 4), _mg_would_veto, now))
                    _mg_audit_id = _mg_cur.lastrowid
                    _mg_conn.commit()
            except Exception as _mg_err:
                log.debug("momentum_gate_audit insert failed: %s", _mg_err)

            if _mg_would_veto:
                log.info(
                    "MOMENTUM_GATE_SHADOW_VETO snap=%d %s move_qual=%.2f%% move_st=%.2f%%",
                    snap_id, mint[:16], _mg_move_qual, _mg_move_st,
                )
                _log_cognition(token_name,
                    f"MOMENTUM_GATE_SHADOW_VETO: move_from_qual={_mg_move_qual:.2f}% "
                    f"threshold={_mg_qual_pct}% — would have blocked entry")
                # Hard gate: only activate if ENABLED and NOT shadow-only
                if _mg_enabled and not _mg_shadow:
                    log.warning("MOMENTUM_GATE_HARD_VETO snap=%d %s — skipping entry",
                                snap_id, mint[:16])
                    continue
            # ── END MOMENTUM GATE ──────────────────────────────────────────
            quantity = (pos_size_usd / entry_price) if entry_price > 0 else 0
            # QUANTITY GUARD: reject absurd quantities from micro-priced tokens
            if quantity > 1_000_000_000:
                log.warning("QUANTITY GUARD: snap=%d qty=%.0f exceeds 1B "
                             "(entry=%.12f) skipping", snap_id, quantity, entry_price)
                continue

            # CLAIM this snapshot for execution (prevents guardian from resetting it
            # as orphaned while we are in the process of opening the position).
            try:
                with get_connection() as conn:
                    conn.execute(
                        "UPDATE market_snapshots SET latch_claimed_until=? WHERE id=?",
                        (now + 30, snap_id),
                    )
                    conn.commit()
            except Exception:
                pass  # non-blocking - open proceeds regardless

            print(f"[EXECUTION ATTEMPT] mint={row['mint_address']} price={entry_price}")

            # ── PAPER SLIPPAGE SIMULATION ─────────────────────────────────
            # Real pump.fun buys via Jupiter cost 0.5-2.5% slippage + fees.
            # Apply in paper mode only so paper results reflect live reality.
            if not _is_live_mode():
                _slip_entry = float(get_config_value("PAPER_SLIPPAGE_ENTRY_PCT", 1.5)) / 100.0
                _fee_entry  = float(get_config_value("PAPER_FEE_PER_TX_USD", 0.10))
                entry_price = entry_price * (1.0 + _slip_entry)   # pay more on entry
                pos_size_usd = pos_size_usd + _fee_entry           # deduct tx fee
                quantity = pos_size_usd / entry_price if entry_price > 0 else quantity

            with get_connection() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO paper_positions (
                        token_name, mint_address, status,
                        entry_price, quantity, position_size_usd,
                        take_profit_pct, stop_loss_pct,
                        realized_pnl_usd, unrealized_pnl_usd, opened_at,
                        last_price, last_marked_at,
                        entry_price_source, entry_price_ts
                    ) VALUES (?, ?, 'OPEN', ?, ?, ?, ?, ?, 0.0, 0.0, ?, ?, ?, ?, ?)
                    """,
                    (token_name, mint, entry_price, quantity, pos_size_usd,
                     tp_pct, sl_pct, now, entry_price, now,
                     price_source, price_ts),
                )
                position_id = cur.lastrowid
                mints_opened_this_batch.add(mint)

                # Update momentum audit row — mark entered=1 with position_id
                if _mg_audit_id:
                    try:
                        conn.execute(
                            "UPDATE momentum_gate_audit SET entered=1, position_id=? WHERE id=?",
                            (position_id, _mg_audit_id),
                        )
                    except Exception:
                        pass

                conn.execute(
                    """
                    INSERT INTO paper_executions (
                        position_id, token_name, mint_address,
                        side, price, quantity, notional_usd, value_usd, reason, timestamp
                    ) VALUES (?, ?, ?, 'BUY', ?, ?, ?, ?, 'ENTRY', ?)
                    """,
                    (position_id, token_name, mint,
                     entry_price, quantity, pos_size_usd, pos_size_usd, now),
                )

                # In live mode: skip paper tracker — real balance synced from chain
                if not _is_live_mode():
                    conn.execute(
                        "UPDATE system_state SET wallet_balance = wallet_balance - ? WHERE id=1",
                        (pos_size_usd,),
                    )

                # Log entry wallet debit
                try:
                    conn.execute(
                        """INSERT INTO wallet_write_log
                            (position_id, delta_usd, new_balance, source, token_name, pnl_usd, pnl_pct, timestamp)
                            VALUES (?, ?, (SELECT wallet_balance FROM system_state WHERE id=1), 'ENTRY', ?, 0.0, 0.0, ?)""",
                        (position_id, -pos_size_usd, token_name, now),
                    )
                except Exception:
                    pass  # never block an entry on log failure

                conn.execute(
                    "UPDATE market_snapshots SET execution_ready=2, candidate_state='executed', latched=0 WHERE id=?",
                    (snap_id,),
                )
                # Emit TRADE_OPENED event into lifecycle spine
                if _TLE_AVAILABLE:
                    try:
                        _tle_opened(conn,
                            position_id=position_id, mint=mint,
                            entry_price=entry_price, pos_size_usd=pos_size_usd,
                            source=price_source)
                    except Exception:
                        pass
                conn.commit()

            # ── LIVE TRADING: execute real on-chain buy ─────────────────────
            if _LIVE_TRADING_AVAILABLE and _is_live_mode():
                try:
                    _lr = _live_buy(mint, pos_size_usd, entry_price, position_id)
                    if _lr["success"]:
                        log.info("[LIVE_BUY] pos=%d sig=%s", position_id,
                                 str(_lr.get("tx_sig",""))[:20])
                    else:
                        log.warning("[LIVE_BUY_FAIL] pos=%d error=%s mode=%s",
                                    position_id, _lr.get("error"), _lr.get("mode"))
                except Exception as _le:
                    log.error("[LIVE_BUY_ERROR] pos=%d: %s", position_id, _le)

            # IMMEDIATE ORACLE SUBSCRIPTION — fired AFTER commit so the position
            # row exists in paper_positions when the oracle's _get_open_mints()
            # poll next runs. Previously this fired before commit so the 1s fallback
            # poll could miss the mint on its first cycle if _force_subscribe()
            # failed silently (WS not yet connected). Moving post-commit closes
            # the race: position is in DB before oracle is asked to track it.
            try:
                _oracle_notify_mint(mint)
            except Exception:
                pass  # never block — oracle will pick up via 1s poll if this fails

            # PRICE BOOTSTRAP: immediately attempt a router price read so the meter
            # has a live value within ~1s of open rather than waiting for the oracle's
            # next write cycle (up to 2s for open mints after Patch A).
            # If router returns nothing, live_exec_* stays NULL — do NOT fake with
            # entry_price, that would show 0.00% which looks identical to no data.
            try:
                # Pass opened_at (= now at this point) so Intel DB filter ts_ms >= opened_at*1000
                # accepts ticks from this moment forward. Using `now` is correct here
                # since the position was just committed — opened_at == now.
                _boot_pr = _router_exec_price(mint, entry_price, now) if _PRICE_ROUTER_AVAILABLE else None
                if _boot_pr and _boot_pr.get("price", 0) > 0 and _boot_pr.get("can_execute_exit"):
                    _boot_pnl = pos_size_usd * (
                        (_boot_pr["price"] - entry_price) / entry_price
                    ) if entry_price > 0 else 0.0
                    update_position_mark(
                        position_id, _boot_pr["price"], _boot_pnl, now,
                        source=_boot_pr.get("source", "bootstrap"),
                        router_result=_boot_pr,
                    )
                    log.info(
                        "PRICE_BOOTSTRAP pos=%d %s price=%.10f pct=%.4f%%",
                        position_id, token_name, _boot_pr["price"],
                        (_boot_pr["price"] - entry_price) / entry_price * 100,
                    )
            except Exception:
                pass  # never block entry on bootstrap failure

            log.info(
                "ENTRY OPENED pos=%d %s @ %.8f size=$%.2f TP=%.0f%% SL=%.0f%%",
                position_id, token_name, entry_price, pos_size_usd, tp_pct, sl_pct,
            )
            # PHASE 1 ENTRY_AUDIT — structured log for price truth validation.
            # Confirm in logs after deployment:
            #   source=qualify  → qualify-time price used (no fresher price found)
            #   source=upgraded → fresher oracle/resolver price used at entry
            # Identical entry prices across tokens = source=qualify + genuinely
            # same bonding-curve stage for all qualifying signals.
            log.info(
                "ENTRY_AUDIT mint=%s qualify=%.8f final=%.8f source=%s "
                "price_age=%.2fs signal_age=%.2fs",
                mint[:16],
                _qualify_price,
                final_price,
                price_source,
                price_age,
                signal_age,
            )
            _log_cognition(token_name,
                f"Deployed ${pos_size_usd:.2f} into {token_name} at ${entry_price:.8f}. "
                f"Position active. TP: {tp_pct:.0f}% | SL: {sl_pct:.0f}%.")
            update_heartbeat(SERVICE_NAME, "ALIVE",
                f"Entry opened pos={position_id} {token_name} @ {entry_price:.8f}",
                work_processed=1, last_success_at=now)

            opened += 1
            if degraded_mode:
                break

        except Exception as e:
            import traceback
            print(f"[EXECUTION ERROR] id={row['id']} mint={row['mint_address']}")
            print(f"[EXECUTION ERROR] {type(e).__name__}: {e}")
            traceback.print_exc()
            log.exception("Entry open failed snap=%s: %s", row["id"], e)
            continue

    return opened


# -----------------------------------------------------------------------------
# LIVE EXIT EVALUATION
# -----------------------------------------------------------------------------

def check_open_positions() -> None:
    """Evaluate all open positions for exit conditions."""
    for position in get_open_positions():
        try:
            # PATCH C — post-entry coverage audit: warn if oracle has no ticks
            # for a position older than 5s. Proof panel for oracle coverage gaps.
            _pos_age = time.time() - float(position.get("opened_at") or 0)
            if _pos_age > 5.0:
                try:
                    _mint_chk = str(position.get("mint_address") or "")
                    _opened_ms = float(position.get("opened_at") or 0) * 1000
                    _iconn = get_intel_connection()
                    _tick_count = _iconn.execute(
                        "SELECT COUNT(*) FROM mtm_ticks WHERE mint_address=? AND ts_ms>=?",
                        (_mint_chk, _opened_ms),
                    ).fetchone()[0]
                    _iconn.close()
                    if _tick_count == 0:
                        log.warning(
                            "[NO_POST_ENTRY_TICKS] pos=%d %s age=%.0fs "
                            "— oracle has ZERO ticks since open. Meter will be blind.",
                            position["id"], _mint_chk[:16], _pos_age,
                        )
                        if _TLE_AVAILABLE:
                            try:
                                with get_connection() as _tle_conn:
                                    emit_coverage_alert = _tle_coverage_alert
                                    emit_coverage_alert(_tle_conn,
                                        position_id=position["id"],
                                        mint=_mint_chk, age_sec=_pos_age)
                                    _tle_conn.commit()
                            except Exception:
                                pass
                except Exception:
                    pass  # never block exit eval on audit failure
            evaluate_exit_for_position(position)
        except Exception as e:
            log.warning("Exit eval failed pos=%s: %s", position.get("id"), e)



def get_best_live_exec_price(
    mint: str,
    entry_price: float,
    opened_at: float,
) -> tuple[float, str, float]:
    """
    Returns (price, source, age_sec) using the FRESHEST valid post-entry price.
    Rule: freshest timestamp wins — NOT most extreme move.
    Rejects: price<=0, price>1000x entry, rows older than opened_at.
    """
    now      = time.time()
    best_price  = 0.0
    best_ts     = 0.0
    best_source = "none"
    max_sane    = entry_price * 1000.0 if entry_price > 0 else 1.0

    # ── a) MTM rows (candidate_state='mtm') after opened_at ──────────────────
    try:
        _ip = _get_price_intel_first(mint)
        if _ip and 0 < _ip < max_sane:
            # Intel ticks don't have a per-row ts we can compare to opened_at
            # Use now as ts — they're always recent by design
            if now > best_ts:
                best_price  = _ip
                best_ts     = now
                best_source = "intel-mtm"
    except Exception:
        pass

    try:
        with get_connection() as _c:
            _row = _c.execute(
                """SELECT observed_price, price_updated_at
                   FROM market_snapshots
                   WHERE mint_address=?
                     AND candidate_state='mtm'
                     AND observed_price > 0
                     AND price_updated_at > ?
                   ORDER BY price_updated_at DESC LIMIT 1""",
                (mint, opened_at),
            ).fetchone()
        if _row:
            _p  = float(_row["observed_price"])
            _ts = float(_row["price_updated_at"] or 0)
            if 0 < _p < max_sane and _ts > best_ts:
                best_price  = _p
                best_ts     = _ts
                best_source = "mtm"
    except Exception:
        pass

    # ── b) Unscoped row after opened_at ───────────────────────────────────────
    try:
        with get_connection() as _c:
            _row = _c.execute(
                """SELECT observed_price, price_updated_at
                   FROM market_snapshots
                   WHERE mint_address=?
                     AND observed_price > 0
                     AND price_updated_at > ?
                   ORDER BY price_updated_at DESC LIMIT 1""",
                (mint, opened_at),
            ).fetchone()
        if _row:
            _p  = float(_row["observed_price"])
            _ts = float(_row["price_updated_at"] or 0)
            if 0 < _p < max_sane and _ts > best_ts:
                best_price  = _p
                best_ts     = _ts
                best_source = "unscoped"
    except Exception:
        pass

    # ── c) DexScreener only if DB data is stale (>30s) ───────────────────────
    db_age = now - best_ts if best_ts > 0 else 9999
    if db_age > 30:
        try:
            _dex = fetch_dexscreener_price(mint)
            if _dex and 0 < _dex < max_sane:
                # DexScreener CDN cache ~30-60s stale — treat as 45s old
                _dex_ts = now - 45.0
                if _dex_ts > best_ts:
                    best_price  = _dex
                    best_ts     = _dex_ts
                    best_source = "dex-stale"
        except Exception:
            pass

    age_sec = now - best_ts if best_ts > 0 else 9999.0
    return (best_price, best_source, age_sec)

def evaluate_exit_for_position(position: dict) -> None:
    """
    Canonical live exit evaluator.
    Full original logic from paper_executor._evaluate_exit - no gate reordering.

    Exit evaluation order:
      1. TIME_CUT           - negative PnL after discovery window
      2. TIME_CUT_STAGNANT  - flat/weakly green after stagnation window
      3. TRAILING_STOP      - after trail_activate, based on peak
      4. TAKE_PROFIT
      5. STOP_LOSS
      6. MAX_HOLD_TIME
    """
    position_id  = int(position["id"])
    mint         = str(position["mint_address"] or "")
    token_name   = str(position["token_name"] or mint or "UNKNOWN")[:20]
    entry_price  = float(position["entry_price"]      or 0)
    tp_pct       = float(position["take_profit_pct"]  or 25.0)
    sl_pct       = float(position["stop_loss_pct"]    or 10.0)
    opened_at    = float(position["opened_at"]        or 0)
    pos_size_usd = float(position["position_size_usd"] or 50.0)

    if not mint or entry_price <= 0:
        return

    # ── PRICE TRUTH ROUTER — single authoritative price read ────────────────
    # Uses price_router.get_execution_price() which enforces:
    #   - ts >= opened_at (no pre-entry MTM bleed)
    #   - Intel DB first, MTM snapshot second, unscoped fallback
    #   - NEVER DexScreener in execution mode
    #   - can_execute_exit=False when price is stale (>120s)
    _pr = _router_exec_price(mint, entry_price, opened_at) if _PRICE_ROUTER_AVAILABLE else None

    if _pr is None or _pr["price"] <= 0:
        # Router has no valid price — update last_price for DB continuity but
        # do NOT overwrite live_exec_price/live_exec_pct with fallback.
        # Leaving live_exec fields at their last real value is more honest than
        # writing entry_price which makes the meter show 0% and hides real movement.
        _fallback_price = float(position.get("last_price") or 0)
        if _fallback_price <= 0:
            _fallback_price = float(position.get("entry_price") or 0)
        if _fallback_price > 0:
            # Write price/timestamp only — no router_result so live_exec_* untouched
            update_position_mark(position_id, _fallback_price, 0.0,
                                 time.time(), source="fallback")
            log.warning(
                "NO_LIVE_PRICE pos=%d %s — mark updated with last known %.10f, "
                "exits suppressed until oracle recovers.",
                position_id, token_name, _fallback_price,
            )
        else:
            hold_s = time.time() - opened_at
            _log_cognition(token_name,
                f"MTM coverage lost for {token_name}. No price available. "
                f"Hold: {hold_s:.0f}s. Awaiting oracle recovery.")
        return

    current_price = _pr["price"]
    price_age     = _pr["age_sec"]
    _pr_can_exit  = _pr["can_execute_exit"]
    _pr_warning   = _pr["warning"]

    log.debug("[PRICE_ROUTER] %s price=%.10f age=%.1fs src=%s can_exit=%s",
              token_name, current_price, price_age, _pr["source"], _pr_can_exit)

    # -- PRICE STALENESS KILL-SWITCH ------------------------------------------
    # SIGN-OFF FIX 3: The outer gate previously used a hardcoded literal 300
    # while stale_kill was read from config (default also 300). If an operator
    # raised STALE_PRICE_FORCE_CLOSE_SECONDS > 300, the outer gate still fired
    # at 300s and returned early — skipping SL for the entire gap window.
    # Fix: read stale_kill once and use it for the outer gate too.
    stale_kill = float(float(get_config_value("STALE_PRICE_FORCE_CLOSE_SECONDS", 300.0)))
    _stale_warn_threshold = min(stale_kill, 300.0)   # begin warning at 300s max

    if current_price <= 0 or price_age > _stale_warn_threshold:
        hold_s     = time.time() - opened_at
        max_hold_s = float(float(get_config_value("EXECUTOR_MAX_HOLD_SECONDS", 900.0)))

        # DexScreener removed from execution path — CDN-cached data is UI-only.
        # If current_price is 0 here, the stale_kill guard below will handle it.
        if current_price <= 0:
            log.debug("EXEC: current_price=0 for %s, stale kill will evaluate", token_name)

        if current_price <= 0 or price_age > stale_kill:
            # SIGN-OFF FIX 10: Re-read last_price fresh from DB rather than using the
            # pre-loop position snapshot, which can be several seconds stale when the
            # oracle has been writing concurrently.
            try:
                with get_connection() as _conn:
                    _fresh_row = _conn.execute(
                        "SELECT last_price FROM paper_positions WHERE id=? AND status='OPEN'",
                        (position_id,),
                    ).fetchone()
                last_known = float(_fresh_row["last_price"] or 0) if _fresh_row else 0.0
            except Exception:
                last_known = float(position.get("last_price") or 0)

            # GATE: only close if router has a fresh executable exit price.
            # Never close using last_known / emergency_exit / entry_price fallback —
            # those produce fake tiny PnL from carried stale marks.
            # If router is unavailable or stale, mark GATE_BLOCKED and keep open.
            _router_exit_price = None
            if _PRICE_ROUTER_AVAILABLE and _pr is not None:
                if _pr.get("can_execute_exit") and _pr.get("price", 0) > 0:
                    _router_exit_price = float(_pr["price"])

            if hold_s >= max_hold_s:
                if _router_exit_price is None:
                    log.warning(
                        "MAX_HOLD_TIME pos=%d %s hold=%.0fs — router not executable, "
                        "keeping open (GATE_BLOCKED, will retry next cycle)",
                        position_id, token_name, hold_s,
                    )
                    update_position_mark(position_id,
                        last_known if last_known > 0 else entry_price,
                        0.0, time.time(), source="gate_blocked")
                    return
                close_position_canonical(position_id, _router_exit_price,
                    f"MAX_HOLD_TIME_{hold_s:.0f}s", closure_mode="normal")
                return

            if price_age > stale_kill or (current_price <= 0 and hold_s >= stale_kill):
                if _router_exit_price is None:
                    log.warning(
                        "STALE_PRICE pos=%d %s age=%.0fs — router not executable, "
                        "keeping open (GATE_BLOCKED, will retry next cycle)",
                        position_id, token_name, price_age,
                    )
                    _log_cognition(token_name,
                        f"STALE PRICE — oracle dark {price_age:.0f}s. Router not executable. "
                        f"Keeping open. Will force-close when router confirms fresh price.")
                    update_position_mark(position_id,
                        last_known if last_known > 0 else entry_price,
                        0.0, time.time(), source="gate_blocked")
                    return
                _log_cognition(token_name,
                    f"STALE PRICE KILL-SWITCH: oracle dark {price_age:.0f}s "
                    f"(limit {stale_kill:.0f}s). Closing at router live price "
                    f"${_router_exit_price:.8f}. Capital protected from silent drift.")
                close_position_canonical(position_id, _router_exit_price,
                    f"STALE_PRICE_FORCE_CLOSE_{price_age:.0f}s", closure_mode="normal")
                return

            _log_cognition(token_name,
                f"MTM price for {token_name} is stale ({price_age:.0f}s). "
                f"Hold: {hold_s:.0f}s. Force-close in "
                f"{max(0, stale_kill - price_age):.0f}s if oracle stays dark.")
            # Carry last_known price forward so UI shows the price badge (not silence),
            # but zero PnL — carried price is not executable truth.
            _last = last_known if last_known > 0 else entry_price
            if _last > 0:
                update_position_mark(position_id, _last, 0.0,
                                     time.time(), source="fallback")
            return

    # ── PRICE ROUTER EXECUTION GATE ─────────────────────────────────────────
    # If router says price is too stale to trust for exit decisions, skip
    # TP/SL evaluation. Stale price MUST NOT trigger exits.
    if _PRICE_ROUTER_AVAILABLE and not _pr_can_exit:
        log.warning(
            "[PRICE_ROUTER] %s price stale (%.1fs) — skipping TP/SL. Warning: %s",
            token_name, price_age, _pr_warning,
        )
        # Zero PnL — router-stale price is not executable truth.
        # Writing computed unreal here produces fake micro-percentages in the UI.
        update_position_mark(position_id, current_price, 0.0, time.time(), source="router-stale")
        return

    # EXIT PRICE SANITY GUARD: reject if current_price > 1000x entry
    # Catches bad oracle data from ALL price sources before fake TP fires
    if entry_price > 0 and current_price > entry_price * 1000:
        log.warning(
            "EXIT PRICE GUARD: rejected price=%.10f for %s "
            "(%.1fx entry) - bad oracle data, skipping cycle",
            current_price, token_name, current_price / entry_price
        )
        return

    pnl_pct    = ((current_price - entry_price) / entry_price) * 100
    hold_s     = time.time() - opened_at
    max_hold_s = float(float(get_config_value("EXECUTOR_MAX_HOLD_SECONDS", 900.0)))

    trail_activate = float(float(get_config_value("TRAIL_ACTIVATE_PCT",  10.0)))
    trail_pct      = float(float(get_config_value("TRAIL_STOP_PCT",      15.0)))

    # ═══════════════════════════════════════════════════════════════════════════
    # EDGE PRESERVATION PATCH V3 — DIRECTIVE COMPLIANT EXIT ORDER
    # Order: 1.HARD_STOP  2.RUNNER  3.STAGNATION  4.MAX_HOLD
    # TIME_CUT (fixed 180s) removed. TAKE_PROFIT removed (runner harvests wins).
    # ═══════════════════════════════════════════════════════════════════════════

    # -- Write live MTM mark FIRST — dashboard sees true state before any exit --
    unreal = pos_size_usd * (pnl_pct / 100.0)
    update_position_mark(
        position_id, current_price, unreal, time.time(),
        source=_pr["source"] if (_PRICE_ROUTER_AVAILABLE and _pr) else "engine",
        router_result=_pr if _PRICE_ROUTER_AVAILABLE else None,
    )
    log.debug(
        "[LIVE_EXEC_PRICE] pos=%d update_position_mark handled live_exec write",
        position_id,
    )

    # highest_price_seen — update every tick before exit evaluation
    # Defaults protect against missing data never triggering false exits
    try:
        peak_price = get_peak_price_since_open(mint, opened_at) or current_price
    except Exception:
        peak_price = current_price
    if peak_price <= 0:
        peak_price = current_price

    # volume_acceleration default: 1.0 if unavailable
    try:
        _vol_acc = float(position.get("volume_acceleration") or 1.0)
    except Exception:
        _vol_acc = 1.0

    # price_change_last_60s default: 0.0 if unavailable
    try:
        _p60 = float(position.get("price_change_last_60s") or 0.0)
    except Exception:
        _p60 = 0.0

    # -- 1. HARD STOP LOSS — NON-NEGOTIABLE, fires before everything -----------
    # Triggers at -20% unrealized. Cannot be bypassed under any condition.
    # Eliminates tail-risk collapse. Replaces old -sl_pct check at position 5.
    _hard_stop_pct = 20.0
    if pnl_pct <= -_hard_stop_pct:
        close_position_canonical(position_id, current_price,
            f"HARD_STOP_LOSS_{pnl_pct:.1f}pct", closure_mode="normal")
        _log_cognition(token_name,
            f"HARD STOP: {token_name} hit -{_hard_stop_pct:.0f}% floor "
            f"at {pnl_pct:.2f}%. Tail risk contained. Capital protected.")
        return

    # -- 2. RUNNER MODE — priority above all time-based logic -----------------
    # Activates at +20% unrealized. Switches to trailing stop only.
    # Trail: 10% from peak. Tightens to 8% if PnL >= +50%.
    # No fixed TP overrides this once active.
    _runner_activate_pct = 20.0
    _runner_trail_pct    = 10.0
    _runner_tight_pct    = 8.0   # tightens at +50%
    _runner_tight_thresh = 50.0
    if pnl_pct >= _runner_activate_pct:
        if position_id not in _trail_logged_positions:
            _log_cognition(token_name,
                f"RUNNER MODE: {token_name} at +{pnl_pct:.1f}%. "
                f"Trailing stop engaged. Floor: {_runner_trail_pct:.0f}% below peak "
                f"(tightens to {_runner_tight_pct:.0f}% at +{_runner_tight_thresh:.0f}%).")
            _trail_logged_positions.add(position_id)
        _active_trail = _runner_tight_pct if pnl_pct >= _runner_tight_thresh else _runner_trail_pct
        runner_stop_price = peak_price * (1 - _active_trail / 100)
        if current_price <= runner_stop_price:
            _peak_pct = ((peak_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
            close_position_canonical(position_id, current_price,
                f"TRAILING_STOP_{pnl_pct:.1f}pct_peak_{_peak_pct:.1f}pct",
                closure_mode="normal")
            _log_cognition(token_name,
                f"RUNNER HARVESTED: {token_name} trail stop at "
                f"{pnl_pct:.2f}%. Peak was +{_peak_pct:.1f}%. "
                f"Trail: {_active_trail:.0f}% from peak.")
            return
        # Runner mode: do not evaluate any other exit — let it run
        return

    # -- 3. STAGNATION EXIT — only after 180s, only on true price death --------
    # Replaces TIME_CUT. Time alone NEVER triggers exit.
    # ALLOW HOLD if: pnl > +0.5% with expanding volume, OR price still moving.
    # EXIT ONLY IF: absolute price change over last 60s < 0.2%.
    _stagnation_window = 180.0
    _stagnation_move_threshold = 0.2   # % absolute price move in last 60s
    if hold_s >= _stagnation_window:
        # Check if price is genuinely stagnant (not just temporarily flat)
        _price_moving = abs(_p60) >= _stagnation_move_threshold
        _volume_expanding = _vol_acc > 1.0
        _real_winner = pnl_pct > 0.5 and _volume_expanding

        if _real_winner or _price_moving:
            # Alive — do not cut. Log once to avoid spam.
            log.debug(
                "STAGNATION_HELD pos=%d %s hold=%.0fs pnl=%.2f%% "
                "moving=%s winner=%s vol_acc=%.2f p60=%.4f",
                position_id, token_name, hold_s, pnl_pct,
                _price_moving, _real_winner, _vol_acc, _p60,
            )
        else:
            # Genuinely dead — exit now
            close_position_canonical(position_id, current_price,
                f"TIME_CUT_STAGNANT_{hold_s:.0f}s_pnl_{pnl_pct:.2f}pct",
                closure_mode="normal")
            _log_cognition(token_name,
                f"STAGNATION EXIT: {token_name} held {hold_s:.0f}s. "
                f"Price moved {abs(_p60):.4f}% in last 60s (floor 0.2%). "
                f"Dead trade cleared. PnL: {pnl_pct:.2f}%.")
            return

    # -- 4. MAX HOLD — failsafe only, never triggers for live trades -----------
    if hold_s >= max_hold_s:
        close_position_canonical(position_id, current_price,
            f"MAX_HOLD_TIME_{hold_s:.0f}s", closure_mode="normal")
        return

    # ── Legacy trailing stop for positions between TRAIL_ACTIVATE and RUNNER --
    # Handles positions that activated old trail but haven't reached +20% yet.
    # Preserves continuity for in-flight positions during directive rollout.
    if pnl_pct >= trail_activate and pnl_pct < _runner_activate_pct:
        if position_id not in _trail_logged_positions:
            _log_cognition(token_name,
                f"Trailing stop activated at {pnl_pct:.1f}% on {token_name}. "
                f"Floor: {trail_pct:.0f}% below peak.")
            _trail_logged_positions.add(position_id)
        try:
            legacy_trail_price = peak_price * (1 - trail_pct / 100)
            if current_price <= legacy_trail_price:
                _peak_pct = ((peak_price - entry_price) / entry_price * 100) if entry_price > 0 else 0
                close_position_canonical(position_id, current_price,
                    f"TRAILING_STOP_{pnl_pct:.1f}pct_peak_{_peak_pct:.1f}pct",
                    closure_mode="normal")
                return
        except Exception:
            pass


# -----------------------------------------------------------------------------
# RECONCILIATION (startup gap handling)
# -----------------------------------------------------------------------------

def reconcile_position(pos: dict, gap_start: float, gap_end: float) -> str:
    """
    Replay MTM ticks from the outage window against a position's TP/SL/MAX_HOLD.
    All closes route through close_position_canonical(closure_mode='reconcile').
    Returns outcome label for summary dict.
    """
    position_id = int(pos["id"])
    mint        = str(pos["mint_address"] or "")
    entry_price = float(pos["entry_price"] or 0)
    opened_at   = float(pos["opened_at"]   or 0)
    tp_pct      = float(pos["take_profit_pct"] or 25.0)
    sl_pct      = float(pos["stop_loss_pct"]   or 10.0)

    if not mint or entry_price <= 0:
        return "skipped"

    max_hold_s = float(float(get_config_value("EXECUTOR_MAX_HOLD_SECONDS", 900.0)))
    now        = time.time()
    hold_s     = now - opened_at

    # MAX_HOLD check first - position may be expired regardless of price
    if hold_s >= max_hold_s:
        last_price = get_last_known_price(mint) or get_last_known_price_unscoped(mint)
        exit_price = last_price if last_price else entry_price
        close_position_canonical(position_id, exit_price,
            f"RECONCILE_MAX_HOLD_{hold_s:.0f}s",
            closure_mode="reconcile", notes_prefix="RECONCILED")
        return "closed_maxhold"

    prices = get_mtm_prices_during_gap(mint, gap_start, gap_end)

    if not prices:
        gap_duration = gap_end - gap_start
        if gap_duration > 300:
            last_price = get_last_known_price(mint) or get_last_known_price_unscoped(mint)
            if last_price:
                pnl_pct = ((last_price - entry_price) / entry_price) * 100
                if pnl_pct >= tp_pct:
                    close_position_canonical(position_id, last_price,
                        f"RECONCILE_TP_{pnl_pct:.1f}pct",
                        closure_mode="reconcile", notes_prefix="RECONCILED")
                    return "closed_nodata"
                if pnl_pct <= -sl_pct:
                    close_position_canonical(position_id, last_price,
                        f"RECONCILE_SL_{pnl_pct:.1f}pct",
                        closure_mode="reconcile", notes_prefix="RECONCILED")
                    return "closed_nodata"
        return "held"

    for tick in prices:
        price   = float(tick["price"])
        ts      = float(tick["ts"])
        pnl_pct = ((price - entry_price) / entry_price) * 100

        if pnl_pct >= tp_pct:
            close_position_canonical(position_id, price,
                f"RECONCILE_TP_{pnl_pct:.1f}pct",
                closure_mode="reconcile", notes_prefix="RECONCILED")
            return "closed_tp"

        if pnl_pct <= -sl_pct:
            close_position_canonical(position_id, price,
                f"RECONCILE_SL_{pnl_pct:.1f}pct",
                closure_mode="reconcile", notes_prefix="RECONCILED")
            return "closed_sl"

        hold_at_tick = ts - opened_at
        if hold_at_tick >= max_hold_s:
            close_position_canonical(position_id, price,
                f"RECONCILE_MAX_HOLD_{hold_at_tick:.0f}s",
                closure_mode="reconcile", notes_prefix="RECONCILED")
            return "closed_maxhold"

    return "held"


def run_reconciliation() -> dict:
    now        = time.time()
    last_pulse = get_last_executor_heartbeat()
    gap        = now - last_pulse if last_pulse > 0 else 0

    if gap < 30:
        return {"gap_seconds": gap, "positions_checked": 0, "skipped": True}

    positions = get_open_positions()
    if not positions:
        return {"gap_seconds": gap, "positions_checked": 0, "closed": 0}

    results: dict[str, int] = {
        "closed_tp": 0, "closed_sl": 0, "closed_maxhold": 0,
        "closed_nodata": 0, "held": 0, "skipped": 0,
    }

    for pos in positions:
        try:
            outcome = reconcile_position(pos, last_pulse, now)
            results[outcome] = results.get(outcome, 0) + 1
        except Exception as e:
            log.error("Reconciliation failed pos=%s: %s", pos.get("id"), e)
            results["skipped"] += 1

    closed = (results["closed_tp"] + results["closed_sl"]
              + results["closed_maxhold"] + results["closed_nodata"])

    if closed > 0:
        _log_cognition("SYSTEM",
            f"Startup reconciliation resolved {closed} position(s) that triggered "
            f"during the {gap:.0f}s service gap. Organism integrity restored.",
            meta={"gap_seconds": round(gap), "results": results})

    return {
        "gap_seconds":       round(gap),
        "positions_checked": len(positions),
        "closed":            closed,
        "results":           results,
    }


# -----------------------------------------------------------------------------
# ZOMBIE RESOLUTION - THREADED (Claude sign-off patch)
# -----------------------------------------------------------------------------
#
# DESIGN: scan_and_resolve_zombies() never blocks the main loop.
# When a zombie is detected, a daemon thread is spawned to handle
# the Telegram HITL poll (up to ZOMBIE_HITL_TIMEOUT_SECONDS).
# The thread posts its result to _zombie_result_queue.
# drain_zombie_results() is called every main cycle to process outcomes.
#
# Thread lifecycle:
#   spawned  - polls Telegram for operator response
#   response - posts (position_id, "release"|"hold"|"timeout"|"tg_offline") to queue
#   main     - drains queue, calls close_position_canonical or mark_hold
# -----------------------------------------------------------------------------

def _tg_post(method: str, payload: dict, timeout: int = 10) -> Optional[dict]:
    if not BOT_TOKEN:
        return None
    try:
        import requests
        resp = requests.post(
            f"https://api.telegram.org/bot{BOT_TOKEN}/{method}",
            json=payload, timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as exc:
        log.warning("Telegram API error (%s): %s", method, exc)
        return None


def _tg_available() -> bool:
    result = _tg_post("getMe", {}, timeout=5)
    return bool(result and result.get("ok"))


def _fmt_duration(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60}s"
    return f"{seconds // 3600}h {(seconds % 3600) // 60}m"


def _send_zombie_hitl_message(pos: dict) -> Optional[int]:
    position_id  = int(pos["id"])
    token_name   = str(pos.get("token_name") or "UNKNOWN")
    opened_at    = float(pos.get("opened_at") or 0)
    entry_price  = float(pos.get("entry_price") or 0)
    pos_size     = float(pos.get("position_size_usd") or 0)
    last_price_t = pos.get("last_price_ts") or 0

    jammed_s    = int(time.time() - opened_at)
    no_price_s  = int(time.time() - last_price_t) if last_price_t else jammed_s
    hitl_timeout = int(int(get_config_value("ZOMBIE_HITL_TIMEOUT_SECONDS", 30)))

    text = (
        f"*ZOMBIE POSITION DETECTED*\n\n"
        f"Token: `{token_name}`\n"
        f"Position ID: `{position_id}`\n"
        f"Entry price: `${entry_price:.8f}`\n"
        f"Size: `${pos_size:.2f}`\n\n"
        f"*No price feed for:* `{_fmt_duration(no_price_s)}`\n"
        f"*Jammed for:* `{_fmt_duration(jammed_s)}`\n\n"
        f"Auto-releases at scratch in *{hitl_timeout}s* if no response."
    )
    keyboard = {"inline_keyboard": [[
        {"text": "RELEASE (close at scratch)", "callback_data": f"zombie_release:{position_id}"},
        {"text": "HOLD (keep open)",           "callback_data": f"zombie_hold:{position_id}"},
    ]]}
    result = _tg_post("sendMessage", {
        "chat_id": OWNER_ID, "text": text,
        "parse_mode": "Markdown", "reply_markup": keyboard,
    })
    return result["result"]["message_id"] if result and result.get("ok") else None


def _poll_for_zombie_response(position_id: int, message_id: int, timeout_s: int) -> str:
    """
    Blocks (in its own thread) polling Telegram for operator response.
    Returns "release", "hold", or "timeout".
    """
    deadline = time.time() + timeout_s
    offset   = None
    while time.time() < deadline:
        params: dict[str, Any] = {"timeout": 2, "allowed_updates": ["callback_query"]}
        if offset is not None:
            params["offset"] = offset
        result = _tg_post("getUpdates", params, timeout=10)
        if result and result.get("ok"):
            for upd in result.get("result", []):
                offset = upd["update_id"] + 1
                cq     = upd.get("callback_query")
                if not cq:
                    continue
                data  = cq.get("data", "")
                cq_id = cq["id"]
                if f":{position_id}" not in data:
                    continue
                _tg_post("answerCallbackQuery", {"callback_query_id": cq_id})
                if data.startswith("zombie_release:"):
                    _tg_post("editMessageText", {
                        "chat_id": OWNER_ID, "message_id": message_id,
                        "text": f"RELEASE confirmed for pos {position_id}. Closing at scratch.",
                    })
                    return "release"
                if data.startswith("zombie_hold:"):
                    _tg_post("editMessageText", {
                        "chat_id": OWNER_ID, "message_id": message_id,
                        "text": f"HOLD confirmed for pos {position_id}. Slot kept open.",
                    })
                    return "hold"
        time.sleep(2)
    return "timeout"


def _zombie_hitl_thread(pos: dict, message_id: int) -> None:
    """
    Daemon thread: polls Telegram, posts result to _zombie_result_queue.
    Never calls close_position_canonical directly - that stays on the main thread.
    """
    position_id  = int(pos["id"])
    hitl_timeout = int(int(get_config_value("ZOMBIE_HITL_TIMEOUT_SECONDS", 30)))

    try:
        response = _poll_for_zombie_response(position_id, message_id, hitl_timeout)
        _zombie_result_queue.put((position_id, response, pos))
    except Exception as e:
        log.warning("Zombie HITL thread failed pos=%d: %s", position_id, e)
        _zombie_result_queue.put((position_id, "timeout", pos))
    finally:
        with _zombie_threads_lock:
            _zombie_threads_active.discard(position_id)


def drain_zombie_results() -> int:
    """
    Called by the main loop every cycle.
    Drains _zombie_result_queue and executes any pending closes/holds.
    Returns number of positions resolved.
    """
    resolved = 0
    while not _zombie_result_queue.empty():
        try:
            position_id, response, pos = _zombie_result_queue.get_nowait()
        except queue.Empty:
            break

        mint = str(pos.get("mint_address") or "")

        if response == "hold":
            cooldown = float(float(get_config_value("HITL_COOLDOWN_SECONDS", 120)))
            _hitl_sent_at[position_id] = time.time()
            _log_cognition("SYSTEM",
                f"Operator confirmed HOLD for position {position_id}. "
                f"Zombie resolver standing down for {int(cooldown)}s.")
            continue

        # response == "release" or "timeout"
        if response == "timeout":
            reason = f"ZOMBIE_AUTO_CLOSE_HITL_TIMEOUT"
        else:
            reason = "ZOMBIE_HITL_OPERATOR_RELEASE"

        # Use best known price if available, else scratch
        best_exit = get_last_known_price(mint) or get_last_known_price_unscoped(mint)
        if best_exit and best_exit > 0 and response == "timeout":
            ok = close_position_canonical(position_id, best_exit, reason,
                closure_mode="zombie", force_scratch=False, notes_prefix="ZOMBIE_CLOSE")
        else:
            ok = close_position_canonical(position_id,
                float(pos.get("entry_price") or 0), reason,
                closure_mode="zombie", force_scratch=True, notes_prefix="ZOMBIE_CLOSE")

        if ok:
            resolved += 1

    return resolved


def scan_and_resolve_zombies() -> int:
    """
    Detect zombie positions (no price feed for > ZOMBIE_PRICE_STALE_SECONDS).
    Spawns a daemon thread per zombie for HITL polling - never blocks main loop.
    For Telegram-offline cases, closes immediately on the calling thread.
    Returns count of positions resolved THIS cycle (offline-path only;
    threaded resolutions are counted via drain_zombie_results).
    """
    positions = get_open_positions()
    if not positions:
        return 0

    stale_threshold = float(float(get_config_value("ZOMBIE_PRICE_STALE_SECONDS", 300)))
    resolved = 0

    for pos in positions:
        position_id = int(pos["id"])
        mint        = str(pos.get("mint_address") or "")
        token_name  = str(pos.get("token_name") or "UNKNOWN")

        if not mint:
            continue

        last_price_ts = get_last_price_ts(mint)
        pos["last_price_ts"] = last_price_ts

        no_price_for = (
            time.time() - last_price_ts
            if last_price_ts
            else time.time() - float(pos.get("opened_at") or 0)
        )

        if no_price_for < stale_threshold:
            continue

        # Cooldown guard - don't re-alert within HITL_COOLDOWN_SECONDS
        cooldown  = float(float(get_config_value("HITL_COOLDOWN_SECONDS", 120)))
        last_sent = _hitl_sent_at.get(position_id, 0)
        if (time.time() - last_sent) <= cooldown:
            continue

        # Don't spawn duplicate thread for same position
        with _zombie_threads_lock:
            if position_id in _zombie_threads_active:
                continue

        _hitl_sent_at[position_id] = time.time()

        _log_cognition(token_name,
            f"Zombie detected: {token_name} has had no price feed for "
            f"{_fmt_duration(int(no_price_for))}. HITL resolution initiated.",
            meta={"position_id": position_id, "no_price_for_seconds": int(no_price_for)})

        tg_online  = _tg_available()
        message_id = None
        if tg_online and BOT_TOKEN and OWNER_ID:
            message_id = _send_zombie_hitl_message(pos)

        if message_id:
            # -- THREADED PATH: spawn daemon, main loop never blocks --------
            with _zombie_threads_lock:
                _zombie_threads_active.add(position_id)
            t = threading.Thread(
                target=_zombie_hitl_thread,
                args=(pos, message_id),
                daemon=True,
                name=f"zombie-hitl-{position_id}",
            )
            t.start()
            log.info("Zombie HITL thread spawned for pos=%d (%s)", position_id, token_name)

        else:
            # -- OFFLINE PATH: TG unavailable - do NOT close, just log ----
            # Closing at entry price when TG is offline destroys PnL.
            # The normal exit evaluator (TIME_CUT / MAX_HOLD / SL) will
            # handle this position correctly. Only close here if held
            # far beyond max hold time with genuinely no price at all.
            hold_s     = time.time() - float(pos.get("opened_at") or 0)
            max_hold_s = float(float(get_config_value("EXECUTOR_MAX_HOLD_SECONDS", 900.0)))
            best_exit  = get_last_known_price(mint) or get_last_known_price_unscoped(mint)

            if hold_s > max_hold_s * 2 and not best_exit:
                # Only force-close if 2x over max hold AND no price ever seen
                reason = "ZOMBIE_AUTO_CLOSE_NO_PRICE_MAXHOLD"
                ok = close_position_canonical(position_id,
                    float(pos.get("entry_price") or 0), reason,
                    closure_mode="zombie", force_scratch=True,
                    notes_prefix="ZOMBIE_CLOSE")
                if ok:
                    resolved += 1
            else:
                _log_cognition(token_name,
                    f"Zombie detected but TG offline - holding position {token_name}. "
                    f"Normal exit logic will handle. Hold: {hold_s:.0f}s")

    return resolved


# -----------------------------------------------------------------------------
# MAIN LOOP
# -----------------------------------------------------------------------------


# ─────────────────────────────────────────────────────────────────────────────
# SAME-EYES EXECUTION MONITOR — read-only dry-run of scan_for_entries
# Mirrors EXACT gate sequence of scan_for_entries with zero writes.
# Returns list of decision dicts for each candidate. Call from UI or debug only.
# ─────────────────────────────────────────────────────────────────────────────
def dry_run_entry_scan(limit: int = 30) -> list:
    """
    Dry-run entry scanner — executor-aligned diagnostic view.

    Mirrors:
    - Gate order
    - Gate logic
    - Entry decision outcomes
    - Config reads (all via get_config_value)
    - degraded_mode fetch behaviour (mirrors fetch_limit = 1 if degraded)

    Intentional differences:
    - Omits SQL price filter (observed_price > 0) to expose hidden candidates
    - Those rows are labeled: BLOCKED_NO_PRICE [not visible to executor SQL]
    - Annotates degraded-mode on WOULD_ENTER instead of silently limiting

    ZERO writes: no INSERT, UPDATE, DELETE, or wallet changes.
    This is a SAME-EYES tool, not a byte-for-byte executor clone.
    """
    results = []
    now = time.time()

    def _decision(row_dict, decision, block_reason, **extra):
        d = {
            "snapshot_id":          row_dict.get("id"),
            "mint_address":         str(row_dict.get("mint_address") or "")[:20],
            "token_name":           str(row_dict.get("token_name") or "")[:18],
            "observed_price":       row_dict.get("observed_price"),
            "upgraded_entry_price": extra.get("upgraded_entry_price"),
            "created_at":           row_dict.get("created_at"),
            "price_updated_at":     row_dict.get("price_updated_at"),
            "signal_age_sec":       extra.get("signal_age_sec"),
            "price_age_sec":        extra.get("price_age_sec"),
            "confidence":           row_dict.get("mint_confidence") or row_dict.get("confidence"),
            "decision":             decision,
            "block_reason":         block_reason,
            "compact_reason":       block_reason,
        }
        return d

    # ── Read same config as executor ─────────────────────────────────────────
    halt            = str(get_config_value("DRAWDOWN_HALT_ACTIVE",        "0")).strip()
    soft_brake      = str(get_config_value("DRAWDOWN_SOFT_BRAKE",         "0")).strip()
    max_pos         = int(get_config_value("EXECUTOR_MAX_OPEN_POSITIONS",  MAX_OPEN_POSITIONS))
    max_price_age   = float(get_config_value("EXECUTOR_MAX_PRICE_AGE_SEC", 300.0))
    max_signal_age  = float(get_config_value("EXECUTOR_MAX_SIGNAL_AGE_SEC", 600.0))
    _oracle_gate_sec = float(get_config_value("ORACLE_LIVENESS_GATE_SEC",  300.0))
    conf_floor      = float(get_config_value("SUPERVISOR_MIN_MINT_CONFIDENCE", 0.65))
    balance         = get_wallet_balance()

    # ── Pre-scan global gates ────────────────────────────────────────────────
    if halt == "1":
        return [{"snapshot_id": None, "mint_address": "—", "token_name": "GLOBAL",
                 "decision": "BLOCKED", "block_reason": "BLOCKED_DRAWDOWN_HALT",
                 "compact_reason": "BLOCKED_DRAWDOWN_HALT",
                 "observed_price": None, "upgraded_entry_price": None,
                 "created_at": None, "price_updated_at": None,
                 "signal_age_sec": None, "price_age_sec": None, "confidence": None}]

    # Oracle liveness
    _oracle_age = 0.0
    try:
        import sqlite3 as _sq3, os as _os
        _idb = _os.path.join(_os.path.dirname(_os.path.dirname(__file__)),
                             "sentinuity_intelligence.db")
        _ic = _sq3.connect(_idb, timeout=2)
        _latest = _ic.execute("SELECT MAX(ts_ms) FROM mtm_ticks").fetchone()[0]
        _ic.close()
        _oracle_age = (now - _latest / 1000.0) if _latest else 9999.0
    except Exception:
        _oracle_age = 0.0  # fail-open

    oracle_blocked = _oracle_age > _oracle_gate_sec and count_open_positions() > 0

    if balance <= 0:
        return [{"snapshot_id": None, "mint_address": "—", "token_name": "GLOBAL",
                 "decision": "BLOCKED", "block_reason": "BLOCKED_NO_BALANCE",
                 "compact_reason": "BLOCKED_NO_BALANCE",
                 "observed_price": None, "upgraded_entry_price": None,
                 "created_at": None, "price_updated_at": None,
                 "signal_age_sec": None, "price_age_sec": None, "confidence": None}]

    open_count = count_open_positions()

    # ── Degraded mode — read from real executor latency cache ──────────────────
    _lc           = getattr(scan_for_entries, "_latency_cache", {"ms": 0.0, "ts": 0.0})
    _latency      = float(_lc.get("ms") or 0.0)
    _limit_ms     = float(get_config_value("EXECUTOR_WRITE_LATENCY_LIMIT_MS", 10000.0))
    degraded_mode = _latency > _limit_ms
    # Mirror real executor fetch_limit: always 25 (degraded_mode limits opens, not inspections)
    real_fetch_limit = 25

    # ── Fetch candidates ────────────────────────────────────────────────────
    # NOTE: intentionally omits "AND observed_price IS NOT NULL AND observed_price > 0"
    # from the real executor SQL. Purpose: diagnostic expanded view — surfaces candidates
    # the executor would never fetch. Those rows are labeled BLOCKED_NO_PRICE below.
    try:
        with get_connection() as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT id, mint_address, token_name, observed_price, price_updated_at,
                       COALESCE(created_at, timestamp, price_updated_at, 0) AS created_at,
                       mint_confidence, confidence, latch_claimed_until,
                       latched, execution_ready, candidate_state, quality_reason
                FROM market_snapshots
                WHERE latched=1 AND execution_ready=1
                  AND candidate_state='latched'
                  AND COALESCE(tx_hash, '') NOT LIKE 'mtm:%'
                  AND (? - COALESCE(created_at, timestamp, price_updated_at, 0)) <= ?
                ORDER BY
                    COALESCE(created_at, timestamp, price_updated_at, 0) DESC,
                    price_updated_at DESC,
                    id DESC
                LIMIT ?
                """,
                (now, 1800, limit),
            ).fetchall()
    # Apply real fetch_limit AFTER fetching (diagnostic fetches full limit, then slices)
    # so all candidates are visible in output but WOULD_ENTER is annotated for degraded.
    # This matches executor behaviour: only real_fetch_limit candidates can enter.
    except Exception as e:
        return [{"snapshot_id": None, "mint_address": "ERROR", "token_name": str(e)[:40],
                 "decision": "BLOCKED", "block_reason": "BLOCKED_DB_ERROR",
                 "compact_reason": str(e)[:40],
                 "observed_price": None, "upgraded_entry_price": None,
                 "created_at": None, "price_updated_at": None,
                 "signal_age_sec": None, "price_age_sec": None, "confidence": None}]

    seen_mints: set = set()

    for row in rows:
        row_dict     = dict(row)
        snap_id      = row_dict.get("id")
        mint         = str(row_dict.get("mint_address") or "")
        token_name   = str(row_dict.get("token_name") or mint or "")[:18]
        obs_price    = float(row_dict.get("observed_price") or 0)
        price_upd_at = float(row_dict.get("price_updated_at") or 0)
        created_ts   = float(row_dict.get("created_at") or 0)
        price_age    = now - price_upd_at if price_upd_at > 0 else 9999.0
        signal_age   = now - created_ts   if created_ts   > 0 else float("inf")
        conf         = float(row_dict.get("mint_confidence") or row_dict.get("confidence") or 0.0)
        latch_until  = float(row_dict.get("latch_claimed_until") or 0)
        row_dict["signal_age_sec"] = round(signal_age, 1)
        row_dict["price_age_sec"]  = round(price_age,  1)

        def _d(decision, reason):
            return _decision(row_dict, decision, reason,
                             signal_age_sec=round(signal_age, 1),
                             price_age_sec=round(price_age, 1))

        # Global oracle gate
        if oracle_blocked:
            results.append(_d("BLOCKED", "BLOCKED_ORACLE_STALE")); continue

        # Global max positions
        if open_count >= max_pos:
            results.append(_d("BLOCKED", "BLOCKED_MAX_POSITIONS")); continue

        # Latch claimed
        if latch_until > now:
            results.append(_d("BLOCKED", "BLOCKED_LATCH_CLAIMED")); continue

        # No price
        if obs_price <= 0:
            results.append(_d("BLOCKED", "BLOCKED_NO_PRICE [not visible to executor SQL]")); continue

        # No price timestamp
        if price_upd_at <= 0:
            results.append(_d("BLOCKED", "BLOCKED_NO_PRICE_TIMESTAMP")); continue

        # Signal too old
        if signal_age > max_signal_age:
            results.append(_d("BLOCKED", f"BLOCKED_SIGNAL_TOO_OLD ({signal_age:.0f}s > {max_signal_age:.0f}s)")); continue

        # Batch dedup
        if mint in seen_mints:
            results.append(_d("BLOCKED", "BLOCKED_BATCH_DEDUP")); continue

        # Price stale
        if price_age > max_price_age:
            results.append(_d("BLOCKED", f"BLOCKED_PRICE_STALE ({price_age:.0f}s > {max_price_age:.0f}s)")); continue

        # Duplicate open
        try:
            with get_connection() as conn:
                if conn.execute("SELECT 1 FROM paper_positions WHERE mint_address=? AND status='OPEN' LIMIT 1",
                                (mint,)).fetchone():
                    results.append(_d("BLOCKED", "BLOCKED_DUPLICATE_OPEN_POSITION")); continue
        except Exception:
            pass

        # No-reentry
        try:
            with get_connection() as conn:
                if conn.execute("SELECT 1 FROM paper_positions WHERE mint_address=? LIMIT 1",
                                (mint,)).fetchone():
                    results.append(_d("BLOCKED", "BLOCKED_NO_REENTRY")); continue
        except Exception:
            pass

        # Blacklist
        try:
            with get_connection() as conn:
                if conn.execute("SELECT 1 FROM mint_blacklist WHERE mint_address=? LIMIT 1",
                                (mint,)).fetchone():
                    results.append(_d("BLOCKED", "BLOCKED_BLACKLISTED")); continue
        except Exception:
            pass

        # Curve graduated
        if _CURVE_CHECK_AVAILABLE:
            try:
                _curve = _get_curve_progress(mint)
                if _curve.get("complete") and not _curve.get("error"):
                    results.append(_d("BLOCKED", "BLOCKED_CURVE_INVALID")); continue
            except Exception:
                pass

        # Entry price upgrade
        _qualify_ts = now - price_age
        try:
            final_price, price_source, price_ts = get_best_entry_price(mint, obs_price, _qualify_ts)
            if not final_price or final_price <= 0:
                final_price = obs_price
                price_source = "qualify-fallback"
        except Exception as _ge:
            results.append(_d("BLOCKED", f"BLOCKED_ENTRY_PRICE_UNAVAILABLE ({_ge})")); continue

        # Quantity sanity
        pos_pct      = float(get_config_value("POSITION_SIZE_PCT", 5.0))
        pos_size_usd = balance * (pos_pct / 100.0) if pos_pct > 0 else float(get_config_value("POSITION_SIZE_USD", 25.0))
        if soft_brake == "1":
            pos_size_usd *= 0.5
        quantity = pos_size_usd / final_price if final_price > 0 else 0
        if quantity > 1_000_000_000:
            results.append(_d("BLOCKED", "BLOCKED_QUANTITY_ABSURD")); continue

        seen_mints.add(mint)
        open_count += 1  # optimistic increment so subsequent rows see correct count

        # ── ADMISSION FILTER (Edge Preservation Directive V3) ─────────────────
        # Soft gate: reduces low-quality entries without starving opportunity flow.
        # Do NOT over-tighten. All three conditions must pass to WOULD_ENTER.
        _adm_conf_floor     = max(conf_floor, 0.65)   # directive minimum
        _adm_max_signal_age = min(max_signal_age, 600.0)  # directive cap
        _adm_min_exec_pct   = 2.0                     # minimum live_exec_pct
        _adm_live_exec_pct  = float(row_dict.get("live_exec_pct") or 0.0)
        _adm_fail = None
        if conf < _adm_conf_floor:
            _adm_fail = f"ADMISSION_BLOCKED_LOW_CONF ({conf:.3f} < {_adm_conf_floor:.2f})"
        elif signal_age > _adm_max_signal_age:
            _adm_fail = f"ADMISSION_BLOCKED_SIGNAL_AGE ({signal_age:.0f}s > {_adm_max_signal_age:.0f}s)"
        elif _adm_live_exec_pct < _adm_min_exec_pct and _adm_live_exec_pct > 0:
            # Only gate on live_exec_pct if it's been set (> 0) — don't block on missing data
            _adm_fail = f"ADMISSION_BLOCKED_LOW_EXEC_PCT ({_adm_live_exec_pct:.2f}% < {_adm_min_exec_pct:.1f}%)"
        if _adm_fail:
            open_count -= 1  # revert optimistic increment
            seen_mints.discard(mint)
            results.append(_d("BLOCKED", _adm_fail))
            log.debug("ADMISSION_FILTER: %s %s", mint[:16], _adm_fail)
            continue

        _dec = "WOULD_ENTER" + (" [DEGRADED: executor opens max 1 this cycle]" if degraded_mode else "")
        r = _decision(row_dict, _dec, "WOULD_ENTER",
                      signal_age_sec=round(signal_age, 1),
                      price_age_sec=round(price_age, 1),
                      upgraded_entry_price=final_price)
        r["upgraded_entry_price"] = final_price
        r["compact_reason"] = f"src={price_source} age={round(now-price_ts,0):.0f}s"
        results.append(r)

    return results


def print_same_eyes_report() -> None:
    """Print the same-eyes execution monitor to stdout. Zero writes."""
    import sys
    results = dry_run_entry_scan(limit=30)
    print("\\n═══ SAME-EYES EXECUTION MONITOR ═══")
    print(f"{'MINT':<16} {'SIG_AGE':>7} {'PRC_AGE':>7} {'CONF':>6}  DECISION")
    print("─" * 65)
    for r in results:
        mint     = str(r.get("mint_address") or "?")[:15]
        sig_age  = f"{r['signal_age_sec']:.0f}s" if r.get("signal_age_sec") else "?"
        prc_age  = f"{r['price_age_sec']:.0f}s"  if r.get("price_age_sec")  else "?"
        conf_val = r.get("confidence")
        conf_str = f"{float(conf_val):.2f}" if conf_val is not None else "  ?"
        decision = str(r.get("block_reason") or r.get("decision") or "?")[:40]
        print(f"{mint:<16} {sig_age:>7} {prc_age:>7} {conf_str:>6}  {decision}")
    print("═" * 65)
    enters = sum(1 for r in results if r.get("decision") == "WOULD_ENTER")
    blocked = len(results) - enters
    print(f"SUMMARY: {enters} WOULD_ENTER  {blocked} BLOCKED  ({len(results)} candidates)")


def run() -> None:
    ensure_executor_schema()
    # Start cognition writer thread before first log call — avoids lazy-init
    # race condition where two threads could both see _COG_WRITER_STARTED=False.
    if _COGNITION_AVAILABLE:
        _start_cognition_writer()
    log.info("EXECUTION ENGINE ONLINE - entry + exit + reconciliation + zombie protection")
    update_heartbeat(SERVICE_NAME, "ALIVE", "Execution engine online")

    # Startup gap reconciliation
    try:
        recon = run_reconciliation()
        if recon.get("closed", 0) > 0:
            log.info("RECONCILER: closed %d from %.0fs gap",
                     recon["closed"], recon["gap_seconds"])
        else:
            log.info("RECONCILER: %d positions checked - no gap triggers (gap=%.0fs)",
                     recon.get("positions_checked", 0), recon.get("gap_seconds", 0))
    except Exception as e:
        log.warning("RECONCILER startup failed (non-fatal): %s", e)

    cycle       = 0
    zombie_tick = 0
    _mg_stat_tick = 0

    while True:
        try:
            cycle       += 1
            zombie_tick += 1
            _mg_stat_tick += 1

            # Core trading cycle
            scan_for_entries()
            check_open_positions()

            # Momentum gate periodic stats — every 20 cycles
            if _mg_stat_tick >= 20:
                _mg_stat_tick = 0
                try:
                    _mgs = momentum_gate_stats()
                    if _mgs.get("total", 0) >= 10:
                        log.info(
                            "MOMENTUM_GATE_SHADOW_STATS total=%d vetoed=%d "
                            "false_neg=%d(%.1f%%) true_neg=%d "
                            "avg_pnl_allowed=%.2f avg_pnl_vetoed=%.2f phase2_ready=%s",
                            _mgs.get("total", 0), _mgs.get("vetoed", 0),
                            _mgs.get("false_negatives", 0),
                            _mgs.get("false_negative_rate_pct", 0),
                            _mgs.get("true_negatives", 0),
                            _mgs.get("avg_pnl_allowed") or 0,
                            _mgs.get("avg_pnl_vetoed") or 0,
                            _mgs.get("ready_for_phase_2", False),
                        )
                        if _mgs.get("ready_for_phase_2"):
                            log.warning(
                                "MOMENTUM_GATE PHASE 2 READY — "
                                "false_neg_rate=%.1f%% consider enabling MOMENTUM_GATE_ENABLED=1",
                                _mgs.get("false_negative_rate_pct", 0)
                            )
                except Exception:
                    pass

            # Drain zombie thread results every cycle (non-blocking)
            drained = drain_zombie_results()
            if drained > 0:
                log.info("ZOMBIE DRAIN: resolved %d position(s)", drained)

            # Zombie scan every ZOMBIE_POLL_EVERY cycles
            if zombie_tick >= ZOMBIE_POLL_EVERY:
                zombie_tick = 0
                offline_resolved = scan_and_resolve_zombies()
                if offline_resolved > 0:
                    log.info("ZOMBIE OFFLINE: resolved %d position(s)", offline_resolved)

            # Periodic heartbeat with pipeline state
            if cycle % 12 == 0:
                with get_connection() as conn:
                    open_count    = conn.execute(
                        "SELECT COUNT(*) AS c FROM paper_positions WHERE status='OPEN'"
                    ).fetchone()["c"]
                    latched_count = conn.execute(
                        "SELECT COUNT(*) AS c FROM market_snapshots "
                        "WHERE latched=1 AND execution_ready=1"
                    ).fetchone()["c"]
                    # Diagnostic: how many exec_ready rows pass the executor SQL query
                    _now_d = time.time()
                    exec_query_count = conn.execute("""
                        SELECT COUNT(*) FROM market_snapshots
                        WHERE latched=1 AND execution_ready=1
                          AND candidate_state='latched'
                          AND observed_price IS NOT NULL AND observed_price > 0
                          AND (? - COALESCE(created_at,timestamp,price_updated_at,0)) <= 1800
                    """, (_now_d,)).fetchone()[0]
                    # Count per-block-reason for the exec_ready rows that DON'T pass
                    wrong_state = conn.execute(
                        "SELECT COUNT(*) FROM market_snapshots "
                        "WHERE execution_ready=1 AND candidate_state!='latched'"
                    ).fetchone()[0]
                    no_price = conn.execute(
                        "SELECT COUNT(*) FROM market_snapshots "
                        "WHERE execution_ready=1 AND (observed_price IS NULL OR observed_price=0)"
                    ).fetchone()[0]
                _note = (
                    f"open_positions={open_count} latched_signals={latched_count} "
                    f"exec_query_matches={exec_query_count}"
                )
                if wrong_state:
                    _note += f" BLOCKED_wrong_state={wrong_state}"
                if no_price:
                    _note += f" BLOCKED_no_price={no_price}"
                if latched_count > 0 and exec_query_count == 0:
                    _note += " ← PICKUP_MISMATCH_RUN_audit_executor_pickup.py"
                update_heartbeat(SERVICE_NAME, "ALIVE", _note)

        except Exception as e:
            log.exception("Execution engine loop error: %s", e)
            update_heartbeat(SERVICE_NAME, "ERROR", str(e)[:120])

        time.sleep(POLL_INTERVAL)



# ─────────────────────────────────────────────────────────────────────────────
# SAME-EYES EXECUTION MONITOR — dry-run path, ZERO writes
# Mirrors scan_for_entries() gate-for-gate using the same config reads,
# the same SQL query, and the same helper calls.
# Returns a list of dicts — one per candidate — with decision and block_reason.
# ─────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    run()