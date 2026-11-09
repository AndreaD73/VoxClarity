"""Draw the VoxClarity icon (icon.ico) and write the matching icon.svg."""
from pathlib import Path
from PIL import Image, ImageDraw

HERE = Path(__file__).parent
BARS = [0.30, 0.55, 0.85, 0.55, 0.38]
SVG = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256"><defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
       '<stop offset="0" stop-color="#6a7bff"/><stop offset="1" stop-color="#37d4c4"/></linearGradient></defs>'
       '<rect width="256" height="256" rx="56" fill="#12151c"/>' +
       "".join(f'<rect x="{46 + i * 36}" y="{128 - h * 90}" width="22" height="{h * 180}" rx="11" fill="url(#g)"/>'
               for i, h in enumerate(BARS)) + "</svg>")
(HERE / "ui" / "icon.svg").write_text(SVG, encoding="utf-8")
S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.rounded_rectangle((0, 0, S - 1, S - 1), 56, fill=(18, 21, 28, 255))
for i, h in enumerate(BARS):
    t = i / 4
    col = (int(106 + (55 - 106) * t), int(123 + (212 - 123) * t), int(255 + (196 - 255) * t), 255)
    d.rounded_rectangle((46 + i * 36, 128 - h * 90, 68 + i * 36, 128 + h * 90), 11, fill=col)
img.save(HERE / "icon.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
