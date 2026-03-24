"""ConfigFileWatcher 单元测试"""
import asyncio
import hashlib
import pytest
import yaml
from pathlib import Path
from unittest.mock import AsyncMock


@pytest.fixture
def config_file(tmp_path):
    p = tmp_path / "config.yml"
    p.write_text(yaml.dump({"llm": {"default_model": "gpt-4o"}}), encoding="utf-8")
    return p


@pytest.mark.asyncio
async def test_watcher_detects_external_change(config_file):
    from sensenova_claw.platform.config.config_file_watcher import ConfigFileWatcher
    callback = AsyncMock()
    loop = asyncio.get_running_loop()
    watcher = ConfigFileWatcher(
        config_path=config_file,
        on_change=callback,
        event_loop=loop,
        get_last_written_hash=lambda: None,
    )
    watcher.start()
    await asyncio.sleep(0.5)
    new_content = yaml.dump({"llm": {"default_model": "gpt-5"}})
    config_file.write_text(new_content, encoding="utf-8")
    await asyncio.sleep(2.0)
    watcher.stop()
    assert callback.call_count >= 1


@pytest.mark.asyncio
async def test_watcher_skips_self_write(config_file):
    from sensenova_claw.platform.config.config_file_watcher import ConfigFileWatcher
    content = yaml.dump({"llm": {"default_model": "gpt-4o"}})
    content_hash = hashlib.md5(content.encode()).hexdigest()
    callback = AsyncMock()
    loop = asyncio.get_running_loop()
    watcher = ConfigFileWatcher(
        config_path=config_file,
        on_change=callback,
        event_loop=loop,
        get_last_written_hash=lambda: content_hash,
    )
    watcher.start()
    await asyncio.sleep(0.5)
    config_file.write_text(content, encoding="utf-8")
    await asyncio.sleep(2.0)
    watcher.stop()
    assert callback.call_count == 0


@pytest.mark.asyncio
async def test_watcher_handles_invalid_yaml(config_file):
    from sensenova_claw.platform.config.config_file_watcher import ConfigFileWatcher
    callback = AsyncMock()
    loop = asyncio.get_running_loop()
    watcher = ConfigFileWatcher(
        config_path=config_file,
        on_change=callback,
        event_loop=loop,
        get_last_written_hash=lambda: None,
    )
    watcher.start()
    await asyncio.sleep(0.5)
    config_file.write_text("invalid: yaml: [unterminated", encoding="utf-8")
    await asyncio.sleep(2.0)
    watcher.stop()
    assert callback.call_count == 0
