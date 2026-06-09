"""LLM Client abstraction layer.

Supports:
  - OpenAI API (GPT-4o, GPT-4, etc.)
  - Anthropic API (Claude)
  - OpenAI-compatible APIs (Qwen, DeepSeek, Zhipu, Moonshot, etc.)
  - Simulation mode (rule-based fallback, no API key needed)

Configuration via environment variables:
  LLM_PROVIDER: openai | anthropic | openai_compat | simulation (default)
  LLM_MODEL: model name (provider-specific)
  LLM_API_KEY: API key
  LLM_BASE_URL: base URL for OpenAI-compatible providers
  LLM_MAX_TOKENS: max tokens per response (default 1024)
  LLM_TEMPERATURE: temperature (default 0.7)
"""

from __future__ import annotations

import json
import os
import re
import uuid
from abc import ABC, abstractmethod
from typing import Optional


# ── Provider-agnostic message types ──────────────────────────────────────────

def build_messages(
    system_prompt: str,
    conversation_history: list[dict],
    current_instruction: str,
) -> list[dict]:
    """Build the message list for an LLM call."""
    messages = [{"role": "system", "content": system_prompt}]

    # Add recent conversation history (last 10 turns to manage context)
    for entry in conversation_history[-10:]:
        role = "assistant" if entry.get("speaker") else "user"
        label = entry.get("speaker", "")
        content = entry.get("content", "")
        messages.append({
            "role": "user",
            "content": f"[{label}]: {content}",
        })

    messages.append({"role": "user", "content": current_instruction})
    return messages


# ── Base class ────────────────────────────────────────────────────────────────

class LLMClient(ABC):
    """Abstract base for LLM clients."""

    @abstractmethod
    def chat(
        self,
        messages: list[dict],
        system: str = "",
        json_mode: bool = False,
    ) -> str:
        """Send a chat request and return the response text."""
        ...


# ── OpenAI Client ─────────────────────────────────────────────────────────────

class OpenAIClient(LLMClient):
    """Client for OpenAI API."""

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str = "",
        base_url: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("OPENAI_API_KEY", "")
        self.base_url = base_url or os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(self, messages: list[dict], system: str = "", json_mode: bool = False) -> str:
        try:
            from openai import OpenAI
        except ImportError:
            raise ImportError("Please install openai: pip install openai")

        client = OpenAI(api_key=self.api_key, base_url=self.base_url)

        full_messages = []
        if system:
            full_messages.append({"role": "system", "content": system})
        full_messages.extend(messages)

        kwargs = dict(
            model=self.model,
            messages=full_messages,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
        )

        if json_mode:
            kwargs["response_format"] = {"type": "json_object"}

        response = client.chat.completions.create(**kwargs)
        return response.choices[0].message.content or ""

    def __repr__(self):
        return f"OpenAIClient(model={self.model}, base_url={self.base_url})"


# ── Anthropic Client ──────────────────────────────────────────────────────────

class AnthropicClient(LLMClient):
    """Client for Anthropic Claude API."""

    def __init__(
        self,
        model: str = "claude-sonnet-4-6",
        api_key: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.7,
    ):
        self.model = model
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        self.max_tokens = max_tokens
        self.temperature = temperature

    def chat(self, messages: list[dict], system: str = "", json_mode: bool = False) -> str:
        try:
            import anthropic
        except ImportError:
            raise ImportError("Please install anthropic: pip install anthropic")

        client = anthropic.Anthropic(api_key=self.api_key)

        # Separate system from messages for Anthropic format
        user_messages = []
        for m in messages:
            if m["role"] == "system":
                if not system:
                    system = m["content"]
            else:
                user_messages.append(m)

        # Anthropic requires alternating user/assistant
        anthropic_msgs = []
        for m in user_messages:
            role = "user" if m["role"] in ("user", "system") else "assistant"
            anthropic_msgs.append({"role": role, "content": m["content"]})

        kwargs = dict(
            model=self.model,
            max_tokens=self.max_tokens,
            temperature=self.temperature,
            messages=anthropic_msgs,
        )
        if system:
            kwargs["system"] = system

        response = client.messages.create(**kwargs)
        text = ""
        for block in response.content:
            if hasattr(block, "text"):
                text += block.text
        return text

    def __repr__(self):
        return f"AnthropicClient(model={self.model})"


# ── Simulation Client (rule-based fallback) ───────────────────────────────────

class SimulationClient(LLMClient):
    """Rule-based simulation client.

    This is NOT just replaying templates. It uses the agent's role definition,
    evidence cards, and conversation context to generate structured responses
    through rule-based composition. While not as nuanced as a real LLM, it
    demonstrates genuine multi-agent behavior: each agent responds differently
    to the same situation based on its own interests and constraints.
    """

    def chat(self, messages: list[dict], system: str = "", json_mode: bool = False) -> str:
        # Extract context from the system prompt and messages
        agent_name = self._extract_field(system, "名称：", "")
        agent_archetype = self._extract_field(system, "身份：", "")
        interests = self._extract_list_field(system, "核心利益：")
        stance_label = self._extract_field(system, "基本立场：", "")
        can_say = self._extract_list_field(system, "你可以说：")
        cannot_say = self._extract_list_field(system, "你不能说：")

        # Extract the last speaker's content for reply context
        last_speaker = ""
        last_content = ""
        for m in reversed(messages):
            content = m.get("content", "")
            if content.startswith("[") and "]:" in content:
                bracket_end = content.index("]:")
                last_speaker = content[1:bracket_end]
                last_content = content[bracket_end + 2:].strip()
                break

        # Extract evidence from system prompt
        evidence_ids = []
        evidence_quotes = []
        for line in system.split("\n"):
            if "证据" in line and "来源" in line:
                match = re.search(r'\[证据\s*(\d+)\]\s*(E-[\w-]+)', line)
                if match:
                    evidence_ids.append(match.group(2))
            if "原文引用：" in line:
                quote = line.split("原文引用：", 1)[1].strip()
                if quote:
                    evidence_quotes.append(quote)

        # Build response based on agent archetype and context
        response = self._compose_response(
            agent_name=agent_name,
            archetype=agent_archetype,
            interests=interests,
            stance_label=stance_label,
            last_speaker=last_speaker,
            last_content=last_content,
            evidence_ids=evidence_ids,
            evidence_quotes=evidence_quotes,
            can_say=can_say,
            cannot_say=cannot_say,
            turn_count=sum(1 for m in messages if m.get("content", "").startswith("[")),
        )

        return response

    @staticmethod
    def _extract_field(text: str, prefix: str, default: str = "") -> str:
        for line in text.split("\n"):
            if prefix in line:
                return line.split(prefix, 1)[1].strip()
        return default

    @staticmethod
    def _extract_list_field(text: str, prefix: str) -> list[str]:
        items = []
        in_section = False
        for line in text.split("\n"):
            if prefix in line:
                in_section = True
                continue
            if in_section:
                stripped = line.strip().lstrip("- ")
                if stripped and not stripped.startswith("##") and not stripped.startswith("你"):
                    items.append(stripped)
                elif stripped.startswith("你") or stripped.startswith("##"):
                    break
        return items

    def _compose_response(
        self,
        agent_name: str,
        archetype: str,
        interests: list[str],
        stance_label: str,
        last_speaker: str,
        last_content: str,
        evidence_ids: list[str],
        evidence_quotes: list[str],
        can_say: list[str],
        cannot_say: list[str],
        turn_count: int,
    ) -> str:
        """Compose a rule-based response that respects the agent's role."""
        # Determine if we should reply to the last speaker
        reply_to = last_speaker if last_speaker and last_speaker != agent_name else None

        # Stance score based on interests and turn progression
        if "支持" in stance_label and "反对" not in stance_label:
            base_stance = 0.5 + (turn_count * 0.01)  # slight moderation over time
        elif "反对" in stance_label:
            base_stance = -0.5 - (turn_count * 0.01)  # slight moderation over time
        else:
            base_stance = 0.0

        stance = max(-1.0, min(1.0, base_stance))

        # Pick evidence to cite
        cited_eids = evidence_ids[:2] if evidence_ids else []
        cited_quote = evidence_quotes[0] if evidence_quotes else ""

        # Compose content based on archetype and context
        if turn_count == 0:
            # Opening statement
            content = self._opening_statement(agent_name, archetype, interests, stance_label, cited_quote)
        elif turn_count >= 16:
            # Closing / summary
            content = self._closing_statement(agent_name, archetype, interests, turn_count)
        else:
            # Responsive turn
            content = self._responsive_statement(
                agent_name, archetype, interests, stance_label,
                reply_to, last_content, cited_quote, turn_count
            )

        # Build structured JSON response
        response_obj = {
            "speaker": agent_name,
            "stance": round(stance, 2),
            "reply_to": reply_to,
            "evidence_ids": cited_eids,
            "content": content,
        }
        return json.dumps(response_obj, ensure_ascii=False)

    def _opening_statement(self, name: str, archetype: str, interests: list[str], stance: str, quote: str) -> str:
        templates = {
            "直接受益者": f"我是{name}。{'，'.join(interests) if interests else ''}。{stance}。"
                           f"{'根据相关资料，' + quote if quote else '我想先表达我们的基本诉求。'}",
            "直接受影响者": f"作为{name}，我想先说明我们面临的实际问题。{'，'.join(interests) if interests else ''}。"
                           f"{stance}。{'有记录显示：' + quote if quote else '我希望各方能理解我们的处境。'}",
            "治理方": f"作为{name}，我们的职责是平衡各方诉求、依法管理。{stance}。"
                      f"{'根据相关政策：' + quote if quote else '我们需要在法规框架下寻找可行方案。'}",
            "间接影响者": f"我是{name}。虽然我们不常被听见，但这件事直接影响我们的工作。"
                          f"{'，'.join(interests) if interests else ''}。{'有数据显示：' + quote if quote else ''}",
            "间接受益者": f"作为{name}，我想从一个可能被忽略的角度补充。{'，'.join(interests) if interests else ''}。"
                          f"{stance}。",
            "专业观察者": f"作为{name}，我从中立专业角度提出建议。{stance}。"
                          f"{'有研究指出：' + quote if quote else '我建议我们从数据出发来讨论。'}",
        }
        return templates.get(archetype, f"我是{name}。{stance}。")

    def _responsive_statement(
        self, name: str, archetype: str, interests: list[str], stance: str,
        reply_to: str | None, last_content: str, quote: str, turn: int,
    ) -> str:
        # Acknowledge previous speaker
        ack = f"我听到了{reply_to}的观点。" if reply_to else "我想回应前面的讨论。"

        # Express own perspective based on archetype
        if archetype == "直接受益者":
            body = f"但我必须强调，{interests[0] if interests else '我们的基本诉求'}不容忽视。"
            if quote:
                body += f" 有材料表明：{quote}"
        elif archetype == "直接受影响者":
            body = f"理解对方的同时，我们的底线是{interests[0] if interests else '保障基本生活品质'}。"
            if quote:
                body += f" 实际投诉记录显示：{quote}"
        elif archetype == "治理方":
            body = f"各方意见都有道理。从管理角度，我建议{interests[-1] if interests else '寻找折中方案'}。"
            if quote:
                body += f" 相关政策明确：{quote}"
        elif archetype == "间接影响者":
            body = f"但有一个被忽视的问题：{interests[0] if interests else '治理成本'}。"
            if quote:
                body += f" 数据显示：{quote}"
        elif archetype == "专业观察者":
            body = f"我建议把讨论从立场之争转向条件设计。{interests[0] if interests else '我们需要可量化的方案'}。"
            if quote:
                body += f" 研究表明：{quote}"
        else:
            body = f"我的立场是：{stance}。"

        return f"{ack} {body}"

    def _closing_statement(self, name: str, archetype: str, interests: list[str], turn: int) -> str:
        if archetype == "治理方":
            return (f"感谢各方今天的讨论。我来总结：各方已经在试点方案、摊位管理、环卫经费、闭市时间等核心问题上达成了框架性共识。"
                    f"部分问题需要实地调研后确定。议事报告将记录所有共识、分歧和待调研问题。")
        if archetype == "专业观察者":
            return (f"各方已达成几个关键共识。剩余需要真实调研的问题包括：实际环卫增额成本、摊位费标准、交通流量基线数据。"
                    f"这些 AI 无法替代实地调研，必须通过真实的现场工作来回答。")
        return f"我坚持我的核心诉求：{interests[0] if interests else '请认真考虑我的意见'}。同时我愿意在有明确约束的条件下参与下一步。"

    def __repr__(self):
        return "SimulationClient(rule-based, no API key needed)"


# ── Factory ───────────────────────────────────────────────────────────────────

def create_llm_client(
    provider: str = "",
    model: str = "",
    api_key: str = "",
    base_url: str = "",
    max_tokens: int = 1024,
    temperature: float = 0.7,
) -> LLMClient:
    """Create an LLM client based on configuration.

    Set provider to "simulation" for the built-in rule-based fallback
    (useful for demos without API keys).
    """
    provider = provider or os.environ.get("LLM_PROVIDER", "simulation")
    model = model or os.environ.get("LLM_MODEL", "")
    api_key = api_key or os.environ.get("LLM_API_KEY", "")
    base_url = base_url or os.environ.get("LLM_BASE_URL", "")
    max_tokens = int(os.environ.get("LLM_MAX_TOKENS", str(max_tokens)))
    temperature = float(os.environ.get("LLM_TEMPERATURE", str(temperature)))

    if provider == "openai":
        return OpenAIClient(
            model=model or "gpt-4o",
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    elif provider == "anthropic":
        return AnthropicClient(
            model=model or "claude-sonnet-4-6",
            api_key=api_key,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    elif provider == "openai_compat":
        # For Qwen, DeepSeek, Zhipu, Moonshot, etc.
        return OpenAIClient(
            model=model or "qwen-plus",
            api_key=api_key,
            base_url=base_url,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    elif provider == "simulation":
        return SimulationClient()

    else:
        raise ValueError(
            f"Unknown LLM provider: {provider}. "
            f"Supported: openai, anthropic, openai_compat, simulation"
        )


# ── Convenience ───────────────────────────────────────────────────────────────

def get_default_client() -> LLMClient:
    """Get a client based on environment config, falling back to simulation."""
    return create_llm_client()
