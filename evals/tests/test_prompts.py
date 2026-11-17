"""The harness must evaluate the *production* prompts, read from server/ without importing it."""


import pytest

from lens_evals.dataset import Task
from lens_evals.prompts import (
    DEFAULT_SERVER_DIR,
    PromptSourceError,
    load_task_prompts,
    read_string_constant,
)


def test_default_server_dir_points_at_the_real_backend():
    assert (DEFAULT_SERVER_DIR / "app.py").is_file()
    assert (DEFAULT_SERVER_DIR / "prompts").is_dir()


@pytest.mark.parametrize("locale", ["ar", "en"])
def test_loads_the_production_prompt_files_for_each_task(locale):
    prompts = load_task_prompts(locale)
    prompt_dir = DEFAULT_SERVER_DIR / "prompts" / locale

    describe = prompts[Task.DESCRIBE_IMAGE]
    read = prompts[Task.READ_TEXT]
    assert describe.developer_prompt == (prompt_dir / "describe_image.txt").read_text(encoding="utf-8").strip()
    assert read.developer_prompt == (prompt_dir / "read_contents.txt").read_text(encoding="utf-8").strip()


def test_user_questions_are_extracted_from_app_py():
    """Drift detector: fails if app.py renames or stops defining the question constants."""
    app_py = DEFAULT_SERVER_DIR / "app.py"
    prompts = load_task_prompts("ar")

    assert prompts[Task.DESCRIBE_IMAGE].user_question == read_string_constant(app_py, "DESCRIBE_IMAGE_QUESTION")
    assert prompts[Task.READ_TEXT].user_question == read_string_constant(app_py, "READ_CONTENTS_QUESTION")
    assert prompts[Task.DESCRIBE_IMAGE].user_question
    assert prompts[Task.READ_TEXT].user_question


def test_every_task_has_a_prompt():
    assert set(load_task_prompts("ar")) == set(Task)


def test_unknown_locale_lists_the_available_ones():
    with pytest.raises(PromptSourceError) as excinfo:
        load_task_prompts("xx")
    message = str(excinfo.value)
    assert "xx" in message and "ar" in message and "en" in message


def test_read_string_constant_reads_module_level_literals(tmp_path):
    module = tmp_path / "mod.py"
    module.write_text('import os\nGREETING = "hello"\nOTHER = os.getenv("X")\n', encoding="utf-8")
    assert read_string_constant(module, "GREETING") == "hello"


def test_read_string_constant_rejects_non_literals(tmp_path):
    module = tmp_path / "mod.py"
    module.write_text('import os\nOTHER = os.getenv("X")\n', encoding="utf-8")
    with pytest.raises(PromptSourceError, match="OTHER"):
        read_string_constant(module, "OTHER")


def test_read_string_constant_reports_missing_names(tmp_path):
    module = tmp_path / "mod.py"
    module.write_text("A = 'a'\n", encoding="utf-8")
    with pytest.raises(PromptSourceError, match="MISSING"):
        read_string_constant(module, "MISSING")


def test_missing_prompt_file_is_reported(tmp_path):
    (tmp_path / "prompts" / "en").mkdir(parents=True)
    (tmp_path / "app.py").write_text(
        "DESCRIBE_IMAGE_QUESTION = 'd'\nREAD_CONTENTS_QUESTION = 'r'\n", encoding="utf-8"
    )
    with pytest.raises(PromptSourceError, match="describe_image.txt"):
        load_task_prompts("en", server_dir=tmp_path)
