<template>
	<view class="zn-page zn-page--no-tabbar bank">
		<zn-nav-bar title="面试题库" show-back border />

		<!-- ==================== 进度总览 ==================== -->
		<view class="hero">
			<!-- 态一：已登录且进度拉取成功 —— 展示真实刷题进度 -->
			<view v-if="progress" class="hero__inner">
				<text class="hero__title">我的备考进度</text>
				<view class="hero__row">
					<text class="hero__num">{{ progress.answered }}</text>
					<text class="hero__sep">/</text>
					<text class="hero__total">共 {{ progress.total }} 题</text>
					<text class="hero__rate">掌握率 {{ progress.accuracy }}%</text>
				</view>
				<view class="hero__bar">
					<zn-progress :percent="answeredPercent" :height="12" color="rgba(255,255,255,0.92)" />
				</view>
				<view class="hero__foot">
					<text class="hero__foot-text">已掌握 {{ progress.mastered }}</text>
					<text class="hero__dot"></text>
					<text class="hero__foot-text">仍薄弱 {{ progress.wrong }}</text>
				</view>
			</view>

			<!-- 态二：未登录 —— 进度接口需要登录，这里只做引导，不发请求 -->
			<view v-else-if="!isLogin" class="hero__inner">
				<text class="hero__title">登录后可记录刷题进度</text>
				<text class="hero__desc">刷题记录、薄弱点复盘都会同步到你的账号，换设备也不丢</text>
				<view class="hero__btn" hover-class="zn-hover" @tap="goLogin">
					<uni-icons type="person" :size="16" color="#008c8d"></uni-icons>
					<text class="hero__btn-text">立即登录</text>
				</view>
			</view>

			<!-- 态三：已登录、进度还没回来 —— 明确显示加载中，不要一闪而过地报「失败」 -->
			<view v-else-if="progressLoading" class="hero__inner">
				<text class="hero__title">正在读取刷题进度…</text>
				<text class="hero__desc">已作答的题目、掌握率都会显示在这里</text>
			</view>

			<!-- 态四：已登录但进度取不到 —— 如实报错并可重试，不编造数据 -->
			<view v-else class="hero__inner">
				<text class="hero__title">刷题进度加载失败</text>
				<text class="hero__desc">{{ progressError }}</text>
				<view class="hero__btn" hover-class="zn-hover" @tap="loadProgress">
					<uni-icons type="refresh" :size="16" color="#008c8d"></uni-icons>
					<text class="hero__btn-text">重新加载</text>
				</view>
			</view>
		</view>

		<!-- 薄弱点复盘入口：常驻，未登录也能进（进页后由该页给登录引导） -->
		<view class="entry" hover-class="zn-hover" @tap="goWrong">
			<view class="entry__icon">
				<!-- uni-icons 白名单里没有「错误/警示」类图标，用 fire-filled + 橙色表达「薄弱点/痛点」 -->
				<uni-icons type="fire-filled" :size="22" color="#ff8f1f"></uni-icons>
			</view>
			<view class="entry__body">
				<text class="entry__title">薄弱点复盘</text>
				<text class="entry__desc">
					{{ progress ? '你答错过的题都收在这里，可重新作答' : '把答错过的题集中重练一遍' }}
				</text>
			</view>
			<uni-icons type="right" :size="16" color="#bbbbbb"></uni-icons>
		</view>

		<!-- ==================== 题库分类 ==================== -->
		<view class="bank__section">
			<zn-section-header title="按职能刷题" :subtitle="bankSubtitle" />
		</view>

		<!-- 分类加载中 -->
		<view v-if="banksLoading" class="bank__state">
			<uni-icons type="spinner-cycle" :size="22" color="#00a6a7"></uni-icons>
			<text class="bank__state-text">正在加载题库…</text>
		</view>

		<!-- 分类加载失败：可点击重试 -->
		<view v-else-if="banksError" class="bank__state bank__state--error" hover-class="zn-hover"
			@tap="loadBanks">
			<uni-icons type="info-filled" :size="22" color="#ff4d4f"></uni-icons>
			<text class="bank__state-text">{{ banksError }}</text>
			<text class="bank__state-retry">点击重试</text>
		</view>

		<!-- 空数据 -->
		<zn-empty v-else-if="!banks.length" icon="list" text="题库暂未开放"
			desc="面试题库正在整理中，稍后再来看看吧" />

		<!-- 分类卡片（两列栅格：8 个分类一屏内基本可见，不必再翻页） -->
		<view v-else class="grid">
			<view v-for="item in banks" :key="item.id" class="grid__card" hover-class="zn-hover"
				@tap="goPractice(item)">
				<view class="grid__head">
					<text class="grid__name zn-ellipsis">{{ item.name }}</text>
					<text v-if="item.position" class="grid__pos zn-ellipsis">{{ item.position }}</text>
				</view>
				<view class="grid__foot">
					<text class="grid__count">{{ item.count }} 题</text>
					<text v-if="answeredOf(item)" class="grid__done">已刷 {{ answeredOf(item) }}</text>
				</view>
			</view>
		</view>

		<!-- ==================== 热门题目 ==================== -->
		<view class="bank__section">
			<zn-section-header title="热门题目" :subtitle="hotSubtitle" />
		</view>

		<view v-if="hotLoading" class="bank__state">
			<uni-icons type="spinner-cycle" :size="22" color="#00a6a7"></uni-icons>
			<text class="bank__state-text">正在加载题目…</text>
		</view>

		<view v-else-if="hotError" class="bank__state bank__state--error" hover-class="zn-hover" @tap="loadHot">
			<uni-icons type="info-filled" :size="22" color="#ff4d4f"></uni-icons>
			<text class="bank__state-text">{{ hotError }}</text>
			<text class="bank__state-retry">点击重试</text>
		</view>

		<zn-empty v-else-if="!hotQuestions.length" icon="chat" text="暂无热门题目"
			desc="题库更新后会在这里给出高频考题" />

		<view v-else class="hot">
			<view v-for="(q, i) in hotQuestions" :key="q.id" class="hot__item" hover-class="zn-hover"
				@tap="goQuestion(q)">
				<text class="hot__index">{{ i + 1 }}</text>
				<view class="hot__body">
					<view class="hot__title-row">
						<text v-if="q.isHot" class="hot__flag">热</text>
						<text class="hot__title zn-ellipsis-2">{{ q.question }}</text>
					</view>
					<view class="hot__meta">
						<text class="hot__meta-text">{{ q.difficultyText }}</text>
						<text v-if="q.source" class="hot__meta-text zn-ellipsis">{{ q.source }}</text>
						<text v-if="q.position" class="hot__meta-text zn-ellipsis">{{ q.position }}</text>
					</view>
				</view>
				<uni-icons type="right" :size="16" color="#c8ced6"></uni-icons>
			</view>
		</view>

		<view class="bank__tip">
			<uni-icons type="info" :size="14" color="#bbbbbb"></uni-icons>
			<text class="bank__tip-text">题目与参考答案由题库接口提供；列表接口不返回答案，进入刷题页按需拉取</text>
		</view>
	</view>
</template>

<script>
	/**
	 * 面试题库首页
	 *
	 * 数据来源（全部走 services/interview.js）：
	 *   GET /interview/banks            8 个二级职能分类（名称 / 题量 / 典型岗位）
	 *   GET /interview/questions        热门题目（pageSize=10，列表**不含答案**）
	 *   GET /interview/progress         刷题进度（🔒 需登录）
	 *
	 * ⚠️ 未登录时**不发** progress 请求，而不是「发了再 catch」：
	 *    services/api.js 对 401 会统一 toast（并清除本地登录态），页面层关不掉这个提示；
	 *    既然未登录是明确可知的状态，直接不发请求才是「不弹报错」的正确做法。
	 *    已登录但 token 过期时仍会走 catch 分支，此时 hero 显示「加载失败 + 重试」，
	 *    既让用户看得见失败，也不会白屏。
	 *
	 * ⚠️ 不做 mock 兜底：题库拉不到就是拉不到，页面给可点击重试的失败态，
	 *    绝不自己编一份分类列表假装有数据。
	 */
	import { getBanks, getQuestions, getPracticeProgress } from '@/services/interview.js'
	import { isLogined } from '@/services/user.js'

	/** 首页热门题目条数：只做「引流到刷题页」，不做完整列表 */
	const HOT_SIZE = 10

	export default {
		data() {
			return {
				isLogin: false,
				// ---------- 分类 ----------
				banks: [],
				stats: { total: 0, hot: 0 },
				banksLoading: false,
				banksError: '',
				// ---------- 热门题目 ----------
				hotQuestions: [],
				hotLoading: false,
				hotError: '',
				// ---------- 刷题进度 ----------
				progress: null,
				progressLoading: false,
				progressError: '',
				inited: false // onLoad 的首轮加载是否已结束（决定 onShow 要不要刷新）
			}
		},
		computed: {
			bankSubtitle() {
				if (this.banksLoading || this.banksError) return ''
				return this.banks.length ? '共 ' + this.banks.length + ' 个方向 · ' + this.stats.total + ' 道题' : ''
			},
			hotSubtitle() {
				return this.stats.hot ? this.stats.hot + ' 道高频题' : ''
			},
			/** 进度条百分比：分母用题库总题数，进度接口已给出 total */
			answeredPercent() {
				const p = this.progress
				if (!p || !p.total) return 0
				return Math.min(100, Math.round((p.answered / p.total) * 100))
			},
			/** 分类 id → 已作答题数（来自 progress.byCategory），用于分类卡片上的「已刷 n」 */
			answeredMap() {
				const map = {}
				const list = (this.progress && this.progress.byCategory) || []
				list.forEach(item => {
					if (item.answered) map[item.categoryId] = item.answered
				})
				return map
			}
		},
		onLoad() {
			this.loadAll()
		},
		onShow() {
			// 从刷题页 / 登录页返回时刷新进度。
			// ⚠️ 用 inited 区分「首次进入」（onLoad 已经在拉）与「返回本页」，
			//    否则进页面瞬间会重复请求一次进度。
			if (this.inited) {
				this.isLogin = isLogined()
				this.loadProgress()
			}
		},
		onPullDownRefresh() {
			this.loadAll(true)
		},
		methods: {
			/** 首屏 / 下拉刷新：三个请求并行，互不阻塞（任一失败只影响它自己的区块） */
			async loadAll(fromPull) {
				await Promise.all([this.loadBanks(), this.loadHot(), this.loadProgress()])
				this.inited = true
				if (fromPull) uni.stopPullDownRefresh()
			},
			async loadBanks() {
				this.banksLoading = true
				this.banksError = ''
				try {
					const res = await getBanks()
					this.banks = res.banks || []
					this.stats = { total: Number(res.total) || 0, hot: Number(res.hot) || 0 }
				} catch (e) {
					// 失败提示已由请求层统一弹出，这里补一个页面内的可重试失败态
					this.banks = []
					this.banksError = e.message || '题库加载失败'
				} finally {
					this.banksLoading = false
				}
			},
			async loadHot() {
				this.hotLoading = true
				this.hotError = ''
				try {
					const res = await getQuestions({ pageSize: HOT_SIZE })
					this.hotQuestions = res.list || []
				} catch (e) {
					this.hotQuestions = []
					this.hotError = e.message || '题目加载失败'
				} finally {
					this.hotLoading = false
				}
			},
			/**
			 * 刷题进度（需登录）
			 * 未登录直接返回并把 progress 置空 —— hero 据此展示登录引导。
			 */
			async loadProgress() {
				this.isLogin = isLogined()
				if (!this.isLogin) {
					this.progress = null
					this.progressError = ''
					this.progressLoading = false
					return
				}
				this.progressError = ''
				this.progressLoading = true
				try {
					this.progress = await getPracticeProgress()
				} catch (e) {
					this.progress = null
					this.progressError = e.message || '进度加载失败'
				} finally {
					this.progressLoading = false
				}
			},
			answeredOf(bank) {
				return this.answeredMap[bank.id] || 0
			},
			/* ---------------- 跳转 ---------------- */
			goLogin() {
				uni.navigateTo({
					url: '/pages/login/login',
					fail: () => uni.showToast({ title: '登录页打开失败，请稍后重试', icon: 'none' })
				})
			},
			goWrong() {
				uni.navigateTo({ url: '/pages/bank/wrong' })
			},
			goPractice(bank) {
				uni.navigateTo({ url: '/pages/bank/practice?category=' + encodeURIComponent(bank.id) })
			},
			/**
			 * 点热门题目 → 刷题页并直接定位到该题
			 * 传 category 是为了让刷题页拿到同一分类的上下文（上一题/下一题在同一职能内切换），
			 * id 由刷题页 onLoad 读取后作为起始题号。
			 */
			goQuestion(q) {
				uni.navigateTo({
					url:
						'/pages/bank/practice?category=' + encodeURIComponent(q.categoryId || '') +
						'&id=' + encodeURIComponent(q.id)
				})
			}
		}
	}
</script>

<style lang="scss" scoped>
	.bank {
		padding-bottom: 60rpx;
	}

	/* ==================== 进度总览 ==================== */
	.hero {
		margin: $zn-gap $zn-page-padding 0;
		border-radius: $zn-radius-lg;
		background: $zn-gradient;
		padding: 30rpx 28rpx;
		box-shadow: $zn-shadow-theme;
	}

	.hero__inner {
		display: flex;
		flex-direction: column;
	}

	.hero__title {
		font-size: 30rpx;
		font-weight: 700;
		color: #ffffff;
	}

	.hero__row {
		display: flex;
		flex-direction: row;
		align-items: baseline;
		margin-top: 16rpx;
	}

	.hero__num {
		font-size: 52rpx;
		font-weight: 700;
		color: #ffffff;
		line-height: 60rpx;
	}

	.hero__sep {
		font-size: 26rpx;
		color: rgba(255, 255, 255, 0.7);
		margin: 0 6rpx;
	}

	.hero__total {
		font-size: 26rpx;
		color: rgba(255, 255, 255, 0.86);
	}

	.hero__rate {
		font-size: 24rpx;
		color: #ffffff;
		margin-left: auto;
		background-color: rgba(255, 255, 255, 0.22);
		border-radius: $zn-radius-pill;
		padding: 6rpx 18rpx;
	}

	.hero__bar {
		margin-top: 20rpx;
	}

	.hero__foot {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 18rpx;
	}

	.hero__foot-text {
		font-size: 22rpx;
		color: rgba(255, 255, 255, 0.88);
	}

	.hero__dot {
		width: 8rpx;
		height: 8rpx;
		border-radius: 50%;
		background-color: rgba(255, 255, 255, 0.6);
		margin: 0 16rpx;
	}

	.hero__desc {
		font-size: 23rpx;
		color: rgba(255, 255, 255, 0.88);
		line-height: 36rpx;
		margin-top: 14rpx;
	}

	.hero__btn {
		align-self: flex-start;
		display: flex;
		flex-direction: row;
		align-items: center;
		height: 64rpx;
		padding: 0 26rpx;
		border-radius: $zn-radius-pill;
		background-color: #ffffff;
		margin-top: 22rpx;
	}

	.hero__btn-text {
		font-size: 26rpx;
		font-weight: 600;
		color: $zn-theme-deep;
		margin-left: 8rpx;
	}

	/* ==================== 薄弱点复盘入口 ==================== */
	.entry {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: 24rpx;
		margin: $zn-gap $zn-page-padding 0;
	}

	.entry__icon {
		width: 72rpx;
		height: 72rpx;
		border-radius: $zn-radius-sm;
		background-color: #fff2e8;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.entry__body {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin: 0 16rpx;
	}

	.entry__title {
		font-size: 30rpx;
		font-weight: 600;
		color: $zn-text-title;
	}

	.entry__desc {
		font-size: 22rpx;
		color: $zn-text-grey;
		margin-top: 6rpx;
	}

	/* ==================== 区块 ==================== */
	.bank__section {
		padding: 0 $zn-page-padding;
	}

	/* ---------- 加载 / 失败 / 空态的统一容器 ---------- */
	.bank__state {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 40rpx 24rpx;
		margin: 0 $zn-page-padding;
	}

	.bank__state--error {
		border: 2rpx solid #ffe0e0;
	}

	.bank__state-text {
		font-size: 24rpx;
		color: $zn-text-sub;
		margin-left: 12rpx;
	}

	.bank__state-retry {
		font-size: 24rpx;
		color: $zn-theme-deep;
		margin-left: 16rpx;
	}

	/* ---------- 分类栅格 ---------- */
	.grid {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		justify-content: space-between;
		padding: 0 $zn-page-padding;
	}

	.grid__card {
		width: 340rpx;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: 24rpx 22rpx;
		margin-bottom: 20rpx;
	}

	.grid__head {
		display: flex;
		flex-direction: column;
	}

	.grid__name {
		font-size: 30rpx;
		font-weight: 600;
		color: $zn-text-title;
	}

	.grid__pos {
		font-size: 21rpx;
		color: $zn-text-grey;
		margin-top: 8rpx;
	}

	.grid__foot {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 18rpx;
	}

	.grid__count {
		font-size: 22rpx;
		font-weight: 600;
		color: $zn-theme-deep;
	}

	.grid__done {
		font-size: 20rpx;
		color: $zn-text-light;
		margin-left: auto;
	}

	/* ---------- 热门题目 ---------- */
	.hot {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		margin: 0 $zn-page-padding;
		overflow: hidden;
	}

	.hot__item {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 24rpx;
		border-bottom: 1rpx solid $zn-line;

		&:last-child {
			border-bottom: none;
		}
	}

	.hot__index {
		width: 44rpx;
		font-size: 26rpx;
		font-weight: 700;
		color: $zn-text-light;
		flex-shrink: 0;
	}

	.hot__body {
		flex: 1;
		min-width: 0;
		margin-right: 12rpx;
	}

	.hot__title-row {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
	}

	.hot__flag {
		flex-shrink: 0;
		font-size: 18rpx;
		line-height: 28rpx;
		color: #ffffff;
		background-color: $zn-red;
		border-radius: 6rpx;
		padding: 0 8rpx;
		margin: 4rpx 10rpx 0 0;
	}

	.hot__title {
		flex: 1;
		min-width: 0;
		font-size: 28rpx;
		color: $zn-text-main;
		line-height: 40rpx;
	}

	.hot__meta {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 12rpx;
	}

	.hot__meta-text {
		font-size: 20rpx;
		color: $zn-text-grey;
		background-color: $zn-bg-grey;
		border-radius: 6rpx;
		padding: 3rpx 10rpx;
		margin-right: 12rpx;
		max-width: 240rpx;
	}

	/* ---------- 底部说明 ---------- */
	.bank__tip {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		padding: 30rpx $zn-page-padding 10rpx;
	}

	.bank__tip-text {
		font-size: 21rpx;
		color: $zn-text-light;
		margin-left: 8rpx;
	}
</style>
