"""学习域出入参、日期口径与「ORM 行 → 前端字段」映射。

⚠️ 日期口径与前端 common/utils/study-store.js **逐条对齐**（这是刻意设计）：
    - 日期一律用「日期 key」字符串 "YYYY-MM-DD"，不用时间戳、不用中文文案。
      因为前端的 dateLabel(key) / dayDiff(key, todayKey()) / weekKeys() 都按这个
      正则 ^\\d{4}-\\d{2}-\\d{2}$ 解析，返回别的格式会让这些 helper 全部得到 NaN。
    - 一周从**周一**开始、共 7 天（与 mondayOf()/weekKeys() 一致）。
    - 展示文案（"3 月 10 日" / "周一" / "3 月 4 日 - 3 月 10 日"）也由本层提供，
      格式与前端的 dateLabel/weekdayLabel/weekRangeLabel 逐字符一致，
      于是前端「自己算」和「直接用服务端给的」两种写法都能跑通。
    - 记忆卡阶段 0~6、间隔表 [1,1,2,4,7,10,15]、三档评价 know/vague/forget 的推进规则，
      同样与前端 rateMemoryCard() 完全一致，避免两边调度算法漂移。
    - 毫秒时间戳字段（updatedAt / lastAt）保持**毫秒**，与前端 Date.now() 同一量纲。

⚠️ 错题记录的形状对齐前端 normalizeWrong() 的产物：
    {id, srcId, bank, bankId, type, stem, options, analysis, knowledge, myAnswer,
     answer, reason, date, wrongTimes, mastered, updatedAt}
    （前端就是这个形状在本地存的；服务端返回同构数据，页面才能「换数据源」而不是改代码）
"""
from datetime import date, datetime, timedelta

from pydantic import BaseModel, ConfigDict, Field

from app.models import MemoryCard, MemoryProgress, Question, QuestionBank, WrongQuestion

# ==========================================================
# 常量：与前端 study-store.js 同源
# ==========================================================

DATE_FMT = "%Y-%m-%d"
WEEKDAY_NAMES = ("周一", "周二", "周三", "周四", "周五", "周六", "周日")

# 记忆阶段上限与间隔天数表（前端 MEMORY_MAX_STAGE / MEMORY_INTERVALS）
MEMORY_MAX_STAGE = 6
MEMORY_INTERVALS = (1, 1, 2, 4, 7, 10, 15)
# 三档评价（前端 rateMemoryCard 的 level 取值）
MEMORY_LEVELS = ("know", "vague", "forget")

# 题库名兜底（前端 normalizeWrong 的默认值就是它）
DEFAULT_BANK_NAME = "未归类题库"


# ==========================================================
# 日期工具
# ==========================================================


def today_key() -> str:
    """今天的日期 key。"""
    return date.today().strftime(DATE_FMT)


def date_key(value: date | datetime | None) -> str:
    """date / datetime → 日期 key；None 返回当天 key。"""
    if value is None:
        return today_key()
    return value.strftime(DATE_FMT)


def parse_key(key: str | None) -> date | None:
    """日期 key → date；格式不对返回 None（与前端 parseKey 的 NaN 语义对应）。"""
    try:
        return datetime.strptime(str(key), DATE_FMT).date()
    except (TypeError, ValueError):
        return None


def monday_of(day: date | None = None) -> date:
    """所在周的周一。"""
    d = day or date.today()
    return d - timedelta(days=(d.weekday()))  # weekday(): 周一=0


def week_keys(day: date | None = None) -> list:
    """本周 7 天的日期 key（周一 → 周日）。"""
    start = monday_of(day)
    return [(start + timedelta(days=i)).strftime(DATE_FMT) for i in range(7)]


def date_label(key: str) -> str:
    """日期 key → '3 月 10 日'（与前端 dateLabel 输出一致）。"""
    d = parse_key(key)
    if d is None:
        return str(key)
    return "%d 月 %d 日" % (d.month, d.day)


def weekday_label(key: str) -> str:
    """日期 key → '周一'…'周日'；不在本周返回空串（与前端 weekdayLabel 一致）。"""
    keys = week_keys()
    return WEEKDAY_NAMES[keys.index(key)] if key in keys else ""


def week_range_label(day: date | None = None) -> str:
    """本周日期范围文案：'3 月 4 日 - 3 月 10 日'。"""
    keys = week_keys(day)
    return date_label(keys[0]) + " - " + date_label(keys[6])


def is_future_day(key: str) -> bool:
    """该日期 key 是否晚于今天。"""
    d = parse_key(key)
    return bool(d and d > date.today())


def epoch_ms(value: datetime | None) -> int:
    """datetime → 毫秒时间戳（与前端 Date.now() 同量纲）；None → 0。"""
    return int(value.timestamp() * 1000) if value else 0


def day_diff(from_key: str, to_key: str) -> int | None:
    """两个日期 key 相差的天数（to 更晚为正）；任一非法返回 None。"""
    a, b = parse_key(from_key), parse_key(to_key)
    if a is None or b is None:
        return None
    return (b - a).days


# ==========================================================
# 记忆卡调度（与前端 rateMemoryCard 同规则）
# ==========================================================


def interval_of(stage: int) -> int:
    """阶段 → 下次复习间隔（天）。"""
    idx = max(0, min(len(MEMORY_INTERVALS) - 1, int(stage)))
    return MEMORY_INTERVALS[idx]


def apply_memory_level(stage: int, level: str, today: date | None = None) -> tuple:
    """按三档评价推进调度，返回 (新阶段, 下次复习日期key)。

    规则与前端的 rateMemoryCard 完全一致：
        know  记住了   → 阶段 +1（封顶 6），下次复习 = 今天 + 阶段间隔
        vague 有点印象 → 阶段不变，明天再复习
        forget 忘记了  → 阶段 -1（不低于 0），今天仍然到期
    """
    base = today or date.today()
    stage = max(0, min(MEMORY_MAX_STAGE, int(stage)))
    if level == "know":
        stage = min(MEMORY_MAX_STAGE, stage + 1)
        nxt = base + timedelta(days=interval_of(stage))
    elif level == "vague":
        nxt = base + timedelta(days=1)
    else:  # forget 及任何未知取值，都按「忘记」处理（宁可多复习一次）
        stage = max(0, stage - 1)
        nxt = base
    return stage, nxt.strftime(DATE_FMT)


# ==========================================================
# 映射：题库 / 题目 / 错题 / 记忆卡 / 答题统计
# ==========================================================


def bank_out(row: QuestionBank, done: int = 0, correct: int = 0, groups: int = 0) -> dict:
    """题库 → 前端结构。

    ⚠️ done / correctRate 返回的是**该用户的真实作答聚合**，不是 question_bank 表里
       那两个种子列：那两列是「全局一行」的 mock 数据，无法表达「每人一份进度」。
       题库总题数 count 仍取内容表的真实值。
    ⚠️ correctRate 与 rate 是同一个值的两个名字（mock 的 banks 用 correctRate，
       前端 bankStat() 用 rate），两边都给，页面不用改。
    """
    rate = round(correct / done * 100) if done else 0
    return {
        "id": row.id,
        "name": row.name,
        "count": row.count,
        "done": done,
        "correct": correct,
        "correctRate": rate,
        "rate": rate,
        "groups": groups,
        "icon": row.icon,
    }


def question_out(row: Question) -> dict:
    """题目 → 前端结构（options/answer 保持数组，与 mock mockQuestions 一致）。

    ⚠️ answer / analysis 一起返回：客户端目前是「本地判卷」，
       需要答案才能即时给对错反馈。若将来改服务端判卷，
       这里应拆出一个不含答案的「答题用」字段集（本期不做）。
    """
    return {
        "id": row.id,
        "bankId": row.bank_id,
        "type": row.type,
        "stem": row.stem,
        "options": row.options or [],
        "answer": row.answer or [],
        "analysis": row.analysis,
        "knowledge": row.knowledge,
    }


def wrong_out(row: WrongQuestion) -> dict:
    """错题 → 前端 normalizeWrong() 的同构结构。"""
    stamp = row.updated_at or row.created_at
    return {
        "id": str(row.id),
        "srcId": row.question_id,
        "bank": row.bank_name or DEFAULT_BANK_NAME,
        "bankId": row.bank_id,
        "type": row.q_type or "single",
        "stem": row.stem,
        "options": row.options or [],
        "analysis": row.analysis,
        "knowledge": row.knowledge,
        "myAnswer": row.my_answer or [],
        "answer": row.answer or [],
        "reason": row.reason,
        "date": date_key(stamp),
        "wrongTimes": row.wrong_times,
        "mastered": bool(row.mastered),
        "updatedAt": epoch_ms(stamp),
        "createdAt": row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else None,
    }


def memory_card_out(row: MemoryCard, progress: MemoryProgress | None) -> dict:
    """记忆卡 → 前端结构（内容 + 该用户的调度状态）。

    ⚠️ stage / nextReview 取「该用户的 memory_progress」；该用户还没复习过这张卡时，
       回退到 memory_card 表里的**初始调度种子值**。
       memory_card 的这两列是全局的，只能当初始值用——一旦用户复习过就以用户数据为准，
       否则所有人会共用一份进度（这正是本期要修掉的问题）。
    """
    stage = progress.stage if progress else row.stage
    return {
        "id": row.id,
        "front": row.front,
        "back": row.back,
        "tag": row.tag,
        "stage": stage,
        "nextReview": (progress.next_review if progress else row.next_review) or "",
        "times": progress.times if progress else 0,
        "mastered": stage >= MEMORY_MAX_STAGE,
        "lastAt": epoch_ms(progress.updated_at) if progress else 0,
        "reviewed": bool(progress and progress.times),
    }


def memory_progress_out(row: MemoryProgress) -> dict:
    """记忆卡进度 → 前端 cardState() 的同构结构。"""
    return {
        "cardId": row.card_id,
        "stage": row.stage,
        "times": row.times,
        "nextReview": row.next_review,
        "mastered": row.stage >= MEMORY_MAX_STAGE,
        "lastAt": epoch_ms(row.updated_at),
        "updatedAt": epoch_ms(row.updated_at),
    }


def activity_bucket(key: str, minutes: int, questions: int) -> dict:
    """一天的活动桶 → 前端 readWeekActivity() 的同构结构。

    ⚠️ 字段名（key/label/short/dateLabel/minutes/questions/isToday/isFuture/hasRecord）
       与前端的桶结构完全一致，学习页柱状图可直接消费，不需要页面侧做映射。
    """
    label = weekday_label(key)
    return {
        "key": key,
        "label": label,
        "short": label.replace("周", ""),
        "dateLabel": date_label(key),
        "minutes": minutes,
        "questions": questions,
        "isToday": key == today_key(),
        "isFuture": is_future_day(key),
        "hasRecord": minutes > 0 or questions > 0,
    }


def continue_days(active_keys: set) -> int:
    """连续学习天数。

    规则（与前端 continueDays 一致）：
        今天有记录 → 从今天往前数；
        今天没有但昨天有 → 从昨天往前数（连续未断）；
        都没有 → 0。
    """
    today = date.today()
    cursor = today
    if today.strftime(DATE_FMT) not in active_keys:
        cursor = today - timedelta(days=1)
        if cursor.strftime(DATE_FMT) not in active_keys:
            return 0
    days = 0
    while cursor.strftime(DATE_FMT) in active_keys:
        days += 1
        cursor -= timedelta(days=1)
    return days


# ==========================================================
# 入参模型
# ==========================================================


class WrongIn(BaseModel):
    """错题入参：客户端把「当时那道题」的整份快照发上来。

    ⚠️ 为什么是快照而不是只发 question_id：题目属于内容层，将来可能被改写或下架，
       而错题本要保留「我当时错的是这道题」。另外免费好课的题目并不在
       question_bank 里，只有 question_id 的话根本存不下来。
    兼容两种来源：
        - 来自题库：带 src_id/question_id，服务端会用库里的题目**覆盖**快照字段，保证权威；
        - 来自题库之外：只带内联字段，服务端按原样存档。
    """

    model_config = ConfigDict(populate_by_name=True)

    # 题目标识：客户端同时发 id 与 srcId（两者相同），任一都能用
    src_id: str | None = Field(default=None, alias="srcId")
    question_id: str | None = None
    id: str | None = None

    # 快照字段
    bank_id: str | None = Field(default=None, alias="bankId")
    bank: str | None = None
    stem: str | None = None
    options: list | None = None
    analysis: str | None = None
    knowledge: str | None = None
    q_type: str | None = Field(default=None, alias="type")
    my_answer: list | None = Field(default=None, alias="myAnswer")
    answer: list | None = None
    reason: str | None = None
    # 客户端已有记录时带上，用于「重练答对 → 标记已掌握」
    mastered: bool | None = None


class AnswerIn(BaseModel):
    """答题记录入参（对齐前端 recordGroup 的入参）。"""

    model_config = ConfigDict(populate_by_name=True)

    bank_id: str = Field(alias="bankId")
    bank_name: str | None = Field(default=None, alias="bankName")
    total: int
    correct: int = 0
    minutes: int = 0


class MemoryProgressIn(BaseModel):
    """记忆卡进度入参。

    两种用法（可任选，`level` 优先）：
        {"card_id": "mc1", "level": "know"}                      服务端按同源规则推进阶段
        {"card_id": "mc1", "stage": 3, "next_review": "2026-09-20"}  客户端自己算好直接存
    """

    model_config = ConfigDict(populate_by_name=True)

    card_id: str = Field(alias="cardId")
    level: str | None = None
    stage: int | None = None
    next_review: str | None = Field(default=None, alias="nextReview")
