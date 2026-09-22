<template>
	<view class="zn-page zn-page--no-tabbar referral">
		<zn-nav-bar title="名企内推专区" show-back border />

		<!-- ==================== 专区头图（纯渐变 + 文案，零图片） ==================== -->
		<view class="hero">
			<text class="hero__title">{{ zone.title }}</text>
			<text class="hero__subtitle">{{ zone.subtitle }}</text>
			<view v-if="total > 0" class="hero__stat">
				<text class="hero__stat-num">{{ total }}</text>
				<text class="hero__stat-text">个内推职位正在招聘</text>
			</view>
		</view>

		<!-- ==================== 配置里的活动位（有才渲染，没配就不占位） ==================== -->
		<view v-if="banners.length" class="banners">
			<view v-for="(b, i) in banners" :key="b.id || i" class="bcard" :class="'is-g' + (i % 2)"
				hover-class="zn-hover" @tap="navigate(b.link)">
				<view class="bcard__tag">{{ b.tag }}</view>
				<text class="bcard__title">{{ b.title }}</text>
				<text class="bcard__subtitle">{{ b.subtitle }}</text>
			</view>
		</view>

		<!-- ==================== 内推职位 ==================== -->
		<view class="referral__body">
			<zn-section-header title="内推职位" :subtitle="totalText" />
			<!-- 列表接口不返回内推奖金，只有详情接口的 job.referralBonus 有，所以这里如实引导，不猜数字 -->
			<text class="referral__tip">点开职位详情可查看该岗位的内推奖金与内推人信息</text>

			<view v-if="loading" class="state">
				<text class="state__text">正在加载内推职位…</text>
			</view>

			<view v-else-if="loadFailed" class="state" hover-class="zn-hover" @tap="refresh">
				<uni-icons type="refresh" :size="18" color="#00a6a7"></uni-icons>
				<text class="state__text">内推职位加载失败，点击重试</text>
			</view>

			<zn-empty v-else-if="!list.length" text="暂无内推职位" desc="内推岗位每周更新，可以先去职位列表看看急招岗位" />

			<template v-else>
				<view v-for="job in list" :key="job.id" class="referral__item">
					<zn-job-card :job="job" @tap="goDetail" />
				</view>
				<view class="more">
					<text v-if="loadingMore" class="more__text">正在加载更多…</text>
					<text v-else-if="loadMoreFailed" class="more__text more__text--tap" @tap="loadMore">
						加载更多失败，点击重试
					</text>
					<text v-else-if="hasMore" class="more__text">上拉加载更多</text>
					<text v-else class="more__text">内推职位已全部展示</text>
				</view>
			</template>
		</view>

		<!-- ==================== 内推规则 ==================== -->
		<view v-if="rules.length" class="card">
			<view class="card__head">
				<view class="card__bar"></view>
				<text class="card__title">内推规则</text>
			</view>
			<view v-for="(r, i) in rules" :key="'rule' + i" class="rule">
				<view class="rule__no">
					<text class="rule__no-text">{{ i + 1 }}</text>
				</view>
				<text class="rule__text">{{ r }}</text>
			</view>
		</view>

		<!-- ==================== 常见问题（折叠面板） ==================== -->
		<view v-if="faq.length" class="card">
			<view class="card__head">
				<view class="card__bar"></view>
				<text class="card__title">常见问题</text>
			</view>
			<view v-for="(f, i) in faq" :key="'faq' + i" class="faq">
				<view class="faq__q" hover-class="zn-hover" @tap="toggleFaq(i)">
					<text class="faq__q-text">{{ f.q }}</text>
					<view class="faq__arrow" :class="{ 'is-open': openFaq === i }">
						<uni-icons type="arrow-down" :size="14" color="#999999"></uni-icons>
					</view>
				</view>
				<text v-if="openFaq === i" class="faq__a">{{ f.a }}</text>
			</view>
		</view>
	</view>
</template>

<script>
	/**
	 * 名企内推专区
	 *
	 * 接口：
	 *   getConfig('rcReferralZone')     专区文案：{title, subtitle, banners, rules, faq}
	 *   getJobList({kind:'referral'})   内推职位（分页）
	 *
	 * ⚠️ 兜底边界（重要）：
	 *    只给「纯展示文案」兜底（标题/副标题/规则/FAQ），配置接口挂了页面不至于是一片空白；
	 *    **绝不**给职位数据兜底 —— 内推职位列表接口失败就是失败态 + 重试，
	 *    否则用户会看到一批并不存在的「内推岗位」。
	 *    另：列表接口不返回内推奖金（只有详情接口有 job.referralBonus），
	 *    所以列表页不显示奖金数字，只做如实引导。
	 */
	import { getJobList } from '@/services/job.js'
	import { getConfig } from '@/services/content.js'

	/** 降级用的纯展示文案（仅在 rcReferralZone 取不到时使用） */
	const DEFAULT_ZONE = {
		title: '名企内推专区',
		subtitle: '在职员工帮你递简历，跳过初筛直通业务面试',
		banners: [],
		rules: [
			'内推服务完全免费，任何以「内推费、保过费、押金」名义收费的都是骗局',
			'内推只加快简历流转，不改变企业的面试与录用标准',
			'建议选择与自身经历匹配度最高的岗位，避免对同一家公司重复投递'
		],
		faq: [
			{
				q: '内推和普通投递有什么区别？',
				a: '内推由在职员工把简历直接提交给用人部门或招聘负责人，通常能跳过初筛环节，反馈更快；但面试标准与普通投递完全一致。'
			},
			{
				q: '使用内推需要付费吗？',
				a: '不需要。直聘通的内推服务完全免费，任何以「内推费、保过费」名义收费的都是骗局，请立即举报。'
			}
		]
	}

	/** 底部 tabBar 页面不能被 navigateTo 打开，需要走 reLaunch */
	const TAB_PAGES = ['/pages/index/index', '/pages/seeker/center', '/pages/ai/ai', '/pages/mine/mine']

	export default {
		data() {
			return {
				zone: Object.assign({}, DEFAULT_ZONE),
				// 职位数据：初值只有空数组，没有兜底数据
				list: [],
				total: 0,
				page: 1,
				pageSize: 10,
				hasMore: false,
				loading: false,
				loadingMore: false,
				loadFailed: false,
				loadMoreFailed: false,
				openFaq: -1 // 当前展开的 FAQ 下标，-1 表示全部收起
			}
		},
		computed: {
			banners() {
				return this.zone.banners || []
			},
			rules() {
				return this.zone.rules || []
			},
			faq() {
				return this.zone.faq || []
			},
			totalText() {
				return this.total > 0 ? '共 ' + this.total + ' 个' : ''
			}
		},
		async onLoad() {
			// 文案与职位互不依赖，并行拉取：任一失败都不影响另一个区块的展示
			this.loadZone()
			await this.refresh()
		},
		async onPullDownRefresh() {
			try {
				this.loadZone()
				await this.refresh()
			} finally {
				uni.stopPullDownRefresh()
			}
		},
		onReachBottom() {
			this.loadMore()
		},
		methods: {
			async loadZone() {
				try {
					const data = await getConfig('rcReferralZone')
					if (!data || typeof data !== 'object') return
					// 逐字段合并：配置里只给了部分字段时，缺的用降级文案，不整体替换
					this.zone = {
						title: data.title || DEFAULT_ZONE.title,
						subtitle: data.subtitle || DEFAULT_ZONE.subtitle,
						banners: Array.isArray(data.banners) ? data.banners : [],
						rules: Array.isArray(data.rules) && data.rules.length ? data.rules : DEFAULT_ZONE.rules,
						faq: Array.isArray(data.faq) && data.faq.length ? data.faq : DEFAULT_ZONE.faq
					}
				} catch (e) {
					// 配置缺失（服务端 42001）不是错误：保留降级文案即可，界面无需提示
				}
			},
			async refresh() {
				this.loading = true
				this.loadFailed = false
				this.loadMoreFailed = false
				try {
					const res = await getJobList({ kind: 'referral', page: 1, pageSize: this.pageSize })
					this.list = res.list || []
					this.total = Number(res.total) || 0
					this.page = Number(res.page) || 1
					this.hasMore = !!res.hasMore
				} catch (e) {
					this.list = []
					this.total = 0
					this.hasMore = false
					this.loadFailed = true
				} finally {
					this.loading = false
				}
			},
			async loadMore() {
				if (this.loading || this.loadingMore || !this.hasMore) return
				this.loadingMore = true
				this.loadMoreFailed = false
				try {
					const next = this.page + 1
					const res = await getJobList({ kind: 'referral', page: next, pageSize: this.pageSize })
					this.list = this.list.concat(res.list || [])
					this.page = Number(res.page) || next
					this.hasMore = !!res.hasMore
				} catch (e) {
					this.loadMoreFailed = true
				} finally {
					this.loadingMore = false
				}
			},
			/** FAQ 折叠：同一时间只展开一条，避免答案把列表撑得太长 */
			toggleFaq(i) {
				this.openFaq = this.openFaq === i ? -1 : i
			},
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
			goDetail(job) {
				if (!job || !job.id) return
				uni.navigateTo({ url: '/pages/job/detail?id=' + encodeURIComponent(job.id) })
			}
		}
	}
</script>

<style lang="scss" scoped>
	.referral {
		background-color: $zn-bg-page;
	}

	/* ==================== 头图 ==================== */
	.hero {
		background: $zn-gradient;
		padding: $zn-gap-lg $zn-page-padding 48rpx;
		display: flex;
		flex-direction: column;
	}

	.hero__title {
		font-size: $zn-font-xl + 4rpx;
		font-weight: 700;
		color: #ffffff;
	}

	.hero__subtitle {
		font-size: $zn-font-sm;
		color: rgba(255, 255, 255, 0.88);
		line-height: 36rpx;
		margin-top: 12rpx;
	}

	.hero__stat {
		display: flex;
		flex-direction: row;
		align-items: baseline;
		margin-top: 20rpx;
	}

	.hero__stat-num {
		font-size: 40rpx;
		font-weight: 700;
		color: #ffffff;
	}

	.hero__stat-text {
		font-size: $zn-font-sm;
		color: rgba(255, 255, 255, 0.88);
		margin-left: 8rpx;
	}

	/* ==================== 活动位 ==================== */
	.banners {
		padding: 0 $zn-page-padding;
		margin-top: -28rpx;
	}

	.bcard {
		border-radius: $zn-radius-lg;
		padding: 24rpx;
		margin-bottom: 16rpx;
		display: flex;
		flex-direction: column;
		box-shadow: $zn-shadow-sm;

		&.is-g0 {
			background: linear-gradient(135deg, $zn-theme 0%, $zn-theme-deep 100%);
		}

		&.is-g1 {
			background: linear-gradient(135deg, $zn-theme-deep 0%, $zn-theme-dark 100%);
		}
	}

	.bcard__tag {
		align-self: flex-start;
		font-size: $zn-font-xs;
		color: #ffffff;
		background-color: rgba(255, 255, 255, 0.25);
		border-radius: $zn-radius-xs;
		padding: 2rpx 12rpx;
		margin-bottom: 14rpx;
	}

	.bcard__title {
		font-size: $zn-font-lg;
		font-weight: 700;
		color: #ffffff;
	}

	.bcard__subtitle {
		font-size: $zn-font-sm;
		color: rgba(255, 255, 255, 0.86);
		margin-top: 8rpx;
	}

	/* ==================== 职位列表 ==================== */
	.referral__body {
		padding: 0 $zn-page-padding;
	}

	.referral__tip {
		display: block;
		font-size: $zn-font-xs;
		color: $zn-orange;
		background-color: #fff4e6;
		border-radius: $zn-radius-sm;
		padding: 10rpx 16rpx;
		margin-bottom: $zn-gap;
	}

	.referral__item {
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
		padding: 10rpx 0 20rpx;
	}

	.more__text {
		font-size: 24rpx;
		color: $zn-text-light;

		&--tap {
			color: $zn-theme;
		}
	}

	/* ==================== 规则 / FAQ 卡片 ==================== */
	.card {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: $zn-gap $zn-page-padding;
		margin: $zn-gap $zn-page-padding 0;
		box-shadow: $zn-shadow-sm;
	}

	.card__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-bottom: 18rpx;
	}

	.card__bar {
		width: 8rpx;
		height: 30rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		margin-right: 14rpx;
	}

	.card__title {
		font-size: $zn-font-md;
		font-weight: 700;
		color: $zn-text-title;
	}

	.rule {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		margin-bottom: 16rpx;
	}

	.rule__no {
		width: 36rpx;
		height: 36rpx;
		border-radius: 50%;
		background-color: $zn-theme-light;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		margin: 4rpx 14rpx 0 0;
	}

	.rule__no-text {
		font-size: $zn-font-xs;
		color: $zn-theme-dark;
		font-weight: 600;
	}

	.rule__text {
		flex: 1;
		min-width: 0;
		font-size: $zn-font-sm;
		color: $zn-text-main;
		line-height: 42rpx;
	}

	.faq {
		border-bottom: 1rpx solid $zn-line;

		&:last-child {
			border-bottom: none;
		}
	}

	.faq__q {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		padding: 20rpx 0;
	}

	.faq__q-text {
		flex: 1;
		min-width: 0;
		font-size: $zn-font;
		color: $zn-text-main;
		font-weight: 500;
		margin-right: 16rpx;
	}

	.faq__arrow {
		width: 40rpx;
		height: 40rpx;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: transform 0.2s;

		&.is-open {
			transform: rotate(180deg);
		}
	}

	.faq__a {
		display: block;
		font-size: $zn-font-sm;
		color: $zn-text-sub;
		line-height: 44rpx;
		padding-bottom: 22rpx;
	}
</style>
