#!/bin/bash
# GCE 인스턴스 초기 설정 스크립트
# 사용법: bash setup-gce.sh

set -e

echo "=== homework-bot GCE 설정 시작 ==="

# 1. 시스템 업데이트 + Python 설치
sudo apt update && sudo apt upgrade -y
sudo apt install -y python3 python3-pip python3-venv git

# 2. 프로젝트 디렉토리 생성
mkdir -p ~/homework-bot
cd ~/homework-bot

# 3. 가상환경 생성 + 의존성 설치
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "=== 설정 완료 ==="
echo ""
echo "다음 단계:"
echo "1. .env 파일을 생성하세요:  nano ~/homework-bot/.env"
echo "2. credentials.json 파일을 업로드하세요"
echo "3. systemd 서비스를 등록하세요:  sudo bash install-service.sh"
