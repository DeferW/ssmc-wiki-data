from __future__ import annotations

import copy
import hashlib
import json
import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from PIL import Image, ImageChops, ImageColor


def layer_map_names(layer: dict[str, Any]) -> set[str]:
    value = layer.get("map")
    if isinstance(value, str):
        return {value}
    if isinstance(value, list):
        return {item for item in value if isinstance(item, str)}
    return set()


def apply_static_preview_states(
    components: dict[str, Any],
    layers: list[dict[str, Any]],
) -> None:
    """Choose the spawn-time state for layers normally updated by game systems."""
    magazine_visuals = components.get("MagazineVisuals")
    if not isinstance(magazine_visuals, dict):
        return
    mag_state = magazine_visuals.get("magState")
    steps = magazine_visuals.get("steps")
    if not isinstance(mag_state, str) or not isinstance(steps, int) or steps <= 0:
        return
    full_state = f"{mag_state}-{max(steps - 1, 0)}"
    for layer in layers:
        if "enum.GunVisualLayers.Mag" in layer_map_names(layer):
            layer["state"] = full_state
            layer["visible"] = True


def apply_closed_container_preview(layers: list[dict[str, Any]]) -> None:
    """Mirror the closed item icon used by vendors, not the opened UI state."""
    for layer in layers:
        maps = {name.casefold() for name in layer_map_names(layer)}
        if any(
            name in {"open", "empty"}
            or "openlayer" in name
            or "emptylayer" in name
            for name in maps
        ):
            layer["visible"] = False
        if any(
            name in {"closed", "full", "lid"}
            or "closedlayer" in name
            for name in maps
        ):
            layer["visible"] = True


def solution_preview_summary(components: dict[str, Any]) -> dict[str, Any] | None:
    visuals = components.get("SolutionContainerVisuals")
    manager = components.get("SolutionContainerManager")
    if not isinstance(visuals, dict) or not isinstance(manager, dict):
        return None
    solutions = manager.get("solutions")
    if not isinstance(solutions, dict) or not solutions:
        return None
    solution_name = visuals.get("solutionName")
    if not isinstance(solution_name, str) or solution_name not in solutions:
        solution_name = next(iter(solutions))
    solution = solutions.get(solution_name)
    if not isinstance(solution, dict):
        return None
    raw_reagents = solution.get("reagents")
    reagents: list[dict[str, Any]] = []
    if isinstance(raw_reagents, list):
        for entry in raw_reagents:
            if not isinstance(entry, dict):
                continue
            reagent_id = entry.get("ReagentId")
            quantity = entry.get("Quantity")
            if isinstance(reagent_id, str) and isinstance(quantity, (int, float)):
                reagents.append({"id": reagent_id, "quantity": quantity})
    elif isinstance(raw_reagents, dict):
        for reagent_id, quantity in raw_reagents.items():
            if isinstance(reagent_id, str) and isinstance(quantity, (int, float)):
                reagents.append({"id": reagent_id, "quantity": quantity})
    volume = sum(
        float(entry["quantity"])
        for entry in reagents
        if isinstance(entry.get("quantity"), (int, float))
    )
    max_volume = solution.get("maxVol")
    if not isinstance(max_volume, (int, float)) or max_volume <= 0:
        max_volume = volume
    result = {
        "layerMap": str(
            visuals.get("layer", "enum.SolutionContainerLayers.Fill")
        ),
        "fillBaseName": visuals.get("fillBaseName"),
        "emptySpriteName": visuals.get("emptySpriteName"),
        "maxFillLevels": visuals.get("maxFillLevels", 1),
        "changeColor": visuals.get("changeColor", True),
        "fillFraction": min(max(volume / max_volume, 0), 1) if max_volume else 0,
        "reagents": reagents,
    }
    return result


def sprite_summary(components: dict[str, Any]) -> dict[str, Any] | None:
    sprite = components.get("Sprite")
    if not isinstance(sprite, dict):
        sprite = components.get("Icon")
    if not isinstance(sprite, dict):
        sprite = {}
    result: dict[str, Any] = {}
    if isinstance(sprite.get("sprite"), str):
        result["sprite"] = sprite["sprite"]
    elif isinstance(sprite.get("texture"), str):
        result["sprite"] = sprite["texture"]
    if isinstance(sprite.get("state"), str):
        result["state"] = sprite["state"]
    if "sprite" not in result:
        item_sprite = components.get("Item", {}).get("sprite")
        if isinstance(item_sprite, str):
            result["sprite"] = item_sprite
    layers = sprite.get("layers")
    if isinstance(layers, list):
        clean_layers = [
            copy.deepcopy(layer) for layer in layers if isinstance(layer, dict)
        ]
        if clean_layers:
            if (
                "StorageFill" in components
                or "ContainerFill" in components
                or "Storage" in components
            ):
                apply_closed_container_preview(clean_layers)
            apply_static_preview_states(components, clean_layers)
            result["layers"] = clean_layers
            if "state" not in result:
                for layer in clean_layers:
                    state = layer.get("state")
                    if isinstance(state, str):
                        result["state"] = state
                        break
    solution_preview = solution_preview_summary(components)
    if solution_preview:
        result["solutionPreview"] = solution_preview
    if (
        "StorageFill" in components
        or "ContainerFill" in components
        or "Storage" in components
    ):
        # Vending UIs show the spawn/closed appearance. Runtime visualizers can
        # otherwise leave a crate or grenade box on its open state in the wiki.
        result["preferClosed"] = True
    return result or None


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


def tint_sprite_layer(image: Image.Image, color_value: Any) -> Image.Image:
    if not isinstance(color_value, str):
        return image
    try:
        red, green, blue, alpha = ImageColor.getcolor(color_value, "RGBA")
    except ValueError as error:
        raise RuntimeError(f"Unsupported sprite layer color: {color_value}") from error

    rgb = ImageChops.multiply(
        image.convert("RGB"),
        Image.new("RGB", image.size, (red, green, blue)),
    )
    source_alpha = image.getchannel("A")
    if alpha != 255:
        source_alpha = ImageChops.multiply(
            source_alpha,
            Image.new("L", image.size, alpha),
        )
    return Image.merge("RGBA", (*rgb.split(), source_alpha))


def layer_offset_pixels(layer: dict[str, Any], width: int, height: int) -> tuple[int, int]:
    value = layer.get("offset")
    if isinstance(value, str):
        parts = [part.strip() for part in value.split(",")]
    elif isinstance(value, (list, tuple)):
        parts = list(value)
    else:
        return 0, 0
    if len(parts) != 2:
        return 0, 0
    try:
        x = float(parts[0])
        y = float(parts[1])
    except (TypeError, ValueError):
        return 0, 0
    return round(x * width), round(-y * height)


def mixed_reagent_color(
    reagents: list[dict[str, Any]],
    reagent_colors: dict[str, str],
) -> str | None:
    weighted: list[tuple[tuple[int, int, int, int], float]] = []
    for entry in reagents:
        reagent_id = entry.get("id")
        quantity = entry.get("quantity")
        color = reagent_colors.get(str(reagent_id))
        if not isinstance(quantity, (int, float)) or quantity <= 0 or not color:
            continue
        try:
            weighted.append((ImageColor.getcolor(color, "RGBA"), float(quantity)))
        except ValueError:
            continue
    total = sum(quantity for _, quantity in weighted)
    if total <= 0:
        return None
    channels = tuple(
        round(sum(color[index] * quantity for color, quantity in weighted) / total)
        for index in range(4)
    )
    return "#" + "".join(f"{channel:02x}" for channel in channels)


def apply_solution_preview(
    summary: dict[str, Any],
    layers: list[dict[str, Any]],
    reagent_colors: dict[str, str],
) -> None:
    preview = summary.get("solutionPreview")
    if not isinstance(preview, dict):
        return
    fraction = preview.get("fillFraction")
    max_levels = preview.get("maxFillLevels")
    if not isinstance(fraction, (int, float)):
        return
    if not isinstance(max_levels, int) or max_levels <= 0:
        max_levels = 1
    level = min(max(math.ceil(float(fraction) * max_levels), 0), max_levels)
    map_name = str(preview.get("layerMap", "enum.SolutionContainerLayers.Fill"))
    color = mixed_reagent_color(preview.get("reagents", []), reagent_colors)
    for layer in layers:
        maps = layer_map_names(layer)
        if map_name not in maps and "enum.SolutionContainerLayers.Fill" not in maps:
            continue
        if level <= 0:
            empty_state = preview.get("emptySpriteName")
            if isinstance(empty_state, str):
                layer["state"] = empty_state
                layer["visible"] = True
            else:
                layer["visible"] = False
            continue
        fill_base = preview.get("fillBaseName")
        if isinstance(fill_base, str):
            layer["state"] = f"{fill_base}{level}"
        layer["visible"] = True
        if preview.get("changeColor", True) and color:
            layer["color"] = color
        else:
            layer.pop("color", None)


def render_sprite_preview(
    game_source: Path,
    summary: dict[str, Any],
    reagent_colors: dict[str, str],
) -> Image.Image:
    base_sprite = summary.get("sprite")
    layers = summary.get("layers")
    render_layers: list[dict[str, Any]] = []

    if isinstance(layers, list):
        prepared_layers = [copy.deepcopy(layer) for layer in layers if isinstance(layer, dict)]
        apply_solution_preview(summary, prepared_layers, reagent_colors)
        for layer in prepared_layers:
            if not isinstance(layer, dict) or layer.get("visible") is False:
                continue
            layer_sprite = layer.get("sprite", base_sprite)
            layer_state = layer.get("state")
            if isinstance(layer_sprite, str):
                # A layer without a state is an initially empty visualizer slot.
                # Reusing Sprite.state here produced unrelated duplicate artwork.
                if not isinstance(layer_state, str):
                    continue
                rendered = copy.deepcopy(layer)
                rendered["sprite"] = layer_sprite
                rendered["state"] = layer_state
                render_layers.append(rendered)
            elif isinstance(layer.get("texture"), str):
                rendered = copy.deepcopy(layer)
                rendered["sprite"] = layer["texture"]
                rendered["state"] = None
                render_layers.append(rendered)

    if not render_layers and isinstance(base_sprite, str):
        state = summary.get("state")
        render_layers.append(
            {
                "sprite": base_sprite,
                "state": state if isinstance(state, str) else None,
            }
        )
    if not render_layers:
        raise RuntimeError("Sprite component has no renderable texture")

    images: list[tuple[Image.Image, dict[str, Any]]] = []
    for layer in render_layers:
        image = load_sprite_frame(
            game_source,
            layer["sprite"],
            layer.get("state"),
            prefer_closed=summary.get("preferClosed") is True,
        )
        image = tint_sprite_layer(image, layer.get("color"))
        images.append((image, layer))
    width = max(image.width for image, _ in images)
    height = max(image.height for image, _ in images)
    preview = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    for image, layer in images:
        offset_x, offset_y = layer_offset_pixels(layer, width, height)
        x = (width - image.width) // 2 + offset_x
        y = (height - image.height) // 2 + offset_y
        preview.alpha_composite(image, (x, y))
    return preview


def render_public_sprites(
    game_source: Path,
    output_dir: Path,
    items: dict[str, Any],
    public_item_ids: list[str],
    reagent_colors: dict[str, str],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    expected: set[str] = set()
    failures: list[str] = []
    solution_images: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for item_id in public_item_ids:
        item = items[item_id]
        summary = item.get("sprite")
        if not isinstance(summary, dict):
            # Some configured vendor entries are selection wrappers rather than
            # drawable entities. They remain public, with the site's normal
            # missing-sprite placeholder, so "publish everything" stays true.
            item.pop("image", None)
            continue
        filename = f"{item_id}.png"
        expected.add(filename)
        try:
            preview = render_sprite_preview(game_source, summary, reagent_colors)
            preview.save(output_dir / filename, format="PNG", optimize=True)
            summary["file"] = filename
            item["image"] = f"sprites/{filename}"
            solution = summary.get("solutionPreview")
            if isinstance(solution, dict) and solution.get("reagents"):
                signature = json.dumps(
                    solution.get("reagents"), ensure_ascii=False, sort_keys=True
                )
                digest = hashlib.sha256(preview.tobytes()).hexdigest()
                solution_images[digest].append((item_id, signature))
        except Exception as error:  # Collect every missing/broken sprite in one run.
            failures.append(f"{item_id}: {error}")

    for path in output_dir.glob("*.png"):
        if path.name not in expected:
            path.unlink()
    if failures:
        raise RuntimeError("Unable to render equipment sprites:\n" + "\n".join(failures))
    ambiguous = [
        sorted(item_id for item_id, _ in entries)
        for entries in solution_images.values()
        if len({signature for _, signature in entries}) > 1
    ]
    if ambiguous:
        raise RuntimeError(
            "Different filled solutions rendered as identical sprites:\n"
            + "\n".join(", ".join(group) for group in ambiguous)
        )
