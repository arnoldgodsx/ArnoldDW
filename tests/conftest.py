import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def pytest_configure(config):
    config.addinivalue_line("markers", "network: test needs internet access (skipped unless --network)")
    config.addinivalue_line("markers", "smoke: fast live check for the nightly platform pulse")


def pytest_addoption(parser):
    parser.addoption("--network", action="store_true", default=False, help="run tests that hit the network")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--network"):
        return
    import pytest

    skip = pytest.mark.skip(reason="needs --network")
    for item in items:
        if "network" in item.keywords:
            item.add_marker(skip)
