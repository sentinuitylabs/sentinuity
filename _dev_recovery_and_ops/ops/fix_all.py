from pathlib import Path

_here = Path(__file__).resolve().parent
# Walk up until we find the project root (has core/ and services/ subdirs)
ROOT = _here
for _candidate in [_here, _here.parent, _here.parent.parent, _here.parent.parent.parent]:
    if (_candidate / "core").exists() and (_candidate / "services").exists():
        ROOT = _candidate
        break
DB   = ROOT / "sentinuity_matrix.db"
LOG  = ROOT / "logs"
"""
fix_all.py
==========
Run this every time trading stalls, or automatically via Launch_Sentinuity.bat.
Clears all known pipeline blockers in one shot:
1. Kills stale raw_dna rows (handles NULL timestamps via string ISO comparison)
2. Clears orphaned MTM snapshots (blocks weaver dedup)
3. Resets TOKEN_TOO_YOUNG rejected rows to pending
4. Releases any stuck qualify locks
5. Clears stale dedup window (NULL-safe: any-timestamp OR no-timestamp >20min)
6. WAL checkpoint
7. Veto rejected+pending blocking rows
"""
import sqlite3, time

db = sqlite3.connect(str(DB), timeout=30)
db.execute("PRAGMA journal_mode=WAL")
db.execute("PRAGMA busy_timeout=30000")
db.row_factory = sqlite3.Row
now = time.time()

print("SENTINUITY PIPELINE FIX - " + str(int(now)))

# ── helpers ───────────────────────────────────────────────────────────────────
def _ts_expr(col):
    """
    Returns a SQL expression that resolves a timestamp column to a float epoch,
    handling both float-epoch strings and ISO datetime strings (e.g. '2026-05-13 09:00:00').
    CAST of an ISO string returns 0 in SQLite, so we use strftime as fallback.
    Result is 0 when the column is NULL or unparseable.
    """
    return (
        f"CASE "
        f"  WHEN {col} IS NULL THEN 0 "
        f"  WHEN CAST({col} AS REAL) > 1000000000 THEN CAST({col} AS REAL) "
        f"  ELSE CAST(strftime('%s', {col}) AS REAL) "
        f"END"
    )

# Best effective timestamp across all three columns
_eff = (
    f"MAX("
    f"  {_ts_expr('first_seen_at')}, "
    f"  {_ts_expr('created_at')}, "
    f"  {_ts_expr('timestamp')}, "
    f"  {_ts_expr('price_updated_at')}"
    f")"
)

# Snapshot effective timestamp (price_updated_at and first_seen_at)
_snap_eff = (
    f"MAX("
    f"  {_ts_expr('price_updated_at')}, "
    f"  {_ts_expr('first_seen_at')}, "
    f"  {_ts_expr('created_at')}, "
    f"  {_ts_expr('timestamp')}"
    f")"
)

# ── 1. Kill stale raw_dna older than 10 min (NULL-safe) ───────────────────────
r1 = db.execute(
    f"""
    UPDATE raw_dna SET processed_state=-1, resolution_note='STALE_KILLED'
    WHERE processed_state IN (0,1)
    AND {_eff} > 0
    AND {_eff} < ?
    """,
    (now - 600,)
)
db.commit()
print('[1] Killed stale raw_dna rows: ' + str(r1.rowcount))

# ── 2. Clear orphaned MTM snapshots ──────────────────────────────────────────
r2 = db.execute("""
    UPDATE market_snapshots SET candidate_state='vetoed', quality_reason='MTM_ORPHAN_CLEARED'
    WHERE candidate_state='mtm'
    AND (mint_address NOT IN (SELECT mint_address FROM paper_positions WHERE status='OPEN')
         OR mint_address IS NULL)
""")
db.commit()
print('[2] Cleared orphaned MTM snapshots: ' + str(r2.rowcount))

# ── 3. Reset TOKEN_TOO_YOUNG rejected rows to pending ─────────────────────────
r3 = db.execute("""
    UPDATE market_snapshots
    SET quality_status='pending', quality_reason='', is_tradeable=0,
        qualify_claimed_until=NULL, candidate_state='pending'
    WHERE quality_status='rejected' AND quality_reason LIKE 'TOKEN_TOO_YOUNG%'
""")
db.commit()
print('[3] Reset TOKEN_TOO_YOUNG rows: ' + str(r3.rowcount))

# ── 4. Release stuck qualify locks ───────────────────────────────────────────
r4 = db.execute("""
    UPDATE market_snapshots SET qualify_claimed_until=NULL
    WHERE candidate_state='pending' AND quality_status='pending'
    AND qualify_claimed_until IS NOT NULL AND qualify_claimed_until < ?
""", (now,))
db.commit()
print('[4] Released stuck qualifier locks: ' + str(r4.rowcount))

# ── 5. Clear stale dedup window (NULL-safe, >20min) ──────────────────────────
# Two passes:
# Pass A — rows WITH a resolvable timestamp older than 20min
r5a = db.execute(
    f"""
    UPDATE market_snapshots SET candidate_state='vetoed', quality_reason='STALE_DEDUP_CLEAR'
    WHERE candidate_state NOT IN ('vetoed','exited','mtm')
    AND quality_status NOT IN ('qualified')
    AND latched=0
    AND {_snap_eff} > 0
    AND {_snap_eff} < ?
    """,
    (now - 1200,)
)
db.commit()

# Pass B — rows where ALL timestamps are NULL/unparseable (zero effective ts)
# These are truly unknown-age rows — safe to veto as they can never be dated
r5b = db.execute(
    f"""
    UPDATE market_snapshots SET candidate_state='vetoed', quality_reason='NULL_TS_CLEAR'
    WHERE candidate_state NOT IN ('vetoed','exited','mtm','latched')
    AND quality_status NOT IN ('qualified')
    AND latched=0
    AND qualified_at IS NULL
    AND {_snap_eff} = 0
    """
)
db.commit()
print('[5] Cleared stale dedup window: ' + str(r5a.rowcount + r5b.rowcount)
      + f' ({r5a.rowcount} dated, {r5b.rowcount} null-ts)')

# ── 6. WAL checkpoint ─────────────────────────────────────────────────────────
db.execute("PRAGMA wal_checkpoint(PASSIVE)")
db.commit()
print('[6] WAL checkpoint done')

# ── 7. Veto rejected+pending blocking rows ────────────────────────────────────
r7 = db.execute("""
    UPDATE market_snapshots
    SET candidate_state='vetoed'
    WHERE quality_status='rejected'
    AND candidate_state='pending'
""")
db.commit()
print('[7] Vetoed rejected+pending blocking rows: ' + str(r7.rowcount))

# ── Summary ───────────────────────────────────────────────────────────────────
s0 = db.execute('SELECT COUNT(*) FROM raw_dna WHERE processed_state=0').fetchone()[0]
s1 = db.execute('SELECT COUNT(*) FROM raw_dna WHERE processed_state=1').fetchone()[0]
pending   = db.execute("SELECT COUNT(*) FROM market_snapshots WHERE candidate_state='pending'").fetchone()[0]
qualified = db.execute("SELECT COUNT(*) FROM market_snapshots WHERE quality_status='qualified' AND candidate_state='pending'").fetchone()[0]
print('\nPipeline state after fix:')
print('  raw_dna state=0: ' + str(s0) + ' (fresh only)')
print('  raw_dna state=1: ' + str(s1) + ' (fresh only)')
print('  snapshots pending: ' + str(pending))
print('  snapshots qualified: ' + str(qualified))
print('\nDone. Trading should resume within 60 seconds.')
db.close()
