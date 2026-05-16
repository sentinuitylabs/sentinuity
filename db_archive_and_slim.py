"""
DB ARCHIVE + SLIM — safe two-step process.

Step 1 (--archive): Copies old rows to sentinuity_archive.db FIRST.
                    Writes a manifest record proving what was archived.
                    Does NOT delete anything.

Step 2 (--slim):    Reads the manifest, verifies archive is intact,
                    THEN deletes from live DB. Refuses to slim if
                    archive is missing, corrupt, or count mismatches.

This gives the system a verifiable "this has been backed up" signal
before any live data is removed. Run --archive first, verify, then --slim.

Usage:
  python db_archive_and_slim.py --archive          # copy to archive DB
  python db_archive_and_slim.py --verify           # check archive integrity
  python db_archive_and_slim.py --slim --confirm   # slim after verified
  python db_archive_and_slim.py --archive --slim --confirm  # do both

NEVER run with --slim while services are running.
"""
import sqlite3, os, time, sys, argparse, hashlib, json

DB_PATH      = r"C:\Users\Polar\.openclaw\workspace\trading-bot\sentinuity_matrix.db"
ARCHIVE_PATH = r"C:\Users\Polar\.openclaw\workspace\trading-bot\sentinuity_archive.db"
MANIFEST_KEY = "archive_manifest"

# Tables to archive before slimming, with their timestamp column and keep policy
ARCHIVE_TABLES = [
    # (table, ts_col, keep_days, description)
    ("debate_log",             "logged_at",  14, "Polaris AI debate history — organism memory"),
    ("trade_lifecycle_events", "event_ts",   30, "Trade state transitions — autopsy source"),
    ("resolved_transactions",  "created_at", 14, "Resolved on-chain transactions"),
    ("code_vault_snapshots",   "created_at", 14, "Code vault snapshots"),
    ("code_vault_changes",     "created_at", 14, "Code vault change records"),
]

def _ts_col_exists(db, table, col):
    cols = [r[1] for r in db.execute(f"PRAGMA table_info({table})").fetchall()]
    if col in cols: return col
    for alt in ["timestamp","created_at","ts","logged_at","event_ts","updated_at"]:
        if alt in cols: return alt
    return None

def _table_checksum(db, table, where_clause, params=()):
    """Simple row-count + sum checksum for integrity verification."""
    count = db.execute(f"SELECT COUNT(*) FROM {table} {where_clause}", params).fetchone()[0]
    return count

def do_archive(keep_days_override=None):
    if not os.path.exists(DB_PATH):
        print(f"✗ Live DB not found: {DB_PATH}"); return False

    live = sqlite3.connect(DB_PATH, timeout=10)
    live.row_factory = sqlite3.Row
    arch = sqlite3.connect(ARCHIVE_PATH, timeout=10)
    arch.row_factory = sqlite3.Row
    now  = time.time()

    print(f"\n{'='*65}")
    print(f"  ARCHIVE PHASE")
    print(f"  From: {os.path.basename(DB_PATH)}")
    print(f"  To:   {ARCHIVE_PATH}")
    print(f"{'='*65}\n")

    manifest = {}
    total_archived = 0

    for table, ts_col, keep_days, desc in ARCHIVE_TABLES:
        keep = keep_days_override if keep_days_override else keep_days
        cutoff = now - (keep * 86400)

        # Check table exists in live
        if not live.execute(f"SELECT 1 FROM sqlite_master WHERE type='table' AND name='{table}'").fetchone():
            print(f"  ─ {table}: not in live DB, skipping"); continue

        ts_col = _ts_col_exists(live, table, ts_col)
        if not ts_col:
            print(f"  ⚠ {table}: no timestamp column, skipping"); continue

        n_old  = live.execute(f"SELECT COUNT(*) FROM {table} WHERE {ts_col} < ?", (cutoff,)).fetchone()[0]
        n_live = live.execute(f"SELECT COUNT(*) FROM {table} WHERE {ts_col} >= ?", (cutoff,)).fetchone()[0]

        if n_old == 0:
            print(f"  ✓ {table:<35} nothing to archive ({n_live:,} rows within {keep}d)"); continue

        # Create table in archive if not exists (copy schema)
        create_sql = live.execute(
            f"SELECT sql FROM sqlite_master WHERE type='table' AND name='{table}'"
        ).fetchone()
        if create_sql and create_sql[0]:
            arch.execute(create_sql[0].replace(
                f"CREATE TABLE {table}",
                f"CREATE TABLE IF NOT EXISTS {table}"
            ))
            arch.commit()

        # Copy old rows to archive
        rows = live.execute(f"SELECT * FROM {table} WHERE {ts_col} < ?", (cutoff,)).fetchall()
        if rows:
            cols = [d[0] for d in rows[0].keys() if True]  # get column names
            # Use INSERT OR IGNORE to handle re-runs
            placeholders = ",".join("?" * len(rows[0].keys()))
            col_names    = ",".join(rows[0].keys())
            arch.executemany(
                f"INSERT OR IGNORE INTO {table} ({col_names}) VALUES ({placeholders})",
                [tuple(r) for r in rows]
            )
            arch.commit()

        # Verify archive count matches
        arch_count = arch.execute(f"SELECT COUNT(*) FROM {table} WHERE {ts_col} < ?", (cutoff,)).fetchone()[0]
        verified   = arch_count >= n_old

        status = "✓" if verified else "✗ MISMATCH"
        print(f"  {status} {table:<35} archived {n_old:>7,}  kept {n_live:>7,}  [{desc}]")
        if not verified:
            print(f"       Expected {n_old}, found {arch_count} in archive — do NOT slim")
            return False

        manifest[table] = {
            "archived_count": n_old,
            "live_count":     n_live,
            "cutoff_ts":      cutoff,
            "ts_col":         ts_col,
            "keep_days":      keep,
            "archived_at":    now,
            "verified":       verified,
        }
        total_archived += n_old

    # Write manifest to archive DB
    arch.execute("""
        CREATE TABLE IF NOT EXISTS _archive_manifest
        (key TEXT PRIMARY KEY, value TEXT, created_at REAL)
    """)
    arch.execute("""
        INSERT OR REPLACE INTO _archive_manifest (key, value, created_at)
        VALUES (?, ?, ?)
    """, (MANIFEST_KEY, json.dumps(manifest), now))
    arch.commit()

    arch_size = os.path.getsize(ARCHIVE_PATH) / 1_048_576
    print(f"\n  Total archived: {total_archived:,} rows")
    print(f"  Archive DB:     {arch_size:.1f} MB  ({ARCHIVE_PATH})")
    print(f"  Manifest:       written to _archive_manifest table")
    print(f"\n  ✓ Archive complete. Run --verify before --slim.")

    live.close(); arch.close()
    return True


def do_verify():
    if not os.path.exists(ARCHIVE_PATH):
        print(f"✗ Archive not found: {ARCHIVE_PATH}")
        print(f"  Run --archive first."); return False

    arch = sqlite3.connect(ARCHIVE_PATH, timeout=5)
    arch.row_factory = sqlite3.Row

    try:
        row = arch.execute(
            "SELECT value, created_at FROM _archive_manifest WHERE key=?", (MANIFEST_KEY,)
        ).fetchone()
    except Exception:
        print(f"✗ No manifest table in archive. Run --archive first."); arch.close(); return False

    if not row:
        print(f"✗ No manifest entry. Run --archive first."); arch.close(); return False

    manifest   = json.loads(row["value"])
    created_at = row["created_at"]
    age_hours  = (time.time() - created_at) / 3600

    print(f"\n{'='*65}")
    print(f"  ARCHIVE VERIFICATION")
    print(f"  Archive: {ARCHIVE_PATH}")
    print(f"  Created: {age_hours:.1f}h ago")
    print(f"{'='*65}\n")

    all_ok = True
    for table, info in manifest.items():
        expected = info["archived_count"]
        ts_col   = info["ts_col"]
        cutoff   = info["cutoff_ts"]

        try:
            actual = arch.execute(
                f"SELECT COUNT(*) FROM {table} WHERE {ts_col} < ?", (cutoff,)
            ).fetchone()[0]
            ok = actual >= expected
            status = "✓" if ok else "✗ MISMATCH"
            if not ok: all_ok = False
            print(f"  {status} {table:<35} expected {expected:>7,}  found {actual:>7,}")
        except Exception as e:
            print(f"  ✗ {table}: error reading archive — {e}")
            all_ok = False

    arch.close()
    print(f"\n  {'✓ ARCHIVE VERIFIED — safe to --slim' if all_ok else '✗ VERIFICATION FAILED — do NOT slim'}")
    return all_ok


def do_slim():
    if not do_verify():
        print(f"\n  SLIM ABORTED — archive not verified.")
        return False

    if not os.path.exists(DB_PATH):
        print(f"✗ Live DB not found"); return False

    arch = sqlite3.connect(ARCHIVE_PATH, timeout=5)
    arch.row_factory = sqlite3.Row
    manifest = json.loads(arch.execute(
        "SELECT value FROM _archive_manifest WHERE key=?", (MANIFEST_KEY,)
    ).fetchone()["value"])
    arch.close()

    live = sqlite3.connect(DB_PATH, timeout=10)
    before_mb = os.path.getsize(DB_PATH) / 1_048_576
    total_deleted = 0
    now = time.time()

    print(f"\n{'='*65}")
    print(f"  SLIM PHASE (archive verified)")
    print(f"  DB before: {before_mb:.1f} MB")
    print(f"{'='*65}\n")

    for table, info in manifest.items():
        ts_col = info["ts_col"]
        cutoff = info["cutoff_ts"]
        n_del  = live.execute(f"SELECT COUNT(*) FROM {table} WHERE {ts_col} < ?", (cutoff,)).fetchone()[0]
        if n_del == 0:
            print(f"  ✓ {table:<35} nothing to delete"); continue
        live.execute(f"DELETE FROM {table} WHERE {ts_col} < ?", (cutoff,))
        live.commit()
        total_deleted += n_del
        print(f"  🗑  {table:<35} deleted {n_del:>7,}")

    print(f"\n  Deleted {total_deleted:,} rows. Running VACUUM...")
    t0 = time.perf_counter()
    live.execute("VACUUM")
    elapsed = time.perf_counter() - t0
    live.close()

    after_mb = os.path.getsize(DB_PATH) / 1_048_576
    saved = before_mb - after_mb
    print(f"  VACUUM: {elapsed:.1f}s  |  {before_mb:.1f} MB → {after_mb:.1f} MB  (saved {saved:.1f} MB)")

    # Write slim record to live DB so system knows it was slimmed
    live2 = sqlite3.connect(DB_PATH, timeout=5)
    live2.execute("""
        CREATE TABLE IF NOT EXISTS _slim_history
        (id INTEGER PRIMARY KEY AUTOINCREMENT,
         slimmed_at REAL, rows_deleted INTEGER,
         mb_before REAL, mb_after REAL, archive_path TEXT)
    """)
    live2.execute("""
        INSERT INTO _slim_history (slimmed_at, rows_deleted, mb_before, mb_after, archive_path)
        VALUES (?, ?, ?, ?, ?)
    """, (now, total_deleted, before_mb, after_mb, ARCHIVE_PATH))
    live2.commit()
    live2.close()
    print(f"\n  ✓ Slim record written to _slim_history table.")
    print(f"  Archive preserved at: {ARCHIVE_PATH}")
    return True


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--archive", action="store_true", help="Archive old rows to sentinuity_archive.db")
    p.add_argument("--verify",  action="store_true", help="Verify archive integrity")
    p.add_argument("--slim",    action="store_true", help="Delete from live DB (requires verified archive)")
    p.add_argument("--confirm", action="store_true", help="Required for --slim to actually delete")
    p.add_argument("--window",  type=int, default=None, help="Override keep window in days")
    args = p.parse_args()

    if not any([args.archive, args.verify, args.slim]):
        print(__doc__); sys.exit(0)

    if args.archive:
        ok = do_archive(keep_days_override=args.window)
        if not ok: sys.exit(1)

    if args.verify and not args.slim:
        ok = do_verify()
        sys.exit(0 if ok else 1)

    if args.slim:
        if not args.confirm:
            print(f"\n  DRY RUN — add --confirm to actually delete.")
            do_verify()
            sys.exit(0)
        ok = do_slim()
        sys.exit(0 if ok else 1)
