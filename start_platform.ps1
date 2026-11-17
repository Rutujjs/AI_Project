# ==============================================================================
# AI-Powered Enterprise ESG Sustainability Platform - Startup Script (PowerShell)
# Orchestrates:
#   1. Policy Intelligence Backend (Member 2)         -> http://localhost:8000
#   2. Core Platform & Intelligence (Members 1,3,4,5) -> http://localhost:8001
#   3. Integrated Unified Frontend                    -> http://localhost:5500
# ==============================================================================

[CmdletBinding()]
param()

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PidFile = Join-Path $ScriptDir ".platform_pids.json"

Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host "   AI-POWERED ENTERPRISE ESG SUSTAINABILITY PLATFORM" -ForegroundColor Cyan
Write-Host "   Automated Multi-Service Orchestrator" -ForegroundColor Cyan
Write-Host "======================================================================" -ForegroundColor Cyan
Write-Host ""

# ------------------------------------------------------------------------------
# 1. Process Ownership & Port Conflict Verification
# ------------------------------------------------------------------------------
$TargetPorts = @(8000, 8001, 5500)

function Check-Port([int]$Port) {
    # 1. Primary check via Get-NetTCPConnection (CIM)
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($conn) {
        return $conn
    }

    # 2. Resilient fallback via direct TCP socket handshake
    try {
        $tcp = New-Object System.Net.Sockets.TcpClient
        $iar = $tcp.BeginConnect("127.0.0.1", $Port, $null, $null)
        if ($iar.AsyncWaitHandle.WaitOne(400, $false)) {
            $tcp.EndConnect($iar)
            $tcp.Close()
            return [PSCustomObject]@{
                LocalPort     = $Port
                State         = "Listen"
                OwningProcess = $null
            }
        }
        $tcp.Close()
    } catch {}

    return $null
}

function Get-ListeningProcessId([int]$Port, [int]$WrapperPid) {
    # 1. Primary: Get-NetTCPConnection OwningProcess
    $conn = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue
    if ($conn -and $conn.OwningProcess) {
        $pidVal = $conn.OwningProcess | Select-Object -Unique -First 1
        if ($pidVal -and [int]$pidVal -gt 0) { return [int]$pidVal }
    }
    # 2. Check child processes of the launcher wrapper
    if ($WrapperPid) {
        $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $WrapperPid" -ErrorAction SilentlyContinue
        if ($children) {
            $first = $children | Select-Object -First 1
            if ($first -and $first.ProcessId) { return [int]$first.ProcessId }
        }
    }
    # 3. Fallback: netstat lookup
    try {
        $lines = netstat -ano | Select-String ":$Port\s+.*LISTENING\s+(\d+)"
        if ($lines) {
            $match = [regex]::Match($lines[0], ":$Port\s+.*LISTENING\s+(\d+)")
            if ($match.Success) {
                return [int]$match.Groups[1].Value
            }
        }
    } catch {}
    return $null
}

# Load previously recorded launcher PIDs if available
$knownLauncherPids = @()
if (Test-Path $PidFile) {
    try {
        $saved = Get-Content $PidFile -Raw | ConvertFrom-Json
        if ($saved.all_owned_pids) {
            foreach ($p in $saved.all_owned_pids) { if ($p) { $knownLauncherPids += [int]$p } }
        }
        if ($saved.policy_pid)          { $knownLauncherPids += [int]$saved.policy_pid }
        if ($saved.platform_pid)        { $knownLauncherPids += [int]$saved.platform_pid }
        if ($saved.frontend_pid)        { $knownLauncherPids += [int]$saved.frontend_pid }
        if ($saved.policy_server_pid)   { $knownLauncherPids += [int]$saved.policy_server_pid }
        if ($saved.platform_server_pid) { $knownLauncherPids += [int]$saved.platform_server_pid }
        if ($saved.frontend_server_pid) { $knownLauncherPids += [int]$saved.frontend_server_pid }
        $knownLauncherPids = $knownLauncherPids | Select-Object -Unique
    } catch {}
}

Write-Host "[1/5] Checking for port conflicts on 8000, 8001, 5500..." -ForegroundColor Yellow

$conflictsFound = $false

foreach ($port in $TargetPorts) {
    $existing = Check-Port $port
    if ($existing) {
        $procId = $existing.OwningProcess | Select-Object -Unique -First 1
        $procObj = Get-Process -Id $procId -ErrorAction SilentlyContinue
        $procName = if ($procObj) { $procObj.ProcessName } else { "Unknown" }

        # Check if this process was launched by our previous launcher run
        if ($knownLauncherPids -contains $procId) {
            Write-Host "  -> Port $port is held by a previous launcher instance (PID: $procId, $procName)." -ForegroundColor Yellow
            Write-Host "     Releasing port by stopping previously owned launcher process..." -ForegroundColor Gray
            # Stop any child processes
            Get-CimInstance Win32_Process -Filter "ParentProcessId = $procId" -ErrorAction SilentlyContinue |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Stop-Process -Id $procId -Force -ErrorAction SilentlyContinue
            Start-Sleep -Milliseconds 800
        } else {
            # Unrelated external process - DO NOT terminate automatically
            Write-Host ""
            Write-Host "  [CONFLICT ERROR] Port $port is occupied by an external, unmanaged process!" -ForegroundColor Red
            Write-Host "    - Port         : $port" -ForegroundColor Red
            Write-Host "    - Process ID   : $procId" -ForegroundColor Red
            Write-Host "    - Process Name : $procName" -ForegroundColor Red
            Write-Host "    - Reason       : This process was NOT launched by this platform orchestrator." -ForegroundColor Yellow
            Write-Host "    - Action       : Please manually close PID $procId or reconfigure the port." -ForegroundColor Yellow
            $conflictsFound = $true
        }
    }
}

if ($conflictsFound) {
    Write-Host ""
    Write-Host "Orchestration aborted due to external port conflict(s). No external processes were killed." -ForegroundColor Red
    exit 1
}

# Verify ports are clear
foreach ($port in $TargetPorts) {
    if (Check-Port $port) {
        Write-Host "  [ERROR] Port $port could not be released. Aborting startup." -ForegroundColor Red
        exit 1
    }
}

Write-Host "  [OK] Ports 8000, 8001, and 5500 are ready and unconflicted." -ForegroundColor Green
Write-Host ""

# ------------------------------------------------------------------------------
# 2. Python Environment Detection
# ------------------------------------------------------------------------------
Write-Host "[2/5] Resolving Python execution environments..." -ForegroundColor Yellow

$RootVenvPython     = Join-Path $ScriptDir ".venv\Scripts\python.exe"
$PlatformVenvPython = Join-Path $ScriptDir "AI_ESG_Platform\backend\venv\Scripts\python.exe"
$SysPython = (Get-Command python -ErrorAction SilentlyContinue).Source
if (-not $SysPython -or -not (Test-Path $SysPython)) {
    $SysPython = "C:\Users\poter\AppData\Local\Programs\Python\Python313\python.exe"
}

$DefaultPython  = if (Test-Path $RootVenvPython) { $RootVenvPython } else { $SysPython }
$Backend1Python = $DefaultPython
$Backend2Python = if (Test-Path $PlatformVenvPython) { $PlatformVenvPython } else { $DefaultPython }
$FrontendPython = $DefaultPython

Write-Host "  -> Policy Backend Python   : $Backend1Python" -ForegroundColor Gray
Write-Host "  -> Platform Backend Python : $Backend2Python" -ForegroundColor Gray
Write-Host "  -> Frontend Server Python  : $FrontendPython" -ForegroundColor Gray
Write-Host ""

# ------------------------------------------------------------------------------
# 3. Launch Persistent Background Services with Ownership Tracking
# ------------------------------------------------------------------------------
Write-Host "[3/5] Starting background services..." -ForegroundColor Yellow

# Enforce offline Hugging Face / Transformers operation and unbuffered logging
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:PYTHONUNBUFFERED = "1"

# Prepare dedicated log directory for process stdout/stderr diagnostics
$LogDir = Join-Path $ScriptDir ".platform_logs"
if (-not (Test-Path $LogDir)) {
    New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
}

$PolicyStdoutLog   = Join-Path $LogDir "policy_stdout.log"
$PolicyStderrLog   = Join-Path $LogDir "policy_stderr.log"
$PlatformStdoutLog = Join-Path $LogDir "platform_stdout.log"
$PlatformStderrLog = Join-Path $LogDir "platform_stderr.log"
$FrontendStdoutLog = Join-Path $LogDir "frontend_stdout.log"
$FrontendStderrLog = Join-Path $LogDir "frontend_stderr.log"

# Persistent process launcher with detached creation and file handle redirection.
# Launches independent of the PowerShell console session, redirecting streams directly
# to file handles so processes survive orchestrator exit with zero broken-pipe errors.
function Start-PersistentService {
    param(
        [string]$Name,
        [string]$PythonExe,
        [string]$Arguments,
        [string]$WorkingDirectory,
        [string]$StdoutLog,
        [string]$StderrLog
    )

    Write-Host "  -> Launching $Name..." -ForegroundColor White

    # Ensure log files exist and are cleared for fresh launch
    "" | Set-Content -Path $StdoutLog -Encoding UTF8 -Force
    "" | Set-Content -Path $StderrLog -Encoding UTF8 -Force

    $cmdLine = "cmd.exe /c set HF_HUB_OFFLINE=1&& set TRANSFORMERS_OFFLINE=1&& set PYTHONUNBUFFERED=1&& `"`"$PythonExe`" $Arguments 1>> `"$StdoutLog`" 2>> `"$StderrLog`"`""

    # Attempt 1: Win32_Process.Create with CREATE_NO_WINDOW (0x08000000)
    try {
        $startup = New-CimInstance -ClassName Win32_ProcessStartup -ClientOnly -Property @{
            ShowWindow  = 0
            CreateFlags = 0x08000000
        }
        $cimResult = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine                = $cmdLine
            CurrentDirectory          = $WorkingDirectory
            ProcessStartupInformation = $startup
        }
        if ($cimResult.ReturnValue -eq 0 -and $cimResult.ProcessId) {
            return [int]$cimResult.ProcessId
        }
    } catch {}

    # Attempt 2: Standard Win32_Process.Create without startup info
    try {
        $cimResult = Invoke-CimMethod -ClassName Win32_Process -MethodName Create -Arguments @{
            CommandLine      = $cmdLine
            CurrentDirectory = $WorkingDirectory
        }
        if ($cimResult.ReturnValue -eq 0 -and $cimResult.ProcessId) {
            return [int]$cimResult.ProcessId
        }
    } catch {}

    # Attempt 3: Start-Process fallback
    $p = Start-Process -FilePath "cmd.exe" -ArgumentList "/c `"`"$PythonExe`" $Arguments 1>> `"$StdoutLog`" 2>> `"$StderrLog`"`"" `
                       -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru
    return [int]$p.Id
}

# A. Start Member 2 Policy Intelligence Backend on Port 8000
$Member2Dir = Join-Path $ScriptDir "esg-enterprise-frontend-complete (2)\esg-enterprise-frontend-complete\esg-cr\backend"
$PolicyWrapperPid = Start-PersistentService `
    -Name "Policy Intelligence Backend (Port 8000)" `
    -PythonExe $Backend1Python `
    -Arguments "-m uvicorn main:app --port 8000 --host 127.0.0.1" `
    -WorkingDirectory $Member2Dir `
    -StdoutLog $PolicyStdoutLog `
    -StderrLog $PolicyStderrLog

# B. Start Core Platform & Document Intelligence Backend on Port 8001
$PlatformDir = Join-Path $ScriptDir "AI_ESG_Platform\backend"
$PlatformWrapperPid = Start-PersistentService `
    -Name "Core Platform Backend (Port 8001)" `
    -PythonExe $Backend2Python `
    -Arguments "-m uvicorn app.main:app --port 8001 --host 127.0.0.1" `
    -WorkingDirectory $PlatformDir `
    -StdoutLog $PlatformStdoutLog `
    -StderrLog $PlatformStderrLog

# C. Start Integrated Frontend Server on Port 5500
$FrontendDir = Join-Path $ScriptDir "integrated-frontend"
$FrontendWrapperPid = Start-PersistentService `
    -Name "Unified Frontend Server (Port 5500)" `
    -PythonExe $FrontendPython `
    -Arguments "-m http.server 5500 --bind 127.0.0.1" `
    -WorkingDirectory $FrontendDir `
    -StdoutLog $FrontendStdoutLog `
    -StderrLog $FrontendStderrLog

# Record initial wrapper PIDs immediately so crash or abort cleanup can target them
$pidsData = @{
    timestamp            = (Get-Date).ToString("o")
    policy_pid           = $PolicyWrapperPid
    platform_pid         = $PlatformWrapperPid
    frontend_pid         = $FrontendWrapperPid
    policy_server_pid    = $null
    platform_server_pid  = $null
    frontend_server_pid  = $null
    all_owned_pids       = @($PolicyWrapperPid, $PlatformWrapperPid, $FrontendWrapperPid)
    logs_dir             = $LogDir
}
$pidsData | ConvertTo-Json | Set-Content -Path $PidFile -Encoding UTF8

Write-Host "  [OK] Initial process handles registered in .platform_pids.json:" -ForegroundColor Green
Write-Host "       Policy Wrapper PID: $PolicyWrapperPid | Platform Wrapper PID: $PlatformWrapperPid | Frontend Wrapper PID: $FrontendWrapperPid" -ForegroundColor Gray
Write-Host "       Diagnostic logs: $LogDir" -ForegroundColor DarkGray
Write-Host ""

# ------------------------------------------------------------------------------
# 4. Health Checks & Verification Loop (Concurrent Polling)
# ------------------------------------------------------------------------------
Write-Host "[4/5] Running health checks and startup readiness verification..." -ForegroundColor Yellow
Write-Host "       (Allowing up to 240s for Core Platform embedding weights and subsystems to load)" -ForegroundColor DarkGray

$policyOk   = $false
$platformOk = $false
$frontendOk = $false
$actualPolicyPid   = $null
$actualPlatformPid = $null
$actualFrontendPid = $null
$maxSeconds = 240
$startTime  = Get-Date
$lastNoticeSec = 0

while (((Get-Date) - $startTime).TotalSeconds -lt $maxSeconds) {
    $elapsed = [int]((Get-Date) - $startTime).TotalSeconds

    # Check for early process crashes (after initial 5s grace period)
    # Only triggers if BOTH the wrapper and server processes are gone AND port is not bound
    if ($elapsed -ge 5) {
        if (-not $policyOk) {
            $wrapperAlive = $PolicyWrapperPid -and ((Get-Process -Id $PolicyWrapperPid -ErrorAction SilentlyContinue) -ne $null)
            $serverAlive  = $actualPolicyPid -and ((Get-Process -Id $actualPolicyPid -ErrorAction SilentlyContinue) -ne $null)
            $portBound    = (Check-Port 8000) -ne $null
            if (-not $wrapperAlive -and -not $serverAlive -and -not $portBound) {
                Write-Host "  -> Policy Intelligence Backend process terminated unexpectedly before port 8000 became ready." -ForegroundColor Red
                break
            }
        }
        if (-not $platformOk) {
            $wrapperAlive = $PlatformWrapperPid -and ((Get-Process -Id $PlatformWrapperPid -ErrorAction SilentlyContinue) -ne $null)
            $serverAlive  = $actualPlatformPid -and ((Get-Process -Id $actualPlatformPid -ErrorAction SilentlyContinue) -ne $null)
            $portBound    = (Check-Port 8001) -ne $null
            if (-not $wrapperAlive -and -not $serverAlive -and -not $portBound) {
                Write-Host "  -> Core Platform Backend process terminated unexpectedly before port 8001 became ready." -ForegroundColor Red
                break
            }
        }
        if (-not $frontendOk) {
            $wrapperAlive = $FrontendWrapperPid -and ((Get-Process -Id $FrontendWrapperPid -ErrorAction SilentlyContinue) -ne $null)
            $serverAlive  = $actualFrontendPid -and ((Get-Process -Id $actualFrontendPid -ErrorAction SilentlyContinue) -ne $null)
            $portBound    = (Check-Port 5500) -ne $null
            if (-not $wrapperAlive -and -not $serverAlive -and -not $portBound) {
                Write-Host "  -> Unified Web Frontend process terminated unexpectedly before port 5500 became ready." -ForegroundColor Red
                break
            }
        }
    }

    # 1. Poll Policy Intelligence (Port 8000)
    if (-not $policyOk) {
        $pConn = Check-Port 8000
        if ($pConn) {
            try {
                $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/health" -Method Get -TimeoutSec 2 -ErrorAction Stop
                $policyOk = $true
                $actualPolicyPid = Get-ListeningProcessId 8000 $PolicyWrapperPid
                Write-Host "  -> Policy Intelligence Backend (http://localhost:8000/health)... READY (HTTP 200 OK in ${elapsed}s, Server PID: $actualPolicyPid)" -ForegroundColor Green
            } catch {
                if ($_.Exception.Response -ne $null -and [int]$_.Exception.Response.StatusCode -eq 200) {
                    $policyOk = $true
                    $actualPolicyPid = Get-ListeningProcessId 8000 $PolicyWrapperPid
                    Write-Host "  -> Policy Intelligence Backend (http://localhost:8000/health)... READY (HTTP 200 OK in ${elapsed}s, Server PID: $actualPolicyPid)" -ForegroundColor Green
                }
            }
        }
    }

    # 2. Poll Core Platform Backend (Port 8001)
    if (-not $platformOk) {
        $plConn = Check-Port 8001
        if ($plConn) {
            try {
                $resp = Invoke-RestMethod -Uri "http://127.0.0.1:8001/health" -Method Get -TimeoutSec 2 -ErrorAction Stop
                $platformOk = $true
                $actualPlatformPid = Get-ListeningProcessId 8001 $PlatformWrapperPid
                Write-Host "  -> Core Platform Backend (http://localhost:8001/health)... READY (HTTP 200 OK in ${elapsed}s, Server PID: $actualPlatformPid)" -ForegroundColor Green
            } catch {
                if ($_.Exception.Response -ne $null) {
                    $status = [int]$_.Exception.Response.StatusCode
                    if ($status -eq 200) {
                        $platformOk = $true
                        $actualPlatformPid = Get-ListeningProcessId 8001 $PlatformWrapperPid
                        Write-Host "  -> Core Platform Backend (http://localhost:8001/health)... READY (HTTP 200 OK in ${elapsed}s, Server PID: $actualPlatformPid)" -ForegroundColor Green
                    } else {
                        Write-Host "     [Core Platform HTTP $status] Warming up..." -ForegroundColor DarkYellow
                    }
                }
            }
        }
    }

    # 3. Poll Unified Web Frontend (Port 5500)
    if (-not $frontendOk) {
        $fConn = Check-Port 5500
        if ($fConn) {
            try {
                $resp = Invoke-RestMethod -Uri "http://127.0.0.1:5500" -Method Get -TimeoutSec 2 -ErrorAction Stop
                $frontendOk = $true
                $actualFrontendPid = Get-ListeningProcessId 5500 $FrontendWrapperPid
                Write-Host "  -> Unified Web Frontend (http://localhost:5500)... READY (HTTP 200 OK in ${elapsed}s, Server PID: $actualFrontendPid)" -ForegroundColor Green
            } catch {
                if ($_.Exception.Response -ne $null -and [int]$_.Exception.Response.StatusCode -eq 200) {
                    $frontendOk = $true
                    $actualFrontendPid = Get-ListeningProcessId 5500 $FrontendWrapperPid
                    Write-Host "  -> Unified Web Frontend (http://localhost:5500)... READY (HTTP 200 OK in ${elapsed}s, Server PID: $actualFrontendPid)" -ForegroundColor Green
                }
            }
        }
    }

    # Continuous monitoring of confirmed ready services:
    # Only flag an issue if the underlying processes are completely dead AND the port is closed.
    # Never call 'break' here to prevent terminating startup while other services are still loading.
    if ($policyOk) {
        $wrapAlive = -not $PolicyWrapperPid -or ((Get-Process -Id $PolicyWrapperPid -ErrorAction SilentlyContinue) -ne $null)
        $srvAlive  = -not $actualPolicyPid -or ((Get-Process -Id $actualPolicyPid -ErrorAction SilentlyContinue) -ne $null)
        if (-not $wrapAlive -and -not $srvAlive -and -not (Check-Port 8000)) {
            Write-Host "  -> Policy Intelligence Backend process terminated unexpectedly." -ForegroundColor Red
            $policyOk = $false
        }
    }
    if ($frontendOk) {
        $wrapAlive = -not $FrontendWrapperPid -or ((Get-Process -Id $FrontendWrapperPid -ErrorAction SilentlyContinue) -ne $null)
        $srvAlive  = -not $actualFrontendPid -or ((Get-Process -Id $actualFrontendPid -ErrorAction SilentlyContinue) -ne $null)
        if (-not $wrapAlive -and -not $srvAlive -and -not (Check-Port 5500)) {
            Write-Host "  -> Unified Web Frontend process terminated unexpectedly." -ForegroundColor Red
            $frontendOk = $false
        }
    }
    if ($platformOk) {
        $wrapAlive = -not $PlatformWrapperPid -or ((Get-Process -Id $PlatformWrapperPid -ErrorAction SilentlyContinue) -ne $null)
        $srvAlive  = -not $actualPlatformPid -or ((Get-Process -Id $actualPlatformPid -ErrorAction SilentlyContinue) -ne $null)
        if (-not $wrapAlive -and -not $srvAlive -and -not (Check-Port 8001)) {
            Write-Host "  -> Core Platform Backend process terminated unexpectedly." -ForegroundColor Red
            $platformOk = $false
        }
    }

    # Periodic progress notification while Core Platform loads ML weights
    if (-not $platformOk -and $elapsed -ge ($lastNoticeSec + 15)) {
        $lastNoticeSec = $elapsed
        Write-Host "     [Still initializing] Core Platform loading ML embedding models and subsystems (${elapsed}s / ${maxSeconds}s)..." -ForegroundColor DarkGray
    }

    if ($policyOk -and $platformOk -and $frontendOk) {
        Write-Host "  [OK] All three services confirmed healthy and operational." -ForegroundColor Green
        break
    }
    Start-Sleep -Seconds 2
}

$elapsedTotal = [int]((Get-Date) - $startTime).TotalSeconds

if (-not $policyOk)   { Write-Host "  -> Policy Intelligence Backend (http://localhost:8000/health)... FAILED" -ForegroundColor Red }
if (-not $platformOk) { Write-Host "  -> Core Platform Backend (http://localhost:8001/health)... FAILED" -ForegroundColor Red }
if (-not $frontendOk) { Write-Host "  -> Unified Web Frontend (http://localhost:5500)... FAILED" -ForegroundColor Red }

Write-Host ""

if (-not ($policyOk -and $platformOk -and $frontendOk)) {
    Write-Host "======================================================================" -ForegroundColor Red
    Write-Host "STARTUP FAILURE DETECTED! One or more services failed to report ready." -ForegroundColor Red
    Write-Host "Elapsed startup time: ${elapsedTotal} seconds (Timeout threshold: ${maxSeconds}s)" -ForegroundColor Yellow
    Write-Host "Policy Backend   : $(if ($policyOk) {'OK'} else {'FAIL - check logs at ' + $PolicyStderrLog})" -ForegroundColor Yellow
    Write-Host "Platform Backend : $(if ($platformOk) {'OK'} else {'FAIL - check logs at ' + $PlatformStderrLog})" -ForegroundColor Yellow
    Write-Host "Frontend Server  : $(if ($frontendOk) {'OK'} else {'FAIL - check logs at ' + $FrontendStderrLog})" -ForegroundColor Yellow
    Write-Host "======================================================================" -ForegroundColor Red

    if (-not $platformOk) {
        Write-Host ""
        Write-Host "--- Core Platform Process Diagnostics (Port 8001) ---" -ForegroundColor Red
        Write-Host "  Wrapper PID  : $PlatformWrapperPid" -ForegroundColor Red
        Write-Host "  Stdout Log   : $PlatformStdoutLog" -ForegroundColor Cyan
        Write-Host "  Stderr Log   : $PlatformStderrLog" -ForegroundColor Cyan

        if (Test-Path $PlatformStderrLog) {
            $errContent = Get-Content -Path $PlatformStderrLog -Tail 40 -ErrorAction SilentlyContinue
            if ($errContent) {
                Write-Host "  Recent Stderr output:" -ForegroundColor Yellow
                $errContent | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkYellow }
            }
        }
        if (Test-Path $PlatformStdoutLog) {
            $outContent = Get-Content -Path $PlatformStdoutLog -Tail 20 -ErrorAction SilentlyContinue
            if ($outContent) {
                Write-Host "  Recent Stdout output:" -ForegroundColor Yellow
                $outContent | ForEach-Object { Write-Host "    $_" -ForegroundColor Gray }
            }
        }
    }

    if (-not $policyOk -and (Test-Path $PolicyStderrLog)) {
        Write-Host ""
        Write-Host "--- Policy Intelligence Process Diagnostics (Port 8000) ---" -ForegroundColor Red
        Get-Content -Path $PolicyStderrLog -Tail 20 -ErrorAction SilentlyContinue | ForEach-Object { Write-Host "    $_" -ForegroundColor DarkYellow }
    }

    Write-Host ""
    Write-Host "Gracefully stopping ONLY the processes owned by this launch attempt..." -ForegroundColor Yellow
    $pidsToCleanup = @($PolicyWrapperPid, $PlatformWrapperPid, $FrontendWrapperPid)
    foreach ($p in $pidsToCleanup) {
        if ($p -and [int]$p -gt 0) {
            Get-CimInstance Win32_Process -Filter "ParentProcessId = $p" -ErrorAction SilentlyContinue |
                ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
            Stop-Process -Id $p -Force -ErrorAction SilentlyContinue
        }
    }
    if (Test-Path $PidFile) { Remove-Item $PidFile -Force -ErrorAction SilentlyContinue }
    Write-Host "Diagnostics preserved in: $LogDir" -ForegroundColor Cyan
    exit 1
}

# ------------------------------------------------------------------------------
# 5. Operational Summary & PID State Persistence
# ------------------------------------------------------------------------------
# Discover exact long-lived server process PIDs listening on the ports
if (-not $actualPolicyPid)   { $actualPolicyPid   = Get-ListeningProcessId 8000 $PolicyWrapperPid }
if (-not $actualPlatformPid) { $actualPlatformPid = Get-ListeningProcessId 8001 $PlatformWrapperPid }
if (-not $actualFrontendPid) { $actualFrontendPid = Get-ListeningProcessId 5500 $FrontendWrapperPid }

$allOwnedPids = @($PolicyWrapperPid, $PlatformWrapperPid, $FrontendWrapperPid, $actualPolicyPid, $actualPlatformPid, $actualFrontendPid) |
    Where-Object { $_ -ne $null -and [int]$_ -gt 0 } | Select-Object -Unique

# Finalize PID state file with verified listening server processes
$finalPidsData = @{
    timestamp            = (Get-Date).ToString("o")
    policy_pid           = [int]$PolicyWrapperPid
    platform_pid         = [int]$PlatformWrapperPid
    frontend_pid         = [int]$FrontendWrapperPid
    policy_server_pid    = if ($actualPolicyPid) { [int]$actualPolicyPid } else { $null }
    platform_server_pid  = if ($actualPlatformPid) { [int]$actualPlatformPid } else { $null }
    frontend_server_pid  = if ($actualFrontendPid) { [int]$actualFrontendPid } else { $null }
    all_owned_pids       = $allOwnedPids
    logs_dir             = $LogDir
}
$finalPidsData | ConvertTo-Json | Set-Content -Path $PidFile -Encoding UTF8

Write-Host "======================================================================" -ForegroundColor Green
Write-Host "   AI-POWERED ENTERPRISE ESG SUSTAINABILITY PLATFORM IS ONLINE" -ForegroundColor Green
Write-Host "======================================================================" -ForegroundColor Green
Write-Host ""
Write-Host "  Unified Web Interface       : http://localhost:5500" -ForegroundColor Cyan
Write-Host "  Core Platform Swagger Docs  : http://localhost:8001/docs" -ForegroundColor Cyan
Write-Host "  Policy Intelligence Docs    : http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host ""
Write-Host "  Startup Logs Directory      : $LogDir" -ForegroundColor DarkGray
Write-Host ""
Write-Host "  Active Server PIDs:" -ForegroundColor White
Write-Host "    Policy Backend (Port 8000)   : Server PID $actualPolicyPid (Wrapper PID: $PolicyWrapperPid)" -ForegroundColor Gray
Write-Host "    Core Platform (Port 8001)    : Server PID $actualPlatformPid (Wrapper PID: $PlatformWrapperPid)" -ForegroundColor Gray
Write-Host "    Frontend Server (Port 5500)  : Server PID $actualFrontendPid (Wrapper PID: $FrontendWrapperPid)" -ForegroundColor Gray
Write-Host ""
Write-Host "  Development Demo Accounts (Pre-Seeded):" -ForegroundColor White
Write-Host "    Administrator : admin     / esg2026" -ForegroundColor Gray
Write-Host "    Auditor       : auditor   / esg2026" -ForegroundColor Gray
Write-Host "    Developer     : developer / esg2026" -ForegroundColor Gray
Write-Host "    Viewer        : viewer    / esg2026" -ForegroundColor Gray
Write-Host ""
Write-Host "----------------------------------------------------------------------" -ForegroundColor DarkGray
Write-Host "  To gracefully stop the platform, run:" -ForegroundColor Yellow
Write-Host "    .\stop_platform.ps1   OR   stop_platform.bat" -ForegroundColor Yellow
Write-Host "======================================================================" -ForegroundColor Green
