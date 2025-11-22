# Kill all Leader and Agent processes
# Run this if the GUI can't stop them

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  FORCE STOP - Leader & Agent Processes" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""

# Function to kill process on a specific port
function Kill-ProcessOnPort {
    param([int]$Port)
    
    Write-Host "Checking port $Port..." -ForegroundColor Yellow
    
    $netstat = netstat -ano | Select-String ":$Port.*LISTENING"
    
    if ($netstat) {
        $netstat | ForEach-Object {
            $line = $_.Line
            $pid = ($line -split '\s+')[-1]
            
            if ($pid -match '^\d+$') {
                try {
                    $process = Get-Process -Id $pid -ErrorAction SilentlyContinue
                    if ($process) {
                        Write-Host "  Killing process $($process.Name) (PID: $pid) on port $Port" -ForegroundColor Red
                        Stop-Process -Id $pid -Force
                        Write-Host "  ✓ Killed successfully" -ForegroundColor Green
                    }
                } catch {
                    Write-Host "  ✗ Could not kill PID $pid" -ForegroundColor Red
                }
            }
        }
    } else {
        Write-Host "  No process found on port $Port" -ForegroundColor Gray
    }
}

# Kill processes on Leader and Agent ports
Write-Host "Stopping Leader (port 8000)..." -ForegroundColor White
Kill-ProcessOnPort -Port 8000

Write-Host ""
Write-Host "Stopping Agents (ports 9000-9003)..." -ForegroundColor White
Kill-ProcessOnPort -Port 9000
Kill-ProcessOnPort -Port 9001
Kill-ProcessOnPort -Port 9002
Kill-ProcessOnPort -Port 9003

Write-Host ""
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "  DONE! All processes should be stopped." -ForegroundColor Green
Write-Host "  You can now start fresh in the GUI." -ForegroundColor Green
Write-Host "==================================================" -ForegroundColor Cyan
Write-Host ""
