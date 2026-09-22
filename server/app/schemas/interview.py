"""招聘域 · 面试题库的出入参与字段映射。

⚠️ 列表与详情刻意返回**不同的字段集**：
    answer（参考答案/答题要点）只在详情接口返回。列表一次 20 条，
    每条答案动辄几百字，全带上会把响应体撑大好几倍，而列表页根本不渲染答案。

⚠️ 字段命名纪律（与 schemas/job.py、schemas/apply.py 一致）：
    数据库列是 snake_case，转换只在本层做一次，映射出来的键一律 camelCase。
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import InterviewQuestion, JobCategory

# 难度文案（1/2/3 与 interview_question.difficulty 的注释一致）
DIFFICULTY_TEXT = {1: "基础", 2: "进阶", 3: "困难"}

# 刷题模式（与 question_record.mode 的注释一致）
VALID_MODES = ("practice", "memory", "review")

# 作答结果：1=会 / 0=不会（0 的题进薄弱点）
VALID_RESULTS = (0, 1)


def difficulty_text(value: int) -> str:
    """难度中文文案；库里只会有 1/2/3，兜底只为不返回 null。"""
    return DIFFICULTY_TEXT.get(int(value or 0), "基础")


def _time_text(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


# ==========================================================
# 映射：题库分类 / 题目 / 薄弱点 / 进度
# ==========================================================


def bank_out(row: JobCategory, count: int, position: str = "") -> dict:
    """题库分类项（按职能分类聚合出来的题量）。

    ⚠️ count 与 position 都是**聚合算出来的**，不是 job_category 表的列：
       count    该分类下的题目数（interview_question 按 category_id 分组）；
       position 该分类下第一道题（sort_order 最小）的适用岗位关键词，
                列表页用它给分类加一句「后端开发 · 32 题」的副标题。
    """
    return {
        "id": row.id,
        "name": row.name,
        "count": int(count or 0),
        "position": position or "",
    }


def question_brief(row: InterviewQuestion) -> dict:
    """题目列表项（**故意不含 answer**，见文件头说明）。"""
    return {
        "id": row.id,
        "categoryId": row.category_id,
        "position": row.position,
        "question": row.question,
        "difficulty": row.difficulty,
        "difficultyText": difficulty_text(row.difficulty),
        "tags": row.tags or [],
        "source": row.source,
        "frequency": row.frequency,
        "isHot": bool(row.is_hot),
    }


def question_detail(row: InterviewQuestion) -> dict:
    """题目详情：在列表项基础上补参考答案。"""
    data = question_brief(row)
    data["answer"] = row.answer or ""
    return data


def wrong_item(
    row: InterviewQuestion,
    last_result: int,
    last_time: datetime | None,
    wrong_count: int,
) -> dict:
    """薄弱点列表项：题目字段 + 该用户在这道题上的作答情况。

    ⚠️ lastResult / lastTime / wrongCount 都是**该用户的作答聚合**，不是题目自身属性
       （题目表里只有全局的 frequency 被考频次），由路由聚合好后传进来。
    ⚠️ lastResult == 1 表示「曾经答错、最近一次已经答对」，即已攻克；
       该题仍留在列表里并带上已掌握标记，与旧学习端错题本的 mastered 字段同义。
    """
    data = question_brief(row)
    data.update({
        "lastResult": int(last_result),
        "lastTime": _time_text(last_time),
        "wrongCount": int(wrong_count),
    })
    return data


def category_progress_out(category_id: str, name: str, answered: int, total: int) -> dict:
    """进度页「按职能」的进度项。"""
    return {
        "categoryId": category_id,
        "name": name or "",
        "answered": int(answered or 0),
        "total": int(total or 0),
    }


# ==========================================================
# 请求体
# ==========================================================


class RecordIn(BaseModel):
    """刷题记录入参。

    ⚠️ result / mode 的取值校验放在路由层（返回 40003「参数不合法」）：
       框架校验失败会被 main.py 归一成 50000，前端拿不到可展示的提示。
    """

    model_config = ConfigDict(populate_by_name=True)

    result: int = Field(default=1, description="1=会 / 0=不会（0 进薄弱点）")
    mode: str = Field(default="practice", description="practice / memory / review")
    duration_sec: int = Field(default=0, alias="durationSec", description="本题耗时（秒）")
