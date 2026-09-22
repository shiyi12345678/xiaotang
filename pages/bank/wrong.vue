<template>
	<view class="zn-page zn-page--no-tabbar wrong">
		<zn-nav-bar title="薄弱点复盘" show-back border />

		<!-- ==================== 未登录：只给登录引导，不发任何需鉴权的请求 ==================== -->
		<zn-empty v-if="!isLogin" icon="person" text="登录后查看薄弱点"
			desc="薄弱点按账号保存，登录即可同步你答错过的题目" btn-text="去登录" @action="goLogin" />

		<template v-else>
			<!-- ==================== 分类筛选 ==================== -->
			<scroll-view class="filter" scroll-x :show-scrollbar="false">
				<view class="filter__inner">
					<view class="filter__item" :class="{ 'is-active': activeCategory === '' }"
						hover-class="zn-hover" @tap="switchCategory('')">
						<text class="filter__text">全部</text>
					</view>
					<view v-for="c in categories" :key="c.id" class="filter__item"
						:class="{ 'is-active': activeCategory === c.id }" hover-class="zn-hover"
						@tap="switchCategory(c.id)">
						<text class="filter__text">{{ c.name }}</text>
					</view>
				</view>
			</scroll-view>

			<!-- 口径说明：把「薄弱点」与进度页的 wrong 差别写在界面上，避免被当成数据不一致 -->
			<view class="note">
				<uni-icons type="info" :size="14" color="#008c8d"></uni-icons>
				<text class="note__text">
					这里收录「曾经答错过」的题；最近一次已答对的题会留在列表里并标记「已攻克」，
					与刷题进度里的「仍薄弱」口径不同
				</text>
			</view>

			<!-- ==================== 加载中 ==================== -->
			<view v-if="loading" class="wrong__state">
				<uni-icons type="spinner-cycle" :size="22" color="#00a6a7"></uni-icons>
				<text class="wrong__state-text">正在加载薄弱点…</text>
			</view>

			<!-- ==================== 加载失败（可重试） ==================== -->
			<view v-else-if="error" class="wrong__state wrong__state--error" hover-class="zn-hover"
				@tap="loadList(true)">
				<uni-icons type="info-filled" :size="22" color="#ff4d4f"></uni-icons>
				<text class="wrong__state-text">{{ error }}</text>
				<text class="wrong__state-retry">点击重试</text>
			</view>

			<!-- ==================== 空态 ==================== -->
			<zn-empty v-else-if="!list.length" icon="checkbox-filled"
				:text="activeCategory ? '这个方向还没有薄弱点' : '还没有薄弱点，去刷题吧'"
				:desc="activeCategory ? '切到「全部」看看其它方向，或先去这个方向刷几道题' : '刷题时答错的题会自动收进这里，方便集中重练'"
				:btn-text="activeCategory ? '看全部薄弱点' : '去刷题'" @action="onEmptyAction" />

			<!-- ==================== 列表 ==================== -->
			<view v-else class="wrong__list">
				<view v-for="item in list" :key="item.id" class="item">
					<view class="item__head" hover-class="zn-hover" @tap="toggle(item)">
						<view class="item__meta-row">
							<zn-tag :text="item.difficultyText || '基础'" :type="difficultyTag(item)" size="sm" />
							<!-- 已攻克：曾经答错、最近一次答对了（口径见文件头注释） -->
							<text v-if="item.lastResult === 1" class="item__mastered">已攻克</text>
							<text class="item__wrong-count">答错 {{ item.wrongCount }} 次</text>
							<text v-if="item.lastTime" class="item__time">{{ item.lastTime }}</text>
						</view>
						<text class="item__question zn-ellipsis-2">{{ item.question }}</text>
						<view class="item__foot">
							<view v-if="(item.tags || []).length" class="item__tags">
								<text v-for="tag in item.tags" :key="tag" class="item__tag">{{ tag }}</text>
							</view>
							<view class="item__toggle">
								<text class="item__toggle-text">{{ isOpen(item) ? '收起' : '看答案' }}</text>
								<uni-icons :type="isOpen(item) ? 'arrow-down' : 'right'" :size="14"
									color="#999999"></uni-icons>
							</view>
						</view>
					</view>

					<!-- ---------- 展开区：答案 + 重新作答 ---------- -->
					<view v-if="isOpen(item)" class="item__body">
						<view v-if="answerLoadingId === item.id" class="item__loading">
							<uni-icons type="spinner-cycle" :size="18" color="#00a6a7"></uni-icons>
							<text class="item__loading-text">正在获取答案…</text>
						</view>
						<text v-else-if="answerErrorMap[item.id]" class="item__error" @tap="openAnswer(item)">
							{{ answerErrorMap[item.id] }}（点击重试）
						</text>
						<text v-else class="item__answer">{{ answerMap[item.id] }}</text>

						<view class="item__actions">
							<text class="item__actions-label">重新作答：</text>
							<view class="item__action item__action--bad" hover-class="zn-hover"
								@tap.stop="answer(item, 0)">
								<text class="item__action-text item__action-text--bad">还是不会</text>
							</view>
							<view class="item__action item__action--ok" hover-class="zn-hover"
								@tap.stop="answer(item, 1)">
								<text class="item__action-text">这次会了</text>
							</view>
						</view>
					</view>
				</view>

				<!-- 触底加载 / 到底提示 -->
				<view class="wrong__more">
					<text v-if="loadingMore" class="wrong__more-text">正在加载更多…</text>
					<text v-else-if="hasMore" class="wrong__more-text">上拉加载更多</text>
					<text v-else class="wrong__more-text">共 {{ total }} 道薄弱题，已全部加载</text>
				</view>
			</view>
		</template>
	</view>
</template>

<script>
	/**
	 * 薄弱点复盘（错题重练）
	 *
	 * 数据来源（services/interview.js）：
	 *   GET  /interview/wrong?category=&page=&pageSize=   薄弱点列表（🔒）
	 *   GET  /interview/banks                             分类筛选选项（公开）
	 *   GET  /interview/questions/{id}                     题目详情（按需拿 answer）
	 *   POST /interview/questions/{id}/record              重新作答（mode='review'）
	 *
	 * ⚠️⚠️ 口径必须说清楚（这是本页最容易被认为是 bug 的地方）：
	 *   1. 进入本列表的条件是「这道题**曾经答错过**」（wrongCount > 0），
	 *      不是「最近一次答错」；因此列表里必然包含「曾答错、最近已答对」的题，
	 *      页面据此显示「已攻克」标记 —— 这是给用户「我把它补上了」的正反馈，
	 *      与旧学习端错题本的 mastered 语义一致。
	 *   2. 这与 /interview/progress 返回的 wrong（只统计**最近一次**答错的题）口径不同：
	 *      weakTotal 可能 **大于** progress.wrong，这是服务端有意为之的差别，不是数据不一致，
	 *      所以本页不展示「仍薄弱 n 道」这类与进度页混用的文案。
	 *   3. 重新作答答对后，该题**不会**从列表消失（它确实答错过），只是 lastResult 变成 1。
	 *      要减少薄弱题量，靠的是「已攻克」而不是把题删掉。
	 *
	 * ⚠️ 为什么重新作答后重新拉第一页而不是只改本地字段：
	 *    服务端按「最近一次作答时间倒序」排序，刚重新作答的题会被顶到列表最前面；
	 *    只改本地字段会让顺序与下一次刷新不一致。重新拉第一页是最简单且不会说谎的做法，
	 *    代价是已翻到后面的分页会被收起（重新作答本身就该回到列表顶部看结果）。
	 *    已展开的答案缓存（answerMap）不随刷新丢弃，避免重复请求详情。
	 *
	 * ⚠️ 需登录：未登录时不发 /wrong 请求（401 会被请求层统一 toast 且清本地登录态），
	 *    直接展示登录引导。
	 */
	import { getWrongQuestions, getBanks, getQuestionDetail, recordQuestion } from '@/services/interview.js'
	import { isLogined } from '@/services/user.js'

	/** 每页条数：接口上限 50，20 条是「一屏能滚完、翻页也不累」的折中 */
	const PAGE_SIZE = 20

	export default {
		data() {
			return {
				isLogin: false,
				// ---------- 筛选 ----------
				categories: [],
				activeCategory: '',
				// ---------- 列表 ----------
				list: [],
				total: 0,
				page: 1,
				hasMore: false,
				loading: false,
				loadingMore: false,
				error: '',
				// ---------- 展开与答案（按题目 id 存，刷新列表后仍保留已拉到的答案） ----------
				openMap: {},
				answerMap: {},
				answerErrorMap: {},
				answerLoadingId: '',
				submittingId: '',
				inited: false
			}
		},
		onLoad() {
			this.isLogin = isLogined()
			if (!this.isLogin) return
			this.loadCategories()
			this.loadList(true)
		},
		onShow() {
			// 登录态可能在本页之外发生变化（用户点「去登录」登录后返回），
			// 因此每次显示都重新判断一次，而不是只在 onLoad 时判断一次。
			const logined = isLogined()
			const changed = this.isLogin !== logined
			this.isLogin = logined
			if (!logined) return
			// changed=刚登录回来（要补加载）；inited=从刷题页返回（要刷新）。
			// 首次进入两者都不成立（onLoad 正在拉），因此不会重复请求。
			if (changed || this.inited) {
				if (!this.categories.length) this.loadCategories()
				this.loadList(true)
			}
		},
		onPullDownRefresh() {
			if (!this.isLogin) {
				uni.stopPullDownRefresh()
				return
			}
			this.loadList(true)
		},
		onReachBottom() {
			if (this.hasMore && !this.loadingMore && !this.loading) this.loadList(false)
		},
		methods: {
			/* ================= 数据 ================= */
			/** 分类筛选项：复用题库分类接口（只有有题目的分类才会返回） */
			async loadCategories() {
				try {
					const res = await getBanks()
					this.categories = res.banks || []
				} catch (e) {
					// 分类只是筛选器，拉不到就不显示筛选条，不影响列表本身
					this.categories = []
				}
			},
			/**
			 * 拉取薄弱点列表
			 * @param {boolean} reset true=重置到第一页（首屏 / 下拉刷新 / 切分类 / 重新作答后）
			 */
			async loadList(reset) {
				if (reset) {
					this.page = 1
					this.loading = true
				} else {
					this.loadingMore = true
				}
				this.error = ''
				try {
					const res = await getWrongQuestions({
						category: this.activeCategory,
						page: this.page,
						pageSize: PAGE_SIZE
					})
					const rows = res.list || []
					this.list = reset ? rows : this.list.concat(rows)
					this.total = Number(res.total) || 0
					this.hasMore = !!res.hasMore
					if (this.hasMore) this.page += 1
				} catch (e) {
					this.error = e.message || '薄弱点加载失败'
					if (reset) this.list = []
				} finally {
					this.loading = false
					this.loadingMore = false
					this.inited = true
					uni.stopPullDownRefresh()
				}
			},
			switchCategory(id) {
				if (this.activeCategory === id) return
				this.activeCategory = id
				// 换分类回到顶部并重新拉第一页；已展开的答案缓存保留（同一个题目 id 仍然有效）
				this.loadList(true)
				uni.pageScrollTo({ scrollTop: 0, duration: 200 })
			},
			/* ================= 展开与答案 ================= */
			isOpen(item) {
				return !!this.openMap[item.id]
			},
			toggle(item) {
				if (this.openMap[item.id]) {
					this.openMap[item.id] = false
					return
				}
				this.openAnswer(item)
			},
			/** 展开并确保答案已拉取（同一题只请求一次详情） */
			async openAnswer(item) {
				this.openMap[item.id] = true
				if (this.answerMap[item.id] !== undefined) return
				this.answerLoadingId = item.id
				this.answerErrorMap[item.id] = ''
				try {
					const res = await getQuestionDetail(item.id)
					// 详情返回 {question:{...}} 包装层，答案取 res.question.answer
					const detail = (res && res.question) || {}
					this.answerMap[item.id] = detail.answer || '该题暂未录入参考答案'
				} catch (e) {
					this.answerErrorMap[item.id] = e.message || '答案加载失败'
				} finally {
					this.answerLoadingId = ''
				}
			},
			/* ================= 重新作答 ================= */
			/**
			 * 重新作答
			 * @param {object} item   列表项
			 * @param {number} result 1=这次会了 / 0=还是不会
			 *
			 * ⚠️ mode 固定传 'review'：服务端用它区分「顺序刷题 / 背诵 / 复盘」三种来源，
			 *    复盘数据不会被混进刷题模式的统计语境里。
			 */
			async answer(item, result) {
				if (this.submittingId) return
				if (!isLogined()) {
					// 登录态在这一页失效（token 过期等）：如实切回登录引导，不要假装记录成功
					this.isLogin = false
					uni.showToast({ title: '登录已失效，请重新登录后再复盘', icon: 'none' })
					return
				}
				this.submittingId = item.id
				try {
					await recordQuestion(item.id, { result, mode: 'review' })
				} catch (e) {
					// 失败提示已由请求层统一弹出；不改本地状态，用户可以再点一次
					this.submittingId = ''
					return
				}
				this.submittingId = ''
				uni.showToast({
					title: result === 1 ? '已记为会了，标记为已攻克' : '已记为不会，继续保持练习',
					icon: 'none',
					duration: 1600
				})
				// 重新拉第一页：刚作答的题会被服务端顶到最前面，顺序与刷新后一致
				this.loadList(true)
			},
			/* ================= 交互 ================= */
			difficultyTag(item) {
				const d = Number(item.difficulty) || 1
				if (d >= 3) return 'red'
				return d === 2 ? 'orange' : 'green'
			},
			onEmptyAction() {
				if (this.activeCategory) {
					this.switchCategory('')
					return
				}
				uni.navigateTo({ url: '/pages/bank/practice' })
			},
			goLogin() {
				uni.navigateTo({
					url: '/pages/login/login',
					fail: () => uni.showToast({ title: '登录页打开失败，请稍后重试', icon: 'none' })
				})
			}
		}
	}
</script>

<style lang="scss" scoped>
	.wrong {
		padding-bottom: 60rpx;
	}

	/* ==================== 分类筛选 ==================== */
	.filter {
		white-space: nowrap;
		background-color: $zn-bg-card;
		padding: 20rpx 0;
		border-bottom: 1rpx solid $zn-line;
	}

	.filter__inner {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 0 $zn-page-padding;
	}

	.filter__item {
		flex-shrink: 0;
		height: 60rpx;
		padding: 0 26rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-right: 16rpx;

		&.is-active {
			background: $zn-gradient;

			.filter__text {
				color: #ffffff;
				font-weight: 600;
			}
		}
	}

	.filter__text {
		font-size: 24rpx;
		color: $zn-text-sub;
	}

	/* ==================== 口径说明 ==================== */
	.note {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		background-color: $zn-theme-light;
		border-radius: $zn-radius-sm;
		padding: 16rpx 20rpx;
		margin: $zn-gap $zn-page-padding 0;
	}

	.note__text {
		flex: 1;
		min-width: 0;
		font-size: 21rpx;
		color: $zn-theme-dark;
		line-height: 34rpx;
		margin-left: 10rpx;
	}

	/* ==================== 状态块 ==================== */
	.wrong__state {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 60rpx 24rpx;
		margin: $zn-gap $zn-page-padding 0;
	}

	.wrong__state--error {
		border: 2rpx solid #ffe0e0;
	}

	.wrong__state-text {
		font-size: 24rpx;
		color: $zn-text-sub;
		margin-left: 12rpx;
	}

	.wrong__state-retry {
		font-size: 24rpx;
		color: $zn-theme-deep;
		margin-left: 16rpx;
	}

	/* ==================== 列表 ==================== */
	.wrong__list {
		padding: $zn-gap $zn-page-padding 0;
	}

	.item {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: 24rpx;
		margin-bottom: 20rpx;
	}

	.item__head {
		display: flex;
		flex-direction: column;
	}

	.item__meta-row {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.item__mastered {
		font-size: 18rpx;
		color: #ffffff;
		background-color: $zn-theme;
		border-radius: 6rpx;
		padding: 2rpx 10rpx;
		margin-left: 12rpx;
	}

	.item__wrong-count {
		font-size: 20rpx;
		color: $zn-red;
		background-color: #fff0f0;
		border-radius: 6rpx;
		padding: 2rpx 10rpx;
		margin-left: 12rpx;
	}

	.item__time {
		font-size: 20rpx;
		color: $zn-text-light;
		margin-left: auto;
	}

	.item__question {
		display: block;
		font-size: 29rpx;
		font-weight: 600;
		color: $zn-text-title;
		line-height: 44rpx;
		margin-top: 16rpx;
	}

	.item__foot {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		margin-top: 16rpx;
	}

	.item__tags {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		flex: 1;
		min-width: 0;
	}

	.item__tag {
		font-size: 19rpx;
		color: $zn-text-grey;
		background-color: $zn-bg-grey;
		border-radius: 6rpx;
		padding: 3rpx 10rpx;
		margin: 0 10rpx 8rpx 0;
	}

	.item__toggle {
		display: flex;
		flex-direction: row;
		align-items: center;
		flex-shrink: 0;
		margin-left: 12rpx;
	}

	.item__toggle-text {
		font-size: 22rpx;
		color: $zn-text-grey;
		margin-right: 4rpx;
	}

	/* ---------- 展开区 ---------- */
	.item__body {
		margin-top: 22rpx;
		padding-top: 22rpx;
		border-top: 1rpx solid $zn-line;
	}

	.item__loading {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.item__loading-text {
		font-size: 23rpx;
		color: $zn-text-grey;
		margin-left: 10rpx;
	}

	.item__error {
		display: block;
		font-size: 23rpx;
		color: $zn-red;
	}

	.item__answer {
		display: block;
		font-size: 26rpx;
		color: $zn-text-main;
		line-height: 46rpx;
		white-space: pre-wrap;
	}

	.item__actions {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 24rpx;
	}

	.item__actions-label {
		font-size: 22rpx;
		color: $zn-text-grey;
		flex-shrink: 0;
	}

	.item__action {
		height: 64rpx;
		padding: 0 26rpx;
		border-radius: $zn-radius-pill;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-left: 14rpx;

		&--bad {
			background-color: #fff0f0;
			border: 2rpx solid #ffd9d9;
		}

		&--ok {
			background: $zn-gradient;
			box-shadow: $zn-shadow-theme;
		}
	}

	.item__action-text {
		font-size: 24rpx;
		font-weight: 600;
		color: #ffffff;

		&--bad {
			color: $zn-red;
		}
	}

	/* ==================== 触底 ==================== */
	.wrong__more {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 20rpx 0 40rpx;
	}

	.wrong__more-text {
		font-size: 21rpx;
		color: $zn-text-light;
	}
</style>
