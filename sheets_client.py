import re
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from config import Config

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

DAY_MAP = {"월": 0, "화": 1, "수": 2, "목": 3, "금": 4, "토": 5, "일": 6}
DAY_NAMES = ["월", "화", "수", "목", "금", "토", "일"]


class SheetsClient:
    def __init__(self):
        creds = Credentials.from_service_account_file(
            Config.GOOGLE_CREDENTIALS_FILE, scopes=SCOPES
        )
        self.gc = gspread.authorize(creds)
        self.spreadsheet = self.gc.open_by_key(Config.GOOGLE_SHEETS_ID)

    def _ensure_result_sheet(self, child_name: str) -> gspread.Worksheet:
        """결과 시트가 없으면 생성"""
        sheet_name = f"{child_name}_결과"
        try:
            ws = self.spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(
                title=sheet_name, rows=1000, cols=6
            )
            ws.update("A1:F1", [["날짜", "과목", "세부항목", "교재명", "결과", "메모"]])
            ws.format("A1:F1", {"textFormat": {"bold": True}})
        return ws

    def _parse_days(self, day_str: str, freq_str: str) -> list[int]:
        """요일 문자열을 파싱하여 weekday 인덱스 리스트로 반환"""
        if not day_str and not freq_str:
            return []

        # "매일" 처리
        if day_str and "매일" in day_str:
            return list(range(7))
        if not day_str and freq_str and "매일" in freq_str:
            return list(range(7))

        # 요일 파싱: "화, 목, 일" 또는 "월,화,수,목"
        if day_str:
            days = []
            for char in day_str:
                if char in DAY_MAP:
                    days.append(DAY_MAP[char])
            return days

        # 요일 없이 "주 N회" 또는 "최소 주 N권" 같은 경우 → 매일 표시
        if freq_str and ("주" in freq_str):
            return list(range(7))

        return []

    def _detect_columns(self, header: list[str]) -> dict[str, int]:
        """헤더에서 컬럼 인덱스를 자동 감지"""
        col_map = {}
        for i, h in enumerate(header):
            h = h.strip()
            if h == "과목":
                col_map["과목"] = i
            elif h == "종류":
                col_map["종류"] = i
            elif h in ("세부 항목", "세부항목"):
                col_map["세부항목"] = i
            elif h == "교재명":
                col_map["교재명"] = i
            elif h == "횟수":
                col_map["횟수"] = i
            elif h == "요일":
                col_map["요일"] = i
        return col_map

    def get_tasks_for_day(self, child_name: str, weekday: int) -> list[dict]:
        """특정 요일에 해당하는 할일 목록을 반환"""
        try:
            ws = self.spreadsheet.worksheet(child_name)
        except gspread.WorksheetNotFound:
            return []

        rows = ws.get_all_values()
        if not rows:
            return []

        # 헤더 기반 컬럼 자동 감지
        col = self._detect_columns(rows[0])

        tasks = []
        current_subject = ""

        for i, row in enumerate(rows):
            if i == 0:  # 헤더 스킵
                continue

            def get_col(name, default=""):
                idx = col.get(name)
                if idx is not None and idx < len(row):
                    return row[idx].strip()
                return default

            subject = get_col("과목")
            category = get_col("종류")
            detail = get_col("세부항목")
            textbook = get_col("교재명")
            frequency = get_col("횟수")
            days_str = get_col("요일")

            # 병합 셀 처리: 과목이 비어있으면 이전 과목 사용
            if subject:
                current_subject = subject
            elif not subject and (category or detail):
                subject = current_subject

            # 빈 행 스킵
            if not subject and not detail:
                continue

            # 요일 파싱
            task_days = self._parse_days(days_str, frequency)

            # 오늘 요일에 해당하는지 확인
            if weekday in task_days:
                label = f"{subject} — {detail}"
                if textbook:
                    label += f" ({textbook})"

                tasks.append(
                    {
                        "과목": subject,
                        "종류": category,
                        "세부항목": detail,
                        "교재명": textbook,
                        "횟수": frequency,
                        "label": label,
                        "row_index": i,
                    }
                )

        return tasks

    def write_result(
        self,
        child_name: str,
        date_str: str,
        task: dict,
        result: str,
        memo: str = "",
    ):
        """결과를 결과 시트에 기록"""
        ws = self._ensure_result_sheet(child_name)

        # 기존 결과가 있는지 확인 (같은 날짜 + 같은 세부항목)
        existing = ws.get_all_values()
        for i, row in enumerate(existing):
            if i == 0:
                continue
            if (
                len(row) >= 4
                and row[0] == date_str
                and row[1] == task["과목"]
                and row[2] == task["세부항목"]
            ):
                # 기존 행 업데이트
                ws.update_cell(i + 1, 5, result)
                if memo:
                    ws.update_cell(i + 1, 6, memo)
                return

        # 새 행 추가
        ws.append_row(
            [
                date_str,
                task["과목"],
                task["세부항목"],
                task["교재명"],
                result,
                memo,
            ]
        )

    def write_memo(self, child_name: str, date_str: str, task: dict, memo: str):
        """메모만 추가/업데이트"""
        ws = self._ensure_result_sheet(child_name)
        existing = ws.get_all_values()
        for i, row in enumerate(existing):
            if i == 0:
                continue
            if (
                len(row) >= 4
                and row[0] == date_str
                and row[1] == task["과목"]
                and row[2] == task["세부항목"]
            ):
                ws.update_cell(i + 1, 6, memo)
                return

    def get_daily_results(self, child_name: str, date_str: str) -> list[dict]:
        """특정 날짜의 결과를 조회"""
        try:
            ws = self._ensure_result_sheet(child_name)
        except Exception:
            return []

        existing = ws.get_all_values()
        results = []
        for i, row in enumerate(existing):
            if i == 0:
                continue
            if len(row) >= 5 and row[0] == date_str:
                results.append(
                    {
                        "과목": row[1],
                        "세부항목": row[2],
                        "교재명": row[3],
                        "결과": row[4],
                        "메모": row[5] if len(row) > 5 else "",
                    }
                )
        return results

    def get_weekly_stats(self, child_name: str, dates: list[str]) -> dict:
        """주간 통계 계산"""
        total = 0
        completed = 0
        partial = 0

        for date_str in dates:
            results = self.get_daily_results(child_name, date_str)
            for r in results:
                total += 1
                if r["결과"] == "완료":
                    completed += 1
                elif r["결과"] == "부분완료":
                    partial += 1

        return {
            "total": total,
            "completed": completed,
            "partial": partial,
            "incomplete": total - completed - partial,
            "rate": round(completed / total * 100) if total > 0 else 0,
        }

    def get_incomplete_tasks(self, child_name: str, week_dates: list[str]) -> list[dict]:
        """이번 주 미완료(미응답/못함) 항목 조회"""
        incomplete = []

        for date_str in week_dates:
            # 해당 날짜의 요일
            dt = datetime.strptime(date_str, "%Y-%m-%d")
            weekday = dt.weekday()

            # 해당 요일에 해야 할 일
            tasks = self.get_tasks_for_day(child_name, weekday)
            if not tasks:
                continue

            # 해당 날짜의 결과
            results = self.get_daily_results(child_name, date_str)
            checked = {(r["과목"], r["세부항목"]): r for r in results}

            for task in tasks:
                key = (task["과목"], task["세부항목"])
                if key in checked:
                    result = checked[key]["결과"]
                    if result in ("미응답", "못함"):
                        incomplete.append({
                            **task,
                            "date": date_str,
                            "weekday": weekday,
                            "prev_result": result,
                        })
                else:
                    # 아직 결과가 없는 항목 (오늘 이전 날짜만)
                    today = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y-%m-%d")
                    if date_str < today:
                        incomplete.append({
                            **task,
                            "date": date_str,
                            "weekday": weekday,
                            "prev_result": "미체크",
                        })

        return incomplete

    # ─── 알파 포인트 ────────────────────────────────────────

    def _ensure_alpha_sheet(self) -> gspread.Worksheet:
        """알파 시트가 없으면 생성"""
        sheet_name = "알파점수"
        try:
            ws = self.spreadsheet.worksheet(sheet_name)
        except gspread.WorksheetNotFound:
            ws = self.spreadsheet.add_worksheet(
                title=sheet_name, rows=1000, cols=5
            )
            ws.update("A1:E1", [["이름", "주차", "시작일", "점수", "상세"]])
            ws.format("A1:E1", {"textFormat": {"bold": True}})
        return ws

    def _get_alpha_rules(self, child_name: str) -> list[dict]:
        """계획 시트에서 알파체크 규칙 읽기"""
        try:
            ws = self.spreadsheet.worksheet(child_name)
        except gspread.WorksheetNotFound:
            return []

        rows = ws.get_all_values()
        if not rows:
            return []

        header = rows[0]
        # 알파체크 컬럼 찾기
        alpha_col = None
        for i, h in enumerate(header):
            if "알파" in h:
                alpha_col = i
                break
        if alpha_col is None:
            return []

        col = self._detect_columns(header)
        rules = []
        current_subject = ""

        for i, row in enumerate(rows):
            if i == 0:
                continue

            def get_col(name, default=""):
                idx = col.get(name)
                if idx is not None and idx < len(row):
                    return row[idx].strip()
                return default

            subject = get_col("과목")
            detail = get_col("세부항목")
            frequency = get_col("횟수")
            days_str = get_col("요일")
            alpha_rule = row[alpha_col].strip() if alpha_col < len(row) else ""

            if subject:
                current_subject = subject
            elif not subject and detail:
                subject = current_subject

            if not alpha_rule or not subject:
                continue

            # 요일 파싱으로 주간 해야할 횟수 계산
            task_days = self._parse_days(days_str, frequency)

            rules.append({
                "과목": subject,
                "세부항목": detail,
                "rule": alpha_rule,
                "expected_days": task_days,
                "expected_count": len(task_days),
            })

        return rules

    def _parse_alpha_rule(self, rule: str, completed_count: int,
                          expected_count: int, memos: list[str],
                          finalize: bool = True) -> tuple[int, str]:
        """알파 규칙을 파싱하여 점수와 사유 반환.

        finalize=False(주중 라이브 계산): 임계 미달 페널티(-M분)는 보류(0).
        보상/복구분만 즉시 반영하고, 페널티는 일요일 정규 계산(finalize=True)에서 확정.
        """

        # 패턴1: "주N회 모두 O 일때 5분, 아니면 -5분"
        m = re.search(r"주(\d+)회\s*모두\s*O\s*일때\s*(\d+)분.*아니면\s*-(\d+)분", rule)
        if m:
            required = int(m.group(1))
            # NA 횟수를 반영: expected_count가 줄어들면 required도 줄임
            effective_required = min(required, expected_count)
            reward = int(m.group(2))
            penalty = int(m.group(3))
            if completed_count >= effective_required:
                return reward, f"주{required}회 중 {effective_required}회 필요, {completed_count}회 달성 → +{reward}분" if effective_required != required else f"주{required}회 달성 → +{reward}분"
            else:
                if not finalize:
                    return 0, f"주{required}회 중 {completed_count}회 (페널티 일요일 확정 보류)"
                return -penalty, f"주{required}회 중 {completed_count}회만 완료 → -{penalty}분"

        # 패턴2: "주N회 모두 O 일때 5분" (벌점 없음)
        m = re.search(r"주(\d+)회\s*모두\s*O\s*일때\s*(\d+)분", rule)
        if m:
            required = int(m.group(1))
            effective_required = min(required, expected_count)
            reward = int(m.group(2))
            if completed_count >= effective_required:
                return reward, f"주{required}회 중 {effective_required}회 필요, {completed_count}회 달성 → +{reward}분" if effective_required != required else f"주{required}회 달성 → +{reward}분"
            else:
                return 0, f"주{required}회 중 {completed_count}회 완료 → 0분"

        # 패턴3: "주N회 모두 입력값이 있을때 5분, 아니면 -5분"
        m = re.search(r"주(\d+)회\s*모두\s*입력값이\s*있을때\s*(\d+)분.*아니면\s*-(\d+)분", rule)
        if m:
            required = int(m.group(1))
            effective_required = min(required, expected_count)
            reward = int(m.group(2))
            penalty = int(m.group(3))
            memo_count = sum(1 for memo in memos if memo.strip())
            if memo_count >= effective_required:
                return reward, f"주{required}회 중 {effective_required}회 필요, {memo_count}회 입력 달성 → +{reward}분" if effective_required != required else f"주{required}회 입력 달성 → +{reward}분"
            else:
                if not finalize:
                    return 0, f"주{required}회 중 {memo_count}회 입력 (페널티 일요일 확정 보류)"
                return -penalty, f"주{required}회 중 {memo_count}회 입력 → -{penalty}분"

        # 패턴6: "0이 입력될때마다 5분씩 추가, 아니면 -5분"
        # ⚠️ 반드시 패턴4보다 먼저 검사 — 패턴4 정규식(입력될때마다 N분씩 추가)이
        #    이 규칙의 부분 문자열에도 매칭되어 패턴6을 가려버리기 때문.
        m = re.search(r"0이\s*입력될때마다\s*(\d+)분씩\s*추가.*아니면\s*-(\d+)분", rule)
        if m:
            reward_per = int(m.group(1))
            penalty = int(m.group(2))
            zero_count = sum(1 for memo in memos if memo.strip() == "0")
            non_zero = sum(1 for memo in memos if memo.strip() and memo.strip() != "0")
            if not finalize:
                # 주중 라이브: 0점 보상만 반영, 기타값 페널티는 일요일 확정 보류
                return zero_count * reward_per, f"0점 {zero_count}회(+{zero_count * reward_per}분), 페널티 일요일 확정 보류"
            total = (zero_count * reward_per) - (non_zero * penalty)
            detail = f"0점 {zero_count}회(+{zero_count * reward_per}분)"
            if non_zero > 0:
                detail += f", 기타 {non_zero}회(-{non_zero * penalty}분)"
            return total, detail

        # 패턴4: "책 이름이 입력될때마다 5분씩 추가"
        m = re.search(r"입력될때마다\s*(\d+)분씩\s*추가", rule)
        if m:
            reward_per = int(m.group(1))
            memo_count = sum(1 for memo in memos if memo.strip())
            total = memo_count * reward_per
            if total > 0:
                return total, f"{memo_count}건 입력 → +{total}분"
            else:
                return 0, "입력 없음 → 0분"

        # 패턴5: "책 이름이 입력될때 5분"
        m = re.search(r"입력될때\s*(\d+)분", rule)
        if m:
            reward = int(m.group(1))
            memo_count = sum(1 for memo in memos if memo.strip())
            if memo_count > 0:
                return reward, f"입력 있음 → +{reward}분"
            else:
                return 0, "입력 없음 → 0분"

        # 패턴7: "시험 점수가 90 이상일때 5분"
        m = re.search(r"시험\s*점수가\s*(\d+)\s*이상일때\s*(\d+)분", rule)
        if m:
            threshold = int(m.group(1))
            reward = int(m.group(2))
            for memo in memos:
                score_match = re.search(r"(\d+)", memo)
                if score_match and int(score_match.group(1)) >= threshold:
                    return reward, f"{score_match.group(1)}점 → +{reward}분"
            return 0, "해당 없음 → 0분"

        return 0, f"규칙 미인식: {rule}"

    def calculate_weekly_alpha(self, child_name: str, week_dates: list[str],
                               finalize: bool = True) -> dict:
        """주간 알파 포인트 계산.

        finalize=True(일요일 정규 계산): 페널티 포함 최종 점수.
        finalize=False(주중 라이브 계산): 보상/복구분만, 임계 페널티는 보류.
        """
        rules = self._get_alpha_rules(child_name)
        if not rules:
            return {"total": 0, "details": [], "rules_count": 0}

        # 해당 주의 모든 결과를 한 번에 읽기 (시트 호출 최소화)
        ws = self._ensure_result_sheet(child_name)
        existing = ws.get_all_values()
        date_set = set(week_dates)
        all_results = []
        for i, row in enumerate(existing):
            if i == 0:
                continue
            if len(row) >= 5 and row[0] in date_set:
                all_results.append({
                    "과목": row[1],
                    "세부항목": row[2],
                    "교재명": row[3],
                    "결과": row[4],
                    "메모": row[5] if len(row) > 5 else "",
                    "날짜": row[0],
                })

        details = []
        total_alpha = 0

        for rule in rules:
            # 이 항목의 주간 완료 횟수 (NA는 제외)
            matching = [
                r for r in all_results
                if r["과목"] == rule["과목"] and r["세부항목"] == rule["세부항목"]
            ]
            na_count = sum(1 for r in matching if r["결과"] == "NA")
            completed_count = sum(1 for r in matching if r["결과"] == "완료")
            memos = [r.get("메모", "") for r in matching if r["결과"] != "NA"]

            # NA 횟수만큼 기대 횟수를 줄임
            adjusted_expected = max(0, rule["expected_count"] - na_count)

            score, reason = self._parse_alpha_rule(
                rule["rule"], completed_count, adjusted_expected, memos,
                finalize=finalize,
            )

            total_alpha += score
            details.append({
                "과목": rule["과목"],
                "세부항목": rule["세부항목"],
                "score": score,
                "reason": reason,
            })

        return {
            "total": total_alpha,
            "details": details,
            "rules_count": len(rules),
        }

    def save_weekly_alpha(self, child_name: str, week_start: str, alpha_result: dict):
        """주간 알파 결과를 시트에 저장"""
        ws = self._ensure_alpha_sheet()

        # 상세 내용 텍스트
        detail_lines = []
        for d in alpha_result["details"]:
            sign = "+" if d["score"] >= 0 else ""
            detail_lines.append(f"{d['과목']}/{d['세부항목']}: {sign}{d['score']}분 ({d['reason']})")
        detail_text = "\n".join(detail_lines)

        # 기존 동일 주차 데이터 확인
        existing = ws.get_all_values()
        for i, row in enumerate(existing):
            if i == 0:
                continue
            if len(row) >= 3 and row[0] == child_name and row[2] == week_start:
                ws.update_cell(i + 1, 4, alpha_result["total"])
                ws.update_cell(i + 1, 5, detail_text)
                return

        # 주차 계산
        from datetime import datetime
        dt = datetime.strptime(week_start, "%Y-%m-%d")
        week_num = dt.isocalendar()[1]
        week_label = f"{dt.year}년 {week_num}주차"

        ws.append_row([
            child_name, week_label, week_start, alpha_result["total"], detail_text
        ])

    def get_cumulative_alpha(self, child_name: str) -> dict:
        """누적 알파 점수 조회"""
        ws = self._ensure_alpha_sheet()
        rows = ws.get_all_values()

        total = 0
        weeks = []
        for i, row in enumerate(rows):
            if i == 0:
                continue
            if len(row) >= 4 and row[0] == child_name:
                score = int(row[3]) if row[3].lstrip("-").isdigit() else 0
                total += score
                weeks.append({
                    "주차": row[1],
                    "시작일": row[2],
                    "점수": score,
                })

        return {
            "total": total,
            "weeks": weeks,
        }

    def _get_stored_week_total(self, child_name: str, week_start: str) -> int:
        """알파점수 시트에 저장된 특정 주차 점수 조회 (없으면 0)"""
        ws = self._ensure_alpha_sheet()
        rows = ws.get_all_values()
        for i, row in enumerate(rows):
            if i == 0:
                continue
            if len(row) >= 4 and row[0] == child_name and row[2] == week_start:
                return int(row[3]) if row[3].lstrip("-").isdigit() else 0
        return 0

    def recalc_live_alpha(self, child_name: str, week_dates: list[str],
                          week_start: str) -> dict:
        """이번 주 알파를 라이브(페널티 보류)로 재계산해 저장하고 증가분을 반환.

        일요일 정규 계산은 같은 결과 시트를 읽어 같은 행을 멱등 덮어쓰므로 이중집계 없음.
        반환: {"old": 이전 저장 점수, "new": 새 점수, "delta": 증가분}
        """
        old_total = self._get_stored_week_total(child_name, week_start)
        result = self.calculate_weekly_alpha(child_name, week_dates, finalize=False)
        self.save_weekly_alpha(child_name, week_start, result)
        return {
            "old": old_total,
            "new": result["total"],
            "delta": result["total"] - old_total,
        }
