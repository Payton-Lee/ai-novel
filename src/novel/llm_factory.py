"""LLM 工厂 — 根据配置创建不同后端的 LLM 实例.

支持的后端:
- qwen: 通义千问 (默认 qwen-plus, 可选 qwen-max)
- claude: Anthropic Claude (需 ANTHROPIC_API_KEY)
- openai: OpenAI 兼容接口 (需 OPENAI_API_KEY + OPENAI_BASE_URL)
- deepseek: DeepSeek (需 DEEPSEEK_API_KEY, 默认 deepseek-v4-flash, OpenAI 兼容接口)
"""

from __future__ import annotations

import os
from typing import Any, Optional


def create_llm(
    provider: str = "qwen",
    model: Optional[str] = None,
    temperature: float = 0.8,
    max_tokens: int = 4096,
    **kwargs: Any,
) -> Any:
    """创建 LLM 实例.

    Args:
        provider: 后端提供商 ("qwen" / "claude" / "openai" / "deepseek")
        model: 模型名称, 为 None 时使用各后端默认值
        temperature: 生成温度, 写作场景建议 0.7-0.9
        max_tokens: 最大输出 token 数
        **kwargs: 传递给具体 LLM 构造函数的额外参数

    Returns:
        配置好的 LangChain ChatModel 实例

    Raises:
        ValueError: 未配置对应 API Key 时抛出
    """
    provider = provider.lower()

    if provider == "qwen":
        return _create_qwen(model or "qwen-plus", temperature, max_tokens, **kwargs)
    elif provider == "claude":
        return _create_claude(model or "claude-sonnet-4-20250514", temperature, max_tokens, **kwargs)
    elif provider == "openai":
        return _create_openai(model or "gpt-4o", temperature, max_tokens, **kwargs)
    elif provider in ("deepseek", "deepseek-chat"):
        return _create_deepseek(model or "deepseek-v4-flash", temperature, max_tokens, **kwargs)
    else:
        raise ValueError(f"不支持的 LLM 后端: {provider}, 可选: qwen/claude/openai/deepseek")


def _create_qwen(model: str, temperature: float, max_tokens: int, **kwargs: Any) -> Any:
    """通义千问."""
    api_key = os.getenv("QWEN_KEY") or os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise ValueError(
            "未配置 QWEN_KEY 或 DASHSCOPE_API_KEY 环境变量。"
            "请在 .env 文件中添加: QWEN_KEY=your_api_key"
        )
    from langchain_community.chat_models import ChatTongyi

    return ChatTongyi(
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )


def _create_claude(model: str, temperature: float, max_tokens: int, **kwargs: Any) -> Any:
    """Anthropic Claude."""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    if not api_key:
        raise ValueError(
            "未配置 ANTHROPIC_API_KEY 环境变量。"
            "请在 .env 文件中添加: ANTHROPIC_API_KEY=your_api_key"
        )
    from langchain_anthropic import ChatAnthropic

    return ChatAnthropic(
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )


def _create_openai(model: str, temperature: float, max_tokens: int, **kwargs: Any) -> Any:
    """OpenAI 兼容接口 (支持自定义 base_url)."""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise ValueError(
            "未配置 OPENAI_API_KEY 环境变量。"
            "请在 .env 文件中添加: OPENAI_API_KEY=your_api_key"
        )
    from langchain_openai import ChatOpenAI

    base_url = os.getenv("OPENAI_BASE_URL")
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        base_url=base_url,
        **kwargs,
    )


def _create_deepseek(model: str, temperature: float, max_tokens: int, **kwargs: Any) -> Any:
    """DeepSeek (OpenAI 兼容接口)."""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise ValueError(
            "未配置 DEEPSEEK_API_KEY 环境变量。"
            "请在 .env 文件中添加: DEEPSEEK_API_KEY=your_api_key"
        )
    from langchain_openai import ChatOpenAI

    base_url = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    # 注意: deepseek-v4-flash 实际走 base_url/v1 兼容路径, 由 SDK 自动处理
    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=temperature,
        max_tokens=max_tokens,
        **kwargs,
    )


def get_llm_from_config(config: Any = None) -> Any:
    """从 LangGraph config 中读取 LLM 配置并创建实例.

    config 格式:
        {"configurable": {"llm_provider": "qwen", "llm_model": "qwen-max",
                          "max_tokens": 8000}}
    """
    cfg = (config or {}).get("configurable", {})
    provider = cfg.get("llm_provider", os.getenv("NOVEL_LLM_PROVIDER", "qwen"))
    model = cfg.get("llm_model", os.getenv("NOVEL_LLM_MODEL"))
    max_tokens = cfg.get("max_tokens")
    if max_tokens:
        return create_llm(provider=provider, model=model, max_tokens=int(max_tokens))
    return create_llm(provider=provider, model=model)
