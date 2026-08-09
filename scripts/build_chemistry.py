from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path


HEADING_RE = re.compile(r"^\s*(#{1,6})\s+(.+?)\s*$")
REAGENT_RE = re.compile(
    r'<GuideReagentEmbed\s+Reagent="([^"]+)"\s*/?>'
)
GROUP_RE = re.compile(
    r'<GuideReagentGroupEmbed\s+Group="([^"]+)"[^>]*/?>'
)


def parse_guide(path: Path) -> list[dict[str, object]]:
    headings: list[str] = []
    entries: list[dict[str, object]] = []

    for raw_line in path.read_text(
        encoding="utf-8-sig"
    ).splitlines():
        heading = HEADING_RE.match(raw_line)

        if heading:
            level = len(heading.group(1))
            title = heading.group(2).strip()

            headings = headings[: level - 1]
            headings.append(title)
            continue

        reagent = REAGENT_RE.search(raw_line)

        if reagent:
            entries.append({
                "type": "reagent",
                "id": reagent.group(1),
                "sectionPath": headings.copy(),
            })
            continue

        group = GROUP_RE.search(raw_line)

        if group:
            entries.append({
                "type": "group",
                "id": group.group(1),
                "sectionPath": headings.copy(),
            })

    return entries


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--game-source",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
    )
    parser.add_argument(
        "--commit",
        default="unknown",
    )

    args = parser.parse_args()

    guide_root = (
        args.game_source
        / "Resources/ServerInfo/Guidebook/_RMC14"
    )

    guides = {
        "ordnance": guide_root / "Chemicals/OT.xml",
        "medicine": guide_root / "Chemicals/Medicine.xml",
        "drinks": guide_root / "Guides/RMCGuideDrinks.xml",
    }

    missing = [
        str(path)
        for path in guides.values()
        if not path.is_file()
    ]

    if missing:
        raise FileNotFoundError(
            "Missing guide files: " + ", ".join(missing)
        )

    result = {
        "schemaVersion": 1,
        "source": {
            "repository": "MetalSage/space-stories-cm14",
            "branch": "master",
            "commit": args.commit,
        },
        "generatedAt": datetime.now(
            timezone.utc
        ).isoformat().replace("+00:00", "Z"),
        "guides": {
            key: parse_guide(path)
            for key, path in guides.items()
        },
    }

    args.output.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    args.output.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
