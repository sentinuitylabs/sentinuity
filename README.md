# 🧬 SENTINUITY — Sovereign Systems Network

**Built for Polar. Open for all.**

A self-healing AI execution architecture for studying algorithmic trading systems.
Multi-agent debate council. Deterministic execution loop. Real-time observability.

## ⚠️ PAPER MODE ONLY — Educational Simulation

This repository contains the **paper trading simulation layer only**.
No real trades execute. No real capital is at risk.
Read `DISCLAIMER.md` before proceeding.

**Not financial advice. No AFSL held.**

---

## What is this?

Sentinuity is a research instrument — an autonomous AI organism that:

- Monitors pump.fun token launches in real time
- Routes signals through a multi-AI debate council (POLARIS + IVARIS + ORACLE + NUGGET)
- Requires internal consensus before any simulated trade executes
- Learns from every closed position via Polaris doctrine updates
- Self-heals when services fail via the system guardian

The public release is locked to paper trading. The organism debates, signals, and
tracks simulated PnL — but never touches real capital.

---

## Quick Start

```bat
:: 1. Install dependencies
pip install -r requirements.txt

:: 2. Copy environment template
copy .env.example .env

:: 3. Run prelaunch check
python launch\prelaunch.py

:: 4. Launch
Launch_Sentinuity.bat
```

Dashboard available at: `http://localhost:8501`

---

## Architecture

```
pump.fun signals
      ↓
DNA ingest pipeline
      ↓
Market intelligence + qualification
      ↓
Neural supervisor (confidence gating)
      ↓
AI debate council (POLARIS vs IVARIS)
      ↓
Execution engine (PAPER ONLY)
      ↓
PnL tracking + Polaris learning
```

---

## Key Components

| File | Purpose |
|------|---------|
| `services/execution_engine.py` | V3 exit logic — hard stop, runner mode, stagnation exit |
| `services/sovereign_hub.py` | Streamlit dashboard — real-time organism state |
| `services/tax_allocator.py` | Auto tax reserve on profitable closes (AU) |
| `launch/prelaunch.py` | Boot gate — schema, config, unjam |
| `Launch_Sentinuity.bat` | One-click launch |

---

## Contribute

Found something? Improved something? Open a PR.
The organism improves through collective intelligence.

---

## Legal

- Educational simulation only
- Not financial advice
- No AFSL held
- Paper trading only — no real execution
- See `DISCLAIMER.md`

---

## ⚠️ Disclaimer

Trading involves substantial risk of loss. Past simulation performance
does not predict future real-money results. This software is provided
for educational and research purposes only.

*One network. Limitless possibilities.*
