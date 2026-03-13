"""EmbeddingService 单元测试"""

from unittest.mock import MagicMock, patch

import pytest

from agentos.capabilities.memory.config import MemoryConfig, SearchConfig


class TestEmbeddingServiceInit:
    """初始化测试"""

    def test_init_success(self):
        """OpenAI 客户端初始化成功"""
        mem_config = MemoryConfig()

        with patch("agentos.capabilities.memory.embedding.config") as mock_config:
            mock_config.get.return_value = {
                "api_key": "sk-test-key",
                "base_url": "https://api.openai.com/v1",
            }
            with patch("openai.OpenAI") as MockOpenAI:
                MockOpenAI.return_value = MagicMock()

                # 需要在 import 之前 patch，或者直接实例化
                from agentos.capabilities.memory.embedding import EmbeddingService
                svc = EmbeddingService(mem_config)

            assert svc.available() is True
            assert svc._client is not None

    def test_init_no_api_key(self):
        """无 API key 时降级"""
        mem_config = MemoryConfig()

        with patch("agentos.capabilities.memory.embedding.config") as mock_config:
            mock_config.get.return_value = {"api_key": "", "base_url": None}

            from agentos.capabilities.memory.embedding import EmbeddingService
            svc = EmbeddingService(mem_config)

        assert svc.available() is False
        assert svc._client is None

    def test_init_exception(self):
        """初始化异常时降级"""
        mem_config = MemoryConfig()

        with patch("agentos.capabilities.memory.embedding.config") as mock_config:
            mock_config.get.return_value = {"api_key": "sk-test", "base_url": None}
            # OpenAI 导入本身就在 _init_client 内部，模拟导入失败
            with patch.dict("sys.modules", {"openai": None}):
                from agentos.capabilities.memory.embedding import EmbeddingService
                svc = EmbeddingService(mem_config)

        assert svc.available() is False


class TestDimensions:
    """向量维度测试"""

    def _make_service(self, model: str):
        """创建一个不调用 _init_client 的 service"""
        mem_config = MemoryConfig(search=SearchConfig(embedding_model=model))
        with patch("agentos.capabilities.memory.embedding.config") as mock_config:
            mock_config.get.return_value = {"api_key": "", "base_url": None}
            from agentos.capabilities.memory.embedding import EmbeddingService
            svc = EmbeddingService(mem_config)
        return svc

    def test_small_model(self):
        svc = self._make_service("text-embedding-3-small")
        assert svc.dimensions() == 1536

    def test_large_model(self):
        svc = self._make_service("text-embedding-3-large")
        assert svc.dimensions() == 3072

    def test_ada_model(self):
        svc = self._make_service("text-embedding-ada-002")
        assert svc.dimensions() == 1536

    def test_unknown_model(self):
        """未知模型默认 1536"""
        svc = self._make_service("custom-model-v1")
        assert svc.dimensions() == 1536


class TestEmbed:
    """embed 方法测试"""

    async def test_embed_success(self):
        """正常嵌入调用"""
        mem_config = MemoryConfig()

        with patch("agentos.capabilities.memory.embedding.config") as mock_config:
            mock_config.get.return_value = {"api_key": "sk-test", "base_url": None}
            with patch("openai.OpenAI") as MockOpenAI:
                mock_client = MagicMock()
                MockOpenAI.return_value = mock_client

                # 模拟 embeddings.create 返回
                mock_item1 = MagicMock()
                mock_item1.embedding = [0.1, 0.2, 0.3]
                mock_item2 = MagicMock()
                mock_item2.embedding = [0.4, 0.5, 0.6]
                mock_response = MagicMock()
                mock_response.data = [mock_item1, mock_item2]
                mock_client.embeddings.create.return_value = mock_response

                from agentos.capabilities.memory.embedding import EmbeddingService
                svc = EmbeddingService(mem_config)

        result = await svc.embed(["hello", "world"])
        assert len(result) == 2
        assert result[0] == [0.1, 0.2, 0.3]
        assert result[1] == [0.4, 0.5, 0.6]

    async def test_embed_unavailable(self):
        """服务不可用时抛出 RuntimeError"""
        mem_config = MemoryConfig()

        with patch("agentos.capabilities.memory.embedding.config") as mock_config:
            mock_config.get.return_value = {"api_key": "", "base_url": None}
            from agentos.capabilities.memory.embedding import EmbeddingService
            svc = EmbeddingService(mem_config)

        with pytest.raises(RuntimeError, match="不可用"):
            await svc.embed(["test"])

    async def test_embed_sdk_exception(self):
        """OpenAI SDK 在 embed 调用时抛出异常，应向上传播"""
        mem_config = MemoryConfig()

        with patch("agentos.capabilities.memory.embedding.config") as mock_config:
            mock_config.get.return_value = {"api_key": "sk-test", "base_url": None}
            with patch("openai.OpenAI") as MockOpenAI:
                mock_client = MagicMock()
                MockOpenAI.return_value = mock_client

                # 模拟 SDK 调用抛出异常
                mock_client.embeddings.create.side_effect = Exception("API rate limit exceeded")

                from agentos.capabilities.memory.embedding import EmbeddingService
                svc = EmbeddingService(mem_config)

        # asyncio.to_thread 会将线程内异常重新抛出到调用方
        with pytest.raises(Exception, match="API rate limit exceeded"):
            await svc.embed(["hello"])

    async def test_embed_empty_string(self):
        """空字符串输入：SDK 正常调用并返回对应向量"""
        mem_config = MemoryConfig()

        with patch("agentos.capabilities.memory.embedding.config") as mock_config:
            mock_config.get.return_value = {"api_key": "sk-test", "base_url": None}
            with patch("openai.OpenAI") as MockOpenAI:
                mock_client = MagicMock()
                MockOpenAI.return_value = mock_client

                # 空字符串也返回一个向量（行为由 SDK 决定，这里只验证透传）
                mock_item = MagicMock()
                mock_item.embedding = [0.0] * 3
                mock_response = MagicMock()
                mock_response.data = [mock_item]
                mock_client.embeddings.create.return_value = mock_response

                from agentos.capabilities.memory.embedding import EmbeddingService
                svc = EmbeddingService(mem_config)

        result = await svc.embed([""])
        assert len(result) == 1
        assert result[0] == [0.0, 0.0, 0.0]
        # 确认空字符串被原样传给 SDK
        mock_client.embeddings.create.assert_called_once_with(
            input=[""], model=mem_config.search.embedding_model
        )

    async def test_embed_empty_list(self):
        """空列表输入：SDK 返回空 data，embed 返回空列表"""
        mem_config = MemoryConfig()

        with patch("agentos.capabilities.memory.embedding.config") as mock_config:
            mock_config.get.return_value = {"api_key": "sk-test", "base_url": None}
            with patch("openai.OpenAI") as MockOpenAI:
                mock_client = MagicMock()
                MockOpenAI.return_value = mock_client

                mock_response = MagicMock()
                mock_response.data = []  # SDK 返回空
                mock_client.embeddings.create.return_value = mock_response

                from agentos.capabilities.memory.embedding import EmbeddingService
                svc = EmbeddingService(mem_config)

        result = await svc.embed([])
        assert result == []
        mock_client.embeddings.create.assert_called_once_with(
            input=[], model=mem_config.search.embedding_model
        )
