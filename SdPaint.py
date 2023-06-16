import argparse

from scripts.views.PygameView import PygameView

# Read command-line arguments
if __name__ == '__main__':
    argParser = argparse.ArgumentParser()
    argParser.add_argument("--img2img", help="img2img mode", action="store_true")
    argParser.add_argument("--source", help="img2img source file", default="#")

    args = argParser.parse_args()

    img2img = args.img2img
    source = args.source
    if img2img:
        img2img = source

    view = PygameView(img2img)
    view.main()
