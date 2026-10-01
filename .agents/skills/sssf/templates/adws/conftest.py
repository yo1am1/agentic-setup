"""adws/ is the shared workflow engine, not project tests.

A factory's own `pytest -q` walks the whole repo and would collect engine
scripts like adw_build_test.py as test modules, importing the engine (and its
dependencies) into the project's test environment. Never collect anything here.
"""

collect_ignore_glob = ["*.py"]
