import streamlit as st
import pandas as pd
import re
import os
from datetime import datetime
from st_click_detector import click_detector

# --- 페이지 설정 ---
st.set_page_config(page_title="수능 영어 1등급", layout="wide")

# --- [스타일] 파란 글씨 차단 & 가독성 최적화 ---
st.markdown("""
<style>
    /* 1. 링크 스타일 원천 차단 */
    .st-click-detector a {
        color: black !important;
        text-decoration: none !important;
        border-bottom: 1px solid transparent;
        transition: background-color 0.1s;
    }
    
    /* 2. 마우스 올렸을 때 */
    .st-click-detector a:hover {
        background-color: #E3F2FD;
        border-radius: 3px;
        color: #1565C0 !important;
    }

    /* 3. 문장 번호 버튼 */
    button.sent-num {
        background-color: #E8F5E9 !important;
        color: #2E7D32 !important;
        border: 1px solid #4CAF50 !important;
        border-radius: 50% !important;
        font-size: 14px !important;
        padding: 0px 6px !important;
    }

    /* 4. 해석 박스 */
    .trans-box {
        background-color: #FAFAFA;
        border-left: 4px solid #4CAF50;
        padding: 10px;
        margin: 5px 0 15px 0;
        color: #333;
    }
    
    /* 5. 해설 박스 */
    .expl-box {
        background-color: #E1F5FE;
        padding: 15px;
        border-radius: 8px;
        margin-top: 15px;
        color: #01579B;
    }
</style>
""", unsafe_allow_html=True)

# --- 상태 초기화 ---
if 'user_name' not in st.session_state: st.session_state.user_name = ""
if 'step' not in st.session_state: st.session_state.step = "login"
if 'unknown_words' not in st.session_state: st.session_state.unknown_words = set()
if 'viewed_trans' not in st.session_state: st.session_state.viewed_trans = set()
if 'viewed_opt_trans' not in st.session_state: st.session_state.viewed_opt_trans = set()

# [핵심] 무한 루프 방지용 번호표 (클릭할 때마다 숫자가 바뀜 -> 새 감지기로 인식)
if 'render_id' not in st.session_state: st.session_state.render_id = 0

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

# --- 로그 저장 함수 ---
def save_log(is_correct, user_ans):
    clean_words = []
    for w in st.session_state.unknown_words:
        parts = w.split('_')
        if len(parts) >= 3: clean_words.append("_".join(parts[2:]))
        else: clean_words.append(w)
    
    words_str = ", ".join(sorted(list(set(clean_words))))
    sent_viewed = ", ".join(sorted([str(i+1) for i in st.session_state.viewed_trans]))
    opt_viewed = ", ".join(sorted([str(i+1) for i in st.session_state.viewed_opt_trans]))

    log_data = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "name": st.session_state.user_name,
        "problem_id": str(st.session_state.current_q['id']),
        "is_correct": "O" if is_correct else "X",
        "user_answer": user_ans,
        "viewed_sentences": sent_viewed if sent_viewed else "None",
        "viewed_options": opt_viewed if opt_viewed else "None",
        "unknown_words": words_str
    }
    
    # 로컬 저장
    local_file = "student_logs.csv"
    try:
        if os.path.exists(local_file):
            pd.DataFrame([log_data]).to_csv(local_file, mode='a', header=False, index=False, encoding='utf-8-sig')
        else:
            pd.DataFrame([log_data]).to_csv(local_file, index=False, encoding='utf-8-sig')
    except: pass

    # 구글 시트 저장
    try:
        conn = st.connection("gsheets", type="gsheets")
        try:
            old = conn.read(worksheet="Logs", ttl=0)
            new = pd.concat([old, pd.DataFrame([log_data])], ignore_index=True)
        except:
            new = pd.DataFrame([log_data])
        conn.update(worksheet="Logs", data=new)
        st.toast("✅ 저장 완료!", icon="Cloud")
    except:
        st.toast(f"💾 로컬 저장 완료", icon="✅")

# --- HTML 생성기 ---
def create_html(text, prefix):
    words = text.split()
    html_parts = []
    
    for idx, word in enumerate(words):
        clean_word = word.strip(".,!?\"'()[]")
        unique_id = f"{prefix}_{idx}_{clean_word}"
        
        # 형광펜 스타일 (CSS 강제 주입)
        if unique_id in st.session_state.unknown_words:
            style = "background-color: #FFF176; color: black; font-weight: bold; border-radius: 3px; padding: 0 2px;"
        else:
            style = "color: black; text-decoration: none;"
            
        # javascript:void(0)로 점프 방지
        html_parts.append(f"<a href='javascript:void(0);' id='{unique_id}' style='{style}'>{word}</a>")
    
    return " ".join(html_parts)

# ===================== 메인 화면 =====================

if not st.session_state.user_name:
    st.title("🎓 수능 영어 독해")
    name = st.text_input("이름")
    if st.button("시작하기", type="primary"):
        if name:
            st.session_state.user_name = name
            st.session_state.step = "new_question"
            st.rerun()

else:
    # 새 문제 뽑기
    if st.session_state.step == "new_question":
        if df.empty:
            st.error("데이터 파일(data.csv)이 없습니다.")
            st.stop()
        st.session_state.current_q = df.sample(1).iloc[0]
        st.session_state.unknown_words = set()
        st.session_state.viewed_trans = set()
        st.session_state.viewed_opt_trans = set()
        st.session_state.render_id = 0 # 새 문제니까 ID 리셋
        st.session_state.step = "solving"
        st.rerun()

    q = st.session_state.current_q
    
    st.markdown(f"#### 👤 {st.session_state.user_name} | 문제 {q['id']}")
    st.divider()

    # [1] 보기 영역
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
        
        with c2:
            html = create_html(opt, f"opt_{i}")
            # [핵심] key에 render_id를 붙여서 클릭할 때마다 '새 컴포넌트'로 인식시킴 -> 루프 차단
            clicked = click_detector(html, key=f"cd_opt_{i}_{st.session_state.render_id}")
            
            if clicked:
                if clicked in st.session_state.unknown_words:
                    st.session_state.unknown_words.remove(clicked)
                else:
                    st.session_state.unknown_words.add(clicked)
                
                # 클릭했으니 판을 새로 깝니다 (ID 증가)
                st.session_state.render_id += 1 
                st.rerun()

            if i in st.session_state.viewed_opt_trans:
                ot = opt_trans[i] if i < len(opt_trans) else ""
                st.markdown(f"<div class='trans-box'>└ {ot}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='margin-bottom:10px'></div>", unsafe_allow_html=True)

    st.divider()

    # [2] 지문 영역
    st.subheader("2️⃣ 지문 독해 (번호 = 해석)")
    
    sentences = re.split(r'(?<=[.?!])\s+', str(q['passage']))
    translations = re.split(r'(?<=[.?!])\s+', str(q['translation']))
    
    for i, sent in enumerate(sentences):
        c1, c2 = st.columns([0.5, 9.5])
        
        with c1:
            if st.button(f"({i+1})", key=f"btn_sent_{i}"):
                if i in st.session_state.viewed_trans: st.session_state.viewed_trans.remove(i)
                else: st.session_state.viewed_trans.add(i)
        
        with c2:
            html_s = create_html(sent, f"sent_{i}")
            # 여기도 render_id 적용!
            clicked_s = click_detector(html_s, key=f"cd_sent_{i}_{st.session_state.render_id}")
            
            if clicked_s:
                if clicked_s in st.session_state.unknown_words:
                    st.session_state.unknown_words.remove(clicked_s)
                else:
                    st.session_state.unknown_words.add(clicked_s)
                
                # 클릭 처리 후 ID 증가 및 리런
                st.session_state.render_id += 1
                st.rerun()
            
            if i in st.session_state.viewed_trans:
                t = translations[i] if i < len(translations) else ""
                st.markdown(f"<div class='trans-box'>🇰🇷 {t}</div>", unsafe_allow_html=True)
            else:
                st.markdown("<div style='margin-bottom:15px'></div>", unsafe_allow_html=True)

    st.divider()

    # [3] 제출
    st.subheader("3️⃣ 정답 선택")
    with st.form("ans_form"):
        user_choice = st.radio("정답", opts)
        submitted = st.form_submit_button("제출하기", type="primary")
        
        if submitted and user_choice:
            correct = str(q['answer']).strip()
            user_num = user_choice.strip()[0]
            is_correct = (user_num == correct)
            
            save_log(is_correct, user_num)
            
            if is_correct:
                st.success("🎉 정답입니다!")
                st.balloons()
            else:
                st.error(f"💥 틀렸습니다. 정답은 {correct}번 입니다.")
            
            expl = q.get('explanation', '')
            st.markdown(f"<div class='expl-box'><b>💡 [해설]</b><br>{expl}</div>", unsafe_allow_html=True)
            
            st.session_state.step = "next"

    if st.session_state.step == "next":
        if st.button("➡️ 다음 문제"):
            st.session_state.step = "new_question"
            st.rerun()