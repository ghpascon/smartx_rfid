"""publish_lib_ghp - A simple Python library demonstrating how to publish packages to PyPI."""

from importlib.metadata import version

try:
    __version__ = version("publish-lib-example")
except Exception:
    # Fallback for development environments
    __version__ = "0.0.0-dev"
