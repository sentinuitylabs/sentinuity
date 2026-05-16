"""
FIX 1: Set synchronous=NORMAL on both DBs.
FULL (2) fsyncs every write to disk. NORMAL (1) only fsyncs at checkpoints.
In WAL mode with NORMAL, you lose at most one checkpoint of data on power loss —
acceptable for a paper trading system. Expected improvement: 50-80% reduction
in UPDATE paper_positions write time (currently 86ms median).
"""
import sqlite3, os

DBS = [
    r"C:\Users\Polar\.openclaw\workspace\trading-bot\sentinuity_matrix.db",
    r"C:\Users\Polar\.openclaw\workspace\trading-bot\sentinuity_intelligence.db",
]

for path in DBS:
    if not os.path.exists(path): print(f"✗ not found: {path}"); continue
    db = sqlite3.connect(path, timeout=5)
    before = db.execute("PRAGMA synchronous").fetchone()[0]
    db.execute("PRAGMA synchronous=NORMAL")
    after  = db.execute("PRAGMA synchronous").fetchone()[0]
    db.close()
    print(f"✓  {os.path.basename(path)}  synchronous: {before} → {after}  (2=FULL was killing write speed)")
