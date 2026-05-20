---
name: deploy
description: 로컬에서 수정/테스트 후 GCE에 배포하는 워크플로우
---

# Homework-Bot 배포 워크플로우

로컬에서 기능 수정/추가 → 테스트 → GCE 배포까지의 전체 프로세스.

## 1단계: GCE 봇 중지

로컬 테스트 전에 GCE 봇을 반드시 중지해야 한다 (동시 실행 시 409 Conflict).

```bash
# GCE SSH 접속 후
sudo systemctl stop homework-bot
```

사용자에게 GCE 봇을 중지했는지 확인을 요청한다.

## 2단계: 로컬 테스트

```bash
cd c:\김우근\project\homework-bot
.venv\Scripts\activate
python bot.py
```

- 테스트 중에는 `.env`의 JIHU_CHAT_ID를 PARENT_CHAT_ID 값으로 임시 변경하면 아빠 계정에서 아이 뷰(버튼 포함)를 볼 수 있다
- 테스트 완료 후 반드시 `.env`를 원래 값으로 복원한다
- 테스트 데이터가 Google Sheets에 남을 수 있으므로 사용자에게 정리 안내

## 3단계: 커밋 및 푸시

```bash
git add <변경된 파일들>
git commit -m "변경 내용 설명"
git push origin main
```

## 4단계: GCE 배포

```bash
# GCE SSH 접속 후
cd ~/homework-bot
git pull origin main
sudo systemctl start homework-bot
sudo systemctl status homework-bot
```

## 5단계: 배포 확인

- `systemctl status`에서 `active (running)` 확인
- 초기 409 Conflict 로그는 정상 (로컬 폴링 세션 캐시가 사라지면 해소)
- Telegram에서 `/today` 등으로 정상 응답 확인

## 주의사항

- 로컬과 GCE 봇을 **절대 동시 실행하지 않는다**
- `.env`와 `credentials.json`은 git에 포함되지 않으므로 GCE에서 별도 관리
- GCE 로그 확인: `sudo journalctl -u homework-bot -f`
