@echo off
title LeadGen AI - Stop Backend
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop-server.ps1"
echo.
pause
