<template>
	<text class="zn-tag" :class="['zn-tag--' + type, 'zn-tag--' + size, plain ? 'is-plain' : '']">{{ text }}</text>
</template>

<script>
	/**
	 * 标签组件：通用状态 / 难度 / 属性标签（如 待处理 / 基础 / 已绑定）
	 * type: green / orange / red / blue / purple / gold / gray
	 */
	export default {
		name: 'zn-tag',
		props: {
			text: { type: String, default: '' },
			type: { type: String, default: 'green' },
			size: { type: String, default: 'sm' }, // xs / sm / md
			plain: { type: Boolean, default: false }
		}
	}
</script>

<style lang="scss" scoped>
	.zn-tag {
		display: inline-block;
		border-radius: 6rpx;
		line-height: 1.5;
		flex-shrink: 0;
		font-weight: 500;
	}

	.zn-tag--xs {
		font-size: 18rpx;
		padding: 1rpx 8rpx;
	}

	.zn-tag--sm {
		font-size: 20rpx;
		padding: 2rpx 10rpx;
	}

	.zn-tag--md {
		font-size: 24rpx;
		padding: 4rpx 14rpx;
	}

	.zn-tag--green {
		color: #2bb14c;
		background-color: $zn-theme-light;
	}

	.zn-tag--orange {
		color: #e07b00;
		background-color: #fff4e6;
	}

	.zn-tag--red {
		color: #e63a3c;
		background-color: #fff0f0;
	}

	.zn-tag--blue {
		color: #2b7fd4;
		background-color: #eaf4ff;
	}

	.zn-tag--purple {
		color: #6b4de0;
		background-color: #f2eeff;
	}

	.zn-tag--gold {
		color: #b07800;
		background-color: #fff8e0;
	}

	.zn-tag--gray {
		color: $zn-text-sub;
		background-color: $zn-bg-grey;
	}
</style>
