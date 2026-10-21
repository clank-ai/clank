"""The owner's own CLANK_HOME, as it was before the suite ran (`REAL_HOME`): only the tests that read this machine's
records on purpose (the real-engine tests, which copy them into a home of their own) use it. Every other test runs
with CLANK_HOME pointed at an empty folder of the session's own (`tests/conftest.py`), so none can reach the owner's
service, records or containers, even by mistake."""

from clank.kernel.home import Home

REAL_HOME = Home.resolve()
