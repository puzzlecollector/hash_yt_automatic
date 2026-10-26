"""LLM steps: pick topics, write the script/cards/metadata, pick shots, QA."""
import json
from . import llm

CHANNEL_RULES = """
[채널 규칙 - 반드시 지킬 것]
- 한국어 뉴스 해설 쇼츠. 사실만, 기사에 근거한 내용만. 추측·과장 금지. 숫자·날짜·이름은 기사와 일치해야 함.
- 의혹/폭로/수사 중 사안은 '의혹', '주장', '~로 알려졌다' 표현을 쓰고 당사자 반박/부인이 있으면 반드시 포함. 확인 안 된 내용은 '확인되지 않았다'고 명시.
- 사적 개인(일반인)의 실명·얼굴·계정 노출 금지. 미성년자 관련 장면·언급 최소화. 욕설·혐오 표현 금지. 투자 관련이면 '투자 권유 아님'.
- 자막/카드/썸네일 문구에 한자(美, 中 등) 금지 - 폰트에 한자가 없음. 이모지도 금지.
- 문체: 짧고 리듬감 있게. 첫 문장은 훅(가장 놀라운 사실). 마지막 문장은 시청자에게 질문.
"""

SKIP_RULES = """
[제외할 주제]
- 광고성 키워드, 상품 추천, 단순 날씨/운세/로또, 진행 중인 경기의 결과 예측(경기 끝나기 전), 일반인 사망·자살·성범죄 피해자 중심 사건,
  미성년자가 중심인 사건, 선거 여론조작 소지, 기사 근거가 부족해 사실 확인이 어려운 주제.
"""


def select_topics(cands, used, n):
    rows = [{"keyword": c["keyword"], "traffic": c["traffic"], "age_h": c["age_h"], "score": c["score"],
             "curve": c["curve"], "prev_traffic": c["prev_traffic"], "news": [x["title"] for x in c["news"][:3]]} for c in cands[:15]]
    prompt = f"""한국 구글 트렌드 실시간 검색어 후보입니다. score는 상승세 점수(높을수록 지금 오르는 중)입니다.
최근에 이미 만든 주제: {json.dumps([u['keyword'] for u in used], ensure_ascii=False)}
{SKIP_RULES}
위 규칙과 상승세를 고려해 유튜브 쇼츠로 만들 주제를 최대 {n + 2}개 골라 우선순위 순으로 주세요(앞의 {n}개가 실패하면 뒤를 씁니다).
같은 사건을 다룬 키워드는 하나만. 이미 만든 주제와 같은 사건이면 제외.

후보:
{json.dumps(rows, ensure_ascii=False, indent=1)}

JSON만 출력:
{{"picks":[{{"keyword":"...","why":"한 줄"}}], "skipped":[{{"keyword":"...","why":"한 줄"}}]}}"""
    return llm.ask_json(prompt, max_tokens=3000)


PLAN_SCHEMA = """{
 "skip": false, "skip_reason": "",
 "slug": "짧은_폴더이름(한글_가능, 공백없이)",
 "tag": "카테고리 · 키워드 (헤더 위 빨간 태그, 12자 이내)",
 "header1": "헤더 1줄(흰색, 14자 이내)", "header2": "헤더 2줄(노란색, 13자 이내)",
 "lines": ["문장 단위 대본. 화면 자막 단위는 ' / '로 구분 (각 덩어리 4~14자)", "..."],
 "tts_replace": [["화면표기","읽는발음"], ["1976년","천구백칠십육 년"], ["SNS","에스엔에스"]],
 "keys": ["자막에서 노란색으로 강조할 문자열(자막 덩어리 안에 정확히 그대로 있어야 함)"],
 "cards": [{"line": 0, "top": "카드 위 작은 라벨", "num": "큰 글씨(8자 이내)", "bot": "아래 설명(26자 이내)", "accent": "yellow|red|blue"}],
 "end_card": {"q": "시청자 질문(16자 이내)", "sub": "댓글로 의견 남겨주세요"},
 "bgm_prompt": "ElevenLabs 음악 프롬프트(영어, 분위기에 맞게, no vocals)",
 "footage_queries": ["유튜브 검색어(한국어) 3~4개 - 방송사 뉴스 클립이 잘 나올 검색어"],
 "footage_subject": "영상에 꼭 나와야 하는 대상(인물/장소/물건) 설명",
 "thumbnail": {"pill": "빨간 알약 라벨(12자)", "line1": "흰 큰 글씨(12자)", "line2": "노란 작은 줄(16자)", "big": "중간 초대형 노란 글씨(8자)", "badge": "하단 빨간 박스(14자)"},
 "upload": {"titles": ["제목1 #shorts","제목2 #shorts","제목3 #shorts"], "description": "설명란(사실 요약 3~5문장, 출처 명시)", "tags": ["태그"], "hashtags": ["#태그"]},
 "risk": "low|medium|high", "risk_notes": "사실확인/명예훼손/저작권 등 주의점"
}"""


def write_plan(keyword, research, today):
    arts = "\n\n".join(f"[기사{i+1}] {a['title']} ({a.get('source','')})\n{a['text']}" for i, a in enumerate(research["articles"]))
    heads = "\n".join(f"- {h['title']} | {h.get('source','')} | {h.get('date','')}" for h in research["headlines"][:10])
    prompt = f"""오늘은 {today}입니다. 키워드 '{keyword}'로 45~58초 분량 유튜브 쇼츠를 기획하세요.
{CHANNEL_RULES}
{SKIP_RULES}
- 대본 총 글자수 330~400자(공백 포함), 문장 6~8개. 각 문장은 카드 1개와 대응(cards[].line = 문장 번호, 0부터, 오름차순). 마지막 문장(질문)에는 카드를 만들지 말 것(엔드카드가 자동으로 붙음).
- tts_replace: 숫자/영문/기호가 TTS에서 어색하게 읽힐 것을 한국어 발음으로. 따옴표(')는 [["'",""]]로 제거.
- keys는 핵심 숫자·고유명사 위주로 10~20개.
- 근거 기사가 부족하거나 제외 주제면 skip=true와 이유만.

[기사 본문]
{arts or '(본문 없음)'}

[관련 헤드라인]
{heads}

아래 형식의 JSON만 출력:
{PLAN_SCHEMA}"""
    return llm.ask_json(prompt, max_tokens=8000)


def pick_shots(plan, segments, sources, sheets, cwd, feedback=None):
    src_desc = "\n".join(f"- {s['id']}: [{s['channel']}] {s['title']} (길이 {s['dur']:.0f}s, {s['w']}x{s['h']}, 업로드 {s.get('date','')})" for s in sources)
    segs = "\n".join(f"{g['i']}: {g['t0']:.2f}~{g['t1']:.2f}s ({g['t1']-g['t0']:.1f}s) \"{g['text']}\"" for g in segments)
    prompt = f"""쇼츠 '{plan['header1']} / {plan['header2']}'의 자료화면을 고릅니다. 꼭 나와야 할 대상: {plan.get('footage_subject','')}
이미지 각각은 소스 영상 하나의 컨택트시트입니다(파일명 = 소스 ID, 칸마다 노란 숫자 = 초). 맨 위 큰 프레임은 화면 구성 확인용.

소스:
{src_desc}

내레이션 구간(각 구간마다 장면 하나):
{segs}

규칙:
- 각 구간 내용과 맞는 장면을 고르고, 같은 장면을 반복하지 말 것. 앵커/기자 얼굴만 나오는 컷, 자막만 있는 그래픽, 광고, 다른 사건 장면은 피할 것.
- 영상 제목·채널로 보아 다른 인물/사건이면 그 소스는 쓰지 말 것. 관중석·행인 등 일반인 얼굴 클로즈업, 미성년자(아이) 클로즈업은 절대 고르지 말 것.
- 원본 영상에 큰 자막/그래픽 글자가 박힌 장면은 피할 것(내 자막과 겹침). 관련 장면이 정말 없으면 그 구간은 가장 무난한 일반 장면(건물 외경, 거리, 경기장 전경 등)을 쓸 것.
- start는 그 칸 시간 근처(장면이 바뀌지 않는 구간 안), 구간 길이만큼 이어지는 장면이어야 함.
- crop: 소스별로 방송사 하단 자막띠·상단 로고를 잘라낼 비율. top/bottom = 남길 영역(0~1). 예: 하단 자막띠가 있으면 bottom 0.80.
- 세로(9:16) 소스는 yc(0~1)로 세로 위치 지정.
- credit: 화면에 표시할 출처(방송사/채널명 짧게).
- thumb: 썸네일용 프레임 2개(a=위 큰 사진, b=아래 사진). 인물 주제면 그 인물이 잘 보이는 프레임.

{('[이전 시도 검수 지적 - 반드시 해결할 것]' + chr(10) + feedback) if feedback else ''}
JSON만:
{{"use":["A","B"], "crop":{{"A":{{"top":0.0,"bottom":0.82,"yc":0.5}}}}, "credit":{{"A":"YTN"}},
 "shots":[{{"i":0,"src":"A","start":12.0}}], "thumb":{{"a":{{"src":"A","t":10.0}},"b":{{"src":"B","t":5.0}}}}, "notes":"" }}"""
    return llm.ask_json(prompt, images=sheets, max_tokens=6000, cwd=cwd)


def qa(plan, frames, cwd):
    prompt = f"""완성된 쇼츠 '{plan['header1']} / {plan['header2']}'의 미리보기 프레임들입니다. 업로드 전 검수하세요.
확인: (1) 글자가 화면 밖으로 넘치거나 깨진 글자(□) (2) 자료화면이 내용과 무관하거나 엉뚱한 인물 (3) 일반인 얼굴/번호판이 크게 식별됨
(4) 미성년자 클로즈업 (5) 방송사 하단 자막띠가 잘리지 않고 크게 남음 (6) 화면이 검거나 깨짐
(7) 원본 영상에 박힌 자막/그래픽의 사실(숫자·지명·사건)이 내레이션·카드와 다른 사례라 시청자가 혼동할 수 있음 (8) 자료화면이 좌우/상하 검은 여백으로 좁게 보이거나 같은 영상 한 개만 계속 반복됨.
치명적 문제(2,3,4,6,7,8)가 있으면 ok=false.
JSON만: {{"ok":true,"issues":["..."]}}"""
    return llm.ask_json(prompt, images=frames, max_tokens=1500, cwd=cwd)
