from __future__ import annotations

import re
from pathlib import Path
from typing import Any


FTL_MESSAGE_RE = re.compile(r"^([A-Za-z0-9][A-Za-z0-9_-]*)\s*=\s*(.*)$")
FTL_ATTRIBUTE_RE = re.compile(r"^\s+\.([A-Za-z0-9_-]+)\s*=\s*(.*)$")
FTL_REFERENCE_RE = re.compile(r"^\{\s*([A-Za-z0-9_-]+)(?:\.([A-Za-z0-9_-]+))?\s*\}$")


class _FluentFileParser:
    """Parse a single .ftl file's lines, mirroring the original flush() closure."""

    def __init__(self) -> None:
        self.current_key: str | None = None
        self.current_attribute: str | None = None
        self.parts: list[str] = []
        self.messages: dict[str, str] = {}

    def flush(self) -> None:
        if self.current_key is None:
            self.parts = []
            return
        key = self.current_key
        if self.current_attribute is not None:
            key += "." + self.current_attribute
        value = " ".join(part.strip() for part in self.parts if part.strip())
        if value and key not in self.messages:
            self.messages[key] = value
        self.parts = []

    def feed_line(self, line: str) -> None:
        message_match = FTL_MESSAGE_RE.match(line)
        if message_match:
            self.flush()
            self.current_key = message_match.group(1)
            self.current_attribute = None
            self.parts = [message_match.group(2)]
            return

        attribute_match = FTL_ATTRIBUTE_RE.match(line)
        if attribute_match and self.current_key is not None:
            self.flush()
            self.current_attribute = attribute_match.group(1)
            self.parts = [attribute_match.group(2)]
            return

        if self.current_key is not None and line.startswith((" ", "\t")):
            stripped = line.strip()
            if stripped and not stripped.startswith("#"):
                self.parts.append(stripped)
            return

        if not line.strip():
            self.flush()
            self.current_key = None
            self.current_attribute = None


def read_fluent_messages(locale_root: Path) -> dict[str, str]:
    if not locale_root.is_dir():
        raise FileNotFoundError(f"Missing locale directory: {locale_root}")

    messages: dict[str, str] = {}
    for path in sorted(locale_root.rglob("*.ftl")):
        parser = _FluentFileParser()
        for line in path.read_text(encoding="utf-8-sig").splitlines():
            parser.feed_line(line)
        parser.flush()
        for key, value in parser.messages.items():
            if key not in messages:
                messages[key] = value

    return messages


class Localizer:
    def __init__(self, messages: dict[str, str]):
        self.messages = messages

    def resolve_key(self, key: str, active: tuple[str, ...] = ()) -> str | None:
        if key in active:
            return None
        value = self.messages.get(key)
        if value is None:
            return None
        reference = FTL_REFERENCE_RE.match(value.strip())
        if reference:
            target = reference.group(1)
            if reference.group(2):
                target += "." + reference.group(2)
            return self.resolve_key(target, active + (key,))
        return value

    def entity_text(
        self,
        prototype_id: str,
        attribute: str | None,
        fallback: Any,
    ) -> str:
        key = f"ent-{prototype_id}"
        if attribute:
            key += "." + attribute
        localized = self.resolve_key(key)
        if localized:
            return localized
        if isinstance(fallback, str) and fallback.strip():
            fallback_reference = FTL_REFERENCE_RE.match(fallback.strip())
            if fallback_reference:
                target = fallback_reference.group(1)
                if fallback_reference.group(2):
                    target += "." + fallback_reference.group(2)
                resolved = self.resolve_key(target)
                if resolved:
                    return resolved
            return fallback
        return prototype_id if attribute is None else ""
