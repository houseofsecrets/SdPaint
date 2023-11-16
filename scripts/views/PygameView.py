import functools
import gc
import os

import pygame
import pygame.gfxdraw
import threading
import base64
import io
import json
import time
import math
from PIL import Image, ImageOps
import tkinter as tk
from tkinter import filedialog, simpledialog
from scripts.common.utils import payload_submit, update_config, save_preset, update_size, new_random_seed, ckpt_name
from scripts.common.cn_requests import Api
from scripts.common.output_files_utils import autosave_image, save_image
from scripts.common.state import State
from sys import platform

# workaround for MacOS as per https://bugs.python.org/issue46573
if platform == "darwin":
    root = tk.Tk()
    root.withdraw()


class TextDialog(simpledialog.Dialog):
    """
        Text input dialog.
    """

    def __init__(self, text, title, dialog_width=800, dialog_height=100):
        self.text = text
        self.dialog_width = dialog_width
        self.dialog_height = dialog_height
        self.result = None
        super().__init__(None, title=title)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.quit()
        gc.collect()

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
            # remove new line inserted when validating the dialog with ENTER
            p = self.e1.get("1.0", tk.INSERT)[:-1] + self.e1.get(tk.INSERT, tk.END)
        else:
            p = self.e1.get("1.0", tk.END)
        self.result = p.strip("\n")


class PygameView:
    """
        SdPaint Pygame interface
    """

    ACCEPTED_FILE_TYPES = ["png", "jpg", "jpeg", "bmp"]

    def __init__(self, img2img):

        self.state = State(img2img)
        self.api = Api(self.state)
        if self.state.img2img:
            if not os.path.exists(self.state.img2img):
                root = tk.Tk()
                root.withdraw()
                self.state.img2img = filedialog.askopenfilename()

            self.img2img_time = os.path.getmtime(self.state.img2img)

            with Image.open(self.state.img2img, mode='r') as im:
                self.state.render["width"] = im.width
                self.state.render["height"] = im.height
                self.state.render["init_width"] = self.state.render["width"] * 1.0
                self.state.render["init_height"] = self.state.render["height"] * 1.0
                update_size(self.state)

        self.img2img_waiting = False
        self.img2img_time = None
        self.img2img_time_prev = None

        self.rendering = False
        self.rendering_key = False
        self.instant_render = False
        self.image_click = False
        self.pause_render = False
        self.osd_always_on_text: str | None = None
        self.progress = 0.0
        self.need_redraw = False
        self.running = False

        self.last_detect_time = time.time()
        self.osd_text = None
        self.osd_text_display_start = None

        if not self.state.configuration["config"]['controlnet_models']:
            self.api.fetch_controlnet_models(self.state)

        # Initialize Pygame
        pygame.init()
        self.clock = pygame.time.Clock()

        # Set up the display
        self.fullscreen = False
        self.screen = pygame.display.set_mode((self.state.render["width"] * (1 if self.state.img2img else 2), self.state.render["height"]))
        self.display_caption = "Sd Paint"
        pygame.display.set_caption(self.display_caption)

        # Setup text
        self.font = pygame.font.SysFont(None, size=24)
        self.font_bold = pygame.font.SysFont(None, size=24, bold=True)
        self.text_input = ""

        # Set up the drawing surface
        self.canvas = pygame.Surface((self.state.render["width"] * 2, self.state.render["height"]))
        pygame.draw.rect(self.canvas, (255, 255, 255), (0, 0, self.state.render["width"] * (1 if self.state.img2img else 2), self.state.render["height"]))

        # Set up the brush
        self.brush_size = {1: 2, 2: 2, 'e': 10, 'z': 2, 's': 2}
        self.brush_colors = {
            1: (0, 0, 0),  # Left mouse button color
            2: (255, 255, 255),  # Middle mouse button color
            'e': (255, 255, 255),  # Eraser color
            'z': (200, 200, 200),  # Eraser zone color
            's': (200, 200, 255),  # Save zone color
        }
        self.brush_color = self.brush_colors[1]
        self.brush_pos = {1: None, 2: None, 'e': None}  # type: dict[int|str, tuple[int, int]|None]
        self.button_down = False
        self.prev_pos = None
        self.prev_pos2 = None
        self.shift_pos = None
        self.eraser_down = False
        self.erase_zone_down = False
        self.save_zone_down = False
        self.zone_pos = []
        self.render_wait = 0.5 if not self.state.img2img else 0.0  # wait time max between 2 draw before launching the render
        self.last_draw_time = time.time()
        self.last_render_bytes: io.BytesIO | None = None

        # Define the cursor size and color
        self.cursor_size = 1
        self.cursor_color = (0, 0, 0)

        # Init the default preset
        save_preset(self.state, 'render', 0)
        save_preset(self.state, 'controlnet', 0)

    def load_preset(self, preset_type, index):
        """
            Load a preset values.
        :param str preset_type: The preset type. ``[render, controlnet]``
        :param int index: The preset numeric keymap.
        """

        presets = self.state.presets["list"]
        index = str(index)

        if presets[preset_type].get(index, None) is None:
            return f"No {preset_type} preset {index}"

        preset = presets[preset_type][index]

        if index == '0':
            text = f"Load default settings:"

            if preset_type == 'controlnet':
                # prepend OSD output with render preset values for default settings display (both called successively)
                for preset_field in self.state.presets["fields"]:
                    text += f"\n  {preset_field[:1].upper()}{preset_field[1:].replace('_', ' ')} :n: {presets['render'][index][preset_field]}"
        else:
            text = f"Load {preset_type} preset {index}:"

        # load preset
        if preset_type == 'render':
            for preset_field in self.state.presets["fields"]:
                if preset.get(preset_field, None) is None:
                    continue

                self.state.render[preset_field] = preset[preset_field]
                text += f"\n  {preset_field[:1].upper()}{preset_field[1:].replace('_', ' ')} :n: {preset[preset_field]}"

        elif preset_type == 'controlnet':
            for preset_field in self.state.control_net["preset_fields"]:
                if preset.get(preset_field, None) is None:
                    continue
                self.state.control_net[preset_field] = preset[preset_field]
                text += f"\n  {preset_field[:1].upper()}{preset_field[1:].replace('_', ' ')} :n: {preset[preset_field]}"

        update_size(self.state)
        return text

    def interrupt_rendering(self):
        """
            Interrupt current rendering.
        """

        response = self.api.interrupt_rendering()
        if response.status_code == 200:
            self.osd(text="Interrupted rendering")

    def load_filepath_into_canvas(self, file_path):
        """
            Load an image file on the sketch canvas.

        :param str file_path: Local image file path.
        """
        width_modificator = 1 if self.state.img2img else 2
        self.canvas = pygame.Surface((self.state.render["width"] * width_modificator, self.state.render["height"]))
        pygame.draw.rect(self.canvas, (255, 255, 255), (0, 0, self.state.render["width"] * width_modificator, self.state.render["height"]))
        img = pygame.image.load(file_path)
        img = pygame.transform.smoothscale(img, (self.state.render["width"], self.state.render["height"]))
        self.canvas.blit(img, (self.state.render["width"], 0))

    def finger_pos(self, finger_x, finger_y):
        """
            Compute finger position on canvas.
        :param float finger_x: Finger X position.
        :param float finger_y: Finger Y position.
        :return: Finger coordinates.
        """

        x = round(min(max(finger_x, 0), 1) * self.state.render["width"] * (1 if self.state.img2img else 2))
        y = round(min(max(finger_y, 0), 1) * self.state.render["height"])
        return x, y

    def save_file_dialog(self):
        """
            Display save file dialog, then write the file.
        """

        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.asksaveasfilename(defaultextension=".png")

        if file_path:
            save_image(file_path, self.last_render_bytes)
            self.save_sketch(file_path)
            time.sleep(1)  # add a 1-second delay

    def save_sketch(self, file_path):
        """
            Save sketch canvas to a file.
        :param str file_path: Render output file path.
        """
        file_name, file_ext = os.path.splitext(file_path)
        sketch_img = self.canvas.subsurface(pygame.Rect(self.state.render["width"], 0, self.state.render["width"], self.state.render["height"])).copy()
        pygame.image.save(sketch_img, f"{file_name}-sketch{file_ext}")

    def load_file_dialog(self):
        """
            Display loading file dialog, then load the image on the sketch canvas.
        """

        root = tk.Tk()
        root.withdraw()
        file_path = filedialog.askopenfilename()
        if not file_path:
            return

        extension = os.path.splitext(file_path)[1][1:].lower()
        if extension in PygameView.ACCEPTED_FILE_TYPES:
            self.load_filepath_into_canvas(file_path)

    def update_image(self, image_data):
        """
            Redraw the image canvas.
        :param str|bytes image_data: Base64 encoded image data, from API response.
        """

        # Decode base64 image data
        if isinstance(image_data, str):
            image_data = base64.b64decode(image_data)

        img_bytes = io.BytesIO(image_data)
        img_surface = pygame.image.load(img_bytes)

        if self.state.autosave["images"]:
            file_name = autosave_image(self.state, io.BytesIO(image_data))
            self.save_sketch(file_name)
        self.last_render_bytes = io.BytesIO(image_data)  # store rendered image in memory

        if self.state.render["soft_upscale"] != 1.0:
            width = img_surface.get_width() * self.state.render["soft_upscale"]
            height = img_surface.get_height() * self.state.render["soft_upscale"]
            img_surface = pygame.transform.smoothscale(img_surface, (width, height))

        self.canvas.blit(img_surface, (0, 0))
        self.need_redraw = True

    def update_batch_images(self, image_datas):
        """
            Redraw the image canvas with multiple images.
        :param list[str]|list[bytes] image_datas: Images data, if ``str`` type : base64 encoded from API response.
        """

        # Close old batch images
        if len(self.state.render["batch_images"]):
            for batch_image in self.state.render["batch_images"]:
                image_bytes = batch_image.get('image', None)
                if isinstance(image_bytes, io.BytesIO):
                    image_bytes.close()

            self.state.render["batch_images"] = []

        to_autosave = []
        nb = math.ceil(math.sqrt(len(image_datas)))
        i, j, batch_index = 0, 0, 1
        for image_data in image_datas:
            pos = (i * self.state.render["width"] // nb, j * self.state.render["height"] // nb)

            # Decode base64 image data
            if isinstance(image_data, str):
                image_data = base64.b64decode(image_data)

            img_bytes = io.BytesIO(image_data)
            img_surface = pygame.image.load(img_bytes)

            if (i, j) == (0, 0):
                # store first rendered image in memory
                self.last_render_bytes = io.BytesIO(image_data)

            if self.state.render["soft_upscale"] != 1.0:
                width = img_surface.get_width() * self.state.render["soft_upscale"] // nb
                height = img_surface.get_height() * self.state.render["soft_upscale"] // nb
                img_surface = pygame.transform.smoothscale(img_surface, (width, height))

            if self.state.autosave["images"]:
                to_autosave.append(io.BytesIO(image_data))

            self.state.render["batch_images"].append({
                "seed": self.state.gen_settings["seed"] + batch_index - 1,
                "image": io.BytesIO(image_data),
                "coord": (pos[0], pos[1], img_surface.get_width(), img_surface.get_height())
            })

            self.canvas.blit(img_surface, pos)

            # increase indices
            i = (i + 1) % nb
            if i == 0:
                j = (j + 1) % nb
            batch_index += 1

        if to_autosave:
            file_names = autosave_image(self.state, to_autosave)
            for file_name in file_names:
                self.save_sketch(file_name)

        self.need_redraw = True

    def select_batch_image(self, pos):
        """
            Select a batch image by clicking on it.
        :param list[int]|tuple[int] pos: The event position.
        """

        if not len(self.state.render["batch_images"]):
            return

        for batch_image in self.state.render["batch_images"]:
            if batch_image['coord'][0] <= pos[0] < batch_image['coord'][0] + batch_image['coord'][2] \
                    and batch_image['coord'][1] <= pos[1] < batch_image['coord'][1] + batch_image['coord'][3]:

                self.need_redraw = True
                self.osd(text_time=f"Select batch image seed {batch_image['seed']}")

                if batch_image.get('image', None):
                    self.update_image(batch_image['image'].getbuffer().tobytes())

                self.state.gen_settings["seed"] = batch_image['seed']

                self.toggle_batch_mode()

                break

    def img2img_submit(self, force=False):
        """
            Read the ``img2img`` file if modified since last render, check every 1s. Call the API to render if needed.
        :param bool force: Force the rendering, even if the file is not modified.
        """
        self.img2img_waiting = False

        self.img2img_time = os.path.getmtime(self.state.img2img)
        if self.img2img_time != self.img2img_time_prev or force:
            self.img2img_time_prev = self.img2img_time

            self.state.server["busy"] = True

            t = threading.Thread(target=self.progress_bar)
            t.start()

            response = self.api.fetch_img2img(self.state)
            if response["status_code"] == 200:
                return_img = response["image"]
                self.update_image(return_img)
                r_info = json.loads(response['info'])
                return_prompt = r_info['prompt']
                return_seed = r_info['seed']
                self.display_caption = f"Sd Paint | Seed: {return_seed} | Prompt: {return_prompt}"
            else:
                self.osd(text=f"Error code returned: HTTP {response['status_code']}")

            self.state.server["busy"] = False

        if not self.img2img_waiting and self.running:
            self.img2img_waiting = True
            time.sleep(1.0)
            self.img2img_submit()

    def progress_bar(self):
        """
            Update the progress bar every 0.25s
        """
        if not self.state.server["busy"]:
            return

        progress_json = self.api.progress_request()
        if progress_json.get("status_code", None):
            self.osd(text=f"Error code returned: HTTP {progress_json['status_code']}")
        self.progress = progress_json.get('progress', None)
        # if progress is not None and progress > 0.0:
        #     print(f"{progress*100:.0f}%")

        if self.state.server["busy"]:
            time.sleep(0.25)
            self.progress_bar()

    def draw_osd_text(self, text, rect, color=(255, 255, 255), shadow_color=(0, 0, 0), distance=1, right_align=False):
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

        text_surface = self.font.render(text, True, shadow_color)
        self.screen.blit(text_surface, (rect[0] + text_surface.get_width() * align_offset + distance, rect[1] + distance, rect[2], rect[3]))
        self.screen.blit(text_surface, (rect[0] + text_surface.get_width() * align_offset - distance, rect[1] + distance, rect[2], rect[3]))
        self.screen.blit(text_surface, (rect[0] + text_surface.get_width() * align_offset + distance, rect[1] - distance, rect[2], rect[3]))
        self.screen.blit(text_surface, (rect[0] + text_surface.get_width() * align_offset - distance, rect[1] - distance, rect[2], rect[3]))
        text_surface = self.font.render(text, True, color)
        self.screen.blit(text_surface, (rect[0] + text_surface.get_width() * align_offset, rect[1], rect[2], rect[3]))

    def osd(self, **kwargs):
        """
            OSD display: progress bar and text messages.

        :param kwargs: Accepted parameters : ``progress, text, text_time, need_redraw``
        """

        osd_size = (128, 20)
        osd_margin = 10
        img2img_modificator = 0 if self.state.img2img else 1
        left = self.state.render["width"] * img2img_modificator + osd_margin
        osd_progress_pos = (left, osd_margin)  # top left of canvas
        # osd_pos = (width*(1 if img2img else 2) // 2 - osd_size [0] // 2, osd_margin)  # top center
        # osd_progress_pos = (width*(1 if img2img else 2) - osd_size[0] - osd_margin, height - osd_size[1] - osd_margin)  # bottom right

        osd_dot_size = osd_size[1] // 2
        # osd_dot_pos = (width*(0 if img2img else 1) + osd_margin, osd_margin, osd_dot_size, osd_dot_size)  # top left
        osd_dot_pos = (self.state.render["width"] * (img2img_modificator + 1) - osd_dot_size * 2 - osd_margin, osd_margin, osd_dot_size, osd_dot_size)  # top right

        osd_text_pos = (left, osd_margin)  # top left of canvas
        # osd_text_pos = (width*(0 if img2img else 1) + osd_margin, height - osd_size[1] - osd_margin)  # bottom left of canvas
        osd_text_offset = 0

        osd_text_split_offset = 250

        self.progress = kwargs.get('progress', self.progress)  # type: float
        text = kwargs.get('text', self.osd_text)  # type: str
        text_time = kwargs.get('text_time', 2.0)  # type: float
        self.need_redraw = kwargs.get('need_redraw', self.need_redraw)  # type: bool
        self.osd_always_on_text = kwargs.get('always_on', self.osd_always_on_text)

        if self.rendering or (self.state.server["busy"] and self.progress is not None and self.progress < 0.02):
            rendering_dot_surface = pygame.Surface(osd_size, pygame.SRCALPHA)

            pygame.draw.circle(rendering_dot_surface, (0, 0, 0), (osd_dot_size + 2, osd_dot_size + 2), osd_dot_size - 2)
            pygame.draw.circle(rendering_dot_surface, (0, 200, 160), (osd_dot_size, osd_dot_size), osd_dot_size - 2)
            self.screen.blit(rendering_dot_surface, osd_dot_pos)

        if self.progress is not None and self.progress > 0.01:
            self.need_redraw = True

            # progress bar
            progress_surface = pygame.Surface(osd_size, pygame.SRCALPHA)
            width = math.floor(osd_size[0] * self.progress)
            pygame.draw.rect(progress_surface, (0, 0, 0), pygame.Rect(2, 2, width, osd_size[1]))
            pygame.draw.rect(progress_surface, (0, 200, 160), pygame.Rect(0, 0, width, osd_size[1] - 2))

            self.screen.blit(progress_surface, pygame.Rect(osd_progress_pos[0], osd_progress_pos[1], osd_size[0], osd_size[1]))

            # progress text
            self.draw_osd_text(f"{self.progress * 100:.0f}%", (osd_size[0] - osd_margin + osd_progress_pos[0], 3 + osd_progress_pos[1], osd_size[0], osd_size[1]), right_align=True)

            osd_text_offset = osd_size[1] + osd_margin

        if self.osd_always_on_text:
            self.need_redraw = True

            # OSD always-on text
            for line in self.osd_always_on_text.split('\n'):
                self.need_redraw = True

                if ':n:' in line:
                    line, line_value = line.split(':n:')
                    line = line.rstrip(' ')
                    line_value = line_value.lstrip(' ')
                else:
                    line_value = None

                self.draw_osd_text(line, (osd_text_pos[0], osd_text_pos[1] + osd_text_offset, osd_size[0], osd_size[1]))
                if line_value:
                    self.draw_osd_text(line_value, (osd_text_pos[0] + osd_text_split_offset, osd_text_pos[1] + osd_text_offset, osd_size[0], osd_size[1]))

                osd_text_offset += osd_size[1]

        if text:
            self.need_redraw = True

            # OSD text
            if self.osd_text_display_start is None or text != self.osd_text:
                self.osd_text_display_start = time.time()
            self.osd_text = text

            for line in self.osd_text.split('\n'):
                self.need_redraw = True

                if ':n:' in line:
                    line, line_value = line.split(':n:')
                    line = line.rstrip(' ')
                    line_value = line_value.lstrip(' ')
                else:
                    line_value = None

                self.draw_osd_text(line, (osd_text_pos[0], osd_text_pos[1] + osd_text_offset, osd_size[0], osd_size[1]))
                if line_value:
                    self.draw_osd_text(line_value, (osd_text_pos[0] + osd_text_split_offset, osd_text_pos[1] + osd_text_offset, osd_size[0], osd_size[1]))

                osd_text_offset += osd_size[1]

            if time.time() - self.osd_text_display_start > text_time:
                self.osd_text = None
                self.osd_text_display_start = None

    def get_image_string_from_pygame(self):
        """
            Get base64 encoded image string from canvas.
        :return: The encoder image.
        """
        img = self.canvas.subsurface(pygame.Rect(self.state.render["width"], 0, self.state.render["width"], self.state.render["height"])).copy()

        if not self.state.render["use_invert_module"]:
            # Convert the Pygame surface to a PIL image
            pil_img = Image.frombytes('RGB', img.get_size(), pygame.image.tostring(img, 'RGB'))

            # Invert the colors of the PIL image
            pil_img = ImageOps.invert(pil_img)

            # Convert the PIL image back to a Pygame surface
            img = pygame.image.fromstring(pil_img.tobytes(), pil_img.size, pil_img.mode).convert_alpha()

        # Save the inverted image as base64-encoded data
        data = io.BytesIO()
        pygame.image.save(img, data)
        return base64.b64encode(data.getvalue()).decode('utf-8')

    def send_request(self):
        """
            Send the API request.
        """

        response = self.api.post_request(self.state)
        if response["status_code"] == 200:
            if response.get("image", None):
                self.update_image(response["image"])
            elif response.get("batch_images", None):
                self.update_batch_images(response["batch_images"])

            r_info = json.loads(response['info'])
            return_prompt = r_info['prompt']
            return_seed = r_info['seed']
            self.display_caption = f"Sd Paint | Seed: {return_seed} | Prompt: {return_prompt}"
        else:
            self.osd(text=f"Error code returned: HTTP {response['status_code']}")
        self.state.server["busy"] = False

    def render(self):
        """
            Call the API to launch the rendering, if another rendering is not in progress.
        """
        if time.time() - self.last_draw_time < self.render_wait and not self.instant_render:
            time.sleep(0.25)
            self.render()
            return

        self.instant_render = False

        if not self.state.server["busy"]:
            self.state.server["busy"] = True

            if not self.state.img2img:
                image_string = self.get_image_string_from_pygame()
                payload_submit(self.state, image_string)
                t = threading.Thread(target=self.send_request)
                t.start()
                t = threading.Thread(target=self.progress_bar)
                t.start()
            else:
                t = threading.Thread(target=functools.partial(self.img2img_submit, True))
                t.start()

    @staticmethod
    def get_angle(pos1, pos2):
        """
            Get the angle between two position.
        :param tuple[int]|list[int] pos1: First position.
        :param tuple[int]|list[int] pos2: Second position.
        :return: radians, degrees, cos, sin
        """

        dx = pos1[0] - pos2[0]
        dy = pos1[1] - pos2[1]
        rads = math.atan2(-dy, dx)
        rads %= 2 * math.pi

        return rads, math.degrees(rads), math.cos(rads), math.sin(rads)

    def brush_stroke(self, event, button, pos):
        """
            Draw the brush stroke.
        :param pygame.event.Event|dict event: The pygame event.
        :param int|str button: The active button.
        :param tuple[int]|list[int] pos: The brush current position.
        """

        if self.prev_pos is None or (abs(event.pos[0] - self.prev_pos[0]) < self.brush_size[button] // 4 and abs(event.pos[1] - self.prev_pos[1]) < self.brush_size[button] // 4):
            # Slow brush stroke, draw circles
            pygame.draw.circle(self.canvas, self.brush_colors[button], event.pos, self.brush_size[button])

        elif not self.prev_pos2 or self.brush_size[button] < 4:
            # Draw a simple polygon for small brush sizes
            pygame.draw.polygon(self.canvas, self.brush_colors[button], [self.prev_pos, event.pos], self.brush_size[button] * 2)

        else:
            # Draw a complex shape with gfxdraw for bigger bush sizes to avoid gaps
            angle_prev = self.get_angle(self.prev_pos, self.prev_pos2)
            angle = self.get_angle(event.pos, self.prev_pos)

            offset_pos_prev = [(self.brush_size[button] * angle_prev[3]), (self.brush_size[button] * angle_prev[2])]
            offset_pos = [(self.brush_size[button] * angle[3]), (self.brush_size[button] * angle[2])]
            pygame.gfxdraw.filled_polygon(self.canvas, [
                (self.prev_pos2[0] - offset_pos_prev[0], self.prev_pos2[1] - offset_pos_prev[1]),
                (self.prev_pos[0] - offset_pos[0], self.prev_pos[1] - offset_pos[1]),
                (event.pos[0] - offset_pos[0], event.pos[1] - offset_pos[1]),
                (event.pos[0] + offset_pos[0], event.pos[1] + offset_pos[1]),
                (self.prev_pos[0] + offset_pos[0], self.prev_pos[1] + offset_pos[1]),
                (self.prev_pos2[0] + offset_pos_prev[0], self.prev_pos2[1] + offset_pos_prev[1])
            ], self.brush_colors[button])

        self.prev_pos2 = self.prev_pos
        self.prev_pos = event.pos

    @property
    def shift_down(self):
        return pygame.key.get_mods() & pygame.KMOD_SHIFT

    @property
    def ctrl_down(self):
        return pygame.key.get_mods() & pygame.KMOD_CTRL

    @property
    def alt_down(self):
        return pygame.key.get_mods() & pygame.KMOD_ALT

    def controlnet_detect(self, detector):
        """
            Call ControlNet active detector on the last rendered image, replace the canvas sketch by the detector result.
        :param str detector: The detector to apply.
        """
        img = self.canvas.subsurface(pygame.Rect(0, 0, self.state.render["width"], self.state.render["height"])).copy()

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

        response = self.api.fetch_detect_image(detector, data, img.get_width(), img.get_height())
        if response["status_code"] == 200:
            return_img = response["image"]
            img_bytes = io.BytesIO(base64.b64decode(return_img))
            pil_img = Image.open(img_bytes)
            pil_img = ImageOps.invert(pil_img)
            pil_img = pil_img.convert('RGB')
            img_surface = pygame.image.fromstring(pil_img.tobytes(), pil_img.size, pil_img.mode)

            self.canvas.blit(img_surface, (self.state.render["width"], 0))
        else:
            self.osd(text=f"Error code returned: HTTP {response['status_code']}")

    def display_configuration(self, wrap=True):
        """
            Display configuration on screen.
        :param bool wrap: Wrap long text.
        """

        self.state.update_webui_config()

        fields = [
            '--Prompt',
            'state/gen_settings/prompt',
            'state/gen_settings/negative_prompt',
            'state/gen_settings/seed',
            '--Render',
            'state/render/checkpoint',
            'state/samplers/sampler',
            'state/render/vae',
            'state/render/render_size',
            'state/render/steps',
            'state/render/cfg_scale',
            'state/render/hr_scale',
            'state/render/hr_upscaler',
            'state/render/denoising_strength',
            'state/render/clip_skip',
            '--ControlNet',
            'state/control_net/controlnet_model',
            'state/control_net/controlnet_weight',
            'state/control_net/controlnet_guidance_end',
            'state/render/pixel_perfect',
            'state/detectors/detector'
        ]

        if wrap and self.state.render["width"] < 800:
            wrap = 50
        elif wrap:
            wrap = 80

        text = ''

        for field in fields:
            if field in ('state/render/steps', 'state/samplers/sampler', 'state/render/cfg_scale', 'state/gen_settings/prompt') and self.state.render["quick_mode"]:
                field = 'state/render/quick/'+field[field.rfind('/')+1:]

            # Display separator
            if field.startswith('--'):
                text += '\n'+field[2:]+'\n'
                continue

            # Field value
            label = ''
            value = ''

            if field == 'state/render/quick/prompt':
                field_components = field.replace('state/', '').split('/')
                label = field_components[2]
                value = self.state.gen_settings['prompt']
                if self.state.render['quick'].get('lora', None) and self.state.render['quick'].get('lora_weight', None):
                    value += f" <lora:{self.state.render['quick']['lora']}:{self.state.render['quick']['lora_weight']}>"

            elif '.' in field:
                field = field.split('.')
                var = globals().get(field[0], locals().get(field[0], None))
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
                if field.startswith('state/'):
                    field_components = field.replace('state/', '').split('/')
                    label = field_components[1]
                    field_value = getattr(self.state, field_components[0])[field_components[1]]
                    if isinstance(field_value, dict) and len(field_components) > 2:
                        label = field_components[2]
                        field_value = field_value.get(field_components[2], None)
                        if field_components[1] == 'quick':
                            field_value = f'{field_value} -quick-'
                else:
                    label = field
                    field_value = globals().get(field, locals().get(field, None))

                if field_value is not None:
                    value = field_value

            if label and value is not None:
                # prettify
                label = label.replace('_', ' ')
                if label.endswith('prompt'):
                    value = value.replace(', ', ',').replace(',', ', ')  # nicer prompt display
                elif 'size' in label and isinstance(value, tuple) and len(value) == 2:
                    value = f"{value[0]}x{value[1]}"
                elif label in ('checkpoint', 'vae'):
                    value = ckpt_name(value)
                else:
                    value = str(value)

                # wrap text
                if wrap and len(value) > wrap:
                    new_value = ''
                    to_wrap = 0
                    for i in range(len(value)):
                        if i % wrap == wrap - 1:
                            to_wrap = i

                        # try to wrap after space
                        if to_wrap and value[i] in [' ', ')'] or (to_wrap and i - to_wrap > 5):
                            new_value += value[i]+'\n:n:'
                            to_wrap = 0
                            continue

                        new_value += value[i]

                    value = new_value

                text += f"    {label} :n: {value}"

            text += '\n'

        self.osd(always_on=text.strip('\n'))

    def toggle_batch_mode(self, cycle=False):
        """
            Toggle batch mode on/off. Alter the setting of HR fix if needed.
        :param bool|int cycle: Cycle the batch size value.
        """

        batch_size = self.state.render["batch_size"]
        if cycle:
            self.rendering_key = True
            batch_sizes = self.state.render["batch_sizes"]
            self.state.render["batch_size"] = batch_sizes[(batch_sizes.index(self.state.render["batch_size"]) + 1) % len(batch_sizes)]
        else:
            self.rendering = True
            if self.state.render["batch_size"] != 1:
                self.state.render["batch_size_prev"] = batch_size
                self.state.render["batch_size"] = 1
            else:
                self.state.render["batch_size"] = self.state.render["batch_size_prev"]

        if self.state.render["batch_size"] == 1:
            self.state.render["hr_scale"] = self.state.render["batch_hr_scale_prev"]
            update_size(self.state)
            self.osd(text=f"Batch rendering: off")
        else:
            self.state.render["batch_hr_scale_prev"] = self.state.render["hr_scale"]
            self.state.render["hr_scale"] = 1.0
            update_size(self.state)
            self.osd(text=f"Batch rendering size: {self.state.render['batch_size']}")

    def main(self):
        # Initial img2img call
        if self.state.img2img:
            t = threading.Thread(target=self.img2img_submit)
            t.start()

        # Set up the main loop
        self.running = True
        self.need_redraw = True

        while self.running:
            self.rendering = False

            # Handle events
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False

                elif event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.FINGERDOWN:
                    self.button_down = True

                    # Handle brush stroke start and modifiers
                    if event.type == pygame.FINGERDOWN:
                        event.button = 1
                        event.pos = self.finger_pos(event.x, event.y)

                    valid_brush_pos = (max(self.state.render["width"], event.pos[0]), event.pos[1])

                    if event.pos[0] < self.state.render["width"]:
                        self.image_click = True  # clicked on the image part
                        if self.state.render["batch_size"] != 1 and len(self.state.render["batch_images"]):
                            self.select_batch_image(event.pos)
                    elif self.erase_zone_down:
                        if not self.zone_pos or self.zone_pos[-1] != valid_brush_pos:
                            self.zone_pos.append(valid_brush_pos)
                        if len(self.zone_pos) > 1:
                            pygame.draw.polygon(self.canvas, self.brush_colors['z'], (self.zone_pos[-2], self.zone_pos[-1]), self.brush_size['z'])
                    elif self.save_zone_down:
                        if not self.zone_pos or self.zone_pos[-1] != valid_brush_pos:
                            self.zone_pos.append(valid_brush_pos)
                        if len(self.zone_pos) > 1:
                            pygame.draw.polygon(self.canvas, self.brush_colors['s'], (self.zone_pos[-2], self.zone_pos[-1]), self.brush_size['s'])
                    else:
                        self.need_redraw = True
                        self.last_draw_time = time.time()

                        brush_key = event.button
                        if self.eraser_down:
                            brush_key = 'e'

                        if brush_key in self.brush_colors:
                            self.brush_pos[brush_key] = event.pos
                        elif event.button == 4:  # scroll up
                            self.brush_size[1] = max(1, self.brush_size[1] + 1)
                            self.brush_size[2] = max(1, self.brush_size[2] + 1)
                            self.osd(text=f"Brush size {self.brush_size[1]}")

                        elif event.button == 5:  # scroll down
                            self.brush_size[1] = max(1, self.brush_size[1] - 1)
                            self.brush_size[2] = max(1, self.brush_size[2] - 1)
                            self.osd(text=f"Brush size {self.brush_size[1]}")

                        if self.shift_down and self.brush_pos[brush_key] is not None:
                            if self.shift_pos is None:
                                self.shift_pos = self.brush_pos[brush_key]
                            else:
                                pygame.draw.polygon(self.canvas, self.brush_colors[brush_key], [self.shift_pos, self.brush_pos[brush_key]], self.brush_size[brush_key] * 2)
                                self.shift_pos = self.brush_pos[brush_key]

                elif event.type == pygame.MOUSEBUTTONUP or event.type == pygame.FINGERUP:
                    self.button_down = False

                    # Handle brush stoke end
                    self.last_draw_time = time.time()

                    if self.state.render["quick_mode"]:
                        self.instant_render = True

                    if event.type == pygame.FINGERUP:
                        event.button = 1
                        event.pos = self.finger_pos(event.x, event.y)

                    if self.erase_zone_down or self.save_zone_down:
                        self.need_redraw = True

                    if not self.image_click:
                        self.need_redraw = True
                        self.rendering = True

                        if event.button in self.brush_colors or self.eraser_down:
                            brush_key = event.button
                            if self.eraser_down:
                                brush_key = 'e'

                            if self.brush_size[brush_key] >= 4 and getattr(event, 'pos', None) is not None:
                                pygame.draw.circle(self.canvas, self.brush_colors[brush_key], event.pos, self.brush_size[brush_key])

                            self.brush_pos[brush_key] = None
                            self.prev_pos = None
                            self.brush_color = self.brush_colors[brush_key]

                    self.image_click = False  # reset image click detection

                elif event.type == pygame.MOUSEMOTION or event.type == pygame.FINGERMOTION:
                    # Handle drawing brush strokes
                    if event.type == pygame.FINGERMOTION:
                        event.pos = self.finger_pos(event.x, event.y)

                    valid_brush_pos = (max(self.state.render["width"], event.pos[0]), event.pos[1])
                    if self.erase_zone_down:
                        self.need_redraw = True
                        if self.button_down:
                            if not self.zone_pos or self.zone_pos[-1] != valid_brush_pos:
                                self.zone_pos.append(valid_brush_pos)
                            if len(self.zone_pos) > 1:
                                pygame.draw.polygon(self.canvas, self.brush_colors['z'], self.zone_pos[-2:], self.brush_size['z'])
                    elif self.save_zone_down:
                        self.need_redraw = True
                        if self.button_down:
                            if not self.zone_pos or self.zone_pos[-1] != valid_brush_pos:
                                self.zone_pos.append(valid_brush_pos)
                            if len(self.zone_pos) > 1:
                                pygame.draw.polygon(self.canvas, self.brush_colors['s'], self.zone_pos[-2:], self.brush_size['s'])
                    elif not self.image_click:
                        self.need_redraw = True
                        for button, pos in self.brush_pos.items():
                            if pos is not None and button in self.brush_colors:
                                self.last_draw_time = time.time()
                                # do the brush stroke
                                self.brush_stroke(event, button, pos)

                elif event.type == pygame.KEYDOWN:
                    # DBG key & modifiers
                    # print(f"key down {event.key}, modifiers:")
                    # print(f" shift:      {pygame.key.get_mods() & pygame.KMOD_SHIFT}")
                    # print(f" ctrl:       {pygame.key.get_mods() & pygame.KMOD_CTRL}")
                    # print(f" alt:        {pygame.key.get_mods() & pygame.KMOD_ALT}")

                    # Handle keyboard shortcuts
                    self.need_redraw = True
                    self.last_draw_time = time.time()
                    self.rendering = False

                    event.button = 1
                    if event.key == pygame.K_UP:
                        self.rendering = True
                        self.instant_render = True
                        self.state.gen_settings["seed"] = self.state.gen_settings["seed"] + self.state.render["batch_size"]
                        update_config(self.state.json_file, write=self.state.autosave["seed"], values={'seed': self.state.gen_settings["seed"]})
                        self.osd(text=f"Seed: {self.state['gen_settings']['seed']}")

                    elif event.key == pygame.K_DOWN:
                        self.rendering = True
                        self.instant_render = True
                        self.state.gen_settings["seed"] = self.state.gen_settings["seed"] - self.state.render["batch_size"]
                        update_config(self.state.json_file, write=self.state.autosave["seed"], values={'seed': self.state.gen_settings["seed"]})
                        self.osd(text=f"Seed: {self.state['gen_settings']['seed']}")

                    elif event.key == pygame.K_n:
                        if self.ctrl_down:
                            with TextDialog(self.state.gen_settings["seed"], title="Seed", dialog_width=200, dialog_height=30) as dialog:
                                if dialog.result and dialog.result.isnumeric():
                                    self.osd(text=f"Seed: {dialog.result}")
                                    self.state.gen_settings["seed"] = int(dialog.result)
                                    update_config(self.state.json_file, write=self.state.autosave["seed"], values={'seed': self.state.gen_settings["seed"]})
                                    self.rendering = True
                                    self.instant_render = True
                        else:
                            self.rendering = True
                            self.instant_render = True
                            self.state.gen_settings["seed"] = new_random_seed(self.state)
                            update_config(self.state.json_file, write=self.state.autosave["seed"], values={'seed': self.state.gen_settings["seed"]})
                            self.osd(text=f"Seed: {self.state['gen_settings']['seed']}")

                    elif event.key == pygame.K_c:
                        if self.shift_down:
                            self.rendering_key = True
                            self.state.render["clip_skip"] -= 1
                            self.state.render["clip_skip"] = (self.state.render["clip_skip"] + 1) % 2
                            self.state.render["clip_skip"] += 1
                            self.osd(text=f"CLIP skip: {self.state['render']['clip_skip']}")
                        else:
                            self.display_configuration()

                    elif event.key == pygame.K_m and self.state.control_net["controlnet_models"]:
                        if self.shift_down:
                            self.rendering_key = True
                            controlnet_models = self.state.control_net["controlnet_models"]
                            controlnet_model = self.state.control_net["controlnet_model"]
                            controlnet_model = controlnet_models[(controlnet_models.index(controlnet_model) + 1) % len(controlnet_models)]
                            self.state.control_net["controlnet_model"] = controlnet_model
                            self.osd(text=f"ControlNet model: {controlnet_model}")

                    elif event.key == pygame.K_i:
                        if self.ctrl_down:
                            self.interrupt_rendering()
                    elif event.key == pygame.K_h:
                        if self.shift_down:
                            self.rendering_key = True
                            self.state.render["hr_scale"] = self.state.render["hr_scales"][(self.state.render["hr_scales"].index(
                                self.state.render["hr_scale"])+1) % len(self.state.render["hr_scales"])]
                        else:
                            self.rendering = True
                            if self.state.render["hr_scale"] != 1.0:
                                self.state.render["hr_scale_prev"] = self.state.render["hr_scale"]
                                self.state.render["hr_scale"] = 1.0
                            else:
                                self.state.render["hr_scale"] = self.state.render["hr_scale_prev"]

                        if self.state.render["hr_scale"] == 1.0:
                            self.osd(text="HR scale: off")
                        else:
                            self.osd(text=f"HR scale: {self.state.render['hr_scale']}")

                        update_size(self.state, hr_scale=self.state.render["hr_scale"])

                    elif event.key in (pygame.K_KP_ENTER, pygame.K_RETURN):
                        self.rendering = True
                        self.instant_render = True
                        self.osd(text=f"Rendering")

                    elif event.key == pygame.K_q:
                        self.rendering = True
                        self.instant_render = True
                        self.state.render["quick_mode"] = not self.state.render["quick_mode"]
                        if self.state.render["quick_mode"]:
                            self.osd(text=f"Quick render: on")
                            self.state.render["hr_scale_prev"] = self.state.render["hr_scale"]
                            self.state.render["hr_scale"] = 1.0
                        else:
                            self.osd(text=f"Quick render: off")
                            self.state.render["hr_scale"] = self.state.render["hr_scale_prev"]

                        update_size(self.state, hr_scale=self.state.render["hr_scale"])

                    elif event.key == pygame.K_a:
                        self.state.autosave["images"] = not self.state.autosave["images"]
                        self.osd(text=f"Autosave images: {'on' if self.state['autosave']['images'] else 'off'}")

                    elif event.key == pygame.K_o:
                        if self.ctrl_down:
                            self.rendering = True
                            self.instant_render = True
                            self.load_file_dialog()

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

                        if self.ctrl_down:
                            if event.key != pygame.K_KP0:
                                preset_info = save_preset(self.state, 'controlnet' if self.alt_down else 'render', keymap.get(event.key))
                                if preset_info['index'] == '0':
                                    self.osd(text=f"Save {preset_info['preset_type']} preset {preset_info['index']}")
                        else:
                            self.rendering = True
                            self.instant_render = True

                            if event.key == pygame.K_KP0:
                                # Reset both render & controlnet settings if keypad 0
                                text = self.load_preset('render', keymap.get(event.key))
                                self.osd(text=text, text_time=4.0)
                                text = self.load_preset('controlnet', keymap.get(event.key))
                                self.osd(text=text, text_time=4.0)
                            else:
                                text = self.load_preset('controlnet' if self.alt_down else 'render', keymap.get(event.key))
                                self.osd(text=text, text_time=4.0)

                    elif event.key == pygame.K_p:
                        if self.ctrl_down:
                            self.pause_render = not self.pause_render

                            if self.pause_render:
                                self.osd(text=f"On-demand rendering (ENTER to render)")

                            else:
                                self.rendering = True
                                self.instant_render = True
                                self.osd(text=f"Dynamic rendering")

                        elif self.alt_down:
                            with TextDialog(self.state.gen_settings["negative_prompt"], title="Negative prompt") as dialog:
                                if dialog.result:
                                    self.osd(text=f"New negative prompt: {dialog.result}")
                                    self.state.gen_settings["negative_prompt"] = dialog.result
                                    update_config(self.state.json_file, write=self.state.autosave["negative_prompt"], values={
                                        'negative_prompt': self.state.gen_settings["negative_prompt"]
                                    })
                                    self.rendering = True
                                    self.instant_render = True
                        else:
                            with TextDialog(self.state.gen_settings["prompt"], title="Prompt") as dialog:
                                if dialog.result:
                                    self.osd(text=f"New prompt: {dialog.result}")
                                    self.state.gen_settings["prompt"] = dialog.result
                                    update_config(self.state.json_file, write=self.state.autosave["prompt"], values={
                                        'prompt': self.state.gen_settings["prompt"]
                                    })
                                    self.rendering = True
                                    self.instant_render = True

                    elif event.key == pygame.K_BACKSPACE:
                        self.rendering = True
                        self.instant_render = True
                        pygame.draw.rect(self.canvas, (255, 255, 255), (self.state.render["width"], 0, self.state.render["width"], self.state.render["height"]))

                    elif event.key == pygame.K_s:
                        if self.ctrl_down:
                            self.save_file_dialog()
                        elif self.shift_down:
                            self.rendering_key = True
                            samplers = self.state.samplers["list"]
                            self.state.samplers["sampler"] = samplers[(samplers.index(self.state.samplers["sampler"]) + 1) % len(samplers)]
                            self.osd(text=f"Sampler: {self.state['samplers']['sampler']}")
                        else:
                            self.save_zone_down = True

                    elif event.key == pygame.K_e:
                        self.eraser_down = True

                    elif event.key == pygame.K_z:
                        self.erase_zone_down = True

                    elif event.key == pygame.K_t:
                        if self.shift_down:
                            if self.render_wait == 2.0:
                                self.render_wait = 0.0
                                self.osd(text="Render wait: off")
                            else:
                                self.render_wait += 0.5
                                self.osd(text=f"Render wait: {self.render_wait}s")

                    elif event.key == pygame.K_u:
                        if self.shift_down:
                            self.rendering_key = True
                            hr_upscalers = self.state.render["hr_upscalers"]
                            hr_upscaler = self.state.render["hr_upscaler"]
                            hr_upscaler = hr_upscalers[(hr_upscalers.index(hr_upscaler) + 1) % len(hr_upscalers)]
                            self.state.render["hr_upscaler"] = hr_upscaler
                            self.osd(text=f"HR upscaler: {hr_upscaler}")

                    elif event.key == pygame.K_b:
                        self.toggle_batch_mode(cycle=self.shift_down)

                    elif event.key == pygame.K_w:
                        if self.shift_down:
                            self.rendering_key = True
                            controlnet_weights = self.state.control_net["controlnet_weights"]
                            controlnet_weight = self.state.control_net["controlnet_weight"]
                            controlnet_weight = controlnet_weights[(controlnet_weights.index(controlnet_weight) + 1) % len(controlnet_weights)]
                            self.state.control_net["controlnet_weight"] = controlnet_weight
                            self.osd(text=f"ControlNet weight: {controlnet_weight}")

                    elif event.key == pygame.K_g:
                        if self.shift_down and self.ctrl_down:
                            self.rendering_key = True
                            self.state.render["pixel_perfect"] = not self.state.render["pixel_perfect"]
                            self.osd(text=f"ControlNet pixel perfect mode: {'on' if self.state.render['pixel_perfect'] else 'off'}")
                        elif self.shift_down:
                            self.rendering_key = True
                            controlnet_guidance_ends = self.state.control_net["controlnet_guidance_ends"]
                            controlnet_guidance_end = self.state.control_net["controlnet_guidance_end"]
                            controlnet_guidance_end = controlnet_guidance_ends[(controlnet_guidance_ends.index(controlnet_guidance_end) + 1) % len(controlnet_guidance_ends)]
                            self.state.control_net["controlnet_guidance_end"] = controlnet_guidance_end
                            self.osd(text=f"ControlNet guidance end: {controlnet_guidance_end}")

                    elif event.key == pygame.K_d:
                        if self.ctrl_down:
                            detector = self.state.detectors['detector']
                            detectors = self.state.detectors["list"]
                            if self.shift_down:
                                # cycle detectors
                                self.state.detectors["detector"] = detectors[(detectors.index(detector)+1) % len(detectors)]
                                self.osd(text=f"ControlNet detector: {detector.replace('_', ' ')}")
                            else:
                                self.osd(text=f"Detect {detector.replace('_', ' ')}")
                                detector = str(detector)

                                t = threading.Thread(target=functools.partial(
                                    self.controlnet_detect, detector))
                                t.start()
                        elif self.shift_down:
                            self.rendering_key = True
                            denoising_strengths = self.state.render["denoising_strengths"]
                            denoising_strength = self.state.render["denoising_strength"]
                            denoising_strength = denoising_strengths[(denoising_strengths.index(denoising_strength) + 1) % len(denoising_strengths)]
                            self.state.render["denoising_strength"] = denoising_strength
                            if self.state.img2img:
                                self.osd(text=f"Denoising: {denoising_strength}")
                            else:
                                self.osd(text=f"HR denoising: {denoising_strength}")

                    elif event.key == pygame.K_f:
                        self.fullscreen = not self.fullscreen
                        if self.fullscreen:
                            pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
                        else:
                            pygame.display.set_mode((self.state.render["width"]*2, self.state.render["height"]))

                    elif event.key in (pygame.K_0, pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4, pygame.K_5, pygame.K_6, pygame.K_7, pygame.K_8, pygame.K_9):
                        for i in range(10):
                            key = getattr(pygame, f'K_{i}', None)
                            if event.key == key:
                                self.brush_size[1] = i if i != 0 else 10
                                self.brush_size[2] = i if i != 0 else 10
                                self.osd(text=f"Brush size {self.brush_size[1]}")

                    elif event.key in (pygame.K_ESCAPE, pygame.K_x):
                        self.running = False
                        pygame.quit()
                        exit(0)

                elif event.type == pygame.KEYUP:
                    # Handle special keys release
                    if event.key == pygame.K_e:
                        self.eraser_down = False
                        self.brush_pos['e'] = None

                    elif event.key in (pygame.K_LSHIFT, pygame.K_RSHIFT):
                        if self.rendering_key:
                            self.rendering = True
                            self.rendering_key = False
                        self.shift_pos = None

                    elif event.key in (pygame.K_z, pygame.K_s):
                        self.rendering = True
                        self.need_redraw = True
                        self.brush_pos['e'] = None
                        if len(self.zone_pos) > 2:
                            if self.save_zone_down:
                                self.zone_pos.insert(0, (self.state.render["width"], 0))
                                # self.zone_pos.insert(1, (self.zone_pos[1][0], 0))
                                self.zone_pos.append(self.zone_pos[1])
                                self.zone_pos.append(self.zone_pos[0])
                                self.zone_pos.append((self.state.render["width"]*2, 0))
                                self.zone_pos.append((self.state.render["width"]*2, self.state.render["height"]))
                                self.zone_pos.append((self.state.render["width"], self.state.render["height"]))

                            pygame.draw.polygon(self.canvas, self.brush_colors['e'], self.zone_pos, self.brush_size['z'])
                            pygame.draw.polygon(self.canvas, self.brush_colors['e'], self.zone_pos)

                        self.zone_pos = []

                        self.erase_zone_down = False
                        self.save_zone_down = False

                    elif event.key in (pygame.K_c,):
                        # Remove OSD always-on text
                        self.need_redraw = True
                        self.osd(always_on=None)

            # Call image render
            if (self.rendering and not self.pause_render) or self.instant_render:
                t = threading.Thread(target=self.render)
                t.start()

            # Draw the canvas and brushes on the screen
            self.screen.blit(self.canvas, (0, 0))

            # Handle mouse display
            mouse_pos = pygame.mouse.get_pos()
            if mouse_pos[0] >= self.state.render["width"]:
                # Create a new surface with a circle
                cursor_size = self.brush_size[1]*2
                cursor_surface = pygame.Surface((cursor_size, cursor_size), pygame.SRCALPHA)
                pygame.draw.circle(cursor_surface, self.cursor_color, (cursor_size // 2, cursor_size // 2), cursor_size // 2)

                # Blit the cursor surface onto the screen surface at the position of the mouse
                self.screen.blit(cursor_surface, (mouse_pos[0] - cursor_size // 2, mouse_pos[1] - cursor_size // 2))
                pygame.mouse.set_visible(False)
            else:
                pygame.mouse.set_visible(True)

            # Handle OSD
            self.osd()

            # Update the display
            if self.need_redraw:
                pygame.display.flip()
                pygame.display.set_caption(self.display_caption)
                self.need_redraw = False

            # Set max FPS
            self.clock.tick(120)

        # Clean up Pygame
        pygame.quit()
