"""
API Handlers package.

Modular handlers for different API concerns:
- chat_handler: Main chat orchestration
- scope_handler: Scope selection/switching
"""

from src.api.handlers.chat_handler import ChatHandler
from src.api.handlers.scope_handler import ScopeHandler

__all__ = ["ChatHandler", "ScopeHandler"]
