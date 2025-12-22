from nicegui import ui, app
import pandas as pd
import re
from datetime import datetime
import io
import os
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import pytz 

# ===================== [1] 설정 및 데이터 로드 =====================

scope = [
    "https://spreadsheets.google.com/feeds",
    "https://www.googleapis.com/auth/drive"
]

json_str = os.environ.get("GOOGLE_KEY") 

if json_str:
    key_dict = json.loads(json_str)
    creds = ServiceAccountCredentials.from_json_keyfile_dict(key_dict, scope)
else:
    try:
        creds = ServiceAccountCredentials.from_json_keyfile_name('service_account.json', scope)
    except:
        print("경고: GOOGLE_KEY 환경변수도 없고 로컬 파일도 없습니다.")
        creds = None

SPREADSHEET_KEY = "1Gtz2LYGjl9uGwbfsNc_NJJdgu68KybQYcep1ncQHCmU" 

def get_student_sheet(student_name):
    if not creds: return None
    client = gspread.authorize(creds)
    spreadsheet = client.open_by_key(SPREADSHEET_KEY)
    
    try:
        # 학생 이름(ID)으로 된 탭이 있는지 확인
        sheet = spreadsheet.worksheet(student_name)
    except gspread.WorksheetNotFound:
        # 없으면 새로 생성
        sheet = spreadsheet.add_worksheet(title=student_name, rows=100, cols=10)
        sheet.append_row([
            "timestamp", "name", "problem_id", "is_correct", 
            "user_answer", "viewed_sentences", "viewed_options", "unknown_words"
        ])
    return sheet

def load_data():
    try:
        df = pd.read_csv("data.csv", sep="|")
        df['id'] = df['id'].astype(str)
        return df
    except Exception as e:
        print(f"데이터 로드 오류: {e}")
        return pd.DataFrame()

# [수정] id와 password만 있으면 됩니다.
def load_users():
    try:
        # 한글 ID를 읽어야 하므로 utf-8 필수
        users = pd.read_csv("users.csv", encoding='utf-8')
        users['id'] = users['id'].astype(str)
        users['password'] = users['password'].astype(str)
        return users
    except Exception as e:
        print(f"유저 파일 로드 오류: {e}")
        return pd.DataFrame()

df = load_data()
users_df = load_users()

# ===================== [2] 앱 로직 클래스 =====================
class HomeworkApp:
    def __init__(self):
        self.user_name = "" # 여기에 한글 이름(ID)이 들어갑니다
        self.homework_log = [] 
        self.current_q = None
        self.unknown_words = set()
        
        self.viewed_opt_indices = set()
        self.viewed_sent_indices = set()
        
        self.main_container = None
        self.sidebar_label = None
        self.log_count_label = None
        self.result_container = None 

    # --- [화면 1] 로그인 화면 ---
    def start_login(self):
        self.main_container.clear()
        with self.main_container:
            ui.markdown("# 🔒 1등급 과외 숙제장").classes('text-center w-full')
            
            with ui.card().classes('w-full max-w-sm mx-auto p-4 flex flex-col gap-2'):
                ui.label("로그인").classes('text-lg font-bold mb-2')
                
                # 라벨을 '이름(ID)'로 변경하여 혼란 방지
                self.id_input = ui.input("이름 (ID)").classes('w-full') 
                self.pw_input = ui.input("비밀번호", password=True).classes('w-full')
                
                self.pw_input.on('keydown.enter', self.process_login)
                
                ui.button("로그인", on_click=self.process_login).props('color=primary').classes('w-full mt-2')

    def process_login(self):
        input_id = self.id_input.value
        input_pw = self.pw_input.value
        
        global users_df
        if users_df.empty: users_df = load_users()

        if users_df.empty:
            ui.notify("유저 정보(users.csv)가 없습니다.", type='negative')
            return

        # 아이디/비번 대조
        user_row = users_df[(users_df['id'] == input_id) & (users_df['password'] == input_pw)]
        
        if not user_row.empty:
            # [수정] 별도의 name 컬럼을 찾지 않고, 입력한 ID를 그대로 이름으로 사용
            self.user_name = input_id 
            
            ui.notify(f"환영합니다, {self.user_name} 학생!", type='positive')
            self.update_sidebar()
            self.render_menu() 
        else:
            ui.notify("이름(ID) 또는 비밀번호가 틀렸습니다.", type='negative')

    # --- [화면 2] 메뉴 선택 화면 ---
    def render_menu(self):
        self.main_container.clear()
        with self.main_container:
            ui.markdown(f"## 👋 반가워요, {self.user_name} 학생!").classes('mb-4')
            ui.label("오늘 학습할 내용을 선택하세요.").classes('text-gray-600 mb-6')
            
            with ui.grid(columns=2).classes('w-full gap-4'):
                with ui.card().classes('cursor-pointer hover:bg-green-50 transition p-4 flex flex-col items-center justify-center h-32 border-2 border-green-500'):
                    ui.icon('edit_note', size='3em', color='green')
                    ui.label('빈칸 추론').classes('font-bold text-lg mt-2')
                    ui.label('Click to Start').classes('text-xs text-gray-400')
                
            ui.separator().classes('my-4')
            
            btn_style = 'height: 60px; font-size: 16px;'
            
            ui.button("📝 빈칸 추론", on_click=self.load_new_question).props('color=primary icon=edit').style(btn_style).classes('w-full')
            
            ui.button("🔀 순서 배열 (준비중)").props('color=grey outline').style(btn_style).classes('w-full').disable()
            ui.button("📥 문장 삽입 (준비중)").props('color=grey outline').style(btn_style).classes('w-full').disable()
            ui.button("💡 주제 찾기 (준비중)").props('color=grey outline').style(btn_style).classes('w-full').disable()
            ui.button("🏷️ 제목 찾기 (준비중)").props('color=grey outline').style(btn_style).classes('w-full').disable()
            
            ui.separator().classes('my-4')
            ui.button("로그아웃", on_click=self.logout).props('flat color=grey').classes('w-full')

    def logout(self):
        self.user_name = ""
        self.homework_log = []
        self.start_login()

    def update_sidebar(self):
        if self.sidebar_label:
            # ID가 곧 이름이므로 하나만 표시
            self.sidebar_label.set_text(f"👤 {self.user_name}")
            self.log_count_label.set_text(f"이번 세션: {len(self.homework_log)}문제")

    def download_csv(self):
        if not self.homework_log:
            ui.notify("방금 푼 기록이 없습니다.", type='warning')
            return
        log_df = pd.DataFrame(self.homework_log)
        csv_buffer = io.BytesIO()
        log_df.to_csv(csv_buffer, index=False, encoding='utf-8-sig')
        csv_buffer.seek(0)
        
        kst = pytz.timezone('Asia/Seoul')
        file_date = datetime.now(kst).strftime("%y%m%d")
        filename = f"{self.user_name}_{file_date}_숙제.csv"
        
        ui.download(csv_buffer.getvalue(), filename=filename)

    # --- 구글 시트 문제 확인 ---
    def get_solved_ids(self):
        try:
            sheet = get_student_sheet(self.user_name)
            if not sheet: return set()
            
            records = sheet.get_all_records()
            if not records: return set()
            
            hist_df = pd.DataFrame(records)
            
            if 'problem_id' in hist_df.columns:
                return set(hist_df['problem_id'].astype(str).unique())
            else:
                return set()
        except Exception as e:
            print(f"구글 시트 읽기 오류: {e}")
            ui.notify("기록을 불러오는 중 오류가 발생했습니다.", type='negative')
            return set()

    # --- [화면 3] 문제 풀기 화면 ---
    def load_new_question(self):
        self.main_container.clear()
        
        if df.empty:
            ui.notify("문제 데이터가 없습니다.", type='negative')
            return

        ui.notify("기록 확인 중...", type='info', timeout=1000)
        solved_ids = self.get_solved_ids()
        
        remaining_df = df[~df['id'].isin(solved_ids)]
        
        if remaining_df.empty:
            self.render_completion_page()
            return

        self.current_q = remaining_df.sample(1).iloc[0]
        
        self.unknown_words = set()
        self.viewed_opt_indices = set()
        self.viewed_sent_indices = set()
        
        self.render_question_page()

    def render_completion_page(self):
        self.main_container.clear()
        with self.main_container:
            ui.markdown(f"## 🎉 축하합니다, {self.user_name} 학생!")
            ui.label("준비된 모든 문제를 풀었습니다.").classes('text-xl text-green-600 font-bold mb-4')
            ui.run_javascript('confetti()') 
            ui.button("메뉴로 돌아가기", on_click=self.render_menu).props('outline')

    def render_question_page(self):
        with self.main_container:
            ui.button('⬅ 메뉴로', on_click=self.render_menu).props('flat dense icon=arrow_back').classes('mb-2')
            
            q = self.current_q
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

        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")

        log_data = {
            "timestamp": now_kst,
            "name": self.user_name, # 여기서도 그냥 ID(이름)가 저장됨
            "problem_id": str(self.current_q['id']),
            "is_correct": "O" if is_correct else "X",
            "user_answer": user_ans,
            "viewed_sentences": viewed_sents_str,
            "viewed_options": viewed_opts_str,
            "unknown_words": ", ".join(sorted(list(set(clean_words))))
        }
        
        self.homework_log.append(log_data)
        
        try:
            sheet = get_student_sheet(self.user_name)
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
        app_logic.sidebar_label = ui.label("👤 로그인 필요").classes('font-bold text-lg mb-2')
        app_logic.log_count_label = ui.label("").classes('mb-4 text-gray-700')
        ui.separator().classes('mb-4')
        ui.button("📥 결과 파일 다운로드", on_click=app_logic.download_csv).props('icon=download flat color=primary align=left').classes('w-full')
        ui.label("👆 오늘 푼 것만 다운로드 됩니다.").classes('text-xs text-gray-500 mt-2')

    with ui.header().classes('bg-white text-black shadow-sm'):
        ui.button(on_click=lambda: drawer.toggle(), icon='menu').props('flat color=black')
        ui.label('영어 숙제장').classes('text-lg font-bold ml-2')

    app_logic.main_container = ui.column().classes('w-full max-w-screen-lg mx-auto p-6 bg-white')
    app_logic.start_login()

ui.run(title="영어 숙제", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=False, show=False)