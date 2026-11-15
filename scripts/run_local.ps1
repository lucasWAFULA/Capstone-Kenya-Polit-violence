[CmdletBinding()]
param([ValidateRange(1024,65535)][int]$Port = 8000)
$ErrorActionPreference = 'Stop'
$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$pythonPath = Join-Path $projectRoot '.venv313\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { $pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe' }
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Create a Python 3.13 virtual environment and install requirements.txt first.' }
$env:PYTHONPATH = Join-Path $projectRoot 'src'
$uvicornArgs = @('-m','uvicorn','severity_service.app:app','--host','127.0.0.1','--port',"$Port",'--reload')
if (Test-Path -LiteralPath (Join-Path $projectRoot '.env')) { $uvicornArgs += @('--env-file', (Join-Path $projectRoot '.env')) }
Push-Location $projectRoot
try { & $pythonPath @uvicornArgs } finally { Pop-Location }
