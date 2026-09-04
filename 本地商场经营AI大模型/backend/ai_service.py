import json
import os
import re

from langchain.prompts import PromptTemplate
from langchain_community.llms import Ollama

# 容器内连宿主机 Ollama 用 http://host.docker.internal:11434；本地裸跑用默认值即可
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

llm = Ollama(model=OLLAMA_MODEL, base_url=OLLAMA_BASE_URL)

_PROMPT = PromptTemplate.from_template("""
你是一位资深商场运营专家。以下是今天{date}的销售数据：
总销售额：{total_sales}元，总毛利：{profit}元，毛利率：{margin}%
各品类表现：{category_detail}

请基于这些数据，用中文给出3条具体的、可执行的运营改进建议。
每条建议包含：
1. 策略名称
2. 针对问题/机会
3. 执行措施
4. 预期效果

直接返回JSON数组，格式：[{{"title":"...","reason":"...","action":"...","effect":"..."}}]
不要多余的解释。
""")
_STRICT_SUFFIX = "\n严格只输出JSON数组，不要任何解释文字，不要使用markdown代码块。"

_REQUIRED_KEYS = ("title", "reason", "action", "effect")


def _clean_output(s: str) -> str:
    """剥掉推理模型的思维链和 markdown 围栏（lstrip 按字符集合剥离，不能用来删前缀）。"""
    s = re.sub(r"<think>.*?</think>", "", s, flags=re.S)
    s = re.sub(r"^\s*```(?:json)?\s*|\s*```\s*$", "", s, flags=re.S)
    return s.strip()


def _extract_json_array(s: str):
    """两级解析：直接 loads → 提取第一个 [...] 再 loads；失败返回 None。"""
    try:
        data = json.loads(s)
    except json.JSONDecodeError:
        match = re.search(r"\[.*\]", s, flags=re.S)
        if not match:
            return None
        try:
            data = json.loads(match.group(0))
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, list) else None


def generate_advice(daily_data, category_data):
    """返回 (suggestions, warning)。调用失败或解析失败都不抛异常，降级为空列表。"""
    variables = {
        "date": daily_data["date"],
        "total_sales": daily_data["total_sales"],
        "profit": daily_data["total_profit"],
        "margin": daily_data["margin"],
        "category_detail": str(category_data),
    }
    try:
        data = _extract_json_array(_clean_output((_PROMPT | llm).invoke(variables)))
        if data is None:  # 重试一次，追加更强的输出约束
            strict = PromptTemplate.from_template(_PROMPT.template + _STRICT_SUFFIX) | llm
            data = _extract_json_array(_clean_output(strict.invoke(variables)))
    except Exception as e:
        return [], f"AI 服务调用失败：{e}"
    if data is None:
        return [], "模型输出解析失败，请稍后重试"
    suggestions = [item for item in data
                   if isinstance(item, dict) and all(k in item for k in _REQUIRED_KEYS)]
    if not suggestions:
        return [], "模型输出格式不符合预期，请稍后重试"
    return suggestions, None
