# 🧬 SENTINUITY — Sovereign Systems Network

**Built for Polar. Open for all.**

A self-healing AI execution architecture for studying algorithmic trading systems.
Multi-agent debate council. Deterministic execution loop. Real-time observability.

## ⚠️ PAPER MODE ONLY — Educational Simulation

**Public snapshot status — reviewed 25 October 2026**

This repository is an incomplete research snapshot last committed on 16 May
2026. It is not the current local Sentinuity runtime or a verified runnable
release. `core/schema.py`, `requirements.txt`, `.env.example`, and several
referenced services are absent.

The intended scope is paper simulation. However, the published engine contains
optional live-trading imports and conditional buy/sell paths. The presence of a
paper launcher or packaging script does not establish that this checkout is
technically locked to paper mode. Do not connect funded wallets or credentials.
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

These describe the intended architecture. The complete pipeline and its
behaviour cannot be reproduced from this snapshot alone.

---

## Running this snapshot

A supported quick start is not available: the dependency manifest, environment
template, schema module and referenced services must first be supplied and
reviewed as a complete paper-only release. No profitability or live-readiness
claim is made.

## October repair status

A separate local repair package dated 24 October addresses an entry-transaction
self-lock, adds exit timing measurements, and restores a shadow-tracker launch.
Those changes and their dependencies are **not included in this public snapshot**.
Installation checks were reported as passing on the local machine on 25 October;
post-repair runtime results and profitability remain unverified here. Installation
checks are not evidence of improved PnL.

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
- Intended for paper research; this snapshot is not verified as locked against real execution
- See `DISCLAIMER.md`

---

## ⚠️ Disclaimer

Trading involves substantial risk of loss. Past simulation performance
does not predict future real-money results. This software is provided
for educational and research purposes only.

*One network. Limitless possibilities.*
