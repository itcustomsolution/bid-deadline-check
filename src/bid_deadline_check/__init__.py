"""Deterministic deadline and compliance extraction for solicitations."""
from .core import analyze, Report, Deadline, read_document

__all__ = ["analyze", "Report", "Deadline", "read_document"]
__version__ = "0.2.0rc3"
