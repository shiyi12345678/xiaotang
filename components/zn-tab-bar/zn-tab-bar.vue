<template>
	<view class="zn-tabbar-wrap">
		<!-- 占位，防止内容被固定 tabBar 遮挡 -->
		<view v-if="placeholder" class="zn-tabbar__placeholder" :style="{ height: wrapHeight }"></view>
		<view class="zn-tabbar" :style="{ paddingBottom: safeBottom + 'px' }">
			<view v-for="item in list" :key="item.key" class="zn-tabbar__item" hover-class="none"
				@tap="switchTo(item)">
				<!-- 中间 AI 助教做凸起强调 -->
				<view v-if="item.center" class="zn-tabbar__center"
					:class="{ 'is-active': current === item.key }">
					<uni-icons :type="current === item.key ? item.iconActive : item.icon" :size="26"
						color="#ffffff"></uni-icons>
				</view>
				<template v-else>
					<view class="zn-tabbar__icon">
						<uni-icons :type="current === item.key ? item.iconActive : item.icon" :size="23"
							:color="current === item.key ? activeColor : inactiveColor"></uni-icons>
						<text v-if="item.badge" class="zn-tabbar__badge">{{ item.badge }}</text>
					</view>
				</template>
				<text class="zn-tabbar__text" :class="{ 'is-active': current === item.key }"
					:style="{ color: current === item.key ? activeColor : inactiveColor }">{{ item.text }}</text>
			</view>
		</view>
	</view>
</template>

<script>
	/**
	 * 自定义底部 tabBar（不依赖任何图片图标资源，基于 uni-icons）
	 *
	 * current 取值：index / category / ai / study / mine
	 *   —— key 沿用了改造前的命名（页面里已按 key 传参），含义已按招聘业务重新映射：
	 *      index    首页         /pages/index/index      职位首页
	 *      category 职位         /pages/job/list         职位列表与职能筛选（原「分类」）
	 *      ai       AI助手       /pages/ai/ai            AI 求职助手（凸起强调）
	 *      study    求职         /pages/seeker/center    求职中心（原「学习」）
	 *      mine     我的         /pages/mine/mine        个人中心
	 *
	 * ⚠️ key 不改名、只改 path 与文案：页面里写的是 current="study" 这类字面量，
	 *    改 key 会让 4 个页面同时失效，而 key 本身对用户不可见。
	 *
	 * 说明：点击其它 tab 使用 uni.reLaunch（本项目不用系统原生 tabBar，
	 *      pages.json 里也没有 tabBar 配置），因此每个 tab 页都要自行渲染本组件。
	 */
	import { getSafeAreaBottom } from '@/common/utils/format.js'

	export default {
		name: 'zn-tab-bar',
		props: {
			current: { type: String, default: 'index' },
			placeholder: { type: Boolean, default: true },
			activeColor: { type: String, default: '#00A6A7' },
			inactiveColor: { type: String, default: '#9aa0a6' }
		},
		data() {
			return {
				safeBottom: 0,
				list: [
					{ key: 'index', text: '首页', icon: 'home', iconActive: 'home-filled', path: '/pages/index/index' },
					{ key: 'category', text: '职位', icon: 'list', iconActive: 'list', path: '/pages/job/list' },
					{ key: 'ai', text: 'AI助手', icon: 'chat', iconActive: 'chat-filled', path: '/pages/ai/ai', center: true },
					{ key: 'study', text: '求职', icon: 'medal', iconActive: 'medal-filled', path: '/pages/seeker/center', badge: '' },
					{ key: 'mine', text: '我的', icon: 'person', iconActive: 'person-filled', path: '/pages/mine/mine' }
				]
			}
		},
		computed: {
			wrapHeight() {
				return 'calc(108rpx + ' + this.safeBottom + 'px)'
			}
		},
		created() {
			this.safeBottom = getSafeAreaBottom()
		},
		methods: {
			switchTo(item) {
				if (item.key === this.current) return
				uni.reLaunch({ url: item.path })
			}
		}
	}
</script>

<style lang="scss" scoped>
	.zn-tabbar {
		position: fixed;
		left: 0;
		right: 0;
		bottom: 0;
		z-index: 980;
		display: flex;
		flex-direction: row;
		align-items: center;
		height: 108rpx;
		box-sizing: content-box;
		background-color: #ffffff;
		border-top: 1rpx solid $zn-line;
		box-shadow: 0 -4rpx 20rpx rgba(20, 40, 30, 0.05);
	}

	.zn-tabbar__item {
		flex: 1;
		height: 108rpx;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
		position: relative;
	}

	.zn-tabbar__icon {
		position: relative;
		height: 46rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.zn-tabbar__text {
		font-size: 20rpx;
		line-height: 28rpx;
		margin-top: 2rpx;

		&.is-active {
			font-weight: 600;
		}
	}

	.zn-tabbar__center {
		width: 84rpx;
		height: 84rpx;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
		background: linear-gradient(135deg, #4fd0d1 0%, #00a6a7 50%, #008c8d 100%);
		box-shadow: 0 8rpx 20rpx rgba(0, 166, 167, 0.4);
		transform: translateY(-24rpx);
		border: 6rpx solid #ffffff;

		&.is-active {
			transform: translateY(-28rpx);
		}
	}

	.zn-tabbar__badge {
		position: absolute;
		top: -6rpx;
		right: -18rpx;
		min-width: 28rpx;
		height: 28rpx;
		padding: 0 8rpx;
		border-radius: 999rpx;
		background-color: $zn-red;
		color: #ffffff;
		font-size: 18rpx;
		line-height: 28rpx;
		text-align: center;
	}
</style>
