from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.common.sprites import load_sprite_frame

# Every xeno caste's Sprite component carries an "alive" state (4 walking
# directions); cropping the first WxH block of that state's spritesheet is
# the same "pick a stable default frame" approach the catalog sprite pipeline
# already uses, and it lands on the south-facing frame.
PREVIEW_STATE = "alive"


def sprite_path_from_component(component: dict[str, Any] | None) -> str | None:
    if not isinstance(component, dict):
        return None
    sprite = component.get("sprite")
    return sprite if isinstance(sprite, str) else None


def render_mob_sprites(
    game_source: Path,
    output_dir: Path,
    sprite_paths: dict[str, str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected: set[str] = set()
    failures: list[str] = []

    for caste_id, sprite_path in sprite_paths.items():
        filename = f"{caste_id}.png"
        expected.add(filename)
        try:
            image = load_sprite_frame(game_source, sprite_path, PREVIEW_STATE)
            image.save(output_dir / filename, format="PNG", optimize=True)
        except Exception as error:  # Collect every missing/broken sprite in one run.
            failures.append(f"{caste_id}: {error}")

    for path in output_dir.glob("*.png"):
        if path.name not in expected:
            path.unlink()
    if failures:
        raise RuntimeError("Unable to render xeno sprites:\n" + "\n".join(failures))
