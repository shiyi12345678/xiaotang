<template>
	<view class="zn-price" :class="'zn-price--' + size" :style="{ color: free ? '#2bb14c' : color }">
		<template v-if="free">
			<text class="zn-price__free">{{ freeText }}</text>
		</template>
		<template v-else>
			<text class="zn-price__unit">¥</text>
			<text class="zn-price__num">{{ num }}</text>
			<text v-if="dec" class="zn-price__dec">{{ dec }}</text>
		</template>
		<text v-if="showOrigin && origin" class="zn-price__origin">¥{{ origin }}</text>
	</view>
</template>

<script>
	/**
	 * 价格组件：统一价格的字号、颜色与「¥ / 整数 / 小数」混排规则
	 * 需求文档要求「价格通过更大的字体和颜色突出显示」，因此本组件字号阶梯较明显
	 */
	import { formatPrice, priceDecimal } from '@/common/utils/format.js'

	export default {
		name: 'zn-price',
		props: {
			value: { type: [Number, String], default: 0 },
			size: { type: String, default: 'md' }, // sm / md / lg / xl
			color: { type: String, default: '#ff5c1a' },
			origin: { type: [Number, String], default: 0 },
			showOrigin: { type: Boolean, default: false },
			freeText: { type: String, default: '免费' }
		},
		computed: {
			free() {
				return Number(this.value) === 0
			},
			num() {
				return formatPrice(this.value)
			},
			dec() {
				return priceDecimal(this.value)
			}
		}
	}
</script>

<style lang="scss" scoped>
	.zn-price {
		display: flex;
		flex-direction: row;
		align-items: baseline;
		font-weight: 700;
	}

	.zn-price__unit {
		font-size: 0.66em;
		margin-right: 2rpx;
	}

	.zn-price__num {
		font-size: 1em;
		line-height: 1.1;
	}

	.zn-price__dec {
		font-size: 0.62em;
	}

	.zn-price__free {
		font-size: 0.9em;
		font-weight: 600;
	}

	.zn-price__origin {
		font-size: 0.52em;
		color: $zn-text-light;
		font-weight: 400;
		text-decoration: line-through;
		margin-left: 10rpx;
	}

	.zn-price--sm {
		font-size: 26rpx;
	}

	.zn-price--md {
		font-size: 32rpx;
	}

	.zn-price--lg {
		font-size: 42rpx;
	}

	.zn-price--xl {
		font-size: 52rpx;
	}
</style>
