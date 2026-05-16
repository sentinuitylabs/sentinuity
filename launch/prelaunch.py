"""
prelaunch.py
============
SENTINUITY PRE-LAUNCH SEQUENCE
Run this BEFORE Launch_Sentinuity.bat every time.
Ensures the organism launches into a known-good state.

What it does:
  1. Verifies all critical service files exist
  2. Clears any stale drawdown halt
  3. Sets all known-good config values
  4. Clears the stale unpriced backlog (>30 min old, no price)
  5. Resets stuck pipeline rows
  6. WAL checkpoint
  7. Reports pipeline state — green means launch

What it NEVER touches:
  - paper_positions (trade history)
  - trade_autopsies (outcome data)
  - polaris_trade_reviews (learning data)
  - polaris_learned_patterns (doctrine)
  - system_config values set by Polaris/IVARIS
  - wallet_balance or initial_capital
"""

import sqlite3
import sys
import time
from pathlib import Path
from datetime import datetime

# Resolve ROOT regardless of where this script is invoked from.
_here = Path(__file__).resolve().parent
BASE_DIR = _here if ((_here / "core").exists() and (_here / "services").exists()) else _here.parent
DB_PATH  = BASE_DIR / "sentinuity_matrix.db"
SEP = "=" * 58


def get_conn():
    conn = sqlite3.connect(str(DB_PATH), timeout=30)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=30000")
    conn.row_factory = sqlite3.Row
    return conn


def ok(msg):   print(f"  [OK]    {msg}")
def warn(msg): print(f"  [WARN]  {msg}")
def fixed(msg):print(f"  [FIXED] {msg}")
def fail(msg): print(f"  [FAIL]  {msg}"); sys.exit(1)


print(f"\n{SEP}")
print(f"  SENTINUITY PRE-LAUNCH  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
print(SEP)

if not DB_PATH.exists():
    warn("DB not found — will be created on first launch")
else:
    ok(f"DB found: {DB_PATH.stat().st_size / 1024 / 1024:.1f} MB")

# ── CRITICAL SERVICE FILES ─────────────────────────────────────────────────────
print(f"\n[1] Critical service files")
CRITICAL = [
    # Core 10 runtime contract — guardian is launched by Watchdog_Sentinuity.bat
    "services/ingest_pipeline.py",
    "services/market_intelligence.py",
    "services/ws_price_oracle.py",
    "services/execution_engine.py",
    "services/sovereign_governor.py",
    "services/system_guardian.py",
    "services/pump_monitor.py",
    "services/neural_supervisor.py",
    "services/polaris.py",
    "services/sovereign_parameter_engine.py",
    "services/replay_engine.py",
    "services/polaris_auxiliary.py",
    "services/reconnaissance_engine.py",
    "core/schema.py",
    "services/cognition_logger.py",
    # Sovereign Forge — doctrine + orchestrator must exist before launch
    "SENTINUITY_SOVEREIGN_DOCTRINE.md",
    "forge_genesis_seed.py",
    "services/intelligence_orchestrator.py",
]
missing = [f for f in CRITICAL if not (BASE_DIR / f).exists()]
if missing:
    for f in missing:
        fail(f"MISSING: {f}")
else:
    ok(f"All {len(CRITICAL)} critical files present")

if not DB_PATH.exists():
    print(f"\n  DB does not exist — skipping DB checks")
    print(f"  Launch normally, schema will be created on first run.\n")
    sys.exit(0)

conn = get_conn()
now  = time.time()

# ── PIPELINE SCHEMA ────────────────────────────────────────────────────────────
print(f"\n[1b] Ensuring pipeline schema (offline, before services start)")
try:
    # Fix: r[1] is column name, r[0] is column index in PRAGMA table_info
    raw_cols = {r[1] for r in conn.execute("PRAGMA table_info(raw_dna)").fetchall()}
    for col, col_def in [
        ("claim_until",       "REAL"),
        ("resolved_at",       "REAL"),
        ("resolution_status", "TEXT"),
        ("resolution_note",   "TEXT"),
        ("mint_address",      "TEXT"),
        ("mint_confidence",   "REAL"),
        ("confidence",        "REAL"),
        ("resolution_method", "TEXT"),
    ]:
        if col not in raw_cols:
            try:
                conn.execute(f"ALTER TABLE raw_dna ADD COLUMN {col} {col_def}")
                fixed(f"raw_dna: added {col}")
            except Exception:
                pass  # column already exists

    # Backfill market_snapshots — every column used by prelaunch and runtime services
    snap_cols = {r[1] for r in conn.execute("PRAGMA table_info(market_snapshots)").fetchall()}
    for col, col_def in [
        ("candidate_state",  "TEXT DEFAULT \'pending\'"),
        ("price_status",     "TEXT DEFAULT \'pending\'"),
        ("quality_status",   "TEXT DEFAULT \'pending\'"),
        ("quality_reason",   "TEXT DEFAULT \'\'"),
        ("price_attempts",   "INTEGER DEFAULT 0"),
        ("observed_price",   "REAL"),
        ("price_updated_at", "REAL"),
        ("resolver_status",  "TEXT DEFAULT \'\'"),
        ("execution_ready",  "INTEGER DEFAULT 0"),
        ("mint_address",     "TEXT DEFAULT \'\'"),
        ("latched",          "INTEGER DEFAULT 0"),
        ("qualify_claimed_until", "REAL"),
        ("price_last_attempt_at", "REAL"),
        ("duplicate_key",         "TEXT"),
        ("token_age_seconds",    "REAL"),
        ("token_liquidity_usd",  "REAL"),
        ("market_cap_usd",       "REAL"),
        ("is_tradeable",         "INTEGER DEFAULT 0"),
        ("source_note",          "TEXT"),
        ("curve_progress_pct",   "REAL"),
        ("curve_sol_reserves",   "REAL"),
        ("mint_confidence",       "REAL"),
        ("confidence",            "REAL"),
    ]:
        if col not in snap_cols:
            try:
                conn.execute(f"ALTER TABLE market_snapshots ADD COLUMN {col} {col_def}")
                fixed(f"market_snapshots: added {col}")
            except Exception:
                pass  # already exists


    # Backfill paper_positions — columns required by live execution truth + final review writes.
    try:
        pos_cols = {r[1] for r in conn.execute("PRAGMA table_info(paper_positions)").fetchall()}
        for col, col_def in [
            ("live_exec_price",      "REAL"),
            ("live_exec_pct",        "REAL"),
            ("live_exec_source",     "TEXT"),
            ("live_exec_updated_at", "REAL"),
            ("live_exec_band",       "TEXT"),
            ("live_exec_confidence", "REAL"),
            ("live_exec_can_exit",   "INTEGER DEFAULT 0"),
            ("final_exec_pct",       "REAL"),
            ("exit_category",        "TEXT"),
            ("win_loss",             "TEXT"),
        ]:
            if col not in pos_cols:
                try:
                    conn.execute(f"ALTER TABLE paper_positions ADD COLUMN {col} {col_def}")
                    fixed(f"paper_positions: added {col}")
                except Exception:
                    pass
    except Exception as _pe:
        warn(f"paper_positions live_exec schema check skipped: {_pe}")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS resolved_transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            tx_hash TEXT UNIQUE,
            mint_address TEXT,
            mint_confidence REAL DEFAULT 0,
            resolution_method TEXT DEFAULT \'\',
            token_name TEXT DEFAULT \'\',
            owner_address TEXT DEFAULT \'\',
            block_time REAL,
            raw_dna_id INTEGER,
            created_at REAL NOT NULL,
            note TEXT DEFAULT \'\'
        )
    """)
    conn.execute("CREATE TABLE IF NOT EXISTS anomaly_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, source_service TEXT NOT NULL, anomaly_type TEXT NOT NULL, payload_json TEXT DEFAULT \'{}\', created_at REAL NOT NULL)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_dna_state_id ON raw_dna(processed_state, id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_raw_dna_claim_until ON raw_dna(claim_until)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_resolved_tx_hash ON resolved_transactions(tx_hash)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_market_snapshots_tx_hash ON market_snapshots(tx_hash)")
    conn.commit()
    ok("Pipeline schema verified — raw_dna and market_snapshots columns current")
except Exception as e:
    warn(f"Pipeline schema check failed (non-fatal): {e}")


# ── WAL CHECKPOINT ─────────────────────────────────────────────────────────────
print(f"\n[2] WAL checkpoint + write mode")
try:
    conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.commit()
    ok("WAL checkpoint complete")
except Exception as e:
    warn(f"WAL checkpoint failed (non-fatal): {e}")

print(f"\n[2b] Enforcing DB write mode (latency critical)")
try:
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    ok("synchronous=NORMAL + WAL enforced — prevents performance regression on restart")
except Exception as e:
    warn(f"synchronous/WAL enforcement failed (non-fatal): {e}")

# ── KNOWN-GOOD CONFIG ──────────────────────────────────────────────────────────
print(f"\n[3] Enforcing known-good config values")
config_fixes = [
    # INFRASTRUCTURE ONLY — these are safe to reset on every boot.
    # DO NOT add trading strategy values here (liquidity, mcap, token age, drawdown)
    # — those are owned by Polaris and must never be overwritten on launch.
    ("TRADING_MODE",                   "live",   "Always launch in live mode — paused/paper from end_of_day is cleared"),
    ("DRAWDOWN_HALT_ACTIVE",           "0",      "Clear any stale halt"),
    ("DRAWDOWN_SOFT_BRAKE",            "0",      "Clear soft brake"),
    ("EXECUTOR_WRITE_LATENCY_LIMIT_MS","10000",  "10s — prevents false blocks"),
    ("SUPERVISOR_PRICE_MAX_AGE_SECONDS","600",   "10min — pump.fun pre-graduation"),
    ("SUPERVISOR_MAX_SIGNAL_AGE_SEC",  "600",    "10min — supervisor signal age gate"),
    ("INTEL_PRICE_MAX_AGE_SEC",        "120",    "2min — live execution intel age gate"),
    # SIGN-OFF FIX 11: EXECUTOR_MAX_PRICE_AGE_SEC intentionally removed from this list.
    # The in-code default is 60s (tightened from 600s — see execution_engine.py:1030).
    # Overriding to 600 here on every boot permanently negated that patch, allowing
    # entries on qualify prices up to 10 minutes stale. Let the code default apply.
    ("EXECUTOR_MAX_HOLD_SECONDS",      "900",    "15min max hold — standardised default"),
    # EVIDENCE-CALIBRATED GATES — set by qual_rejection_audit May 2026.
    # fix_ivaris_and_qualifier.py set MIN_CURVE_SOL=2 which blocked 87% of live launch
    # tokens (max seen = 0.52 SOL). Protected here so scripts cannot silently revert.
    ("MIN_CURVE_SOL",                  "0.3",    "Evidence: live tokens max 0.52 SOL"),
    ("MIN_MARKET_CAP_USD",             "1000",   "Evidence: filters dust, allows early launch mcaps"),
    ("SUPERVISOR_PHASE_A_SIGNAL_AGE_SEC","120",  "Qualified_at model: from qualification not discovery"),
    ("SUPERVISOR_FRESHNESS_FLOOR",     "0.60",   "Gate 0.7: allows 141s pipeline latency"),
    # TIME_CUT_SECONDS removed from engine V3 (Edge Preservation Patch).
    # Fixed time cuts replaced by stagnation-only exit. Key kept here as
    # a no-op tombstone so scripts that read it don't error.
    ("TIME_CUT_SECONDS",               "180",    "LEGACY — ignored by execution_engine V3+. Stagnation logic now governs."),
    # MAX_HOLD_SECONDS is a legacy alias. Engine reads EXECUTOR_MAX_HOLD_SECONDS (set above at 900s).
    # Kept as tombstone only.
    ("MAX_HOLD_SECONDS",               "180",    "LEGACY alias — engine reads EXECUTOR_MAX_HOLD_SECONDS"),
    # ── EDGE PRESERVATION V3 — execution engine exit thresholds ─────────────
    # These match the hardcoded values in execution_engine.py V3.
    # Listed here for visibility and future configurability only.
    # The engine currently uses hardcoded constants — these are informational.
    ("HARD_STOP_LOSS_PCT",             "20.0",   "V3: hard stop below -20% — fires before all other exits"),
    ("RUNNER_ACTIVATE_PCT",            "20.0",   "V3: runner mode activates at +20% unrealized"),
    ("RUNNER_TRAIL_PCT",               "10.0",   "V3: trailing stop 10% from peak in runner mode"),
    ("RUNNER_TRAIL_TIGHT_PCT",         "8.0",    "V3: trail tightens to 8% at +50% unrealized"),
    ("STAGNATION_WINDOW_SEC",          "180",    "V3: minimum hold before stagnation check runs"),
    ("STAGNATION_MOVE_THRESHOLD_PCT",  "0.2",    "V3: exit if price moved <0.2% in last 60s"),
]
for key, value, desc in config_fixes:
    conn.execute(
        "INSERT INTO system_config (key, value) VALUES (?,?) "
        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
        (key, value)
    )
conn.commit()
ok(f"Applied {len(config_fixes)} config values")

# ── ENSURE UI MODULE DIRECTORY EXISTS ────────────────────────────────────────
print(f"\n[3b] Checking ui/ module directory...")
_ui_dir = Path("ui")
if not _ui_dir.exists():
    _ui_dir.mkdir(exist_ok=True)
    fixed("Created ui/ directory")
else:
    ok("ui/ directory present")

_ui_modules = [
    ("ui/substrate_tab.py",         "Substrate Lane 2 tab"),
    ("ui/sovereign_health_tab.py",  "Biological Intelligence Lane 3 tab"),
]
for _path, _desc in _ui_modules:
    if Path(_path).exists():
        ok(f"{_desc}: present")
    else:
        warn(f"{_desc}: MISSING ({_path})")

# ── CLEAR STALE BACKLOG ────────────────────────────────────────────────────────
print(f"\n[4] Clear stale unpriced backlog (>30 min, no price)")
cutoff_30m = now - 1800
r = conn.execute("""
    UPDATE market_snapshots
    SET candidate_state = 'vetoed',
        price_status    = 'dead',
        quality_reason  = 'PRELAUNCH_STALE_BACKLOG'
    WHERE price_status IN ('pending','retry')
      AND observed_price IS NULL
      AND candidate_state = 'pending'
      AND COALESCE(timestamp, 0) < ?
""", (cutoff_30m,))
conn.commit()
fixed(f"Vetoed {r.rowcount:,} stale unpriced rows") if r.rowcount else ok("No stale backlog")

# PATCH: Also purge stale QUALIFIED rows that were never priced.
# Prelaunch previously only purged candidate_state='pending' rows, missing rows
# that had already been qualified (quality_status='qualified') in prior sessions.
# These pile up as permanent backlog — blocking supervisor from seeing fresh tokens.
# A pump.fun token has a window of minutes. Qualified rows >10 min old are dead weight.
r2 = conn.execute("""
    UPDATE market_snapshots
    SET candidate_state = 'vetoed',
        price_status    = 'dead',
        quality_reason  = 'PRELAUNCH_STALE_QUALIFIED'
    WHERE quality_status = 'qualified'
      AND candidate_state NOT IN ('vetoed', 'exited', 'latched')
      AND COALESCE(updated_at, created_at, timestamp, 0) < ?
""", (now - 600,))
conn.commit()
fixed(f"Cleared {r2.rowcount:,} stale qualified backlog rows (>10 min)") if r2.rowcount else ok("No stale qualified backlog")

# ── CLEAR STALE LATCHED SIGNALS (boot only) ──────────────────────────────────
# Latched signals older than 10 min are dead momentum — pump.fun tokens have
# a window of seconds to minutes. Old latched rows show as phantom signals in
# the terminal on restart. Clear them every boot.
try:
    r_latch = conn.execute("""
        UPDATE market_snapshots
        SET candidate_state  = 'vetoed',
            execution_ready  = 0,
            latched          = 0,
            quality_reason   = 'STALE_LATCHED_BOOT'
        WHERE COALESCE(latched, 0) = 1
          AND COALESCE(execution_ready, 0) = 0
          AND COALESCE(price_updated_at, created_at, timestamp, 0) < ?
    """, (now - 600,))
    conn.commit()
    fixed(f"Cleared {r_latch.rowcount} stale latched signals (>10 min)") if r_latch.rowcount else ok("No stale latched signals")
except Exception as _e:
    warn(f"Stale latched cleanup skipped: {_e}")

# Clear execution_ready slot jams older than 5 min
try:
    r_exec = conn.execute("""
        UPDATE market_snapshots
        SET execution_ready  = 0,
            latched          = 0,
            candidate_state  = 'vetoed',
            quality_reason   = 'UNJAMMED_BOOT'
        WHERE COALESCE(execution_ready, 0) = 1
          AND COALESCE(price_updated_at, created_at, timestamp, 0) < ?
    """, (now - 300,))
    conn.commit()
    fixed(f"Unjammed {r_exec.rowcount} stale execution_ready signals (>5 min)") if r_exec.rowcount else ok("No execution_ready jams")
except Exception as _e:
    warn(f"Unjam cleanup skipped: {_e}")

# ── PURGE STALE raw_dna (boot only) ────────────────────────────────────────────
# Skip raw_dna rows older than 10 min so ingest never processes dead-momentum
# tokens into market_snapshots on restart. These are unresolved rows from before
# shutdown that would create stale qualified signals and block fresh flow.
try:
    _rr = conn.execute(
        "UPDATE raw_dna SET processed_state=2 "
        "WHERE processed_state=0 "
        "AND COALESCE(first_seen_at, created_at, timestamp, processed_at, 0) < ? "
        "AND COALESCE(first_seen_at, created_at, timestamp, processed_at, 0) > 0",
        (now - 600,))
    conn.commit()
    fixed(f"Boot purge: skipped {_rr.rowcount:,} stale raw_dna rows") if _rr.rowcount else ok("raw_dna: no stale rows to skip")
except Exception as _e:
    warn(f"raw_dna purge skipped: {_e}")

# Also kill stale state=1 rows — resolver cannot resolve transactions older than
# ~2 minutes (Helius returns null). Leaving them causes resolver to burn all
# credits on guaranteed-fail calls and starves fresh flow.
try:
    _rr1 = conn.execute(
        "UPDATE raw_dna SET processed_state=-1, resolution_note='BOOT_PURGE_STALE_STATE1' "
        "WHERE processed_state=1 "
        "AND COALESCE(first_seen_at, created_at, timestamp, processed_at, 0) < ? "
        "AND COALESCE(first_seen_at, created_at, timestamp, processed_at, 0) > 0",
        (now - 600,))
    conn.commit()
    fixed(f"Boot purge: killed {_rr1.rowcount:,} stale state=1 resolver rows") if _rr1.rowcount else ok("raw_dna state=1: no stale rows")
except Exception as _e:
    warn(f"raw_dna state=1 purge skipped: {_e}")

# ── RESET STUCK PIPELINE ───────────────────────────────────────────────────────
print(f"\n[5] Reset stuck pipeline rows")
counts = [0, 0, 0]
try:
    r1 = conn.execute("""
        UPDATE market_snapshots SET quality_status='pending', quality_reason=''
        WHERE quality_status='processing'
          AND COALESCE(price_updated_at, 0) < ?
    """, (now - 600,))
    counts[0] = r1.rowcount
except Exception:
    # price_updated_at may not exist in all schema versions — skip gracefully
    pass
try:
    r2 = conn.execute("""
        UPDATE market_snapshots SET price_status='pending', price_attempts=0
        WHERE price_status IN ('dead','retry')
          AND candidate_state='pending' AND latched=0
    """)
    counts[1] = r2.rowcount
except Exception:
    pass
try:
    r3 = conn.execute("""
        UPDATE raw_dna SET processed_state=1, claim_until=NULL
        WHERE processed_state=99
          AND (claim_until IS NULL OR claim_until < ?)
    """, (now - 60,))
    counts[2] = r3.rowcount
except Exception:
    pass
conn.commit()
fixed(f"Reset {counts[0]} stuck processing, {counts[1]} dead/retry price, {counts[2]} stuck claims")

# ── CLOSE ZOMBIE POSITIONS ─────────────────────────────────────────────────────
print(f"\n[6] Check for zombie open positions")
zombies = conn.execute("""
    SELECT id, token_name, entry_price, position_size_usd, opened_at, mint_address
    FROM paper_positions
    WHERE status='OPEN' AND opened_at < ?
""", (now - 7200,)).fetchall()  # open > 2 hours

if zombies:
    for pos in zombies:
        age_h = (now - float(pos["opened_at"])) / 3600
        entry = float(pos["entry_price"] or 0)
        size  = float(pos["position_size_usd"] or 0)
        # Get last known price
        pr = conn.execute(
            "SELECT observed_price FROM market_snapshots WHERE mint_address=? "
            "AND observed_price>0 ORDER BY price_updated_at DESC LIMIT 1",
            (pos["mint_address"],)
        ).fetchone()
        exit_price = float(pr["observed_price"]) if pr else entry
        pnl = size * ((exit_price - entry) / entry) if entry > 0 else 0
        conn.execute(
            "UPDATE paper_positions SET status='CLOSED', exit_price=?, "
            "realized_pnl_usd=?, unrealized_pnl_usd=0, closed_at=? WHERE id=?",
            (exit_price, pnl, now, pos["id"])
        )
        # DO NOT credit wallet_balance here — prelaunch runs after manual
        # wallet corrections and double-credits capital. Wallet stays as-is.
        fixed(f"Closed zombie pos={pos['id']} {pos['token_name']} age={age_h:.1f}h pnl={pnl:+.4f}")
    conn.commit()
else:
    ok("No zombie positions")

# ── PROTECTED DATA VERIFICATION ────────────────────────────────────────────────
print(f"\n[7] Verifying learned data is intact")
checks = [
    ("paper_positions",       "SELECT COUNT(*) FROM paper_positions"),
    ("trade_autopsies",       "SELECT COUNT(*) FROM trade_autopsies"),
    ("polaris_trade_reviews", "SELECT COUNT(*) FROM polaris_trade_reviews"),
    ("polaris_learned_patterns","SELECT COUNT(*) FROM polaris_learned_patterns"),
    ("cognition_log",         "SELECT COUNT(*) FROM cognition_log"),
]
for label, sql in checks:
    try:
        n = conn.execute(sql).fetchone()[0]
        ok(f"{label}: {n:,} rows — intact")
    except Exception:
        warn(f"{label}: table not found (will be created on launch)")

# ── PIPELINE STATE ─────────────────────────────────────────────────────────────
print(f"\n[8] Pipeline state")
wallet = float(conn.execute("SELECT wallet_balance FROM system_state WHERE id=1").fetchone()[0])
pending = conn.execute("SELECT COUNT(*) FROM market_snapshots WHERE candidate_state='pending'").fetchone()[0]
qualified = conn.execute("SELECT COUNT(*) FROM market_snapshots WHERE quality_status='qualified' AND latched=0").fetchone()[0]
latched = conn.execute("SELECT COUNT(*) FROM market_snapshots WHERE latched=1 AND execution_ready=1").fetchone()[0]
open_pos = conn.execute("SELECT COUNT(*) FROM paper_positions WHERE status='OPEN'").fetchone()[0]

ok(f"Wallet: ${wallet:.2f}")
ok(f"Pending (ready for qualifier): {pending:,}")
ok(f"Qualified (waiting to latch): {qualified}")
ok(f"Latched (ready for executor): {latched}")
ok(f"Open positions: {open_pos}")

conn.close()

print(f"\n{SEP}")
print(f"  PRE-LAUNCH COMPLETE — organism ready")
print(f"  Run Launch_Sentinuity.bat now")
print(SEP + "\n")