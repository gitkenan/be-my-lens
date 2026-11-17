import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))

import lua_coverage
from android_contract import AndroidContract, load_android_contract
from jieshuo_host import FakeJieshuo


def pytest_sessionfinish(session):
    if lua_coverage.enabled():
        lua_coverage.write()


@pytest.fixture(scope="session")
def contract() -> AndroidContract:
    """The Android side of the integration, read from the app's Kotlin and manifest sources."""
    return load_android_contract()


@pytest.fixture
def jieshuo(tmp_path, contract) -> FakeJieshuo:
    """A phone with Jieshuo and Be My Lens installed, where everything works by default."""
    return FakeJieshuo(tmp_path, contract)
