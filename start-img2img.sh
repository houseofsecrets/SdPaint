#!/bin/bash

[ -d venv ] || python -m venv venv

if [[ -d  ./venv/Scripts/ ]]; then
    source ./venv/Scripts/activate
else
  source ./venv/bin/activate
fi

SOURCE="${@}"
if [[ -z "${SOURCE}" ]]; then
    SOURCE="#"
fi

pip install -r requirements.txt

python SdPaint.py --img2img --source "${SOURCE}"

deactivate