@echo off
rem Once per PC: sign in to Microsoft 365 in the agent's own Chrome profile, then
rem close the window. sharepoint.py reuses this sign-in to read the GC8 sheet.
start "" "C:\Program Files\Google\Chrome\Application\chrome.exe" --user-data-dir="%USERPROFILE%\.bgv-agent\pa-browser" https://grandtimber.sharepoint.com/sites/GC8HSKP
