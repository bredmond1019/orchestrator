"""Knowledge workspace resolver — contract §3 semantics (docs/workspace-contract.md v1.0.0).

Mirrors bastion's shipped `src/config.rs` `resolve_workspace_root` / `FileConfig` name-for-name
(decision D47: each consumer keeps its own registry file, but the *semantics* are pinned and
shared). This module owns the Python half's registry loader and the pure resolution function
that `scripts/index_brain.py` uses to select a workspace root.
"""

import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_NAME_PATTERN = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


class WorkspaceResolverError(Exception):
    """Base class for all typed errors raised by this module."""


class UnknownWorkspaceError(WorkspaceResolverError):
    """A named workspace was supplied but is not present in the registry."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"unknown workspace '{name}' — not found in [workspaces] registry"
        )


class NoWorkspaceRegistryError(WorkspaceResolverError):
    """A workspace name was supplied but no registry file exists at all."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            "no [workspaces] table in config — add [workspaces] to "
            "~/.config/orchestrator/config.toml "
            f"(requested workspace '{name}')"
        )


class MalformedRegistryError(WorkspaceResolverError):
    """The registry file exists but is not valid TOML / not the expected shape."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"config file is malformed: {detail}")


class InvalidWorkspaceNameError(WorkspaceResolverError):
    """A workspace name does not conform to the §2 kebab-case format."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"invalid workspace name '{name}' — must be kebab-case "
            "(lowercase ASCII letters, digits, and hyphens)"
        )


@dataclass(frozen=True)
class WorkspaceRegistry:
    """Parsed `[workspaces]` registry — name -> path (verbatim strings), plus a default name.

    ``is_empty`` is true when no registry file was loaded (absent/unreadable file), as opposed
    to a registry file that was loaded but declares no `[workspaces]` entries — both behave the
    same for lookups (empty `workspaces` dict), but callers that need to distinguish "no file at
    all" from "file with an empty table" can use this flag.
    """

    workspaces: dict[str, str] = field(default_factory=dict)
    default_workspace: str | None = None
    is_empty: bool = True


def _default_registry_path() -> Path:
    """Default registry path.

    `$XDG_CONFIG_HOME/orchestrator/config.toml`, falling back to
    `~/.config/orchestrator/config.toml`.
    """
    xdg_config_home = os.environ.get("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "orchestrator" / "config.toml"
    return Path.home() / ".config" / "orchestrator" / "config.toml"


def validate_workspace_name(name: str) -> None:
    """Raise `InvalidWorkspaceNameError` unless `name` is kebab-case per contract §2."""
    if not _NAME_PATTERN.match(name):
        raise InvalidWorkspaceNameError(name)


def load_registry(path: Path | None = None) -> WorkspaceRegistry:
    """Load the `[workspaces]` registry from `path` (default: the XDG-derived config path).

    - Absent or unreadable file -> empty registry, no error.
    - Present but malformed TOML / wrong shape -> `MalformedRegistryError`.
    """
    registry_path = path if path is not None else _default_registry_path()

    try:
        contents = registry_path.read_text(encoding="utf-8")
    except OSError:
        return WorkspaceRegistry()

    try:
        data = tomllib.loads(contents)
    except tomllib.TOMLDecodeError as e:
        raise MalformedRegistryError(str(e)) from e

    raw_workspaces = data.get("workspaces", {})
    if not isinstance(raw_workspaces, dict):
        raise MalformedRegistryError(
            f"[workspaces] must be a table, got {type(raw_workspaces).__name__}"
        )
    for name, workspace_path in raw_workspaces.items():
        if not isinstance(name, str) or not isinstance(workspace_path, str):
            raise MalformedRegistryError(
                "[workspaces] entries must be string name = string path"
            )

    default_workspace = data.get("default_workspace")
    if default_workspace is not None and not isinstance(default_workspace, str):
        raise MalformedRegistryError("default_workspace must be a string")

    return WorkspaceRegistry(
        workspaces=dict(raw_workspaces),
        default_workspace=default_workspace,
        is_empty=False,
    )


def resolve_workspace_root(
    explicit_root: Path | None,
    workspace: str | None,
    registry: WorkspaceRegistry,
) -> Path:
    """Resolve a workspace name/root to a corpus root per contract §3.

    Precedence (highest -> lowest):
    1. `explicit_root` -- always wins, no registry lookup.
    2. `workspace` -- looked up in `registry.workspaces`; unknown -> `UnknownWorkspaceError`;
       no registry loaded at all -> `NoWorkspaceRegistryError`.
    3. `registry.default_workspace` -- resolved the same way as step 2.
    4. Built-in default: `Path(".")`.

    Pure function: no I/O, no canonicalization, no existence check. Registry paths are
    returned verbatim.
    """
    if explicit_root is not None:
        return explicit_root

    if workspace is not None:
        validate_workspace_name(workspace)
        if registry.is_empty:
            raise NoWorkspaceRegistryError(workspace)
        if workspace not in registry.workspaces:
            raise UnknownWorkspaceError(workspace)
        return Path(registry.workspaces[workspace])

    if registry.default_workspace is not None:
        default_name = registry.default_workspace
        validate_workspace_name(default_name)
        if registry.is_empty:
            raise NoWorkspaceRegistryError(default_name)
        if default_name not in registry.workspaces:
            raise UnknownWorkspaceError(default_name)
        return Path(registry.workspaces[default_name])

    return Path(".")
