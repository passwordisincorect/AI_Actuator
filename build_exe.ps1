$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$Python = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    throw "Khong tim thay .venv. Hay tao venv va cai dependency truoc."
}

& $Python -m pip install -e ".[dev]"
& $Python -m PyInstaller `
    --noconfirm `
    --clean `
    --name "AI_Actuator" `
    --collect-all "mcp" `
    --collect-all "starlette" `
    "src\ai_actuator\__main__.py"

Write-Host "Da build: $PSScriptRoot\dist\AI_Actuator\AI_Actuator.exe"

