import streamlit as st
import feedparser
import ssl
import random
import json
import os
from datetime import date
from openai import OpenAI

# ──────────────────────────────────────────────
# 0. 기본 세팅
# ──────────────────────────────────────────────
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

PROGRESS_FILE = "hojun_progress.json"   # 누적 족보/진도 영구 저장

# 손예진 톤 연기 디렉션 (실존 인물 목소리 복제 X, '분위기'만 연출)
VOICE_NAME = "coral"
VOICE_INSTRUCTIONS = (
    "You are a bright, warm Korean actress in her late 20s hosting a morning English "
    "radio show — think the cozy, sincere, slightly playful warmth of a beloved Korean "
    "drama lead. Speak with gentle energy, never shouting. English lines: clear, natural "
    "American pronunciation, a touch slower so a driver can follow. Korean lines: tender, "
    "lively, like talking to a close friend named 호준. When you say '따라 해보세요', pause "
    "and slow down so the listener can repeat after you."
)

# ──────────────────────────────────────────────
# 1. 족보 / 진도 영구 저장 (호준님 CSV/JSON 선호 반영)
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
    }
    try:
        with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

# 초기화
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

for k in ['current_script', 'current_audio', 'current_theme']:
    if k not in st.session_state:
        st.session_state[k] = None

# ──────────────────────────────────────────────
# 2. 방송 코너(포맷) 정의 — 매일 다른 분위기로 다양화
# ──────────────────────────────────────────────
FORMATS = {
    "korea_news": {
        "label": "🇰🇷 오늘의 국내 주요 뉴스 (영어로)",
        "needs_news": "korea",
        "brief": "오늘 한국의 주요 뉴스 하나를 골라, 그 내용을 쉬운 영어로 소개하고 핵심 표현을 가르쳐 주세요. "
                 "정치적으로 민감한 사안은 중립적으로 사실만 짧게 다루고, 영어 표현 학습에 집중하세요.",
    },
    "global_news": {
        "label": "🌍 글로벌 비즈니스 뉴스",
        "needs_news": "global",
        "brief": "오늘의 글로벌 경제/비즈니스 뉴스를 소재로, 비즈니스 현장에서 바로 쓰는 영어 표현을 가르쳐 주세요.",
    },
    "movie_quote": {
        "label": "🎬 영화 · 드라마 명대사",
        "needs_news": None,
        "brief": "널리 알려진 영화나 드라마의 명대사 한 줄을 골라(짧은 인용만), 그 장면의 맥락과 함께 영어 표현·뉘앙스를 "
                 "가르쳐 주세요. 호준 씨가 일상이나 영업 현장에서 응용할 수 있는 변형 예문도 곁들이세요.",
    },
    "wisdom_quote": {
        "label": "📜 명언 · 삶의 지혜 · 유명 글귀",
        "needs_news": None,
        "brief": "역사적 인물이나 고전의 유명한 명언/글귀 하나를 영어 원문으로 소개하고(짧은 인용), 그 안에 담긴 삶의 지혜를 "
                 "따뜻하게 풀어주세요. 명언 속 핵심 표현을 실전 영어로 응용하는 법까지 알려주세요.",
    },
    "trivia": {
        "label": "🧠 알아두면 똑똑해지는 교양 · 상식",
        "needs_news": None,
        "brief": "역사·과학·경제·세계문화 중 하나에서 '오 신기하다' 싶은 흥미로운 상식 하나를 골라 영어로 설명하고, "
                 "그 주제를 말할 때 쓰는 영어 표현을 가르쳐 주세요.",
    },
    "biz_roleplay": {
        "label": "💼 창호 영업 실전 비즈니스 영어 (호준님 맞춤)",
        "needs_news": None,
        "brief": "호준 씨는 KCC글라스 홈씨씨에서 아파트 리모델링용 창호(windows)를 인테리어 업체에 공급하는 B2B 영업팀장입니다. "
                 "해외 바이어 상담, 견적 제시, 단가 협상, 납기/시공 일정 조율 같은 '실제 영업 상황'을 짧은 롤플레이 대화로 보여주고, "
                 "거기서 바로 쓰는 비즈니스 영어 표현을 가르쳐 주세요.",
    },
}

# ──────────────────────────────────────────────
# 3. 뉴스 수집 (국내 / 글로벌)
# ──────────────────────────────────────────────
def fetch_rss_title(urls):
    for url in urls:
        try:
            feed = feedparser.parse(url)
            if feed.entries:
                e = random.choice(feed.entries[:6])
                summary = getattr(e, "summary", "")
                return f"{e.title} - {summary}"[:600]
        except Exception:
            continue
    return None

def get_news(kind):
    if kind == "korea":
        urls = [
            "https://www.yna.co.kr/rss/news.xml",          # 연합뉴스
            "https://www.hani.co.kr/rss/",                 # 한겨레
            "https://rss.donga.com/total.xml",             # 동아일보
        ]
        return fetch_rss_title(urls) or "오늘 한국에서는 경제·생활 분야의 다양한 소식이 전해지고 있습니다."
    else:
        urls = [
            "http://feeds.bbci.co.uk/news/business/rss.xml",
            "https://feeds.bbci.co.uk/news/world/rss.xml",
        ]
        return fetch_rss_title(urls) or "Global markets are showing notable shifts ahead of the economic forum."

# ──────────────────────────────────────────────
# 4. 라디오 대본 생성
# ──────────────────────────────────────────────
def generate_radio_script(fmt_key, news_content):
    fmt = FORMATS[fmt_key]
    patterns_str = ", ".join([f"'{p['pattern']}'({p['meaning']})" for p in st.session_state['hojun_past_patterns'][:8]])
    words_str = ", ".join([f"'{w['word']}'({w['meaning']})" for w in st.session_state['hojun_past_words'][:8]])
    news_block = f"\n[참고 뉴스]\n{news_content}\n" if news_content else ""

    system_prompt = f"""
당신은 아침 영어 라디오를 진행하는, 밝고 따뜻하며 살짝 장난기 있는 20대 후반 한국인 여배우 영어 선생님입니다.
오늘의 단 한 명의 청취자는 운전 중인 '호준 씨'입니다. 다정하지만 과하지 않게, 운전에 방해되지 않는 톤으로 진행하세요.

[★ 오늘의 코너: {fmt['label']} ★]
{fmt['brief']}

[★ 운전자용 필수 규칙 — 영어 직후 한국어 해석 ★]
영어 문장이 나올 때는 절대 영어만 말하고 넘어가지 마세요. 운전 중인 호준 씨가 귀로만 듣고 바로 이해하도록,
영어 문장 직후 "이건 ~라는 뜻이에요" 하고 정확한 한국어 해석과 핵심 단어 뜻을 다정하게 바로 이어 붙이세요.

[★ 쉐도잉(따라 말하기) 구간 — 운전 중 핵심 학습 ★]
본문 중 가장 중요한 표현 1~2개는 "자, 저 따라 천천히 해볼게요" 하고 또박또박 천천히 읽은 뒤,
"이제 호준 씨 차례예요, 따라 해보세요... (잠시) ... 좋아요, 한 번 더!" 식으로 반복 연습 구간을 꼭 넣으세요.

[★ 상단 텍스트 표출 ★]
대본 맨 위에 [Today's Text] 섹션을 두고 오늘의 핵심 영어 원문(1~3문장)을 적되, 핵심 표현은 반드시 :red[핵심 표현] 형태로 컬러 처리하세요.

[★ 누적 족보 연동 ★]
오프닝이나 토크 중 호준 씨의 과거 족보 패턴({patterns_str}) 또는 단어({words_str}) 중 1~2개를 자연스럽게 소환하고,
그 표현이 들어간 실전 예문 1개와 한국어 해석을 함께 들려주세요.

[대본 구성]
1. 📝 [Today's Text] : 오늘의 핵심 영어 원문 (핵심 표현 컬러)
2. ✨ 활기찬 오프닝 + 족보 복습 실전 예문/뜻
3. 🎯 오늘의 코너 본문 (위 코너 지침대로) + 쉐도잉 구간
4. 📐 0.5초 영작 챌린지 (호준 씨에게 한국어 문장 주고 영작 유도 → 정답/해석)
5. 🗂️ 오늘의 노트 & 해피 클로징 : 오늘 배운 핵심 단어 3개 정리

전체 대본은 자연스러운 라디오 멘트체로, 너무 길지 않게(약 1800자 내외). 운전 중 한 번에 듣기 좋은 분량으로.

[★ 데이터 추출 마커 — 반드시 맨 마지막 줄에 ★]
대본이 끝난 뒤 정확히 아래 서식을 추가하세요.
|||EXTRACT|||
NEW_PATTERN: 오늘배운패턴구조 | 패턴뜻
NEW_WORD1: 새단어1 | 뜻1
NEW_WORD2: 새단어2 | 뜻2
NEW_WORD3: 새단어3 | 뜻3
"""
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"오늘 방송 대본을 만들어 주세요.{news_block}"},
        ],
        temperature=0.85,
    )
    return response.choices[0].message.content

def parse_and_update_storage(raw_script):
    if "|||EXTRACT|||" not in raw_script:
        return raw_script
    parts = raw_script.split("|||EXTRACT|||")
    clean_script = parts[0].strip()
    data_part = parts[1].strip()
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
                wrd, mean = content.split("|", 1)
                if not any(w['word'].lower() == wrd.strip().lower() for w in st.session_state['hojun_past_words']):
                    st.session_state['hojun_past_words'].append({"word": wrd.strip(), "meaning": mean.strip()})
                    added += 1
    st.session_state['total_learned'] += added
    return clean_script

def generate_instant_lesson(selected_item, item_type):
    system_prompt = (
        "당신은 밝고 따뜻한 20대 후반 한국인 여배우 영어 선생님입니다. "
        "호준 씨가 고른 표현에 대해 비즈니스 실전 예문 2개를 주고, 각 예문의 한국어 뜻과 미묘한 뉘앙스를 "
        "톡톡 튀고 명쾌하게 설명하세요. 영어 문장 뒤에는 반드시 한국어 해석을 바로 붙이세요(운전 중 청취)."
    )
    user_content = f"호준 씨가 고른 {item_type}: [{selected_item}] 에 대한 1분 원포인트 레슨을 만들어 주세요."
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        temperature=0.7,
    )
    return response.choices[0].message.content

# ──────────────────────────────────────────────
# 5. TTS — 손예진 톤 디렉션 + 긴 대본 청크 분할
# ──────────────────────────────────────────────
def _chunk_text(text, limit=1600):
    chunks, cur = [], ""
    for line in text.split("\n"):
        if len(cur) + len(line) + 1 > limit and cur:
            chunks.append(cur)
            cur = ""
        cur += line + "\n"
    if cur.strip():
        chunks.append(cur)
    return chunks

def text_to_speech(text):
    audio = b""
    for chunk in _chunk_text(text):
        if not chunk.strip():
            continue
        try:
            resp = client.audio.speech.create(
                model="gpt-4o-mini-tts",
                voice=VOICE_NAME,
                input=chunk,
                instructions=VOICE_INSTRUCTIONS,
            )
        except Exception:
            # 환경에서 gpt-4o-mini-tts 미지원 시 안전 폴백
            resp = client.audio.speech.create(model="tts-1", voice="nova", input=chunk)
        audio += resp.content
    return audio

# ──────────────────────────────────────────────
# 6. UI
# ──────────────────────────────────────────────
st.set_page_config(page_title="여배우의 영라디오", page_icon="📻")
st.title("📻 여배우의 영라디오")
st.caption("🎙️ AI 음성으로 진행되는 1:1 맞춤 영어 라디오 · 운전하며 듣는 데일리 영어")

c1, c2, c3 = st.columns(3)
c1.metric("📅 함께한 날", f"Day {st.session_state['day_count']}")
c2.metric("🗂️ 누적 족보", f"{len(st.session_state['hojun_past_patterns']) + len(st.session_state['hojun_past_words'])}개")
c3.metric("✨ 배운 표현", f"{st.session_state['total_learned']}개")
st.divider()

# 사이드바 — 족보
with st.sidebar:
    st.header("🗂️ 호준 님의 영어 족보")
    st.caption("표현을 누르면 즉석 오디오 레슨이 시작돼요.")
    st.subheader("📝 누적 핵심 패턴")
    for p in st.session_state['hojun_past_patterns']:
        if st.button(f"🔗 {p['pattern']} ({p['meaning']})", key=f"pat_{p['pattern']}", use_container_width=True):
            with st.spinner("🎙️ 원포인트 오디오 굽는 중..."):
                lesson = generate_instant_lesson(f"{p['pattern']} ({p['meaning']})", "비즈니스 핵심 패턴")
                st.session_state['instant_lesson'] = lesson
                st.session_state['lesson_title'] = p['pattern']
                st.session_state['instant_audio'] = text_to_speech(lesson)
    st.subheader("📚 단어장")
    for w in st.session_state['hojun_past_words']:
        if st.button(f"🗂️ {w['word']} : {w['meaning']}", key=f"wrd_{w['word']}", use_container_width=True):
            with st.spinner("🎙️ 원포인트 오디오 굽는 중..."):
                lesson = generate_instant_lesson(f"{w['word']} ({w['meaning']})", "필수 비즈니스 단어")
                st.session_state['instant_lesson'] = lesson
                st.session_state['lesson_title'] = w['word']
                st.session_state['instant_audio'] = text_to_speech(lesson)

# 즉석 레슨 출력
if 'instant_lesson' in st.session_state:
    st.success(f"🎯 원포인트 레슨: [{st.session_state['lesson_title']}]")
    st.audio(st.session_state['instant_audio'], format="audio/mp3")
    st.info(st.session_state['instant_lesson'])
    if st.button("❌ 레슨 창 닫기"):
        del st.session_state['instant_lesson']
        del st.session_state['instant_audio']
        st.rerun()
    st.divider()

# 코너 선택
st.subheader("🎚️ 오늘 어떤 방송 들을까요?")
mode = st.radio("코너 선택", ["🎲 랜덤 (오늘의 깜짝 코너)"] + [v["label"] for v in FORMATS.values()],
                label_visibility="collapsed")

if st.button("▶️ 오늘 자 방송 듣기", use_container_width=True, type="primary"):
    if mode.startswith("🎲"):
        fmt_key = random.choice(list(FORMATS.keys()))
    else:
        fmt_key = next(k for k, v in FORMATS.items() if v["label"] == mode)
    fmt = FORMATS[fmt_key]

    news_content = None
    if fmt["needs_news"]:
        with st.spinner("📡 오늘의 뉴스를 가져오는 중..."):
            news_content = get_news(fmt["needs_news"])

    st.toast(f"오늘의 코너: {fmt['label']}")
    with st.spinner("🎙️ 선생님이 원고를 톡톡 튀게 쓰는 중..."):
        raw = generate_radio_script(fmt_key, news_content)
        script = parse_and_update_storage(raw)
    with st.spinner("🎵 밝고 따뜻한 목소리로 녹음 중 (약 10초)..."):
        audio = text_to_speech(script)

    # 진도 갱신 (하루 1회 카운트)
    today = str(date.today())
    if st.session_state['last_date'] != today:
        st.session_state['day_count'] += 1
        st.session_state['last_date'] = today

    st.session_state['current_script'] = script
    st.session_state['current_audio'] = audio
    st.session_state['current_theme'] = fmt['label']
    save_progress()
    st.rerun()

# 출력부
if st.session_state['current_script']:
    st.success(f"✨ 방송 준비 완료 — {st.session_state['current_theme']}")
    st.markdown("### 🎧 오디오 스트리밍")
    st.audio(st.session_state['current_audio'], format="audio/mp3")
    st.caption("ℹ️ 본 음성은 AI로 생성된 합성 음성입니다.")
    st.markdown("---")
    st.markdown(st.session_state['current_script'])
else:
    st.write("버튼을 누르면 비타민처럼 활기찬 여배우의 영어 라디오가 시작됩니다 🎶")
