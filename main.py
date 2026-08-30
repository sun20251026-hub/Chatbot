import os
import streamlit as st
import anthropic
from dotenv import load_dotenv
from rag import build_index, query_context, is_index_ready

# 로컬: .env 로드 / Streamlit Cloud: st.secrets 사용
load_dotenv()

def get_secret(key: str, default: str = "") -> str:
    """st.secrets(Streamlit Cloud) → os.environ(.env) → default 순으로 조회."""
    try:
        return st.secrets[key]
    except (KeyError, FileNotFoundError):
        return os.environ.get(key, default)

# ────────────────────────────────────────────────────────────────────────────
# 카카오톡 사용설명서 (시스템 프롬프트에 항상 포함)
# ────────────────────────────────────────────────────────────────────────────
PROFILE = """
당신은 카카오톡 사용설명서 어시스턴트입니다. 카카오톡의 모든 기능과 사용법에 대해 친절하게 설명합니다.

[카카오톡 기본 정보]
앱명: 카카오톡 / 버전: 모바일 26.7.2
용도: 메시징, 통화, 소셜 플랫폼
개발사: 카카오 (https://www.kakaocorp.com)

[주요 기능]
- 메시지: 1:1 채팅, 그룹 채팅, 오픈채팅
- 통화: 음성 통화, 영상 통화, 화면 공유
- 스토리: 사진, 영상, 텍스트 공유 및 피드
- 지갑: 송금, 결제, 포인트 관리
- 프로필: 닉네임, 프로필 사진, 상태 메시지 관리
- 설정: 알림, 개인정보, 보안, 테마 등 커스터마이징

[답변 방침]
- 카카오톡 사용법: PDF 자료를 우선 참고하여 상세히 설명
- 구체적인 기능 설명: 단계별 가이드 제공
- 모르는 내용: "사용설명서에서 확인할 수 없는 내용입니다"라고 답변
- 문제 해결: 구체적인 해결 방법 제시
- 모든 답변은 한국어로, 친절하고 이해하기 쉬운 톤
""".strip()


# ────────────────────────────────────────────────────────────────────────────
# Streamlit 설정
# ────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="카카오톡 사용설명서",
    page_icon="💬",
    layout="centered",
)

st.markdown("""
<style>
@import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard@v1.3.9/dist/web/variable/pretendardvariable-dynamic-subset.min.css');
html, body, [class*="css"] { font-family: 'Pretendard Variable', Pretendard, sans-serif; }
.source-box { background:#f0f9ff; border-left:3px solid #0891b2; padding:0.6rem 0.8rem;
              font-size:0.82rem; color:#334155; border-radius:0 6px 6px 0; margin-top:0.5rem; }
</style>
""", unsafe_allow_html=True)

st.title("💬 카카오톡 사용설명서")
st.caption("카카오톡 모바일 26.7.2의 모든 기능과 사용법에 대해 물어보세요.")

# ────────────────────────────────────────────────────────────────────────────
# 사이드바 — API 키 & RAG 인덱스 관리
# ────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.header("⚙️ 설정")

    api_key = get_secret("ANTHROPIC_API_KEY")
    if not api_key:
        api_key = st.text_input(
            "Anthropic API 키",
            type="password",
            placeholder="sk-ant-...",
        )

    st.divider()
    st.subheader("📚 사용설명서 데이터")

    ready = is_index_ready()
    if ready:
        st.success("✓ 사용설명서 준비 완료")
    else:
        st.warning("사용설명서 없음 — 관리자 로그인 후 로드하세요.")

    # 관리자 잠금 영역
    if "admin_unlocked" not in st.session_state:
        st.session_state.admin_unlocked = False

    if not st.session_state.admin_unlocked:
        admin_pw = st.text_input("관리자 비밀번호", type="password", placeholder="비밀번호 입력…")
        if st.button("로그인", use_container_width=True):
            correct = get_secret("ADMIN_PASSWORD", "admin1234")
            if admin_pw == correct:
                st.session_state.admin_unlocked = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
    else:
        st.success("관리자 모드")
        if st.button("📚 사용설명서 로드 / 재로드", use_container_width=True):
            with st.spinner("PDF 처리 중… (첫 실행 시 수 분 소요)"):
                try:
                    count = build_index()
                    st.success(f"✓ 완료: {count}개 항목 로드")
                    st.rerun()
                except FileNotFoundError as e:
                    st.error(str(e))
        if st.button("잠금", use_container_width=True, type="secondary"):
            st.session_state.admin_unlocked = False
            st.rerun()

    use_rag = st.toggle("📖 사용설명서 참고", value=ready, disabled=not ready)

    st.divider()
    n_results = st.slider("참고할 설명서 섹션 수", 1, 10, 5)

if not api_key:
    st.info("사이드바에서 Anthropic API 키를 입력하세요.")
    st.stop()

client = anthropic.Anthropic(api_key=api_key)

# ────────────────────────────────────────────────────────────────────────────
# 대화
# ────────────────────────────────────────────────────────────────────────────
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

if prompt := st.chat_input("카카오톡 사용법을 물어보세요…"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # RAG 검색
    rag_context = ""
    if use_rag and ready:
        rag_context = query_context(prompt, n_results=n_results)

    # 시스템 프롬프트 구성
    system_prompt = PROFILE
    if rag_context:
        system_prompt += f"\n\n[PDF 자료에서 검색된 관련 내용]\n{rag_context}"

    with st.chat_message("assistant"):
        with st.spinner("답변 생성 중…"):
            response = client.messages.create(
                model="claude-sonnet-4-6",
                max_tokens=1500,
                system=system_prompt,
                messages=[
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ],
            )
            answer = response.content[0].text

        st.markdown(answer)

        # 참고 자료 표시
        if rag_context:
            sources = set()
            for line in rag_context.splitlines():
                if line.startswith("[출처:"):
                    src = line.split("|")[0].replace("[출처:", "").strip()
                    sources.add(src)
            if sources:
                st.markdown(
                    "<div class='source-box'>📖 참고된 사용설명서 섹션: "
                    + ", ".join(sorted(sources))
                    + "</div>",
                    unsafe_allow_html=True,
                )

        st.session_state.messages.append({"role": "assistant", "content": answer})

# 초기화 버튼
if st.session_state.messages:
    if st.button("🔄 대화 초기화", type="secondary"):
        st.session_state.messages = []
        st.rerun()
