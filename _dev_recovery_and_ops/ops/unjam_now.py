# python ops\unjam_now.py
import sqlite3, time
from pathlib import Path

_here = Path(__file__).resolve().parent
# Walk up until we find the project root (has core/ and services/ subdirs)
ROOT = _here
for _candidate in [_here, _here.parent, _here.parent.parent, _here.parent.parent.parent]:
    if (_candidate / "core").exists() and (_candidate / "services").exists():
        ROOT = _candidate
        break
DB   = ROOT / "sentinuity_matrix.db"

conn = sqlite3.connect(str(DB), timeout=15)
conn.row_factory = sqlite3.Row
now  = time.time()

# Check actual columns first
ms_cols = {r[1] for r in conn.execute("PRAGMA table_info(market_snapshots)").fetchall()}
pp_cols = {r[1] for r in conn.execute("PRAGMA table_info(paper_positions)").fetchall()}

print("Clearing jammed latched signals...")

# Clear execution_ready signals older than 5 min (stuck)
r1 = conn.execute("""
    UPDATE market_snapshots
    SET execution_ready=0, latched=0,
        candidate_state='vetoed',
        quality_reason='UNJAMMED'
    WHERE execution_ready=1
      AND COALESCE(price_updated_at, timestamp, 0) < ?
""", (now - 300,))
conn.commit()
print(f"  Cleared {r1.rowcount} stale execution_ready signals")

# Clear close_claimed_until on paper_positions if column exists
if 'close_claimed_until' in pp_cols:
    SANE = now + (7 * 24 * 3600)
    r2 = conn.execute("""
        UPDATE paper_positions
        SET close_claimed_until=NULL
        WHERE close_claimed_until > ?
    """, (SANE,))
    conn.commit()
    print(f"  Cleared {r2.rowcount} jammed position claims")
else:
    print("  paper_positions.close_claimed_until not present - skipping")

# Also clear any market_snapshots close_claimed_until if it exists
if 'close_claimed_until' in ms_cols:
    SANE = now + (7 * 24 * 3600)
    r3 = conn.execute("""
        UPDATE market_snapshots
        SET close_claimed_until=NULL,
            execution_ready=0, latched=0
        WHERE close_claimed_until > ?
    """, (SANE,))
    conn.commit()
    print(f"  Cleared {r3.rowcount} jammed snapshot claims")

# Reset SYSTEM_REPAIR proposals
r4 = conn.execute("""
    UPDATE polaris_proposals
    SET seen_count=0, status='open'
    WHERE UPPER(proposal_type)='SYSTEM_REPAIR'
      AND status IN ('open','debating','pending','critic_unavailable')
""")
conn.commit()
print(f"  Reset {r4.rowcount} SYSTEM_REPAIR proposals")

# Show where tokens are stuck
print("\nToken pipeline state:")
rows = conn.execute("""
    SELECT quality_status, price_status, candidate_state, COUNT(*) n
    FROM market_snapshots
    GROUP BY quality_status, price_status, candidate_state
    ORDER BY n DESC LIMIT 12
""").fetchall()
for r in rows:
    print(f"  quality={str(r['quality_status'] or 'NULL'):<12} price={str(r['price_status'] or 'NULL'):<10} state={str(r['candidate_state'] or 'NULL'):<12} n={r['n']}")

ready = conn.execute("""
    SELECT COUNT(*) n FROM market_snapshots
    WHERE quality_status='qualified'
      AND price_status='priced'
      AND COALESCE(execution_ready,0)=0
      AND COALESCE(latched,0)=0
""").fetchone()['n']
print(f"\nReady for supervisor (qualified+priced, not latched): {ready}")

conn.close()
print("Done. Services still running.")
