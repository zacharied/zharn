@echo off
rem Run zharn from this checkout (Windows). Creates .venv and installs on first run.
rem Usage: run.bat [args passed to `python -m harness`]
rem Env vars work as usual, e.g.:  set HARNESS_SMOKE_PROMPT=say pong&& run.bat
setlocal
cd /d "%~dp0"
rem Until the start screen exists, open this checkout as the workspace (unset to get Scratch).
if not defined HARNESS_WORKSPACE set "HARNESS_WORKSPACE=%~dp0."

if not exist ".venv\Scripts\python.exe" (
    echo [run] no .venv yet - creating one and installing zharn ^(editable^)...
    where py >nul 2>nul && (py -3 -m venv .venv) || (python -m venv .venv)
    if not exist ".venv\Scripts\python.exe" (
        echo [run] could not create .venv - is Python 3.10+ installed and on PATH?
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --quiet --upgrade pip
    ".venv\Scripts\python.exe" -m pip install --quiet -e .[dev] || exit /b 1
)

".venv\Scripts\python.exe" -m harness %*
exit /b %errorlevel%
