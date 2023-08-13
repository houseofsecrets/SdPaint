import json
import requests
import threading

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from scripts.common.state import State
from scripts.common.cn_requests import Api
from scripts.common.utils import payload_submit


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=['*'],
    allow_credentials=True,
    allow_methods=['*'],
    allow_headers=['*'],
)

app.mount("/static", StaticFiles(directory="scripts/views/WebView/build"), name="static")

sd_response = None,

state = State()
api = Api(state)
url = state.server.get('url', 'http://127.0.0.1:7860')

if not state.configuration["config"]['controlnet_models']:
    api.fetch_controlnet_models(state)


def send_request(data):
    global sd_response
    response = api.post_request(state)
    if response["status_code"] == 200:
        info = json.loads(response["info"])
        input_image = data["config"]["controlnet_units"][0]["input_image"]
        info["input_image"] = input_image
        info["with_tiling"] = data["config"]["tiling"]
        response["info"] = json.dumps(info)
        sd_response = response
    state.server["busy"] = False


@app.get('/config')
async def root():
    with open(state.control_net["config_file"], 'r') as f:
        return json.load(f)


@app.post('/config')
async def root(data: Request):
    data = await data.json()
    with open(state.control_net["config_file"], 'r') as f:
        json_data = json.load(f)
    json_data["prompt"] = data["prompt"]
    json_data["negative_prompt"] = data["negative_prompt"]
    json_data["seed"] = data["seed"]
    json_data["steps"] = data["steps"]
    json_data["cfg_scale"] = data["cfg_scale"]
    json_data["batch_size"] = data["batch_size"]
    json_data["tiling"] = data["tiling"]
    json_data["width"] = data["width"]
    json_data["height"] = data["height"]
    json_data["controlnet_units"][0]["module"] = data["module"]
    json_data["controlnet_units"][0]["model"] = data["model"]
    with open(state.control_net["config_file"], 'w') as f:
        f.write(json.dumps(json_data, indent=4))


@app.post('/skip')
async def root():
    response = api.skip_rendering()
    if response.ok:
        state.server["busy"] = False
        return response.json()


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
        state["main_json_data"]["width"] = data["config"]["width"]
        state["main_json_data"]["height"] = data["config"]["height"]
        state["main_json_data"]["batch_size"] = data["config"]["batch_size"]
        state["main_json_data"]["tiling"] = data["config"]["tiling"]
        t = threading.Thread(target=send_request, args=[data])
        t.start()


@app.get('/server_status')
async def root():
    if not state.server["busy"]:
        return

    progress_json = api.progress_request()
    progress = progress_json.get('progress', None)
    if progress == 0.0:
        return "NOT READY"
    return progress


@app.get('/cn_image')
async def root():
    if sd_response:
        return sd_response
