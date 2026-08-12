from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
import re

from .model import GgenCreateError, Replacement, validate_identifier

# The bare case-family transform keys `values_for`/`forms_for` produce -- used to
# tell an unprefixed ("name" seed) Replacement.variable apart from a prefixed
# ("<other_seed>_<transform>") one in the multi-seed rendering path below.
_CASE_FAMILY_KEYS = frozenset(
    {
        "name",
        "upper",
        "lower",
        "capitalized",
        "pascal",
        "camel",
        "snake",
        "upper_snake",
        "kebab",
        "title",
    }
)


@dataclass(frozen=True)
class CaseForm:
    literal: str
    variable: str
    transform: str


def split_words(value: str) -> list[str]:
    if not value:
        raise GgenCreateError(
            "EMPTY_PARAMETER_REFUSED",
            "parameter seed must not be empty",
        )

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
    value = validate_identifier(
        value,
        code="PARAMETER_VALUE_REFUSED",
        label="parameter value",
    )
    words = split_words(value)
    joined = "".join(words)
    pascal = "".join(word[:1].upper() + word[1:] for word in words)
    camel = words[0] + "".join(
        word[:1].upper() + word[1:]
        for word in words[1:]
    )
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
            (
                "title",
                " ".join(word[:1].upper() + word[1:] for word in words),
            ),
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


def _prefixed(replacement: Replacement, seed_name: str) -> Replacement:
    """Rewrite a single-seed Replacement's `variable` under `seed_name`'s own
    namespace (`row.<seed_name>_<transform>`) -- the seed named "name" is exempt
    (kept unprefixed) so the default/legacy seed's Tera bindings never change,
    per Phase 2's back-compat requirement."""
    if seed_name == "name":
        return replacement
    return Replacement(
        start=replacement.start,
        end=replacement.end,
        old_text=replacement.old_text,
        transform=replacement.transform,
        variable=f"{seed_name}_{replacement.variable}",
    )


def replacements_for_many(
    text: str, seeds: list[tuple[str, str]]
) -> list[Replacement]:
    """Phase 2: multiple seeds, combined occurrence scan.

    Reuses the real, unmodified `replacements_for` once per seed (each seed keeps
    its own existing single-seed duplicate-literal priority/left-boundary law
    unchanged), then merges the per-seed results by start position. Two DIFFERENT
    seeds whose matched spans genuinely overlap is a real, refused collision
    (`PARAMETER_COLLISION_REFUSED`) -- never resolved by silently preferring one
    seed's match over the other's, matching this phase's own PRD/ARD requirement.

    With exactly one seed named "name" (`seeds == [("name", value)]`, the legacy
    single-seed shape), this returns byte-identical output to
    `replacements_for(text, value)` -- the back-compat proof this function exists
    to satisfy.
    """
    per_seed: list[Replacement] = []
    for seed_name, seed_value in seeds:
        per_seed.extend(
            _prefixed(r, seed_name) for r in replacements_for(text, seed_value)
        )
    per_seed.sort(key=lambda r: r.start)
    for previous, current in zip(per_seed, per_seed[1:]):
        if current.start < previous.end:
            raise GgenCreateError(
                "PARAMETER_COLLISION_REFUSED",
                f"overlapping occurrences: {previous.variable!r} "
                f"({previous.old_text!r} at {previous.start}:{previous.end}) and "
                f"{current.variable!r} ({current.old_text!r} at "
                f"{current.start}:{current.end})",
            )
    return per_seed


def parameterize_body_many(
    text: str, seeds: list[tuple[str, str]]
) -> tuple[str, list[Replacement]]:
    replacements = replacements_for_many(text, seeds)
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


def parameterize_path_many(
    text: str, seeds: list[tuple[str, str]]
) -> tuple[str, list[Replacement]]:
    replacements = replacements_for_many(text, seeds)
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


def render_concrete_many(
    text: str,
    seeds: list[tuple[str, str]],
    values: list[tuple[str, str]],
) -> tuple[str, list[Replacement]]:
    """Like `render_concrete`, generalized to multiple seeds: `values` supplies a
    real concrete replacement value per seed name, in the same order as `seeds`."""
    replacements = replacements_for_many(text, seeds)
    values_by_seed = {name: values_for(value) for name, value in values}
    out: list[str] = []
    cursor = 0
    for replacement in replacements:
        # The "name" seed's variables are unprefixed (bare transform names, e.g.
        # "pascal"); every other seed's variables are "<seed_name>_<transform>".
        # Disambiguate against the small, fixed case-family key set rather than
        # string-splitting on "_" alone (a seed's own name could itself contain
        # an underscore).
        if replacement.variable in _CASE_FAMILY_KEYS:
            out.append(values_by_seed["name"][replacement.variable])
        else:
            owner, _, transform_key = replacement.variable.partition("_")
            out.append(values_by_seed[owner][transform_key])
        cursor = replacement.end
    out.append(text[cursor:])
    return "".join(out), replacements


def _raw(text: str) -> str:
    if not text:
        return ""
    if "{% endraw %}" in text:
        raise GgenCreateError(
            "TERA_RAW_SENTINEL_REFUSED",
            "static exemplar content contains the reserved Tera raw terminator",
        )
    return "{% raw %}" + text + "{% endraw %}"


def parameterize_body(
    text: str,
    seed: str,
) -> tuple[str, list[Replacement]]:
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


def parameterize_path(
    text: str,
    seed: str,
) -> tuple[str, list[Replacement]]:
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


def render_concrete(
    text: str,
    seed: str,
    value: str,
) -> tuple[str, list[Replacement]]:
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
