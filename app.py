import streamlit as st
import feedparser
import ssl
import random
import json
import os
import io
import re
import wave
from datetime import date, datetime, timedelta
from openai import OpenAI

# ──────────────────────────────────────────────
# 0. 기본 세팅
# ──────────────────────────────────────────────
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

PROGRESS_FILE = "hojun_progress.json"
LIB_DIR = "broadcasts"
LIB_INDEX = os.path.join(LIB_DIR, "index.json")

# 손예진 톤 연기 디렉션 (실존 인물 복제 X, '분위기'만 연출)
VOICE_INSTRUCTIONS = (
    "You are a bright, warm Korean actress in her late 20s hosting a cozy English "
    "radio show — the sincere, slightly playful warmth of a beloved Korean drama lead. "
    "Speak with gentle energy, never shouting. English lines: clear, natural American "
    "pronunciation, a touch slower and well-articulated. Korean lines: tender and lively, "
    "like talking to a close friend named 호준. When you say '따라 해보세요', slow down and "
    "articulate each word clearly so it is easy to repeat."
)


# 추천 보이스 (발랄 여성 톤 우선)
VOICE_OPTIONS = {
    "nova":    "🌟 nova — 밝고 활기찬 (발랄 여배우)",
    "coral":   "🍑 coral — 친근하고 살짝 달콤",
    "shimmer": "✨ shimmer — 부드럽고 경쾌",
    "sage":    "🌿 sage — 차분하고 지적",
    "ballad":  "🎵 ballad — 감성 낭독",
    "marin":   "🌊 marin — 맑고 고음질(신규)",
    "fable":   "📖 fable — 영국 억양 이야기꾼",
    "alloy":   "⚪ alloy — 중성적 만능",
}

# ──────────────────────────────────────────────
# 1. 구글 드라이브 연동 (서버 대용 저장소)
#    secrets에 gcp_service_account + DRIVE_FOLDER_ID 가 있으면 자동 활성화
# ──────────────────────────────────────────────
def get_drive():
    if "gcp_service_account" not in st.secrets or not st.secrets.get("DRIVE_FOLDER_ID"):
        return None
    try:
        from google.oauth2 import service_account
        from googleapiclient.discovery import build
        creds = service_account.Credentials.from_service_account_info(
            dict(st.secrets["gcp_service_account"]),
            scopes=["https://www.googleapis.com/auth/drive"],
        )
        return build("drive", "v3", credentials=creds, cache_discovery=False)
    except Exception:
        return None

DRIVE = get_drive()
DRIVE_FOLDER_ID = st.secrets.get("DRIVE_FOLDER_ID", "") if "DRIVE_FOLDER_ID" in st.secrets else ""

def _drive_find(name):
    """폴더 안에서 이름으로 파일 찾기 → file_id or None"""
    q = f"name='{name}' and '{DRIVE_FOLDER_ID}' in parents and trashed=false"
    res = DRIVE.files().list(q=q, fields="files(id,name)", pageSize=1).execute()
    files = res.get("files", [])
    return files[0]["id"] if files else None

def drive_upload(name, data_bytes, mimetype):
    from googleapiclient.http import MediaIoBaseUpload
    media = MediaIoBaseUpload(io.BytesIO(data_bytes), mimetype=mimetype, resumable=False)
    existing = _drive_find(name)
    if existing:
        DRIVE.files().update(fileId=existing, media_body=media).execute()
        return existing
    meta = {"name": name, "parents": [DRIVE_FOLDER_ID]}
    f = DRIVE.files().create(body=meta, media_body=media, fields="id").execute()
    return f["id"]

def drive_download(file_id):
    from googleapiclient.http import MediaIoBaseDownload
    buf = io.BytesIO()
    req = DRIVE.files().get_media(fileId=file_id)
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue()

def drive_delete(file_id):
    try:
        DRIVE.files().delete(fileId=file_id).execute()
    except Exception:
        pass

# ──────────────────────────────────────────────
# 2. 진도/족보 영구 저장
# ──────────────────────────────────────────────
def load_progress():
    # 드라이브 연동 시 드라이브에서 먼저 복원
    if DRIVE:
        try:
            fid = _drive_find(PROGRESS_FILE)
            if fid:
                return json.loads(drive_download(fid).decode("utf-8"))
        except Exception:
            pass
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return None

def save_progress():
    data = {
        "patterns": st.session_state['hojun_past_patterns'],
        "words": st.session_state['hojun_past_words'],
        "day_count": st.session_state['day_count'],
        "last_date": st.session_state['last_date'],
        "total_learned": st.session_state['total_learned'],
        "voice": st.session_state['voice'],
    }
    payload = json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")
    # 로컬 저장 (캐시/폴백)
    try:
        with open(PROGRESS_FILE, "wb") as f:
            f.write(payload)
    except Exception:
        pass
    # 드라이브 저장 (영구 보관)
    if DRIVE:
        try:
            drive_upload(PROGRESS_FILE, payload, "application/json")
        except Exception:
            pass

# ── 보관함 (드라이브 우선, 없으면 로컬) ──
def load_library():
    if DRIVE:
        try:
            fid = _drive_find("index.json")
            if fid:
                return json.loads(drive_download(fid).decode("utf-8"))
        except Exception:
            pass
        return []
    if os.path.exists(LIB_INDEX):
        try:
            with open(LIB_INDEX, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return []

def _write_index(lib):
    if DRIVE:
        drive_upload("index.json", json.dumps(lib, ensure_ascii=False, indent=2).encode("utf-8"), "application/json")
    else:
        os.makedirs(LIB_DIR, exist_ok=True)
        with open(LIB_INDEX, "w", encoding="utf-8") as f:
            json.dump(lib, f, ensure_ascii=False, indent=2)

def save_broadcast(script, audio_bytes, theme):
    try:
        bid = datetime.now().strftime("%Y%m%d_%H%M%S")
        fname = f"영라디오_{bid}.wav"
        entry = {"id": bid, "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "theme": theme, "script": script, "audio": fname}
        if DRIVE:
            entry["drive_file_id"] = drive_upload(fname, audio_bytes, "audio/wav")
        else:
            os.makedirs(LIB_DIR, exist_ok=True)
            with open(os.path.join(LIB_DIR, fname), "wb") as f:
                f.write(audio_bytes)
        lib = load_library()
        lib.insert(0, entry)
        _write_index(lib)
    except Exception as e:
        st.warning(f"보관함 저장 중 문제: {e}")

def read_broadcast_audio(entry):
    if DRIVE and entry.get("drive_file_id"):
        try:
            return drive_download(entry["drive_file_id"])
        except Exception:
            return None
    path = os.path.join(LIB_DIR, entry["audio"])
    if os.path.exists(path):
        with open(path, "rb") as f:
            return f.read()
    return None

def delete_broadcast(entry):
    try:
        if DRIVE and entry.get("drive_file_id"):
            drive_delete(entry["drive_file_id"])
        else:
            p = os.path.join(LIB_DIR, entry["audio"])
            if os.path.exists(p):
                os.remove(p)
        lib = [b for b in load_library() if b["id"] != entry["id"]]
        _write_index(lib)
    except Exception:
        pass

# ──────────────────────────────────────────────
# 3. 세션 초기화
# ──────────────────────────────────────────────
_saved = load_progress()
if 'hojun_past_patterns' not in st.session_state:
    st.session_state['hojun_past_patterns'] = (_saved or {}).get("patterns", [
        {"pattern": "I'm planning to", "meaning": "~할 계획이에요"},
        {"pattern": "I'm calling to", "meaning": "~하려고 전화드렸습니다"},
        {"pattern": "What do you think about ~?", "meaning": "~에 대해 어떻게 생각하세요?"},
        {"pattern": "Why don't we ~?", "meaning": "~하는 게 어떨까요?"},
        {"pattern": "Could you please tell me about ~?", "meaning": "~에 대해 알려주실 수 있나요?"},
    ])
if 'hojun_past_words' not in st.session_state:
    st.session_state['hojun_past_words'] = (_saved or {}).get("words", [
        {"word": "Potential", "meaning": "잠재력"},
        {"word": "Boost", "meaning": "증대시키다"},
        {"word": "Streamline", "meaning": "간소화하다"},
        {"word": "Prospective", "meaning": "잠재적인 (고객/파트너)"},
        {"word": "Get back on track", "meaning": "궤도에 오르다"},
    ])
if 'day_count' not in st.session_state:
    st.session_state['day_count'] = (_saved or {}).get("day_count", 0)
if 'last_date' not in st.session_state:
    st.session_state['last_date'] = (_saved or {}).get("last_date", "")
if 'total_learned' not in st.session_state:
    st.session_state['total_learned'] = (_saved or {}).get("total_learned", 0)
if 'voice' not in st.session_state:
    st.session_state['voice'] = (_saved or {}).get("voice", "nova")
for k in ['current_script', 'current_audio', 'current_theme']:
    if k not in st.session_state:
        st.session_state[k] = None

# ──────────────────────────────────────────────
# 3-2. 복습 엔진 (간격 반복 / SRS) + 치트키 예문
# ──────────────────────────────────────────────
def _ensure_srs(item):
    """기존 족보 항목에 복습용 필드가 없으면 기본값 부여 (마이그레이션)."""
    item.setdefault('interval', 1)          # 현재 복습 간격(일)
    item.setdefault('reps', 0)              # 복습 성공 횟수
    item.setdefault('due', str(date.today()))  # 다음 복습 예정일
    item.setdefault('last', '')             # 마지막 복습일
    item.setdefault('ex', [])              # 치트키가 들어간 예문 [{en, ko}]

for _it in st.session_state['hojun_past_patterns']:
    _ensure_srs(_it)
for _it in st.session_state['hojun_past_words']:
    _ensure_srs(_it)

def all_review_items():
    """(종류, dict, 표현, 뜻) 통합 리스트."""
    items = []
    for p in st.session_state['hojun_past_patterns']:
        items.append(("pattern", p, p['pattern'], p['meaning']))
    for w in st.session_state['hojun_past_words']:
        items.append(("word", w, w['word'], w['meaning']))
    return items

def get_due_items():
    today = str(date.today())
    return [it for it in all_review_items() if it[1].get('due', today) <= today]

def review_item(d, grade):
    """grade: 'easy'(기억남) → 간격 늘림 / 'again'(다시) → 1일로 리셋."""
    if grade == "easy":
        d['interval'] = max(1, int(round(d.get('interval', 1) * 2.2)))
        d['reps'] = d.get('reps', 0) + 1
    else:
        d['interval'] = 1
    d['last'] = str(date.today())
    d['due'] = str(date.today() + timedelta(days=d['interval']))

def make_cheat_sentences(expr, meaning):
    """치트키 표현이 '반드시 들어간' 실전 비즈니스 문장 2개 생성 → [{en, ko}]."""
    prompt = (
        f"표현 '{expr}' (뜻: {meaning}) 이(가) 반드시 포함된, 호준 씨(창호 B2B 영업팀장)가 실제로 쓸 법한 "
        f"비즈니스 영어 문장 2개를 만들어라. 각 문장의 자연스러운 한국어 해석도 붙여라. "
        f'반드시 아래 JSON 배열로만 출력(설명 금지): [{{"en":"...","ko":"..."}},{{"en":"...","ko":"..."}}]'
    )
    try:
        resp = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
        )
        txt = resp.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
        data = json.loads(txt)
        return [{"en": d.get("en", ""), "ko": d.get("ko", "")} for d in data][:2]
    except Exception:
        return []

def get_yesterday_items():
    """어제 새로 배운 표현 (60초 복습용)."""
    y = str(date.today() - timedelta(days=1))
    res = []
    for _t, d, expr, mean in all_review_items():
        if d.get('added', '') == y:
            res.append((expr, mean))
    return res

def pick_today_formula(exclude=None):
    """오늘 집중할 회화 공식 1개 선택: 복습 타이밍(due) 우선 → 가장 오래 안 본 것 → 랜덤."""
    patterns = st.session_state['hojun_past_patterns']
    if not patterns:
        return None
    exclude = exclude or set()
    cand = [p for p in patterns if p['pattern'] not in exclude] or patterns
    today = str(date.today())
    due = [p for p in cand if p.get('due', today) <= today]
    pool = due if due else cand
    # 가장 오래 복습 안 한 것 우선 (last 오름차순), 동률이면 랜덤
    pool = sorted(pool, key=lambda p: (p.get('last', ''), random.random()))
    return pool[0]

# ── 3단계: 한국어→영어 말하기 퀴즈 + 음성 채점 ──
def generate_quiz():
    items = all_review_items()
    hint = ""
    if items:
        _t, d, expr, mean = random.choice(items)
        hint = f"가능하면 학습자의 족보 표현 '{expr}'({mean})를 자연스럽게 쓰게 되는 상황으로. "
    prompt = (
        "호준 씨(KCC 창호 B2B 영업팀장)를 위한 '한국어→영어 말하기' 퀴즈 1개를 만들어라. "
        f"{hint}실제 영업/업무에서 쓸 법한 자연스러운 한국어 문장 1개와 모범 영어 답안을 주되, "
        '아래 JSON으로만 출력(설명 금지): {"ko":"...","answer":"..."}'
    )
    try:
        resp = client.chat.completions.create(model="gpt-4o-mini",
                                              messages=[{"role": "user", "content": prompt}], temperature=0.7)
        txt = resp.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(txt)
    except Exception:
        return {"ko": "다음 주까지 견적서를 보내드리겠습니다.", "answer": "I'll send you the quote by next week."}

def transcribe_audio(audio_bytes):
    bio = io.BytesIO(audio_bytes); bio.name = "speech.wav"
    tr = client.audio.transcriptions.create(model="whisper-1", file=bio, language="en")
    return tr.text

def grade_answer(ko, model_answer, user_said):
    prompt = (
        f"한국어 문장: {ko}\n모범 영어 답안: {model_answer}\n학습자가 말한 영어(STT 결과): {user_said}\n\n"
        "학습자의 영어가 의미를 제대로 전달했는지 너그럽지만 정확하게 평가하라(약간의 표현 차이는 정답으로 인정). "
        '아래 JSON으로만 출력: {"score": 0~100 정수, "verdict": "정답" 또는 "거의" 또는 "다시", '
        '"feedback": "한국어로 따뜻하고 구체적인 1~2문장", "better": "더 자연스러운 영어 예시 1개"}'
    )
    try:
        resp = client.chat.completions.create(model="gpt-4o-mini",
                                              messages=[{"role": "user", "content": prompt}], temperature=0.4)
        txt = resp.choices[0].message.content.strip().replace("```json", "").replace("```", "").strip()
        return json.loads(txt)
    except Exception:
        return {"score": 0, "verdict": "다시", "feedback": "채점 중 문제가 생겼어요. 다시 해볼까요?", "better": model_answer}
# ──────────────────────────────────────────────
# 4. 방송 코너 정의
# ──────────────────────────────────────────────
# 회화 공식 팩 — 비기너(80%) → 확장(90%) + 비즈니스(옵션)
# 비기너: 회화의 약 80%를 커버하는 핵심 골격
FORMULAS_BEGINNER = [
    {"pattern": "The way I see it ~", "meaning": "제가 보기엔 ~ (의견)"},
    {"pattern": "If you ask me ~", "meaning": "제 생각을 말하자면 ~"},
    {"pattern": "What I mean is ~", "meaning": "제 말은 ~라는 거예요"},
    {"pattern": "I see your point, but ~", "meaning": "무슨 말인지 알지만 ~ (부분 동의)"},
    {"pattern": "I couldn't agree more", "meaning": "전적으로 동의해요"},
    {"pattern": "I'm not so sure about that", "meaning": "그건 잘 모르겠어요 (완곡한 반대)"},
    {"pattern": "Why don't we ~?", "meaning": "우리 ~하는 게 어때요?"},
    {"pattern": "What if we ~?", "meaning": "~하면 어떨까요?"},
    {"pattern": "How about ~?", "meaning": "~는 어때요?"},
    {"pattern": "Would you mind ~?", "meaning": "~해주실 수 있을까요? (공손)"},
    {"pattern": "I was wondering if you could ~", "meaning": "혹시 ~해주실 수 있나 해서요"},
    {"pattern": "Do you happen to ~?", "meaning": "혹시 ~하시나요?"},
    {"pattern": "I'm afraid ~", "meaning": "죄송하지만 ~ / 유감이지만 ~"},
    {"pattern": "To be honest ~", "meaning": "솔직히 말하면 ~"},
    {"pattern": "Unfortunately ~", "meaning": "안타깝게도 ~"},
    {"pattern": "So what you're saying is ~", "meaning": "그러니까 ~라는 말씀이죠?"},
    {"pattern": "Just to make sure ~", "meaning": "확실히 하자면 ~"},
    {"pattern": "Let me get this straight", "meaning": "정리 좀 할게요 / 이거 맞죠"},
    {"pattern": "That's a good question", "meaning": "좋은 질문이에요 (생각할 시간 벌기)"},
    {"pattern": "Let me think for a second", "meaning": "잠깐 생각해볼게요"},
    {"pattern": "Off the top of my head ~", "meaning": "지금 바로 떠오르는 건 ~"},
    {"pattern": "Let me put it this way", "meaning": "이렇게 말해볼게요"},
    {"pattern": "What I'm trying to say is ~", "meaning": "제가 하려는 말은 ~"},
    {"pattern": "I'll get back to you on ~", "meaning": "~는 다시 알려드릴게요"},
    {"pattern": "Let's touch base on ~", "meaning": "~에 대해 다시 얘기해요"},
    {"pattern": "Let's circle back to ~", "meaning": "~로 다시 돌아가죠"},
    {"pattern": "That makes sense", "meaning": "말 되네요 / 이해돼요"},
    {"pattern": "I'm really into ~", "meaning": "저 ~에 푹 빠졌어요"},
]

# 확장: 80% → 90%. 디테일·뉘앙스·리액션
FORMULAS_EXTENDED = [
    {"pattern": "No way!", "meaning": "말도 안 돼! / 설마!"},
    {"pattern": "Same here", "meaning": "저도 그래요"},
    {"pattern": "I know, right?", "meaning": "그러니까요! (강한 공감)"},
    {"pattern": "By the way ~", "meaning": "그건 그렇고 ~ (화제 전환)"},
    {"pattern": "Speaking of which ~", "meaning": "말 나온 김에 ~"},
    {"pattern": "Before I forget ~", "meaning": "잊기 전에 말인데 ~"},
    {"pattern": "The thing is ~", "meaning": "문제는/사실은 ~ (핵심 꺼낼 때)"},
    {"pattern": "At the end of the day ~", "meaning": "결국 중요한 건 ~"},
    {"pattern": "I guess ~", "meaning": "~인 것 같아요 (약한 추측)"},
    {"pattern": "It seems like ~", "meaning": "~인 것 같아 보여요"},
    {"pattern": "As far as I know ~", "meaning": "내가 알기로는 ~"},
    {"pattern": "Chances are ~", "meaning": "아마 ~일 거예요"},
    {"pattern": "Then again ~", "meaning": "하긴 또 ~ (생각 뒤집기)"},
    {"pattern": "Having said that ~", "meaning": "그렇긴 하지만 ~"},
    {"pattern": "If you don't mind ~", "meaning": "괜찮으시면 ~"},
    {"pattern": "Just so you know ~", "meaning": "참고로 알려드리면 ~"},
    {"pattern": "Correct me if I'm wrong ~", "meaning": "제가 틀렸으면 고쳐주세요 ~"},
    {"pattern": "I totally get it", "meaning": "완전 이해해요"},
    {"pattern": "That must be tough", "meaning": "정말 힘들겠어요 (공감)"},
    {"pattern": "First of all ~", "meaning": "우선 ~"},
    {"pattern": "In the meantime ~", "meaning": "그동안에 ~"},
    {"pattern": "From now on ~", "meaning": "이제부터 ~"},
    {"pattern": "Long story short ~", "meaning": "간단히 말하면 ~"},
    {"pattern": "All in all ~", "meaning": "전체적으로 보면 ~"},
    {"pattern": "Either way ~", "meaning": "어느 쪽이든 ~"},
    {"pattern": "More importantly ~", "meaning": "더 중요한 건 ~"},
    {"pattern": "Now that I think about it ~", "meaning": "생각해보니 ~"},
]

# 비즈니스 팩(옵션): 전화·미팅·견적·협상·이메일 — 호준님 영업 실무
FORMULAS_BUSINESS = [
    {"pattern": "I'm calling to ~", "meaning": "~하려고 전화드렸습니다"},
    {"pattern": "I'm calling regarding ~", "meaning": "~건으로 연락드렸습니다"},
    {"pattern": "Could we schedule a meeting for ~?", "meaning": "~로 미팅을 잡을 수 있을까요?"},
    {"pattern": "I'd like to follow up on ~", "meaning": "~건을 다시 확인하고 싶어서요"},
    {"pattern": "Just following up on my last email", "meaning": "지난 메일 관련해 다시 연락드립니다"},
    {"pattern": "Please find attached ~", "meaning": "~을 첨부드립니다 (이메일)"},
    {"pattern": "I'll send you the quote by ~", "meaning": "~까지 견적서를 보내드리겠습니다"},
    {"pattern": "Would it be possible to ~?", "meaning": "~가 가능할까요? (공손 요청)"},
    {"pattern": "We're looking at around ~", "meaning": "대략 ~ 정도로 보고 있습니다 (가격/수량)"},
    {"pattern": "Is there any room for negotiation?", "meaning": "협상의 여지가 있을까요?"},
    {"pattern": "Let me run it by my team", "meaning": "저희 팀과 상의해보겠습니다"},
    {"pattern": "Let's iron out the details", "meaning": "세부 사항을 정리합시다"},
    {"pattern": "That works for us", "meaning": "저희는 그걸로 괜찮습니다"},
    {"pattern": "I'll loop you in", "meaning": "관련해서 계속 공유드릴게요"},
    {"pattern": "Let's keep this moving", "meaning": "이 건 계속 진행하시죠"},
]

FORMULA_PACKS = {
    "💬 비기너 공식 (80%)": FORMULAS_BEGINNER,
    "🚀 확장 공식 (90%)": FORMULAS_EXTENDED,
    "💼 비즈니스 팩 (영업 실무)": FORMULAS_BUSINESS,
}

# ──────────────────────────────────────────────
# 영작 엔진 — 문장을 만들어내는 뼈대 10개 (우선순위 순)
WRITING_ENGINES = [
    {"id": "be_verb", "title": "1. be동사 vs 일반동사",
     "point": "모든 문장의 출발점. 상태(~이다/~하다 형용사)는 be동사, 동작은 일반동사. 'I am happy'(O) / 'I happy'(X)."},
    {"id": "five_forms", "title": "2. 문장 5형식 (골격)",
     "point": "부품을 어순에 맞게 놓는 틀. 1형식(주+동), 2형식(주+동+보어), 3형식(주+동+목적어), 4형식(주+동+사람+사물), 5형식(주+동+목적어+그걸 설명하는 말)."},
    {"id": "tense", "title": "3. 실전 시제 6개",
     "point": "현재/과거/미래 + 현재진행(~하고 있다)/현재완료(~해본 적/막 ~했다)/과거. '했어요/하고 있어요/해본 적 있어요'를 구분."},
    {"id": "modal", "title": "4. 조동사 (뉘앙스)",
     "point": "can/could/will/would/should/might. 같은 문장도 '할 수 있어요/해주실래요(공손)/해야 해요/아마요'로 강도와 공손함이 바뀜."},
    {"id": "question_negative", "title": "5. 의문문·부정문",
     "point": "긍정문을 질문(~인가요?)·부정(~아니에요)으로 바꾸기. do/does/did 넣기, be동사는 자리 바꾸기(도치)."},
    {"id": "to_ing", "title": "6. to부정사 / 동명사",
     "point": "'~하는 것'. want to do(하고 싶다), enjoy doing(하기를 즐기다). 동사마다 뒤에 to-동사 or -ing가 정해져 있음."},
    {"id": "relative", "title": "7. 관계대명사 (문장 잇기)",
     "point": "who/which/that으로 명사를 꾸며 길게 연결. 'the client who called me'(나에게 전화한 그 고객)."},
    {"id": "preposition", "title": "8. 전치사 감각",
     "point": "in/on/at/by/for/with… 한국어엔 없는 감각이라 제일 자주 틀림. 시간·장소·방향·수단의 작은 차이."},
    {"id": "conjunction", "title": "9. 접속사 (연결)",
     "point": "and/but/so/because/although로 문장을 자연스럽게 잇기. 짧은 문장을 한 문장으로 묶는 힘."},
    {"id": "article_plural", "title": "10. 관사·셀 수 있는 명사",
     "point": "a/an/the, 단수·복수. 한국어에 없어서 계속 빠뜨리는 부분. 'a quote / the quote / quotes'의 차이."},
]

def generate_engine_lesson(engine):
    """영작 엔진 1개에 대한 미니 레슨 (호준 씨 맞춤 예문 + 흔한 실수 + 따라하기)."""
    system_prompt = (
        "당신은 밝고 따뜻한 20대 후반 한국인 여배우 영어 선생님입니다. 호준 씨(KCC 창호 B2B 영업팀장)에게 "
        "영작에 꼭 필요한 문법 '엔진' 하나를 귀로 듣고 따라 말하며 익히게 가르칩니다.\n"
        "규칙: ① 핵심 규칙을 일상 비유로 아주 쉽게 ② 한국인이 자주 하는 실수 1개와 교정(틀린 문장→고친 문장) "
        "③ 호준 씨의 영업/일상 예문 3개(영어 직후 반드시 한국어 해석) ④ 각 예문은 의미 단위로 끊어 읽고 각 조각 뒤 [[PAUSE]] 마커로 따라 말할 시간을 주고 '좋아요!'로 이어가기. "
        "전체 약 900~1200자, 다정한 라디오 멘트체."
    )
    user = f"오늘의 영작 엔진: {engine['title']}\n핵심: {engine['point']}\n이걸로 미니 레슨을 만들어 주세요."
    resp = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user}],
        temperature=0.8,
    )
    return resp.choices[0].message.content

FORMATS = {
    "korea_news": {"label": "🇰🇷 국내 주요 뉴스", "needs_news": "korea",
        "brief": "오늘 한국의 주요 뉴스 하나를 골라 쉬운 영어로 소개하고 핵심 표현을 가르쳐 주세요. 정치적으로 민감한 사안은 중립적으로 사실만 짧게 다루세요."},
    "global_news": {"label": "🌍 글로벌 비즈니스 뉴스", "needs_news": "global",
        "brief": "오늘의 글로벌 경제/비즈니스 뉴스를 소재로, 현장에서 바로 쓰는 비즈니스 영어 표현을 가르쳐 주세요."},
    "movie_quote": {"label": "🎬 영화 · 드라마 명대사", "needs_news": None,
        "brief": "널리 알려진 영화/드라마 명대사 한 줄(짧은 인용만)을 골라 장면 맥락과 함께 영어 표현·뉘앙스를 가르치고, 호준 씨가 응용할 변형 예문도 곁들이세요."},
    "wisdom_quote": {"label": "📜 명언 · 삶의 지혜 · 유명 글귀", "needs_news": None,
        "brief": "역사적 인물/고전의 유명 명언 하나를 영어 원문으로 소개하고(짧은 인용), 담긴 삶의 지혜를 따뜻하게 풀어주세요. 핵심 표현을 실전 영어로 응용까지."},
    "trivia": {"label": "🧠 알아두면 똑똑해지는 교양 · 상식", "needs_news": None,
        "brief": "역사·과학·경제·세계문화 중 '오 신기하다' 싶은 상식 하나를 영어로 설명하고, 그 주제를 말할 때 쓰는 영어 표현을 가르쳐 주세요."},
    "biz_roleplay": {"label": "💼 창호 영업 실전 비즈니스 영어 (호준님 맞춤)", "needs_news": None,
        "brief": "호준 씨는 KCC글라스 홈씨씨에서 아파트 리모델링용 창호(windows)를 인테리어 업체에 공급하는 B2B 영업팀장입니다. 해외 바이어 상담·견적·단가 협상·납기 조율 같은 실제 상황을 짧은 롤플레이로 보여주고 비즈니스 영어를 가르쳐 주세요."},
    "daily_life": {"label": "🗣️ 일상생활 영어", "needs_news": None,
        "brief": "카페 주문, 장보기·쇼핑, 이웃·친구와의 가벼운 대화, 약속 잡기 등 매일의 일상에서 자주 쓰는 생활 영어 표현을 짧은 상황 대화로 보여주고 가르쳐 주세요. 너무 어렵지 않게, 바로 따라 쓸 수 있는 표현 위주로."},
    "travel": {"label": "✈️ 해외여행 영어", "needs_news": None,
        "brief": "공항 입국심사, 호텔 체크인, 식당 주문, 길 묻기, 택시·교통, 쇼핑 등 해외여행 중 실제로 마주치는 상황의 영어 표현을 짧은 대화로 보여주고 가르쳐 주세요. 호준 씨는 여행을 좋아하니(일본 오타루 등), 설레는 여행 분위기로 다정하게."},
    "book": {"label": "📖 책 속 한 문장", "needs_news": None,
        "brief": "유명한 책(고전·소설·자기계발)에서 인상적인 문장이나 핵심 아이디어 하나를 영어로 소개하고(짧은 인용만), 거기서 일상·업무에 써먹을 영어 표현을 가르쳐 주세요. 책의 메시지를 호준 씨 삶에 연결해 따뜻하게."},
}

# ──────────────────────────────────────────────
# 5. 뉴스 수집
# ──────────────────────────────────────────────
def fetch_rss_title(urls):
    for url in urls:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                e = random.choice(feed.entries[:6])
                return f"{e.title} - {getattr(e, 'summary', '')}"[:600]
        except Exception:
            continue
    return None

def get_news(kind):
    if kind == "korea":
        urls = ["https://www.yna.co.kr/rss/news.xml", "https://www.hani.co.kr/rss/", "https://rss.donga.com/total.xml"]
        return fetch_rss_title(urls) or "오늘 한국에서는 경제·생활 분야의 다양한 소식이 전해지고 있습니다."
    urls = ["http://feeds.bbci.co.uk/news/business/rss.xml", "https://feeds.bbci.co.uk/news/world/rss.xml"]
    return fetch_rss_title(urls) or "Global markets are showing notable shifts ahead of the economic forum."

# ──────────────────────────────────────────────
# 6. 대본 생성
# ──────────────────────────────────────────────
def generate_radio_script(situation_key, news_content, formula_str, formula_meaning, yesterday_str=""):
    sit = FORMATS[situation_key]
    news_block = f"\n[참고 뉴스]\n{news_content}\n" if news_content else ""
    # 메인 공식 외에 호준 씨가 이미 아는 다른 공식들 (자연스럽게 같이 짚어주기용)
    others = [p['pattern'] for p in st.session_state['hojun_past_patterns'] if p['pattern'] != formula_str][:20]
    known_str = ", ".join(f"'{o}'" for o in others)
    yesterday_block = ""
    if yesterday_str:
        yesterday_block = f"""
[★ 어제 공식 60초 복습 (맨 처음) ★]
방송을 시작하면 가장 먼저, 어제 배운 표현을 60초 안에 빠르게 짚어주세요. 예문 1개 + 한국어 해석 + 짧은 따라하기.
어제 표현: {yesterday_str}
"""
    length_rule = "전체 약 2000~2400자, 자연스러운 라디오 멘트체. 문법 코너는 충분히, 군더더기 없이."
    system_prompt = f"""
당신은 밝고 따뜻하며 살짝 장난기 있는 20대 후반 한국인 여배우 영어 라디오 선생님입니다.
오늘의 단 한 명의 청취자는 '호준 씨'입니다. 다정하지만 과하지 않은 톤으로, 귀로 듣고 따라 말하며 배우는 라디오를 진행하세요.
{yesterday_block}
[★ 이 방송의 핵심 — 오늘의 회화 공식 1개 ★]
오늘의 공식: "{formula_str}"  (뜻: {formula_meaning})
이 방송의 목표는 '바로 이 공식 하나'를 호준 씨 입에 붙이는 거예요. 단, 지루하지 않게 — 오늘의 '상황'에 이 공식을 입혀 **매번 새로운 문장**으로 반복 연습시키세요.
방송 전반에 걸쳐 이 공식이 들어간 서로 다른 문장이 최소 5~6번 자연스럽게 등장해야 합니다.

[★ 오늘의 상황(무대): {sit['label']} ★]
{sit['brief']}
→ 이 상황 안에서, 위 공식이 자연스럽게 들어가는 '새로운' 예문과 대화를 만들어 주세요. (상황은 재미를 위한 옷, 주인공은 어디까지나 오늘의 공식입니다.)

[★ 보너스 — 다른 공식도 함께 짚어주기 ★]
호준 씨가 이미 아는 다른 회화 공식들: {known_str}
예문이나 대화를 만들다가 위 공식 중 하나가 자연스럽게 섞여 들어가면, 그냥 지나치지 말고 "어, 이 문장엔 우리가 아는 공식 '~'도 들어있네요!" 하고 짧게 짚어주며 뜻을 한 번 복습시키세요. (단, 억지로 끼워넣지는 말고 자연스러울 때만. 메인 공식이 흐려지지 않게 가볍게.)

[★ 필수 규칙 — 영어 직후 한국어 해석 ★]
영어 문장 직후 "이건 ~라는 뜻이에요" 하고 정확한 한국어 해석을 다정하게 바로 이어 붙이세요. 절대 영어만 말하고 넘어가지 마세요.

[★ 끊어 읽기 + 따라하기 — 매우 중요 ★]
따라할 영어 문장은 통으로 시키지 말고 의미 단위(2~4단어)로 끊어, 각 조각 뒤에 [[PAUSE]] 마커를 넣어 따라 말할 시간을 주세요(무음이 자동 삽입됨). 끊는 곳은 줄임표(…). [[PAUSE]] 뒤엔 "좋아요!" 같은 격려를 이어가세요.
  예) "I was wondering… [[PAUSE]] if you could… [[PAUSE]] send me the file. [[PAUSE]]" 그다음 "좋아요! 전체로 한 번 더!" + 전체 문장 + [[PAUSE]].

[대본 구성]
1. 📝 [Today's Formula] : 오늘의 공식을 :red[{formula_str}] 로 표시하고, 언제·왜 쓰는지 한국어로 쉽게 소개.
2. 🎬 오늘의 상황({sit['label']})에서 : 이 공식이 들어간 '새로운' 예문 3~4개를 상황에 맞게 만들고, 각각 한국어 해석 + 끊어 읽기 따라하기.
3. 💬 미니 실전 대화 : 그 상황의 짧은 대화(2~4줄)에 공식을 녹여서. 핵심 줄은 따라하기.
4. 🧩 문법 깊이 알기 : 이 공식의 ① 구조/형태 ② 왜 그렇게 쓰는지(뉘앙스) ③ 비슷한 표현과의 차이 1쌍 ④ 한국인이 자주 하는 실수 1개와 교정.
5. 📐 단계별 영작 훈련 (오늘의 공식 활용) — 아래 순서를 꼭 지키세요:
   (가) 한국어 문장 1개를 주고, 먼저 ① 이 문장이 몇 형식인지 알려주고(1~5형식 중) ② 부품으로 분해한 뒤 ③ 영어 어순으로 재배열해 들려주세요.
        - 형식은 쉽게 설명: 1형식(주어+동사), 2형식(주어+동사+보어=상태), 3형식(주어+동사+목적어), 4형식(주어+동사+사람+사물), 5형식(주어+동사+목적어+그 목적어를 설명하는 말).
        - 예: "다음 주까지 당신에게 견적을 보낼게요" → "이건 4형식이에요. '누구에게(you) + 무엇을(the quote)'이 오죠. 한국어는 동사가 끝에 오지만 영어는 앞으로 와요: I'll / send / you / the quote / by next week."
        - 한국어가 동사를 끝에 두는 것과 영어가 동사를 앞에 두는 차이를 매번 한 번 짚어주세요.
   (나) ① 빈칸 영작: 거의 완성된 영어 문장에서 핵심 부분만 빈칸으로 비워 부르고(예: "I'll ___ you the quote ___ next week"), [[PAUSE:4]]로 채울 시간을 준 뒤 정답.
   (다) ② 뼈대 영작: 한국어 + 영어 키워드 힌트 2~3개만 주고(예: 힌트: send / you / quote / by), [[PAUSE:5]]로 조립할 시간을 준 뒤 정답.
   (라) ③ 자유 영작: 한국어만 주고 [[PAUSE:5]]. 그다음 '쉬운 버전 → 자연스러운 버전' 두 가지 정답을 들려주고 각각 따라하기.
   세 단계 모두 오늘의 공식이 들어가게 하고, 정답 문장은 끊어 읽기 + 따라하기.
6. 🗂️ 오늘의 노트 & 클로징 : 오늘의 공식 한 번 더 + 새 단어 3개 정리.

[★ 클로징 단어 정리 — 한글 발음 ★]
새 단어 3개에 한글 발음을 괄호로 달되, 철자가 아니라 실제 원어민 소리에 가깝게(강세·약모음·연음·받침 반영).
예: "Schedule (스케쥴)", "Comfortable (컴퍼터블)", "Quote (쿠욷)", "Water (워럴)".

{length_rule}

[★ 데이터 추출 마커 — 반드시 맨 마지막 줄 ★]
|||EXTRACT|||
NEW_PATTERN: 오늘공식또는새표현 | 뜻
NEW_WORD1: 단어1 | 한글발음1 | 뜻1
NEW_WORD2: 단어2 | 한글발음2 | 뜻2
NEW_WORD3: 단어3 | 한글발음3 | 뜻3
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": f"오늘 방송 대본을 만들어 주세요.{news_block}"}],
        temperature=0.85,
    )
    return response.choices[0].message.content

def parse_and_update_storage(raw_script):
    if "|||EXTRACT|||" not in raw_script:
        return raw_script
    parts = raw_script.split("|||EXTRACT|||")
    clean_script, data_part = parts[0].strip(), parts[1].strip()
    added = 0
    for line in data_part.split("\n"):
        if line.startswith("NEW_PATTERN:"):
            content = line.replace("NEW_PATTERN:", "").strip()
            if "|" in content:
                pat, mean = content.split("|", 1)
                if not any(p['pattern'].lower() == pat.strip().lower() for p in st.session_state['hojun_past_patterns']):
                    np = {"pattern": pat.strip(), "meaning": mean.strip()}
                    _ensure_srs(np); np['added'] = str(date.today())
                    st.session_state['hojun_past_patterns'].append(np)
                    added += 1
        elif "NEW_WORD" in line:
            try:
                content = line.split(":", 1)[1].strip()
            except IndexError:
                continue
            if "|" in content:
                bits = [b.strip() for b in content.split("|")]
                if len(bits) >= 3:
                    wrd, pron, mean = bits[0], bits[1], bits[2]
                else:
                    wrd, pron, mean = bits[0], "", bits[1]
                if not any(w['word'].lower() == wrd.lower() for w in st.session_state['hojun_past_words']):
                    nw = {"word": wrd, "pron": pron, "meaning": mean}
                    _ensure_srs(nw); nw['added'] = str(date.today())
                    st.session_state['hojun_past_words'].append(nw)
                    added += 1
    st.session_state['total_learned'] += added
    return clean_script

def generate_instant_lesson(selected_item, item_type):
    system_prompt = (
        "당신은 밝고 따뜻한 20대 후반 한국인 여배우 영어 선생님입니다. 호준 씨가 고른 표현에 대해 "
        "비즈니스 실전 예문 2개를 주고, 각 예문의 한국어 뜻과 미묘한 뉘앙스를 톡톡 튀게 설명하세요. "
        "영어 문장 뒤에는 반드시 한국어 해석을 바로 붙이세요."
    )
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_prompt},
                  {"role": "user", "content": f"호준 씨가 고른 {item_type}: [{selected_item}] 에 대한 1분 원포인트 레슨을 만들어 주세요."}],
        temperature=0.7,
    )
    return response.choices[0].message.content

# ──────────────────────────────────────────────
# 7. TTS (보이스 선택 + 청크 분할)
# ──────────────────────────────────────────────
def strip_pause_markers(text):
    """화면 표시용: [[PAUSE]] 마커를 보기 좋은 표시로 치환"""
    return re.sub(r"\[\[PAUSE(?::\d+(?:\.\d+)?)?\]\]", " 🔁 *(따라 말해보기)* ", text)

def _chunk_text(text, limit=180):
    """문장 단위 분할. 영어가 든 문장은 '단독'으로 떼어 TTS 누락을 막고,
    한국어 설명만 limit 한도로 합쳐 호출 수를 줄인다."""
    raw = re.split(r'(?<=[\.!?。…?!])\s+|\n+', text)
    units = []
    for u in raw:
        u = u.strip()
        if not u:
            continue
        if len(u) > limit:
            for part in re.split(r'(?<=[,;:、])\s+', u):
                part = part.strip()
                if part:
                    units.append(part)
        else:
            units.append(u)
    chunks, cur = [], ""
    def _flush():
        nonlocal cur
        if cur.strip():
            chunks.append(cur)
        cur = ""
    for u in units:
        has_eng = bool(re.search(r"[A-Za-z]", u))
        if has_eng:
            _flush()
            chunks.append(u)               # 영어 문장 → 단독 TTS (안 잘림)
        else:
            if len(cur) + len(u) + 1 > limit and cur:
                _flush()
            cur += (" " if cur else "") + u
    _flush()
    return chunks

def _auto_pause_seconds(seg):
    """따라할 영어 분량(단어수)에 비례해 쉬는 시간 자동 산정 (2.5~8초)."""
    n = len(re.findall(r"[A-Za-z']+", seg))
    return max(2.5, min(8.0, n * 0.55 + 1.6))

def text_to_speech(text, voice=None):
    """TTS를 무압축 wav(PCM)로 받아 샘플 단위로 정확히 이어붙임 → 경계 잘림 없음, ffmpeg 불필요."""
    voice = voice or st.session_state['voice']
    fmt = {"rate": 24000, "width": 2, "ch": 1, "set": False}  # OpenAI TTS wav 기본값

    def _tts_frames(seg):
        out = b""
        for chunk in _chunk_text(seg):
            if not chunk.strip():
                continue
            try:
                resp = client.audio.speech.create(model="gpt-4o-mini-tts", voice=voice,
                                                   input=chunk, instructions=VOICE_INSTRUCTIONS,
                                                   response_format="wav")
            except Exception:
                resp = client.audio.speech.create(model="tts-1", voice="nova",
                                                   input=chunk, response_format="wav")
            with wave.open(io.BytesIO(resp.content), "rb") as w:
                if not fmt["set"]:
                    fmt["rate"], fmt["width"], fmt["ch"] = w.getframerate(), w.getsampwidth(), w.getnchannels()
                    fmt["set"] = True
                out += w.readframes(w.getnframes())
        return out

    def _silence(seconds):
        n = int(fmt["rate"] * seconds)
        return b"\x00" * (n * fmt["width"] * fmt["ch"])

    parts = re.split(r"\[\[PAUSE(?::(\d+(?:\.\d+)?))?\]\]", text)
    frames = b""
    i = 0
    while i < len(parts):
        seg = parts[i]
        if seg and seg.strip():
            frames += _tts_frames(seg)
        if i + 1 < len(parts):
            dur = parts[i + 1]
            seconds = float(dur) if dur else _auto_pause_seconds(seg or "")
            frames += _silence(seconds)
        i += 2

    # 맨 앞 리드인 0.25초
    frames = _silence(0.25) + frames

    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(fmt["ch"]); w.setsampwidth(fmt["width"]); w.setframerate(fmt["rate"])
        w.writeframes(frames)
    return out.getvalue()

# ──────────────────────────────────────────────
# 8. UI
# ──────────────────────────────────────────────
st.set_page_config(page_title="여배우의 영라디오", page_icon="📻")
st.title("📻 여배우의 영라디오")
st.caption("🎙️ AI 음성 1:1 맞춤 영어 라디오 · 운전하며 듣는 데일리 영어" + ("  ·  ☁️ 구글 드라이브 연결됨" if DRIVE else ""))

c1, c2, c3 = st.columns(3)
c1.metric("📅 함께한 날", f"Day {st.session_state['day_count']}")
c2.metric("🗂️ 누적 족보", f"{len(st.session_state['hojun_past_patterns']) + len(st.session_state['hojun_past_words'])}개")
c3.metric("✨ 배운 표현", f"{st.session_state['total_learned']}개")
st.divider()

# 사이드바: 목소리 고르기 + 족보
with st.sidebar:
    st.header("🎙️ 목소리 고르기")
    vkeys = list(VOICE_OPTIONS.keys())
    sel = st.selectbox("선생님 목소리", vkeys,
                       index=vkeys.index(st.session_state['voice']) if st.session_state['voice'] in vkeys else 0,
                       format_func=lambda k: VOICE_OPTIONS[k])
    if sel != st.session_state['voice']:
        st.session_state['voice'] = sel
        save_progress()
    if st.button("🔊 이 목소리 미리듣기", use_container_width=True):
        with st.spinner("샘플 굽는 중..."):
            sample = ("안녕하세요 호준 씨! 오늘도 활기차게 시작해볼까요? "
                      "Let's get started! 이건 '자, 시작해봐요'라는 뜻이에요. "
                      "함께라면 영어, 정말 쉬워질 거예요!")
            st.session_state['voice_sample'] = text_to_speech(sample, voice=sel)
    if 'voice_sample' in st.session_state:
        st.audio(st.session_state['voice_sample'], format="audio/wav")
    st.caption("💡 더 많은 목소리는 openai.fm 에서도 들어볼 수 있어요.")
    st.divider()

    st.header("🗂️ 영어 족보")
    st.caption("표현을 누르면 즉석 오디오 레슨이 시작돼요.")
    st.caption("☁️ 족보·복습이 구글 드라이브에 자동 백업돼요." if DRIVE
               else "💾 족보·복습은 로컬에 저장돼요. (드라이브 연동 시 영구 백업)")
    st.markdown("**💬 회화 공식 채우기**")
    st.caption("비기너부터 시작 → 익으면 확장. 비즈니스는 필요할 때.")
    for pack_name, pack in FORMULA_PACKS.items():
        have = sum(1 for f in pack if any(p['pattern'].lower() == f['pattern'].lower()
                                          for p in st.session_state['hojun_past_patterns']))
        done = have == len(pack)
        label = f"{'✅' if done else '➕'} {pack_name} ({have}/{len(pack)})"
        if st.button(label, key=f"pack_{pack_name}", use_container_width=True, disabled=done):
            added = 0
            for f in pack:
                if not any(p['pattern'].lower() == f['pattern'].lower() for p in st.session_state['hojun_past_patterns']):
                    nf = {"pattern": f['pattern'], "meaning": f['meaning']}
                    _ensure_srs(nf); nf['added'] = str(date.today())
                    st.session_state['hojun_past_patterns'].append(nf)
                    added += 1
            save_progress()
            st.toast(f"{pack_name} {added}개 추가됨!" if added else "이미 다 들어가 있어요!")
            st.rerun()
    st.subheader("📝 핵심 패턴")
    for p in st.session_state['hojun_past_patterns']:
        if st.button(f"🔗 {p['pattern']} ({p['meaning']})", key=f"pat_{p['pattern']}", use_container_width=True):
            with st.spinner("🎙️ 원포인트 굽는 중..."):
                lesson = generate_instant_lesson(f"{p['pattern']} ({p['meaning']})", "비즈니스 핵심 패턴")
                st.session_state['instant_lesson'] = lesson
                st.session_state['lesson_title'] = p['pattern']
                st.session_state['instant_audio'] = text_to_speech(lesson)
    st.subheader("📚 단어장")
    for w in st.session_state['hojun_past_words']:
        pron = w.get('pron', '')
        label = f"🗂️ {w['word']}" + (f" ({pron})" if pron else "") + f" : {w['meaning']}"
        if st.button(label, key=f"wrd_{w['word']}", use_container_width=True):
            with st.spinner("🎙️ 원포인트 굽는 중..."):
                lesson = generate_instant_lesson(f"{w['word']} ({w['meaning']})", "필수 비즈니스 단어")
                st.session_state['instant_lesson'] = lesson
                st.session_state['lesson_title'] = w['word']
                st.session_state['instant_audio'] = text_to_speech(lesson)

# 즉석 레슨 (공통 — 어느 탭에서든 표시)
if 'instant_lesson' in st.session_state:
    st.success(f"🎯 원포인트 레슨: [{st.session_state['lesson_title']}]")
    st.audio(st.session_state['instant_audio'], format="audio/wav")
    st.info(st.session_state['instant_lesson'])
    if st.button("❌ 레슨 창 닫기"):
        del st.session_state['instant_lesson']; del st.session_state['instant_audio']; st.rerun()
    st.divider()

tab_radio, tab_quiz, tab_engine, tab_review, tab_lib = st.tabs(
    ["📻 라디오", "🎤 말하기 퀴즈", "📐 영작 엔진", "🔁 복습", "📼 보관함"])

# ══════════════ 📻 라디오 탭 ══════════════
with tab_radio:
    sk = st.session_state.get('skip_formulas', set())
    cur = st.session_state.get('today_formula_pattern')
    formula = None
    if cur and cur not in sk:
        formula = next((p for p in st.session_state['hojun_past_patterns'] if p['pattern'] == cur), None)
    if formula is None:
        formula = pick_today_formula(exclude=sk)
        if formula:
            st.session_state['today_formula_pattern'] = formula['pattern']
    if formula is None:
        st.warning("아직 회화 공식이 없어요. 사이드바의 **💬 회화 공식 라이브러리 채우기**를 먼저 눌러주세요!")
    else:
        st.markdown("#### 💬 오늘의 공식")
        st.success(f"### {formula['pattern']}\n**{formula['meaning']}**")
        cfa, cfb = st.columns(2)
        if cfa.button("🎲 다른 공식으로", use_container_width=True):
            sk = set(st.session_state.get('skip_formulas', set()))
            sk.add(formula['pattern'])
            st.session_state['skip_formulas'] = sk
            st.session_state.pop('today_formula_pattern', None)
            st.rerun()
        if cfb.button("↩️ 공식 다시 (초기화)", use_container_width=True):
            st.session_state['skip_formulas'] = set()
            st.session_state.pop('today_formula_pattern', None)
            st.rerun()

        # 상황(무대): 기본 랜덤, 원하면 직접 선택
        with st.expander("🎬 상황 고르기 (기본은 랜덤)"):
            sit_choice = st.radio("오늘의 상황",
                                  ["🎲 랜덤"] + [v["label"] for v in FORMATS.values()],
                                  label_visibility="collapsed")

        if st.button("▶️ 오늘의 공식 방송 듣기", use_container_width=True, type="primary"):
            if sit_choice.startswith("🎲"):
                situation_key = random.choice(list(FORMATS.keys()))
            else:
                situation_key = next(k for k, v in FORMATS.items() if v["label"] == sit_choice)
            sit = FORMATS[situation_key]
            news_content = None
            if sit["needs_news"]:
                with st.spinner("📡 오늘의 뉴스를 가져오는 중..."):
                    news_content = get_news(sit["needs_news"])
            st.toast(f"오늘의 공식: {formula['pattern']}  ·  무대: {sit['label']}")
            yesterday = get_yesterday_items()
            yesterday_str = ", ".join(f"'{e}'({m})" for e, m in yesterday)
            with st.spinner("🎙️ 선생님이 오늘의 공식으로 원고를 쓰는 중..."):
                script_raw = parse_and_update_storage(
                    generate_radio_script(situation_key, news_content,
                                          formula['pattern'], formula['meaning'], yesterday_str))
            with st.spinner("🎵 밝고 따뜻한 목소리로 녹음 중..."):
                audio = text_to_speech(script_raw)
            script_display = strip_pause_markers(script_raw)
            today = str(date.today())
            if st.session_state['last_date'] != today:
                st.session_state['day_count'] += 1
                st.session_state['last_date'] = today
            review_item(formula, "easy")        # 오늘의 공식 복습 처리 → 다음 복습일로
            theme = f"💬 {formula['pattern']} · {sit['label']}"
            st.session_state['current_script'] = script_display
            st.session_state['current_audio'] = audio
            st.session_state['current_theme'] = theme
            save_broadcast(script_display, audio, theme)
            save_progress()
            st.rerun()

    if st.session_state['current_script']:
        st.divider()
        st.success(f"✨ 방송 준비 완료 — {st.session_state['current_theme']}")
        st.markdown("### 🎧 오디오 스트리밍")
        st.audio(st.session_state['current_audio'], format="audio/wav")
        st.download_button("⬇️ 이 방송 폰에 저장 (wav)", data=st.session_state['current_audio'],
                           file_name=f"영라디오_{datetime.now().strftime('%m%d_%H%M')}.wav",
                           mime="audio/wav", use_container_width=True)
        st.caption("ℹ️ AI 합성 음성입니다." + ("  ·  ☁️ 드라이브 보관함에 자동 저장됐어요." if DRIVE else "  ·  보관함에 자동 저장됐어요."))
        st.markdown("---")
        st.markdown(st.session_state['current_script'])

# ══════════════ 🎤 말하기 퀴즈 탭 ══════════════
with tab_quiz:
    st.subheader("🎤 한국어 → 영어 말하기 퀴즈")
    st.caption("한국어 문장을 영어로 말해보세요. 녹음하면 AI가 알아듣고 채점해줘요. (조용한 곳·정차 시 권장)")
    if st.button("🎲 새 문제 받기", use_container_width=True, type="primary"):
        with st.spinner("문제 만드는 중..."):
            st.session_state['quiz'] = generate_quiz()
            st.session_state.pop('quiz_result', None)
    if 'quiz' in st.session_state:
        q = st.session_state['quiz']
        st.markdown(f"#### 🇰🇷 {q['ko']}")
        st.caption("👆 이 문장을 영어로 말해보세요")
        if hasattr(st, "audio_input"):
            rec = st.audio_input("🎙️ 여기를 눌러 녹음", key="quiz_mic")
            if rec is not None and st.button("✅ 제출하고 채점받기", use_container_width=True, type="primary"):
                with st.spinner("듣고 채점하는 중..."):
                    try:
                        said = transcribe_audio(rec.getvalue())
                    except Exception:
                        said = ""
                    result = grade_answer(q['ko'], q['answer'], said)
                    result['said'] = said
                    st.session_state['quiz_result'] = result
        else:
            st.warning("음성 녹음(st.audio_input)은 최신 Streamlit이 필요해요. requirements.txt의 streamlit을 최신으로 올려 주세요.")
        if 'quiz_result' in st.session_state:
            r = st.session_state['quiz_result']
            st.markdown(f"🗣️ **내가 말한 영어:** {r.get('said','(인식 실패)')}")
            v, score = r.get('verdict', ''), r.get('score', 0)
            if v == "정답":
                st.success(f"🎉 {v} · {score}점")
            elif v == "거의":
                st.warning(f"👍 {v} · {score}점")
            else:
                st.error(f"💪 {v} · {score}점")
            st.info(r.get('feedback', ''))
            st.markdown(f"✨ **더 자연스럽게:** {r.get('better','')}")
            st.caption(f"모범 답안: {q['answer']}")
    else:
        st.write("‘새 문제 받기’를 눌러 시작해요. 족보에 쌓인 표현이 문제로 나옵니다.")

# ══════════════ 📐 영작 엔진 탭 ══════════════
with tab_engine:
    st.subheader("📐 영작 엔진 — 문장을 만드는 뼈대 10개")
    st.caption("공식이 '덩어리'라면, 이건 문장을 굴러가게 하는 엔진이에요. 우선순위 순으로 하나씩 익혀요.")
    if st.button("➕ 영작 엔진 10개를 복습 족보에 넣기", use_container_width=True):
        added = 0
        for e in WRITING_ENGINES:
            tag = f"[영작엔진] {e['title']}"
            if not any(p['pattern'] == tag for p in st.session_state['hojun_past_patterns']):
                nf = {"pattern": tag, "meaning": e['point']}
                _ensure_srs(nf); nf['added'] = str(date.today())
                st.session_state['hojun_past_patterns'].append(nf)
                added += 1
        save_progress()
        st.toast(f"영작 엔진 {added}개를 복습에 추가!" if added else "이미 다 들어가 있어요!")
        st.rerun()
    st.divider()
    for i, e in enumerate(WRITING_ENGINES):
        with st.expander(f"📐 {e['title']}"):
            st.markdown(e['point'])
            if st.button("🔊 미니 레슨 듣기", key=f"eng_{e['id']}", use_container_width=True):
                with st.spinner("🎙️ 호준 님 맞춤 영작 레슨 만드는 중..."):
                    lesson_raw = generate_engine_lesson(e)
                    st.session_state[f'englesson_{i}'] = strip_pause_markers(lesson_raw)
                    st.session_state[f'engaudio_{i}'] = text_to_speech(lesson_raw)
            if f'engaudio_{i}' in st.session_state:
                st.audio(st.session_state[f'engaudio_{i}'], format="audio/wav")
                st.markdown(st.session_state[f'englesson_{i}'])

# ══════════════ 🔁 복습 탭 ══════════════
with tab_review:
    due_items = get_due_items()
    st.subheader(f"🔁 오늘의 복습 ({len(due_items)})")
    if not due_items:
        st.caption("오늘 복습할 표현이 없어요. 방송을 들으면 새 표현이 쌓이고, 시간이 지나면 복습 타이밍이 떠요.")
    else:
        st.caption("복습 타이밍이 된 치트키예요. 문장으로 불러와 따라 말해보고, '기억나요/다시'로 다음 복습 간격을 정해요.")
        if st.button("📥 오늘 복습할 치트키 문장 불러오기", use_container_width=True):
            with st.spinner("치트키가 들어간 실전 문장 만드는 중..."):
                for _t, d, expr, mean in due_items:
                    if not d.get('ex'):
                        d['ex'] = make_cheat_sentences(expr, mean)
            save_progress(); st.rerun()
        for i, (_t, d, expr, mean) in enumerate(due_items):
            with st.expander(f"🔑 {expr} — {mean}"):
                if d.get('ex'):
                    say = ""
                    for e in d['ex']:
                        st.markdown(f"- **{e['en']}**  \n  ↳ {e['ko']}")
                        say += f"{e['en']}. 이건 '{e['ko']}'라는 뜻이에요. 자, 따라 해보세요. [[PAUSE]] 좋아요! "
                    if st.button("🔊 예문 듣고 따라하기", key=f"revaud_{i}"):
                        with st.spinner("녹음 중..."):
                            st.session_state[f'revbytes_{i}'] = text_to_speech(say)
                    if f'revbytes_{i}' in st.session_state:
                        st.audio(st.session_state[f'revbytes_{i}'], format="audio/wav")
                else:
                    st.caption("위 버튼으로 치트키 문장을 먼저 불러오세요.")
                ca, cb = st.columns(2)
                if ca.button("😊 기억나요", key=f"easy_{i}", use_container_width=True):
                    review_item(d, "easy"); save_progress(); st.rerun()
                if cb.button("😵 다시", key=f"again_{i}", use_container_width=True):
                    review_item(d, "again"); save_progress(); st.rerun()

# ══════════════ 📼 보관함 탭 ══════════════
with tab_lib:
    library = load_library()
    st.subheader(f"📼 보관함 ({len(library)})" + ("  ☁️" if DRIVE else ""))
    if not library:
        st.caption("아직 저장된 방송이 없어요. 방송을 들으면 여기에 쌓입니다.")
    else:
        labels = [f"{b['date']} · {b['theme']}" for b in library]
        idx = st.selectbox("다시 들을 방송", range(len(library)), format_func=lambda i: labels[i], label_visibility="collapsed")
        chosen = library[idx]
        audio_bytes = read_broadcast_audio(chosen)
        if audio_bytes:
            st.audio(audio_bytes, format="audio/wav")
            a, b = st.columns(2)
            a.download_button("⬇️ 폰에 저장", data=audio_bytes, file_name=chosen["audio"],
                              mime="audio/wav", use_container_width=True, key=f"dl_{chosen['id']}")
            if b.button("🗑️ 삭제", use_container_width=True, key=f"del_{chosen['id']}"):
                delete_broadcast(chosen); st.rerun()
            with st.expander("📄 대본 보기"):
                st.markdown(chosen["script"])
        else:
            st.warning("오디오를 찾지 못했어요.")
            if st.button("🗑️ 목록에서 제거", key=f"delm_{chosen['id']}"):
                delete_broadcast(chosen); st.rerun()
    if DRIVE:
        st.caption("📱 폰에서 바로 듣기: 구글 드라이브 앱 → '영라디오' 폴더 → mp3 파일 탭하면 재생돼요.")
