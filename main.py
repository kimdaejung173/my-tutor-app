from nicegui import ui, app
import pandas as pd
import re
from datetime import datetime
import time 
import os
import json
import pytz 
from supabase import create_client, Client

# ===================== [1] Supabase 설정 =====================
# URL과 KEY는 본인의 것으로 유지하세요
SUPABASE_URL = "https://akckfshjloggszaqgbqc.supabase.co"
SUPABASE_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6ImFrY2tmc2hqbG9nZ3N6YXFnYnFjIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NjcwNjI4NDcsImV4cCI6MjA4MjYzODg0N30.G4NAE_4DLlcrqjF00ZbIRsJELGlyI677p0ou8viwfwc"

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase 연결 실패: {e}")
    supabase = None

# --- 데이터 로드 함수 ---
def fetch_data(table_name):
    """Supabase에서 전체 데이터 가져오기"""
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table(table_name).select('*').execute()
        if response.data:
            df = pd.DataFrame(response.data)
            # id 컬럼들은 문자열로 통일
            if 'id' in df.columns: df['id'] = df['id'].astype(str)
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"{table_name} 로드 오류: {e}")
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

# 전역 캐싱
questions_df = pd.DataFrame()

# ===================== [2] 앱 로직 =====================
class HomeworkApp:
    def __init__(self):
        self.user_id = ""      
        self.user_name = ""
        
        # 상태 관리
        self.mode = "practice"
        self.current_q = None
        self.start_time = 0    
        
        self.submission_stage = 0 
        self.requested_hints = set() 
        self.unknown_words = set()   
        
        # UI
        self.main_container = None
        self.sidebar_label = None

    # --- [화면 1] 로그인 ---
    def start_login(self):
        self.main_container.clear()
        with self.main_container:
            # [수정됨] Streamlit 문법 제거하고 NiceGUI 방식으로 여백 추가
            ui.html("<br><br>") 
            
            ui.markdown("# 🔒 1등급 영어 과외").classes('text-center w-full mb-6 text-gray-800')
            
            # 테두리 없는 깔끔한 컨테이너
            with ui.column().classes('w-full max-w-sm mx-auto p-4 flex flex-col gap-4'):
                ui.label("학생 로그인").classes('text-xl font-bold mb-2 self-center text-indigo-600')
                
                self.id_input = ui.input("아이디").classes('w-full bg-white').props('outlined dense')
                self.pw_input = ui.input("비밀번호", password=True).classes('w-full bg-white').props('outlined dense')
                self.pw_input.on('keydown.enter', self.process_login)
                
                ui.button("입장하기", on_click=self.process_login).props('color=indigo unelevated').classes('w-full mt-2 font-bold h-10')

    def process_login(self):
        input_id = self.id_input.value
        input_pw = self.pw_input.value
        
        # 유저 DB 확인
        users_df = fetch_data('users')
        if users_df.empty:
            # 비상용 테스트 계정 (DB 연결 안될 때 사용)
            users_df = pd.DataFrame([{'id': 'student', 'password': '123', 'name': '테스트학생'}])
        
        user_row = users_df[(users_df['id'] == input_id) & (users_df['password'] == input_pw)]
        
        if not user_row.empty:
            self.user_id = input_id
            self.user_name = user_row.iloc[0].get('name', input_id)
            
            ui.notify(f"환영합니다, {self.user_name} 학생!", type='positive')
            
            # [수정됨] 실제 DB 테이블 이름 'exam_questions' 사용
            global questions_df
            questions_df = fetch_data('exam_questions')
            
            self.update_sidebar()
            self.render_menu_selection()
        else:
            ui.notify("아이디 또는 비밀번호를 확인해주세요.", type='negative')

    def update_sidebar(self):
        if self.sidebar_label:
            text = f"👤 {self.user_name}" if self.user_id else "👤 로그인 필요"
            self.sidebar_label.set_text(text)

    def logout(self):
        self.user_id = ""
        self.user_name = "" 
        self.update_sidebar()
        self.start_login()

    # --- [화면 2] 모드 선택 ---
    def render_menu_selection(self):
        self.main_container.clear()
        
        # 메뉴 진입 시 데이터 갱신
        global questions_df
        questions_df = fetch_data('exam_questions')

        with self.main_container:
            ui.markdown(f"## 👋 학습 모드 선택").classes('mb-2 text-gray-800')
            ui.label("원하는 학습 방식을 선택하세요.").classes('text-gray-500 mb-8')
            
            with ui.row().classes('w-full gap-6 justify-center wrap'):
                
                # 1. 유형별 연습 (카드 전체 클릭)
                with ui.card().on('click', self.select_practice_type).classes('w-72 cursor-pointer hover:shadow-xl hover:-translate-y-1 transition p-6 flex flex-col items-center border-t-4 border-indigo-500 gap-3'):
                    ui.icon('category', size='3.5em', color='indigo')
                    ui.label('유형별 격파').classes('font-bold text-xl')
                    ui.label('빈칸, 순서, 삽입 등\n취약 유형 집중 공략').classes('text-center text-sm text-gray-400 whitespace-pre-line')
                    ui.button("시작하기").props('flat color=indigo').classes('w-full mt-2 pointer-events-none')

                # 2. 실전 모의고사 (카드 전체 클릭)
                with ui.card().on('click', self.start_mock_exam).classes('w-72 cursor-pointer hover:shadow-xl hover:-translate-y-1 transition p-6 flex flex-col items-center border-t-4 border-red-500 gap-3'):
                    ui.icon('timer', size='3.5em', color='red')
                    ui.label('실전 모의고사').classes('font-bold text-xl')
                    ui.label('랜덤 하프 모의고사\n(기록 별도 관리)').classes('text-center text-sm text-gray-400 whitespace-pre-line')
                    ui.button("시작하기").props('flat color=red').classes('w-full mt-2 pointer-events-none')
            
            ui.separator().classes('my-8')
            ui.button("로그아웃", on_click=self.logout).props('outline color=grey dense').classes('mx-auto')

    def select_practice_type(self):
        """유형별 모드: 유형 선택 화면"""
        self.mode = 'practice'
        
        # 컬럼명 확인 ('type' 또는 'q_type')
        type_col = 'type' if 'type' in questions_df.columns else 'q_type'

        if questions_df.empty:
            ui.notify("등록된 문제가 없습니다.", type='warning')
            return
            
        available_types = questions_df[type_col].unique().tolist()
        
        self.main_container.clear()
        with self.main_container:
            ui.button('⬅ 뒤로가기', on_click=self.render_menu_selection).props('flat icon=arrow_back dense text-color=grey')
            ui.markdown("### 🎯 유형 선택")
            with ui.grid(columns=2).classes('w-full gap-3 mt-4'):
                for q_type in available_types:
                    count = len(questions_df[questions_df[type_col] == q_type])
                    ui.button(f"{q_type} ({count})", on_click=lambda t=q_type: self.load_question(t)).props('outline color=indigo').classes('h-14 text-lg')

    def start_mock_exam(self):
        self.mode = 'mock'
        self.load_question(target_type=None)

    # --- [로직] 문제 로드 ---
    def load_question(self, target_type=None):
        global questions_df
        if questions_df.empty: return

        solved_ids = fetch_solved_ids(self.user_id, self.mode)
        type_col = 'type' if 'type' in questions_df.columns else 'q_type'
        
        cond = ~questions_df['id'].isin(solved_ids)
        if target_type:
            cond = cond & (questions_df[type_col] == target_type)
        
        remaining_df = questions_df[cond]
        
        if remaining_df.empty:
            ui.notify("해당 조건의 모든 문제를 풀었습니다! 🎉", type='positive')
            self.render_menu_selection()
            return

        self.current_q = remaining_df.sample(1).iloc[0]
        
        self.submission_stage = 0
        self.requested_hints = set()
        self.unknown_words = set()
        self.start_time = time.time()
        
        self.render_question_page()

    # --- [화면 3] 문제 풀이 ---
    def render_question_page(self):
        self.main_container.clear()
        q = self.current_q
        
        with self.main_container:
            with ui.row().classes('w-full justify-between items-center mb-2'):
                ui.button('그만하기', on_click=self.render_menu_selection).props('flat dense icon=close color=grey')
                badge_color = 'red' if self.mode == 'mock' else 'indigo'
                ui.badge(f"{self.mode.upper()} MODE").props(f'color={badge_color} outline')
            
            q_text = q.get('question_text', '다음 글을 읽고 물음에 답하시오.')
            ui.label(q_text).classes('text-lg font-bold mb-2')
            ui.separator().classes('mb-4')

            extra = q.get('extra_content')
            if extra and str(extra).lower() not in ['nan', 'none', '']:
                with ui.card().classes('w-full bg-gray-50 border border-gray-300 p-4 mb-6 shadow-sm'):
                    self.render_interactive_text(extra, "extra")

            passage = str(q.get('passage', ''))
            sentences = re.split(r'(?<=[.?!])\s+', passage)
            trans_text = str(q.get('translation', ''))
            translations = re.split(r'(?<=[.?!])\s+', trans_text) if trans_text else []

            with ui.column().classes('w-full gap-4 mb-6'):
                for i, sent in enumerate(sentences):
                    if not sent.strip(): continue
                    
                    with ui.row().classes('w-full items-start no-wrap'):
                        is_requested = (i in self.requested_hints)
                        btn_color = 'green' if is_requested else 'grey'
                        btn_props = 'unelevated' if is_requested else 'outline'
                        
                        hint_btn = ui.button(f'{i+1}', on_click=lambda _, idx=i: self.toggle_hint(idx))\
                            .props(f'size=sm color={btn_color} {btn_props}')\
                            .classes('min-w-[28px] px-0 mr-2 mt-1 transition-colors')
                        
                        if self.submission_stage >= 1:
                            hint_btn.disable()

                        with ui.column().classes('flex-1'):
                            self.render_interactive_text(sent, f"sent_{i}")
                            
                            if self.submission_stage >= 1 and is_requested:
                                t_text = translations[i] if i < len(translations) else "(해석 없음)"
                                ui.html(f"<div class='text-sm text-green-700 bg-green-50 p-2 rounded mt-1'>🇰🇷 {t_text}</div>")

            ui.separator().classes('my-4')

            try:
                raw_opts = q.get('options')
                if isinstance(raw_opts, str):
                    opts = json.loads(raw_opts.replace("'", '"')) if '[' in raw_opts else raw_opts.split('^')
                else: opts = raw_opts 
            except: opts = ["보기 로드 실패"]

            if not isinstance(opts, list): opts = ["보기 데이터 형식 오류"]

            self.radio_val = ui.radio(opts).props('color=indigo').classes('text-base ml-2')

            with ui.row().classes('w-full mt-8 justify-center'):
                if self.submission_stage == 0:
                    ui.button("정답 제출 / 힌트 확인", on_click=self.submit_handler)\
                        .props('color=indigo size=lg icon=check').classes('w-full font-bold')
                elif self.submission_stage == 1:
                    ui.button("최종 정답 제출", on_click=self.submit_final)\
                        .props('color=red size=lg icon=done_all').classes('w-full font-bold')
                else:
                    type_col = 'type' if 'type' in questions_df.columns else 'q_type'
                    next_type = q[type_col] if self.mode == 'practice' else None
                    ui.button("➡️ 다음 문제", on_click=lambda: self.load_question(next_type))\
                        .props('color=green size=lg').classes('w-full font-bold')

            self.result_container = ui.column().classes('w-full mt-4')
            if self.submission_stage == 2:
                self.render_result()

    def toggle_hint(self, idx):
        if self.submission_stage > 0: return 
        if idx in self.requested_hints: self.requested_hints.remove(idx)
        else: self.requested_hints.add(idx)
        self.render_question_page()

    def submit_handler(self):
        if not self.radio_val.value:
            ui.notify("보기를 선택해주세요!", type='warning')
            return
        if len(self.requested_hints) == 0:
            self.submit_final()
            return
        self.submission_stage = 1
        ui.notify("요청하신 해석이 공개되었습니다.", type='info')
        self.render_question_page()

    def submit_final(self):
        if not self.radio_val.value:
            ui.notify("정답을 선택해주세요!", type='warning')
            return

        duration = int(time.time() - self.start_time)
        user_choice_str = str(self.radio_val.value)
        try:
            user_num = int(re.search(r'\d+', user_choice_str).group())
        except:
            user_num = 0
            
        correct_ans = str(self.current_q['answer']).strip()
        is_correct = (str(user_num) == correct_ans)

        self.submission_stage = 2
        self.save_log(str(user_num), is_correct, duration)
        self.render_question_page()

    def save_log(self, user_ans, is_correct, duration):
        if not supabase: return
        viewed_str = ", ".join(map(str, sorted(list(self.requested_hints))))
        unknown_str = ", ".join(sorted(list(self.unknown_words)))
        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")

        log_data = {
            "timestamp": now_kst,
            "user_id": self.user_id,
            "problem_id": str(self.current_q['id']),
            "mode": self.mode,
            "is_correct": "O" if is_correct else "X",
            "user_answer": user_ans,
            "viewed_sentences": viewed_str,
            "unknown_words": unknown_str,
            "duration": duration
        }
        try:
            supabase.table('study_logs').insert(log_data).execute()
        except Exception as e:
            print(f"저장 실패: {e}")

    def render_result(self):
        with self.result_container:
            ui.separator()
            correct_ans = str(self.current_q['answer']).strip()
            try:
                final_val = int(re.search(r'\d+', str(self.radio_val.value)).group())
            except: final_val = 0
            
            is_correct = (str(final_val) == correct_ans)

            if is_correct:
                ui.markdown("### 🎉 정답입니다!").classes('text-green-600 font-bold')
                ui.run_javascript('confetti()') 
            else:
                ui.markdown(f"### 💥 아쉽네요. 정답은 **{correct_ans}번** 입니다.").classes('text-red-600 font-bold')
            
            expl = self.current_q.get('explanation', '해설 없음')
            with ui.expansion('💡 해설 보기', icon='help', value=True).classes('w-full bg-blue-50 rounded mt-2'):
                ui.markdown(expl).classes('p-4 text-gray-800')

    def render_interactive_text(self, text, prefix):
        words = str(text).split()
        with ui.row().classes('gap-1 wrap items-baseline w-full'): 
            for idx, word in enumerate(words):
                clean_word = re.sub(r'[^\w]', '', word)
                unique_id = f"{prefix}_{idx}_{clean_word}"
                lbl = ui.label(word).classes('word-span text-lg leading-relaxed cursor-pointer rounded px-1 transition-colors')
                if unique_id in self.unknown_words: lbl.classes('highlight')
                lbl.on('click', lambda _, l=lbl, w=unique_id: self.toggle_word(l, w))

    def toggle_word(self, label_element, word):
        if word in self.unknown_words:
            self.unknown_words.remove(word)
            label_element.classes(remove='highlight')
        else:
            self.unknown_words.add(word)
            label_element.classes(add='highlight')

# ===================== [3] 메인 실행 =====================
@ui.page('/')
def main():
    ui.add_head_html('''
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
            body { font-family: 'Noto Sans KR', sans-serif; background-color: #f8f9fa; }
            .highlight { background-color: #fef08a !important; color: black !important; }
            .word-span:hover { background-color: #e0f2fe; color: #0284c7; }
        </style>
        <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
    ''')

    app_logic = HomeworkApp()

    with ui.left_drawer(value=False).props('width=240 bordered').classes('bg-white q-pa-md') as drawer:
        app_logic.sidebar_label = ui.label("👤 로그인 필요").classes('font-bold text-lg mb-4')
        ui.separator().classes('mb-4')
        ui.button("메뉴로", on_click=app_logic.render_menu_selection).props('flat dense align=left icon=home').classes('w-full')

    with ui.header().classes('bg-white text-black shadow-sm h-14'):
        ui.button(on_click=lambda: drawer.toggle(), icon='menu').props('flat color=black dense')
        ui.label('수능 영어 마스터').classes('text-lg font-bold ml-2 text-indigo-700')

    app_logic.main_container = ui.column().classes('w-full max-w-screen-md mx-auto p-4 bg-white min-h-screen shadow-sm')
    app_logic.start_login()

ui.run(title="영어 숙제장", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=False, show=False)