<template>
	<view class="zn-empty">
		<view class="zn-empty__icon">
			<uni-icons :type="icon" :size="56" color="#d6dae0"></uni-icons>
		</view>
		<text class="zn-empty__text">{{ text }}</text>
		<text v-if="desc" class="zn-empty__desc">{{ desc }}</text>
		<view v-if="btnText" class="zn-empty__btn" hover-class="zn-hover" @tap="$emit('action')">
			<text class="zn-empty__btn-text">{{ btnText }}</text>
		</view>
	</view>
</template>

<script>
	/**
	 * 空状态 / 占位组件
	 */
	export default {
		name: 'zn-empty',
		props: {
			icon: { type: String, default: 'info' },
			text: { type: String, default: '暂无内容' },
			desc: { type: String, default: '' },
			btnText: { type: String, default: '' }
		}
	}
</script>

<style lang="scss" scoped>
	.zn-empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		padding: 100rpx 40rpx;
	}

	.zn-empty__icon {
		width: 140rpx;
		height: 140rpx;
		border-radius: 50%;
		background-color: #f7f9fb;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.zn-empty__text {
		font-size: 28rpx;
		color: $zn-text-sub;
		margin-top: $zn-gap;
	}

	.zn-empty__desc {
		font-size: 24rpx;
		color: $zn-text-light;
		margin-top: 10rpx;
		text-align: center;
	}

	.zn-empty__btn {
		margin-top: $zn-gap-lg;
		padding: 0 48rpx;
		height: 68rpx;
		border-radius: 999rpx;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;
	}

	.zn-empty__btn-text {
		color: #ffffff;
		font-size: 28rpx;
		font-weight: 600;
	}
</style>
