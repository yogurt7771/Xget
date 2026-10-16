@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0xget-ip.ps1"
set "xget_exit=%errorlevel%"
if not "%xget_exit%"=="0" pause
exit /b %xget_exit%
