import pygame
import requests
import threading
import numpy as np
import base64
import io
import json
from PIL import Image, ImageOps

# Initialize Pygame
pygame.init()

# setup sd inputs
url = "http://127.0.0.1:7860"
prompt = "A painting by Monet"
seed = 3456456767

# Set up the display
screen = pygame.display.set_mode((1024, 512))
pygame.display.set_caption("Sd Paint")
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

# Set up flag to check if server is busy or not
server_busy = False

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
        elif event.type == pygame.MOUSEBUTTONDOWN:
            if event.button in brush_colors:
                brush_pos[event.button] = event.pos
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
                                        #data = io.BytesIO()
                    #pygame.image.save(canvas.subsurface(pygame.Rect(512, 0, 512, 512)), data)
                    #data = base64.b64encode(data.getvalue()).decode('utf-8')
                    with open("payload.json", "r") as f:
                        payload = json.load(f)
                    payload['controlnet_units'][0]['input_image'] = data
                    
                    def send_request():
                        global server_busy
                        response = requests.post(url=f'{url}/controlnet/txt2img', json=payload)
                        r = response.json()
                        return_img = r['images'][0]
                        update_image(return_img)
                        server_busy = False
                    
                    t = threading.Thread(target=send_request)
                    t.start()

        elif event.type == pygame.MOUSEMOTION:
            for button, pos in brush_pos.items():
                if pos is not None and button in brush_colors:
                    pygame.draw.circle(canvas, brush_colors[button], event.pos, brush_size[button])

    # Draw the canvas and brushes on the screen
    screen.blit(canvas, (0, 0))
    for button, pos in brush_pos.items():
        if pos is not None and button in brush_colors:
            pygame.draw.circle(screen, brush_colors[button], pos, brush_size[button])

    # Update the display
    pygame.display.update()

# Clean up Pygame
pygame.quit()
