# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

# Homework-Bot

아이들(지후, 윤후)의 일일 학습 과제를 관리하는 Telegram 봇. GCE에서 24/7 운영 중.

## 핵심 구조 (한 그림)

```
Google Sheets (계획)        Telegram (UX)              Google Sheets (결과)
  ┌────────────┐           ┌──────────────┐           ┌────────────────┐
  │ 지후 / 윤후 │ ──read──► │   bot.py     │ ──write─► │ 지후_결과       │
  │ (계획+규칙) │           │ JobQueue +   │           │ 윤후_결과       │
  └────────────┘           │ Callbacks    │           │ 알파점수        │
                           └──────┬───────┘           └────────────────┘
                                  │
                                  ▼
                         daily_state / memo_waiting
                         (인메모리, 재시작 시 휘발)
```

3개 파일로 나뉘어 있다:
- `bot.py` — Telegram I/O, 스케줄러(JobQueue), 콜백 라우팅, 인메모리 상태
- `sheets_client.py` — Google Sheets I/O, 알파 규칙 파싱, 미완료 조회
- `config.py` — `.env` 로딩 (`Config` 정적 클래스)

`bot.py`의 글로벌 `sheets: SheetsClient` 싱글톤이 `main()`에서 주입되어 모든 핸들러가 공유한다.

## 콜백 데이터 프로토콜 (디버깅 시 필수)

Telegram inline button은 64바이트 제한이 있어 짧은 토큰을 쓴다. `bot.py` `handle_callback()`에서 파싱:

| 형식 | 의미 |
|------|------|
| `noop` | 이미 체크된 항목 (안내 토스트만) |
| `{child_id}:{task_idx}:{c\|p\|f\|n}` | 오늘 할일 결과 (완료/부분/못함/NA) |
| `{child_id}:{task_idx}:m` | 메모 추가 버튼 |
| `cu:{child_id}:{task_idx}:{MM-DD}:{c\|p\|n}` | catchup 결과 (원래 날짜 덮어쓰기) |
| `cum:{child_id}:{task_idx}:{MM-DD}` | catchup 메모 |

`child_id`는 `Config.CHILDREN` dict의 인덱스 (0=지후, 1=윤후). `_child_name_to_id` / `_id_to_child_name`로 변환.

`MM-DD`만 콜백에 담고 연도는 `datetime.now(KST).year`로 복원 → **연말~연초 catchup은 연도가 어긋날 수 있다**.

## 인메모리 상태 (재시작 시 소실)

- `daily_state[(chat_id, child_name)]` — 오늘의 tasks/results/message_ids
- `daily_state[(chat_id, f"catchup_{child_name}")]` — catchup 세션
- `memo_waiting[chat_id]` — 다음 텍스트 입력을 메모로 받기 위한 대기 상태

봇 재시작 시 모든 세션이 사라지므로, 사용자는 `/today`나 `/catchup`을 다시 호출해야 버튼이 동작한다. 새 기능 추가 시 영속화가 필요하면 Sheets에 저장하거나 별도 캐시 도입을 고려.

## Google Sheets 구조

### 계획 시트 (부모가 관리)
시트명: `지후`, `윤후`. 컬럼은 **헤더 이름으로 자동 감지** (`_detect_columns`) — 순서가 달라도 OK.

인식하는 헤더: `과목`, `종류`, `세부 항목`(또는 `세부항목`), `교재명`, `횟수`, `요일`, `알파...`로 시작하는 컬럼.

특수 규칙:
- 과목 셀이 비어있고 세부항목/종류만 있으면 **이전 행의 과목을 상속** (병합 셀 흉내)
- `요일`이 "월,수,금" 형식 또는 "매일" — `_parse_days`가 파싱
- `요일`이 비고 `횟수`에 "주N회"만 있으면 매일 표시 (요일 미지정)

### 결과 시트 (봇이 자동 생성)
시트명: `지후_결과`, `윤후_결과`. 컬럼: 날짜, 과목, 세부항목, 교재명, 결과, 메모.

결과 값: `완료` / `부분완료` / `못함` / `미응답` / `NA`.

write_result는 (날짜+과목+세부항목)로 **upsert** — 중복 행 안 만들고 기존 행 update.

### 알파점수 시트 (봇이 자동 생성)
시트명: `알파점수`. 컬럼: 이름, 주차, 시작일, 점수, 상세. 주차 = `dt.isocalendar()[1]`.

## 알파 포인트 규칙 (7개 패턴)

`sheets_client.py`의 `_parse_alpha_rule`에서 regex로 매칭. **위에서부터 순서대로 매칭**되므로 패턴 추가 시 더 구체적인 패턴을 위에 두어야 한다.

1. `주N회 모두 O 일때 M분, 아니면 -M분` — 보상+벌점
2. `주N회 모두 O 일때 M분` — 보상만 (패턴1보다 느슨하므로 아래)
3. `주N회 모두 입력값이 있을때 M분, 아니면 -M분` — 메모 기반
4. `입력될때마다 M분씩 추가` — 건별 보상
5. `입력될때 M분` — 입력 유무
6. `0이 입력될때마다 M분씩 추가, 아니면 -M분` — 특정값 체크
7. `시험 점수가 N 이상일때 M분` — 점수 기반

번호는 의미상 ID이고, **코드 물리 순서는 1·2·3·6·4·5·7**이다. 패턴6은 패턴4(`입력될때마다 M분씩 추가`) 정규식의 부분 문자열에 걸리므로 **반드시 패턴4보다 먼저 검사**해야 한다 (안 그러면 패턴6이 가려져 0점 보상·기타값 벌점이 무시됨).

**NA 처리**: `effective_required = min(required, expected_count - na_count)` — NA만큼 주간 목표 횟수를 줄여 페널티를 면제.

## 즉시 게임시간 적립 (라이브 알파)

게임시간 = 알파 포인트(분). 기본은 일요일 21:30 주간 일괄 계산이지만, 두 경우는 **즉시 재계산·적립**한다:

- **책이름 등 메모 입력** (`handle_message`) → 입력 기반 패턴(4·5)이 있으면 즉시 +N분
- **밀린 숙제 catchup 완료** (`handle_callback`의 `cu:` 완료/부분) → 즉시 +N분 "복구"

구현: `_credit_game_time`(bot.py) → `recalc_live_alpha`(sheets_client.py)가 이번 주를 **`finalize=False`로 재계산**(임계 미달 페널티는 보류, 보상/복구분만)하고 `알파점수` 시트의 이번 주 행을 **upsert**한다. 증가분(delta)이 양수면 그 chat에 알림.

**이중집계 방지**: 일요일 정규 계산(`finalize=True`)이 같은 결과 시트를 읽어 같은 행을 멱등 덮어쓴다 → 라이브 적립분은 일요일에 페널티 포함 최종값으로 정정될 뿐 중복 가산되지 않는다.

**페널티 시점**: `finalize=False`는 패턴1·3·6의 `-M분`을 0으로 보류. 주중엔 보상만 보이고, 페널티는 일요일에만 확정 (catchup으로 만회할 여지를 줌).

**주의**: 라이브 적립은 메모·catchup 이벤트에서만 트리거. 평소 `/today` 완료로 임계(패턴2 등)를 채운 보상은 다음 메모/catchup 또는 일요일에 반영된다.

## 자동 스케줄 (모두 KST)

| 시간 | 동작 | 함수 |
|------|------|------|
| 매일 22:00 | 아이에게 과제 전송 | `scheduled_send_tasks` |
| 매일 23:00 | 부모 일일 요약 + **미응답 자동 기록** | `scheduled_parent_summary` |
| 목요일 23:00 | 지난주 알파 리마인드 (`scheduled_parent_summary` 내부) | `_send_alpha_reminder` |
| 일요일 21:30 | 주간 알파 계산 + 저장 + 전송 | `scheduled_weekly_alpha` |

스케줄러는 `python-telegram-bot`의 내장 `JobQueue` (APScheduler 기반)를 사용. `bot.py` `main()`에서 `run_daily`로 등록.

`record_no_response=True`는 **23:00 스케줄에서만** True — 그 외 시간에 `/summary`를 누르면 "미체크"로만 표시되고 시트에 안 박힌다.

## 사용자 구성 (멀티 뷰)

- **아빠 폰** (`PARENT_CHAT_ID`): 부모 뷰 — 요약/통계 수신, 버튼 없음
- **엄마 폰 + 태블릿** (`PARENT2_CHAT_ID` + `JIHU_CHAT_ID` + `YUNHU_CHAT_ID`):
  - 엄마 계정 하나가 부모 뷰 + 지후 뷰 + 윤후 뷰 **모두 수신**
  - `.env`에서 `PARENT2_CHAT_ID` = `JIHU_CHAT_ID` = `YUNHU_CHAT_ID`로 설정
  - `_chat_id_to_child_names`가 리스트를 반환하는 이유 — 한 chat_id에 여러 아이가 매핑

신규 chat_id가 메시지를 보내면 `/start`에서 본인의 chat_id를 알려준다 → `.env`에 등록.

## 봇 명령어

| 명령어 | 대상 | 설명 |
|--------|------|------|
| `/start` | 모두 | 등록 확인, 미등록 시 본인 Chat ID 표시 |
| `/today` | 아이/부모 | 오늘 할일 (아이=버튼, 부모=조회만) |
| `/status` | 아이/부모 | 오늘 진행 상황 |
| `/summary` | 부모 | 일일 요약 (미응답 기록 안 함) |
| `/week` | 부모 | 이번 주 통계 |
| `/alpha` | 아이/부모 | 누적 알파 포인트 |
| `/catchup` | 아이/부모 | 이번 주 월~어제 미완료 항목 재체크 |

## 기술 스택

- Python 3.13 + venv (`venv/` 폴더, `.gitignore`됨)
- `python-telegram-bot==21.10` (`Application` + `JobQueue`, polling 모드)
- `gspread==6.1.4` + `google-auth==2.38.0`
- `python-dotenv==1.1.0`
- GCE e2-micro (free tier, us-central1) + systemd 서비스

`requirements.txt`에 `APScheduler==3.11.0`도 있지만 직접 임포트는 안 함 (PTB가 내부적으로 사용).

## 로컬 개발

```powershell
# 가상환경 활성화 (Windows PowerShell)
venv\Scripts\Activate.ps1

# 또는 cmd
venv\Scripts\activate.bat

# 의존성 설치
pip install -r requirements.txt

# 봇 실행
python bot.py
```

정상 시작 로그:
```
Google Sheets 연결 완료
스케줄 등록: 할일 전송 22:00, 부모 요약 23:00, 알파 계산 일요일 21:30, ...
봇 시작!
```

**필수**: `.env`와 `credentials.json`은 git에 없음. `.env.example` 참고하여 직접 생성 또는 다른 PC에서 복사. `HOME_SETUP_GUIDE.md` 참고.

`get_chat_id.py`는 신규 사용자의 chat_id를 콘솔에 찍어주는 일회성 유틸 (봇 토큰만 있으면 됨).

## ⚠️ 동시 실행 금지 (다중 환경 운영)

GCE + 집 PC + 회사 강의장 PC 3곳에서 같은 레포·같은 토큰으로 작업한다.
두 곳에서 동시에 봇을 띄우면 Telegram 409 Conflict로 양쪽 다 메시지를 놓친다.

**원칙**: GCE가 마스터. 로컬 테스트 전에 반드시 GCE 봇을 멈춘다.

```bash
# GCE SSH에서
sudo systemctl stop homework-bot
# ... 로컬 테스트 ...
sudo systemctl start homework-bot
```

**Conflict 디버깅, 토큰 갱신, 인시던트 로그**는 [OPERATIONS.md](OPERATIONS.md) 참고.
- 다른 PC에서 작업 시작할 때 가장 먼저 확인할 문서
- 토큰 갱신은 순서가 중요 (revoke 전 GCE stop 필수)

## GCE 배포

- 인스턴스: e2-micro / us-central1 / Debian 12
- 서비스 파일: `homework-bot.service` (템플릿, `__USER__` 치환)
- 등록 스크립트: `install-service.sh` (sudo 필요)
- 초기 설정 스크립트: `setup-gce.sh` (Python + venv + deps)
- 서비스 제어: `sudo systemctl {start|stop|restart|status} homework-bot`
- 로그: `sudo journalctl -u homework-bot -f`
- 코드 업데이트: `cd ~/homework-bot && git pull && sudo systemctl restart homework-bot`

상세 절차는 `GCE_DEPLOY_GUIDE.md` 참고.

## 배포 워크플로우 (deploy 스킬)

`.claude/skills/deploy/SKILL.md`에 정의됨. 핵심 순서:

1. GCE 봇 중지 (`sudo systemctl stop homework-bot`)
2. 로컬에서 수정 + 테스트 (`python bot.py`)
3. 커밋 + 푸시 (`git push origin main`)
4. GCE에서 `git pull` + `sudo systemctl restart`
5. 텔레그램에서 `/today` 등으로 동작 확인

테스트 시 `.env`의 `JIHU_CHAT_ID`를 `PARENT_CHAT_ID`로 임시 변경하면 아빠 계정에서 아이 뷰(버튼 포함)를 미리 볼 수 있다. **테스트 후 반드시 원복**.

## 작업 시 유의

- 시트 컬럼 추가/순서 변경은 `_detect_columns`가 흡수하지만, **헤더 이름**이 정확해야 한다 (`과목`, `세부항목`/`세부 항목` 둘 다 OK).
- 알파 규칙 신규 패턴 추가 시 `_parse_alpha_rule` 위쪽에 더 구체적인 패턴을 두지 않으면 패턴2(`주N회 모두 O 일때 M분`)에 먼저 잡힌다.
- 텍스트 메시지(`handle_message`)는 `memo_waiting`에 있는 chat_id만 처리 — 명령어 외의 일반 텍스트는 무시되는 것이 정상.
- 시간대 모든 곳에서 `KST = ZoneInfo("Asia/Seoul")` 사용. naive datetime 쓰지 말 것.
- 결과 시트 행 매칭 키는 (날짜, 과목, 세부항목) — 같은 과목/세부항목 페어가 한 시트에 중복되면 안 됨.
