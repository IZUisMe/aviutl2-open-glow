"""Build the AviUtl2 installer ZIP using the same layout as r1/r2."""
from pathlib import Path
import hashlib
import re
import zipfile

root = Path(__file__).resolve().parents[1]
source = (root / "OpenGlow.anm2").read_text(encoding="utf-8")
version = re.search(r"^--information:Open Glow (r\d+) ", source).group(1)
metadata = (root / "packaging/package.ini").read_text(encoding="utf-8")
if f"information=Open Glow {version} by " not in metadata:
    raise SystemExit("Script and package versions do not match")
out = root / "dist" / f"aviutl2_script_OpenGlow-{version}.au2pkg.zip"
out.parent.mkdir(exist_ok=True)
files = {
    "Script/OpenGlow.anm2": "OpenGlow.anm2",
    "Script/OpenGlow/LICENSE": "LICENSE",
    "Script/OpenGlow/OpenglowONOFF.gif": "OpenglowONOFF.gif",
    "Script/OpenGlow/README.md": "README.md",
    "package.ini": "packaging/package.ini",
    "package.txt": "packaging/package.txt",
}
with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as archive:
    for target, path in files.items():
        archive.write(root / path, target)
with zipfile.ZipFile(out) as archive:
    assert archive.testzip() is None
    assert archive.namelist() == list(files)
    for target, path in files.items():
        assert archive.read(target) == (root / path).read_bytes()
print(out)
print("SHA256:", hashlib.sha256(out.read_bytes()).hexdigest())
