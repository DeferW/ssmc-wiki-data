from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from PIL import Image


def texture_path(game_source: Path, sprite_path: str) -> Path:
    normalized = sprite_path.replace("\\", "/").lstrip("/")
    if normalized.startswith("Textures/"):
        normalized = normalized[len("Textures/") :]
    return game_source / "Resources/Textures" / normalized


def first_rsi_state(
    meta: dict[str, Any],
    sprite_path: str = "",
    requested: str | None = None,
    prefer_closed: bool = False,
) -> str | None:
    states = meta.get("states")
    if not isinstance(states, list):
        return None
    names = [
        state["name"]
        for state in states
        if isinstance(state, dict) and isinstance(state.get("name"), str)
    ]
    stem = Path(sprite_path).stem.casefold()
    folded = {name.casefold(): name for name in names}
    if prefer_closed and isinstance(requested, str) and (
        "open" in requested.casefold() or "empty" in requested.casefold()
    ):
        closed_candidates: list[str] = []
        requested_folded = requested.casefold()
        closed_candidates.extend(
            (
                requested_folded.replace("opened", "closed").replace("empty", "closed"),
                requested_folded.replace("open", "closed").replace("empty", "closed"),
                re.sub(r"(?:^|[-_])(?:open(?:ed)?|empty)(?:$|[-_])", "", requested_folded).strip("-_"),
            )
        )
        closed_candidates.extend(("closed", "icon", "item", "default", stem, "base", "idle", "full"))
        for candidate in closed_candidates:
            if candidate and candidate in folded:
                return folded[candidate]
    if requested in names:
        return requested
    preferred = (
        ("closed", "icon", "item", "default", stem, "base", "idle", "full")
        if prefer_closed
        else ("icon", "item", "default", stem, "base", "idle", "closed", "full")
    )
    for candidate in preferred:
        if candidate and candidate in folded:
            return folded[candidate]
    non_equipped = [
        name
        for name in names
        if not any(
            marker in name.casefold()
            for marker in (
                "inhand",
                "equipped",
                "-left",
                "-right",
                "-front",
                "-back",
            )
        )
    ]
    return (non_equipped or names or [None])[0]


def load_sprite_frame(
    game_source: Path,
    sprite_path: str,
    state: str | None,
    prefer_closed: bool = False,
) -> Image.Image:
    source = texture_path(game_source, sprite_path)
    if source.suffix.lower() != ".rsi":
        if not source.is_file():
            raise FileNotFoundError(f"Missing sprite texture: {source}")
        return Image.open(source).convert("RGBA")

    meta_path = source / "meta.json"
    if not meta_path.is_file():
        raise FileNotFoundError(f"Missing RSI metadata: {meta_path}")
    meta = json.loads(meta_path.read_text(encoding="utf-8-sig"))
    if not isinstance(meta, dict):
        raise RuntimeError(f"Invalid RSI metadata: {meta_path}")

    selected_state = first_rsi_state(
        meta,
        sprite_path,
        state,
        prefer_closed=prefer_closed,
    )
    if not selected_state:
        raise RuntimeError(f"RSI has no states: {meta_path}")
    state_path = source / f"{selected_state}.png"
    if not state_path.is_file():
        raise FileNotFoundError(f"Missing RSI state {selected_state}: {meta_path}")
    sheet = Image.open(state_path).convert("RGBA")

    size = meta.get("size", {})
    width = size.get("x") if isinstance(size, dict) else None
    height = size.get("y") if isinstance(size, dict) else None
    if not isinstance(width, int) or not isinstance(height, int):
        width, height = sheet.height, sheet.height
    return sheet.crop((0, 0, min(width, sheet.width), min(height, sheet.height)))
