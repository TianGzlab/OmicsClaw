"""Routing module for OmicsClaw orchestrators."""

from .llm_router import route_with_llm

__all__ = ["route_with_llm"]
