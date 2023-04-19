# SdPaint
A simple python script that lets you paint on a canvas and sends that image every stroke to the automatic1111 API and updates the canvas when the image is generated

## Controls

| Key / Mouse button                  | Control                          |
|-------------------------------------|----------------------------------|
| Left button                         | Draw with the current brush size |
| Scroll up / down                    | Increase / decrease brush size   |
| Middle button, or `e` + Left button | Eraser                           |
| `shift` + Left button               | Draw a line                      |
| `s`                                 | Save the current generated image |
| `RETURN` or `ENTER`                 | Force image rendering            |
| `UP` / `DOWN`                       | Increase / decrease seed by 1    |
| `n`                                 | Random seed value                |
| `x` or `ESC`                        | Quit                             |


## Installation

Run the Start.bat file and it will create a venv and install a few packages

## Usage

Make sure you have the [automatic1111 webui](https://github.com/AUTOMATIC1111/stable-diffusion-webui) in API mode running in the background and that you have the controlnet extension installed and activated
To start the webui with the API enabled modify the webui-user.bat file by adding ```--api``` after ```set COMMANDLINE_ARGS=```
You also need to make sure the "Allow other script to control this extension" option is enabled in the settings of control net

You can modify the payload.json file for a different prompt, seed or different controlnet model.
When you save the json file the program will use it after the next brush stroke.
in the extra folder there are the names of different controlnet models you may have.
replace this part ```"control_sd15_scribble [fef5e48e]",``` in the Payload.json with a different one from the modelnames.txt
left mouse to draw and middlemouse to erase
press backspace to erase the image.
the program is bound to 512x512 images right now
I may add more features at a later time.
If you want to add aditional models into your controlnet extension you can do so by adding the model folder into the models folder of the controlnet extension.
```bash
    ".\stable-diffusion-webui\extensions\sd-webui-controlnet\models"
```


## Contributing

Pull requests are welcome. For major changes, please open an issue first
to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License

[MIT](https://choosealicense.com/licenses/mit/)