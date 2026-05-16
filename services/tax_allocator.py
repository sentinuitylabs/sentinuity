"""
tax_allocator.py — Sentinuity Tax Reserve Engine (AU)
======================================================
Allocates tax liability on every profitable trade close.
Never sends funds. Never touches execution timing.
Virtual capital reduction only — real sweep is manual.

AU context:
  - Active trading income taxed as income, not CGT
  - Tax-free threshold ~$18,200 (adjust TAX_RATE once you know your bracket)
  - DSP: still taxable above threshold, effective rate depends on total income
  - Safe default: 20% (conservative — adjust after first tax return)

Deploy to: trading-bot\services\tax_allocator.py
Hook in:   close_position_canonical() in execution_engine.py
"""
import sqlite3
import time
import os
from pathlib import Path

# Robust root resolution — works from any subfolder
_here = Path(__file__).resolve().parent
ROOT = _here
for _c in [_here, _here.parent, _here.parent.parent]:
    if (_c / "core").exists() and (_c / "services").exists():
        ROOT = _c
        break
DB_PATH = ROOT / "sentinuity_matrix.db"

# ── Tax rate ─────────────────────────────────────────────────────────────────
# Start at 20% — conservative AU buffer.
# Adjust after first tax return + accountant advice.
# Can also be overridden via system_config key TAX_RESERVE_RATE.
DEFAULT_TAX_RATE = 0.20

def _get_rate() -> float:
    """Read rate from system_config if set, else use DEFAULT_TAX_RATE."""
    try:
        c = sqlite3.connect(str(DB_PATH), timeout=3)
        row = c.execute(
            "SELECT value FROM system_config WHERE key='TAX_RESERVE_RATE'"
        ).fetchone()
        c.close()
        if row:
            return float(row[0])
    except Exception:
        pass
    return DEFAULT_TAX_RATE

def _conn():
    c = sqlite3.connect(str(DB_PATH), timeout=5)
    c.row_factory = sqlite3.Row
    return c

def ensure_tax_schema() -> None:
    """Create tax tables if they don't exist. Safe to call multiple times."""
    try:
        with _conn() as c:
            c.execute("""
                CREATE TABLE IF NOT EXISTS tax_reserve (
                    id              INTEGER PRIMARY KEY AUTOINCREMENT,
                    position_id     INTEGER,
                    token_name      TEXT DEFAULT '',
                    pnl_usd         REAL,
                    tax_allocated   REAL,
                    tax_rate_used   REAL,
                    financial_year  TEXT,
                    created_at      REAL
                )
            """)
            c.execute("""
                CREATE TABLE IF NOT EXISTS tax_state (
                    id                  INTEGER PRIMARY KEY,
                    total_reserved      REAL DEFAULT 0,
                    total_gross_profit  REAL DEFAULT 0,
                    trade_count         INTEGER DEFAULT 0,
                    last_updated        REAL DEFAULT 0
                )
            """)
            c.execute("""
                INSERT OR IGNORE INTO tax_state
                (id, total_reserved, total_gross_profit, trade_count, last_updated)
                VALUES (1, 0, 0, 0, 0)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_tax_reserve_pos
                ON tax_reserve(position_id)
            """)
            c.execute("""
                CREATE INDEX IF NOT EXISTS idx_tax_reserve_fy
                ON tax_reserve(financial_year)
            """)
            c.commit()
    except Exception as e:
        pass  # non-fatal — schema may already exist

def _financial_year(ts: float) -> str:
    """Return AU financial year string e.g. 'FY2025-26' for dates Jul25-Jun26."""
    import datetime
    dt = datetime.datetime.fromtimestamp(ts)
    if dt.month >= 7:
        return f"FY{dt.year}-{str(dt.year+1)[2:]}"
    else:
        return f"FY{dt.year-1}-{str(dt.year)[2:]}"

def allocate_tax(position_id: int, pnl_usd: float,
                 token_name: str = "") -> float:
    """
    Allocate tax on a profitable trade.
    Returns the tax amount allocated (0 if pnl <= 0).

    Called from close_position_canonical() — must be fast and non-blocking.
    Any failure is silent — never interrupts trade close.
    """
    if pnl_usd <= 0:
        return 0.0

    try:
        rate = _get_rate()
        tax  = round(pnl_usd * rate, 6)
        now  = time.time()
        fy   = _financial_year(now)

        with _conn() as c:
            c.execute("""
                INSERT INTO tax_reserve
                (position_id, token_name, pnl_usd, tax_allocated,
                 tax_rate_used, financial_year, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (position_id, token_name, pnl_usd, tax, rate, fy, now))

            c.execute("""
                UPDATE tax_state
                SET total_reserved      = total_reserved + ?,
                    total_gross_profit  = total_gross_profit + ?,
                    trade_count         = trade_count + 1,
                    last_updated        = ?
                WHERE id = 1
            """, (tax, pnl_usd, now))
            c.commit()

        return tax

    except Exception:
        return 0.0  # never interrupt trade close

def get_tax_state() -> dict:
    """Return current tax state for UI display."""
    try:
        with _conn() as c:
            row = c.execute(
                "SELECT * FROM tax_state WHERE id=1"
            ).fetchone()
            if row:
                return {
                    "total_reserved":     round(float(row["total_reserved"] or 0), 2),
                    "total_gross_profit": round(float(row["total_gross_profit"] or 0), 2),
                    "trade_count":        int(row["trade_count"] or 0),
                    "last_updated":       float(row["last_updated"] or 0),
                    "rate":               _get_rate(),
                }
    except Exception:
        pass
    return {"total_reserved": 0.0, "total_gross_profit": 0.0,
            "trade_count": 0, "last_updated": 0, "rate": DEFAULT_TAX_RATE}

def get_effective_capital(wallet_balance: float) -> float:
    """
    Return tradeable capital after removing tax reserve.
    Use this for position sizing — prevents re-trading tax money.
    """
    state = get_tax_state()
    reserved = state["total_reserved"]
    return max(0.0, wallet_balance - reserved)

def generate_tax_report(output_path: str = "tax_report.csv") -> str:
    """
    Generate accountant-ready CSV of all taxable trade events.
    Groups by financial year. Run manually — not called during trading.
    """
    try:
        import csv, datetime
        rows = []
        with _conn() as c:
            records = c.execute("""
                SELECT
                    tr.id,
                    tr.position_id,
                    tr.token_name,
                    tr.pnl_usd,
                    tr.tax_allocated,
                    tr.tax_rate_used,
                    tr.financial_year,
                    tr.created_at,
                    pp.opened_at,
                    pp.closed_at,
                    pp.entry_price,
                    pp.exit_price,
                    pp.exit_reason
                FROM tax_reserve tr
                LEFT JOIN paper_positions pp ON pp.id = tr.position_id
                ORDER BY tr.created_at ASC
            """).fetchall()

        with open(output_path, 'w', newline='') as f:
            writer = csv.writer(f)
            writer.writerow([
                "tax_id", "position_id", "token", "financial_year",
                "trade_date", "pnl_usd", "tax_allocated", "tax_rate",
                "opened_at", "closed_at", "entry_price", "exit_price",
                "exit_reason"
            ])
            for r in records:
                dt = datetime.datetime.fromtimestamp(
                    r["created_at"]
                ).strftime("%Y-%m-%d %H:%M:%S")
                writer.writerow([
                    r["id"], r["position_id"], r["token_name"] or "",
                    r["financial_year"], dt,
                    f"{r['pnl_usd']:.4f}", f"{r['tax_allocated']:.4f}",
                    f"{r['tax_rate_used']:.2f}",
                    r["opened_at"] or "", r["closed_at"] or "",
                    r["entry_price"] or "", r["exit_price"] or "",
                    r["exit_reason"] or ""
                ])

        total_tax = sum(float(r["tax_allocated"] or 0) for r in records)
        total_pnl = sum(float(r["pnl_usd"] or 0) for r in records)
        return f"✓ {len(records)} trades | Gross profit: ${total_pnl:.2f} | Tax reserved: ${total_tax:.2f} → {output_path}"

    except Exception as e:
        return f"✗ Report failed: {e}"


# ── Schema init on import ─────────────────────────────────────────────────────
ensure_tax_schema()


if __name__ == "__main__":
    import sys
    if "--report" in sys.argv:
        print(generate_tax_report())
    elif "--state" in sys.argv:
        s = get_tax_state()
        print(f"Tax reserved:    ${s['total_reserved']:.2f}")
        print(f"Gross profit:    ${s['total_gross_profit']:.2f}")
        print(f"Trades counted:  {s['trade_count']}")
        print(f"Current rate:    {s['rate']*100:.0f}%")
        eff = get_effective_capital(float(sys.argv[sys.argv.index('--state')+1])
                                    if '--balance' in sys.argv else 1000.0)
        print(f"Effective capital (if $1000 wallet): ${eff:.2f}")
    else:
        print("Usage: python tax_allocator.py --state | --report")
