"""Executable deliberation protocols.

The protocol layer owns procedure. LLMs propose language and structured
actions, but never decide whether an action is procedurally legal.
"""

from .protocol_runtime import ProtocolRuntime

__all__ = ["ProtocolRuntime"]
