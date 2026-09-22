<template>
	<view class="zn-nav">
		<!-- 占位，避免固定定位遮挡内容 -->
		<view v-if="fixed && placeholder" class="zn-nav__placeholder" :style="{ height: totalHeight + 'px' }"></view>
		<view class="zn-nav__bar" :class="['zn-nav__bar--' + type, border ? 'is-border' : '']" :style="barStyle">
			<view class="zn-nav__status" :style="{ height: statusBarHeight + 'px' }"></view>
			<view class="zn-nav__content">
				<view class="zn-nav__left">
					<view v-if="showBack" class="zn-nav__btn" hover-class="zn-hover" @tap="onBack">
						<uni-icons type="left" :size="22" :color="textColor"></uni-icons>
					</view>
					<slot name="left"></slot>
				</view>
				<view class="zn-nav__center">
					<slot>
						<text class="zn-nav__title" :style="{ color: textColor }">{{ title }}</text>
					</slot>
				</view>
				<view class="zn-nav__right">
					<slot name="right"></slot>
					<text v-if="rightText" class="zn-nav__right-text" :style="{ color: textColor }"
						@tap="$emit('rightClick')">{{ rightText }}</text>
				</view>
			</view>
		</view>
	</view>
</template>

<script>
	/**
	 * 自定义导航栏
	 * 项目所有页面统一使用 navigationStyle: custom，由本组件负责状态栏与标题栏
	 * type: green | white | transparent
	 */
	import { getStatusBarHeight } from '@/common/utils/format.js'

	export default {
		name: 'zn-nav-bar',
		props: {
			title: { type: String, default: '' },
			type: { type: String, default: 'white' }, // green / white / transparent
			showBack: { type: Boolean, default: false },
			fixed: { type: Boolean, default: true },
			placeholder: { type: Boolean, default: true },
			border: { type: Boolean, default: false },
			rightText: { type: String, default: '' },
			textColor: { type: String, default: '' }, // 文字/图标颜色，留空则按 type 自动
			bgColor: { type: String, default: '' } // 自定义背景（覆盖 type）
		},
		data() {
			return {
				statusBarHeight: 0
			}
		},
		computed: {
			totalHeight() {
				return this.statusBarHeight + 44
			},
			barStyle() {
				const style = {
					paddingTop: this.statusBarHeight + 'px'
				}
				if (this.bgColor) {
					style.background = this.bgColor
				} else if (this.type === 'green') {
					// ⚠️ 这里只能写死色值：computed 是 JS，读不到 uni.scss 里的 $zn-gradient。
					//    取值必须与 uni.scss 的 $zn-gradient 一致（135deg，#33c4c5 → #00a6a7 → #008c8d）。
					//    改造前这里写的是学习端绿渐变（#5ee27a / #4cd964 / #2bb14c）——
					//    凡是没改用别的 type 的页面都会渲染成旧配色，属于「组件里藏着旧品牌色」的典型坑。
					style.background = 'linear-gradient(135deg, #33c4c5 0%, #00a6a7 45%, #008c8d 100%)'
				} else if (this.type === 'transparent') {
					style.background = 'transparent'
				} else {
					style.background = '#ffffff'
				}
				return style
			}
		},
		created() {
			this.statusBarHeight = getStatusBarHeight()
		},
		methods: {
			onBack() {
				const pages = getCurrentPages()
				if (pages.length > 1) {
					uni.navigateBack({ delta: 1 })
				} else {
					uni.reLaunch({ url: '/pages/index/index' })
				}
			}
		}
	}
</script>

<style lang="scss" scoped>
	.zn-nav__bar {
		position: fixed;
		top: 0;
		left: 0;
		right: 0;
		z-index: 990;

		&.is-border {
			border-bottom: 1rpx solid $zn-line;
		}
	}

	.zn-nav__content {
		height: 44px;
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 0 $zn-gap-sm;
	}

	.zn-nav__left,
	.zn-nav__right {
		min-width: 120rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.zn-nav__right {
		justify-content: flex-end;
	}

	.zn-nav__center {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
	}

	.zn-nav__title {
		font-size: $zn-font-lg;
		font-weight: 600;
		max-width: 420rpx;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	.zn-nav__btn {
		width: 60rpx;
		height: 60rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.zn-nav__right-text {
		font-size: $zn-font;
		padding-left: $zn-gap-sm;
	}
</style>
