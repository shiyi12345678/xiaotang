"""招聘域 · 企业 HR 端的出入参与状态机。

⚠️ 投递状态机（本文件是**唯一**的流转规则来源）：
    前端只负责把按钮置灰，真正的合法性判断必须在服务端 ——
    否则改一个请求体就能把候选人直接推到「已入职」。
    与 models/apply.py 文件头的状态枚举保持一致。

⚠️ 为什么用「允许集合」而不是「禁止集合」：
    新增一个状态时，禁止集合会默认放行所有未列出的组合（危险），
    允许集合默认拒绝（安全）。这是权限类逻辑该有的默认值方向。
"""
from pydantic import BaseModel, ConfigDict, Field

# 每个状态允许流转到的下一状态；空集合 = 终态
ALLOWED_TRANSITIONS: dict[str, set] = {
    "submitted": {"viewed", "chatting", "rejected"},
    "viewed": {"chatting", "interview", "rejected"},
    "chatting": {"interview", "rejected"},
    "interview": {"passed", "rejected"},
    "passed": {"hired", "rejected"},
    "hired": set(),
    "rejected": set(),
    # 求职者撤回后 HR 不能再单方面推进（需要候选人自己重新投递）
    "withdrawn": set(),
}

# HR 可直接设置的目标状态（interview 只能由「发面试邀约」接口设置，
# 否则会出现「状态是待面试但没有任何面试邀约记录」的脏数据）
DIRECT_STATUSES = ("viewed", "chatting", "passed", "hired", "rejected")


def can_transition(current: str, target: str) -> bool:
    """判断状态流转是否合法。"""
    return target in ALLOWED_TRANSITIONS.get(current, set())


def transition_error(current: str, target: str) -> str:
    """给出可读的拒绝原因，直接展示给 HR。"""
    if target == current:
        return "状态未发生变化"
    if current in ("hired", "rejected", "withdrawn"):
        return "该候选人已处于终态，不能再变更状态"
    return "当前状态不允许变更为「%s」" % target


# ==========================================================
# 请求体
# ==========================================================


class BindCompanyIn(BaseModel):
    """绑定公司、成为该公司的招聘方（演示用的「切换为企业身份」）。

    ⚠️ 真实产品这里需要企业资质审核；演示环境下简化为选一家公司即可，
       但仍然要求明确的公司归属，后续所有 HR 数据都按 company_id 隔离。
    """

    model_config = ConfigDict(populate_by_name=True)

    company_id: str = Field(alias="companyId", min_length=1, max_length=32)
    hr_title: str = Field(default="招聘经理", alias="hrTitle", max_length=30)


class JobPostIn(BaseModel):
    """发布 / 编辑职位入参。

    ⚠️ 不接受 companyId：职位归属只能来自调用者绑定的公司，
       否则任何人都能往别家公司挂职位。
    """

    model_config = ConfigDict(populate_by_name=True)

    title: str = Field(min_length=2, max_length=80)
    category_id: str = Field(alias="categoryId", max_length=32)
    city_id: str = Field(alias="cityId", max_length=32)
    district: str = Field(default="", max_length=30)
    salary_min: int = Field(alias="salaryMin", ge=1, le=500, description="单位 K")
    salary_max: int = Field(alias="salaryMax", ge=1, le=500, description="单位 K")
    salary_months: int = Field(default=12, alias="salaryMonths", ge=12, le=20)
    experience: str = Field(default="经验不限", max_length=20)
    education: str = Field(default="学历不限", max_length=20)
    job_type: str = Field(default="fulltime", alias="jobType", max_length=12)
    kind: str = Field(default="normal", max_length=10)
    tags: list = Field(default_factory=list)
    description: str = Field(default="", max_length=4000)
    requirements: str = Field(default="", max_length=4000)
    status: int = Field(default=1, ge=0, le=1)
    process: list = Field(default_factory=list, description="招聘流程步骤，写入 extra.process")


class JobStatusIn(BaseModel):
    """职位上下架。"""

    model_config = ConfigDict(populate_by_name=True)

    status: int = Field(ge=0, le=1, description="1=招聘中 / 0=已关闭")


class ApplicationStatusIn(BaseModel):
    """HR 变更候选人状态。"""

    model_config = ConfigDict(populate_by_name=True)

    status: str = Field(min_length=1, max_length=12)
    remark: str = Field(default="", max_length=200, description="HR 备注（仅企业侧可见）")
    rating: int = Field(default=0, ge=0, le=5, description="0=未评 / 1~5 星")


class InterviewInviteIn(BaseModel):
    """发出面试邀约。

    ⚠️ roundName 允许自定义：不同公司的轮次叫法不同（一面/技术面/交叉面/终面）。
    """

    model_config = ConfigDict(populate_by_name=True)

    round_no: int = Field(default=1, alias="roundNo", ge=1, le=10)
    round_name: str = Field(default="一面", alias="roundName", max_length=20)
    interview_time: str = Field(alias="interviewTime", description="格式 YYYY-MM-DD HH:MM")
    duration_min: int = Field(default=60, alias="durationMin", ge=10, le=480)
    mode: str = Field(default="onsite", description="onsite / video / phone")
    address: str = Field(default="", max_length=160)
    online_link: str = Field(default="", alias="onlineLink", max_length=200)
    interviewer: str = Field(default="", max_length=40)
    contact: str = Field(default="", max_length=60)
    remark: str = Field(default="", max_length=200)


class CompanyUpdateIn(BaseModel):
    """公司信息维护（企业主页）。"""

    model_config = ConfigDict(populate_by_name=True)

    short_name: str = Field(default="", alias="shortName", max_length=30)
    logo_text: str = Field(default="", alias="logoText", max_length=4)
    logo_color: str = Field(default="", alias="logoColor", max_length=20)
    industry: str = Field(default="", max_length=30)
    scale: str = Field(default="", max_length=20)
    stage: str = Field(default="", max_length=20)
    city: str = Field(default="", max_length=20)
    address: str = Field(default="", max_length=120)
    intro: str = Field(default="", max_length=4000)
    benefits: list = Field(default_factory=list)
    website: str = Field(default="", max_length=120)
