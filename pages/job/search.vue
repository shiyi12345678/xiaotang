<template>
	<view class="zn-page zn-page--no-tabbar search">
		<!-- ==================== 顶部：搜索框 + 取消 ==================== -->
		<view class="search__nav" :style="{ paddingTop: statusBarHeight + 'px' }">
			<view class="search__box">
				<uni-icons type="search" :size="17" color="#9aa0a6"></uni-icons>
				<input class="search__input" v-model="keyword" :focus="autoFocus" type="text"
					confirm-type="search" placeholder="搜索职位 / 公司，如「前端开发」" placeholder-class="search__ph"
					@confirm="onConfirm" @input="onInput" />
				<view v-if="keyword" class="search__clear" hover-class="zn-hover" @tap="clearKeyword">
					<uni-icons type="clear" :size="16" color="#c8ccd4"></uni-icons>
				</view>
			</view>
			<view class="search__cancel" hover-class="zn-hover" @tap="goBack">
				<text class="search__cancel-text">取消</text>
			</view>
		</view>

		<!-- ==================== 未输入关键词：热词 + 本地历史 ==================== -->
		<view v-if="!searched" class="search__panel">
			<view v-if="history.length" class="block">
				<view class="block__head">
					<text class="block__title">搜索历史</text>
					<view class="block__action" hover-class="zn-hover" @tap="clearHistory">
						<uni-icons type="trash" :size="14" color="#999999"></uni-icons>
						<text class="block__action-text">清空</text>
					</view>
				</view>
				<view class="chips">
					<text v-for="(w, i) in history" :key="'h' + i" class="chips__item" hover-class="zn-hover"
						@tap="searchWord(w)">{{ w }}</text>
				</view>
			</view>

			<view v-if="hotKeywords.length" class="block">
				<view class="block__head">
					<text class="block__title">热门搜索</text>
					<text class="block__sub">来自平台职位热度</text>
				</view>
				<view class="chips">
					<text v-for="(w, i) in hotKeywords" :key="'k' + i" class="chips__item chips__item--hot"
						hover-class="zn-hover" @tap="searchWord(w)">{{ w }}</text>
				</view>
			</view>

			<!-- 历史与热词都为空（如配置接口失败）：如实展示空态，不编造热词 -->
			<zn-empty v-if="!history.length && !hotKeywords.length" icon="search" text="输入关键词开始搜索"
				desc="支持搜索职位名称与公司名称，如「产品经理」「星野智能」" />
		</view>

		<!-- ==================== 搜索结果 ==================== -->
		<view v-else class="search__body">
			<view class="search__summary">
				<text class="search__count">「{{ activeKeyword }}」共 {{ total }} 个职位</text>
			</view>

			<view v-if="loading" class="state">
				<text class="state__text">正在搜索…</text>
			</view>

			<view v-else-if="loadFailed" class="state" hover-class="zn-hover" @tap="doSearch">
				<uni-icons type="refresh" :size="18" color="#00a6a7"></uni-icons>
				<text class="state__text">搜索失败，点击重试</text>
			</view>

			<zn-empty v-else-if="!list.length" icon="search" text="没有找到相关职位"
				desc="换个关键词试试，或用更通用的职位名（如「运营」而不是「内容运营专员」）" />

			<template v-else>
				<view v-for="job in list" :key="job.id" class="search__item">
					<zn-job-card :job="job" show-favorite @tap="goDetail" @favorite="onFavorite" />
				</view>
				<view class="more">
					<text v-if="loadingMore" class="more__text">正在加载更多…</text>
					<text v-else-if="loadMoreFailed" class="more__text more__text--tap" @tap="loadMore">
						加载更多失败，点击重试
					</text>
					<text v-else-if="hasMore" class="more__text">上拉加载更多</text>
					<text v-else class="more__text">没有更多结果了</text>
				</view>
			</template>
		</view>
	</view>
</template>

<script>
	/**
	 * 职位搜索
	 *
	 * 接口：
	 *   getJobList({keyword, page, pageSize})  服务端同一个列表接口，带 keyword 即搜索
	 *                                           （匹配职位名 / 公司全名 / 公司简称）
	 *   getConfig('rcHotKeywords')             热词是展示型配置，取不到就当没有（catch 掉，不拦整页）
	 * 本地：
	 *   uni.getStorageSync('zn_job_search_history')  搜索历史，最多 10 条
	 *
	 * ⚠️ 为什么历史放本地而不放服务端：这个项目没有「搜索记录」表，
	 *    而搜索历史是强个性化的轻量数据，放本地既不占接口也够用；
	 *    代价是换设备/清缓存会丢，属于可接受的取舍。
	 */
	import { getJobList, toggleFavorite } from '@/services/job.js'
	import { getConfig } from '@/services/content.js'
	import { isLogined } from '@/services/user.js'

	/** 搜索历史缓存键（与页面约定一致，别的页面若要读取历史也用这个键） */
	const HISTORY_KEY = 'zn_job_search_history'
	/** 历史条数上限：超过 10 条后旧的会被挤掉，避免面板无限变长 */
	const HISTORY_MAX = 10

	export default {
		data() {
			return {
				statusBarHeight: 0,
				keyword: '', // 输入框里的实时内容
				activeKeyword: '', // 真正发起过搜索的关键词（结果区标题用它，避免打字时标题乱跳）
				autoFocus: false,
				searched: false,
				hotKeywords: [],
				history: [],
				list: [],
				total: 0,
				page: 1,
				pageSize: 10,
				hasMore: false,
				loading: false,
				loadingMore: false,
				loadFailed: false,
				loadMoreFailed: false
			}
		},
		onLoad(options) {
			this.statusBarHeight = uni.getSystemInfoSync().statusBarHeight || 0
			this.history = this.readHistory()
			this.loadHotKeywords()
			const kw = options && options.keyword ? String(options.keyword) : ''
			if (kw) {
				// 从列表页带着关键词进来：直接当作一次搜索，用户不用再敲一遍
				this.keyword = kw
				this.activeKeyword = kw
				this.doSearch()
			} else {
				// 只有冷启动进搜索页才自动聚焦；带关键词进来时不抢焦点（否则会立刻弹起键盘挡住结果）
				this.autoFocus = true
			}
		},
		async onPullDownRefresh() {
			// 没搜过的时候下拉只清个动画，不做无意义的请求
			try {
				if (this.searched) await this.doSearch()
			} finally {
				uni.stopPullDownRefresh()
			}
		},
		onReachBottom() {
			this.loadMore()
		},
		methods: {
			/* ---------------- 热词 ---------------- */
			async loadHotKeywords() {
				try {
					const value = await getConfig('rcHotKeywords')
					this.hotKeywords = Array.isArray(value) ? value : []
				} catch (e) {
					// 热词是「可有可无」的展示配置：取不到就不显示这一块，界面照样能用
					this.hotKeywords = []
				}
			},

			/* ---------------- 本地搜索历史 ---------------- */
			readHistory() {
				const saved = uni.getStorageSync(HISTORY_KEY)
				return Array.isArray(saved) ? saved.filter(w => !!w) : []
			},
			saveHistory(word) {
				const w = String(word || '').trim()
				if (!w) return
				// 去重后置顶：重复搜索同一个词应该把它顶到最前面，而不是留下两条
				const next = [w].concat(this.history.filter(item => item !== w)).slice(0, HISTORY_MAX)
				this.history = next
				uni.setStorageSync(HISTORY_KEY, next)
			},
			clearHistory() {
				uni.showModal({
					title: '清空搜索历史',
					content: '清空后无法恢复，确定继续吗？',
					success: r => {
						if (!r.confirm) return
						this.history = []
						uni.removeStorageSync(HISTORY_KEY)
						uni.showToast({ title: '已清空', icon: 'none' })
					}
				})
			},

			/* ---------------- 搜索 ---------------- */
			onInput(e) {
				const value = (e.detail && e.detail.value) || ''
				this.keyword = value
				// 用户把关键词删空：退回热词/历史面板，而不是继续显示上一次的结果（避免「空关键词却有结果」的错觉）
				if (!value.trim()) {
					this.searched = false
					this.activeKeyword = ''
				}
			},
			clearKeyword() {
				this.keyword = ''
				this.searched = false
				this.activeKeyword = ''
				this.autoFocus = true
			},
			onConfirm() {
				const w = this.keyword.trim()
				if (!w) {
					uni.showToast({ title: '请输入搜索关键词', icon: 'none' })
					return
				}
				this.activeKeyword = w
				this.keyword = w
				this.saveHistory(w)
				this.doSearch()
			},
			/** 点击热词 / 历史词：直接发起搜索 */
			searchWord(word) {
				this.keyword = String(word)
				this.activeKeyword = this.keyword
				this.saveHistory(this.keyword)
				this.doSearch()
			},
			async doSearch() {
				if (!this.activeKeyword) return
				this.loading = true
				this.loadFailed = false
				this.loadMoreFailed = false
				// 搜索条件变了，结果区先清空：否则会短暂显示上一次关键词的结果
				this.list = []
				this.total = 0
				try {
					const res = await getJobList({ keyword: this.activeKeyword, page: 1, pageSize: this.pageSize })
					this.list = res.list || []
					this.total = Number(res.total) || 0
					this.page = Number(res.page) || 1
					this.hasMore = !!res.hasMore
					this.searched = true
				} catch (e) {
					this.loadFailed = true
					this.searched = true
				} finally {
					this.loading = false
				}
			},
			async loadMore() {
				if (!this.searched || this.loading || this.loadingMore || !this.hasMore) return
				this.loadingMore = true
				this.loadMoreFailed = false
				try {
					const next = this.page + 1
					const res = await getJobList({ keyword: this.activeKeyword, page: next, pageSize: this.pageSize })
					this.list = this.list.concat(res.list || [])
					this.page = Number(res.page) || next
					this.hasMore = !!res.hasMore
				} catch (e) {
					this.loadMoreFailed = true
				} finally {
					this.loadingMore = false
				}
			},

			/* ---------------- 跳转与收藏 ---------------- */
			goBack() {
				if (getCurrentPages().length > 1) {
					uni.navigateBack({ delta: 1 })
				} else {
					uni.reLaunch({ url: '/pages/index/index' })
				}
			},
			goDetail(job) {
				if (!job || !job.id) return
				uni.navigateTo({ url: '/pages/job/detail?id=' + encodeURIComponent(job.id) })
			},
			async onFavorite(job) {
				if (!isLogined()) {
					uni.showToast({ title: '登录后才能收藏职位', icon: 'none' })
					setTimeout(() => uni.navigateTo({ url: '/pages/login/login' }), 800)
					return
				}
				try {
					const next = await toggleFavorite(job.id, job.isFavorite)
					job.isFavorite = next
					uni.showToast({ title: next ? '已收藏' : '已取消收藏', icon: 'none' })
				} catch (e) {
					// 提示已由请求层给出
				}
			}
		}
	}
</script>

<style lang="scss" scoped>
	.search {
		background-color: $zn-bg-page;
	}

	/* ==================== 顶部搜索 ==================== */
	.search__nav {
		position: sticky;
		top: 0;
		z-index: 20;
		display: flex;
		flex-direction: row;
		align-items: center;
		padding-left: $zn-page-padding;
		padding-right: $zn-page-padding;
		background-color: $zn-bg-card;
		box-shadow: $zn-shadow-sm;
	}

	.search__box {
		flex: 1;
		min-width: 0;
		height: 72rpx;
		margin: 16rpx 0;
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 0 20rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
	}

	.search__input {
		flex: 1;
		min-width: 0;
		margin-left: 10rpx;
		font-size: 26rpx;
		color: $zn-text-main;
	}

	.search__ph {
		color: $zn-text-light;
		font-size: 26rpx;
	}

	.search__clear {
		width: 44rpx;
		height: 44rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.search__cancel {
		flex-shrink: 0;
		padding-left: 20rpx;
	}

	.search__cancel-text {
		font-size: 28rpx;
		color: $zn-theme;
	}

	/* ==================== 热词 / 历史 ==================== */
	.search__panel {
		padding: $zn-gap $zn-page-padding;
	}

	.block {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: $zn-gap;
		margin-bottom: $zn-gap;
		box-shadow: $zn-shadow-sm;
	}

	.block__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		margin-bottom: 18rpx;
	}

	.block__title {
		font-size: $zn-font-md;
		font-weight: 700;
		color: $zn-text-title;
	}

	.block__sub {
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	.block__action {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.block__action-text {
		font-size: $zn-font-xs;
		color: $zn-text-grey;
		margin-left: 6rpx;
	}

	.chips {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
	}

	.chips__item {
		margin: 0 16rpx 16rpx 0;
		padding: 10rpx 24rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		font-size: $zn-font-sm;
		color: $zn-text-main;

		&--hot {
			background-color: $zn-theme-light;
			color: $zn-theme-dark;
		}
	}

	/* ==================== 结果 ==================== */
	.search__body {
		padding: 0 $zn-page-padding 20rpx;
	}

	.search__summary {
		padding: 20rpx 0 12rpx;
	}

	.search__count {
		font-size: 24rpx;
		color: $zn-text-sub;
	}

	.search__item {
		margin-bottom: $zn-gap;
	}

	.state {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 28rpx $zn-gap;
		box-shadow: $zn-shadow-sm;
	}

	.state__text {
		font-size: 26rpx;
		color: $zn-text-sub;
		margin-left: 10rpx;
	}

	.more {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 10rpx 0 30rpx;
	}

	.more__text {
		font-size: 24rpx;
		color: $zn-text-light;

		&--tap {
			color: $zn-theme;
		}
	}
</style>
