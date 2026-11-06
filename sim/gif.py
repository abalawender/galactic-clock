"""Animated GIF output for simulator frames. Requires Pillow (only used when
--gif is passed; play/record text modes stay dependency-free)."""


def fb_to_image(fb, scale):
    from PIL import Image
    h = len(fb)
    w = len(fb[0])
    img = Image.new("RGB", (w, h))
    img.putdata([p for row in fb for p in row])
    if scale != 1:
        img = img.resize((w * scale, h * scale), Image.NEAREST)
    return img


def write_gif(fbs, path, scale=8, delay_ms=200, texts=()):
    """fbs: list of framebuffers (H rows x W cols of (r, g, b)).
    texts: iterable of (x, y, string) drawn on every frame, in scaled px."""
    from PIL import ImageDraw
    imgs = [fb_to_image(fb, scale) for fb in fbs]
    if texts:
        for img in imgs:
            dr = ImageDraw.Draw(img)
            for x, y, s in texts:
                dr.text((x, y), s, fill=(255, 255, 255))
    imgs[0].save(path, save_all=True, append_images=imgs[1:],
                 duration=delay_ms, loop=0)
    return path
