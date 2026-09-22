<template>
	<view class="zn-avatar" :style="boxStyle" @tap="$emit('click')">
		<image v-if="src" class="zn-avatar__img" :src="src" mode="aspectFill"></image>
		<view v-else class="zn-avatar__ph" :style="{ background: gradient }">
			<text class="zn-avatar__char" :style="{ fontSize: fontSize }">{{ char }}</text>
		</view>
		<!-- 主色描边环（重点标识 / 企业认证等） -->
		<view v-if="ring" class="zn-avatar__ring"></view>
		<view v-if="badge" class="zn-avatar__badge" :style="{ background: badgeColor }">{{ badge }}</view>
	</view>
</template>

<script>
	/**
	 * 头像占位组件（用户头像 / 企业头像）
	 * 未传 src 时用渐变圆 + 首字渲染，无需图片资源
	 */
	import { gradientOf, firstChar } from '@/common/utils/format.js'

	export default {
		name: 'zn-avatar',
		props: {
			src: { type: String, default: '' },
			name: { type: String, default: '' },
			size: { type: [String, Number], default: 72 },
			ring: { type: Boolean, default: false }, // 主色描边环
			badge: { type: String, default: '' },
			badgeColor: { type: String, default: '#4cd964' },
			offset: { type: Number, default: 0 },
			border: { type: Boolean, default: false } // 白色描边（头像叠加时用）
		},
		computed: {
			gradient() {
				return gradientOf(this.name || '师', this.offset)
			},
			char() {
				return firstChar(this.name)
			},
			fontSize() {
				const s = typeof this.size === 'number' ? this.size : parseFloat(this.size)
				return Math.round(s * 0.42) + 'rpx'
			},
			boxStyle() {
				const unit = typeof this.size === 'number' ? this.size + 'rpx' : this.size
				const style = {
					width: unit,
					height: unit
				}
				if (this.border) {
					style.border = '3rpx solid #ffffff'
				}
				return style
			}
		}
	}
</script>

<style lang="scss" scoped>
	.zn-avatar {
		position: relative;
		border-radius: 50%;
		overflow: visible;
		flex-shrink: 0;
	}

	.zn-avatar__img,
	.zn-avatar__ph {
		width: 100%;
		height: 100%;
		border-radius: 50%;
		overflow: hidden;
	}

	.zn-avatar__ph {
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.zn-avatar__char {
		color: #ffffff;
		font-weight: 600;
		line-height: 1;
	}

	.zn-avatar__ring {
		position: absolute;
		left: -4rpx;
		top: -4rpx;
		right: -4rpx;
		bottom: -4rpx;
		border-radius: 50%;
		border: 3rpx solid rgba(76, 217, 100, 0.5);
	}

	.zn-avatar__badge {
		position: absolute;
		right: -6rpx;
		bottom: -6rpx;
		min-width: 28rpx;
		height: 28rpx;
		padding: 0 6rpx;
		border-radius: 999rpx;
		color: #ffffff;
		font-size: 18rpx;
		line-height: 28rpx;
		text-align: center;
		border: 2rpx solid #ffffff;
	}
</style>
