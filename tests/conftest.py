from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
# Importing AstrBot creates a data/ directory under its root (the cwd by default);
# keep it out of the plugin checkout.
os.environ.setdefault("ASTRBOT_ROOT", tempfile.mkdtemp(prefix="astrbot-root-"))


@pytest.fixture(scope="session")
def plugin_main(tmp_path_factory):
    """Import main.py the way AstrBot does: as a submodule of the plugin package."""
    pytest.importorskip("astrbot.api")
    pkg_parent = tmp_path_factory.mktemp("plugins")
    (pkg_parent / "astrbot_plugin_keenable").symlink_to(ROOT, target_is_directory=True)
    sys.path.insert(0, str(pkg_parent))
    return importlib.import_module("astrbot_plugin_keenable.main")
