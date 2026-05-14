#!/bin/bash
# systemd 서비스 등록 스크립트
# 사용법: sudo bash install-service.sh

set -e

USERNAME=$(whoami)

# 서비스 파일 복사 + 사용자명 치환
sed "s/__USER__/$USERNAME/g" homework-bot.service | sudo tee /etc/systemd/system/homework-bot.service > /dev/null

# systemd 등록 + 시작
sudo systemctl daemon-reload
sudo systemctl enable homework-bot
sudo systemctl start homework-bot

echo ""
echo "=== 서비스 등록 완료 ==="
echo ""
echo "상태 확인:  sudo systemctl status homework-bot"
echo "로그 보기:  sudo journalctl -u homework-bot -f"
echo "재시작:     sudo systemctl restart homework-bot"
echo "중지:       sudo systemctl stop homework-bot"
