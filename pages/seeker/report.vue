<template>
	<view class="zn-page zn-page--no-tabbar">
		<!-- ==================== 顶部导航 ==================== -->
		<zn-nav-bar title="求职报告" show-back border />

		<!-- ==================== 三态 ==================== -->
		<!-- 报告需要登录后才有数据（接口 auth: true） -->
		<zn-empty v-if="!isLogin" icon="person" text="登录后查看求职报告"
			desc="报告基于你的投递、面试与简历数据生成" btn-text="去登录" @action="goLogin" />

		<view v-else-if="loading" class="state">
			<text class="state__text">正在生成求职报告…</text>
		</view>

		<view v-else-if="loadFailed" class="state state--fail" hover-class="zn-hover" @tap="refresh">
			<uni-icons type="refresh" :size="18" color="#ff4d4f"></uni-icons>
			<text class="state__text state__text--fail">报告加载失败，点击重试</text>
		</view>

		<template v-else>
			<view class="report__body">
				<!-- ==================== 头部文案（标题/副标题来自配置） ==================== -->
				<view class="hero">
					<text class="hero__title">{{ copy.title }}</text>
					<text class="hero__sub">{{ copy.subtitle }}</text>
					<view class="hero__rate">
						<text class="hero__rate-num">{{ hasData ? (summary.interviewRate || 0) : '—' }}</text>
						<text class="hero__rate-unit">%</text>
						<text class="hero__rate-label">面试转化率（投递 → 进入面试）</text>
					</view>
				</view>

				<!-- ==================== 空数据引导 ==================== -->
				<!--
					一条投递都没有时：不摆一排 0 让用户自己猜，直接说明「为什么是空的」以及现在能做什么。
					注意就业力（radar）与建议仍然有效 —— 它们同时依赖简历与练习记录，不只看投递。
				-->
				<view v-if="!hasData" class="guide">
					<uni-icons type="info-filled" :size="18" color="#00a6a7"></uni-icons>
					<view class="guide__info">
						<text class="guide__title">还没有投递记录，漏斗暂时是空的</text>
						<text class="guide__desc">先投出 3 个匹配的岗位，这里才会出现真实的转化数据；下面的求职力与建议已按你的简历和练习记录生成。</text>
					</view>
					<view class="guide__btn" hover-class="zn-hover" @tap="goJobs">
						<text class="guide__btn-text">去逛逛职位</text>
					</view>
				</view>

				<!-- ==================== 数字概览 ==================== -->
				<view class="card">
					<zn-section-header title="数据概览" :subtitle="overviewSubtitle" />
					<view class="nums">
						<view v-for="item in cells" :key="item.key" class="nums__cell">
							<view class="nums__num">
								<text class="nums__value" :class="{ 'is-none': item.none }">{{ item.value }}</text>
								<text v-if="item.unit" class="nums__unit">{{ item.unit }}</text>
							</view>
							<text class="nums__label">{{ item.label }}</text>
						</view>
					</view>
				</view>

				<!-- ==================== 求职漏斗 ==================== -->
				<view class="card">
					<zn-section-header title="求职漏斗" subtitle="累计口径 · 后一阶段的人必然经过前一阶段" />
					<view v-for="(item, i) in funnel" :key="item.stage" class="funnel">
						<view class="funnel__head">
							<text class="funnel__label">{{ item.label }}</text>
							<text class="funnel__count">{{ item.count }} 份</text>
						</view>
						<view class="funnel__track">
							<view class="funnel__fill" :style="funnelStyle(item, i)"></view>
						</view>
						<!-- 阶段说明来自配置（rcSeekerReport.funnel），没有配置就整行不显示 -->
						<text v-if="item.desc" class="funnel__desc">{{ item.desc }}</text>
					</view>
				</view>

				<!-- ==================== 求职力（横向进度条，不用 canvas） ==================== -->
				<view class="card">
					<zn-section-header title="求职力" subtitle="按规则计算 · 0-100 分" />
					<view v-for="(item, i) in radar" :key="item.name" class="radar">
						<view class="radar__head">
							<text class="radar__name">{{ item.name }}</text>
							<text class="radar__score">{{ item.value }} 分</text>
						</view>
						<view class="radar__bar">
							<zn-progress :percent="item.value" :height="14" :color="radarColor(i)"></zn-progress>
						</view>
						<text v-if="item.desc" class="radar__desc">{{ item.desc }}</text>
					</view>
				</view>

				<!-- ==================== 改进建议（规则算出，带序号） ==================== -->
				<view class="card">
					<zn-section-header title="改进建议" subtitle="按你的数据算出来，可直接执行" />
					<view v-for="(tip, i) in tips" :key="'tip-' + i" class="tip">
						<view class="tip__no">
							<text class="tip__no-text">{{ i + 1 }}</text>
						</view>
						<text class="tip__text">{{ tip }}</text>
					</view>
					<view v-if="!tips.length" class="tip__none">
						<text class="tip__none-text">暂时没有针对性建议</text>
					</view>
				</view>

				<!-- ==================== 通用建议（配置文案，与上面的个性化建议区分开） ==================== -->
				<view v-if="commonTips.length" class="card">
					<zn-section-header title="通用求职建议" subtitle="来自运营配置 · 不针对个人数据" />
					<view v-for="(tip, i) in commonTips" :key="'ct-' + i" class="ctip">
						<view class="ctip__dot"></view>
						<text class="ctip__text">{{ tip }}</text>
					</view>
				</view>

				<view class="report__foot">
					<text class="report__foot-text">{{ footText }}</text>
				</view>
			</view>
		</template>
	</view>
</template>

<script>
	/**
	 * 求职报告
	 *
	 * 数据来源（services/apply.js）：
	 *   getResumeReport() → {funnel, radar, tips, summary}
	 *     funnel  [{stage,label,count}]  5 个阶段，累计口径
	 *     radar   [{name,value,desc}]    5 个维度，value 为 0~100
	 *     tips    [string]               服务端按规则算出来的改进建议（不是 AI 生成）
	 *     summary {delivered,interviewed,passed,favorited,answered,completeness,interviewRate}
	 *
	 * 文案来源（services/content.js）：
	 *   getConfig('rcSeekerReport') → {title,subtitle,funnel[],radar[],tips[]}
	 *   这是「可有可无」的展示型配置，取不到就整体回落本页的本地默认文案（DEFAULT_COPY），
	 *   **不影响数据**：漏斗/求职力/建议的数字与文案始终来自上面的接口。
	 *
	 * ⚠️ 配置与接口的口径差异（这是本页最需要讲清的一处取舍）：
	 *    - 配置里的 funnel 是通用口径的描述文案（浏览职位 → 投递简历 → … → 拿到 Offer），
	 *      与接口的求职者投递状态口径（已投递 → 被查看 → … → 成功入职）**名字对不上**，
	 *      因此只能**按序号**把 desc 贴到对应阶段上，且仅在两者条数一致时才贴（否则整段不显示）；
	 *    - 配置里的 radar 只有 name/desc（没有分数），分数必须用接口的 value；
	 *      所以名字与分数以接口为准，接口没给 desc 时才用配置的 desc 补一句；
	 *    - 配置里的 tips 是运营写的通用建议，与接口按个人数据算出的 tips 性质不同，
	 *      因此分成两块展示（「改进建议」= 个性化、「通用求职建议」= 配置），不混在一起。
	 */
	import { isLogined } from '@/services/user.js'
	import { getResumeReport } from '@/services/apply.js'
	import { getConfig } from '@/services/content.js'

	/** 配置取不到时的本地默认文案（只兜底文案，不兜底数字） */
	const DEFAULT_COPY = {
		title: '我的求职报告',
		subtitle: '基于你的投递、面试与简历数据实时生成',
		funnel: [],
		radar: [],
		tips: []
	}

	/** 漏斗各段配色（与求职中心一致：越往后越深，一眼看出转化路径） */
	const FUNNEL_COLORS = [
		'linear-gradient(90deg, #5ed3d4 0%, #33c4c5 100%)',
		'linear-gradient(90deg, #33c4c5 0%, #00a6a7 100%)',
		'linear-gradient(90deg, #00a6a7 0%, #008c8d 100%)',
		'linear-gradient(90deg, #008c8d 0%, #00797b 100%)',
		'linear-gradient(90deg, #00797b 0%, #00696b 100%)'
	]

	/**
	 * 求职力各维度的颜色
	 * 用固定色而不是「按分数变色」：同一个人每次打开颜色都一样，方便横向比较各维度强弱。
	 */
	const RADAR_COLORS = [
		'linear-gradient(90deg, #5ed3d4 0%, #00a6a7 100%)',
		'linear-gradient(90deg, #6ee7b7 0%, #10b981 100%)',
		'linear-gradient(90deg, #7cc4ff 0%, #3b9dff 100%)',
		'linear-gradient(90deg, #c4a8ff 0%, #8a6cf6 100%)',
		'linear-gradient(90deg, #ffc46b 0%, #ff8f1f 100%)'
	]

	export default {
		data() {
			return {
				isLogin: false,
				loading: true,
				loadFailed: false,
				report: {
					funnel: [],
					radar: [],
					tips: [],
					summary: {}
				},
				copy: DEFAULT_COPY,
				configLoaded: false
			}
		},
		computed: {
			summary() {
				return this.report.summary || {}
			},
			/** 有没有投递数据：没有的话漏斗全 0，需要用引导代替冷冰冰的数字 */
			hasData() {
				return (this.summary.delivered || 0) > 0
			},
			funnel() {
				const rows = this.report.funnel || []
				const conf = Array.isArray(this.copy.funnel) ? this.copy.funnel : []
				// 只在条数一致时按序号补阶段说明（口径差异见文件头注释）
				const sameLength = conf.length === rows.length
				return rows.map((item, i) => {
					const desc = sameLength && conf[i] ? conf[i].desc : ''
					return {
						stage: item.stage,
						label: item.label,
						count: item.count || 0,
						desc: desc || ''
					}
				})
			},
			funnelMax() {
				const list = this.funnel.map(item => Number(item.count) || 0)
				return Math.max.apply(null, list.concat([1]))
			},
			radar() {
				const rows = this.report.radar || []
				const conf = Array.isArray(this.copy.radar) ? this.copy.radar : []
				return rows.map((item, i) => {
					const confDesc = conf[i] ? conf[i].desc : ''
					return {
						name: item.name,
						value: Math.max(0, Math.min(100, Number(item.value) || 0)),
						// 接口的 desc 更贴近真实数据，优先用；它没给才用配置的
						desc: item.desc || confDesc || ''
					}
				})
			},
			/** 个性化建议：服务端按规则算的（可能为空数组，页面已做空态） */
			tips() {
				return this.report.tips || []
			},
			/** 通用建议：只在配置取到且有内容时展示 */
			commonTips() {
				return Array.isArray(this.copy.tips) ? this.copy.tips : []
			},
			overviewSubtitle() {
				return this.hasData ? '口径：投递 / 面试 / Offer / 收藏 / 练习' : '还没有投递，部分指标暂无意义'
			},
			/**
			 * 底部说明：配置没取到时如实说明「正在用本地默认文案」，
			 * 而不是让用户以为看到的就是运营配的文案。
			 */
			footText() {
				if (!this.configLoaded) return '报告由规则实时计算（不消耗 AI 额度）· 文案配置未取到，使用本地默认文案'
				return '报告由规则实时计算（不消耗 AI 额度）；深度分析请用 AI 求职助手'
			},
			/**
			 * 数字概览格
			 * ⚠️ 区分两种 0：
			 *   「没有投递所以还是 0」的指标显示 —（避免让用户以为是自己做得差），
			 *   而收藏 / 练习 / 简历完整度与投递无关，始终显示真实值。
			 */
			cells() {
				const s = this.summary
				const dash = '—'
				return [
					{ key: 'delivered', label: '累计投递', value: this.hasData ? (s.delivered || 0) : dash, unit: '份', none: !this.hasData },
					{ key: 'interviewed', label: '进入面试', value: this.hasData ? (s.interviewed || 0) : dash, unit: '场', none: !this.hasData },
					{ key: 'passed', label: '面试通过', value: this.hasData ? (s.passed || 0) : dash, unit: '个', none: !this.hasData },
					{ key: 'favorited', label: '收藏职位', value: s.favorited || 0, unit: '个', none: false },
					{ key: 'answered', label: '面试题练习', value: s.answered || 0, unit: '题', none: false },
					{ key: 'completeness', label: '简历完整度', value: s.completeness || 0, unit: '%', none: false },
					{ key: 'rate', label: '面试转化率', value: this.hasData ? (s.interviewRate || 0) : dash, unit: '%', none: !this.hasData }
				]
			}
		},
		onLoad() {
			this.refresh()
		},
		onShow() {
			// 从投递/简历页返回时数据可能已变（比如刚补完简历），重新拉一次
			if (this.isLogin) this.refresh()
		},
		onPullDownRefresh() {
			this.refresh(true)
		},
		methods: {
			async refresh(fromPull) {
				this.isLogin = isLogined()
				if (!this.isLogin) {
					this.loading = false
					this.loadFailed = false
					this.report = { funnel: [], radar: [], tips: [], summary: {} }
					if (fromPull) uni.stopPullDownRefresh()
					return
				}

				this.loading = true
				// 配置是可有可无的：单独包一层 catch，绝不让配置失败拖垮整页数据
				const [reportRes, copyRes] = await Promise.all([
					getResumeReport().then(data => ({ ok: true, data })).catch(() => ({ ok: false })),
					this.loadCopy()
				])

				if (reportRes.ok) {
					const data = reportRes.data || {}
					this.report = {
						funnel: data.funnel || [],
						radar: data.radar || [],
						tips: data.tips || [],
						summary: data.summary || {}
					}
					this.loadFailed = false
				} else {
					// 纯接口模式：失败就是失败，不编报告
					this.report = { funnel: [], radar: [], tips: [], summary: {} }
					this.loadFailed = true
				}
				this.copy = copyRes
				this.loading = false

				if (fromPull) {
					uni.stopPullDownRefresh()
					uni.showToast({ title: this.loadFailed ? '刷新失败' : '已更新', icon: 'none' })
				}
			},

			/**
			 * 读取报告文案配置
			 * 任何异常（未种子 / 网络失败 / 结构不对）都回落 DEFAULT_COPY，
			 * 这样报告页在配置没种子的环境里依然完整可用。
			 */
			async loadCopy() {
				try {
					const value = await getConfig('rcSeekerReport')
					if (!value || typeof value !== 'object') {
						this.configLoaded = false
						return DEFAULT_COPY
					}
					this.configLoaded = true
					return {
						title: value.title || DEFAULT_COPY.title,
						subtitle: value.subtitle || DEFAULT_COPY.subtitle,
						funnel: Array.isArray(value.funnel) ? value.funnel : [],
						radar: Array.isArray(value.radar) ? value.radar : [],
						tips: Array.isArray(value.tips) ? value.tips : []
					}
				} catch (e) {
					this.configLoaded = false
					return DEFAULT_COPY
				}
			},

			/** 漏斗某段宽度：按 count 占最大值的比例（非零值至少 6%，否则细到看不见） */
			funnelStyle(item, index) {
				const count = Number(item.count) || 0
				const percent = count ? Math.max(6, Math.round((count / this.funnelMax) * 100)) : 2
				return {
					width: percent + '%',
					background: count ? FUNNEL_COLORS[index % FUNNEL_COLORS.length] : '#f2f4f7'
				}
			},

			radarColor(index) {
				return RADAR_COLORS[index % RADAR_COLORS.length]
			},

			/** 职位首页是 tab 页：reLaunch 才能同步底部 tabBar 高亮 */
			goJobs() {
				uni.reLaunch({ url: '/pages/index/index' })
			},

			goLogin() {
				uni.navigateTo({ url: '/pages/login/login' })
			}
		}
	}
</script>

<style lang="scss" scoped>
	.report__body {
		padding: $zn-gap $zn-page-padding 40rpx;
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

	/* ==================== 头部 ==================== */
	.hero {
		background: linear-gradient(135deg, #00a6a7 0%, #008c8d 55%, #00696b 100%);
		border-radius: $zn-radius-lg;
		padding: $zn-gap-lg $zn-gap;
		box-shadow: $zn-shadow-lg;
	}

	.hero__title {
		display: block;
		font-size: 38rpx;
		font-weight: 700;
		color: #ffffff;
	}

	.hero__sub {
		display: block;
		font-size: 22rpx;
		color: rgba(255, 255, 255, 0.86);
		margin-top: 10rpx;
		line-height: 32rpx;
	}

	.hero__rate {
		display: flex;
		flex-direction: row;
		align-items: baseline;
		margin-top: 24rpx;
		padding-top: 22rpx;
		border-top: 1rpx solid rgba(255, 255, 255, 0.24);
	}

	.hero__rate-num {
		font-size: 52rpx;
		font-weight: 700;
		color: #ffffff;
		line-height: 58rpx;
	}

	.hero__rate-unit {
		font-size: 24rpx;
		color: rgba(255, 255, 255, 0.9);
		margin-left: 4rpx;
	}

	.hero__rate-label {
		font-size: 21rpx;
		color: rgba(255, 255, 255, 0.8);
		margin-left: $zn-gap;
	}

	/* ==================== 空数据引导 ==================== */
	.guide {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: $zn-theme-light;
		border-radius: $zn-radius-lg;
		padding: 24rpx;
		margin-top: $zn-gap;
	}

	.guide__info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin-left: 14rpx;
	}

	.guide__title {
		font-size: 26rpx;
		font-weight: 600;
		color: $zn-theme-dark;
	}

	.guide__desc {
		font-size: 22rpx;
		color: $zn-text-sub;
		margin-top: 8rpx;
		line-height: 32rpx;
	}

	.guide__btn {
		flex-shrink: 0;
		height: 60rpx;
		padding: 0 22rpx;
		margin-left: $zn-gap-sm;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;
	}

	.guide__btn-text {
		font-size: 24rpx;
		font-weight: 600;
		color: #ffffff;
	}

	/* ==================== 通用白卡 ==================== */
	.card {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 0 $zn-gap $zn-gap;
		margin-top: $zn-gap;
		box-shadow: $zn-shadow-sm;
	}

	/* ==================== 数字概览 ==================== */
	.nums {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
	}

	.nums__cell {
		width: 33.33%;
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 18rpx 0;
	}

	.nums__num {
		display: flex;
		flex-direction: row;
		align-items: baseline;
	}

	.nums__value {
		font-size: 40rpx;
		font-weight: 700;
		color: $zn-theme-dark;
		line-height: 46rpx;

		&.is-none {
			color: $zn-text-light;
		}
	}

	.nums__unit {
		font-size: 20rpx;
		color: $zn-text-grey;
		margin-left: 4rpx;
	}

	.nums__label {
		font-size: 21rpx;
		color: $zn-text-grey;
		margin-top: 6rpx;
	}

	/* ==================== 漏斗 ==================== */
	.funnel {
		margin-bottom: 22rpx;

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

	.funnel__desc {
		display: block;
		font-size: 21rpx;
		color: $zn-text-grey;
		margin-top: 10rpx;
		line-height: 30rpx;
	}

	/* ==================== 求职力 ==================== */
	.radar {
		margin-bottom: 24rpx;

		&:last-child {
			margin-bottom: 0;
		}
	}

	.radar__head {
		display: flex;
		flex-direction: row;
		align-items: baseline;
		justify-content: space-between;
	}

	.radar__name {
		font-size: 26rpx;
		color: $zn-text-main;
	}

	.radar__score {
		font-size: 24rpx;
		font-weight: 700;
		color: $zn-theme-dark;
	}

	.radar__bar {
		margin-top: 10rpx;
	}

	.radar__desc {
		display: block;
		font-size: 21rpx;
		color: $zn-text-grey;
		margin-top: 8rpx;
		line-height: 30rpx;
	}

	/* ==================== 建议 ==================== */
	.tip {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		padding: 16rpx 0;
		border-bottom: 1rpx solid $zn-line;

		&:last-child {
			border-bottom: none;
		}
	}

	.tip__no {
		width: 40rpx;
		height: 40rpx;
		border-radius: 50%;
		background-color: $zn-theme-light;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		margin-top: 2rpx;
	}

	.tip__no-text {
		font-size: 22rpx;
		font-weight: 700;
		color: $zn-theme-dark;
	}

	.tip__text {
		flex: 1;
		min-width: 0;
		font-size: 25rpx;
		color: $zn-text-main;
		line-height: 38rpx;
		margin-left: 16rpx;
	}

	.tip__none {
		padding: 16rpx 0;
	}

	.tip__none-text {
		font-size: 24rpx;
		color: $zn-text-light;
	}

	.ctip {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		padding: 12rpx 0;
	}

	.ctip__dot {
		width: 12rpx;
		height: 12rpx;
		border-radius: 50%;
		background-color: $zn-theme;
		flex-shrink: 0;
		margin: 14rpx 14rpx 0 0;
	}

	.ctip__text {
		flex: 1;
		min-width: 0;
		font-size: 24rpx;
		color: $zn-text-sub;
		line-height: 38rpx;
	}

	/* ==================== 底部 ==================== */
	.report__foot {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: $zn-gap-lg 0 10rpx;
	}

	.report__foot-text {
		font-size: 21rpx;
		color: $zn-text-light;
		text-align: center;
		line-height: 32rpx;
	}
</style>
