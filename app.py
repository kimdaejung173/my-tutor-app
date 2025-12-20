import streamlit as st
from openai import OpenAI

# 페이지 기본 설정
st.set_page_config(page_title="영어 답지 공부법 생성기", page_icon="📝")

# 제목 및 설명
st.title("📝 수능 영어 독해 : 답지 공부법 모드")
st.write("선택지를 먼저 보고, 접속사 빈칸을 추론하며 지문을 읽어보세요.")

# 사이드바: API 키 입력
with st.sidebar:
    st.header("설정")
    api_key = st.text_input("OpenAI API Key를 입력하세요", type="password")
    st.markdown("[API Key 발급받는 곳](https://platform.openai.com/api-keys)")
    st.info("입력한 키는 저장되지 않고 휘발됩니다.")

# 프롬프트 설정 (AI에게 내리는 지시사항)
system_prompt = """
너는 수능 영어 전문 과외 선생님이다.
사용자를 위해 '학술적 소재(과학, 철학, 경제, 사회 등)'의 고난도 영어 지문 3개를 생성하라.
각 문제는 반드시 아래의 [포맷]을 엄격하게 준수해야 한다.

[포맷 가이드]
1. 문제 번호 및 제목
2. **[선택지]**: 5개의 영어 선택지와 한글 해석을 가장 먼저 보여준다. (정답은 표시하지 마라)
3. **[지문 독해]**:
   - 지문을 문장 단위로 쪼개어 나열한다.
   - 영어 문장 바로 아래에 한글 해석을 병렬로 배치한다.
   - 지문 내의 핵심 '논리 연결사(However, Therefore, For instance 등)'는 영어 문장에서 `[ A ]`, `[ B ]` 형태로 빈칸을 뚫어라. (한글 해석에는 해당 접속사의 의미를 괄호 치고 숨겨라. 예: ( 그 결과 ))
   - 지문의 핵심 내용은 빈칸 `_________`으로 뚫어라.
4. 모든 지문이 끝난 후 맨 마지막에 '정답 및 해설' 섹션을 따로 만든다.

[출력 예시]
### 문제 1. (주제)
**[선택지]**
1. apple (사과)
...
**[지문 독해]**
The world is round.
세상은 둥글다.
`[ A ]`, we can travel around it.
`[ A ]`(  ), 우리는 그 주위를 여행할 수 있다.
...
"""

# 버튼 클릭 시 실행
if st.button("문제 3개 생성하기 (Click) 🚀"):
    if not api_key:
        st.error("왼쪽 사이드바에 OpenAI API Key를 먼저 넣어주세요!")
    else:
        try:
            client = OpenAI(api_key=api_key)
            
            with st.spinner("AI 선생님이 최신 수능 트렌드 지문을 분석 중입니다... ⏳"):
                response = client.chat.completions.create(
                    model="gpt-4o", # gpt-4o가 비싸면 "gpt-3.5-turbo"로 변경 가능
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": "수능 영어 고난도 빈칸 추론 문제 3개를 생성해줘. 접속사 빈칸 모드로."}
                    ],
                    temperature=0.7 
                )
                
                content = response.choices[0].message.content
                
                # 결과 출력 (메인 화면에는 문제만)
                # 정답을 가리기 위해 텍스트를 분리하는 로직을 쓸 수도 있지만, 
                # 간단하게 전체 내용을 보여주되 정답 부분은 Expander(접는 UI)로 처리해달라고 프롬프트로 제어하거나
                # 여기서는 AI가 준 텍스트를 그대로 뿌리고, 사용자가 스크롤로 조절하게 함.
                # 더 깔끔하게: AI에게 "정답 및 해설"이라는 텍스트를 기준으로 나눠달라고 할 수도 있음.
                
                # 여기서는 심플하게 전체 출력 후, 맨 아래에 정답 확인 버튼처럼 보이게 Expander 사용
                
                if "정답" in content:
                    question_part, answer_part = content.split("정답 및 해설", 1) # '정답 및 해설'을 기준으로 자름
                    st.markdown(question_part)
                    
                    st.write("---")
                    with st.expander("🔍 정답 및 단어 테스트 확인하기 (Click)"):
                        st.markdown("### 정답 및 해설")
                        st.markdown(answer_part)
                else:
                    st.markdown(content)

        except Exception as e:
            st.error(f"에러가 발생했습니다: {e}")