@echo off
setlocal enabledelayedexpansion

REM Check if venv folder exists, create it if not
if not exist venv (
    python -m venv venv
)

REM Activate the virtual environment
call venv/Scripts/activate.bat

REM Install required packages
pip install -r requirements.txt

REM Run the script
python Scripts/SdPaint.py

REM Deactivate the virtual environment
deactivate
