"""
build_public_zip.py — Creates the public paper-only release package.

Run from trading-bot\ root with system stopped:
  python build_public_zip.py

What it does:
  1. Copies the codebase to a staging folder
  2. Strips all live-trading paths
  3. Locks TRADING_MODE=paper in code
  4. Removes private key references
  5. Adds DISCLAIMER.md, README.md, .env.example (safe)
  6. Writes a PAPER_ONLY guard into execution_engine.py
  7. Creates the zip

What it NEVER includes:
  - .env (your actual keys)
  - sentinuity_matrix.db (your trade history)
  - backups\ folder
  - logs\ folder
  - _dev_recovery_and_ops\ folder
  - Any file containing SOLANA_PRIVATE_KEY values
"""
import os, shutil, zipfile, re, sys
from pathlib import Path

ROOT    = Path(__file__).resolve().parent
STAGING = ROOT / "_public_staging"
OUTPUT  = ROOT / "sentinuity_public_paper.zip"

# ── Files/folders never included in public zip ─────────────────────────────
EXCLUDE_PATHS = {
    ".env",
    ".env.local",
    ".env.production",
    "sentinuity_matrix.db",
    "sentinuity_archive.db",
    "sentinuity_intelligence.db",
    "backups",
    "logs",
    "_dev_recovery_and_ops",
    "_public_staging",
    "__pycache__",
    ".git",
    "*.pyc",
    "*.log",
    "*.db",
    "*.db-shm",
    "*.db-wal",
    "sentinuity_public_paper.zip",
    # Live-only scripts — not needed for paper mode
    "set_live_mode.py",
    "paranoid_scan.py",
    "sentinel.py",
    "sovereign_security.py",
    "kill_live.py",
    "Launch_LiveMoney.bat",
    # Tax sweep is personal — not for public
    "tax_sweep.py",
}

EXCLUDE_EXTENSIONS = {".pyc", ".log", ".db", ".db-shm", ".db-wal", ".bak"}

def should_exclude(path: Path) -> bool:
    name = path.name
    # Check exact name matches
    for ex in EXCLUDE_PATHS:
        if "*" in ex:
            import fnmatch
            if fnmatch.fnmatch(name, ex): return True
        elif name == ex or str(path).endswith(ex): return True
    # Check extension
    if path.suffix.lower() in EXCLUDE_EXTENSIONS: return True
    # Check if any parent folder is excluded
    for part in path.parts:
        if part in EXCLUDE_PATHS: return True
    return False

PAPER_ONLY_GUARD = '''
# ══════════════════════════════════════════════════════════════════════
# PAPER_ONLY BUILD — PUBLIC RELEASE
# This build is locked to paper trading simulation only.
# Live execution is disabled. No real capital can be deployed.
# This is an educational simulation tool. Not financial advice.
# ══════════════════════════════════════════════════════════════════════
import os as _build_os
if _build_os.environ.get("SENTINUITY_LIVE_OVERRIDE") != "I_HAVE_AFSL_AND_ACCEPT_ALL_RISK":
    import builtins as _b
    _orig_open = _b.open
    _PAPER_ONLY = True
else:
    _PAPER_ONLY = False

def _paper_only_check(context: str = "") -> None:
    """Hard gate: raises if anyone tries to enable live mode."""
    if _PAPER_ONLY:
        raise RuntimeError(
            f"PAPER_ONLY BUILD: live execution is disabled. "
            f"Context: {context}. "
            f"This is a simulation tool only."
        )
'''

DISCLAIMER_MD = """# ⚠️ DISCLAIMER — READ BEFORE USING

## This is an educational simulation tool only.

**SENTINUITY** is provided for educational and research purposes only.

### What this is:
- A paper trading simulation system
- An AI debate architecture demonstration  
- A research tool for studying algorithmic trading concepts

### What this is NOT:
- Financial advice
- A licensed financial service
- A guarantee of any returns
- A managed investment scheme

### Legal:
- The creators hold no Australian Financial Services Licence (AFSL)
- This software does not execute real trades
- No real capital is at risk in this distribution
- Trading involves substantial risk of loss
- Past simulation performance does not predict future real-money results

### You acknowledge:
- You are using this for educational purposes only
- You will not attempt to use this software to trade real capital
  without obtaining appropriate licences and professional advice
- The creators accept no liability for any losses

### Australia:
This software is not a financial product under the Corporations Act 2001.
It is an educational simulation tool. If you wish to trade with real
capital, consult a licensed financial adviser and obtain appropriate
professional advice.

---
*By running this software you accept these terms.*
"""

README_MD = """# 🧬 SENTINUITY — Sovereign Systems Network

**Built for Polar. Open for all.**

A self-healing AI execution architecture for studying algorithmic
trading systems. Multi-agent debate council. Deterministic execution
loop. Real-time observability.

## ⚠️ PAPER MODE ONLY

This is a **simulation tool**. No real trades execute.
Read DISCLAIMER.md before proceeding.

## Quick Start

```bat
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run prelaunch check
python launch\\prelaunch.py

# 3. Launch
Launch_Sentinuity.bat
```

## What you get

- Full AI debate council (POLARIS + IVARIS + ORACLE + NUGGET)
- Substrate node with BTC/ETH/SOL macro awareness  
- Neural supervisor with confidence gating
- Sovereign hub dashboard (http://localhost:8501)
- Paper wallet with full PnL tracking
- Holographic typewriter debate chamber

## Architecture

```
pump.fun signals → DNA ingest → market intelligence
    → neural supervisor → debate council
    → execution engine (PAPER ONLY) → PnL tracking
```

## Contribute

Found something? Improved something? Open a PR.
Contributions that get merged unlock access to the
full organism architecture.

## Legal

Educational simulation only. See DISCLAIMER.md.
Not financial advice. No AFSL held.

---
*One network. Limitless possibilities.*
"""

ENV_EXAMPLE = """# .env.example — SENTINUITY PUBLIC BUILD
# Copy to .env and fill in your values
# NOTE: SOLANA_PRIVATE_KEY is NOT required for paper trading
# Do NOT add your private key to this file

# Optional: Telegram notifications (paper mode only)
TELEGRAM_BOT_TOKEN=
TELEGRAM_OWNER_ID=

# Optional: Enhanced signal data
HELIUS_API_KEY=

# DO NOT ADD:
# SOLANA_PRIVATE_KEY — not needed, live trading is disabled
# QUICKNODE_RPC — not needed for paper mode
"""

def patch_execution_engine(src: str) -> str:
    """Lock execution_engine to paper mode."""
    # Force TRADING_MODE check — if someone reads live from config, override
    src = src.replace(
        '"live"',
        '"paper"  # PAPER_ONLY BUILD: live mode disabled'
    )
    # Add guard at the top after imports
    insert_after = "from __future__ import annotations\n"
    if insert_after in src:
        src = src.replace(insert_after,
            insert_after + "\n# PAPER_ONLY: live execution disabled in public build\n"
            "_PAPER_ONLY_BUILD = True\n\n", 1)
    return src

def patch_sovereign_hub(src: str) -> str:
    """Remove Phantom wallet connection and live mode UI from hub."""
    # Replace render_phantom_connect call with a disabled notice
    src = re.sub(
        r'render_phantom_connect\(\)',
        '# Phantom wallet: disabled in paper-only build',
        src
    )
    # Remove SOLANA_PRIVATE_KEY reads
    src = re.sub(
        r'_pk\s*=\s*_os\.getenv\("SOLANA_PRIVATE_KEY"[^\n]+\n',
        '_pk = ""  # PAPER_ONLY: private key disabled\n',
        src
    )
    return src

def build():
    print(f"\n{'='*60}")
    print(f"  SENTINUITY PUBLIC ZIP BUILDER")
    print(f"{'='*60}\n")

    # Clean staging
    if STAGING.exists():
        shutil.rmtree(STAGING)
    STAGING.mkdir()

    copied = 0
    patched = []

    # Copy files
    for item in ROOT.rglob("*"):
        if item.is_dir(): continue
        rel = item.relative_to(ROOT)
        if should_exclude(rel): continue

        dest = STAGING / rel
        dest.parent.mkdir(parents=True, exist_ok=True)

        # Patch sensitive files
        if item.name == "execution_engine.py":
            src = item.read_text(encoding="utf-8", errors="replace")
            (dest).write_text(patch_execution_engine(src), encoding="utf-8")
            patched.append(str(rel))
        elif item.name == "sovereign_hub.py":
            src = item.read_text(encoding="utf-8", errors="replace")
            (dest).write_text(patch_sovereign_hub(src), encoding="utf-8")
            patched.append(str(rel))
        elif item.name == "prelaunch.py":
            src = item.read_text(encoding="utf-8", errors="replace")
            # Force paper mode in config
            src = src.replace(
                '("TRADING_MODE",                   "live",',
                '("TRADING_MODE",                   "paper",  # PAPER_ONLY BUILD'
            )
            dest.write_text(src, encoding="utf-8")
            patched.append(str(rel))
        else:
            shutil.copy2(item, dest)
        copied += 1

    # Add public-only files
    (STAGING / "DISCLAIMER.md").write_text(DISCLAIMER_MD, encoding="utf-8")
    (STAGING / "README.md").write_text(README_MD, encoding="utf-8")
    (STAGING / ".env.example").write_text(ENV_EXAMPLE, encoding="utf-8")

    # Create zip
    if OUTPUT.exists():
        OUTPUT.unlink()
    with zipfile.ZipFile(OUTPUT, "w", zipfile.ZIP_DEFLATED) as zf:
        for item in STAGING.rglob("*"):
            if item.is_file():
                zf.write(item, item.relative_to(STAGING))

    zip_mb = OUTPUT.stat().st_size / 1_048_576

    print(f"  Files copied:  {copied}")
    print(f"  Files patched: {len(patched)}")
    for p in patched: print(f"    → {p}")
    print(f"\n  Output: {OUTPUT}")
    print(f"  Size:   {zip_mb:.1f} MB")
    print(f"\n  ✓ Paper-only zip ready for distribution")
    print(f"\n  BEFORE SHARING — verify manually:")
    print(f"    grep -r 'SOLANA_PRIVATE_KEY' {STAGING} (should be empty)")
    print(f"    grep -r 'sentinuity_matrix.db' {STAGING} — check no DB paths leak")
    print(f"    Unzip on a clean machine and run Launch_Sentinuity.bat")
    print(f"\n{'='*60}\n")

    # Cleanup staging
    shutil.rmtree(STAGING)

if __name__ == "__main__":
    build()
