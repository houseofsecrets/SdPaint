#!/bin/bash

[ -d venv ] || python -m venv venv

source ./venv/bin/activate

pip install pygame requests Pillow opencv-python-headless

python Scripts/SdPaint.py

deactivate