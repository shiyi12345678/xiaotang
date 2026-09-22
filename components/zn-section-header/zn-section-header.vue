<template>
	<view class="zn-section" :class="{ 'is-plain': plain }">
		<view class="zn-section__left">
			<view v-if="bar" class="zn-section__bar"></view>
			<uni-icons v-if="icon" :type="icon" :size="18" :color="iconColor"></uni-icons>
			<text class="zn-section__title">{{ title }}</text>
			<text v-if="subtitle" class="zn-section__subtitle">{{ subtitle }}</text>
		</view>
		<view class="zn-section__right" hover-class="zn-hover" @tap="$emit('more')">
			<slot name="right">
				<text v-if="more" class="zn-section__more">{{ more }}</text>
				<uni-icons v-if="more" type="right" :size="14" color="#bbbbbb"></uni-icons>
			</slot>
		</view>
	</view>
</template>

<script>
	/**
	 * 模块标题组件（首页/列表页各分段通用）
	 */
	export default {
		name: 'zn-section-header',
		props: {
			title: { type: String, default: '' },
			subtitle: { type: String, default: '' },
			more: { type: String, default: '' },
			icon: { type: String, default: '' },
			iconColor: { type: String, default: '#4cd964' },
			bar: { type: Boolean, default: true },
			plain: { type: Boolean, default: false }
		}
	}
</script>

<style lang="scss" scoped>
	.zn-section {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		padding: $zn-gap 0 $zn-gap-sm;
	}

	.zn-section__left {
		display: flex;
		flex-direction: row;
		align-items: center;
		flex: 1;
		min-width: 0;
	}

	.zn-section__bar {
		width: 8rpx;
		height: 32rpx;
		border-radius: 999rpx;
		background: $zn-gradient;
		margin-right: 14rpx;
	}

	.zn-section__title {
		font-size: $zn-font-lg;
		font-weight: 700;
		color: $zn-text-title;
		margin-left: 8rpx;
	}

	.zn-section__subtitle {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
		margin-left: 14rpx;
		flex-shrink: 1;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	.zn-section__right {
		display: flex;
		flex-direction: row;
		align-items: center;
		flex-shrink: 0;
	}

	.zn-section__more {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
		margin-right: 4rpx;
	}
</style>
