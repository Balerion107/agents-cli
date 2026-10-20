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

"""Checks for values passed to git as arguments.

A value read from a project file or typed by the user can reach git as an
option (e.g. ``--upload-pack=<cmd>``, which runs a command). Callers check
values with these before building a git command, and also put ``--`` before
positional arguments where the git subcommand accepts it.
"""

import re

# Only a full 40-char SHA is unambiguous. A short/partial hex string could
# instead be a branch or tag named like hex (e.g. "cafe123").
_COMMIT_SHA_RE = re.compile(r"[0-9a-f]{40}")


def is_commit_sha(value: str) -> bool:
    """True for a full 40-char lowercase hex commit SHA."""
    # fullmatch, not match with "$": "$" also matches before a trailing newline.
    return bool(_COMMIT_SHA_RE.fullmatch(value))


def is_option_like(value: str) -> bool:
    """True when git would read ``value`` as an option rather than an operand.

    No valid git ref name starts with "-".
    """
    return value.startswith("-")
