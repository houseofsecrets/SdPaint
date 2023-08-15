# SdPaintWeb

A Web script that lets you paint on a canvas and sends that image to the automatic1111 API and updates the result frame when the image is generated.

## Controls

| Key / Mouse button                      | Control                                             |
| --------------------------------------- | --------------------------------------------------- |
| `Left button`                           | Draw with the current brush size                    |
| `Middle button`                         | Draw with a white color brush                       |
| `Escape`                                | Escape from image viewer or switch off zen mode     |
| `Enter`                                 | Request image rendering                             |
| `Equal`                                 | Increase brush size                                 |
| `Minus`                                 | Decrease brush size                                 |
| `Delete`                                | Clear painting canvas                               |
| `Backspace`                             | Stop image generation                               |
| `~`                                     | Increase seed by 1                                  |
| `Shift` + `~`                           | Decrease seed by 1                                  |
| `Alt` + `~`                           | Randomize seed                                 |
| `a`                                     | Switch audio signal                                 |
| `c`                                     | Loads config from `controlnet.json` to form         |
| `Shift` + `c`                           | Saves config from forms to `controlnet.json`        |
| `d`                                     | Download result image (if any) from browser         |
| `e`                                     | Set brush type to `ellipse`                         |
| `l`                                     | Set brush type to `line`                            |
| `m`                                     | Switch multiple images mode                         |
| `p`                                     | Set brush type to `pencil`                          |
| `r`                                     | Set brush type to `rectangle`                       |
| `Ctrl` + `e`                            | Switch eraser brush mode                            |
| `f`                                     | Switch fill brush mode                              |
| `i`                                     | Switch instant generation mode                      |
| `Ctrl` + `r`                            | Reset interface (standard browser page reload)      |
| `s`                                     | Open settings                                       |
| `v`                                     | Switch image viewer mode (if there is result image) |
| `z`                                     | Switch zen mode                                     |
| `Ctrl` + `z`                            | Undo canvas action                                  |
| `Shift` + `y` or `Ctrl` + `Shift` + `z` | Redo an undone canvas action                        |

_Note_ : most widgets can handle standard browser hotkeys such as `Ctrl` + `a` in text input to select all it's content

## Installation

Windows: [Link to step-by-step Windows installation instructions with screenshots](INSTALL_Windows.md)

macOS: [Link to step-by-step MacOS installation instructions with screenshots](INSTALL_MacOS.md)

Linux: To Do

TLDR; [Web UI](https://github.com/AUTOMATIC1111/stable-diffusion-webui) with
the [ControlNet](https://github.com/Mikubill/sd-webui-controlnet) extension, API mode enabled in settings, and
the [AI Models](https://huggingface.co/lllyasviel/ControlNet-v1-1)

## Interface

![image](images/web_view.png)

Web interface consists of `config form`, `tools section`, `painting canvas` and `result area`

### `Config form`

![image](images/web_form.png)
This is partial representation of `configs\controlnet.json` file. It consists of:

- `prompt` input
- `negative prompt` input
- `seed` input
- `steps` input
- `module` selector
- `model` selector
- `tiling` switch

All this data is sent to ControlNet API when you request image generation.

### `Tools section`

![image](images/web_tools.png)

This is main control panel of this app. Here are:

- `Brush customizer` section. It handles behavior of drawing brush. Here you can change width, switch eraser, toggle shape modes and their filling. There is four shape modes: `pencil`, `line`, `ellipse` and `rectangle`.
- `Download` button. Downloads result image (if any).
- `Load config` button ( ⤒ ). Loads `controlnet.json` data to form fields.
- `Save config` button ( ⤓ ). Saves data from form fields to `controlnet.json`.
- `Settings` button ( ⛭ ). Opens settings modal.
- `Clear` button. Resets `painting canvas`.
- `Zen mode` button. Enters simplified interface mode.
- `Multiple mode` checkbox. Switches multiple images generation result.
- `Generate` button. Triggers ControlNet API image generation.

### `Settings modal`

![image](images/web_settings.png)

Here you can change:

- `Instant mode`. Switches instant mode (requests image redraw just when you stroke).
- `Multiple images count`. Selects how many images will be generated in multiple mode.
- `Audio signal`. Toggles audio signal.
- `Audio theme`. Customizes the audio signal theme.

### `Painting canvas`

![image](images/web_canvas.png)

This is area for drawing. If instant mode enabled, after each stroke image will be requested.
Size of canvas (and result image) can be customized:

![image](images/web_resizer.png)

### `Result area`

![image](images/web_result.png)

There is a place for ControlNet generations. If in process, progressbar and loader will appear. If you can click loader to cancel image generation

![image](images/web_loading.png)
![image](images/web_skip.png)

If you select multiple mode, there will appear multiple images
![image](images/web_multiple.png)
Each of them use its own seed and you can switch to it by clicking button (appears on hover on image that use it).

## Image viewer

![image](images/web_viewer.png)
Image viewer appears when you click on result image.
There is:

- image info such as used sketch, prompt, negative prompt etc.. In the sketch section, you can overlay the sketch on the image used for generation. Also if image was generated with `tiling` option you can switch tiling mode here
![image](images/web_tiling.png)
![image](images/web_viewer_with_sketch.png)
- actually the image itself
- images carousel (if multiple)

### Zen mode

![image](images/web_zen.png)

Zen mode is more simplified interface mode. Only `painting canvas` and `result area` are present. `ControlNet form` is hidden. `Tools section` is minified and hidden. By clicking arrows you can invoke them.

![image](images/web_controls.png)

## Contributing

Pull requests are welcome. Development brunch is https://github.com/Pythongor/SdPaint/tree/web-view.

To run in development mode first you need to install `npm`. If you're done with it run `StartWeb.bat` or `start-web.sh` depending on your OS. There can be alert, ignore it. In separated terminal run `cd scripts\views\WebView; npm install` then `npm start` from project root. Your default browser will open http://localhost:3000/ with app. Now all your changes in `scripts\views\WebView\src` will renew page.

## License

[MIT](https://choosealicense.com/licenses/mit/)
