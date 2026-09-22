<template>
	<view class="zn-page zn-page--no-tabbar">
		<!-- ==================== 顶部导航 ==================== -->
		<zn-nav-bar title="我的收藏" show-back border />

		<!-- ==================== 内容区 ==================== -->
		<view class="fav__body">
			<!-- 未登录：收藏是账号私有数据（接口 auth: true），只给登录引导 -->
			<zn-empty v-if="!isLogin" icon="person" text="登录后查看收藏的职位"
				desc="收藏的职位会跟随账号，换设备也在" btn-text="去登录" @action="goLogin" />

			<!-- 加载中 -->
			<view v-else-if="loading" class="state">
				<text class="state__text">正在加载收藏…</text>
			</view>

			<!-- 加载失败：可点击重试（不做 mock 兜底） -->
			<view v-else-if="loadFailed" class="state state--fail" hover-class="zn-hover" @tap="refresh">
				<uni-icons type="refresh" :size="18" color="#ff4d4f"></uni-icons>
				<text class="state__text state__text--fail">收藏列表加载失败，点击重试</text>
			</view>

			<!-- 空态：引导回职位首页 -->
			<zn-empty v-else-if="!list.length" icon="star" text="还没有收藏的职位"
				desc="看到合适的岗位先收藏，投递前再对比一遍" btn-text="去逛逛职位" @action="goJobs" />

			<template v-else>
				<view class="fav__count">
					<text class="fav__count-text">共收藏 {{ total }} 个职位</text>
				</view>

				<!-- ---------- 收藏列表：统一用 zn-job-card（与首页/列表页同一张卡片） ---------- -->
				<view v-for="item in list" :key="item.id" class="fav__item">
					<!-- favoriteAt 是收藏时间（服务端在收藏列表里额外返回），放在卡片上方做辅助信息 -->
					<text v-if="item.favoriteAt" class="fav__time">{{ item.favoriteAt }} 收藏</text>
					<zn-job-card :job="item" show-favorite @tap="goDetail" @favorite="onUnfavorite"></zn-job-card>
				</view>

				<view class="foot">
					<text class="foot__text">{{ footTip }}</text>
				</view>
			</template>
		</view>
	</view>
</template>

<script>
	/**
	 * 我的收藏
	 *
	 * 数据来源（services/job.js）：
	 *   getFavoriteList({page, pageSize}) → {list,total,page,pageSize,hasMore}
	 *     list 元素 = 职位卡片字段（job_brief）+ favoriteAt，且服务端固定带 isFavorite=true
	 *   removeFavorite(jobId) → 取消收藏（幂等）
	 *
	 * ⚠️ 本页的收藏语义只有一个方向：页面上的都是「已收藏」，
	 *    点星标就是取消收藏，所以不弹二次确认 —— 列表本身就是收藏夹，
	 *    取消后条目直接从当前列表移除（误触可以回职位详情重新收藏）。
	 *    这与职位列表页星标要「判断当前是否已收藏再切换」的语义不同，
	 *    所以这里直接用 removeFavorite 而不是 toggleFavorite。
	 *
	 * ⚠️ 取消收藏成功后不重新请求整页：本地移除该条并 total-1，
	 *    否则重拉后列表会跳动、滚动位置也会丢。
	 */
	import { isLogined } from '@/services/user.js'
	import { getFavoriteList, removeFavorite } from '@/services/job.js'

	const PAGE_SIZE = 10

	export default {
		data() {
			return {
				isLogin: false,
				list: [],
				total: 0,
				page: 0,
				hasMore: true,
				loading: true,
				loadingMore: false,
				loadFailed: false,
				seq: 0, // 请求序号：丢弃过期响应，避免快速下拉/返场时新旧数据交叉
				removing: {} // 正在取消收藏的 jobId，防止连点重复提交
			}
		},
		computed: {
			footTip() {
				if (this.loadingMore) return '正在加载更多…'
				if (this.hasMore) return '上滑加载更多'
				return '已显示全部 ' + this.total + ' 个收藏职位'
			}
		},
		onLoad() {
			this.refresh()
		},
		onShow() {
			// 从职位详情返回：用户可能在详情页取消了收藏，重新拉一次保证列表与服务端一致
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
			 * 拉取收藏列表
			 * @param {boolean} reset    是否重置（首次 / 下拉刷新）
			 * @param {boolean} fromPull 是否来自下拉刷新
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
					const res = await getFavoriteList({ page: nextPage, pageSize: PAGE_SIZE })
					if (seq !== this.seq) return
					const rows = (res && res.list) || []
					this.list = reset ? rows : this.list.concat(rows)
					this.total = (res && res.total) || 0
					this.page = (res && res.page) || nextPage
					this.hasMore = !!(res && res.hasMore)
					this.loadFailed = false
				} catch (e) {
					if (seq !== this.seq) return
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
				this.loadList(false, false)
			},

			/* ---------------- 取消收藏 ---------------- */
			/**
			 * 星标点击 = 取消收藏
			 * 幂等：服务端重复取消不报错（changed=false），本地同样按「已移除」处理
			 */
			async onUnfavorite(job) {
				const jobId = job && job.id
				if (!jobId || this.removing[jobId]) return
				this.removing[jobId] = true
				try {
					await removeFavorite(jobId)
					this.list = this.list.filter(row => row.id !== jobId)
					this.total = Math.max(0, this.total - 1)
					uni.showToast({ title: '已取消收藏', icon: 'none' })
				} catch (e) {
					// 失败提示由 services/api.js 统一处理；列表保持原样，让用户能再试一次
				} finally {
					this.removing[jobId] = false
				}
			},

			/* ---------------- 跳转 ---------------- */
			goDetail(job) {
				uni.navigateTo({ url: '/pages/job/detail?id=' + job.id })
			},
			/** 职位首页是 tab 页：用 reLaunch 才能正确同步底部 tabBar 高亮 */
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
	.fav__body {
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

	.fav__count {
		padding-bottom: 16rpx;
	}

	.fav__count-text {
		font-size: 23rpx;
		color: $zn-text-grey;
	}

	.fav__item {
		margin-bottom: 20rpx;
	}

	.fav__time {
		display: block;
		font-size: 20rpx;
		color: $zn-text-light;
		margin-bottom: 8rpx;
	}

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
</style>
