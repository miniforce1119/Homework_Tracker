# Google Compute Engine 배포 가이드

homework-bot을 GCE e2-micro (무료 tier)에 배포하는 방법입니다.

---

## STEP 1. GCE 인스턴스 생성

1. [Google Cloud Console](https://console.cloud.google.com) 접속
2. 기존 프로젝트(homeworkTracker) 선택
3. 좌측 메뉴 → **Compute Engine** → **VM 인스턴스**
4. 처음이면 **Compute Engine API 사용** 클릭 (활성화에 1~2분 소요)
5. **인스턴스 만들기** 클릭

### 인스턴스 설정

| 항목 | 값 |
|------|-----|
| 이름 | `homework-bot` |
| 리전 | `us-central1` (무료 tier 대상) |
| 영역 | `us-central1-a` |
| 머신 유형 | **e2-micro** (무료 tier) |
| 부팅 디스크 | **Debian 12**, 표준 영구 디스크 10GB |
| 방화벽 | 체크 불필요 (봇은 외부 접속 안 받음) |

6. **만들기** 클릭

> 무료 tier 조건: e2-micro 1대, us-central1, 30GB 디스크, 월 1GB 이그레스

---

## STEP 2. SSH 접속

인스턴스가 생성되면:

1. VM 인스턴스 목록에서 `homework-bot` 행의 **SSH** 버튼 클릭
2. 브라우저에서 SSH 터미널이 열림

---

## STEP 3. 프로젝트 파일 업로드

### 방법 A: Git clone (추천)

homework-bot이 GitHub에 올라가 있다면:

```bash
git clone https://github.com/본인계정/homework-bot.git
cd homework-bot
```

### 방법 B: SSH 창에서 직접 업로드

SSH 창 우측 상단의 **톱니바퀴** → **파일 업로드** 로 아래 파일들을 업로드:

- `bot.py`
- `config.py`
- `sheets_client.py`
- `requirements.txt`
- `.env`
- `credentials.json`
- `setup-gce.sh`
- `install-service.sh`
- `homework-bot.service`

업로드된 파일은 홈 디렉토리에 저장됩니다. 폴더로 이동:

```bash
mkdir -p ~/homework-bot
mv ~/bot.py ~/config.py ~/sheets_client.py ~/requirements.txt ~/.env ~/credentials.json ~/setup-gce.sh ~/install-service.sh ~/homework-bot.service ~/homework-bot/
cd ~/homework-bot
```

---

## STEP 4. 환경 설정

### 4-1. 초기 설정 스크립트 실행

```bash
cd ~/homework-bot
bash setup-gce.sh
```

Python, venv, 의존성 패키지가 자동으로 설치됩니다.

### 4-2. .env 파일 확인/수정

```bash
nano .env
```

로컬에서 사용하던 `.env` 내용과 동일하게 설정합니다.
저장: `Ctrl+O` → `Enter` → `Ctrl+X`

### 4-3. credentials.json 확인

```bash
ls -la credentials.json
```

파일이 있는지 확인합니다.

---

## STEP 5. 테스트 실행

서비스 등록 전에 먼저 직접 실행해서 정상 동작하는지 확인합니다:

```bash
cd ~/homework-bot
source .venv/bin/activate
python bot.py
```

- 로그에 `봇 시작!`이 나오면 성공
- 텔레그램에서 `/today` 명령어로 테스트
- 확인 후 `Ctrl+C`로 종료

---

## STEP 6. systemd 서비스 등록

봇을 백그라운드 서비스로 등록하면:
- VM이 재부팅되어도 **자동으로 다시 실행**
- 봇이 에러로 죽어도 **10초 후 자동 재시작**

```bash
cd ~/homework-bot
sudo bash install-service.sh
```

### 서비스 관리 명령어

```bash
# 상태 확인
sudo systemctl status homework-bot

# 실시간 로그 보기
sudo journalctl -u homework-bot -f

# 재시작
sudo systemctl restart homework-bot

# 중지
sudo systemctl stop homework-bot

# 시작
sudo systemctl start homework-bot
```

---

## STEP 7. 동작 확인

1. `sudo systemctl status homework-bot` → `active (running)` 확인
2. 텔레그램에서 `/today` 명령어 테스트
3. SSH 창을 닫아도 봇이 계속 동작하는지 확인

---

## 코드 업데이트 방법

봇 코드를 수정한 후 GCE에 반영하려면:

### Git을 사용하는 경우

```bash
cd ~/homework-bot
git pull
sudo systemctl restart homework-bot
```

### 수동 업로드하는 경우

1. SSH 창에서 파일 업로드
2. 파일을 `~/homework-bot/`으로 이동
3. `sudo systemctl restart homework-bot`

---

## 트러블슈팅

### 봇이 시작되지 않을 때

```bash
sudo journalctl -u homework-bot --no-pager -n 50
```

로그에서 에러 메시지를 확인합니다.

### 흔한 문제

| 증상 | 원인 | 해결 |
|------|------|------|
| `ModuleNotFoundError` | venv 패키지 미설치 | `source .venv/bin/activate && pip install -r requirements.txt` |
| `FileNotFoundError: credentials.json` | 파일 경로 문제 | `ls ~/homework-bot/credentials.json` 확인 |
| `Unauthorized` | 봇 토큰 오류 | `.env`의 `TELEGRAM_BOT_TOKEN` 확인 |
| Google Sheets 접근 에러 | 서비스 계정 공유 안 됨 | 시트에 서비스 계정 이메일 공유 확인 |

### 로컬 PC에서 봇 중지

GCE에서 봇을 실행하면, **로컬 PC의 봇은 반드시 중지**해야 합니다.
같은 토큰으로 두 곳에서 동시에 polling하면 충돌합니다.
