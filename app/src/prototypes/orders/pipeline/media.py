#!/usr/bin/env python3
"""Make small renditions of the heavy media a homepage shows.

    python3 pipeline/media.py <company>

Writes smaller renditions to `<cache>/<company>/replace/<same path>`. The build publishes a
rendition under the original URL, so the page itself stays as the company wrote it.
  shrink   each listed video becomes H.264 at the given width, with the sound left out (a hero
           video plays muted) and the index at the front so it starts at once
  photos   each category's product photo, as the catalogue names it, is fitted to the given width

Reads   <cache>/<company>/site/<path>
Writes  <cache>/<company>/replace/<path>
Needs   ffmpeg on PATH for videos and Pillow for photos. With a tool absent the command says so
        and the build leaves those files out or publishes them as they are.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pipeline import catalog, common, homepage  # noqa: E402


def video(source: Path, target: Path, options: dict) -> None:
    rate = str(options.get("maxrate", "700k"))
    doubled = f"{int(rate[:-1]) * 2}{rate[-1]}" if rate[:-1].isdigit() else rate
    subprocess.run(
        ["ffmpeg", "-nostdin", "-loglevel", "error", "-y", "-i", str(source), "-an",
         "-vf", f"scale={int(options.get('width', 1280))}:-2", "-c:v", "libx264", "-preset", "slow",
         "-crf", str(int(options.get("crf", 31))), "-maxrate", rate, "-bufsize", doubled,
         "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(target)],
        check=True,
    )


def photo(source: Path, target: Path, options: dict) -> None:
    from PIL import Image

    width, quality = int(options.get("width", 960)), int(options.get("quality", 80))
    with Image.open(source) as image:
        kind = image.format
        if image.width > width:
            image = image.resize((width, round(image.height * width / image.width)), Image.LANCZOS)
        if kind == "JPEG":
            image.convert("RGB").save(target, "JPEG", quality=quality, optimize=True, progressive=True)
        else:
            image.save(target, kind, optimize=True)


def photos(config: dict, site: Path) -> int:
    """Renditions of the catalogue's product photos. Returns the bytes they came to."""
    options = config.get("photos")
    if not options:
        return 0
    before = after = 0
    paths = sorted(catalog.photos(catalog.build(config, site)[0]))
    for path in paths:
        source, target = site / path, site.parent / "replace" / path
        if not source.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(".part-" + target.name)
        photo(source, partial, options)
        partial.replace(target)
        before, after = before + source.stat().st_size, after + target.stat().st_size
    print(f"{len(paths)} product photos: {before / 1e6:.1f} MB -> {after / 1e6:.2f} MB at {options.get('width', 960)} px")
    return after


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip())
        return 2
    config = common.company(argv[1])
    site = common.site_dir(config["slug"])
    photos(config, site)
    wanted = config.get("shrink") or {}
    if not wanted:
        return 0
    if not shutil.which("ffmpeg"):
        print("ffmpeg is absent from PATH: install it, or the build leaves these files out")
        return 1
    for path, options in wanted.items():
        source = site / path
        if not source.is_file():
            raise SystemExit(f"{config['slug']}: {source} is missing from the mirror")
        target = site.parent / "replace" / path
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part" + target.suffix)
        video(source, partial, options)
        partial.replace(target)
        before, after = source.stat().st_size, target.stat().st_size
        fits = "fits" if after <= homepage.FILE_BYTES else "is still over the per-file limit: lower width or maxrate"
        print(f"{path}: {before / 1e6:.1f} MB -> {after / 1e6:.2f} MB ({fits})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
