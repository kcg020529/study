# 02_agent.py
# LangGraph prebuilt ReAct 에이전트: 질문을 보고 도구 호출 여부를 스스로 판단함
# 모델: DeepSeek (OpenAI 호환 API라 ChatOpenAI로 연결)

from langchain_core.tools import tool
from langchain_openai import ChatOpenAI
import os
import sys
from dotenv import load_dotenv

load_dotenv()

# LangGraph 1.x: langchain.agents.create_agent / 구버전: langgraph.prebuilt.create_react_agent
try:
    from langchain.agents import create_agent as _create_agent

    def build_agent(model, tools, system_prompt):
        return _create_agent(model, tools, system_prompt=system_prompt)
except ImportError:
    from langgraph.prebuilt import create_react_agent as _create_agent

    def build_agent(model, tools, system_prompt):
        return _create_agent(model, tools, prompt=system_prompt)

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass


# docstring을 보고 모델이 호출 필요 여부를 판단함
@tool
def calculate_add(a: int, b: int) -> int:
    """두 정수 a, b를 더한 값을 반환한다. 덧셈이 필요할 때 호출."""
    return a + b


tools = [calculate_add]


def run_agent():
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("[오류]: DEEPSEEK_API_KEY가 설정되지 않음. .env에 DEEPSEEK_API_KEY=... 추가")
        return

    model = ChatOpenAI(
        model="deepseek-chat",
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
        temperature=0  # 도구 호출 판단의 일관성을 위해 0
    )

    system_prompt = "당신은 덧셈 질문에 맞춰 calculate_add 도구를 호출하는 계산 도우미다."
    agent_app = build_agent(model, tools, system_prompt)

    query = "345 더하기 987은 몇이야?"
    print(f"=== 질문: {query} ===")

    try:
        response = agent_app.invoke({"messages": [("user", query)]})
        print("\n=== 실행 내역 ===")
        for msg in response["messages"]:
            print(f"[{msg.type.upper()}]: {msg.content}")
    except Exception as e:
        print(f"\n[오류]: {type(e).__name__}: {e}")


if __name__ == "__main__":
    run_agent()
