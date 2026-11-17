"""Eval dataset schema, loading and validation.

A dataset is a JSON file::

    {
      "description": "optional free text",
      "cases": [
        {
          "id": "crosswalk-red-signal",
          "task": "describe_image",            # or "read_text"
          "image": "images/crosswalk.jpg",     # relative to the JSON file
          "must_include": ["..."],             # essential elements (>= 1)
          "must_not_include": ["..."],         # optional forbidden elements
          "notes": "optional free text"
        }
      ]
    }

Validation is strict (unknown keys are rejected) and collects every problem
before failing, so authors can fix a whole file in one pass.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Iterable, Sequence


class Task(str, Enum):
    """The backend features under evaluation."""

    DESCRIBE_IMAGE = "describe_image"  # POST /describe
    READ_TEXT = "read_text"  # POST /read

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class EvalCase:
    id: str
    task: Task
    image: Path
    must_include: tuple[str, ...]
    must_not_include: tuple[str, ...] = ()
    notes: str | None = None


class DatasetError(ValueError):
    """Raised when a dataset cannot be loaded; ``errors`` lists every problem found."""

    def __init__(self, errors: Sequence[str] | str):
        self.errors = [errors] if isinstance(errors, str) else list(errors)
        super().__init__("\n".join(self.errors))


_TOP_LEVEL_KEYS = {"description", "cases"}
_REQUIRED_CASE_KEYS = ("id", "task", "image", "must_include")
_OPTIONAL_CASE_KEYS = ("must_not_include", "notes")
_VALID_TASKS = ", ".join(t.value for t in Task)


def load_dataset(path: Path | str) -> list[EvalCase]:
    """Load and validate a dataset file. Relative image paths resolve against the file's folder."""
    path = Path(path)
    return parse_dataset(read_json_file(path), base_dir=path.parent)


def read_json_file(path: Path) -> Any:
    if not path.is_file():
        raise DatasetError(f"Dataset file not found: {path}")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise DatasetError(f"{path}: invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}") from exc


def parse_dataset(data: Any, base_dir: Path) -> list[EvalCase]:
    if not isinstance(data, dict):
        raise DatasetError("Dataset must be a JSON object with a 'cases' list.")

    errors: list[str] = []
    unknown = sorted(set(data) - _TOP_LEVEL_KEYS)
    if unknown:
        errors.append(f"Unknown top-level key(s): {', '.join(unknown)}")

    raw_cases = data.get("cases")
    if not isinstance(raw_cases, list):
        raise DatasetError(errors + ["Dataset must contain a 'cases' list."])
    if not raw_cases:
        raise DatasetError(errors + ["Dataset must contain at least one case."])

    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    for index, raw in enumerate(raw_cases):
        parsed, case_errors = _parse_case(raw, index, base_dir)
        errors.extend(case_errors)
        if parsed is None:
            continue
        if parsed.id in seen_ids:
            errors.append(f"cases[{index}]: duplicate id '{parsed.id}'")
            continue
        seen_ids.add(parsed.id)
        cases.append(parsed)

    if errors:
        raise DatasetError(errors)
    return cases


def _parse_case(raw: Any, index: int, base_dir: Path) -> tuple[EvalCase | None, list[str]]:
    if not isinstance(raw, dict):
        return None, [f"cases[{index}]: each case must be a JSON object"]

    raw_id = raw.get("id")
    label = f"cases[{index}] ('{raw_id}')" if isinstance(raw_id, str) and raw_id.strip() else f"cases[{index}]"
    errors: list[str] = []

    def err(message: str) -> None:
        errors.append(f"{label}: {message}")

    unknown = sorted(set(raw) - set(_REQUIRED_CASE_KEYS) - set(_OPTIONAL_CASE_KEYS))
    if unknown:
        err(f"unknown key(s) {', '.join(unknown)} (allowed: {', '.join(_REQUIRED_CASE_KEYS + _OPTIONAL_CASE_KEYS)})")
    for key in _REQUIRED_CASE_KEYS:
        if key not in raw:
            err(f"missing required key '{key}'")

    # Validate every field that is present, even if others are missing, so one pass reports everything.
    case_id = _non_empty_string(raw["id"], "id", err) if "id" in raw else ""
    image = _non_empty_string(raw["image"], "image", err) if "image" in raw else ""

    task = None
    if "task" in raw:
        try:
            task = Task(raw["task"])
        except ValueError:
            err(f"invalid task {raw['task']!r}; expected one of: {_VALID_TASKS}")

    must_include = (
        _string_list(raw["must_include"], "must_include", err, allow_empty=False) if "must_include" in raw else ()
    )
    must_not_include = _string_list(raw.get("must_not_include", []), "must_not_include", err, allow_empty=True)

    notes = raw.get("notes")
    if notes is not None and not isinstance(notes, str):
        err("'notes' must be a string")

    if errors:
        return None, errors

    image_path = Path(image)
    if not image_path.is_absolute():
        image_path = base_dir / image_path

    return (
        EvalCase(
            id=case_id,
            task=task,
            image=image_path,
            must_include=must_include,
            must_not_include=must_not_include,
            notes=notes,
        ),
        [],
    )


def _non_empty_string(value: Any, field: str, err) -> str:
    if not isinstance(value, str) or not value.strip():
        err(f"'{field}' must be a non-empty string")
        return ""
    return value.strip()


def _string_list(value: Any, field: str, err, *, allow_empty: bool) -> tuple[str, ...]:
    requirement = "a list of non-empty strings" if allow_empty else "a non-empty list of non-empty strings"
    if not isinstance(value, list) or (not allow_empty and not value):
        err(f"'{field}' must be {requirement}")
        return ()
    if not all(isinstance(item, str) and item.strip() for item in value):
        err(f"'{field}' must be {requirement}")
        return ()
    return tuple(item.strip() for item in value)


def find_missing_images(cases: Iterable[EvalCase]) -> list[EvalCase]:
    return [case for case in cases if not case.image.is_file()]


def filter_cases(
    cases: Sequence[EvalCase],
    *,
    tasks: Iterable[Task] | None = None,
    ids: Iterable[str] | None = None,
) -> list[EvalCase]:
    """Select a subset of cases, preserving dataset order. Unknown ids are an error."""
    selected = list(cases)
    if ids:
        wanted = list(dict.fromkeys(ids))
        known = {case.id for case in cases}
        unknown = [case_id for case_id in wanted if case_id not in known]
        if unknown:
            raise DatasetError(f"Unknown case id(s): {', '.join(unknown)}")
        selected = [case for case in selected if case.id in set(wanted)]
    if tasks:
        task_set = set(tasks)
        selected = [case for case in selected if case.task in task_set]
    return selected
