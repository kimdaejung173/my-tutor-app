import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import json
import os
import re
from datetime import datetime

# --- 페이지 설정 ---
st.set_page_config(page_title="영어 숙제", layout="wide")

# --- 상태 초기화 ---
if 'user_name' not in st.session_state: st.session_state.user_name = ""
if 'step' not in st.session_state: st.session_state.step = "login"
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
def add_log(q_id, is_correct, user_ans, unknown_words):
    log_data = {
        "시간": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "이름": st.session_state.user_name,
        "문제번호": str(q_id),
        "결과": "정답" if is_correct else "오답",
        "학생답안": user_ans,
        "모르는단어": unknown_words
    }
    st.session_state.homework_log.append(log_data)

# --- [핵심] 자바스크립트 기반 UI 생성기 ---
# 파이썬은 HTML만 던져주고, 색칠 놀이는 브라우저(JS)가 알아서 하게 둠
def render_interactive_problem(q):
    # 1. 데이터 준비 (따옴표 에러 방지용 처리)
    passage = str(q['passage']).replace('"', '&quot;').replace("'", "&#39;")
    translation = str(q['translation']).replace('"', '&quot;').replace("'", "&#39;")
    options_raw = str(q['options']).split('^')
    options_trans_raw = str(q.get('option_trans', '')).split('^')
    
    # 보기 데이터 JSON 변환
    opts_data = []
    for i, opt in enumerate(options_raw):
        trans = options_trans_raw[i] if i < len(options_trans_raw) else ""
        opts_data.append({"text": opt.strip(), "trans": trans.strip()})
    
    opts_json = json.dumps(opts_data).replace('"', '&quot;')

    # 2. HTML/JS/CSS 코드 덩어리
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            body {{ font-family: "Helvetica Neue", Arial, sans-serif; padding: 10px; }}
            .word {{ cursor: pointer; padding: 0 2px; border-radius: 3px; transition: background 0.1s; }}
            .word:hover {{ background-color: #E3F2FD; color: #1565C0; }}
            .highlight {{ background-color: #FFF176 !important; color: black !important; font-weight: bold; }}
            
            .section-title {{ font-size: 1.1em; font-weight: bold; margin-top: 20px; margin-bottom: 10px; color: #333; }}
            
            /* 보기 스타일 */
            .opt-row {{ display: flex; margin-bottom: 8px; align-items: baseline; }}
            .opt-num {{ 
                background: #E8F5E9; color: #2E7D32; border: 1px solid #4CAF50; 
                border-radius: 50%; width: 24px; height: 24px; text-align: center; 
                line-height: 22px; font-size: 13px; font-weight: bold; cursor: pointer; margin-right: 10px; flex-shrink: 0;
            }}
            .opt-text {{ line-height: 1.6; }}
            
            /* 지문 스타일 */
            .sent-row {{ margin-bottom: 15px; }}
            .sent-num {{ 
                display: inline-block; background: #E8F5E9; color: #2E7D32; border: 1px solid #4CAF50; 
                border-radius: 50%; font-size: 12px; padding: 1px 6px; margin-right: 5px; cursor: pointer; vertical-align: middle;
            }}
            
            /* 해석 박스 */
            .trans-box {{ 
                display: none; background: #FAFAFA; border-left: 4px solid #4CAF50; 
                padding: 8px; margin-top: 5px; color: #333; font-size: 0.9em; 
            }}
            .show {{ display: block; }}
            
            /* 정답 선택 라디오 */
            .radio-group {{ margin-top: 20px; background: #f9f9f9; padding: 15px; border-radius: 8px; }}
            .radio-label {{ display: block; margin: 10px 0; cursor: pointer; }}
            
            /* 제출 버튼 */
            #submit-btn {{
                background-color: #FF4B4B; color: white; border: none; padding: 10px 20px;
                border-radius: 5px; font-size: 16px; font-weight: bold; cursor: pointer; width: 100%; margin-top: 20px;
            }}
            #submit-btn:hover {{ background-color: #FF3333; }}
        </style>
    </head>
    <body>
    
        <div class="section-title">1️⃣ 보기 (클릭 = 형광펜)</div>
        <div id="options-area"></div>

        <div class="section-title">2️⃣ 지문 독해 (번호 = 해석)</div>
        <div id="passage-area"></div>

        <div class="section-title">3️⃣ 정답 선택</div>
        <div class="radio-group">
            <label class="radio-label"><input type="radio" name="ans" value="1"> 1번</label>
            <label class="radio-label"><input type="radio" name="ans" value="2"> 2번</label>
            <label class="radio-label"><input type="radio" name="ans" value="3"> 3번</label>
            <label class="radio-label"><input type="radio" name="ans" value="4"> 4번</label>
            <label class="radio-label"><input type="radio" name="ans" value="5"> 5번</label>
        </div>

        <button id="submit-btn" onclick="submitData()">제출하기</button>

        <script>
            // 데이터 파싱
            const passageRaw = "{passage}";
            const transRaw = "{translation}";
            const optsData = JSON.parse("{opts_json}");

            // --- 렌더링 함수들 ---
            
            function createWordSpan(word) {{
                const span = document.createElement('span');
                span.innerText = word + " ";
                span.className = 'word';
                // 단어 클릭 시 형광펜 토글 (자바스크립트로 즉시 처리 -> 딜레이 0초)
                span.onclick = function() {{ this.classList.toggle('highlight'); }};
                return span;
            }}

            // 1. 보기 렌더링
            const optContainer = document.getElementById('options-area');
            optsData.forEach((opt, idx) => {{
                const row = document.createElement('div');
                row.className = 'opt-row';
                
                // 번호 버튼
                const numBtn = document.createElement('div');
                numBtn.className = 'opt-num';
                numBtn.innerText = "(" + (idx + 1) + ")";
                numBtn.onclick = function() {{ document.getElementById('opt-trans-' + idx).classList.toggle('show'); }};
                
                // 텍스트 & 해석
                const textDiv = document.createElement('div');
                textDiv.className = 'opt-text';
                
                // 단어 쪼개기
                opt.text.split(' ').forEach(w => textDiv.appendChild(createWordSpan(w)));
                
                // 해석 박스
                const transDiv = document.createElement('div');
                transDiv.id = 'opt-trans-' + idx;
                transDiv.className = 'trans-box';
                transDiv.innerText = "└ " + opt.trans;
                
                textDiv.appendChild(transDiv);
                row.appendChild(numBtn);
                row.appendChild(textDiv);
                optContainer.appendChild(row);
            }});

            // 2. 지문 렌더링
            const psgContainer = document.getElementById('passage-area');
            // 문장 단위 분리 (정규식)
            const sentences = passageRaw.split(/(?<=[.?!])\s+/);
            const translations = transRaw.split(/(?<=[.?!])\s+/);
            
            sentences.forEach((sent, idx) => {{
                const row = document.createElement('div');
                row.className = 'sent-row';
                
                // 문장 번호
                const sNum = document.createElement('span');
                sNum.className = 'sent-num';
                sNum.innerText = "(" + (idx + 1) + ")";
                sNum.onclick = function() {{ document.getElementById('sent-trans-' + idx).classList.toggle('show'); }};
                row.appendChild(sNum);
                
                // 단어들
                sent.split(' ').forEach(w => row.appendChild(createWordSpan(w)));
                
                // 해석 박스
                const tBox = document.createElement('div');
                tBox.id = 'sent-trans-' + idx;
                tBox.className = 'trans-box';
                tBox.innerText = "🇰🇷 " + (translations[idx] || "");
                row.appendChild(tBox);
                
                psgContainer.appendChild(row);
            }});

            // --- 제출 함수 ---
            function submitData() {{
                // 1. 정답 가져오기
                const radios = document.getElementsByName('ans');
                let userAns = "";
                for (let r of radios) {{ if (r.checked) userAns = r.value; }}
                
                if (!userAns) {{ alert("정답을 선택해주세요!"); return; }}
                
                // 2. 형광펜 칠한 단어 수집
                const highlights = document.querySelectorAll('.highlight');
                const words = [];
                highlights.forEach(el => words.push(el.innerText.trim()));
                const uniqueWords = [...new Set(words)].join(', ');

                // 3. 데이터 포장해서 파이썬(Streamlit)으로 전송 (URL 파라미터 방식)
                // 현재 페이지를 다시 로드하면서 쿼리 파라미터를 붙임
                const params = new URLSearchParams();
                params.set('submitted', 'true');
                params.set('ans', userAns);
                params.set('words', uniqueWords);
                
                // 상위 프레임(Streamlit 앱) 새로고침
                window.top.location.search = params.toString();
            }}
        </script>
    </body>
    </html>
    """
    # 3. Streamlit에 iframe으로 쏴주기
    components.html(html_code, height=900, scrolling=True)

# ===================== 메인 화면 로직 =====================

# 1. 로그인
if not st.session_state.user_name:
    st.title("📝 영어 숙제장")
    name = st.text_input("이름을 입력하세요")
    if st.button("시작하기", type="primary"):
        if name:
            st.session_state.user_name = name
            st.session_state.step = "new_question"
            st.rerun()
else:
    # 2. 결과 처리 (URL에 제출 데이터가 있는지 확인)
    # Streamlit 1.30+ 기준: st.query_params 사용
    params = st.query_params 
    
    if "submitted" in params:
        # 제출된 상태면 결과 화면 표시
        if df.empty: df = load_data() # 새로고침으로 데이터 날아갔을 경우 대비
        
        # 문제 ID 복구 (가장 최근 문제거나, URL에 저장해야 하지만 간단히 마지막 문제로 가정)
        # *주의* 새로고침하면 current_q가 날아갈 수 있으므로, 실제로는 문제 ID도 URL에 넘기는 게 안전함
        # 여기선 간단히 처리
        if 'current_q' not in st.session_state:
             # 비상시: 데이터 다시 로드
             if not df.empty: st.session_state.current_q = df.iloc[0]

        q = st.session_state.current_q
        user_ans = params.get("ans", "X")
        unknown_words = params.get("words", "")
        
        correct = str(q['answer']).strip()
        is_correct = (user_ans == correct)
        
        # 로그 저장
        add_log(q['id'], is_correct, user_ans, unknown_words)
        
        st.title("결과 확인")
        if is_correct:
            st.success("🎉 정답입니다!")
            st.balloons()
        else:
            st.error(f"💥 틀렸습니다. (정답: {correct}번, 내 답: {user_ans}번)")
            
        st.info(f"💡 [해설] {q.get('explanation', '해설 없음')}")
        st.write(f"📝 **내가 체크한 단어:** {unknown_words}")
        
        # 다음 문제 버튼 (누르면 URL 파라미터 싹 지우고 새 문제)
        if st.button("➡️ 다음 문제 풀기", type="primary"):
            st.query_params.clear() # URL 깨끗하게
            st.session_state.step = "new_question"
            st.rerun()
            
    else:
        # 3. 문제 풀기 화면 (평소 상태)
        
        # 사이드바 (결과 다운로드)
        with st.sidebar:
            st.write(f"👤 **{st.session_state.user_name}**")
            st.write(f"완료: {len(st.session_state.homework_log)}문제")
            if st.session_state.homework_log:
                log_df = pd.DataFrame(st.session_state.homework_log)
                csv = log_df.to_csv(index=False).encode('utf-8-sig')
                st.download_button("📥 결과 다운로드", csv, f"{st.session_state.user_name}_결과.csv", "text/csv")

        # 새 문제 뽑기
        if st.session_state.step == "new_question":
            if df.empty: st.error("데이터 없음"); st.stop()
            st.session_state.current_q = df.sample(1).iloc[0]
            st.session_state.step = "solving"
        
        q = st.session_state.current_q
        
        st.markdown(f"#### 문제 {q['id']}")
        
        # [핵심] HTML/JS 컴포넌트 렌더링
        render_interactive_problem(q)