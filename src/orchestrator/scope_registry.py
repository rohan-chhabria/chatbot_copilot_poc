"""
Registry of available pipeline scopes.

Pipelines register themselves at import time via the @register_pipeline decorator.
The registry provides:
- Pipeline lookup by scope_id
- Scope metadata for API responses
- Pipeline instantiation and caching
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import TYPE_CHECKING, Type

from src.shared.logger import get_logger

if TYPE_CHECKING:
    from src.pipelines.base import Pipeline

logger = get_logger(__name__)


@dataclass
class ScopeDefinition:
    """Metadata for a registered scope."""

    id: str
    label: str
    icon: str
    description: str
    category: str | None
    pipeline_class: Type[Pipeline]
    enabled: bool = True


class ScopeRegistry:
    """
    Central registry of all available pipeline scopes.

    Pipelines register themselves at import time via @register decorator.
    """

    _scopes: dict[str, ScopeDefinition] = {}
    _instances: dict[str, Pipeline] = {}

    @classmethod
    def register(cls, scope: ScopeDefinition) -> None:
        """Register a scope definition."""
        cls._scopes[scope.id] = scope
        logger.info("Registered scope: %s (%s)", scope.id, scope.label)

    @classmethod
    def get(cls, scope_id: str) -> Pipeline:
        """Get or create pipeline instance for a scope."""
        if scope_id not in cls._scopes:
            raise ValueError(f"Unknown scope: {scope_id}")

        if scope_id not in cls._instances:
            definition = cls._scopes[scope_id]
            if not definition.enabled:
                raise ValueError(f"Scope disabled: {scope_id}")
            cls._instances[scope_id] = definition.pipeline_class()
            logger.info("Instantiated pipeline: %s", scope_id)

        return cls._instances[scope_id]

    @classmethod
    def get_definition(cls, scope_id: str) -> ScopeDefinition | None:
        """Get scope definition without instantiating."""
        return cls._scopes.get(scope_id)

    @classmethod
    def get_all(cls, include_disabled: bool = False) -> list[ScopeDefinition]:
        """Get all registered scopes."""
        return [
            s for s in cls._scopes.values() if include_disabled or s.enabled
        ]

    @classmethod
    def get_by_category(cls) -> dict[str, list[ScopeDefinition]]:
        """Get scopes grouped by category."""
        result: dict[str, list[ScopeDefinition]] = defaultdict(list)
        for scope in cls.get_all():
            result[scope.category or "Other"].append(scope)
        return dict(result)

    @classmethod
    def is_valid_scope(cls, scope_id: str) -> bool:
        """Check if scope exists and is enabled."""
        defn = cls._scopes.get(scope_id)
        return defn is not None and defn.enabled

    @classmethod
    def get_options_for_api(cls) -> list[dict]:
        """Get scope options formatted for API response."""
        return [
            {
                "id": s.id,
                "label": s.label,
                "icon": s.icon,
                "description": s.description,
                "category": s.category,
            }
            for s in cls.get_all()
        ]

    @classmethod
    def clear(cls) -> None:
        """Clear all registrations (for testing)."""
        cls._scopes.clear()
        cls._instances.clear()


def register_pipeline(
    scope_id: str,
    label: str,
    icon: str,
    description: str,
    category: str | None = None,
    enabled: bool = True,
):
    """
    Decorator to register a pipeline class.

    Usage:
        @register_pipeline("document_qa", "Documents", "📄", "Search docs")
        class DocumentQAPipeline(Pipeline):
            ...
    """

    def decorator(cls: Type[Pipeline]) -> Type[Pipeline]:
        cls.scope_id = scope_id
        cls.scope_label = label
        cls.scope_icon = icon
        cls.scope_description = description

        ScopeRegistry.register(
            ScopeDefinition(
                id=scope_id,
                label=label,
                icon=icon,
                description=description,
                category=category,
                pipeline_class=cls,
                enabled=enabled,
            )
        )
        return cls

    return decorator
