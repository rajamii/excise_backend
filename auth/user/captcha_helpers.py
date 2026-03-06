import random

from captcha.conf import settings as captcha_settings


def noise_dots_light(draw, image):
    """Low-density dot noise so captcha stays readable."""
    width, height = image.size
    dot_count = max(18, int(width * height * 0.03))

    for _ in range(dot_count):
        draw.point(
            (random.randint(0, width - 1), random.randint(0, height - 1)),
            fill=captcha_settings.CAPTCHA_FOREGROUND_COLOR,
        )
    return draw


def random_letter_color_dark(_idx, _plaintext_captcha):
    """Random per-letter color with strong contrast for readability."""
    return "#{:02X}{:02X}{:02X}".format(
        random.randint(20, 120),
        random.randint(20, 120),
        random.randint(20, 120),
    )
