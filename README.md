# SdPaint
A Python script that lets you paint on a canvas and sends that image every stroke to the automatic1111 API and updates the canvas when the image is generated.

## Controls

| Key / Mouse button    | Control                                     |
|-----------------------|---------------------------------------------|
| Left button           | Draw with the current brush size            |
| Middle button         | Draw with a white color brush               |
| `e` + Left button     | Eraser brush (bigger)                       |
| Scroll up / down      | Increase / decrease brush size              |
| `backspace`           | Erase the entire sketch                     |
| `shift` + Left button | Draw a line between two clicks              |
| `RETURN` or `ENTER`   | Force image rendering                       |
| `t`                   | Cycle render wait time (+0.5s, or off)      |
| `UP` / `DOWN`         | Increase / decrease seed by 1               |
| `n`                   | Random seed value                           |
| `s`                   | Save the current generated image            |
| `o`                   | Open an image file as sketch                |
| `m`                   | Cycle ControlNel models                     |
| `d`                   | Cycle ControlNet detectors, replace sketch  |
| `h`                   | Cycle HR fix: off, 1.25, 1.5, 2.0           |
| `q`                   | Toggle quick rendering : low steps & HR off |
| `x` or `ESC`          | Quit                                        |


## Installation

Run the `Start.bat` file, and it will create a venv and install needed packages.

## Usage

Make sure you have the [automatic1111 webui](https://github.com/AUTOMATIC1111/stable-diffusion-webui) in API mode running in the background and that you have the controlnet extension installed and activated
To start the webui with the API enabled modify the `webui-user.bat` file by adding `--api` after `set COMMANDLINE_ARGS=`.
You also need to make sure the "Allow other script to control this extension" option is enabled in the settings of control net.

## Configuration

On first launch, the script will create the `config.json`, `controlnet.json` and `img2img.json` configuration files as needed. The ControlNet
available models for scribble and lineart will be automatically fetched from your API and set in configuration.

The `config.json` file handles global interface and script configuration.

The `controlnet.json` or `img2img.json` files can be used to configure the prompt, negative prompt, seed, controlnet model, etc. 
When you save the json file the program will use it after the next brush stroke or when you press `enter`.

A `controlnet-high.json-dist` example configuration file is available for better image quality, at the cost of longer rendering time.
Use only with a powerful graphics card.

If you want to add additional models into your controlnet extension you can do so by adding the model folder into the models folder of the controlnet extension.
```
    ".\stable-diffusion-webui\extensions\sd-webui-controlnet\models"
```

### Multiple ControlNet models

You can update the `config.json` `"controlnet_models"` list to have multiple ControlNet models available. You can then cycle 
between the models using the `l` and `m` keys.

The models set by default correspond to the ones available on https://huggingface.co/comfyanonymous/ControlNet-v1-1_fp16_safetensors :
 - Scribble
 - Lineart
 - Lineart anime

### ControlNet detectors

You can also update the `config.json` `"detectors"` list to configure the line detection on the generated image. Cycle between detections
with the `d` key.

The default detectors are:
 - Lineart
 - Lineart coarse
 - Sketch (pidinet)
 - Scribble (pidinet)

You can find the full list of supported modules with this URL http://127.0.0.1:7860/controlnet/module_list .

## Img2img Experimental mode

Launch the program with `--img2img <image_file_path>` to watch an image file for changes, and use it as img2img source. If the script is launched
with an empty image file path, a loading file dialog will be displayed.
The `img2img.json` file is used in this mode.

## Contributing

Pull requests are welcome. For major changes, please open an issue first
to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License

[MIT](https://choosealicense.com/licenses/mit/)