

import json
import os
import base64
from io import BytesIO
import requests
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from scripts.common.state import State
from scripts.common.cn_requests import fetch_controlnet_models, post_request, progress_request
from scripts.common.utils import payload_submit


url = 'http://127.0.0.1:7860'

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

sd_image = ''

state = State()

if not state.configuration["config"]['controlnet_models']:
    fetch_controlnet_models(state)


def send_request():
    global sd_image
    response = post_request(state)
    if response["status_code"] == 200:
        print(response.keys(), response["status_code"], response.get(
            "image", None)[:10])
        if response.get("image", None):
            sd_image = response["image"]
        # elif response.get("batch_images", None):
        #     self.update_batch_images(response["batch_images"])
    state.server["busy"] = False


@app.get('/config')
async def root():
    with open('../controlnet.json', 'r') as f:
        return json.load(f)


@app.get('/models')
async def root():
    return state.control_net["controlnet_models"]


@app.get('/modules')
async def root():
    response = requests.get(url=f'{url}/controlnet/module_list')
    if response.ok:
        return response.json()


@app.post('/paint_image')
async def root(data: Request):
    if not state.server["busy"]:
        state.server["busy"] = True
        data = await data.json()
        payload_submit(state, data["config"]
                       ["controlnet_units"][0]["input_image"])
        state["main_json_data"]["prompt"] = data["config"]["prompt"]
        state["main_json_data"]["negative_prompt"] = data["config"]["negative_prompt"]
        state["main_json_data"]["seed"] = data["config"]["seed"]
        t = threading.Thread(target=send_request)
        t.start()


@app.get('/server_status')
async def root():
    if not state.server["busy"]:
        return

    progress_json = progress_request(state)
    progress = progress_json.get('progress', None)
    if progress == 0.0:
        return 1.0
    return progress


@app.get('/cn_image')
async def root():
    if sd_image:
        bytes_image = BytesIO(base64.b64decode(sd_image))
        return Response(content=bytes_image.getvalue(), media_type='image/png')
