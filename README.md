# SdPaint
A simple python script that lets you paint on a canvas and sends that image every stroke to the automatic1111 API and updates the canvas when the image is generated

## Updates

- Added the possibility to save the image created by pressing the ```s``` key
- You can use the scrollmouse key to change the brush size

## Installation

Assuming you started from no experience with SD, and some experience with GitHub.

Clone:

The Tool
```https://github.com/houseofsecrets/SdPaint```
The SD interface, installs all other SD components
```https://github.com/AUTOMATIC1111/stable-diffusion-webui```
The AI models
```https://huggingface.co/lllyasviel/ControlNet-v1-1```

Run the Web UI by doube clicking the file 
```stable-diffusion-webui\webui-user.bat```

The first time will also install SD so you can use this independently if you wish.

In the Web UI, add the extension from
```https://github.com/Mikubill/sd-webui-controlnet```

Reload UI

In the settings of the Web UI, look for "Allow other script to control this extension" and enable it. Apply settings.

Close the Web UI and the terminal window running the process. For extra certainty, restart your computer, but it should not be needed unless some background process is stuck or you are unsure how to reload it.

Move the .pth files from the AI models folder
```ControlNet-v1-1```
To the folder at
```stable-diffusion-webui\extensions\sd-webui-controlnet\models```

Right click and edit the file 
```stable-diffusion-webui\webui-user.bat```

Change the line
```set COMMANDLINE_ARGS=```
to read:
```set COMMANDLINE_ARGS= --api```

You can undo this anytime to disable api access. Just ensure you close and relaunch. You can still access the Web UI with API access on, but it is not recommended.

## Usage

Launch the file 
```stable-diffusion-webui\webui-user.bat```
Note: You need to wait until the "Startup time:" is shown before it is ready to be used, but you can launch SdPaint while the web ui loads.

Launch the file
```SdPaint\Start.bat```
Run the Start.bat file and it will create a venv and install a few packages the very first time. Then it will open the canvas.

Right click and edit the file
```SdPaint\payload.json```

This contains your prompt parameters. For beginners, the following is the primary things you need to worry about:
  prompt
  negative_prompt
  model

A list of the working models you downloaded for convenience can be found in
```SdPaint\extra\Modelnames.txt```

Save this file after making your changes. You don't need to close this file or any program when you make changes, just save it. The changes will take effect after the next brush stroke or erasure, basically the next time SdPaint queries the API.

## Controls

```Left Mouse``` to draw
```Scroll Wheel``` to change the draw size
```Middle Mouse``` to erase - fixed size in present version
```Backspace``` to erase the entire image
```S``` to save the output image. Give it a name and location to save to.

## Limitations

The program is bound to 512x512 images right now. 
The drawing canvas is very simple. Only functionality currently in #Controls is working.
It is not presently possible to save or load drawings into the canvas.

## Contributing

Pull requests are welcome. For major changes, please open an issue first
to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License

[MIT](https://choosealicense.com/licenses/mit/)
