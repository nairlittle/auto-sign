from io import BytesIO

from PIL import Image


def rm_transparent(img_bytes: bytes) -> bytes:
    image = Image.open(BytesIO(img_bytes))
    background = Image.new("RGB", image.size, (255, 255, 255))
    merged = Image.composite(image, background, image)

    buffer = BytesIO()
    merged.save(buffer, format="PNG")
    return buffer.getvalue()


def normalize_captcha(img_bytes: bytes) -> bytes:
    image = Image.open(BytesIO(img_bytes)).convert("RGB")
    width, height = image.size
    resized = image.resize((width * 2, height * 2))

    buffer = BytesIO()
    resized.save(buffer, format="PNG")
    return buffer.getvalue()
