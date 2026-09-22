<script>
	/**
	 * 应用根组件
	 *
	 * ⚠️ 登录态策略：本项目「不记住登录」。
	 *    每次应用启动都清空本地登录态，保证「打开就是未登录」，必须由用户自己重新登录。
	 */
	import { clearLoginState } from '@/services/user.js'

	export default {
		globalData: {
			statusBarHeight: 0, // 状态栏高度
			safeAreaBottom: 0, // 底部安全区高度
			theme: '#00A6A7',
			userInfo: null
		},
		onLaunch() {
			// ---------- 登录态策略：不记住登录（产品需求） ----------
			// 目的：打开浏览器 / 冷启动时一律为「未登录」，强制用户自己重新登录。
			// 原因：登录态写在本地缓存（H5 下即 localStorage），会跨浏览器会话保留；
			//       叠加服务端 JWT_EXPIRE_DAYS=7，7 天内打开页面都会「直接是上次那个账号」。
			// 做法：在应用启动的最早期清空 token 与用户缓存，保证首屏一定读到「未登录」。
			// ⚠️ 副作用 1：H5 下浏览器刷新（F5）也会触发 onLaunch，刷新后同样需要重新登录；
			//             App / 小程序端仅冷启动触发，从后台切回（热启动）不会登出。
			// ⚠️ 副作用 2：未清 zn_last_login，登录页仍会回填上次登录的邮箱；
			//             若要连邮箱也不回填，需另行改动 pages/login/login.vue 的 onLoad。
			// ⚠️ 回滚方式：删除下面这一行 clearLoginState() 即可恢复「记住登录」。
			clearLoginState()

			const sys = uni.getSystemInfoSync()
			this.globalData.statusBarHeight = sys.statusBarHeight || 0
			this.globalData.safeAreaBottom = sys.screenHeight - (sys.safeArea ? sys.safeArea.bottom : sys.screenHeight)
			// 模拟：本地缓存的登录态
			// ⚠️ 上面已清空登录态，因此这里恒为空、不会命中 if 分支；
			//    保留该分支是为了「删掉 clearLoginState() 即可完整回滚」，勿顺手删除。
			const user = uni.getStorageSync('zn_user')
			if (user) {
				this.globalData.userInfo = user
			}
			console.log('[App] onLaunch', sys.platform, sys.statusBarHeight)
		},
		onShow() {
			console.log('[App] onShow')
		},
		onHide() {
			console.log('[App] onHide')
		}
	}
</script>

<style lang="scss">
	/* ============ 全局样式（uni-app 中 App.vue 的样式为全局样式） ============ */
	page {
		background-color: $zn-bg-page;
		color: $zn-text-main;
		font-size: $zn-font;
		font-family: -apple-system, BlinkMacSystemFont, 'Helvetica Neue', 'PingFang SC',
			'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
		-webkit-font-smoothing: antialiased;
	}

	view,
	text,
	image,
	scroll-view,
	swiper {
		box-sizing: border-box;
	}

	/* ---------- 通用布局工具类 ---------- */
	.zn-page {
		min-height: 100vh;
		background-color: $zn-bg-page;
		/* 给自定义 tabBar 留出空间 */
		padding-bottom: calc(#{$zn-tabbar-height} + 24rpx);
	}

	.zn-page--no-tabbar {
		padding-bottom: 40rpx;
	}

	.zn-card {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
	}

	.zn-row {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.zn-col {
		display: flex;
		flex-direction: column;
	}

	.zn-between {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.zn-center {
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.zn-flex1 {
		flex: 1;
		min-width: 0;
	}

	/* ---------- 文本工具类 ---------- */
	.zn-ellipsis {
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	.zn-ellipsis-2 {
		overflow: hidden;
		text-overflow: ellipsis;
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 2;
		word-break: break-all;
	}

	.zn-ellipsis-3 {
		overflow: hidden;
		text-overflow: ellipsis;
		display: -webkit-box;
		-webkit-box-orient: vertical;
		-webkit-line-clamp: 3;
		word-break: break-all;
	}

	.zn-bold {
		font-weight: 600;
	}

	.zn-price-text {
		color: $zn-price;
		font-weight: 700;
	}

	.zn-grey {
		color: $zn-text-grey;
	}

	/* ---------- 点击态 ---------- */
	.zn-hover {
		opacity: 0.7;
	}

	/* ---------- 分段标题通用 ---------- */
	.zn-block {
		margin: 0 $zn-page-padding $zn-gap;
	}
</style>
