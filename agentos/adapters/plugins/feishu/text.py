"""飞书消息文本分片：按换行符边界分片，感知 Markdown 代码块状态"""


def chunk_text(text: str, limit: int = 4000) -> list[str]:
    """按换行符边界分片，感知 Markdown 代码块状态。"""
    if len(text) <= limit:
        return [text]

    chunks: list[str] = []
    remaining = text
    while remaining:
        if len(remaining) <= limit:
            chunks.append(remaining)
            break

        cut = remaining.rfind("\n\n", 0, limit)
        if cut <= 0:
            cut = remaining.rfind("\n", 0, limit)
        if cut <= 0:
            cut = limit

        chunk = remaining[:cut].rstrip()
        rest = remaining[cut:].lstrip("\n")

        fence_count = chunk.count("```")
        if fence_count % 2 == 1:
            chunk += "\n```"
            rest = "```\n" + rest

        chunks.append(chunk)
        remaining = rest

    return chunks
