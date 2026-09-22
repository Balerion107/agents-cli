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

"""Security vetting for symlinks found in fetched template sources.

Isolates the CWE-59 policy: a template may share code via a symlink that stays
within its own repository, but a link that escapes the repo, points at VCS
metadata / an environment file, dangles, or forms a cycle is refused. The copy
machinery in ``copy_files.py`` calls :func:`require_safe_symlink` and then
materializes the resolved target as real files.
"""

import os
import pathlib

from .fs import is_ignored_name, is_secret_file

# Backstop to the inode-based cycle guard: refuse to materialize a template
# tree nested more deeply than this (a symlink loop, or a pathological repo).
MAX_COPY_DEPTH = 64


class ScaffoldSymlinkSecurityError(ValueError):
    """A template source contains a symlink that cannot be safely materialized.

    Subclasses ``ValueError`` so ``create()``'s handler renders it as a concise
    one-line ``ClickException`` rather than a traceback.
    """


def resolve_safe_symlink(link: pathlib.Path, clone_root: pathlib.Path) -> pathlib.Path:
    """Resolve a template symlink and verify it is safe to materialize.

    A symlink is safe only when its fully-resolved target exists and stays
    within *clone_root* (the fetched repository), and does not point at an
    ignored path (VCS metadata, caches, build output, dependencies) or an
    environment/secret file (``.env``). This preserves the CWE-59 protection — a
    link escaping the repository (e.g. ``id_rsa -> ~/.ssh/id_rsa``) is still
    refused — while letting a template share code within its own repo.

    The containment check is against the **cloned repo root**, not the template
    subdirectory: a shared library naturally sits at the repo root while the
    template is a subdirectory, so a link legitimately points "up" out of the
    template dir but never out of the repo.

    Args:
        link: The symlink found in the template source.
        clone_root: Root the resolved target must stay within (the clone).

    Returns:
        The canonical (fully resolved) target path.

    Raises:
        ScaffoldSymlinkSecurityError: If the link is dangling, cyclic, escapes the
            repo, or targets an ignored path / an environment file.
    """
    root = clone_root.resolve()
    try:
        # strict=True normalizes `..`, follows intermediate links, and fails on
        # a dangling target so the generated project never gets a dead link.
        target = link.resolve(strict=True)
    except (OSError, RuntimeError) as e:
        # FileNotFoundError (dangling target) or ELOOP / "too many levels of
        # symbolic links" (a symlink cycle).
        raise ScaffoldSymlinkSecurityError(
            f"Symlink '{_symlink_display(link)}' points to a missing target or "
            "forms a loop. Copy the shared files directly into the template "
            "instead of linking to them."
        ) from e

    if not target.is_relative_to(root):
        raise ScaffoldSymlinkSecurityError(
            f"Symlink '{link}' resolves to '{target}', which "
            "is outside the template repository. For security reasons a symlink "
            "may not escape the repository; copy the shared files directly into "
            "the template instead."
        )

    rel_parts = target.relative_to(root).parts
    if any(is_ignored_name(part) for part in rel_parts):
        raise ScaffoldSymlinkSecurityError(
            f"Symlink '{_symlink_display(link)}' resolves into an ignored path "
            "(version-control metadata, caches, build output, or dependencies), "
            "which is never copied into a generated project."
        )
    if is_secret_file(target.name):
        raise ScaffoldSymlinkSecurityError(
            f"Symlink '{link}' targets a credential file "
            f"('{target.name}'); refusing to copy it into the project."
        )
    return target


def require_safe_symlink(
    link: pathlib.Path, clone_root: pathlib.Path | None
) -> pathlib.Path:
    """Resolve *link* to its safe target, or reject it.

    With no *clone_root* (a bundled, trusted copy) there is no repository to
    contain the link, so any symlink is refused. Otherwise the link is vetted by
    :func:`resolve_safe_symlink`.
    """
    if clone_root is None:
        raise ScaffoldSymlinkSecurityError(
            f"Symlink detected at '{_symlink_display(link)}'. Symlinks are not "
            "allowed here for security reasons; copy the files directly instead."
        )
    return resolve_safe_symlink(link, clone_root)


def _symlink_display(link: pathlib.Path) -> str:
    """``<link> -> <raw target>`` for error messages, best-effort."""
    try:
        return f"{link} -> {os.readlink(link)}"
    except OSError:
        return f"{link} -> (unresolvable)"
