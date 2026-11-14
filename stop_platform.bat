@echo off
REM ==============================================================================
REM AI-Powered Enterprise ESG Sustainability Platform - Windows Stop Script
REM ==============================================================================
title Stop AI Enterprise ESG Platform
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0stop_platform.ps1"
echo.
pause

