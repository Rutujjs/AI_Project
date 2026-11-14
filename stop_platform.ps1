# ==============================================================================
# AI-Powered Enterprise ESG Sustainability Platform - Stop Script (PowerShell)
# Gracefully stops ONLY the processes launched and owned by start_platform.ps1.
# Does NOT terminate unrelated external processes.
# ==============================================================================

[CmdletBinding()]
param(
    [switch]$ForceUnmanaged = $false
)

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ScriptDir ".platform_pids.json"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "   AI-POWERED ENTERPRISE ESG SUSTAINABILITY PLATFORM" -ForegroundColor Cyan
Write-Host "   Safe Process Shutdown Manager" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

$stoppedAny = $false

if (Test-Path $PidFile) {
    Write-Host "Reading launcher process ownership tracking file (.platform_pids.json)..." -ForegroundColor Yellow
    try {
        $pidsData = Get-Content $PidFile -Raw | ConvertFrom-Json
        $pidsToStop = @()

        if ($pidsData.all_owned_pids) {
            foreach ($p in $pidsData.all_owned_pids) {
                if ($p -and [int]$p -gt 0) { $pidsToStop += [int]$p }
            }
        }
        if ($pidsData.policy_pid)          { $pidsToStop += [int]$pidsData.policy_pid }
        if ($pidsData.policy_server_pid)   { $pidsToStop += [int]$pidsData.policy_server_pid }
        if ($pidsData.platform_pid)        { $pidsToStop += [int]$pidsData.platform_pid }
        if ($pidsData.platform_server_pid) { $pidsToStop += [int]$pidsData.platform_server_pid }
        if ($pidsData.frontend_pid)        { $pidsToStop += [int]$pidsData.frontend_pid }
        if ($pidsData.frontend_server_pid) { $pidsToStop += [int]$pidsData.frontend_server_pid }

        $uniquePids = $pidsToStop | Select-Object -Unique

        foreach ($pidToStop in $uniquePids) {
            # Find and stop child processes first
            Get-CimInstance Win32_Process -Filter "ParentProcessId = $pidToStop" -ErrorAction SilentlyContinue |
                ForEach-Object {
                    $childId = $_.ProcessId
                    $cp = Get-Process -Id $childId -ErrorAction SilentlyContinue
                    if ($cp) {
                        Write-Host "  -> Terminating child process [PID: $childId, Name: $($cp.ProcessName)] of PID $pidToStop..." -ForegroundColor White
                        Stop-Process -Id $childId -Force -ErrorAction SilentlyContinue
                        $stoppedAny = $true
                    }
                }

            $p = Get-Process -Id $pidToStop -ErrorAction SilentlyContinue
            if ($p) {
                Write-Host "  -> Terminating owned process [PID: $pidToStop, Name: $($p.ProcessName)]..." -ForegroundColor White
                Stop-Process -Id $pidToStop -Force -ErrorAction SilentlyContinue
                $stoppedAny = $true
            } else {
                Write-Host "  -> Process [PID: $pidToStop] is already stopped." -ForegroundColor DarkGray
            }
        }
        Remove-Item $PidFile -Force -ErrorAction SilentlyContinue
        Write-Host "Ownership tracking file cleared." -ForegroundColor DarkGray
    } catch {
        Write-Warning "Could not parse .platform_pids.json: $_"
    }
} else {
    Write-Host "No active launcher session found (.platform_pids.json does not exist)." -ForegroundColor Yellow
}

# Scan target ports to inform user if any unmanaged processes remain
$TargetPorts = @(8000, 8001, 5500)
$unmanagedFound = @()

foreach ($port in $TargetPorts) {
    $conn = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        $procId = $conn.OwningProcess | Select-Object -Unique -First 1
        $procObj = Get-Process -Id $procId -ErrorAction SilentlyContinue
        $procName = if ($procObj) { $procObj.ProcessName } else { "Unknown" }
        $unmanagedFound += [PSCustomObject]@{ Port = $port; PID = $procId; Name = $procName }
    }
}

if ($unmanagedFound.Count -gt 0) {
    Write-Host ""
    Write-Host "NOTICE: The following port(s) are still occupied by external/unmanaged processes:" -ForegroundColor Yellow
    foreach ($item in $unmanagedFound) {
        Write-Host "  - Port $($item.Port): PID $($item.PID) ($($item.Name))" -ForegroundColor Gray
    }

    if ($ForceUnmanaged) {
        Write-Host "  -ForceUnmanaged was specified. Terminating unmanaged listeners..." -ForegroundColor Yellow
        foreach ($item in $unmanagedFound) {
            Stop-Process -Id $item.PID -Force -ErrorAction SilentlyContinue
            Write-Host "  Terminated PID $($item.PID) on port $($item.Port)." -ForegroundColor Gray
        }
    } else {
        Write-Host "For safety, these unmanaged processes were NOT terminated." -ForegroundColor Cyan
        Write-Host "To force termination of all processes on these ports, run: .\stop_platform.ps1 -ForceUnmanaged" -ForegroundColor DarkGray
    }
}

Write-Host ""
Write-Host "Shutdown manager completed." -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Cyan
