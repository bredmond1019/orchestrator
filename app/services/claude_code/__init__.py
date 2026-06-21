"""Claude Code LLM provider package.

Exports the backend protocol + result type, the shared pydantic-ai
`ClaudeCodeModel`, and the SDK-backed `ClaudeAgentSdkBackend` that drives the
official `claude-agent-sdk`.
"""

from services.claude_code.backend import ClaudeCodeBackend, ClaudeResult
from services.claude_code.model import ClaudeCodeModel
from services.claude_code.sdk_backend import ClaudeAgentSdkBackend

__all__ = [
    "ClaudeCodeBackend",
    "ClaudeResult",
    "ClaudeCodeModel",
    "ClaudeAgentSdkBackend",
]
