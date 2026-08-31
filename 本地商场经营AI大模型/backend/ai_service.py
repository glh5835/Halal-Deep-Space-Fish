from langchain_community.llms import Ollama
from langchain.prompts import PromptTemplate
import json

llm = Ollama(model="qwen2.5:14b", base_url="http://ollama:11434")  # docker内部服务名

def generate_advice(daily_data, category_data):
    prompt = PromptTemplate.from_template("""
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
    chain = prompt | llm
    result = chain.invoke({
        "date": daily_data["date"],
        "total_sales": daily_data["total_sales"],
        "profit": daily_data["total_profit"],
        "margin": daily_data["margin"],
        "category_detail": str(category_data)
    })
    # 清洗可能包裹的markdown
    result = result.strip().lstrip("```json").rstrip("```").strip()
    return json.loads(result)