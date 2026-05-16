@echo off
setlocal EnableExtensions EnableDelayedExpansion

title SENTINUITY SOVEREIGN TERMINAL

set "ROOT_PATH=C:\Users\Polar\.openclaw\workspace\trading-bot"
set "LOG_PATH=%ROOT_PATH%\logs"

cd /d "%ROOT_PATH%"
set "PYTHONPATH=%ROOT_PATH%"

rem ============================================================
rem  PRODUCTION MODE — 3 VISIBLE WINDOWS ONLY:
rem    1. Gateway                      (openclaw)
rem    2. SENTINUITY SOVEREIGN CONSOLE (brain feed)
rem    3. SENTINUITY GUARDIAN          (watchdog)
rem
rem  All services run silently in background, logging to:
rem    %LOG_PATH%\<service>.log
rem
rem  To debug a service: type "%LOG_PATH%\ingest_pipeline.log"
rem ============================================================

echo ============================================================
echo PHASE 0: ENVIRONMENT + GHOST KILL
echo ============================================================

taskkill /F /IM python.exe      /T >nul 2>&1
taskkill /F /IM pythonw.exe     /T >nul 2>&1
taskkill /F /IM openclaw.exe    /T >nul 2>&1
taskkill /F /IM cloudflared.exe /T >nul 2>&1
taskkill /F /IM streamlit.exe   /T >nul 2>&1

for %%T in (
  "SENTINUITY GUARDIAN" "SENTINUITY WATCHDOG" "WATCHDOG"
  "SENTINUITY SOVEREIGN CONSOLE" "Gateway"
  "Scout" "Ingest" "Resolver" "Weaver" "Oracle" "Qualifier"
  "Supervisor" "Executor" "ZombieRes"
  "Polaris" "Researcher" "Reviewer" "Calibrator" "Messenger"
  "Reflect" "SPE" "TG Scout" "CH Analyst" "HITL Bot"
  "Debate" "Health" "DB Prune" "Healer" "Vault" "Ivy Forge"
  "Tunnel" "Dashboard" "Replay" "WalletScout" "Substrate"
  "IngestPipeline" "MarketIntel" "ExecEngine"
  "SovGovernor" "SysGuardian" "SovHub" "PolarisAux" "Recon"
  "TelegramScout" "WalletScoutSvc" "SymbioticRouter" "WsOracle"
) do taskkill /F /FI "WINDOWTITLE eq %%~T" /T >nul 2>&1

if not exist "%LOG_PATH%" mkdir "%LOG_PATH%"
if not exist "%ROOT_PATH%\ui" mkdir "%ROOT_PATH%\ui"

timeout /t 2 /nobreak >nul

echo ============================================================
echo PHASE 0b: DB SLIM  [DISABLED — Phase A stabilization]
echo   slim_db.py is manual-only. Run from tools\maintenance\
echo   after clean shutdown with explicit backup first.
echo ============================================================
rem PHASE A: slim_db.py disabled — wipes raw_dna and market_snapshots
rem which destroys fresh HOT/WARM ingestion state and causes split-brain.
rem To slim manually: python _dev_recovery_and_ops\tools\maintenance\slim_db.py (stopped system only)
rem python slim_db.py >> "%LOG_PATH%\slim_db.log" 2>&1
echo [OK] DB slim skipped (Phase A stabilization mode).

echo ============================================================
echo PHASE 1: GATEWAY
echo ============================================================
start "Gateway" cmd /k "cd /d %ROOT_PATH% && openclaw gateway"
timeout /t 4 /nobreak >nul

echo ============================================================
echo PHASE 1.5: PRE-LAUNCH + PREFLIGHT
echo ============================================================

python launch\prelaunch.py
if errorlevel 1 (
    echo.
    echo [ABORT] PRELAUNCH FAILED — system did not reach known-good state.
    echo         Check output above. Fix the issue before launching.
    echo         If this is a non-critical warning, edit prelaunch.py to downgrade.
    pause
    exit /b 1
)

python _dev_recovery_and_ops\ops\unjam_now.py >> "%LOG_PATH%\unjam_now.log" 2>&1
echo [OK] Unjam complete.

python _dev_recovery_and_ops\ops\fix_all.py >> "%LOG_PATH%\fix_all.log" 2>&1
echo [OK] Pipeline fix complete.

python services\preflight_verifier.py
if errorlevel 1 (
    echo [WARN] Preflight failed - continuing boot (non-fatal)
)

echo Pre-check phase complete.

echo ============================================================
echo PHASE 2: SCHEMA + PIPELINE RESET
echo [PAPER MODE] Preserving wallet balance, setting paper trading mode...
python wal_checkpoint.py
python -c "import sqlite3,time; db=sqlite3.connect('sentinuity_matrix.db'); db.row_factory=sqlite3.Row; row=db.execute('SELECT wallet_balance,initial_capital FROM system_state WHERE id=1').fetchone(); cur=float(row['wallet_balance'] if row else 0); init=float(row['initial_capital'] if row else 0); baseline=cur if cur>1.0 else 100.0; stuck=db.execute(\"SELECT id,position_size_usd FROM paper_positions WHERE status='OPEN'\").fetchall(); reverted=sum(float(p['position_size_usd'] or 0) for p in stuck); [db.execute(\"UPDATE paper_positions SET status='CLOSED',exit_category='RESTART_REVERT',win_loss='SCRATCH',realized_pnl_usd=0,final_exec_pct=0,unrealized_pnl_usd=0,closed_at=? WHERE id=?\", (time.time(),p['id'])) for p in stuck]; final=baseline+reverted; db.execute('UPDATE system_state SET wallet_balance=?,initial_capital=? WHERE id=1',(final,init if init>1.0 else 100.0)); db.execute(\"INSERT OR REPLACE INTO system_config(key,value,description) VALUES(?,?,?)\",('TRADING_MODE','paper','paper launch')); db.execute(\"INSERT OR REPLACE INTO system_config(key,value,description) VALUES(?,?,?)\",('PAPER_WALLET_TRACKS_LIVE','0','paper launch')); db.execute(\"INSERT OR REPLACE INTO system_config(key,value,description) VALUES(?,?,?)\",('PAPER_WALLET_BASELINE_USD',str(final),'paper launch')); db.execute(\"INSERT OR REPLACE INTO system_config(key,value,description) VALUES(?,?,?)\",('POSITION_SIZE_USD','25.0','position size')); db.commit(); db.close(); print(f'[OK] Paper mode — wallet preserved at ${final:.2f} (was ${cur:.2f}, reverted {len(stuck)} stuck positions)')"
echo [CLEANUP] Clearing stale positions from previous session...
python clear_stale_on_launch.py
echo ============================================================

python -c "import sys;sys.path.insert(0,chr(46));from core.schema import startup_cleanup,init_db;init_db();startup_cleanup()" >> "%LOG_PATH%\startup_cleanup.log" 2>&1

echo Schema + pipeline ready.

echo ============================================================
echo PHASE 3: CORE PIPELINE  [silent - logs to files]
echo ============================================================

start "IngestPipeline" /b cmd /c "cd /d %ROOT_PATH% && python -m services.ingest_pipeline >> %LOG_PATH%\ingest_pipeline.log 2>&1"
timeout /t 5 /nobreak >nul

start "Scout" /b cmd /c "cd /d %ROOT_PATH% && python -m services.pump_monitor >> %LOG_PATH%\pump_monitor.log 2>&1"
timeout /t 5 /nobreak >nul

start "MarketIntel" /b cmd /c "cd /d %ROOT_PATH% && python -m services.market_intelligence >> %LOG_PATH%\market_intelligence.log 2>&1"
timeout /t 5 /nobreak >nul

start "Supervisor" /b cmd /c "cd /d %ROOT_PATH% && python -m services.neural_supervisor >> %LOG_PATH%\neural_supervisor.log 2>&1"
timeout /t 5 /nobreak >nul

start "ExecEngine" /b cmd /c "cd /d %ROOT_PATH% && python -m services.execution_engine >> %LOG_PATH%\execution_engine.log 2>&1"
timeout /t 3 /nobreak >nul

start "WsOracle" /b cmd /c "cd /d %ROOT_PATH% && python -m services.ws_price_oracle >> %LOG_PATH%\ws_price_oracle.log 2>&1"
timeout /t 5 /nobreak >nul

start "SysGuardian" /b cmd /c "cd /d %ROOT_PATH% && python -m services.system_guardian >> %LOG_PATH%\system_guardian.log 2>&1"
start "RollingEviction" /b cmd /c "cd /d %ROOT_PATH% && python -m services.rolling_eviction >> %LOG_PATH%\rolling_eviction.log 2>&1"
start "TideMonitor" /b cmd /c "cd /d %ROOT_PATH% && python -m services.pump_activity_monitor >> %LOG_PATH%\pump_activity_monitor.log 2>&1"
start "FreshnessEnforcer" /b cmd /c "cd /d %ROOT_PATH% && python -m services.freshness_enforcer >> %LOG_PATH%\freshness_enforcer.log 2>&1"
start "PeriodicRefresh" /b cmd /c "cd /d %ROOT_PATH% && python -m services.periodic_refresh >> %LOG_PATH%\periodic_refresh.log 2>&1"
start "MacroPriceFeed" /b cmd /c "cd /d %ROOT_PATH% && python -m services.macro_price_feed >> %LOG_PATH%\macro_price_feed.log 2>&1"
start "MacroChannel"   /b cmd /c "cd /d %ROOT_PATH% && python -m services.macro_channel   >> %LOG_PATH%\macro_channel.log   2>&1"
start "GithubScout"    /b cmd /c "cd /d %ROOT_PATH% && python -m services.github_scout >> %LOG_PATH%\github_scout.log 2>&1"

echo ============================================================
echo PHASE 4: GOVERNANCE LAYER  [silent - logs to files]
echo ============================================================

start "SovGovernor" /b cmd /c "cd /d %ROOT_PATH% && python -m services.sovereign_governor >> %LOG_PATH%\sovereign_governor.log 2>&1"
timeout /t 5 /nobreak >nul

start "Polaris" /b cmd /c "cd /d %ROOT_PATH% && python -m services.polaris >> %LOG_PATH%\polaris.log 2>&1"
timeout /t 5 /nobreak >nul

start "SPE" /b cmd /c "cd /d %ROOT_PATH% && python -m services.sovereign_parameter_engine >> %LOG_PATH%\spe.log 2>&1"
timeout /t 5 /nobreak >nul

start "Replay" /b cmd /c "cd /d %ROOT_PATH% && python -m services.replay_engine >> %LOG_PATH%\replay_engine.log 2>&1"
timeout /t 3 /nobreak >nul

rem Sovereign Forge — starts in governance phase alongside POLARIS/governor.
rem Run forge_genesis_seed.py once manually before first launch to seed projects.
tasklist /FI "IMAGENAME eq python.exe" 2>nul | find /I "intelligence_orchestrator" >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo [FORGE] intelligence_orchestrator already running -- skipping duplicate launch.
) else (
    start "ForgeOrchestrator" /b cmd /c "cd /d %ROOT_PATH% && python -m services.intelligence_orchestrator >> %LOG_PATH%\intelligence_orchestrator.log 2>&1"
    echo [FORGE] ForgeOrchestrator started.
start "ForgeWriter" /b cmd /c "cd /d %ROOT_PATH% && python -m services.forge_code_writer >> %LOG_PATH%\forge_code_writer.log 2>&1"
)

echo ============================================================
echo PHASE 5: AUXILIARY LANES  [silent - logs to files]
echo ============================================================

start "PolarisAux" /b cmd /c "cd /d %ROOT_PATH% && python -m services.polaris_auxiliary >> %LOG_PATH%\polaris_auxiliary.log 2>&1"
start "Recon"      /b cmd /c "cd /d %ROOT_PATH% && python -m services.reconnaissance_engine >> %LOG_PATH%\recon.log 2>&1"

echo ============================================================
echo PHASE 5b: SCOUTS  [silent - logs to files]
echo ============================================================

start "WalletScoutSvc" /b cmd /c "cd /d %ROOT_PATH% && python -m services.wallet_scout >> %LOG_PATH%\wallet_scout.log 2>&1"
timeout /t 3 /nobreak >nul

start "TelegramScout" /b cmd /c "cd /d %ROOT_PATH% && python -m services.telegram_scout >> %LOG_PATH%\telegram_scout.log 2>&1"
timeout /t 3 /nobreak >nul

start "XScout" /b cmd /c "cd /d %ROOT_PATH% && python -m services.x_scout >> %LOG_PATH%\x_scout.log 2>&1"
timeout /t 2 /nobreak >nul

start "SymbioticRouter" /b cmd /c "cd /d %ROOT_PATH% && python -m services.symbiotic_router >> %LOG_PATH%\symbiotic_router.log 2>&1"

echo ============================================================
echo PHASE 6: UTILITIES  [silent - logs to files]
echo ============================================================

start "Vault" /b cmd /c "cd /d %ROOT_PATH% && python -m services.code_vault service >> %LOG_PATH%\code_vault.log 2>&1"

echo ============================================================
echo PHASE 7: TUNNEL + DASHBOARD  [silent - logs to files]
echo ============================================================

start "Tunnel" /b cmd /c "cd /d %ROOT_PATH% && C:\cloudflared\cloudflared.exe tunnel run sentinuity-tunnel >> %LOG_PATH%\tunnel.log 2>&1"
start "SovHub" /b cmd /c "cd /d %ROOT_PATH% && streamlit run services\sovereign_hub.py --server.headless true --server.port 8501 >> %LOG_PATH%\sovereign_hub.log 2>&1"

echo.
echo Allowing services to stabilise (25s)...
timeout /t 25 /nobreak >nul

echo ============================================================
echo PHASE 8: CONSOLE + GUARDIAN  [2 visible windows]
echo ============================================================

start "SENTINUITY SOVEREIGN CONSOLE" cmd /k "cd /d %ROOT_PATH% && python -m services.master_console"
start "SENTINUITY GUARDIAN"          cmd /k "cd /d %ROOT_PATH% && call launch\Watchdog_Sentinuity.bat"

echo.
echo Waiting 15s for services to register heartbeats...
timeout /t 15 /nobreak >nul

echo ============================================================
echo PHASE 9: HEARTBEAT VERIFICATION
echo ============================================================

python _dev_recovery_and_ops\tools\check_heartbeats.py

echo ============================================================
echo LAUNCH COMPLETE
echo ============================================================
echo.
echo  PRODUCTION MODE — 3 visible windows only:
echo    1. Gateway                      (this terminal closes after boot)
echo    2. SENTINUITY SOVEREIGN CONSOLE (brain feed)
echo    3. SENTINUITY GUARDIAN          (watchdog)
echo.
echo  Dashboard: http://localhost:8501
echo.
echo  All services running silently. Check logs at:
echo    %LOG_PATH%\
echo.
echo  Quick log checks:
echo    type "%LOG_PATH%\execution_engine.log"
echo    type "%LOG_PATH%\neural_supervisor.log"
echo    type "%LOG_PATH%\market_intelligence.log"
echo    type "%LOG_PATH%\ingest_pipeline.log"
echo    type "%LOG_PATH%\intelligence_orchestrator.log"
echo.
echo  Forge seed (run once before first launch):
echo    python forge_genesis_seed.py
echo.
echo  If trading halts run:  python _dev_recovery_and_ops\ops\unjam_now.py
echo  Full restart:          Shutdown_Sentinuity.bat then Launch_Sentinuity.bat
echo ============================================================

pause
