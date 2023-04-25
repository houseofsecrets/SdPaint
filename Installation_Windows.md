
## Installation

These instructions are for getting started with SDPaint on a Windows machine. Assuming you started from no experience with SD, and some experience with GitHub.

Clone:

The Tool
```https://github.com/houseofsecrets/SdPaint```

The AI models
```https://huggingface.co/lllyasviel/ControlNet-v1-1```

Follow the instructions to install the Web UI for Windows. It can be used independatly, and will install Stable Diffusion.
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

You can undo this anytime to disable api access. Just ensure you close and relaunch.

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

Configuration is OS agnostic. See the [README](README.md) for configuration instructions.
