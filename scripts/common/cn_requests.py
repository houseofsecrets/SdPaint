import functools
import requests
from requests.models import Response
from requests.adapters import HTTPAdapter, Retry
import json
from .utils import get_img2img_json, controlnet_to_sdapi


class Api:
    """
        Connector to SDAPI and ControlNet API
    """

    def __init__(self, state, retries=5):
        self.state = state
        self.url = state.server['url']
        self.retries = retries
        self.session = requests.Session()
        retries = Retry(total=retries)
        self.session.mount('http://', HTTPAdapter(max_retries=retries))

    def request(self, endpoint, *args, method="get", **kwargs):
        """
            Makes a request with retries and ConnectionError handling
        :param str endpoint: url endpoint
        :return: Response
        """

        url = f'{self.url}/{endpoint}'
        if method == 'post':
            fetch = self.session.post
        else:
            fetch = self.session.get
        try:
            return fetch(url, *args, **kwargs)
        except requests.exceptions.ConnectionError:
            response = Response()
            response.status_code = 503
            response.reason = 'Connection error'
            return response

    def fetch_controlnet_models(self, state, safe_only=True):
        """
            Fetch the available ControlNet models list from the API.
        :param State state: Application state.
        :return: The ControlNet models.
        """

        controlnet_models = []
        response = self.request('controlnet/model_list')
        if response.status_code == 200:
            r = response.json()
            for model in r.get('model_list', []):  # type: str
                if safe_only and 'scribble' not in model and 'lineart' not in model:
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

    def progress_request(self):
        """
            Call the API for rendering progression status.
        :return: The API JSON response.
        """

        response = self.request('sdapi/v1/progress')
        if response.status_code == 200:
            return response.json()
        else:
            return {"status_code": response.status_code}

    def fetch_detect_image(self, detector, image, width, height, thresholds=None):
        """
            Call detect image feature from the API.
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

        response = self.request('controlnet/detect', method="post", json=json_data)
        if response.status_code == 200:
            r = response.json()
            return {"status_code": response.status_code, "image": r['images'][0], "info": r["info"]}
        else:
            return {"status_code": response.status_code}

    def fetch_img2img(self, state):
        """
            Call img2img from the API.
        :param State state: Application state.
        :return: Requested status, image(s), and info.
        """
        json_data = get_img2img_json(state)
        response = self.request(
            'sdapi/v1/img2img', method="post", json=json_data)
        if response.status_code == 200:
            r = response.json()
            return {"status_code": response.status_code, "image": r['images'][0], "info": r["info"]}
        elif response.status_code == 500 and state.render['clip_skip_setting'] == 'clip_skip' and response.content.index(b'clip_skip') != -1:
            # Revert to old clip skip setting name if needed
            state.render['clip_skip_setting'] = 'CLIP_stop_at_last_layers'
            return self.fetch_img2img(state)
        else:
            return {"status_code": response.status_code}

    def post_request(self, state):
        """
            POST a request to the API.
        :param State state: Application state.
        :return: Requested status, image(s), and info.
        """
        endpoint = f'sdapi/v1/{"img2img" if state.img2img else "txt2img"}'
        response = self.request(endpoint, method="post", json=controlnet_to_sdapi(state["main_json_data"]))
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
            return self.post_request(state)
        else:
            return {"status_code": response.status_code}

    def fetch_configuration(self):
        """
            Request current configuration from the webui API.
        :return: The configuration JSON.
        """

        response = self.request('sdapi/v1/options')
        if response.status_code == 200:
            r = response.json()
            return r
        else:
            return {}

    def interrupt_rendering(self):
        """
            Interrupt current image generating.
        """

        return self.request("sdapi/v1/interrupt", method="post")

    def skip_rendering(self):
        """
            Skip current image generating.
        """

        return self.request("sdapi/v1/skip", method="post")

    def get_samplers(self):
        """
            Request current samplers from the webui API.
        :return: The samplers JSON.
        """

        response = self.request('sdapi/v1/samplers')
        if response.status_code == 200:
            r = response.json()
            return r
        else:
            return []

    def get_upscalers(self):
        """
            Request current upscalers from the webui API.
        :return: The upscalers JSON.
        """

        response = self.request('sdapi/v1/upscalers')
        if response.status_code == 200:
            r = response.json()
            return r
        else:
            return []


# Type hinting imports:
# from .state import State
