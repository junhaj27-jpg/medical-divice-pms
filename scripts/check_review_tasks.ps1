param(
    [Parameter(Mandatory=$true)][string]$DatabasePath,
    [string]$PythonPath
)
$ErrorActionPreference = "Stop"
$repoPath = Split-Path -Parent $PSScriptRoot
if (-not (Test-Path -LiteralPath $DatabasePath -PathType Leaf)) { throw "Existing SQLite database required: $DatabasePath" }
if (-not $PythonPath) { $PythonPath = Join-Path $repoPath '.venv/Scripts/python.exe' }
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) { throw "Python executable missing: $PythonPath" }
$env:SQLITE_PATH = (Resolve-Path -LiteralPath $DatabasePath).Path
$env:PYTHONIOENCODING = 'utf-8'
$dependencyPath = Join-Path (Split-Path -Parent $repoPath) 'deps'
if (Test-Path -LiteralPath $dependencyPath) { $env:PYTHONPATH = $dependencyPath + ';' + $env:PYTHONPATH }
Push-Location $repoPath
try {
    & $PythonPath manage.py notify_tasks
    if ($LASTEXITCODE -ne 0) { throw "notify_tasks failed: $LASTEXITCODE" }
} finally { Pop-Location }
