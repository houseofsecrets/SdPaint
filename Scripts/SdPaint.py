import copy
import functools
import os
import random
import shutil
import sys

import pygame
import pygame.gfxdraw
import requests
import threading
# import numpy as np
import base64
import io
import json
import time
import math
from PIL import Image, ImageOps
from psd_tools import PSDImage
import tkinter as tk
from tkinter import filedialog, simpledialog
import argparse

# Initialize Pygame
pygame.init()
clock = pygame.time.Clock()


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


# Read JSON main configuration file
config_file = "config.json"
config = load_config(config_file)

presets_file = "presets.json"
presets = load_config(presets_file)

settings = {}

# Setup
url = config.get('url', 'http://127.0.0.1:7860')

ACCEPTED_FILE_TYPES = ["png", "jpg", "jpeg", "bmp"]

# Global variables
img2img = None
img2img_waiting = False
img2img_time_prev = None

hr_scales = config.get("hr_scales", [1.0, 1.25, 1.5, 2.0])
if 1.0 not in hr_scales:
    hr_scales.insert(0, 1.0)
hr_scale = hr_scales[0]
hr_scale_prev = hr_scales[1]

hr_upscalers = config.get("hr_upscalers", ['Latent (bicubic)'])
hr_upscaler = hr_upscalers[0]

denoising_strengths = config.get("denoising_strengths", [0.6])
denoising_strength = denoising_strengths[0]

samplers = config.get("samplers", ["DDIM"])
sampler = samplers[0]

controlnet_weights = config.get("controlnet_weights", [0.6, 1.0, 1.6])
controlnet_weight = controlnet_weights[0]

controlnet_guidance_ends = config.get("controlnet_guidance_ends", [1.0, 0.2, 0.3])
controlnet_guidance_end = controlnet_guidance_ends[0]

render_preset_fields = config.get('preset_fields', ["hr_enabled", "hr_scale", "hr_upscaler", "denoising_strength"])
cn_preset_fields = config.get('cn_preset_fields', ["controlnet_model", "controlnet_weight", "controlnet_guidance_end"])

batch_sizes = config.get("batch_sizes", [1, 4, 9, 16])
if 1 not in batch_sizes:
    batch_sizes.insert(0, 1)
batch_size = batch_sizes[0]
batch_size_prev = batch_sizes[1]
batch_hr_scale_prev = hr_scale

autosave_seed = config.get('autosave_seed', 'false') == 'true'
autosave_prompt = config.get('autosave_prompt', 'false') == 'true'
autosave_negative_prompt = config.get('autosave_negative_prompt', 'false') == 'true'

main_json_data = {}
quick_mode = False
server_busy = False
rendering = False
rendering_key = False
instant_render = False
pause_render = False
use_invert_module = True
osd_always_on_text: str|None = None
progress = 0.0
controlnet_models: list[str] = config.get("controlnet_models", [])

detectors = config.get('detectors', ('lineart',))
detector = detectors[0]

last_detect_time = time.time()
osd_text = None
osd_text_display_start = None
clip_skip = 1

# Read command-line arguments
if __name__ == '__main__':
    argParser = argparse.ArgumentParser()
    argParser.add_argument("--img2img", help="img2img source file")

    args = argParser.parse_args()

    img2img = args.img2img
    if img2img == '':
        img2img = '#'  # force load file dialog if launched with --img2img without value


def update_size_thread(**kwargs):
    """
        Update interface threaded method.

        If a rendering is in progress, wait before resizing.

    :param kwargs: Accepted override parameter: ``hr_scale``
    """

    global width, height, soft_upscale, hr_scale

    while server_busy:
        # Wait for rendering to end
        time.sleep(0.25)

    interface_width = config.get('interface_width', init_width * (1 if img2img else 2))
    interface_height = config.get('interface_height', init_height)

    if round(interface_width / interface_height * 100) != round(init_width * (1 if img2img else 2) / init_height * 100):
        ratio = init_width / init_height
        if ratio < 1:
            interface_width = math.floor(interface_height * ratio)
        else:
            interface_height = math.floor(interface_width * ratio)

    soft_upscale = 1.0
    if interface_width != init_width * (1 if img2img else 2) or interface_height != init_height:
        soft_upscale = min(config['interface_width'] / init_width, config['interface_height'] / init_height)

    if kwargs.get('hr_scale', None) is not None:
        hr_scale = kwargs.get('hr_scale')

    soft_upscale = soft_upscale / hr_scale
    width = math.floor(init_width * hr_scale)
    height = math.floor(init_height * hr_scale)

    width = math.floor(width * soft_upscale)
    height = math.floor(height * soft_upscale)


def update_size(**kwargs):
    """
        Update the interface scale, according to image width & height, and HR scale if enabled.
    :param kwargs: Accepted override parameter: ``hr_scale``
    :return:
    """

    t = threading.Thread(target=functools.partial(update_size_thread, **kwargs))
    t.start()


def fetch_controlnet_models():
    """
        Fetch the available ControlNet models list from the API.
    :return: The ControlNet models.
    """
    global controlnet_models

    controlnet_models = []
    response = requests.get(url=f'{url}/controlnet/model_list')
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

        if controlnet_models != config['controlnet_models']:
            with open(config_file, "w") as f:
                config['controlnet_models'] = controlnet_models
                json.dump(config, f, indent=4)
    else:
        print(f"Error code returned: HTTP {response.status_code}")


if not config['controlnet_models']:
    fetch_controlnet_models()


# Read JSON rendering configuration files
json_file = "controlnet.json"
if img2img:
    json_file = "img2img.json"

settings = load_config(json_file)

seed = settings.get('seed', 3456456767)
if settings.get('override_settings', None) is not None and settings['override_settings'].get('CLIP_stop_at_last_layers', None) is not None:
    clip_skip = settings['override_settings']['CLIP_stop_at_last_layers']

if settings.get('enable_hr', 'false') == 'true':
    hr_scale = hr_scales[1]
    batch_hr_scale_prev = hr_scale

prompt = settings.get('prompt', '')
negative_prompt = settings.get('negative_prompt', '')

if settings.get("controlnet_units", None) and settings.get("controlnet_units")[0].get('pixel_perfect', None):
    pixel_perfect = settings.get("controlnet_units")[0]["pixel_perfect"] == "true"
else:
    pixel_perfect = False

width = settings.get('width', 512)
height = settings.get('height', 512)
init_width = width * 1.0
init_height = height * 1.0
soft_upscale = 1.0
if settings.get("controlnet_units", None) and settings.get("controlnet_units")[0].get('model', None):
    controlnet_model = settings.get("controlnet_units")[0]["model"]
elif controlnet_models:
    controlnet_model = controlnet_models[0]
else:
    controlnet_model = None
update_size()

if controlnet_model and settings.get("controlnet_units", None) and not settings.get("controlnet_units")[0].get('model', None):
    settings['controlnet_units'][0]['model'] = controlnet_model
    with open(json_file, "w") as f:
        json.dump(settings, f, indent=4)

if img2img:
    if not os.path.exists(img2img):
        root = tk.Tk()
        root.withdraw()
        img2img = filedialog.askopenfilename()

    img2img_time = os.path.getmtime(img2img)

    with Image.open(img2img, mode='r') as im:
        width = im.width
        height = im.height
        init_width = width * 1.0
        init_height = height * 1.0
        update_size()

# Set up the display
fullscreen = False
screen = pygame.display.set_mode((width * (1 if img2img else 2), height))
display_caption = "Sd Paint"
pygame.display.set_caption(display_caption)

# Setup text
font = pygame.font.SysFont(None, size=24)
font_bold = pygame.font.SysFont(None, size=24, bold=True)
text_input = ""

# Set up the drawing surface
canvas = pygame.Surface((width*2, height))
pygame.draw.rect(canvas, (255, 255, 255), (0, 0, width * (1 if img2img else 2), height))

# Set up the brush
brush_size = {1: 2, 2: 2, 'e': 10}
brush_colors = {
    1: (0, 0, 0),  # Left mouse button color
    2: (255, 255, 255),  # Middle mouse button color
    'e': (255, 255, 255),  # Eraser color
}
brush_pos = {1: None, 2: None, 'e': None}
prev_pos = None
prev_pos2 = None
shift_pos = None
eraser_down = False
render_wait = 0.5 if not img2img else 0.0  # wait time max between 2 draw before launching the render
last_draw_time = time.time()
last_render_bytes: io.BytesIO = None

# Define the cursor size and color
cursor_size = 1
cursor_color = (0, 0, 0)


def save_preset(preset_type, index):
    """
        Save the current rendering settings as preset.
    :param str preset_type: The preset type. ``[render, controlnet]``
    :param int index: The preset numeric keymap.
    """
    global presets

    if presets.get(preset_type, None) is None:
        presets[preset_type] = {}

    index = str(index)

    if index == '0':
        if preset_type == 'render':
            presets[preset_type][index] = {
                'clip_skip':                    settings.get('override_settings', {}).get('CLIP_stop_at_last_layers', 1),
                'hr_scale':                     config['hr_scales'][1] if settings.get('enable_hr', 'false') == 'true' else 1.0,
                'hr_upscaler':                  config['hr_upscalers'][0],
                'denoising_strength':           config['denoising_strengths'][0],
                'sampler':                      config['samplers'][0]
            }
        elif preset_type == 'controlnet':
            presets[preset_type][index] = {
                'controlnet_weight':            config['controlnet_weights'][0],
                'controlnet_guidance_end':      config['controlnet_guidance_ends'][0],
                'controlnet_model':             config['controlnet_models'][0]
            }
    else:
        if presets[preset_type].get(index, None) is None:
            presets[preset_type][index] = {}

        if preset_type == 'render':
            presets[preset_type][index] = {
                'clip_skip':                    clip_skip,
                'hr_scale':                     hr_scale,
                'hr_upscaler':                  hr_upscaler,
                'denoising_strength':           denoising_strength,
                'sampler':                      sampler
            }
        elif preset_type == 'controlnet':
            presets[preset_type][index] = {
                'controlnet_weight':            controlnet_weight,
                'controlnet_guidance_end':      controlnet_guidance_end,
                'controlnet_model':             controlnet_model
            }

        osd(text=f"Save {preset_type} preset {index}")

    # print(f"Save {preset_type} preset {index}")
    # print(presets[preset_type][index])

    with open(presets_file, 'w') as f:
        json.dump(presets, f, indent=4)


def load_preset(preset_type, index):
    """
        Load a preset values.
    :param str preset_type: The preset type. ``[render, controlnet]``
    :param int index: The preset numeric keymap.
    """

    index = str(index)

    if presets[preset_type].get(index, None) is None:
        osd(text=f"No {preset_type} preset {index}")
        return None

    preset = presets[preset_type][index]

    if index == '0':
        text = f"Load default settings:"

        if preset_type == 'controlnet':
            # prepend OSD output with render preset values for default settings display (both called successively)
            for preset_field in render_preset_fields:
                text += f"\n  {preset_field[:1].upper()}{preset_field[1:].replace('_', ' ')} :: {presets['render'][index][preset_field]}"
    else:
        text = f"Load {preset_type} preset {index}:"

    # load preset
    for preset_field in (render_preset_fields if preset_type == 'render' else cn_preset_fields):
        globals()[preset_field] = preset[preset_field]
        text += f"\n  {preset_field[:1].upper()}{preset_field[1:].replace('_', ' ')} :: {preset[preset_field]}"

    osd(text=text, text_time=4.0)
    update_size()


# Init the default preset
save_preset('render', 0)
save_preset('controlnet', 0)


def load_filepath_into_canvas(file_path):
    """
        Load an image file on the sketch canvas.

    :param str file_path: Local image file path.
    """
    global canvas
    canvas = pygame.Surface((width * (1 if img2img else 2), height))
    pygame.draw.rect(canvas, (255, 255, 255), (0, 0, width * (1 if img2img else 2), height))
    img = pygame.image.load(file_path)
    img = pygame.transform.smoothscale(img, (width, height))
    canvas.blit(img, (width, 0))


def finger_pos(finger_x, finger_y):
    x = round(min(max(finger_x, 0), 1) * width * (1 if img2img else 2))
    y = round(min(max(finger_y, 0), 1) * height)
    return x, y


def save_file_dialog():
    """
        Display save file dialog, then write the file.

    :return: The saved file path.
    """
    global last_render_bytes

    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.asksaveasfilename(defaultextension=".png")

    if file_path:
        file_name, file_ext = os.path.splitext(file_path)

        # save last rendered image
        with open(file_path, "wb") as image_file:
            image_file.write(last_render_bytes.getbuffer().tobytes())

        # save sketch
        sketch_img = canvas.subsurface(pygame.Rect(width, 0, width, height)).copy()
        pygame.image.save(sketch_img, f"{file_name}-sketch{file_ext}")

        time.sleep(1)  # add a 1-second delay
    return file_path


def load_file_dialog():
    """
        Display loading file dialog, then load the image on the sketch canvas.
    """

    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename()
    if not file_path:
        return

    extension = os.path.splitext(file_path)[1][1:].lower()
    if extension in ACCEPTED_FILE_TYPES:
        load_filepath_into_canvas(file_path)


def update_image(image_data):
    """
        Redraw the image canvas.

    :param str image_data: Base64 encoded image data, from API response.
    """
    global last_render_bytes

    # Decode base64 image data
    img_bytes = io.BytesIO(base64.b64decode(image_data))
    img_surface = pygame.image.load(img_bytes)
    last_render_bytes = io.BytesIO(base64.b64decode(image_data))

    if soft_upscale != 1.0:
        img_surface = pygame.transform.smoothscale(img_surface, (img_surface.get_width() * soft_upscale, img_surface.get_height() * soft_upscale))

    canvas.blit(img_surface, (0, 0))
    global need_redraw
    need_redraw = True


def update_images(image_datas):
    """
        Redraw the image canvas with multiple images.

    :param list[str] image_datas: Base64 encoded images data, from API response.
    """
    global last_render_bytes

    nb = math.ceil(math.sqrt(len(image_datas)))
    i, j = 0, 0
    for image_data in image_datas:
        pos = (i * width // nb, j * height // nb)

        # Decode base64 image data
        img_bytes = io.BytesIO(base64.b64decode(image_data))
        img_surface = pygame.image.load(img_bytes)
        last_render_bytes = io.BytesIO(base64.b64decode(image_data))

        if soft_upscale != 1.0:
            img_surface = pygame.transform.smoothscale(img_surface, (img_surface.get_width() * soft_upscale // nb, img_surface.get_height() * soft_upscale // nb))

        canvas.blit(img_surface, pos)
        i = (i + 1) % nb
        if i == 0:
            j = (j + 1) % nb

    global need_redraw
    need_redraw = True


def new_random_seed():
    """
        Generate a new random seed.

    :return: The new seed.
    """

    global seed
    seed = random.randint(0, 2**32-1)
    return seed


def img2img_submit(force=False):
    """
        Read the ``img2img`` file if modified since last render, check every 1s. Call the API to render if needed.

    :param bool force: Force the rendering, even if the file is not modified.
    """

    global img2img_time_prev, img2img_time, img2img_waiting, seed, server_busy
    img2img_waiting = False

    img2img_time = os.path.getmtime(img2img)
    if img2img_time != img2img_time_prev or force:
        img2img_time_prev = img2img_time

        with open(json_file, "r") as f:
            json_data = json.load(f)

        if os.path.splitext(img2img)[1] == '.psd':
            psd = PSDImage.open(img2img)
            im = psd.composite()
            data = io.BytesIO()
            im.save(data, format="png")
            data = base64.b64encode(data.getvalue()).decode('utf-8')
            json_data['width'] = im.width
            json_data['height'] = im.height
        else:
            with Image.open(img2img, mode='r') as im:
                data = io.BytesIO()
                im.save(data, format=im.format)
                data = base64.b64encode(data.getvalue()).decode('utf-8')
                json_data['width'] = im.width
                json_data['height'] = im.height

        json_data['init_images'] = [data]

        json_data['seed'] = seed
        json_data['prompt'] = prompt
        json_data['negative_prompt'] = negative_prompt
        json_data['denoising_strength'] = denoising_strength
        json_data['sampler_name'] = sampler

        if json_data.get('override_settings', None) is None:
            json_data['override_settings'] = {}

        json_data['override_settings']['CLIP_stop_at_last_layers'] = clip_skip

        if quick_mode:
            json_data['steps'] = json_data.get('quick_steps', json_data['steps'] // 2)  # use quick_steps setting, or halve steps if not set

        server_busy = True

        t = threading.Thread(target=progress_bar)
        t.start()

        response = requests.post(url=f'{url}/sdapi/v1/img2img', json=json_data)
        if response.status_code == 200:
            r = response.json()
            return_img = r['images'][0]
            update_image(return_img)
            r_info = json.loads(r['info'])
            return_prompt = r_info['prompt']
            return_seed = r_info['seed']
            global display_caption
            display_caption = f"Sd Paint | Seed: {return_seed} | Prompt: {return_prompt}"
        else:
            osd(text=f"Error code returned: HTTP {response.status_code}")

        server_busy = False

    if not img2img_waiting and running:
        img2img_waiting = True
        time.sleep(1.0)
        img2img_submit()


def progress_request():
    """
        Call the API for rendering progression status.

    :return: The API JSON response.
    """

    response = requests.get(url=f'{url}/sdapi/v1/progress')
    if response.status_code == 200:
        r = response.json()
        return r
    else:
        osd(text=f"Error code returned: HTTP {response.status_code}")
        return {}


def progress_bar():
    """
        Update the progress bar every 0.25s
    """
    global progress

    if not server_busy:
        return

    progress_json = progress_request()
    progress = progress_json.get('progress', None)
    # if progress is not None and progress > 0.0:
    #     print(f"{progress*100:.0f}%")

    if server_busy:
        time.sleep(0.25)
        progress_bar()


def draw_osd_text(text, rect, color=(255, 255, 255), shadow_color=(0, 0, 0), distance=1, right_align=False):
    """
        Draw OSD text with outline.
    :param str text: The text to draw.
    :param list[int]|tuple[int]|pygame.Rect rect: Destination rect.
    :param tuple|int color: Text color.
    :param tuple|int shadow_color: Outline color.
    :param int distance: Outline/shadow size.
    :param bool right_align: Align text to the right.
    """

    align_offset = 0
    if right_align:
        align_offset = -1

    text_surface = font.render(text, True, shadow_color)
    screen.blit(text_surface, (rect[0] + text_surface.get_width() * align_offset + distance, rect[1] + distance, rect[2], rect[3]))
    screen.blit(text_surface, (rect[0] + text_surface.get_width() * align_offset - distance, rect[1] + distance, rect[2], rect[3]))
    screen.blit(text_surface, (rect[0] + text_surface.get_width() * align_offset + distance, rect[1] - distance, rect[2], rect[3]))
    screen.blit(text_surface, (rect[0] + text_surface.get_width() * align_offset - distance, rect[1] - distance, rect[2], rect[3]))
    text_surface = font.render(text, True, color)
    screen.blit(text_surface, (rect[0] + text_surface.get_width() * align_offset, rect[1], rect[2], rect[3]))


def osd(**kwargs):
    """
        OSD display: progress bar and text messages.

    :param kwargs: Accepted parameters : ``progress, text, text_time, need_redraw``
    """

    global osd_text, osd_text_display_start

    osd_size = (128, 20)
    osd_margin = 10
    osd_progress_pos = (width*(0 if img2img else 1) + osd_margin, osd_margin)  # top left of canvas
    # osd_pos = (width*(1 if img2img else 2) // 2 - osd_size [0] // 2, osd_margin)  # top center
    # osd_progress_pos = (width*(1 if img2img else 2) - osd_size[0] - osd_margin, height - osd_size[1] - osd_margin)  # bottom right

    osd_dot_size = osd_size[1] // 2
    # osd_dot_pos = (width*(0 if img2img else 1) + osd_margin, osd_margin, osd_dot_size, osd_dot_size)  # top left
    osd_dot_pos = (width*(1 if img2img else 2) - osd_dot_size * 2 - osd_margin, osd_margin, osd_dot_size, osd_dot_size)  # top right

    osd_text_pos = (width*(0 if img2img else 1) + osd_margin, osd_margin)  # top left of canvas
    # osd_text_pos = (width*(0 if img2img else 1) + osd_margin, height - osd_size[1] - osd_margin)  # bottom left of canvas
    osd_text_offset = 0

    osd_text_split_offset = 250

    global progress, need_redraw, osd_always_on_text

    progress = kwargs.get('progress', progress)  # type: float
    text = kwargs.get('text', osd_text)  # type: str
    text_time = kwargs.get('text_time', 2.0)  # type: float
    need_redraw = kwargs.get('need_redraw', need_redraw)  # type: bool
    osd_always_on_text = kwargs.get('always_on', osd_always_on_text)

    if rendering or (server_busy and progress is not None and progress < 0.02):
        rendering_dot_surface = pygame.Surface(osd_size, pygame.SRCALPHA)

        pygame.draw.circle(rendering_dot_surface, (0, 0, 0), (osd_dot_size + 2, osd_dot_size + 2), osd_dot_size - 2)
        pygame.draw.circle(rendering_dot_surface, (0, 200, 160), (osd_dot_size, osd_dot_size), osd_dot_size - 2)
        screen.blit(rendering_dot_surface, osd_dot_pos)

    if progress is not None and progress > 0.01:
        need_redraw = True

        # progress bar
        progress_surface = pygame.Surface(osd_size, pygame.SRCALPHA)
        pygame.draw.rect(progress_surface, (0, 0, 0), pygame.Rect(2, 2, math.floor(osd_size[0] * progress), osd_size[1]))
        pygame.draw.rect(progress_surface, (0, 200, 160), pygame.Rect(0, 0, math.floor(osd_size[0] * progress), osd_size[1] - 2))

        screen.blit(progress_surface, pygame.Rect(osd_progress_pos[0], osd_progress_pos[1], osd_size[0], osd_size[1]))

        # progress text
        draw_osd_text(f"{progress * 100:.0f}%", (osd_size[0] - osd_margin + osd_progress_pos[0], 3 + osd_progress_pos[1], osd_size[0], osd_size[1]), right_align=True)

        osd_text_offset = osd_size[1] + osd_margin

    if osd_always_on_text:
        need_redraw = True

        # OSD always-on text
        for line in osd_always_on_text.split('\n'):
            need_redraw = True

            if '::' in line:
                line, line_value = line.split('::')
                line = line.rstrip(' ')
                line_value = line_value.lstrip(' ')
            else:
                line_value = None

            draw_osd_text(line, (osd_text_pos[0], osd_text_pos[1] + osd_text_offset, osd_size[0], osd_size[1]))
            if line_value:
                draw_osd_text(line_value, (osd_text_pos[0] + osd_text_split_offset, osd_text_pos[1] + osd_text_offset, osd_size[0], osd_size[1]))

            osd_text_offset += osd_size[1]

    if text:
        need_redraw = True

        # OSD text
        if osd_text_display_start is None or text != osd_text:
            osd_text_display_start = time.time()
        osd_text = text

        for line in osd_text.split('\n'):
            need_redraw = True

            if '::' in line:
                line, line_value = line.split('::')
                line = line.rstrip(' ')
                line_value = line_value.lstrip(' ')
            else:
                line_value = None

            draw_osd_text(line, (osd_text_pos[0], osd_text_pos[1] + osd_text_offset, osd_size[0], osd_size[1]))
            if line_value:
                draw_osd_text(line_value, (osd_text_pos[0] + osd_text_split_offset, osd_text_pos[1] + osd_text_offset, osd_size[0], osd_size[1]))

            osd_text_offset += osd_size[1]

        if time.time() - osd_text_display_start > text_time:
            osd_text = None
            osd_text_display_start = None


def payload_submit():
    """
        Fill the payload to be sent to the API.

        Set ``main_json_data`` variable.
    """

    global main_json_data
    img = canvas.subsurface(pygame.Rect(width, 0, width, height)).copy()

    if not use_invert_module:
        # Convert the Pygame surface to a PIL image
        pil_img = Image.frombytes('RGB', img.get_size(), pygame.image.tostring(img, 'RGB'))

        # Invert the colors of the PIL image
        pil_img = ImageOps.invert(pil_img)

        # Convert the PIL image back to a Pygame surface
        img = pygame.image.fromstring(pil_img.tobytes(), pil_img.size, pil_img.mode).convert_alpha()

    # Save the inverted image as base64-encoded data
    data = io.BytesIO()
    pygame.image.save(img, data)
    data = base64.b64encode(data.getvalue()).decode('utf-8')
    with open(json_file, "r") as f:
        json_data = json.load(f)

    if quick_mode:
        json_data['steps'] = json_data.get('quick_steps', json_data['steps'] // 2)  # use quick_steps setting, or halve steps if not set

    json_data['controlnet_units'][0]['input_image'] = data
    json_data['controlnet_units'][0]['model'] = controlnet_model
    json_data['controlnet_units'][0]['weight'] = controlnet_weight
    if json_data['controlnet_units'][0].get('guidance_start', None) is None:
        json_data['controlnet_units'][0]['guidance_start'] = 0.0
    json_data['controlnet_units'][0]['guidance_end'] = controlnet_guidance_end
    json_data['controlnet_units'][0]['pixel_perfect'] = pixel_perfect
    if use_invert_module:
        json_data['controlnet_units'][0]['module'] = 'invert'
    if not pixel_perfect:
        json_data['controlnet_units'][0]['processor_res'] = min(width, height)

    json_data['hr_second_pass_steps'] = max(8, math.floor(json_data['steps'] * denoising_strength))  # at least 8 steps

    if hr_scale > 1.0:
        json_data['enable_hr'] = 'true'
    else:
        json_data['enable_hr'] = 'false'

    json_data['batch_size'] = batch_size
    json_data['seed'] = seed
    json_data['prompt'] = prompt
    json_data['negative_prompt'] = negative_prompt
    json_data['hr_scale'] = hr_scale
    json_data['hr_upscaler'] = hr_upscaler
    json_data['denoising_strength'] = denoising_strength
    json_data['sampler_name'] = sampler

    if json_data.get('override_settings', None) is None:
        json_data['override_settings'] = {}

    json_data['override_settings']['CLIP_stop_at_last_layers'] = clip_skip

    main_json_data = json_data


def controlnet_to_sdapi(json_data):
    """
        Convert deprecated ``/controlnet/*2img`` JSON data to the new ``sdapi/v1/*2img`` format.

    :param dict json_data: The JSON API data.
    :return: The converted payload content.
    """

    json_data = copy.deepcopy(json_data)  # ensure main_json_data is left untouched

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


def send_request():
    """
        Send the API request.

        Use ``main_json_data`` variable.
    """

    global server_busy
    response = requests.post(url=f'{url}/sdapi/v1/{"img2img" if img2img else "txt2img"}', json=controlnet_to_sdapi(main_json_data))
    if response.status_code == 200:
        r = response.json()

        ignore_images = 1  # last image returned is the sketch, ignore when updating
        if hr_scale != 1.0:
            ignore_images += 1  # two sketch images are returned with HR fix

        if len(r['images']) == 1 + ignore_images:
            return_img = r['images'][0]
            update_image(return_img)
        else:
            update_images(r['images'][:-ignore_images])

        r_info = json.loads(r['info'])
        return_prompt = r_info['prompt']
        return_seed = r_info['seed']
        global display_caption
        display_caption = f"Sd Paint | Seed: {return_seed} | Prompt: {return_prompt}"
    else:
        osd(text=f"Error code returned: HTTP {response.status_code}")
    server_busy = False


def render():
    """
        Call the API to launch the rendering, if another rendering is not in progress.
    """
    global server_busy, instant_render

    if time.time() - last_draw_time < render_wait and not instant_render:
        time.sleep(0.25)
        render()
        return

    instant_render = False

    if not server_busy:
        server_busy = True

        if not img2img:
            payload_submit()
            t = threading.Thread(target=send_request)
            t.start()
            t = threading.Thread(target=progress_bar)
            t.start()
        else:
            t = threading.Thread(target=functools.partial(img2img_submit, True))
            t.start()


def get_angle(pos1, pos2):
    """
        Get the angle between two position.
    :param tuple[int]|list[int] pos1: First position.
    :param tuple[int]|list[int] pos2: Second position.
    :param bool deg: Get the angle as degrees, otherwise radians.
    :return: radians, degrees, cos, sin
    """

    dx = pos1[0] - pos2[0]
    dy = pos1[1] - pos2[1]
    rads = math.atan2(-dy, dx)
    rads %= 2 * math.pi

    return rads, math.degrees(rads), math.cos(rads), math.sin(rads)


def brush_stroke(pos):
    """
        Draw the brush stroke.
    :param tuple[int]|list[int] pos: The brush current position.
    """

    global prev_pos, prev_pos2

    if prev_pos is None or (abs(event.pos[0] - prev_pos[0]) < brush_size[button] // 4 and abs(event.pos[1] - prev_pos[1]) < brush_size[button] // 4):
        # Slow brush stroke, draw circles
        pygame.draw.circle(canvas, brush_colors[button], event.pos, brush_size[button])

    elif not prev_pos2 or brush_size[button] < 4:
        # Draw a simple polygon for small brush sizes
        pygame.draw.polygon(canvas, brush_colors[button], [prev_pos, event.pos], brush_size[button] * 2)

    else:
        # Draw a complex shape with gfxdraw for bigger bush sizes to avoid gaps
        angle_prev = get_angle(prev_pos, prev_pos2)
        angle = get_angle(event.pos, prev_pos)

        offset_pos_prev = [(brush_size[button] * angle_prev[3]), (brush_size[button] * angle_prev[2])]
        offset_pos = [(brush_size[button] * angle[3]), (brush_size[button] * angle[2])]
        pygame.gfxdraw.filled_polygon(canvas, [
            (prev_pos2[0] - offset_pos_prev[0], prev_pos2[1] - offset_pos_prev[1]),
            (prev_pos[0] - offset_pos[0], prev_pos[1] - offset_pos[1]),
            (event.pos[0] - offset_pos[0], event.pos[1] - offset_pos[1]),
            (event.pos[0] + offset_pos[0], event.pos[1] + offset_pos[1]),
            (prev_pos[0] + offset_pos[0], prev_pos[1] + offset_pos[1]),
            (prev_pos2[0] + offset_pos_prev[0], prev_pos2[1] + offset_pos_prev[1])
        ], brush_colors[button])

    prev_pos2 = prev_pos
    prev_pos = event.pos


def shift_down():
    return pygame.key.get_mods() & pygame.KMOD_SHIFT


def ctrl_down():
    return pygame.key.get_mods() & pygame.KMOD_CTRL


def alt_down():
    return pygame.key.get_mods() & pygame.KMOD_ALT


def controlnet_detect():
    """
        Call ControlNet active detector on the last rendered image, replace the canvas sketch by the detector result.
    """
    global last_detect_time, detector

    img = canvas.subsurface(pygame.Rect(0, 0, width, height)).copy()

    # Convert the Pygame surface to a PIL image
    pil_img = Image.frombytes('RGB', img.get_size(), pygame.image.tostring(img, 'RGB'))

    # Invert the colors of the PIL image
    pil_img = ImageOps.invert(pil_img)

    # Convert the PIL image back to a Pygame surface
    img = pygame.image.fromstring(pil_img.tobytes(), pil_img.size, pil_img.mode).convert_alpha()

    # Save the inverted image as base64-encoded data
    data = io.BytesIO()
    pygame.image.save(img, data)
    data = base64.b64encode(data.getvalue()).decode('utf-8')

    json_data = {
        "controlnet_module": detector,
        "controlnet_input_images": [data],
        "controlnet_processor_res": min(img.get_width(), img.get_height()),
        "controlnet_threshold_a": 64,
        "controlnet_threshold_b": 64
    }

    response = requests.post(url=f'{url}/controlnet/detect', json=json_data)
    if response.status_code == 200:
        r = response.json()
        return_img = r['images'][0]
        img_bytes = io.BytesIO(base64.b64decode(return_img))
        pil_img = Image.open(img_bytes)
        pil_img = ImageOps.invert(pil_img)
        pil_img = pil_img.convert('RGB')
        img_surface = pygame.image.fromstring(pil_img.tobytes(), pil_img.size, pil_img.mode)

        canvas.blit(img_surface, (width, 0))
    else:
        osd(text=f"Error code returned: HTTP {response.status_code}")


def display_configuration(wrap=True):
    """
        Display configuration on screen.
    :param bool wrap: Wrap long text.
    """

    fields = [
        '--Prompt',
        'prompt',
        'negative_prompt',
        'seed',
        '--Render',
        'settings.steps',
        'settings.cfg_scale',
        'hr_scale',
        'hr_upscaler',
        'denoising_strength',
        'clip_skip',
        '--ControlNet',
        'controlnet_model',
        'controlnet_weight',
        'controlnet_guidance_end',
        'pixel_perfect'
    ]

    if wrap and width < 800:
        wrap = 50
    elif wrap:
        wrap = 80

    text = ''

    for field in fields:
        if field == 'settings.steps' and quick_mode:
            field = 'settings.quick_steps'

        # Display separator
        if field.startswith('--'):
            text += '\n'+field[2:]+'\n'
            continue

        # Field value
        label = ''
        value = ''

        if '.' in field:
            field = field.split('.')
            var = globals().get(field[0], None)
            if var is None:
                continue

            if isinstance(var, dict) and var.get(field[1], None) is not None:
                label = field[1]
                value = var.get(field[1])
            elif (isinstance(var, list) or isinstance(var, tuple)) and field[1].isnumeric() and int(field[1]) < len(var):
                label = field[0]
                value = var[int(field[1])]
            elif getattr(var, field[1], None) is not None:
                label = field[1]
                value = getattr(var, field[1])
        else:
            if globals().get(field, None) is not None:
                label = field
                value = globals().get(field)

        if label and value is not None:
            value = str(value)
            label = label.replace('_', ' ')
            if label.endswith('prompt'):
                value = value.replace(', ', ',').replace(',', ', ')  # nicer prompt display

            # wrap text
            if wrap and len(value) > wrap:
                new_value = ''
                to_wrap = 0
                for i in range(len(value)):
                    if i % wrap == wrap - 1:
                        to_wrap = i

                    if to_wrap and value[i] in [' ', ')'] or (to_wrap and i - to_wrap > 5):  # try to wrap after space
                        new_value += value[i]+'\n::'
                        to_wrap = 0
                        continue

                    new_value += value[i]

                value = new_value

            text += f"    {label} :: {value}"

        text += '\n'

    osd(always_on=text.strip('\n'))


class TextDialog(simpledialog.Dialog):
    """
        Text input dialog.
    """

    def __init__(self, text, title, dialog_width=800, dialog_height=100):
        self.text = text
        self.dialog_width = dialog_width
        self.dialog_height = dialog_height
        super().__init__(None, title=title)

    def body(self, master):
        self.geometry(f'{self.dialog_width}x{self.dialog_height}')

        self.e1 = tk.Text(master)
        self.e1.insert("1.0", self.text)
        self.e1.pack(padx=0, pady=0, fill=tk.BOTH)

        self.attributes("-topmost", True)
        master.pack(fill=tk.BOTH, expand=True)

        return self.e1

    def apply(self):
        if "_"+self.e1.get("1.0", tk.INSERT)[-1:]+"_" == "_\n_":
            p = self.e1.get("1.0", tk.INSERT)[:-1] + self.e1.get(tk.INSERT, tk.END)  # remove new line inserted when validating the dialog with ENTER
        else:
            p = self.e1.get("1.0", tk.END)
        self.result = p.strip("\n")


# Initial img2img call
if img2img:
    t = threading.Thread(target=img2img_submit)
    t.start()

# Set up the main loop
running = True
need_redraw = True
while running:
    rendering = False

    # Handle events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.FINGERDOWN:
            # Handle brush stroke start and modifiers
            need_redraw = True
            last_draw_time = time.time()

            if event.type == pygame.FINGERDOWN:
                event.button = 1
                event.pos = finger_pos(event.x, event.y)

            brush_key = event.button
            if eraser_down:
                brush_key = 'e'

            if brush_key in brush_colors:
                brush_pos[brush_key] = event.pos
            elif event.button == 4:  # scroll up
                brush_size[1] = max(1, brush_size[1] + 1)
                brush_size[2] = max(1, brush_size[2] + 1)
                osd(text=f"Brush size {brush_size[1]}")

            elif event.button == 5:  # scroll down
                brush_size[1] = max(1, brush_size[1] - 1)
                brush_size[2] = max(1, brush_size[2] - 1)
                osd(text=f"Brush size {brush_size[1]}")

            if shift_down() and brush_pos[brush_key] is not None:
                if shift_pos is None:
                    shift_pos = brush_pos[brush_key]
                else:
                    pygame.draw.polygon(canvas, brush_colors[brush_key], [shift_pos, brush_pos[brush_key]], brush_size[brush_key] * 2)
                    shift_pos = brush_pos[brush_key]

        elif event.type == pygame.MOUSEBUTTONUP or event.type == pygame.FINGERUP:
            # Handle brush stoke end
            need_redraw = True
            rendering = True
            last_draw_time = time.time()

            if event.type == pygame.FINGERUP:
                event.button = 1
                event.pos = finger_pos(event.x, event.y)

            if event.button in brush_colors or eraser_down:
                brush_key = event.button
                if eraser_down:
                    brush_key = 'e'

                if brush_size[brush_key] >= 4 and getattr(event, 'pos', None) is not None:
                    pygame.draw.circle(canvas, brush_colors[brush_key], event.pos, brush_size[brush_key])

                brush_pos[brush_key] = None
                prev_pos = None
                brush_color = brush_colors[brush_key]

        elif event.type == pygame.MOUSEMOTION or event.type == pygame.FINGERMOTION:
            # Handle drawing brush strokes
            need_redraw = True

            if event.type == pygame.FINGERMOTION:
                event.pos = finger_pos(event.x, event.y)

            for button, pos in brush_pos.items():
                if pos is not None and button in brush_colors:
                    last_draw_time = time.time()
                    brush_stroke(pos)  # do the brush stroke

        elif event.type == pygame.KEYDOWN:
            # DBG key & modifiers
            # print(f"key down {event.key}, modifiers:")
            # print(f" shift:      {pygame.key.get_mods() & pygame.KMOD_SHIFT}")
            # print(f" ctrl:       {pygame.key.get_mods() & pygame.KMOD_CTRL}")
            # print(f" alt:        {pygame.key.get_mods() & pygame.KMOD_ALT}")

            # Handle keyboard shortcuts
            need_redraw = True
            last_draw_time = time.time()
            rendering = False

            event.button = 1
            if event.key == pygame.K_UP:
                rendering = True
                instant_render = True
                seed = seed + 1
                update_config(json_file, write=autosave_seed, values={'seed': seed})
                osd(text=f"Seed: {seed}")

            elif event.key == pygame.K_DOWN:
                rendering = True
                instant_render = True
                seed = seed - 1
                update_config(json_file, write=autosave_seed, values={'seed': seed})
                osd(text=f"Seed: {seed}")

            elif event.key == pygame.K_n:
                if ctrl_down():
                    dialog = TextDialog(seed, title="Seed", dialog_width=200, dialog_height=30)
                    if dialog.result and dialog.result.isnumeric():
                        osd(text=f"Seed: {dialog.result}")
                        seed = int(dialog.result)
                        update_config(json_file, write=autosave_seed, values={'seed': seed})
                        rendering = True
                        instant_render = True
                else:
                    rendering = True
                    instant_render = True
                    seed = new_random_seed()
                    update_config(json_file, write=autosave_seed, values={'seed': seed})
                    osd(text=f"Seed: {seed}")

            elif event.key == pygame.K_c:
                if shift_down():
                    rendering_key = True
                    clip_skip -= 1
                    clip_skip = (clip_skip + 1) % 2
                    clip_skip += 1
                    osd(text=f"CLIP skip: {clip_skip}")
                else:
                    display_configuration()

            elif event.key == pygame.K_m and controlnet_model:
                if shift_down():
                    rendering_key = True
                    controlnet_model = controlnet_models[(controlnet_models.index(controlnet_model) + 1) % len(controlnet_models)]
                    osd(text=f"ControlNet model: {controlnet_model}")

            elif event.key == pygame.K_h:
                if shift_down():
                    rendering_key = True
                    hr_scale = hr_scales[(hr_scales.index(hr_scale)+1) % len(hr_scales)]
                else:
                    rendering = True
                    if hr_scale != 1.0:
                        hr_scale_prev = hr_scale
                        hr_scale = 1.0
                    else:
                        hr_scale = hr_scale_prev

                if hr_scale == 1.0:
                    osd(text="HR scale: off")
                else:
                    osd(text=f"HR scale: {hr_scale}")

                update_size(hr_scale=hr_scale)

            elif event.key in (pygame.K_KP_ENTER, pygame.K_RETURN):
                rendering = True
                instant_render = True
                osd(text=f"Rendering")

            elif event.key == pygame.K_q:
                rendering = True
                instant_render = True
                quick_mode = not quick_mode
                if quick_mode:
                    osd(text=f"Quick render: on")
                    hr_scale_prev = hr_scale
                    hr_scale = 1.0
                else:
                    osd(text=f"Quick render: off")
                    hr_scale = hr_scale_prev

                update_size(hr_scale=hr_scale)

            elif event.key == pygame.K_o:
                if ctrl_down():
                    rendering = True
                    instant_render = True
                    load_file_dialog()

            elif event.key in (pygame.K_KP0, pygame.K_KP1, pygame.K_KP2, pygame.K_KP3, pygame.K_KP4,
                               pygame.K_KP5, pygame.K_KP6, pygame.K_KP7, pygame.K_KP8, pygame.K_KP9):
                keymap = {
                    pygame.K_KP0:   0,
                    pygame.K_KP1:   1,
                    pygame.K_KP2:   2,
                    pygame.K_KP3:   3,
                    pygame.K_KP4:   4,
                    pygame.K_KP5:   5,
                    pygame.K_KP6:   6,
                    pygame.K_KP7:   7,
                    pygame.K_KP8:   8,
                    pygame.K_KP9:   9
                }

                if ctrl_down():
                    if event.key != pygame.K_KP0:
                        save_preset('controlnet' if alt_down() else 'render', keymap.get(event.key))
                else:
                    rendering = True
                    instant_render = True

                    if event.key == pygame.K_KP0:
                        # Reset both render & controlnet settings if keypad 0
                        load_preset('render', keymap.get(event.key))
                        load_preset('controlnet', keymap.get(event.key))
                    else:
                        load_preset('controlnet' if alt_down() else 'render', keymap.get(event.key))

            elif event.key == pygame.K_p:
                if ctrl_down():
                    pause_render = not pause_render

                    if pause_render:
                        osd(text=f"On-demand rendering (ENTER to render)")

                    else:
                        rendering = True
                        instant_render = True
                        osd(text=f"Dynamic rendering")
                elif alt_down():
                    dialog = TextDialog(negative_prompt, title="Negative prompt")
                    if dialog.result:
                        osd(text=f"New negative prompt: {dialog.result}")
                        negative_prompt = dialog.result
                        update_config(json_file, write=autosave_negative_prompt, values={'negative_prompt': negative_prompt})
                        rendering = True
                        instant_render = True
                else:
                    dialog = TextDialog(prompt, title="Prompt")
                    if dialog.result:
                        osd(text=f"New prompt: {dialog.result}")
                        prompt = dialog.result
                        update_config(json_file, write=autosave_prompt, values={'prompt': prompt})
                        rendering = True
                        instant_render = True

            elif event.key == pygame.K_BACKSPACE:
                pygame.draw.rect(canvas, (255, 255, 255), (width, 0, width, height))

            elif event.key == pygame.K_s:
                if ctrl_down():
                    save_file_dialog()
                elif shift_down():
                    rendering_key = True
                    sampler = samplers[(samplers.index(sampler) + 1) % len(samplers)]
                    osd(text=f"Sampler: {sampler}")

            elif event.key == pygame.K_e:
                eraser_down = True

            elif event.key == pygame.K_t:
                if shift_down():
                    if render_wait == 2.0:
                        render_wait = 0.0
                        osd(text="Render wait: off")
                    else:
                        render_wait += 0.5
                        osd(text=f"Render wait: {render_wait}s")

            elif event.key == pygame.K_u:
                if shift_down():
                    rendering_key = True
                    hr_upscaler = hr_upscalers[(hr_upscalers.index(hr_upscaler) + 1) % len(hr_upscalers)]
                    osd(text=f"HR upscaler: {hr_upscaler}")

            elif event.key == pygame.K_b:
                if shift_down():
                    rendering_key = True
                    batch_size = batch_sizes[(batch_sizes.index(batch_size) + 1) % len(batch_sizes)]
                else:
                    rendering = True
                    if batch_size != 1:
                        batch_size_prev = batch_size
                        batch_size = 1
                    else:
                        batch_size = batch_size_prev

                if batch_size == 1:
                    hr_scale = batch_hr_scale_prev
                    update_size()
                    osd(text=f"Batch rendering: off")
                else:
                    batch_hr_scale_prev = hr_scale
                    hr_scale = 1.0
                    update_size()
                    osd(text=f"Batch rendering size: {batch_size}")

            elif event.key == pygame.K_w:
                if shift_down():
                    rendering_key = True
                    controlnet_weight = controlnet_weights[(controlnet_weights.index(controlnet_weight) + 1) % len(controlnet_weights)]
                    osd(text=f"ControlNet weight: {controlnet_weight}")

            elif event.key == pygame.K_g:
                if shift_down() and ctrl_down():
                    rendering_key = True
                    pixel_perfect = not pixel_perfect
                    osd(text=f"ControlNet pixel perfect mode: {'on' if pixel_perfect else 'off'}")
                elif shift_down():
                    rendering_key = True
                    controlnet_guidance_end = controlnet_guidance_ends[(controlnet_guidance_ends.index(controlnet_guidance_end) + 1) % len(controlnet_guidance_ends)]
                    osd(text=f"ControlNet guidance end: {controlnet_guidance_end}")

            elif event.key == pygame.K_d:
                if shift_down():
                    rendering_key = True
                    denoising_strength = denoising_strengths[(denoising_strengths.index(denoising_strength) + 1) % len(denoising_strengths)]
                    if img2img:
                        osd(text=f"Denoising: {denoising_strength}")
                    else:
                        osd(text=f"HR denoising: {denoising_strength}")
                elif ctrl_down():
                    osd(text=f"Detect {detector}")

                    t = threading.Thread(target=controlnet_detect())
                    t.start()

                    # select next detector
                    detector = detectors[(detectors.index(detector)+1) % len(detectors)]

            elif event.key == pygame.K_f:
                fullscreen = not fullscreen
                if fullscreen:
                    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                else:
                    screen = pygame.display.set_mode((width*2, height))

            elif event.key in (pygame.K_ESCAPE, pygame.K_x):
                running = False
                pygame.quit()
                exit(0)

        elif event.type == pygame.KEYUP:
            # Handle special keys release
            if event.key == pygame.K_e:
                eraser_down = False
                brush_pos['e'] = None

            elif event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                if rendering_key:
                    rendering = True
                    rendering_key = False
                shift_pos = None

            elif event.key in (pygame.K_c,):
                # Remove OSD always-on text
                need_redraw = True
                osd(always_on=None)

    # Call image render
    if (rendering and not pause_render) or instant_render:
        t = threading.Thread(target=render)
        t.start()

    # Draw the canvas and brushes on the screen
    screen.blit(canvas, (0, 0))

    # Create a new surface with a circle
    cursor_size = brush_size[1]*2
    cursor_surface = pygame.Surface((cursor_size, cursor_size), pygame.SRCALPHA)
    pygame.draw.circle(cursor_surface, cursor_color, (cursor_size // 2, cursor_size // 2), cursor_size // 2)

    # Blit the cursor surface onto the screen surface at the position of the mouse
    mouse_pos = pygame.mouse.get_pos()
    screen.blit(cursor_surface, (mouse_pos[0] - cursor_size // 2, mouse_pos[1] - cursor_size // 2))

    # Handle OSD
    osd()

    # Update the display
    if need_redraw:
        pygame.display.flip()
        pygame.display.set_caption(display_caption)
        need_redraw = False

    # Set max FPS
    clock.tick(120)

# Clean up Pygame
pygame.quit()
