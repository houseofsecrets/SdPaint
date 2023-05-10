import os
import re


def delete_image(file_path):
    """
        Delete an image file, and associated sketch file if existing.
    :param str file_path: The file path.
    """

    file_name, file_ext = os.path.splitext(file_path)

    if os.path.exists(file_path):
        os.remove(file_path)

    if os.path.exists(f"{file_name}-sketch{file_ext}"):
        os.remove(f"{file_name}-sketch{file_ext}")


def rename_image(src_path, dest_path):
    """
        Rename an image file, and associated sketch file if existing.
    :param str src_path: The source file path.
    :param str dest_path: The destination file path.
    """

    src_name, src_ext = os.path.splitext(src_path)
    dest_name, dest_ext = os.path.splitext(dest_path)

    if not os.path.exists(src_path):
        return

    delete_image(dest_path)

    os.rename(src_path, dest_path)

    if os.path.exists(f"{src_name}-sketch{src_ext}"):
        os.rename(f"{src_name}-sketch{src_ext}", f"{dest_name}-sketch{dest_ext}")


def autosave_cleanup(state, images_type):
    """
        Cleanup the autosave files.
    :param str images_type: Images type to cleanup. ``[single, batch]``
    :return:
    """

    file_path = os.path.join("outputs", "autosave")
    if not os.path.exists(file_path):
        return

    if images_type == 'batch':
        image_pattern = re.compile(r"(\d+)-(batch-\d+).png")
    else:
        image_pattern = re.compile(r"(\d+)-(image).png")

    files_list = list(os.listdir(file_path))
    for file in sorted(files_list, reverse=True):
        m = image_pattern.match(file)
        if m:
            if int(m.group(1)) >= state.autosave["images_max"]:
                delete_image(os.path.join(file_path, file))
            else:
                rename_image(os.path.join(file_path, file), os.path.join(file_path, f"{int(m.group(1))+1:02d}-{m.group(2)}.png"))


def autosave_image(state, image_bytes):
    """
        Auto save image(s) in the output dir.
    :param io.BytesIO|list[io.BytesIO] image_bytes: The image(s) data.
    """

    file_path = "outputs"
    if state.autosave["images_max"] > 0 and not os.path.exists(os.path.join(file_path, "autosave")):
        os.makedirs(os.path.join(file_path, "autosave"))

    if isinstance(image_bytes, list):
        autosave_cleanup(state, "batch")
        batch_image_pattern = re.compile(r"batch-\d+(-sketch)?.png")

        for f in os.listdir(file_path):
            if not batch_image_pattern.match(f) or os.path.isdir(os.path.join(file_path, f)):
                continue

            if state.autosave["images_max"] > 0:
                rename_image(os.path.join(file_path, f), os.path.join(file_path, "autosave", f"01-{f}"))

        file_names = []
        for i in range(len(image_bytes)):
            file_name = f"batch-{i+1:02d}.png"
            file_names.append(os.path.join(file_path, file_name))
            save_image(os.path.join(file_path, file_name), image_bytes[i])
        return file_names
    else:
        autosave_cleanup(state, "single")

        file_name = f"image.png"
        if os.path.exists(os.path.join(file_path, file_name)) and state.autosave["images_max"] > 0:
            rename_image(os.path.join(file_path, file_name), os.path.join(file_path, "autosave", f"01-{file_name}"))

        save_image(os.path.join(file_path, file_name), image_bytes)
        return os.path.join(file_path, file_name)


def save_image(file_path, image_bytes):
    """
        Save an image file to disk.
    :param str file_path: The file path.
    :param io.BytesIO image_bytes: The image data.
    :param bool save_sketch: Save the sketch alongside the image.
    """

    file_dir = os.path.dirname(file_path)
    if not os.path.exists(file_dir):
        os.makedirs(file_dir)

    # save last rendered image
    with open(file_path, "wb") as image_file:
        image_file.write(image_bytes.getbuffer().tobytes())