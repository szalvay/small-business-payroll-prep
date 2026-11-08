#!/usr/bin/env python3
"""Render the README banner and icon in the Duotone Tape look (navy panel, yellow hook
words, one thin orange stripe, Anton + Oswald, square corners).

Needs Pillow and the Anton and Oswald fonts (free on Google Fonts):
    python3 tools/make_brand_images.py --fonts /path/to/fonts
"""
import argparse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

NAVY, ORANGE, YELLOW, CREAM, WHITE = "#141034", "#E58700", "#F8D300", "#F6ECD4", "#FFFFFF"
OUT = Path(__file__).resolve().parents[1] / "docs" / "images"


def font(folder, name, size):
    return ImageFont.truetype(str(Path(folder) / name), size)


def words(draw, x, y, parts, fnt, gap):
    """Draw [(text, color), ...] left to right on one baseline."""
    for text, color in parts:
        draw.text((x, y), text, font=fnt, fill=color)
        x += draw.textlength(text, font=fnt) + gap
    return x


def banner(fonts):
    w, h = 1600, 520
    img = Image.new("RGB", (w, h), NAVY)
    d = ImageDraw.Draw(img)
    pad = 80
    mark = font(fonts, "Anton-Regular.ttf", 46)
    words(d, pad, 64, [("SALON & SPA", WHITE), ("PAYROLL", YELLOW), ("PREP", WHITE)], mark, 14)
    hook = font(fonts, "Anton-Regular.ttf", 104)
    words(d, pad, 150, [("CATCH THE", WHITE), ("ERRORS", YELLOW), ("AND", WHITE)], hook, 26)
    words(d, pad, 272, [("OMISSIONS", YELLOW), ("BEFORE PAYDAY", WHITE)], hook, 26)
    label = font(fonts, "Oswald-Medium.ttf", 30)
    d.text((pad, 420), "An open-source Claude skill for multi-location salons and spas  ·  piece rate, commissions, tips, overtime",
           font=label, fill=CREAM)
    d.rectangle([0, h - 12, w, h], fill=ORANGE)
    img.save(OUT / "banner.png", optimize=True)


def icon(fonts):
    s = 512
    img = Image.new("RGB", (s, s), NAVY)
    d = ImageDraw.Draw(img)
    big = font(fonts, "Anton-Regular.ttf", 210)
    t = "PAY"
    tw = d.textlength(t, font=big)
    d.text(((s - tw) / 2, 70), t, font=big, fill=YELLOW)
    small = font(fonts, "Anton-Regular.ttf", 92)
    t2 = "PREP"
    d.text(((s - d.textlength(t2, font=small)) / 2, 318), t2, font=small, fill=WHITE)
    d.rectangle([96, 452, s - 96, 464], fill=ORANGE)
    img.save(OUT / "icon.png", optimize=True)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--fonts", required=True, help="folder with Anton-Regular.ttf and Oswald-Medium.ttf")
    a = ap.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    banner(a.fonts)
    icon(a.fonts)
    print(f"wrote {OUT / 'banner.png'} and {OUT / 'icon.png'}")
