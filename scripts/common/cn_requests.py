import functools
import requests
import json
from .utils import get_img2img_json, controlnet_to_sdapi


def fetch_controlnet_models(state):
    """
        Fetch the available ControlNet models list from the API.
    :param State state: Application state.
    :return: The ControlNet models.
    """

    controlnet_models = []
    response = requests.get(url=f'{state.server["url"]}/controlnet/model_list')
    if response.status_code == 200:
        r = response.json()
        for model in r.get('model_list', []):  # type: str
            if 'scribble' not in model and 'lineart' not in model:
                continue

            if ' [' in model:
                model = model[:model.rindex(' [')]

            controlnet_models.append(model)

        def cmp_model(o1, o2):
            # Sort scribble first
            if 'scribble' in o1 and 'scribble' not in o2:
                return -1
            elif o1 < o2:
                return -1
            elif o1 > o2:
                return 1
            else:
                return 0

        controlnet_models.sort(key=functools.cmp_to_key(cmp_model))

        if controlnet_models != state.configuration["config"]['controlnet_models']:
            with open(state['configuration']["config_file"], "w") as f:
                state.configuration["config"]['controlnet_models'] = controlnet_models
                json.dump(state.configuration["config"], f, indent=4)
    else:
        print(f"Error code returned: HTTP {response.status_code}")

    state.control_net["controlnet_models"] = controlnet_models


def progress_request(state):
    """
        Call the API for rendering progression status.
    :param State state: Application state.
    :return: The API JSON response.
    """

    response = requests.get(url=f'{state.server["url"]}/sdapi/v1/progress')
    if response.status_code == 200:
        return response.json()
    else:
        return {"status_code": response.status_code}


def fetch_detect_image(state, detector, image, width, height, thresholds=None):
    """
        Call detect image feature from the API.
    :param State state: Application state.
    :param str detector: The detector to use.
    :param str image: Base64 encoder image.
    :param int width: Image width.
    :param int height: Image height.
    :param tuple[int]|None thresholds: Detector thresholds. ``(default: 64, 64)``
    :return: Requested status, image(s), and info.
    """

    # Default thresholds
    if thresholds is None:
        if detector == 'scribble_xdog':
            thresholds = (32, 32)
        elif detector == 'mlsd':
            thresholds = (0.1, 0.1)
        else:
            thresholds = (64, 64)

    json_data = {
        "controlnet_module": detector,
        "controlnet_input_images": [image],
        "controlnet_processor_res": min(width, height),
        "controlnet_threshold_a": thresholds[0],
        "controlnet_threshold_b": thresholds[1]
    }

    response = requests.post(url=f'{state.server["url"]}/controlnet/detect', json=json_data)
    if response.status_code == 200:
        r = response.json()
        return {"status_code": response.status_code, "image": r['images'][0], "info": r["info"]}
    else:
        return {"status_code": response.status_code}


def fetch_img2img(state):
    """
        Call img2img from the API.
    :param State state: Application state.
    :return: Requested status, image(s), and info.
    """
    json_data = get_img2img_json(state)
    response = requests.post(url=f'{state.server["url"]}/sdapi/v1/img2img', json=json_data)
    if response.status_code == 200:
        r = response.json()
        return {"status_code": response.status_code, "image": r['images'][0], "info": r["info"]}
    elif response.status_code == 500 and state.render['clip_skip_setting'] == 'clip_skip' and response.content.index(b'clip_skip') != -1:
        # Revert to old clip skip setting name if needed
        state.render['clip_skip_setting'] = 'CLIP_stop_at_last_layers'
        return fetch_img2img(state)
    else:
        return {"status_code": response.status_code}


def post_request(state):
    """
        POST a request to the API.
    :param State state: Application state.
    :return: Requested status, image(s), and info.
    """
    response = requests.post(url=f'{state.server["url"]}/sdapi/v1/{"img2img" if state.img2img else "txt2img"}', json=controlnet_to_sdapi(state["main_json_data"]))
    if response.status_code == 200:
        r = response.json()

        ignore_images = 1  # last image returned is the sketch, ignore when updating
        if state.render["hr_scale"] != 1.0:
            ignore_images += 1  # two sketch images are returned with HR fix

        if len(r['images']) == 1 + ignore_images:
            return {"status_code": response.status_code, "image":  r['images'][0], "info": r["info"]}
        else:
            return {"status_code": response.status_code, "batch_images": r['images'][:-ignore_images], "info": r["info"]}
    elif response.status_code == 500 and state.render['clip_skip_setting'] == 'clip_skip' and response.content.index(b'clip_skip') != -1:
        # Revert to old clip skip setting name if needed
        state.render['clip_skip_setting'] = 'CLIP_stop_at_last_layers'
        state['main_json_data']['override_settings']['CLIP_stop_at_last_layers'] = state['main_json_data']['override_settings']['clip_skip']
        del (state['main_json_data']['override_settings']['clip_skip'])
        return post_request(state)
    else:
        return {"status_code": response.status_code}


# Type hinting imports:
# from .state import State
