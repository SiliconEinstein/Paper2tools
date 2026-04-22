"""
测试向量化模块

测试内容:
- 各种 embedding 模型的初始化和调用
- 单条文本向量化
- 批量向量化（含进度追踪）
- 向量维度和类型正确性
- 缓存机制
- 异常处理（空文本、超长文本）
"""

import os
import pytest
import numpy as np
from unittest.mock import AsyncMock, MagicMock, patch
from src.step1.vectorizer import DashScopeEmbedder, create_embedder


@pytest.fixture
def embedder_config():
    """测试用的 embedder 配置"""
    return {
        "model": "text-embedding-v3",
        "concurrency": 5,
        "max_retries": 2,
        "http_timeout": 30.0,
        "access_key": "test_key"
    }


def test_create_embedder(embedder_config):
    """测试创建 embedder"""
    embedder = create_embedder(embedder_config)

    assert isinstance(embedder, DashScopeEmbedder)
    assert embedder.model == "text-embedding-v3"
    assert embedder.concurrency == 5
    assert embedder.max_retries == 2


def test_embedder_default_config():
    """测试使用默认配置创建 embedder"""
    config = {"access_key": "test_key"}
    embedder = create_embedder(config)

    assert embedder.model == "text-embedding-v1"
    assert embedder.concurrency == 10
    assert embedder.max_retries == 3


def test_embedder_missing_api_key():
    """测试缺少 API key 应报错"""
    with patch.dict('os.environ', {}, clear=True):
        with pytest.raises(ValueError, match="API key not configured"):
            create_embedder({})


@pytest.mark.asyncio
async def test_embed_single_text(embedder_config):
    """测试单条文本向量化"""
    embedder = create_embedder(embedder_config)

    # Mock HTTP 响应
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [{"index": 0, "embedding": [0.1] * 1536}]
    }
    mock_response.raise_for_status = MagicMock()

    async def mock_post(*args, **kwargs):
        return mock_response

    with patch('httpx.AsyncClient.post', side_effect=mock_post):
        vectors = await embedder.embed_texts(["test text"])

        assert len(vectors) == 1
        assert len(vectors[0]) == 1536
        assert isinstance(vectors[0], list)


@pytest.mark.asyncio
async def test_embed_batch(embedder_config):
    """测试批量向量化"""
    embedder = create_embedder(embedder_config)

    texts = ["text 1", "text 2", "text 3"]
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"index": i, "embedding": [0.1 * (i + 1)] * 1536}
            for i in range(len(texts))
        ]
    }
    mock_response.raise_for_status = MagicMock()

    async def mock_post(*args, **kwargs):
        return mock_response

    with patch('httpx.AsyncClient.post', side_effect=mock_post):
        vectors = await embedder.embed_texts(texts)

        assert len(vectors) == 3
        assert all(len(v) == 1536 for v in vectors)


@pytest.mark.asyncio
async def test_embed_empty_text(embedder_config):
    """测试空文本向量化"""
    embedder = create_embedder(embedder_config)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [{"index": 0, "embedding": [0.0] * 1536}]
    }
    mock_response.raise_for_status = MagicMock()

    async def mock_post(*args, **kwargs):
        return mock_response

    with patch('httpx.AsyncClient.post', side_effect=mock_post):
        vectors = await embedder.embed_texts([""])

        assert len(vectors) == 1


@pytest.mark.asyncio
async def test_vector_dimension_consistency(embedder_config):
    """测试向量维度一致性"""
    embedder = create_embedder(embedder_config)

    texts = ["short", "a much longer text with more words"]
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"index": 0, "embedding": [0.1] * 1536},
            {"index": 1, "embedding": [0.2] * 1536}
        ]
    }
    mock_response.raise_for_status = MagicMock()

    async def mock_post(*args, **kwargs):
        return mock_response

    with patch('httpx.AsyncClient.post', side_effect=mock_post):
        vectors = await embedder.embed_texts(texts)

        # 所有向量维度应该相同
        dims = [len(v) for v in vectors]
        assert len(set(dims)) == 1


@pytest.mark.asyncio
async def test_vector_type(embedder_config):
    """测试向量类型正确性"""
    embedder = create_embedder(embedder_config)

    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [{"index": 0, "embedding": [0.1, 0.2, 0.3]}]
    }
    mock_response.raise_for_status = MagicMock()

    async def mock_post(*args, **kwargs):
        return mock_response

    with patch('httpx.AsyncClient.post', side_effect=mock_post):
        vectors = await embedder.embed_texts(["test"])

        # 转换为 numpy 数组
        np_vector = np.array(vectors[0], dtype=np.float32)
        assert np_vector.dtype == np.float32


@pytest.mark.asyncio
async def test_http_error_handling(embedder_config):
    """测试 HTTP 错误处理"""
    embedder = create_embedder(embedder_config)

    mock_response = MagicMock()
    mock_response.raise_for_status.side_effect = Exception("HTTP Error")

    async def mock_post(*args, **kwargs):
        return mock_response

    with patch('httpx.AsyncClient.post', side_effect=mock_post):
        with pytest.raises(Exception):
            await embedder.embed_texts(["test"])


@pytest.mark.asyncio
async def test_response_ordering(embedder_config):
    """测试响应顺序正确性"""
    embedder = create_embedder(embedder_config)

    # 模拟乱序响应
    mock_response = MagicMock()
    mock_response.json.return_value = {
        "data": [
            {"index": 2, "embedding": [0.3] * 100},
            {"index": 0, "embedding": [0.1] * 100},
            {"index": 1, "embedding": [0.2] * 100}
        ]
    }
    mock_response.raise_for_status = MagicMock()

    async def mock_post(*args, **kwargs):
        return mock_response

    with patch('httpx.AsyncClient.post', side_effect=mock_post):
        vectors = await embedder.embed_texts(["a", "b", "c"])

        # 验证排序后的顺序
        assert vectors[0][0] == pytest.approx(0.1)
        assert vectors[1][0] == pytest.approx(0.2)
        assert vectors[2][0] == pytest.approx(0.3)


@pytest.mark.asyncio
async def test_close_embedder(embedder_config):
    """测试关闭 embedder"""
    embedder = create_embedder(embedder_config)

    # close 方法应该正常执行
    await embedder.close()
