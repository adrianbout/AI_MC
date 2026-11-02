@echo off
setlocal
cd /d "%~dp0"
title AI MC

rem First run: create the virtual environment and install dependencies.
if not exist "venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    where py >nul 2>nul && (py -3 -m venv venv) || (python -m venv venv)
    if errorlevel 1 (
        echo Failed to create venv - is Python installed and on PATH?
        pause
        exit /b 1
    )
    call "venv\Scripts\activate.bat"
    python -m pip install --upgrade pip
    python -m pip install -r requirements.txt
    if errorlevel 1 (
        echo Dependency install failed.
        pause
        exit /b 1
    )
) else (
    call "venv\Scripts\activate.bat"
)

python app.py
if errorlevel 1 (
    echo.
    echo AI MC exited with an error.
)
pause
