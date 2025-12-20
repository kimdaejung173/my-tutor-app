import streamlit as st
import pandas as pd
import re
import os
from datetime import datetime
from st_click_detector import click_detector

# --- 페이지 설정 ---
st.set_page_config(page_title="영어 숙제", layout="wide")

# --- 스타일 설정 ---
st.markdown("""
<style>
    /* 전체 링크 스타일 제거 (파란색, 밑줄 방지) */
    .st-click-detector a {
        color: black !important;
        text-decoration: none !important;
        border-bottom: 1px solid transparent;
        transition: all 0.1s ease-in-out;
    }
    
    /* 단어 마우스 올렸을 때 */
    .st-click-detector a.word:hover {
        background-color: #E3F2FD;
        border-radius: 3px;
        color: #1565C0 !important;
    }
    
    /* 문장 번호 스타일 */
    .st-click-detector a.num {
        display: inline-block;
        background-color: #E8F5E9;
        color: #2E7D32 !important;
        border: 1px solid #4CAF50;
        border-radius: 50%;
        font-size: 13px;
        font-weight: bold;
        padding: 0px 5px;
        margin-right: 6px;
        margin-bottom: 2px;
        vertical-align: middle;
    }
    .st-click-detector a.num:hover {
        background-color: #C8E6C9;
        cursor: pointer;
    }

    /* 해석 박스 (HTML 내부에 삽입될 스타일) */
    .trans-box {
        display: block;
        background-color: #FAFAFA;
        border-left: 4px solid #4CAF50;
        padding: 8px 12px;
        margin: 8px 0 15px 5px;
        color: #333;
        font-size: 0.95rem;
        border-radius: 0 4px 4px 0;
    }
    
    /* 보기 영역 간격 */
    .opt-container { margin-bottom: 12px; }
    
    /* 해설 박스 */
    .expl-box { background-color: #E1F5FE; padding: 15px; border-radius: 8px; margin-top: 15px; color: #01579B; }
</style>
""", unsafe_allow_html=True)

# --- 상태 초기화 ---
if 'user_name' not in st.session_state: st.session_state.user_name = ""
if 'step' not in st.session_state: st.session_state.step = "login"
if 'unknown_words' not in st.session_state: st.session_state.unknown_words = set()
if 'viewed_trans' not in st.session_state: st.session_state.viewed_trans = set()
if 'viewed_opt_trans' not in st.session_state: st.session_state.viewed_opt_trans = set()
if 'homework_log' not in st.session_state: st.session_state.homework_log = [] 

# --- 데이터 로드 ---
@st.cache_data
def load_data():
    try:
        df = pd.read_csv("data.csv", sep="|")
        df['id'] = df['id'].astype(str)
        return df
    except:
        return pd.DataFrame()

df = load_data()

# --- 로그 기록 함수 ---
def add_log(is_correct, user_ans):
    clean_words = []
    for w in st.session_state.unknown_words:
        parts = w.split('_')
        if len(parts) >= 3: clean_words.append("_".join(parts[2:]))
        else: clean_words.append(w)
    
    log_data = {
        "시간": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "이름": st.session_state.user_name,
        "문제번호": str(st.session_state.current_q['id']),
        "결과": "정답" if is_correct else "오답",
        "학생답안": user_ans,
        "모르는단어": ", ".join(sorted(list(set(clean_words))))
    }
    st.session_state.homework_log.append(log_data)

# --- [핵심 1] 통합 HTML 생성기 (지문 전체를 한 덩어리로 만듦) ---
def create_combined_html(text_list, trans_list, type="passage", viewed_set=None):
    html_parts = []
    
    for i, text in enumerate(text_list):
        # 1. 문장/보기 번호 (클릭 가능한 링크로 만듦)
        # ID 형식: trans_0 (0번 문장 해석 토글)
        num_id = f"trans_{i}"
        html_parts.append(f"<div class='opt-container'>") # 줄바꿈 컨테이너
        html_parts.append(f"<a href='javascript:void(0);' id='{num_id}' class='num'>({i+1})</a>")
        
        # 2. 단어들 (형광펜 기능)
        words = text.split()
        for idx, word in enumerate(words):
            clean_word = word.strip(".,!?\"'()[]")
            # ID 형식: word_0_12_apple (0번 문장, 12번째 단어, apple)
            unique_id = f"word_{i}_{idx}_{clean_word}"
            
            # 형광펜 스타일 적용
            if unique_id in st.session_state.unknown_words:
                style = "background-color: #FFF176; color: black; font-weight: bold; border-radius: 3px; padding: 0 2px;"
            else:
                style = ""
            
            html_parts.append(f"<a href='javascript:void(0);' id='{unique_id}' class='word' style='{style}'>{word}</a>")
        
        # 3. 해석 박스 (켜져 있으면 HTML 사이에 끼워넣기)
        if i in viewed_set:
            t = trans_list[i] if i < len(trans_list) else ""
            # 줄바꿈 후 박스 생성
            html_parts.append(f"<div class='trans-box'>🇰🇷 {t}</div>")
            
        html_parts.append("</div>") # div 닫기 (줄바꿈 효과)
        
    return " ".join(html_parts)

# --- [핵심 2] 부분 리모델링 적용 (@st.fragment) ---
# 이 함수 안에서 일어나는 일은 전체 화면을 새로고침하지 않음!
@st.fragment
def render_passage_area(q):
    st.subheader("2️⃣ 지문 독해")
    
    sentences = re.split(r'(?<=[.?!])\s+', str(q['passage']))
    translations = re.split(r'(?<=[.?!])\s+', str(q['translation']))
    
    # 지문 전체를 HTML 한 덩어리로 생성
    full_html = create_combined_html(sentences, translations, "passage", st.session_state.viewed_trans)
    
    # 감지기 1개로 전체 통제 (로딩 1번만 함)
    clicked = click_detector(full_html, key="passage_detector")
    
    if clicked:
        # 클릭된 ID 분석 (trans_... 인지 word_... 인지)
        if clicked.startswith("trans_"):
            # 해석 번호를 누른 경우
            idx = int(clicked.split("_")[1])
            if idx in st.session_state.viewed_trans:
                st.session_state.viewed_trans.remove(idx)
            else:
                st.session_state.viewed_trans.add(idx)
            st.rerun() # 프래그먼트 내부만 리런
            
        elif clicked.startswith("word_"):
            # 단어를 누른 경우
            if clicked in st.session_state.unknown_words:
                st.session_state.unknown_words.remove(clicked)
            else:
                st.session_state.unknown_words.add(clicked)
            st.rerun() # 프래그먼트 내부만 리런

@st.fragment
def render_options_area(q):
    st.subheader("1️⃣ 보기 (클릭 = 형광펜)")
    try:
        opts = str(q['options']).split("^")
        opt_trans = str(q.get('option_trans', '')).split("^")
    except: opts, opt_trans = [], []
    
    # 보기 전체를 HTML 한 덩어리로 생성
    full_html = create_combined_html(opts, opt_trans, "option", st.session_state.viewed_opt_trans)
    
    clicked = click_detector(full_html, key="option_detector")
    
    if clicked:
        if clicked.startswith("trans_"):
            idx = int(clicked.split("_")[1])
            if idx in st.session_state.viewed_opt_trans:
                st.session_state.viewed_opt_trans.remove(idx)
            else:
                st.session_state.viewed_opt_trans.add(idx)
            st.rerun()
            
        elif clicked.startswith("word_"):
            if clicked in st.session_state.unknown_words:
                st.session_state.unknown_words.remove(clicked)
            else:
                st.session_state.unknown_words.add(clicked)
            st.rerun()

# ===================== 메인 화면 =====================

if not st.session_state.user_name:
    st.title("📝 영어 숙제장")
    st.write("이름을 입력하고 숙제를 시작하세요.")
    name = st.text_input("이름")
    if st.button("숙제 시작하기", type="primary"):
        if name:
            st.session_state.user_name = name
            st.session_state.step = "new_question"
            st.rerun()

else:
    # 사이드바
    with st.sidebar:
        st.write(f"👤 **{st.session_state.user_name}** 학생")
        st.write(f"푼 문제: {len(st.session_state.homework_log)}개")
        if st.session_state.homework_log:
            st.divider()
            log_df = pd.DataFrame(st.session_state.homework_log)
            csv_data = log_df.to_csv(index=False).encode('utf-8-sig')
            st.download_button(
                label="📥 결과 파일 다운로드",
                data=csv_data,
                file_name=f"{st.session_state.user_name}_숙제결과.csv",
                mime="text/csv",
                type="primary"
            )

    # 문제 뽑기
    if st.session_state.step == "new_question":
        if df.empty:
            st.error("데이터 파일이 없습니다.")
            st.stop()
        st.session_state.current_q = df.sample(1).iloc[0]
        st.session_state.unknown_words = set()
        st.session_state.viewed_trans = set()
        st.session_state.viewed_opt_trans = set()
        st.session_state.step = "solving"
        st.rerun()

    q = st.session_state.current_q
    
    st.markdown(f"#### 문제 {q['id']}")
    st.divider()

    # [1] 보기 영역 (프래그먼트 적용)
    render_options_area(q)
    
    st.divider()

    # [2] 지문 영역 (프래그먼트 적용)
    render_passage_area(q)

    st.divider()

    # [3] 제출 영역
    st.subheader("3️⃣ 정답 선택")
    with st.form("ans_form"):
        try:
            opts = str(q['options']).split("^")
        except: opts = []
        user_choice = st.radio("정답", opts)
        submitted = st.form_submit_button("제출하기", type="primary")
        
        if submitted and user_choice:
            correct = str(q['answer']).strip()
            user_num = user_choice.strip()[0]
            is_correct = (user_num == correct)
            
            add_log(is_correct, user_num)
            
            if is_correct:
                st.success("🎉 정답입니다!")
                st.balloons()
            else:
                st.error(f"💥 틀렸습니다. 정답은 {correct}번 입니다.")
            
            expl = q.get('explanation', '')
            st.markdown(f"<div class='expl-box'><b>💡 [해설]</b><br>{expl}</div>", unsafe_allow_html=True)
            
            st.session_state.step = "next"

    if st.session_state.step == "next":
        if st.button("➡️ 다음 문제 (자동 저장됨)"):
            st.session_state.step = "new_question"
            st.rerun()