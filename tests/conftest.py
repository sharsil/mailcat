import pytest


def pytest_configure(config):
    config.addinivalue_line("markers", "e2e: end-to-end tests requiring network access")


def pytest_addoption(parser):
    parser.addoption(
        "--e2e", action="store_true", default=False, help="Run e2e tests (real network)"
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--e2e"):
        skip = pytest.mark.skip(reason="Need --e2e option to run")
        for item in items:
            if "e2e" in item.keywords:
                item.add_marker(skip)
