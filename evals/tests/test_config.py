"""Environment configuration: the judge model and API key come from env vars."""

import pytest

from lens_evals.config import API_KEY_ENV, JUDGE_MODEL_ENV, ConfigError, load_settings


def test_env_var_names_are_stable():
    assert JUDGE_MODEL_ENV == "EVAL_JUDGE_MODEL"
    assert API_KEY_ENV == "OPENAI_API_KEY"


def test_reads_judge_model_and_api_key():
    settings = load_settings({"EVAL_JUDGE_MODEL": "gpt-4.1", "OPENAI_API_KEY": "sk-test"})
    assert settings.judge_model == "gpt-4.1"
    assert settings.api_key == "sk-test"


def test_values_are_stripped():
    settings = load_settings({"EVAL_JUDGE_MODEL": " gpt-4.1 \n", "OPENAI_API_KEY": " sk-test "})
    assert settings.judge_model == "gpt-4.1"
    assert settings.api_key == "sk-test"


@pytest.mark.parametrize(
    "environ, missing",
    [
        ({}, ["EVAL_JUDGE_MODEL", "OPENAI_API_KEY"]),
        ({"OPENAI_API_KEY": "sk"}, ["EVAL_JUDGE_MODEL"]),
        ({"EVAL_JUDGE_MODEL": "   ", "OPENAI_API_KEY": "sk"}, ["EVAL_JUDGE_MODEL"]),
        ({"EVAL_JUDGE_MODEL": "gpt-4.1"}, ["OPENAI_API_KEY"]),
    ],
)
def test_reports_all_missing_variables_together(environ, missing):
    with pytest.raises(ConfigError) as excinfo:
        load_settings(environ)
    assert excinfo.value.missing == missing
    for name in missing:
        assert name in str(excinfo.value)


def test_api_key_value_never_appears_in_repr():
    settings = load_settings({"EVAL_JUDGE_MODEL": "gpt-4.1", "OPENAI_API_KEY": "sk-secret-value"})
    assert "sk-secret-value" not in repr(settings)
