#!/usr/bin/env python3
"""
Modelo de dominio normalizado y clase base abstracta para adaptadores de transcripción.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class NormalizedToolCall:
    """Representa una llamada a herramienta normalizada."""
    name: str
    args: Dict[str, Any] = field(default_factory=dict)
    tool_action: str = ""
    tool_summary: str = ""
    call_id: Optional[str] = None
    status: str = "DONE"  # DONE, ERROR, CANCELLED, UNKNOWN
    error: Optional[str] = None
    raw_output: Optional[str] = None


@dataclass
class NormalizedStep:
    """Representa un paso o evento unificado en la conversación."""
    step_index: int
    source: str  # USER, MODEL, SYSTEM, TOOL
    step_type: str  # USER_INPUT, PLANNER_RESPONSE, TOOL_OUTPUT, EPHEMERAL, SYSTEM
    created_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    content: Optional[str] = None
    thinking: Optional[str] = None
    tool_calls: List[NormalizedToolCall] = field(default_factory=list)
    status: str = "DONE"  # DONE, ERROR, CANCELLED
    truncated_fields: List[str] = field(default_factory=list)
    tokens: Dict[str, int] = field(default_factory=dict)
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ConversationMetadata:
    """Metadatos generales de la sesión auditada."""
    session_id: str
    runtime: str
    source_path: str
    title: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None


def clean_title(text: Optional[str], max_len: int = 120) -> Optional[str]:
    """Limpia y sanitiza el texto del primer prompt de usuario para usarlo como título u objetivo."""
    if not text:
        return None
    import re
    # Extraer contenido de <USER_REQUEST> si existe
    match = re.search(r"<USER_REQUEST>\s*(.*?)\s*(?:</USER_REQUEST>|$)", text, re.DOTALL | re.IGNORECASE)
    cleaned = match.group(1) if match else text

    # Remover etiquetas XML/HTML remanentes si las hay
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    # Normalizar secuencias de espacios en blanco
    cleaned = " ".join(cleaned.split()).strip()

    if not cleaned:
        return None

    if len(cleaned) > max_len:
        return cleaned[:max_len - 3].rstrip() + "..."
    return cleaned


class TranscriptAdapter(ABC):
    """Interfaz abstracta para parsers de transcripciones de diferentes runtimes."""

    @abstractmethod
    def resolve_path(self, target: Path) -> Path:
        """Resuelve la ruta física del archivo de sesión o transcripción a partir de un ID o ruta."""
        pass

    @abstractmethod
    def detect(self, path: Path) -> bool:
        """Determina si el archivo o ruta corresponde a este runtime."""
        pass

    @abstractmethod
    def parse(self, path: Path) -> List[NormalizedStep]:
        """Parsea la transcripción y retorna la lista de pasos normalizados."""
        pass

    @abstractmethod
    def extract_metadata(self, path: Path, steps: List[NormalizedStep]) -> ConversationMetadata:
        """Extrae metadatos globales de la conversación."""
        pass

    def fast_extract_metadata(self, path: Path) -> ConversationMetadata:
        """Extrae metadatos globales (sesión, título, tiempos) de forma rápida sin parsear todos los pasos."""
        steps = self.parse(path)
        return self.extract_metadata(path, steps)

