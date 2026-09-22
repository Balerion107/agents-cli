# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Copying template files into a generated project.

The generic tree copier (:func:`copy_files`) plus the frontend, deployment, and
flat-structure helpers that build on it. Symlink safety is delegated to
``symlinks.py``: a link whose resolved target stays inside the fetched repo is
materialized as real files, an unsafe one is refused.
"""

import logging
import pathlib
import shutil
import sys

from google.agents.cli.scaffold.utils.fs import is_ignored_name

from .symlinks import MAX_COPY_DEPTH, ScaffoldSymlinkSecurityError, require_safe_symlink

DEFAULT_FRONTEND = "None"

_TOOL_CACHES = frozenset(
    {"__pycache__", ".ruff_cache", ".pytest_cache", ".mypy_cache", ".venv"}
)

# In a flat-structure template, files with these extensions go to the agent
# directory; everything else goes to the project root.
_FLAT_AGENT_FILE_EXTENSIONS = frozenset({".py"})

# Flat-structure entries never copied into the generated project.
_FLAT_SKIP_FILES = frozenset(
    {"pyproject.toml", "uv.lock", "README.md", ".gitignore", "__pycache__"}
)


def copy_files(
    src: pathlib.Path,
    dst: pathlib.Path,
    agent_name: str | None = None,
    overwrite: bool = False,
    *,
    skip_manifest: bool = False,
    guidance_filename: str | None = None,
    clone_root: pathlib.Path | None = None,
    _visited: frozenset[tuple[int, int]] | None = None,
    _depth: int = 0,
) -> None:
    """
    Copy files with configurable behavior for exclusions and overwrites.

    Symlink handling: when *clone_root* is given (a fetched template), a symlink
    whose resolved target stays inside the repository is **materialized** — its
    real contents are copied so the generated project is portable — while an
    unsafe link (escaping the repo, targeting an ignored path / .env, dangling,
    or cyclic) raises ``ScaffoldSymlinkSecurityError``. With no *clone_root* (a bundled,
    trusted copy) any symlink is refused.

    Args:
        src: Source path
        dst: Destination path
        agent_name: Name of the agent (for agent-specific exclusions)
        overwrite: Whether to overwrite existing files (True) or skip them (False)
        guidance_filename: Write a root AGENTS.md under this name instead, so a
            template's guide replaces the base one whatever the project calls it.
        skip_manifest: Skip a root agents-cli-manifest.yaml. Set when copying a
            fetched template, whose manifest describes the template rather than
            the project and has already been read for config.
        clone_root: Repository root that materialized symlink targets must stay
            within. When None, symlinks are refused rather than followed.
        _visited: Internal — inodes of directories on the current recursion
            path, used to detect symlink cycles.
        _depth: Internal — current recursion depth, capped at MAX_COPY_DEPTH.
    """
    if _visited is None:
        _visited = frozenset()

    if _depth > MAX_COPY_DEPTH:
        raise ScaffoldSymlinkSecurityError(
            f"Template nesting exceeded {MAX_COPY_DEPTH} levels while copying "
            f"'{src}'; refusing to continue (possible symlink loop)."
        )

    if _should_skip(src, skip_manifest=skip_manifest):
        logging.debug("Skipping file/directory: %s", src)
        return

    if src.is_dir():
        _copy_dir(
            src,
            dst,
            agent_name=agent_name,
            overwrite=overwrite,
            skip_manifest=skip_manifest,
            guidance_filename=guidance_filename,
            clone_root=clone_root,
            visited=_visited,
            depth=_depth,
        )
    elif src.is_symlink():
        _materialize_symlink(
            src,
            dst,
            clone_root=clone_root,
            agent_name=agent_name,
            overwrite=overwrite,
            visited=_visited,
            depth=_depth,
        )
    else:
        _copy_file(src, dst, overwrite=overwrite)


def copy_frontend_files(frontend_type: str, project_template: pathlib.Path) -> None:
    """Copy files from the specified frontend folder directly to project root."""
    # Skip copying if frontend_type is "None" or empty
    if not frontend_type or frontend_type == "None":
        logging.debug("Frontend type is 'None' or empty, skipping frontend files")
        return

    # Get the frontends directory path
    frontends_path = pathlib.Path(__file__).parent.parent / "frontends" / frontend_type

    if frontends_path.exists():
        logging.debug("Copying frontend files from %s", frontends_path)
        # Copy frontend files directly to project root instead of a nested frontend directory
        copy_files(frontends_path, project_template, overwrite=True)
    else:
        logging.warning("Frontend type directory not found: %s", frontends_path)
        # Don't fall back to default if it's "None" - just skip
        if DEFAULT_FRONTEND != "None":
            logging.info("Falling back to default frontend: %s", DEFAULT_FRONTEND)
            copy_frontend_files(DEFAULT_FRONTEND, project_template)
        else:
            logging.debug("No default frontend configured, skipping frontend files")


def copy_deployment_files(
    deployment_target: str,
    agent_name: str,
    project_template: pathlib.Path,
    agent_directory: str = "app",
) -> None:
    """Copy files from the specified deployment target folder."""
    if not deployment_target:
        return

    deployment_path = (
        pathlib.Path(__file__).parent.parent / "deployment_targets" / deployment_target
    )

    if deployment_path.exists():
        logging.debug("Copying deployment files from %s", deployment_path)
        # Pass agent_name to respect agent-specific exclusions
        copy_files(
            deployment_path,
            project_template,
            agent_name=agent_name,
            overwrite=True,
        )
    else:
        logging.warning("Deployment target directory not found: %s", deployment_path)


def copy_flat_structure_agent_files(
    src: pathlib.Path,
    dst: pathlib.Path,
    agent_directory: str,
    *,
    clone_root: pathlib.Path | None = None,
    guidance_filename: str | None = None,
) -> None:
    """Copy agent files from a flat structure template to the agent directory.

    For flat structure templates, Python files (*.py) in the root are copied
    to the agent directory, while other files are copied to the project root.

    Security: the resolved destination path is verified to be contained within
    *dst* before any write occurs. Symlinks are handled like the standard path
    (see ``copy_files``): with *clone_root* a link whose target stays inside the
    repository is materialized as real files, otherwise it is refused.

    Args:
        src: Source path (template root with flat structure)
        dst: Destination path (project root)
        agent_directory: Target agent directory name
        clone_root: Repository root that materialized symlink targets must stay
            within. When None, symlinks are refused rather than followed.
        guidance_filename: Write a root AGENTS.md under this name instead, so a
            template's guide replaces the base one whatever the project calls it
            (matching the standard copy path).
    """
    agent_dst = dst / agent_directory
    # Path-containment guard: reject traversal that slipped past validation
    _assert_path_within(agent_dst, dst)
    agent_dst.mkdir(parents=True, exist_ok=True)

    for item in src.iterdir():
        if item.name.startswith(".") or item.name in _FLAT_SKIP_FILES:
            continue
        # A symlink is materialized from its vetted target; a plain entry is
        # copied from itself. Either way it is named and classified below by the
        # entry's own name, not the target's.
        source = require_safe_symlink(item, clone_root) if item.is_symlink() else item
        _place_flat_entry(
            item,
            source,
            dst=dst,
            agent_dst=agent_dst,
            clone_root=clone_root,
            guidance_filename=guidance_filename,
        )


def _should_skip(path: pathlib.Path, *, skip_manifest: bool) -> bool:
    """Whether a template entry should be skipped during copying.

    Drops compiled artifacts and build caches, VCS directories, the template's
    own ``.template`` config, and (optionally) its manifest.
    """
    if is_ignored_name(path.name):
        return True
    if path.suffix in [".pyc"]:
        return True
    if path.is_dir() and path.name == ".template":
        return True
    if skip_manifest and path.name == "agents-cli-manifest.yaml":
        return True
    return False


def _warn_if_long_windows_path(path: pathlib.Path) -> None:
    """Log a warning if *path* exceeds the Windows MAX_PATH limit."""
    if sys.platform == "win32":
        path_str = str(path.absolute())
        if len(path_str) >= 260:
            logging.error(
                "Path length (%d chars) may exceed Windows limit. "
                "Try using a shorter output directory.",
                len(path_str),
            )


def _copy_file(src: pathlib.Path, dst: pathlib.Path, *, overwrite: bool) -> None:
    """Copy a single regular file, creating parent dirs; skip if it exists."""
    if not overwrite and dst.exists():
        logging.debug("Skipping existing file: %s", dst)
        return
    try:
        dst.parent.mkdir(parents=True, exist_ok=True)
        logging.debug("Copying file: %s -> %s", src, dst)
        shutil.copy2(src, dst)
    except OSError:
        logging.error("Failed to copy: %s -> %s", src, dst)
        _warn_if_long_windows_path(dst)
        raise


def _dir_cycle_key(path: pathlib.Path) -> tuple[int, int] | None:
    """``(st_dev, st_ino)`` identity of a directory, for cycle detection."""
    try:
        st = path.stat()
    except OSError:
        return None
    return (st.st_dev, st.st_ino)


def _destination_for(
    item: pathlib.Path, dst: pathlib.Path, guidance_filename: str | None
) -> pathlib.Path:
    """Destination for *item*, renaming a root AGENTS.md to *guidance_filename*.

    Renamed whether AGENTS.md is a real file or a symlink to a file, so a
    template that shares its guide via an intra-repo symlink overwrites the base
    guidance file instead of leaving it in place and dropping a stray AGENTS.md.
    """
    if guidance_filename and item.name == "AGENTS.md" and item.is_file():
        return dst / guidance_filename
    return dst / item.name


def _materialize_symlink(
    link: pathlib.Path,
    dest: pathlib.Path,
    *,
    clone_root: pathlib.Path | None,
    agent_name: str | None,
    overwrite: bool,
    visited: frozenset[tuple[int, int]],
    depth: int,
) -> None:
    """Copy a symlink's resolved contents into the project, or reject it.

    The link is vetted by ``require_safe_symlink`` (which refuses it outright
    when there is no *clone_root*); a directory target is then walked via
    ``copy_files`` so nested symlinks are vetted too and the cycle guard sees the
    target's inode, while a file target is copied as real bytes.
    """
    target = require_safe_symlink(link, clone_root)
    if target.is_dir():
        copy_files(
            target,
            dest,
            agent_name,
            overwrite,
            clone_root=clone_root,
            _visited=visited,
            _depth=depth + 1,
        )
    else:
        logging.debug("Materializing symlink: %s -> %s", link, dest)
        _copy_file(target, dest, overwrite=overwrite)


def _copy_dir(
    src: pathlib.Path,
    dst: pathlib.Path,
    *,
    agent_name: str | None,
    overwrite: bool,
    skip_manifest: bool,
    guidance_filename: str | None,
    clone_root: pathlib.Path | None,
    visited: frozenset[tuple[int, int]],
    depth: int,
) -> None:
    """Copy the contents of directory *src* into *dst* (see ``copy_files``)."""
    # Cycle guard: re-entering a directory already on the recursion path means a
    # symlink pointed back up the tree.
    key = _dir_cycle_key(src)
    if key is not None and key in visited:
        raise ScaffoldSymlinkSecurityError(
            f"Symlink cycle detected while copying template at '{src}'."
        )
    child_visited = visited | {key} if key is not None else visited

    if not dst.exists():
        try:
            dst.mkdir(parents=True)
            logging.debug("Created directory: '%s'", dst)
        except OSError as e:
            logging.error("Failed to create directory: %s", dst)
            logging.error("Error: %s", e)
            raise

    for item in src.iterdir():
        if _should_skip(item, skip_manifest=skip_manifest):
            logging.debug("Skipping file/directory: %s", item)
            continue
        dest = _destination_for(item, dst, guidance_filename)
        if item.is_symlink():
            _materialize_symlink(
                item,
                dest,
                clone_root=clone_root,
                agent_name=agent_name,
                overwrite=overwrite,
                visited=child_visited,
                depth=depth,
            )
        elif item.is_dir():
            copy_files(
                item,
                dest,
                agent_name,
                overwrite,
                clone_root=clone_root,
                _visited=child_visited,
                _depth=depth + 1,
            )
        else:
            _copy_file(item, dest, overwrite=overwrite)


def _assert_path_within(
    candidate: pathlib.Path,
    root: pathlib.Path,
) -> None:
    """Raise ValueError if *candidate* is not contained within *root*.

    Both paths are resolved to their real absolute forms before the check so
    that symbolic links and ``..`` components cannot be used to bypass the
    boundary.

    Args:
        candidate: The path that must be inside *root*.
        root: The allowed root directory.

    Raises:
        ValueError: If *candidate* resolves to a location outside *root*.
    """
    try:
        candidate.resolve().relative_to(root.resolve())
    except ValueError as e:
        raise ValueError(
            f"Security check failed: '{candidate}' would be written "
            f"outside the project directory '{root}'. "
            "Aborting to prevent path-traversal exploitation."
        ) from e


def _place_flat_entry(
    item: pathlib.Path,
    source: pathlib.Path,
    *,
    dst: pathlib.Path,
    agent_dst: pathlib.Path,
    clone_root: pathlib.Path | None,
    guidance_filename: str | None = None,
) -> None:
    """Copy one flat-structure entry, reading bytes from *source*.

    Placement follows *item*'s own name: a directory is materialized (replacing
    any existing one) at the project root, a ``.py`` file lands in the agent
    directory, and anything else in the project root — where a root AGENTS.md is
    renamed to *guidance_filename* (see ``_destination_for``). *source* is the
    entry itself, or the vetted target when *item* is a symlink.
    """
    if source.is_dir():
        dest_dir = dst / item.name
        _assert_path_within(dest_dir, dst)
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        copy_files(source, dest_dir, clone_root=clone_root, overwrite=True)
        return

    if item.suffix in _FLAT_AGENT_FILE_EXTENSIONS:
        dest_file = agent_dst / item.name
    else:
        dest_file = _destination_for(item, dst, guidance_filename)
    _assert_path_within(dest_file, dst)
    _copy_file(source, dest_file, overwrite=True)
