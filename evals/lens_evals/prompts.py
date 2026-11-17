"""Load the production prompts used by the backend, without importing or modifying it.

The backend (``server/app.py``) sends, per task, a developer prompt from
``server/prompts/<locale>/<file>.txt`` and a fixed user question defined as a
module-level string constant. We read both directly from the source so the evals
always exercise exactly what production sends:

* prompt files are read as text, stripped like ``app.py`` does;
* question constants are extracted with ``ast`` (no import => no side effects,
  no FastAPI dependency, no ``.env`` loading).
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

from .dataset import Task

DEFAULT_SERVER_DIR = Path(__file__).resolve().parents[2] / "server"
DEFAULT_LOCALE = "ar"  # matches the backend's PROMPT_LOCALE default

# task -> (prompt file name, question constant in app.py). Mirrors the /describe and /read handlers.
TASK_SOURCES: dict[Task, tuple[str, str]] = {
    Task.DESCRIBE_IMAGE: ("describe_image.txt", "DESCRIBE_IMAGE_QUESTION"),
    Task.READ_TEXT: ("read_contents.txt", "READ_CONTENTS_QUESTION"),
}


class PromptSourceError(RuntimeError):
    """The production prompts could not be located or parsed."""


@dataclass(frozen=True)
class TaskPrompt:
    task: Task
    developer_prompt: str
    user_question: str


def load_task_prompts(locale: str = DEFAULT_LOCALE, server_dir: Path = DEFAULT_SERVER_DIR) -> dict[Task, TaskPrompt]:
    prompts_root = server_dir / "prompts"
    prompt_dir = prompts_root / locale
    if not prompt_dir.is_dir():
        available = sorted(p.name for p in prompts_root.iterdir() if p.is_dir()) if prompts_root.is_dir() else []
        raise PromptSourceError(
            f"No prompts for locale '{locale}' in {prompts_root}. Available: {', '.join(available) or 'none'}"
        )

    app_py = server_dir / "app.py"
    prompts: dict[Task, TaskPrompt] = {}
    for task, (file_name, constant) in TASK_SOURCES.items():
        prompt_file = prompt_dir / file_name
        if not prompt_file.is_file():
            raise PromptSourceError(f"Missing prompt file for task '{task}': {prompt_file}")
        prompts[task] = TaskPrompt(
            task=task,
            developer_prompt=prompt_file.read_text(encoding="utf-8").strip(),
            user_question=read_string_constant(app_py, constant),
        )
    return prompts


def read_string_constant(module_path: Path, name: str) -> str:
    """Return the value of a module-level ``NAME = "literal"`` assignment."""
    try:
        tree = ast.parse(module_path.read_text(encoding="utf-8"), filename=str(module_path))
    except (OSError, SyntaxError) as exc:
        raise PromptSourceError(f"Could not parse {module_path}: {exc}") from exc

    for node in tree.body:
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                return value.value
            raise PromptSourceError(f"{name} in {module_path} is not a plain string literal")
    raise PromptSourceError(f"{name} is not defined in {module_path}")
