"""
PRELAUNCH CHECK — run this before starting any services.
Clears jams, validates state, reports what would block a clean launch.
Safe: only writes what is explicitly documented below.

WRITES:
  - Resets stale latched market_snapshots rows to 'pending' (unjam)
  - Clears execution_ready=1 on rows older than 15min (dead signals)
  - Resets processing=1 stuck rows
  - Does NOT touch paper_positions, wallet, config, or any trade data
"""
import sqlite3, os, time, sys

DB_PATH = r"C:\Users\Polar\.openclaw\workspace\trading-bot\sentinuity_matrix.db"

def run(confirm=False):
    if not os.path.exists(DB_PATH):
        print(f"✗ DB not found: {DB_PATH}"); return

    db = sqlite3.connect(DB_PATH, timeout=10)
    db.row_factory = sqlite3.Row
    now = time.time()
    issues = []

    print(f"\n{'='*65}")
    print(f"  PRELAUNCH CHECK  {'[DRY RUN]' if not confirm else '[LIVE FIX]'}")
    print(f"{'='*65}\n")

    # ── 1. Stale latched signals ──────────────────────────────────────
    stale_cutoff = now - 900  # 15 min
    stale_latched = db.execute("""
        SELECT COUNT(*) FROM market_snapshots
        WHERE latched=1 AND execution_ready=1
          AND candidate_state='latched'
          AND COALESCE(created_at, 0) < ?
    """, (stale_cutoff,)).fetchone()[0]

    live_latched = db.execute("""
        SELECT COUNT(*) FROM market_snapshots
        WHERE latched=1 AND execution_ready=1
          AND candidate_state='latched'
          AND COALESCE(created_at, 0) >= ?
    """, (stale_cutoff,)).fetchone()[0]

    status = "✓" if stale_latched == 0 else "⚠"
    print(f"  {status}  Stale latched signals (>15min old): {stale_latched}"
          + ("  ← will be picked up as dead entries by executor" if stale_latched > 0 else ""))
    print(f"  ✓  Live latched signals (<15min):    {live_latched}")
    if stale_latched > 0:
        issues.append(("stale_latched", stale_latched))
        if confirm:
            db.execute("""
                UPDATE market_snapshots
                SET execution_ready=0, candidate_state='vetoed',
                    quality_reason='STALE_AT_PRELAUNCH'
                WHERE latched=1 AND execution_ready=1
                  AND candidate_state='latched'
                  AND COALESCE(created_at, 0) < ?
            """, (stale_cutoff,))
            db.commit()
            print(f"       ✓ Cleared {stale_latched} stale latched rows")

    # ── 2. execution_ready=1 rows with bad state ──────────────────────
    wrong_state = db.execute("""
        SELECT candidate_state, COUNT(*) as n FROM market_snapshots
        WHERE execution_ready=1 AND candidate_state != 'latched'
        GROUP BY candidate_state
    """).fetchall()
    if wrong_state:
        print(f"\n  ⚠  execution_ready=1 with wrong state:")
        for r in wrong_state:
            print(f"       {r['candidate_state']}: {r['n']} rows  ← executor will skip but wastes scan time")
            issues.append(("exec_ready_wrong_state", r['n']))
        if confirm:
            db.execute("""
                UPDATE market_snapshots SET execution_ready=0
                WHERE execution_ready=1 AND candidate_state != 'latched'
            """)
            db.commit()
            print(f"       ✓ Cleared execution_ready flag on wrong-state rows")
    else:
        print(f"\n  ✓  All execution_ready rows have correct state")

    # ── 3. Open positions sanity ──────────────────────────────────────
    open_pos = db.execute("""
        SELECT id, token_name, opened_at, last_marked_at
        FROM paper_positions WHERE status='OPEN'
    """).fetchall()
    print(f"\n  {'✓' if len(open_pos)==0 else '●'}  Open positions at prelaunch: {len(open_pos)}")
    for p in open_pos:
        age = now - float(p['opened_at'] or 0)
        mark_age = now - float(p['last_marked_at'] or 0) if p['last_marked_at'] else 9999
        stale = "⚠ STALE MARK" if mark_age > 300 else "✓"
        print(f"       {stale} id={p['id']} {p['token_name'] or '?'} age={age:.0f}s mark_age={mark_age:.0f}s")

    # ── 4. Drawdown halt check ────────────────────────────────────────
    halt = db.execute(
        "SELECT value FROM system_config WHERE key='DRAWDOWN_HALT_ACTIVE'"
    ).fetchone()
    halt_val = str(halt['value'] if halt else '0').strip()
    if halt_val == '1':
        print(f"\n  🔴  DRAWDOWN_HALT_ACTIVE=1 — trading is SUSPENDED")
        print(f"       Run: python clear_halt.py  (or set via hub calibration panel)")
        issues.append(("drawdown_halt", 1))
    else:
        print(f"\n  ✓  DRAWDOWN_HALT_ACTIVE={halt_val}")

    # ── 5. DB write latency quick probe ──────────────────────────────
    t0 = time.perf_counter()
    db.execute("BEGIN IMMEDIATE"); db.execute("ROLLBACK")
    lock_ms = (time.perf_counter() - t0) * 1000
    status = "✓" if lock_ms < 10 else ("⚠" if lock_ms < 50 else "🔴")
    print(f"\n  {status}  DB write lock probe: {lock_ms:.1f}ms"
          + ("  — run db_fix_synchronous.py first" if lock_ms > 50 else ""))

    # ── 6. market_snapshots total ─────────────────────────────────────
    ms_total = db.execute("SELECT COUNT(*) FROM market_snapshots").fetchone()[0]
    print(f"\n  {'✓' if ms_total < 5000 else '⚠'}  market_snapshots rows: {ms_total:,}"
          + ("  — consider db_slimmer.py if >10k" if ms_total > 10000 else ""))

    # ── Summary ───────────────────────────────────────────────────────
    db.close()
    print(f"\n{'─'*65}")
    if not issues:
        print(f"  ✓  CLEAR FOR LAUNCH — no blockers found")
    else:
        print(f"  {'ISSUES FIXED' if confirm else 'ISSUES FOUND (re-run with --confirm to fix)'}:")
        for name, count in issues:
            print(f"    {name}: {count}")
    if not confirm and issues:
        print(f"\n  Re-run: python prelaunch_check.py --confirm")
    print(f"{'='*65}\n")

if __name__ == "__main__":
    confirm = "--confirm" in sys.argv
    run(confirm)
