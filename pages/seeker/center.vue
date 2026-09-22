<template>
	<view class="zn-page center">
		<!-- ==================== 顶部：深青绿渐变头部 ==================== -->
		<view class="center__header">
			<!-- 头部本身是渐变底，导航栏用 transparent（zn-nav-bar 的 green 是旧版绿色渐变，与本项目主题色不符） -->
			<zn-nav-bar type="transparent" />

			<view class="center__hero">
				<view class="center__hero-left">
					<text class="center__hero-title">求职中心</text>
					<text class="center__hero-tip">{{ heroTip }}</text>
				</view>
				<view class="center__hero-entry" hover-class="zn-hover" @tap="goReport">
					<text class="center__hero-entry-text">求职报告</text>
					<uni-icons type="right" :size="13" color="#ffffff"></uni-icons>
				</view>
			</view>
		</view>

		<!-- ==================== 内容区 ==================== -->
		<view class="center__body">
			<!-- 未登录：投递/收藏/面试都是账号私有数据，服务端一律要求鉴权，这里只给登录引导 -->
			<zn-empty v-if="!isLogin" icon="person" text="登录后查看求职中心"
				desc="投递记录、收藏职位与面试安排都跟随账号" btn-text="去登录" @action="goLogin" />

			<!-- 加载中 -->
			<view v-else-if="loading" class="state">
				<text class="state__text">正在加载求职数据…</text>
			</view>

			<!-- 加载失败：不做 mock 兜底，如实失败并提供重试 -->
			<view v-else-if="loadFailed" class="state state--fail" hover-class="zn-hover" @tap="refresh">
				<uni-icons type="refresh" :size="18" color="#ff4d4f"></uni-icons>
				<text class="state__text state__text--fail">求职数据加载失败，点击重试</text>
			</view>

			<template v-else>
				<!-- ---------- 1. 顶部统计卡（深青绿渐变，上浮压住头部下沿） ---------- -->
				<view class="stats">
					<view v-for="item in statCells" :key="item.key" class="stats__cell">
						<view class="stats__num">
							<text class="stats__value">{{ item.value }}</text>
							<text class="stats__unit">{{ item.unit }}</text>
						</view>
						<text class="stats__label">{{ item.label }}</text>
					</view>
				</view>

				<!-- ---------- 2. 一条投递都没有：先给可执行的引导，而不是一排 0 ---------- -->
				<zn-empty v-if="!delivered" icon="paperplane" text="还没有投递记录"
					desc="投出第一份简历后，这里会显示漏斗进度与面试安排" btn-text="去逛逛职位"
					@action="goJobs" />

				<!-- ---------- 3. 求职漏斗（累计口径） ---------- -->
				<view v-else class="card">
					<zn-section-header title="求职漏斗" subtitle="累计口径 · 进入面试的必然先被查看" />
					<view v-for="(item, i) in funnel" :key="item.stage" class="funnel__row">
						<view class="funnel__head">
							<text class="funnel__label">{{ item.label }}</text>
							<text class="funnel__count">{{ item.count }} 份</text>
						</view>
						<view class="funnel__track">
							<view class="funnel__fill" :style="funnelStyle(item, i)"></view>
						</view>
					</view>
				</view>

				<!-- ---------- 4. 待办：即将到来的面试 ---------- -->
				<view v-if="delivered" class="card">
					<zn-section-header title="即将面试" :subtitle="interviewSubtitle" more="面试日程"
						@more="goInterview" />
					<view v-if="!upcoming.length" class="todo__none">
						<text class="todo__none-text">暂时没有待办面试，保持投递节奏</text>
					</view>
					<view v-for="item in upcoming" :key="item.id" class="todo" hover-class="zn-hover"
						@tap="goInterview">
						<view class="todo__head">
							<text class="todo__round zn-ellipsis">{{ item.roundName || '面试' }}</text>
							<text class="todo__status">{{ item.statusText }}</text>
						</view>
						<view class="todo__meta">
							<uni-icons type="calendar" :size="15" color="#00a6a7"></uni-icons>
							<text class="todo__time">{{ item.timeText }}</text>
							<text class="todo__dot">·</text>
							<text class="todo__mode">{{ item.modeText }}</text>
							<text v-if="item.durationMin" class="todo__dot">·</text>
							<text v-if="item.durationMin" class="todo__mode">{{ item.durationMin }} 分钟</text>
						</view>
						<!-- 现场面试看地址、视频面试看链接：两者服务端只会给其中一个 -->
						<text v-if="item.address" class="todo__place zn-ellipsis">{{ item.address }}</text>
						<text v-else-if="item.onlineLink" class="todo__place zn-ellipsis">{{ item.onlineLink }}</text>
					</view>
				</view>

				<!-- ---------- 5. 功能宫格（展示型配置，来自 page_config 的 rcMineGridGroups） ---------- -->
				<view v-for="(group, gi) in groups" :key="gi" class="grid">
					<zn-section-header :title="group.title" :subtitle="gridSubtitle(gi)" />
					<view class="grid__items">
						<view v-for="item in group.items" :key="item.id" class="grid__item" hover-class="zn-hover"
							@tap="goGrid(item)">
							<view class="grid__icon" :style="{ backgroundColor: item.bg }">
								<uni-icons :type="safeIcon(item.icon)" :size="24"
									:color="item.color || '#00a6a7'"></uni-icons>
								<text v-if="gridBadge(item)" class="grid__badge">{{ gridBadge(item) }}</text>
							</view>
							<text class="grid__name">{{ item.name }}</text>
						</view>
					</view>
				</view>
			</template>
		</view>

		<!-- ==================== 底部 tabBar ==================== -->
		<zn-tab-bar current="study" />
	</view>
</template>

<script>
	/**
	 * 求职中心（tab 页）
	 *
	 * 数据来源：
	 *   统计 / 漏斗 / 待办面试   GET /api/v1/apply/stats（services/apply.js → getApplyStats）
	 *   功能宫格                 GET /api/v1/content/config/rcMineGridGroups（展示型配置）
	 *
	 * ⚠️ 漏斗与 byStatus 不是一回事（服务端已在 apply.js 注释里写明）：
	 *    funnel 是**累计**口径（进入面试的人必然先被查看过），
	 *    byStatus 是**当前状态快照**。本页只展示 funnel，
	 *    状态明细在各状态的筛选列表里看（/pages/seeker/applications），不在这里混用两套数字。
	 *
	 * ⚠️ 配置里的 link / icon / badge 都不能直接用：
	 *    1. link 只放行公约冻结路由表内的路径，越界的一律提示「未开放」而不是硬跳（见 ALLOWED_ROUTES）；
	 *    2. icon 里有 uni-icons 不存在的名字（如 chart），会渲染成空白方块 →
	 *       白名单校验后取替代图标；
	 *    3. badge 属展示型运营角标，配置里已清空（此前写死过 "3" / "12" 这类与真实数量不符的假数字）；
	 *       有真实数据的入口由本页用接口数字覆盖，纯文字角标（如 AI）保留。
	 */
	import { isLogined } from '@/services/user.js'
	import { getApplyStats } from '@/services/apply.js'
	import { getConfig } from '@/services/content.js'

	/**
	 * uni-icons 可用图标白名单（与《招聘改造-页面公约》第三节一致）
	 * 为什么要在页面里再存一份：宫格图标名来自数据库配置，不受代码控制，
	 * 传了不存在的名字 uni-icons 只会渲染成空白方块，肉眼很难发现是配置错了。
	 */
	const ICON_WHITELIST = [
		'arrow-down', 'bars', 'calendar', 'chat', 'checkbox', 'checkbox-filled', 'checkmarkempty',
		'clear', 'closeempty', 'compose', 'email', 'eye', 'fire-filled', 'gear', 'gift', 'headphones',
		'info', 'info-filled', 'left', 'list', 'locked', 'medal-filled', 'more-filled', 'notification',
		'notification-filled', 'paperplane', 'paperplane-filled', 'person', 'person-filled', 'plusempty',
		'pyq', 'refresh', 'right', 'search', 'send', 'smallcircle-filled', 'spinner-cycle', 'staff-filled',
		'star', 'star-filled', 'text', 'trash', 'tune', 'videocam', 'videocam-filled', 'vip-filled'
	]

	/**
	 * 冻结路由表白名单：只在其中的路径才允许跳转（跳错路由比不跳更难排查）
	 *
	 * ⚠️ 这里刻意**不维护「旧路径 → 新路径」的别名表**：
	 *    别名表的键是 /pages/... 形式的字符串，会被 tools/check-routes.js
	 *    当成真实跳转目标而误报「未注册路由」；旧路径的根因在种子数据（已修正），
	 *    页面里再留映射表就是死代码。漏网的旧路径一律提示「暂未开放」。
	 */
	const ALLOWED_ROUTES = [
		'/pages/index/index', '/pages/job/list', '/pages/job/search', '/pages/job/detail',
		'/pages/job/referral', '/pages/seeker/center', '/pages/seeker/applications',
		'/pages/seeker/favorites', '/pages/seeker/resume', '/pages/seeker/report',
		'/pages/seeker/interview', '/pages/bank/list', '/pages/bank/practice', '/pages/bank/wrong',
		'/pages/ai/ai', '/pages/mine/message', '/pages/chat/chat', '/pages/mine/mine',
		'/pages/mine/settings', '/pages/mine/agreement', '/pages/login/login'
	]

	/**
	 * 配置读取失败时的本地兜底宫格
	 *
	 * ⚠️ 这只兜底「导航入口」，不兜底任何业务数字（数字仍只来自 /apply/stats）：
	 *    配置接口不通时若整块宫格消失，用户将无法从求职中心进入投递/收藏/简历等页面，
	 *    而这几个页面本身是好用的 —— 入口消失属于可用性事故，所以用最小入口表兜住。
	 *    业务数据一律不兜底（公约第四节第 2 条）。
	 */
	const LOCAL_GRID = [
		{
			title: '我的求职',
			items: [
				{ id: 'mine-deliver', name: '我的投递', icon: 'paperplane', color: '#00A6A7', bg: '#e6f7f7', link: '/pages/seeker/applications' },
				{ id: 'mine-favorite', name: '我的收藏', icon: 'star', color: '#ff8f1f', bg: '#fff4e6', link: '/pages/seeker/favorites' },
				{ id: 'mine-interview', name: '面试日程', icon: 'calendar', color: '#3b9dff', bg: '#eaf4ff', link: '/pages/seeker/interview' },
				{ id: 'mine-resume', name: '简历管理', icon: 'compose', color: '#8a6cf6', bg: '#f2eeff', link: '/pages/seeker/resume' }
			]
		},
		{
			title: '求职服务',
			items: [
				{ id: 'mine-question-bank', name: '面试题库', icon: 'medal-filled', color: '#ff6b4a', bg: '#fff0ec', link: '/pages/bank/list' },
				{ id: 'mine-report', name: '求职报告', icon: 'bars', color: '#2bb14c', bg: '#e9fbef', link: '/pages/seeker/report' },
				{ id: 'mine-ai', name: 'AI 求职助手', icon: 'chat', color: '#5b7cfa', bg: '#eef1ff', link: '/pages/ai/ai' },
				{ id: 'mine-referral', name: '名企内推', icon: 'fire-filled', color: '#ff8f1f', bg: '#fff4e6', link: '/pages/job/referral' }
			]
		}
	]

	/** 配置里的 icon 名 → uni-icons 里语义最接近的可用图标 */
	const ICON_ALIAS = {
		medal: 'medal-filled',
		chart: 'bars',
		paperplane: 'paperplane',
		heart: 'star'
	}

	/** 哪些宫格角标可以用本页真实数字覆盖（其余角标是「热 / 新 / AI」这类固定文案，保留） */
	const BADGE_BY_STATS = {
		'mine-deliver': 'delivered',
		'mine-favorite': 'favorited',
		'mine-interview': 'upcoming'
	}

	/** 漏斗各段配色：越往后颜色越深，一眼能看出转化路径 */
	const FUNNEL_COLORS = [
		'linear-gradient(90deg, #5ed3d4 0%, #33c4c5 100%)',
		'linear-gradient(90deg, #33c4c5 0%, #00a6a7 100%)',
		'linear-gradient(90deg, #00a6a7 0%, #008c8d 100%)',
		'linear-gradient(90deg, #008c8d 0%, #00797b 100%)',
		'linear-gradient(90deg, #00797b 0%, #00696b 100%)'
	]

	export default {
		data() {
			return {
				isLogin: false,
				loading: true,
				loadFailed: false,
				// 服务端统计快照（refresh 时整体重建，模板只读这里）
				stats: {
					delivered: 0,
					favorited: 0,
					byStatus: {},
					funnel: [],
					upcomingInterviews: [],
					interviewRate: 0
				},
				groups: [],
				gridFallback: false
			}
		},
		computed: {
			delivered() {
				return this.stats.delivered || 0
			},
			upcoming() {
				return this.stats.upcomingInterviews || []
			},
			/** 头部一句话：把「现在该做什么」说出来，而不是复述标题 */
			heroTip() {
				if (!this.delivered) return '投出第一份简历，开始积累你的求职数据'
				if (this.upcoming.length) return '有 ' + this.upcoming.length + ' 场面试待办，记得提前准备'
				return '已投递 ' + this.delivered + ' 份 · 面试转化率 ' + (this.stats.interviewRate || 0) + '%'
			},
			/** 顶部四个统计格 */
			statCells() {
				return [
					{ key: 'delivered', label: '已投递', value: this.delivered, unit: '份' },
					{ key: 'favorited', label: '收藏职位', value: this.stats.favorited || 0, unit: '个' },
					{ key: 'rate', label: '面试转化率', value: this.stats.interviewRate || 0, unit: '%' },
					{ key: 'upcoming', label: '即将面试', value: this.upcoming.length, unit: '场' }
				]
			},
			funnel() {
				return this.stats.funnel || []
			},
			/** 漏斗最大计数：各段宽度按它换算百分比（delivered 恒为最大，但用 max 更稳） */
			funnelMax() {
				const list = this.funnel.map(item => Number(item.count) || 0)
				return Math.max.apply(null, list.concat([1]))
			},
			interviewSubtitle() {
				return this.upcoming.length ? '共 ' + this.upcoming.length + ' 场待办' : '暂无待办'
			}
		},
		onLoad() {
			this.refresh()
		},
		onShow() {
			// 从投递/收藏/简历页返回时重新拉取：撤回投递、取消收藏后数字要立刻对上
			if (this.isLogin) this.refresh()
		},
		onPullDownRefresh() {
			// refresh 完成后统一停表（见 refresh 的 finally）
			this.refresh(true)
		},
		methods: {
			/* ---------------- 数据 ---------------- */
			/**
			 * 拉取统计数据与宫格配置
			 * @param {boolean} [fromPull] 是否来自下拉刷新（决定要不要 stopPullDownRefresh）
			 */
			async refresh(fromPull) {
				this.isLogin = isLogined()
				if (!this.isLogin) {
					// 未登录：清空为初始值，不展示任何编造的数字
					this.loading = false
					this.loadFailed = false
					this.resetStats()
					this.gridFallback = true
					this.groups = this.buildGroups(this.gridFallbackList())
					if (fromPull) uni.stopPullDownRefresh()
					return
				}
				this.loading = true
				try {
					const data = await getApplyStats()
					this.stats = {
						delivered: data.delivered || 0,
						favorited: data.favorited || 0,
						byStatus: data.byStatus || {},
						funnel: data.funnel || [],
						upcomingInterviews: data.upcomingInterviews || [],
						interviewRate: data.interviewRate || 0
					}
					this.loadFailed = false
					await this.loadGrid()
				} catch (e) {
					// 纯接口模式：失败就是失败（services/api.js 已弹提示），本页只置失败态供重试
					this.resetStats()
					this.gridFallback = true
					this.groups = this.buildGroups(this.gridFallbackList())
					this.loadFailed = true
				} finally {
					this.loading = false
					if (fromPull) {
						uni.stopPullDownRefresh()
						uni.showToast({ title: this.loadFailed ? '刷新失败' : '已更新', icon: 'none' })
					}
				}
			},

			resetStats() {
				this.stats = {
					delivered: 0,
					favorited: 0,
					byStatus: {},
					funnel: [],
					upcomingInterviews: [],
					interviewRate: 0
				}
			},

			/** 宫格配置读取（失败回落本地入口表，理由见 LOCAL_GRID 注释） */
			async loadGrid() {
				let raw = []
				try {
					const value = await getConfig('rcMineGridGroups')
					raw = Array.isArray(value) ? value : []
				} catch (e) {
					raw = []
				}
				this.gridFallback = !raw.length
				this.groups = this.buildGroups(this.gridFallback ? this.gridFallbackList() : raw)
			},

			/** 本地兜底入口（未登录 / 配置读取失败 / 统计请求失败时都用它，保证入口可达） */
			gridFallbackList() {
				return LOCAL_GRID
			},

			/**
			 * 规范化宫格配置：补 icon 白名单校验、角标数字、items 结构
			 * 不改配置里的 title / name / color / bg（视觉以运营配置为准）
			 */
			buildGroups(raw) {
				const groups = Array.isArray(raw) ? raw : []
				return groups.map(group => {
					const items = (group && Array.isArray(group.items) ? group.items : []).map(item => {
						return Object.assign({}, item, {
							icon: this.safeIcon(item.icon),
							color: item.color || '#00a6a7',
							bg: item.bg || '#e5f7f7'
						})
					})
					return { title: (group && group.title) || '', items }
				}).filter(group => group.items.length)
			},

			/**
			 * 图标白名单校验：不在白名单里的名字按 ICON_ALIAS 取替代，取不到用 info
			 * 目的：配置改错图标名时页面不会出现空白方块，也不会整页报错
			 */
			safeIcon(name) {
				const key = String(name || '')
				if (ICON_WHITELIST.indexOf(key) > -1) return key
				const alias = ICON_ALIAS[key]
				return alias && ICON_WHITELIST.indexOf(alias) > -1 ? alias : 'info'
			},

			/** 角标：有真实数字的入口显示真实值（0 不显示），其余保留配置文案 */
			gridBadge(item) {
				const key = BADGE_BY_STATS[item && item.id]
				if (key === 'delivered') return this.delivered ? String(this.delivered) : ''
				if (key === 'favorited') return this.stats.favorited ? String(this.stats.favorited) : ''
				if (key === 'upcoming') return this.upcoming.length ? String(this.upcoming.length) : ''
				return (item && item.badge) || ''
			},

			gridSubtitle(index) {
				if (!this.gridFallback) return ''
				return index === 0 ? '配置未取到，显示默认入口' : ''
			},

			/** 漏斗某段宽度：按 count 占最大值的比例（非零值至少留 6%，否则细到看不见） */
			funnelStyle(item, index) {
				const count = Number(item.count) || 0
				const percent = count ? Math.max(6, Math.round((count / this.funnelMax) * 100)) : 2
				return {
					width: percent + '%',
					background: count ? FUNNEL_COLORS[index % FUNNEL_COLORS.length] : '#f2f4f7'
				}
			},

			/* ---------------- 跳转 ---------------- */
			goLogin() {
				uni.navigateTo({ url: '/pages/login/login' })
			},
			goReport() {
				uni.navigateTo({ url: '/pages/seeker/report' })
			},
			goInterview() {
				uni.navigateTo({ url: '/pages/seeker/interview' })
			},
			/** 空态引导：职位首页是 tab 页，用 reLaunch 才能正确切换底部 tabBar 高亮 */
			goJobs() {
				uni.reLaunch({ url: '/pages/index/index' })
			},

			/**
			 * 宫格跳转：先做旧路径别名映射，再校验是否在冻结路由表内
			 * 映射不到 / 不在表内 → 只提示「暂未开放」，绝不跳到不存在的页面
			 */
			goGrid(item) {
				const url = this.resolveLink(item && item.link)
				if (!url) {
					uni.showToast({ title: '该入口暂未开放', icon: 'none' })
					return
				}
				uni.navigateTo({ url })
			},

			resolveLink(link) {
				const raw = String(link || '').split('?')[0]
				// 只放行白名单内的路径；解析不出来返回空串，调用方据此提示「暂未开放」
				return ALLOWED_ROUTES.indexOf(raw) > -1 ? String(link) : ''
			}
		}
	}
</script>

<style lang="scss" scoped>
	.center {
		/* tab 页：底部留白由 .zn-page 负责，这里不重复加 */
		background-color: $zn-bg-page;
	}

	/* ==================== 头部 ==================== */
	.center__header {
		background: linear-gradient(160deg, #33c4c5 0%, #00a6a7 45%, #00696b 100%);
		padding-bottom: 72rpx;
	}

	.center__hero {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		padding: 12rpx $zn-page-padding 0;
	}

	.center__hero-left {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}

	.center__hero-title {
		font-size: 40rpx;
		font-weight: 700;
		color: #ffffff;
	}

	.center__hero-tip {
		font-size: 22rpx;
		color: rgba(255, 255, 255, 0.88);
		margin-top: 10rpx;
	}

	.center__hero-entry {
		flex-shrink: 0;
		display: flex;
		flex-direction: row;
		align-items: center;
		height: 56rpx;
		padding: 0 20rpx;
		border-radius: $zn-radius-pill;
		background-color: rgba(255, 255, 255, 0.22);
		margin-left: $zn-gap-sm;
	}

	.center__hero-entry-text {
		font-size: 23rpx;
		color: #ffffff;
		margin-right: 6rpx;
	}

	/* ==================== 内容区 ==================== */
	.center__body {
		position: relative;
		z-index: 2;
		margin-top: -56rpx;
		padding: 0 $zn-page-padding 40rpx;
	}

	/* ---------- 三态 ---------- */
	.state {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		padding: 80rpx 0;
	}

	.state--fail {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 40rpx 24rpx;
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

	/* ---------- 1. 统计卡 ---------- */
	.stats {
		display: flex;
		flex-direction: row;
		align-items: center;
		background: linear-gradient(135deg, #00a6a7 0%, #008c8d 55%, #00696b 100%);
		border-radius: $zn-radius-lg;
		padding: 30rpx 12rpx 26rpx;
		box-shadow: $zn-shadow-lg;
		border: 2rpx solid rgba(255, 255, 255, 0.28);
	}

	.stats__cell {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.stats__num {
		display: flex;
		flex-direction: row;
		align-items: baseline;
	}

	.stats__value {
		font-size: 46rpx;
		font-weight: 700;
		color: #ffffff;
		line-height: 52rpx;
	}

	.stats__unit {
		font-size: 20rpx;
		color: rgba(255, 255, 255, 0.8);
		margin-left: 4rpx;
	}

	.stats__label {
		font-size: 21rpx;
		color: rgba(255, 255, 255, 0.85);
		margin-top: 8rpx;
	}

	/* ---------- 通用白卡 ---------- */
	.card {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 0 $zn-gap $zn-gap;
		margin-top: $zn-gap;
		box-shadow: $zn-shadow-sm;
	}

	/* ---------- 3. 漏斗 ---------- */
	.funnel__row {
		margin-bottom: 20rpx;

		&:last-child {
			margin-bottom: 0;
		}
	}

	.funnel__head {
		display: flex;
		flex-direction: row;
		align-items: baseline;
		justify-content: space-between;
	}

	.funnel__label {
		font-size: 26rpx;
		color: $zn-text-main;
	}

	.funnel__count {
		font-size: 24rpx;
		font-weight: 600;
		color: $zn-theme-dark;
	}

	.funnel__track {
		height: 20rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		overflow: hidden;
		margin-top: 10rpx;
	}

	.funnel__fill {
		height: 100%;
		border-radius: $zn-radius-pill;
		transition: width 0.35s ease;
	}

	/* ---------- 4. 待办面试 ---------- */
	.todo {
		padding: 20rpx 0;
		border-bottom: 1rpx solid $zn-line;

		&:last-child {
			border-bottom: none;
		}
	}

	.todo__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.todo__round {
		flex: 1;
		min-width: 0;
		font-size: 28rpx;
		font-weight: 600;
		color: $zn-text-title;
	}

	.todo__status {
		flex-shrink: 0;
		font-size: 20rpx;
		color: $zn-theme-dark;
		background-color: $zn-theme-light;
		border-radius: $zn-radius-xs;
		padding: 2rpx 12rpx;
		margin-left: $zn-gap-sm;
	}

	.todo__meta {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 12rpx;
	}

	.todo__time {
		font-size: 24rpx;
		color: $zn-text-sub;
		margin-left: 8rpx;
	}

	.todo__dot {
		font-size: 22rpx;
		color: $zn-text-light;
		margin: 0 8rpx;
	}

	.todo__mode {
		font-size: 23rpx;
		color: $zn-text-sub;
	}

	.todo__place {
		display: block;
		font-size: 22rpx;
		color: $zn-text-grey;
		margin-top: 8rpx;
	}

	.todo__none {
		padding: 24rpx 0 8rpx;
	}

	.todo__none-text {
		font-size: 24rpx;
		color: $zn-text-light;
	}

	/* ---------- 5. 功能宫格 ---------- */
	.grid {
		margin-top: 8rpx;
	}

	.grid__items {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 28rpx 8rpx 10rpx;
		box-shadow: $zn-shadow-sm;
	}

	.grid__item {
		width: 25%;
		display: flex;
		flex-direction: column;
		align-items: center;
		margin-bottom: 26rpx;
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
		top: -8rpx;
		right: -10rpx;
		min-width: 28rpx;
		height: 28rpx;
		padding: 0 8rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-red;
		color: #ffffff;
		font-size: 18rpx;
		line-height: 28rpx;
		text-align: center;
	}

	.grid__name {
		font-size: 23rpx;
		color: $zn-text-sub;
		margin-top: 12rpx;
		text-align: center;
	}
</style>
