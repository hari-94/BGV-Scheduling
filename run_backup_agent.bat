@echo off
rem The backup PC: answers HotSOS Preview/Push only while the office PC is offline.
cd /d "%~dp0"
if not exist "%USERPROFILE%\.bgv-agent" mkdir "%USERPROFILE%\.bgv-agent"
python hotsos_agent.py backup >> "%USERPROFILE%\.bgv-agent\agent.log" 2>&1
