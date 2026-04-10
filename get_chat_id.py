"""Chat ID 확인용 임시 스크립트 - 세팅 후 삭제해도 됨"""
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler
from dotenv import load_dotenv
import os

load_dotenv()

async def start(update: Update, context):
    chat_id = update.effective_chat.id
    name = update.effective_user.first_name or "사용자"
    await update.message.reply_text(
        f"안녕하세요 {name}님!\n"
        f"당신의 Chat ID: {chat_id}\n\n"
        f"이 숫자를 부모님(관리자)에게 알려주세요."
    )
    print(f"[Chat ID 확인] {name}: {chat_id}")

def main():
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", start))
    print("Chat ID 확인 봇 실행 중... 각 사용자가 /start를 누르면 ID가 표시됩니다.")
    print("모두 확인되면 Ctrl+C로 종료하세요.\n")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
