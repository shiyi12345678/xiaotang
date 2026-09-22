"""招聘域 · 投递与简历的出入参与字段映射。

⚠️ 投递状态机（必须与 models/apply.py 文件头保持一致）：
    submitted → viewed → chatting → interview → passed → hired
    任意阶段都可能走向 rejected（不合适）或 withdrawn（求职者撤回）

⚠️ statusText / statusType 在服务端给出：
    求职者端与 HR 端的同一个状态**文案不同**（同一份 submitted，
    求职者看到「已投递」、HR 看到「待处理」），因此这里提供两套文案，
    由路由按角色选择，避免两端各自硬编码导致口径不一致。
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models import Application, Interview, Resume

# ---------- 求职者视角 ----------
CANDIDATE_STATUS_TEXT = {
    "submitted": "已投递",
    "viewed": "简历已查看",
    "chatting": "沟通中",
    "interview": "待面试",
    "passed": "面试通过",
    "hired": "已入职",
    "rejected": "不合适",
    "withdrawn": "已撤回",
}

# ---------- 企业 HR 视角 ----------
HR_STATUS_TEXT = {
    "submitted": "待处理",
    "viewed": "已查看",
    "chatting": "沟通中",
    "interview": "待面试",
    "passed": "面试通过",
    "hired": "已入职",
    "rejected": "不合适",
    "withdrawn": "候选人撤回",
}

# 前端徽标配色语义（success=绿 / warning=橙 / danger=红 / info=灰）
STATUS_TYPE = {
    "submitted": "info",
    "viewed": "info",
    "chatting": "warning",
    "interview": "warning",
    "passed": "success",
    "hired": "success",
    "rejected": "danger",
    "withdrawn": "info",
}

# 求职漏斗的固定阶段（报告页与统计接口共用，顺序即漏斗顺序）
FUNNEL_STAGES = (
    ("submitted", "已投递"),
    ("viewed", "被查看"),
    ("interview", "进入面试"),
    ("passed", "面试通过"),
    ("hired", "成功入职"),
)


def status_text(status: str, role: str = "candidate") -> str:
    """按角色返回状态文案。"""
    table = HR_STATUS_TEXT if role == "hr" else CANDIDATE_STATUS_TEXT
    return table.get(status, status)


def _time_text(value: datetime | None) -> str:
    return value.strftime("%Y-%m-%d %H:%M:%S") if value else ""


def application_out(
    row: Application,
    role: str = "candidate",
    resume: Resume | None = None,
    interviews: list | None = None,
) -> dict:
    """投递记录的对外结构（求职者端「我的投递」与 HR 端「收到简历」共用）。"""
    data = {
        "id": row.id,
        "jobId": row.job_id,
        "jobTitle": row.job_title,
        "companyId": row.company_id,
        "companyName": row.company_name,
        "salaryText": row.salary_text,
        "status": row.status,
        "statusText": status_text(row.status, role),
        "statusType": STATUS_TYPE.get(row.status, "info"),
        "greeting": row.greeting,
        "resumeId": row.resume_id,
        "createdAt": _time_text(row.created_at),
        "updatedAt": _time_text(row.updated_at),
        "viewedAt": _time_text(row.viewed_at),
        # 列表页直接显示「3天前投递」这种相对时间
        "createdText": _relative(row.created_at),
    }

    # HR 侧才返回备注与评分（求职者不该看到内部评价）
    if role == "hr":
        data["hrRemark"] = row.hr_remark
        data["hrRating"] = row.hr_rating
        data["candidateId"] = row.user_id
        if resume is not None:
            data["candidate"] = resume_brief(resume)

    if interviews is not None:
        data["interviews"] = [interview_out(i) for i in interviews]
    return data


def _relative(value: datetime | None) -> str:
    """相对时间文案（与 schemas/job.py 的 relative_time 同口径，此处只处理投递时间）。"""
    if value is None:
        return ""
    from app.schemas.job import relative_time

    return relative_time(value)


def interview_out(row: Interview) -> dict:
    """面试邀约。"""
    mode_text = {"onsite": "现场面试", "video": "视频面试", "phone": "电话面试"}.get(
        row.mode, "现场面试"
    )
    return {
        "id": row.id,
        "applicationId": row.application_id,
        "jobId": row.job_id,
        "roundNo": row.round_no,
        "roundName": row.round_name,
        "time": _time_text(row.interview_time),
        "timeText": row.interview_time.strftime("%m月%d日 %H:%M") if row.interview_time else "待定",
        "durationMin": row.duration_min,
        "mode": row.mode,
        "modeText": mode_text,
        "address": row.address,
        "onlineLink": row.online_link,
        "interviewer": row.interviewer,
        "contact": row.contact,
        "status": row.status,
        "statusText": {
            "pending": "待确认",
            "confirmed": "已确认",
            "finished": "已结束",
            "canceled": "已取消",
        }.get(row.status, row.status),
        "remark": row.remark,
    }


def resume_brief(row: Resume) -> dict:
    """简历摘要（HR 列表卡片上显示）。"""
    return {
        "id": row.id,
        "userId": row.user_id,
        "name": row.name,
        "gender": row.gender,
        "genderText": {0: "", 1: "男", 2: "女"}.get(row.gender, ""),
        "age": _age(row.birth_year),
        "city": row.city,
        "educationLevel": row.education_level,
        "school": row.school,
        "major": row.major,
        "graduationYear": row.graduation_year,
        "workYears": row.work_years,
        "workYearsText": "应届生" if not row.work_years else f"{row.work_years}年经验",
        "currentStatus": row.current_status,
        "expectedCity": row.expected_city,
        "expectedPosition": row.expected_position,
        "expectedSalaryText": _salary_text(row.expected_salary_min, row.expected_salary_max),
        "skills": row.skills or [],
        "completeness": row.completeness,
        "isOpen": bool(row.is_open),
        "updatedAt": _time_text(row.updated_at),
    }


def resume_detail(row: Resume) -> dict:
    """简历完整内容（简历编辑页 / HR 候选人详情页）。"""
    data = resume_brief(row)
    data.update({
        "phone": row.phone,
        "email": row.email,
        # ⚠️ birthYear 必须回传，不能只给算好的 age：
        #    简历保存是**全量覆盖**，编辑页要用接口返回值初始化表单再整体提交。
        #    只给 age 的话，前端只能反推 birthYear（当年 - age），
        #    而「未填」与「年龄超出 16~80 岁」都会算成 age=0，反推就会把原本填好的出生年清空。
        "birthYear": row.birth_year,
        "advantage": row.advantage or "",
        "educations": row.educations or [],
        "experiences": row.experiences or [],
        "projects": row.projects or [],
    })
    return data


def _age(birth_year: int) -> int:
    """按出生年份算年龄；未填返回 0（前端不显示）。"""
    if not birth_year:
        return 0
    current = datetime.now().year
    age = current - birth_year
    return age if 16 <= age <= 80 else 0


def _salary_text(low: int, high: int) -> str:
    if not low and not high:
        return "面议"
    if low == high:
        return f"{low}K"
    return f"{low}-{high}K"


def empty_resume() -> dict:
    """未创建简历时返回的空模板。

    ⚠️ 为什么不返回 null：
       前端简历页拿到 data 后直接双向绑定到表单，返回 null 会迫使每个字段都判空；
       给一份结构完整、值为空串/0 的模板，页面代码可以完全一致。
    """
    return {
        "id": 0,
        "userId": 0,
        "name": "",
        "gender": 0,
        "genderText": "",
        "age": 0,
        "birthYear": 0,
        "phone": "",
        "email": "",
        "city": "",
        "educationLevel": "",
        "school": "",
        "major": "",
        "graduationYear": 0,
        "workYears": 0,
        "workYearsText": "",
        "currentStatus": "",
        "expectedCity": "",
        "expectedPosition": "",
        "expectedSalaryMin": 0,
        "expectedSalaryMax": 0,
        "expectedSalaryText": "面议",
        "skills": [],
        "advantage": "",
        "educations": [],
        "experiences": [],
        "projects": [],
        "completeness": 0,
        "isOpen": True,
        "updatedAt": "",
    }


# ==========================================================
# 请求体
# ==========================================================


class ApplyIn(BaseModel):
    """投递入参。

    ⚠️ 只收 jobId 与打招呼语：
       职位名/公司名/薪资一律由服务端从职位行取快照，
       不信任客户端上报的标题与薪资（否则可伪造投递记录）。
    """

    model_config = ConfigDict(populate_by_name=True)

    job_id: str = Field(alias="jobId", min_length=1, max_length=32)
    greeting: str = Field(default="", max_length=200, description="打招呼语")


class ResumeIn(BaseModel):
    """简历保存入参（全量覆盖式保存）。

    ⚠️ 为什么用全量覆盖而不是逐字段 PATCH：
       简历编辑页是一个表单，用户点「保存」时提交的是整份内容；
       逐字段增量更新会引入「用户没动过的字段被意外清空」的经典问题。
    """

    model_config = ConfigDict(populate_by_name=True)

    name: str = Field(default="", max_length=30)
    gender: int = Field(default=0, ge=0, le=2)
    birth_year: int = Field(default=0, alias="birthYear", ge=0, le=2100)
    phone: str = Field(default="", max_length=20)
    email: str = Field(default="", max_length=120)
    city: str = Field(default="", max_length=20)
    education_level: str = Field(default="", alias="educationLevel", max_length=20)
    school: str = Field(default="", max_length=60)
    major: str = Field(default="", max_length=60)
    graduation_year: int = Field(default=0, alias="graduationYear", ge=0, le=2100)
    work_years: int = Field(default=0, alias="workYears", ge=0, le=60)
    current_status: str = Field(default="", alias="currentStatus", max_length=20)
    expected_city: str = Field(default="", alias="expectedCity", max_length=20)
    expected_position: str = Field(default="", alias="expectedPosition", max_length=60)
    expected_salary_min: int = Field(default=0, alias="expectedSalaryMin", ge=0, le=500)
    expected_salary_max: int = Field(default=0, alias="expectedSalaryMax", ge=0, le=500)
    skills: list = Field(default_factory=list)
    advantage: str = Field(default="", max_length=2000)
    educations: list = Field(default_factory=list)
    experiences: list = Field(default_factory=list)
    projects: list = Field(default_factory=list)
    is_open: bool = Field(default=True, alias="isOpen")


def compute_completeness(row: Resume) -> int:
    """计算简历完整度（0~100），各字段等权重。

    ⚠️ 放在服务端算的原因：完整度会同时出现在求职者端（简历页进度环）
       与 HR 端（候选人卡片），两端各算一遍必然出现对不上的情况。
    """
    fields = (
        row.name, row.phone, row.city, row.education_level, row.school,
        row.expected_city, row.expected_position,
    )
    filled = sum(1 for v in fields if v not in (None, "", 0))
    score = filled / len(fields) * 55          # 基础信息占 55 分

    if row.skills:
        score += 10
    if row.advantage and len(str(row.advantage)) >= 20:
        score += 10
    if row.educations:
        score += 8
    if row.experiences:
        score += 12
    if row.projects:
        score += 5

    return max(0, min(100, int(round(score))))
