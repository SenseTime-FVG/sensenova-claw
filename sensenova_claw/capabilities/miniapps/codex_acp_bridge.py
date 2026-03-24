from __future__ import annotations

import asyncio
import contextlib
import json
import os
import shlex
import sys
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable


def _extract_prompt_text(prompt: Any) -> str:
    if isinstance(prompt, str):
        return prompt.strip()
    if not isinstance(prompt, list):
        return ""

    chunks: list[str] = []
    for item in prompt:
        if not isinstance(item, dict):
            continue
        if item.get("type") != "text":
            continue
        text = str(item.get("text") or "").strip()
        if text:
            chunks.append(text)
    return "\n\n".join(chunks).strip()


def _load_extra_codex_args() -> list[str]:
    raw = str(os.getenv("CODEX_EXEC_ARGS", "") or "").strip()
    if not raw:
        return []
    return shlex.split(raw)


def build_codex_exec_command(
    *,
    codex_bin: str,
    cwd: str,
    prompt: str,
    output_file: str,
    model: str = "",
    profile: str = "",
    extra_args: list[str] | None = None,
) -> list[str]:
    command = [
        codex_bin,
        "exec",
        "--skip-git-repo-check",
        "--json",
        "--full-auto",
        "--output-last-message",
        output_file,
        "--cd",
        cwd,
    ]
    if model.strip():
        command.extend(["--model", model.strip()])
    if profile.strip():
        command.extend(["--profile", profile.strip()])
    command.extend(extra_args or [])
    command.append(prompt)
    return command


def _summarize_codex_stream_line(text: str) -> str:
    stripped = text.strip()
    if not stripped:
        return ""

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        return stripped

    if not isinstance(parsed, dict):
        return stripped

    for key in ("message", "msg", "summary", "title"):
        value = parsed.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    event_type = parsed.get("type")
    if isinstance(event_type, str) and event_type.strip():
        return stripped
    return stripped


@dataclass
class CodexBridgeSession:
    session_id: str
    cwd: str


class CodexACPBridge:
    """把 Sensenova-Claw 当前使用的 ACP 子集桥接到 `codex exec`。"""

    def __init__(
        self,
        *,
        writer: Callable[[dict[str, Any]], None] | None = None,
        runner: Callable[[CodexBridgeSession, str], Any] | None = None,
    ) -> None:
        self._writer = writer or _write_json_line
        self._runner = runner or self._run_codex_prompt
        self._sessions: dict[str, CodexBridgeSession] = {}
        self._codex_bin = str(os.getenv("CODEX_BIN", "codex") or "codex").strip() or "codex"
        self._codex_model = str(os.getenv("CODEX_MODEL", "") or "").strip()
        self._codex_profile = str(os.getenv("CODEX_PROFILE", "") or "").strip()
        self._extra_args = _load_extra_codex_args()

    async def serve(self) -> None:
        while True:
            line = await asyncio.to_thread(sys.stdin.readline)
            if not line:
                return
            text = line.strip()
            if not text:
                continue

            try:
                message = json.loads(text)
            except json.JSONDecodeError:
                await self._notify("codex.bridge.error", f"忽略非法 JSON: {text}")
                continue
            await self.handle_message(message)

    async def handle_message(self, message: dict[str, Any]) -> None:
        request_id = message.get("id")
        method = str(message.get("method") or "").strip()
        params = message.get("params") or {}

        if not method:
            if request_id is not None:
                self._write({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"message": "missing method"},
                })
            return

        try:
            result = await self._dispatch(method, params)
        except Exception as exc:
            if request_id is not None:
                self._write({
                    "jsonrpc": "2.0",
                    "id": request_id,
                    "error": {"message": str(exc)},
                })
            return

        if request_id is not None:
            self._write({
                "jsonrpc": "2.0",
                "id": request_id,
                "result": result,
            })

    async def _dispatch(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if method == "initialize":
            return {
                "protocolVersion": 1,
                "agentInfo": {
                    "name": "Codex ACP Bridge",
                    "version": "0.1.0",
                },
                "serverCapabilities": {
                    "session": True,
                    "prompt": True,
                },
            }

        if method == "session/new":
            cwd = str(params.get("cwd") or "").strip()
            if not cwd:
                raise RuntimeError("session/new 缺少 cwd")
            session_id = f"codex-{uuid.uuid4().hex}"
            self._sessions[session_id] = CodexBridgeSession(session_id=session_id, cwd=cwd)
            await self._notify("codex.bridge.status", f"session created: {session_id}")
            return {"sessionId": session_id}

        if method == "session/prompt":
            session_id = str(params.get("sessionId") or "").strip()
            session = self._sessions.get(session_id)
            if session is None:
                raise RuntimeError(f"unknown session: {session_id}")
            prompt_text = _extract_prompt_text(params.get("prompt"))
            if not prompt_text:
                raise RuntimeError("session/prompt 缺少文本 prompt")
            return await self._runner(session, prompt_text)

        raise RuntimeError(f"unsupported method: {method}")

    async def _run_codex_prompt(self, session: CodexBridgeSession, prompt_text: str) -> dict[str, Any]:
        output_file = tempfile.NamedTemporaryFile(prefix="codex-acp-", suffix=".txt", delete=False)
        output_file.close()
        output_path = Path(output_file.name)

        command = build_codex_exec_command(
            codex_bin=self._codex_bin,
            cwd=session.cwd,
            prompt=prompt_text,
            output_file=str(output_path),
            model=self._codex_model,
            profile=self._codex_profile,
            extra_args=self._extra_args,
        )

        await self._notify("codex.bridge.status", f"启动 Codex: {' '.join(shlex.quote(part) for part in command[:-1])}")
        proc = await asyncio.create_subprocess_exec(
            *command,
            cwd=session.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=os.environ.copy(),
        )

        stdout_lines, stderr_lines = await asyncio.gather(
            self._pump_stream(proc.stdout, "codex.bridge.stdout"),
            self._pump_stream(proc.stderr, "codex.bridge.stderr"),
        )
        return_code = await proc.wait()

        output_text = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
        with contextlib.suppress(FileNotFoundError):
            output_path.unlink()

        if return_code != 0:
            error_text = output_text or "\n".join(stderr_lines[-20:]) or "\n".join(stdout_lines[-20:])
            raise RuntimeError(error_text or f"codex exec failed with exit code {return_code}")

        final_text = output_text or "Codex 执行完成，但没有输出最终消息。"
        await self._notify("codex.bridge.status", "Codex 执行完成")
        return {
            "content": {
                "text": final_text,
            },
            "exitCode": return_code,
        }

    async def _pump_stream(self, stream: asyncio.StreamReader | None, method: str) -> list[str]:
        if stream is None:
            return []

        lines: list[str] = []
        while True:
            chunk = await stream.readline()
            if not chunk:
                return lines
            text = chunk.decode("utf-8", errors="replace").strip()
            if not text:
                continue
            lines.append(text)
            summary = _summarize_codex_stream_line(text)
            if summary:
                await self._notify(method, summary)

    async def _notify(self, method: str, text: str) -> None:
        self._write({
            "jsonrpc": "2.0",
            "method": method,
            "params": {
                "content": {
                    "text": text,
                },
            },
        })

    def _write(self, payload: dict[str, Any]) -> None:
        self._writer(payload)


def _write_json_line(payload: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(payload, ensure_ascii=False) + "\n")
    sys.stdout.flush()


async def _main() -> None:
    bridge = CodexACPBridge()
    await bridge.serve()


if __name__ == "__main__":
    asyncio.run(_main())
