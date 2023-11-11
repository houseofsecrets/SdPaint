import copy
import functools
import os
import random
import re
import shutil
import threading
import base64
import io
import json
import time
import math

from PIL import Image
from psd_tools import PSDImage


def load_config(config_file):
    """
        Load a configuration file, update the local configuration file with missing settings
        from distribution file if needed.
    :param str config_file: The configuration file name.
    :return: The configuration file content.
    """

    if not os.path.exists(config_file):
        shutil.copy(f"{config_file}-dist", config_file)

    with open(config_file, "r") as f:
        config_content: dict = json.load(f)

    with open(f"{config_file}-dist", "r") as f:
        config_dist_content: dict = json.load(f)

    # Update local config with new settings
    if isinstance(config_content, dict):
        if config_content.keys() != config_dist_content.keys():
            config_dist_content.update(config_content)
            config_content = config_dist_content

            print(f"Updated {config_file} with new settings.")

            with open(config_file, "w") as f:
                json.dump(config_content, f, indent=4)

    return config_content


def update_config(config_file, write=False, values=None):
    """
        Update configuration, overwriting given fields. Optionally save the configuration to local file.
    :param str config_file: The configuration file name.
    :param bool write: Write the configuration file on disk.
    :param dict values: The arguments to overwrite.
    :return:
    """

    if not os.path.exists(config_file):
        shutil.copy(f"{config_file}-dist", config_file)

    with open(config_file, "r") as f:
        config_content: dict = json.load(f)

    if values:
        config_content.update(values)

    if write:
        with open(config_file, "w") as f:
            json.dump(config_content, f, indent=4)

    return config_content


def controlnet_to_sdapi(json_data):
    """
        Convert deprecated ``/controlnet/*2img`` JSON data to the new ``sdapi/v1/*2img`` format.
    :param dict json_data: The JSON API data.
    :return: The converted payload content.
    """

    # ensure main_json_data is left untouched
    json_data = copy.deepcopy(json_data)

    if json_data.get('alwayson_scripts', None) is None:
        json_data['alwayson_scripts'] = {}

    if not json_data['alwayson_scripts'].get('controlnet', {}):
        json_data['alwayson_scripts']['controlnet'] = {
            'args': []
        }

    if json_data.get('controlnet_units', []) and not json_data.get('alwayson_scripts', {}).get('controlnet', {}).get('args', []):
        if json_data.get('alwayson_scripts', None) is None:
            json_data['alwayson_scripts'] = {}

        json_data['alwayson_scripts']['controlnet'] = {
            'args': json_data['controlnet_units']
        }

        del json_data['controlnet_units']

    return json_data


def save_preset(state, preset_type, index):
    """
        Save the current rendering settings as preset.
    :param State state: Application state.
    :param str preset_type: The preset type. ``[render, controlnet]``
    :param int index: The preset numeric keymap.
    """
    presets = state.presets["list"]

    if presets.get(preset_type, None) is None:
        presets[preset_type] = {}

    index = str(index)

    if index == '0':
        if preset_type == 'render':
            presets[preset_type][index] = {
                'clip_skip':                    state.settings.get('override_settings', {}).get('CLIP_stop_at_last_layers', 1),
                'hr_scale':                     state.configuration["config"]['hr_scales'][1] if state.settings.get('enable_hr', 'false') == 'true' else 1.0,
                'hr_upscaler':                  state.configuration["config"]['hr_upscalers'][0],
                'denoising_strength':           state.configuration["config"]['denoising_strengths'][0],
                'sampler':                      state.configuration["config"]['samplers'][0]
            }
        elif preset_type == 'controlnet':
            presets[preset_type][index] = {
                'controlnet_weight':            state.configuration["config"]['controlnet_weights'][0],
                'controlnet_guidance_end':      state.configuration["config"]['controlnet_guidance_ends'][0],
                'controlnet_model':             state.configuration["config"]['controlnet_models'][0]
            }
    else:
        if presets[preset_type].get(index, None) is None:
            presets[preset_type][index] = {}

        if preset_type == 'render':
            presets[preset_type][index] = {
                'clip_skip':                    state.render["clip_skip"],
                'hr_scale':                     state.render["hr_scale"],
                'hr_upscaler':                  state.render["hr_upscaler"],
                'denoising_strength':           state.render["denoising_strengths"],
                'sampler':                     state.samplers["sampler"]
            }
        elif preset_type == 'controlnet':
            presets[preset_type][index] = {
                'controlnet_weight':            state.control_net["controlnet_weight"],
                'controlnet_guidance_end':      state.control_net["controlnet_guidance_end"],
                'controlnet_model':             state.control_net["controlnet_models"]
            }

    # print(f"Save {preset_type} preset {index}")
    # print(presets[preset_type][index])

    with open(state.presets["presets_file"], 'w') as f:
        json.dump(presets, f, indent=4)
    return {"preset_type": preset_type, "index": index}


def update_size_thread(state, **kwargs):
    """
        Update interface threaded method.

        If a rendering is in progress, wait before resizing.
    :param State state: Application state.
    :param kwargs: Accepted override parameter: ``hr_scale``
    """

    while state.server["busy"]:
        # Wait for rendering to end
        time.sleep(0.25)

    interface_width = state.configuration["config"].get('interface_width', state.render["init_width"] * (1 if state.img2img else 2))
    interface_height = state.configuration["config"].get('interface_height', state.render["init_height"])

    if round(interface_width / interface_height * 100) != round(state.render["init_width"] * (1 if state.img2img else 2) / state.render["init_height"] * 100):
        ratio = state.render["init_width"] / state.render["init_height"]
        if ratio < 1:
            interface_width = math.floor(interface_height * ratio)
        else:
            interface_height = math.floor(interface_width * ratio)

    state.render["soft_upscale"] = 1.0
    if interface_width != state.render["init_width"] * (1 if state.img2img else 2) or interface_height != state.render["init_height"]:
        state.render["soft_upscale"] = min(state.configuration["config"]['interface_width'] / state.render["init_width"], state.configuration["config"]['interface_height'] / state.render["init_height"])

    if kwargs.get('hr_scale', None) is not None:
        hr_scale = kwargs.get('hr_scale')
    else:
        hr_scale = state.render["hr_scale"]

    state.render["soft_upscale"] = state.render["soft_upscale"] / hr_scale
    state.render["width"] = math.floor(state.render["init_width"] * hr_scale)
    state.render["height"] = math.floor(state.render["init_height"] * hr_scale)

    state.render["render_size"] = (state.render["width"], state.render["height"])

    state.render["width"] = math.floor(state.render["width"] * state.render["soft_upscale"])
    state.render["height"] = math.floor(state.render["height"] * state.render["soft_upscale"])


def update_size(state, **kwargs):
    """
        Update the interface scale, according to image width & height, and HR scale if enabled.
    :param State state: Application state.
    :param kwargs: Accepted override parameter: ``hr_scale``
    """

    t = threading.Thread(target=functools.partial(update_size_thread, state, **kwargs))
    t.start()


def new_random_seed(state):
    """
        Generate a new random seed.
    :param State state: Application state.
    :return: The new seed.
    """

    state.gen_settings["seed"] = random.randint(0, 2**32-1)
    return state.gen_settings["seed"]


def payload_submit(state, image_string):
    """
        Fill the payload to be sent to the API.
        Set ``state.main_json_data`` variable.
    :param State state: Application state.
    :param str image_string: Image data as Base64 encoded string.
    """

    with open(state.json_file, "r") as f:
        json_data = json.load(f)

    quick_mode = state.render["quick_mode"] and json_data.get('quick', None) is not None

    if quick_mode:
        # use quick_steps setting, or halve steps if not set
        json_data['steps'] = json_data['quick'].get('steps', json_data['steps'] // 2)
        json_data['cfg_scale'] = json_data['quick'].get('cfg_scale', json_data['cfg_scale'])

    if not json_data.get('controlnet_units', None):
        json_data['controlnet_units'] = [{}]
    if not json_data['controlnet_units']:
        json_data['controlnet_units'].append({})

    json_data['controlnet_units'][0]['input_image'] = image_string
    json_data['controlnet_units'][0]['model'] = state.control_net["controlnet_model"]
    json_data['controlnet_units'][0]['weight'] = state.control_net["controlnet_weight"]
    if json_data['controlnet_units'][0].get('guidance_start', None) is None:
        json_data['controlnet_units'][0]['guidance_start'] = 0.0
    json_data['controlnet_units'][0]['guidance_end'] = state.control_net["controlnet_guidance_end"]
    json_data['controlnet_units'][0]['pixel_perfect'] = state.render["pixel_perfect"]
    if state.render["use_invert_module"]:
        json_data['controlnet_units'][0]['module'] = 'invert'
    if not state.render["pixel_perfect"]:
        json_data['controlnet_units'][0]['processor_res'] = min(state.render["width"], state.render["height"])
    json_data['hr_second_pass_steps'] = max(4, math.floor(int(json_data['steps']) * state.render["denoising_strength"]))  # at least 4 steps

    if state.render["hr_scale"] > 1.0:
        json_data['enable_hr'] = 'true'
    else:
        json_data['enable_hr'] = 'false'

    json_data['batch_size'] = state.render["batch_size"]
    json_data['seed'] = state.gen_settings["seed"]
    json_data['prompt'] = state.gen_settings["prompt"]
    if quick_mode and json_data['quick'].get('lora', None):
        json_data['prompt'] += f" <lora:{json_data['quick']['lora']}:{json_data['quick']['lora_weight']}>"
    json_data['negative_prompt'] = state.gen_settings["negative_prompt"]
    json_data['hr_scale'] = state.render["hr_scale"]
    json_data['hr_upscaler'] = state.render["hr_upscaler"]
    json_data['denoising_strength'] = state.render["denoising_strength"]
    if quick_mode and json_data['quick'].get('sampler', None):
        json_data['sampler_name'] = json_data['quick']['sampler']
    else:
        json_data['sampler_name'] = state.samplers["sampler"]

    if json_data.get('override_settings', None) is None:
        json_data['override_settings'] = {}

    json_data['override_settings'][state.render['clip_skip_setting']] = state.render["clip_skip"]

    state["main_json_data"] = json_data


def get_img2img_json(state):
    """
       Construct img2img JSON payload.
    :param State state: Application state.
    :return: JSON payload.
    """

    with open(state.json_file, "r") as f:
        json_data = json.load(f)

    if os.path.splitext(state.img2img)[1] == '.psd':
        psd = PSDImage.open(state.img2img)
        im = psd.composite()
        data = io.BytesIO()
        im.save(data, format="png")
        data = base64.b64encode(data.getvalue()).decode('utf-8')
        json_data['width'] = im.width
        json_data['height'] = im.height
    else:
        with Image.open(state.img2img, mode='r') as im:
            data = io.BytesIO()
            im.save(data, format=im.format)
            data = base64.b64encode(data.getvalue()).decode('utf-8')
            json_data['width'] = im.width
            json_data['height'] = im.height

    quick_mode = state.render["quick_mode"] and json_data.get('quick', None) is not None

    json_data['init_images'] = [data]

    json_data['seed'] = state.gen_settings["seed"]
    json_data['prompt'] = state.gen_settings["prompt"]
    if quick_mode and json_data['quick'].get('lora', None):
        json_data['prompt'] += f" <lora:{json_data['quick']['lora']}:{json_data['quick']['lora_weight']}>"
    json_data['negative_prompt'] = state.gen_settings["negative_prompt"]
    json_data['denoising_strength'] = state.render["denoising_strength"]
    if quick_mode and json_data['quick'].get('sampler', None):
        json_data['sampler_name'] = json_data['quick']['sampler']
    else:
        json_data['sampler_name'] = state.samplers["sampler"]

    if json_data.get('override_settings', None) is None:
        json_data['override_settings'] = {}

    json_data['override_settings'][state.render['clip_skip_setting']] = state.render["clip_skip"]

    if quick_mode:
        # use quick_steps setting, or halve steps if not set
        json_data['steps'] = json_data['quick'].get('steps', json_data['steps'] // 2)
        json_data['cfg_scale'] = json_data['quick'].get('cfg_scale', json_data['cfg_scale'])

    return json_data


checkpoint_pattern = re.compile(r'^(?P<dir>.*(?:\\|\/))?(?P<name>.*?)(?P<vae>\.vae)?(?P<ext>\.safetensors|\.pt|\.ckpt) ?(?P<hash>\[[^\]]*\])?.*')


def ckpt_name(name, display_dir=False, display_ext=False, display_hash=False):
    """
        Clean checkpoint name.
    :param str name: Checkpoint name.
    :param bool display_dir: Display full path.
    :param bool display_ext: Display checkpoint extension.
    :param bool display_hash: Display checkpoint hash.
    :return: Cleaned checkpoint name.
    """

    replace = ''
    if display_dir:
        replace += r'\g<dir>'

    replace += r'\g<name>'

    if display_ext:
        replace += r'\g<vae>\g<ext>'

    if display_hash:
        replace += r' \g<hash>'

    return checkpoint_pattern.sub(replace, name)
