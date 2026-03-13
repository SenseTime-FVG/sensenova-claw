"""文本分块器：按段落/句子边界智能分块"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass


@dataclass
class MemoryChunk:
    chunk_id: str
    path: str
    start_line: int
    end_line: int
    text: str


class Chunker:
    """按段落/句子边界分块，保留 overlap 确保上下文连续性。

    使用字符数近似 token 数（中文约 1.5 字符/token，英文约 4 字符/token，
    取平均 ~3 字符/token）。
    """

    CHARS_PER_TOKEN = 3

    def chunk(
        self,
        text: str,
        path: str,
        chunk_size: int = 400,
        overlap: int = 80,
    ) -> list[MemoryChunk]:
        """将文本分块，返回 MemoryChunk 列表

        Args:
            text: 原始文本
            path: workspace 相对路径
            chunk_size: 目标 token 数
            overlap: 重叠 token 数
        """
        if not text.strip():
            return []

        target_chars = chunk_size * self.CHARS_PER_TOKEN
        overlap_chars = overlap * self.CHARS_PER_TOKEN

        lines = text.split("\n")
        chunks: list[MemoryChunk] = []

        current_text = ""
        current_start = 1  # 行号从 1 开始
        current_end = 0

        for i, line in enumerate(lines, start=1):
            line_with_newline = line + "\n"
            current_text += line_with_newline
            current_end = i

            if len(current_text) >= target_chars:
                # 尝试在段落或句子边界切分
                split_pos = self._find_split_point(current_text, target_chars)
                chunk_text = current_text[:split_pos].strip()

                if chunk_text:
                    chunks.append(MemoryChunk(
                        chunk_id=uuid.uuid4().hex[:16],
                        path=path,
                        start_line=current_start,
                        end_line=current_end,
                        text=chunk_text,
                    ))

                # 保留 overlap 部分
                remaining = current_text[max(0, split_pos - overlap_chars):]
                # 回溯计算新的起始行号
                overlap_line_count = remaining.count("\n")
                current_start = max(1, current_end - overlap_line_count)
                current_text = remaining

        # 处理剩余文本
        remaining_text = current_text.strip()
        if remaining_text:
            chunks.append(MemoryChunk(
                chunk_id=uuid.uuid4().hex[:16],
                path=path,
                start_line=current_start,
                end_line=current_end,
                text=remaining_text,
            ))

        return chunks

    def _find_split_point(self, text: str, target: int) -> int:
        """在目标位置附近寻找合适的切分点（段落 > 句子 > 词边界）"""
        # 优先在段落边界切分（双换行）
        para_pattern = re.compile(r"\n\n")
        best = target
        for m in para_pattern.finditer(text):
            pos = m.end()
            if pos >= target * 0.6:
                return pos
            if pos <= target * 1.2:
                best = pos

        # 其次在句子边界切分
        sent_pattern = re.compile(r"[。！？.!?]\s*\n?")
        for m in sent_pattern.finditer(text):
            pos = m.end()
            if target * 0.8 <= pos <= target * 1.2:
                return pos

        return best
