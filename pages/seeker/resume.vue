<template>
	<view class="zn-page zn-page--no-tabbar resume">
		<!-- ==================== 顶部导航 ==================== -->
		<zn-nav-bar title="简历管理" show-back border />

		<!-- ==================== 三态 ==================== -->
		<!-- 未登录：简历接口 auth: true，未登录不展示空表单（否则填完保存才发现要登录） -->
		<zn-empty v-if="!isLogin" icon="person" text="登录后编辑简历"
			desc="简历与账号绑定，投递时会一并发送给企业" btn-text="去登录" @action="goLogin" />

		<view v-else-if="loading" class="state">
			<text class="state__text">正在加载简历…</text>
		</view>

		<view v-else-if="loadFailed" class="state state--fail" hover-class="zn-hover" @tap="load">
			<uni-icons type="refresh" :size="18" color="#ff4d4f"></uni-icons>
			<text class="state__text state__text--fail">简历加载失败，点击重试</text>
		</view>

		<template v-else>
			<view class="resume__body">
				<!-- ==================== 完整度 ==================== -->
				<view class="hero">
					<!--
						⚠️ 圆环用 CSS conic-gradient 画（本项目零图片、不用 canvas）：
						   它只是完整度的视觉强化，百分比文字始终显示，
						   旧 webview 不支持 conic-gradient 时退化成实心主色圆，信息不丢。
						   完整度分数一律用服务端返回的 completeness —— 前端不自己算分。
					-->
					<view class="ring" :style="ringStyle">
						<view class="ring__inner">
							<text class="ring__num">{{ completeness }}</text>
							<text class="ring__unit">%</text>
						</view>
					</view>
					<view class="hero__info">
						<text class="hero__title">{{ completenessTitle }}</text>
						<text class="hero__tip">{{ guideText }}</text>
						<!-- 百分比用共享进度条再表达一次：进度条是视觉基线，颜色/高度与全站一致 -->
						<view class="hero__bar">
							<zn-progress :percent="completeness" :height="12" show-text />
						</view>
						<text class="hero__meta">{{ metaText }}</text>
					</view>
				</view>

				<!-- ==================== 1. 基本信息 ==================== -->
				<view class="card">
					<view class="sec__head" hover-class="zn-hover" @tap="toggle('basic')">
						<text class="sec__title">基本信息</text>
						<text class="sec__sum zn-ellipsis">{{ basicSummary }}</text>
						<view class="sec__arrow" :class="{ 'is-fold': collapsed.basic }">
							<uni-icons type="arrow-down" :size="16" color="#bbbbbb"></uni-icons>
						</view>
					</view>
					<view v-if="!collapsed.basic" class="sec__body">
						<view class="field">
							<text class="field__label">姓名</text>
							<input class="field__input" v-model="form.name" placeholder="请输入真实姓名"
								placeholder-class="field__ph" maxlength="30" />
						</view>
						<view class="field">
							<text class="field__label">性别</text>
							<view class="pills">
								<view v-for="opt in genderOptions" :key="opt.value" class="pills__item"
									:class="{ 'is-active': form.gender === opt.value }" hover-class="zn-hover"
									@tap="setGender(opt.value)">
									<text class="pills__text">{{ opt.label }}</text>
								</view>
							</view>
						</view>
						<view class="field">
							<text class="field__label">出生年</text>
							<input class="field__input" type="number" v-model="form.birthYear"
								placeholder="如 1998" placeholder-class="field__ph" maxlength="4" />
						</view>
						<view class="field">
							<text class="field__label">电话</text>
							<input class="field__input" type="number" v-model="form.phone"
								placeholder="方便 HR 联系你" placeholder-class="field__ph" maxlength="20" />
						</view>
						<view class="field">
							<text class="field__label">邮箱</text>
							<input class="field__input" v-model="form.email" placeholder="用于接收面试通知"
								placeholder-class="field__ph" maxlength="120" />
						</view>
						<view class="field">
							<text class="field__label">现居城市</text>
							<input class="field__input" v-model="form.city" placeholder="如 成都"
								placeholder-class="field__ph" maxlength="20" />
						</view>
					</view>
				</view>

				<!-- ==================== 2. 教育背景 ==================== -->
				<view class="card">
					<view class="sec__head" hover-class="zn-hover" @tap="toggle('edu')">
						<text class="sec__title">教育背景</text>
						<text class="sec__sum zn-ellipsis">{{ eduSummary }}</text>
						<view class="sec__arrow" :class="{ 'is-fold': collapsed.edu }">
							<uni-icons type="arrow-down" :size="16" color="#bbbbbb"></uni-icons>
						</view>
					</view>
					<view v-if="!collapsed.edu" class="sec__body">
						<view class="field">
							<text class="field__label">最高学历</text>
							<view class="field__picker">
								<picker mode="selector" :range="eduOptions" :value="eduIndex" @change="onEduChange">
									<view class="field__value" :class="{ 'is-empty': !form.educationLevel }">
										{{ form.educationLevel || '请选择' }}
									</view>
								</picker>
							</view>
						</view>
						<view class="field">
							<text class="field__label">学校</text>
							<input class="field__input" v-model="form.school" placeholder="毕业院校"
								placeholder-class="field__ph" maxlength="60" />
						</view>
						<view class="field">
							<text class="field__label">专业</text>
							<input class="field__input" v-model="form.major" placeholder="所学专业"
								placeholder-class="field__ph" maxlength="60" />
						</view>
						<view class="field">
							<text class="field__label">毕业年份</text>
							<input class="field__input" type="number" v-model="form.graduationYear"
								placeholder="如 2024" placeholder-class="field__ph" maxlength="4" />
						</view>
					</view>
				</view>

				<!-- ==================== 3. 求职意向 ==================== -->
				<view class="card">
					<view class="sec__head" hover-class="zn-hover" @tap="toggle('intent')">
						<text class="sec__title">求职意向</text>
						<text class="sec__sum zn-ellipsis">{{ intentSummary }}</text>
						<view class="sec__arrow" :class="{ 'is-fold': collapsed.intent }">
							<uni-icons type="arrow-down" :size="16" color="#bbbbbb"></uni-icons>
						</view>
					</view>
					<view v-if="!collapsed.intent" class="sec__body">
						<view class="field">
							<text class="field__label">工作年限</text>
							<view class="field__picker">
								<picker mode="selector" :range="workYearLabels" :value="workYearIndex"
									@change="onWorkYearChange">
									<view class="field__value">{{ workYearLabel }}</view>
								</picker>
							</view>
						</view>
						<view class="field">
							<text class="field__label">求职状态</text>
							<view class="field__picker">
								<picker mode="selector" :range="statusOptions" :value="statusIndex"
									@change="onStatusChange">
									<view class="field__value" :class="{ 'is-empty': !form.currentStatus }">
										{{ form.currentStatus || '请选择' }}
									</view>
								</picker>
							</view>
						</view>
						<view class="field">
							<text class="field__label">期望城市</text>
							<input class="field__input" v-model="form.expectedCity" placeholder="如 成都 / 远程"
								placeholder-class="field__ph" maxlength="20" />
						</view>
						<view class="field">
							<text class="field__label">期望职位</text>
							<input class="field__input" v-model="form.expectedPosition" placeholder="如 前端开发工程师"
								placeholder-class="field__ph" maxlength="60" />
						</view>
						<view class="field">
							<text class="field__label">期望薪资</text>
							<view class="salary">
								<input class="salary__input" type="number" v-model="form.expectedSalaryMin"
									placeholder="最低" placeholder-class="field__ph" maxlength="3" />
								<text class="salary__sep">—</text>
								<input class="salary__input" type="number" v-model="form.expectedSalaryMax"
									placeholder="最高" placeholder-class="field__ph" maxlength="3" />
								<text class="salary__unit">K</text>
							</view>
						</view>
					</view>
				</view>

				<!-- ==================== 4. 技能标签 ==================== -->
				<view class="card">
					<view class="sec__head" hover-class="zn-hover" @tap="toggle('skills')">
						<text class="sec__title">技能标签</text>
						<text class="sec__sum zn-ellipsis">{{ skillsSummary }}</text>
						<view class="sec__arrow" :class="{ 'is-fold': collapsed.skills }">
							<uni-icons type="arrow-down" :size="16" color="#bbbbbb"></uni-icons>
						</view>
					</view>
					<view v-if="!collapsed.skills" class="sec__body">
						<view class="chips">
							<view v-for="(skill, i) in form.skills" :key="skill + '-' + i" class="chips__item">
								<text class="chips__text">{{ skill }}</text>
								<view class="chips__del" hover-class="zn-hover" @tap="removeSkill(i)">
									<uni-icons type="closeempty" :size="14" color="#7f8c8d"></uni-icons>
								</view>
							</view>
							<text v-if="!form.skills.length" class="chips__none">还没有技能标签，添加后完整度可 +10</text>
						</view>
						<view class="addrow">
							<input class="addrow__input" v-model="skillInput" placeholder="如 Vue / Python / 数据分析"
								placeholder-class="field__ph" maxlength="20" confirm-type="done" @confirm="addSkill" />
							<view class="addrow__btn" hover-class="zn-hover" @tap="addSkill">
								<text class="addrow__btn-text">添加</text>
							</view>
						</view>
					</view>
				</view>

				<!-- ==================== 5. 个人优势 ==================== -->
				<view class="card">
					<view class="sec__head" hover-class="zn-hover" @tap="toggle('adv')">
						<text class="sec__title">个人优势</text>
						<text class="sec__sum zn-ellipsis">{{ advSummary }}</text>
						<view class="sec__arrow" :class="{ 'is-fold': collapsed.adv }">
							<uni-icons type="arrow-down" :size="16" color="#bbbbbb"></uni-icons>
						</view>
					</view>
					<view v-if="!collapsed.adv" class="sec__body">
						<!-- maxlength 与服务端上限（2000）一致，避免提交时才 422 -->
						<textarea class="textarea" v-model="form.advantage" maxlength="2000"
							placeholder="一句话说清你的核心优势，例如：5 年后端经验，主导过日均千万级订单系统的重构"
							placeholder-class="field__ph" :auto-height="true" />
						<view class="textarea__foot">
							<text class="textarea__tip">建议 20 字以上，完整度会因此提升</text>
							<text class="textarea__count">{{ advantageLength }}/2000</text>
						</view>
					</view>
				</view>

				<!-- ==================== 6. 经历（教育 / 工作 / 项目） ==================== -->
				<view class="card">
					<view class="sec__head" hover-class="zn-hover" @tap="toggle('exp')">
						<text class="sec__title">经历明细</text>
						<text class="sec__sum zn-ellipsis">{{ expSummary }}</text>
						<view class="sec__arrow" :class="{ 'is-fold': collapsed.exp }">
							<uni-icons type="arrow-down" :size="16" color="#bbbbbb"></uni-icons>
						</view>
					</view>
					<view v-if="!collapsed.exp" class="sec__body">
						<!-- ---------- 教育经历 ---------- -->
						<view class="group">
							<text class="group__title">教育经历</text>
							<view v-for="(item, i) in form.educations" :key="'edu-' + i" class="entry">
								<view class="entry__head">
									<text class="entry__no">教育经历 {{ i + 1 }}</text>
									<view class="entry__del" hover-class="zn-hover"
										@tap="removeEntry('educations', i)">
										<uni-icons type="trash" :size="16" color="#ff4d4f"></uni-icons>
									</view>
								</view>
								<view class="field field--stack">
									<text class="field__label">学校</text>
									<input class="field__input" v-model="item.school" placeholder="学校名称"
										placeholder-class="field__ph" maxlength="60" />
								</view>
								<view class="field field--stack">
									<text class="field__label">专业</text>
									<input class="field__input" v-model="item.major" placeholder="专业名称"
										placeholder-class="field__ph" maxlength="60" />
								</view>
								<view class="field field--stack">
									<text class="field__label">学历</text>
									<view class="field__picker">
										<picker mode="selector" :range="eduOptions" :value="degreeIndex(item)"
											@change="onDegreeChange($event, item)">
											<view class="field__value" :class="{ 'is-empty': !item.degree }">
												{{ item.degree || '请选择' }}
											</view>
										</picker>
									</view>
								</view>
								<view class="field field--stack">
									<text class="field__label">起止时间</text>
									<view class="period">
										<input class="period__input" v-model="item.start" placeholder="2018.09"
											placeholder-class="field__ph" maxlength="12" />
										<text class="period__sep">至</text>
										<input class="period__input" v-model="item.end" placeholder="2022.06"
											placeholder-class="field__ph" maxlength="12" />
									</view>
								</view>
							</view>
							<view class="entry-add" hover-class="zn-hover" @tap="addEntry('educations')">
								<uni-icons type="plusempty" :size="16" color="#00a6a7"></uni-icons>
								<text class="entry-add__text">添加教育经历</text>
							</view>
						</view>

						<!-- ---------- 工作经历 ---------- -->
						<view class="group">
							<text class="group__title">工作经历</text>
							<view v-for="(item, i) in form.experiences" :key="'work-' + i" class="entry">
								<view class="entry__head">
									<text class="entry__no">工作经历 {{ i + 1 }}</text>
									<view class="entry__del" hover-class="zn-hover"
										@tap="removeEntry('experiences', i)">
										<uni-icons type="trash" :size="16" color="#ff4d4f"></uni-icons>
									</view>
								</view>
								<view class="field field--stack">
									<text class="field__label">公司</text>
									<input class="field__input" v-model="item.company" placeholder="公司名称"
										placeholder-class="field__ph" maxlength="60" />
								</view>
								<view class="field field--stack">
									<text class="field__label">职位</text>
									<input class="field__input" v-model="item.title" placeholder="担任职位"
										placeholder-class="field__ph" maxlength="60" />
								</view>
								<view class="field field--stack">
									<text class="field__label">起止时间</text>
									<view class="period">
										<input class="period__input" v-model="item.start" placeholder="2022.07"
											placeholder-class="field__ph" maxlength="12" />
										<text class="period__sep">至</text>
										<input class="period__input" v-model="item.end" placeholder="至今"
											placeholder-class="field__ph" maxlength="12" />
									</view>
								</view>
								<view class="field field--stack">
									<text class="field__label">工作内容</text>
									<textarea class="textarea textarea--sm" v-model="item.desc" maxlength="1000"
										placeholder="负责什么、用到什么技术、拿到什么结果"
										placeholder-class="field__ph" :auto-height="true" />
								</view>
								<view class="field field--stack">
									<text class="field__label">亮点（可多条）</text>
									<view v-for="(hl, hi) in item.highlights" :key="'hl-' + hi" class="addrow">
										<input class="addrow__input" v-model="item.highlights[hi]"
											placeholder="用数字说明收益，如：接口耗时下降 40%"
											placeholder-class="field__ph" maxlength="120" />
										<view class="addrow__del" hover-class="zn-hover"
											@tap="removeHighlight(item, hi)">
											<uni-icons type="closeempty" :size="16" color="#7f8c8d"></uni-icons>
										</view>
									</view>
									<view class="entry-add entry-add--sm" hover-class="zn-hover"
										@tap="addHighlight(item)">
										<uni-icons type="plusempty" :size="14" color="#00a6a7"></uni-icons>
										<text class="entry-add__text">添加亮点</text>
									</view>
								</view>
							</view>
							<view class="entry-add" hover-class="zn-hover" @tap="addEntry('experiences')">
								<uni-icons type="plusempty" :size="16" color="#00a6a7"></uni-icons>
								<text class="entry-add__text">添加工作经历</text>
							</view>
						</view>

						<!-- ---------- 项目经历 ---------- -->
						<view class="group">
							<text class="group__title">项目经历</text>
							<view v-for="(item, i) in form.projects" :key="'prj-' + i" class="entry">
								<view class="entry__head">
									<text class="entry__no">项目经历 {{ i + 1 }}</text>
									<view class="entry__del" hover-class="zn-hover" @tap="removeEntry('projects', i)">
										<uni-icons type="trash" :size="16" color="#ff4d4f"></uni-icons>
									</view>
								</view>
								<view class="field field--stack">
									<text class="field__label">项目名称</text>
									<input class="field__input" v-model="item.name" placeholder="项目名称"
										placeholder-class="field__ph" maxlength="60" />
								</view>
								<view class="field field--stack">
									<text class="field__label">担任角色</text>
									<input class="field__input" v-model="item.role" placeholder="如 前端负责人"
										placeholder-class="field__ph" maxlength="40" />
								</view>
								<view class="field field--stack">
									<text class="field__label">起止时间</text>
									<view class="period">
										<input class="period__input" v-model="item.start" placeholder="2023.03"
											placeholder-class="field__ph" maxlength="12" />
										<text class="period__sep">至</text>
										<input class="period__input" v-model="item.end" placeholder="2023.11"
											placeholder-class="field__ph" maxlength="12" />
									</view>
								</view>
								<view class="field field--stack">
									<text class="field__label">项目说明</text>
									<textarea class="textarea textarea--sm" v-model="item.desc" maxlength="1000"
										placeholder="项目背景、你的职责、最终成果"
										placeholder-class="field__ph" :auto-height="true" />
								</view>
							</view>
							<view class="entry-add" hover-class="zn-hover" @tap="addEntry('projects')">
								<uni-icons type="plusempty" :size="16" color="#00a6a7"></uni-icons>
								<text class="entry-add__text">添加项目经历</text>
							</view>
						</view>
					</view>
				</view>

				<!-- ==================== 7. 是否公开 ==================== -->
				<view class="card">
					<view class="sec__head" hover-class="zn-hover" @tap="toggle('open')">
						<text class="sec__title">简历公开</text>
						<text class="sec__sum zn-ellipsis">{{ form.isOpen ? '公开给企业' : '仅自己可见' }}</text>
						<view class="sec__arrow" :class="{ 'is-fold': collapsed.open }">
							<uni-icons type="arrow-down" :size="16" color="#bbbbbb"></uni-icons>
						</view>
					</view>
					<view v-if="!collapsed.open" class="sec__body">
						<view class="open">
							<view class="open__info">
								<text class="open__title">公开简历给招聘方</text>
								<text class="open__tip">公开后企业可主动联系你；关闭只影响「被发现」，不影响已投递的职位</text>
							</view>
							<switch :checked="form.isOpen" color="#00A6A7" @change="onOpenChange" />
						</view>
					</view>
				</view>

				<view class="resume__foot">
					<text class="resume__foot-text">{{ footTip }}</text>
				</view>
			</view>

			<!-- ==================== 底部固定保存 ==================== -->
			<!-- 表单是长页面，保存按钮固定底部，避免每次都要滑到底 -->
			<view class="savebar">
				<view class="savebar__btn" :class="{ 'is-disabled': saving }" hover-class="zn-hover"
					@tap="onSave">
					<text class="savebar__btn-text">{{ saving ? '保存中…' : '保存简历' }}</text>
				</view>
			</view>
		</template>
	</view>
</template>

<script>
	/**
	 * 简历管理
	 *
	 * 数据来源（services/apply.js）：
	 *   读取  getResume() → {resume, exists}
	 *         exists=false 时 resume 是**结构完整、值为空**的模板（服务端已用账号信息预填 name/email/phone），
	 *         所以表单可以直接绑定，不需要逐字段判空。
	 *   保存  saveResume(整个表单对象) → {resume}
	 *
	 * ⚠️⚠️ 服务端保存是**全量覆盖**（PUT /resume，见 server/app/routers/apply.py save_resume）：
	 *    提交时**没带上来的字段会被置空**。因此本页的纪律是：
	 *      1. 表单必须由 getResume() 的返回值初始化（不是本地空对象）；
	 *      2. 保存时提交**整份表单**（buildPayload），不做「只提交改动字段」的增量提交；
	 *      3. 保存成功后用服务端返回的 resume 回写页面数据 —— 完整度由服务端重算，回写后进度环才准。
	 *    另外：新增字段（比如以后服务端加了「期望行业」而页面还没有对应控件）也会在保存时被清空，
	 *    所以任何字段要上线，必须与表单控件同时上线。
	 *
	 * ⚠️ 出生年（birthYear）字段的特殊处理：
	 *    入参有 birthYear，但服务端的 resume_detail 只回传由它算出的 age（见 schemas/apply.py 的 _age）。
	 *    同一个公式可以无损反推：birthYear = 当前年份 - age（age 为 0 表示没填/超出 16~80 岁）。
	 *    所以加载与保存回写时都用 age 反推 birthYear —— 否则「全量覆盖」会在下一次保存时把出生年清空。
	 *
	 * ⚠️ 本页不做下拉刷新：这是编辑表单，下拉重拉会丢掉用户还没保存的输入（公约的列表页规则不适用于表单页）。
	 *    同理 onShow 也不重新加载，只有 onLoad 与「加载失败重试」会请求接口。
	 */
	import { isLogined } from '@/services/user.js'
	import { getResume, saveResume } from '@/services/apply.js'

	/** 学历选项（服务端只存中文文案、不限枚举，这里是前端的表单选项） */
	const EDU_OPTIONS = ['高中及以下', '大专', '本科', '硕士', '博士']

	/** 求职状态选项（服务端字段默认值就是「离职-随时到岗」） */
	const STATUS_OPTIONS = ['离职-随时到岗', '在职-月内到岗', '在职-考虑机会', '在校-寻找实习']

	/**
	 * 工作年限选项
	 * ⚠️ 服务端只存一个整数年限，而招聘产品习惯用区间表述，
	 *    因此区间在这里折成一个代表值（6-8 年 → 7）。加载时按最接近的选项回显，
	 *    保存后该值会被规整为选项代表值 —— 这是「区间 ↔ 整数」无法避免的取舍。
	 */
	const WORK_YEARS = [
		{ label: '应届生 / 无经验', value: 0 },
		{ label: '1 年', value: 1 },
		{ label: '2 年', value: 2 },
		{ label: '3 年', value: 3 },
		{ label: '4 年', value: 4 },
		{ label: '5 年', value: 5 },
		{ label: '6-8 年', value: 7 },
		{ label: '9-12 年', value: 10 },
		{ label: '12 年以上', value: 15 }
	]

	const GENDER_OPTIONS = [
		{ label: '未填', value: 0 },
		{ label: '男', value: 1 },
		{ label: '女', value: 2 }
	]

	/** 技能标签条数上限：简历上的技能堆到几十条反而稀释重点，服务端也不建议 */
	const MAX_SKILLS = 30

	/** 空表单模板（与 empty_resume 的字段集一致，值为表单可直接绑定的初始值） */
	function makeEmptyForm() {
		return {
			name: '',
			gender: 0,
			birthYear: '',
			phone: '',
			email: '',
			city: '',
			educationLevel: '',
			school: '',
			major: '',
			graduationYear: '',
			workYears: 0,
			currentStatus: '',
			expectedCity: '',
			expectedPosition: '',
			expectedSalaryMin: '',
			expectedSalaryMax: '',
			skills: [],
			advantage: '',
			educations: [],
			experiences: [],
			projects: [],
			isOpen: true
		}
	}

	/** 三类经历的条目模板（新增条目时用，字段名与服务端注释里的 JSON 结构一致） */
	const ENTRY_TEMPLATE = {
		educations: { school: '', major: '', degree: '', start: '', end: '' },
		experiences: { company: '', title: '', start: '', end: '', desc: '', highlights: [] },
		projects: { name: '', role: '', start: '', end: '', desc: '' }
	}

	export default {
		data() {
			return {
				isLogin: false,
				loading: true,
				loadFailed: false,
				saving: false,
				exists: false,
				form: makeEmptyForm(),
				completeness: 0,
				updatedAt: '',
				eduOptions: EDU_OPTIONS,
				statusOptions: STATUS_OPTIONS,
				genderOptions: GENDER_OPTIONS,
				skillInput: '',
				// 经历明细默认折叠：表单已经很长，先让用户看到「还差什么」，需要时再展开填条目
				collapsed: {
					basic: false,
					edu: false,
					intent: false,
					skills: false,
					adv: false,
					exp: true,
					open: true
				}
			}
		},
		computed: {
			ringStyle() {
				const v = Math.max(0, Math.min(100, Number(this.completeness) || 0))
				return {
					background: 'conic-gradient(#00a6a7 0% ' + v + '%, #e5f7f7 ' + v + '% 100%)'
				}
			},
			completenessTitle() {
				if (this.completeness >= 100) return '简历已完整'
				if (this.completeness >= 80) return '简历基本完整'
				if (this.completeness >= 50) return '简历还差一些内容'
				return '简历内容偏少'
			},
			/**
			 * 引导文案：按服务端 compute_completeness 的同一份字段清单算出「还差哪些」。
			 * ⚠️ 分数不用前端算（用服务端的 completeness），这里只是把分数翻译成可执行的待办。
			 */
			missingParts() {
				const list = []
				const f = this.form
				if (!String(f.name || '').trim()) list.push('姓名')
				if (!String(f.phone || '').trim()) list.push('电话')
				if (!String(f.city || '').trim()) list.push('现居城市')
				if (!f.educationLevel) list.push('最高学历')
				if (!String(f.school || '').trim()) list.push('毕业院校')
				if (!String(f.expectedCity || '').trim()) list.push('期望城市')
				if (!String(f.expectedPosition || '').trim()) list.push('期望职位')
				if (!(f.skills || []).length) list.push('技能标签')
				if (String(f.advantage || '').length < 20) list.push('个人优势（20 字以上）')
				if (!(f.educations || []).length) list.push('教育经历')
				if (!(f.experiences || []).length) list.push('工作经历')
				if (!(f.projects || []).length) list.push('项目经历')
				return list
			},
			guideText() {
				const miss = this.missingParts
				if (!miss.length) return '所有加分项都填好了，保持更新即可'
				if (miss.length > 4) return '还差 ' + miss.length + ' 项：' + miss.slice(0, 4).join('、') + ' 等'
				return '还差：' + miss.join('、')
			},
			metaText() {
				if (!this.exists) return '还未创建简历 · 已用账号信息预填基本信息'
				return this.updatedAt ? '最近更新：' + this.updatedAt : '已保存'
			},
			advantageLength() {
				return String(this.form.advantage || '').length
			},
			basicSummary() {
				const gender = (GENDER_OPTIONS.filter(g => g.value === this.form.gender)[0] || {}).label || ''
				const parts = [this.form.name, this.form.gender ? gender : '', this.form.city]
				return parts.filter(Boolean).join(' · ') || '待填写'
			},
			eduSummary() {
				const parts = [this.form.educationLevel, this.form.school]
				return parts.filter(Boolean).join(' · ') || '待填写'
			},
			salaryText() {
				const min = this.toInt(this.form.expectedSalaryMin)
				const max = this.toInt(this.form.expectedSalaryMax)
				if (!min && !max) return ''
				if (min && max) return min + '-' + max + 'K'
				return (min || max) + 'K'
			},
			intentSummary() {
				const parts = [this.form.expectedPosition, this.form.expectedCity, this.salaryText]
				return parts.filter(Boolean).join(' · ') || '待填写'
			},
			skillsSummary() {
				return this.form.skills.length ? this.form.skills.length + ' 个标签' : '待填写'
			},
			advSummary() {
				return this.advantageLength ? this.advantageLength + ' 字' : '待填写'
			},
			expSummary() {
				return '教育 ' + this.form.educations.length + ' · 工作 ' + this.form.experiences.length +
					' · 项目 ' + this.form.projects.length
			},
			eduIndex() {
				const i = EDU_OPTIONS.indexOf(this.form.educationLevel)
				return i > -1 ? i : 0
			},
			statusIndex() {
				const i = STATUS_OPTIONS.indexOf(this.form.currentStatus)
				return i > -1 ? i : 0
			},
			workYearLabels() {
				return WORK_YEARS.map(item => item.label)
			},
			/** 工作年限回显：历史值不在选项里时取最接近的一项（见 WORK_YEARS 注释） */
			workYearIndex() {
				const value = Number(this.form.workYears) || 0
				let best = 0
				let bestGap = Math.abs(WORK_YEARS[0].value - value)
				WORK_YEARS.forEach((item, i) => {
					const gap = Math.abs(item.value - value)
					if (gap < bestGap) {
						best = i
						bestGap = gap
					}
				})
				return best
			},
			workYearLabel() {
				return WORK_YEARS[this.workYearIndex].label
			},
			footTip() {
				return this.exists
					? '简历保存后，投递时会自动发送给企业'
					: '保存后即生成简历，之后投递会自动带上'
			}
		},
		onLoad() {
			this.load()
		},
		methods: {
			/* ==========================================================
			 * 数据
			 * ========================================================== */
			async load() {
				this.isLogin = isLogined()
				if (!this.isLogin) {
					this.form = makeEmptyForm()
					this.completeness = 0
					this.loading = false
					this.loadFailed = false
					return
				}
				this.loading = true
				try {
					const res = await getResume()
					this.exists = !!(res && res.exists)
					this.applyResume((res && res.resume) || {}, false)
					this.loadFailed = false
				} catch (e) {
					// 纯接口模式：失败就显示失败态（不做 mock 兜底），表单保持空模板
					this.form = makeEmptyForm()
					this.completeness = 0
					this.loadFailed = true
				} finally {
					this.loading = false
				}
			},

			/**
			 * 用服务端返回的简历回写表单
			 * @param {object} raw 服务端 resume 对象（新建时为结构完整的空模板）
			 * @param {boolean} keepBirthYear 服务端未给出可用 age 时，是否沿用页面上已填的出生年
			 *        （保存回写时传 true：用户刚填的值不该被一次回写清掉）
			 */
			applyResume(raw, keepBirthYear) {
				const data = raw || {}
				const recovered = this.birthYearFromAge(data.age)
				const birthYear = recovered
					? String(recovered)
					: (keepBirthYear ? this.form.birthYear : '')
				this.form = {
					name: data.name || '',
					gender: Number(data.gender) || 0,
					birthYear,
					phone: data.phone || '',
					email: data.email || '',
					city: data.city || '',
					educationLevel: data.educationLevel || '',
					school: data.school || '',
					major: data.major || '',
					graduationYear: data.graduationYear ? String(data.graduationYear) : '',
					workYears: Number(data.workYears) || 0,
					currentStatus: data.currentStatus || '',
					expectedCity: data.expectedCity || '',
					expectedPosition: data.expectedPosition || '',
					expectedSalaryMin: data.expectedSalaryMin ? String(data.expectedSalaryMin) : '',
					expectedSalaryMax: data.expectedSalaryMax ? String(data.expectedSalaryMax) : '',
					skills: (data.skills || []).slice(),
					advantage: data.advantage || '',
					educations: this.normalizeEntries(data.educations, 'educations'),
					experiences: this.normalizeEntries(data.experiences, 'experiences'),
					projects: this.normalizeEntries(data.projects, 'projects'),
					// 服务端 is_open 是 0/1，空模板给的是布尔；统一收敛成布尔给 switch 用
					isOpen: data.isOpen === undefined ? true : !!data.isOpen
				}
				this.completeness = Number(data.completeness) || 0
				this.updatedAt = data.updatedAt || ''
			},

			/**
			 * 经历数组规整
			 * ⚠️ 服务端把三类经历存成 JSON，历史数据里可能缺字段（如没有 highlights），
			 *    这里按条目的字段清单补默认值 —— 这不是编造业务数据，而是把缺失字段规整成表单的合法初值，
			 *    否则数组操作（push / splice）与 v-model 会在 undefined 上炸掉。
			 */
			normalizeEntries(list, type) {
				const rows = Array.isArray(list) ? list : []
				return rows.map(row => {
					const src = row || {}
					const tpl = ENTRY_TEMPLATE[type]
					const item = {}
					Object.keys(tpl).forEach(key => {
						if (key === 'highlights') {
							item.highlights = (Array.isArray(src.highlights) ? src.highlights : [])
								.map(hl => String(hl || ''))
						} else {
							item[key] = src[key] === undefined || src[key] === null ? '' : String(src[key])
						}
					})
					return item
				})
			},

			/** age → 出生年（与服务端 _age 同一公式的反推，见文件头说明） */
			birthYearFromAge(age) {
				const value = Number(age) || 0
				if (value < 16 || value > 80) return 0
				return new Date().getFullYear() - value
			},

			/* ==========================================================
			 * 折叠 / 表单操作
			 * ========================================================== */
			toggle(key) {
				this.collapsed[key] = !this.collapsed[key]
			},

			setGender(value) {
				this.form.gender = value
			},

			onEduChange(e) {
				this.form.educationLevel = EDU_OPTIONS[Number(e.detail.value)] || ''
			},

			onStatusChange(e) {
				this.form.currentStatus = STATUS_OPTIONS[Number(e.detail.value)] || ''
			},

			onWorkYearChange(e) {
				const hit = WORK_YEARS[Number(e.detail.value)]
				this.form.workYears = hit ? hit.value : 0
			},

			onOpenChange(e) {
				this.form.isOpen = !!e.detail.value
			},

			/** 教育经历条目里的「学历」选择器的下标 */
			degreeIndex(item) {
				const i = EDU_OPTIONS.indexOf(item.degree)
				return i > -1 ? i : 0
			},

			onDegreeChange(e, item) {
				item.degree = EDU_OPTIONS[Number(e.detail.value)] || ''
			},

			/* ---------------- 技能标签 ---------------- */
			addSkill() {
				const value = String(this.skillInput || '').trim()
				if (!value) {
					uni.showToast({ title: '请输入技能名称', icon: 'none' })
					return
				}
				if (this.form.skills.indexOf(value) > -1) {
					uni.showToast({ title: '该技能已添加', icon: 'none' })
					return
				}
				if (this.form.skills.length >= MAX_SKILLS) {
					uni.showToast({ title: '技能标签最多 ' + MAX_SKILLS + ' 个', icon: 'none' })
					return
				}
				this.form.skills.push(value)
				this.skillInput = ''
			},

			removeSkill(index) {
				this.form.skills.splice(index, 1)
			},

			/* ---------------- 经历条目 ---------------- */
			addEntry(type) {
				const tpl = ENTRY_TEMPLATE[type]
				const item = {}
				Object.keys(tpl).forEach(key => {
					item[key] = key === 'highlights' ? [] : ''
				})
				this.form[type].push(item)
			},

			removeEntry(type, index) {
				this.form[type].splice(index, 1)
			},

			addHighlight(item) {
				if (!Array.isArray(item.highlights)) item.highlights = []
				item.highlights.push('')
			},

			removeHighlight(item, index) {
				item.highlights.splice(index, 1)
			},

			/* ==========================================================
			 * 校验与保存
			 * ========================================================== */
			toInt(value) {
				const n = parseInt(value, 10)
				return isNaN(n) ? 0 : n
			},

			/** 本地校验：把服务端的 422 提前成一句人话（服务端仍会再校验一次） */
			validate() {
				if (!String(this.form.name || '').trim()) return '请填写姓名'
				const year = new Date().getFullYear()
				const birth = this.toInt(this.form.birthYear)
				if (birth && (birth < 1940 || birth > year)) return '出生年份请填 1940 - ' + year
				const grad = this.toInt(this.form.graduationYear)
				if (grad && (grad < 1950 || grad > year + 10)) return '毕业年份填写有误，请检查'
				const min = this.toInt(this.form.expectedSalaryMin)
				const max = this.toInt(this.form.expectedSalaryMax)
				if (min > 500 || max > 500) return '期望薪资请填 0 - 500（单位 K）'
				if (min && max && min > max) return '期望薪资下限不能高于上限'
				const phone = String(this.form.phone || '').trim()
				if (phone && !/^[0-9+\-]{6,20}$/.test(phone)) return '联系电话格式不正确'
				const email = String(this.form.email || '').trim()
				if (email && email.indexOf('@') < 1) return '邮箱格式不正确'
				return ''
			},

			/**
			 * 组装提交体
			 * ⚠️ 这里必须是**整份表单**：接口是全量覆盖，漏一个字段就等于把它清空。
			 *    同时把三类经历按明确的字段清单重建，避免把页面上的辅助字段（如下标、临时态）提交上去。
			 */
			buildPayload() {
				const f = this.form
				return {
					name: String(f.name || '').trim(),
					gender: Number(f.gender) || 0,
					birthYear: this.toInt(f.birthYear),
					phone: String(f.phone || '').trim(),
					email: String(f.email || '').trim(),
					city: String(f.city || '').trim(),
					educationLevel: f.educationLevel || '',
					school: String(f.school || '').trim(),
					major: String(f.major || '').trim(),
					graduationYear: this.toInt(f.graduationYear),
					workYears: Number(f.workYears) || 0,
					currentStatus: f.currentStatus || '',
					expectedCity: String(f.expectedCity || '').trim(),
					expectedPosition: String(f.expectedPosition || '').trim(),
					expectedSalaryMin: this.toInt(f.expectedSalaryMin),
					expectedSalaryMax: this.toInt(f.expectedSalaryMax),
					skills: (f.skills || []).map(s => String(s || '').trim()).filter(Boolean),
					advantage: String(f.advantage || ''),
					educations: (f.educations || []).map(item => ({
						school: String(item.school || '').trim(),
						major: String(item.major || '').trim(),
						degree: item.degree || '',
						start: String(item.start || '').trim(),
						end: String(item.end || '').trim()
					})),
					experiences: (f.experiences || []).map(item => ({
						company: String(item.company || '').trim(),
						title: String(item.title || '').trim(),
						start: String(item.start || '').trim(),
						end: String(item.end || '').trim(),
						desc: String(item.desc || ''),
						// 亮点里的空行不发出去，避免简历上出现空条目
						highlights: (item.highlights || []).map(h => String(h || '').trim()).filter(Boolean)
					})),
					projects: (f.projects || []).map(item => ({
						name: String(item.name || '').trim(),
						role: String(item.role || '').trim(),
						start: String(item.start || '').trim(),
						end: String(item.end || '').trim(),
						desc: String(item.desc || '')
					})),
					isOpen: !!f.isOpen
				}
			},

			async onSave() {
				if (this.saving) return
				const msg = this.validate()
				if (msg) {
					uni.showToast({ title: msg, icon: 'none' })
					return
				}
				this.saving = true
				try {
					const res = await saveResume(this.buildPayload())
					// 回写服务端结果：完整度是服务端重算的，不回写进度环就不准
					this.applyResume((res && res.resume) || {}, true)
					this.exists = true
					uni.showToast({ title: '简历已保存', icon: 'none' })
				} catch (e) {
					// 失败提示由 services/api.js 统一处理；表单内容原样保留，用户可直接重试
					// （全量提交没有「保存了一半」的中间态）
				} finally {
					this.saving = false
				}
			},

			goLogin() {
				uni.navigateTo({ url: '/pages/login/login' })
			}
		}
	}
</script>

<style lang="scss" scoped>
	/* 底部固定保存条占位，避免最后一个区块被遮住 */
	.resume__body {
		padding: $zn-gap $zn-page-padding 180rpx;
	}

	.state {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		padding: 100rpx 0;
	}

	.state--fail {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 40rpx 24rpx;
		margin: 40rpx $zn-page-padding 0;
		box-shadow: $zn-shadow-sm;
	}

	.state__text {
		font-size: 26rpx;
		color: $zn-text-grey;
	}

	.state__text--fail {
		color: $zn-red;
		margin-left: 10rpx;
	}

	/* ==================== 完整度 ==================== */
	.hero {
		display: flex;
		flex-direction: row;
		align-items: center;
		background: linear-gradient(135deg, #ffffff 0%, #f2fbfb 100%);
		border-radius: $zn-radius-lg;
		padding: 28rpx 24rpx;
		box-shadow: $zn-shadow;
	}

	.ring {
		width: 148rpx;
		height: 148rpx;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.ring__inner {
		width: 116rpx;
		height: 116rpx;
		border-radius: 50%;
		background-color: #ffffff;
		display: flex;
		flex-direction: row;
		align-items: baseline;
		justify-content: center;
	}

	.ring__num {
		font-size: 46rpx;
		font-weight: 700;
		color: $zn-theme-dark;
		line-height: 116rpx;
	}

	.ring__unit {
		font-size: 22rpx;
		color: $zn-theme-dark;
		margin-left: 2rpx;
	}

	.hero__info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin-left: $zn-gap;
	}

	.hero__title {
		font-size: 32rpx;
		font-weight: 700;
		color: $zn-text-title;
	}

	.hero__tip {
		font-size: 23rpx;
		color: $zn-text-sub;
		margin-top: 10rpx;
		line-height: 34rpx;
	}

	.hero__bar {
		margin-top: 16rpx;
	}

	.hero__meta {
		font-size: 20rpx;
		color: $zn-text-light;
		margin-top: 12rpx;
	}

	/* ==================== 分区卡片 ==================== */
	.card {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		margin-top: $zn-gap;
		box-shadow: $zn-shadow-sm;
		overflow: hidden;
	}

	.sec__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 26rpx $zn-gap;
	}

	.sec__title {
		font-size: 30rpx;
		font-weight: 700;
		color: $zn-text-title;
		flex-shrink: 0;
	}

	.sec__sum {
		flex: 1;
		min-width: 0;
		font-size: 22rpx;
		color: $zn-text-grey;
		margin: 0 $zn-gap-sm 0 $zn-gap;
		text-align: right;
	}

	.sec__arrow {
		width: 40rpx;
		height: 40rpx;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		transition: transform 0.2s ease;

		&.is-fold {
			transform: rotate(-90deg);
		}
	}

	.sec__body {
		padding: 0 $zn-gap $zn-gap;
		border-top: 1rpx solid $zn-line;
		padding-top: $zn-gap;
	}

	/* ==================== 表单行 ==================== */
	.field {
		display: flex;
		flex-direction: row;
		align-items: center;
		min-height: 88rpx;
		border-bottom: 1rpx solid $zn-line;

		&:last-child {
			border-bottom: none;
		}

		&--stack {
			flex-direction: column;
			align-items: stretch;
			padding: 16rpx 0;
		}
	}

	.field__label {
		width: 160rpx;
		flex-shrink: 0;
		font-size: 26rpx;
		color: $zn-text-main;
	}

	.field--stack .field__label {
		width: auto;
		font-size: 23rpx;
		color: $zn-text-grey;
		margin-bottom: 8rpx;
	}

	.field__input {
		flex: 1;
		min-width: 0;
		font-size: 27rpx;
		color: $zn-text-main;
		text-align: right;
		height: 60rpx;
	}

	.field--stack .field__input {
		text-align: left;
		background-color: $zn-bg-grey;
		border-radius: $zn-radius-sm;
		padding: 0 16rpx;
		height: 68rpx;
	}

	.field__ph {
		color: $zn-text-light;
		font-size: 25rpx;
	}

	.field__picker {
		flex: 1;
		min-width: 0;
	}

	.field__value {
		font-size: 27rpx;
		color: $zn-text-main;
		text-align: right;

		&.is-empty {
			color: $zn-text-light;
		}
	}

	.field--stack .field__value {
		text-align: left;
		background-color: $zn-bg-grey;
		border-radius: $zn-radius-sm;
		padding: 18rpx 16rpx;
		font-size: 26rpx;
	}

	/* ---------- 性别 / 选项胶囊 ---------- */
	.pills {
		flex: 1;
		display: flex;
		flex-direction: row;
		justify-content: flex-end;
	}

	.pills__item {
		height: 60rpx;
		padding: 0 26rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-left: 14rpx;

		&.is-active {
			background-color: $zn-theme-light;
		}
	}

	.pills__text {
		font-size: 25rpx;
		color: $zn-text-sub;
	}

	.pills__item.is-active .pills__text {
		color: $zn-theme-dark;
		font-weight: 600;
	}

	/* ---------- 薪资区间 ---------- */
	.salary {
		flex: 1;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: flex-end;
	}

	.salary__input {
		width: 140rpx;
		height: 60rpx;
		background-color: $zn-bg-grey;
		border-radius: $zn-radius-sm;
		text-align: center;
		font-size: 26rpx;
		color: $zn-text-main;
	}

	.salary__sep {
		font-size: 24rpx;
		color: $zn-text-light;
		margin: 0 12rpx;
	}

	.salary__unit {
		font-size: 24rpx;
		color: $zn-text-sub;
		margin-left: 12rpx;
	}

	/* ==================== 技能标签 ==================== */
	.chips {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		min-height: 60rpx;
	}

	.chips__item {
		display: flex;
		flex-direction: row;
		align-items: center;
		height: 56rpx;
		padding: 0 16rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-theme-light;
		margin: 0 14rpx 14rpx 0;
	}

	.chips__text {
		font-size: 24rpx;
		color: $zn-theme-dark;
	}

	.chips__del {
		width: 34rpx;
		height: 34rpx;
		margin-left: 6rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.chips__none {
		font-size: 23rpx;
		color: $zn-text-light;
		line-height: 56rpx;
	}

	.addrow {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 12rpx;
	}

	.addrow__input {
		flex: 1;
		min-width: 0;
		height: 72rpx;
		background-color: $zn-bg-grey;
		border-radius: $zn-radius-sm;
		padding: 0 16rpx;
		font-size: 26rpx;
		color: $zn-text-main;
	}

	.addrow__btn {
		flex-shrink: 0;
		height: 72rpx;
		padding: 0 28rpx;
		margin-left: 14rpx;
		border-radius: $zn-radius-sm;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.addrow__btn-text {
		font-size: 26rpx;
		font-weight: 600;
		color: #ffffff;
	}

	.addrow__del {
		width: 56rpx;
		height: 72rpx;
		margin-left: 8rpx;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	/* ==================== 个人优势 / 多行文本 ==================== */
	.textarea {
		width: 100%;
		min-height: 180rpx;
		background-color: $zn-bg-grey;
		border-radius: $zn-radius-sm;
		padding: 20rpx;
		font-size: 26rpx;
		color: $zn-text-main;
		line-height: 40rpx;

		&--sm {
			min-height: 120rpx;
			font-size: 25rpx;
		}
	}

	.textarea__foot {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		margin-top: 12rpx;
	}

	.textarea__tip {
		font-size: 21rpx;
		color: $zn-theme-dark;
	}

	.textarea__count {
		font-size: 21rpx;
		color: $zn-text-light;
	}

	/* ==================== 经历条目 ==================== */
	.group {
		margin-bottom: $zn-gap-lg;
	}

	.group__title {
		display: block;
		font-size: 26rpx;
		font-weight: 700;
		color: $zn-theme-dark;
		margin-bottom: 12rpx;
	}

	.entry {
		background-color: $zn-theme-lighter;
		border-radius: $zn-radius;
		padding: 20rpx;
		margin-bottom: 16rpx;
	}

	.entry__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 8rpx;
	}

	.entry__no {
		font-size: 24rpx;
		font-weight: 600;
		color: $zn-text-main;
	}

	.entry__del {
		width: 52rpx;
		height: 52rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.entry-add {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		height: 76rpx;
		border-radius: $zn-radius;
		border: 2rpx dashed rgba(0, 166, 167, 0.4);
		background-color: $zn-theme-lighter;

		&--sm {
			height: 60rpx;
			margin-top: 4rpx;
		}
	}

	.entry-add__text {
		font-size: 25rpx;
		color: $zn-theme-dark;
		margin-left: 8rpx;
	}

	/* 起止时间 */
	.period {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.period__input {
		flex: 1;
		min-width: 0;
		height: 68rpx;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-sm;
		padding: 0 16rpx;
		font-size: 25rpx;
		color: $zn-text-main;
	}

	.period__sep {
		font-size: 24rpx;
		color: $zn-text-light;
		margin: 0 12rpx;
	}

	/* ==================== 简历公开 ==================== */
	.open {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding-top: 4rpx;
	}

	.open__info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin-right: $zn-gap;
	}

	.open__title {
		font-size: 27rpx;
		color: $zn-text-main;
	}

	.open__tip {
		font-size: 22rpx;
		color: $zn-text-grey;
		margin-top: 8rpx;
		line-height: 32rpx;
	}

	/* ==================== 底部说明 ==================== */
	.resume__foot {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: $zn-gap-lg 0 10rpx;
	}

	.resume__foot-text {
		font-size: 22rpx;
		color: $zn-text-light;
	}

	/* ==================== 固定保存条 ==================== */
	.savebar {
		position: fixed;
		left: 0;
		right: 0;
		bottom: 0;
		z-index: 960;
		padding: 18rpx $zn-page-padding calc(18rpx + env(safe-area-inset-bottom));
		background-color: rgba(255, 255, 255, 0.96);
		border-top: 1rpx solid $zn-line;
	}

	.savebar__btn {
		height: 88rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;

		&.is-disabled {
			opacity: 0.6;
		}
	}

	.savebar__btn-text {
		font-size: 30rpx;
		font-weight: 700;
		color: #ffffff;
	}
</style>
