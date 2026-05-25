# OPERATIONS

운영 환경, 토큰 관리, 인시던트 대응 가이드. **다른 PC에서 작업할 때 가장 먼저 확인할 것.**

## 작업 환경 (3곳에서 작업)

| 환경 | 역할 | 위치 |
|------|------|------|
| **GCE e2-micro** | 운영 (24/7 polling) | `~/homework-bot/`, systemd `homework-bot` 서비스 |
| **집 PC** | 로컬 개발 | `C:\project\homework-tracker` |
| **회사 강의장 PC** | 로컬 개발 | (경로 확인 필요) |

같은 GitHub 레포(`miniforce1119/Homework_Tracker`) + 같은 봇 토큰을 3곳이 공유. **동시에 봇을 띄우면 안 됨** (Telegram 409 Conflict).

## ⚠️ 단일 인스턴스 규칙

Telegram Bot API는 같은 토큰에 대해 동시 long-polling을 허용하지 않음.
두 곳에서 동시에 `python bot.py`를 돌리면:
- 약 30초마다 polling 권한을 뺏고 뺏김 → 양쪽 다 메시지 일부만 수신
- 로그에 `telegram.error.Conflict: terminated by other getUpdates request` 반복
- 사용자 체감: 봇이 응답을 가끔 빼먹음, 버튼 눌러도 반영 안 됨

**원칙**: GCE가 마스터. 로컬에서 코드를 돌릴 거면 GCE 봇을 먼저 멈춘다.

```bash
# GCE SSH
sudo systemctl stop homework-bot
# ... 로컬 테스트 ...
sudo systemctl start homework-bot
```

## Conflict 디버깅 체크리스트

GCE 로그에 `Conflict: terminated by other getUpdates request`가 반복되면:

```bash
# 1. GCE 자체 중복 실행 확인 (보통 1개)
ps aux | grep -E "python.*bot.py" | grep -v grep

# 2. webhook이 안 걸려있는지 확인 (polling 모드에선 비어있어야 함)
curl -s "https://api.telegram.org/bot$(grep TELEGRAM_BOT_TOKEN .env | cut -d= -f2)/getWebhookInfo"

# 3. 로그에서 Conflict 패턴 확인
sudo journalctl -u homework-bot --since "1 hour ago" --no-pager | grep -iE "conflict" | tail -20
```

GCE는 깨끗한데 Conflict가 계속 뜨면 → **다른 PC(집/회사)에서 봇이 돌고 있는 것**. 해당 PC에 접근해서 `python.exe` 프로세스 종료. 접근 불가하면 토큰 갱신.

## 토큰 갱신 절차

회사 PC 등에 접근 불가하거나, 토큰이 외부에 노출됐을 때.

**순서가 중요**: revoke 전에 GCE를 먼저 멈추지 않으면, GCE가 옛 토큰으로 401 받고 systemd가 10초마다 재시작 시도하는 루프에 빠짐.

```bash
# Step 1: GCE에서 봇 중지
sudo systemctl stop homework-bot

# Step 2: 텔레그램 @BotFather에서 /revoke → 새 토큰 받기
#         이 시점에 다른 PC의 봇은 자동으로 401로 죽음

# Step 3: GCE .env 백업 + 토큰 교체 (GCE SSH에서 직접 입력 권장, 채팅 노출 금지)
cd ~/homework-bot
cp .env .env.bak.$(date +%Y%m%d_%H%M%S)
nano .env  # TELEGRAM_BOT_TOKEN 줄 수정

# Step 4: 검증
curl -s "https://api.telegram.org/bot<NEW_TOKEN>/getMe"
# {"ok":true,"result":{...}} 확인

# Step 5: 재시작 + 로그 확인
sudo systemctl start homework-bot
sleep 3
sudo journalctl -u homework-bot --since "1 minute ago" --no-pager | tail -20
# 'getUpdates 200 OK'가 10초 간격으로 깨끗하게 나오고 Conflict 없어야 함

# Step 6: 텔레그램에서 /today 또는 /start로 실제 응답 확인
```

**토큰 노출 주의**: 새 토큰을 채팅·이슈·커밋·로그에 절대 붙이지 않는다. 노출됐다면 즉시 다시 revoke.

## 다른 PC에서 작업 시작할 때

1. `git pull origin main` — 최신 코드 받기
2. `git status` 깨끗한지 확인 (다른 PC에서 미커밋 작업 남아있으면 충돌)
3. **GCE 봇을 먼저 멈추고** 로컬 테스트
4. 작업 끝나면 커밋·푸시 → GCE에서 `git pull` + `systemctl restart`

## .env / credentials.json 동기화

git에 안 들어가는 시크릿이라 새 PC에는 직접 복사 필요. 자세한 절차는 [HOME_SETUP_GUIDE.md](HOME_SETUP_GUIDE.md) 참고.

회사 PC의 `.env` 토큰이 옛것으로 남아있으면 위험. **회사 PC에 갈 일이 있으면 `.env`의 `TELEGRAM_BOT_TOKEN`을 GCE 현재 값과 맞추거나, 빈 값으로 두기**.

## 시크릿 노출 시 대응

| 노출 항목 | 대응 |
|----------|------|
| `TELEGRAM_BOT_TOKEN` | BotFather `/revoke` → 새 토큰 → GCE 업데이트 |
| `credentials.json` | Google Cloud Console → 서비스 계정 → 키 삭제 → 새 키 발급 → GCE 업로드 |
| `GOOGLE_SHEETS_ID` | 시트 URL — 일반적으로 보안 위협 없음 (서비스 계정 없이는 접근 불가) |
| Chat ID | 노출돼도 자체로는 위협 없음 (봇 토큰 없이는 메시지 못 보냄) |

## 인시던트 로그

큰 사건은 여기 기록해 미래 디버깅 단서로 활용.

### 2026-05-25 — 회사 PC 봇이 동시 polling
- 증상: GCE 로그에 `Conflict: terminated by other getUpdates request` 반복, 봇 응답이 가끔 빠짐
- 원인: 회사 강의장 PC에서 옛 코드의 봇이 백그라운드로 계속 polling 중이었음
- 조치: BotFather `/revoke` → 새 토큰 → GCE `.env` 업데이트 → 회사 PC 봇은 401로 자동 사망
- 후속: 회사 PC `.env`의 옛 토큰 제거 + 자동 시작 등록 여부 확인 필요
