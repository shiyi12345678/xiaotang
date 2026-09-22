<template>
	<view class="zn-page zn-page--no-tabbar hrapps">
		<zn-nav-bar title="收到简历" :show-back="true" border />

		<!-- ==================== 状态筛选（横向滚动 + 角标） ====================
			 角标数字来自服务端返回的 counts，不是前端自己数当前页 —— 当前页只有 10 条，
			 自己数出来的数字会随翻页变化，那是错的。 -->
		<scroll-view class="hrapps__tabs" scroll-x :show-scrollbar="false">
			<view class="hrapps__tabs-inner">
				<view v-for="(tab, i) in tabs" :key="tab.key" class="hrapps__tab"
					:class="{ 'is-active': tabIndex === i }" hover-class="zn-hover" @tap="switchTab(i)">
					<text class="hrapps__tab-text">{{ tab.text }}</text>
					<text v-if="countOf(tab.key) > 0" class="hrapps__tab-badge">{{ countOf(tab.key) }}</text>
					<view v-if="tabIndex === i" class="hrapps__tab-bar"></view>
				</view>
			</view>
		</scroll-view>

		<!-- 只看某个职位时给一句明确提示，避免 HR 以为简历变少了 -->
		<view v-if="jobId" class="filter-tip">
			<uni-icons type="info" :size="14" color="#00A6A7"></uni-icons>
			<text class="filter-tip__text zn-ellipsis">仅显示「{{ filterJobTitle }}」收到的简历</text>
			<text class="filter-tip__clear" @tap="clearJobFilter">查看全部</text>
		</view>

		<view class="hrapps__body">
			<!-- ---------- 加载中 ---------- -->
			<view v-if="loading" class="hrapps__state">
				<text class="hrapps__state-text">正在加载简历…</text>
			</view>

			<!-- ---------- 加载失败：可重试 ---------- -->
			<zn-empty v-else-if="failed" icon="info" text="简历列表加载失败" :desc="failedMsg"
				btn-text="重新加载" @action="reload" />

			<!-- ---------- 空态 ---------- -->
			<zn-empty v-else-if="!list.length" icon="email"
				:text="tabIndex === 0 ? '还没有收到简历' : '该状态下没有简历'"
				:desc="tabIndex === 0 ? '职位上架后，求职者的投递会出现在这里' : '换个状态筛选看看'" />

			<!-- ---------- 列表 ---------- -->
			<block v-else>
				<view v-for="item in list" :key="item.id" class="cad" hover-class="zn-hover" @tap="goCandidate(item)">
					<!-- 候选人用 zn-avatar（姓名首字渐变圆），不是公司 Logo -->
					<view class="cad__top">
						<zn-avatar :name="nameOf(item)" :size="88" />
						<view class="cad__main">
							<view class="cad__row">
								<text class="cad__name zn-ellipsis">{{ nameOf(item) }}</text>
								<!-- HR 视角状态文案一律用服务端 statusText（如 submitted → 待处理） -->
								<zn-tag :text="item.statusText" :type="tagType(item.statusType)" size="xs" />
							</view>
							<text class="cad__meta zn-ellipsis">{{ metaOf(item) }}</text>
							<view class="cad__salary-row">
								<text class="cad__salary">{{ candidate(item).expectedSalaryText || '薪资面议' }}</text>
								<text class="cad__exp">期望：{{ candidate(item).expectedPosition || '未填写' }}</text>
							</view>
						</view>
					</view>

					<!-- 简历完整度：低完整度的简历要提醒 HR 先沟通再约面 -->
					<view class="cad__progress">
						<text class="cad__progress-label">简历完整度</text>
						<view class="cad__progress-bar">
							<zn-progress :percent="candidate(item).completeness || 0" :height="8" />
						</view>
						<text class="cad__progress-num">{{ candidate(item).completeness || 0 }}%</text>
					</view>

					<view class="cad__foot">
						<text class="cad__job zn-ellipsis">投递职位：{{ item.jobTitle || '—' }}</text>
						<text class="cad__time">{{ item.createdText }}</text>
					</view>
				</view>

				<view class="hrapps__foot">
					<text class="hrapps__foot-text">{{ footText }}</text>
				</view>
			</block>
		</view>
	</view>
</template>

<script>
	/**
	 * 收到简历（投递列表）
	 *
	 * 接口：GET /hr/applications?jobId=&status=&page=&pageSize=（services/hr.js → getApplications）
	 *   → { list, total, page, pageSize, hasMore, counts }
	 *
	 * ⚠️ 状态文案：服务端按角色翻译（schemas/apply.py 的 HR_STATUS_TEXT），
	 *    同一份 submitted 求职者看「已投递」、HR 看「待处理」，
	 *    所以列表项直接用 item.statusText，绝不在这里自己写一套。
	 *
	 * ⚠️ 但筛选标签的文字必须本地写一份：某个状态可能 0 条，
	 *    此时服务端不会返回任何该状态的 statusText（它是逐条下发的），
	 *    标签文案没有可用的服务端来源。这里的 8 个标签名与 HR_STATUS_TEXT 保持同一口径，
	 *    改动时要两边同步（这是本页唯一一处「文案在前端」的地方，特此标注）。
	 *
	 * ⚠️ 不要在这里预加载候选人详情（getHrApplicationDetail）：
	 *    那个接口会把投递从「待处理」推进为「已查看」，批量预加载会把状态刷成一片「已查看」。
	 *    详情只在候选人详情页里按需调用。
	 *
	 * ⚠️ 数据隔离：服务端按绑定的公司过滤，前端不传 companyId（jobId 只是筛选条件）。
	 */
	import { getApplications } from '@/services/hr.js'

	/** 筛选项：key 为状态值，'' 表示全部；文本与 HR_STATUS_TEXT 同口径 */
	const TABS = [
		{ key: '', text: '全部' },
		{ key: 'submitted', text: '待处理' },
		{ key: 'viewed', text: '已查看' },
		{ key: 'chatting', text: '沟通中' },
		{ key: 'interview', text: '待面试' },
		{ key: 'passed', text: '面试通过' },
		{ key: 'hired', text: '已入职' },
		{ key: 'rejected', text: '不合适' },
		{ key: 'withdrawn', text: '候选人撤回' }
	]

	const TAG_TYPE = { success: 'green', warning: 'orange', danger: 'red', info: 'gray' }

	const PAGE_SIZE = 10

	export default {
		data() {
			return {
				tabs: TABS,
				tabIndex: 0,
				jobId: '',
				list: [],
				counts: {},
				total: 0,
				page: 1,
				hasMore: false,
				loading: true,
				ready: false,
				loadingMore: false,
				failed: false,
				failedMsg: ''
			}
		},
		computed: {
			currentStatus() {
				return this.tabs[this.tabIndex].key
			},
			/** 列表里带的职位名（投递行存了职位快照），用来提示当前筛的是哪个职位 */
			filterJobTitle() {
				const hit = this.list.find(it => it.jobTitle)
				return hit ? hit.jobTitle : this.jobId
			},
			footText() {
				if (this.loadingMore) return '正在加载更多…'
				if (this.hasMore) return '上拉加载更多'
				return '已到底部 · 共 ' + this.total + ' 份简历'
			}
		},
		onLoad(options) {
			this.jobId = (options && options.jobId) || ''
			// 工作台的数据卡片会带 status 进来（待处理 / 待面试 / 已入职）
			const status = (options && options.status) || ''
			if (status) {
				const i = TABS.findIndex(t => t.key === status)
				if (i > -1) this.tabIndex = i
			}
			this.reload()
		},
		onShow() {
			// 从候选人详情返回时状态可能已变（已查看/沟通中/不合适…），必须重拉
			if (this.ready) this.reload()
		},
		async onPullDownRefresh() {
			try {
				await this.reload()
			} finally {
				uni.stopPullDownRefresh()
			}
		},
		onReachBottom() {
			this.loadMore()
		},
		methods: {
			/* ---------------- 数据 ---------------- */
			async reload() {
				this.loading = !this.ready
				this.failed = false
				this.page = 1
				try {
					const res = await this.fetch(1)
					this.list = res.list
					this.counts = res.counts
					this.total = res.total
					this.hasMore = res.hasMore
				} catch (e) {
					if (this.handleUnbound(e)) return
					this.failed = true
					this.failedMsg = (e && e.message) || '请检查服务端是否已启动'
					this.list = []
					this.counts = {}
				} finally {
					this.loading = false
					this.ready = true
				}
			},
			async loadMore() {
				if (this.loadingMore || !this.hasMore || this.loading) return
				this.loadingMore = true
				const next = this.page + 1
				try {
					const res = await this.fetch(next)
					const exists = {}
					this.list.forEach(it => { exists[it.id] = true })
					this.list = this.list.concat(res.list.filter(it => !exists[it.id]))
					this.counts = res.counts
					this.total = res.total
					this.hasMore = res.hasMore
					this.page = next
				} catch (e) {
					this.handleUnbound(e)
				} finally {
					this.loadingMore = false
				}
			},
			/** 统一取数：counts 每次都会带上（不随筛选变化，始终是该公司/该职位的全量分布） */
			async fetch(page) {
				const res = await getApplications({
					jobId: this.jobId,
					status: this.currentStatus,
					page,
					pageSize: PAGE_SIZE
				})
				return {
					list: (res && res.list) || [],
					counts: (res && res.counts) || {},
					total: (res && res.total) || 0,
					hasMore: !!(res && res.hasMore)
				}
			},
			handleUnbound(err) {
				if (!err || (err.code !== 40301 && err.status !== 403)) return false
				uni.reLaunch({ url: '/pages/hr/bind' })
				return true
			},

			/* ---------------- 展示辅助 ---------------- */
			candidate(item) {
				return item.candidate || {}
			},
			nameOf(item) {
				return this.candidate(item).name || '匿名候选人'
			},
			metaOf(item) {
				const c = this.candidate(item)
				return [c.educationLevel, c.workYearsText, c.expectedCity].filter(Boolean).join(' · ') || '简历信息待完善'
			},
			countOf(key) {
				// 全部标签不显示角标（那是所有状态之和，意义不大且容易被误读）
				if (!key) return 0
				return this.counts[key] || 0
			},
			tagType(type) {
				return TAG_TYPE[type] || 'gray'
			},

			/* ---------------- 交互 ---------------- */
			switchTab(i) {
				if (this.tabIndex === i) return
				this.tabIndex = i
				this.list = []
				this.reload()
			},
			clearJobFilter() {
				this.jobId = ''
				this.list = []
				this.reload()
			},
			goCandidate(item) {
				uni.navigateTo({ url: '/pages/hr/candidate?id=' + item.id })
			}
		}
	}
</script>

<style lang="scss" scoped>
	.hrapps__tabs {
		background-color: $zn-bg-card;
		white-space: nowrap;
	}

	.hrapps__tabs-inner {
		display: flex;
		flex-direction: row;
		padding: 0 $zn-page-padding;
	}

	.hrapps__tab {
		flex-shrink: 0;
		height: 88rpx;
		padding: 0 22rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
		position: relative;
	}

	.hrapps__tab-text {
		font-size: $zn-font-sm;
		color: $zn-text-sub;
	}

	.hrapps__tab.is-active .hrapps__tab-text {
		color: $zn-theme;
		font-weight: 700;
	}

	.hrapps__tab-badge {
		margin-left: 8rpx;
		min-width: 30rpx;
		height: 30rpx;
		padding: 0 8rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		color: $zn-text-grey;
		font-size: 18rpx;
		line-height: 30rpx;
		text-align: center;
	}

	.hrapps__tab.is-active .hrapps__tab-badge {
		background-color: $zn-theme-light;
		color: $zn-theme-deep;
	}

	.hrapps__tab-bar {
		position: absolute;
		left: 50%;
		bottom: 10rpx;
		margin-left: -24rpx;
		width: 48rpx;
		height: 6rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
	}

	/* ---------------- 职位筛选提示 ---------------- */
	.filter-tip {
		margin: $zn-gap-sm $zn-page-padding 0;
		padding: 16rpx $zn-gap-sm;
		border-radius: $zn-radius;
		background-color: $zn-theme-lighter;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.filter-tip__text {
		flex: 1;
		min-width: 0;
		margin-left: 8rpx;
		font-size: $zn-font-xs;
		color: $zn-theme-dark;
	}

	.filter-tip__clear {
		flex-shrink: 0;
		margin-left: 12rpx;
		font-size: $zn-font-xs;
		color: $zn-theme;
		text-decoration: underline;
	}

	.hrapps__body {
		padding: $zn-gap $zn-page-padding 0;
	}

	.hrapps__state {
		padding: 120rpx 0;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.hrapps__state-text {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
	}

	/* ---------------- 候选人卡 ---------------- */
	.cad {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: $zn-gap;
		margin-bottom: $zn-gap;
	}

	.cad__top {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
	}

	.cad__main {
		flex: 1;
		min-width: 0;
		margin-left: $zn-gap-sm;
		display: flex;
		flex-direction: column;
	}

	.cad__row {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.cad__name {
		max-width: 300rpx;
		font-size: $zn-font-md;
		font-weight: 700;
		color: $zn-text-title;
		margin-right: 12rpx;
	}

	.cad__meta {
		margin-top: 8rpx;
		font-size: $zn-font-xs;
		color: $zn-text-sub;
	}

	.cad__salary-row {
		margin-top: 10rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.cad__salary {
		font-size: $zn-font-sm;
		font-weight: 700;
		color: $zn-price;
		flex-shrink: 0;
	}

	.cad__exp {
		flex: 1;
		min-width: 0;
		margin-left: 14rpx;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	/* ---------------- 完整度 ---------------- */
	.cad__progress {
		margin-top: $zn-gap-sm;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.cad__progress-label {
		flex-shrink: 0;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
		margin-right: 12rpx;
	}

	.cad__progress-bar {
		flex: 1;
		min-width: 0;
	}

	.cad__progress-num {
		flex-shrink: 0;
		margin-left: 12rpx;
		font-size: $zn-font-xs;
		color: $zn-theme-deep;
	}

	/* ---------------- 底部 ---------------- */
	.cad__foot {
		margin-top: $zn-gap-sm;
		padding-top: $zn-gap-sm;
		border-top: 1rpx solid $zn-line;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.cad__job {
		flex: 1;
		min-width: 0;
		font-size: $zn-font-xs;
		color: $zn-text-sub;
	}

	.cad__time {
		flex-shrink: 0;
		margin-left: 12rpx;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	.hrapps__foot {
		padding: $zn-gap 0 $zn-gap-lg;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.hrapps__foot-text {
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}
</style>
