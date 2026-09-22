<template>
	<view class="zn-page zn-page--no-tabbar hrivs">
		<zn-nav-bar title="面试安排" :show-back="true" border />

		<!-- ==================== 状态筛选 ==================== -->
		<view class="hrivs__tabs">
			<view v-for="(tab, i) in tabs" :key="tab.key" class="hrivs__tab"
				:class="{ 'is-active': tabIndex === i }" hover-class="zn-hover" @tap="switchTab(i)">
				<text class="hrivs__tab-text">{{ tab.text }}</text>
				<view v-if="tabIndex === i" class="hrivs__tab-bar"></view>
			</view>
		</view>

		<view class="hrivs__body">
			<!-- ---------- 加载中 ---------- -->
			<view v-if="loading" class="hrivs__state">
				<text class="hrivs__state-text">正在加载面试安排…</text>
			</view>

			<!-- ---------- 加载失败：可重试 ---------- -->
			<zn-empty v-else-if="failed" icon="info" text="面试安排加载失败" :desc="failedMsg"
				btn-text="重新加载" @action="reload" />

			<!-- ---------- 空态 ---------- -->
			<zn-empty v-else-if="!list.length" icon="calendar"
				:text="tabIndex === 0 ? '还没有面试安排' : '该状态下没有面试'"
				:desc="tabIndex === 0 ? '在候选人详情页发出面试邀约后会出现在这里' : '换个状态筛选看看'" />

			<!-- ---------- 面试列表（服务端已按时间正序：先面谁排在前面） ---------- -->
			<block v-else>
				<view v-for="item in list" :key="item.id" class="ivc" hover-class="zn-hover"
					@tap="goCandidate(item)">
					<!-- 时间条 -->
					<view class="ivc__time">
						<text class="ivc__date">{{ dateOf(item) }}</text>
						<text class="ivc__clock">{{ clockOf(item) }}</text>
						<text class="ivc__dur">{{ item.durationMin }} 分钟</text>
					</view>

					<view class="ivc__main">
						<view class="ivc__row">
							<text class="ivc__round zn-ellipsis">{{ item.roundName || ('第' + item.roundNo + '轮') }}</text>
							<zn-tag :text="item.statusText" :type="statusTagType(item.status)" size="xs" />
						</view>

						<view class="ivc__person">
							<zn-avatar :name="candidateName(item)" :size="56" />
							<text class="ivc__cand zn-ellipsis">{{ candidateName(item) }}</text>
							<text class="ivc__candmeta zn-ellipsis">{{ candidateMeta(item) }}</text>
						</view>

						<text class="ivc__job zn-ellipsis">面试职位：{{ item.jobTitle || '—' }}</text>

						<view class="ivc__kv">
							<text class="ivc__k">方式</text>
							<text class="ivc__v">{{ item.modeText }}</text>
						</view>
						<view v-if="item.address" class="ivc__kv">
							<text class="ivc__k">地点</text>
							<text class="ivc__v zn-ellipsis">{{ item.address }}</text>
						</view>
						<view v-if="item.onlineLink" class="ivc__kv">
							<text class="ivc__k">链接</text>
							<text class="ivc__v zn-ellipsis">{{ item.onlineLink }}</text>
							<!-- 复制按钮：@tap.stop 防止冒泡到卡片跳转候选人详情 -->
							<view class="ivc__copy" hover-class="zn-hover" @tap.stop="copyLink(item)">
								<text class="ivc__copy-text">复制链接</text>
							</view>
						</view>
						<view v-if="item.interviewer" class="ivc__kv">
							<text class="ivc__k">面试官</text>
							<text class="ivc__v">{{ item.interviewer }}</text>
						</view>
						<view v-if="item.contact" class="ivc__kv">
							<text class="ivc__k">联系方式</text>
							<text class="ivc__v">{{ item.contact }}</text>
						</view>
						<view v-if="item.remark" class="ivc__remark">
							<text class="ivc__remark-text">{{ item.remark }}</text>
						</view>
					</view>
				</view>

				<view class="hrivs__foot">
					<text class="hrivs__foot-text">{{ footText }}</text>
				</view>
			</block>
		</view>
	</view>
</template>

<script>
	/**
	 * 面试安排（企业 HR 视角）
	 *
	 * 接口：GET /hr/interviews?status=&page=&pageSize=（services/hr.js → getInterviews）
	 *   → list 元素 = 面试邀约（interview_out）+ jobTitle + candidate（简历摘要）
	 *
	 * ⚠️ 服务端已按面试时间**正序**返回（HR 关心「接下来面谁」），
	 *    前端不要再按其他维度重排，否则翻页时会看到乱序。
	 *
	 * ⚠️ 点卡片进候选人详情：会调 getHrApplicationDetail，
	 *    该接口只在投递还能流转到 viewed 时推进状态（即「待处理」→「已查看」）。
	 *    面试阶段的状态是 interview，不在 ALLOWED_TRANSITIONS['interview'] 里，
	 *    所以从本页点进去不会把「待面试」改回「已查看」。
	 *
	 * ⚠️ 数据隔离：服务端按绑定的公司过滤面试，前端不传 companyId。
	 */
	import { getInterviews } from '@/services/hr.js'

	/** 筛选标签：与 interview_out 的 statusText 同口径（pending/confirmed/finished/canceled） */
	const TABS = [
		{ key: '', text: '全部' },
		{ key: 'pending', text: '待确认' },
		{ key: 'confirmed', text: '已确认' },
		{ key: 'finished', text: '已结束' },
		{ key: 'canceled', text: '已取消' }
	]

	const PAGE_SIZE = 10

	/** 面试状态 → 徽标配色（待确认=橙、已确认=绿、已结束=灰、已取消=红） */
	const STATUS_TAG = {
		pending: 'orange',
		confirmed: 'green',
		finished: 'gray',
		canceled: 'red'
	}

	export default {
		data() {
			return {
				tabs: TABS,
				tabIndex: 0,
				list: [],
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
			footText() {
				if (this.loadingMore) return '正在加载更多…'
				if (this.hasMore) return '上拉加载更多'
				return '已到底部 · 共 ' + this.total + ' 场面试'
			}
		},
		onLoad(options) {
			// 支持从工作台的「待面试」卡片直接带状态进来
			const status = (options && options.status) || ''
			if (status) {
				const i = TABS.findIndex(t => t.key === status)
				if (i > -1) this.tabIndex = i
			}
			this.reload()
		},
		onShow() {
			// 从候选人详情发完邀约返回时，新面试要能立刻出现
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
					this.total = res.total
					this.hasMore = res.hasMore
				} catch (e) {
					if (this.handleUnbound(e)) return
					this.failed = true
					this.failedMsg = (e && e.message) || '请检查服务端是否已启动'
					this.list = []
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
					this.total = res.total
					this.hasMore = res.hasMore
					this.page = next
				} catch (e) {
					this.handleUnbound(e)
				} finally {
					this.loadingMore = false
				}
			},
			async fetch(page) {
				const res = await getInterviews({
					status: this.currentStatus,
					page,
					pageSize: PAGE_SIZE
				})
				return {
					list: (res && res.list) || [],
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
			/** 服务端 timeText 形如「09月20日 14:30」，拆成日期/时刻两行更好扫读 */
			dateOf(item) {
				const text = item.timeText || ''
				const parts = text.split(' ')
				return parts[0] || '待定'
			},
			clockOf(item) {
				const text = item.timeText || ''
				const parts = text.split(' ')
				return parts[1] || ''
			},
			candidateName(item) {
				return (item.candidate && item.candidate.name) || '匿名候选人'
			},
			candidateMeta(item) {
				const c = item.candidate || {}
				return [c.educationLevel, c.workYearsText, c.expectedPosition].filter(Boolean).join(' · ') || '简历信息待完善'
			},
			statusTagType(status) {
				return STATUS_TAG[status] || 'gray'
			},

			/* ---------------- 交互 ---------------- */
			switchTab(i) {
				if (this.tabIndex === i) return
				this.tabIndex = i
				this.list = []
				this.reload()
			},
			copyLink(item) {
				if (!item.onlineLink) return
				uni.setClipboardData({
					data: item.onlineLink,
					success: () => uni.showToast({ title: '链接已复制', icon: 'none' })
				})
			},
			goCandidate(item) {
				if (!item.applicationId) return
				uni.navigateTo({ url: '/pages/hr/candidate?id=' + item.applicationId })
			}
		}
	}
</script>

<style lang="scss" scoped>
	.hrivs__tabs {
		display: flex;
		flex-direction: row;
		background-color: $zn-bg-card;
		padding: 0 $zn-page-padding;
	}

	.hrivs__tab {
		flex: 1;
		height: 88rpx;
		display: flex;
		align-items: center;
		justify-content: center;
		position: relative;
	}

	.hrivs__tab-text {
		font-size: $zn-font-sm;
		color: $zn-text-sub;
	}

	.hrivs__tab.is-active .hrivs__tab-text {
		color: $zn-theme;
		font-weight: 700;
	}

	.hrivs__tab-bar {
		position: absolute;
		bottom: 8rpx;
		width: 48rpx;
		height: 6rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
	}

	.hrivs__body {
		padding: $zn-gap $zn-page-padding 0;
	}

	.hrivs__state {
		padding: 120rpx 0;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.hrivs__state-text {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
	}

	/* ---------------- 面试卡 ---------------- */
	.ivc {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: $zn-gap;
		margin-bottom: $zn-gap;
		display: flex;
		flex-direction: row;
	}

	.ivc__time {
		width: 168rpx;
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 12rpx 0;
		border-radius: $zn-radius;
		background-color: $zn-theme-lighter;
	}

	.ivc__date {
		font-size: $zn-font-xs;
		color: $zn-text-sub;
	}

	.ivc__clock {
		margin-top: 6rpx;
		font-size: $zn-font-lg;
		font-weight: 700;
		color: $zn-theme-deep;
	}

	.ivc__dur {
		margin-top: 6rpx;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	.ivc__main {
		flex: 1;
		min-width: 0;
		margin-left: $zn-gap-sm;
		display: flex;
		flex-direction: column;
	}

	.ivc__row {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.ivc__round {
		flex: 1;
		min-width: 0;
		font-size: $zn-font-md;
		font-weight: 700;
		color: $zn-text-title;
		margin-right: 12rpx;
	}

	.ivc__person {
		margin-top: 12rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.ivc__cand {
		max-width: 180rpx;
		margin-left: 12rpx;
		font-size: $zn-font-sm;
		font-weight: 600;
		color: $zn-text-main;
	}

	.ivc__candmeta {
		flex: 1;
		min-width: 0;
		margin-left: 12rpx;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
	}

	.ivc__job {
		margin-top: 10rpx;
		font-size: $zn-font-xs;
		color: $zn-text-sub;
	}

	.ivc__kv {
		margin-top: 8rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.ivc__k {
		width: 110rpx;
		flex-shrink: 0;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	.ivc__v {
		flex: 1;
		min-width: 0;
		font-size: $zn-font-xs;
		color: $zn-text-sub;
	}

	.ivc__copy {
		flex-shrink: 0;
		margin-left: 12rpx;
		height: 48rpx;
		padding: 0 18rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-theme-light;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.ivc__copy-text {
		font-size: $zn-font-xs;
		color: $zn-theme-deep;
	}

	.ivc__remark {
		margin-top: 12rpx;
		padding: 12rpx;
		border-radius: $zn-radius-sm;
		background-color: $zn-bg-grey;
	}

	.ivc__remark-text {
		font-size: $zn-font-xs;
		color: $zn-text-sub;
		line-height: 38rpx;
	}

	.hrivs__foot {
		padding: $zn-gap 0 $zn-gap-lg;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.hrivs__foot-text {
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}
</style>
