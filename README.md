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


# SdPaint
A simple python script that lets you paint on a canvas and sends that image every stroke to the automatic1111 API and updates the canvas when the image is generated

## Updates

- Added the possibility to save the image created by pressing the ```s``` key
- You can use the scrollmouse key to change the brush size

## Installation

Assuming you started from no experience with SD, and some experience with GitHub. SDPaint presently only has a launch script for *Windows* through a .bat file. However, as it is a python program, launch scripts can be made for other OS that WebUI and ControlNet supports.

Clone:

The Tool
```https://github.com/houseofsecrets/SdPaint```

The AI models
```https://huggingface.co/lllyasviel/ControlNet-v1-1```

Follow the instructions for your OS to install the Web UI. It also installs Stable Diffusion and can be used independantly.
```https://github.com/AUTOMATIC1111/stable-diffusion-webui```

You should now have the following folders:

![image](https://user-images.githubusercontent.com/22615608/234105284-66051525-d434-48af-852f-c3c7add4fa39.png)

Run the Web UI by launching
```stable-diffusion-webui\webui-user.bat```

The first time will also install SD so you can use this independently if you wish.

The Web UI is now running locally. In a browser, visit the default address at 
```http://127.0.0.1:7860```

![WebUI_First_Open](https://user-images.githubusercontent.com/22615608/234109327-a1a58b3b-885e-448a-bfca-64bcb24e5e7f.jpg)

In the Web UI, navigate to the "Extensions Tab" add go to the "Install from URL" tab. Then add the extension from
```https://github.com/Mikubill/sd-webui-controlnet```

Nothing will seem to happen, but if you go back to the "Installed" tab, it should be processing.
<img width="1507" alt="Screenshot 2023-04-24 at 12 43 43 PM" src="https://user-images.githubusercontent.com/22615608/234099711-9f4d435d-54ec-4176-8f1b-dbbb2bde47d8.png">

Press the "Check for Updates" button, just in case. Then press the "Apply and Restart UI".
<img width="1507" alt="Screenshot 2023-04-24 at 12 45 04 PM" src="https://user-images.githubusercontent.com/22615608/234100186-23b9b745-b0d2-4486-96b8-3077910c3d7e.png">

Once reloaded, navigate to the the settings of the Web UI, look for "Allow other script to control this extension" and enable it. Apply settings.
<img width="1507" alt="Screenshot 2023-04-24 at 12 45 53 PM" src="https://user-images.githubusercontent.com/22615608/234100172-2f5f2a8f-719e-4bf4-bc74-ca59d8cc2ea3.png">

Close the Web UI and the terminal window running the process. For extra certainty, restart your computer, but it should not be needed unless some background process is stuck or you are unsure how to reload it.

Move the .pth files from the AI models folder
```ControlNet-v1-1```
To the folder at
```stable-diffusion-webui\extensions\sd-webui-controlnet\models```

Also ensure that each .pth file has a matching .yaml file (the names must be the same except for the extension)

![image](https://user-images.githubusercontent.com/22615608/234105622-8b391fdc-2885-4854-b143-d1b20b456e78.png)

Right click and edit the launch file
```stable-diffusion-webui\webui-user.bat```

Change the line
```set COMMANDLINE_ARGS=```
to read:
```set COMMANDLINE_ARGS= --api```

You can undo this anytime to disable api access. Just ensure you close and relaunch. You can still access the Web UI with API access on, but it is not recommended.

![image](https://user-images.githubusercontent.com/22615608/234108398-150ac601-199c-4071-b9a3-d047b3ec9d7c.png)

## Usage

Launch the Web UI as normal with
```stable-diffusion-webui\webui-user.bat```

Note: You need to wait until the "Startup time:" is shown in the terminal before it is ready to be used.

Launch the file
```SdPaint\Start.bat```
Run the Start.bat file and it will create a venv and install a few packages the very first time. Then it will open the canvas.

![image](https://user-images.githubusercontent.com/22615608/234108003-a0fe4045-eb12-4225-8edf-1072d1ec5566.png)

With the basics ready, it is two terminal windows running the processes, and the once SD Paint program window. You can safely minimize the termial windows, but remember to close them when you are done to free up system memory.

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
