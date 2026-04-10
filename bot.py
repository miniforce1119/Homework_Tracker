import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    CallbackQueryHandler,
    MessageHandler,
    filters,
)

from config import Config
from sheets_client import SheetsClient

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

KST = ZoneInfo(Config.TIMEZONE)
DAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]

# 인메모리 상태 저장
# {(chat_id, child_name): {date, tasks, results, message_ids}}
daily_state = {}
# {chat_id: {child_name, date, task_idx, task, message_id}} - 메모 입력 대기
memo_waiting = {}

sheets: SheetsClient = None


# ─── 유틸리티 ───────────────────────────────────────────────

def build_task_message(child_name: str, tasks: list[dict], results: dict) -> tuple[str, InlineKeyboardMarkup]:
    """할일 메시지 + 인라인 키보드 생성"""
    now = datetime.now(KST)
    date_str = f"{now.month}월 {now.day}일 {DAY_NAMES[now.weekday()]}요일"
    text = f"📚 {child_name}의 오늘 할일 ({date_str})\n\n"

    keyboard = []
    all_done = True

    for i, task in enumerate(tasks):
        result = results.get(i)
        if result:
            emoji = {"완료": "✅", "부분완료": "△", "못함": "✗", "미응답": "🔇"}.get(result, "❓")
            text += f"{emoji} {i + 1}. {task['label']}\n"
            # 이미 체크된 항목은 버튼 비활성화 표시
            keyboard.append(
                [InlineKeyboardButton(f"{i + 1}. {emoji} {result}", callback_data="noop")]
            )
        else:
            all_done = False
            text += f"⬜ {i + 1}. {task['label']}\n"
            child_id = _child_name_to_id(child_name)
            keyboard.append(
                [
                    InlineKeyboardButton("✅완료", callback_data=f"{child_id}:{i}:c"),
                    InlineKeyboardButton("△부분", callback_data=f"{child_id}:{i}:p"),
                    InlineKeyboardButton("✗못함", callback_data=f"{child_id}:{i}:f"),
                ]
            )

    if all_done:
        text += "\n🎉 오늘 할일을 모두 체크했어! 수고했어!"
    else:
        text += "\n각 항목의 버튼을 눌러서 결과를 체크해줘!"
        text += "\n💬 메모를 남기려면 텍스트를 보내면 돼"

    return text, InlineKeyboardMarkup(keyboard)


def _child_name_to_id(name: str) -> str:
    """아이 이름 → 짧은 ID"""
    children = list(Config.CHILDREN.keys())
    return str(children.index(name)) if name in children else "0"


def _id_to_child_name(child_id: str) -> str:
    """짧은 ID → 아이 이름"""
    children = list(Config.CHILDREN.keys())
    idx = int(child_id)
    return children[idx] if idx < len(children) else children[0]


def _chat_id_to_child_name(chat_id: int) -> str | None:
    """chat_id → 첫 번째 매칭되는 아이 이름 (단일)"""
    for name, cid in Config.CHILDREN.items():
        if cid == chat_id:
            return name
    return None


def _chat_id_to_child_names(chat_id: int) -> list[str]:
    """chat_id → 매칭되는 모든 아이 이름 (복수)"""
    return [name for name, cid in Config.CHILDREN.items() if cid == chat_id]


def _is_parent(chat_id: int) -> bool:
    """부모 계정인지 확인"""
    return chat_id in (Config.PARENT_CHAT_ID, Config.PARENT2_CHAT_ID)


def _parent_chat_ids() -> list[int]:
    """활성화된 부모 chat_id 리스트"""
    ids = [Config.PARENT_CHAT_ID]
    if Config.PARENT2_CHAT_ID != 0:
        ids.append(Config.PARENT2_CHAT_ID)
    return ids


async def _send_to_parents(context_or_bot, text: str):
    """모든 부모에게 메시지 전송"""
    bot = context_or_bot.bot if hasattr(context_or_bot, 'bot') else context_or_bot
    for chat_id in _parent_chat_ids():
        try:
            await bot.send_message(chat_id=chat_id, text=text)
        except Exception as e:
            logger.error(f"부모 메시지 전송 실패 (chat_id={chat_id}): {e}")


# ─── 명령어 핸들러 ──────────────────────────────────────────

async def cmd_start(update: Update, context):
    """봇 시작 명령어"""
    chat_id = update.effective_chat.id
    child_names = _chat_id_to_child_names(chat_id)

    if child_names:
        names_str = ", ".join(child_names)
        await update.message.reply_text(
            f"안녕 {names_str}! 🏠\n"
            f"매일 저녁 {Config.TASK_SEND_HOUR}시에 오늘의 할일을 보내줄게.\n\n"
            f"명령어:\n"
            f"/today - 오늘 할일 보기\n"
            f"/status - 오늘 진행 상황"
        )
    elif _is_parent(chat_id):
        children_str = ", ".join(Config.CHILDREN.keys())
        await update.message.reply_text(
            f"부모님 계정으로 연결되었습니다. 👋\n"
            f"관리 대상: {children_str}\n\n"
            f"명령어:\n"
            f"/summary - 오늘 요약 보기\n"
            f"/week - 이번 주 통계"
        )
    else:
        await update.message.reply_text(
            f"등록되지 않은 사용자입니다.\n"
            f"당신의 Chat ID: {chat_id}\n"
            f".env 파일에 이 ID를 등록해주세요."
        )


async def cmd_today(update: Update, context):
    """오늘 할일 수동 요청"""
    chat_id = update.effective_chat.id
    child_names = _chat_id_to_child_names(chat_id)

    if child_names:
        # 아이 계정: 매칭되는 모든 아이의 할일 전송
        for name in child_names:
            await _send_tasks_to_chat(context, name, chat_id)
    elif _is_parent(chat_id):
        # 부모 계정: 모든 아이의 할일 전송 (버튼 없이)
        for name in Config.CHILDREN:
            await _send_tasks_to_chat(context, name, chat_id, parent_view=True)
    else:
        await update.message.reply_text("등록되지 않은 사용자입니다.")


async def cmd_status(update: Update, context):
    """오늘 진행 상황 확인"""
    chat_id = update.effective_chat.id
    child_names = _chat_id_to_child_names(chat_id)

    if not child_names:
        if _is_parent(chat_id):
            child_names = list(Config.CHILDREN.keys())
        else:
            await update.message.reply_text("등록되지 않은 사용자입니다.")
            return

    now = datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d")

    for child_name in child_names:
        results = sheets.get_daily_results(child_name, date_str)

        if not results:
            await update.message.reply_text(f"{child_name}: 오늘 아직 체크한 항목이 없어!")
            continue

        text = f"📊 {child_name} 진행 상황 ({now.month}월 {now.day}일)\n\n"
        for r in results:
            emoji = {"완료": "✅", "부분완료": "△", "못함": "✗"}.get(r["결과"], "❓")
            text += f"{emoji} {r['과목']} — {r['세부항목']}"
            if r["메모"]:
                text += f" 💬{r['메모']}"
            text += "\n"

        completed = sum(1 for r in results if r["결과"] == "완료")
        total = len(results)
        text += f"\n📈 달성률: {round(completed / total * 100)}% ({completed}/{total})"

        await update.message.reply_text(text)


async def cmd_summary(update: Update, context):
    """부모용 요약"""
    chat_id = update.effective_chat.id
    if not _is_parent(chat_id):
        await update.message.reply_text("부모 계정에서만 사용 가능합니다.")
        return

    await _send_parent_summary(context)


async def cmd_week(update: Update, context):
    """부모용 주간 통계"""
    chat_id = update.effective_chat.id
    if not _is_parent(chat_id):
        await update.message.reply_text("부모 계정에서만 사용 가능합니다.")
        return

    now = datetime.now(KST)
    # 이번 주 월~오늘까지의 날짜 리스트
    monday = now - timedelta(days=now.weekday())
    dates = [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(now.weekday() + 1)]

    text = f"📊 이번 주 통계 ({dates[0]} ~ {dates[-1]})\n\n"

    for child_name in Config.CHILDREN:
        stats = sheets.get_weekly_stats(child_name, dates)
        text += f"👤 {child_name}\n"
        text += f"  ✅ 완료: {stats['completed']}건\n"
        text += f"  △ 부분완료: {stats['partial']}건\n"
        text += f"  ✗ 미완료: {stats['incomplete']}건\n"
        text += f"  📈 달성률: {stats['rate']}%\n\n"

    await _send_to_parents(context, text)


async def cmd_alpha(update: Update, context):
    """알파 포인트 조회 (아이 + 부모 모두 사용 가능)"""
    chat_id = update.effective_chat.id
    child_names = _chat_id_to_child_names(chat_id)

    if not child_names:
        if _is_parent(chat_id):
            child_names = list(Config.CHILDREN.keys())
        else:
            await update.message.reply_text("등록되지 않은 사용자입니다.")
            return

    for child_name in child_names:
        alpha = sheets.get_cumulative_alpha(child_name)

        text = f"⭐ {child_name}의 알파 포인트\n\n"
        text += f"🏆 누적 점수: {alpha['total']}분\n\n"

        if alpha["weeks"]:
            text += "📅 주차별 기록:\n"
            for w in alpha["weeks"]:
                sign = "+" if w["점수"] >= 0 else ""
                text += f"  {w['주차']}: {sign}{w['점수']}분\n"
        else:
            text += "아직 기록이 없어! 일요일 저녁에 계산돼."

        await update.message.reply_text(text)


async def cmd_catchup(update: Update, context):
    """밀린 숙제 보기"""
    chat_id = update.effective_chat.id
    child_names = _chat_id_to_child_names(chat_id)

    if not child_names:
        if _is_parent(chat_id):
            child_names = list(Config.CHILDREN.keys())
        else:
            await update.message.reply_text("등록되지 않은 사용자입니다.")
            return

    now = datetime.now(KST)
    monday = now - timedelta(days=now.weekday())
    # 월요일 ~ 어제까지 (오늘은 /today로 체크)
    today_str = now.strftime("%Y-%m-%d")
    week_dates = []
    for i in range(now.weekday()):  # 월~어제
        d = (monday + timedelta(days=i)).strftime("%Y-%m-%d")
        week_dates.append(d)

    if not week_dates:
        await update.message.reply_text("월요일이라 아직 밀린 숙제가 없어!")
        return

    for child_name in child_names:
        incomplete = sheets.get_incomplete_tasks(child_name, week_dates)

        if not incomplete:
            await update.message.reply_text(f"🎉 {child_name}: 밀린 숙제가 없어! 대단해!")
            continue

        child_id = _child_name_to_id(child_name)
        total = len(incomplete)

        # 헤더
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📋 {child_name}의 밀린 숙제 — {total}개",
        )

        # catchup 상태 저장
        state_key = (chat_id, f"catchup_{child_name}")
        daily_state[state_key] = {
            "date": today_str,
            "tasks": incomplete,
            "results": {},
        }

        # 항목별 메시지
        is_parent_view = _is_parent(chat_id) and not _chat_id_to_child_names(chat_id)
        for i, task in enumerate(incomplete):
            day_name = DAY_NAMES[task["weekday"]]
            prev = task["prev_result"]
            prev_emoji = {"미응답": "🔇", "못함": "✗", "미체크": "⬜"}.get(prev, "❓")
            text = f"[{day_name}] {task['label']} — {prev_emoji}{prev}"

            if is_parent_view:
                keyboard = None
            else:
                # cu:child_id:idx:date:result
                date_short = task["date"][5:]  # "04-08"
                keyboard = InlineKeyboardMarkup([[
                    InlineKeyboardButton("✅완료", callback_data=f"cu:{child_id}:{i}:{date_short}:c"),
                    InlineKeyboardButton("△부분", callback_data=f"cu:{child_id}:{i}:{date_short}:p"),
                ]])

            msg = await context.bot.send_message(
                chat_id=chat_id,
                text=text,
                reply_markup=keyboard,
            )
            daily_state[state_key][f"msg_{i}"] = msg.message_id


# ─── 콜백 핸들러 (버튼 탭) ──────────────────────────────────

async def handle_callback(update: Update, context):
    """인라인 버튼 콜백 처리"""
    query = update.callback_query

    if query.data == "noop":
        await query.answer("이미 체크된 항목이야!")
        return

    parts = query.data.split(":")
    chat_id = update.effective_chat.id
    now = datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d")

    # catchup 버튼 처리: "cu:child_id:idx:date_short:result_code"
    if parts[0] == "cu" and len(parts) == 5:
        _, child_id, idx_str, date_short, result_code = parts
        idx = int(idx_str)
        child_name = _id_to_child_name(child_id)
        original_date = f"{now.year}-{date_short}"  # "2026-04-08"

        result_map = {"c": "완료", "p": "부분완료"}
        result_text = result_map.get(result_code, "완료")
        result_emoji = {"c": "✅", "p": "△"}.get(result_code, "❓")

        state_key = (chat_id, f"catchup_{child_name}")
        state = daily_state.get(state_key)
        if not state or idx >= len(state["tasks"]):
            await query.answer("잘못된 요청입니다.")
            return

        task = state["tasks"][idx]

        # 원래 날짜의 결과를 덮어쓰기
        try:
            sheets.write_result(child_name, original_date, task, result_text)
        except Exception as e:
            logger.error(f"catchup Sheets 기록 실패: {e}")

        day_name = DAY_NAMES[task["weekday"]]
        checked_text = f"{result_emoji} [{day_name}] {task['label']} — {result_text}"
        child_id_str = _child_name_to_id(child_name)

        # 메모 추가 버튼 (catchup용): "cum:child_id:idx:date_short"
        checked_keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("💬 메모 추가", callback_data=f"cum:{child_id_str}:{idx}:{date_short}"),
        ]])
        await query.answer(f"{result_emoji} {task['과목']} {result_text}!")
        await query.edit_message_text(text=checked_text, reply_markup=checked_keyboard)
        return

    # catchup 메모 버튼 처리: "cum:child_id:idx:date_short"
    if parts[0] == "cum" and len(parts) == 4:
        _, child_id, idx_str, date_short = parts
        idx = int(idx_str)
        child_name = _id_to_child_name(child_id)
        original_date = f"{now.year}-{date_short}"

        state_key = (chat_id, f"catchup_{child_name}")
        state = daily_state.get(state_key)
        if not state or idx >= len(state["tasks"]):
            await query.answer("잘못된 요청입니다.")
            return

        task = state["tasks"][idx]
        memo_waiting[chat_id] = {
            "child_name": child_name,
            "date": original_date,
            "task_idx": idx,
            "task": task,
            "message_id": query.message.message_id,
        }

        await query.answer("메모를 입력해줘!")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📝 {task['과목']}/{task['세부항목']} 메모를 입력해줘:",
        )
        return

    # 메모 추가 버튼 처리: "child_id:task_idx:m"
    if len(parts) == 3 and parts[2] == "m":
        child_id, task_idx_str, _ = parts
        task_idx = int(task_idx_str)
        child_name = _id_to_child_name(child_id)

        state_key = (chat_id, child_name)
        state = daily_state.get(state_key)
        if not state or task_idx >= len(state["tasks"]):
            await query.answer("잘못된 요청입니다.")
            return

        task = state["tasks"][task_idx]

        # 메모 대기 상태 저장
        memo_waiting[chat_id] = {
            "child_name": child_name,
            "date": date_str,
            "task_idx": task_idx,
            "task": task,
            "message_id": query.message.message_id,
        }

        await query.answer("메모를 입력해줘!")
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📝 {task['과목']}/{task['세부항목']} 메모를 입력해줘:",
        )
        return

    # 결과 체크 버튼 처리: "child_id:task_idx:c/p/f"
    try:
        child_id, task_idx_str, result_code = parts
        task_idx = int(task_idx_str)
    except ValueError:
        await query.answer("잘못된 요청입니다.")
        return

    child_name = _id_to_child_name(child_id)
    result_map = {"c": "완료", "p": "부분완료", "f": "못함"}
    result_text = result_map.get(result_code, "완료")
    result_emoji = {"c": "✅", "p": "△", "f": "✗"}.get(result_code, "❓")

    # 인메모리 상태 업데이트 (chat_id + child_name 조합)
    state_key = (chat_id, child_name)
    state = daily_state.get(state_key)
    if not state or state["date"] != date_str:
        await query.answer("오늘 할일을 다시 불러와주세요. /today")
        return

    if task_idx >= len(state["tasks"]):
        await query.answer("잘못된 항목입니다.")
        return

    task = state["tasks"][task_idx]
    state["results"][task_idx] = result_text

    # Google Sheets에 기록
    try:
        sheets.write_result(child_name, date_str, task, result_text)
    except Exception as e:
        logger.error(f"Sheets 기록 실패: {e}")

    # 해당 메시지를 체크 완료 + 메모 버튼 표시
    total = len(state["tasks"])
    child_id_str = _child_name_to_id(child_name)
    checked_text = f"{result_emoji} {task_idx+1}/{total}  {task['label']} — {result_text}"
    checked_keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("💬 메모 추가", callback_data=f"{child_id_str}:{task_idx}:m"),
    ]])
    await query.answer(f"{result_emoji} {task['과목']} {result_text}!")
    await query.edit_message_text(text=checked_text, reply_markup=checked_keyboard)

    # 모든 항목 체크 완료 시 부모에게 알림
    if len(state["results"]) == len(state["tasks"]):
        try:
            await _send_child_summary_to_parent(context, child_name, date_str)
        except Exception as e:
            logger.error(f"부모 알림 실패: {e}")


# ─── 메모 핸들러 ────────────────────────────────────────────

async def handle_message(update: Update, context):
    """텍스트 메시지 → 메모로 저장 (💬 메모 추가 버튼을 누른 후)"""
    chat_id = update.effective_chat.id
    waiting = memo_waiting.get(chat_id)

    if not waiting:
        return

    memo_text = update.message.text.strip()
    if not memo_text:
        return

    child_name = waiting["child_name"]
    task = waiting["task"]
    task_idx = waiting["task_idx"]

    try:
        sheets.write_memo(
            child_name,
            waiting["date"],
            task,
            memo_text,
        )

        await update.message.reply_text(
            f"📝 메모 저장! ({task['과목']} — {task['세부항목']})"
        )

        # 원래 메시지를 메모 포함 상태로 업데이트
        state_key = (chat_id, child_name)
        state = daily_state.get(state_key)
        if state:
            result = state["results"].get(task_idx, "완료")
            emoji = {"완료": "✅", "부분완료": "△", "못함": "✗", "미응답": "🔇"}.get(result, "❓")
            total = len(state["tasks"])
            updated_text = f"{emoji} {task_idx+1}/{total}  {task['label']} — {result}\n💬 {memo_text}"
            try:
                await context.bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=waiting["message_id"],
                    text=updated_text,
                )
            except Exception:
                pass  # 메시지 수정 실패해도 메모는 이미 저장됨

    except Exception as e:
        logger.error(f"메모 저장 실패: {e}")
        await update.message.reply_text("메모 저장에 실패했어. 다시 시도해줘.")

    # 메모 저장 후 대기 초기화
    del memo_waiting[chat_id]


# ─── 스케줄 작업 ────────────────────────────────────────────

async def _send_tasks_to_chat(
    context, child_name: str, chat_id: int, parent_view: bool = False
):
    """특정 아이의 오늘 할일을 항목별 개별 메시지로 전송"""
    now = datetime.now(KST)
    weekday = now.weekday()
    date_str = now.strftime("%Y-%m-%d")
    date_display = f"{now.month}월 {now.day}일 {DAY_NAMES[weekday]}요일"

    tasks = sheets.get_tasks_for_day(child_name, weekday)

    if not tasks:
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"📚 {child_name}: {DAY_NAMES[weekday]}요일은 할일이 없어! 🎉",
        )
        return

    # 오늘 이미 체크한 결과 복원
    existing_results = sheets.get_daily_results(child_name, date_str)
    results = {}
    for i, task in enumerate(tasks):
        for r in existing_results:
            if r["과목"] == task["과목"] and r["세부항목"] == task["세부항목"]:
                results[i] = r["결과"]
                break

    child_id = _child_name_to_id(child_name)
    total = len(tasks)

    # 인메모리 상태 저장 (chat_id + child_name 조합으로 키)
    state_key = (chat_id, child_name)
    daily_state[state_key] = {
        "date": date_str,
        "tasks": tasks,
        "results": results,
        "message_ids": {},
    }

    # 헤더 메시지
    await context.bot.send_message(
        chat_id=chat_id,
        text=f"📚 {child_name}의 오늘 할일 ({date_display}) - 총 {total}개",
    )

    # 항목별 개별 메시지
    for i, task in enumerate(tasks):
        result = results.get(i)
        if result:
            emoji = {"완료": "✅", "부분완료": "△", "못함": "✗", "미응답": "🔇"}.get(result, "❓")
            text = f"{emoji} {i+1}/{total}  {task['label']} — {result}"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton(f"{emoji} {result}", callback_data="noop"),
            ]])
        elif parent_view:
            text = f"⬜ {i+1}/{total}  {task['label']}"
            keyboard = None
        else:
            text = f"{i+1}/{total}  {task['label']}"
            keyboard = InlineKeyboardMarkup([[
                InlineKeyboardButton("✅완료", callback_data=f"{child_id}:{i}:c"),
                InlineKeyboardButton("△부분", callback_data=f"{child_id}:{i}:p"),
                InlineKeyboardButton("✗못함", callback_data=f"{child_id}:{i}:f"),
            ]])

        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=text,
            reply_markup=keyboard,
        )
        daily_state[state_key]["message_ids"][i] = msg.message_id


async def scheduled_send_tasks(context):
    """매일 저녁 자동 전송 (JobQueue에서 호출)"""
    logger.info("스케줄: 일일 할일 전송 시작")
    for child_name, chat_id in Config.CHILDREN.items():
        if chat_id == 0:  # 아직 미등록
            continue
        try:
            await _send_tasks_to_chat(context, child_name, chat_id)
            logger.info(f"  {child_name}에게 전송 완료")
        except Exception as e:
            logger.error(f"  {child_name} 전송 실패: {e}")


async def _send_child_summary_to_parent(context, child_name: str, date_str: str):
    """개별 아이의 결과를 부모에게 전송"""
    results = sheets.get_daily_results(child_name, date_str)
    if not results:
        return

    now = datetime.now(KST)
    text = f"📊 {child_name} 완료 ({now.month}월 {now.day}일)\n\n"
    for r in results:
        emoji = {"완료": "✅", "부분완료": "△", "못함": "✗"}.get(r["결과"], "❓")
        text += f"{emoji} {r['과목']} — {r['세부항목']}"
        if r["메모"]:
            text += f"\n   💬 {r['메모']}"
        text += "\n"

    completed = sum(1 for r in results if r["결과"] == "완료")
    total = len(results)
    text += f"\n📈 달성률: {round(completed / total * 100)}% ({completed}/{total})"

    await _send_to_parents(context, text)


async def _send_parent_summary(context, record_no_response: bool = False):
    """전체 요약을 부모에게 전송. record_no_response=True면 미체크 항목을 미응답으로 기록"""
    now = datetime.now(KST)
    date_str = now.strftime("%Y-%m-%d")

    text = f"📊 일일 학습 리포트 ({now.month}월 {now.day}일 {DAY_NAMES[now.weekday()]}요일)\n\n"

    for child_name in Config.CHILDREN:
        results = sheets.get_daily_results(child_name, date_str)
        tasks = sheets.get_tasks_for_day(child_name, now.weekday())

        text += f"👤 {child_name}"
        if not tasks:
            text += " — 오늘 할일 없음\n\n"
            continue
        text += "\n"

        # 결과가 있는 항목
        checked_details = {(r["과목"], r["세부항목"]): r for r in results}

        for task in tasks:
            key = (task["과목"], task["세부항목"])
            if key in checked_details:
                r = checked_details[key]
                emoji = {"완료": "✅", "부분완료": "△", "못함": "✗", "미응답": "🔇"}.get(r["결과"], "❓")
                text += f"  {emoji} {task['label']}"
                if r["메모"]:
                    text += f" 💬{r['메모']}"
            else:
                if record_no_response:
                    # 23시 스케줄에서만 미응답 기록
                    try:
                        sheets.write_result(child_name, date_str, task, "미응답")
                    except Exception as e:
                        logger.error(f"미응답 기록 실패: {e}")
                    text += f"  🔇 {task['label']} (미응답)"
                else:
                    text += f"  ⬜ {task['label']} (미체크)"
            text += "\n"

        # 달성률 계산
        if record_no_response:
            results = sheets.get_daily_results(child_name, date_str)
        completed = sum(1 for r in results if r["결과"] == "완료")
        total = len(tasks)
        rate = round(completed / total * 100) if total > 0 else 0
        text += f"  📈 달성률: {rate}% ({completed}/{total})\n\n"

    # 주간 누적
    monday = now - timedelta(days=now.weekday())
    dates = [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(now.weekday() + 1)]

    text += "📅 이번 주 누적: "
    parts = []
    for child_name in Config.CHILDREN:
        stats = sheets.get_weekly_stats(child_name, dates)
        parts.append(f"{child_name} {stats['rate']}%")
    text += " | ".join(parts)

    await _send_to_parents(context, text)


async def scheduled_parent_summary(context):
    """매일 23시 부모 요약 전송 (스케줄러에서 호출) — 미응답 자동 기록"""
    logger.info("스케줄: 부모 요약 전송")
    try:
        await _send_parent_summary(context, record_no_response=True)
    except Exception as e:
        logger.error(f"부모 요약 전송 실패: {e}")


async def scheduled_weekly_alpha(context):
    """매주 일요일 21:30 알파 포인트 계산 + 전송 (스케줄러에서 호출)"""
    logger.info("스케줄: 주간 알파 계산 시작")
    now = datetime.now(KST)

    # 이번 주 월~일 날짜 리스트
    monday = now - timedelta(days=now.weekday())
    week_dates = [(monday + timedelta(days=i)).strftime("%Y-%m-%d") for i in range(7)]
    week_start = week_dates[0]

    for child_name in Config.CHILDREN:
        try:
            alpha_result = sheets.calculate_weekly_alpha(child_name, week_dates)
            sheets.save_weekly_alpha(child_name, week_start, alpha_result)

            # 누적 점수 조회
            cumulative = sheets.get_cumulative_alpha(child_name)

            # 리포트 메시지 생성
            sign = "+" if alpha_result["total"] >= 0 else ""
            text = f"⭐ {child_name}의 주간 알파 리포트\n"
            text += f"📅 {week_dates[0]} ~ {week_dates[6]}\n\n"
            text += f"이번 주: {sign}{alpha_result['total']}분\n"
            text += f"🏆 누적 점수: {cumulative['total']}분\n\n"

            text += "📋 상세:\n"
            for d in alpha_result["details"]:
                s = "+" if d["score"] >= 0 else ""
                emoji = "✅" if d["score"] > 0 else ("❌" if d["score"] < 0 else "➖")
                text += f"  {emoji} {d['과목']}/{d['세부항목']}: {s}{d['score']}분\n"
                text += f"     {d['reason']}\n"

            # 부모 + 아이 모두에게 전송
            await _send_to_parents(context, text)

            child_chat_id = Config.CHILDREN.get(child_name)
            if child_chat_id and child_chat_id != 0:
                try:
                    await context.bot.send_message(chat_id=child_chat_id, text=text)
                except Exception:
                    pass

            logger.info(f"  {child_name} 알파 계산 완료: {alpha_result['total']}분")
        except Exception as e:
            logger.error(f"  {child_name} 알파 계산 실패: {e}")


# ─── 메인 ───────────────────────────────────────────────────

def main():
    global sheets

    # Google Sheets 클라이언트 초기화
    sheets = SheetsClient()
    logger.info("Google Sheets 연결 완료")

    # Telegram 봇 초기화
    app = Application.builder().token(Config.BOT_TOKEN).build()

    # 핸들러 등록
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("today", cmd_today))
    app.add_handler(CommandHandler("status", cmd_status))
    app.add_handler(CommandHandler("summary", cmd_summary))
    app.add_handler(CommandHandler("week", cmd_week))
    app.add_handler(CommandHandler("alpha", cmd_alpha))
    app.add_handler(CommandHandler("catchup", cmd_catchup))
    app.add_handler(CallbackQueryHandler(handle_callback))
    app.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message)
    )

    # python-telegram-bot 내장 JobQueue로 스케줄링
    job_queue = app.job_queue

    # 매일 22:00 KST 할일 전송
    from datetime import time as dt_time
    task_time = dt_time(
        hour=Config.TASK_SEND_HOUR,
        minute=Config.TASK_SEND_MINUTE,
        tzinfo=KST,
    )
    job_queue.run_daily(scheduled_send_tasks, time=task_time, name="daily_tasks")

    # 매일 23:00 KST 부모 요약
    summary_time = dt_time(
        hour=Config.SUMMARY_HOUR,
        minute=Config.SUMMARY_MINUTE,
        tzinfo=KST,
    )
    job_queue.run_daily(scheduled_parent_summary, time=summary_time, name="parent_summary")

    # 매주 일요일 21:30 KST 알파 계산
    alpha_time = dt_time(hour=21, minute=30, tzinfo=KST)
    job_queue.run_daily(
        scheduled_weekly_alpha,
        time=alpha_time,
        days=(6,),  # 일요일만 (0=월, 6=일)
        name="weekly_alpha",
    )

    logger.info(
        f"스케줄 등록: 할일 전송 {Config.TASK_SEND_HOUR}:{Config.TASK_SEND_MINUTE:02d}, "
        f"부모 요약 {Config.SUMMARY_HOUR}:{Config.SUMMARY_MINUTE:02d}, "
        f"알파 계산 일요일 21:30"
    )

    # 봇 실행
    logger.info("봇 시작!")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
