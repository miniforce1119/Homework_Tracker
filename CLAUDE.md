# Homework-Bot

아이들(지후, 윤후)의 일일 학습 과제를 관리하는 Telegram 봇. GCE에서 운영 중.

## 프로젝트 구조

- `bot.py` — 메인 봇 로직 (명령어, 콜백, 스케줄러)
- `sheets_client.py` — Google Sheets API 클라이언트 (과제 조회, 결과 기록, 알파 계산)
- `config.py` — 환경변수 로딩 (.env)
- `credentials.json` — Google 서비스 계정 키 (git 미포함)
- `.env` — 시크릿 (git 미포함)

## 기술 스택

- Python 3.13
- python-telegram-bot 21.10 (내장 JobQueue로 스케줄링)
- gspread 6.1.4 (Google Sheets API)
- GCE e2-micro (free tier), systemd 서비스

## 주요 기능

- **일일 과제 전송**: 매일 22:00 KST, 아이별 과제를 인라인 키보드로 전송
- **결과 체크**: 완료/부분완료/못함/NA 버튼으로 체크, Google Sheets에 기록
- **메모**: 텍스트 입력으로 메모 추가
- **밀린 숙제**: `/catchup`으로 이번 주 미완료 항목 확인 및 처리
- **부모 요약**: 매일 23:00 부모에게 일일 리포트 전송, 미체크 항목은 "미응답" 자동 기록
- **알파 포인트**: 매주 일요일 21:30 주간 알파 계산, 목요일 23:00 지난주 결과 리마인드
- **NA 처리**: 수업 취소 등으로 해당없는 항목은 NA로 표시, 알파 계산에서 제외

## 스케줄

| 시간 | 동작 |
|------|------|
| 매일 22:00 | 아이에게 과제 전송 |
| 매일 23:00 | 부모 일일 요약 (미응답 자동 기록) |
| 목요일 23:00 | 지난주 알파 리마인드 (금요일 게임시간 확인용) |
| 일요일 21:30 | 주간 알파 포인트 계산 |

## 사용자 구성

- **아빠**: PARENT_CHAT_ID (부모 뷰 - 버튼 없이 조회만)
- **엄마**: PARENT2_CHAT_ID (부모 뷰) + JIHU_CHAT_ID/YUNHU_CHAT_ID (아이 뷰 - 태블릿으로 수신)
- 엄마 계정이 부모+아이 뷰 모두 수신하는 멀티 구조

## Google Sheets 구조

- `지후` / `윤후` 시트: 과제 계획 (과목, 세부항목, 교재명, 횟수, 요일, 알파체크 규칙)
- `지후_결과` / `윤후_결과` 시트: 일별 결과 기록 (날짜, 과목, 세부항목, 교재명, 결과, 메모)
- `알파점수` 시트: 주간 알파 포인트 기록

## 알파 포인트 규칙 (7개 패턴)

sheets_client.py의 `_parse_alpha_rule`에서 regex로 파싱:
1. "주N회 모두 O 일때 M분, 아니면 -M분" (보상+벌점)
2. "주N회 모두 O 일때 M분" (보상만)
3. "주N회 모두 입력값이 있을때 M분, 아니면 -M분" (메모 기반)
4. "입력될때마다 M분씩 추가" (건별 보상)
5. "입력될때 M분" (입력 유무)
6. "0이 입력될때마다 M분씩 추가, 아니면 -M분" (특정값 체크)
7. "시험 점수가 N 이상일때 M분" (점수 기반)

NA 처리: `effective_required = min(required, expected_count - na_count)`

## GCE 배포

- 인스턴스: GCE e2-micro
- 서비스: `sudo systemctl {start|stop|restart|status} homework-bot`
- 로그: `sudo journalctl -u homework-bot -f`
- 경로: `/home/user/homework-bot/`

## 로컬 개발

```bash
cd c:\김우근\project\homework-bot
.venv\Scripts\activate
python bot.py
```

**주의**: 로컬과 GCE 동시 실행 시 409 Conflict 발생. 테스트 전 GCE 봇 중지 필요.

## 봇 명령어

- `/start` — 봇 시작, Chat ID 확인
- `/today` — 오늘 할일 보기
- `/status` — 오늘 진행 상황
- `/summary` — 부모용 요약
- `/week` — 주간 통계
- `/alpha` — 알파 포인트 조회
- `/catchup` — 밀린 숙제 확인
