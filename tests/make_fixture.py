"""Generate disposable AviUtl2 projects for Issue #2 visual verification."""
from pathlib import Path
from PIL import Image, ImageDraw

out = Path(__file__).resolve().parents[1] / ".validation"
out.mkdir(exist_ok=True)
image = Image.new("RGBA", (6251, 4501), (0, 0, 0, 255))
draw = ImageDraw.Draw(image)
for x in (180, 3125, 6070):
    for y in (180, 2250, 4320):
        draw.ellipse((x - 30, y - 30, x + 30, y + 30), fill="white")
image.save(out / "sources.png")
project = """[project]
version=2011000
display.scene=0
preview.scene=0
[scene.0]
scene=0
name=Root
video.width=1920
video.height=1080
video.rate=30
video.scale=1
audio.rate=44100
cursor.frame=0
[0]
layer=0
frame=0,29
[0.0]
effect.name=画像ファイル
ファイル={image}
[0.1]
effect.name=標準描画
拡大率=20.000
[0.2]
effect.name={effect}
強さ=400
拡散=300
減衰=2
しきい値=0
ガンマ=2.2
縦横比={aspect}
角度={angle}
ディザ=1
サイズ固定=1
"""
for name, effect, aspect, angle in (
    ("fixed", "OpenGlowIssue2Test", 0, 0),
    ("rotated", "OpenGlowIssue2Test", 3, 45),
    ("original", "OpenGlow", 0, 0),
):
    (out / f"{name}.aup2").write_text(
        project.format(image=out / "sources.png", effect=effect, aspect=aspect, angle=angle),
        encoding="utf-8",
    )
print(out)
