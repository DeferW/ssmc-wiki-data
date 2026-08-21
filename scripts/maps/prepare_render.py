from __future__ import annotations

import argparse
import re
from pathlib import Path


COMPONENT_RE = re.compile(r"^(?P<indent>[ ]*)- type: (?P<type>[^ #\r\n]+)[ ]*(?:#.*)?(?:\r?\n)?$")
ACTORS_RE = re.compile(r"^(?P<indent>[ ]*)actors:[ ]*(?:#.*)?(?:\r?\n)?$")

# These map overrides drive live server state but cannot change the static image.
# Old maps may contain values that no longer exist in current prototypes, causing
# Content.MapRenderer to abort while initializing entities. Strip them from every
# temporary render copy, so the protection also covers newly added maps.
NON_VISUAL_RUNTIME_COMPONENTS = frozenset(
    {
        "ActiveUserInterface",
        "DoorSignalControl",
    }
)


def _indent(line: str) -> int | None:
    if not line.strip():
        return None
    return len(line) - len(line.lstrip(" "))


def sanitize_map_text(text: str) -> tuple[str, int]:
    """Remove serialized UI session state that the headless renderer cannot load.

    UserInterface itself is retained because it can contain static map overrides. Only
    runtime fields and non-visual components that can hold obsolete prototype references
    are removed. The edit is deliberately line based so engine-specific YAML tags are
    left intact instead of being rewritten by a generic YAML dumper.
    """
    lines = text.splitlines(keepends=True)
    result: list[str] = []
    removed = 0
    index = 0

    while index < len(lines):
        line = lines[index]
        component = COMPONENT_RE.match(line)
        if component is None:
            result.append(line)
            index += 1
            continue

        component_indent = len(component.group("indent"))
        component_type = component.group("type")
        if component_type in NON_VISUAL_RUNTIME_COMPONENTS:
            removed += 1
            index += 1
            while index < len(lines):
                next_indent = _indent(lines[index])
                if next_indent is not None and next_indent <= component_indent:
                    break
                index += 1
            continue

        result.append(line)
        index += 1
        if component_type != "UserInterface":
            continue

        while index < len(lines):
            next_indent = _indent(lines[index])
            if next_indent is not None and next_indent <= component_indent:
                break
            actors = ACTORS_RE.match(lines[index])
            if actors is None or len(actors.group("indent")) <= component_indent:
                result.append(lines[index])
                index += 1
                continue

            actors_indent = len(actors.group("indent"))
            removed += 1
            index += 1
            while index < len(lines):
                child_indent = _indent(lines[index])
                if child_indent is not None and child_indent <= actors_indent:
                    break
                index += 1

    return "".join(result), removed


def prepare_render_maps(render_list: Path, output: Path, output_list: Path) -> int:
    sources = [Path(line) for line in render_list.read_text(encoding="utf-8").splitlines() if line]
    output.mkdir(parents=True, exist_ok=True)
    prepared: list[Path] = []
    names: set[str] = set()
    removed = 0

    for source in sources:
        name = source.name.casefold()
        if name in names:
            raise ValueError(f"Duplicate map filename in render list: {source.name}")
        names.add(name)
        destination = output / source.name
        clean_text, count = sanitize_map_text(source.read_text(encoding="utf-8-sig"))
        destination.write_text(clean_text, encoding="utf-8", newline="")
        prepared.append(destination.resolve())
        removed += count

    output_list.parent.mkdir(parents=True, exist_ok=True)
    output_list.write_text("".join(f"{path}\n" for path in prepared), encoding="utf-8")
    return removed


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare clean temporary map copies for rendering")
    parser.add_argument("--render-list", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--output-list", required=True, type=Path)
    args = parser.parse_args()

    removed = prepare_render_maps(args.render_list, args.output, args.output_list)
    print(f"Prepared render maps; removed transient UI blocks: {removed}")


if __name__ == "__main__":
    main()
