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

# 전역 캐싱 (앱 시작 시 한 번 로드)
# [변경] exam_questions -> problem_set
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
        self.requested_hints = set()     # 지문 힌트 (문장 번호)
        self.viewed_options_idx = set()  # 보기 해석 본 번호
        self.unknown_words = set()       # 모르는 단어 (태그 포함)
        
        self.first_answer = ""           # 1차 답안
        self.final_answer = ""           # 최종 답안
        
        # UI 참조
        self.main_container = None
        self.sidebar_label = None
        self.radio_comp = None           # 라디오 버튼 컴포넌트

    # --- [화면 1] 로그인 ---
    def start_login(self):
        self.main_container.clear()
        with self.main_container:
            # 안전하게 여백 주기
            ui.label().classes('h-16') 
            
            ui.markdown("# 🔒 1등급 영어 과외").classes('text-center w-full mb-6 text-gray-800')
            
            with ui.column().classes('w-full max-w-sm mx-auto p-4 flex flex-col gap-4'):
                ui.label("학생 로그인").classes('text-xl font-bold mb-2 self-center text-indigo-600')
                
                self.id_input = ui.input("아이디").classes('w-full bg-white').props('outlined dense')
                self.pw_input = ui.input("비밀번호", password=True).classes('w-full bg-white').props('outlined dense')
                self.pw_input.on('keydown.enter', self.process_login)
                
                ui.button("입장하기", on_click=self.process_login).props('color=indigo unelevated').classes('w-full mt-2 font-bold h-10')

    def process_login(self):
        input_id = self.id_input.value
        input_pw = self.pw_input.value
        
        users_df = fetch_data('users')
        if users_df.empty:
            users_df = pd.DataFrame([{'id': 'student', 'password': '123', 'name': '테스트학생'}])
        
        user_row = users_df[(users_df['id'] == input_id) & (users_df['password'] == input_pw)]
        
        if not user_row.empty:
            self.user_id = input_id
            self.user_name = user_row.iloc[0].get('name', input_id)
            ui.notify(f"환영합니다, {self.user_name} 학생!", type='positive')
            
            # [변경] 문제 테이블 이름 'problem_set'으로 로드
            global questions_df
            questions_df = fetch_data('problem_set')
            
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
        questions_df = fetch_data('problem_set')

        with self.main_container:
            ui.markdown(f"## 👋 학습 모드 선택").classes('mb-2 text-gray-800')
            ui.label("원하는 학습 방식을 선택하세요.").classes('text-gray-500 mb-8')
            
            with ui.row().classes('w-full gap-6 justify-center wrap'):
                
                # 1. 유형별 연습 (버튼 제거, 카드 전체 클릭)
                with ui.card().on('click', self.select_practice_type).classes('w-72 cursor-pointer hover:shadow-xl hover:-translate-y-1 transition p-6 flex flex-col items-center border-t-4 border-indigo-500 gap-3'):
                    ui.icon('category', size='3.5em', color='indigo')
                    ui.label('유형별 격파').classes('font-bold text-xl')
                    ui.label('빈칸, 순서, 삽입 등\n취약 유형 집중 공략').classes('text-center text-sm text-gray-400 whitespace-pre-line')
                    # 시작하기 버튼 제거함

                # 2. 실전 모의고사 (버튼 제거, 카드 전체 클릭)
                with ui.card().on('click', self.start_mock_exam).classes('w-72 cursor-pointer hover:shadow-xl hover:-translate-y-1 transition p-6 flex flex-col items-center border-t-4 border-red-500 gap-3'):
                    ui.icon('timer', size='3.5em', color='red')
                    ui.label('실전 모의고사').classes('font-bold text-xl')
                    ui.label('랜덤 하프 모의고사\n(기록 별도 관리)').classes('text-center text-sm text-gray-400 whitespace-pre-line')
                    # 시작하기 버튼 제거함
            
            ui.separator().classes('my-8')
            ui.button("로그아웃", on_click=self.logout).props('outline color=grey dense').classes('mx-auto')

    def select_practice_type(self):
        self.mode = 'practice'
        type_col = 'type' if 'type' in questions_df.columns else 'q_type'

        if questions_df.empty:
            ui.notify("등록된 문제가 없습니다. (DB 확인 필요)", type='warning')
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
        
        # 상태 초기화
        self.submission_stage = 0
        self.requested_hints = set()
        self.viewed_options_idx = set()
        self.unknown_words = set()
        self.first_answer = ""
        self.final_answer = ""
        self.start_time = time.time()
        
        self.render_question_page()

    # --- [화면 3] 문제 풀이 (보기 -> 지문 순서) ---
    def render_question_page(self):
        self.main_container.clear()
        q = self.current_q
        
        with self.main_container:
            # 상단 헤더
            with ui.row().classes('w-full justify-between items-center mb-2'):
                ui.button('그만하기', on_click=self.render_menu_selection).props('flat dense icon=close color=grey')
                badge_color = 'red' if self.mode == 'mock' else 'indigo'
                ui.badge(f"{self.mode.upper()} MODE").props(f'color={badge_color} outline')
            
            # 발문
            q_text = q.get('question_text', '다음 글을 읽고 물음에 답하시오.')
            ui.label(q_text).classes('text-lg font-bold mb-4')

            # [변경] 1. 보기(Options) 영역 먼저 배치
            self.render_options_area(q)

            ui.separator().classes('my-6')

            # 2. 추가 지문 (Extra Content) - 보기가 있더라도 박스 지문은 필요할 수 있음
            extra = q.get('extra_content')
            if extra and str(extra).lower() not in ['nan', 'none', '']:
                with ui.card().classes('w-full bg-gray-50 border border-gray-300 p-4 mb-6 shadow-sm'):
                    self.render_interactive_text(extra, "extra")

            # 3. 본문 (Passage)
            passage = str(q.get('passage', ''))
            sentences = re.split(r'(?<=[.?!])\s+', passage)
            trans_text = str(q.get('translation', ''))
            translations = re.split(r'(?<=[.?!])\s+', trans_text) if trans_text else []

            with ui.column().classes('w-full gap-4 mb-6'):
                for i, sent in enumerate(sentences):
                    if not sent.strip(): continue
                    
                    with ui.row().classes('w-full items-start no-wrap'):
                        # 힌트 버튼
                        is_requested = (i in self.requested_hints)
                        btn_color = 'green' if is_requested else 'grey'
                        btn_props = 'unelevated' if is_requested else 'outline'
                        
                        hint_btn = ui.button(f'{i+1}', on_click=lambda _, idx=i: self.toggle_hint(idx))\
                            .props(f'size=sm color={btn_color} {btn_props}')\
                            .classes('min-w-[28px] px-0 mr-2 mt-1 transition-colors')
                        
                        # 이미 제출했으면 힌트 버튼 비활성화
                        if self.submission_stage >= 1:
                            hint_btn.disable()

                        with ui.column().classes('flex-1'):
                            # 상호작용 가능한 문장 렌더링
                            self.render_interactive_text(sent, f"sent_{i}")
                            
                            # 힌트 요청 시 해석 표시
                            if self.submission_stage >= 1 and is_requested:
                                t_text = translations[i] if i < len(translations) else "(해석 없음)"
                                # ui.html 대신 style이 적용된 label 사용 권장 (여기선 html sanitize=False로 유지하되 주의)
                                ui.html(f"<div class='text-sm text-green-700 bg-green-50 p-2 rounded mt-1'>🇰🇷 {t_text}</div>")

            ui.separator().classes('my-4')

            # 4. 정답 선택 영역 (Radio Button) - 하단에 배치
            # 라디오 버튼은 텍스트만 보여주고, 실제 선택은 여기서 함
            opts = self.get_options_list(q)
            # 보기 텍스트만 추출해서 라디오 버튼 생성
            # (위의 보기 영역은 '읽기용', 여기는 '제출용')
            radio_options = [f"{i+1}. {opt}" for i, opt in enumerate(opts)]
            
            ui.label("정답을 선택하세요:").classes('font-bold text-gray-700')
            self.radio_comp = ui.radio(radio_options).props('color=indigo').classes('text-base ml-2')

            # 5. 제출 버튼 영역
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

            # 결과 화면
            self.result_container = ui.column().classes('w-full mt-4')
            if self.submission_stage == 2:
                self.render_result()

    def get_options_list(self, q):
        try:
            raw_opts = q.get('options')
            if isinstance(raw_opts, str):
                return json.loads(raw_opts.replace("'", '"')) if '[' in raw_opts else raw_opts.split('^')
            elif isinstance(raw_opts, list):
                return raw_opts
            return ["보기 로드 실패"]
        except: return ["보기 데이터 형식 오류"]

    def get_options_trans_list(self, q):
        # options_translation 필드가 있으면 가져오고, 없으면 빈 리스트
        try:
            raw = q.get('options_translation')
            if not raw or str(raw).lower() == 'nan': return []
            if isinstance(raw, str):
                return json.loads(raw.replace("'", '"')) if '[' in raw else raw.split('^')
            elif isinstance(raw, list):
                return raw
            return []
        except: return []

    def render_options_area(self, q):
        """보기 영역을 상호작용 가능하게 렌더링"""
        opts = self.get_options_list(q)
        trans = self.get_options_trans_list(q)
        
        ui.label("보기 (Options)").classes('font-bold text-gray-600 mb-2')
        
        with ui.column().classes('w-full gap-2 border p-4 rounded bg-white'):
            for i, opt_text in enumerate(opts):
                with ui.row().classes('items-center w-full'):
                    # 번호
                    ui.label(f"{i+1}.").classes('font-bold mr-2 text-gray-500')
                    
                    # 보기 텍스트 (단어 클릭 가능)
                    with ui.row().classes('flex-1 wrap items-baseline'):
                        self.render_interactive_text(opt_text, f"opt_{i}")
                    
                    # 해석 보기 버튼 (해석 데이터가 있을 때만)
                    if trans and i < len(trans):
                        has_viewed = (i in self.viewed_options_idx)
                        btn_icon = 'visibility' if not has_viewed else 'check'
                        
                        def show_opt_trans(idx=i, t_text=trans[i]):
                            self.viewed_options_idx.add(idx)
                            ui.notify(f"보기 {idx+1} 해석: {t_text}", type='info', timeout=5000)
                            # 버튼 아이콘 업데이트를 위해 페이지 리렌더링 (간단하게)
                            # 여기서는 notify로 띄우지만, 원하면 아래에 텍스트를 추가할 수도 있음.
                        
                        ui.button(icon=btn_icon, on_click=lambda _, idx=i: show_opt_trans(idx))\
                            .props('flat round size=sm color=grey').classes('ml-2')

    def toggle_hint(self, idx):
        if self.submission_stage > 0: return 
        if idx in self.requested_hints: self.requested_hints.remove(idx)
        else: self.requested_hints.add(idx)
        self.render_question_page()

    def get_selected_number(self):
        """라디오 버튼에서 선택된 번호 추출 (없으면 0)"""
        if not self.radio_comp or not self.radio_comp.value:
            return 0
        try:
            # "1. Apple" -> 1 추출
            return int(re.search(r'\d+', str(self.radio_comp.value)).group())
        except:
            return 0

    # --- [제출 로직] 1차 제출 ---
    def submit_handler(self):
        user_num = self.get_selected_number()
        if user_num == 0:
            ui.notify("보기를 선택해주세요!", type='warning')
            return
        
        # 힌트를 하나도 안 골랐으면 바로 최종 제출로 간주
        if len(self.requested_hints) == 0:
            self.first_answer = str(user_num)
            self.submit_final()
            return

        # 1차 답안 저장
        self.first_answer = str(user_num)
        self.submission_stage = 1
        
        ui.notify("요청하신 해석이 공개되었습니다. 답을 수정할 수 있습니다.", type='info')
        self.render_question_page()

    # --- [제출 로직] 최종 제출 ---
    def submit_final(self):
        user_num = self.get_selected_number()
        if user_num == 0:
            ui.notify("정답을 선택해주세요!", type='warning')
            return

        self.final_answer = str(user_num)
        
        # 정답 확인
        correct_ans = str(self.current_q['answer']).strip()
        is_correct = (self.final_answer == correct_ans)
        duration = int(time.time() - self.start_time)

        self.submission_stage = 2
        self.save_log(is_correct, duration)
        self.render_question_page()

    def save_log(self, is_correct, duration):
        if not supabase: return
        
        # 데이터 정제
        viewed_sent_str = ", ".join(map(str, sorted(list(self.requested_hints))))
        viewed_opt_str = ", ".join(map(str, sorted(list(self.viewed_options_idx))))
        
        # [변경] 태그 제거: 'sent_0_5_apple' -> 'apple'
        clean_words = set()
        for raw_w in self.unknown_words:
            parts = raw_w.split('_')
            if len(parts) > 1:
                clean_words.add(parts[-1]) # 맨 뒤가 단어
            else:
                clean_words.add(raw_w)
        unknown_str = ", ".join(sorted(list(clean_words)))

        kst = pytz.timezone('Asia/Seoul')
        now_kst = datetime.now(kst).strftime("%Y-%m-%d %H:%M:%S")

        # [변경] 새 DB 스키마에 맞춘 데이터
        log_data = {
            "timestamp": now_kst,
            "user_id": self.user_id,
            "problem_id": str(self.current_q['id']),
            "mode": self.mode,
            "is_correct": "O" if is_correct else "X",
            "first_answer": self.first_answer,
            "final_answer": self.final_answer,
            "viewed_sentences": viewed_sent_str,
            "viewed_options": viewed_opt_str,
            "unknown_words": unknown_str,
            "duration": duration
        }
        
        try:
            supabase.table('study_logs').insert(log_data).execute()
        except Exception as e:
            print(f"저장 실패: {e}")
            ui.notify(f"기록 저장 실패: {str(e)}", type='negative')

    def render_result(self):
        with self.result_container:
            ui.separator()
            correct_ans = str(self.current_q['answer']).strip()
            
            # 내가 쓴 답 (최종)
            is_correct = (self.final_answer == correct_ans)

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
                # 단어 정제 (특수문자 제외)
                clean_word = re.sub(r'[^\w]', '', word)
                unique_id = f"{prefix}_{idx}_{clean_word}"
                
                lbl = ui.label(word).classes('word-span text-lg leading-relaxed cursor-pointer rounded px-1 transition-colors')
                
                # 이미 모르는 단어로 체크했으면 하이라이트
                if unique_id in self.unknown_words: 
                    lbl.classes('highlight')
                
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