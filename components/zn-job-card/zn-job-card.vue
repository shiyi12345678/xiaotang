<template>
	<view class="zn-job-card" :class="{ 'is-compact': compact }" hover-class="zn-hover" @tap="onTap">
		<!-- ============ 第一行：职位名 + 薪资 ============ -->
		<view class="zn-job-card__head">
			<view class="zn-job-card__title-row">
				<text v-if="kindText" class="zn-job-card__kind" :class="'is-' + job.kind">{{ kindText }}</text>
				<text class="zn-job-card__title zn-ellipsis">{{ job.title }}</text>
			</view>
			<text class="zn-job-card__salary">{{ job.salaryText }}</text>
		</view>

		<!-- ============ 第二行：经验 / 学历 / 地点 ============ -->
		<view class="zn-job-card__meta">
			<text class="zn-job-card__meta-item">{{ job.experience }}</text>
			<text class="zn-job-card__dot">·</text>
			<text class="zn-job-card__meta-item">{{ job.education }}</text>
			<text v-if="job.location" class="zn-job-card__dot">·</text>
			<text v-if="job.location" class="zn-job-card__meta-item zn-ellipsis">{{ job.location }}</text>
		</view>

		<!-- ============ 第三行：技能标签 ============ -->
		<view v-if="visibleTags.length" class="zn-job-card__tags">
			<text v-for="(tag, i) in visibleTags" :key="i" class="zn-job-card__tag">{{ tag }}</text>
		</view>

		<!-- ============ 第四行：公司 ============ -->
		<view class="zn-job-card__company">
			<zn-company-logo :text="job.logoText" :color="job.logoColor" :size="56"></zn-company-logo>
			<view class="zn-job-card__company-info">
				<text class="zn-job-card__company-name zn-ellipsis">{{ job.companyName || job.companyFullName }}</text>
				<text class="zn-job-card__company-desc zn-ellipsis">{{ companyDesc }}</text>
			</view>
			<view v-if="showFavorite" class="zn-job-card__fav" hover-class="zn-hover"
				@tap.stop="onFavorite">
				<uni-icons :type="job.isFavorite ? 'star-filled' : 'star'" :size="20"
					:color="job.isFavorite ? '#ff8f1f' : '#c8ccd4'"></uni-icons>
			</view>
		</view>

		<!-- ============ 第五行：招聘者 + 发布时间 ============ -->
		<view v-if="!compact" class="zn-job-card__foot">
			<text class="zn-job-card__hr">{{ hrText }}</text>
			<text class="zn-job-card__time">{{ job.publishText }}</text>
		</view>
	</view>
</template>

<script>
	/**
	 * 职位卡片（求职者端所有列表的统一呈现）
	 *
	 * ⚠️ 为什么做成组件而不是各页面自己写：
	 *    首页推荐、列表页、搜索结果、内推专区、我的收藏、HR 端职位管理一共 6 处
	 *    要展示同一份职位数据。若各写一遍，字段口径（比如薪资是 salaryText 还是自己拼）
	 *    一定会漂移，改一次要改六处。
	 *
	 * ⚠️ 卡片只负责「展示 + 抛事件」，不自己发请求：
	 *    收藏是页面级动作（要更新列表里这一条的 isFavorite，还可能提示登录），
	 *    组件内部发请求会让状态同步变得不可控。
	 */
	export default {
		name: 'zn-job-card',
		props: {
			/** 职位对象，字段来自服务端 job_brief（见 server/app/schemas/job.py） */
			job: { type: Object, required: true },
			/** 是否显示收藏按钮 */
			showFavorite: { type: Boolean, default: false },
			/** 紧凑模式：隐藏底部的招聘者信息（用于「相似职位」这类次要位置） */
			compact: { type: Boolean, default: false }
		},
		/**
		 * ⚠️ 为什么 emits 里除了 'tap' 还要声明 'click'：
		 *    H5 平台编译时 uni-app 会把模板里的 `@tap` 统一改写成 `onClick`
		 *    （连自定义组件标签也照改），所以父页面写 `@tap="goDetail"` 传到本组件的
		 *    prop 名字其实是 onClick；而 App / 小程序 端仍是 onTap。
		 *    若不声明 'click'，父传的 onClick 会作为普通属性 fallthrough 到根元素上，
		 *    造成「DOM click 直接调用 goDetail(事件对象)」的额外一次无效调用。
		 */
		emits: ['tap', 'click', 'favorite'],
		computed: {
			/** 职位形态角标；普通职位不显示角标 */
			kindText() {
				return {
					urgent: '急招',
					referral: '内推',
					intern: '实习',
					campus: '校招'
				}[this.job.kind] || ''
			},
			/** 公司副标题：行业 · 规模 · 融资阶段，缺哪项就跳过哪项 */
			companyDesc() {
				return [this.job.industry, this.job.scale, this.job.stage]
					.filter(Boolean)
					.join(' · ')
			},
			hrText() {
				return [this.job.hrName, this.job.hrTitle, this.job.hrActive]
					.filter(Boolean)
					.join(' · ')
			},
			/** 标签最多显示 4 个：多了会把卡片撑高，列表一屏信息量反而下降 */
			visibleTags() {
				const tags = this.job.tags || []
				return tags.slice(0, 4)
			}
		},
		methods: {
			/**
			 * 点击卡片 → 抛给父页面处理（父页面负责 navigateTo 详情页）
			 *
			 * ⚠️ 跨端坑（2026-09-21 修复「点击职位卡片毫无反应」）：
			 *    H5 端父页面 `@tap="goDetail"` 会被编译成 onClick，只 emit('tap')
			 *    父页面永远收不到 → 点击卡片没任何反应（也进不去有「投递简历」按钮的详情页）；
			 *    反过来只 emit('click')，App / 小程序 端（父页面监听的是 onTap）又会失效。
			 *    因此两个名字都发：两端各自命中一个，另一端因为「emits 已声明但无监听器」
			 *    是空操作，不会重复触发父页面的 goDetail。
			 */
			onTap() {
				this.$emit('tap', this.job) // App / 小程序：父页面 @tap
				this.$emit('click', this.job) // H5：父页面 @tap 被编译为 onClick
			},
			onFavorite() {
				this.$emit('favorite', this.job)
			}
		}
	}
</script>

<style lang="scss" scoped>
	.zn-job-card {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: $zn-gap-lg $zn-gap;
		box-shadow: $zn-shadow-sm;
	}

	/* ---------- 标题 + 薪资 ---------- */
	.zn-job-card__head {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		justify-content: space-between;
	}

	.zn-job-card__title-row {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.zn-job-card__kind {
		flex-shrink: 0;
		margin-right: 10rpx;
		padding: 0 10rpx;
		height: 34rpx;
		line-height: 34rpx;
		border-radius: $zn-radius-xs;
		font-size: $zn-font-xs;
		color: #ffffff;

		&.is-urgent {
			background-color: $zn-red;
		}

		&.is-referral {
			background-color: $zn-orange;
		}

		&.is-intern,
		&.is-campus {
			background-color: $zn-blue;
		}
	}

	.zn-job-card__title {
		flex: 1;
		min-width: 0;
		font-size: $zn-font-md;
		font-weight: 600;
		color: $zn-text-title;
	}

	.zn-job-card__salary {
		flex-shrink: 0;
		margin-left: $zn-gap-sm;
		font-size: $zn-font-sm + 2rpx;
		font-weight: 700;
		color: $zn-price;
	}

	/* ---------- 经验 / 学历 / 地点 ---------- */
	.zn-job-card__meta {
		margin-top: 14rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
		font-size: $zn-font-sm;
		color: $zn-text-sub;
	}

	.zn-job-card__meta-item {
		max-width: 320rpx;
	}

	.zn-job-card__dot {
		margin: 0 8rpx;
		color: $zn-text-light;
	}

	/* ---------- 标签 ---------- */
	.zn-job-card__tags {
		margin-top: 16rpx;
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
	}

	.zn-job-card__tag {
		margin: 0 12rpx 8rpx 0;
		padding: 4rpx 14rpx;
		border-radius: $zn-radius-xs;
		background-color: $zn-bg-grey;
		font-size: $zn-font-xs;
		color: $zn-text-sub;
	}

	/* ---------- 公司 ---------- */
	.zn-job-card__company {
		margin-top: 16rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.zn-job-card__company-info {
		flex: 1;
		min-width: 0;
		margin-left: 16rpx;
		display: flex;
		flex-direction: column;
	}

	.zn-job-card__company-name {
		font-size: $zn-font-sm;
		color: $zn-text-main;
	}

	.zn-job-card__company-desc {
		margin-top: 4rpx;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
	}

	.zn-job-card__fav {
		flex-shrink: 0;
		width: 64rpx;
		height: 64rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	/* ---------- 招聘者 + 时间 ---------- */
	.zn-job-card__foot {
		margin-top: 16rpx;
		padding-top: 16rpx;
		border-top: 1rpx solid $zn-line;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.zn-job-card__hr {
		flex: 1;
		min-width: 0;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
	}

	.zn-job-card__time {
		flex-shrink: 0;
		margin-left: $zn-gap-sm;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	/* ---------- 紧凑模式 ---------- */
	.zn-job-card.is-compact {
		padding: $zn-gap;
	}
</style>
