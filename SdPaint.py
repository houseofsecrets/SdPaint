import argparse

from scripts.views.PygameView import PygameView

# Read command-line arguments
if __name__ == '__main__':
    argParser = argparse.ArgumentParser()
    argParser.add_argument("--img2img", help="img2img source file")

    args = argParser.parse_args()

    img2img = args.img2img
    if img2img == '':
        img2img = '#'  # force load file dialog if launched with --img2img without value

    view = PygameView(img2img)
    view.main()
