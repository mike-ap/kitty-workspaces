def pytest_addoption(parser):
    parser.addoption(
        "--run-kitty-integration",
        action="store_true",
        help="Launch isolated Kitty windows for integration tests",
    )


def pytest_ignore_collect(collection_path, config):
    if collection_path == collection_path.parent / "integration":
        return not config.getoption("--run-kitty-integration")
    return None
