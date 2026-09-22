<template>
	<view class="zn-progress">
		<view class="zn-progress__track" :style="{ height: h, backgroundColor: trackColor }">
			<view class="zn-progress__fill" :style="fillStyle"></view>
		</view>
		<text v-if="showText" class="zn-progress__text">{{ percent }}%</text>
	</view>
</template>

<script>
	/**
	 * 进度条（答题进度 / 简历完整度 / 投递进度 / 求职报告指标）
	 */
	export default {
		name: 'zn-progress',
		props: {
			percent: { type: [Number, String], default: 0 },
			height: { type: [Number, String], default: 12 },
			color: { type: String, default: '' },
			trackColor: { type: String, default: '#f0f2f5' },
			showText: { type: Boolean, default: false }
		},
		computed: {
			h() {
				return typeof this.height === 'number' ? this.height + 'rpx' : this.height
			},
			fillStyle() {
				const p = Math.max(0, Math.min(100, Number(this.percent) || 0))
				const style = { width: p + '%' }
				if (this.color) {
					style.background = this.color
				} else {
					style.background = 'linear-gradient(90deg, #6ee287 0%, #4cd964 60%, #2bb14c 100%)'
				}
				return style
			}
		}
	}
</script>

<style lang="scss" scoped>
	.zn-progress {
		display: flex;
		flex-direction: row;
		align-items: center;
		width: 100%;
	}

	.zn-progress__track {
		flex: 1;
		border-radius: 999rpx;
		overflow: hidden;
	}

	.zn-progress__fill {
		height: 100%;
		border-radius: 999rpx;
		transition: width 0.3s ease;
	}

	.zn-progress__text {
		font-size: 22rpx;
		color: $zn-text-grey;
		margin-left: 12rpx;
		flex-shrink: 0;
	}
</style>
