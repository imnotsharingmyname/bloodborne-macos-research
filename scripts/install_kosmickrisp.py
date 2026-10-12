#!/usr/bin/env python3
"""Install a pinned x86_64 KosmicKrisp artifact into a staged macOS app.

The driver is bundled beside its ICD; no game files are included.
Run before re-signing, re-auditing and repackaging the experimental app.
"""
import argparse
import json
from pathlib import Path
import shutil
import subprocess
import zipfile

def install(archive: Path, app: Path):
    if not (app / "Contents/Helpers/bb-runtime").is_file():
        raise RuntimeError("Expected a fully staged game runtime app")
    with zipfile.ZipFile(archive) as z:
        files = {Path(n).name: n for n in z.namelist() if not n.endswith("/")}
        name = "libvulkan_kosmickrisp.dylib"
        if name not in files:
            raise RuntimeError("KosmicKrisp artifact is missing " + name)
        outdir = app / "Contents/Resources/vulkan/kosmickrisp"
        outdir.mkdir(parents=True, exist_ok=True)
        driver = outdir / name
        with z.open(files[name]) as source, driver.open("wb") as dest:
            shutil.copyfileobj(source, dest)
    archs = subprocess.check_output(["lipo", "-archs", str(driver)], text=True).split()
    if "x86_64" not in archs:
        driver.unlink()
        raise RuntimeError("KosmicKrisp driver has no x86_64 architecture")
    (outdir / "kosmickrisp_mesa_icd.json").write_text(json.dumps({
        "file_format_version": "1.0.0",
        "ICD": {
            "library_path": "./libvulkan_kosmickrisp.dylib",
            "api_version": "1.3.0"
        }
    }, indent=2) + "\n")
    print("Bundled experimental KosmicKrisp driver:", driver)

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("archive", type=Path)
    parser.add_argument("app", type=Path)
    options = parser.parse_args()
    install(options.archive, options.app)
