@echo off
REM ==============================================================================
REM AI-Powered Enterprise ESG Sustainability Platform - Windows Batch Launcher
REM ==============================================================================
title AI Enterprise ESG Platform Launcher
cd /d "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0start_platform.ps1" %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Platform failed to start. Review errors above.
    pause
) else (
    echo.
    echo ======================================================================
    echo Platform services are running in the background.
    echo Press any key to close this launcher window (services will remain running)...
    pause >nul
)

