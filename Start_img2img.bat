@echo off
setlocal enabledelayedexpansion
pushd %~dp0

REM Check if venv folder exists, create it if not
if not exist venv (
    python -m venv venv
)

REM Activate the virtual environment
call venv/Scripts/activate.bat

set "var=%~1"
if "!var!" == "" set "var=#"

REM Install required packages
pip install -r requirements.txt

REM Run the script

python SdPaint.py --img2img --source "!var!"

REM Deactivate the virtual environment
deactivate
