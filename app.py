import streamlit as st
import feedparser
import ssl
import random
import json
import os
import io
import re
import base64
from datetime import date, datetime
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

# 0.5초 무음 mp3 (24kHz mono) — '따라 해보세요' 뒤 실제 쉼 구간용
SILENCE_05_B64 = (
    "SUQzBAAAAAAAI1RTU0UAAAAPAAADTGF2ZjYwLjE2LjEwMAAAAAAAAAAAAAAA//OEwAAAAAAAAAAAAEluZm8AAAAPAAAAFwAACWAAHh4eHigoKCgzMzMzMz09PT1HR0dHUVFRUVFcXFxcZmZmZnBwcHBwenp6eoWFhYWPj4+Pj5mZmZmjo6Ojrq6urq64uLi4wsLCwszMzMzM19fX1+Hh4eHr6+vr6/X19fX/////AAAAAExhdmM2MC4zMQAAAAAAAAAAAAAAACQCoAAAAAAAAAlgDUx3IwAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA//NExAAAAANIAAAAAExBTUUzLjEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExFMAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKYAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVTEFNRTMu//NExKwAAANIAAAAADEwMFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//NExKwAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV//NExKwAAANIAAAAAFVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVVV"
)
SILENCE_05 = base64.b64decode(SILENCE_05_B64)

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
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
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
        fname = f"영라디오_{bid}.mp3"
        entry = {"id": bid, "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                 "theme": theme, "script": script, "audio": fname}
        if DRIVE:
            entry["drive_file_id"] = drive_upload(fname, audio_bytes, "audio/mpeg")
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
# 4. 방송 코너 정의
# ──────────────────────────────────────────────
FORMATS = {
    "korea_news": {"label": "🇰🇷 오늘의 국내 주요 뉴스 (영어로)", "needs_news": "korea",
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
def generate_radio_script(fmt_key, news_content):
    fmt = FORMATS[fmt_key]
    patterns_str = ", ".join([f"'{p['pattern']}'({p['meaning']})" for p in st.session_state['hojun_past_patterns'][:8]])
    words_str = ", ".join([f"'{w['word']}'({w['meaning']})" for w in st.session_state['hojun_past_words'][:8]])
    news_block = f"\n[참고 뉴스]\n{news_content}\n" if news_content else ""
    system_prompt = f"""
당신은 아침 영어 라디오를 진행하는, 밝고 따뜻하며 살짝 장난기 있는 20대 후반 한국인 여배우 영어 선생님입니다.
오늘의 단 한 명의 청취자는 '호준 씨'입니다. 다정하지만 과하지 않은 톤으로, 귀로 듣고 따라 말하며 배우는 라디오를 진행하세요.

[★ 오늘의 코너: {fmt['label']} ★]
{fmt['brief']}

[★ 필수 규칙 — 영어 직후 한국어 해석 ★]
영어 문장 직후 "이건 ~라는 뜻이에요" 하고 정확한 한국어 해석과 핵심 단어 뜻을 다정하게 바로 이어 붙이세요. 절대 영어만 말하고 넘어가지 마세요.

[★ 따라하기 시간 마커 — 매우 중요 ★]
"따라 해보세요" 라고 말한 직후에는 반드시 마커 [[PAUSE:3]] 를 넣으세요. 이 마커 자리에서 호준 씨가 직접 따라 말할 시간이 주어집니다.
- 짧은 표현이면 [[PAUSE:3]], 긴 문장이면 [[PAUSE:4]] 또는 [[PAUSE:5]] 를 쓰세요.
- 마커 뒤에 "좋아요!" 같은 격려를 이어가세요. (마커 없이 바로 격려로 넘어가면 안 됩니다.)
- 같은 표현을 한 번 더 시키려면 다시 [[PAUSE:3]] 를 넣으세요.

[★ 지난 족보 복습 — 예문 + 따라하기 ★]
오프닝에서 과거 족보 패턴({patterns_str}) 또는 단어({words_str}) 중 1~2개를 골라,
각 표현마다 실전 예문 1~2개를 영어로 들려주고 한국어 해석을 붙이세요.
그리고 그 예문도 "자, 저 따라 해보세요" → [[PAUSE:3]] → "좋아요!" 형태로 따라하기 시간을 꼭 주세요.

[★ 상단 텍스트 ★]
맨 위 [Today's Text] 섹션에 핵심 영어 원문(1~3문장)을 적고, 핵심 표현은 :red[핵심 표현] 형태로 컬러 처리.

[대본 구성]
1. 📝 [Today's Text] (핵심 표현 컬러)
2. ✨ 활기찬 오프닝 + 지난 족보 예문 복습 & 따라하기([[PAUSE]] 포함)
3. 🎯 코너 본문 + 핵심 표현 따라하기([[PAUSE]] 포함)
4. 📐 0.5초 영작 챌린지 (한국어 문장 주고 영작 유도 → [[PAUSE:4]] → 정답/해석)
5. 🗂️ 오늘의 노트 & 클로징

[★ 클로징 단어 정리 — 한글 발음 음 달기 ★]
마지막에 오늘의 핵심 단어 3개를 정리할 때, 각 단어에 한글 발음을 괄호로 달아 읽기 쉽게 하세요.
예: "Streamline (스트림라인) — 간소화하다", "Prospective (프러스펙티브) — 잠재적인".

전체 약 1800자 내외, 자연스러운 라디오 멘트체.

[★ 데이터 추출 마커 — 반드시 맨 마지막 줄. 발음은 한글 음차 ★]
|||EXTRACT|||
NEW_PATTERN: 패턴구조 | 뜻
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
                    st.session_state['hojun_past_patterns'].append({"pattern": pat.strip(), "meaning": mean.strip()})
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
                    st.session_state['hojun_past_words'].append({"word": wrd, "pron": pron, "meaning": mean})
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

def _chunk_text(text, limit=1600):
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit and cur:
            chunks.append(cur); cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur)
    return chunks

def text_to_speech(text, voice=None):
    voice = voice or st.session_state['voice']

    def _tts_one(seg):
        out = b""
        for chunk in _chunk_text(seg):
            if not chunk.strip():
                continue
            try:
                resp = client.audio.speech.create(model="gpt-4o-mini-tts", voice=voice,
                                                   input=chunk, instructions=VOICE_INSTRUCTIONS)
            except Exception:
                resp = client.audio.speech.create(model="tts-1", voice="nova", input=chunk)
            out += resp.content
        return out

    # [[PAUSE]] 또는 [[PAUSE:3]] 마커 → 실제 무음 구간 삽입
    parts = re.split(r"\[\[PAUSE(?::(\d+(?:\.\d+)?))?\]\]", text)
    audio = b""
    i = 0
    while i < len(parts):
        seg = parts[i]
        if seg and seg.strip():
            audio += _tts_one(seg)
        if i + 1 < len(parts):           # 다음 원소는 캡처된 초(또는 None)
            dur = parts[i + 1]
            seconds = float(dur) if dur else 3.5   # 기본 3.5초 따라하기 시간
            reps = max(1, round(seconds / 0.5))
            audio += SILENCE_05 * reps
        i += 2
    return audio

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
        st.audio(st.session_state['voice_sample'], format="audio/mp3")
    st.caption("💡 더 많은 목소리는 openai.fm 에서도 들어볼 수 있어요.")
    st.divider()

    st.header("🗂️ 영어 족보")
    st.caption("표현을 누르면 즉석 오디오 레슨이 시작돼요.")
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

# 즉석 레슨
if 'instant_lesson' in st.session_state:
    st.success(f"🎯 원포인트 레슨: [{st.session_state['lesson_title']}]")
    st.audio(st.session_state['instant_audio'], format="audio/mp3")
    st.info(st.session_state['instant_lesson'])
    if st.button("❌ 레슨 창 닫기"):
        del st.session_state['instant_lesson']; del st.session_state['instant_audio']; st.rerun()
    st.divider()

# 코너 선택
st.subheader("🎚️ 오늘 어떤 방송 들을까요?")
mode = st.radio("코너 선택", ["🎲 랜덤 (오늘의 깜짝 코너)"] + [v["label"] for v in FORMATS.values()],
                label_visibility="collapsed")

if st.button("▶️ 오늘 자 방송 듣기", use_container_width=True, type="primary"):
    fmt_key = random.choice(list(FORMATS.keys())) if mode.startswith("🎲") else next(k for k, v in FORMATS.items() if v["label"] == mode)
    fmt = FORMATS[fmt_key]
    news_content = None
    if fmt["needs_news"]:
        with st.spinner("📡 오늘의 뉴스를 가져오는 중..."):
            news_content = get_news(fmt["needs_news"])
    st.toast(f"오늘의 코너: {fmt['label']}")
    with st.spinner("🎙️ 선생님이 원고를 톡톡 튀게 쓰는 중..."):
        script_raw = parse_and_update_storage(generate_radio_script(fmt_key, news_content))
    with st.spinner("🎵 밝고 따뜻한 목소리로 녹음 중 (약 10초)..."):
        audio = text_to_speech(script_raw)   # 마커 포함 원본으로 무음 삽입
    script_display = strip_pause_markers(script_raw)
    today = str(date.today())
    if st.session_state['last_date'] != today:
        st.session_state['day_count'] += 1
        st.session_state['last_date'] = today
    st.session_state['current_script'] = script_display
    st.session_state['current_audio'] = audio
    st.session_state['current_theme'] = fmt['label']
    save_broadcast(script_display, audio, fmt['label'])
    save_progress()
    st.rerun()

# 현재 방송
if st.session_state['current_script']:
    st.success(f"✨ 방송 준비 완료 — {st.session_state['current_theme']}")
    st.markdown("### 🎧 오디오 스트리밍")
    st.audio(st.session_state['current_audio'], format="audio/mp3")
    st.download_button("⬇️ 이 방송 폰에 저장 (mp3)", data=st.session_state['current_audio'],
                       file_name=f"영라디오_{datetime.now().strftime('%m%d_%H%M')}.mp3",
                       mime="audio/mp3", use_container_width=True)
    st.caption("ℹ️ AI 합성 음성입니다." + ("  ·  ☁️ 구글 드라이브 보관함에 자동 저장됐어요." if DRIVE else "  ·  보관함에 자동 저장됐어요."))
    st.markdown("---")
    st.markdown(st.session_state['current_script'])
else:
    st.write("버튼을 누르면 비타민처럼 활기찬 여배우의 영어 라디오가 시작됩니다 🎶")

# 보관함
st.divider()
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
        st.audio(audio_bytes, format="audio/mp3")
        a, b = st.columns(2)
        a.download_button("⬇️ 폰에 저장", data=audio_bytes, file_name=chosen["audio"],
                          mime="audio/mp3", use_container_width=True, key=f"dl_{chosen['id']}")
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
