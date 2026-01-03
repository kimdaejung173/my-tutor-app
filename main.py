from nicegui import ui, app
import pandas as pd
import re
from datetime import datetime
import time 
import os
import json
import pytz 
import traceback # 에러 추적용
from supabase import create_client, Client

# ===================== [1] Supabase 설정 =====================
SUPABASE_URL = "https://akckfshjloggszaqgbqc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFrY2tmc2hqbG9nZ3N6YXFnYnFjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjcwNjI4NDcsImV4cCI6MjA4MjYzODg0N30.G4NAE_4DLlcrqjF00ZbIRsJELGlyI677p0ou8viwfwc"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase 연결 실패: {e}")
    supabase = None

# --- 데이터 로드 함수 (실패 시 알림 기능 추가) ---
def fetch_data(table_name):
    if not supabase: 
        ui.notify("데이터베이스 연결 실패!", type='negative')
        return pd.DataFrame()
    try:
        response = supabase.table(table_name).select('*').execute()
        if response.data:
            df = pd.DataFrame(response.data)
            # ID 컬럼 문자열 변환
            if 'id' in df.columns: df['id'] = df['id'].astype(str)
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"{table_name} 로드 오류: {e}")
        # 화면에 에러 띄우기 (디버깅용)
        ui.notify(f"데이터 로드 실패 ({table_name}): {e}", type='negative', timeout=5000)
        return pd.DataFrame()

def fetch_solved_ids(user_id, mode):
    if not supabase: return set()
    try:
        response = supabase.table('study_logs').select('problem_id').eq('user_id', user_id).eq('mode', mode).execute()
        if response.data:
            return set(str(item['problem_id']) for item in response.data)
        return set()
    except Exception as e:
        print(f"기록 로드 오류: {e}")
        return set()

# 전역 변수
questions_df = pd.DataFrame()

# ===================== [2] 앱 로직 =====================
class HomeworkApp:
    def __init__(self):
        self.user_id = ""      
        self.user_name = ""
        self.is_admin = False
        
        self.mode = "practice"
        self.current_q = None
        self.start_time = 0    
        self.submission_stage = 0 
        self.requested_hints = set()     
        self.viewed_options_idx = set()  
        self.unknown_words = set()       
        self.first_answer = ""           
        self.final_answer = ""
        
        self.admin_selected_student = None
        self.admin_selected_date = None
        self.admin_logs = []
        self.admin_current_idx = 0

        self.main_container = None
        self.sidebar_label = None
        self.radio_comp = None

    # ---------------------------------------------------------
    # [화면 1] 로그인
    # ---------------------------------------------------------
    def start_login(self):
        self.main_container.clear()
        with self.main_container:
            ui.label().classes('h-24') 
            with ui.column().classes('w-full max-w-xs mx-auto gap-4'):
                self.id_input = ui.input("ID").classes('w-full bg-white').props('outlined dense')
                self.pw_input = ui.input("PW", password=True).classes('w-full bg-white').props('outlined dense')
                self.pw_input.on('keydown.enter', self.process_login)
                ui.button("로그인", on_click=self.process_login).props('color=indigo unelevated').classes('w-full mt-2 font-bold')

    def process_login(self):
        global questions_df 
        input_id = self.id_input.value
        input_pw = self.pw_input.value
        
        # 1. 어드민 체크
        if input_id == 'admin':
            self.user_id = 'admin'
            self.user_name = '관리자'
            self.is_admin = True
            ui.notify("관리자 모드로 진입합니다.", type='positive')
            
            # 데이터 로드 시도 및 결과 알림
            questions_df = fetch_data('problem_set')
            if questions_df.empty:
                ui.notify("문제 데이터가 0개입니다! DB를 확인하세요.", type='warning', timeout=0, close_button=True)
            else:
                ui.notify(f"{len(questions_df)}개의 문제를 로드했습니다.", type='positive')

            self.update_sidebar()
            self.render_admin_dashboard()
            return

        # 2. 일반 학생 체크
        users_df = fetch_data('users')
        if users_df.empty:
            users_df = pd.DataFrame([{'id': 'student', 'password': '123', 'name': '테스트학생'}])
        
        user_row = users_df[(users_df['id'] == input_id) & (users_df['password'] == input_pw)]
        
        if not user_row.empty:
            self.user_id = input_id
            self.user_name = user_row.iloc[0].get('name', input_id)
            self.is_admin = False
            ui.notify(f"환영합니다, {self.user_name}님!", type='positive')
            
            # 데이터 로드 시도 및 결과 알림
            questions_df = fetch_data('problem_set')
            if questions_df.empty:
                ui.notify("문제 데이터가 0개입니다! DB 권한을 확인하세요.", type='warning', timeout=0, close_button=True)
            
            self.update_sidebar()
            self.render_menu_selection()
        else:
            ui.notify("아이디 또는 비밀번호 오류", type='negative')

    def update_sidebar(self):
        if self.sidebar_label:
            role = "관리자" if self.is_admin else "학생"
            text = f"👤 {self.user_name} ({role})" if self.user_id else "👤 로그인 필요"
            self.sidebar_label.set_text(text)

    def logout(self):
        self.user_id = ""
        self.user_name = "" 
        self.is_admin = False
        self.update_sidebar()
        self.start_login()

    # ---------------------------------------------------------
    # [화면 2-A] 학생 메뉴
    # ---------------------------------------------------------
    def render_menu_selection(self):
        self.main_container.clear()
        # 메뉴 진입 시 데이터 재확인 (안전장치)
        global questions_df
        if questions_df.empty:
            questions_df = fetch_data('problem_set')

        with self.main_container:
            ui.label().classes('h-10')
            with ui.row().classes('w-full gap-6 justify-center wrap'):
                with ui.card().on('click', self.select_practice_type).classes('w-64 cursor-pointer hover:shadow-lg hover:-translate-y-1 transition p-8 flex flex-col items-center border-t-4 border-indigo-500 gap-4'):
                    ui.icon('category', size='4em', color='indigo')
                    ui.label('유형').classes('font-bold text-2xl text-gray-700')

                with ui.card().on('click', self.start_mock_exam).classes('w-64 cursor-pointer hover:shadow-lg hover:-translate-y-1 transition p-8 flex flex-col items-center border-t-4 border-red-500 gap-4'):
                    ui.icon('timer', size='4em', color='red')
                    ui.label('모의고사').classes('font-bold text-2xl text-gray-700')
            
            ui.separator().classes('my-12 w-1/2 mx-auto')
            ui.button("로그아웃", on_click=self.logout).props('flat color=grey dense').classes('mx-auto')

    # ---------------------------------------------------------
    # [화면 2-B] 어드민 대시보드
    # ---------------------------------------------------------
    def render_admin_dashboard(self):
        self.main_container.clear()
        logs_df = fetch_data('study_logs')
        if logs_df.empty:
            with self.main_container:
                ui.label("아직 학습 기록이 없습니다.").classes('text-lg text-gray-500')
                ui.button("새로고침", on_click=self.render_admin_dashboard)
            return

        students = sorted(logs_df['user_id'].unique().tolist())
        with self.main_container:
            ui.label("관리자 대시보드").classes('text-xl font-bold mb-4 text-indigo-700')
            with ui.row().classes('gap-4 items-end mb-6'):
                stu_select = ui.select(students, label='학생 선택').classes('w-40')
                date_select = ui.select([], label='날짜 선택').classes('w-40')
                
                def update_dates(e):
                    selected_stu = e.value
                    if selected_stu:
                        stu_logs = logs_df[logs_df['user_id'] == selected_stu]
                        dates = sorted(list(set(t.split(' ')[0] for t in stu_logs['timestamp'])), reverse=True)
                        date_select.options = dates
                        date_select.value = dates[0] if dates else None
                stu_select.on_value_change(update_dates)
                
                def load_admin_view():
                    stu = stu_select.value
                    date = date_select.value
                    if not stu or not date:
                        ui.notify("학생과 날짜를 선택해주세요.", type='warning')
                        return
                    filtered = logs_df[
                        (logs_df['user_id'] == stu) & 
                        (logs_df['timestamp'].str.startswith(date))
                    ].sort_values('timestamp')
                    
                    if filtered.empty:
                        ui.notify("기록이 없습니다.", type='warning')
                        return
                    
                    self.admin_selected_student = stu
                    self.admin_selected_date = date
                    self.admin_logs = filtered.to_dict('records')
                    self.admin_current_idx = 0
                    self.render_admin_review_page()

                ui.button("조회", on_click=load_admin_view).props('unelevated color=indigo')

    def render_admin_review_page(self):
        self.main_container.clear()
        log = self.admin_logs[self.admin_current_idx]
        q_id = log['problem_id']
        
        q_row = questions_df[questions_df['id'] == q_id]
        if q_row.empty:
            with self.main_container:
                ui.label(f"문제 정보를 찾을 수 없습니다. (ID: {q_id})").classes('text-red-500')
                self.render_admin_nav()
            return
        
        q = q_row.iloc[0]
        try:
            viewed_sents = set(map(int, str(log.get('viewed_sentences','')).split(', '))) if log.get('viewed_sentences') else set()
            unknown_w = set(str(log.get('unknown_words','')).split(', ')) if log.get('unknown_words') else set()
            final_ans = str(log.get('final_answer', '-'))
            is_correct = (log.get('is_correct') == 'O')
        except:
            viewed_sents, unknown_w = set(), set()
            final_ans, is_correct = '-', False

        with self.main_container:
            with ui.card().classes('w-full bg-gray-100 p-2 mb-4 flex-row justify-between items-center'):
                ui.label(f"학생: {self.admin_selected_student} | 날짜: {self.admin_selected_date}").classes('font-bold')
                status_color = 'green' if is_correct else 'red'
                status_text = "정답 ⭕" if is_correct else f"오답 ❌ (학생선택: {final_ans})"
                ui.badge(status_text).props(f'color={status_color}').classes('text-lg')

            self.render_read_only_options(q, unknown_w)
            ui.separator().classes('my-4')
            self.render_read_only_passage(q, viewed_sents, unknown_w)
            self.render_admin_nav()

    def render_admin_nav(self):
        with ui.row().classes('w-full justify-between mt-6'):
            if self.admin_current_idx > 0:
                ui.button("◀ 이전 문제", on_click=lambda: self.move_admin_idx(-1)).props('outline color=grey')
            else:
                ui.label()
            ui.label(f"{self.admin_current_idx + 1} / {len(self.admin_logs)}").classes('font-bold self-center')
            if self.admin_current_idx < len(self.admin_logs) - 1:
                ui.button("다음 문제 ▶", on_click=lambda: self.move_admin_idx(1)).props('unelevated color=indigo')
            else:
                ui.button("목록으로", on_click=self.render_admin_dashboard).props('flat color=grey')

    def move_admin_idx(self, delta):
        self.admin_current_idx += delta
        self.render_admin_review_page()

    def render_read_only_options(self, q, unknown_w):
        opts = self.get_options_list(q)
        trans = self.get_options_trans_list(q)
        ui.label("보기 (Options)").classes('font-bold text-gray-500 mb-2')
        with ui.column().classes('w-full gap-2 border p-4 rounded bg-white'):
            for i, opt_text in enumerate(opts):
                with ui.row().classes('items-center w-full'):
                    ui.label(f"{i+1}.").classes('font-bold mr-2 text-gray-500')
                    self.render_static_text(opt_text, unknown_w)
                    if trans and i < len(trans):
                        ui.icon('translate', color='grey').tooltip(trans[i])

    def render_read_only_passage(self, q, viewed_sents, unknown_w):
        passage = str(q.get('passage', ''))
        sentences = re.split(r'(?<=[.?!])\s+', passage)
        trans_text = str(q.get('translation', ''))
        translations = re.split(r'(?<=[.?!])\s+', trans_text) if trans_text else []
        with ui.column().classes('w-full gap-4'):
            for i, sent in enumerate(sentences):
                if not sent.strip(): continue
                with ui.row().classes('w-full items-start no-wrap'):
                    color = 'green' if i in viewed_sents else 'grey'
                    ui.badge(f"{i+1}").props(f'color={color}').classes('mt-1 mr-2')
                    with ui.column().classes('flex-1'):
                        self.render_static_text(sent, unknown_w)
                        if i in viewed_sents and i < len(translations):
                            ui.label(f"🇰🇷 {translations[i]}").classes('text-sm text-green-700 bg-green-50 p-1 rounded mt-1')

    def render_static_text(self, text, unknown_w):
        words = str(text).split()
        with ui.row().classes('gap-1 wrap items-baseline w-full'):
            for word in words:
                clean_word = re.sub(r'[^\w]', '', word)
                lbl = ui.label(word).classes('text-lg leading-relaxed rounded px-1')
                if clean_word in unknown_w or word in unknown_w:
                    lbl.classes('bg-yellow-200')

    # ---------------------------------------------------------
    # [화면 2,3] 학생용 로직 (디버깅 강화)
    # ---------------------------------------------------------
    def select_practice_type(self):
        try:
            self.mode = 'practice'
            if questions_df.empty:
                ui.notify("등록된 문제가 없습니다. DB 연결을 확인해주세요.", type='negative', close_button=True)
                return
                
            type_col = 'type' if 'type' in questions_df.columns else 'q_type'
            available_types = questions_df[type_col].unique().tolist()
            
            self.main_container.clear()
            with self.main_container:
                ui.button('⬅', on_click=self.render_menu_selection).props('flat icon=arrow_back dense text-color=grey')
                ui.label("유형 선택").classes('text-xl font-bold mb-4')
                with ui.grid(columns=2).classes('w-full gap-3'):
                    for q_type in available_types:
                        count = len(questions_df[questions_df[type_col] == q_type])
                        ui.button(f"{q_type} ({count})", on_click=lambda t=q_type: self.load_question(t)).props('outline color=indigo').classes('h-14 text-lg')
        except Exception as e:
            ui.notify(f"유형 선택 오류: {e}", type='negative', close_button=True)
            print(traceback.format_exc())

    def start_mock_exam(self):
        self.mode = 'mock'
        self.load_question(None)

    def load_question(self, target_type=None):
        try:
            global questions_df
            if questions_df.empty:
                ui.notify("문제 데이터가 로드되지 않았습니다.", type='negative', close_button=True)
                return

            solved_ids = fetch_solved_ids(self.user_id, self.mode)
            type_col = 'type' if 'type' in questions_df.columns else 'q_type'
            
            cond = ~questions_df['id'].isin(solved_ids)
            if target_type:
                cond = cond & (questions_df[type_col] == target_type)
            
            remaining = questions_df[cond]
            
            if remaining.empty:
                ui.notify("해당 조건의 문제를 모두 풀었습니다! 🎉", type='positive')
                self.render_menu_selection()
                return

            self.current_q = remaining.sample(1).iloc[0]
            self.submission_stage = 0
            self.requested_hints = set()
            self.viewed_options_idx = set()
            self.unknown_words = set()
            self.first_answer = ""
            self.final_answer = ""
            self.start_time = time.time()
            self.render_question_page()
            
        except Exception as e:
            ui.notify(f"문제 로드 중 오류 발생: {str(e)}", type='negative', timeout=0, close_button=True)
            print(traceback.format_exc())

    def render_question_page(self):
        self.main_container.clear()
        q = self.current_q
        with self.main_container:
            with ui.row().classes('w-full justify-between items-center mb-2'):
                ui.button(icon='close', on_click=self.render_menu_selection).props('flat dense color=grey')
                ui.badge(self.mode.upper()).props('outline color=indigo')

            self.render_options_area(q)
            ui.separator().classes('my-6')

            extra = q.get('extra_content')
            if extra and str(extra).lower() not in ['nan', 'none', '']:
                with ui.card().classes('w-full bg-gray-50 border p-4 mb-4'):
                    self.render_interactive_text(extra, "extra")
            
            passage = str(q.get('passage', ''))
            sentences = re.split(r'(?<=[.?!])\s+', passage)
            translations = re.split(r'(?<=[.?!])\s+', str(q.get('translation', '')))

            with ui.column().classes('w-full gap-4 mb-6'):
                for i, sent in enumerate(sentences):
                    if not sent.strip(): continue
                    with ui.row().classes('w-full items-start no-wrap'):
                        hint_btn = ui.button(f'{i+1}', on_click=lambda _, idx=i: self.toggle_hint(idx))\
                            .props(f'size=sm {"unelevated color=green" if i in self.requested_hints else "outline color=grey"}')\
                            .classes('min-w-[28px] px-0 mr-2 mt-1')
                        if self.submission_stage >= 1: hint_btn.disable()

                        with ui.column().classes('flex-1'):
                            self.render_interactive_text(sent, f"sent_{i}")
                            if self.submission_stage >= 1 and i in self.requested_hints and i < len(translations):
                                # 500 에러 원인이었던 unsafe_allow_html 제거됨 (sanitize=False도 기본값이라 생략 가능)
                                ui.html(f"<div class='text-sm text-green-700 bg-green-50 p-2 rounded mt-1'>🇰🇷 {translations[i]}</div>")

            ui.separator().classes('my-4')
            opts = self.get_options_list(q)
            radio_options = [f"{i+1}. {opt}" for i, opt in enumerate(opts)]
            ui.label("정답 선택:").classes('font-bold text-gray-700')
            self.radio_comp = ui.radio(radio_options).props('color=indigo').classes('ml-2')

            with ui.row().classes('w-full mt-8 justify-center'):
                if self.submission_stage == 0:
                    ui.button("제출 / 힌트확인", on_click=self.submit_handler).props('color=indigo size=lg icon=check').classes('w-full font-bold')
                elif self.submission_stage == 1:
                    ui.button("최종 제출", on_click=self.submit_final).props('color=red size=lg icon=done_all').classes('w-full font-bold')
                else:
                    type_col = 'type' if 'type' in questions_df.columns else 'q_type'
                    next_type = q[type_col] if self.mode == 'practice' else None
                    ui.button("다음 문제 ➡️", on_click=lambda: self.load_question(next_type)).props('color=green size=lg').classes('w-full font-bold')

            self.result_container = ui.column().classes('w-full mt-4')
            if self.submission_stage == 2:
                self.render_result()

    # --- 헬퍼 함수들 ---
    def get_options_list(self, q):
        try:
            raw = q.get('options')
            if isinstance(raw, str): return json.loads(raw.replace("'", '"')) if '[' in raw else raw.split('^')
            return raw if isinstance(raw, list) else ["보기 에러"]
        except: return ["보기 에러"]

    def get_options_trans_list(self, q):
        try:
            raw = q.get('options_translation')
            if not raw or str(raw).lower() == 'nan': return []
            if isinstance(raw, str): return json.loads(raw.replace("'", '"')) if '[' in raw else raw.split('^')
            return raw if isinstance(raw, list) else []
        except: return []

    def render_options_area(self, q):
        opts = self.get_options_list(q)
        trans = self.get_options_trans_list(q)
        
        ui.label("보기 (Options)").classes('font-bold text-gray-600 mb-2')
        with ui.column().classes('w-full gap-2 border p-4 rounded bg-white'):
            for i, opt_text in enumerate(opts):
                with ui.row().classes('items-center w-full'):
                    ui.label(f"{i+1}.").classes('font-bold mr-2 text-gray-500')
                    with ui.row().classes('flex-1 wrap items-baseline'):
                        self.render_interactive_text(opt_text, f"opt_{i}")
                    
                    if trans and i < len(trans):
                        def show_trans(t=trans[i], idx=i):
                            self.viewed_options_idx.add(idx)
                            ui.notify(f"해석: {t}", type='info', timeout=3000)
                        ui.button(icon='translate', on_click=lambda _, i=i: show_trans(idx=i)).props('flat round size=sm color=grey')

    def render_interactive_text(self, text, prefix):
        words = str(text).split()
        with ui.row().classes('gap-1 wrap items-baseline w-full'):
            for idx, word in enumerate(words):
                clean_word = re.sub(r'[^\w]', '', word)
                unique_id = f"{prefix}_{idx}_{clean_word}"
                lbl = ui.label(word).classes('cursor-pointer rounded px-1 transition-colors hover:bg-blue-100 hover:text-blue-600 text-lg')
                if unique_id in self.unknown_words: lbl.classes('bg-yellow-200')
                lbl.on('click', lambda _, l=lbl, w=unique_id: self.toggle_word(l, w))

    def toggle_word(self, label, word_id):
        if word_id in self.unknown_words:
            self.unknown_words.remove(word_id)
            label.classes(remove='bg-yellow-200')
        else:
            self.unknown_words.add(word_id)
            label.classes(add='bg-yellow-200')

    def toggle_hint(self, idx):
        if self.submission_stage > 0: return
        if idx in self.requested_hints: self.requested_hints.remove(idx)
        else: self.requested_hints.add(idx)
        self.render_question_page()

    def get_selected_number(self):
        if not self.radio_comp or not self.radio_comp.value: return 0
        try: return int(re.search(r'\d+', str(self.radio_comp.value)).group())
        except: return 0

    def submit_handler(self):
        num = self.get_selected_number()
        if num == 0:
            ui.notify("선택해주세요!", type='warning')
            return
        if not self.requested_hints:
            self.first_answer = str(num)
            self.submit_final()
            return
        self.first_answer = str(num)
        self.submission_stage = 1
        ui.notify("해석이 공개되었습니다.", type='info')
        self.render_question_page()

    def submit_final(self):
        num = self.get_selected_number()
        if num == 0:
            ui.notify("선택해주세요!", type='warning')
            return
        self.final_answer = str(num)
        correct = str(self.current_q['answer']).strip()
        is_correct = (self.final_answer == correct)
        duration = int(time.time() - self.start_time)
        self.submission_stage = 2
        self.save_log(is_correct, duration)
        self.render_question_page()

    def save_log(self, is_correct, duration):
        if not supabase: return
        clean_words = set()
        for w in self.unknown_words:
            parts = w.split('_')
            if len(parts) > 1: clean_words.add(parts[-1])
            else: clean_words.add(w)
        data = {
            "timestamp": datetime.now(pytz.timezone('Asia/Seoul')).strftime("%Y-%m-%d %H:%M:%S"),
            "user_id": self.user_id,
            "problem_id": str(self.current_q['id']),
            "mode": self.mode,
            "is_correct": "O" if is_correct else "X",
            "first_answer": self.first_answer,
            "final_answer": self.final_answer,
            "viewed_sentences": ", ".join(map(str, sorted(list(self.requested_hints)))),
            "viewed_options": ", ".join(map(str, sorted(list(self.viewed_options_idx)))),
            "unknown_words": ", ".join(sorted(list(clean_words))),
            "duration": duration
        }
        try:
            supabase.table('study_logs').insert(data).execute()
        except Exception as e:
            print(f"Log Error: {e}")
            ui.notify(f"로그 저장 실패: {str(e)}", type='negative')

    def render_result(self):
        with self.result_container:
            ui.separator()
            ans = str(self.current_q['answer']).strip()
            if self.final_answer == ans:
                ui.markdown("### 정답입니다! 🎉").classes('text-green-600')
                ui.run_javascript('confetti()')
            else:
                ui.markdown(f"### 오답입니다. 정답: **{ans}번**").classes('text-red-600')
            with ui.expansion('해설 보기', icon='help').classes('w-full bg-blue-50'):
                ui.markdown(self.current_q.get('explanation', '해설 없음')).classes('p-4')

# ===================== [3] 메인 실행 =====================
@ui.page('/')
def main():
    ui.add_head_html('''
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
            body { font-family: 'Noto Sans KR', sans-serif; background-color: #f8f9fa; }
        </style>
        <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
    ''')

    app = HomeworkApp()

    with ui.left_drawer(value=False).props('bordered').classes('bg-white') as drawer:
        app.sidebar_label = ui.label("👤 로그인 필요").classes('font-bold text-lg mb-4')
        ui.separator().classes('mb-4')
        ui.button("메뉴로", on_click=lambda: app.render_menu_selection() if not app.is_admin else app.render_admin_dashboard()).props('flat icon=home').classes('w-full')

    with ui.header().classes('bg-white text-black shadow-sm h-14'):
        ui.button(on_click=lambda: drawer.toggle(), icon='menu').props('flat color=black dense')

    app.main_container = ui.column().classes('w-full max-w-screen-md mx-auto p-4 bg-white min-h-screen shadow-sm')
    app.start_login()

ui.run(title="영어 숙제장", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=False, show=False)