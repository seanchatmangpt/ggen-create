from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import re

from .model import GgenCreateError, Replacement


@dataclass(frozen=True)
class CaseForm:
    literal: str
    variable: str
    transform: str


def split_words(value: str) -> list[str]:
    if not value:
        raise GgenCreateError("EMPTY_PARAMETER_REFUSED", "parameter seed must not be empty")

    normalized = re.sub(r"[^A-Za-z0-9]+", " ", value).strip()
    if not normalized:
        raise GgenCreateError(
            "NON_ALPHANUMERIC_PARAMETER_REFUSED",
            "parameter seed must contain at least one alphanumeric character",
        )

    words: list[str] = []
    for token in normalized.split():
        parts = re.findall(
            r"[A-Z]+(?=[A-Z][a-z]|\d|$)|[A-Z]?[a-z]+|\d+",
            token,
        )
        words.extend(part.lower() for part in parts if part)
    if not words:
        words = [normalized.lower()]
    return words


def values_for(value: str) -> OrderedDict[str, str]:
    words = split_words(value)
    joined = "".join(words)
    pascal = "".join(word[:1].upper() + word[1:] for word in words)
    camel = words[0] + "".join(word[:1].upper() + word[1:] for word in words[1:])
    capitalized = value[:1].upper() + value[1:]
    return OrderedDict(
        [
            ("name", value),
            ("upper", joined.upper()),
            ("lower", joined.lower()),
            ("capitalized", capitalized),
            ("pascal", pascal),
            ("camel", camel),
            ("snake", "_".join(words)),
            ("upper_snake", "_".join(words).upper()),
            ("kebab", "-".join(words)),
            ("title", " ".join(word[:1].upper() + word[1:] for word in words)),
        ]
    )


def forms_for(seed: str) -> list[CaseForm]:
    values = values_for(seed)
    # Match the original implementation's fixed alternative priority. Duplicate
    # literals are kept only at their first admitted transform.
    priority = [
        "upper",
        "lower",
        "capitalized",
        "pascal",
        "camel",
        "snake",
        "upper_snake",
        "kebab",
        "title",
        "name",
    ]
    seen: set[str] = set()
    result: list[CaseForm] = []
    for variable in priority:
        literal = values[variable]
        if literal in seen:
            continue
        seen.add(literal)
        result.append(CaseForm(literal, variable, variable))
    return result


def replacements_for(text: str, seed: str) -> list[Replacement]:
    forms = forms_for(seed)
    result: list[Replacement] = []
    i = 0
    while i < len(text):
        if i > 0 and text[i - 1].isalnum():
            i += 1
            continue

        match: CaseForm | None = None
        for form in forms:
            if text.startswith(form.literal, i):
                match = form
                break
        if match is None:
            i += 1
            continue

        result.append(
            Replacement(
                start=i,
                end=i + len(match.literal),
                old_text=match.literal,
                transform=match.transform,
                variable=match.variable,
            )
        )
        i += len(match.literal)
    return result


def _raw(text: str) -> str:
    if not text:
        return ""
    if "{% endraw %}" in text:
        raise GgenCreateError(
            "TERA_RAW_SENTINEL_REFUSED",
            "static exemplar content contains the reserved Tera raw terminator",
        )
    return "{% raw %}" + text + "{% endraw %}"


def parameterize_body(text: str, seed: str) -> tuple[str, list[Replacement]]:
    replacements = replacements_for(text, seed)
    if not replacements:
        return _raw(text), []

    out: list[str] = []
    cursor = 0
    for replacement in replacements:
        out.append(_raw(text[cursor : replacement.start]))
        out.append("{{ row." + replacement.variable + " }}")
        cursor = replacement.end
    out.append(_raw(text[cursor:]))
    return "".join(out), replacements


def parameterize_path(text: str, seed: str) -> tuple[str, list[Replacement]]:
    replacements = replacements_for(text, seed)
    if "{{" in text or "{%" in text:
        raise GgenCreateError(
            "TEMPLATED_SOURCE_PATH_REFUSED",
            f"source path already contains template delimiters: {text}",
        )
    out: list[str] = []
    cursor = 0
    for replacement in replacements:
        out.append(text[cursor : replacement.start])
        out.append("{{ row." + replacement.variable + " }}")
        cursor = replacement.end
    out.append(text[cursor:])
    return "".join(out), replacements


def render_concrete(text: str, seed: str, value: str) -> tuple[str, list[Replacement]]:
    replacements = replacements_for(text, seed)
    replacement_values = values_for(value)
    out: list[str] = []
    cursor = 0
    for replacement in replacements:
        out.append(text[cursor : replacement.start])
        out.append(replacement_values[replacement.variable])
        cursor = replacement.end
    out.append(text[cursor:])
    return "".join(out), replacements
