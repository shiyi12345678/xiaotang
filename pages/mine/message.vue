<template>
	<view class="zn-page zn-page--no-tabbar msg">
		<zn-nav-bar title="沟通" show-back border />

		<!-- ==================== 切换到企业端 ==================== -->
		<!--
			同一个账号可以同时是求职者与企业 HR，但**两端的沟通列表是互相独立的**：
			服务端 /chat/conversations 按 role 参数决定用 candidate_id 还是 hr_id 过滤，
			因此这里看到的会话与「企业端」看到的是两批数据（这是正确行为，不是丢数据）。
			入口常驻，方便演示时来回切换两种身份。
		-->
		<view class="switch" hover-class="zn-hover" @tap="goHr">
			<view class="switch__icon">
				<uni-icons type="staff-filled" :size="20" color="#008c8d"></uni-icons>
			</view>
			<view class="switch__body">
				<text class="switch__title">切换到企业端</text>
				<text class="switch__desc">以招聘方身份查看收到的简历与候选人沟通</text>
			</view>
			<uni-icons type="right" :size="16" color="#bbbbbb"></uni-icons>
		</view>

		<!-- ==================== 未登录：只给登录引导 ==================== -->
		<zn-empty v-if="!isLogin" icon="chat" text="登录后查看沟通消息"
			desc="与 HR 的沟通记录保存在账号里，登录即可继续" btn-text="去登录" @action="goLogin" />

		<template v-else>
			<!-- ==================== 加载中 ==================== -->
			<view v-if="loading" class="msg__state">
				<uni-icons type="spinner-cycle" :size="22" color="#00a6a7"></uni-icons>
				<text class="msg__state-text">正在加载会话…</text>
			</view>

			<!-- ==================== 加载失败（可重试） ==================== -->
			<view v-else-if="error" class="msg__state msg__state--error" hover-class="zn-hover" @tap="loadList(true)">
				<uni-icons type="info-filled" :size="22" color="#ff4d4f"></uni-icons>
				<text class="msg__state-text">{{ error }}</text>
				<text class="msg__state-retry">点击重试</text>
			</view>

			<!-- ==================== 空态 ==================== -->
			<zn-empty v-else-if="!list.length" icon="chat" text="还没有沟通记录"
				desc="在职位详情页点「立即沟通」，就能直接和 HR 聊起来" btn-text="去看职位"
				@action="goJobs" />

			<!-- ==================== 会话列表 ==================== -->
			<view v-else class="msg__list">
				<view v-for="item in list" :key="item.id" class="conv" hover-class="zn-hover" @tap="openChat(item)">
					<zn-company-logo :text="item.companyName" :size="88" />
					<view class="conv__body">
						<view class="conv__row">
							<text class="conv__name zn-ellipsis">{{ contactOf(item) }}</text>
							<text class="conv__time">{{ item.lastText }}</text>
						</view>
						<text class="conv__job zn-ellipsis">{{ jobLine(item) }}</text>
						<view class="conv__row">
							<text class="conv__last zn-ellipsis">{{ item.lastMessage || '已建立沟通，打个招呼吧' }}</text>
							<text v-if="item.unread > 0" class="conv__badge">{{ unreadText(item.unread) }}</text>
						</view>
					</view>
				</view>

				<view class="msg__more">
					<text v-if="loadingMore" class="msg__more-text">正在加载更多…</text>
					<text v-else-if="hasMore" class="msg__more-text">上拉加载更多</text>
					<text v-else class="msg__more-text">共 {{ total }} 个会话</text>
				</view>
			</view>
		</template>
	</view>
</template>

<script>
	/**
	 * 消息列表（求职者 ↔ 企业 HR 的沟通会话）
	 *
	 * 数据来源：GET /chat/conversations?role=candidate（services/im.js，🔒 需登录）
	 *   每条会话：contactName 对方 HR 名字 / companyName 公司 / jobTitle 职位 /
	 *             lastMessage 最后一条消息 / lastText 相对时间 / unread 未读角标
	 *
	 * ⚠️ 本页只负责「求职者视角」的列表（role 固定 candidate）：
	 *    服务端按 role 决定用 candidate_id 还是 hr_id 过滤，
	 *    因此同一个账号在求职者端与企业端看到的是**两批互相独立**的会话。
	 *    这不是数据丢失，而是刻意的身份隔离 —— 顶上那个「切换到企业端」入口
	 *    只是为了方便演示时来回切身份，两个列表本来就该不一样。
	 *
	 * ⚠️ 为什么未登录时不发请求：
	 *    getConversations 需要 token，401 会被 services/api.js 统一 toast 并清本地登录态，
	 *    页面层关不掉那个提示；未登录是明确可知的状态，先判断再决定发不发请求才是干净的。
	 *
	 * ⚠️ 不做 mock 兜底：拉不到会话就显示失败态并可点击重试，不编造聊天记录。
	 */
	import { getConversations } from '@/services/im.js'
	import { isLogined } from '@/services/user.js'

	const PAGE_SIZE = 20

	export default {
		data() {
			return {
				isLogin: false,
				list: [],
				total: 0,
				page: 1,
				hasMore: false,
				loading: false,
				loadingMore: false,
				error: '',
				inited: false
			}
		},
		onLoad() {
			this.isLogin = isLogined()
			if (this.isLogin) this.loadList(true)
		},
		onShow() {
			// 登录态可能在本页之外变化（用户点「去登录」登录后返回），因此每次显示都重新判断。
			const logined = isLogined()
			const changed = this.isLogin !== logined
			this.isLogin = logined
			if (!logined) return
			// changed=刚登录回来需要补加载；inited=从会话页返回需要刷新摘要与未读角标。
			// 首次进入两者都不成立（onLoad 正在拉），因此不会重复请求。
			if (changed || this.inited) this.loadList(true)
		},
		onPullDownRefresh() {
			if (!this.isLogin) {
				uni.stopPullDownRefresh()
				return
			}
			this.loadList(true)
		},
		onReachBottom() {
			if (this.hasMore && !this.loadingMore && !this.loading) this.loadList(false)
		},
		methods: {
			/**
			 * 拉取会话列表
			 * @param {boolean} reset true=回到第一页（首屏 / 下拉刷新 / 返回本页）
			 */
			async loadList(reset) {
				if (reset) {
					this.page = 1
					this.loading = true
				} else {
					this.loadingMore = true
				}
				this.error = ''
				try {
					const res = await getConversations({ role: 'candidate', page: this.page, pageSize: PAGE_SIZE })
					const rows = res.list || []
					this.list = reset ? rows : this.list.concat(rows)
					this.total = Number(res.total) || 0
					this.hasMore = !!res.hasMore
					if (this.hasMore) this.page += 1
				} catch (e) {
					this.error = e.message || '会话加载失败'
					if (reset) this.list = []
				} finally {
					this.loading = false
					this.loadingMore = false
					this.inited = true
					uni.stopPullDownRefresh()
				}
			},
			/** 对方名字：服务端取的是对方昵称，为空时用「HR」占位（不编造姓名） */
			contactOf(item) {
				return item.contactName || 'HR'
			},
			/** 「公司 · 职位」一行；公司名缺失时只显示职位 */
			jobLine(item) {
				if (item.companyName && item.jobTitle) return item.companyName + ' · ' + item.jobTitle
				return item.jobTitle || item.companyName || '沟通中的职位'
			},
			unreadText(n) {
				return n > 99 ? '99+' : String(n)
			},
			openChat(item) {
				uni.navigateTo({
					url: '/pages/chat/chat?id=' + encodeURIComponent(item.id) + '&role=candidate'
				})
			},
			goHr() {
				uni.navigateTo({
					url: '/pages/hr/dashboard',
					fail: () => uni.showToast({ title: '企业端工作台打开失败', icon: 'none' })
				})
			},
			goLogin() {
				uni.navigateTo({
					url: '/pages/login/login',
					fail: () => uni.showToast({ title: '登录页打开失败，请稍后重试', icon: 'none' })
				})
			},
			goJobs() {
				uni.navigateTo({
					url: '/pages/index/index',
					fail: () => uni.reLaunch({ url: '/pages/index/index' })
				})
			}
		}
	}
</script>

<style lang="scss" scoped>
	.msg {
		padding-bottom: 60rpx;
	}

	/* ==================== 切换到企业端 ==================== */
	.switch {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: $zn-theme-light;
		border-radius: $zn-radius-lg;
		padding: 22rpx 24rpx;
		margin: $zn-gap $zn-page-padding 0;
	}

	.switch__icon {
		width: 64rpx;
		height: 64rpx;
		border-radius: $zn-radius-sm;
		background-color: #ffffff;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.switch__body {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin: 0 16rpx;
	}

	.switch__title {
		font-size: 27rpx;
		font-weight: 600;
		color: $zn-theme-dark;
	}

	.switch__desc {
		font-size: 21rpx;
		color: $zn-theme-deep;
		margin-top: 6rpx;
	}

	/* ==================== 状态块 ==================== */
	.msg__state {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 60rpx 24rpx;
		margin: $zn-gap $zn-page-padding 0;
	}

	.msg__state--error {
		border: 2rpx solid #ffe0e0;
	}

	.msg__state-text {
		font-size: 24rpx;
		color: $zn-text-sub;
		margin-left: 12rpx;
	}

	.msg__state-retry {
		font-size: 24rpx;
		color: $zn-theme-deep;
		margin-left: 16rpx;
	}

	/* ==================== 会话列表 ==================== */
	.msg__list {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		margin: $zn-gap $zn-page-padding 0;
		overflow: hidden;
	}

	.conv {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 24rpx;
		border-bottom: 1rpx solid $zn-line;

		&:last-child {
			border-bottom: none;
		}
	}

	.conv__body {
		flex: 1;
		min-width: 0;
		margin-left: 20rpx;
	}

	.conv__row {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.conv__name {
		flex: 1;
		min-width: 0;
		font-size: 30rpx;
		font-weight: 600;
		color: $zn-text-title;
	}

	.conv__time {
		font-size: 20rpx;
		color: $zn-text-light;
		flex-shrink: 0;
		margin-left: 12rpx;
	}

	.conv__job {
		display: block;
		font-size: 22rpx;
		color: $zn-theme-deep;
		margin-top: 8rpx;
	}

	.conv__last {
		flex: 1;
		min-width: 0;
		font-size: 23rpx;
		color: $zn-text-grey;
		margin-top: 10rpx;
	}

	.conv__badge {
		flex-shrink: 0;
		min-width: 34rpx;
		height: 34rpx;
		padding: 0 10rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-red;
		color: #ffffff;
		font-size: 20rpx;
		line-height: 34rpx;
		text-align: center;
		margin-left: 12rpx;
	}

	/* ==================== 触底 ==================== */
	.msg__more {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 24rpx 0;
	}

	.msg__more-text {
		font-size: 21rpx;
		color: $zn-text-light;
	}
</style>
