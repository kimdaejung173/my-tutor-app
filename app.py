import streamlit as st
import pandas as pd
import re
import os
import time
from datetime import datetime
from st_click_detector import click_detector

# --- 페이지 설정 ---
st.set_page_config(page_title="영어 숙제", layout="wide")

# --- 스타일 설정 ---
st.markdown("""
<style>
    .st-click-detector a { color: black !important; text-decoration: none !important; border-bottom: 1px solid transparent; transition: background-color 0.1s; }
    .st-click-detector a:hover { background-color: #E3F2FD; border-radius: 3px; color: #1565C0 !important; }
    button.sent-num { background-color: #E8F5E9 !important; color: #2E7D32 !important; border: 1px solid #4CAF50 !important; border-radius: 50%; font-size: 14px; padding: 0 6px; }
    .trans-box { background-color: #FAFAFA; border-left: 4px solid #4CAF50; padding: 10px; margin: 5px 0 15px 0; color: #333; }
    .expl-box { background-color: #E1F5FE; padding: 15px; border-radius: 8px; margin-top: 15px; color: #01579B; }
</style>
""", unsafe_allow_html=True)

# --- 상태 초기화 ---
if 'user_name' not in st.session_state: st.session_state.user_name = ""
if 'step' not in st.session_state: st.session_state.step = "login"
if 'unknown_words' not in st.session_state: st.session_state.unknown_words = set()
if 'viewed_trans' not in st.session_state: st.session_state.viewed_trans = set()
if 'viewed_opt_trans' not in st.session_state: st.session_state.viewed_opt_trans = set()
if 'render_id' not in st.session_state: st.session_state.render_id = 0
if 'homework_log' not in st.session_state: st.session_state.homework_log = []

# --- 데이터 로드 ---
@st.cache_data
def load_data():
    try:
        # data.csv가 있어야 함 (| 구분자)
        df = pd.read_csv("data.csv", sep="|")
        df['id'] = df['id'].astype(str)
        return df
    except Exception as e:
        st.error(f"데이터 파일(data.csv)을 읽을 수 없습니다: {e}")
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

# --- HTML 생성기 ---
def create_html(text, prefix):
    words = text.split()
    html_parts = []
    for idx, word in enumerate(words):
        clean_word = word.strip(".,!?\"'()[]")
        unique_id = f"{prefix}_{idx}_{clean_word}"
        if unique_id in st.session_state.unknown_words:
            style = "background-color: #FFF176; color: black; font-weight: bold; border-radius: 3px; padding: 0 2px;"
        else:
            style = "color: black; text-decoration: none;"
        html_parts.append(f"<a href='javascript:void(0);' id='{unique_id}' style='{style}'>{word}</a>")
    return " ".join(html_parts)

# --- [핵심] 부분 렌더링 함수 (Fragment) ---
@st.fragment
def render_options_fragment(q):
    st.subheader("1️⃣ 보기 (클릭 = 형광펜)")
    try:
        opts = str(q['options']).split("^")
        opt_trans = str(q.get('option_trans', '')).split("^")
    except: opts, opt_trans = [], []

    for i, opt in enumerate(opts):
        c1, c2 = st.columns([0.5, 9.5])
        with c1:
            if st.button(f"({i+1})", key=f"btn_opt_{i}"):
                if i in st.session_state.viewed_opt_trans: st.session_state.viewed_opt_trans.remove(i)
                else: st.session_state.viewed_opt_trans.add(i)
                st.rerun() # Fragment 내부만 리런
        with c2:
            html = create_html(opt, f"opt_{i}")
            # key에 render_id를 포함시켜 클릭 시마다 컴포넌트 갱신
            clicked = click_detector(html, key=f"cd_opt_{i}_{st.session_state.render_id}")
            if clicked:
                if clicked in st.session_state.unknown_words: st.session_state.unknown_words.remove(clicked)
                else: st.session_state.unknown_words.add(clicked)
                st.session_state.render_id += 1
                st.rerun() # Fragment 내부만 리런
            
            if i in st.session_state.viewed_opt_trans:
                ot = opt_trans[i] if i < len(opt_trans) else ""
                st.markdown(f"<div class='trans-box'>└ {ot}</div>", unsafe_allow_html=True)
            else: 
                st.markdown("<div style='margin-bottom:10px'></div>", unsafe_allow_html=True)

@st.fragment
def render_passage_fragment(q):
    st.subheader("2️⃣ 지문 독해")
    sentences = re.split(r'(?<=[.?!])\s+', str(q['passage']))
    translations = re.split(r'(?<=[.?!])\s+', str(q['translation']))
    
    for i, sent in enumerate(sentences):
        if not sent.strip(): continue # 빈 문장 건너뛰기
        c1, c2 = st.columns([0.5, 9.5])
        with c1:
            if st.button(f"({i+1})", key=f"btn_sent_{i}"):
                if i in st.session_state.viewed_trans: st.session_state.viewed_trans.remove(i)
                else: st.session_state.viewed_trans.add(i)
                st.rerun() # Fragment 내부만 리런
        with c2:
            html_s = create_html(sent, f"sent_{i}")
            clicked_s = click_detector(html_s, key=f"cd_sent_{i}_{st.session_state.render_id}")
            if clicked_s:
                if clicked_s in st.session_state.unknown_words: st.session_state.unknown_words.remove(clicked_s)
                else: st.session_state.unknown_words.add(clicked_s)
                st.session_state.render_id += 1
                st.rerun() # Fragment 내부만 리런
            
            if i in st.session_state.viewed_trans:
                t = translations[i] if i < len(translations) else ""
                st.markdown(f"<div class='trans-box'>🇰🇷 {t}</div>", unsafe_allow_html=True)
            else: 
                st.markdown("<div style='margin-bottom:15px'></div>", unsafe_allow_html=True)

# ===================== 메인 화면 =====================

# 1. 로그인 화면
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
            st.info("👆 숙제를 마치고 버튼을 눌러 파일을 저장한 뒤 선생님께 보내주세요.")

    # 2. 문제 뽑기
    if st.session_state.step == "new_question":
        if df.empty:
            st.error("데이터 파일이 없습니다.")
            st.stop()
        st.session_state.current_q = df.sample(1).iloc[0]
        st.session_state.unknown_words = set()
        st.session_state.viewed_trans = set()
        st.session_state.viewed_opt_trans = set()
        st.session_state.render_id = 0
        st.session_state.step = "solving"
        st.rerun()

    q = st.session_state.current_q
    
    st.markdown(f"#### 문제 {q['id']}")
    st.divider()

    # [1] 보기 영역 (Fragment)
    render_options_fragment(q)

    st.divider()

    # [2] 지문 영역 (Fragment)
    render_passage_fragment(q)

    st.divider()

    # [3] 제출 영역
    st.subheader("3️⃣ 정답 선택")
    with st.form("ans_form"):
        try:
            # 보기 텍스트가 복잡할 경우를 대비해 단순화 처리
            raw_opts = str(q['options']).split("^")
            # 라디오 버튼에는 전체 텍스트 표시
            user_choice = st.radio("정답", raw_opts)
            submitted = st.form_submit_button("제출하기", type="primary")
        except:
            st.error("보기를 불러올 수 없습니다.")
            submitted = False

        if submitted and user_choice:
            correct = str(q['answer']).strip()
            # "(1) ..." 형태라고 가정하고 첫 글자나 괄호 안 숫자 파싱
            # 단순히 첫 글자만 비교하는 방식 (유저 코드 유지)
            user_num = user_choice.strip()[1] # (1) 형태면 인덱스 1이 숫자
            if not user_num.isdigit(): user_num = user_choice.strip()[0] # 그냥 숫자만 있으면 0
            
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