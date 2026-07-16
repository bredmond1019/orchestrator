"""Knowledge workspace resolver — contract §3 semantics (docs/workspace-contract.md v1.0.0).

Mirrors bastion's shipped `src/config.rs` `resolve_workspace_root` + `FileConfig.workspaces`/
`default_workspace` (name-parity registries per brain decision D47): each consumer keeps its own
registry file, but the resolution *semantics* are identical across the Rust and Python halves.

Registry file: `$XDG_CONFIG_HOME/orchestrator/config.toml` (falling back to
`~/.config/orchestrator/config.toml`) with a `[workspaces]` table (name -> path, as strings) and
an optional top-level `default_workspace` key.

Resolution precedence (highest -> lowest), pure — no I/O, no canonicalization, no existence
checks:

1. Explicit root — always wins, no registry lookup.
2. Named workspace — looked up in the registry.
3. Registry `default_workspace` — looked up the same way.
4. Built-in default — `Path(".")`.
"""

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

_NAME_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class WorkspaceResolverError(Exception):
    """Base class for typed workspace-resolution errors."""


class UnknownWorkspaceError(WorkspaceResolverError):
    """A workspace name was supplied but is not present in the registry."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(f"unknown workspace '{name}' — not found in [workspaces] registry")


class NoWorkspaceRegistryError(WorkspaceResolverError):
    """A workspace name was supplied but no registry exists at all."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"no [workspaces] table in config — add [workspaces] to "
            f"~/.config/orchestrator/config.toml to resolve workspace '{name}'"
        )


class MalformedRegistryError(WorkspaceResolverError):
    """The registry file is present but is invalid TOML or the wrong shape."""

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(f"config file is malformed: {detail}")


class InvalidWorkspaceNameError(WorkspaceResolverError):
    """A workspace name does not conform to the §2 kebab-case format."""

    def __init__(self, name: str) -> None:
        self.name = name
        super().__init__(
            f"invalid workspace name '{name}' — must be kebab-case "
            "(lowercase ASCII letters, digits, and hyphens only)"
        )


@dataclass(frozen=True)
class WorkspaceRegistry:
    """A loaded (or empty) `[workspaces]` registry.

    `workspaces` maps name -> path, both verbatim strings (no canonicalization).
    """

    workspaces: dict[str, str] = field(default_factory=dict)
    default_workspace: str | None = None

    @property
    def is_empty(self) -> bool:
        """True when no registry file was found/loaded at all (distinct from a present-but-empty
        `[workspaces]` table)."""
        return not self.workspaces and self.default_workspace is None


def validate_workspace_name(name: str) -> None:
    """Validate `name` conforms to contract §2 (kebab-case).

    Raises:
        InvalidWorkspaceNameError: if `name` does not match the kebab-case format.
    """
    if not _NAME_RE.match(name):
        raise InvalidWorkspaceNameError(name)


def default_registry_path(
    xdg_config_home: str | None = None, home: str | None = None
) -> Path | None:
    """Resolve the default registry path from `$XDG_CONFIG_HOME` / `$HOME`, without touching
    `os.environ` directly (callers/tests inject the values). Pure function.

    Returns `None` when neither `xdg_config_home` nor `home` is supplied.
    """
    if xdg_config_home:
        return Path(xdg_config_home) / "orchestrator" / "config.toml"
    if home:
        return Path(home) / ".config" / "orchestrator" / "config.toml"
    return None


def load_registry(path: Path | None = None) -> WorkspaceRegistry:
    """Load the `[workspaces]` registry from `path`.

    Degradation contract:
    - `path` is `None`, absent, or unreadable -> empty registry (no error).
    - `path` exists but is malformed TOML or the wrong shape -> `MalformedRegistryError`.
    """
    if path is None:
        return WorkspaceRegistry()

    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return WorkspaceRegistry()

    try:
        data = tomllib.loads(raw)
    except tomllib.TOMLDecodeError as e:
        raise MalformedRegistryError(str(e)) from e

    raw_workspaces = data.get("workspaces", {})
    if not isinstance(raw_workspaces, dict):
        raise MalformedRegistryError(
            f"[workspaces] must be a table, got {type(raw_workspaces).__name__}"
        )
    workspaces: dict[str, str] = {}
    for name, value in raw_workspaces.items():
        if not isinstance(name, str) or not isinstance(value, str):
            raise MalformedRegistryError(
                "[workspaces] entries must be string name -> string path"
            )
        workspaces[name] = value

    default_workspace = data.get("default_workspace")
    if default_workspace is not None and not isinstance(default_workspace, str):
        raise MalformedRegistryError("default_workspace must be a string")

    return WorkspaceRegistry(workspaces=workspaces, default_workspace=default_workspace)


def resolve_workspace_root(
    explicit_root: Path | None,
    workspace: str | None,
    registry: WorkspaceRegistry,
) -> Path:
    """Resolve a workspace name/root to an effective corpus root path.

    Precedence (highest -> lowest):
    1. `explicit_root` — always wins, no registry lookup.
    2. `workspace` — looked up in `registry.workspaces`.
    3. `registry.default_workspace` — looked up in `registry.workspaces`.
    4. Built-in default: `Path(".")`.

    Pure — no I/O, no canonicalization, no existence checks. Registry paths are returned
    verbatim.

    Raises:
        InvalidWorkspaceNameError: `workspace` (or the resolved default name) is not kebab-case.
        UnknownWorkspaceError: the name is not present in a non-empty registry.
        NoWorkspaceRegistryError: a name was supplied but the registry is entirely empty.
    """
    # 1. Explicit root wins outright.
    if explicit_root is not None:
        return explicit_root

    # 2. Named workspace lookup.
    if workspace is not None:
        validate_workspace_name(workspace)
        if registry.is_empty:
            raise NoWorkspaceRegistryError(workspace)
        if workspace not in registry.workspaces:
            raise UnknownWorkspaceError(workspace)
        return Path(registry.workspaces[workspace])

    # 3. Registry default_workspace.
    if registry.default_workspace is not None:
        default_name = registry.default_workspace
        validate_workspace_name(default_name)
        if registry.is_empty:
            raise NoWorkspaceRegistryError(default_name)
        if default_name not in registry.workspaces:
            raise UnknownWorkspaceError(default_name)
        return Path(registry.workspaces[default_name])

    # 4. Built-in default.
    return Path(".")
