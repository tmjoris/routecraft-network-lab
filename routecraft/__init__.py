"""Routing topology validation and failure analysis."""

from .model import Topology
from .analysis import analyze, validate

__all__ = ["Topology", "analyze", "validate"]

