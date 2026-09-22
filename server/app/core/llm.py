"""大模型接入（DeepSeek）。

设计要点：
    - 通过 OpenAI SDK 访问 DeepSeek（官方兼容 OpenAI 协议）；
    - api_key 只存在于服务端，绝不下发到客户端；
    - 单一 chat.completions 通道，stream=True 流式输出；
    - 首条注入「AI 求职助手」人设 + 「当前日期」两条 system 消息：
      人设保证模型在任何情况下都知道自己是谁、该按什么口径回答；
      日期用来解决模型不知道今天是哪天、时效类问题引用旧数据的问题；
    - 产出 (kind, text)：kind='text' 正文 / 'thinking' 思考链。

⚠️ 本期仅文本对话：
   deepseek-v4-flash 不支持图片输入，官方会把 input_image 替换为占位文本，
   唯一支持图片的是 deepseek-v4-flash-vision-exp（实验版），本期不实现。
"""
import logging
from datetime import datetime

from openai import AsyncOpenAI

from app.config import AI_API_KEY, AI_BASE_URL, AI_MODEL

logger = logging.getLogger(__name__)

# AsyncOpenAI 单例，避免每次对话重建连接池
_client: AsyncOpenAI | None = None


def get_client() -> AsyncOpenAI:
    """获取 AsyncOpenAI 客户端（单例）。

    异常：
        RuntimeError —— 未配置 AI_API_KEY 时抛出，文案直接指明改哪里，
                        避免用户只看到一句含糊的「对话失败」。
    """
    global _client
    if _client is None:
        if not AI_API_KEY:
            raise RuntimeError(
                "AI_API_KEY 未配置：请在 server/.env 中填写 DeepSeek API Key"
            )
        _client = AsyncOpenAI(api_key=AI_API_KEY, base_url=AI_BASE_URL)
    return _client


def _persona_line() -> str:
    """构造「AI 求职助手」的人设提示词。

    ⚠️ 为什么必须有它，而不是只靠 RAG 注入：
        RAG 的 system 消息只在**检索命中**时才注入（见 routers/ai.py 的 _inject_rag：
        无命中就直接 return False）。用户问通用问题（"简历怎么写"、"面试紧张怎么办"）时
        检索常常为空，此时模型收不到任何角色指令 —— 既不知道自己是谁，
        也不知道该按招聘口径还是通用口径回答。
        把「人设」放在这里，保证「有没有检索结果」都不影响它是谁。

    ⚠️ 与 RAG 提示词的分工：
        本函数管「身份与总原则」，rag.build_system_prompt() 管「本次检索到的资料怎么用」。
        两者同时存在是合法的（LLM 允许多条 system 消息），且顺序上人设在前。
    """
    return (
        "你是「直聘通」App 里的 AI 求职助手，同时服务求职者与企业招聘方。"
        "你的专长是：解读职位要求、优化简历、准备面试、分析岗位匹配度、给出求职与招聘建议。"
        "回答要求："
        "1. 用中文作答，条理清晰，需要分点时使用 Markdown 列表；"
        "2. 涉及具体职位、公司、薪资、经验或学历要求时，必须以检索到的资料为准，不要编造；"
        "3. 资料未涵盖时先说明「现有资料未涵盖」，再基于通用经验补充，并标明哪部分属于经验推断；"
        "4. 不给出法律、医疗等专业领域的确定性结论，也不替用户做最终决定。"
    )


def _today_line() -> str:
    """构造「当前日期」提示词。

    模型自身不知道今天日期，时效类问题会引用训练数据里的旧日期。
    在首条 system 消息中注入当天日期可显著改善此类回答。
    """
    now = datetime.now()
    return (
        "今天是 %d 年 %d 月 %d 日（星期%s，ISO %s）。"
        "涉及时间、时效性或最新信息的问题一律以今天为准，"
        "不要引用训练数据里的旧日期。" % (
            now.year, now.month, now.day,
            "一二三四五六日"[now.weekday()],
            now.strftime("%Y-%m-%d"),
        )
    )


def _delta_text(delta) -> tuple:
    """提取增量内容，返回 (正文, 思考链)。

    ⚠️ 推理内容字段名可能随 SDK 版本变化，这里同时兼容：
        - `reasoning_content` 顶层属性
        - `model_extra` 中的同名键
       取不到思考内容时退化为只返回正文，不影响主流程。
    """
    content = delta.content
    thinking = getattr(delta, "reasoning_content", None)
    if thinking is None:
        extra = getattr(delta, "model_extra", None) or {}
        thinking = extra.get("reasoning_content")
    return content, thinking


async def stream_chat(messages: list):
    """流式生成，逐段产出 (kind, text)，kind ∈ {'text', 'thinking'}。

    参数：
        messages: 上游消息列表（不含日期 system，由本函数注入）

    说明：
        - 上游错误原样上抛，由路由层统一转成 error 帧；
        - 整体超时由路由层 asyncio.timeout 控制，此处不设。
    """
    msgs = [
        {"role": "system", "content": _persona_line()},
        {"role": "system", "content": _today_line()},
        *messages,
    ]

    client = get_client()
    resp = await client.chat.completions.create(
        model=AI_MODEL,
        messages=msgs,
        stream=True,
    )

    async for chunk in resp:
        # 少数 chunk 的 choices 为空（如仅含用量统计），跳过
        if not chunk.choices:
            continue
        content, thinking = _delta_text(chunk.choices[0].delta)
        if thinking:
            yield "thinking", thinking
        elif content:
            yield "text", content
