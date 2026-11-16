#!/usr/bin/env python3
"""
Paquete de adaptadores de transcripciones para conversation-audit.
"""

from pathlib import Path
from typing import List, Optional, Type

from .antigravity import AntigravityAdapter
from .base import (
    ConversationMetadata,
    NormalizedStep,
    NormalizedToolCall,
    TranscriptAdapter,
)
from .claude import ClaudeAdapter

ADAPTERS: List[TranscriptAdapter] = [
    AntigravityAdapter(),
    ClaudeAdapter(),
]


def get_adapter(path: Path, runtime_hint: str = "auto") -> TranscriptAdapter:
    """
    Obtiene el adaptador correspondiente según el runtime especificado o por detección automática.
    """
    hint = runtime_hint.lower().strip()
    if hint == "antigravity":
        return AntigravityAdapter()
    elif hint == "claude":
        return ClaudeAdapter()
    elif hint == "auto":
        for adapter in ADAPTERS:
            if adapter.detect(path):
                return adapter
        # Fallback predeterminado a Antigravity si no se detecta explícitamente
        return AntigravityAdapter()
    else:
        raise ValueError(f"Runtime no soportado: '{runtime_hint}'. Opciones válidas: 'auto', 'antigravity', 'claude'.")


__all__ = [
    "TranscriptAdapter",
    "NormalizedStep",
    "NormalizedToolCall",
    "ConversationMetadata",
    "AntigravityAdapter",
    "ClaudeAdapter",
    "get_adapter",
]
