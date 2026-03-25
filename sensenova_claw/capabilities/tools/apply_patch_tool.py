from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Literal

from sensenova_claw.capabilities.tools.base import Tool, ToolRiskLevel
from sensenova_claw.capabilities.tools.builtin import _resolve_with_workdir

BEGIN_PATCH_MARKER = "*** Begin Patch"
END_PATCH_MARKER = "*** End Patch"
ADD_FILE_MARKER = "*** Add File: "
DELETE_FILE_MARKER = "*** Delete File: "
UPDATE_FILE_MARKER = "*** Update File: "
MOVE_TO_MARKER = "*** Move to: "
EOF_MARKER = "*** End of File"
CHANGE_CONTEXT_MARKER = "@@ "
EMPTY_CHANGE_CONTEXT_MARKER = "@@"


@dataclass
class AddFileHunk:
    kind: Literal["add"]
    path: str
    contents: str


@dataclass
class DeleteFileHunk:
    kind: Literal["delete"]
    path: str


@dataclass
class UpdateFileChunk:
    change_context: str | None
    old_lines: list[str]
    new_lines: list[str]
    is_end_of_file: bool


@dataclass
class UpdateFileHunk:
    kind: Literal["update"]
    path: str
    move_path: str | None
    chunks: list[UpdateFileChunk]


Hunk = AddFileHunk | DeleteFileHunk | UpdateFileHunk


class ApplyPatchTool(Tool):
    name = "apply_patch"
    description = (
        "Apply a patch to one or more files using the apply_patch format. "
        "The input should include *** Begin Patch and *** End Patch markers."
    )
    risk_level = ToolRiskLevel.MEDIUM
    parameters = {
        "type": "object",
        "properties": {
            "input": {
                "type": "string",
                "description": (
                    "Patch content using the *** Begin Patch/End Patch format. "
                    "Use *** Add File:, *** Delete File:, or *** Update File: as hunk headers. "
                    "Within an update hunk, @@ starts a chunk; use plain @@ for no explicit context, "
                    "or @@ <context> to anchor the chunk on an existing line. "
                    "Use *** Move to: inside *** Update File: to rename a file, and *** End of File "
                    "for EOF-only inserts. "
                    "Example:\n"
                    "*** Begin Patch\n"
                    "*** Add File: path/to/file.txt\n"
                    "+line 1\n"
                    "+line 2\n"
                    "*** Update File: src/app.py\n"
                    "@@\n"
                    "-old line\n"
                    "+new line\n"
                    "*** Delete File: obsolete.txt\n"
                    "*** End Patch"
                ),
            },
        },
        "required": ["input"],
    }

    async def execute(self, **kwargs: Any) -> Any:
        agent_workdir: str | None = kwargs.pop("_agent_workdir", None)
        path_policy = kwargs.pop("_path_policy", None)
        patch_input = str(kwargs.get("input", ""))

        try:
            result = apply_patch_text(
                patch_input,
                agent_workdir=agent_workdir,
                path_policy=path_policy,
            )
        except Exception as exc:
            return {"success": False, "error": str(exc).strip() or type(exc).__name__}

        return {
            "success": True,
            "summary": result["summary"],
            "message": result["message"],
        }


def apply_patch_text(
    patch_input: str,
    *,
    agent_workdir: str | None,
    path_policy: Any = None,
) -> dict[str, Any]:
    hunks = parse_patch_text(patch_input)
    if not hunks:
        raise ValueError("No files were modified.")

    summary = {"added": [], "modified": [], "deleted": []}
    seen = {"added": set(), "modified": set(), "deleted": set()}

    for hunk in hunks:
        if isinstance(hunk, AddFileHunk):
            target_path, display_path = resolve_patch_path(
                hunk.path,
                agent_workdir=agent_workdir,
                path_policy=path_policy,
            )
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(hunk.contents, encoding="utf-8")
            record_summary(summary, seen, "added", display_path)
            continue

        if isinstance(hunk, DeleteFileHunk):
            target_path, display_path = resolve_patch_path(
                hunk.path,
                agent_workdir=agent_workdir,
                path_policy=path_policy,
            )
            if not target_path.exists():
                raise FileNotFoundError(f"文件不存在: {display_path}")
            target_path.unlink()
            record_summary(summary, seen, "deleted", display_path)
            continue

        target_path, _ = resolve_patch_path(
            hunk.path,
            agent_workdir=agent_workdir,
            path_policy=path_policy,
        )
        applied = apply_update_hunks(target_path, hunk.chunks)

        if hunk.move_path:
            move_path, move_display = resolve_patch_path(
                hunk.move_path,
                agent_workdir=agent_workdir,
                path_policy=path_policy,
            )
            move_path.parent.mkdir(parents=True, exist_ok=True)
            move_path.write_text(applied, encoding="utf-8")
            target_path.unlink()
            record_summary(summary, seen, "modified", move_display)
        else:
            target_path.write_text(applied, encoding="utf-8")
            record_summary(summary, seen, "modified", to_display_path(target_path, agent_workdir))

    return {
        "summary": summary,
        "message": format_summary(summary),
    }


def record_summary(
    summary: dict[str, list[str]],
    seen: dict[str, set[str]],
    bucket: Literal["added", "modified", "deleted"],
    value: str,
) -> None:
    if value in seen[bucket]:
        return
    seen[bucket].add(value)
    summary[bucket].append(value)


def format_summary(summary: dict[str, list[str]]) -> str:
    lines = ["Success. Updated the following files:"]
    for file_path in summary["added"]:
        lines.append(f"A {file_path}")
    for file_path in summary["modified"]:
        lines.append(f"M {file_path}")
    for file_path in summary["deleted"]:
        lines.append(f"D {file_path}")
    return "\n".join(lines)


def resolve_patch_path(
    raw_path: str,
    *,
    agent_workdir: str | None,
    path_policy: Any = None,
) -> tuple[Path, str]:
    resolved = _resolve_with_workdir(raw_path, agent_workdir)
    if path_policy:
        verdict = path_policy.check_write(str(resolved))
        verdict_name = getattr(verdict, "value", str(verdict))
        if verdict_name == "deny":
            raise PermissionError(f"系统目录禁止写入: {raw_path}")
        if verdict_name == "need_grant":
            raise PermissionError(f"该路径未授权，请先获得用户许可: {raw_path}")
    return resolved, to_display_path(resolved, agent_workdir)


def to_display_path(path: Path, agent_workdir: str | None) -> str:
    if not agent_workdir:
        return str(path)
    workdir = Path(agent_workdir).expanduser().resolve()
    try:
        return str(path.relative_to(workdir))
    except ValueError:
        return str(path)


def parse_patch_text(patch_input: str) -> list[Hunk]:
    trimmed = patch_input.strip()
    if not trimmed:
        raise ValueError("Invalid patch: input is empty.")

    lines = trimmed.splitlines()
    validated = check_patch_boundaries_lenient(lines)

    hunks: list[Hunk] = []
    remaining = validated[1:-1]
    line_number = 2
    while remaining:
        hunk, consumed = parse_one_hunk(remaining, line_number)
        hunks.append(hunk)
        remaining = remaining[consumed:]
        line_number += consumed

    return hunks


def check_patch_boundaries_lenient(lines: list[str]) -> list[str]:
    strict_error = check_patch_boundaries_strict(lines)
    if not strict_error:
        return lines

    if len(lines) < 4:
        raise ValueError(strict_error)
    first = lines[0]
    last = lines[-1]
    if first in {"<<EOF", "<<'EOF'", '<<"EOF"'} and last.endswith("EOF"):
        inner = lines[1:-1]
        inner_error = check_patch_boundaries_strict(inner)
        if not inner_error:
            return inner
        raise ValueError(inner_error)

    raise ValueError(strict_error)


def check_patch_boundaries_strict(lines: list[str]) -> str | None:
    first = lines[0].strip() if lines else ""
    last = lines[-1].strip() if lines else ""
    if first != BEGIN_PATCH_MARKER:
        return "The first line of the patch must be '*** Begin Patch'"
    if last != END_PATCH_MARKER:
        return "The last line of the patch must be '*** End Patch'"
    return None


def parse_one_hunk(lines: list[str], line_number: int) -> tuple[Hunk, int]:
    if not lines:
        raise ValueError(f"Invalid patch hunk at line {line_number}: empty hunk")
    first_line = lines[0].strip()
    if first_line.startswith(ADD_FILE_MARKER):
        return parse_add_file_hunk(lines), consume_add_hunk(lines)
    if first_line.startswith(DELETE_FILE_MARKER):
        target_path = first_line[len(DELETE_FILE_MARKER):]
        return DeleteFileHunk(kind="delete", path=target_path), 1
    if first_line.startswith(UPDATE_FILE_MARKER):
        return parse_update_file_hunk(lines, line_number)
    raise ValueError(
        f"Invalid patch hunk at line {line_number}: '{lines[0]}' is not a valid hunk header. "
        "Valid hunk headers: '*** Add File: {path}', '*** Delete File: {path}', "
        "'*** Update File: {path}'"
    )


def parse_add_file_hunk(lines: list[str]) -> AddFileHunk:
    target_path = lines[0].strip()[len(ADD_FILE_MARKER):]
    contents: list[str] = []
    for line in lines[1:]:
        if not line.startswith("+"):
            break
        contents.append(line[1:])
    return AddFileHunk(kind="add", path=target_path, contents="\n".join(contents) + "\n")


def consume_add_hunk(lines: list[str]) -> int:
    consumed = 1
    for line in lines[1:]:
        if not line.startswith("+"):
            break
        consumed += 1
    return consumed


def parse_update_file_hunk(lines: list[str], line_number: int) -> tuple[UpdateFileHunk, int]:
    target_path = lines[0].strip()[len(UPDATE_FILE_MARKER):]
    remaining = lines[1:]
    consumed = 1
    move_path: str | None = None

    move_candidate = remaining[0].strip() if remaining else None
    if move_candidate and move_candidate.startswith(MOVE_TO_MARKER):
        move_path = move_candidate[len(MOVE_TO_MARKER):]
        remaining = remaining[1:]
        consumed += 1

    chunks: list[UpdateFileChunk] = []
    while remaining:
        if remaining[0].strip() == "":
            remaining = remaining[1:]
            consumed += 1
            continue
        if remaining[0].startswith("***"):
            break
        chunk, chunk_consumed = parse_update_file_chunk(
            remaining,
            line_number + consumed,
            allow_missing_context=len(chunks) == 0,
        )
        chunks.append(chunk)
        remaining = remaining[chunk_consumed:]
        consumed += chunk_consumed

    if not chunks:
        raise ValueError(
            f"Invalid patch hunk at line {line_number}: Update file hunk for path '{target_path}' is empty"
        )

    return (
        UpdateFileHunk(kind="update", path=target_path, move_path=move_path, chunks=chunks),
        consumed,
    )


def parse_update_file_chunk(
    lines: list[str],
    line_number: int,
    allow_missing_context: bool,
) -> tuple[UpdateFileChunk, int]:
    if not lines:
        raise ValueError(
            f"Invalid patch hunk at line {line_number}: Update hunk does not contain any lines"
        )

    change_context: str | None = None
    start_index = 0
    if lines[0] == EMPTY_CHANGE_CONTEXT_MARKER:
        start_index = 1
    elif lines[0].startswith(CHANGE_CONTEXT_MARKER):
        change_context = lines[0][len(CHANGE_CONTEXT_MARKER):]
        start_index = 1
    elif not allow_missing_context:
        raise ValueError(
            f"Invalid patch hunk at line {line_number}: Expected update hunk to start with a @@ "
            f"context marker, got: '{lines[0]}'"
        )

    if start_index >= len(lines):
        raise ValueError(
            f"Invalid patch hunk at line {line_number + 1}: Update hunk does not contain any lines"
        )

    old_lines: list[str] = []
    new_lines: list[str] = []
    parsed_lines = 0
    is_end_of_file = False

    for line in lines[start_index:]:
        if line == EOF_MARKER:
            if parsed_lines == 0:
                raise ValueError(
                    f"Invalid patch hunk at line {line_number + 1}: Update hunk does not contain any lines"
                )
            is_end_of_file = True
            parsed_lines += 1
            break

        marker = line[0] if line else ""
        if not marker:
            old_lines.append("")
            new_lines.append("")
            parsed_lines += 1
            continue
        if marker == " ":
            value = line[1:]
            old_lines.append(value)
            new_lines.append(value)
            parsed_lines += 1
            continue
        if marker == "+":
            new_lines.append(line[1:])
            parsed_lines += 1
            continue
        if marker == "-":
            old_lines.append(line[1:])
            parsed_lines += 1
            continue

        if parsed_lines == 0:
            raise ValueError(
                f"Invalid patch hunk at line {line_number + 1}: Unexpected line found in update hunk: '{line}'. "
                "Every line should start with ' ' (context line), '+' (added line), or '-' (removed line)"
            )
        if line.startswith("***") or line.startswith("@@"):
            break
        break

    return (
        UpdateFileChunk(
            change_context=change_context,
            old_lines=old_lines,
            new_lines=new_lines,
            is_end_of_file=is_end_of_file,
        ),
        parsed_lines + start_index,
    )


def apply_update_hunks(file_path: Path, chunks: list[UpdateFileChunk]) -> str:
    if not file_path.exists():
        raise FileNotFoundError(f"文件不存在: {file_path}")

    original_contents = file_path.read_text(encoding="utf-8")
    original_lines = original_contents.split("\n")
    if original_lines and original_lines[-1] == "":
        original_lines.pop()

    replacements = compute_replacements(original_lines, str(file_path), chunks)
    new_lines = apply_replacements(original_lines, replacements)
    if not new_lines or new_lines[-1] != "":
        new_lines.append("")
    return "\n".join(new_lines)


def compute_replacements(
    original_lines: list[str],
    file_path: str,
    chunks: list[UpdateFileChunk],
) -> list[tuple[int, int, list[str]]]:
    replacements: list[tuple[int, int, list[str]]] = []
    line_index = 0

    for chunk in chunks:
        if chunk.change_context is not None:
            context_index = seek_sequence(original_lines, [chunk.change_context], line_index, False)
            if context_index is None:
                raise ValueError(f"Failed to find context '{chunk.change_context}' in {file_path}")
            line_index = context_index + 1

        if not chunk.old_lines:
            replacements.append((len(original_lines), 0, chunk.new_lines))
            continue

        pattern = list(chunk.old_lines)
        new_slice = list(chunk.new_lines)
        found = seek_sequence(original_lines, pattern, line_index, chunk.is_end_of_file)

        if found is None and pattern and pattern[-1] == "":
            pattern = pattern[:-1]
            if new_slice and new_slice[-1] == "":
                new_slice = new_slice[:-1]
            found = seek_sequence(original_lines, pattern, line_index, chunk.is_end_of_file)

        if found is None:
            raise ValueError(
                f"Failed to find expected lines in {file_path}:\n" + "\n".join(chunk.old_lines)
            )

        replacements.append((found, len(pattern), new_slice))
        line_index = found + len(pattern)

    replacements.sort(key=lambda item: item[0])
    return replacements


def apply_replacements(
    lines: list[str],
    replacements: list[tuple[int, int, list[str]]],
) -> list[str]:
    result = list(lines)
    for start_index, old_len, new_lines in reversed(replacements):
        del result[start_index:start_index + old_len]
        for offset, line in enumerate(new_lines):
            result.insert(start_index + offset, line)
    return result


def seek_sequence(
    lines: list[str],
    pattern: list[str],
    start: int,
    eof: bool,
) -> int | None:
    if not pattern:
        return start
    if len(pattern) > len(lines):
        return None

    max_start = len(lines) - len(pattern)
    search_start = max_start if eof and len(lines) >= len(pattern) else start
    if search_start > max_start:
        return None

    normalizers: list[Callable[[str], str]] = [
        lambda value: value,
        lambda value: value.rstrip(),
        lambda value: value.strip(),
        lambda value: normalize_punctuation(value.strip()),
    ]
    for normalize in normalizers:
        for idx in range(search_start, max_start + 1):
            if lines_match(lines, pattern, idx, normalize):
                return idx
    return None


def lines_match(
    lines: list[str],
    pattern: list[str],
    start: int,
    normalize: Callable[[str], str],
) -> bool:
    for offset, expected in enumerate(pattern):
        if normalize(lines[start + offset]) != normalize(expected):
            return False
    return True


def normalize_punctuation(value: str) -> str:
    table = {
        "\u2010": "-",
        "\u2011": "-",
        "\u2012": "-",
        "\u2013": "-",
        "\u2014": "-",
        "\u2015": "-",
        "\u2212": "-",
        "\u2018": "'",
        "\u2019": "'",
        "\u201A": "'",
        "\u201B": "'",
        "\u201C": '"',
        "\u201D": '"',
        "\u201E": '"',
        "\u201F": '"',
        "\u00A0": " ",
        "\u2002": " ",
        "\u2003": " ",
        "\u2004": " ",
        "\u2005": " ",
        "\u2006": " ",
        "\u2007": " ",
        "\u2008": " ",
        "\u2009": " ",
        "\u200A": " ",
        "\u202F": " ",
        "\u205F": " ",
        "\u3000": " ",
    }
    return "".join(table.get(char, char) for char in value)
