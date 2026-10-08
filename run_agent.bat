@echo off
rem Started by Task Scheduler at logon: the HotSOS push + SSRS forecast agent.
cd /d "%~dp0"
if not exist "%USERPROFILE%\.bgv-agent" mkdir "%USERPROFILE%\.bgv-agent"
python hotsos_agent.py run >> "%USERPROFILE%\.bgv-agent\agent.log" 2>&1
