#!/usr/bin/env python3
"""测试 Obsidian 工具"""
import asyncio
import sys
from pathlib import Path

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent))

from sensenova_claw.capabilities.tools.obsidian_tool import (
    ObsidianSearchTool,
    ObsidianReadTool,
    ObsidianWriteTool,
    ObsidianListVaultsTool,
)


async def test_list_vaults():
    """测试列出 vault"""
    print("\n=== 测试 1: 列出 Vaults ===")
    tool = ObsidianListVaultsTool()
    result = await tool.execute()

    print(f"成功: {result.get('success')}")
    if result.get('success'):
        print(f"找到 {result.get('count')} 个 vault:")
        for vault in result.get('vaults', []):
            print(f"  - {vault.get('name')} ({vault.get('type')})")
            if vault.get('type') == 'local':
                print(f"    路径: {vault.get('path')}")
                print(f"    笔记数: {vault.get('note_count')}")
    else:
        print(f"错误: {result.get('error')}")
        print(f"提示: {result.get('hint')}")

    return result


async def test_list_specific_vault(vault_name: str):
    """测试列出指定 vault"""
    print(f"\n=== 测试 1.5: 列出指定 Vault (vault='{vault_name}') ===")
    tool = ObsidianListVaultsTool()
    result = await tool.execute(vault=vault_name)

    print(f"成功: {result.get('success')}")
    if result.get('success'):
        print(f"找到 {result.get('count')} 个 vault:")
        for vault in result.get('vaults', []):
            print(f"  - {vault.get('name')} ({vault.get('type')})")
            if vault.get('type') == 'local':
                print(f"    路径: {vault.get('path')}")
                print(f"    笔记数: {vault.get('note_count')}")
    else:
        print(f"错误: {result.get('error')}")

    return result


async def test_search(query="test"):
    """测试搜索笔记"""
    print(f"\n=== 测试 2: 搜索笔记 (query='{query}') ===")
    tool = ObsidianSearchTool()
    result = await tool.execute(query=query, limit=5)

    print(f"成功: {result.get('success')}")
    if result.get('success'):
        print(f"找到 {result.get('count')} 条结果:")
        for note in result.get('results', []):
            print(f"  - {note.get('title')}")
            print(f"    路径: {note.get('path')}")
            print(f"    标签: {note.get('tags')}")
            print(f"    摘要: {note.get('summary')[:80]}...")
    else:
        print(f"错误: {result.get('error')}")

    return result


async def test_write_and_read():
    """测试写入和读取笔记"""
    print("\n=== 测试 3: 写入笔记 ===")

    # 写入测试笔记
    write_tool = ObsidianWriteTool()
    test_content = """# 测试笔记

这是一个由 sensenova-claw 创建的测试笔记。

#test #automation

创建时间: 2026-03-25
"""

    write_result = await write_tool.execute(
        path="test/sensenova_test.md",
        content=test_content
    )

    print(f"写入成功: {write_result.get('success')}")
    if write_result.get('success'):
        print(f"  Vault: {write_result.get('vault')}")
        print(f"  路径: {write_result.get('path')}")
        print(f"  操作: {write_result.get('action')}")
    else:
        print(f"  错误: {write_result.get('error')}")
        return write_result

    # 读取刚写入的笔记
    print("\n=== 测试 4: 读取笔记 ===")
    read_tool = ObsidianReadTool()
    read_result = await read_tool.execute(path="test/sensenova_test.md")

    print(f"读取成功: {read_result.get('success')}")
    if read_result.get('success'):
        print(f"  标题: {read_result.get('title')}")
        print(f"  标签: {read_result.get('tags')}")
        print(f"  内容长度: {len(read_result.get('content', ''))} 字符")
        print(f"  内容预览: {read_result.get('content', '')[:100]}...")
    else:
        print(f"  错误: {read_result.get('error')}")

    return read_result


async def main():
    """运行所有测试"""
    print("开始测试 Obsidian 工具...")

    try:
        # 测试 1: 列出 vaults
        vaults_result = await test_list_vaults()

        # 如果没有找到 vault，跳过后续测试
        if not vaults_result.get('success'):
            print("\n⚠️  未找到 Obsidian vault，跳过搜索和读写测试")
            print("请配置 vault 或确保 Obsidian 安装在常见位置")
            return

        # 测试 1.5: 列出指定 vault（如果有多个 vault）
        vaults = vaults_result.get('vaults', [])
        if len(vaults) > 0:
            first_vault_name = vaults[0].get('name')
            await test_list_specific_vault(first_vault_name)

            # 测试不存在的 vault
            await test_list_specific_vault("nonexistent_vault_xyz")

        # 测试 2: 搜索
        await test_search()

        # 测试 3 & 4: 写入和读取
        await test_write_and_read()

        print("\n✅ 所有测试完成")

    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(main())
