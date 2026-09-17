"""
Minimal stand-in for the parts of `pytest` that tests/test_pipeline.py uses
(`@pytest.fixture`), so it can be imported in this network-less sandbox.
Not used when the real pytest is installed — run_tests_no_pytest.py only
installs this shim into sys.modules if `import pytest` would otherwise fail.
"""


def fixture(*args, **kwargs):
    def decorator(fn):
        fn.__is_fixture__ = True
        return fn
    if args and callable(args[0]) and not kwargs:
        return decorator(args[0])
    return decorator
