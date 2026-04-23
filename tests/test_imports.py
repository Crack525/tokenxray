"""Smoke tests: every commands submodule must import without error."""
import importlib
import pkgutil
from argparse import Namespace

import tokenxray.commands


def test_all_commands_import():
    """Catch dead imports in any commands/*.py before they reach users."""
    for mod_info in pkgutil.iter_modules(tokenxray.commands.__path__):
        importlib.import_module(f"tokenxray.commands.{mod_info.name}")


def test_mcp_run_empty_dir(tmp_path):
    """--mcp with an empty directory short-circuits cleanly (no crash)."""
    import tokenxray.commands.mcp as mcp
    args = Namespace(path=str(tmp_path), enumerate_tools=False)
    mcp.run(args)  # should print "No Claude Code sessions found." and return
