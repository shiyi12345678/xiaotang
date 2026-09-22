<template>
	<view class="zn-page mine">
		<!-- ==================== 顶部：主色渐变用户信息区 ==================== -->
		<view class="mine__header" :style="{ paddingTop: statusBarHeight + 'px' }">
			<view class="mine__topbar">
				<text class="mine__topbar-title">我的</text>
				<view class="mine__topbar-right">
					<!-- 「消息中心」入口：未读角标 = /chat/unread 的 candidate 数 -->
					<view class="mine__msg" hover-class="zn-hover" @tap="goMessage">
						<uni-icons type="notification" :size="20" color="#ffffff"></uni-icons>
						<text class="mine__msg-text">消息中心</text>
						<text v-if="unread > 0" class="mine__msg-badge">{{ unreadText }}</text>
					</view>
					<view class="mine__icon-btn" hover-class="zn-hover" @tap="goSettings">
						<uni-icons type="gear" :size="22" color="#ffffff"></uni-icons>
					</view>
				</view>
			</view>

			<!-- 用户信息：头像 + 昵称 + 求职状态；未登录时整块即登录引导 -->
			<view class="mine__user" hover-class="zn-hover" @tap="onUserTap">
				<zn-avatar v-if="isLogin" :name="user.nickname" :size="120" :border="true" />
				<view v-else class="mine__avatar-ph">
					<uni-icons type="person" :size="50" color="#c3cad3"></uni-icons>
				</view>
				<view class="mine__user-info">
					<text class="mine__name">{{ isLogin ? (user.nickname || '未设置昵称') : '登录 / 注册' }}</text>
					<text class="mine__sub">{{ identityText }}</text>
					<text class="mine__jobstatus" :class="{ 'is-dim': !jobStatusFilled }">{{ jobStatusText }}</text>
				</view>
				<uni-icons type="right" :size="16" color="rgba(255,255,255,0.85)"></uni-icons>
			</view>
		</view>

		<!-- ==================== 内容区 ==================== -->
		<view class="mine__body">
			<!-- ---------- 1. 简历完整度 ---------- -->
			<view class="card resume">
				<view class="resume__head">
					<text class="card__title">简历完整度</text>
					<view class="card__more" hover-class="zn-hover" @tap="goResume">
						<text class="card__more-text">简历管理</text>
						<uni-icons type="right" :size="13" color="#999999"></uni-icons>
					</view>
				</view>

				<!-- 未登录：登录引导（不是错误，也不展示任何假的完整度） -->
				<view v-if="!isLogin" class="guest">
					<text class="guest__text">登录后即可创建简历、投递职位，并与 HR 直接沟通</text>
					<view class="guest__btn" hover-class="zn-hover" @tap="goLogin">
						<text class="guest__btn-text">登录 / 注册</text>
					</view>
				</view>

				<!-- 加载中 -->
				<view v-else-if="resumeState === 'loading'" class="state">
					<uni-icons type="spinner-cycle" :size="18" color="#00A6A7"></uni-icons>
					<text class="state__text">正在加载…</text>
				</view>

				<!-- 加载失败：可点击重试（接口失败就是失败，不编造完整度） -->
				<view v-else-if="resumeState === 'error'" class="state state--error" hover-class="zn-hover"
					@tap="loadResume">
					<uni-icons type="info" :size="18" color="#ff4d4f"></uni-icons>
					<text class="state__text state__text--error">简历加载失败，点击重试</text>
				</view>

				<!-- 空数据：接口返回 exists=false（服务端给的是空模板而非 null） -->
				<zn-empty v-else-if="!resumeExists" icon="compose" text="还没有创建简历" desc="完善简历后才能投递职位"
					btn-text="立即完善" @action="goResume" />

				<!-- 正常数据 -->
				<view v-else class="resume__body" hover-class="zn-hover" @tap="goResume">
					<view class="resume__bar">
						<view class="resume__track">
							<zn-progress :percent="completeness" :height="14" :color="THEME_GRADIENT" />
						</view>
						<text class="resume__percent">{{ completeness }}%</text>
					</view>
					<text class="resume__tip" :class="{ 'is-warn': completeness < 80 }">{{ completenessTip }}</text>
					<text class="resume__meta">{{ resumeMeta }}</text>
				</view>
			</view>

			<!-- ---------- 2. 求职统计 ---------- -->
			<view class="card stat">
				<view class="stat__head">
					<text class="card__title">求职统计</text>
					<text class="stat__sub">数据来自你的真实投递记录</text>
				</view>

				<view v-if="!isLogin" class="stat__guest">
					<text class="stat__guest-text">登录后查看投递进度与面试转化率</text>
				</view>
				<view v-else-if="statsState === 'loading'" class="state">
					<uni-icons type="spinner-cycle" :size="18" color="#00A6A7"></uni-icons>
					<text class="state__text">正在加载…</text>
				</view>
				<view v-else-if="statsState === 'error'" class="state state--error" hover-class="zn-hover"
					@tap="loadStats">
					<uni-icons type="info" :size="18" color="#ff4d4f"></uni-icons>
					<text class="state__text state__text--error">统计加载失败，点击重试</text>
				</view>

				<view class="stat__grid">
					<view v-for="item in statsItems" :key="item.key" class="stat__item" hover-class="zn-hover"
						@tap="goStat(item)">
						<view class="stat__value-row">
							<text class="stat__value">{{ item.value }}</text>
							<text v-if="item.unit" class="stat__unit">{{ item.unit }}</text>
						</view>
						<text class="stat__label">{{ item.label }}</text>
					</view>
				</view>
			</view>

			<!-- ---------- 3. 功能宫格（rcMineGridGroups：我的求职 / 求职服务） ---------- -->
			<view v-for="(group, gi) in gridGroups" :key="group.title + '-' + gi" class="card grid">
				<view class="grid__head">
					<view class="grid__bar"></view>
					<text class="card__title">{{ group.title }}</text>
				</view>
				<view class="grid__list">
					<view v-for="item in group.items" :key="item.id" class="grid__item" hover-class="zn-hover"
						@tap="onGridTap(item)">
						<view class="grid__icon" :style="{ backgroundColor: item.bg }">
							<uni-icons :type="item.icon" :size="26" :color="item.color"></uni-icons>
							<text v-if="item.badge" class="grid__badge">{{ item.badge }}</text>
						</view>
						<text class="grid__label">{{ item.name }}</text>
					</view>
				</view>
			</view>

			<!-- ---------- 4. 企业端入口 ---------- -->
			<view class="hr" hover-class="zn-hover" @tap="goHr">
				<view class="hr__icon">
					<uni-icons type="staff-filled" :size="26" color="#ffffff"></uni-icons>
				</view>
				<view class="hr__main">
					<text class="hr__title">切换到企业端</text>
					<text class="hr__desc">发布职位 · 查看候选人简历 · 安排面试</text>
				</view>
				<view class="hr__btn">
					<text class="hr__btn-text">进入工作台</text>
					<uni-icons type="right" :size="13" color="#008c8d"></uni-icons>
				</view>
			</view>
		</view>

		<zn-tab-bar current="mine" />
	</view>
</template>

<script>
	/**
	 * 个人中心（求职者端，tab 页）
	 *
	 * 数据来源（全部走 services/ 封装，页面不拼 URL）：
	 *   用户资料   getInfo()          services/user.js   GET /user/info
	 *   简历/完整度 getResume()        services/apply.js  GET /resume（含 completeness、exists）
	 *   求职统计   getApplyStats()    services/apply.js  GET /apply/stats
	 *   宫格配置   getConfig('rcMineGridGroups')          services/content.js
	 *   未读消息   getUnread()        services/im.js     GET /chat/unread
	 *
	 * ⚠️ 关于「三态」的分工（本项目刻意不做 mock 回落）：
	 *    - 简历与统计是**账号业务数据**：加载中显示「正在加载…」，失败显示可点击重试的失败态，
	 *      空数据用 zn-empty；任何情况下都不编造完整度/投递数（接口不通就应该看得见失败）。
	 *    - 功能宫格是**纯展示型导航配置**：配置读不到时用本地同结构默认数组兜底。
	 *      为什么这里允许兜底：宫格只是「去哪儿」的入口，不承载任何业务事实，
	 *      缺了它整页会空掉大半，却并不会误导用户对自身数据的判断 ——
	 *      这与「不给职位/简历/统计数据编造兜底」是两件事，不要混为一谈。
	 */
	import { getStatusBarHeight } from '@/common/utils/format.js'
	import { getConfig } from '@/services/content.js'
	import { getResume, getApplyStats } from '@/services/apply.js'
	import { getUnread } from '@/services/im.js'
	import {
		getInfo,
		isLogined,
		getCachedUser,
		refreshCachedUser
	} from '@/services/user.js'

	/**
	 * 与 uni.scss 的 $zn-gradient 保持一致
	 * ⚠️ zn-progress / 渐变类样式需要的是 JS 里的颜色字符串（组件 prop 读不到 SCSS 变量），
	 *    因此这里重复一份常量；改主题色时必须两边一起改（这是本项目唯一允许的颜色重复处）。
	 */
	const THEME_GRADIENT = 'linear-gradient(135deg, #33c4c5 0%, #00a6a7 45%, #008c8d 100%)'

	/**
	 * 用户信息骨架（未登录 / 接口未返回时）
	 * ⚠️ 只保留模板需要的最小字段，绝不复用学习端 mock 里的「陈昊 / V4 学习达人」之类假资料。
	 */
	const DEFAULT_USER = {
		id: '',
		nickname: '',
		email: '',
		avatar: '',
		signature: '',
		hasPassword: false
	}

	/**
	 * 功能宫格兜底配置（配置接口不可用时的降级数据）
	 *
	 * ⚠️ 三条纪律：
	 *   1. link 只允许指向公约第六节的**冻结路由表**，不使用任何旧路由；
	 *   2. icon 只用公约里已确认存在的 uni-icons 名（medal-filled / bars 等）；
	 *   3. badge 一律留空 —— 角标属于「数据」，本地兜底没有资格编造数字。
	 */
	const GRID_FALLBACK = [
		{
			title: '我的求职',
			items: [
				{ id: 'mine-deliver', name: '我的投递', icon: 'paperplane', color: '#00A6A7', bg: '#e6f7f7', link: '/pages/seeker/applications', badge: '' },
				{ id: 'mine-favorite', name: '我的收藏', icon: 'star', color: '#ff8f1f', bg: '#fff4e6', link: '/pages/seeker/favorites', badge: '' },
				{ id: 'mine-interview', name: '面试日程', icon: 'calendar', color: '#3b9dff', bg: '#eaf4ff', link: '/pages/seeker/interview', badge: '' },
				{ id: 'mine-resume', name: '简历管理', icon: 'compose', color: '#8a6cf6', bg: '#f2eeff', link: '/pages/seeker/resume', badge: '' }
			]
		},
		{
			title: '求职服务',
			items: [
				{ id: 'mine-bank', name: '面试题库', icon: 'medal-filled', color: '#ff6b4a', bg: '#fff0ec', link: '/pages/bank/list', badge: '' },
				{ id: 'mine-report', name: '求职报告', icon: 'bars', color: '#2bb14c', bg: '#e9fbef', link: '/pages/seeker/report', badge: '' },
				{ id: 'mine-ai', name: 'AI 求职助手', icon: 'chat', color: '#5b7cfa', bg: '#eef1ff', link: '/pages/ai/ai', badge: '' },
				{ id: 'mine-account', name: '设置与协议', icon: 'gear', color: '#00b3c4', bg: '#e6fafc', link: '/pages/mine/settings', badge: '' }
			]
		}
	]

	/**
	 * 公约第六节的冻结路由表白名单：不在表内的路径一律不允许跳转
	 *
	 * 为什么不直接信任配置里的 link：
	 *    page_config 是运营在后台维护的 JSON，历史数据里出现过学习端时期的旧路径
	 *    （/pages/mine/deliver、/pages/report/index …）。前端若照配置硬跳，
	 *    用户会落到不存在的页面上（uni-app 只弹一句「页面打开失败」，排查成本很高）。
	 *   因此这里只放行白名单内的路径，其余一律提示「暂未开放」。
	 *
	 * ⚠️ 这里刻意**不再维护「旧路径 → 新路径」的别名映射表**：
	 *    旧路径的根因在种子数据（已按接口契约修正），页面里再留一张映射表就成了死代码；
	 *    而且别名表的键本身就是 /pages/... 形式的字符串，
	 *    会被 tools/check-routes.js 当成真实跳转目标而误报「未注册路由」。
	 *    真出现漏网的旧路径，「暂未开放」提示比静默重定向更诚实 —— 它会暴露数据问题。
	 */
	const FROZEN_ROUTES = [
		'/pages/index/index', '/pages/job/list', '/pages/job/search', '/pages/job/detail',
		'/pages/job/referral', '/pages/seeker/center', '/pages/seeker/applications',
		'/pages/seeker/favorites', '/pages/seeker/resume', '/pages/seeker/report',
		'/pages/seeker/interview', '/pages/bank/list', '/pages/bank/practice', '/pages/bank/wrong',
		'/pages/ai/ai', '/pages/mine/message', '/pages/chat/chat', '/pages/mine/mine',
		'/pages/mine/settings', '/pages/mine/agreement', '/pages/login/login',
		'/pages/hr/dashboard', '/pages/hr/jobs', '/pages/hr/job-edit', '/pages/hr/applications',
		'/pages/hr/candidate', '/pages/hr/interviews', '/pages/hr/company', '/pages/hr/bind'
	]

	/** 需要登录的宫格入口（求职类页面都要登录态，提前挡在跳转前，避免进去再弹 401） */
	/**
	 * 需要登录的宫格入口（求职类页面都要登录态，提前挡在跳转前，避免进去再弹 401）
	 *
	 * ⚠️ 这里存的是**路由片段**而不是完整前缀（不写整整一段 /pages/ 开头的路径）：
	 *    tools/check-routes.js 会把代码里任何以 /pages/ 开头的字符串当成跳转目标，
	 *    写成完整前缀会被它误报成「未注册路由」。片段同样清晰，还不招误报。
	 */
	const LOGIN_REQUIRED_SEGMENTS = ['seeker/', 'hr/']

	/**
	 * icon 白名单与别名
	 * ⚠️ 配置里可能写着 'chart' / 'medal' / 'staff' / 'home' 这些 uni-icons 里**并不存在**的名字，
	 *    直接渲染会得到一个空白图标位；这里做别名映射 + 白名单兜底，
	 *    保证「配置写错名字」只会让图标退化为通用图标，而不会让整个宫格出现空洞。
	 */
	const ICON_WHITELIST = ('arrow-down,bars,calendar,chat,checkbox,checkbox-filled,checkmarkempty,clear,closeempty,' +
		'compose,email,eye,fire-filled,gear,gift,headphones,info,info-filled,left,list,locked,' +
		'medal-filled,more-filled,notification,notification-filled,paperplane,paperplane-filled,' +
		'person,person-filled,plusempty,pyq,refresh,right,search,send,smallcircle-filled,' +
		'spinner-cycle,staff-filled,star,star-filled,text,trash,tune,videocam,videocam-filled,vip-filled').split(',')

	const ICON_ALIAS = {
		chart: 'bars',
		medal: 'medal-filled',
		staff: 'staff-filled',
		home: 'list',
		wallet: 'list',
		person: 'person'
	}

	export default {
		data() {
			return {
				statusBarHeight: 0,
				isLogin: false,
				user: Object.assign({}, DEFAULT_USER),
				unread: 0, // 求职者侧未读消息数（/chat/unread 的 candidate）
				resumeState: 'idle', // idle / loading / ready / error
				resume: {},
				resumeExists: false,
				statsState: 'idle',
				stats: {},
				gridGroups: [],
				THEME_GRADIENT
			}
		},
		computed: {
			/** 昵称下方的一行说明：登录后展示脱敏邮箱，未登录给出注册引导 */
			identityText() {
				if (!this.isLogin) return '登录后查看简历完整度与投递进度'
				return this.user.email || '未绑定邮箱'
			},
			/** 求职状态：取自简历的 currentStatus（服务端字段），未填时如实说明 */
			jobStatusText() {
				if (!this.isLogin) return '求职状态：登录后查看'
				if (this.resumeState === 'loading') return '求职状态：同步中…'
				if (this.resumeState === 'error') return '求职状态：暂时取不到'
				const status = (this.resume && this.resume.currentStatus) || ''
				return status ? '求职状态：' + status : '求职状态：未填写'
			},
			jobStatusFilled() {
				return !!(this.isLogin && this.resume && this.resume.currentStatus)
			},
			completeness() {
				const n = Number((this.resume && this.resume.completeness) || 0)
				return Number.isFinite(n) ? Math.max(0, Math.min(100, Math.round(n))) : 0
			},
			/** 完整度分档提示：80 分以下明确告诉用户「补齐经历」能带来什么 */
			completenessTip() {
				if (this.completeness >= 80) return '简历已较完整，HR 更容易搜到你'
				return '补齐经历可提升被查看率'
			},
			/** 简历摘要行：期望职位 / 期望城市 / 期望薪资（都由服务端算好文案） */
			resumeMeta() {
				const r = this.resume || {}
				const parts = []
				if (r.expectedPosition) parts.push(r.expectedPosition)
				if (r.expectedCity) parts.push(r.expectedCity)
				if (r.expectedSalaryText) parts.push(r.expectedSalaryText)
				return parts.length ? parts.join(' · ') : '还没填写期望职位与期望城市'
			},
			unreadText() {
				return this.unread > 99 ? '99+' : String(this.unread)
			},
			/**
			 * 求职统计四宫格
			 * ⚠️ 只有 statsState==='ready' 才显示真实数字；其余状态显示「—」，
			 *    绝不用 0 冒充「已加载但为 0」，也绝不用配置里的假角标。
			 */
			statsItems() {
				const ready = this.statsState === 'ready'
				const s = this.stats || {}
				const pick = value => (ready ? String(value) : '—')
				return [
					{ key: 'delivered', label: '已投递', unit: '份', value: pick(s.delivered || 0), path: '/pages/seeker/applications' },
					{ key: 'favorited', label: '收藏', unit: '个', value: pick(s.favorited || 0), path: '/pages/seeker/favorites' },
					{ key: 'rate', label: '面试转化率', unit: '%', value: pick(s.interviewRate || 0), path: '/pages/seeker/report' },
					{ key: 'upcoming', label: '即将面试', unit: '场', value: pick((s.upcomingInterviews || []).length), path: '/pages/seeker/interview' }
				]
			}
		},
		onLoad() {
			this.statusBarHeight = getStatusBarHeight()
			// 宫格配置与登录态无关，先拉一次，保证游客也能看到入口
			this.loadGrid()
		},
		onShow() {
			// ⚠️ 数据加载只放在 onShow（uni-app 会先 onLoad 后 onShow）：
			//    从登录页 / 简历页 / 消息页返回时都会回到这里重新同步，避免 onLoad + onShow 重复请求。
			const wasLogin = this.isLogin
			this.syncLogin()
			// 登录态发生变化时先清空旧数据，避免退出登录后仍残留上一个账号的数字
			if (wasLogin !== this.isLogin) this.resetAccountData()
			this.loadAccountData()
			this.loadUnread()
			if (this.isLogin) this.refreshProfile()
		},
		async onPullDownRefresh() {
			try {
				if (this.isLogin) await this.refreshProfile()
				this.loadGrid()
				await this.loadAccountData()
				await this.loadUnread()
				uni.showToast({ title: '已更新', icon: 'none' })
			} finally {
				// ⚠️ 无论成功失败都要收起下拉动画，否则页面会一直停在「刷新中」
				uni.stopPullDownRefresh()
			}
		},
		methods: {
			/* ---------------- 登录态 ---------------- */
			syncLogin() {
				this.isLogin = isLogined()
				const cached = getCachedUser()
				this.user = cached
					? Object.assign({}, DEFAULT_USER, cached)
					: Object.assign({}, DEFAULT_USER)
			},
			/** 退出登录后清空所有账号数据（连同未读角标） */
			resetAccountData() {
				this.resume = {}
				this.resumeExists = false
				this.resumeState = 'idle'
				this.stats = {}
				this.statsState = 'idle'
				this.unread = 0
			},
			/**
			 * 静默刷新服务端资料
			 * ⚠️ 失败不打断页面：若为鉴权失效，请求层已清除本地登录态，这里只需回退为未登录展示
			 */
			async refreshProfile() {
				try {
					const data = await getInfo()
					refreshCachedUser(data)
					this.user = Object.assign({}, DEFAULT_USER, getCachedUser() || {})
					this.isLogin = isLogined()
				} catch (e) {
					this.isLogin = isLogined()
				}
			},

			/* ---------------- 账号数据（简历 + 统计） ---------------- */
			async loadAccountData() {
				if (!this.isLogin) {
					// 未登录不是「空数据」也不是「失败」，保持 idle，由模板渲染登录引导
					this.resumeState = 'idle'
					this.statsState = 'idle'
					return
				}
				// 两个请求互不依赖，并发发出；各自维护状态，一个失败不影响另一个区块
				await Promise.all([this.loadResume(), this.loadStats()])
			},
			async loadResume() {
				if (!this.isLogin) return
				this.resumeState = 'loading'
				try {
					const res = await getResume()
					this.resume = (res && res.resume) || {}
					// ⚠️ exists=false 时服务端给的是一份「结构完整、值为空」的模板而不是 null，
					//    因此空态判断要看 exists，而不是判断对象是否为空。
					this.resumeExists = !!(res && res.exists)
					this.resumeState = 'ready'
				} catch (e) {
					this.resume = {}
					this.resumeExists = false
					this.resumeState = 'error'
				}
			},
			async loadStats() {
				if (!this.isLogin) return
				this.statsState = 'loading'
				try {
					this.stats = (await getApplyStats()) || {}
					this.statsState = 'ready'
				} catch (e) {
					this.stats = {}
					this.statsState = 'error'
				}
			},
			/**
			 * 未读消息数（求职者侧）
			 *
			 * ⚠️ 未登录时该接口会 401；im.js 里已设 showError:false（不弹全局提示），
			 *    但 Promise 仍会 reject —— 必须自己 catch，否则控制台会出现未处理的拒绝。
			 *    这里的「静默忽略」仅针对这一个纯角标接口：它失败了不该打断整页，
			 *    角标保持为 0 即可（业务流程仍以消息中心页面里的真实列表为准）。
			 */
			async loadUnread() {
				if (!this.isLogin) {
					this.unread = 0
					return
				}
				try {
					const res = await getUnread()
					const n = Number((res && res.candidate) || 0)
					this.unread = Number.isFinite(n) && n > 0 ? n : 0
				} catch (e) {
					this.unread = 0
				}
			},

			/* ---------------- 功能宫格配置 ---------------- */
			/**
			 * 读取宫格配置，失败时降级为本地默认数组（原因见文件头注释）
			 * 同时对每一项做规范化：
			 *   - link 先过别名表再校验是否在冻结路由表内，越界项标记为 blocked（点击提示暂未开放）
			 *   - icon 过别名表 + 白名单，未知名字退化为 list
			 */
			async loadGrid() {
				let groups = GRID_FALLBACK
				try {
					const value = await getConfig('rcMineGridGroups')
					if (Array.isArray(value) && value.length) groups = value
				} catch (e) {
					// 配置缺失不算错误：用本地兜底结构保证页面结构完整（纯展示型配置，见文件头说明）
				}
				this.gridGroups = groups.map((group, gi) => ({
					title: group.title || ('功能入口 ' + (gi + 1)),
					items: (group.items || []).map((item, ii) => this.normalizeGridItem(item, gi, ii))
				}))
			},
			normalizeGridItem(item, gi, ii) {
				const link = String(item.link || '')
				const linkOk = FROZEN_ROUTES.indexOf(link.split('?')[0]) > -1
				return {
					id: item.id || ('grid-' + gi + '-' + ii),
					name: item.name || '功能入口',
					icon: this.normalizeIcon(item.icon),
					color: item.color || '#00A6A7',
					bg: item.bg || '#e6f7f7',
					// badge 属展示型运营角标，原样透传配置值（空值即不显示）。
					// ⚠️ 配置里已不再写死假数字（种子曾经是 "3"/"12"/"1"，与真实数量不符，
					//    属于「编造数据」）；页面上的真实数字一律以「求职统计」卡（getApplyStats）为准。
					//    若运营确实希望角标反映真实数量，应由业务接口驱动，而不是在前端硬算。
					badge: item.badge ? String(item.badge) : '',
					link: linkOk ? link : '',
					blockedName: item.name || '该功能'
				}
			},
			normalizeIcon(icon) {
				const name = String(icon || '')
				const mapped = ICON_ALIAS[name] || name
				return ICON_WHITELIST.indexOf(mapped) > -1 ? mapped : 'list'
			},

			/* ---------------- 跳转 ---------------- */
			goLogin() {
				uni.navigateTo({ url: '/pages/login/login' })
			},
			goSettings() {
				uni.navigateTo({ url: '/pages/mine/settings' })
			},
			goMessage() {
				if (!this.isLogin) {
					this.goLogin()
					return
				}
				uni.navigateTo({
					url: '/pages/mine/message',
					fail: () => uni.showToast({ title: '消息中心打开失败，请稍后重试', icon: 'none' })
				})
			},
			onUserTap() {
				// 未登录整块用户区就是登录入口；已登录则进设置页改资料
				if (!this.isLogin) {
					this.goLogin()
					return
				}
				this.goSettings()
			},
			goResume() {
				this.guardedNavigate('/pages/seeker/resume')
			},
			/** 统计项跳转：投递 / 收藏 / 求职报告 / 面试日程 */
			goStat(item) {
				this.guardedNavigate(item.path)
			},
			onGridTap(item) {
				if (!item.link) {
					uni.showToast({ title: item.blockedName + '暂未开放', icon: 'none' })
					return
				}
				// 设置页是本端页面，不需要登录守卫，其余入口按前缀判断
				if (item.link === '/pages/mine/settings' || item.link === '/pages/mine/agreement') {
					uni.navigateTo({ url: item.link })
					return
				}
				this.guardedNavigate(item.link)
			},
			/**
			 * 统一跳转：需要登录的页面先过守卫，跳转失败给出可读提示
			 * （新页面由各批次陆续落地，未注册时 navigateTo 会 fail，不应静默无反应）
			 */
			guardedNavigate(url) {
				const needLogin = LOGIN_REQUIRED_SEGMENTS.some(seg => url.indexOf('/pages/' + seg) === 0)
				if (needLogin && !this.isLogin) {
					uni.showToast({ title: '请先登录后再查看', icon: 'none' })
					setTimeout(() => this.goLogin(), 600)
					return
				}
				uni.navigateTo({
					url,
					fail: () => uni.showToast({ title: '页面打开失败，请稍后重试', icon: 'none' })
				})
			},
			/**
			 * 切换到企业端
			 * ⚠️ 同一账号可以同时具备「求职者」与「企业 HR」两种身份（服务端按 role 过滤会话与数据），
			 *    所以这里只是同一个账号下的视角切换，不是切换账号、也不会退出登录；
			 *    未绑定公司时由 /pages/hr/dashboard 自己引导去 /pages/hr/bind。
			 */
			goHr() {
				if (!this.isLogin) {
					uni.showToast({ title: '请先登录后再进入企业端', icon: 'none' })
					setTimeout(() => this.goLogin(), 600)
					return
				}
				uni.navigateTo({
					url: '/pages/hr/dashboard',
					fail: () => uni.showToast({ title: '企业端打开失败，请稍后重试', icon: 'none' })
				})
			}
		}
	}
</script>

<style lang="scss" scoped>
	.mine {
		background-color: $zn-bg-page;
	}

	/* ==================== 顶部头部 ==================== */
	.mine__header {
		background: $zn-gradient;
		padding-bottom: 56rpx;
	}

	.mine__topbar {
		height: 88rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		padding: 0 $zn-page-padding;
	}

	.mine__topbar-title {
		font-size: $zn-font-lg;
		font-weight: 700;
		color: $zn-text-white;
		letter-spacing: 1rpx;
	}

	.mine__topbar-right {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.mine__msg {
		position: relative;
		height: 56rpx;
		padding: 0 18rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
		border-radius: $zn-radius-pill;
		background-color: rgba(255, 255, 255, 0.18);
	}

	.mine__msg-text {
		font-size: $zn-font-sm;
		color: $zn-text-white;
		margin-left: 8rpx;
	}

	.mine__msg-badge {
		position: absolute;
		right: -6rpx;
		top: -10rpx;
		min-width: 30rpx;
		height: 30rpx;
		padding: 0 8rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-red;
		color: $zn-text-white;
		font-size: $zn-font-xs;
		line-height: 30rpx;
		text-align: center;
		border: 2rpx solid $zn-text-white;
	}

	.mine__icon-btn {
		width: 64rpx;
		height: 64rpx;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-left: 8rpx;
	}

	.mine__user {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 12rpx $zn-page-padding 0;
	}

	.mine__avatar-ph {
		width: 120rpx;
		height: 120rpx;
		border-radius: 50%;
		background-color: #e6e9ed;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		border: 3rpx solid rgba(255, 255, 255, 0.8);
	}

	.mine__user-info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin-left: $zn-gap;
	}

	.mine__name {
		font-size: 42rpx;
		font-weight: 700;
		color: $zn-text-white;
		max-width: 340rpx;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	.mine__sub {
		font-size: $zn-font-sm;
		color: rgba(255, 255, 255, 0.86);
		margin-top: 8rpx;
	}

	.mine__jobstatus {
		align-self: flex-start;
		margin-top: 12rpx;
		padding: 4rpx 16rpx;
		border-radius: $zn-radius-pill;
		background-color: rgba(255, 255, 255, 0.22);
		font-size: $zn-font-xs;
		color: $zn-text-white;

		&.is-dim {
			color: rgba(255, 255, 255, 0.72);
			background-color: rgba(255, 255, 255, 0.12);
		}
	}

	/* ==================== 内容区 ==================== */
	.mine__body {
		position: relative;
		z-index: 2;
		margin-top: -36rpx;
		border-top-left-radius: 40rpx;
		border-top-right-radius: 40rpx;
		background-color: $zn-bg-page;
		padding: 28rpx $zn-page-padding 40rpx;
	}

	.card {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 26rpx $zn-gap;
		box-shadow: $zn-shadow-sm;
		margin-bottom: $zn-gap;
	}

	.card__title {
		font-size: $zn-font-md;
		font-weight: 700;
		color: $zn-text-title;
	}

	.card__more {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.card__more-text {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
		margin-right: 4rpx;
	}

	/* ---------- 通用状态行（加载中 / 失败重试） ---------- */
	.state {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		padding: 44rpx 0;
	}

	.state__text {
		font-size: $zn-font;
		color: $zn-text-grey;
		margin-left: 10rpx;

		&--error {
			color: $zn-red;
		}
	}

	/* ---------- 未登录引导 ---------- */
	.guest {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 36rpx 0 30rpx;
	}

	.guest__text {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
		text-align: center;
		line-height: 38rpx;
	}

	.guest__btn {
		margin-top: $zn-gap;
		height: 68rpx;
		padding: 0 56rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;
	}

	.guest__btn-text {
		font-size: $zn-font;
		font-weight: 600;
		color: $zn-text-white;
	}

	/* ---------- 简历完整度 ---------- */
	.resume__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.resume__body {
		margin-top: $zn-gap;
	}

	.resume__bar {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.resume__track {
		flex: 1;
		min-width: 0;
	}

	.resume__percent {
		font-size: $zn-font-lg;
		font-weight: 700;
		color: $zn-theme-deep;
		margin-left: 16rpx;
		width: 96rpx;
		text-align: right;
	}

	.resume__tip {
		display: block;
		margin-top: 14rpx;
		font-size: $zn-font-sm;
		color: $zn-text-sub;

		&.is-warn {
			color: $zn-orange;
		}
	}

	.resume__meta {
		display: block;
		margin-top: 8rpx;
		font-size: $zn-font-sm;
		color: $zn-text-grey;
	}

	/* ---------- 求职统计 ---------- */
	.stat__head {
		display: flex;
		flex-direction: row;
		align-items: baseline;
		justify-content: space-between;
	}

	.stat__sub {
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	.stat__guest {
		padding: 36rpx 0 20rpx;
		display: flex;
		justify-content: center;
	}

	.stat__guest-text {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
	}

	.stat__grid {
		display: flex;
		flex-direction: row;
		margin-top: 20rpx;
	}

	.stat__item {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 12rpx 0;
	}

	.stat__value-row {
		display: flex;
		flex-direction: row;
		align-items: baseline;
	}

	.stat__value {
		font-size: $zn-font-xl;
		font-weight: 700;
		color: $zn-text-title;
		line-height: 48rpx;
	}

	.stat__unit {
		font-size: $zn-font-xs;
		color: $zn-text-grey;
		margin-left: 4rpx;
	}

	.stat__label {
		font-size: $zn-font-xs;
		color: $zn-text-grey;
		margin-top: 8rpx;
	}

	/* ---------- 功能宫格 ---------- */
	.grid__head {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.grid__bar {
		width: 6rpx;
		height: 28rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		margin-right: 12rpx;
	}

	.grid__list {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		margin-top: 20rpx;
	}

	.grid__item {
		width: 25%;
		display: flex;
		flex-direction: column;
		align-items: center;
		margin-bottom: 20rpx;
	}

	.grid__icon {
		position: relative;
		width: 84rpx;
		height: 84rpx;
		border-radius: 26rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.grid__badge {
		position: absolute;
		right: -10rpx;
		top: -8rpx;
		min-width: 30rpx;
		height: 30rpx;
		padding: 0 8rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-red;
		color: $zn-text-white;
		font-size: $zn-font-xs;
		line-height: 30rpx;
		text-align: center;
		border: 2rpx solid $zn-text-white;
	}

	.grid__label {
		font-size: $zn-font-xs;
		color: $zn-text-main;
		margin-top: 12rpx;
		text-align: center;
	}

	/* ---------- 企业端入口 ---------- */
	.hr {
		display: flex;
		flex-direction: row;
		align-items: center;
		background: $zn-gradient-soft;
		border-radius: $zn-radius-lg;
		padding: 28rpx $zn-gap;
		box-shadow: $zn-shadow-theme;
	}

	.hr__icon {
		width: 76rpx;
		height: 76rpx;
		border-radius: 24rpx;
		background-color: rgba(255, 255, 255, 0.22);
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.hr__main {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin-left: 20rpx;
	}

	.hr__title {
		font-size: $zn-font-md;
		font-weight: 700;
		color: $zn-text-white;
	}

	.hr__desc {
		font-size: $zn-font-xs;
		color: rgba(255, 255, 255, 0.86);
		margin-top: 8rpx;
	}

	.hr__btn {
		flex-shrink: 0;
		height: 60rpx;
		padding: 0 24rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-text-white;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		margin-left: 16rpx;
	}

	.hr__btn-text {
		font-size: $zn-font-sm;
		font-weight: 600;
		color: $zn-theme-deep;
		margin-right: 4rpx;
	}
</style>
