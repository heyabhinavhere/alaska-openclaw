"""Alaska capabilities — the BON-specific document generators behind /alaska.

Each generator ties an existing Alaska skill (its data) to the generic, stdlib-only
Artifact Service (lib/alaska_artifacts) to produce + deliver a beautiful DOCX/PDF.
Kept separate from lib/alaska_artifacts (the engine stays generic) and from
lib/alaska_command_gateway (the routing brain).

P0: user_casefile (/alaska user <id>).
"""
from __future__ import annotations

__version__ = "0.1.0"
__all__ = ["user_casefile"]
