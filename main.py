from nicegui import ui, app
import pandas as pd
import re
from datetime import datetime
import time # 시간 측정을 위해 추가
import os
import json
import pytz 
from supabase import create_client, Client # Supabase 라이브러리

# ===================== [1] 설정 및 데이터 로드 (Supabase) =====================

# 🛑 [중요] 아까 복사한 Supabase 정보로 여기를 바꿔주세요!
SUPABASE_URL = "https://your-project-url.supabase.co"
SUPABASE_KEY = "your-anon-public-key"

# Supabase 클라이언트 연결
try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"Supabase 연결 실패: {e}")
    supabase = None

# ---------------------------------------------------------
# 기존 load_data, load_users, get_student_sheet 함수는 
# 이제 필요 없으므로 삭제하거나 Supabase용으로 대체합니다.
# ---------------------------------------------------------

def fetch_questions_from_db():
    """Supabase의 'questions' 테이블에서 모든 문제 가져오기"""
    if not supabase: return pd.DataFrame()
    try:
        response = supabase.table('questions').select('*').execute()
        # 데이터가 있으면 DataFrame으로 변환
        if response.data:
            df = pd.DataFrame(response.data)
            return df
        return pd.DataFrame()
    except Exception as e:
        print(f"문제 로드 오류: {e}")
        return pd.DataFrame()

def fetch_user_from_db(user_id, password):
    """로그인 검증"""
    if not supabase: return None
    try:
        response = supabase.table('users').select('*').eq('id', user_id).eq('password', password).execute()
        if response.data:
            return response.data[0] # 유저 정보 딕셔너리 리턴
        return None
    except Exception as e:
        print(f"로그인 오류: {e}")
        return None

def fetch_solved_ids(user_id, mode):
    """
    해당 유저가 '특정 모드(mock/practice)'에서 이미 푼 문제 ID 목록 가져오기
    -> 이것으로 모의고사와 유형연습 기록을 분리합니다.
    """
    if not supabase: return set()
    try:
        # user_id와 mode가 일치하는 기록만 가져옴
        response = supabase.table('study_logs').select('question_id').eq('user_id', user_id).eq('mode', mode).execute()
        if response.data:
            return set(item['question_id'] for item in response.data)
        return set()
    except Exception as e:
        print(f"기록 로드 오류: {e}")
        return set()

# 전역 변수로 데이터프레임 관리 (캐싱 역할)
questions_df = pd.DataFrame() 

# ===================== [2] 앱 로직 클래스 =====================
class HomeworkApp:
    def __init__(self):
        self.user_info = None  # 로그인한 유저 전체 정보
        self.user_id = ""      
        
        # 상태 관리 변수들
        self.mode = "practice" # 'mock'(모의고사) or 'practice'(유형연습)
        self.current_q = None
        self.start_time = 0    # 문제 로딩 시점 (초)
        
        # 2단계 제출 시스템을 위한 변수들
        self.submission_stage = 0 # 0: 풀이중, 1: 1차제출(힌트오픈), 2: 최종완료
        self.first_answer = None  # 1차 답안
        self.requested_hints = set() # 힌트(해석)를 요청한 문장 인덱스들
        
        self.unknown_words = set()
        
        # UI 컨테이너
        self.main_container = None
        self.sidebar_label = None
        self.log_label = None
        self.result_container = None 

    # --- [화면 1] 로그인 화면 ---
    def start_login(self):
        self.main_container.clear()
        with self.main_container:
            ui.markdown("# 🔒 1등급 영어 과외").classes('text-center w-full mb-6')
            
            with ui.card().classes('w-full max-w-sm mx-auto p-6 flex flex-col gap-3 shadow-lg'):
                ui.label("학생 로그인").classes('text-xl font-bold mb-2 self-center')
                
                self.id_input = ui.input("아이디").classes('w-full') 
                self.pw_input = ui.input("비밀번호", password=True).classes('w-full')
                self.pw_input.on('keydown.enter', self.process_login)
                
                ui.button("입장하기", on_click=self.process_login).props('color=indigo push').classes('w-full mt-4 font-bold')

    def process_login(self):
        input_id = self.id_input.value
        input_pw = self.pw_input.value
        
        user_data = fetch_user_from_db(input_id, input_pw)
        
        if user_data:
            self.user_info = user_data
            self.user_id = user_data['id']
            self.user_name = user_data['name']
            
            ui.notify(f"환영합니다, {self.user_name} 학생!", type='positive')
            
            # 로그인 성공 시 전체 문제 데이터 한 번 로드 (캐싱)
            global questions_df
            questions_df = fetch_questions_from_db()
            
            self.update_sidebar()
            self.render_menu() 
        else:
            ui.notify("아이디 또는 비밀번호를 확인해주세요.", type='negative')

    def update_sidebar(self):
        if self.sidebar_label:
            self.sidebar_label.set_text(f"👤 {self.user_name}")

    # --- [화면 2] 메뉴 선택 화면 ---
    def render_menu(self):
        self.main_container.clear()
        
        # 메뉴 들어올 때마다 문제 데이터 갱신 (관리자가 새로 올렸을 수 있으니)
        global questions_df
        questions_df = fetch_questions_from_db()

        with self.main_container:
            ui.markdown(f"## 👋 학습 모드 선택").classes('mb-2')
            ui.label("원하는 학습 방식을 선택하세요.").classes('text-gray-500 mb-8')
            
            # 모드 선택 버튼들
            with ui.row().classes('w-full gap-4 justify-center'):
                # 1. 유형별 연습 (Practice)
                with ui.card().classes('w-64 cursor-pointer hover:shadow-xl transition p-6 flex flex-col items-center border-t-4 border-blue-500'):
                    ui.icon('category', size='3em', color='blue')
                    ui.label('유형별 격파').classes('font-bold text-lg mt-3')
                    ui.label('빈칸, 순서, 삽입 등\n취약 유형 집중 공략').classes('text-center text-sm text-gray-400 mt-2 whitespace-pre-line')
                    ui.button("시작하기", on_click=lambda: self.select_practice_type()).props('flat color=blue').classes('w-full mt-4')

                # 2. 실전 모의고사 (Mock) - 구현 예시
                with ui.card().classes('w-64 cursor-pointer hover:shadow-xl transition p-6 flex flex-col items-center border-t-4 border-red-500'):
                    ui.icon('timer', size='3em', color='red')
                    ui.label('실전 모의고사').classes('font-bold text-lg mt-3')
                    ui.label('랜덤 하프 모의고사\n(기록 분리됨)').classes('text-center text-sm text-gray-400 mt-2 whitespace-pre-line')
                    ui.button("시작하기", on_click=lambda: self.start_mock_exam()).props('flat color=red').classes('w-full mt-4')

            ui.button("로그아웃", on_click=self.logout).props('outline color=grey').classes('w-full max-w-xs mx-auto mt-12')

    def select_practice_type(self):
        """유형별 연습 선택 시 세부 유형 필터링"""
        self.mode = 'practice'
        
        # 현재 DB에 있는 유형들만 추출
        if questions_df.empty:
            ui.notify("등록된 문제가 없습니다.", type='warning')
            return
            
        available_types = questions_df['q_type'].unique().tolist()
        
        self.main_container.clear()
        with self.main_container:
            ui.button('⬅ 뒤로가기', on_click=self.render_menu).props('flat icon=arrow_back')
            ui.markdown("### 🎯 공략할 유형을 선택하세요")
            
            with ui.grid(columns=2).classes('w-full gap-3 mt-4'):
                for q_type in available_types:
                    # 해당 유형 문제 수 계산
                    count = len(questions_df[questions_df['q_type'] == q_type])
                    btn_text = f"{q_type} ({count}문제)"
                    
                    ui.button(btn_text, on_click=lambda t=q_type: self.load_question_sequence(t)).props('outline color=indigo').classes('h-16 text-lg')

    def start_mock_exam(self):
        """모의고사 모드 시작"""
        self.mode = 'mock'
        # 유형 구분 없이 로드하되, 모의고사 모드 기록을 참조하여 안 푼 것 가져옴
        self.load_question_sequence(target_type=None)

    def logout(self):
        self.user_id = ""
        self.user_info = None
        self.start_login()

    # --- [로직] 문제 로드 및 필터링 ---
    def load_question_sequence(self, target_type=None):
        """조건에 맞는 안 푼 문제 하나를 가져와서 렌더링"""
        global questions_df
        if questions_df.empty: return

        # 1. 푼 문제 ID 목록 가져오기 (현재 모드 기준)
        solved_ids = fetch_solved_ids(self.user_id, self.mode)
        
        # 2. 필터링 (유형 & 안 푼 문제)
        cond = ~questions_df['id'].isin(solved_ids)
        if target_type:
            cond = cond & (questions_df['q_type'] == target_type)
        
        remaining_df = questions_df[cond]
        
        if remaining_df.empty:
            ui.notify("선택하신 유형의 모든 문제를 풀었습니다! 🎉", type='positive')
            self.render_menu()
            return

        # 3. 랜덤으로 하나 선택
        self.current_q = remaining_df.sample(1).iloc[0]
        
        # 4. 상태 초기화
        self.submission_stage = 0
        self.first_answer = None
        self.requested_hints = set()
        self.unknown_words = set()
        self.start_time = time.time() # 시간 측정 시작
        
        self.render_question_page()

    # --- [화면 3] 문제 풀이 화면 (핵심 UI) ---
    def render_question_page(self):
        self.main_container.clear()
        q = self.current_q
        
        with self.main_container:
            # 상단 헤더
            with ui.row().classes('w-full justify-between items-center mb-4'):
                ui.button('그만하기', on_click=self.render_menu).props('flat dense icon=close color=grey')
                # 모드 표시 배지
                badge_color = 'red' if self.mode == 'mock' else 'blue'
                badge_text = '실전 모의고사' if self.mode == 'mock' else f"{q['q_type']} 연습"
                ui.badge(badge_text).props(f'color={badge_color}')
            
            # 발문 (Question Text)
            q_text = q.get('question_text', '다음 글을 읽고 물음에 답하시오.')
            if not q_text: q_text = '다음 글을 읽고 물음에 답하시오.'
            ui.label(q_text).classes('text-lg font-bold mb-2')
            
            ui.separator().classes('mb-4')

            # --- [추가] 박스형 지문 (순서/삽입 등) ---
            extra = q.get('extra_content')
            if extra and str(extra).lower() != 'nan':
                with ui.card().classes('w-full bg-gray-50 border border-gray-300 p-4 mb-6 shadow-sm'):
                    self.render_interactive_text(extra, "extra")

            # --- 본문 (Passage) ---
            # 문장 단위 분리 로직 (마침표 기준, 개선 가능)
            sentences = re.split(r'(?<=[.?!])\s+', str(q['passage']))
            # 해석 데이터가 없으면 빈 리스트 처리
            trans_text = str(q.get('translation', ''))
            translations = re.split(r'(?<=[.?!])\s+', trans_text) if trans_text else []

            with ui.column().classes('w-full gap-3 mb-6'):
                for i, sent in enumerate(sentences):
                    if not sent.strip(): continue
                    
                    with ui.row().classes('w-full items-start no-wrap'):
                        # 힌트 버튼 (2단계 시스템 핵심)
                        # Stage 0: 누르면 색칠됨 (요청 상태)
                        # Stage 1: 요청한 것만 해석 보임
                        btn_color = 'green' if i in self.requested_hints else 'grey'
                        btn_props = 'unelevated' if i in self.requested_hints else 'outline'
                        
                        hint_btn = ui.button(f'({i+1})', on_click=lambda _, idx=i: self.toggle_hint_request(idx))\
                            .props(f'size=sm color={btn_color} {btn_props}')\
                            .classes('min-w-[30px] px-1 mr-2 mt-1 transition-colors')
                        
                        # 힌트 버튼 비활성화 (Stage 1 이상이면 못 바꿈)
                        if self.submission_stage >= 1:
                            hint_btn.disable()

                        with ui.column().classes('flex-1'):
                            # 영어 문장 (단어 클릭 가능)
                            self.render_interactive_text(sent, f"sent_{i}")
                            
                            # 한글 해석 (Stage 1 이상이고, 요청했을 때만 보임)
                            if self.submission_stage >= 1 and i in self.requested_hints:
                                t_text = translations[i] if i < len(translations) else "(해석 없음)"
                                ui.label(f"└ {t_text}").classes('text-sm text-green-700 mt-1 bg-green-50 p-1 rounded')

            ui.separator().classes('my-4')

            # --- 보기 (Options) ---
            try:
                # JSON 배열이 문자열로 들어올 경우 파싱, 리스트면 그대로 사용
                raw_opts = q.get('options')
                if isinstance(raw_opts, str):
                    opts = json.loads(raw_opts)
                elif isinstance(raw_opts, list):
                    opts = raw_opts
                else:
                    opts = []
            except: 
                opts = ["보기 데이터 오류"]

            # 라디오 버튼 값을 바인딩할 변수
            self.radio_val = ui.radio(opts).props('color=indigo').classes('text-base')

            # --- 제출 버튼 영역 (상태에 따라 변경) ---
            with ui.row().classes('w-full mt-6 justify-center'):
                if self.submission_stage == 0:
                    # 1단계: 힌트 보기 및 1차 선택
                    ui.button("1차 제출 (힌트 확인)", on_click=self.submit_stage_1)\
                        .props('color=indigo size=lg icon=visibility').classes('w-full max-w-md font-bold')
                        
                elif self.submission_stage == 1:
                    # 2단계: 최종 제출
                    ui.button("최종 정답 제출", on_click=self.submit_final)\
                        .props('color=red size=lg icon=check').classes('w-full max-w-md font-bold')
                
                else:
                    # 완료: 다음 문제
                    ui.button("➡️ 다음 문제 풀기", on_click=lambda: self.load_question_sequence(q['q_type'] if self.mode == 'practice' else None))\
                        .props('color=green size=lg').classes('w-full max-w-md font-bold')

            # 결과 화면 (하단에 붙음)
            self.result_container = ui.column().classes('w-full mt-4')
            if self.submission_stage == 2:
                self.render_result()

    # --- [로직] 힌트 요청 토글 ---
    def toggle_hint_request(self, idx):
        if self.submission_stage > 0: return # 이미 제출했으면 못 바꿈
        
        if idx in self.requested_hints:
            self.requested_hints.remove(idx)
        else:
            self.requested_hints.add(idx)
        
        # 화면 전체 리로드 대신 버튼만 바꾸면 좋겠지만, 
        # NiceGUI 구조상 전체 리렌더링이 가장 버그가 적음 (깜빡임은 있음)
        self.render_question_page()

    # --- [로직] 1차 제출 ---
    def submit_stage_1(self):
        if not self.radio_val.value:
            ui.notify("보기를 선택해주세요!", type='warning')
            return
            
        # 선택한 보기에서 번호 추출 (예: "1. Apple" -> 1)
        sel_text = self.radio_val.value
        try:
            # 숫자만 추출하거나 첫 글자 확인
            sel_num = int(re.search(r'\d+', sel_text).group())
        except:
            sel_num = 0

        self.first_answer = sel_num
        self.submission_stage = 1
        
        ui.notify("힌트(해석)가 공개되었습니다. 답을 수정할 수 있습니다.", type='info')
        self.render_question_page() # 화면 갱신해서 해석 보여줌

    # --- [로직] 최종 제출 ---
    def submit_final(self):
        if not self.radio_val.value:
            ui.notify("최종 정답을 선택해주세요!", type='warning')
            return

        # 걸린 시간 계산
        duration = int(time.time() - self.start_time)

        # 최종 답 추출
        sel_text = self.radio_val.value
        try:
            final_num = int(re.search(r'\d+', sel_text).group())
        except:
            final_num = 0

        correct_ans = int(self.current_q['answer'])
        is_correct = (final_num == correct_ans)

        self.submission_stage = 2
        
        # DB 저장 (Supabase)
        self.save_log_to_db(final_num, is_correct, duration)
        
        # 결과 화면 렌더링
        self.render_question_page()

    def save_log_to_db(self, final_num, is_correct, duration):
        """Supabase study_logs 테이블에 저장"""
        if not supabase: return
        
        log_data = {
            "user_id": self.user_id,
            "question_id": self.current_q['id'],
            "mode": self.mode,
            "stage1_answer": self.first_answer,
            "final_answer": final_num,
            "is_correct": is_correct,
            "viewed_hints": list(self.requested_hints), # set -> list 변환
            "duration": duration,
            "timestamp": datetime.now(pytz.timezone('Asia/Seoul')).isoformat()
        }
        
        try:
            supabase.table('study_logs').insert(log_data).execute()
        except Exception as e:
            print(f"로그 저장 실패: {e}")
            ui.notify("결과 저장 실패 (인터넷 확인)", type='negative')

    def render_result(self):
        with self.result_container:
            ui.separator()
            correct_ans = int(self.current_q['answer'])
            is_correct = (self.first_answer == correct_ans) # 1차인지 최종인지 기준은 정책에 따라 다름. 여기선 최종(저장된값)은 DB가고 화면엔 그냥 결과표시
            
            # 실제 정답 여부는 DB에 저장된 final_answer 기준
            final_sel_text = self.radio_val.value
            final_num = int(re.search(r'\d+', final_sel_text).group()) if final_sel_text else 0
            real_correct = (final_num == correct_ans)

            if real_correct:
                ui.markdown("### 🎉 정답입니다!").classes('text-green-600')
                ui.run_javascript('confetti()') 
            else:
                ui.markdown(f"### 💥 아쉽네요. 정답은 **{correct_ans}번** 입니다.").classes('text-red-600')
            
            # 해설 박스
            expl = self.current_q.get('explanation', '')
            with ui.expansion('💡 해설 보기', icon='help', value=True).classes('w-full bg-blue-50'):
                ui.markdown(expl).classes('p-4')

    # --- [유틸] 단어 클릭 등 ---
    def render_interactive_text(self, text, prefix):
        words = str(text).split()
        with ui.row().classes('gap-1 wrap items-baseline w-full'): 
            for idx, word in enumerate(words):
                # 특수문자 제거 후 순수 단어 추출
                clean_word = re.sub(r'[^\w]', '', word)
                unique_id = f"{prefix}_{idx}_{clean_word}"
                
                # HTML 태그(<u> 등)가 있으면 ui.html로, 아니면 ui.label로
                if '<' in word and '>' in word:
                    lbl = ui.html(word).classes('word-span text-lg leading-relaxed')
                else:
                    lbl = ui.label(word).classes('word-span text-lg leading-relaxed')
                
                # 단어 클릭 시 노란 형광펜
                if unique_id in self.unknown_words: 
                    lbl.classes('highlight')
                
                # 클릭 이벤트 (lambda로 스코프 고정)
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
    # 스타일 정의 (형광펜 등)
    ui.add_head_html('''
        <style>
            @import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;700&display=swap');
            body { font-family: 'Noto Sans KR', sans-serif; background-color: #f8f9fa; }
            .highlight { background-color: #fef08a !important; color: black !important; border-radius: 4px; padding: 0 2px; }
            .word-span { cursor: pointer; transition: all 0.2s; padding: 2px 1px; border-radius: 4px; }
            .word-span:hover { background-color: #e0f2fe; color: #0284c7; }
        </style>
        <script src="https://cdn.jsdelivr.net/npm/canvas-confetti@1.5.1/dist/confetti.browser.min.js"></script>
    ''')

    app_logic = HomeworkApp()

    # 왼쪽 사이드바
    with ui.left_drawer(value=True).props('width=240 bordered').classes('bg-white q-pa-md') as drawer:
        app_logic.sidebar_label = ui.label("👤 로그인 필요").classes('font-bold text-lg mb-4')
        ui.separator().classes('mb-4')
        ui.label("학습 현황").classes('text-xs text-gray-400 font-bold mb-2')
        # 여기에 나중에 통계 같은거 넣으면 됨
        ui.label("오늘도 화이팅! 🔥").classes('text-sm text-gray-600')

    # 헤더
    with ui.header().classes('bg-white text-black shadow-sm h-14'):
        ui.button(on_click=lambda: drawer.toggle(), icon='menu').props('flat color=black dense')
        ui.label('수능 영어 마스터').classes('text-lg font-bold ml-2 text-indigo-700')

    # 메인 컨테이너 설정
    app_logic.main_container = ui.column().classes('w-full max-w-screen-md mx-auto p-4 bg-white min-h-screen shadow-sm')
    
    # 시작은 로그인 화면
    app_logic.start_login()

ui.run(title="영어 숙제", host="0.0.0.0", port=int(os.environ.get("PORT", 8080)), reload=False, show=False)