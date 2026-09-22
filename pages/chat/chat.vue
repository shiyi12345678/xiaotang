<template>
	<view class="zn-page zn-page--no-tabbar chat">
		<zn-nav-bar :title="navTitle" show-back border />

		<!-- ==================== 会话对象：职位 + 对方 ==================== -->
		<view class="head">
			<zn-company-logo :text="companyName" :size="64" />
			<view class="head__body">
				<text class="head__contact zn-ellipsis">{{ contactLabel }}</text>
				<text class="head__job zn-ellipsis">{{ jobLine }}</text>
			</view>
			<view v-if="unreadHint" class="head__hint">
				<text class="head__hint-text">{{ unreadHint }}</text>
			</view>
		</view>

		<!-- ==================== 未登录 ==================== -->
		<zn-empty v-if="!isLogin" icon="chat" text="登录后查看沟通消息"
			desc="与 HR 的聊天记录保存在账号里，登录即可继续" btn-text="去登录" @action="goLogin" />

		<template v-else>
			<!-- ==================== 消息区 ==================== -->
			<scroll-view class="chat__scroll" scroll-y :scroll-into-view="scrollIntoId" :scroll-top="scrollTop"
				:scroll-with-animation="false" :upper-threshold="40" @scrolltoupper="loadEarlier" @scroll="onScroll">
				<view class="chat__inner">
					<!-- 加载更早的消息（服务端按「最新优先」分页，page+1 就是更早的一页） -->
					<view class="chat__history">
						<text v-if="loadingMore" class="chat__history-text">正在加载更早的消息…</text>
						<text v-else-if="historyError" class="chat__history-error" @tap="loadEarlier">
							{{ historyError }}，点击重试
						</text>
						<text v-else-if="hasMore" class="chat__history-text">上滑查看更早的消息</text>
						<text v-else-if="messages.length" class="chat__history-text">没有更早的消息了</text>
					</view>

					<!-- 首次加载中 / 失败 -->
					<view v-if="loading" class="chat__state">
						<uni-icons type="spinner-cycle" :size="22" color="#00a6a7"></uni-icons>
						<text class="chat__state-text">正在加载消息…</text>
					</view>
					<view v-else-if="error" class="chat__state chat__state--error" hover-class="zn-hover"
						@tap="loadMessages">
						<uni-icons type="info-filled" :size="22" color="#ff4d4f"></uni-icons>
						<text class="chat__state-text">{{ error }}</text>
						<text class="chat__state-retry">点击重试</text>
					</view>
					<zn-empty v-else-if="!messages.length" icon="chat" text="还没有消息"
						desc="发条消息和对方聊聊岗位与面试安排吧" />

					<!-- ---------- 消息列表 ---------- -->
					<view v-for="item in renderList" :key="item.id" :id="'msg-' + item.id">
						<!-- 系统提示：居中灰字 -->
						<view v-if="item.msgType === 'system'" class="sys">
							<text class="sys__text">{{ item.content }}</text>
						</view>

						<!-- 面试邀约卡片 -->
						<view v-else-if="item.msgType === 'invite'" class="invite"
							:class="[item.mine ? 'is-mine' : 'is-other', item.showHead ? '' : 'is-run']">
							<view class="invite__card">
								<view class="invite__head">
									<uni-icons type="calendar" :size="18" color="#008c8d"></uni-icons>
									<text class="invite__title">面试邀约</text>
								</view>
								<view v-for="row in inviteRows(item)" :key="row.label" class="invite__row">
									<text class="invite__label">{{ row.label }}</text>
									<text class="invite__value">{{ row.value }}</text>
								</view>
								<text class="invite__note">{{ item.content }}</text>
							</view>
						</view>

						<!-- 简历卡片（服务端支持 msgType=resume，简历页发起沟通时会用到） -->
						<view v-else-if="item.msgType === 'resume'" class="invite"
							:class="[item.mine ? 'is-mine' : 'is-other', item.showHead ? '' : 'is-run']">
							<view class="invite__card">
								<view class="invite__head">
									<uni-icons type="compose" :size="18" color="#008c8d"></uni-icons>
									<text class="invite__title">简历</text>
								</view>
								<text class="invite__note">{{ item.content }}</text>
							</view>
						</view>

						<!-- 普通文本气泡 -->
						<view v-else class="bubble"
							:class="[item.mine ? 'is-mine' : 'is-other', item.showHead ? '' : 'is-run']">
							<view v-if="!item.mine" class="bubble__avatar">
								<zn-avatar v-if="item.showHead" :name="contactLabel" :size="72" />
							</view>
							<view class="bubble__content">
								<text class="bubble__time" v-if="item.showHead">{{ item.timeText }}</text>
								<text class="bubble__text" :class="item.mine ? 'is-mine' : 'is-other'">{{ item.content }}</text>
							</view>
							<view v-if="item.mine" class="bubble__avatar">
								<zn-avatar v-if="item.showHead" :name="myName" :size="72" />
							</view>
						</view>
					</view>

					<!-- 滚动锚点：新消息进来 / 发送成功后滚到这里 -->
					<view id="msg-bottom" class="chat__anchor"></view>
				</view>
			</scroll-view>

			<!-- ==================== 输入区 ==================== -->
			<view class="input">
				<textarea class="input__area" :value="draft" auto-height :maxlength="500"
					placeholder="输入想说的话，聊聊岗位、经验或面试时间" placeholder-class="input__ph"
					:show-confirm-bar="false" confirm-type="send" @input="onInput" @confirm="send" />
				<view class="input__btn" :class="{ 'is-disabled': !canSend }" hover-class="zn-hover" @tap="send">
					<text class="input__btn-text">{{ sending ? '发送中' : '发送' }}</text>
				</view>
			</view>
			<!-- 发送失败提示：toast 会消失，这条会一直留到下一次发送成功 -->
			<view v-if="sendError" class="input__error">
				<uni-icons type="info-filled" :size="14" color="#ff4d4f"></uni-icons>
				<text class="input__error-text">{{ sendError }}</text>
			</view>
		</template>
	</view>
</template>

<script>
	/**
	 * 与 HR 的会话（聊天页）
	 *
	 * onLoad 参数：
	 *   id    会话 id
	 *   role  candidate=求职者（默认）/ hr=企业 HR
	 *
	 * 数据来源（services/im.js，全部需登录）：
	 *   GET  /chat/conversations/{id}/messages?page=&pageSize=  消息（已按时间正序返回）
	 *   POST /chat/conversations/{id}/messages                  发送消息
	 *   POST /chat/conversations/{id}/read                      标记已读（onShow 调用）
	 *   GET  /chat/conversations?role=                          取会话对象（职位名 / 对方名字，仅用于标题）
	 *
	 * ⚠️ 左右气泡只看服务端给的 mine：
	 *    message_out 里 mine = (sender_role == 调用方角色)，服务端按 token 判定真实身份。
	 *    因此即使 URL 里的 role 参数传错，气泡方向也不会反 ——
	 *    role 只用于「取会话对象」这一个装饰性请求，页面用它时以服务端返回的 res.role 为准。
	 *
	 * ⚠️ 更早的消息（page+1）：
	 *    服务端按「最新优先」分页取，再把当页反转成正序返回，
	 *    所以 page+1 = 更早的一页，插到列表**前面**即可。
	 *    插入后如果不管滚动位置，视图会「停在原来的 scrollTop 数字上」，
	 *    表现为一下子跳到很旧的消息 —— 因此这里在插入前后各量一次内容高度，
	 *    把 scrollTop 补偿回去（量不到就退化为不补偿，不会报错）。
	 *
	 * ⚠️ 连续同一发送者的消息（可选优化，已实现）：
	 *    同一发送者连续发的消息只在第一条显示头像与时间，其余收紧上间距，
	 *    聊天记录看起来更像主流 IM；判断逻辑在 renderList 里，不改变消息本身的数据。
	 *
	 * ⚠️ 发送失败必须保留输入内容：
	 *    发送成功后服务端返回完整的消息结构（含 mine / timeText），直接 push 即可；
	 *    失败时**不清空** draft，并在输入框下方留一条常驻提示（toast 一闪就没，用户会以为白打了）。
	 */
	import { getMessages, sendMessage, markConversationRead, getConversations } from '@/services/im.js'
	import { isLogined, getCachedUser } from '@/services/user.js'
	import { safeDecode } from '@/common/utils/format.js'

	/** 每页消息条数（接口上限 50）：30 条约等于一屏半到两屏，适合聊天场景 */
	const PAGE_SIZE = 30

	export default {
		data() {
			return {
				id: '',
				role: 'candidate',
				isLogin: false,
				// ---------- 消息 ----------
				messages: [],
				page: 1,
				hasMore: false,
				loading: false,
				loadingMore: false,
				error: '',
				historyError: '',
				// ---------- 会话对象（标题装饰） ----------
				contactName: '',
				companyName: '',
				jobTitle: '',
				// ---------- 发送 ----------
				draft: '',
				sending: false,
				sendError: '',
				// ---------- 滚动控制 ----------
				scrollIntoId: '',
				scrollTop: 0,
				inited: false, // 首屏消息是否已加载过（onShow 据此决定要不要补加载）
				ready: false, // 首屏滚到底之前不允许触发「加载更早」
				readyTimer: null
			}
		},
		computed: {
			navTitle() {
				return this.contactName || '沟通'
			},
			/** 对方名字：服务端没有昵称时用身份占位，不编造姓名 */
			contactLabel() {
				if (this.contactName) return this.contactName
				return this.role === 'hr' ? '候选人' : 'HR'
			},
			jobLine() {
				if (this.companyName && this.jobTitle) return this.companyName + ' · ' + this.jobTitle
				return this.jobTitle || this.companyName || '沟通中的职位'
			},
			unreadHint() {
				const n = this.messages.filter(m => !m.mine && !m.isRead).length
				return n > 0 ? n + ' 条未读' : ''
			},
			myName() {
				const u = getCachedUser() || {}
				return u.nickname || '我'
			},
			canSend() {
				return !!this.draft.trim() && !this.sending
			},
			/**
			 * 渲染列表：给每条消息补两个展示态字段
			 *   showHead 该条是否为「同一发送者连续消息」的第一条（决定是否显示头像 / 时间）
			 * 只影响渲染，不修改服务端数据。
			 */
			renderList() {
				return this.messages.map((m, i) => {
					const prev = this.messages[i - 1]
					const showHead = !prev || prev.msgType === 'system' || m.msgType === 'system' ||
						prev.mine !== m.mine || prev.senderRole !== m.senderRole
					return Object.assign({}, m, { showHead })
				})
			}
		},
		onLoad(options) {
			const opt = options || {}
			this.id = opt.id ? safeDecode(opt.id) : ''
			// 传 hr 时表示从企业端进来（左右气泡仍由服务端的 mine 决定，这里只影响标题文案）
			this.role = opt.role === 'hr' ? 'hr' : 'candidate'
			this.isLogin = isLogined()
			if (!this.isLogin) return
			if (!this.id) {
				this.error = '缺少会话参数'
				return
			}
			this.loadMessages()
			this.loadConversationMeta()
			// 首屏消息渲染 + 滚到底需要一点时间，这段时间内不响应 scrolltoupper，
			// 否则刚进页面就会被当成「滑到顶部」而立刻再拉一页更早的消息
			if (this.readyTimer) clearTimeout(this.readyTimer)
			this.readyTimer = setTimeout(() => {
				this.ready = true
				this.readyTimer = null
			}, 500)
		},
		async onShow() {
			// 登录态可能在本页之外变化（未登录时点「去登录」再返回）：
			// 因此这里重新判断一次，并在「刚登录回来」或「首屏还没成功加载」时补一次加载。
			const logined = isLogined()
			const changed = this.isLogin !== logined
			this.isLogin = logined
			if (!logined || !this.id) return
			if (changed || !this.inited) {
				// 先等首屏消息到手，再同步已读：否则标记的是空列表，
				// 随后加载进来的消息仍是未读态，顶栏会一直显示「n 条未读」
				await this.loadMessages()
				this.loadConversationMeta()
				this.syncRead()
				return
			}
			this.syncRead()
		},
		onUnload() {
			if (this.readyTimer) {
				clearTimeout(this.readyTimer)
				this.readyTimer = null
			}
		},
		methods: {
			/* ================= 加载消息 ================= */
			/**
			 * 加载第一页消息（首屏 / 失败重试）
			 *
			 * ⚠️ 更早的消息不走这里，而是 loadEarlier()：两者对列表的处理方向相反
			 *    （这个是整体替换 + 滚到底，那个是插到前面 + 补偿滚动位置），
			 *    混在一个方法里容易改错方向。
			 */
			async loadMessages() {
				this.page = 1
				this.loading = true
				this.error = ''
				try {
					const res = await getMessages(this.id, { page: 1, pageSize: PAGE_SIZE })
					this.messages = res.list || []
					this.hasMore = !!res.hasMore
					// 以服务端判定出来的角色为准（URL 参数可能与企业端 / 求职者端不一致）
					if (res.role) this.role = res.role
				} catch (e) {
					this.error = e.message || '消息加载失败'
					this.messages = []
				} finally {
					this.loading = false
					this.inited = true
					this.scrollToBottom()
				}
			},
			/**
			 * 加载更早的消息（page+1，插到列表前面）
			 *
			 * 关键：插入前记下内容高度与当前滚动位置，插入后再量一次，
			 * 用差值把 scrollTop 补偿回去，用户的视线才会停在原来那条消息上。
			 */
			async loadEarlier() {
				if (!this.ready || !this.hasMore || this.loadingMore || this.loading) return
				this.loadingMore = true
				this.historyError = ''
				const before = await this.measureHeight()
				const top = this.viewTop || 0
				try {
					const res = await getMessages(this.id, { page: this.page + 1, pageSize: PAGE_SIZE })
					this.page += 1
					this.hasMore = !!res.hasMore
					const older = res.list || []
					// 按 id 去重：服务端分页理论上不重叠，但新消息进来会让「页」整体位移，
					// 去重可以避免个别消息重复出现（重复的 key 还会让渲染报错）
					const seen = {}
					this.messages.forEach(m => {
						seen[m.id] = true
					})
					const add = older.filter(m => !seen[m.id])
					if (add.length) {
						// 清掉「滚到底」的锚点，避免它与下面补偿用的 scrollTop 互相打架
						this.scrollIntoId = ''
						this.messages = add.concat(this.messages)
						await this.$nextTick()
						const after = await this.measureHeight()
						if (before && after) this.scrollTop = top + (after - before)
					}
				} catch (e) {
					this.historyError = e.message || '更早的消息加载失败'
				} finally {
					this.loadingMore = false
				}
			},
			/**
			 * 会话对象（职位名 / 对方名字 / 公司）：只用于标题，失败不阻塞聊天
			 */
			async loadConversationMeta() {
				try {
					const res = await getConversations({ role: this.role, page: 1, pageSize: 50 })
					const found = (res.list || []).find(c => String(c.id) === String(this.id))
					if (found) {
						this.contactName = found.contactName || ''
						this.companyName = found.companyName || ''
						this.jobTitle = found.jobTitle || ''
						return
					}
				} catch (e) {
					// 忽略：标题装饰取不到就用静态文案，不要把聊天页整个变成失败态
				}
				// 兜底：会话不在第一条时（分页里找不到）保留静态标题，不编造公司与职位
				this.contactName = this.contactName || ''
			},
			/**
			 * 标记会话已读（onShow 调用）
			 *
			 * ⚠️ 必须在首屏消息到手之后再调：
			 *    服务端只把「对方发来的、未读的」消息置为已读，本地的 isRead 不会自己变，
			 *    所以要拿成功响应把本地同侧消息也标记掉，否则顶栏会一直显示「n 条未读」。
			 * ⚠️ 该接口失败时 services/api.js 会统一 toast（页面关不掉），
			 *    这里不再额外弹提示，避免一次失败弹两次。
			 */
			async syncRead() {
				try {
					await markConversationRead(this.id)
					this.messages.forEach(m => {
						if (!m.mine) m.isRead = true
					})
				} catch (e) {
					// 已读标记失败不影响看消息：保留「未读」提示，下次进页面会再试一次
				}
			},
			/* ================= 发送 ================= */
			onInput(e) {
				this.draft = e.detail.value
				if (this.sendError) this.sendError = ''
			},
			async send() {
				const content = (this.draft || '').trim()
				if (!content) {
					uni.showToast({ title: '请输入消息内容', icon: 'none' })
					return
				}
				if (this.sending) return
				this.sending = true
				this.sendError = ''
				try {
					const res = await sendMessage(this.id, content)
					const msg = res && res.message
					// 服务端没回消息体时按失败处理：宁可让用户重试，也不能把内容清掉却什么也没发出去
					if (!msg) throw new Error('服务端未返回消息')
					this.messages.push(msg)
					this.draft = ''
					this.scrollToBottom()
				} catch (e) {
					// 关键取舍：失败时**保留** draft，并在输入框下方留一条常驻提示。
					// 请求层已经 toast 过一次，这里不再重复弹，避免一次失败弹两次。
					this.sendError = '发送失败，内容已保留：' + (e.message || '请稍后重试')
				} finally {
					this.sending = false
				}
			},
			/* ================= 滚动 ================= */
			/**
			 * 记录滚动位置
			 * ⚠️ viewTop 不是 data 字段（在 created 里挂到实例上）：
			 *    滚动事件很密集，放进 data 会引发高频重渲染，聊天页会明显卡顿。
			 */
			onScroll(e) {
				this.viewTop = e.detail.scrollTop
			},
			/** 内容高度（用于插入历史消息后的滚动补偿）；量不到返回 0 */
			measureHeight() {
				return new Promise(resolve => {
					const query = uni.createSelectorQuery().in(this)
					query.select('.chat__inner').boundingClientRect(rect => {
						resolve(rect && rect.height ? rect.height : 0)
					})
					query.exec()
				})
			},
			scrollToBottom() {
				// 先清空再赋值：scroll-into-view 的值不变时不会重新触发滚动
				this.scrollIntoId = ''
				this.$nextTick(() => {
					this.scrollIntoId = 'msg-bottom'
				})
			},
			/* ================= 渲染辅助 ================= */
			/**
			 * 面试邀约卡片的字段行
			 *
			 * ⚠️ extra 是服务端 message.extra（JSON），键名由写入方决定；
			 *    这里按常见键名读取，读不到就只显示 content（文案兜底），
			 *    绝不自己编造面试时间 / 地点。
			 */
			inviteRows(msg) {
				const extra = msg.extra || {}
				const rows = []
				const job = extra.jobTitle || extra.position
				const time = extra.time || extra.interviewTime || extra.timeText
				const place = extra.address || extra.place || extra.location
				const contact = extra.contact || extra.contactName || extra.hrName
				const way = extra.interviewType || extra.mode || extra.way
				if (job) rows.push({ label: '职位', value: job })
				if (time) rows.push({ label: '时间', value: time })
				if (place) rows.push({ label: '地点', value: place })
				if (way) rows.push({ label: '形式', value: way })
				if (contact) rows.push({ label: '联系人', value: contact })
				return rows
			},
			/* ================= 跳转 ================= */
			goLogin() {
				uni.navigateTo({
					url: '/pages/login/login',
					fail: () => uni.showToast({ title: '登录页打开失败，请稍后重试', icon: 'none' })
				})
			}
		},
		created() {
			// 非响应式的滚动位置（见 onScroll 说明）
			this.viewTop = 0
		}
	}
</script>

<style lang="scss" scoped>
	/* 聊天页用「高度 100vh 的纵向 flex」而不是整页滚动：
	   导航栏占位 → 会话头 → 消息滚动区（flex:1）→ 输入区固定在最下面。 */
	.chat {
		height: 100vh;
		display: flex;
		flex-direction: column;
		/* zn-page 的 tabBar 留白在这里会顶起输入区，聊天页不需要 */
		padding-bottom: 0;
	}

	/* ==================== 会话头 ==================== */
	.head {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: $zn-bg-card;
		padding: 18rpx $zn-page-padding;
		border-bottom: 1rpx solid $zn-line;
		flex-shrink: 0;
	}

	.head__body {
		flex: 1;
		min-width: 0;
		margin-left: 16rpx;
	}

	.head__contact {
		display: block;
		font-size: 27rpx;
		font-weight: 600;
		color: $zn-text-title;
	}

	.head__job {
		display: block;
		font-size: 21rpx;
		color: $zn-text-grey;
		margin-top: 6rpx;
	}

	.head__hint {
		flex-shrink: 0;
		background-color: $zn-theme-light;
		border-radius: $zn-radius-pill;
		padding: 6rpx 16rpx;
	}

	.head__hint-text {
		font-size: 20rpx;
		color: $zn-theme-dark;
	}

	/* ==================== 消息滚动区 ==================== */
	.chat__scroll {
		flex: 1;
		min-height: 0;
		background-color: $zn-bg-page;
	}

	.chat__inner {
		padding: 20rpx $zn-page-padding 20rpx;
	}

	.chat__history {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 10rpx 0 20rpx;
	}

	.chat__history-text {
		font-size: 20rpx;
		color: $zn-text-light;
	}

	.chat__history-error {
		font-size: 20rpx;
		color: $zn-red;
	}

	.chat__state {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 40rpx 24rpx;
		margin-bottom: 20rpx;
	}

	.chat__state--error {
		border: 2rpx solid #ffe0e0;
	}

	.chat__state-text {
		font-size: 23rpx;
		color: $zn-text-sub;
		margin-left: 12rpx;
	}

	.chat__state-retry {
		font-size: 23rpx;
		color: $zn-theme-deep;
		margin-left: 16rpx;
	}

	.chat__anchor {
		height: 2rpx;
	}

	/* ==================== 系统消息 ==================== */
	.sys {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 12rpx 0;
	}

	.sys__text {
		font-size: 21rpx;
		color: $zn-text-grey;
		background-color: rgba(0, 0, 0, 0.05);
		border-radius: $zn-radius-pill;
		padding: 6rpx 20rpx;
		text-align: center;
	}

	/* ==================== 气泡 ==================== */
	.bubble {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		margin-top: 24rpx;

		/* 连续同一发送者的后续消息：收紧间距 */
		&.is-run {
			margin-top: 10rpx;
		}

		&.is-mine {
			flex-direction: row;
			justify-content: flex-end;
		}

		&.is-other {
			flex-direction: row;
			justify-content: flex-start;
		}
	}

	.bubble__avatar {
		width: 72rpx;
		flex-shrink: 0;
	}

	.bubble__content {
		max-width: 460rpx;
		display: flex;
		flex-direction: column;
	}

	.bubble__time {
		font-size: 19rpx;
		color: $zn-text-light;
		margin-bottom: 8rpx;
	}

	.bubble__text {
		font-size: 28rpx;
		line-height: 44rpx;
		border-radius: $zn-radius-lg;
		padding: 18rpx 22rpx;
		word-break: break-all;

		&.is-other {
			background-color: $zn-bg-card;
			color: $zn-text-main;
			border-top-left-radius: 8rpx;
		}

		&.is-mine {
			background: $zn-gradient;
			color: #ffffff;
			border-top-right-radius: 8rpx;
		}
	}

	/* ==================== 邀约 / 简历卡片 ==================== */
	.invite {
		display: flex;
		flex-direction: row;
		margin-top: 24rpx;

		&.is-run {
			margin-top: 10rpx;
		}

		&.is-mine {
			justify-content: flex-end;
		}

		&.is-other {
			justify-content: flex-start;
		}
	}

	.invite__card {
		max-width: 540rpx;
		background-color: $zn-bg-card;
		border: 2rpx solid $zn-theme-light;
		border-radius: $zn-radius-lg;
		padding: 22rpx;
		box-shadow: $zn-shadow-sm;
	}

	.invite__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding-bottom: 14rpx;
		border-bottom: 1rpx solid $zn-line;
	}

	.invite__title {
		font-size: 27rpx;
		font-weight: 700;
		color: $zn-theme-dark;
		margin-left: 8rpx;
	}

	.invite__row {
		display: flex;
		flex-direction: row;
		margin-top: 14rpx;
	}

	.invite__label {
		width: 96rpx;
		font-size: 22rpx;
		color: $zn-text-grey;
		flex-shrink: 0;
	}

	.invite__value {
		flex: 1;
		min-width: 0;
		font-size: 24rpx;
		color: $zn-text-main;
		line-height: 36rpx;
	}

	.invite__note {
		display: block;
		font-size: 23rpx;
		color: $zn-text-sub;
		line-height: 38rpx;
		margin-top: 16rpx;
		white-space: pre-wrap;
	}

	/* ==================== 输入区 ==================== */
	.input {
		display: flex;
		flex-direction: row;
		align-items: flex-end;
		background-color: $zn-bg-card;
		border-top: 1rpx solid $zn-line;
		padding: 18rpx $zn-page-padding;
		flex-shrink: 0;
	}

	.input__area {
		flex: 1;
		min-width: 0;
		min-height: 72rpx;
		max-height: 200rpx;
		background-color: $zn-bg-grey;
		border-radius: $zn-radius;
		padding: 18rpx 20rpx;
		font-size: 28rpx;
		color: $zn-text-main;
		line-height: 40rpx;
	}

	.input__ph {
		font-size: 26rpx;
		color: $zn-text-light;
	}

	.input__btn {
		flex-shrink: 0;
		height: 72rpx;
		padding: 0 32rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-left: 16rpx;
		box-shadow: $zn-shadow-theme;

		&.is-disabled {
			background: #dfe3e8;
			box-shadow: none;
		}
	}

	.input__btn-text {
		font-size: 27rpx;
		font-weight: 600;
		color: #ffffff;
	}

	.input__error {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: #fff0f0;
		padding: 12rpx $zn-page-padding calc(12rpx + env(safe-area-inset-bottom));
		flex-shrink: 0;
	}

	.input__error-text {
		font-size: 21rpx;
		color: $zn-red;
		margin-left: 8rpx;
		flex: 1;
		min-width: 0;
	}
</style>
