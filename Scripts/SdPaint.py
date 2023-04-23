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
from tkinter import filedialog
import argparse

# Initialize Pygame
pygame.init()
clock = pygame.time.Clock()

# Read JSON main configuration file
config_file = "config.json"
if not os.path.exists(config_file):
    shutil.copy(f"{config_file}-dist", config_file)

with open(config_file, "r") as f:
    config = json.load(f)

# Setup
url = config.get('url', 'http://127.0.0.1:7860')

ACCEPTED_FILE_TYPES = ["png", "jpg", "jpeg", "bmp"]
ACCEPTED_KEYDOWN_EVENTS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_UP,
                           pygame.K_DOWN, pygame.K_n, pygame.K_m,
                           pygame.K_o, pygame.K_h, pygame.K_q)

# Global variables
img2img = None
img2img_waiting = False
img2img_time_prev = None
hr_scale = 1.0
hr_scale_prev = 1.0
hr_scales = [1.0, 1.25, 1.5, 2.0]
main_json_data = None
quick_mode = False
server_busy = False
instant_render = False
progress = 0.0
controlnet_models: list[str] = config.get("controlnet_models", [])
detectors = config.get('detectors', ('lineart',))
detector = detectors[0]
last_detect_time = time.time()
osd_text = None
osd_text_display_start = None


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

    if settings.get('enable_hr', 'false') == 'true':
        if kwargs.get('hr_scale', None) is not None:
            hr_scale = kwargs.get('hr_scale')
        else:
            hr_scale = settings.get('hr_scale', 1.0)
        soft_upscale = soft_upscale / hr_scale
        width = math.floor(init_width * hr_scale)
        height = math.floor(init_height * hr_scale)
    else:
        width = init_width * 1.0
        height = init_height * 1.0
        hr_scale = 1.0

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

if not os.path.exists(json_file):
    shutil.copy(f"{json_file}-dist", json_file)

with open(json_file, "r") as f:
    settings = json.load(f)

    prompt = settings.get('prompt', 'A painting by Monet')
    seed = settings.get('seed', 3456456767)
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
pygame.display.set_caption("Sd Paint")

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
shift_down = False
shift_pos = None
eraser_down = False
render_wait = 0.5 if not img2img else 0.0  # wait time max between 2 draw before launching the render
last_draw_time = time.time()

# Define the cursor size and color
cursor_size = 1
cursor_color = (0, 0, 0)


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

    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.asksaveasfilename(defaultextension=".png")
    saveimg = canvas.subsurface(pygame.Rect(0, 0, width, height)).copy()
    if soft_upscale != 1.0:
        saveimg = pygame.transform.smoothscale(saveimg, (saveimg.get_width() // soft_upscale, saveimg.get_height() // soft_upscale))
    if file_path:
        pygame.image.save(saveimg, file_path)
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

    # Decode base64 image data
    img_bytes = io.BytesIO(base64.b64decode(image_data))
    img_surface = pygame.image.load(img_bytes)
    if soft_upscale != 1.0:
        img_surface = pygame.transform.smoothscale(img_surface, (img_surface.get_width() * soft_upscale, img_surface.get_height() * soft_upscale))

    canvas.blit(img_surface, (0, 0))
    global need_redraw
    need_redraw = True


def new_random_seed_for_payload():
    """
        Set the seed to a new random number, save the relevant JSON configuration file (creating a local copy if needed).

    :return: The JSON payload content.
    """

    global seed, json_file
    seed = random.randint(0, 2**32-1)
    with open(json_file, "r") as f:
        payload = json.load(f)
    # write the seed to the selected payload
    payload['seed'] = seed

    if json_file.endswith("-dist"):
        json_file = json_file[:-5]

    with open(json_file, "w") as f:
        json.dump(payload, f, indent=4)
    return payload


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

        if quick_mode:
            json_data['steps'] = json_data.get('quick_steps', json_data['steps'] // 2)  # use quick_steps setting, or halve steps if not set

        server_busy = True

        t = threading.Thread(target=progress_bar)
        t.start()

        response = requests.post(url=f'{url}/controlnet/img2img', json=json_data)
        if response.status_code == 200:
            r = response.json()
            return_img = r['images'][0]
            update_image(return_img)
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

    json_data = {}
    response = requests.post(url=f'{url}/internal/progress', json=json_data)
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

    osd_text_pos = (width*(1 if img2img else 2) - width + osd_margin, osd_margin)  # bottom left of canvas
    # osd_text_pos = (width*(1 if img2img else 2) - width + osd_margin, height - osd_size[1] - osd_margin)  # bottom left of canvas
    osd_text_offset = 0

    global progress, need_redraw

    progress = kwargs.get('progress', progress)
    text = kwargs.get('text', osd_text)
    text_time = kwargs.get('text_time', 2.0)
    need_redraw = kwargs.get('need_redraw', need_redraw)

    if progress is not None and progress > 0.0:
        need_redraw = True

        # progress bar
        progress_surface = pygame.Surface(osd_size, pygame.SRCALPHA)
        pygame.draw.rect(progress_surface, (0, 0, 0), pygame.Rect(2, 2, math.floor(osd_size[0] * progress), osd_size[1]))
        pygame.draw.rect(progress_surface, (0, 200, 160), pygame.Rect(0, 0, math.floor(osd_size[0] * progress), osd_size[1] - 2))

        screen.blit(progress_surface, pygame.Rect(osd_progress_pos[0], osd_progress_pos[1], osd_size[0], osd_size[1]))

        # progress text
        text_surface = font.render(f"{progress*100:.0f}%", True, (0, 0, 0))
        screen.blit(text_surface, pygame.Rect(osd_size[0] - osd_margin + osd_progress_pos[0]+1 - text_surface.get_width(), 3 + osd_progress_pos[1]+1, osd_size[0], osd_size[1]))
        screen.blit(text_surface, pygame.Rect(osd_size[0] - osd_margin + osd_progress_pos[0]+1 - text_surface.get_width(), 3 + osd_progress_pos[1]-1, osd_size[0], osd_size[1]))
        screen.blit(text_surface, pygame.Rect(osd_size[0] - osd_margin + osd_progress_pos[0]-1 - text_surface.get_width(), 3 + osd_progress_pos[1]+1, osd_size[0], osd_size[1]))
        screen.blit(text_surface, pygame.Rect(osd_size[0] - osd_margin + osd_progress_pos[0]-1 - text_surface.get_width(), 3 + osd_progress_pos[1]-1, osd_size[0], osd_size[1]))
        text_surface = font.render(f"{progress*100:.0f}%", True, (255, 255, 255))
        screen.blit(text_surface, pygame.Rect(osd_size[0] - osd_margin + osd_progress_pos[0] - text_surface.get_width(), 3 + osd_progress_pos[1], osd_size[0], osd_size[1]))

        osd_text_offset = osd_size[1] + osd_margin

    if text:
        # OSD text
        if osd_text_display_start is None or text != osd_text:
            osd_text_display_start = time.time()
        osd_text = text

        need_redraw = True
        text_surface = font.render(text, True, (0, 0, 0))
        screen.blit(text_surface, pygame.Rect(osd_text_pos[0]+1, osd_text_pos[1]+1 + osd_text_offset, osd_size[0], osd_size[1]))
        screen.blit(text_surface, pygame.Rect(osd_text_pos[0]+1, osd_text_pos[1]-1 + osd_text_offset, osd_size[0], osd_size[1]))
        screen.blit(text_surface, pygame.Rect(osd_text_pos[0]-1, osd_text_pos[1]+1 + osd_text_offset, osd_size[0], osd_size[1]))
        screen.blit(text_surface, pygame.Rect(osd_text_pos[0]-1, osd_text_pos[1]-1 + osd_text_offset, osd_size[0], osd_size[1]))
        text_surface = font.render(text, True, (255, 255, 255))
        screen.blit(text_surface, pygame.Rect(osd_text_pos[0], osd_text_pos[1] + osd_text_offset, osd_size[0], osd_size[1]))

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
    json_data['hr_second_pass_steps'] = max(8, math.floor(json_data['steps'] * json_data['denoising_strength']))  # at least 8 steps

    if hr_scale > 1.0:
        json_data['enable_hr'] = 'true'
    else:
        json_data['enable_hr'] = 'false'

    json_data['seed'] = seed
    json_data['hr_scale'] = hr_scale

    main_json_data = json_data


def send_request():
    """
        Send the API request.

        Use ``main_json_data`` variable.
    """

    global server_busy
    response = requests.post(url=f'{url}/controlnet/{"img2img" if img2img else "txt2img"}', json=main_json_data)
    if response.status_code == 200:
        r = response.json()
        return_img = r['images'][0]
        update_image(return_img)
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


# Initial img2img call
if img2img:
    t = threading.Thread(target=img2img_submit)
    t.start()

# Set up the main loop
running = True
need_redraw = True
while running:
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

            if shift_down and brush_pos[brush_key] is not None:
                if shift_pos is None:
                    shift_pos = brush_pos[brush_key]
                else:
                    pygame.draw.polygon(canvas, brush_colors[brush_key], [shift_pos, brush_pos[brush_key]], brush_size[brush_key] * 2)
                    shift_pos = brush_pos[brush_key]

        elif event.type == pygame.MOUSEBUTTONUP or event.type == pygame.FINGERUP \
            or (event.type == pygame.KEYDOWN and event.key in ACCEPTED_KEYDOWN_EVENTS):
            # Handle brush stoke end, and rendering
            need_redraw = True
            last_draw_time = time.time()

            # Handle keyboard rendering shortcuts
            if event.type == pygame.KEYDOWN:
                event.button = 1
                if event.key == pygame.K_UP:
                    instant_render = True
                    seed = seed + 1
                    osd(text=f"Seed: {seed}")

                elif event.key == pygame.K_DOWN:
                    instant_render = True
                    seed = seed - 1
                    osd(text=f"Seed: {seed}")

                elif event.key == pygame.K_n:
                    instant_render = True
                    new_random_seed_for_payload()
                    osd(text=f"Seed: {seed}")

                elif event.key == pygame.K_m and controlnet_model:
                    controlnet_model = controlnet_models[(controlnet_models.index(controlnet_model) + 1) % len(controlnet_models)]
                    osd(text=f"ControlNet model: {controlnet_model}")

                elif event.key == pygame.K_h:
                    hr_scale = hr_scales[(hr_scales.index(hr_scale)+1) % len(hr_scales)]

                    if hr_scale == 1.0:
                        osd(text="HR scale: off")
                    else:
                        osd(text=f"HR scale: {hr_scale}")

                    update_size(hr_scale=hr_scale)

                elif event.key in (pygame.K_KP_ENTER, pygame.K_RETURN):
                    instant_render = True
                    osd(text=f"Rendering")

                elif event.key == pygame.K_q:
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
                    load_file_dialog()
                    continue

            elif event.type == pygame.FINGERUP:
                event.button = 1
                event.pos = finger_pos(event.x, event.y)

            if event.button in brush_colors or eraser_down:
                brush_key = event.button
                if eraser_down:
                    brush_key = 'e'

                if brush_size[brush_key] >= 4:
                    pygame.draw.circle(canvas, brush_colors[brush_key], event.pos, brush_size[brush_key])

                brush_pos[brush_key] = None
                prev_pos = None
                brush_color = brush_colors[brush_key]

                # Call image render
                t = threading.Thread(target=render)
                t.start()

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
            need_redraw = True

            # Handle keyboard shortcuts
            if event.key == pygame.K_BACKSPACE:
                pygame.draw.rect(canvas, (255, 255, 255), (width, 0, width, height))

            elif event.key == pygame.K_s:
                save_file_dialog()

            elif event.key == pygame.K_e:
                eraser_down = True

            elif event.key == pygame.K_d:
                osd(text=f"Detect {detector}")

                t = threading.Thread(target=controlnet_detect())
                t.start()

                # select next detector
                detector = detectors[(detectors.index(detector)+1) % len(detectors)]

            elif event.key == pygame.K_t:
                if render_wait == 2.0:
                    render_wait = 0.0
                    osd(text="Render wait: off")
                else:
                    render_wait += 0.5
                    osd(text=f"Render wait: {render_wait}s")

            elif event.key == pygame.K_f:
                fullscreen = not fullscreen
                if fullscreen:
                    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                else:
                    screen = pygame.display.set_mode((width*2, height))

            elif event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                shift_down = True

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
                shift_down = False
                shift_pos = None

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
        need_redraw = False

    # Set max FPS
    clock.tick(120)

# Clean up Pygame
pygame.quit()
