import pygame
import requests
import threading
import numpy as np
import base64
import io
import json
import time
from PIL import Image, ImageOps
import tkinter as tk
from tkinter import filedialog

# Initialize Pygame
pygame.init()

# setup sd inputs
url = "http://127.0.0.1:7860"
prompt = "A painting by Monet"
seed = 3456456767

# Set up the display
screen = pygame.display.set_mode((1024, 512))
display_caption = "Sd Paint"
pygame.display.set_caption(display_caption)

# Setup text
font = pygame.font.SysFont(None, 24)
text_input = ""
# Set up the drawing surface
canvas = pygame.Surface((1024, 512))
pygame.draw.rect(canvas, (255, 255, 255), (0, 0, 1024, 512))

# Set up the brush
brush_size = {1: 2, 2: 10}
brush_colors = {
    1: (0, 0, 0),  # Left mouse button color
    2: (255, 255, 255),  # Middle mouse button color
}
brush_pos = {1: None, 2: None}

# Define the cursor size and color
cursor_size = 1
cursor_color = (0, 0, 0)

# Set up flag to check if server is busy or not
server_busy = False

def save_file_dialog():
    root = tk.Tk()
    root.withdraw()
    file_path = filedialog.asksaveasfilename(defaultextension=".png")
    saveimg = canvas.subsurface(pygame.Rect(0, 0, 512, 512)).copy()
    if file_path:
        pygame.image.save(saveimg, file_path)
        time.sleep(1)  # add a 1-second delay
    return file_path

def update_image(image_data):
    # Decode base64 image data
    img_bytes = io.BytesIO(base64.b64decode(image_data))
    img_surface = pygame.image.load(img_bytes)
    canvas.blit(img_surface, (0, 0))

# Set up the main loop
running = True
while running:

    # Handle events
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_BACKSPACE:
                pygame.draw.rect(canvas, (255, 255, 255), (512, 0, 512, 512))
            elif event.key == pygame.K_s:
                save_file_dialog()
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button in brush_colors:
                brush_pos[event.button] = event.pos
            elif event.button == 4:  # scroll up
                brush_size[1] = max(1, brush_size[1] + 1)
            elif event.button == 5:  # scroll down
                brush_size[1] = max(1, brush_size[1] - 1)
        elif event.type == pygame.MOUSEBUTTONUP:
            if event.button in brush_colors:
                brush_pos[event.button] = None
                brush_color = brush_colors[event.button]
                # Check if server is busy before sending request
                if not server_busy:
                    server_busy = True
                    img = canvas.subsurface(pygame.Rect(512, 0, 512, 512)).copy()

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
                    
                    def send_request():
                        global server_busy
                        global display_caption
                        response = requests.post(url=f'{url}/controlnet/txt2img', json=payload)
                        r = response.json()
                        return_img = r['images'][0]
                        r_info = json.loads(r['info'])
                        return_prompt = r_info['prompt']
                        return_seed = r_info['seed']
                        update_image(return_img)
                        display_caption = f"Sd Paint | Seed: {return_seed} | Prompt: {return_prompt}"
                        server_busy = False
                    
                    t = threading.Thread(target=send_request)
                    t.start()
        elif event.type == pygame.MOUSEMOTION:
            for button, pos in brush_pos.items():
                if pos is not None and button in brush_colors:
                    pygame.draw.circle(canvas, brush_colors[button], event.pos, brush_size[button])
    
    # Draw the canvas and brushes on the screen
    screen.blit(canvas, (0, 0))
    
    # Create a new surface with a circle
    cursor_size = brush_size[1]*2
    cursor_surface = pygame.Surface((cursor_size, cursor_size), pygame.SRCALPHA)
    pygame.draw.circle(cursor_surface, cursor_color, (cursor_size // 2, cursor_size // 2), cursor_size // 2)

    # Blit the cursor surface onto the screen surface at the position of the mouse
    mouse_pos = pygame.mouse.get_pos()
    screen.blit(cursor_surface, (mouse_pos[0] - cursor_size // 2, mouse_pos[1] - cursor_size // 2))
        
    for button, pos in brush_pos.items():
        if pos is not None and button in brush_colors:
            pygame.draw.circle(screen, brush_colors[button], pos, brush_size[button])

    # Update the display
    pygame.display.update()
    pygame.display.set_caption(display_caption)

# Clean up Pygame
pygame.quit()
