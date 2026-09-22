<template>
	<view class="session">
		<!-- ==================== 顶部导航 ==================== -->
		<zn-nav-bar title="会话详情" show-back border right-text="继续对话" @rightClick="onRightContinue" />

		<view class="session__body">
			<!-- ---------- 会话信息（标题 + 时间） ---------- -->
			<view class="head">
				<view class="head__row">
					<text class="head__title">{{ title }}</text>
					<view v-if="pinned" class="head__pin">
						<uni-icons type="star-filled" :size="12" color="#ff8f1f"></uni-icons>
						<text class="head__pin-text">置顶</text>
					</view>
				</view>
				<text class="head__meta">{{ metaText }}</text>
			</view>

			<!-- ---------- 完整对话内容 ---------- -->
			<view v-for="(msg, index) in messages" :key="msg.id" class="msg" :class="'msg--' + msg.role">
				<!-- 用户消息：右侧绿色渐变气泡 -->
				<template v-if="msg.role === 'user'">
					<view class="bubble bubble--user">
						<text class="bubble__text">{{ msg.content }}</text>
					</view>
					<zn-avatar :name="user.nickname" :size="64" />
				</template>

				<!-- AI 消息：左侧头像 + 白色气泡（同一套 Markdown 渲染） -->
				<template v-else>
					<view class="msg__avatar">
						<uni-icons type="paperplane" :size="18" color="#ffffff"></uni-icons>
					</view>
					<view class="msg__col">
						<view v-if="msg.thinking" class="think">
							<uni-icons type="tune" :size="12" color="#999999"></uni-icons>
							<text class="think__text">{{ msg.thinking }}</text>
						</view>
						<view class="bubble bubble--ai">
							<view v-for="(block, bi) in msg.blocks" :key="bi" class="md"
								:class="'md--' + block.type">
								<text v-if="block.type === 'li'" class="md__dot">•</text>
								<text v-else-if="block.type === 'ol'" class="md__dot">{{ block.index }}.</text>
								<text class="md__text">
									<text v-for="(seg, si) in block.segments" :key="si" class="md__seg"
										:class="{ 'is-bold': seg.bold }">{{ seg.text }}</text>
								</text>
							</view>
						</view>
						<text v-if="msg.time" class="msg__time">{{ msg.time }}</text>
					</view>
				</template>
			</view>

			<!-- 历史记录结束提示 -->
			<view class="end">
				<view class="end__line"></view>
				<text class="end__text">以上为该会话的全部历史记录</text>
				<view class="end__line"></view>
			</view>
		</view>

		<!-- ==================== 底部：只读提示 + 继续对话 ==================== -->
		<view class="bar" :style="{ paddingBottom: (safeBottom + 20) + 'px' }">
			<view class="bar__tip">
				<uni-icons type="locked" :size="12" color="#999999"></uni-icons>
				<text class="bar__tip-text">该会话为历史记录，仅可查看</text>
			</view>
			<view class="bar__btn" hover-class="zn-hover" @tap="onContinue">
				<text class="bar__btn-text">继续对话</text>
			</view>
		</view>
		<!-- 底部固定条占位，避免最后一条消息被遮挡 -->
		<view :style="placeholderStyle"></view>
	</view>
</template>

<script>
	/**
	 * 历史会话详情
	 * 展示某个历史对话的完整消息（样式与 AI 求职助手主页面保持一致），
	 * 支持同一套轻量 Markdown 渲染（本页保留一份简化实现，不提取公共文件）
	 * 底部为只读提示 + 「继续对话」入口（返回 AI 求职助手主页面）
	 *
	 * 数据来源：消息列表 GET /ai/sessions/{id}/messages（services/chat.js）；
	 *          头像昵称取自本地登录缓存（不再引用 common/mock 的演示用户）。
	 */
	import { getSafeAreaBottom, toast, storage } from '@/common/utils/format.js'
	import { listMessages } from '@/services/chat.js'
	import { getCachedUser } from '@/services/user.js'

	export default {
		data() {
			return {
				safeBottom: 0,
				// 登录后由 services/user.js 写入本机缓存的用户信息；未登录时为空对象
				user: getCachedUser() || {},
				// 历史消息：进入页面后从服务端加载（见 loadMessages）
				messages: [],
				sessionId: '',
				title: 'AI 求职助手对话',
				metaText: '',
				pinned: false,
				jumpTimer: null
			}
		},
		computed: {
			/** 底部固定条 + 安全区的占位高度 */
			placeholderStyle() {
				return { height: 'calc(200rpx + ' + this.safeBottom + 'px)' }
			}
		},
		onLoad(options) {
			this.safeBottom = getSafeAreaBottom()
			this.sessionId = (options && options.id) || ''
			this.resolveSession(options || {})
			this.loadMessages()
		},
		onUnload() {
			// 清理延时跳转定时器
			if (this.jumpTimer) {
				clearTimeout(this.jumpTimer)
				this.jumpTimer = null
			}
		},
		methods: {
			/* =========================================================
			 * 一、简化版 Markdown 渲染（与主页面同一套结构，本页不提取公共文件）
			 * 返回 [{ type: 'h3'|'h2'|'p'|'li'|'ol'|'quote', text, index?, segments: [{ text, bold }] }]
			 * =======================================================*/
			/** 从服务端加载本会话的全部消息 */
			async loadMessages() {
				if (!this.sessionId) return
				try {
					const res = await listMessages(this.sessionId)
					if (res.title) this.title = res.title
					this.messages = (res.list || []).map(m => ({
						id: m.id,
						role: m.role,
						content: m.content,
						time: this.timeText(m.createdAt),
						thinking: '',
						// 助手消息解析 Markdown，用户消息按纯文本渲染
						blocks: m.role === 'assistant' ? this.parseMarkdown(m.content) : []
					}))
					this.metaText = '共 ' + this.messages.length + ' 条消息'
				} catch (e) {
					// 失败提示已由请求层统一弹出
				}
			},

			/** 把 "yyyy-MM-dd HH:mm:ss" 截成 "HH:mm" 展示 */
			timeText(str) {
				if (!str) return ''
				const parts = String(str).split(' ')
				return parts.length > 1 ? parts[1].slice(0, 5) : String(str)
			},

			parseMarkdown(content) {
				const blocks = []
				String(content || '')
					.split('\n')
					.forEach(raw => {
						const text = raw.trim()
						if (!text) return
						let type = 'p'
						let body = text
						let index = 0
						const rules = [
							{ re: /^#{2,3}\s+/, type: 'h3' }, // ### 标题（## 也按三级标题渲染）
							{ re: /^>\s?/, type: 'quote' }, // > 引用
							{ re: /^[-*]\s+/, type: 'li' }, // - 无序列表
							{ re: /^\d+[.、]\s*/, type: 'ol' } // 1. 有序列表
						]
						if (/^#{1}\s+/.test(text)) {
							type = 'h2'
							body = text.replace(/^#\s+/, '')
						} else {
							for (const rule of rules) {
								if (rule.re.test(text)) {
									type = rule.type
									body = text.replace(rule.re, '')
									if (type === 'ol') index = Number(text.match(/^(\d+)/)[1]) || 1
									break
								}
							}
						}
						blocks.push({ type, text: body, index, segments: this.splitBold(body) })
					})
				return blocks
			},

			/** 把 **加粗** 拆成参考片段 */
			splitBold(text) {
				const segments = []
				const re = /\*\*(.+?)\*\*/g
				let last = 0
				let m
				while ((m = re.exec(text))) {
					if (m.index > last) segments.push({ text: text.slice(last, m.index), bold: false })
					segments.push({ text: m[1], bold: true })
					last = m.index + m[0].length
				}
				if (last < text.length) segments.push({ text: text.slice(last), bold: false })
				return segments.length ? segments : [{ text, bold: false }]
			},

			/* =========================================================
			 * 二、会话信息
			 * =======================================================*/
			/** 解析路由参数得到标题（消息条数以服务端加载结果为准） */
			resolveSession(options) {
				let title = ''
				if (options.title) {
					// 平台对 query 的解码行为不一致，带 % 时才手动解码
					try {
						title = options.title.indexOf('%') > -1 ? decodeURIComponent(options.title) : options.title
					} catch (e) {
						title = options.title
					}
				}
				this.title = title || 'AI 求职助手对话'
				this.metaText = '共 ' + this.messages.length + ' 条消息'
			},

			/* =========================================================
			 * 三、交互
			 * =======================================================*/

			/** 顶部「继续对话」：提示后跳回主页面 */
			onRightContinue() {
				toast('即将返回 AI 求职助手继续提问')
				if (this.jumpTimer) clearTimeout(this.jumpTimer)
				this.jumpTimer = setTimeout(() => {
					this.onContinue()
				}, 500)
			},

			/** 底部「继续对话」按钮：把会话ID交回 AI 页并返回 */
			onContinue() {
				// ⚠️ 用 storage 传递会话ID —— navigateBack 不支持携带参数
				storage.set('zn_ai_session', this.sessionId)
				const pages = getCurrentPages()
				if (pages.length > 1) {
					// 由 AI 页跳转而来：直接返回上一页。
					// 原先用 navigateTo 会不断压入新的 AI 页实例，导致页面栈无限增长
					uni.navigateBack({ delta: 1 })
				} else {
					uni.reLaunch({ url: '/pages/ai/ai' })
				}
			}
		}
	}
</script>

<style lang="scss" scoped>
	.session {
		min-height: 100vh;
		background-color: $zn-bg-page;
	}

	.session__body {
		padding: 24rpx $zn-page-padding 0;
	}

	/* ==================== 会话信息 ==================== */
	.head {
		background-color: #ffffff;
		border-radius: $zn-radius-lg;
		padding: 26rpx 24rpx;
		box-shadow: $zn-shadow-sm;
	}

	.head__row {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.head__title {
		font-size: 32rpx;
		font-weight: 700;
		color: $zn-text-title;
		line-height: 44rpx;
		flex: 1;
		min-width: 0;
	}

	.head__pin {
		display: flex;
		flex-direction: row;
		align-items: center;
		height: 40rpx;
		padding: 0 14rpx;
		margin-left: 16rpx;
		border-radius: $zn-radius-pill;
		background-color: #fff4e8;
		flex-shrink: 0;
	}

	.head__pin-text {
		font-size: 20rpx;
		color: $zn-orange;
		margin-left: 6rpx;
	}

	.head__meta {
		display: block;
		font-size: 22rpx;
		color: $zn-text-grey;
		margin-top: 12rpx;
	}

	/* ==================== 消息（与主页面样式保持一致） ==================== */
	.msg {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		margin-top: 36rpx;
	}

	.msg--user {
		justify-content: flex-end;
	}

	.msg--assistant {
		justify-content: flex-start;
	}

	.msg__avatar {
		width: 64rpx;
		height: 64rpx;
		border-radius: 50%;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.msg__col {
		flex: 1;
		min-width: 0;
		margin-left: 16rpx;
		display: flex;
		flex-direction: column;
		align-items: flex-start;
	}

	.msg__time {
		font-size: 20rpx;
		color: $zn-text-light;
		margin-top: 12rpx;
	}

	/* ---------- 气泡 ---------- */
	.bubble {
		max-width: 78%;
		border-radius: $zn-radius-lg;
		padding: 22rpx 26rpx;
	}

	.bubble--user {
		background: $zn-gradient;
		border-top-right-radius: 8rpx;
		box-shadow: $zn-shadow-theme;
	}

	.bubble--ai {
		max-width: 100%;
		background-color: #ffffff;
		border-top-left-radius: 8rpx;
		box-shadow: $zn-shadow-sm;
	}

	.bubble__text {
		font-size: 29rpx;
		color: #ffffff;
		line-height: 44rpx;
		word-break: break-all;
	}

	/* ---------- 深度思考小字 ---------- */
	.think {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-bottom: 10rpx;
	}

	.think__text {
		font-size: 22rpx;
		color: $zn-text-grey;
		margin-left: 8rpx;
	}

	/* ---------- 轻量 Markdown 块 ---------- */
	.md {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
	}

	.md + .md {
		margin-top: 10rpx;
	}

	.md__text {
		font-size: 29rpx;
		color: $zn-text-main;
		line-height: 46rpx;
		word-break: break-all;
	}

	.md__seg {
		font-size: 29rpx;
		color: $zn-text-main;
		line-height: 46rpx;

		&.is-bold {
			font-weight: 700;
			color: $zn-text-title;
		}
	}

	.md--h2 .md__text,
	.md--h2 .md__seg,
	.md--h3 .md__text,
	.md--h3 .md__seg {
		font-size: 31rpx;
		font-weight: 700;
		color: $zn-text-title;
		line-height: 48rpx;
	}

	.md--h2,
	.md--h3 {
		margin-top: 18rpx;
	}

	.md--li,
	.md--ol {
		margin-top: 6rpx;
	}

	.md__dot {
		width: 32rpx;
		font-size: 29rpx;
		line-height: 46rpx;
		color: $zn-theme-deep;
		font-weight: 700;
		flex-shrink: 0;
	}

	.md--li .md__text,
	.md--ol .md__text {
		flex: 1;
		min-width: 0;
	}

	.md--quote {
		background-color: $zn-bg-grey;
		border-left: 6rpx solid $zn-theme;
		border-radius: $zn-radius-sm;
		padding: 16rpx 20rpx;
		margin-top: 14rpx;
	}

	.md--quote .md__text,
	.md--quote .md__seg {
		font-size: 26rpx;
		color: $zn-text-sub;
		line-height: 42rpx;
	}

	/* ==================== 历史结束提示 ==================== */
	.end {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin: 40rpx 0 20rpx;
	}

	.end__line {
		flex: 1;
		height: 1rpx;
		background-color: $zn-line;
	}

	.end__text {
		font-size: 21rpx;
		color: $zn-text-light;
		padding: 0 18rpx;
	}

	/* ==================== 底部只读条 ==================== */
	.bar {
		position: fixed;
		left: 0;
		right: 0;
		bottom: 0;
		z-index: 900;
		background-color: #ffffff;
		border-top: 1rpx solid $zn-line;
		padding: 20rpx $zn-page-padding 20rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		box-shadow: 0 -6rpx 24rpx rgba(20, 40, 30, 0.06);
	}

	.bar__tip {
		display: flex;
		flex-direction: row;
		align-items: center;
		flex: 1;
		min-width: 0;
	}

	.bar__tip-text {
		font-size: 22rpx;
		color: $zn-text-grey;
		margin-left: 8rpx;
	}

	.bar__btn {
		flex-shrink: 0;
		height: 76rpx;
		padding: 0 44rpx;
		margin-left: 16rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;
	}

	.bar__btn-text {
		font-size: 28rpx;
		font-weight: 600;
		color: #ffffff;
	}
</style>
