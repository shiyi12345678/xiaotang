<template>
	<view class="zn-page zn-page--no-tabbar hrcand">
		<zn-nav-bar title="候选人详情" :show-back="true" border />

		<!-- ==================== 一、加载中 ==================== -->
		<view v-if="loading" class="hrcand__state">
			<text class="hrcand__state-text">正在打开简历…</text>
		</view>

		<!-- ==================== 二、加载失败：可重试 ==================== -->
		<zn-empty v-else-if="failed" icon="info" text="候选人详情加载失败" :desc="failedMsg"
			btn-text="重新加载" @action="load" />

		<!-- ==================== 三、内容 ==================== -->
		<block v-else>
			<!-- ---------- 候选人头部 ---------- -->
			<view class="hero">
				<zn-avatar :name="cand.name" :size="120" />
				<view class="hero__main">
					<view class="hero__row">
						<text class="hero__name">{{ cand.name || '匿名候选人' }}</text>
						<zn-tag :text="app.statusText" :type="tagType(app.statusType)" size="sm" />
					</view>
					<text class="hero__meta">{{ heroMeta }}</text>
					<view class="hero__progress">
						<text class="hero__progress-label">完整度 {{ cand.completeness || 0 }}%</text>
						<view class="hero__progress-bar">
							<zn-progress :percent="cand.completeness || 0" :height="8" />
						</view>
					</view>
				</view>
			</view>

			<!-- ---------- 投递信息（含职位快照） ---------- -->
			<view class="sec">
				<zn-section-header title="投递信息" />
				<view class="kv">
					<text class="kv__k">投递职位</text>
					<text class="kv__v zn-ellipsis">{{ (app.job && app.job.title) || app.jobTitle || '—' }}</text>
				</view>
				<view class="kv">
					<text class="kv__k">职位薪资</text>
					<text class="kv__v">{{ (app.job && app.job.salaryText) || app.salaryText || '面议' }}</text>
				</view>
				<view v-if="app.job && app.job.status === 0" class="kv">
					<text class="kv__k">职位状态</text>
					<text class="kv__v kv__v--warn">该职位已关闭（投递记录仍在）</text>
				</view>
				<view class="kv">
					<text class="kv__k">投递时间</text>
					<text class="kv__v">{{ app.createdAt || app.createdText || '—' }}</text>
				</view>
				<view class="kv">
					<text class="kv__k">查看时间</text>
					<text class="kv__v">{{ app.viewedAt || '—' }}</text>
				</view>
				<view v-if="app.greeting" class="kv kv--block">
					<text class="kv__k">打招呼</text>
					<text class="kv__v kv__v--text">{{ app.greeting }}</text>
				</view>
			</view>

			<!-- ---------- 联系方式 ---------- -->
			<view class="sec">
				<zn-section-header title="联系方式" subtitle="仅招聘方可见" />
				<view class="kv">
					<text class="kv__k">电话</text>
					<text class="kv__v">{{ detail.phone || '未填写' }}</text>
				</view>
				<view class="kv">
					<text class="kv__k">邮箱</text>
					<text class="kv__v">{{ detail.email || '未填写' }}</text>
				</view>
				<view class="kv">
					<text class="kv__k">现居 / 期望</text>
					<text class="kv__v zn-ellipsis">{{ [cand.city, cand.expectedCity].filter(Boolean).join(' → ') || '未填写' }}</text>
				</view>
				<view class="kv">
					<text class="kv__k">期望职位</text>
					<text class="kv__v zn-ellipsis">{{ cand.expectedPosition || '未填写' }}</text>
				</view>
				<view class="kv">
					<text class="kv__k">期望薪资</text>
					<text class="kv__v">{{ cand.expectedSalaryText || '面议' }}</text>
				</view>
				<view class="kv">
					<text class="kv__k">求职状态</text>
					<text class="kv__v">{{ cand.currentStatus || '未填写' }}</text>
				</view>
			</view>

			<!-- ---------- 教育经历 ---------- -->
			<view class="sec">
				<zn-section-header title="教育经历" :subtitle="(detail.educations || []).length + ' 段'"
					:more="open.edu ? '收起' : '展开'" @more="toggle('edu')" />
				<block v-if="open.edu">
					<zn-empty v-if="!(detail.educations || []).length" icon="info" text="未填写教育经历" />
					<view v-for="(e, i) in (detail.educations || [])" :key="i" class="item">
						<view class="item__head">
							<text class="item__title zn-ellipsis">{{ e.school || '—' }}</text>
							<text class="item__time">{{ period(e.start, e.end) }}</text>
						</view>
						<text class="item__sub">{{ [e.major, e.degree].filter(Boolean).join(' · ') || '—' }}</text>
					</view>
				</block>
			</view>

			<!-- ---------- 工作经历 ---------- -->
			<view class="sec">
				<zn-section-header title="工作经历" :subtitle="(detail.experiences || []).length + ' 段'"
					:more="open.exp ? '收起' : '展开'" @more="toggle('exp')" />
				<block v-if="open.exp">
					<zn-empty v-if="!(detail.experiences || []).length" icon="info" text="未填写工作经历" />
					<view v-for="(e, i) in (detail.experiences || [])" :key="i" class="item">
						<view class="item__head">
							<text class="item__title zn-ellipsis">{{ e.company || '—' }}</text>
							<text class="item__time">{{ period(e.start, e.end) }}</text>
						</view>
						<text class="item__sub">{{ e.title || '—' }}</text>
						<text v-if="e.desc" class="item__desc">{{ e.desc }}</text>
						<view v-if="(e.highlights || []).length" class="item__points">
							<text v-for="(h, j) in e.highlights" :key="j" class="item__point">· {{ h }}</text>
						</view>
					</view>
				</block>
			</view>

			<!-- ---------- 项目经历 ---------- -->
			<view class="sec">
				<zn-section-header title="项目经历" :subtitle="(detail.projects || []).length + ' 段'"
					:more="open.proj ? '收起' : '展开'" @more="toggle('proj')" />
				<block v-if="open.proj">
					<zn-empty v-if="!(detail.projects || []).length" icon="info" text="未填写项目经历" />
					<view v-for="(p, i) in (detail.projects || [])" :key="i" class="item">
						<view class="item__head">
							<text class="item__title zn-ellipsis">{{ p.name || '—' }}</text>
							<text class="item__time">{{ period(p.start, p.end) }}</text>
						</view>
						<text v-if="p.role" class="item__sub">{{ p.role }}</text>
						<text v-if="p.desc" class="item__desc">{{ p.desc }}</text>
					</view>
				</block>
			</view>

			<!-- ---------- 技能 / 个人优势 ---------- -->
			<view class="sec">
				<zn-section-header title="技能标签" :subtitle="(cand.skills || []).length + ' 项'"
					:more="open.skill ? '收起' : '展开'" @more="toggle('skill')" />
				<block v-if="open.skill">
					<zn-empty v-if="!(cand.skills || []).length" icon="info" text="未填写技能标签" />
					<view v-else class="chips">
						<text v-for="(s, i) in cand.skills" :key="i" class="chip">{{ s }}</text>
					</view>
				</block>
			</view>

			<view class="sec">
				<zn-section-header title="个人优势" :more="open.adv ? '收起' : '展开'" @more="toggle('adv')" />
				<block v-if="open.adv">
					<text v-if="detail.advantage" class="para">{{ detail.advantage }}</text>
					<zn-empty v-else icon="info" text="未填写个人优势" />
				</block>
			</view>

			<!-- ---------- 面试邀约记录 ---------- -->
			<view class="sec">
				<zn-section-header title="面试邀约" :subtitle="interviews.length + ' 场'" />
				<zn-empty v-if="!interviews.length" icon="calendar" text="还没有发出面试邀约"
					desc="点击下方「发面试邀约」安排面试" />
				<view v-else class="ivs">
					<view v-for="it in interviews" :key="it.id" class="iv">
						<view class="iv__head">
							<text class="iv__round">{{ it.roundName || ('第' + it.roundNo + '轮') }}</text>
							<zn-tag :text="it.statusText" type="orange" size="xs" />
						</view>
						<view class="kv">
							<text class="kv__k">时间</text>
							<text class="kv__v">{{ it.timeText }}（{{ it.durationMin }} 分钟）</text>
						</view>
						<view class="kv">
							<text class="kv__k">方式</text>
							<text class="kv__v">{{ it.modeText }}</text>
						</view>
						<view v-if="it.address" class="kv">
							<text class="kv__k">地点</text>
							<text class="kv__v zn-ellipsis">{{ it.address }}</text>
						</view>
						<view v-if="it.onlineLink" class="kv">
							<text class="kv__k">链接</text>
							<text class="kv__v zn-ellipsis">{{ it.onlineLink }}</text>
						</view>
						<view v-if="it.interviewer" class="kv">
							<text class="kv__k">面试官</text>
							<text class="kv__v">{{ it.interviewer }}</text>
						</view>
						<view v-if="it.contact" class="kv">
							<text class="kv__k">联系方式</text>
							<text class="kv__v">{{ it.contact }}</text>
						</view>
						<view v-if="it.remark" class="kv kv--block">
							<text class="kv__k">备注</text>
							<text class="kv__v kv__v--text">{{ it.remark }}</text>
						</view>
					</view>
				</view>
			</view>

			<!-- ---------- 我的处理记录（仅企业侧可见） ---------- -->
			<view class="sec">
				<zn-section-header title="我的处理记录" subtitle="仅企业侧可见" />
				<view class="kv">
					<text class="kv__k">评分</text>
					<view class="stars">
						<uni-icons v-for="n in 5" :key="n" :type="(app.hrRating || 0) >= n ? 'star-filled' : 'star'"
							:size="16" :color="(app.hrRating || 0) >= n ? '#ff8f1f' : '#dddddd'"></uni-icons>
					</view>
				</view>
				<view class="kv kv--block">
					<text class="kv__k">备注</text>
					<text class="kv__v kv__v--text">{{ app.hrRemark || '暂无备注' }}</text>
				</view>
			</view>

			<!-- ---------- 沟通入口（仅当候选人主动发起过沟通） ---------- -->
			<view class="sec">
				<zn-section-header title="在线沟通" />
				<view v-if="conversation" class="chat-entry" hover-class="zn-hover" @tap="goChat">
					<uni-icons type="chat" :size="20" color="#00A6A7"></uni-icons>
					<view class="chat-entry__main">
						<text class="chat-entry__title">查看与 {{ cand.name }} 的沟通记录</text>
						<text class="chat-entry__sub">候选人主动发起过沟通，可继续在会话里聊</text>
					</view>
					<uni-icons type="right" :size="14" color="#bbbbbb"></uni-icons>
				</view>
				<view v-else class="chat-tip">
					<uni-icons type="info" :size="16" color="#999999"></uni-icons>
					<!-- ⚠️ 为什么这里没有「立即沟通」按钮：
						 services/im.js 的 createConversation(jobId) 只接收 jobId，
						 服务端会以「当前登录用户 = 候选人」创建会话（求职者视角的接口），
						 HR 调它会把 HR 自己写成候选人，会话双方就错了。
						 因此企业端不做主动发起入口，只提示「等候选人先发起」。 -->
					<text class="chat-tip__text">HR 暂不能主动发起沟通：求职者在职位详情点「立即沟通」后，这里会出现会话入口</text>
				</view>
			</view>

			<!-- ---------- 面试邀约表单 ---------- -->
			<view v-if="invite.visible" class="sec sec--form">
				<zn-section-header title="发出面试邀约" subtitle="时间格式 YYYY-MM-DD HH:MM" />
				<view class="field-row">
					<view class="field field--half">
						<text class="field__label">第几轮</text>
						<input class="field__input" v-model="invite.roundNo" type="number" :maxlength="2" />
					</view>
					<view class="field field--half">
						<text class="field__label">轮次名称</text>
						<input class="field__input" v-model="invite.roundName" :maxlength="20" placeholder="如：一面" />
					</view>
				</view>
				<view class="chips">
					<view v-for="r in roundPresets" :key="r" class="chip" hover-class="zn-hover" @tap="invite.roundName = r">
						<text class="chip__text">{{ r }}</text>
					</view>
				</view>

				<view class="field-row">
					<view class="field field--half">
						<text class="field__label">日期</text>
						<picker mode="date" :value="invite.date" @change="onDateChange">
							<view class="field__picker">
								<text class="field__picker-text">{{ invite.date }}</text>
								<uni-icons type="arrow-down" :size="12" color="#999999"></uni-icons>
							</view>
						</picker>
					</view>
					<view class="field field--half">
						<text class="field__label">时间</text>
						<picker mode="time" :value="invite.time" @change="onTimeChange">
							<view class="field__picker">
								<text class="field__picker-text">{{ invite.time }}</text>
								<uni-icons type="arrow-down" :size="12" color="#999999"></uni-icons>
							</view>
						</picker>
					</view>
				</view>
				<text class="field__tip">提交时拼成「{{ inviteTime }}」，服务端严格校验该格式（错格式返回 40014）</text>

				<view class="field-row">
					<view class="field field--half">
						<text class="field__label">时长</text>
						<picker mode="selector" :range="durationLabels" :value="durationIndex" @change="onDurationChange">
							<view class="field__picker">
								<text class="field__picker-text">{{ invite.durationMin }} 分钟</text>
								<uni-icons type="arrow-down" :size="12" color="#999999"></uni-icons>
							</view>
						</picker>
					</view>
					<view class="field field--half">
						<text class="field__label">面试方式</text>
						<picker mode="selector" :range="modeLabels" :value="modeIndex" @change="onModeChange">
							<view class="field__picker">
								<text class="field__picker-text">{{ modeText }}</text>
								<uni-icons type="arrow-down" :size="12" color="#999999"></uni-icons>
							</view>
						</picker>
					</view>
				</view>

				<view class="field">
					<text class="field__label">面试地点</text>
					<input class="field__input" v-model="invite.address" :maxlength="160"
						placeholder="现场面试填写：如 北京市海淀区中关村大街 1 号 A 座 12 层" />
				</view>
				<view class="field">
					<text class="field__label">线上链接</text>
					<input class="field__input" v-model="invite.onlineLink" :maxlength="200"
						placeholder="视频/电话面试填写会议链接" />
				</view>
				<view class="field-row">
					<view class="field field--half">
						<text class="field__label">面试官</text>
						<input class="field__input" v-model="invite.interviewer" :maxlength="40" placeholder="如：王工" />
					</view>
					<view class="field field--half">
						<text class="field__label">联系方式</text>
						<input class="field__input" v-model="invite.contact" :maxlength="60" placeholder="如：138****0000" />
					</view>
				</view>
				<view class="field">
					<text class="field__label">备注</text>
					<input class="field__input" v-model="invite.remark" :maxlength="200"
						placeholder="给候选人的提示，如：请提前 10 分钟到达" />
				</view>
			</view>

			<view class="hrcand__gap"></view>
		</block>

		<!-- ==================== 四、底部操作条 ====================
			 ⚠️ 置灰只是体验优化：服务端状态机（schemas/hr.py 的 ALLOWED_TRANSITIONS）
			    会再拦一次，非法流转返回 409（code 40910），页面不该把置灰当权限。 -->
		<view v-if="!loading && !failed" class="bar">
			<view class="bar__btn" :class="{ 'is-off': !can('chatting') }" hover-class="zn-hover"
				@tap="openStatusPanel('chatting', '标记为沟通中')">
				<text class="bar__btn-text">沟通中</text>
			</view>
			<view class="bar__btn bar__btn--primary" :class="{ 'is-off': !can('interview') }" hover-class="zn-hover"
				@tap="toggleInvite">
				<text class="bar__btn-text bar__btn-text--on">发面试邀约</text>
			</view>
			<view class="bar__btn" :class="{ 'is-off': !can('passed') }" hover-class="zn-hover"
				@tap="openStatusPanel('passed', '面试通过')">
				<text class="bar__btn-text">面试通过</text>
			</view>
			<view class="bar__btn" :class="{ 'is-off': !can('hired') }" hover-class="zn-hover"
				@tap="openStatusPanel('hired', '已入职')">
				<text class="bar__btn-text">已入职</text>
			</view>
			<view class="bar__btn bar__btn--danger" :class="{ 'is-off': !can('rejected') }" hover-class="zn-hover"
				@tap="openStatusPanel('rejected', '不合适')">
				<text class="bar__btn-text bar__btn-text--danger">不合适</text>
			</view>
		</view>

		<!-- ==================== 五、状态变更小表单（备注 + 评分） ==================== -->
		<view v-if="statusPanel.visible" class="mask" @tap="statusPanel.visible = false">
			<view class="sheet" @tap.stop>
				<text class="sheet__title">{{ statusPanel.text }}</text>
				<text class="sheet__sub">备注与评分仅企业侧可见，候选人看不到</text>
				<view class="field field--sheet">
					<text class="field__label">备注</text>
					<input class="field__input" v-model="statusPanel.remark" :maxlength="200"
						placeholder="如：技术面表现良好，安排 HR 面" />
				</view>
				<view class="field field--sheet">
					<text class="field__label">评分</text>
					<view class="stars stars--lg">
						<view v-for="n in 5" :key="n" class="stars__item" hover-class="zn-hover"
							@tap="statusPanel.rating = n">
							<uni-icons :type="statusPanel.rating >= n ? 'star-filled' : 'star'" :size="24"
								:color="statusPanel.rating >= n ? '#ff8f1f' : '#dddddd'"></uni-icons>
						</view>
					</view>
				</view>
				<view class="sheet__actions">
					<view class="sheet__btn" hover-class="zn-hover" @tap="statusPanel.visible = false">
						<text class="sheet__btn-text">取消</text>
					</view>
					<view class="sheet__btn sheet__btn--primary" hover-class="zn-hover" @tap="confirmStatus">
						<text class="sheet__btn-text sheet__btn-text--on">确认{{ statusPanel.text }}</text>
					</view>
				</view>
			</view>
		</view>
	</view>
</template>

<script>
	/**
	 * 候选人详情（HR 查看简历 + 推进流程 + 发面试邀约）
	 *
	 * 接口：
	 *   GET  /hr/applications/{id}          getHrApplicationDetail
	 *   POST /hr/applications/{id}/status   updateApplicationStatus
	 *   POST /hr/applications/{id}/interview inviteInterview
	 *   GET  /chat/conversations?role=hr    getConversations（找候选人主动发起的会话）
	 *
	 * ⚠️ getHrApplicationDetail 有**写副作用**：首次调用会把投递从「待处理」推进为「已查看」
	 *    （server/app/routers/hr.py 的 read_application，有意的设计 —— 打开简历即已查看，
	 *     交给前端再发一个「标记已查看」请求的话，网络失败就会丢状态）。
	 *    因此：列表页绝不预加载详情，本页每次进入只调一次。
	 *    重复进入不会反复改写状态：只有 status 允许流转到 viewed 时才会推进。
	 *
	 * ⚠️ 状态机（与 server/app/schemas/hr.py 的 ALLOWED_TRANSITIONS 一致）：
	 *      submitted → viewed/chatting/rejected
	 *      viewed    → chatting/interview/rejected
	 *      chatting  → interview/rejected
	 *      interview → passed/rejected
	 *      passed    → hired/rejected
	 *      hired / rejected / withdrawn 为终态
	 *    「待面试 interview」不能直接调状态接口设置（服务端 40013），
	 *    必须走「发面试邀约」，以保证状态与邀约记录一致。
	 */
	import { getHrApplicationDetail, updateApplicationStatus, inviteInterview } from '@/services/hr.js'
	import { getConversations } from '@/services/im.js'
	import { padZero } from '@/common/utils/format.js'

	/** 合法流转表：仅用于按钮置灰，真正的校验在服务端 */
	const ALLOWED = {
		submitted: ['viewed', 'chatting', 'rejected'],
		viewed: ['chatting', 'interview', 'rejected'],
		chatting: ['interview', 'rejected'],
		interview: ['passed', 'rejected'],
		passed: ['hired', 'rejected'],
		hired: [],
		rejected: [],
		withdrawn: []
	}

	const TAG_TYPE = { success: 'green', warning: 'orange', danger: 'red', info: 'gray' }

	/** 面试时长候选（服务端要求 10~480） */
	const DURATIONS = [30, 45, 60, 90, 120]

	const MODES = [
		{ label: '现场面试', value: 'onsite' },
		{ label: '视频面试', value: 'video' },
		{ label: '电话面试', value: 'phone' }
	]

	const ROUND_PRESETS = ['一面', '二面', '三面', '技术面', 'HR面', '终面']

	/** 轮次序号 → 默认轮次名称 */
	const ROUND_NAME_BY_NO = { 1: '一面', 2: '二面', 3: '三面', 4: 'HR面', 5: '终面' }

	export default {
		data() {
			return {
				id: '',
				loading: true,
				ready: false,
				failed: false,
				failedMsg: '',
				submitting: false, // 状态变更 / 发面试邀约的防连点

				app: {},
				candidateDetail: null,
				interviews: [],
				conversation: null, // 候选人主动发起过沟通时的会话

				open: { edu: true, exp: true, proj: true, skill: true, adv: true },

				durationLabels: DURATIONS.map(d => d + ' 分钟'),
				modeLabels: MODES.map(m => m.label),
				roundPresets: ROUND_PRESETS,

				statusPanel: { visible: false, target: '', text: '', remark: '', rating: 0 },

				invite: {
					visible: false,
					roundNo: '1',
					roundName: '一面',
					date: '',
					time: '10:00',
					durationMin: 60,
					mode: 'onsite',
					address: '',
					onlineLink: '',
					interviewer: '',
					contact: '',
					remark: ''
				}
			}
		},
		computed: {
			cand() {
				return this.app.candidate || {}
			},
			detail() {
				return this.candidateDetail || {}
			},
			heroMeta() {
				const c = this.cand
				return [
					c.genderText,
					c.age ? c.age + '岁' : '',
					c.educationLevel,
					c.workYearsText,
					c.school
				].filter(Boolean).join(' · ') || '简历信息待完善'
			},
			current() {
				return this.app.status || ''
			},
			/** 提交给服务端的面试时间字符串：必须是 'YYYY-MM-DD HH:MM' */
			inviteTime() {
				return this.invite.date && this.invite.time
					? this.invite.date + ' ' + this.invite.time
					: ''
			},
			durationIndex() {
				const i = DURATIONS.indexOf(Number(this.invite.durationMin))
				return i < 0 ? 0 : i
			},
			modeIndex() {
				const i = MODES.findIndex(m => m.value === this.invite.mode)
				return i < 0 ? 0 : i
			},
			modeText() {
				const hit = MODES.find(m => m.value === this.invite.mode)
				return hit ? hit.label : '现场面试'
			}
		},
		onLoad(options) {
			this.id = (options && options.id) || ''
			if (!this.id) {
				this.failed = true
				this.failedMsg = '缺少投递 id，请从「收到简历」列表进入'
				this.loading = false
				return
			}
			this.load()
		},
		methods: {
			/* ================= 数据 ================= */
			async load() {
				this.loading = !this.ready
				this.failed = false
				try {
					const res = await getHrApplicationDetail(this.id)
					this.app = (res && res.application) || {}
					this.candidateDetail = this.app.candidateDetail || null
					this.interviews = this.app.interviews || []
					this.prefillInvite()
					this.findConversation()
				} catch (e) {
					if (this.handleUnbound(e)) return
					this.failed = true
					this.failedMsg = (e && e.message) || '请检查服务端是否已启动'
				} finally {
					this.loading = false
					this.ready = true
				}
			},
			handleUnbound(err) {
				if (!err || (err.code !== 40301 && err.status !== 403)) return false
				uni.reLaunch({ url: '/pages/hr/bind' })
				return true
			},
			/**
			 * 找「候选人主动发起过」的会话
			 * ⚠️ 匹配口径：会话行的 jobId 相同，且对方用户 id 与本投递的 candidateId 相同。
			 *    （services/im.js 的 JSDoc 没列 contactId，但接口实际会返回它 —— 实测确认；
			 *      老环境若没有 contactId，退化为「同一职位 + 姓名相同」，宁可漏也不误配。）
			 * ⚠️ 失败静默处理：这个入口是加分项，取不到就只显示「HR 不能主动发起」的提示，
			 *    不该因为它把整页简历详情变成失败态。
			 */
			async findConversation() {
				this.conversation = null
				try {
					const res = await getConversations({ role: 'hr', page: 1, pageSize: 50 })
					const list = (res && res.list) || []
					const uid = this.app.candidateId
					const name = this.cand.name || ''
					const hit = list.find(c => {
						if (c.jobId !== this.app.jobId) return false
						if (uid && c.contactId) return String(c.contactId) === String(uid)
						return !!name && c.contactName === name
					})
					this.conversation = hit || null
				} catch (e) {
					this.conversation = null
				}
			},

			/* ================= 面试邀约表单 ================= */
			/** 默认值：轮次取已有邀约的下一轮；时间取「两小时后」（跨天则顺延到次日 10:00） */
			prefillInvite() {
				const maxRound = this.interviews.reduce((m, it) => Math.max(m, Number(it.roundNo) || 0), 0)
				const nextNo = Math.min(10, maxRound + 1)
				this.invite.roundNo = String(nextNo)
				this.invite.roundName = ROUND_NAME_BY_NO[nextNo] || ('第' + nextNo + '轮')

				const d = new Date()
				d.setMinutes(0, 0, 0)
				d.setHours(d.getHours() + 2)
				if (d.getHours() >= 22) {
					d.setDate(d.getDate() + 1)
					d.setHours(10, 0, 0, 0)
				}
				this.invite.date = d.getFullYear() + '-' + padZero(d.getMonth() + 1) + '-' + padZero(d.getDate())
				this.invite.time = padZero(d.getHours()) + ':' + padZero(d.getMinutes())
			},
			toggleInvite() {
				if (!this.can('interview')) {
					uni.showToast({ title: this.blockedTip('interview'), icon: 'none' })
					return
				}
				this.invite.visible = !this.invite.visible
			},
			onDateChange(e) {
				this.invite.date = e.detail.value
			},
			onTimeChange(e) {
				this.invite.time = e.detail.value
			},
			onDurationChange(e) {
				this.invite.durationMin = DURATIONS[Number(e.detail.value)]
			},
			onModeChange(e) {
				this.invite.mode = MODES[Number(e.detail.value)].value
			},
			async submitInvite() {
				if (this.submitting) return
				const inv = this.invite
				const roundNo = Number(inv.roundNo)
				if (!(roundNo >= 1 && roundNo <= 10)) {
					uni.showToast({ title: '轮次需在 1~10 之间', icon: 'none' })
					return
				}
				if (!inv.roundName.trim()) {
					uni.showToast({ title: '请填写轮次名称', icon: 'none' })
					return
				}
				// 格式必须与服务端 strptime('%Y-%m-%d %H:%M') 完全一致，否则 40014
				if (!/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}$/.test(this.inviteTime)) {
					uni.showToast({ title: '请选择面试日期与时间', icon: 'none' })
					return
				}
				this.submitting = true
				try {
					await inviteInterview(this.id, {
						roundNo,
						roundName: inv.roundName.trim(),
						interviewTime: this.inviteTime,
						durationMin: Number(inv.durationMin),
						mode: inv.mode,
						address: inv.address.trim(),
						onlineLink: inv.onlineLink.trim(),
						interviewer: inv.interviewer.trim(),
						contact: inv.contact.trim(),
						remark: inv.remark.trim()
					})
					uni.showToast({ title: '面试邀约已发出', icon: 'none' })
					this.invite.visible = false
					// 重新拉一次：状态会变「待面试」，并出现新的邀约记录
					await this.load()
				} catch (e) {
					if (this.handleUnbound(e)) return
					// 40911（已终态）等错误由 services/api.js 弹出服务端原文
				} finally {
					this.submitting = false
				}
			},

			/* ================= 状态流转 ================= */
			can(target) {
				return (ALLOWED[this.current] || []).indexOf(target) > -1
			},
			/** 置灰时给出可读原因，而不是让 HR 对着灰按钮猜 */
			blockedTip(target) {
				if (this.current === target) return '当前已是该状态'
				if (!this.current) return '投递状态未知，请重新加载'
				if (this.current === 'hired') return '该候选人已入职，流程已结束'
				if (this.current === 'rejected') return '该候选人已被标记不合适'
				if (this.current === 'withdrawn') return '候选人已撤回投递，无法继续推进'
				if (target === 'interview') return '当前状态不能直接发面试邀约，请先「标记为沟通中」'
				return '当前状态不允许变更为该状态'
			},
			openStatusPanel(target, text) {
				if (!this.can(target)) {
					uni.showToast({ title: this.blockedTip(target), icon: 'none' })
					return
				}
				this.statusPanel = {
					visible: true,
					target,
					text,
					remark: this.app.hrRemark || '',
					rating: this.app.hrRating || 0
				}
			},
			async confirmStatus() {
				if (this.submitting) return
				this.submitting = true
				const panel = this.statusPanel
				try {
					await updateApplicationStatus(this.id, {
						status: panel.target,
						remark: (panel.remark || '').trim(),
						rating: Number(panel.rating) || 0
					})
					this.statusPanel.visible = false
					uni.showToast({ title: '已更新为「' + panel.text + '」', icon: 'none' })
					await this.load()
				} catch (e) {
					if (this.handleUnbound(e)) return
					// 40910（状态机拒绝）等错误已由 services/api.js 弹出服务端原文
				} finally {
					this.submitting = false
				}
			},

			/* ================= 展示 / 跳转 ================= */
			toggle(key) {
				this.open[key] = !this.open[key]
			},
			period(start, end) {
				// 起止时间可能是 '2021-07' 或 '2021-07-01'，原样展示即可，不解析
				const a = start || ''
				const b = end || ''
				if (!a && !b) return ''
				return a + ' ~ ' + (b || '至今')
			},
			tagType(type) {
				return TAG_TYPE[type] || 'gray'
			},
			goChat() {
				if (!this.conversation) return
				uni.navigateTo({
					url: '/pages/chat/chat?id=' + this.conversation.id + '&role=hr',
					fail: () => uni.showToast({ title: '会话打开失败', icon: 'none' })
				})
			}
		}
	}
</script>

<style lang="scss" scoped>
	.hrcand {
		padding-bottom: 200rpx; /* 底部固定操作条 */
	}

	.hrcand__state {
		padding: 160rpx 0;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.hrcand__state-text {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
	}

	.hrcand__gap {
		height: 40rpx;
	}

	/* ---------------- 候选人头部 ---------------- */
	.hero {
		margin: $zn-gap $zn-page-padding 0;
		padding: $zn-gap-lg $zn-gap;
		border-radius: $zn-radius-lg;
		background: $zn-gradient;
		display: flex;
		flex-direction: row;
		align-items: center;
		box-shadow: $zn-shadow-theme;
	}

	.hero__main {
		flex: 1;
		min-width: 0;
		margin-left: $zn-gap;
		display: flex;
		flex-direction: column;
	}

	.hero__row {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.hero__name {
		max-width: 280rpx;
		font-size: $zn-font-lg;
		font-weight: 700;
		color: #ffffff;
		margin-right: 12rpx;
	}

	.hero__meta {
		margin-top: 10rpx;
		font-size: $zn-font-xs;
		color: rgba(255, 255, 255, 0.9);
	}

	.hero__progress {
		margin-top: 16rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.hero__progress-label {
		flex-shrink: 0;
		margin-right: 12rpx;
		font-size: $zn-font-xs;
		color: rgba(255, 255, 255, 0.9);
	}

	.hero__progress-bar {
		flex: 1;
		min-width: 0;
	}

	/* ---------------- 分区 ---------------- */
	.sec {
		margin: $zn-gap-sm $zn-page-padding 0;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: 0 $zn-gap $zn-gap;
	}

	.sec--form {
		border: 2rpx solid $zn-theme-light;
	}

	/* ---------------- 键值行 ---------------- */
	.kv {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 12rpx 0;

		&--block {
			align-items: flex-start;
		}
	}

	.kv__k {
		width: 170rpx;
		flex-shrink: 0;
		font-size: $zn-font-sm;
		color: $zn-text-grey;
	}

	.kv__v {
		flex: 1;
		min-width: 0;
		font-size: $zn-font-sm;
		color: $zn-text-main;

		&--text {
			line-height: 42rpx;
		}

		&--warn {
			color: $zn-orange;
		}
	}

	/* ---------------- 经历条目 ---------------- */
	.item {
		padding: $zn-gap-sm 0;
		border-top: 1rpx solid $zn-line;
		display: flex;
		flex-direction: column;
	}

	.item__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.item__title {
		flex: 1;
		min-width: 0;
		font-size: $zn-font;
		font-weight: 600;
		color: $zn-text-title;
	}

	.item__time {
		flex-shrink: 0;
		margin-left: 12rpx;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	.item__sub {
		margin-top: 6rpx;
		font-size: $zn-font-sm;
		color: $zn-text-sub;
	}

	.item__desc {
		margin-top: 10rpx;
		font-size: $zn-font-sm;
		color: $zn-text-sub;
		line-height: 42rpx;
	}

	.item__points {
		margin-top: 8rpx;
		display: flex;
		flex-direction: column;
	}

	.item__point {
		font-size: $zn-font-sm;
		color: $zn-text-sub;
		line-height: 42rpx;
	}

	.para {
		font-size: $zn-font-sm;
		color: $zn-text-sub;
		line-height: 44rpx;
	}

	/* ---------------- 技能芯片 ---------------- */
	.chips {
		margin-top: 12rpx;
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
	}

	.chip {
		margin: 0 12rpx 12rpx 0;
		height: 56rpx;
		padding: 0 22rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-theme-light;
		font-size: $zn-font-xs;
		color: $zn-theme-deep;
		line-height: 56rpx;
	}

	/* ---------------- 面试邀约记录 ---------------- */
	.ivs {
		display: flex;
		flex-direction: column;
	}

	.iv {
		padding: $zn-gap-sm 0;
		border-top: 1rpx solid $zn-line;
	}

	.iv__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-bottom: 6rpx;
	}

	.iv__round {
		font-size: $zn-font;
		font-weight: 600;
		color: $zn-text-title;
		margin-right: 12rpx;
	}

	/* ---------------- 星级 ---------------- */
	.stars {
		flex: 1;
		display: flex;
		flex-direction: row;
		align-items: center;

		&--lg {
			margin-top: 8rpx;
		}
	}

	.stars__item {
		width: 64rpx;
		height: 64rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	/* ---------------- 沟通入口 ---------------- */
	.chat-entry {
		padding: $zn-gap-sm;
		border-radius: $zn-radius;
		background-color: $zn-theme-lighter;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.chat-entry__main {
		flex: 1;
		min-width: 0;
		margin-left: 12rpx;
		display: flex;
		flex-direction: column;
	}

	.chat-entry__title {
		font-size: $zn-font-sm;
		font-weight: 600;
		color: $zn-theme-dark;
	}

	.chat-entry__sub {
		margin-top: 4rpx;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
	}

	.chat-tip {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
	}

	.chat-tip__text {
		flex: 1;
		min-width: 0;
		margin-left: 10rpx;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
		line-height: 38rpx;
	}

	/* ---------------- 表单 ---------------- */
	.field {
		margin-top: $zn-gap-sm;
	}

	.field--half {
		width: 48%;
	}

	.field--sheet {
		margin-top: $zn-gap;
	}

	.field-row {
		display: flex;
		flex-direction: row;
		justify-content: space-between;
	}

	.field__label {
		font-size: $zn-font-sm;
		color: $zn-text-sub;
	}

	.field__input {
		margin-top: 12rpx;
		height: 84rpx;
		padding: 0 $zn-gap-sm;
		border-radius: $zn-radius;
		background-color: $zn-bg-grey;
		font-size: $zn-font-sm;
		color: $zn-text-main;
	}

	.field__picker {
		margin-top: 12rpx;
		height: 84rpx;
		padding: 0 $zn-gap-sm;
		border-radius: $zn-radius;
		background-color: $zn-bg-grey;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.field__picker-text {
		flex: 1;
		min-width: 0;
		font-size: $zn-font-sm;
		color: $zn-text-main;
	}

	.field__tip {
		display: block;
		margin-top: 10rpx;
		font-size: $zn-font-xs;
		color: $zn-theme-deep;
	}

	/* ---------------- 底部操作条 ---------------- */
	.bar {
		position: fixed;
		left: 0;
		right: 0;
		bottom: 0;
		padding: $zn-gap-sm $zn-gap-sm calc(#{$zn-gap-sm} + env(safe-area-inset-bottom));
		background-color: $zn-bg-card;
		box-shadow: 0 -4rpx 16rpx rgba(20, 40, 30, 0.06);
		display: flex;
		flex-direction: row;
		align-items: center;
		z-index: 30;
	}

	.bar__btn {
		flex: 1;
		height: 80rpx;
		margin-right: 10rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		display: flex;
		align-items: center;
		justify-content: center;

		&:last-child {
			margin-right: 0;
		}

		&.is-off {
			opacity: 0.45;
		}

		&--primary {
			background: $zn-gradient;
		}

		&--danger {
			background-color: #fff0f0;
		}
	}

	.bar__btn-text {
		font-size: $zn-font-xs;
		color: $zn-text-sub;

		&--on {
			color: #ffffff;
			font-weight: 600;
		}

		&--danger {
			color: $zn-red;
		}
	}

	/* ---------------- 底部弹层 ---------------- */
	.mask {
		position: fixed;
		left: 0;
		right: 0;
		top: 0;
		bottom: 0;
		background-color: $zn-mask;
		z-index: 40;
		display: flex;
		flex-direction: column;
		justify-content: flex-end;
	}

	.sheet {
		background-color: $zn-bg-card;
		border-top-left-radius: $zn-radius-xl;
		border-top-right-radius: $zn-radius-xl;
		padding: $zn-gap-lg $zn-page-padding calc(#{$zn-gap-lg} + env(safe-area-inset-bottom));
		display: flex;
		flex-direction: column;
	}

	.sheet__title {
		font-size: $zn-font-lg;
		font-weight: 700;
		color: $zn-text-title;
	}

	.sheet__sub {
		margin-top: 8rpx;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	.sheet__actions {
		margin-top: $zn-gap-lg;
		display: flex;
		flex-direction: row;
	}

	.sheet__btn {
		flex: 1;
		height: 88rpx;
		margin-right: $zn-gap-sm;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		display: flex;
		align-items: center;
		justify-content: center;

		&:last-child {
			margin-right: 0;
		}

		&--primary {
			background: $zn-gradient;
		}
	}

	.sheet__btn-text {
		font-size: $zn-font;
		font-weight: 600;
		color: $zn-text-sub;

		&--on {
			color: #ffffff;
		}
	}
</style>
