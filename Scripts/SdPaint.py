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
import tkinter as tk
from tkinter import filedialog
import os
import random

# Initialize Pygame
pygame.init()
clock = pygame.time.Clock()

# setup sd inputs
url = "http://127.0.0.1:7860"


def update_size():
    global width, height, soft_upscale

    interface_width = settings.get('interface_width', width * 2)
    interface_height = settings.get('interface_height', height)

    if round(interface_width / interface_height * 100) != round(width * 2 / height * 100):
        ratio = width / height
        print(f"different ratios{interface_width / interface_height} != {width * 2 / height}")
        if ratio < 1:
            interface_width = math.floor(interface_height * ratio)
        else:
            interface_height = math.floor(interface_width * ratio)

    soft_upscale = 1.0
    if interface_width != width * 2 or interface_height != height:
        soft_upscale = min(settings['interface_width'] / width, settings['interface_height'] / height)

    if settings['enable_hr'] == 'true':
        soft_upscale = soft_upscale / settings['hr_scale']
        width = math.floor(width * settings['hr_scale'])
        height = math.floor(height * settings['hr_scale'])

    width = math.floor(width * soft_upscale)
    height = math.floor(height * soft_upscale)


# read settings from payload
with open("payload.json", "r") as f:
    settings = json.load(f)

    prompt = settings.get('prompt', 'A painting by Monet')
    seed = settings.get('seed', 3456456767)
    width = settings.get('width', 512)
    height = settings.get('height', 512)
    soft_upscale = 1.0
    update_size()

# Set up the display
fullscreen = False
screen = pygame.display.set_mode((width*2, height))
pygame.display.set_caption("Sd Paint")

# Setup text
font = pygame.font.SysFont(None, 24)
text_input = ""
# Set up the drawing surface
canvas = pygame.Surface((width*2, height))
pygame.draw.rect(canvas, (255, 255, 255), (0, 0, width*2, height))

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

# Define the cursor size and color
cursor_size = 1
cursor_color = (0, 0, 0)

# Set up flag to check if server is busy or not
server_busy = False


def finger_pos(finger_x, finger_y):
    x = round(min(max(finger_x, 0), 1) * width * 2)
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


def update_image(image_data):
    # Decode base64 image data
    img_bytes = io.BytesIO(base64.b64decode(image_data))
    img_surface = pygame.image.load(img_bytes)
    if soft_upscale != 1.0:
        img_surface = pygame.transform.smoothscale(img_surface, (img_surface.get_width() * soft_upscale, img_surface.get_height() * soft_upscale))

    canvas.blit(img_surface, (0, 0))
    global need_redraw
    need_redraw = True

def new_random_seed_for_payload(seed=None):
    with open("payload.json", "r") as f:
        payload = json.load(f)
    if seed is None:
        seed = random.randint(0, 1000000000)
    payload['seed'] = seed
    # write
    with open("payload.json", "w") as f:
        json.dump(payload, f, indent=4)
    return payload

# Set up the main loop
running = True
need_redraw = True
while running:
    # Handle events
    for event in pygame.event.get():
        need_redraw = True

        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.FINGERDOWN:
            if event.type == pygame.FINGERDOWN:
                event.button = 1
                event.pos = finger_pos(event.x, event.y)

            brush_key = event.button
            if eraser_down:
                brush_key = 'e'

            if shift_down and brush_pos[brush_key] is not None:
                if shift_pos is None:
                    shift_pos = brush_pos[brush_key]
                else:
                    pygame.draw.polygon(canvas, brush_colors[brush_key], [shift_pos, brush_pos[brush_key]], brush_size[brush_key] * 2)
                    shift_pos = brush_pos[brush_key]

            if brush_key in brush_colors:
                brush_pos[brush_key] = event.pos
            elif event.button == 4:  # scroll up
                brush_size[1] = max(1, brush_size[1] + 1)
            elif event.button == 5:  # scroll down
                brush_size[1] = max(1, brush_size[1] - 1)

        elif event.type == pygame.MOUSEBUTTONUP or event.type == pygame.FINGERUP \
                or (event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_UP, pygame.K_DOWN, pygame.K_n)):
            if event.type == pygame.KEYDOWN:
                event.button = 1

                if event.key == pygame.K_UP:
                    seed = seed + 1
                elif event.key == pygame.K_DOWN:
                    seed = seed - 1
                elif event.key == pygame.K_n:
                    seed = round(random.random() * sys.maxsize)
                    new_random_seed_for_payload(seed)

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
                # Check if server is busy before sending request
                if not server_busy:
                    server_busy = True
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
                    with open("payload.json", "r") as f:
                        payload = json.load(f)

                    payload['controlnet_units'][0]['input_image'] = data
                    payload['hr_second_pass_steps'] = math.floor(payload['steps'] * payload['denoising_strength'])
                    payload['seed'] = seed

                    def send_request():
                        global server_busy
                        response = requests.post(url=f'{url}/controlnet/txt2img', json=payload)
                        if response.status_code == 200:
                            r = response.json()
                            return_img = r['images'][0]
                            update_image(return_img)
                        else:
                            print(f"Error code returned: HTTP {response.status_code}")

                        server_busy = False

                    t = threading.Thread(target=send_request)
                    t.start()

        elif event.type == pygame.MOUSEMOTION or event.type == pygame.FINGERMOTION:
            if event.type == pygame.FINGERMOTION:
                event.pos = finger_pos(event.x, event.y)

            for button, pos in brush_pos.items():
                if pos is not None and button in brush_colors:
                    if prev_pos is None or (abs(event.pos[0] - prev_pos[0]) < brush_size[button] // 4 and abs(event.pos[1] - prev_pos[1]) < brush_size[button] // 4):
                        pygame.draw.circle(canvas, brush_colors[button], event.pos, brush_size[button])
                        prev_pos = None
                    else:
                        pygame.draw.polygon(canvas, brush_colors[button], [prev_pos, event.pos], brush_size[button] * 2)
                        # pygame.draw.line(canvas, brush_colors[button], prev_pos, event.pos, brush_size[button] * 2)

                    prev_pos = event.pos

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                pygame.draw.rect(canvas, (255, 255, 255), (width, 0, width, height))
            elif event.key == pygame.K_s:
                save_file_dialog()
            elif event.key == pygame.K_e:
                eraser_down = True
            elif event.key == pygame.K_f:
                fullscreen = not fullscreen
                if fullscreen:
                    screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                else:
                    screen = pygame.display.set_mode((width*2, height))
            elif event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                shift_down = True
            elif event.key in (pygame.K_ESCAPE, pygame.K_x):
                pygame.quit()
                exit(0)

        elif event.type == pygame.KEYUP:
            if event.key == pygame.K_e:
                eraser_down = False
                brush_pos['e'] = None
            elif event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                shift_down = False
                shift_pos = None

        else:
            need_redraw = False

    # Draw the canvas and brushes on the screen
    screen.blit(canvas, (0, 0))

    # Create a new surface with a circle
    cursor_size = brush_size[1]*2
    cursor_surface = pygame.Surface((cursor_size, cursor_size), pygame.SRCALPHA)
    pygame.draw.circle(cursor_surface, cursor_color, (cursor_size // 2, cursor_size // 2), cursor_size // 2)

    # Blit the cursor surface onto the screen surface at the position of the mouse
    mouse_pos = pygame.mouse.get_pos()
    screen.blit(cursor_surface, (mouse_pos[0] - cursor_size // 2, mouse_pos[1] - cursor_size // 2))

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
