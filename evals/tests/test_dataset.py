"""Dataset schema: how eval authors describe an image and its expectations."""

from pathlib import Path

import pytest

from lens_evals.dataset import (
    DatasetError,
    Task,
    filter_cases,
    find_missing_images,
    load_dataset,
    parse_dataset,
)


def case(**overrides):
    base = {
        "id": "crosswalk",
        "task": "describe_image",
        "image": "images/crosswalk.jpg",
        "must_include": ["a pedestrian crosswalk"],
    }
    base.update(overrides)
    return base


def test_loads_valid_dataset_and_resolves_image_relative_to_the_file(write_json, tmp_path):
    path = write_json(
        {
            "cases": [
                case(must_not_include=["says it is safe to cross"], notes="rainy day"),
                case(id="menu", task="read_text", image="images/menu.png", must_include=["Soup of the day"]),
            ]
        }
    )

    cases = load_dataset(path)

    assert [c.id for c in cases] == ["crosswalk", "menu"]
    assert cases[0].task is Task.DESCRIBE_IMAGE
    assert cases[1].task is Task.READ_TEXT
    assert cases[0].image == tmp_path / "images" / "crosswalk.jpg"
    assert cases[0].must_include == ("a pedestrian crosswalk",)
    assert cases[0].must_not_include == ("says it is safe to cross",)
    assert cases[0].notes == "rainy day"


def test_must_not_include_is_optional(write_json):
    cases = load_dataset(write_json({"cases": [case()]}))
    assert cases[0].must_not_include == ()


def test_absolute_image_paths_are_kept(tmp_path):
    absolute = tmp_path / "elsewhere" / "photo.jpg"
    cases = parse_dataset({"cases": [case(image=str(absolute))]}, base_dir=Path("/ignored"))
    assert cases[0].image == absolute


def test_items_are_stripped_of_surrounding_whitespace(write_json):
    cases = load_dataset(write_json({"cases": [case(must_include=["  a crosswalk \n"])]}))
    assert cases[0].must_include == ("a crosswalk",)


def test_reports_every_problem_at_once_instead_of_stopping_at_the_first(write_json):
    path = write_json(
        {
            "cases": [
                case(id="a", task="summarise"),
                case(id="b", must_include=[]),
            ]
        }
    )

    with pytest.raises(DatasetError) as excinfo:
        load_dataset(path)

    errors = excinfo.value.errors
    assert len(errors) == 2
    assert any("'a'" in e and "task" in e for e in errors)
    assert any("'b'" in e and "must_include" in e for e in errors)


def test_unknown_task_error_lists_the_valid_tasks():
    with pytest.raises(DatasetError) as excinfo:
        parse_dataset({"cases": [case(task="ocr")]}, base_dir=Path("."))
    message = str(excinfo.value)
    assert "describe_image" in message and "read_text" in message


def test_rejects_duplicate_ids():
    with pytest.raises(DatasetError, match="duplicate id 'crosswalk'"):
        parse_dataset({"cases": [case(), case()]}, base_dir=Path("."))


@pytest.mark.parametrize(
    "field, value",
    [
        ("must_include", []),
        ("must_include", "a crosswalk"),
        ("must_include", ["ok", "   "]),
        ("must_include", ["ok", 3]),
        ("must_not_include", [""]),
        ("must_not_include", "not a list"),
        ("id", ""),
        ("id", 7),
        ("image", ""),
    ],
)
def test_rejects_malformed_fields(field, value):
    with pytest.raises(DatasetError, match=field):
        parse_dataset({"cases": [case(**{field: value})]}, base_dir=Path("."))


@pytest.mark.parametrize("missing", ["id", "task", "image", "must_include"])
def test_rejects_missing_required_fields(missing):
    data = case()
    del data[missing]
    with pytest.raises(DatasetError, match=missing):
        parse_dataset({"cases": [data]}, base_dir=Path("."))


def test_rejects_unknown_keys_so_typos_do_not_silently_drop_expectations():
    with pytest.raises(DatasetError, match="must_inlcude"):
        parse_dataset({"cases": [case(must_inlcude=["x"])]}, base_dir=Path("."))


@pytest.mark.parametrize(
    "data, fragment",
    [
        ([], "JSON object"),
        ({}, "cases"),
        ({"cases": []}, "at least one case"),
        ({"cases": "nope"}, "cases"),
        ({"cases": ["nope"]}, "object"),
        ({"cases": [case()], "extra": 1}, "extra"),
    ],
)
def test_rejects_malformed_top_level(data, fragment):
    with pytest.raises(DatasetError, match=fragment):
        parse_dataset(data, base_dir=Path("."))


def test_top_level_description_is_allowed():
    cases = parse_dataset({"description": "street scenes", "cases": [case()]}, base_dir=Path("."))
    assert len(cases) == 1


def test_invalid_json_is_reported_with_its_location(tmp_path):
    path = tmp_path / "broken.json"
    path.write_text('{"cases": [}', encoding="utf-8")
    with pytest.raises(DatasetError, match="line 1"):
        load_dataset(path)


def test_missing_dataset_file_raises_dataset_error(tmp_path):
    with pytest.raises(DatasetError, match="not found"):
        load_dataset(tmp_path / "nope.json")


def test_find_missing_images(write_json, tmp_path):
    (tmp_path / "images").mkdir()
    (tmp_path / "images" / "present.jpg").write_bytes(b"\xff\xd8")
    cases = load_dataset(
        write_json({"cases": [case(id="ok", image="images/present.jpg"), case(id="gone", image="images/gone.jpg")]})
    )

    assert [c.id for c in find_missing_images(cases)] == ["gone"]


class TestFilterCases:
    @pytest.fixture
    def cases(self):
        return parse_dataset(
            {
                "cases": [
                    case(id="d1"),
                    case(id="r1", task="read_text"),
                    case(id="d2"),
                ]
            },
            base_dir=Path("."),
        )

    def test_no_filters_returns_everything(self, cases):
        assert filter_cases(cases) == cases

    def test_filter_by_task(self, cases):
        assert [c.id for c in filter_cases(cases, tasks=[Task.READ_TEXT])] == ["r1"]

    def test_filter_by_id_keeps_dataset_order(self, cases):
        assert [c.id for c in filter_cases(cases, ids=["d2", "d1"])] == ["d1", "d2"]

    def test_unknown_ids_are_an_error_not_a_silent_empty_run(self, cases):
        with pytest.raises(DatasetError, match="typo"):
            filter_cases(cases, ids=["d1", "typo"])


def test_key_problems_do_not_hide_value_problems_in_the_same_case():
    raw = case(task="read", must_inlcude=["x"])
    del raw["must_include"]
    with pytest.raises(DatasetError) as excinfo:
        parse_dataset({"cases": [raw]}, base_dir=Path("."))
    message = str(excinfo.value)
    assert "must_inlcude" in message
    assert "missing required key 'must_include'" in message
    assert "invalid task 'read'" in message
