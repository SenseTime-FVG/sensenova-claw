#!/usr/bin/env python3
"""测试 Obsidian 工具（仅本地功能）"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))


async def test_local_detection():
    """测试本地 vault 检测"""
    print("\n=== 测试: 本地 Vault 检测 ===")

    from sensenova_claw.capabilities.tools.obsidian_tool import (
        _detect_obsidian_vaults,
        _get_configured_local_vaults,
    )

    detected = _detect_obsidian_vaults()
    print(f"自动检测到 {len(detected)} 个 vault:")
    for vault in detected:
        print(f"  - {vault.name}: {vault}")

    configured = _get_configured_local_vaults()
    print(f"\n配置的 vault: {len(configured)} 个")
    for vault in configured:
        print(f"  - {vault.name}: {vault}")

    return detected or configured


async def test_parse_functions():
    """测试解析函数"""
    print("\n=== 测试: Markdown 解析 ===")

    from sensenova_claw.capabilities.tools.obsidian_tool import (
        _parse_frontmatter,
        _extract_tags,
        _extract_links,
    )

    test_content = """---
title: Test Note
tags: [project, work]
date: 2026-03-25
---

# 测试笔记

这是一个测试 #test #automation

参考 [[其他笔记]] 和 [[文档|别名]]
"""

    metadata, body = _parse_frontmatter(test_content)
    print(f"Frontmatter: {metadata}")
    print(f"Body 长度: {len(body)} 字符")

    tags = _extract_tags(test_content)
    print(f"提取的标签: {tags}")

    links = _extract_links(test_content)
    print(f"提取的链接: {links}")


async def main():
    """运行测试"""
    print("开始测试 Obsidian 工具（本地功能）...")

    try:
        # 测试解析功能
        await test_parse_functions()

        # 测试 vault 检测
        vaults = await test_local_detection()

        if vaults:
            print(f"\n✅ 找到 {len(vaults)} 个本地 vault")
            print("\n提示: 远程功能需要 httpx 模块")
            print("运行 'uv sync' 安装依赖后可测试完整功能")
        else:
            print("\n⚠️  未找到本地 vault")
            print("请在以下位置创建 Obsidian vault 或配置路径:")
            print("  - ~/Documents/Obsidian")
            print("  - ~/Obsidian")
            print("  - 或在 config.yml 中配置")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
