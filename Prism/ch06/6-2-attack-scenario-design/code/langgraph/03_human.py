# 03_human.py
# Human-in-the-Loop: 민감한 행동(메일 발송 등) 전에 멈추고 사람 승인을 기다림
# interrupt_before + MemorySaver(체크포인터) 조합이 핵심

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass
from langgraph.checkpoint.memory import MemorySaver


class AgentState(TypedDict):
    action_type: str
    user_approved: bool


def prepare_email_node(state: AgentState) -> AgentState:
    print("\n--- [1] 메일 준비 완료 ---")
    return {"action_type": "send_email", "user_approved": False}


def send_email_node(state: AgentState) -> AgentState:
    print("\n--- [2] 메일 발송 ---")
    print("결과: 발송됨")
    return {"user_approved": True}


def run_human_in_the_loop():
    memory = MemorySaver()  # 중단 시점 상태를 저장해 이어서 실행 가능하게 함

    workflow = StateGraph(AgentState)
    workflow.add_node("prepare_email", prepare_email_node)
    workflow.add_node("send_email", send_email_node)
    workflow.add_edge(START, "prepare_email")
    workflow.add_edge("prepare_email", "send_email")
    workflow.add_edge("send_email", END)

    # send_email 실행 직전에 멈춤
    app = workflow.compile(checkpointer=memory, interrupt_before=["send_email"])

    # thread_id로 세션을 구분해야 이어서 실행할 수 있음
    config = {"configurable": {"thread_id": "session_1"}}
    print("=== 1단계: 메일 준비 ===")
    app.invoke({"action_type": "none", "user_approved": False}, config)

    print("\n[승인 대기] 발송 직전에 멈춤")
    user_confirm = input("발송할까요? (yes / no): ").strip().lower()

    if user_confirm == "yes":
        print("\n=== 2단계: 재개 ===")
        # None 입력 + 같은 config = 멈췄던 지점에서 이어서 실행
        app.invoke(None, config)
    else:
        print("\n거절됨. 발송 취소")


if __name__ == "__main__":
    run_human_in_the_loop()
