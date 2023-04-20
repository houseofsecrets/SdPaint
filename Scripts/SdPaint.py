import os
import random
import sys

import pygame
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

# setup sd inputs
url = "http://127.0.0.1:7860"

ACCEPTED_FILE_TYPES = ["png", "jpg", "jpeg", "bmp"]
ACCEPTED_KEYDOWN_EVENTS = (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_UP,
                pygame.K_DOWN, pygame.K_n, pygame.K_l, pygame.K_m,
                pygame.K_o,)
img2img = None
img2img_waiting = False
img2img_time_prev = None
main_json_data = None
if __name__ == '__main__':
    argParser = argparse.ArgumentParser()
    argParser.add_argument("--img2img", help="img2img source file")

    args = argParser.parse_args()

    img2img = args.img2img


def update_size():
    global width, height, soft_upscale

    interface_width = settings.get('interface_width', width * (1 if img2img else 2))
    interface_height = settings.get('interface_height', height)

    if round(interface_width / interface_height * 100) != round(width * (1 if img2img else 2) / height * 100):
        ratio = width / height
        if ratio < 1:
            interface_width = math.floor(interface_height * ratio)
        else:
            interface_height = math.floor(interface_width * ratio)

    soft_upscale = 1.0
    if interface_width != width * (1 if img2img else 2) or interface_height != height:
        soft_upscale = min(settings['interface_width'] / width, settings['interface_height'] / height)

    if settings.get('enable_hr', 'false') == 'true':
        soft_upscale = soft_upscale / settings['hr_scale']
        width = math.floor(width * settings['hr_scale'])
        height = math.floor(height * settings['hr_scale'])

    width = math.floor(width * soft_upscale)
    height = math.floor(height * soft_upscale)


# read settings from payload
json_file = "payload.json"
if img2img:
    json_file = "img2img.json"

with open(json_file, "r") as f:
    settings = json.load(f)

    prompt = settings.get('prompt', 'A painting by Monet')
    seed = settings.get('seed', 3456456767)
    width = settings.get('width', 512)
    height = settings.get('height', 512)
    soft_upscale = 1.0
    controlnet_models: list[str] = settings.get("controlnet_models", [])
    if settings.get("controlnet_units", None):
        controlnet_model = settings.get("controlnet_units")[0]["model"]
    else:
        controlnet_model = None
    update_size()

if img2img:
    img2img_time = os.path.getmtime(img2img)

    with Image.open(img2img, mode='r') as im:
        width = im.width
        height = im.height
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
brush_size = {1: 2, 2: 10, 'e': 10}
brush_colors = {
    1: (0, 0, 0),  # Left mouse button color
    2: (255, 255, 255),  # Middle mouse button color
    'e': (255, 255, 255),  # Eraser color
}
brush_pos = {1: None, 2: None, 'e': None}
prev_pos = None
shift_down = False
shift_pos = None
eraser_down = False
render_wait = 0.5  # wait time max between 2 draw before launching the render
last_draw_time = time.time()

# Define the cursor size and color
cursor_size = 1
cursor_color = (0, 0, 0)

# Set up flag to check if server is busy or not
server_busy = False
progress = 0.0

def load_filepath_into_canvas(file_path):
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
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.askopenfilename()
    if not file_path:
        return
    # windows only solution to get extention path
    extention = file_path.split(".")[-1].lower()
    if extention in ACCEPTED_FILE_TYPES:
        load_filepath_into_canvas(file_path)

def update_image(image_data):
    # Decode base64 image data
    img_bytes = io.BytesIO(base64.b64decode(image_data))
    img_surface = pygame.image.load(img_bytes)
    if soft_upscale != 1.0:
        img_surface = pygame.transform.smoothscale(img_surface, (img_surface.get_width() * soft_upscale, img_surface.get_height() * soft_upscale))

    canvas.blit(img_surface, (0, 0))
    global need_redraw
    need_redraw = True

def upload_image_path(file_path):
    with open(file_path, "rb") as f:
        data = f.read()
    data = base64.b64encode(data).decode('utf-8')
    with open("payload.json", "r") as f:
        payload = json.load(f)
    payload['controlnet_units'][0]['input_image'] = data
    response = requests.post(url=f'{url}/controlnet/txt2img', json=payload)
    r = response.json()
    return_img = r['images'][0]
    update_image(return_img)

def new_random_seed_for_payload():
    global seed
    seed = random.randint(0, 2**32-1)
    json_path = "payload.json"
    if img2img:
        json_path = "img2img.json"
    with open(json_path, "r") as f:
        payload = json.load(f)
    # write the seed to the selected payload
    payload['seed'] = seed
    with open(json_path, "w") as f:
        json.dump(payload, f, indent=4)
    return payload

def img2img_submit(force=False):
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

        server_busy = True

        t = threading.Thread(target=progress_bar)
        t.start()

        response = requests.post(url=f'{url}/controlnet/img2img', json=json_data)
        if response.status_code == 200:
            r = response.json()
            return_img = r['images'][0]
            update_image(return_img)
        else:
            print(f"Error code returned: HTTP {response.status_code}")

        server_busy = False

    if not img2img_waiting and running:
        img2img_waiting = True
        time.sleep(1.0)
        img2img_submit()


def progress_request():
    json_data = {}
    response = requests.post(url=f'{url}/internal/progress', json=json_data)
    if response.status_code == 200:
        r = response.json()
        return r
    else:
        print(f"Error code returned: HTTP {response.status_code}")
        return {}


def progress_bar():
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


osd_text = None
osd_text_display_start = None


def osd(**kwargs):
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

    json_data['controlnet_units'][0]['input_image'] = data
    json_data['controlnet_units'][0]['model'] = controlnet_model
    json_data['hr_second_pass_steps'] = math.floor(json_data['steps'] * json_data['denoising_strength'])

    json_data['seed'] = seed
    main_json_data = json_data

def send_request():
    global server_busy
    response = requests.post(url=f'{url}/controlnet/{"img2img" if img2img else "txt2img"}', json=main_json_data)
    if response.status_code == 200:
        r = response.json()
        return_img = r['images'][0]
        update_image(return_img)
    else:
        print(f"Error code returned: HTTP {response.status_code}")
    server_busy = False

def render():
    """
        Call the API to launch the rendering, if another rendering is not in progress.
    """
    global server_busy

    if time.time() - last_draw_time < render_wait:
        time.sleep(0.25)
        render()
        return

    if not server_busy:
        server_busy = True

        if not img2img:
            payload_submit()
            t = threading.Thread(target=send_request)
            t.start()
            t = threading.Thread(target=progress_bar)
            t.start()
        else:
            img2img_submit(True)
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
            elif event.button == 5:  # scroll down
                brush_size[1] = max(1, brush_size[1] - 1)

            if shift_down and brush_pos[brush_key] is not None:
                if shift_pos is None:
                    shift_pos = brush_pos[brush_key]
                else:
                    pygame.draw.polygon(canvas, brush_colors[brush_key], [shift_pos, brush_pos[brush_key]], brush_size[brush_key] * 2)
                    shift_pos = brush_pos[brush_key]

        elif event.type == pygame.MOUSEBUTTONUP or event.type == pygame.FINGERUP \
            or (event.type == pygame.KEYDOWN and event.key in ACCEPTED_KEYDOWN_EVENTS):
            need_redraw = True
            last_draw_time = time.time()

            if event.type == pygame.KEYDOWN:
                event.button = 1
                if event.key == pygame.K_UP:
                    seed = seed + 1
                    osd(text=f"Seed: {seed}")
                elif event.key == pygame.K_DOWN:
                    seed = seed - 1
                    osd(text=f"Seed: {seed}")
                elif event.key == pygame.K_n:
                    new_random_seed_for_payload()
                    osd(text=f"Seed: {seed}")
                elif event.key == pygame.K_l and controlnet_model:
                    controlnet_model = controlnet_models[(controlnet_models.index(controlnet_model) - 1) % len(controlnet_models)]
                    osd(text=f"ControlNet model: {controlnet_model}")
                elif event.key == pygame.K_m and controlnet_model:
                    controlnet_model = controlnet_models[(controlnet_models.index(controlnet_model) + 1) % len(controlnet_models)]
                    osd(text=f"ControlNet model: {controlnet_model}")
                elif event.key in (pygame.K_KP_ENTER, pygame.K_RETURN):
                    osd(text=f"Rendering")
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

                brush_pos[brush_key] = None
                prev_pos = None
                brush_color = brush_colors[brush_key]

                # Call image render
                t = threading.Thread(target=render)
                t.start()

        elif event.type == pygame.MOUSEMOTION or event.type == pygame.FINGERMOTION:
            need_redraw = True

            if event.type == pygame.FINGERMOTION:
                event.pos = finger_pos(event.x, event.y)

            for button, pos in brush_pos.items():
                if pos is not None and button in brush_colors:
                    last_draw_time = time.time()

                    if prev_pos is None or (abs(event.pos[0] - prev_pos[0]) < brush_size[button] // 4 and abs(event.pos[1] - prev_pos[1]) < brush_size[button] // 4):
                        pygame.draw.circle(canvas, brush_colors[button], event.pos, brush_size[button])
                        prev_pos = None
                    else:
                        pygame.draw.polygon(canvas, brush_colors[button], [prev_pos, event.pos], brush_size[button] * 2)
                        # pygame.draw.line(canvas, brush_colors[button], prev_pos, event.pos, brush_size[button] * 2)

                    prev_pos = event.pos

        elif event.type == pygame.KEYDOWN:
            need_redraw = True

            if event.key == pygame.K_BACKSPACE:
                pygame.draw.rect(canvas, (255, 255, 255), (width, 0, width, height))
            elif event.key == pygame.K_s:
                save_file_dialog()
            elif event.key == pygame.K_e:
                eraser_down = True
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

    # for button, pos in brush_pos.items():
    #     if pos is not None and button in brush_colors:
    #         pygame.draw.circle(screen, brush_colors[button], pos, brush_size[button])

    # Update the display
    if need_redraw:
        pygame.display.flip()
        need_redraw = False

    # Set max FPS
    clock.tick(120)

# Clean up Pygame
pygame.quit()
