"""Routing topology validation and failure analysis."""

from importlib.metadata import PackageNotFoundError, version

from .analysis import analyze, resilience, shortest_path, validate
from .io import TopologyFormatError, load
from .model import Link, Topology

try:
    __version__ = version("routecraft")
except PackageNotFoundError:  # running from a source tree without installing
    __version__ = "0.0.0+unknown"

__all__ = [
    "Link",
    "Topology",
    "TopologyFormatError",
    "__version__",
    "analyze",
    "load",
    "resilience",
    "shortest_path",
    "validate",
]
