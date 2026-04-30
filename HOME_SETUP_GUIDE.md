# Homework Bot 집 PC 설정 가이드

> 회사 PC에서 돌리던 homework-bot을 집 PC에서 실행하기 위한 가이드

---

## 1단계: 코드 가져오기

```bash
git clone https://github.com/miniforce1119/Homework_Tracker.git
cd Homework_Tracker
pip install -r requirements.txt
```

---

## 2단계: 보안 파일 생성 (2개)

GitHub에는 보안 파일이 포함되어 있지 않으므로 직접 만들어야 합니다.

### 파일 1: `.env`

`Homework_Tracker/` 폴더에 `.env` 파일을 새로 만들고 아래 내용 입력:

```
TELEGRAM_BOT_TOKEN=8637183823:AAGdCLAHV6y98IbkVHVrKHe2gp573nJC3Y4
PARENT_CHAT_ID=8746731544
PARENT2_CHAT_ID=8795221692
JIHU_CHAT_ID=8795221692
YUNHU_CHAT_ID=8795221692
GOOGLE_SHEETS_ID=1rW9od576Dgk5HWw0zZlqO-HnpCqzEnuXgrXLs_XinqY
GOOGLE_CREDENTIALS_FILE=credentials.json
TASK_SEND_HOUR=22
TASK_SEND_MINUTE=0
SUMMARY_HOUR=23
SUMMARY_MINUTE=0
```

### 파일 2: `credentials.json`

Google 서비스 계정 키 파일입니다.
회사 PC `c:\김우근\project\homework-bot\credentials.json`을 집 PC로 복사하세요.

**전달 방법:**
- 자신의 Gmail(head1119@gmail.com)로 첨부 발송 → 집에서 다운로드 → 보낸 메일 삭제
- 또는 USB로 복사

`credentials.json`을 `Homework_Tracker/` 폴더에 넣으면 됩니다.

---

## 3단계: 실행

```bash
cd Homework_Tracker
python bot.py
```

정상 동작하면 텔레그램에서 봇 메시지가 오는지 확인하세요.

---

## 보안 주의사항

| 항목 | 주의 |
|------|------|
| `.env` | GitHub에 push 금지 (`.gitignore`에 등록됨) |
| `credentials.json` | GitHub에 push 금지 (`.gitignore`에 등록됨) |
| 봇 토큰 유출 시 | Telegram BotFather에서 `/revoke`로 재발급 |
| credentials.json 메일 전달 후 | 보낸 메일에서 삭제 |
| remote URL | 토큰 노출 없이 `https://github.com/miniforce1119/Homework_Tracker.git` 사용 |

---

## 트러블슈팅

### "ModuleNotFoundError" 에러
```bash
pip install -r requirements.txt
```

### "credentials.json not found" 에러
`credentials.json` 파일이 `Homework_Tracker/` 폴더 안에 있는지 확인

### "Telegram bot token invalid" 에러
`.env` 파일의 `TELEGRAM_BOT_TOKEN` 값 확인 (공백이나 줄바꿈 없어야 함)

### 봇이 두 곳에서 동시에 실행되면
한 곳에서만 실행해야 합니다. 회사 PC에서 봇을 종료한 후 집에서 실행하세요.
동시에 두 곳에서 돌리면 Telegram API 충돌이 발생합니다.
