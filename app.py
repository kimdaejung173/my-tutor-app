import streamlit as st
import pandas as pd
import random
import re
import io
import time
from datetime import datetime

# --- 페이지 설정 ---
st.set_page_config(page_title="영어 독해 트레이닝", layout="wide")

# --- CSS 스타일: 버튼을 '진짜 글자'처럼 만들기 (가독성 혁명) ---
st.markdown("""
<style>
    /* 버튼의 네모 테두리, 배경 제거하고 글자처럼 만들기 */
    .stButton button {
        background-color: transparent !important;
        border: none !important;
        padding: 0px 3px !important;
        margin: 0px !important;
        color: black !important;
        font-size: 18px !important;
        line-height: 1.8 !important;
        display: inline-block !important;
        text-align: left !important;
        font-family: "Noto Sans KR", sans-serif !important;
    }
    .stButton button:hover {
        color: #2962FF !important;
        background-color: #E3F2FD !important;
        border-radius: 4px !important;
    }
    .stButton {
        display: inline-block !important;
        margin-right: -4px !important; /* 버튼 사이 간격 좁히기 */
    }
    
    /* 선택된 단어 (노란 형광펜) */
    .word-selected button {
        background-color: #FFF176 !important;
        font-weight: bold !important;
        border-radius: 4px !important;
        color: black !important;
    }
    
    /* 보기 박스 스타일 */
    .option-box {
        padding: 15px;
        background-color: #F8F9FA;
        border-radius: 10px;
        margin-bottom: 10px;
        border: 1px solid #E0E0E0;
    }
</style>
""", unsafe_allow_html=True)

# --- 상태 초기화 ---
if 'step' not in st.session_state: st.session_state.step = "login"
if 'user_name' not in st.session_state: st.session_state.user_name = ""
if 'current_q' not in st.session_state: st.session_state.current_q = None
if 'unknown_words' not in st.session_state: st.session_state.unknown_words = set()
if 'hint_used' not in st.session_state: st.session_state.hint_used = False
if 'hint_locked' not in st.session_state: st.session_state.hint_locked = False # 해석 보기 영구 박제

# --- 데이터 로드 함수 (오류 방지) ---
@st.cache_data
def load_data():
    try:
        # 구분자를 '|'로 지정
        df = pd.read_csv("data.csv", sep="|")
        # 보기(options) 분리할 때 기존 | 와 충돌 방지를 위해 ^ 기호 사용 권장
        return df
    except:
        return pd.DataFrame()

# --- 구글 시트 저장 함수 (핵심) ---
def save_to_google_sheet(data_row):
    """
    구글 시트에 데이터를 저장합니다.
    설정이 안 되어 있으면 로컬 CSV에 저장합니다.
    """
    try:
        # streamlit_google_sheets 라이브러리가 필요함 (requirements.txt에 추가)
        conn = st.connection("gsheets", type="gsheets")
        # 기존 데이터 읽기
        existing_data = conn.read(worksheet="Logs", usecols=list(range(6)), ttl=5)
        
        # 새 데이터 추가
        updated_data = pd.concat([existing_data, pd.DataFrame([data_row])], ignore_index=True)
        
        # 업데이트 (이 부분이 실제로 시트에 씀)
        conn.update(worksheet="Logs", data=updated_data)
        st.toast("☁️ 구글 시트에 저장 성공!", icon="✅")
        
    except Exception as e:
        # 구글 시트 연결 실패 시 로컬 파일에 저장 (백업)
        st.toast(f"⚠️ 구글 시트 연동 안됨. 로컬에 저장합니다.", icon="💾")
        local_log = "student_logs.csv"
        try:
            old_df = pd.read_csv(local_log)
            new_df = pd.concat([old_df, pd.DataFrame([data_row])])
        except:
            new_df = pd.DataFrame([data_row])
        new_df.to_csv(local_log, index=False, encoding='utf-8-sig')

# --- 단어 클릭 토글 함수 ---
def toggle_word(word):
    clean = word.strip(".,!?;:\"'")
    if clean in st.session_state.unknown_words:
        st.session_state.unknown_words.remove(clean)
    else:
        st.session_state.unknown_words.add(clean)

# ================= 메인 로직 =================

df = load_data()

# 1. 로그인 화면
if st.session_state.step == "login":
    st.title("🔐 Student Login")
    name = st.text_input("이름을 입력하세요")
    
    if st.button("학습 시작하기", type="primary"):
        if name and not df.empty:
            st.session_state.user_name = name
            
            # --- 랜덤 문제 뽑기 로직 ---
            # 나중에는 구글 시트에서 '이 학생이 푼 문제 ID'를 가져와서 빼야 함
            # 지금은 단순히 랜덤으로 하나 뽑음
            random_idx = random.randint(0, len(df) - 1)
            st.session_state.current_q = df.iloc[random_idx]
            
            # 상태 초기화
            st.session_state.unknown_words = set()
            st.session_state.hint_used = False
            st.session_state.hint_locked = False
            
            st.session_state.step = "step1_options"
            st.rerun()
        elif df.empty:
            st.error("데이터 파일(data.csv)이 없습니다! 선생님에게 문의하세요.")

# 2. Step 1: 보기 먼저 보기
elif st.session_state.step == "step1_options":
    q = st.session_state.current_q
    st.subheader(f"Step 1. 보기를 먼저 읽고 내용을 예측해보세요 ({st.session_state.user_name})")
    
    # 보기 출력 (구분자를 ^로 가정)
    try:
        options = q['options'].split("^") 
    except:
        options = ["데이터 형식 오류: 보기를 ^ 기호로 구분해주세요"]

    for opt in options:
        st.markdown(f"<div class='option-box'>{opt}</div>", unsafe_allow_html=True)
    
    st.write("")
    if st.button("지문 읽으러 가기 (Next) ➡️", type="primary"):
        st.session_state.step = "step2_passage"
        st.rerun()

# 3. Step 2: 지문 읽기 (자연스러운 텍스트 버전)
elif st.session_state.step == "step2_passage":
    q = st.session_state.current_q
    st.subheader("Step 2. 지문을 읽고 모르는 단어를 클릭하세요")
    
    # 지문을 단어 단위로 쪼개기
    # 정규표현식으로 단어와 공백/특수문자를 분리해서 보존
    tokens = re.findall(r"[\w']+|[.,!?;:\"]|\s", q['passage'])
    
    # --- [매우 중요] 단어를 '줄글'처럼 보이게 하는 레이아웃 ---
    # Streamlit의 columns 대신 HTML/CSS flow를 흉내내기 위해
    # 화면 가로폭에 맞춰 버튼을 나열하는 건 불가능하므로, 
    # 'experimental_fragment'와 커스텀 CSS를 활용해 버튼을 inline으로 배치
    
    with st.container():
        # 문단을 흉내내기 위해 버튼들을 쭉 나열
        for idx, token in enumerate(tokens):
            if token.strip() == "": 
                continue # 공백은 무시 (버튼 사이 마진으로 대체되거나 별도 처리)
            
            clean_word = token.strip(".,!?;:\"'")
            is_sel = clean_word in st.session_state.unknown_words
            
            # CSS 클래스를 동적으로 적용하기 위해 빈 컨테이너 사용 불가 -> 버튼 자체 스타일링
            # 버튼이 눌리면 바로 리런됨
            btn_key = f"word_{idx}_{clean_word}"
            
            # 선택된 단어인지 확인하여 스타일 적용할 방법이 제한적임.
            # 따라서 버튼 텍스트 자체에 표시를 하거나(비추), 
            # 위 CSS에서 .stButton button 상태를 제어해야 함.
            # 여기서는 Streamlit 제약상 'type="primary"'를 사용하여 색상 구분
            
            if st.button(token, key=btn_key, type="primary" if is_sel else "secondary"):
                toggle_word(token)
                st.rerun()

    st.divider()
    
    # 해석 보기 (낙장불입)
    col1, col2 = st.columns([1, 4])
    if not st.session_state.hint_locked:
        if col1.button("👁️ 전체 해석 보기 (한번만 가능)"):
            st.session_state.hint_locked = True
            st.session_state.hint_used = True
            st.rerun()
    else:
        col1.warning("해석을 확인했습니다. (기록됨)")
        st.info(q['translation'])

    st.divider()
    
    # 정답 제출
    st.subheader("Q. 정답을 선택하세요")
    # 보기 다시 가져오기
    try:
        options = q['options'].split("^")
    except:
        options = ["보기 데이터 오류"]
        
    choice = st.radio("선택지", options, label_visibility="collapsed")
    
    if st.button("제출하기 📤", type="primary"):
        # 정답 체크 로직 (데이터에 정답란이 숫자 1,2,3... 이라고 가정)
        # 보기에 "1. 어쩌구" 처럼 숫자가 있다고 가정하고 첫 글자 비교
        user_ans_num = choice.strip()[0] 
        correct_ans = str(q['answer']).strip()
        
        is_correct = (user_ans_num == correct_ans)
        
        # 데이터 저장
        log_data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "name": st.session_state.user_name,
            "problem_id": q['id'],
            "is_correct": "O" if is_correct else "X",
            "hint_used": "Used" if st.session_state.hint_used else "No",
            "unknown_words": ", ".join(st.session_state.unknown_words)
        }
        
        save_to_google_sheet(log_data)
        
        st.session_state.last_result = is_correct
        st.session_state.step = "result"
        st.rerun()

# 4. 결과 화면
elif st.session_state.step == "result":
    if st.session_state.last_result:
        st.success("🎉 정답입니다!")
        st.balloons()
    else:
        st.error("앗, 틀렸습니다. 다시 복습해보세요.")
        
    if st.button("다음 문제 풀기 ➡️"):
        st.session_state.step = "login" # 다시 로그인 화면(혹은 대시보드)으로
        st.rerun()