# 01_basic.py
# LangGraph 최소 구조: State(상태), Node(노드), Edge(엣지)

from typing import TypedDict
from langgraph.graph import StateGraph, START, END
import sys

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass


# 노드들이 공유하는 상태. 각 노드는 바뀐 키만 반환하고 나머지는 자동 병합됨
class GraphState(TypedDict):
    input_text: str
    processed_text: str


def first_node(state: GraphState) -> GraphState:
    print("\n--- [Node 1] ---")
    current_input = state["input_text"]
    return {"processed_text": current_input + " -> (1차 가공)"}


def second_node(state: GraphState) -> GraphState:
    print("\n--- [Node 2] ---")
    current_processed = state["processed_text"]
    return {"processed_text": current_processed + " -> (최종 가공)"}


def run_basic_graph():
    workflow = StateGraph(GraphState)
    workflow.add_node("node_one", first_node)
    workflow.add_node("node_two", second_node)

    # START -> node_one -> node_two -> END
    workflow.add_edge(START, "node_one")
    workflow.add_edge("node_one", "node_two")
    workflow.add_edge("node_two", END)

    app = workflow.compile()

    result = app.invoke({"input_text": "로컬 그래프 실습"})
    print("\n=== 결과 ===")
    print(result["processed_text"])


if __name__ == "__main__":
    run_basic_graph()
