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

REM open view in default browser
start "" "http://localhost:8000/static/index.html"

REM start server
uvicorn --host "0.0.0.0" scripts.views.WebView.app:app --reload

REM Deactivate the virtual environment
deactivate