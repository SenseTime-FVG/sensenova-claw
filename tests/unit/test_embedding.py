"""EmbeddingService 真实 API 测试

不使用任何 mock，通过真实配置验证 EmbeddingService 行为。
OpenAI API key 为占位符时自动 skip embedding 调用测试。
"""
from __future__ import annotations

from pathlib import Path

import pytest

from agentos.capabilities.memory.config import MemoryConfig, SearchConfig
from agentos.platform.config.config import Config

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(scope="module")
def real_config() -> Config:
    """从项目根目录加载真实配置"""
    return Config(config_path=PROJECT_ROOT / "config.yml")


def _is_openai_key_valid(cfg: Config) -> bool:
    """检查 OpenAI API key 是否为真实 key（非占位符）"""
    api_key = cfg.get("llm.openai.api_key", "")
    # 占位符通常是短字符串或包含 1234567890
    if not api_key:
        return False
    if "1234567890" in api_key:
        return False
    if len(api_key) < 20:
        return False
    return True


def _make_service(cfg: Config, model: str = "text-embedding-3-small"):
    """使用真实配置创建 EmbeddingService 实例"""
    import agentos.capabilities.memory.embedding as mod
    original_config = mod.config
    mod.config = cfg
    try:
        from agentos.capabilities.memory.embedding import EmbeddingService
        mem_config = MemoryConfig(search=SearchConfig(embedding_model=model))
        svc = EmbeddingService(mem_config)
    finally:
        mod.config = original_config
    return svc


# ---------------------------------------------------------------------------
# 维度测试（纯逻辑，不需要 API key）
# ---------------------------------------------------------------------------

class TestDimensions:
    """向量维度测试"""

    def test_small_model(self, real_config) -> None:
        svc = _make_service(real_config, "text-embedding-3-small")
        assert svc.dimensions() == 1536

    def test_large_model(self, real_config) -> None:
        svc = _make_service(real_config, "text-embedding-3-large")
        assert svc.dimensions() == 3072

    def test_ada_model(self, real_config) -> None:
        svc = _make_service(real_config, "text-embedding-ada-002")
        assert svc.dimensions() == 1536

    def test_unknown_model(self, real_config) -> None:
        """未知模型默认 1536"""
        svc = _make_service(real_config, "custom-model-v1")
        assert svc.dimensions() == 1536


# ---------------------------------------------------------------------------
# 初始化测试
# ---------------------------------------------------------------------------

class TestEmbeddingServiceInit:
    """初始化测试"""

    def test_init_with_valid_key(self, real_config) -> None:
        """有 API key 时应初始化成功（available 取决于 key 是否有效）"""
        svc = _make_service(real_config)
        api_key = real_config.get("llm.providers.openai.api_key", "")
        if api_key and "1234567890" not in api_key:
            # 真实 key，应可用
            assert svc.available() is True
            assert svc._client is not None
        else:
            # 占位符 key，OpenAI SDK 仍可实例化（校验发生在调用时）
            # 只要 key 非空，SDK 实例化不会失败
            if api_key:
                assert svc._client is not None
            else:
                assert svc.available() is False

    def test_init_no_api_key(self) -> None:
        """无 API key 时降级：使用临时空配置"""
        empty_cfg = Config.__new__(Config)
        empty_cfg.data = {
            "llm": {
                "providers": {"openai": {"api_key": "", "base_url": None}}
            }
        }

        import agentos.capabilities.memory.embedding as mod
        original_config = mod.config
        mod.config = empty_cfg
        try:
            from agentos.capabilities.memory.embedding import EmbeddingService
            svc = EmbeddingService(MemoryConfig())
        finally:
            mod.config = original_config

        assert svc.available() is False
        assert svc._client is None


# ---------------------------------------------------------------------------
# embed 方法测试（需要真实 API）
# ---------------------------------------------------------------------------

class TestEmbed:
    """embed 方法测试"""

    @pytest.mark.slow
    async def test_embed_unavailable(self) -> None:
        """服务不可用时抛出 RuntimeError"""
        empty_cfg = Config.__new__(Config)
        empty_cfg.data = {
            "llm": {
                "providers": {"openai": {"api_key": "", "base_url": None}}
            }
        }

        import agentos.capabilities.memory.embedding as mod
        original_config = mod.config
        mod.config = empty_cfg
        try:
            from agentos.capabilities.memory.embedding import EmbeddingService
            svc = EmbeddingService(MemoryConfig())
        finally:
            mod.config = original_config

        with pytest.raises(RuntimeError, match="不可用"):
            await svc.embed(["test"])

    @pytest.mark.slow
    async def test_embed_success(self, real_config) -> None:
        """真实 API 嵌入调用：验证返回向量结构"""
        if not _is_openai_key_valid(real_config):
            pytest.skip("OpenAI API key 为占位符，跳过真实 embedding 测试")

        svc = _make_service(real_config)
        result = await svc.embed(["hello", "world"])

        assert isinstance(result, list)
        assert len(result) == 2
        # 每个向量应为 float 列表
        for vec in result:
            assert isinstance(vec, list)
            assert len(vec) > 0
            assert all(isinstance(v, float) for v in vec)

    @pytest.mark.slow
    async def test_embed_single_text(self, real_config) -> None:
        """单条文本嵌入"""
        if not _is_openai_key_valid(real_config):
            pytest.skip("OpenAI API key 为占位符，跳过真实 embedding 测试")

        svc = _make_service(real_config)
        result = await svc.embed(["测试文本"])

        assert len(result) == 1
        assert isinstance(result[0], list)
        assert len(result[0]) == svc.dimensions()

    @pytest.mark.slow
    async def test_embed_empty_string(self, real_config) -> None:
        """空字符串输入应正常返回向量"""
        if not _is_openai_key_valid(real_config):
            pytest.skip("OpenAI API key 为占位符，跳过真实 embedding 测试")

        svc = _make_service(real_config)
        result = await svc.embed([""])

        assert len(result) == 1
        assert isinstance(result[0], list)
        assert len(result[0]) > 0
