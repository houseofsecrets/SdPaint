#!/bin/bash

[ -d venv ] || python -m venv venv

source ./venv/bin/activate

pip install -r requirements.txt

open "scripts/views/WebView/build/index.html"
uvicorn --host "0.0.0.0" scripts.views.WebView.app:app --reload

deactivate