"""
Orchestrator package — coordinates scope management and pipeline dispatch.

Components:
- ScopeRegistry: Registry of available pipeline scopes
- ScopeStateMachine: Manages scope state and transitions
- CrossScopeHandler: Handles scope-agnostic interactions
"""

from src.orchestrator.cross_scope import CrossScopeHandler
from src.orchestrator.scope_registry import ScopeRegistry, register_pipeline
from src.orchestrator.state_machine import ScopeStateMachine

__all__ = [
    "ScopeRegistry",
    "register_pipeline",
    "ScopeStateMachine",
    "CrossScopeHandler",
]
