# 05_agentic_rag.py
# Agentic RAG: 질문 분류 -> 검색어 재작성 -> 검색 -> 문서 판정 -> (재검색 | 답변 | 안내)
#
# 모델 구성
#   - 임베딩: Gemini (DeepSeek은 임베딩 API가 없음)
#   - 채팅/분류/판정: DeepSeek
#
# 흐름
#   START -> router -+- chat -> general_chat --------------------------> END
#                     +- rag  -> rewrite_query -> retrieve -> grade_documents
#                                     ^                              |
#                                     | 관련 문서 없음 + 재시도 가능       |
#                                     +------------------------------+
#                                          있음 -> generate -> END
#                                          한도 초과 -> fallback -> END
#
# 실행: .env에 GOOGLE_API_KEY(임베딩용), DEEPSEEK_API_KEY(채팅용) 필요

import os
import sys
from typing import TypedDict, List, Literal

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from langchain_community.vectorstores import FAISS
from langchain_google_genai import GoogleGenerativeAIEmbeddings
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langgraph.graph import StateGraph, START, END

if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

load_dotenv()

MAX_RETRIES = 2   # 재검색 최대 횟수 (무한 루프 방지)
TOP_K = 3
FALLBACK_MESSAGE = "죄송합니다. 문의하신 내용은 확인된 정보에 없습니다. 매장으로 직접 문의해 주세요."

DOCUMENTS = [
    ("store_info#hours", "이 피자 가게의 영업시간은 매일 오전 11시부터 오후 10시까지입니다."),
    ("store_info#menu", "대표 메뉴인 페퍼로니 피자의 가격은 18,000원이며, 치즈 추가는 2,000원입니다."),
    ("store_info#parking", "가게 앞 전용 주차장이 있으며, 방문 손님은 2시간까지 무료로 주차할 수 있습니다."),
    ("store_info#reservation", "예약은 전화로만 가능하며, 4인 이상 단체는 하루 전까지 예약해야 합니다."),
]


# Literal에 없는 값은 거부됨 -> 응답 형식이 깨지지 않음
class Route(BaseModel):
    route: Literal["rag", "chat"] = Field(description="가게 정보 질문이면 rag, 일상 대화면 chat")


class Grade(BaseModel):
    relevant: Literal["yes", "no"] = Field(description="문서에 질문의 답이 있으면 yes")


class GraphState(TypedDict):
    question: str
    route: str
    search_query: str
    attempts: int
    documents: List[dict]
    relevant_docs: List[dict]
    generation: str
    path: str  # 평가용: "rag" / "chat" / "fallback"


def safe_print(text: str):
    try:
        print(text)
    except UnicodeEncodeError:
        print(text.encode(sys.stdout.encoding, errors='replace').decode(sys.stdout.encoding))


def build_app(google_api_key: str, deepseek_api_key: str):
    # 임베딩은 Gemini로 고정 (DeepSeek은 임베딩 미지원)
    embeddings = GoogleGenerativeAIEmbeddings(model="models/gemini-embedding-001", google_api_key=google_api_key)
    embeddings.embed_query("test")  # 키/모델명 사전 검증
    print("[INFO] Gemini embeddings 연결됨")

    vectorstore = FAISS.from_texts(
        [text for _, text in DOCUMENTS], embeddings,
        metadatas=[{"source": source} for source, _ in DOCUMENTS],
    )

    model = ChatOpenAI(
        model="deepseek-chat", api_key=deepseek_api_key,
        base_url="https://api.deepseek.com/v1", temperature=0, timeout=60, max_retries=3,
    )
    # DeepSeek은 function_calling 방식으로 구조화 출력을 강제함
    router_llm = model.with_structured_output(Route, method="function_calling")
    grader_llm = model.with_structured_output(Grade, method="function_calling")

    # 질문 유형 분류 (Adaptive): 일상 대화는 검색 없이 바로 답함
    def route_question(state: GraphState) -> GraphState:
        print(f"[Router] '{state['question']}'")
        prompt = ChatPromptTemplate.from_template(
            "질문을 분류하세요.\n- 가게 정보(영업시간·메뉴·가격·주차·예약·배달)면 rag\n- 인사·잡담·상식이면 chat\n- 애매하면 rag\n\n질문: {question}"
        )
        result = (prompt | router_llm).invoke({"question": state["question"]})
        route = result.route if result is not None else "rag"  # 파싱 실패 시 검색 경로(안전한 쪽)
        print(f"[*] {route.upper()}")
        return {"route": route, "attempts": 0}

    def generate_general_answer(state: GraphState) -> GraphState:
        answer = (model | StrOutputParser()).invoke(state["question"])
        return {"generation": answer, "path": "chat"}

    # 검색어 재작성: 재시도 때는 이전 검색어와 다른 표현으로
    def rewrite_query(state: GraphState) -> GraphState:
        attempts = state.get("attempts", 0)
        if attempts == 0:
            prompt = ChatPromptTemplate.from_template(
                "다음 질문을 검색하기 좋은 짧은 문장으로 바꾸세요. 바꾼 문장만 출력.\n\n질문: {question}"
            )
            query = (prompt | model | StrOutputParser()).invoke({"question": state["question"]})
        else:
            prompt = ChatPromptTemplate.from_template(
                "이전 검색어로 문서를 못 찾았습니다. 다른 표현으로 검색 문장을 만드세요. 만든 문장만 출력.\n\n질문: {question}\n이전 검색어: {previous}"
            )
            query = (prompt | model | StrOutputParser()).invoke(
                {"question": state["question"], "previous": state["search_query"]}
            )
        query = query.strip()
        print(f"[Rewrite] ({attempts + 1}차) '{query}'")
        return {"search_query": query, "attempts": attempts + 1}

    def retrieve_info(state: GraphState) -> GraphState:
        results = vectorstore.similarity_search_with_score(state["search_query"], k=TOP_K)
        documents = [
            {"text": doc.page_content, "source": doc.metadata.get("source", "unknown"), "score": float(score)}
            for doc, score in results
        ]
        print("[Retrieve] " + ", ".join(f"{d['source']}({d['score']:.2f})" for d in documents))
        return {"documents": documents}

    # 문서별 관련성 판정. 검색은 항상 가장 가까운 문서를 돌려주므로 판정이 필요함
    def grade_documents(state: GraphState) -> GraphState:
        prompt = ChatPromptTemplate.from_template(
            "[문서]에 [질문]의 답이 있으면 relevant=yes, 없으면 no.\n\n[문서]\n{document}\n\n[질문]\n{question}"
        )
        inputs = [{"document": d["text"], "question": state["question"]} for d in state["documents"]]
        grades = (prompt | grader_llm).batch(inputs)
        relevant = [d for d, g in zip(state["documents"], grades) if g is not None and g.relevant == "yes"]
        print(f"[Grade] {len(relevant)}/{len(state['documents'])}건: " + (", ".join(d["source"] for d in relevant) or "없음"))
        return {"relevant_docs": relevant}

    # 통과한 문서만 근거로 답하고 출처를 붙임 (없는 내용은 지어내지 않음)
    def generate_rag_answer(state: GraphState) -> GraphState:
        context = "\n".join(f"[출처: {d['source']}] {d['text']}" for d in state["relevant_docs"])
        prompt = ChatPromptTemplate.from_template(
            "피자 가게 점원이다. [참고 정보]에 있는 내용만 사용해 답하라. 없는 내용은 지어내지 말고, 끝에 (출처: ID)를 적어라.\n\n[참고 정보]\n{context}\n\n질문: {question}"
        )
        answer = (prompt | model | StrOutputParser()).invoke({"context": context, "question": state["question"]})
        return {"generation": answer, "path": "rag"}

    # 재시도 한도까지 못 찾으면 LLM 호출 없이 고정 안내문
    def fallback_answer(state: GraphState) -> GraphState:
        return {"generation": FALLBACK_MESSAGE, "path": "fallback"}

    def decide_after_route(state: GraphState) -> str:
        return "rag" if state["route"] == "rag" else "chat"

    def decide_after_grade(state: GraphState) -> str:
        if state["relevant_docs"]:
            return "generate"
        if state["attempts"] <= MAX_RETRIES:
            return "rewrite"
        return "fallback"

    workflow = StateGraph(GraphState)
    workflow.add_node("router", route_question)
    workflow.add_node("general_chat", generate_general_answer)
    workflow.add_node("rewrite_query", rewrite_query)
    workflow.add_node("retrieve", retrieve_info)
    workflow.add_node("grade_documents", grade_documents)
    workflow.add_node("generate", generate_rag_answer)
    workflow.add_node("fallback", fallback_answer)

    workflow.add_edge(START, "router")
    workflow.add_edge("rewrite_query", "retrieve")
    workflow.add_edge("retrieve", "grade_documents")
    workflow.add_conditional_edges("router", decide_after_route, {"rag": "rewrite_query", "chat": "general_chat"})
    workflow.add_conditional_edges(
        "grade_documents", decide_after_grade,
        {"generate": "generate", "rewrite": "rewrite_query", "fallback": "fallback"}
    )
    workflow.add_edge("general_chat", END)
    workflow.add_edge("generate", END)
    workflow.add_edge("fallback", END)

    return workflow.compile()


# 기대 경로와 실제 경로를 비교해 정확도를 측정
EVAL_SET = [
    ("피자 가격 알려주세요.", "rag"),
    ("몇 시까지 영업하나요?", "rag"),
    ("주차 가능한가요?", "rag"),
    ("배달도 되나요?", "fallback"),  # 가게 질문이지만 문서에 답이 없음
    ("아인슈타인이 누구야?", "chat"),
    ("안녕하세요!", "chat"),
]


def run_agentic_rag():
    google_api_key = os.environ.get("GOOGLE_API_KEY", "").strip()
    deepseek_api_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if not google_api_key:
        print("[오류]: GOOGLE_API_KEY가 설정되지 않음 (임베딩용)")
        return
    if not deepseek_api_key:
        print("[오류]: DEEPSEEK_API_KEY가 설정되지 않음 (채팅용)")
        return

    try:
        app = build_app(google_api_key, deepseek_api_key)
    except Exception as e:
        print(f"[오류]: 초기화 실패 - {type(e).__name__}: {e}")
        return

    correct = 0
    mismatches = []
    for i, (question, expected) in enumerate(EVAL_SET, start=1):
        print(f"\n=== [{i}/{len(EVAL_SET)}] {question} (기대: {expected}) ===")
        try:
            result = app.invoke({"question": question})
        except Exception as e:
            print(f"[오류]: {type(e).__name__}: {e}")
            mismatches.append((question, expected, "error"))
            continue

        actual = result.get("path", "unknown")
        safe_print(f"답변: {result['generation']}")
        print(f"실제 경로: {actual}")
        if actual == expected:
            correct += 1
        else:
            mismatches.append((question, expected, actual))

    print(f"\n=== 정확도: {correct}/{len(EVAL_SET)} ({correct / len(EVAL_SET):.0%}) ===")
    for question, expected, actual in mismatches:
        print(f"  불일치: '{question}' 기대={expected}, 실제={actual}")


if __name__ == "__main__":
    run_agentic_rag()
