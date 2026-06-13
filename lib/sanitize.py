"""Shared text sanitizer for SQLite TEXT binds.

Strips C0 control bytes from text before it is bound into a SQLite ``TEXT``
column. The critical one is NUL (``\\x00``): SQLite's TEXT binding is C-string
based and truncates the value at the first NUL, so a message like
``"deploy blocked\\x00<rest>"`` would silently lose everything after the NUL.
``\\t`` (09), ``\\n`` (0a), ``\\r`` (0d) are real in chat text and are preserved.

Used by the ``intent_inbox`` parsers (``ingest_messages``, ``write_classification``).
Deployed to ``/opt/lib`` (Dockerfile ``COPY lib/ /opt/lib/``) and importable flat
because ``/opt/lib`` is on ``PYTHONPATH`` (entrypoint.sh).
"""
import re

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean(value):
    """Strip C0 control bytes from a text field; pass ``None`` through untouched."""
    return value if value is None else _CTRL.sub("", value)
