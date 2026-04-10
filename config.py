import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # Telegram
    BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    PARENT_CHAT_ID = int(os.getenv("PARENT_CHAT_ID", "0"))
    PARENT2_CHAT_ID = int(os.getenv("PARENT2_CHAT_ID", "0"))  # 엄마

    # 아이 설정: {시트이름: chat_id}
    CHILDREN = {
        "지후": int(os.getenv("JIHU_CHAT_ID", "0")),
        "윤후": int(os.getenv("YUNHU_CHAT_ID", "0")),
    }

    # Google Sheets
    GOOGLE_SHEETS_ID = os.getenv("GOOGLE_SHEETS_ID", "")
    GOOGLE_CREDENTIALS_FILE = os.getenv("GOOGLE_CREDENTIALS_FILE", "credentials.json")

    # 스케줄 시간 (KST)
    TASK_SEND_HOUR = int(os.getenv("TASK_SEND_HOUR", "22"))
    TASK_SEND_MINUTE = int(os.getenv("TASK_SEND_MINUTE", "0"))
    SUMMARY_HOUR = int(os.getenv("SUMMARY_HOUR", "23"))
    SUMMARY_MINUTE = int(os.getenv("SUMMARY_MINUTE", "0"))

    # 타임존
    TIMEZONE = "Asia/Seoul"
