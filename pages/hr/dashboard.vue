<template>
	<view class="zn-page zn-page--no-tabbar hrdash">
		<!-- ==================== 自定义导航栏 ====================
			 企业端没有 tabBar，每个页面靠 zn-nav-bar 提供返回；
			 工作台是企业端的「首页」，所以返回/右上角都回求职者端首页（reLaunch）。 -->
		<zn-nav-bar title="招聘工作台">
			<view slot="left" class="hrdash__navbtn" hover-class="zn-hover" @tap="goSeekerHome">
				<uni-icons type="left" :size="22" color="#222222"></uni-icons>
			</view>
			<!-- 双身份切换入口：同一个账号既可以投简历（求职者）也可以招人（HR），
				 服务端用 user_role 区分，两端看到的数据互不影响，所以这里给一个显式出口。 -->
			<view slot="right" class="hrdash__navbtn hrdash__navbtn--wide" hover-class="zn-hover"
				@tap="goSeekerHome">
				<uni-icons type="person" :size="18" color="#00A6A7"></uni-icons>
				<text class="hrdash__navbtn-text">求职者端</text>
			</view>
		</zn-nav-bar>

		<!-- ==================== 一、加载中 ==================== -->
		<view v-if="loading" class="hrdash__state">
			<uni-icons type="spinner-cycle" :size="30" color="#00A6A7"></uni-icons>
			<text class="hrdash__state-text">正在加载工作台…</text>
		</view>

		<!-- ==================== 二、加载失败（可重试） ====================
			 公约第四条：接口失败就是失败，不做 mock 兜底，只给可点击的重试。 -->
		<view v-else-if="failed" class="hrdash__state">
			<zn-empty icon="info" text="工作台加载失败" :desc="failedMsg" btn-text="重新加载"
				@action="load" />
		</view>

		<!-- ==================== 三、未绑定公司：绑定引导 ====================
			 企业端所有数据接口都以「你绑定的公司」为隔离依据（服务端 _hr_context），
			 没绑定就没有任何招聘数据可看，所以这里不展示空数字，而是引导去绑定。 -->
		<view v-else-if="bound === false" class="bind-guide">
			<view class="bind-guide__logo">
				<uni-icons type="staff-filled" :size="46" color="#ffffff"></uni-icons>
			</view>
			<text class="bind-guide__title">你还不是企业招聘方</text>
			<text class="bind-guide__desc">绑定一家公司后即可发布职位、查看收到的简历、安排面试</text>
			<view class="bind-guide__btn" hover-class="zn-hover" @tap="goBind">
				<text class="bind-guide__btn-text">立即绑定公司</text>
			</view>
			<text class="bind-guide__tip">演示环境下直接从公司列表里选一家绑定即可</text>
		</view>

		<!-- ==================== 四、正常内容 ==================== -->
		<block v-else>
			<!-- ---------- 公司名片 ---------- -->
			<view class="hcard">
				<zn-company-logo :text="company.logoText" :color="company.logoColor" :size="96" />
				<view class="hcard__main">
					<text class="hcard__name zn-ellipsis">{{ company.name || company.shortName }}</text>
					<view class="hcard__meta">
						<text class="hcard__hr">{{ hrTitle || '招聘负责人' }}</text>
						<text class="hcard__dot">·</text>
						<text class="hcard__date">{{ todayText }}</text>
					</view>
				</view>
				<view class="hcard__company-btn" hover-class="zn-hover" @tap="goCompany">
					<text class="hcard__company-text">企业主页</text>
					<uni-icons type="right" :size="13" color="#999999"></uni-icons>
				</view>
			</view>

			<!-- ---------- 数据总览 ---------- -->
			<view class="stats">
				<view v-for="item in statCards" :key="item.key" class="stats__item" hover-class="zn-hover"
					@tap="goStat(item)">
					<text class="stats__value">{{ item.value }}</text>
					<text class="stats__label">{{ item.label }}</text>
				</view>
			</view>

			<!-- ---------- 快捷操作（page_config.rcHrDashboard.quickActions） ---------- -->
			<view v-if="quickActions.length" class="quick">
				<zn-section-header title="快捷操作" :bar="true" />
				<view class="quick__grid">
					<view v-for="item in quickActions" :key="item.id" class="quick__item" hover-class="zn-hover"
						@tap="onQuickAction(item)">
						<view class="quick__icon" :style="{ backgroundColor: item.bg || '#e5f7f7' }">
							<uni-icons :type="item.icon" :size="26" :color="item.color || '#00A6A7'"></uni-icons>
						</view>
						<text class="quick__label zn-ellipsis">{{ item.name }}</text>
					</view>
				</view>
			</view>

			<!-- ---------- 运营提示（同一条配置的 tips） ---------- -->
			<view v-if="tips.length" class="tips">
				<view class="tips__head">
					<uni-icons type="info-filled" :size="16" color="#00A6A7"></uni-icons>
					<text class="tips__title">招聘建议</text>
				</view>
				<view v-for="(tip, i) in tips" :key="i" class="tips__row">
					<text class="tips__index">{{ i + 1 }}</text>
					<text class="tips__text">{{ tip }}</text>
				</view>
			</view>

			<!-- ---------- 待处理简历 ---------- -->
			<view class="panel">
				<zn-section-header title="待处理简历" :subtitle="'最近 ' + recentApplications.length + ' 条'"
					more="全部简历" @more="goApplications()" />
				<zn-empty v-if="!recentApplications.length" icon="email" text="暂时没有新的投递"
					desc="职位上架后，求职者的投递会出现在这里" btn-text="去发布职位" @action="goJobEdit" />
				<view v-else class="apps">
					<view v-for="item in recentApplications" :key="item.id" class="app" hover-class="zn-hover"
						@tap="goCandidate(item)">
						<zn-avatar :name="candidateName(item)" :size="82" />
						<view class="app__main">
							<view class="app__row">
								<text class="app__name zn-ellipsis">{{ candidateName(item) }}</text>
								<!-- 状态文案一律用服务端按 HR 视角翻译好的 statusText，
									 不在这里自己写一套（同一份数据求职者端文案不同）。 -->
								<zn-tag :text="item.statusText" :type="tagType(item.statusType)" size="xs" />
							</view>
							<text class="app__meta zn-ellipsis">{{ candidateMeta(item) }}</text>
							<text class="app__job zn-ellipsis">投递：{{ item.jobTitle || '—' }}</text>
						</view>
						<view class="app__side">
							<text class="app__time">{{ item.createdText }}</text>
							<uni-icons type="right" :size="14" color="#cccccc"></uni-icons>
						</view>
					</view>
				</view>
			</view>

			<!-- ---------- 即将到来的面试 ---------- -->
			<view class="panel">
				<zn-section-header title="即将到来的面试" :subtitle="'共 ' + upcomingInterviews.length + ' 场'"
					more="面试安排" @more="goInterviews" />
				<zn-empty v-if="!upcomingInterviews.length" icon="calendar" text="近期没有面试安排"
					desc="在候选人详情页发出面试邀约后会显示在这里" />
				<view v-else class="ivs">
					<view v-for="it in upcomingInterviews" :key="it.id" class="iv" hover-class="zn-hover"
						@tap="goInterviews">
						<view class="iv__time">
							<text class="iv__time-text">{{ it.timeText }}</text>
							<text class="iv__dur">{{ it.durationMin }} 分钟</text>
						</view>
						<view class="iv__main">
							<view class="iv__row">
								<text class="iv__round zn-ellipsis">{{ it.roundName || ('第' + it.roundNo + '轮') }}</text>
								<zn-tag :text="it.statusText" type="orange" size="xs" />
							</view>
							<text class="iv__meta zn-ellipsis">{{ it.modeText }}{{ it.address ? ' · ' + it.address : '' }}</text>
							<text v-if="it.interviewer" class="iv__meta zn-ellipsis">面试官：{{ it.interviewer }}</text>
						</view>
					</view>
				</view>
			</view>

			<!-- ---------- 底部出口 ---------- -->
			<view class="hrdash__foot" hover-class="zn-hover" @tap="goSeekerHome">
				<text class="hrdash__foot-text">切换到求职者端</text>
			</view>
		</block>
	</view>
</template>

<script>
	/**
	 * HR 工作台（企业端首页）
	 *
	 * 数据来源：
	 *   身份      GET /hr/me          （services/hr.js → getHrMe）
	 *   概览      GET /hr/dashboard   （getHrDashboard）
	 *   宫格/提示 GET /content/config/rcHrDashboard（getConfig，展示型配置，可缺）
	 *
	 * ⚠️ 为什么先调 getHrMe 再调 getHrDashboard：
	 *    工作台是企业端入口，必须先把 bound=false 的账号挡在绑定引导上；
	 *    虽然 dashboard 本身在未绑定时也会 403，但那样用户看到的是报错而不是引导。
	 *    （本页两种情况都处理：getHrMe 判定 + 40301 兜底跳绑定页。）
	 *
	 * ⚠️ 数据隔离：服务端按「当前账号绑定的公司」过滤（hr.py 的 _hr_context），
	 *    前端**不传也不必传 companyId** —— 传了也会被忽略。
	 *
	 * ⚠️ quickActions 的 link 是**运营可改的配置数据**，不能直接拿去跳转：
	 *    实测数据库里已是冻结路由（/pages/hr/job-edit 等），而 seed 文件里还是老式路径
	 *    （/pages/hr/job/edit 等），另有 /pages/ai/ai 这种本期没有对应页面的入口。
	 *    因此本页用「冻结路由白名单 + 旧路径别名表」解析 link（见 resolveLink），
	 *    解析不出来的只提示「暂未开放」，不做假跳转，也不去改服务端种子数据。
	 */
	import { getHrMe, getHrDashboard } from '@/services/hr.js'
	import { getConfig } from '@/services/content.js'

	/**
	 * 冻结路由表里真实存在的企业端页面
	 * ⚠️ 只允许跳这些路径：配置是运营可改的数据，写错一个字符就会跳转失败，
	 *    白名单能把「配置写错」变成一句可读提示，而不是一个诡异的跳转失败。
	 */
	const FROZEN_ROUTES = [
		'/pages/hr/dashboard',
		'/pages/hr/jobs',
		'/pages/hr/job-edit',
		'/pages/hr/applications',
		'/pages/hr/candidate',
		'/pages/hr/interviews',
		'/pages/hr/company',
		'/pages/hr/bind'
	]

	/**
	 * 把配置里的 link 解析成可跳转的路径（解析不出来返回空串）
	 * 允许带查询串（如 /pages/hr/applications?status=submitted）
	 *
	 * ⚠️ 这里只认白名单，**不再维护「旧路径 → 新路径」的别名表**：
	 *    别名表的键本身就是 /pages/... 形式的字符串，会被 tools/check-routes.js
	 *    当成真实跳转目标而误报「未注册路由」；而旧路径的根因在种子数据（已按接口契约修正），
	 *    页面里再留一张映射表就是死代码。
	 *    真出现漏网的旧路径时返回空串 → 页面提示「暂未开放」，比静默重定向更诚实（会暴露数据问题）。
	 */
	function resolveLink(link) {
		if (!link) return ''
		const path = String(link).split('?')[0]
		return FROZEN_ROUTES.indexOf(path) > -1 ? link : ''
	}

	/** 状态徽标配色：服务端 statusType(success/warning/danger/info) → zn-tag 的 type */
	const TAG_TYPE = {
		success: 'green',
		warning: 'orange',
		danger: 'red',
		info: 'gray'
	}

	export default {
		data() {
			return {
				loading: true,
				ready: false, // onLoad 之后紧跟一次 onShow，用它跳过首次重复请求
				failed: false,
				failedMsg: '',
				bound: null, // null=还没判定 / false=未绑定 / true=已绑定
				company: {},
				hrTitle: '',
				stats: {},
				recentApplications: [],
				upcomingInterviews: [],
				quickActions: [],
				tips: []
			}
		},
		computed: {
			/** 数字卡片。字段缺失时显示 '-' 而不是 0，避免「接口没给」被误读成「一个都没有」 */
			statCards() {
				const s = this.stats || {}
				return [
					{ key: 'openJobs', label: '在招职位', value: this.num(s.openJobs), path: '/pages/hr/jobs' },
					{ key: 'totalApplications', label: '累计简历', value: this.num(s.totalApplications), path: '/pages/hr/applications' },
					{ key: 'pending', label: '待处理', value: this.num(s.pending), path: '/pages/hr/applications', status: 'submitted' },
					{ key: 'interviewing', label: '待面试', value: this.num(s.interviewing), path: '/pages/hr/applications', status: 'interview' },
					{ key: 'hired', label: '已入职', value: this.num(s.hired), path: '/pages/hr/applications', status: 'hired' },
					// 今日新投递没有对应的筛选参数（接口不支持按日期过滤），只展示不跳转
					{ key: 'todayApplications', label: '今日新投递', value: this.num(s.todayApplications), path: '' }
				]
			},
			todayText() {
				const d = new Date()
				return (d.getMonth() + 1) + '月' + d.getDate() + '日'
			}
		},
		onLoad() {
			this.load()
		},
		onShow() {
			// 从候选人详情 / 职位管理返回时刷新，保证状态与数字是最新的
			if (this.ready) this.load()
		},
		async onPullDownRefresh() {
			try {
				await this.load()
			} finally {
				uni.stopPullDownRefresh()
			}
		},
		methods: {
			/* ---------------- 数据 ---------------- */
			async load() {
				this.loading = !this.ready
				this.failed = false
				try {
					const me = await getHrMe()
					this.bound = !!(me && me.bound)
					if (!this.bound) {
						// 未绑定：清掉上一次的旧数据，不能拿上一家公司的数字继续展示
						this.company = {}
						this.stats = {}
						this.recentApplications = []
						this.upcomingInterviews = []
						return
					}
					const data = await getHrDashboard()
					this.company = data.company || {}
					this.hrTitle = data.hrTitle || ''
					this.stats = data.stats || {}
					this.recentApplications = data.recentApplications || []
					this.upcomingInterviews = data.upcomingInterviews || []
				} catch (e) {
					if (this.isUnbound(e)) {
						this.bound = false
						return
					}
					this.failed = true
					this.failedMsg = (e && e.message) || '请检查服务端是否已启动'
				} finally {
					this.loading = false
					this.ready = true
					this.loadConfig()
				}
			},
			/**
			 * 工作台的宫格与运营提示（展示型配置）
			 * ⚠️ 配置缺失不弹错、不影响主体数据 —— 它是可有可无的运营位，失败就整块不渲染。
			 */
			async loadConfig() {
				try {
					const cfg = await getConfig('rcHrDashboard')
					this.quickActions = (cfg && cfg.quickActions) || []
					this.tips = (cfg && cfg.tips) || []
				} catch (e) {
					this.quickActions = []
					this.tips = []
				}
			},
			/** 40301 / HTTP 403：账号还不是企业招聘方（可能刚被别人解绑），统一去绑定页 */
			isUnbound(err) {
				return !!err && (err.code === 40301 || err.status === 403)
			},
			num(v) {
				return v === null || v === undefined ? '-' : v
			},

			/* ---------------- 展示辅助 ---------------- */
			candidateName(item) {
				return (item.candidate && item.candidate.name) || '匿名候选人'
			},
			candidateMeta(item) {
				const c = item.candidate || {}
				return [c.educationLevel, c.workYearsText, c.expectedPosition].filter(Boolean).join(' · ') || '简历信息待完善'
			},
			tagType(type) {
				return TAG_TYPE[type] || 'gray'
			},

			/* ---------------- 跳转 ---------------- */
			goSeekerHome() {
				// 双身份切换：回求职者端首页。用 reLaunch 清栈，避免两个身份来回切换时栈越堆越深
				uni.reLaunch({ url: '/pages/index/index' })
			},
			goBind() {
				uni.reLaunch({ url: '/pages/hr/bind' })
			},
			goCompany() {
				uni.navigateTo({ url: '/pages/hr/company' })
			},
			goJobEdit() {
				uni.navigateTo({ url: '/pages/hr/job-edit' })
			},
			goInterviews() {
				uni.navigateTo({ url: '/pages/hr/interviews' })
			},
			goApplications(status) {
				const url = status
					? '/pages/hr/applications?status=' + encodeURIComponent(status)
					: '/pages/hr/applications'
				uni.navigateTo({ url })
			},
			goCandidate(item) {
				uni.navigateTo({ url: '/pages/hr/candidate?id=' + item.id })
			},
			goStat(item) {
				if (!item.path) return
				if (item.path === '/pages/hr/applications') {
					this.goApplications(item.status)
					return
				}
				uni.navigateTo({
					url: item.path,
					fail: () => uni.showToast({ title: '页面打开失败', icon: 'none' })
				})
			},
			onQuickAction(item) {
				const target = resolveLink(item.link)
				if (!target) {
					// 配置指向了尚未实现的页面（如 /pages/ai/ai 或写错的路径）：如实提示，不做假跳转
					uni.showToast({ title: item.name + '暂未开放', icon: 'none' })
					return
				}
				uni.navigateTo({
					url: target,
					fail: () => uni.showToast({ title: item.name + '打开失败', icon: 'none' })
				})
			}
		}
	}
</script>

<style lang="scss" scoped>
	.hrdash {
		padding-bottom: 60rpx;
	}

	/* ---------------- 导航栏右侧按钮 ---------------- */
	.hrdash__navbtn {
		width: 60rpx;
		height: 60rpx;
		display: flex;
		align-items: center;
		justify-content: center;

		&--wide {
			width: auto;
			padding-left: 12rpx;
		}
	}

	.hrdash__navbtn-text {
		font-size: $zn-font-sm;
		color: $zn-theme;
		margin-left: 6rpx;
	}

	/* ---------------- 三态：加载中 / 失败 ---------------- */
	.hrdash__state {
		padding: 160rpx $zn-page-padding;
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.hrdash__state-text {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
		margin-top: $zn-gap;
	}

	/* ---------------- 绑定引导 ---------------- */
	.bind-guide {
		margin: 80rpx $zn-page-padding 0;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: 60rpx $zn-gap-lg;
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.bind-guide__logo {
		width: 148rpx;
		height: 148rpx;
		border-radius: $zn-radius-xl;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;
	}

	.bind-guide__title {
		margin-top: $zn-gap-lg;
		font-size: $zn-font-lg;
		font-weight: 700;
		color: $zn-text-title;
	}

	.bind-guide__desc {
		margin-top: 14rpx;
		font-size: $zn-font-sm;
		color: $zn-text-sub;
		text-align: center;
		line-height: 40rpx;
	}

	.bind-guide__btn {
		margin-top: 44rpx;
		width: 100%;
		height: 92rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;
	}

	.bind-guide__btn-text {
		font-size: $zn-font-md;
		font-weight: 600;
		color: #ffffff;
	}

	.bind-guide__tip {
		margin-top: 20rpx;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	/* ---------------- 公司名片 ---------------- */
	.hcard {
		margin: $zn-gap $zn-page-padding 0;
		padding: $zn-gap-lg $zn-gap;
		border-radius: $zn-radius-lg;
		background: $zn-gradient;
		display: flex;
		flex-direction: row;
		align-items: center;
		box-shadow: $zn-shadow-theme;
	}

	.hcard__main {
		flex: 1;
		min-width: 0;
		margin-left: $zn-gap;
		display: flex;
		flex-direction: column;
	}

	.hcard__name {
		font-size: $zn-font-lg;
		font-weight: 700;
		color: #ffffff;
	}

	.hcard__meta {
		margin-top: 10rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.hcard__hr,
	.hcard__date {
		font-size: $zn-font-sm;
		color: rgba(255, 255, 255, 0.88);
	}

	.hcard__dot {
		margin: 0 10rpx;
		font-size: $zn-font-sm;
		color: rgba(255, 255, 255, 0.6);
	}

	.hcard__company-btn {
		flex-shrink: 0;
		height: 56rpx;
		padding: 0 20rpx;
		border-radius: $zn-radius-pill;
		background-color: rgba(255, 255, 255, 0.22);
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.hcard__company-text {
		font-size: $zn-font-xs;
		color: #ffffff;
		margin-right: 4rpx;
	}

	/* ---------------- 数据总览 ---------------- */
	.stats {
		margin: $zn-gap $zn-page-padding 0;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: 12rpx 0;
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
	}

	.stats__item {
		width: 33.33%;
		padding: 22rpx 0;
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.stats__value {
		font-size: $zn-font-xl;
		font-weight: 700;
		color: $zn-theme-deep;
		line-height: 48rpx;
	}

	.stats__label {
		margin-top: 8rpx;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
	}

	/* ---------------- 快捷操作 ---------------- */
	.quick {
		margin: $zn-gap-sm $zn-page-padding 0;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: 8rpx $zn-gap 20rpx;
	}

	.quick__grid {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
	}

	.quick__item {
		width: 25%;
		display: flex;
		flex-direction: column;
		align-items: center;
		margin-bottom: 12rpx;
	}

	.quick__icon {
		width: 84rpx;
		height: 84rpx;
		border-radius: $zn-radius;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.quick__label {
		margin-top: 12rpx;
		max-width: 140rpx;
		font-size: $zn-font-xs;
		color: $zn-text-main;
		text-align: center;
	}

	/* ---------------- 运营提示 ---------------- */
	.tips {
		margin: $zn-gap-sm $zn-page-padding 0;
		background-color: $zn-theme-lighter;
		border: 1rpx solid $zn-theme-light;
		border-radius: $zn-radius-lg;
		padding: $zn-gap;
	}

	.tips__head {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.tips__title {
		margin-left: 8rpx;
		font-size: $zn-font-sm;
		font-weight: 600;
		color: $zn-theme-dark;
	}

	.tips__row {
		margin-top: 14rpx;
		display: flex;
		flex-direction: row;
		align-items: flex-start;
	}

	.tips__index {
		width: 32rpx;
		height: 32rpx;
		border-radius: 50%;
		background-color: $zn-theme;
		color: #ffffff;
		font-size: $zn-font-xs;
		text-align: center;
		line-height: 32rpx;
		flex-shrink: 0;
		margin-top: 4rpx;
	}

	.tips__text {
		flex: 1;
		min-width: 0;
		margin-left: 14rpx;
		font-size: $zn-font-sm;
		color: $zn-text-sub;
		line-height: 40rpx;
	}

	/* ---------------- 区块容器 ---------------- */
	.panel {
		margin: $zn-gap-sm $zn-page-padding 0;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: 0 $zn-gap $zn-gap-sm;
	}

	/* ---------------- 待处理简历 ---------------- */
	.apps {
		display: flex;
		flex-direction: column;
	}

	.app {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 22rpx 0;
		border-top: 1rpx solid $zn-line;
	}

	.app__main {
		flex: 1;
		min-width: 0;
		margin-left: $zn-gap-sm;
		display: flex;
		flex-direction: column;
	}

	.app__row {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.app__name {
		max-width: 300rpx;
		font-size: $zn-font;
		font-weight: 600;
		color: $zn-text-title;
		margin-right: 12rpx;
	}

	.app__meta {
		margin-top: 8rpx;
		font-size: $zn-font-xs;
		color: $zn-text-sub;
	}

	.app__job {
		margin-top: 6rpx;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
	}

	.app__side {
		flex-shrink: 0;
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-left: 12rpx;
	}

	.app__time {
		font-size: $zn-font-xs;
		color: $zn-text-light;
		margin-right: 6rpx;
	}

	/* ---------------- 面试 ---------------- */
	.ivs {
		display: flex;
		flex-direction: column;
	}

	.iv {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 22rpx 0;
		border-top: 1rpx solid $zn-line;
	}

	.iv__time {
		width: 190rpx;
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
	}

	.iv__time-text {
		font-size: $zn-font-sm;
		font-weight: 600;
		color: $zn-theme-deep;
	}

	.iv__dur {
		margin-top: 6rpx;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	.iv__main {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}

	.iv__row {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.iv__round {
		max-width: 260rpx;
		font-size: $zn-font;
		font-weight: 600;
		color: $zn-text-title;
		margin-right: 12rpx;
	}

	.iv__meta {
		margin-top: 8rpx;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
	}

	/* ---------------- 底部出口 ---------------- */
	.hrdash__foot {
		margin: $zn-gap-lg $zn-page-padding 0;
		height: 92rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-card;
		box-shadow: $zn-shadow-sm;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.hrdash__foot-text {
		font-size: $zn-font;
		font-weight: 600;
		color: $zn-theme;
	}
</style>
