<template>
	<view class="zn-logo" :style="boxStyle">
		<text class="zn-logo__text" :style="textStyle">{{ displayText }}</text>
	</view>
</template>

<script>
	/**
	 * 公司/企业 Logo 占位块（零图片资源方案的统一实现）
	 *
	 * ⚠️ 为什么不用图片：
	 *    本项目全程零图片资源（改造前就是如此），公司 Logo 用「主色底 + 简称首字」占位。
	 *    如果每个页面各写一遍，会出现同一家公司在列表页和详情页颜色/字号不一致的问题，
	 *    所以收敛成一个组件。
	 *
	 * ⚠️ 渐变怎么做的：
	 *    不用 8 位十六进制色值（部分低版本 webview 不认），
	 *    而是「纯色 background-color + 一层半透明白到透明的 background-image」，
	 *    这样任意 logoColor 都能得到统一的立体感，也不会因色值格式不合规而整块变透明。
	 */
	export default {
		name: 'zn-company-logo',
		props: {
			/** 占位文字（1~2 字），为空时显示 '公' */
			text: { type: String, default: '' },
			/** 主色，来自公司的 logoColor */
			color: { type: String, default: '#00A6A7' },
			/** 边长（rpx） */
			size: { type: Number, default: 88 }
		},
		computed: {
			displayText() {
				const t = String(this.text || '').trim()
				return t ? t.slice(0, 2) : '公'
			},
			boxStyle() {
				return {
					width: this.size + 'rpx',
					height: this.size + 'rpx',
					borderRadius: this.size * 0.26 + 'rpx',
					backgroundColor: this.color || '#00A6A7',
					backgroundImage:
						'linear-gradient(180deg, rgba(255,255,255,0.24) 0%, rgba(255,255,255,0) 58%, rgba(0,0,0,0.06) 100%)'
				}
			},
			textStyle() {
				// 字号随边长走：1 个字时略大，2 个字时缩小，避免撑破方块
				const base = this.displayText.length > 1 ? this.size * 0.34 : this.size * 0.42
				return { fontSize: Math.round(base) + 'rpx' }
			}
		}
	}
</script>

<style lang="scss" scoped>
	.zn-logo {
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
		overflow: hidden;
	}

	.zn-logo__text {
		color: #ffffff;
		font-weight: 600;
		line-height: 1;
		letter-spacing: 1rpx;
	}
</style>
