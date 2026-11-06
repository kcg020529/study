# 04_memory.py
# 대화 이력 누적(add_messages)과 thread_id별 세션 격리 실습
# 모델: DeepSeek

from typing import Annotated
from typing_extensions import TypedDict
import os
import sys
from dotenv import load_dotenv
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages  # 메시지를 덮어쓰지 않고 누적하는 Reducer
from langgraph.checkpoint.memory import MemorySaver
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

load_dotenv()

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass


class MessageState(TypedDict):
    messages: Annotated[list, add_messages]


def run_conversational_agent():
    api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not api_key:
        print("[오류]: DEEPSEEK_API_KEY가 설정되지 않음. .env에 DEEPSEEK_API_KEY=... 추가")
        return

    model = ChatOpenAI(
        model="deepseek-chat",
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
        temperature=0.7
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", "상대방 이름을 기억하고 다정하게 답하는 챗봇 비서다."),
        MessagesPlaceholder(variable_name="messages")
    ])

    def call_model(state: MessageState):
        chain = prompt | model
        response = chain.invoke({"messages": state["messages"]})
        return {"messages": [response]}  # add_messages가 기존 이력 뒤에 누적

    memory = MemorySaver()

    workflow = StateGraph(MessageState)
    workflow.add_node("chatbot", call_model)
    workflow.add_edge(START, "chatbot")
    workflow.add_edge("chatbot", END)
    app = workflow.compile(checkpointer=memory)

    config_a = {"configurable": {"thread_id": "user_a_session"}}
    config_b = {"configurable": {"thread_id": "user_b_session"}}

    # A: 이름을 알려줌
    print("=== [A] 1차 질문 ===")
    q1 = [("user", "안녕! 내 이름은 홍길동이야. 기억해 줘.")]
    try:
        res1 = app.invoke({"messages": q1}, config_a)
        print(f"답변: {res1['messages'][-1].content}\n")
    except Exception as e:
        print(f"[오류]: {e}\n")
        return

    # B: 다른 세션이라 A의 이름을 모름이 정상
    print("=== [B] 세션 격리 확인 ===")
    q2 = [("user", "방금 내 이름을 말한 사람 이름이 뭐야?")]
    try:
        res2 = app.invoke({"messages": q2}, config_b)
        print(f"답변: {res2['messages'][-1].content}\n")
    except Exception as e:
        print(f"[오류]: {e}\n")

    # A: 같은 thread_id라 이름을 기억함
    print("=== [A] 메모리 확인 ===")
    q3 = [("user", "내 이름이 뭔지 다시 말해봐.")]
    try:
        res3 = app.invoke({"messages": q3}, config_a)
        print(f"답변: {res3['messages'][-1].content}\n")
    except Exception as e:
        print(f"[오류]: {e}\n")


if __name__ == "__main__":
    run_conversational_agent()
