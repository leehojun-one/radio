import streamlit as st
import feedparser
import ssl
import random
from openai import OpenAI

# 1. 인증서 에러 방지
if hasattr(ssl, '_create_unverified_context'):
    ssl._create_default_https_context = ssl._create_unverified_context

# 2. OpenAI API 초기화
client = OpenAI(api_key="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")

# ==========================================
# 🗂️ 호준 님의 족보 데이터 및 방송 메모리 초기화
# ==========================================
if 'hojun_past_patterns' not in st.session_state:
    st.session_state['hojun_past_patterns'] = [
        {"pattern": "I'm planning to", "meaning": "~할 계획이에요"},
        {"pattern": "I'm calling to", "meaning": "~하려고 전화드렸습니다"},
        {"pattern": "What do you think about ~?", "meaning": "~에 대해 어떻게 생각하세요?"},
        {"pattern": "Why don't we ~?", "meaning": "~하는 게 어떨까요?"},
        {"pattern": "How was your weekend?", "meaning": "주말 어떻게 보내셨어요?"},
        {"pattern": "Could you please tell me about ~?", "meaning": "~에 대해 알려주실 수 있나요? (견적/비용 요청)"}
    ]

if 'hojun_past_words' not in st.session_state:
    st.session_state['hojun_past_words'] = [
        {"word": "Potential", "meaning": "잠재력"},
        {"word": "Boost", "meaning": "증대시키다"},
        {"word": "Streamline", "meaning": "간소화하다"},
        {"word": "Prospective", "meaning": "잠재적인 (고객/파트너)"},
        {"word": "Get back on track", "meaning": "궤도에 오르다"}
    ]

if 'current_script' not in st.session_state:
    st.session_state['current_script'] = None
if 'current_audio' not in st.session_state:
    st.session_state['current_audio'] = None
if 'current_theme' not in st.session_state:
    st.session_state['current_theme'] = None

def get_realtime_news():
    rss_url = "http://feeds.bbci.co.uk/news/business/rss.xml"
    feed = feedparser.parse(rss_url)
    if not feed.entries:
        return "Global market trends are showing significant shifts ahead of the economic forum."
    random_entry = random.choice(feed.entries[:5])
    return random_entry.title + " - " + random_entry.summary

def generate_radio_script(news_content, past_patterns, past_words, selected_theme):
    patterns_str = ", ".join([f"'{p['pattern']}'({p['meaning']})" for p in past_patterns])
    words_str = ", ".join([f"'{w['word']}'({w['meaning']})" for w in past_words])
    
    # 💡 영어 문장 직후 무조건 한글 뜻을 라디오 멘트로 읽어주도록 프롬프트를 대폭 강화했습니다!
    system_prompt = f"""
    당신은 아침 라디오 방송을 진행하는 통통 튀고, 활기차며, 비타민처럼 밝은 에너지를 가진 '20~30대 젊은 여배우 영어 선생님'입니다.
    오늘의 청취자는 오직 당신이 너무나 아끼는 '호준 씨' 한 명뿐입니다. 

    [★ 오늘의 방송 스페셜 무작위 테마: {selected_theme} ★]
    오늘 방송은 반드시 지정된 테마의 분위기를 중심 축으로 삼아 이끌어가야 합니다.
    - 테마가 '문학 작품'일 경우: 유명 고전의 철학에서 영감을 받아 호준 씨에게 교훈을 줄 수 있는 멋진 영어 문장(2~3문장)을 직접 창작해 들려주세요.
    - 테마가 '시사/교양 상식'일 경우: 역사, 상식, 경제 스토리에 관한 흥미로운 영어 지식을 다루세요.
    - 테마가 '유머/위트'일 경우: 유쾌하고 재치 있는 일상 에피소드를 다루세요.

    [★ 필수: 영어 예문 직후 한국어 해석/뜻풀이 연동 규칙 ★]
    대본 전체를 통틀어 영어 문장이나 예문(과거 복습 문장, 본문 예문, 패턴 챌린지 문장 등)이 튀어나올 때는 **절대로 영어만 말하고 넘어가면 안 됩니다.**
    운전 중인 호준 씨가 귀로 듣고 바로 직관적으로 이해할 수 있도록, 영어 문장을 말한 직후 **"이 문장은 한국어로 ~라는 뜻이에요!"** 또는 **"~라는 의미를 담고 있답니다"**라며 정확한 한국어 번역과 핵심 단어 뜻을 다정하게 이어서 읊어주세요.

    [★ 영어 원문 강제 표출 및 컬러링 규칙 ★]
    대본 가장 상단에 [Today's Text] 섹션을 두고 오늘 다룰 영어 원문(2~3문장)을 표출하세요. 핵심 표현은 반드시 **:red[핵심 표현]** 형태로 컬러 처리를 해주세요.

    [호준 씨의 누적 족보 기록장 연동 지침]
    - 오프닝이나 토크 중에 과거 족보 패턴({patterns_str})이나 단어({words_str}) 중 최소 1~2개를 상큼하게 소환하되, 반드시 해당 표현이 들어간 실전 예문 1개와 그에 대한 한국어 해석을 대사로 함께 풀어주세요.

    [대본 구성 지침]
    1. 📝 [Today's Text] : 오늘의 스페셜 영어 원문 표출 (핵심 표현 컬러 처리)
    2. ✨ 활력 폭발 오프닝 & 족보 실전 예문/뜻 복습 (최소 500자)
    3. 📰 본문 테마 융합 토크 & 핵심 문장/뜻풀이 해설 (최소 800자)
    4. 📐 딕션의 비밀: 0.5초 영작 챌린지 (최소 500자) : 오늘 배운 표현용 마스터 패턴 1개와 응용 문장 2개를 주되, 문장마다 한글 뜻을 완벽하게 매칭하여 설명하세요.
    5. 🗂️ 오늘의 노트 & 해피 클로징 (최소 400자) : 필수 단어 3개 정리.

    [★ 데이터 자동 추출 마커 ★]
    대본이 완전히 끝난 후, 맨 마지막 줄에 정확히 아래 서식을 추가해 주세요.
    |||EXTRACT|||
    NEW_PATTERN: 오늘새로배운패턴구조 | 패턴뜻
    NEW_WORD1: 오늘새단어1 | 뜻1
    NEW_WORD2: 오늘새단어2 | 뜻2
    NEW_WORD3: 오늘새단어3 | 뜻3
    """
    user_content = f"[오늘의 뉴스 정보]\n{news_content}"
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        temperature=0.85
    )
    return response.choices[0].message.content

def parse_and_update_storage(raw_script):
    if "|||EXTRACT|||" in raw_script:
        parts = raw_script.split("|||EXTRACT|||")
        clean_script = parts[0].strip()
        data_part = parts[1].strip()
        
        for line in data_part.split("\n"):
            if line.startswith("NEW_PATTERN:"):
                content = line.replace("NEW_PATTERN:", "").strip()
                if "|" in content:
                    pat, mean = content.split("|")
                    if not any(p['pattern'].lower() == pat.strip().lower() for p in st.session_state['hojun_past_patterns']):
                        st.session_state['hojun_past_patterns'].append({"pattern": pat.strip(), "meaning": mean.strip()})
            elif "NEW_WORD" in line:
                content = line.split(":", 1)[1].strip()
                if "|" in content:
                    wrd, mean = content.split("|")
                    if not any(w['word'].lower() == wrd.strip().lower() for w in st.session_state['hojun_past_words']):
                        st.session_state['hojun_past_words'].append({"word": wrd.strip(), "meaning": mean.strip()})
        return clean_script
    return raw_script

def generate_instant_lesson(selected_item, item_type):
    system_prompt = """
    당신은 상큼 발랄하고 에너지가 넘치는 '젊은 여배우 영어 senescence 선생님'입니다.
    호준 씨가 요청한 표현에 대해 최고급 비즈니스 실전 예문 2개를 주고, 그 예문들의 한글 뜻과 미묘한 비즈니스 뉘앙스를 아주 톡톡 튀고 명쾌하게 설명해 주세요.
    """
    user_content = f"호준 씨가 요청한 {item_type}: [{selected_item}]에 대한 실시간 1분 원포인트 레슨을 만들어 주세요."
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_content}],
        temperature=0.7
    )
    return response.choices[0].message.content

def text_to_speech(text):
    response = client.audio.speech.create(
        model="tts-1",
        voice="nova",
        input=text
    )
    return response.content

# ==========================================
# 🎨 스트림릿 프리미엄 웹 UI
# ==========================================

st.set_page_config(page_title="여배우의 무작위 영라디오", page_icon="📻")

st.title("📻 여배우의 영라디오")
st.markdown("🔍 **[Premium Class] 매일 새로운 테마와 실시간 적립 족보 시스템**")
st.divider()

# 사이드바 동적 족보 표시
with st.sidebar:
    st.header("🗂️ 호준 님의 영어 족보 (Ver 1.0)")
    st.caption("💡 표현이나 단어를 누르면 즉석 오디오 레슨이 시작됩니다.")
    st.write("---")
    
    st.subheader("📝 누적 핵심 패턴")
    for p in st.session_state['hojun_past_patterns']:
        if st.button(f"🔗 {p['pattern']}\n({p['meaning']})", key=f"pat_{p['pattern']}", use_container_width=True):
            with st.spinner("🎙️ 상큼한 원포인트 오디오 굽는 중..."):
                lesson = generate_instant_lesson(f"{p['pattern']} ({p['meaning']})", "비즈니스 핵심 패턴")
                st.session_state['instant_lesson'] = lesson
                st.session_state['lesson_title'] = p['pattern']
                st.session_state['instant_audio'] = text_to_speech(lesson)
    
    st.write("---")
    st.subheader("📚 오늘의 단어장")
    for w in st.session_state['hojun_past_words']:
        if st.button(f"🗂️ {w['word']} : {w['meaning']}", key=f"wrd_{w['word']}", use_container_width=True):
            with st.spinner("🎙️ 상큼한 원포인트 오디오 굽는 중..."):
                lesson = generate_instant_lesson(f"{w['word']} ({w['meaning']})", "필수 비즈니스 단어")
                st.session_state['instant_lesson'] = lesson
                st.session_state['lesson_title'] = w['word']
                st.session_state['instant_audio'] = text_to_speech(lesson)

# 🎯 실시간 원포인트 레슨 오디오 출력 창
if 'instant_lesson' in st.session_state:
    st.success(f"🎯 여배우 선생님의 원포인트 족보 레슨: [{st.session_state['lesson_title']}]")
    st.audio(st.session_state['instant_audio'], format="audio/mp3")
    st.info(st.session_state['instant_lesson'])
    if st.button("❌ 레슨 창 닫기"):
        del st.session_state['instant_lesson']
        del st.session_state['instant_audio']
        st.rerun()
    st.divider()

# 📻 메인 화면 재생 버튼 클릭 시 로직
if st.button("▶️ 오늘 자 랜덤 스페셜 방송 청취하기", use_container_width=True):
    
    themes = [
        "📚 고전 및 유명 문학 작품의 구절과 삶의 지혜 테마",
        "💡 알아두면 지식이 풍성해지는 흥미로운 시사/교양 상식 테마",
        "🍿 하루를 유쾌하게 만드는 재미있는 세상 이야기와 위트 유머 테마"
    ]
    selected_theme = random.choice(themes)
    
    with st.spinner("📡 최신 글로벌 경제 뉴스를 분석하는 중입니다..."):
        today_news = get_realtime_news()
    
    st.toast(f"오늘의 주파수 테마: {selected_theme.split('테마')[0]}")
    
    with st.spinner(f"🎙️ 여배우 선생님이 원고를 톡톡 튀게 작성 중입니다..."):
        raw_radio_script = generate_radio_script(today_news, st.session_state['hojun_past_patterns'], st.session_state['hojun_past_words'], selected_theme)
        radio_script = parse_and_update_storage(raw_radio_script)
    
    with st.spinner(f"🎵 밝고 활기찬 목소리로 오디오 녹음 중 (약 10초 소요)..."):
        main_audio_bytes = text_to_speech(radio_script)
    
    st.session_state['current_script'] = radio_script
    st.session_state['current_audio'] = main_audio_bytes
    st.session_state['current_theme'] = selected_theme.split('테마')[0]
    
    st.rerun()

# 📺 화면 출력부
if st.session_state['current_script'] is not None:
    st.success(f"✨ 오늘의 스페셜 방송 준비 완료! ({st.session_state['current_theme']})")
    st.markdown("### 🎧 오디오 방송 스트리밍")
    st.audio(st.session_state['current_audio'], format="audio/mp3")
    st.markdown("---")
    st.markdown(st.session_state['current_script'])
else:
    st.write("버튼을 누르시면 비타민처럼 활기찬 젊은 여배우의 영어 라디오가 시작됩니다!")