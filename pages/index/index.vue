<template>
	<view class="zn-page home">
		<!-- ==================== 顶部：状态栏 + 品牌栏 + 搜索框 ==================== -->
		<view class="home__header" :style="{ paddingTop: statusBarHeight + 'px' }">
			<view class="home__topbar">
				<view class="home__brand">
					<text class="home__brand-name">直聘通</text>
					<text class="home__brand-slogan">好工作，直接聊</text>
				</view>
				<view class="home__icon-btn" hover-class="zn-hover" @tap="goMessage">
					<uni-icons type="notification" :size="21" color="#ffffff"></uni-icons>
					<text v-if="unreadCount > 0" class="home__icon-badge">{{ unreadCount > 99 ? '99+' : unreadCount }}</text>
				</view>
			</view>

			<!-- 搜索入口：首页不做输入，统一点进搜索页（那里才有热词与历史） -->
			<view class="home__search" hover-class="zn-hover" @tap="goSearch">
				<uni-icons type="search" :size="18" color="#9aa0a6"></uni-icons>
				<text class="home__search-ph">{{ searchPlaceholder }}</text>
				<view class="home__search-btn">
					<text class="home__search-btn-text">搜索</text>
				</view>
			</view>
		</view>

		<!-- ==================== 内容区 ==================== -->
		<view class="home__body">
			<!-- 三态之一：加载失败（纯接口模式，不做 Mock 兜底，给可点重试） -->
			<view v-if="loadFailed && !loading" class="state" hover-class="zn-hover" @tap="loadHome">
				<uni-icons type="refresh" :size="18" color="#00a6a7"></uni-icons>
				<text class="state__text">首页数据加载失败，点击重试</text>
			</view>
			<!-- 三态之二：加载中 -->
			<view v-else-if="loading" class="state">
				<text class="state__text">正在加载职位…</text>
			</view>

			<template v-else>
				<!-- ---------- 1. 轮播 ---------- -->
				<view v-if="home.banners.length" class="banner">
					<swiper class="banner__swiper" :autoplay="true" :interval="4000" :duration="400" circular
						@change="onBannerChange">
						<swiper-item v-for="(item, i) in home.banners" :key="item.id">
							<!-- 渐变按序号轮换：色值写在 SCSS 里（要用到 $zn-theme 系列变量），模板只切 class -->
							<view class="banner__item" :class="'is-g' + (i % 3)" hover-class="zn-hover"
								@tap="navigate(item.link)">
								<view class="banner__tag">{{ item.tag }}</view>
								<view class="banner__text">
									<text class="banner__title">{{ item.title }}</text>
									<text class="banner__subtitle">{{ item.subtitle }}</text>
								</view>
								<text class="banner__watermark">{{ i + 1 }}</text>
							</view>
						</swiper-item>
					</swiper>
					<view class="banner__dots">
						<view v-for="(item, i) in home.banners" :key="'dot' + item.id" class="banner__dot"
							:class="{ 'is-active': bannerIndex === i }"></view>
					</view>
				</view>

				<!-- ---------- 2. 职能入口（5 列 × 2 行） ---------- -->
				<view v-if="home.entries.length" class="entries">
					<view v-for="item in home.entries" :key="item.id" class="entries__item" hover-class="zn-hover"
						@tap="navigate(item.link)">
						<view class="entries__icon" :style="{ backgroundColor: item.bg }">
							<!-- 服务端给的是图标名，必须过一遍白名单（见 normalizeIcon：不在白名单的字形会渲染成空白） -->
							<uni-icons :type="normalizeIcon(item.icon)" :size="26" :color="item.color"></uni-icons>
						</view>
						<text class="entries__name">{{ item.name }}</text>
					</view>
				</view>

				<!-- ---------- 3. 公告（竖向滚动） ---------- -->
				<view v-if="home.notices.length" class="notice">
					<uni-icons type="notification-filled" :size="15" color="#00a6a7"></uni-icons>
					<swiper class="notice__swiper" vertical circular :autoplay="true" :interval="3200" :duration="500">
						<swiper-item v-for="(n, i) in home.notices" :key="'notice' + i">
							<text class="notice__text zn-ellipsis">{{ n }}</text>
						</swiper-item>
					</swiper>
				</view>

				<!-- ---------- 4. 列表标签（全部/社招/急聘/内推/实习/校招） ---------- -->
				<view v-if="home.listTabs.length" class="tabs">
					<view v-for="tab in home.listTabs" :key="tab.id" class="tabs__item" hover-class="zn-hover"
						@tap="goListByKind(tab.kind)">
						<text class="tabs__text">{{ tab.name }}</text>
					</view>
				</view>

				<!-- ---------- 5. 推荐职位 ---------- -->
				<zn-section-header title="推荐职位" :subtitle="totalJobsText" more="更多职位" @more="goAllJobs" />
				<view v-if="home.recommend.length" class="joblist">
					<!-- 外面套一层 view 是为了给卡片之间留间距：easycom 组件的根节点样式无法从页面里选到 -->
					<view v-for="job in home.recommend" :key="job.id" class="joblist__item">
						<zn-job-card :job="job" show-favorite @tap="goDetail" @favorite="onFavorite" />
					</view>
				</view>
				<zn-empty v-else text="暂无推荐职位" desc="换个职能方向看看，或直接搜索职位关键词" />

				<!-- ---------- 6. 急招专区（横向滚动） ---------- -->
				<template v-if="home.urgent.length">
					<zn-section-header title="急招专区" subtitle="HR 平均 2 小时回复" more="全部急招"
						@more="goUrgentAll" />
					<scroll-view class="hscroll" scroll-x :show-scrollbar="false">
						<view class="hscroll__row">
							<view v-for="job in home.urgent" :key="job.id" class="ucard" hover-class="zn-hover"
								@tap="goDetail(job)">
								<view class="ucard__tag">
									<uni-icons type="fire-filled" :size="12" color="#ffffff"></uni-icons>
									<text class="ucard__tag-text">急招</text>
								</view>
								<text class="ucard__title zn-ellipsis">{{ job.title }}</text>
								<text class="ucard__salary">{{ job.salaryText }}</text>
								<text class="ucard__meta zn-ellipsis">{{ job.experience }} · {{ job.education }}</text>
								<text class="ucard__company zn-ellipsis">{{ job.companyName || job.companyFullName }}</text>
								<text class="ucard__location zn-ellipsis">{{ job.location }}</text>
							</view>
						</view>
					</scroll-view>
				</template>

				<!-- ---------- 7. 内推专区（横向 2~3 张 + 查看全部） ---------- -->
				<template v-if="home.referral.length">
					<zn-section-header title="名企内推" subtitle="跳过初筛，简历直达用人部门" more="查看全部"
						@more="goReferralZone" />
					<scroll-view class="hscroll" scroll-x :show-scrollbar="false">
						<view class="hscroll__row">
							<view v-for="job in home.referral" :key="job.id" class="rcard" hover-class="zn-hover"
								@tap="goDetail(job)">
								<view class="rcard__head">
									<view class="rcard__tag">
										<uni-icons type="gift" :size="12" color="#ffffff"></uni-icons>
										<text class="rcard__tag-text">内推</text>
									</view>
									<text class="rcard__salary">{{ job.salaryText }}</text>
								</view>
								<text class="rcard__title zn-ellipsis">{{ job.title }}</text>
								<text class="rcard__company zn-ellipsis">{{ job.companyName || job.companyFullName }}</text>
								<view class="rcard__line">
									<text class="rcard__meta zn-ellipsis">{{ job.location }}</text>
									<text class="rcard__meta">{{ job.experience }}</text>
								</view>
								<!-- 内推奖金只有详情接口返回，列表页不编造；这里如实引导到详情 -->
								<text class="rcard__tip">内推奖金见职位详情</text>
							</view>
						</view>
					</scroll-view>
				</template>
			</template>
		</view>

		<!-- ==================== 底部 tabBar ==================== -->
		<zn-tab-bar current="index" />
	</view>
</template>

<script>
	/**
	 * 职位首页（求职者端浏览主链路的入口）
	 *
	 * 数据来源：GET /job/home（services/job.js 的 getJobHome）一次拿全 9 个区块：
	 *   banners / entries / notices / hotKeywords / listTabs / recommend / referral / urgent / totalJobs
	 * 之所以不在页面里分别读 page_config：/job/home 已经把配置包装成业务语义的键，
	 * 多读几次配置只会多几个并发请求，还得自己做键名映射。
	 *
	 * ⚠️ 纯接口模式：接口失败不做 Mock 兜底，直接展示失败态 + 重试入口，
	 *    避免用户看到与真实数据不一致的「假职位」。
	 */
	import { getJobHome, toggleFavorite } from '@/services/job.js'
	import { getUnread } from '@/services/im.js'
	import { isLogined } from '@/services/user.js'

	/** 底部 tabBar 页面：navigateTo 对它们是无效的（会失败），必须换 reLaunch */
	const TAB_PAGES = ['/pages/index/index', '/pages/seeker/center', '/pages/ai/ai', '/pages/mine/mine']

	/**
	 * uni-icons 白名单（公约第二节）。
	 *
	 * ⚠️ 为什么还要一层映射：
	 *    职能入口的 icon 名来自服务端 rcHomeEntries（如 color/chart/shop/wallet/phone/cart），
	 *    这些名字**不在**公约确认存在的白名单里，直接透传会渲染成空白方块。
	 *    这里把服务端可能给出的名字收敛到白名单中最接近的字形，
	 *    既保证「图标一定能画出来」，也不至于让 10 个入口长得一模一样。
	 *    未收录的名字统一退化为 list（列表），绝不透传原始值。
	 */
	const ICON_ALIAS = {
		gear: 'gear',
		compose: 'compose',
		star: 'star',
		paperplane: 'paperplane',
		flag: 'medal-filled',
		color: 'star-filled', // 设计创意
		chart: 'bars', // 运营 / 数据
		shop: 'gift', // 销售 / 商务
		wallet: 'list', // 财务审计（台账）
		phone: 'headphones', // 客户服务
		cart: 'paperplane-filled', // 供应链物流（发运）
		settings: 'gear'
	}

	export default {
		data() {
			return {
				statusBarHeight: 0,
				searchPlaceholder: '搜索职位 / 公司，如「前端开发」',
				// 首页聚合数据：键名与 /job/home 返回一一对应，初值全部为空，不做假数据
				home: {
					banners: [],
					entries: [],
					notices: [],
					hotKeywords: [],
					listTabs: [],
					recommend: [],
					referral: [],
					urgent: [],
					totalJobs: 0
				},
				bannerIndex: 0,
				loading: false, // 首屏 / 下拉刷新中的聚合请求
				loadFailed: false, // 加载失败态（纯接口模式：不做 Mock 兜底）
				unreadCount: 0 // 未读沟通数（getUnread 的 candidate 字段；未登录时静默为 0）
			}
		},
		computed: {
			totalJobsText() {
				return this.home.totalJobs ? '在招 ' + this.home.totalJobs + ' 个职位' : ''
			}
		},
		async onLoad() {
			this.statusBarHeight = uni.getSystemInfoSync().statusBarHeight || 0
			await this.loadHome()
		},
		onShow() {
			// 从消息页 / 会话页返回时角标要跟着变，所以每次显示都重新取一次未读数
			this.loadUnread()
		},
		async onPullDownRefresh() {
			// 下拉刷新：真实重新拉取（不是本地重排），并复位轮播下标
			try {
				this.bannerIndex = 0
				await this.loadHome()
				if (!this.loadFailed) {
					uni.showToast({ title: '已是最新职位', icon: 'none' })
				}
			} finally {
				// 无论成功失败都要收起刷新动画，否则下拉指示器会一直转
				uni.stopPullDownRefresh()
			}
		},
		methods: {
			/* ---------------- 数据 ---------------- */
			async loadHome() {
				this.loading = true
				try {
					const data = await getJobHome()
					// 服务端保证这些键永远存在（缺失给 []），这里仍逐个兜底成数组只是为了模板不炸
					this.home = {
						banners: data.banners || [],
						entries: data.entries || [],
						notices: data.notices || [],
						hotKeywords: data.hotKeywords || [],
						listTabs: data.listTabs || [],
						recommend: data.recommend || [],
						referral: data.referral || [],
						urgent: data.urgent || [],
						totalJobs: Number(data.totalJobs) || 0
					}
					this.loadFailed = false
				} catch (e) {
					// 错误提示已由 services/api.js 统一弹出，这里只负责切换到失败态
					this.loadFailed = true
				} finally {
					this.loading = false
				}
			},
			/**
			 * 未读角标
			 * ⚠️ 未登录时该接口返回 401（im.js 已把 showError 关掉），
			 *    首页是公开页面，**静默忽略**即可，不能弹「登录失效」打断浏览。
			 */
			async loadUnread() {
				try {
					const res = await getUnread()
					this.unreadCount = Number(res && res.candidate) || 0
				} catch (e) {
					this.unreadCount = 0
				}
			},

			/* ---------------- 展示辅助 ---------------- */
			normalizeIcon(icon) {
				return ICON_ALIAS[icon] || 'list'
			},
			onBannerChange(e) {
				this.bannerIndex = e.detail.current
			},

			/* ---------------- 跳转 ---------------- */
			/**
			 * 统一跳转：link 是服务端配置里的完整路径（可能带 query）
			 * ⚠️ navigateTo 不能跳 tabBar 页，命中就直接 reLaunch；
			 *    其余未知页面（如尚未注册的路由）用 toast 如实反馈，不假装跳成功。
			 */
			navigate(link) {
				if (!link) return
				const path = String(link).split('?')[0]
				if (TAB_PAGES.indexOf(path) > -1) {
					uni.reLaunch({ url: link })
					return
				}
				uni.navigateTo({
					url: link,
					fail: () => {
						uni.showToast({ title: '该页面暂时无法打开', icon: 'none' })
					}
				})
			},
			goSearch() {
				uni.navigateTo({ url: '/pages/job/search' })
			},
			goMessage() {
				uni.navigateTo({ url: '/pages/mine/message' })
			},
			goListByKind(kind) {
				uni.navigateTo({ url: '/pages/job/list?kind=' + encodeURIComponent(kind || 'all') })
			},
			goAllJobs() {
				uni.navigateTo({ url: '/pages/job/list' })
			},
			goUrgentAll() {
				uni.navigateTo({ url: '/pages/job/list?kind=urgent' })
			},
			goReferralZone() {
				uni.navigateTo({ url: '/pages/job/referral' })
			},
			goDetail(job) {
				if (!job || !job.id) return
				uni.navigateTo({ url: '/pages/job/detail?id=' + encodeURIComponent(job.id) })
			},

			/* ---------------- 收藏 ---------------- */
			/**
			 * 收藏 / 取消收藏
			 * ⚠️ 收藏接口必须登录：未登录时**先提示再去登录页**，
			 *    而不是把 401 抛给用户看（services/api.js 也会清登录态并提示一次，这里不再重复弹提示）。
			 */
			async onFavorite(job) {
				if (!isLogined()) {
					uni.showToast({ title: '登录后才能收藏职位', icon: 'none' })
					setTimeout(() => uni.navigateTo({ url: '/pages/login/login' }), 800)
					return
				}
				try {
					const next = await toggleFavorite(job.id, job.isFavorite)
					// 就地更新这一条卡片的状态（Vue 3 的响应式代理对数组元素属性赋值可直接生效）
					job.isFavorite = next
					uni.showToast({ title: next ? '已收藏' : '已取消收藏', icon: 'none' })
				} catch (e) {
					// 失败提示已由请求层统一弹出；状态保持原样，不做乐观更新回滚
				}
			}
		}
	}
</script>

<style lang="scss" scoped>
	.home {
		/* 顶部渐变是满幅的，所以根节点不再留左右内边距，交给各区块自己控制 */
		background-color: $zn-bg-page;
	}

	/* ==================== 顶部 ==================== */
	.home__header {
		background: $zn-gradient;
		padding-bottom: 56rpx;
	}

	.home__topbar {
		height: 88rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		padding: 0 $zn-page-padding;
	}

	.home__brand {
		display: flex;
		flex-direction: row;
		align-items: baseline;
	}

	.home__brand-name {
		font-size: 38rpx;
		font-weight: 700;
		color: #ffffff;
		letter-spacing: 1rpx;
	}

	.home__brand-slogan {
		font-size: 20rpx;
		color: rgba(255, 255, 255, 0.82);
		margin-left: 14rpx;
	}

	.home__icon-btn {
		position: relative;
		width: 64rpx;
		height: 64rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.home__icon-badge {
		position: absolute;
		right: 0;
		top: 4rpx;
		min-width: 28rpx;
		height: 28rpx;
		padding: 0 6rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-red;
		color: #ffffff;
		font-size: 18rpx;
		line-height: 28rpx;
		text-align: center;
		border: 2rpx solid #ffffff;
	}

	.home__search {
		margin: 8rpx $zn-page-padding 0;
		height: 76rpx;
		background-color: #ffffff;
		border-radius: $zn-radius-pill;
		display: flex;
		flex-direction: row;
		align-items: center;
		padding-left: 22rpx;
		box-shadow: 0 6rpx 16rpx rgba(0, 105, 107, 0.12);
	}

	.home__search-ph {
		flex: 1;
		min-width: 0;
		font-size: 26rpx;
		color: $zn-text-light;
		margin-left: 12rpx;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	.home__search-btn {
		height: 60rpx;
		padding: 0 34rpx;
		margin-right: 8rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.home__search-btn-text {
		color: #ffffff;
		font-size: 26rpx;
		font-weight: 600;
	}

	/* ==================== 内容区 ==================== */
	.home__body {
		position: relative;
		z-index: 2;
		margin-top: -32rpx;
		border-top-left-radius: 36rpx;
		border-top-right-radius: 36rpx;
		background-color: $zn-bg-page;
		padding: 28rpx $zn-page-padding 20rpx;
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

	/* ---------- 轮播 ---------- */
	.banner {
		position: relative;
	}

	.banner__swiper {
		height: 280rpx;
	}

	.banner__item {
		position: relative;
		height: 280rpx;
		border-radius: $zn-radius-lg;
		overflow: hidden;
		padding: 40rpx 36rpx;
		display: flex;
		flex-direction: column;
		justify-content: center;

		/* 三套同色系渐变：只用 uni.scss 里的主色变量，避免出现绿/青混用 */
		&.is-g0 {
			background: $zn-gradient;
		}

		&.is-g1 {
			background: $zn-gradient-soft;
		}

		&.is-g2 {
			background: linear-gradient(135deg, $zn-theme 0%, $zn-theme-deep 55%, $zn-theme-dark 100%);
		}
	}

	.banner__tag {
		align-self: flex-start;
		background-color: rgba(255, 255, 255, 0.25);
		color: #ffffff;
		font-size: 20rpx;
		font-weight: 600;
		padding: 4rpx 16rpx;
		border-radius: $zn-radius-pill;
		margin-bottom: 18rpx;
	}

	.banner__text {
		display: flex;
		flex-direction: column;
	}

	.banner__title {
		font-size: 40rpx;
		font-weight: 700;
		color: #ffffff;
		line-height: 54rpx;
	}

	.banner__subtitle {
		font-size: 23rpx;
		color: rgba(255, 255, 255, 0.88);
		margin-top: 10rpx;
	}

	.banner__watermark {
		position: absolute;
		right: 24rpx;
		bottom: -34rpx;
		font-size: 170rpx;
		font-weight: 700;
		color: rgba(255, 255, 255, 0.16);
		line-height: 1;
	}

	.banner__dots {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		margin-top: 16rpx;
	}

	.banner__dot {
		width: 12rpx;
		height: 6rpx;
		border-radius: $zn-radius-pill;
		background-color: #d5dbe1;
		margin: 0 6rpx;
		transition: all 0.3s;

		&.is-active {
			width: 32rpx;
			background-color: $zn-theme;
		}
	}

	/* ---------- 职能入口 ---------- */
	.entries {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 28rpx 8rpx 6rpx;
		margin-top: $zn-gap;
		box-shadow: $zn-shadow-sm;
	}

	.entries__item {
		width: 20%;
		display: flex;
		flex-direction: column;
		align-items: center;
		margin-bottom: 26rpx;
	}

	.entries__icon {
		width: 84rpx;
		height: 84rpx;
		border-radius: 26rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.entries__name {
		font-size: 22rpx;
		color: $zn-text-main;
		margin-top: 12rpx;
		text-align: center;
		line-height: 30rpx;
		max-width: 130rpx;
	}

	/* ---------- 公告 ---------- */
	.notice {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-pill;
		height: 68rpx;
		padding: 0 24rpx;
		margin-top: 6rpx;
		box-shadow: $zn-shadow-sm;
	}

	.notice__swiper {
		flex: 1;
		min-width: 0;
		height: 40rpx;
		margin-left: 12rpx;
	}

	.notice__text {
		font-size: 24rpx;
		color: $zn-text-sub;
		line-height: 40rpx;
	}

	/* ---------- 列表标签 ---------- */
	.tabs {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		margin-top: $zn-gap;
	}

	.tabs__item {
		height: 64rpx;
		padding: 0 28rpx;
		margin: 0 16rpx 16rpx 0;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-card;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-sm;
	}

	.tabs__text {
		font-size: 26rpx;
		color: $zn-theme-dark;
		font-weight: 500;
	}

	/* ---------- 推荐职位 ---------- */
	.joblist {
		display: flex;
		flex-direction: column;
	}

	.joblist__item {
		margin-bottom: $zn-gap;
	}

	/* ---------- 横向滚动容器 ---------- */
	.hscroll {
		white-space: nowrap;
	}

	.hscroll__row {
		display: flex;
		flex-direction: row;
	}

	/* ---------- 急招小卡 ---------- */
	.ucard {
		width: 300rpx;
		flex-shrink: 0;
		margin-right: 20rpx;
		background-color: $zn-bg-card;
		border-radius: $zn-radius;
		padding: 22rpx 20rpx;
		display: flex;
		flex-direction: column;
		box-shadow: $zn-shadow-sm;
	}

	.ucard__tag {
		align-self: flex-start;
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: $zn-red;
		border-radius: $zn-radius-xs;
		padding: 2rpx 10rpx;
	}

	.ucard__tag-text {
		font-size: 18rpx;
		color: #ffffff;
		margin-left: 4rpx;
	}

	.ucard__title {
		font-size: 28rpx;
		font-weight: 600;
		color: $zn-text-title;
		margin-top: 14rpx;
	}

	.ucard__salary {
		font-size: 30rpx;
		font-weight: 700;
		color: $zn-price;
		margin-top: 8rpx;
	}

	.ucard__meta {
		font-size: 22rpx;
		color: $zn-text-sub;
		margin-top: 8rpx;
	}

	.ucard__company {
		font-size: 22rpx;
		color: $zn-text-main;
		margin-top: 12rpx;
	}

	.ucard__location {
		font-size: 20rpx;
		color: $zn-text-grey;
		margin-top: 4rpx;
	}

	/* ---------- 内推卡 ---------- */
	.rcard {
		width: 420rpx;
		flex-shrink: 0;
		margin-right: 20rpx;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 24rpx 22rpx;
		display: flex;
		flex-direction: column;
		box-shadow: $zn-shadow-sm;
		border-left: 8rpx solid $zn-orange;
	}

	.rcard__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.rcard__tag {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: $zn-orange;
		border-radius: $zn-radius-xs;
		padding: 2rpx 10rpx;
	}

	.rcard__tag-text {
		font-size: 18rpx;
		color: #ffffff;
		margin-left: 4rpx;
	}

	.rcard__salary {
		font-size: 30rpx;
		font-weight: 700;
		color: $zn-price;
	}

	.rcard__title {
		font-size: 30rpx;
		font-weight: 600;
		color: $zn-text-title;
		margin-top: 14rpx;
	}

	.rcard__company {
		font-size: 24rpx;
		color: $zn-text-sub;
		margin-top: 8rpx;
	}

	.rcard__line {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		margin-top: 10rpx;
	}

	.rcard__meta {
		font-size: 22rpx;
		color: $zn-text-grey;
	}

	.rcard__tip {
		font-size: 20rpx;
		color: $zn-orange;
		background-color: #fff4e6;
		border-radius: $zn-radius-xs;
		padding: 6rpx 12rpx;
		margin-top: 14rpx;
		align-self: flex-start;
	}
</style>
