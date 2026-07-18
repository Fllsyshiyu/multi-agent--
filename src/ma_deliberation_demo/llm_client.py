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


# ── Provider to API key env var mapping ─────────────────────────────────────

PROVIDER_API_KEY_ENV = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "openai_compat": "OPENAI_API_KEY",  # fallback
    "deepseek": "DEEPSEEK_API_KEY",
    "qwen": "DASHSCOPE_API_KEY",
    "zhipu": "ZHIPU_API_KEY",
    "moonshot": "MOONSHOT_API_KEY",
    "gemini": "GEMINI_API_KEY",
}


def resolve_api_key(provider: str, api_key: str = "", model: str = "") -> str:
    """Resolve API key: explicit > provider-specific env > generic env."""
    if api_key:
        return api_key

    # Try provider-specific env var
    env_var = PROVIDER_API_KEY_ENV.get(provider, "")
    if env_var:
        val = os.environ.get(env_var, "")
        if val:
            return val

    # Fallback: try LLM_API_KEY
    return os.environ.get("LLM_API_KEY", "")


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
        self.api_key = resolve_api_key("openai", api_key, model)
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
        msg = response.choices[0].message
        content = msg.content or ""
        # DeepSeek V4 reasoning models may return content in reasoning_content
        if not content:
            reasoning = getattr(msg, "reasoning_content", "") or ""
            if reasoning:
                content = reasoning
        return content

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
        self.api_key = resolve_api_key("anthropic", api_key, model)
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

    # A rule-based fallback is useful for demonstrations, but callers must be
    # able to distinguish it from a live model.
    is_simulation = True

    def chat(self, messages: list[dict], system: str = "", json_mode: bool = False) -> str:
        user_text = "\n".join(str(message.get("content", "")) for message in messages)
        task = self._detect_task(user_text)

        # Proposal, review, revision, and report prompts have incompatible JSON
        # contracts.  Previously this client returned a speech object for every
        # task, allowing an identity statement to become a proposal and a missing
        # review recommendation to silently default to "pass".
        if task == "proposal":
            return json.dumps(self._simulation_proposal(user_text), ensure_ascii=False)
        if task == "review":
            return json.dumps(self._simulation_review(), ensure_ascii=False)
        if task == "revision":
            return json.dumps({
                "content": "【规则模拟】无法代替模型或人工对方案作实质修订；请补充有效讨论与证据后重新生成。",
            }, ensure_ascii=False)
        if task == "report":
            return json.dumps({
                "executive_summary": "【规则模拟】本轮未调用真实语言模型，不能据此形成公共事务结论。",
                "recommendations": ["配置并验证模型后重新开展讨论", "补充可核验的事实材料与证据引用"],
                "minority_preservation": "规则模拟不构成对少数意见的实质记录。",
            }, ensure_ascii=False)

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
            match = re.search(r"\[([^\]]+)\]:\s*([^\n]+)", content)
            if match:
                last_speaker = match.group(1).strip()
                last_content = match.group(2).strip()
                break

        # Extract evidence from system prompt
        evidence_ids = []
        evidence_quotes = []
        for line in system.split("\n"):
            if "证据" in line and "来源" in line:
                match = re.search(r'\[证据\s*(\d+)\]\s*([\w:-]+)', line)
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
            turn_count=len(re.findall(r"\[[^\]]+\]:", user_text)),
        )

        return response

    @staticmethod
    def _detect_task(user_text: str) -> str:
        """Classify the requested JSON contract before composing a response."""
        if "required_revisions" in user_text and "recommendation" in user_text:
            return "review"
        if "evaluation_criteria" in user_text and "方案正文" in user_text:
            return "proposal"
        if "修订后的完整方案正文" in user_text:
            return "revision"
        if "executive_summary" in user_text and "recommendations" in user_text:
            return "report"
        return "speech"

    @staticmethod
    def _simulation_proposal(user_text: str) -> dict:
        """Return a correctly typed non-final draft in rule simulation mode."""
        topic_match = re.search(r"##\s*议题\s*\n([^\n]+)", user_text)
        topic = topic_match.group(1).strip() if topic_match else "当前议题"
        return {
            "title": f"关于{topic[:24]}的待补证据草案",
            "content": (
                "【规则模拟草案，禁止作为结论】当前未获得真实语言模型的实质论证输出。"
                "在补充利益相关方的具体主张、可核验证据、分歧回应及实施条件前，"
                "本系统只能登记待讨论事项，不能形成治理方案或公共决策建议。"
            ),
            "timeline": "待模型讨论与事实核验完成后确定",
            "resources": "待核验：组织协调、事实调研、记录与反馈渠道",
            "risks": "缺少实质讨论和证据时，任何具体治理措施均可能误判实际情况",
            "evaluation_criteria": ["每个关键主张均有可追溯证据", "主要分歧得到明确记录"],
        }

    @staticmethod
    def _simulation_review() -> dict:
        """A simulation must block, rather than auto-approve, proposal review."""
        return {
            "issues": ["当前使用规则模拟回退，未形成可供审查的真实模型讨论与方案输出。"],
            "public_resource_scores": {},
            "universalization_result": {"status": "fail", "reason": "缺少可验证的实质讨论"},
            "minority_retention_ok": False,
            "required_revisions": ["配置可用模型并补充证据后重新开展议事"],
            "recommendation": "revise",
            "review_detail": "规则模拟只能演示流程，不能替代方案审查；本次结果不得标记为通过。",
        }

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
                inline = line.split(prefix, 1)[1].strip()
                if inline:
                    items.extend(item.strip() for item in re.split(r"[，,；;]", inline) if item.strip())
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
        # Dynamic role planning uses more precise role names than the legacy
        # demo. Normalize them here so the simulation remains a meaningful
        # fallback instead of printing "我是… + 基本立场" verbatim.
        aliases = {
            "直接受益方": "直接受益者",
            "直接受影响方": "直接受影响者",
            "治理与执行方": "治理方",
            "一线实施与运维方": "间接影响者",
            "专业与证据角色": "专业观察者",
        }
        archetype = aliases.get(archetype, archetype)
        core_interest = interests[0] if interests else "与议题相关的实际影响"
        templates = {
            "直接受益者": f"我们关注{core_interest}。我主张保留合理空间，但前提是把对他人的影响、可执行边界和责任写清楚。"
                           f"{'可参考材料：' + quote if quote else '请先核验实际需求与承受的成本。'}",
            "直接受影响者": f"我们首先要回应{core_interest}带来的具体影响。任何安排都应设置可投诉、可复核、可退出的保障条件。"
                           f"{'现有材料提示：' + quote if quote else '在事实未核验前，不能把影响视为可以忽略。'}",
            "治理方": f"治理上需要同时处理{core_interest}和各方权利边界。建议将争议拆成可执行的条件、责任主体和复盘节点。"
                      f"{'相关材料：' + quote if quote else '先以小范围试点和公开反馈来检验方案。'}",
            "间接影响者": f"从实施和运维角度，{core_interest}会影响日常资源与执行成本。"
                          f"建议把人力、时间和风险写入方案后再讨论是否推进。{'材料依据：' + quote if quote else ''}",
            "间接受益者": f"除了直接参与者，还应考虑{core_interest}这一容易被忽略的影响。"
                          "我支持在明确边界、透明监督和定期评估的条件下寻找折中安排。",
            "专业观察者": f"从证据与评估角度，{core_interest}需要先转化为可观察指标。"
                          f"{'现有材料显示：' + quote if quote else '建议先补齐基线事实，再比较不同方案的风险和收益。'}",
            "主持人": f"本轮先围绕具体争议与可核验事实展开，不作价值裁决。请各方说明主张、依据、底线及可接受条件，并回应上一位发言者。",
            "评审员": "目前不形成结论。请检查各方主张是否有依据、是否回应了受影响群体，以及未解决分歧是否被完整记录。",
        }
        return templates.get(
            archetype,
            f"围绕{core_interest}，我提出一个待核验的具体关注：需要明确实际影响、责任边界和可接受条件，再决定下一步方案。",
        )

    def _responsive_statement(
        self, name: str, archetype: str, interests: list[str], stance: str,
        reply_to: str | None, last_content: str, quote: str, turn: int,
    ) -> str:
        # Acknowledge previous speaker
        ack = f"我听到了{reply_to}的观点。" if reply_to else "我想回应前面的讨论。"

        aliases = {
            "直接受益方": "直接受益者", "直接受影响方": "直接受影响者",
            "治理与执行方": "治理方", "一线实施与运维方": "间接影响者",
            "专业与证据角色": "专业观察者",
        }
        archetype = aliases.get(archetype, archetype)

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
    base_url = base_url or os.environ.get("LLM_BASE_URL", "")
    max_tokens = int(os.environ.get("LLM_MAX_TOKENS", str(max_tokens)))
    temperature = float(os.environ.get("LLM_TEMPERATURE", str(temperature)))

    # Resolve API key: explicit arg > provider-specific env > LLM_API_KEY
    api_key = resolve_api_key(provider, api_key, model)

    if provider == "openai":
        return OpenAIClient(
            model=model or "gpt-4o",
            api_key=api_key,
            base_url=base_url or "https://api.openai.com/v1",
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
        # For Qwen, DeepSeek, Zhipu, Moonshot, Gemini, etc.
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


# ── Key Validation ────────────────────────────────────────────────────────────

def validate_api_key(provider: str, model: str, api_key: str, base_url: str = "") -> dict:
    """Test an API key with a minimal call. Returns {valid: bool, error: str, provider: str, model: str}.

    Makes a tiny chat completion request (max 10 tokens) and checks the response.
    """
    result = {"valid": False, "error": "", "provider": provider, "model": model}

    if not api_key or not api_key.strip():
        result["error"] = "API Key 为空"
        return result

    if provider == "simulation":
        result["valid"] = True
        return result

    print(f"[VALIDATE] Testing {provider}/{model} via {base_url}...", flush=True)

    try:
        if provider == "anthropic":
            import anthropic
            client = anthropic.Anthropic(api_key=api_key)
            response = client.messages.create(
                model=model,
                max_tokens=10,
                messages=[{"role": "user", "content": "say ok"}],
            )
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text
            if text.strip():
                result["valid"] = True
                print(f"[VALIDATE] OK: {text[:30]}...", flush=True)
            else:
                result["error"] = "返回空响应"
                print(f"[VALIDATE] FAILED: empty response", flush=True)
        else:
            # OpenAI and OpenAI-compatible providers
            from openai import OpenAI
            url = base_url or "https://api.openai.com/v1"
            client = OpenAI(api_key=api_key, base_url=url)
            response = client.chat.completions.create(
                model=model,
                max_tokens=50,
                messages=[{"role": "user", "content": "say ok"}],
            )
            msg = response.choices[0].message
            content = (msg.content or "").strip()
            # DeepSeek V4 thinking mode may put response in reasoning_content
            reasoning = getattr(msg, "reasoning_content", "") or ""
            if content:
                result["valid"] = True
                print(f"[VALIDATE] OK: {content[:40]}...", flush=True)
            elif reasoning:
                result["valid"] = True
                print(f"[VALIDATE] OK (reasoning): {reasoning[:40]}...", flush=True)
            else:
                result["error"] = f"返回空响应 (finish_reason={response.choices[0].finish_reason})"
                print(f"[VALIDATE] FAILED: empty response, finish_reason={response.choices[0].finish_reason}", flush=True)
    except Exception as e:
        err_str = str(e)
        print(f"[VALIDATE] FAILED: {err_str[:120]}", flush=True)
        # Extract the most useful part of the error
        if "401" in err_str or "403" in err_str or "Unauthorized" in err_str:
            result["error"] = "API Key 无效 (认证失败)"
        elif "429" in err_str or "rate" in err_str.lower():
            result["error"] = "API 频率限制，稍后重试"
        elif "insufficient" in err_str.lower() or "balance" in err_str.lower():
            result["error"] = "API 余额不足"
        elif "connect" in err_str.lower() or "timeout" in err_str.lower() or "refused" in err_str.lower():
            result["error"] = "无法连接到 API 服务器"
        else:
            # Truncate long errors
            result["error"] = err_str[:150] if len(err_str) > 150 else err_str

    return result


# ── Convenience ───────────────────────────────────────────────────────────────

def get_default_client() -> LLMClient:
    """Get a client based on environment config, falling back to simulation."""
    return create_llm_client()
