# structured_output.py
# --------------------
# 06 단계: 구조화된 출력 (Structured Output) — 기본 개념
#
# 지금까지는 StrOutputParser로 AI의 답변을 "문자열"로만 받았음.
# 문자열은 사람이 읽기엔 좋지만, 코드에서 쓰려면(화면 표시, DB 저장, 다른 함수로 전달 등)
# 필요한 값을 다시 잘라 내야 함.
#
#   04단계(문자열)  : "...난이도는 3점이에요..."  → 코드가 문장에서 3을 직접 찾아야 함
#   06단계(구조화)  : card.difficulty == 3        → 필드로 바로 접근, 타입·범위는 자동 검증
#
# 이 실습은 Pydantic 클래스로 "받고 싶은 형식"을 먼저 정의하고,
# model.with_structured_output(클래스)로 AI의 답변을 그 형식의 객체로 바로 받음.
#
# 흐름도: structured_output_flow.svg
#   ① 질문 → ② 프롬프트 → ③ 구조화된 모델 → ④ ConceptCard 객체 → ⑤ 필드별 활용
#   (아래 "▶ 플로우" 주석이 각 노드의 코드 위치를 가리킴.)
#
# 이 파일과 risk_summary.py의 차이
#   - structured_output.py : with_structured_output 한 가지로 개념을 가장 짧게 보여 줌. (입문용)
#   - risk_summary.py      : Literal 허용값, 파서, 재시도, 실패 사례 등 운영에서 필요한 패턴을 다룸. (실습용)
#
# 실행 방법: 06_structured_output 폴더에서  python structured_output.py
#
# 사전 준비
#   - .env 파일에 DEEPSEEK_API_KEY 를 넣어 둠.

import os
import sys
from typing import List

from dotenv import load_dotenv                                  # .env 파일의 값을 환경변수로 읽어오는 도구
from pydantic import BaseModel, Field                           # 받고 싶은 데이터 형식을 정의하는 도구
from langchain_core.prompts import ChatPromptTemplate           # 질문을 담아 모델에 전달할 프롬프트 템플릿
from langchain_openai import ChatOpenAI                         # DeepSeek 호환 API용 채팅 모델 래퍼

# 터미널 출력 인코딩이 UTF-8이 아니면 한글이 깨질 수 있어 보정함.
# (reconfigure()를 지원하지 않는 오래된 Python 버전에서는 AttributeError가 나므로 무시함.)
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

# .env의 값을 환경변수로 로드함. (현재 파일 위치에서 상위 폴더 방향으로 .env를 탐색)
# - 이미 OS 환경변수로 설정된 값이 있으면 그 값이 우선함. (load_dotenv 기본 동작)
load_dotenv()


# [1단계] 받고 싶은 출력 형식 정의  ▶ 플로우 ④ ConceptCard 객체의 설계도
# - BaseModel을 상속한 클래스의 "필드 이름과 타입"이 곧 AI가 채워야 할 답변 형식이 됨.
# - Field(description=...): 각 필드가 무엇인지 AI에게 알려 주는 설명임. (답변 품질에 영향)
#   모델은 이 설명을 보고 어떤 내용을 어느 필드에 넣을지 판단하므로, 구체적으로 쓸수록 정확해짐.
# - ge/le: 숫자 범위 검사(greater-or-equal / less-or-equal). 범위를 벗어난 값이 오면 Pydantic이 검증 오류를 냄.
# - List[str]: 문자열 목록. 타입이 맞지 않으면(예: 문자열 하나만 온 경우) 검증에서 거부됨.
class ConceptCard(BaseModel):
    name: str = Field(description="설명하는 개념의 이름")
    summary: str = Field(description="개념을 한 문장으로 요약")
    analogy: str = Field(description="초등학생도 이해할 수 있는 쉬운 비유")
    difficulty: int = Field(description="이해 난이도. 1(매우 쉬움) ~ 5(매우 어려움)", ge=1, le=5)
    keywords: List[str] = Field(description="핵심 키워드 3개")


def main():
    # API 키 읽기
    # - 키가 없는 채로 모델을 만들면 인증 오류가 나므로, 먼저 확인하고 안내 후 종료함.
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        print("[오류] .env 파일에 DEEPSEEK_API_KEY가 설정되어 있지 않습니다.")
        return

    # [2단계] 일반 채팅 모델 생성 (04단계와 동일)
    # - 이 시점에는 API 요청을 보내지 않음. 요청은 chain.invoke() 때 발생함.
    # - temperature: 0.0에 가까울수록 일관된 답, 1.0에 가까울수록 다양한 답
    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=api_key,
        base_url="https://api.deepseek.com/v1",
        temperature=0.7
    )

    # [3단계] 모델에 출력 형식 연결  ▶ 플로우 ③ 구조화된 모델
    # - with_structured_output(ConceptCard): "이 형식으로만 답하라"는 제약을 모델에 붙임.
    #   (내부적으로 클래스의 JSON Schema를 모델의 구조화 출력 기능에 전달함.)
    # - 이 모델의 출력은 AIMessage나 문자열이 아니라 ConceptCard 객체임.
    # - 따라서 체인 끝에 StrOutputParser가 필요 없음. (파싱과 검증을 이미 수행)
    # - DeepSeek API의 도구 호출 기능을 사용해 스키마를 전달함.
    structured_llm = llm.with_structured_output(ConceptCard, method="function_calling")

    # [4단계] 프롬프트 템플릿  ▶ 플로우 ② 프롬프트
    # - 출력 형식은 코드(ConceptCard)로 지정했으므로, 프롬프트에는 역할과 요청만 적으면 됨.
    #   ("JSON으로 답해라" 같은 형식 지시문을 프롬프트에 따로 쓸 필요가 없음.)
    # - {concept}는 실행 시점에 실제 개념으로 치환되는 변수임.
    prompt = ChatPromptTemplate.from_template(
        "당신은 초등학생도 쉽게 이해하도록 돕는 유능한 교육용 튜터입니다. "
        "다음 개념을 설명하는 카드를 만들어 주세요.\n\n개념: {concept}"
    )

    # [5단계] LCEL 체인 조립: 프롬프트 -> 구조화된 모델
    # - 04단계의 "프롬프트 | 모델 | 파서"에서 마지막 파서가 빠진 형태임.
    chain = prompt | structured_llm

    # [6단계] 체인 실행  ▶ 플로우 ① 질문 → ④ ConceptCard 객체
    # - invoke()에 넘기는 딕셔너리의 키는 프롬프트의 변수명({concept})과 같아야 함.
    concept_query = "네트워크 라우터 (Router)"
    print(f"=== [구조화된 출력] 개념 카드 요청: '{concept_query}' ===")

    # 네트워크/인증/요금/검증 오류가 나도 프로그램이 비정상 종료되지 않도록 try로 감쌈.
    try:
        # 이때 실제 API 요청이 발생하고, 결과는 ConceptCard 객체로 돌아옴.
        card = chain.invoke({"concept": concept_query})

        # [7단계] 결과 활용  ▶ 플로우 ⑤ 필드별 활용
        # - card는 문자열이 아니라 ConceptCard 객체이므로 필드에 바로 접근할 수 있음.
        # - difficulty는 정수(int)이므로 문자열 처리 없이 별 모양 계산에 바로 쓸 수 있음.
        print(f"\n[타입] {type(card).__name__}")
        print(f"이름     : {card.name}")
        print(f"요약     : {card.summary}")
        print(f"비유     : {card.analogy}")
        print(f"난이도   : {'★' * card.difficulty}{'☆' * (5 - card.difficulty)} ({card.difficulty}/5)")
        print(f"키워드   : {', '.join(card.keywords)}")

        # 코드에서 다시 쓰기 좋은 형태로 변환할 수도 있음. (JSON 저장, API 응답 등)
        # - model_dump_json(): 객체를 JSON 문자열로, model_dump(): 파이썬 딕셔너리로 변환함.
        print("\n[JSON 변환]")
        print(card.model_dump_json(indent=2))

    except Exception as e:
        # 흔한 원인: 키 오류, 크레딧 소진(429), 모델이 형식에 맞지 않는 값을 낸 경우(검증 오류)
        print(f"\n[오류 발생]: {e}")


# 이 파일을 직접 실행할 때만 main()을 호출함. (다른 파일에서 import 하면 실행되지 않음)
if __name__ == "__main__":
    main()

