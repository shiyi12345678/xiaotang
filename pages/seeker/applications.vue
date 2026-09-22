<template>
	<view class="zn-page zn-page--no-tabbar">
		<!-- ==================== 顶部导航 ==================== -->
		<zn-nav-bar title="我的投递" show-back border />

		<!-- ==================== 状态筛选（横向滚动，7 个标签一屏放不下） ==================== -->
		<scroll-view class="filter" scroll-x :show-scrollbar="false">
			<view class="filter__inner">
				<view v-for="tab in tabs" :key="tab.key || 'all'" class="filter__item"
					:class="{ 'is-active': status === tab.key }" hover-class="zn-hover" @tap="switchTab(tab.key)">
					<text class="filter__text">{{ tab.text }}</text>
					<view v-if="status === tab.key" class="filter__bar"></view>
				</view>
			</view>
		</scroll-view>

		<!-- ==================== 内容区 ==================== -->
		<view class="apps__body">
			<!-- 未登录：投递记录是账号私有数据（接口 auth: true），只给登录引导 -->
			<zn-empty v-if="!isLogin" icon="person" text="登录后查看我的投递"
				desc="投递进度与面试邀约都跟随账号" btn-text="去登录" @action="goLogin" />

			<!-- 加载中 -->
			<view v-else-if="loading" class="state">
				<text class="state__text">正在加载投递记录…</text>
			</view>

			<!-- 加载失败：可点击重试（不做 mock 兜底） -->
			<view v-else-if="loadFailed" class="state state--fail" hover-class="zn-hover" @tap="refresh">
				<uni-icons type="refresh" :size="18" color="#ff4d4f"></uni-icons>
				<text class="state__text state__text--fail">投递记录加载失败，点击重试</text>
			</view>

			<!-- 空态：按当前筛选给不同引导（全部为空才引导去投递） -->
			<zn-empty v-else-if="!list.length" :icon="emptyConf.icon" :text="emptyConf.text"
				:desc="emptyConf.desc" :btn-text="emptyConf.btnText" @action="onEmptyAction" />

			<template v-else>
				<view class="apps__count">
					<text class="apps__count-text">{{ countText }}</text>
				</view>

				<!-- ---------- 投递列表 ---------- -->
				<view v-for="item in list" :key="item.id" class="item">
					<view class="item__main" hover-class="zn-hover" @tap="openDetail(item)">
						<!--
							⚠️ application_out 只给了 companyName，没有 logoText / logoColor：
							这里用公司名前两字做占位文字，底色固定用主题色。
							不按公司名哈希取随机色 —— 同一家公司在职位卡片与这里颜色不一致会更显眼。
						-->
						<zn-company-logo :text="logoText(item.companyName)" size="80"></zn-company-logo>
						<view class="item__info">
							<view class="item__row">
								<text class="item__title zn-ellipsis">{{ item.jobTitle }}</text>
								<text class="item__salary">{{ item.salaryText }}</text>
							</view>
							<text class="item__company zn-ellipsis">{{ item.companyName }}</text>
							<view class="item__foot">
								<zn-tag :text="item.statusText" :type="tagType(item.statusType)" size="xs" />
								<text class="item__time">{{ item.createdText }}</text>
							</view>
						</view>
						<uni-icons type="right" :size="14" color="#c8ced6"></uni-icons>
					</view>

					<!--
						撤回按钮只在 submitted / viewed / chatting 三个状态下出现。
						原因：状态机规定「进入面试流程后不允许撤回」，服务端对
						interview/passed/hired/rejected 一律返回 40903；
						按钮在这里直接不渲染，比渲成灰色再让用户点一次失败更清楚。
						（即便如此，服务端仍会再拦一次 —— 前端隐藏只是体验，不是权限。）
					-->
					<view v-if="canWithdraw(item)" class="item__actions">
						<view class="item__btn" hover-class="zn-hover" @tap.stop="onWithdraw(item)">
							<text class="item__btn-text">撤回投递</text>
						</view>
					</view>
				</view>

				<!-- 触底加载状态 -->
				<view class="foot">
					<text class="foot__text">{{ footTip }}</text>
				</view>
			</template>
		</view>

		<!-- ==================== 投递详情弹层（点整条 → getApplicationDetail） ==================== -->
		<view v-if="sheetVisible" class="mask" @tap="closeDetail">
			<view class="sheet" @tap.stop>
				<view class="sheet__head">
					<text class="sheet__title">投递详情</text>
					<view class="sheet__close" hover-class="zn-hover" @tap="closeDetail">
						<uni-icons type="closeempty" :size="20" color="#999999"></uni-icons>
					</view>
				</view>

				<scroll-view class="sheet__body" scroll-y>
					<view v-if="detailLoading" class="state">
						<text class="state__text">正在加载详情…</text>
					</view>

					<view v-else-if="detailFailed" class="state state--fail" hover-class="zn-hover"
						@tap="loadDetail(currentId)">
						<uni-icons type="refresh" :size="18" color="#ff4d4f"></uni-icons>
						<text class="state__text state__text--fail">详情加载失败，点击重试</text>
					</view>

					<template v-else-if="detail">
						<!-- 职位快照（服务端在投递时就做了快照，职位改名/下线后这里仍是当时投的岗位） -->
						<view class="snap">
							<view class="snap__row">
								<text class="snap__title">{{ detail.jobTitle }}</text>
								<text class="snap__salary">{{ detail.salaryText }}</text>
							</view>
							<text class="snap__company">{{ detail.companyName }}</text>
							<view class="snap__meta">
								<zn-tag :text="detail.statusText" :type="tagType(detail.statusType)" size="xs" />
								<text class="snap__time">{{ detail.createdText }}投递</text>
							</view>
							<!-- job 是当前职位行（可能已下线）：status !== 1 时如实标注 -->
							<view v-if="detail.job" class="snap__job">
								<text class="snap__job-line zn-ellipsis">
									{{ jobLine(detail.job) }}
								</text>
								<text v-if="detail.job.status !== 1" class="snap__job-off">该职位已停止招聘</text>
							</view>
							<view class="snap__actions">
								<view class="snap__btn" hover-class="zn-hover" @tap="goJob(detail.jobId)">
									<text class="snap__btn-text">查看职位</text>
								</view>
							</view>
						</view>

						<!-- 打招呼语（投递时带上的，没有就不显示这一块） -->
						<view v-if="detail.greeting" class="block">
							<text class="block__title">我的打招呼语</text>
							<text class="block__text">{{ detail.greeting }}</text>
						</view>

						<!-- 面试邀约列表 -->
						<view class="block">
							<text class="block__title">面试邀约</text>
							<view v-if="!interviews.length" class="block__none">
								<text class="block__none-text">HR 还没有发出面试邀约</text>
							</view>
							<view v-for="it in interviews" :key="it.id" class="iv">
								<view class="iv__head">
									<text class="iv__round zn-ellipsis">{{ it.roundName }}</text>
									<text class="iv__status">{{ it.statusText }}</text>
								</view>
								<view class="iv__meta">
									<text class="iv__time">{{ it.timeText }}</text>
									<text class="iv__dot">·</text>
									<text class="iv__mode">{{ it.modeText }}</text>
									<text v-if="it.durationMin" class="iv__dot">·</text>
									<text v-if="it.durationMin" class="iv__mode">{{ it.durationMin }} 分钟</text>
								</view>
								<text v-if="it.interviewer" class="iv__line">面试官：{{ it.interviewer }}</text>
								<text v-if="it.address" class="iv__line">{{ it.address }}</text>
								<text v-else-if="it.onlineLink" class="iv__line">{{ it.onlineLink }}</text>
							</view>
						</view>
					</template>
				</scroll-view>
			</view>
		</view>
	</view>
</template>

<script>
	/**
	 * 我的投递
	 *
	 * 数据来源（services/apply.js）：
	 *   列表   getMyApplications({status, page, pageSize}) → {list,total,page,pageSize,hasMore}
	 *   详情   getApplicationDetail(id)  → {application}，含职位快照与 interviews
	 *   撤回   withdrawApplication(id)
	 *
	 * ⚠️ 状态文案与配色一律用服务端返回的 statusText / statusType：
	 *    求职者端（已投递 / 简历已查看）与 HR 端（待处理 / 已查看）对同一状态的中文说法不同，
	 *    服务端已按角色翻译好，前端再写一套必然出现两端口径不一致。
	 *    statusType 只有 info / warning / success / danger 四种，这里只做「语义 → zn-tag 配色」的映射。
	 *
	 * ⚠️ 撤回投递的边界：submitted / viewed / chatting 可撤；进入面试流程后服务端返回 40903。
	 *    本条记录撤回成功后从当前列表移除，并把 total 减 1（不重新请求整页，保持滚动位置）。
	 *
	 * ⚠️ 切筛选 / 翻页的竞态：快速点标签时旧请求可能后返回，
	 *    用自增的 seq 标记每次请求，响应回来时 seq 不一致就整包丢弃（否则会出现「点了待面试却显示全部」）。
	 */
	import { isLogined } from '@/services/user.js'
	import { getMyApplications, getApplicationDetail, withdrawApplication } from '@/services/apply.js'

	/**
	 * 顶部筛选：key 直接就是服务端的状态枚举，'' 表示不传（全部）
	 *
	 * ⚠️ 这里没有「已撤回」标签：撤回后服务端把状态置为 withdrawn，
	 *    但产品上不要求把撤回记录当作一个可筛选项，因此撤回过的记录只会在「全部」里出现
	 *    （带上服务端给的「已撤回」文案，且不再显示撤回按钮）。要加这个标签时只需往 TABS 里补一项。
	 */
	const TABS = [
		{ key: '', text: '全部' },
		{ key: 'submitted', text: '已投递' },
		{ key: 'viewed', text: '已查看' },
		{ key: 'chatting', text: '沟通中' },
		{ key: 'interview', text: '待面试' },
		{ key: 'passed', text: '面试通过' },
		{ key: 'rejected', text: '不合适' }
	]

	/** 允许撤回的状态（与服务端 WITHDRAWABLE 一致，见 services/apply.js 注释） */
	const WITHDRAWABLE = ['submitted', 'viewed', 'chatting']

	/** statusType → zn-tag 的配色类型 */
	const TAG_TYPE = {
		info: 'gray',
		warning: 'orange',
		success: 'green',
		danger: 'red'
	}

	const PAGE_SIZE = 10

	export default {
		data() {
			return {
				tabs: TABS,
				status: '',
				list: [],
				total: 0,
				page: 0,
				hasMore: true,
				loading: true,
				loadingMore: false,
				loadFailed: false,
				isLogin: false,
				seq: 0, // 请求序号，用于丢弃过期响应
				// 详情弹层
				sheetVisible: false,
				currentId: '',
				detail: null,
				detailLoading: false,
				detailFailed: false
			}
		},
		computed: {
			/** 当前筛选下的条数：以服务端 total 为准（不是 list.length，后者只是已加载页） */
			countText() {
				const name = this.statusName
				return name ? name + ' · 共 ' + this.total + ' 份投递' : '共 ' + this.total + ' 份投递'
			},
			statusName() {
				const hit = TABS.filter(t => t.key === this.status)[0]
				return hit ? hit.text : ''
			},
			interviews() {
				return (this.detail && this.detail.interviews) || []
			},
			/** 空态文案：只有「全部」为空才引导去投递，其它筛选为空只是这个状态下没有记录 */
			emptyConf() {
				if (!this.status) {
					return {
						icon: 'paperplane',
						text: '还没有投递记录',
						desc: '去职位首页挑几个匹配的岗位，投出第一份简历',
						btnText: '去逛逛职位'
					}
				}
				return {
					icon: 'info',
					text: '没有「' + this.statusName + '」的投递',
					desc: '换个状态看看，或回到全部查看完整进度',
					btnText: '查看全部投递'
				}
			},
			footTip() {
				if (this.loadingMore) return '正在加载更多…'
				if (this.hasMore) return '上滑加载更多'
				return '已显示全部 ' + this.total + ' 份投递'
			}
		},
		onLoad() {
			this.refresh()
		},
		onShow() {
			// 从职位详情投递后返回：重新拉一次，新投递会立刻出现在顶部
			if (this.isLogin) this.refresh()
		},
		onPullDownRefresh() {
			this.loadList(true, true)
		},
		onReachBottom() {
			this.loadMore()
		},
		methods: {
			/* ---------------- 数据 ---------------- */
			refresh() {
				this.loadList(true, false)
			},

			/**
			 * 拉取列表
			 * @param {boolean} reset    是否重置（切筛选 / 下拉刷新 / 首次进页）
			 * @param {boolean} fromPull 是否来自下拉刷新（决定是否 stopPullDownRefresh）
			 */
			async loadList(reset, fromPull) {
				this.isLogin = isLogined()
				if (!this.isLogin) {
					this.loading = false
					this.loadFailed = false
					this.list = []
					this.total = 0
					if (fromPull) uni.stopPullDownRefresh()
					return
				}

				const seq = ++this.seq
				const nextPage = reset ? 1 : this.page + 1
				if (reset) {
					this.loading = true
					this.loadFailed = false
				} else {
					this.loadingMore = true
				}

				try {
					const res = await getMyApplications({
						status: this.status,
						page: nextPage,
						pageSize: PAGE_SIZE
					})
					if (seq !== this.seq) return // 过期响应（用户已切筛选）整包丢弃
					const rows = (res && res.list) || []
					this.list = reset ? rows : this.list.concat(rows)
					this.total = (res && res.total) || 0
					this.page = (res && res.page) || nextPage
					this.hasMore = !!(res && res.hasMore)
					this.loadFailed = false
				} catch (e) {
					if (seq !== this.seq) return
					// 纯接口模式：失败就是失败。重置请求失败清空列表并显示重试；翻页失败保留已加载内容
					if (reset) {
						this.list = []
						this.total = 0
						this.loadFailed = true
					} else {
						uni.showToast({ title: '加载更多失败', icon: 'none' })
					}
				} finally {
					if (seq === this.seq) {
						this.loading = false
						this.loadingMore = false
						if (fromPull) {
							uni.stopPullDownRefresh()
							uni.showToast({ title: this.loadFailed ? '刷新失败' : '已更新', icon: 'none' })
						}
					}
				}
			},

			loadMore() {
				if (!this.isLogin || this.loading || this.loadingMore || !this.hasMore) return
				// 触底加载失败不弹整页错误，只保留已有内容（nextPage 由 loadList 内部按 page+1 计算）
				this.loadList(false, false)
			},

			switchTab(key) {
				if (this.status === key) return
				this.status = key
				// 列表先清空：避免新旧筛选的数据在同一屏里混着显示
				this.list = []
				this.page = 0
				this.hasMore = true
				this.loadList(true, false)
			},

			/* ---------------- 详情弹层 ---------------- */
			openDetail(item) {
				this.sheetVisible = true
				this.loadDetail(item.id)
			},

			closeDetail() {
				this.sheetVisible = false
				this.detail = null
				this.currentId = ''
				this.detailFailed = false
			},

			async loadDetail(id) {
				this.currentId = id
				this.detailLoading = true
				this.detailFailed = false
				try {
					const res = await getApplicationDetail(id)
					this.detail = (res && res.application) || null
				} catch (e) {
					this.detail = null
					this.detailFailed = true
				} finally {
					this.detailLoading = false
				}
			},

			/* ---------------- 撤回 ---------------- */
			canWithdraw(item) {
				return WITHDRAWABLE.indexOf(item.status) > -1
			},

			onWithdraw(item) {
				uni.showModal({
					title: '撤回投递',
					content: '确定撤回对「' + item.jobTitle + '」的投递吗？撤回后需要重新投递。',
					confirmColor: '#00A6A7',
					success: async res => {
						if (!res.confirm) return
						try {
							await withdrawApplication(item.id)
							// 撤回成功后本地移除该条并修正总数：比重新请求整页体验更稳（不丢滚动位置）
							// ⚠️ 记录本身没有删除，只是状态变成 withdrawn —— 下拉刷新后会以「已撤回」重新出现在「全部」里
							this.list = this.list.filter(row => row.id !== item.id)
							this.total = Math.max(0, this.total - 1)
							uni.showToast({ title: '已撤回投递', icon: 'none' })
						} catch (e) {
							// 40903（已进入面试流程）等错误提示由 services/api.js 统一弹出；
							// 这里刷新一次列表，让界面与服务端的真实状态重新对齐
							this.loadList(true, false)
						}
					}
				})
			},

			/* ---------------- 展示 / 跳转 ---------------- */
			/** statusType → zn-tag 配色；未知类型按 info（灰）处理，不猜颜色 */
			tagType(statusType) {
				return TAG_TYPE[statusType] || 'gray'
			},

			/** 公司名 → Logo 占位文字（取前两字，与 zn-company-logo 的展示规则一致） */
			logoText(companyName) {
				const str = String(companyName || '').trim()
				return str ? str.slice(0, 2) : '公'
			},

			/** 职位快照的一行摘要：能拿到的字段才拼，缺项直接跳过 */
			jobLine(job) {
				const place = [job.cityName, job.district].filter(Boolean).join('·')
				return [place, job.experience, job.education].filter(Boolean).join(' | ')
			},

			goJob(jobId) {
				if (!jobId) {
					uni.showToast({ title: '职位信息缺失', icon: 'none' })
					return
				}
				this.closeDetail()
				uni.navigateTo({ url: '/pages/job/detail?id=' + jobId })
			},

			onEmptyAction() {
				if (!this.status) {
					uni.reLaunch({ url: '/pages/index/index' })
					return
				}
				this.switchTab('')
			},

			goLogin() {
				uni.navigateTo({ url: '/pages/login/login' })
			}
		}
	}
</script>

<style lang="scss" scoped>
	/* ==================== 状态筛选 ==================== */
	.filter {
		white-space: nowrap;
		background-color: $zn-bg-card;
		border-bottom: 1rpx solid $zn-line;
	}

	.filter__inner {
		display: inline-flex;
		flex-direction: row;
		align-items: center;
		padding: 0 $zn-page-padding;
	}

	.filter__item {
		position: relative;
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 22rpx 0;
		margin-right: 44rpx;
	}

	.filter__text {
		font-size: 27rpx;
		color: $zn-text-grey;
	}

	.filter__item.is-active .filter__text {
		font-size: 30rpx;
		font-weight: 700;
		color: $zn-theme-dark;
	}

	.filter__bar {
		position: absolute;
		left: 50%;
		bottom: 8rpx;
		width: 40rpx;
		height: 6rpx;
		margin-left: -20rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
	}

	/* ==================== 内容区 ==================== */
	.apps__body {
		padding: $zn-gap $zn-page-padding 40rpx;
	}

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

	.apps__count {
		padding-bottom: 16rpx;
	}

	.apps__count-text {
		font-size: 23rpx;
		color: $zn-text-grey;
	}

	/* ---------- 投递条目 ---------- */
	.item {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 24rpx;
		margin-bottom: 20rpx;
		box-shadow: $zn-shadow-sm;
	}

	.item__main {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.item__info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin: 0 12rpx 0 20rpx;
	}

	.item__row {
		display: flex;
		flex-direction: row;
		align-items: baseline;
		justify-content: space-between;
	}

	.item__title {
		flex: 1;
		min-width: 0;
		font-size: 30rpx;
		font-weight: 600;
		color: $zn-text-title;
	}

	.item__salary {
		flex-shrink: 0;
		margin-left: $zn-gap-sm;
		font-size: 26rpx;
		font-weight: 700;
		color: $zn-price;
	}

	.item__company {
		font-size: 24rpx;
		color: $zn-text-sub;
		margin-top: 8rpx;
	}

	.item__foot {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		margin-top: 12rpx;
	}

	.item__time {
		font-size: 21rpx;
		color: $zn-text-light;
	}

	.item__actions {
		display: flex;
		flex-direction: row;
		justify-content: flex-end;
		margin-top: 18rpx;
		padding-top: 18rpx;
		border-top: 1rpx solid $zn-line;
	}

	.item__btn {
		height: 56rpx;
		padding: 0 26rpx;
		border-radius: $zn-radius-pill;
		border: 1rpx solid $zn-line;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.item__btn-text {
		font-size: 24rpx;
		color: $zn-text-sub;
	}

	/* ---------- 底部加载提示 ---------- */
	.foot {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 24rpx 0 10rpx;
	}

	.foot__text {
		font-size: 23rpx;
		color: $zn-text-light;
	}

	/* ==================== 详情弹层 ==================== */
	.mask {
		position: fixed;
		left: 0;
		right: 0;
		top: 0;
		bottom: 0;
		z-index: 995;
		background-color: $zn-mask;
		display: flex;
		flex-direction: column;
		justify-content: flex-end;
	}

	.sheet {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-xl $zn-radius-xl 0 0;
		max-height: 82vh;
		display: flex;
		flex-direction: column;
	}

	.sheet__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		padding: 28rpx $zn-page-padding 20rpx;
		border-bottom: 1rpx solid $zn-line;
	}

	.sheet__title {
		font-size: 32rpx;
		font-weight: 700;
		color: $zn-text-title;
	}

	.sheet__close {
		width: 56rpx;
		height: 56rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.sheet__body {
		flex: 1;
		max-height: 62vh;
		padding: 0 $zn-page-padding;
	}

	/* ---------- 弹层里的职位快照 ---------- */
	.snap {
		background-color: $zn-theme-lighter;
		border-radius: $zn-radius;
		padding: 24rpx;
		margin: 24rpx 0;
	}

	.snap__row {
		display: flex;
		flex-direction: row;
		align-items: baseline;
		justify-content: space-between;
	}

	.snap__title {
		flex: 1;
		min-width: 0;
		font-size: 30rpx;
		font-weight: 600;
		color: $zn-text-title;
	}

	.snap__salary {
		flex-shrink: 0;
		margin-left: $zn-gap-sm;
		font-size: 28rpx;
		font-weight: 700;
		color: $zn-price;
	}

	.snap__company {
		display: block;
		font-size: 24rpx;
		color: $zn-text-sub;
		margin-top: 8rpx;
	}

	.snap__meta {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 14rpx;
	}

	.snap__time {
		font-size: 21rpx;
		color: $zn-text-light;
		margin-left: 12rpx;
	}

	.snap__job {
		margin-top: 14rpx;
		padding-top: 14rpx;
		border-top: 1rpx solid $zn-line;
	}

	.snap__job-line {
		display: block;
		font-size: 23rpx;
		color: $zn-text-grey;
	}

	.snap__job-off {
		display: block;
		font-size: 22rpx;
		color: $zn-red;
		margin-top: 6rpx;
	}

	.snap__actions {
		display: flex;
		flex-direction: row;
		justify-content: flex-end;
		margin-top: 18rpx;
	}

	.snap__btn {
		height: 60rpx;
		padding: 0 28rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;
	}

	.snap__btn-text {
		font-size: 24rpx;
		font-weight: 600;
		color: #ffffff;
	}

	/* ---------- 弹层里的通用区块 ---------- */
	.block {
		margin-bottom: 28rpx;
	}

	.block__title {
		display: block;
		font-size: 28rpx;
		font-weight: 600;
		color: $zn-text-title;
		margin-bottom: 12rpx;
	}

	.block__text {
		display: block;
		font-size: 25rpx;
		color: $zn-text-sub;
		line-height: 40rpx;
	}

	.block__none {
		padding: 12rpx 0;
	}

	.block__none-text {
		font-size: 24rpx;
		color: $zn-text-light;
	}

	.iv {
		background-color: $zn-bg-grey;
		border-radius: $zn-radius;
		padding: 20rpx;
		margin-bottom: 16rpx;
	}

	.iv__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.iv__round {
		flex: 1;
		min-width: 0;
		font-size: 27rpx;
		font-weight: 600;
		color: $zn-text-main;
	}

	.iv__status {
		flex-shrink: 0;
		font-size: 20rpx;
		color: $zn-theme-dark;
		background-color: $zn-theme-light;
		border-radius: $zn-radius-xs;
		padding: 2rpx 12rpx;
		margin-left: $zn-gap-sm;
	}

	.iv__meta {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 10rpx;
	}

	.iv__time {
		font-size: 24rpx;
		color: $zn-text-sub;
	}

	.iv__dot {
		font-size: 22rpx;
		color: $zn-text-light;
		margin: 0 8rpx;
	}

	.iv__mode {
		font-size: 23rpx;
		color: $zn-text-sub;
	}

	.iv__line {
		display: block;
		font-size: 22rpx;
		color: $zn-text-grey;
		margin-top: 8rpx;
	}
</style>
