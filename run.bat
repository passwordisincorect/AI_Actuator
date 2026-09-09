@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [AI_Actuator] Chua tim thay .venv.
    echo Chay: python -m venv .venv
    echo Sau do: .\.venv\Scripts\python.exe -m pip install -e .
    pause
    exit /b 1
)

".venv\Scripts\python.exe" -m ai_actuator
if errorlevel 1 pause

