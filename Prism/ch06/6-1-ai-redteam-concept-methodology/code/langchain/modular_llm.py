# modular_llm.py
# --------------
# 04 단계: 랭체인의 언어 모델(LLM) 컴포넌트를 독립 모듈로 분리 선언함.
#
# 프롬프트(modular_prompt.py) · 모델(이 파일) · 파서(modular_parser.py)를 파일별로 나눠 두면,
# 각 부품을 따로 수정·교체·재사용할 수 있고, modular_main.py에서는 import 한 뒤
# `simple_prompt | chat_model | string_parser` 처럼 파이프(|)로 조립하기만 하면 됨.
#
# 이 모듈이 외부에 제공하는 것
#   - chat_model : 설정이 끝난 DeepSeek 채팅 모델 객체 (modular_main.py가 import 해서 사용)
#
# 사전 준비
#   - .env 파일에 DEEPSEEK_API_KEY=... 를 넣어 둠. (키는 코드에 직접 쓰지 않음.)

import os                                                          # 환경변수를 읽기 위한 표준 라이브러리
from dotenv import load_dotenv                                     # .env 파일의 값을 환경변수로 읽어오는 도구
from langchain_openai import ChatOpenAI                            # DeepSeek 호환 API용 채팅 모델 래퍼

# [1단계] 환경변수(.env) 로딩 수행
# - 인자 없이 호출하면 현재 파일 위치에서 시작해 상위 폴더 방향으로 .env를 찾아 읽음.
# - 이미 OS 환경변수로 설정된 값이 있으면 그 값이 우선함. (load_dotenv 기본 동작)
# - import 되는 순간 실행되므로, modular_main.py가 이 모듈을 import 할 때 함께 로드됨.
load_dotenv()

# [2단계] 환경변수에서 DeepSeek API 키를 읽어 모델 인스턴스 구축
# - 소스 코드에 키가 하드코딩되지 않으므로, 이 모듈을 안심하고 다른 팀원들과 공유할 수 있음.
# - os.getenv()는 변수가 없으면 None을 돌려줌. 오류가 나면 .env의 변수 이름과 값을 확인.
api_key = os.getenv("DEEPSEEK_API_KEY")

# [3단계] 채팅 모델 객체 생성 (이 시점에는 API 요청을 보내지 않고, 실제 요청은 chain.invoke() 때 발생)
# - model/base_url: DeepSeek 모델과 API 엔드포인트
# - api_key: 위에서 읽은 인증 키
# - temperature: 답변의 창의성 정도 (0.0에 가까울수록 일관되고 1.0에 가까울수록 창의적)
# - 모듈 최상위(전역)에 만들어 두었기 때문에, 여러 파일이 import 해도 같은 객체를 재사용함.
chat_model = ChatOpenAI(
    model="deepseek-chat",
    api_key=api_key,
    base_url="https://api.deepseek.com/v1",
    temperature=0.7
)

