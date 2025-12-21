from nicegui import ui, app
import pandas as pd
import re
from datetime import datetime
import io
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import streamlit as st
import json

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

# 1. 서버 금고(Secrets)에서 'google_key'라고 저장한 내용을 가져옴
key_dict = json.loads(st.secrets["google_key"])

# 2. 파일 이름 대신, 가져온 내용(key_dict)으로 인증함
creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)

# ===================== [1] 설정 및 데이터 로드 =====================

# [중요] 여기에 구글 스프레드시트 주소 중간에 있는 ID를 복사해서 넣으세요.
SPREADSHEET_KEY = "1Gtz2LYGjl9uGwbfsNc_NJJdgu68KybQYcep1ncQHCmU" 

# 구글 시트 인증 함수
def get_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    # 서비스 계정 키 파일이 같은 폴더에 있어야 합니다.
    client = gspread.authorize(creds)
    sheet = client.open_by_key(SPREADSHEET_KEY).sheet1  # 첫 번째 시트 사용
    return sheet

def load_data():
    try:
        df = pd.read_csv("data.csv", sep="|")
        df['id'] = df['id'].astype(str)
        return df
    except Exception as e:
        print(f"데이터 로드 오류: {e}")
        return pd.DataFrame()

df = load_data()

# ===================== [2] 앱 로직 클래스 =====================
class HomeworkApp:
    def __init__(self):
        self.user_name = ""
        self.homework_log = [] 
        self.current_q = None
        self.unknown_words = set()
        
        self.viewed_opt_indices = set()
        self.viewed_sent_indices = set()
        
        self.main_container = None
        self.sidebar_label = None
        self.log_count_label = None
        self.result_container = None 

    def start_login(self):
        self.main_container.clear()
        with self.main_container:
            ui.markdown("# 📝 영어 숙제장 (Online)")
            ui.label("구글 시트에 기록이 자동 저장됩니다.").classes('mb-2 text-gray-600')
            name_input = ui.input("이름").classes('w-64')
            name_input.on('keydown.enter', lambda: self.process_login(name_input.value))
            ui.button("숙제 시작하기", on_click=lambda: self.process_login(name_input.value)).props('color=primary')

    def process_login(self, name):
        if not name:
            ui.notify("이름을 입력해주세요.", type='warning')
            return
        self.user_name = name.strip()
        self.update_sidebar()
        self.load_new_question()

    def update_sidebar(self):
        if self.sidebar_label:
            self.sidebar_label.set_text(f"👤 {self.user_name} 학생")
            self.log_count_label.set_text(f"이번 세션: {len(self.homework_log)}문제")

    def download_csv(self):
        if not self.homework_log:
            ui.notify("방금 푼 기록이 없습니다.", type='warning')
            return
        log_df = pd.DataFrame(self.homework_log)
        csv_buffer = io.BytesIO()
        log_df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
        csv_buffer.seek(0)
        
        file_date = datetime.now().strftime("%y%m%d")
        filename = f"{self.user_name}_{file_date}_숙제.csv"
        
        ui.download(csv_buffer.getvalue(), filename=filename)

    # --- [핵심] 구글 시트에서 푼 문제 확인 ---
    def get_solved_ids(self):
        try:
            sheet = get_google_sheet()
            records = sheet.get_all_records() # 모든 기록 가져오기
            
            # 기록이 없으면 빈 집합 반환
            if not records:
                return set()
            
            # Pandas DF로 변환해서 필터링 (편의상)
            hist_df = pd.DataFrame(records)
            
            # 현재 접속한 학생의 이름으로 필터링
            if 'name' in hist_df.columns and 'problem_id' in hist_df.columns:
                # 숫자/문자 혼용 방지를 위해 전부 string으로 변환 후 비교
                user_hist = hist_df[hist_df['name'].astype(str) == self.user_name]
                return set(user_hist['problem_id'].astype(str).unique())
            else:
                return set()
                
        except Exception as e:
            print(f"구글 시트 읽기 오류: {e}")
            ui.notify("기록을 불러오는 중 오류가 발생했습니다.", type='negative')
            return set()

    def load_new_question(self):
        if df.empty:
            ui.notify("문제 데이터(data.csv)가 없습니다.", type='negative')
            return

        # 1. 구글 시트에서 푼 문제 번호 가져오기 (로딩 표시)
        ui.notify("기록 확인 중...", type='info', timeout=1000)
        solved_ids = self.get_solved_ids()
        
        # 2. 안 푼 문제 필터링
        remaining_df = df[~df['id'].isin(solved_ids)]
        
        # 3. 완료 화면
        if remaining_df.empty:
            self.render_completion_page()
            return

        # 4. 문제 뽑기
        self.current_q = remaining_df.sample(1).iloc[0]
        
        # 상태 초기화
        self.unknown_words = set()
        self.viewed_opt_indices = set()
        self.viewed_sent_indices = set()
        
        self.render_question_page()

    def render_completion_page(self):
        self.main_container.clear()
        with self.main_container:
            ui.markdown(f"## 🎉 축하합니다, {self.user_name} 학생!")
            ui.label("모든 문제를 다 풀었습니다.").classes('text-xl text-green-600 font-bold mb-4')
            ui.run_javascript('confetti()') 

    def render_question_page(self):
        self.main_container.clear()
        q = self.current_q
        
        with self.main_container:
            ui.markdown(f"#### 문제 {q['id']}") 
            ui.separator()

            # --- 보기 영역 ---
            ui.markdown("##### 1️⃣ 보기 (클릭 = 형광펜)")
            try:
                opts = str(q['options']).split("^")
                opt_trans = str(q.get('option_trans', '')).split("^")
            except: opts, opt_trans = [], []

            with ui.column().classes('w-full gap-2'):
                for i, opt in enumerate(opts):
                    with ui.row().classes('w-full items-start no-wrap'):
                        t_box = None 
                        btn = ui.button(f'({i+1})').props('outline size=sm color=green').classes('min-w-[30px] px-1 mr-2 mt-1')
                        with ui.column().classes('flex-1'):
                            self.render_interactive_text(opt, f"opt_{i}")
                            ot = opt_trans[i] if i < len(opt_trans) else ""
                            t_box = ui.html(f"<div style='margin-top:4px;'>└ {ot}</div>", sanitize=False).classes('trans-box hidden')
                            btn.on_click(lambda _, idx=i, target=t_box: self.toggle_trans_state(idx, 'opt', target))
            
            ui.separator().classes('my-4')

            # --- 지문 영역 ---
            ui.markdown("##### 2️⃣ 지문 독해")
            sentences = re.split(r'(?<=[.?!])\s+', str(q['passage']))
            translations = re.split(r'(?<=[.?!])\s+', str(q['translation']))

            with ui.column().classes('w-full gap-3'):
                for i, sent in enumerate(sentences):
                    if not sent.strip(): continue
                    with ui.row().classes('w-full items-start no-wrap'):
                        btn = ui.button(f'({i+1})').props('outline size=sm color=green').classes('min-w-[30px] px-1 mr-2 mt-1')
                        with ui.column().classes('flex-1'):
                            self.render_interactive_text(sent, f"sent_{i}")
                            t = translations[i] if i < len(translations) else ""
                            t_box = ui.html(f"<div style='margin-top:4px;'>🇰🇷 {t}</div>", sanitize=False).classes('trans-box hidden')
                            btn.on_click(lambda _, idx=i, target=t_box: self.toggle_trans_state(idx, 'sent', target))

            ui.separator().classes('my-4')

            # --- 정답 선택 ---
            ui.markdown("##### 3️⃣ 정답 선택")
            with ui.column().classes('gap-2 w-full'):
                radio = ui.radio(opts).props('color=primary')
                ui.button("제출하기", on_click=lambda: self.check_answer(radio.value)).props('color=primary')
            
            self.result_container = ui.column().classes('w-full mt-4')

    def check_answer(self, user_choice):
        if not user_choice:
            ui.notify("정답을 선택해주세요!", type='warning')
            return

        correct = str(self.current_q['answer']).strip()
        user_num = user_choice.strip()[1]
        if not user_num.isdigit(): user_num = user_choice.strip()[0]

        is_correct = (user_num == correct)
        
        self.add_log(is_correct, user_num)
        self.update_sidebar()

        self.result_container.clear()
        with self.result_container:
            if is_correct:
                ui.markdown("### 🎉 정답입니다!")
                ui.run_javascript('confetti()') 
            else:
                ui.markdown(f"### 💥 틀렸습니다. 정답은 **{correct}번** 입니다.")
            
            expl = self.current_q.get('explanation', '')
            ui.html(f"<div class='expl-box'><b>💡 [해설]</b><br>{expl}</div>", sanitize=False)
            
            ui.button("➡️ 다음 문제", on_click=self.load_new_question).props('color=secondary').classes('mt-4')

    def add_log(self, is_correct, user_ans):
        clean_words = []
        for w in self.unknown_words:
            parts = w.split('_')
            if len(parts) >= 3: clean_words.append("_".join(parts[2:]))
            else: clean_words.append(w)
            
        viewed_opts_str = ", ".join(map(str, sorted([i+1 for i in self.viewed_opt_indices])))
        viewed_sents_str = ", ".join(map(str, sorted([i+1 for i in self.viewed_sent_indices])))

        # 로그 데이터 구성
        log_data = {
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "name": self.user_name,
            "problem_id": str(self.current_q['id']),
            "is_correct": "O" if is_correct else "X",
            "user_answer": user_ans,
            "viewed_sentences": viewed_sents_str,
            "viewed_options": viewed_opts_str,
            "unknown_words": ", ".join(sorted(list(set(clean_words))))
        }
        
        # 1. 세션 기록 (다운로드용)
        self.homework_log.append(log_data)
        
        # 2. [핵심] 구글 시트에 저장
        try:
            sheet = get_google_sheet()
            # 첫 번째 행(헤더)이 비어있으면 헤더 추가
            if not sheet.get_all_values():
                sheet.append_row(list(log_data.keys()))
            
            # 데이터 추가
            sheet.append_row(list(log_data.values()))
        except Exception as e:
            print(f"구글 시트 저장 실패: {e}")
            ui.notify("서버 저장 실패 (인터넷 연결 확인)", type='negative')

    def toggle_word(self, label_element, word):
        if word in self.unknown_words:
            self.unknown_words.remove(word)
            label_element.classes(remove='highlight')
        else:
            self.unknown_words.add(word)
            label_element.classes(add='highlight')

    def toggle_trans_state(self, idx, type_str, target_element):
        target_set = self.viewed_opt_indices if type_str == 'opt' else self.viewed_sent_indices
        if idx in target_set: target_set.remove(idx)
        else: target_set.add(idx)
        target_element.classes(toggle='hidden')

    def render_interactive_text(self, text, prefix):
        words = text.split()
        with ui.row().classes('gap-0 wrap items-baseline w-full'): 
            for idx, word in enumerate(words):
                clean_word = word.strip(".,!?\"'()[]")
                unique_id = f"{prefix}_{idx}_{clean_word}"
                lbl = ui.label(word).classes('word-span text-base text-black')
                if unique_id in self.unknown_words: lbl.classes('highlight')
                lbl.on('click', lambda _, l=lbl, w=unique_id: self.toggle_word(l, w))
                if idx < len(words) - 1: ui.label('\u00A0').classes('text-base')

# ===================== [3] 메인 실행 =====================
@ui.page('/')
def main():
    ui.add_head_html('''
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background-color: white; }
            .highlight { background-color: #FFF176 !important; color: black !important; font-weight: bold; border-radius: 3px; }
            .word-span { cursor: pointer; padding: 2px; margin-right: 3px; transition: 0.1s; border-radius: 3px; }
            .word-span:hover { background-color: #E3F2FD; color: #1565C0; }
            .trans-box { background-color: #FAFAFA; border-left: 4px solid #4CAF50; padding: 10px; color: #333; width: 100%; font-size: 0.95rem; }
            .expl-box { background-color: #E1F5FE; padding: 15px; border-radius: 8px; margin-top: 15px; color: #01579B; width: 100%; }
        </style>
        <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
    ''')

    app_logic = HomeworkApp()

    with ui.left_drawer(value=True).props('width=250 bordered').classes('bg-gray-50 q-pa-md') as drawer:
        app_logic.sidebar_label = ui.label("👤 학생 정보 없음").classes('font-bold text-lg mb-2')
        app_logic.log_count_label = ui.label("이번 세션: 0문제").classes('mb-4 text-gray-700')
        ui.separator().classes('mb-4')
        ui.button("📥 결과 파일 다운로드", on_click=app_logic.download_csv).props('icon=download flat color=primary align=left').classes('w-full')
        ui.label("👆 오늘 푼 것만 다운로드 됩니다.").classes('text-xs text-gray-500 mt-2')

    with ui.header().classes('bg-white text-black shadow-sm'):
        ui.button(on_click=lambda: drawer.toggle(), icon='menu').props('flat color=black')
        ui.label('영어 숙제장').classes('text-lg font-bold ml-2')

    app_logic.main_container = ui.column().classes('w-full max-w-screen-lg mx-auto p-6 bg-white')
    app_logic.start_login()

ui.run(title="영어 숙제", port=8080, reload=False, show=True)