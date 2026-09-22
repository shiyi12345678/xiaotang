<template>
	<view class="ai">
		<!-- ==================== 1. 顶部导航（固定在顶端） ====================
			 本页 pages.json 里已配置 disableScroll: true，页面整体不滚动，
			 所以用「根节点 100vh + flex 纵向布局」实现顶部导航与底部输入区固定、中间对话区自己滚动，
			 效果等同于 position: fixed，同时避免 fixed 定位在键盘弹起时的错位问题。
		-->
		<view class="ai__header" :style="{ paddingTop: statusBarHeight + 'px' }">
			<view class="ai__nav">
				<!-- 左侧：弹出历史对话列表 -->
				<view class="ai__nav-btn" hover-class="zn-hover" @tap="openHistory">
					<uni-icons type="bars" :size="23" color="#ffffff"></uni-icons>
					<text v-if="historyTotal" class="ai__nav-badge">{{ historyTotal }}</text>
				</view>
				<!-- 中间：标题 + 模型选择入口 -->
				<view class="ai__nav-center" hover-class="zn-hover" @tap="onPickModel">
					<text class="ai__nav-title">AI 求职助手</text>
					<view class="ai__nav-sub">
						<text class="ai__nav-sub-text">{{ currentModel.desc }}</text>
						<uni-icons type="arrow-down" :size="11" color="rgba(255,255,255,0.92)"></uni-icons>
					</view>
				</view>
				<!-- 右侧：新建对话（清空消息，回到欢迎态） -->
				<view class="ai__nav-btn" hover-class="zn-hover" @tap="onNewChat">
					<uni-icons type="plusempty" :size="23" color="#ffffff"></uni-icons>
				</view>
			</view>
		</view>

		<!-- ==================== 2. 中间：与 LLM 的对话内容（自己滚动） ==================== -->
		<scroll-view class="ai__chat" scroll-y :scroll-into-view="scrollInto" :scroll-with-animation="true"
			:show-scrollbar="false">
			<!-- ---------- 2.1 欢迎态（无消息时） ---------- -->
			<view v-if="!messages.length" class="welcome">
				<view class="welcome__logo">
					<uni-icons type="paperplane" :size="36" color="#ffffff"></uni-icons>
				</view>
				<text class="welcome__greeting">{{ aiWelcome.greeting }}</text>
				<text class="welcome__desc">{{ aiWelcome.desc }}</text>

				<!-- 4 个快捷能力卡（2×2 宫格） -->
				<view class="caps">
					<view v-for="(item, i) in aiCapabilities" :key="item.title" class="caps__item"
						hover-class="zn-hover" @tap="onCapability(item)">
						<view class="caps__icon" :style="{ backgroundColor: capabilityBgs[i] }">
							<uni-icons :type="item.icon" :size="26" :color="item.color"></uni-icons>
						</view>
						<text class="caps__title">{{ item.title }}</text>
						<text class="caps__desc zn-ellipsis">{{ item.desc }}</text>
					</view>
				</view>

				<!-- 推荐问题（点击直接发送） -->
				<view class="sugs">
					<text class="sugs__label">你可以这样问我</text>
					<view v-for="item in aiWelcome.suggestions" :key="item.title" class="sugs__item"
						hover-class="zn-hover" @tap="sendText(item.prompt || item.title)">
						<view class="sugs__icon">
							<uni-icons :type="item.icon" :size="17" color="#00A6A7"></uni-icons>
						</view>
						<view class="sugs__info">
							<text class="sugs__title">{{ item.title }}</text>
							<text class="sugs__desc zn-ellipsis">{{ item.desc }}</text>
						</view>
						<uni-icons type="right" :size="14" color="#bbbbbb"></uni-icons>
					</view>
				</view>
			</view>

			<!-- ---------- 2.2 对话态 ---------- -->
			<view v-else class="chat">
				<view v-for="(msg, index) in messages" :key="msg.id" :id="'msg' + index" class="msg"
					:class="'msg--' + msg.role">
					<!-- 用户消息：右侧绿色渐变气泡 + 白字 -->
					<template v-if="msg.role === 'user'">
						<view class="bubble bubble--user">
							<!-- 附件图片：点击可看大图 -->
							<view v-if="msg.images.length" class="uimg">
								<image v-for="(img, ii) in msg.images" :key="ii" class="uimg__item" :src="img.url"
									mode="aspectFill" @tap="previewImage(msg, ii)"></image>
							</view>
							<text v-if="msg.content" class="bubble__text">{{ msg.content }}</text>
						</view>
						<zn-avatar :name="user.nickname" :size="64" />
					</template>

					<!-- AI 消息：左侧头像 + 白色气泡 + 操作区 + 参考来源 -->
					<template v-else>
						<view class="msg__avatar">
							<uni-icons type="paperplane" :size="18" color="#ffffff"></uni-icons>
						</view>
						<view class="msg__col">
							<!-- 深度思考：气泡上方一行浅灰小字 -->
							<view v-if="msg.thinking" class="think">
								<uni-icons type="tune" :size="12" color="#999999"></uni-icons>
								<text class="think__text">{{ msg.thinking }}</text>
							</view>

							<view class="bubble bubble--ai">
								<!-- 联网搜索加载态 -->
								<view v-if="msg.searching" class="searching">
									<uni-icons class="searching__icon" type="spinner-cycle" :size="16"
										color="#4cd964"></uni-icons>
									<text class="searching__text">正在联网搜索…</text>
								</view>

								<!-- 轻量 Markdown 渲染：由 parseMarkdown() 逐行解析出的块结构 -->
								<view v-for="(block, bi) in msg.blocks" :key="bi" class="md"
									:class="'md--' + block.type">
									<text v-if="block.type === 'li'" class="md__dot">•</text>
									<text v-else-if="block.type === 'ol'" class="md__dot">{{ block.index }}.</text>
									<text class="md__text">
										<!-- **加粗** 用分段渲染实现 -->
										<text v-for="(seg, si) in block.segments" :key="si" class="md__seg"
											:class="{ 'is-bold': seg.bold }">{{ seg.text }}</text>
										<!-- 流式输出光标：跟在最后一段文字末尾，模拟逐字输出 -->
										<text v-if="msg.streaming && bi === msg.blocks.length - 1"
											class="bubble__cursor">▍</text>
									</text>
								</view>

								<!-- 刚刚开始输出（还没有任何块）时的光标 -->
								<view v-if="msg.streaming && !msg.blocks.length" class="md md--p">
									<text class="md__text">
										<text class="bubble__cursor">▍</text>
									</text>
								</view>
							</view>

							<!-- 气泡下方一行操作按钮：复制 / 重新生成 / 点赞 -->
							<view v-if="!msg.streaming && !msg.searching" class="acts">
								<view class="acts__btn" hover-class="zn-hover" @tap="copyMessage(msg)">
									<uni-icons type="compose" :size="14" color="#999999"></uni-icons>
									<text class="acts__text">复制</text>
								</view>
								<!-- ⚠️ 只传下标：regenerate(index) 只声明了一个形参，
								     传 (msg, index) 会让下标位置收到消息对象，回调里取不到东西 -->
								<view class="acts__btn" hover-class="zn-hover" @tap="regenerate(index)">
									<uni-icons type="refresh" :size="14" color="#999999"></uni-icons>
									<text class="acts__text">重新生成</text>
								</view>
								<view class="acts__btn" hover-class="zn-hover" @tap="toggleLike(msg)">
									<uni-icons :type="msg.liked ? 'heart-filled' : 'heart'" :size="14"
										:color="msg.liked ? '#ff4d4f' : '#999999'"></uni-icons>
									<text class="acts__text">{{ msg.liked ? '已赞' : '点赞' }}</text>
								</view>
							</view>

							<!-- 参考来源（2~3 个浅灰小卡片） -->
							<view v-if="msg.refs.length && !msg.streaming && !msg.searching" class="refs">
								<text class="refs__title">参考来源</text>
								<view v-for="(ref, ri) in msg.refs" :key="ri" class="refs__item"
									hover-class="zn-hover" @tap="onRefTap(ref)">
									<text class="refs__name zn-ellipsis">{{ ref.title }}</text>
									<text class="refs__source zn-ellipsis">{{ ref.source }}</text>
								</view>
							</view>
						</view>
					</template>
				</view>

				<!-- 消息不多时把内容顶到上方，保证最后一条能滚到可视位置 -->
				<view class="chat__pad"></view>
			</view>
		</scroll-view>

		<!-- ==================== 3. 底部：输入区（固定在底部） ==================== -->
		<view class="ai__footer" :style="{ paddingBottom: safeBottom + 'px' }">
			<!-- 流式生成期间：停止生成 -->
			<view v-if="generating" class="stopbar">
				<view class="stopbar__btn" hover-class="zn-hover" @tap="onStopGenerate">
					<uni-icons type="smallcircle-filled" :size="13" color="#1f9c40"></uni-icons>
					<text class="stopbar__text">停止生成</text>
				</view>
			</view>

			<!-- 已选图片：上传中 / 上传失败的状态直接画在缩略图上，发送前可随时移除 -->
			<view v-if="pickedImages.length" class="picked">
				<view v-for="(img, i) in pickedImages" :key="img.key" class="picked__item">
					<image class="picked__img" :src="img.path" mode="aspectFill"></image>
					<!-- 上传中：转圈 + 文案，此时不允许发送 -->
					<view v-if="img.status === 'uploading'" class="picked__mask">
						<uni-icons class="picked__spin" type="spinner-cycle" :size="18" color="#ffffff"></uni-icons>
						<text class="picked__mask-text">上传中</text>
					</view>
					<!-- 上传失败：点一下重试，失败原因由服务端给出（见 uploadOne 的提示） -->
					<view v-else-if="img.status === 'failed'" class="picked__mask picked__mask--fail"
						@tap="retryUpload(i)">
						<uni-icons type="refresh" :size="18" color="#ffffff"></uni-icons>
						<text class="picked__mask-text">重试</text>
					</view>
					<view class="picked__del" @tap="removeImage(i)">
						<uni-icons type="closeempty" :size="11" color="#ffffff"></uni-icons>
					</view>
				</view>
			</view>
			<!-- 如实说明：当前模型不读图，图片只作为附件随问题一起发送，避免夸大能力 -->
			<text v-if="pickedImages.length" class="picked__tip">当前模型为纯文本模型，图片仅作为附件记录</text>

			<!-- ⚠️ 提示文案放在输入卡片【上方】（2026-09-22 调整）：
			     原先放在最底部，会被底部 tabBar 中央那个向上凸起的「AI助手」圆钮压住 -->
			<text class="ai__tip">AI 生成内容仅供参考，求职决策请结合自身情况判断</text>

			<view class="editor">
				<!-- 高度随内容自动增高：初始 1 行 56rpx，每行 +40rpx，最多 5 行 -->
				<textarea v-if="!hasOverlay" class="editor__input" :style="{ height: inputHeight + 'rpx' }"
					v-model="inputText" :maxlength="-1" :placeholder="inputPlaceholder"
					placeholder-class="editor__ph" :adjust-position="true" :show-confirm-bar="false"
					:cursor-spacing="24" confirm-type="send" @input="onInput"
					@linechange="onLineChange"></textarea>
				<!-- App 端原生 textarea 层级高于普通元素，弹层打开时用等高文本占位替换，避免压住遮罩 -->
				<view v-else class="editor__input editor__input--fake" :style="{ height: inputHeight + 'rpx' }">
					<text class="editor__fake-text zn-ellipsis">{{ inputText || inputPlaceholder }}</text>
				</view>

				<view class="editor__tools">
					<!-- 两个选项开关：联网搜索 / 深度思考 -->
					<view class="switch" :class="{ 'is-on': netSearch }" hover-class="zn-hover"
						@tap="netSearch = !netSearch">
						<uni-icons v-if="netSearch" type="checkmarkempty" :size="12" color="#1f9c40"></uni-icons>
						<text class="switch__text">联网搜索</text>
					</view>
					<view class="switch" :class="{ 'is-on': deepThink }" hover-class="zn-hover"
						@tap="deepThink = !deepThink">
						<uni-icons v-if="deepThink" type="checkmarkempty" :size="12" color="#1f9c40"></uni-icons>
						<text class="switch__text">深度思考</text>
					</view>

					<view class="editor__flex"></view>

					<!-- 「+」上传图片 / 文件 -->
					<view class="editor__plus" hover-class="zn-hover" @tap="openUpload">
						<uni-icons type="plusempty" :size="18" color="#8a9099"></uni-icons>
					</view>
					<!-- 发送：绿色圆形，输入为空时置灰不可点 -->
					<view class="editor__send" :class="{ 'is-disabled': !canSend }" hover-class="zn-hover"
						@tap="onSend">
						<uni-icons type="paperplane-filled" :size="17" color="#ffffff"></uni-icons>
					</view>
				</view>
			</view>
		</view>

		<!-- ==================== 4. 弹出层：历史对话列表（左侧抽屉） ==================== -->
		<view v-if="historyVisible" class="drawer">
			<view class="drawer__mask" @tap="closeHistory"></view>
			<view class="drawer__panel" :style="{ paddingTop: statusBarHeight + 'px' }">
				<!-- 顶部：搜索对话 -->
				<view class="drawer__head">
					<view class="drawer__search">
						<uni-icons type="search" :size="16" color="#9aa0a6"></uni-icons>
						<input class="drawer__input" v-model="keyword" placeholder="搜索历史对话"
							placeholder-class="drawer__ph" confirm-type="search" />
						<view v-if="keyword" class="drawer__clear" @tap="keyword = ''">
							<uni-icons type="closeempty" :size="15" color="#bbbbbb"></uni-icons>
						</view>
					</view>
					<text class="drawer__count">共 {{ historyTotal }} 个对话</text>
				</view>

				<!-- 分组列表：今日 / 7 天内 / 30 天内 / 更早（面板内部自己滚动） -->
				<scroll-view class="drawer__body" scroll-y :show-scrollbar="false">
					<view v-for="group in filteredConversations" :key="group.group" class="group">
						<text class="group__title">{{ group.group }}</text>
						<view v-for="item in group.list" :key="item.id" class="conv" hover-class="zn-hover"
							@tap="openSession(item)">
							<view class="conv__main">
								<view class="conv__row">
									<uni-icons v-if="item.pinned" type="star-filled" :size="12"
										color="#ff8f1f"></uni-icons>
									<text class="conv__title zn-ellipsis">{{ item.title }}</text>
								</view>
								<!-- 副标题用服务端返回的首条提问（preview），不再显示不存在的消息条数 -->
								<text class="conv__meta zn-ellipsis">{{ item.time }}{{ item.preview ? ' · ' + item.preview : '' }}</text>
							</view>
							<view class="conv__more" @tap.stop="onConvMore(item)">
								<uni-icons type="more-filled" :size="18" color="#999999"></uni-icons>
							</view>
						</view>
					</view>
					<view v-if="!filteredConversations.length" class="drawer__empty">
						<uni-icons type="search" :size="26" color="#d5dbe1"></uni-icons>
						<text class="drawer__empty-text">没有找到相关对话</text>
					</view>
					<view class="drawer__pad"></view>
				</scroll-view>

				<!-- 底部：用户头像 + 昵称 + 横向三个点（进入个人设置） -->
				<view class="drawer__foot" :style="{ paddingBottom: (safeBottom + 20) + 'px' }"
					hover-class="zn-hover" @tap="goSettings">
					<zn-avatar :name="user.nickname" :size="76" ring />
					<view class="drawer__foot-info">
						<text class="drawer__nickname">{{ user.nickname }}</text>
						<text class="drawer__level">{{ user.level }}</text>
					</view>
					<uni-icons type="more-filled" :size="20" color="#999999"></uni-icons>
				</view>
			</view>
		</view>

		<!-- ==================== 5. 弹出层：「+」上传操作面板（底部弹出） ==================== -->
		<view v-if="uploadVisible" class="sheet">
			<view class="sheet__mask" @tap="uploadVisible = false"></view>
			<view class="sheet__panel" :style="{ paddingBottom: (safeBottom + 24) + 'px' }">
				<text class="sheet__title">上传图片 / 文件</text>
				<!-- 不写「拍照解题」：当前模型是纯文本模型，不读图，只把图片作为附件记录 -->
				<text class="sheet__desc">拍照或从相册选择，图片随问题一起发送（当前模型为纯文本模型）</text>
				<view class="sheet__grid">
					<view v-for="(act, i) in uploadActions" :key="act.key" class="sheet__item"
						hover-class="zn-hover" @tap="onUpload(act)">
						<view class="sheet__icon" :style="{ backgroundColor: uploadBgs[i] }">
							<uni-icons :type="act.icon" :size="25" :color="act.color"></uni-icons>
						</view>
						<text class="sheet__label">{{ act.title }}</text>
					</view>
				</view>
				<view class="sheet__cancel" hover-class="zn-hover" @tap="uploadVisible = false">
					<text class="sheet__cancel-text">取消</text>
				</view>
			</view>
		</view>

		<!-- ==================== 底部 tabBar ==================== -->
		<zn-tab-bar class="ai__tabbar" current="ai" />
	</view>
</template>

<script>
	/**
	 * AI 求职助手（本页是 tab 页）
	 * 严格实现需求文档：固定顶部导航（左弹出会话列表 / 右新建对话）、中间对话区、固定底部输入区
	 * （自动增高输入框、联网搜索 / 深度思考开关、「+」拍照与相册）
	 * 并按行业惯例（默会知识）补充：欢迎态能力卡与推荐问题、轻量 Markdown 渲染、
	 * 复制 / 重新生成 / 点赞、历史会话抽屉（搜索 + 分组 + 置顶/重命名/删除）
	 * 说明：对话走真实链路 —— 列表与消息来自 HTTP 接口（services/chat.js），
	 * 回答文本由 WebSocket 流式推送（见 initChat），不再有本地模拟输出；
	 * 拍照 / 相册选中的图片会先上传到 POST /ai/upload，再随 chat 帧的 images 字段发出，
	 * 历史消息里的 images 也会渲染成缩略图（当前模型为纯文本模型，图片只作附件记录）。
	 */
	import { getStatusBarHeight, getSafeAreaBottom, fromNow, toast, storage } from '@/common/utils/format.js'
	import { getConfig } from '@/services/content.js'
	import { createChat, listMessages, listSessions, deleteSession, uploadImage } from '@/services/chat.js'
	import { BASE_URL } from '@/common/config.js'
	// 登录态判断与清除：WebSocket 鉴权依赖 token，未登录连接必被服务端关闭
	import { isLogined, clearLoginState, getCachedUser } from '@/services/user.js'

	/* =========================================================
	 * 本页额外 Mock 数据（不改 common/mock，避免多人并行冲突）
	 * =======================================================*/

	/** 可切换的模型 / 模式（顶部中间的模型选择入口） */
	const AI_MODELS = [
		{ name: '深度思考', desc: '已接入深度思考' },
		{ name: '快速回答', desc: '快速回答 · 秒回' },
		{ name: '联网增强', desc: '已开启联网增强' }
	]

	/** 快捷能力卡底色（图标颜色用 mock 数据自带的 color） */
	const CAPABILITY_BGS = ['#e9fbef', '#eaf4ff', '#fff4e8', '#f2eefd']

	/** 「+」上传面板的三个操作 */
	const UPLOAD_ACTIONS = [
		{ key: 'camera', title: '拍照', icon: 'camera', color: '#4cd964' },
		{ key: 'album', title: '从相册选择', icon: 'image', color: '#3b9dff' },
		{ key: 'file', title: '选择文件', icon: 'folder-add', color: '#ff8f1f' }
	]

	/** 上传面板图标底色 */
	const UPLOAD_BGS = ['#e9fbef', '#eaf4ff', '#fff4e8']

	/**
	 * 把服务端时间字符串（yyyy-MM-dd HH:mm:ss）转成各端都能解析的写法
	 * ⚠️ iOS / 部分小程序里 new Date('2024-01-01 10:00:00') 会得到 Invalid Date，
	 *    必须先把短横线换成斜杠；解析失败时调用方按「更早」处理。
	 */
	function toDateStr(value) {
		return String(value || '').replace(/-/g, '/')
	}

	/** 最多可同时挂几张图片（与服务端上传接口无关，纯粹是输入区的容量上限） */
	const MAX_IMAGES = 3

	/**
	 * 服务端源站地址：BASE_URL 去掉结尾的 /api/v1
	 * ⚠️ 不写死任何 IP/域名：换环境只需改 common/config.js，这里自动跟随
	 */
	function serverOrigin() {
		return String(BASE_URL).replace(/\/api\/v\d+\/?$/, '')
	}

	/**
	 * 把上传接口返回的「相对源站」地址转成可直接喂给 <image> 的地址
	 * 以 / 开头的才拼源站；本地临时路径（blob:、http://tmp/、_doc/ 等）原样返回
	 */
	function mediaUrl(url) {
		if (!url) return ''
		return String(url).charAt(0) === '/' ? serverOrigin() + url : String(url)
	}

	export default {
		data() {
			return {
				statusBarHeight: 0,
				safeBottom: 0,
				/* ---------------- 静态数据（欢迎态文案与能力卡，来自页面配置） ---------------- */
				aiWelcome: { greeting: '', desc: '', suggestions: [] },
				aiCapabilities: [],
				// 头像/昵称取自本地登录缓存（未登录时为空对象，模板按空值渲染）
				user: {},
				models: AI_MODELS,
				modelIndex: 0,
				// 历史对话：平铺列表，页面加载后从服务端拉取（见 loadSessions）；
				// 搜索过滤与时间分组由 filteredConversations 计算得出
				conversations: [],
				capabilityBgs: CAPABILITY_BGS,
				uploadActions: UPLOAD_ACTIONS,
				uploadBgs: UPLOAD_BGS,
				/* ---------------- 弹出层状态 ---------------- */
				historyVisible: false,
				uploadVisible: false,
				keyword: '',
				/* ---------------- 对话消息 ---------------- */
				messages: [],
				scrollInto: '',
				/* ---------------- 输入区 ---------------- */
				inputText: '',
				inputPlaceholder: '问我任何求职问题，可换行输入',
				inputLines: 1,
				maxLines: 5,
				netSearch: true,
				deepThink: true,
				// 待发送图片：[{ key, path, status: uploading|done|failed, id, url, error }]
				pickedImages: [],
				imgSeed: 0,
				/* ---------------- 生成状态 ---------------- */
				generating: false,
				streamIndex: -1,
				searchTimer: null,
				msgSeed: 0,
				/* ---------------- 服务端会话 ---------------- */
				sessionId: '',   // 当前会话ID；空串表示新会话（由服务端懒建并回传）
				chatCtl: null    // WebSocket 连接控制器；为 null 即代表需要重建（见 onShow / sendText）
			}
		},
		computed: {
			/** 当前模型 / 模式 */
			currentModel() {
				return this.models[this.modelIndex] || this.models[0]
			},
			/** 输入框是否有内容（空则发送按钮置灰不可点） */
			canSend() {
				return this.inputText.trim().length > 0
			},
			/**
			 * 输入框高度：1 行 56rpx，之后每行 +40rpx，最多 maxLines 行
			 *
			 * ⚠️ 这两个数字必须与 `.editor__input` 的 line-height(40rpx) 和上下 padding(8rpx) 对齐：
			 *    1 行 = 8 + 40 + 8 = 56rpx；每多一行正好多一行文字高 40rpx，不会出现半行裁切。
			 * ⚠️ 2026-09-22 紧凑化：原为「1 行 80rpx、每行 +44rpx」，输入区整体约 137px 高，
			 *    在小屏手机上挤占对话可视区（用户反馈「输入框太大，挡着看回答」），
			 *    故整体压缩约 25%（输入区 + 底部 tabBar 由约 191px 降至约 160px）。
			 * ⚠️ 2026-09-22 二次紧凑化：1 行高度由 68rpx 收到 56rpx（padding 14 -> 8），
			 *    并把开关、停止按钮、提示文案一并收小，底部输入区整体再矮约 40%。
			 */
			inputHeight() {
				return 56 + (this.inputLines - 1) * 40
			},
			/** 是否有弹层打开（打开时用等高文本占位替换原生 textarea） */
			hasOverlay() {
				return this.historyVisible || this.uploadVisible
			},
			/** 历史对话总数 */
			historyTotal() {
				return this.conversations.length
			},
			/** 搜索过滤 + 按最后活跃时间分组（今日 / 7 天内 / 30 天内 / 更早） */
			filteredConversations() {
				const kw = this.keyword.trim()
				// 标题与首条提问都参与搜索，避免「聊过的内容搜不到」
				const list = kw
					? this.conversations.filter(item => (item.title + item.preview).indexOf(kw) > -1)
					: this.conversations
				// 服务端已按 updated_at 倒序返回，顺序遍历即可保持组内顺序，
				// 组的先后顺序也随之固定为 今日 → 7 天内 → 30 天内 → 更早
				const groups = []
				list.forEach(item => {
					const name = this.groupName(this.convStamp(item))
					let group = groups.find(g => g.group === name)
					if (!group) {
						group = { group: name, list: [] }
						groups.push(group)
					}
					group.list.push(item)
				})
				return groups
			}
		},
		onLoad() {
			this.statusBarHeight = getStatusBarHeight()
			this.safeBottom = getSafeAreaBottom()

			// 欢迎态文案与能力卡：来自服务端页面配置（失败时保持空态，不影响对话功能）
			this.loadWelcomeConfig()
			this.user = getCachedUser() || {}

			// ---------- 登录守卫 ----------
			// WebSocket 握手时会把 token 放在 query 上做鉴权，
			// 未登录时服务端会立刻以 4401 关闭连接，用户提问后得不到任何回答。
			// 这里只提前说明原因，不在这里建立连接：连接与列表统一交给 onShow，
			// 这样「先打开页面 → 再去登录 → 切回本 tab」也能自动完成初始化。
			if (!isLogined()) {
				uni.showToast({ title: '请先登录后使用 AI 求职助手', icon: 'none' })
			}
		},
		onShow() {
			// 昵称 / 等级可能在「我的 → 设置」里被改过，每次回到本页同步一次
			this.user = getCachedUser() || {}

			// 从「会话详情页 → 继续对话」返回时，恢复对应会话
			const pending = storage.get('zn_ai_session')
			if (pending) {
				storage.remove('zn_ai_session')
				// 边界：若期间登录态已失效，恢复会话必然 401，
				// 清掉标记直接跳过，避免弹一个让人摸不着头脑的错误提示
				if (isLogined()) this.resumeSession(pending)
			}

			// 每次回到本页都重建状态：
			//   - onShow 在 onLoad 之后必然触发一次，初始化放这里不会重复拉取；
			//   - 连接已在 onHide 断开（见 teardownChat），需要重新 initChat()；
			//   - 未登录时直接返回，用户登录后再切回来即可拉到会话列表，
			//     修复此前「抽屉里一直显示共 0 个对话」的问题。
			if (!isLogined()) return
			this.initChat()
			this.loadSessions()
		},
		onHide() {
			// ⚠️ 本页是 tabBar 页：切到其他 tab / 跳转其他页面只触发 onHide，
			//    永远等不到 onUnload。必须在这里断开连接，
			//    否则服务端会继续把生成结果推给一个看不见的页面（最长挂到 AI_WS_IDLE 空闲超时）。
			this.teardownChat()
		},
		onUnload() {
			// 页面卸载：与 onHide 共用同一套收尾
			this.teardownChat()
		},
		methods: {
			/**
			 * 加载欢迎态文案与能力卡（服务端页面配置）
			 *
			 * ⚠️ 两个配置互不依赖，且都属于「可有可无」的展示内容：
			 *    失败时保持空态（欢迎区不渲染），绝不阻塞对话主流程。
			 */
			async loadWelcomeConfig() {
				// ⚠️ 招聘改造：配置键由 aiWelcome / aiCapabilities 改为 rcAiWelcome / rcAiCapabilities
				//    （rc 前缀是招聘端在 page_config 表里的命名空间；学习端的旧键原样保留以便回滚）。
				//    字段结构也随之变化：旧的 {greeting, desc} → 新的 {title, subtitle}，
				//    suggestions 每项多了 prompt 字段（真正发给模型的完整问题，比标题更适合当提问内容）。
				const [welcome, caps] = await Promise.all([
					this.safeConfig('rcAiWelcome'),
					this.safeConfig('rcAiCapabilities')
				])
				if (welcome && typeof welcome === 'object') {
					this.aiWelcome = {
						greeting: welcome.title || '',
						desc: welcome.subtitle || '',
						suggestions: Array.isArray(welcome.suggestions) ? welcome.suggestions : []
					}
				}
				if (Array.isArray(caps)) this.aiCapabilities = caps
			},
			/** 读取一条页面配置，失败返回 null（不弹错） */
			async safeConfig(key) {
				try {
					return await getConfig(key)
				} catch (e) {
					return null
				}
			},

			/* =========================================================
			 * 一、轻量 Markdown 渲染（零依赖，逐行解析）
			 * 调用 parseMarkdown(content) 得到块结构：
			 * [{ type: 'h3'|'h2'|'p'|'li'|'ol'|'quote', text, index?, segments: [{ text, bold }] }]
			 * 模板里 v-for 渲染，**加粗** 用 segments 分段渲染实现
			 * =======================================================*/

			/** 解析一行里的 **加粗** 片段 */
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
				if (!segments.length) segments.push({ text, bold: false })
				return segments
			},

			/** 逐行解析 Markdown 文本为块数组 */
			parseMarkdown(content) {
				const lines = String(content || '').split('\n')
				const blocks = []
				lines.forEach(raw => {
					const line = raw.replace(/\s+$/, '')
					const text = line.trim()
					if (!text) return // 空行只做段落分隔，不渲染
					let type = 'p'
					let body = text
					let index = 0
					if (/^###\s+/.test(text)) {
						type = 'h3'
						body = text.replace(/^###\s+/, '')
					} else if (/^##\s+/.test(text)) {
						type = 'h2'
						body = text.replace(/^##\s+/, '')
					} else if (/^#\s+/.test(text)) {
						type = 'h2'
						body = text.replace(/^#\s+/, '')
					} else if (/^>\s?/.test(text)) {
						type = 'quote'
						body = text.replace(/^>\s?/, '')
					} else if (/^[-*]\s+/.test(text)) {
						type = 'li'
						body = text.replace(/^[-*]\s+/, '')
					} else if (/^\d+[.、]\s*/.test(text)) {
						type = 'ol'
						body = text.replace(/^\d+[.、]\s*/, '')
						index = Number(text.match(/^(\d+)/)[1]) || 1
					}
					blocks.push({ type, text: body, index, segments: this.splitBold(body) })
				})
				return blocks
			},

			/* =========================================================
			 * 二、模拟流式输出（纯本地，无网络请求）
			 * =======================================================*/

			/** 新建一条消息（字段一次声明全，保证流式追加时响应式生效） */
			createMessage(role, content) {
				this.msgSeed++
				return {
					id: 'msg' + this.msgSeed,
					role,
					content,
					blocks: role === 'assistant' ? this.parseMarkdown(content) : [],
					// 附件图片（用户消息用）：[{ url }]，url 已是可直接渲染的地址
					images: [],
					time: this.timeNow(),
					thinking: '',
					refs: [],
					liked: false,
					searching: false,
					streaming: false
				}
			},

			/** 当前时间 HH:mm */
			timeNow() {
				const d = new Date()
				const p = n => String(n).padStart(2, '0')
				return p(d.getHours()) + ':' + p(d.getMinutes())
			},

			/* =========================================================
			 * 二、WebSocket 连接与真实流式对话
			 * =======================================================*/

			/** 建立 WebSocket 连接（onShow 时调用，断开后由 sendText / onShow 自动重建） */
			initChat() {
				if (this.chatCtl) return
				// ⚠️ 先落到局部变量：onError / onClose 里要靠它做「还是不是当前连接」的身份比对
				const ctl = createChat({
					// 懒建会话：服务端创建会话后回传 id 与标题
					onSession: frame => {
						this.sessionId = frame.session_id || ''
						this.loadSessions()
					},
					// 增量文本：追加到当前助手消息并重新解析 markdown
					onDelta: text => {
						const msg = this.messages[this.streamIndex]
						if (!msg) return
						msg.content += text
						msg.blocks = this.parseMarkdown(msg.content)
						this.scrollToLatest()
					},
					onDone: () => {
						this.finishStream()
					},
					onError: (code, msg) => {
						// code === -1 表示连接级故障（连不上 / 已断开），
						// 此时必须作废控制器，否则后续提问会被塞进坏连接里静默丢弃。
						// ⚠️ 只在「当前控制器就是它」时才置空（onClose 同理）：
						//    同一条 socket 会先 onError 再 onClose，中间用户若已 initChat 建了新连接，
						//    无脑置空会把新连接变成野指针 —— 既没人关闭它，后续提问还会再建一条。
						if (code === -1 && (!this.chatCtl || this.chatCtl === ctl)) this.chatCtl = null
						this.onStreamError(code, msg)
					},
					onClose: code => {
						// ⚠️ 关键修复点：这里必须把控制器置空。
						// 原实现只置了一个从未被读取的 wsClosed 标记，
						// 导致 sendText 中 `if (!this.chatCtl) this.initChat()` 判断失真：
						// 控制器仍指向一条已关闭的连接，提问帧进入 pending 队列后永远发不出去，
						// 页面一直停在「正在生成」——表现出来就是「AI 求职助手不回答问题」。
						// 另外做身份比对，避免把后来新建的连接误伤成野指针。
						if (!this.chatCtl || this.chatCtl === ctl) this.chatCtl = null

						// 4401 = 服务端判定未登录 / 登录已过期（对应后端的 close(4401)）
						if (code === 4401) {
							clearLoginState()
							toast('登录已失效，请重新登录', 'none')
							return
						}

						// 生成过程中连接断开：收尾并提示
						if (this.generating) this.onStreamError(-1, '连接已断开，请重试')
					}
				})
				this.chatCtl = ctl
			},

			/**
			 * 断开连接并收尾在途生成（onHide / onUnload 共用）
			 *
			 * ⚠️ 本页是 tabBar 页，切 tab 不会触发 onUnload，必须在 onHide 里主动断开：
			 *    否则服务端会继续把增量推给一个看不见的页面，最长一直挂到空闲超时。
			 *    断连后服务端会取消本轮并把已生成的内容落库，回到本页仍能看到半截回答。
			 */
			teardownChat() {
				// 只有在途生成才需要本地收尾：
				// 空闲时断开不改动任何消息，否则每次切 tab 都会把最后一条的时间刷成当前时间
				if (this.generating) {
					const cur = this.endLocalStream()
					if (cur) cur.time = this.timeNow()
				}
				if (this.chatCtl) {
					this.chatCtl.close()
					this.chatCtl = null
				}
			},

			/**
			 * 加载服务端会话列表
			 *
			 * 保留 updatedAt 与 preview：
			 *   - updatedAt：渲染相对时间，并作为 今日 / 7 天内 / 30 天内 / 更早 的分组依据；
			 *   - preview ：该会话的首条提问，替代原先凭空写死的「N 条消息」（服务端没有条数字段）。
			 * 分组与搜索都在 filteredConversations 里计算，这里只做平铺映射。
			 */
			async loadSessions() {
				try {
					const list = await listSessions()
					this.conversations = list.map(s => ({
						id: s.id,
						title: s.title || '新对话',
						preview: s.preview || '',
						updatedAt: s.updatedAt || '',
						time: fromNow(toDateStr(s.updatedAt)) || '时间未知'
					}))
				} catch (e) {
					// 未登录或网络异常：静默保持现状，不打断当前对话
				}
			},

			/** 会话最后活跃时间的时间戳（毫秒）；解析不出来时返回 0 */
			convStamp(item) {
				const t = new Date(toDateStr(item.updatedAt)).getTime()
				return isNaN(t) ? 0 : t
			},

			/** 按时间戳归组：今日 / 7 天内 / 30 天内 / 更早 */
			groupName(stamp) {
				if (!stamp) return '更早'
				const now = new Date()
				const day = 24 * 60 * 60 * 1000
				// 以「今天 00:00」为基准，避免用 24 小时差把昨天下午算进今日
				const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime()
				if (stamp >= startOfToday) return '今日'
				if (stamp >= startOfToday - 6 * day) return '7 天内'
				if (stamp >= startOfToday - 29 * day) return '30 天内'
				return '更早'
			},

			/** 恢复指定会话：拉取其历史消息并绑定 sessionId */
			async resumeSession(sessionId) {
				try {
					const res = await listMessages(sessionId)
					this.sessionId = String(sessionId)
					this.messages = (res.list || []).map(m => ({
						id: 'srv' + m.id,
						role: m.role,
						content: m.content,
						blocks: m.role === 'assistant' ? this.parseMarkdown(m.content) : [],
						// 历史里的附件：服务端给的是相对源站地址，拼上源站才能渲染
						images: (m.images || []).map(img => ({ url: mediaUrl(img.url) })),
						time: '',
						thinking: '',
						refs: [],
						liked: false,
						searching: false,
						streaming: false
					}))
					this.streamIndex = this.messages.length - 1
					this.$nextTick(() => this.scrollToLatest())
				} catch (e) {
					// 失败提示已由请求层统一弹出
				}
			},

			/** 发送一条文本（推荐问题 / 能力卡 / 输入框共用，附件图片随本次提问一起发出） */
			sendText(text) {
				const content = String(text || '').trim()
				if (!content) return
				// 登录态可能在使用过程中失效（如 token 过期、被其他页面登出），
				// 此处二次校验，避免把提问发进一条注定被拒绝的连接
				if (!isLogined()) {
					toast('请先登录后使用 AI 求职助手', 'none')
					return
				}
				if (this.generating) {
					toast('正在生成中，可先点「停止生成」')
					return
				}
				// 图片还没上传完 / 上传失败时先不发：否则会漏掉还没拿到 id 的图片
				const attached = this.readyImages()
				if (!attached) return
				// 控制器为空说明连接尚未建立或已断开，此处重建（见 initChat 的 onClose）
				if (!this.chatCtl) this.initChat()

				// 先把本地缩略图挂到用户气泡上：此后清空输入区也不会丢图
				const userMsg = this.createMessage('user', content)
				userMsg.images = attached.bubbles
				this.messages.push(userMsg)
				this.inputText = ''
				this.inputLines = 1

				// 立刻插入一条空的助手消息，由 WebSocket 增量填充
				this.messages.push(this.createMessage('assistant', ''))
				this.streamIndex = this.messages.length - 1
				this.generating = true

				const msg = this.messages[this.streamIndex]
				msg.streaming = true
				if (this.deepThink) msg.thinking = '已深度思考'
				this.scrollToLatest()

				// 发起提问（sessionId 为空则由服务端懒建会话；images 为空则不下发该字段）
				this.chatCtl.chat(content, this.sessionId, attached.ids)
				// 确认这一帧已经发出（chat() 要么直接发，要么入队等 onOpen）后再清空待发列表
				this.pickedImages = []
			},

			/**
			 * 汇总本次可以发送的图片
			 * @returns {{ids:Array<string>, bubbles:Array<object>}|null}
			 *          ids     —— 上传接口返回的图片 id，交给 chat 帧
			 *          bubbles —— 用户气泡要显示的缩略图地址
			 *          null    —— 当前不能发送（原因已通过 toast 说明）
			 */
			readyImages() {
				if (!this.pickedImages.length) return { ids: [], bubbles: [] }
				if (this.pickedImages.some(img => img.status === 'uploading')) {
					toast('图片还在上传中，请稍候')
					return null
				}
				if (this.pickedImages.some(img => img.status !== 'done' || !img.id)) {
					toast('有图片上传失败，请先点重试或移除')
					return null
				}
				return {
					ids: this.pickedImages.map(img => img.id),
					// 优先用服务端地址（临时文件被清理后依然能显示），没有则退回本地路径
					bubbles: this.pickedImages.map(img => ({ url: mediaUrl(img.url) || img.path }))
				}
			},

			/**
			 * 本地收尾在途生成（不发任何网络请求）
			 * 出错 / 页面隐藏共用同一套规则：停掉动画与定时器，
			 * 一个字都没生成时删掉这条空助手消息，否则由调用方补时间戳。
			 * @returns {object|null} 保留下来的助手消息；无内容被删除时返回 null
			 */
			endLocalStream() {
				this.clearTimers()
				this.generating = false
				const cur = this.messages[this.streamIndex]
				if (!cur) return null
				cur.streaming = false
				cur.searching = false
				cur.thinking = ''
				// 若一个字都没生成，直接移除这条空助手消息
				if (!cur.content) {
					this.messages.splice(this.streamIndex, 1)
					this.streamIndex = -1
					return null
				}
				return cur
			},

			/** 对话出错：终止当前消息并提示 */
			onStreamError(code, msg) {
				const cur = this.endLocalStream()
				if (cur) cur.time = this.timeNow()
				toast(msg || ('对话失败（' + code + '）'), 'none')
			},

			/* 说明：原「本地模拟流式输出」已移除，
			   现在文本由 WebSocket 的 onDelta 回调逐段拼接（见 initChat）。 */

			/** 流式正常结束 */
			finishStream() {
				const msg = this.messages[this.streamIndex]
				this.clearTimers()
				this.generating = false
				if (!msg) return
				msg.streaming = false
				msg.searching = false
				msg.thinking = ''
				msg.time = this.timeNow()
				// 真实对话不再展示模拟的「参考来源」，保持为空
				msg.refs = []
				this.scrollToLatest()
			},

			/** 停止生成（用户点「停止生成」） */
			onStopGenerate() {
				// 通知服务端中断本轮生成（已生成的部分会落库）
				if (this.chatCtl) this.chatCtl.stop()
				const msg = this.messages[this.streamIndex]
				this.clearTimers()
				this.generating = false
				if (msg) {
					msg.streaming = false
					msg.searching = false
					msg.thinking = ''
					if (!msg.content) {
						msg.content = '已停止生成，你可以换个问法再问我一次。'
						msg.blocks = this.parseMarkdown(msg.content)
					} else {
						msg.time = this.timeNow()
					}
				}
				toast('已停止生成')
			},

			/** 清理遗留定时器（仅剩联网搜索提示用的延时器） */
			clearTimers() {
				if (this.searchTimer) {
					clearTimeout(this.searchTimer)
					this.searchTimer = null
				}
			},

			/* =========================================================
			 * 三、消息交互
			 * =======================================================*/

			/** 复制该条回复 */
			copyMessage(msg) {
				uni.setClipboardData({
					data: msg.content,
					success: () => toast('已复制到剪贴板')
				})
			},

			/**
			 * 重新生成：清空该条助手消息，把上一条用户提问重新发一遍
			 *
			 * ⚠️ 修复：模板原先写 @tap="regenerate(msg, index)"，而方法只声明了一个形参，
			 *    于是形参拿到的是消息对象：`index - 1` 变成 NaN、`this.messages[index]`
			 *    取到 undefined，函数在取消息那一步就 return 了 —— 点了完全没反应。
			 *    现在模板改成 @tap="regenerate(index)"，形参与实参一一对应。
			 *    最后一条回复同样适用：问题在它前面，循环一定能找到。
			 */
			regenerate(index) {
				if (this.generating) {
					toast('正在生成中，请稍候')
					return
				}
				if (!isLogined()) {
					toast('请先登录后使用 AI 求职助手', 'none')
					return
				}
				const msg = this.messages[index]
				if (!msg || msg.role !== 'assistant') return

				// 取上一条用户提问作为重新生成的依据
				let question = ''
				for (let i = index - 1; i >= 0; i--) {
					if (this.messages[i].role === 'user') {
						question = this.messages[i].content
						break
					}
				}
				if (!question) {
					toast('没有找到对应的问题，无法重新生成')
					return
				}

				// 连接可能在 onHide 时被断开，按发送路径重建
				if (!this.chatCtl) this.initChat()

				// 清空这一条后复用同一套流式渲染：sessionId 不变，
				// 服务端会带着该会话的历史上下文重新生成
				msg.content = ''
				msg.blocks = []
				msg.refs = []
				msg.thinking = this.deepThink ? '已深度思考' : ''
				msg.streaming = true
				this.streamIndex = index
				this.generating = true
				// 滚到正在重新生成的那一条（不一定是最后一条）
				this.scrollToMsg(index)
				this.chatCtl.chat(question, this.sessionId)
			},

			/** 点赞 / 取消点赞 */
			toggleLike(msg) {
				msg.liked = !msg.liked
			},

			/** 点击参考来源 */
			onRefTap(ref) {
				toast('查看来源：' + ref.title)
			},

			/** 滚到指定下标的这条消息（先清空再赋值，保证连续追加也能触发滚动） */
			scrollToMsg(index) {
				if (index < 0 || index >= this.messages.length) return
				const target = 'msg' + index
				this.scrollInto = ''
				this.$nextTick(() => {
					this.scrollInto = target
				})
			},

			/** 滚到最新一条消息 */
			scrollToLatest() {
				this.scrollToMsg(this.messages.length - 1)
			},

			/* =========================================================
			 * 四、底部输入区
			 * =======================================================*/

			/** 发送 */
			onSend() {
				if (!this.canSend) {
					// 图片只作为附件，服务端要求正文非空，这里如实提示而不是让请求白跑一次
					toast(this.pickedImages.length ? '请先输入问题，图片会随问题一起发送' : '请先输入内容')
					return
				}
				this.sendText(this.inputText)
			},

			/**
			 * 输入事件：按字符数兜底估算行数（一行约 26 个汉字），换行符按整行计算
			 * App 端 @linechange 更准确，两者都会调用 applyLines 收敛到 1~5 行
			 */
			onInput(e) {
				const val = (e.detail && e.detail.value) || ''
				this.inputText = val
				const lines = val.split('\n').reduce((n, seg) => n + Math.max(1, Math.ceil(seg.length / 26)), 0)
				this.applyLines(lines)
			},

			/** textarea 官方行数变化事件（平台给出的真实行数，优先采用） */
			onLineChange(e) {
				this.applyLines((e.detail && e.detail.lineCount) || 1)
			},

			/** 收敛行数：最少 1 行，最多 maxLines 行 */
			applyLines(lines) {
				this.inputLines = Math.min(this.maxLines, Math.max(1, Number(lines) || 1))
			},

			/** 打开「+」上传面板 */
			openUpload() {
				this.uploadVisible = true
			},

			/** 上传面板三项操作：拍照 / 相册 / 选择文件 */
			onUpload(act) {
				this.uploadVisible = false
				if (act.key === 'file') {
					this.chooseFile()
					return
				}
				if (this.pickedImages.length >= MAX_IMAGES) {
					toast('最多只能添加 ' + MAX_IMAGES + ' 张图片')
					return
				}
				// 拍照与相册使用标准 API：uni.chooseImage，选完立刻开始上传
				uni.chooseImage({
					count: MAX_IMAGES - this.pickedImages.length,
					sizeType: ['compressed'],
					sourceType: [act.key === 'camera' ? 'camera' : 'album'],
					success: res => {
						const paths = res.tempFilePaths || []
						paths
							.slice(0, MAX_IMAGES - this.pickedImages.length)
							.forEach(path => this.addPickedImage(path))
					},
					fail: res => {
						// 用户主动取消不是错误，只有真正的失败（如权限被拒）才提示
						if (/cancel/i.test((res && res.errMsg) || '')) return
						toast('无法打开' + (act.key === 'camera' ? '相机' : '相册') + '，请检查系统权限')
					}
				})
			},

			/**
			 * 选择文件：各端可用的 API 不同，不支持的平台如实说明（不假装「开发中」）
			 *   - 微信小程序：uni.chooseMessageFile（从聊天记录里选）
			 *   - H5 / App：uni.chooseFile（系统文件选择器）
			 *   - 其余平台：两个 API 都不存在，直接提示改用拍照 / 相册
			 * ⚠️ 上传接口只接受图片，因此两个入口都限制为图片格式，
			 *    选到别的格式会被服务端以 41009 拒绝，没必要让用户白跑一趟。
			 */
			chooseFile() {
				if (this.pickedImages.length >= MAX_IMAGES) {
					toast('最多只能添加 ' + MAX_IMAGES + ' 张图片')
					return
				}
				let picked = false
				// #ifdef MP-WEIXIN
				picked = true
				uni.chooseMessageFile({
					count: 1,
					type: 'image',
					success: res => {
						const file = (res.tempFiles || [])[0]
						if (file && file.path) this.addPickedImage(file.path)
					},
					fail: res => {
						if (/cancel/i.test((res && res.errMsg) || '')) return
						toast('无法打开聊天文件，请改用拍照或相册')
					}
				})
				// #endif
				// #ifdef H5 || APP-PLUS
				picked = true
				uni.chooseFile({
					count: 1,
					// 只让用户选图片：上传接口只接受图片，选到别的格式必然被 41009 拒绝
					type: 'image',
					success: res => {
						const path = (res.tempFilePaths || [])[0]
						if (path) this.addPickedImage(path)
					},
					fail: res => {
						if (/cancel/i.test((res && res.errMsg) || '')) return
						toast('无法打开文件选择器，请改用拍照或相册')
					}
				})
				// #endif
				if (!picked) toast('当前平台暂不支持选择文件，请使用拍照或相册', 'none')
			},

			/** 新增一张待发送图片，并立即开始上传 */
			addPickedImage(path) {
				const item = {
					key: 'img' + (++this.imgSeed),
					path,
					status: 'uploading',
					id: '',
					url: '',
					error: ''
				}
				this.pickedImages.push(item)
				this.uploadOne(item)
			},

			/**
			 * 上传单张图片
			 * 失败时保留缩略图并标记为 failed，用户可以在缩略图上点「重试」或直接移除；
			 * 服务端会给出准确原因（41009 不是有效图片 / 41010 超过体积上限 / 41011 文件为空），
			 * 这里原样展示，不做二次翻译。
			 */
			async uploadOne(item) {
				item.status = 'uploading'
				item.error = ''
				try {
					const data = await uploadImage(item.path)
					if (!data.id) {
						item.status = 'failed'
						item.error = '服务端未返回图片标识'
						toast(item.error, 'none')
						return
					}
					item.id = data.id
					item.url = data.url || ''
					item.status = 'done'
				} catch (e) {
					item.status = 'failed'
					item.error = (e && e.message) || '上传失败'
					toast(item.error, 'none')
				}
			},

			/** 上传失败后重试 */
			retryUpload(index) {
				const item = this.pickedImages[index]
				if (!item) return
				this.uploadOne(item)
			},

			/** 发送前移除某张图片（上传中 / 失败 / 成功都可移除） */
			removeImage(index) {
				this.pickedImages.splice(index, 1)
			},

			/** 点开图片看大图（用户气泡里的附件） */
			previewImage(msg, index) {
				const urls = (msg.images || []).map(img => img.url).filter(Boolean)
				if (!urls.length) return
				uni.previewImage({ urls, current: urls[index] || urls[0] })
			},

			/* =========================================================
			 * 五、顶部导航交互
			 * =======================================================*/

			/** 切换模型 / 模式 */
			onPickModel() {
				uni.showActionSheet({
					itemList: this.models.map(m => m.name),
					success: res => {
						this.modelIndex = res.tapIndex
					}
				})
			},

			/** 新建对话：清空消息列表并回到欢迎态 */
			onNewChat() {
				// 生成中则先通知服务端中断，避免其继续写入旧会话
				if (this.generating) {
					if (this.chatCtl) this.chatCtl.stop()
					this.clearTimers()
				}
				this.generating = false
				this.messages = []
				this.scrollInto = ''
				this.pickedImages = []
				this.inputText = ''
				this.inputLines = 1
				// ⚠️ 清空会话ID：下次提问时由服务端懒建新会话
				this.sessionId = ''
				this.streamIndex = -1
				toast('已开启新对话')
			},

			/**
			 * 快捷能力卡：直接发送卡片自带的完整提问
			 *
			 * ⚠️ 招聘改造遗留已修：改造前这里是「第 1 张卡唤起上传面板（拍照解题）、
			 *    其余发送硬编码的学习类提问（练口语 / 批改英语作文 / 复盘错题）」。
			 *    现在的四张卡是简历优化 / 模拟面试 / 岗位匹配分析 / 求职进度诊断，
			 *    沿用旧逻辑会导致点「简历优化」弹出相册面板、其余三张发出与招聘无关的提问。
			 *
			 * @param {Object} item 能力卡配置对象 { icon, title, desc, prompt }
			 * 兜底：种子数据若缺 prompt，退化为卡片标题（title 语义完整，仍能发起有效提问）
			 */
			onCapability(item) {
				if (!item) return
				const text = item.prompt || item.title || ''
				if (!text) return
				this.sendText(text)
			},

			/* =========================================================
			 * 六、历史对话抽屉
			 * =======================================================*/

			openHistory() {
				this.historyVisible = true
			},

			closeHistory() {
				this.historyVisible = false
			},

			/** 查看对话详情 */
			openSession(item) {
				this.historyVisible = false
				uni.navigateTo({
					url: '/pages/ai/session?id=' + item.id + '&title=' + encodeURIComponent(item.title)
				})
			},

			/** 单条对话的更多操作：置顶 / 重命名 / 删除 */
			onConvMore(item) {
				uni.showActionSheet({
					itemList: [item.pinned ? '取消置顶' : '置顶该对话', '重命名', '删除'],
					success: res => {
						if (res.tapIndex === 0) {
							item.pinned = !item.pinned
							toast(item.pinned ? '已置顶' : '已取消置顶')
						} else if (res.tapIndex === 1) {
							this.renameConv(item)
						} else if (res.tapIndex === 2) {
							this.deleteConv(item)
						}
					}
				})
			},

			/** 重命名对话 */
			renameConv(item) {
				uni.showModal({
					title: '重命名对话',
					editable: true,
					placeholderText: '请输入新的对话标题',
					content: item.title,
					success: res => {
						const val = (res.content || '').trim()
						if (res.confirm && val) {
							item.title = val
							toast('已重命名')
						}
					}
				})
			},

			/**
			 * 删除对话：先调 DELETE /ai/sessions/{id}，成功后再从列表移除
			 * （此前只做本地 splice，刷新一次会话又回来了）
			 */
			async deleteConv(item) {
				const res = await new Promise(resolve => {
					uni.showModal({
						title: '删除对话',
						content: '删除后不可恢复，确定删除该对话吗？',
						success: resolve,
						fail: () => resolve({ confirm: false })
					})
				})
				if (!res.confirm) return
				try {
					await deleteSession(item.id)
				} catch (e) {
					// 删除失败：保留该行，错误提示已由请求层统一弹出
					return
				}
				const i = this.conversations.findIndex(c => c.id === item.id)
				if (i > -1) this.conversations.splice(i, 1)
				toast('已删除')
			},

			/** 抽屉底部：进入个人设置页 */
			goSettings() {
				this.historyVisible = false
				uni.navigateTo({ url: '/pages/mine/settings' })
			}
		}
	}
</script>

<style lang="scss" scoped>
	/* ==================== 页面骨架：100vh 纵向 flex ====================
	   顶部导航 + 底部输入区固定，中间对话区（scroll-view）占满剩余高度
	*/
	.ai {
		height: 100vh;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		background-color: $zn-bg-page;
	}

	.ai__tabbar {
		flex-shrink: 0;
	}

	/* ==================== 1. 顶部导航 ==================== */
	.ai__header {
		flex-shrink: 0;
		background: linear-gradient(135deg, #5ee27a 0%, #4cd964 55%, #2bb14c 100%);
		box-shadow: 0 4rpx 16rpx rgba(43, 177, 76, 0.18);
	}

	.ai__nav {
		height: 88rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		padding: 0 $zn-page-padding;
	}

	.ai__nav-btn {
		position: relative;
		width: 64rpx;
		height: 64rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.ai__nav-badge {
		position: absolute;
		right: 0rpx;
		top: 4rpx;
		min-width: 26rpx;
		height: 26rpx;
		padding: 0 5rpx;
		border-radius: 999rpx;
		background-color: rgba(255, 255, 255, 0.92);
		color: $zn-theme-dark;
		font-size: 17rpx;
		line-height: 26rpx;
		text-align: center;
	}

	.ai__nav-center {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
	}

	.ai__nav-title {
		font-size: 34rpx;
		font-weight: 700;
		color: #ffffff;
		letter-spacing: 1rpx;
	}

	.ai__nav-sub {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 2rpx;
	}

	.ai__nav-sub-text {
		font-size: 20rpx;
		color: rgba(255, 255, 255, 0.9);
		margin-right: 6rpx;
	}

	/* ==================== 2. 对话区 ==================== */
	.ai__chat {
		flex: 1;
		min-height: 0;
		background-color: $zn-bg-page;
	}

	/* ---------- 欢迎态 ---------- */
	.welcome {
		padding: 56rpx $zn-page-padding 40rpx;
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.welcome__logo {
		width: 132rpx;
		height: 132rpx;
		border-radius: 50%;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;
	}

	.welcome__greeting {
		font-size: 40rpx;
		font-weight: 700;
		color: $zn-text-title;
		text-align: center;
		line-height: 56rpx;
		margin-top: 28rpx;
	}

	.welcome__desc {
		font-size: 26rpx;
		color: $zn-text-grey;
		text-align: center;
		line-height: 38rpx;
		margin-top: 12rpx;
	}

	/* ---------- 4 个快捷能力卡（2×2 宫格） ---------- */
	.caps {
		width: 100%;
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		justify-content: space-between;
		margin-top: 40rpx;
	}

	.caps__item {
		width: 48.6%;
		background-color: #ffffff;
		border-radius: $zn-radius-lg;
		padding: 24rpx;
		margin-bottom: 20rpx;
		display: flex;
		flex-direction: column;
		box-shadow: $zn-shadow-sm;
	}

	.caps__icon {
		width: 76rpx;
		height: 76rpx;
		border-radius: 24rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.caps__title {
		font-size: 29rpx;
		font-weight: 600;
		color: $zn-text-title;
		margin-top: 18rpx;
	}

	.caps__desc {
		font-size: 22rpx;
		color: $zn-text-grey;
		margin-top: 8rpx;
	}

	/* ---------- 推荐问题 ---------- */
	.sugs {
		width: 100%;
		margin-top: 12rpx;
	}

	.sugs__label {
		font-size: 24rpx;
		color: $zn-text-grey;
		margin-bottom: 16rpx;
	}

	.sugs__item {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: #ffffff;
		border-radius: $zn-radius;
		padding: 22rpx 24rpx;
		margin-bottom: 16rpx;
		box-shadow: $zn-shadow-sm;
	}

	.sugs__icon {
		width: 62rpx;
		height: 62rpx;
		border-radius: 50%;
		background-color: $zn-theme-light;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.sugs__info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin: 0 16rpx;
	}

	.sugs__title {
		font-size: 28rpx;
		color: $zn-text-title;
		font-weight: 500;
	}

	.sugs__desc {
		font-size: 22rpx;
		color: $zn-text-light;
		margin-top: 6rpx;
	}

	/* ---------- 对话态 ---------- */
	.chat {
		padding: 28rpx $zn-page-padding 20rpx;
	}

	.chat__pad {
		height: 20rpx;
	}

	.msg {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		margin-bottom: 36rpx;
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

	/* ---------- 用户气泡里的附件图片 ---------- */
	.uimg {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		margin-bottom: 12rpx;
	}

	.uimg__item {
		width: 168rpx;
		height: 168rpx;
		border-radius: $zn-radius-sm;
		margin: 0 12rpx 12rpx 0;
		background-color: rgba(255, 255, 255, 0.25);
	}

	.bubble__cursor {
		font-size: 26rpx;
		color: $zn-theme;
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

	/* ---------- 联网搜索加载态 ---------- */
	.searching {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 6rpx 0;
	}

	.searching__icon {
		animation: ai-spin 1s linear infinite;
	}

	.searching__text {
		font-size: 26rpx;
		color: $zn-text-sub;
		margin-left: 12rpx;
	}

	@keyframes ai-spin {
		from {
			transform: rotate(0deg);
		}

		to {
			transform: rotate(360deg);
		}
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
	.md--h2 .md__seg {
		font-size: 34rpx;
		font-weight: 700;
		color: $zn-text-title;
		line-height: 50rpx;
	}

	.md--h3 {
		margin-top: 18rpx;
	}

	.md--h3 .md__text,
	.md--h3 .md__seg {
		font-size: 31rpx;
		font-weight: 700;
		color: $zn-text-title;
		line-height: 48rpx;
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

	/* ---------- 操作按钮 ---------- */
	.acts {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 16rpx;
	}

	.acts__btn {
		display: flex;
		flex-direction: row;
		align-items: center;
		height: 48rpx;
		padding: 0 20rpx;
		margin-right: 12rpx;
		background-color: #ffffff;
		border-radius: $zn-radius-pill;
		border: 1rpx solid $zn-line;
	}

	.acts__text {
		font-size: 22rpx;
		color: $zn-text-grey;
		margin-left: 8rpx;
	}

	/* ---------- 参考来源 ---------- */
	.refs {
		width: 100%;
		margin-top: 18rpx;
	}

	.refs__title {
		font-size: 22rpx;
		color: $zn-text-grey;
	}

	.refs__item {
		background-color: $zn-bg-grey;
		border-radius: $zn-radius-sm;
		padding: 16rpx 20rpx;
		margin-top: 12rpx;
		display: flex;
		flex-direction: column;
	}

	.refs__name {
		font-size: 25rpx;
		color: $zn-text-main;
		font-weight: 500;
	}

	.refs__source {
		font-size: 21rpx;
		color: $zn-text-grey;
		margin-top: 6rpx;
	}

	/* ==================== 3. 底部输入区 ==================== */
	/* 2026-09-22 紧凑化：顶部内边距由 20rpx 收到 12rpx */
	.ai__footer {
		flex-shrink: 0;
		background-color: #ffffff;
		border-top-left-radius: $zn-radius-xl;
		border-top-right-radius: $zn-radius-xl;
		padding: 8rpx $zn-page-padding 0;
		box-shadow: 0 -6rpx 24rpx rgba(20, 40, 30, 0.06);
	}

	/* ---------- 停止生成 ---------- */
	.stopbar {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		padding-bottom: 6rpx;
	}

	.stopbar__btn {
		display: flex;
		flex-direction: row;
		align-items: center;
		height: 48rpx;
		padding: 0 22rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-theme-light;
		border: 1rpx solid rgba(76, 217, 100, 0.4);
	}

	.stopbar__text {
		font-size: 22rpx;
		color: $zn-theme-dark;
		font-weight: 600;
		margin-left: 6rpx;
	}

	/* ---------- 已选图片 ---------- */
	.picked {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding-bottom: 8rpx;
	}

	.picked__item {
		position: relative;
		width: 100rpx;
		height: 100rpx;
		margin-right: 16rpx;
	}

	.picked__img {
		width: 120rpx;
		height: 120rpx;
		border-radius: $zn-radius-sm;
	}

	.picked__del {
		position: absolute;
		right: -8rpx;
		top: -8rpx;
		width: 34rpx;
		height: 34rpx;
		border-radius: 50%;
		background-color: rgba(0, 0, 0, 0.55);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	/* ---------- 上传中 / 上传失败的遮罩 ---------- */
	.picked__mask {
		position: absolute;
		left: 0;
		top: 0;
		width: 120rpx;
		height: 120rpx;
		border-radius: $zn-radius-sm;
		background-color: rgba(0, 0, 0, 0.45);
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
	}

	.picked__mask--fail {
		background-color: rgba(0, 0, 0, 0.6);
	}

	.picked__spin {
		animation: ai-spin 1s linear infinite;
	}

	.picked__mask-text {
		font-size: 20rpx;
		color: #ffffff;
		margin-top: 6rpx;
	}

	/* ---------- 纯文本模型的说明（不夸大图片的作用） ---------- */
	.picked__tip {
		display: block;
		font-size: 20rpx;
		color: $zn-text-light;
		padding-bottom: 6rpx;
	}

	/* ---------- 输入卡片 ---------- */
	/* 2026-09-22 紧凑化：内边距由 18/20/16 收到 12/16/10，减少纵向占用 */
	/* 2026-09-22 二次紧凑化：改 6/10/4 + 小圆角 + 细描边，输入卡片更扁更清爽 */
	.editor {
		background-color: $zn-bg-grey;
		border: 1rpx solid $zn-line;
		border-radius: $zn-radius;
		padding: 6rpx 10rpx 4rpx;
	}

	/* ⚠️ 上下 padding(8rpx) + line-height(40rpx) 必须与计算属性 inputHeight 的口径一致，
	   否则单行会偏上/偏下或末行被裁切（见 inputHeight 注释） */
	.editor__input {
		width: 100%;
		font-size: 28rpx;
		line-height: 40rpx;
		color: $zn-text-main;
		padding: 8rpx 4rpx;
	}

	.editor__input--fake {
		display: flex;
		align-items: center;
	}

	.editor__fake-text {
		font-size: 28rpx;
		color: $zn-text-light;
	}

	.editor__ph {
		font-size: 28rpx;
		color: $zn-text-light;
	}

	.editor__tools {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 2rpx;
	}

	/* ---------- 联网搜索 / 深度思考 开关 ---------- */
	.switch {
		display: flex;
		flex-direction: row;
		align-items: center;
		height: 40rpx;
		padding: 0 12rpx;
		margin-right: 8rpx;
		border-radius: $zn-radius-pill;
		background-color: #ffffff;
		border: 1rpx solid $zn-line;

		&.is-on {
			background-color: $zn-theme-light;
			border-color: rgba(76, 217, 100, 0.45);
		}
	}

	.switch__text {
		font-size: 20rpx;
		color: $zn-text-grey;
		margin-left: 5rpx;
	}

	.switch.is-on .switch__text {
		color: $zn-theme-dark;
		font-weight: 600;
	}

	.editor__flex {
		flex: 1;
		min-width: 0;
	}

	.editor__plus {
		width: 44rpx;
		height: 44rpx;
		border-radius: 50%;
		background-color: #ffffff;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-right: 8rpx;
	}

	.editor__send {
		width: 48rpx;
		height: 48rpx;
		border-radius: 50%;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;

		&.is-disabled {
			background: #dfe4e8;
			box-shadow: none;
		}
	}

	/* 提示文案：2026-09-22 由输入卡片下方移到上方，避免被 tabBar 中央凸起按钮遮挡；
	   同时字号由 20rpx 收到 18rpx、去掉底部留白，为对话区腾出约 24rpx 高度 */
	.ai__tip {
		display: block;
		text-align: center;
		font-size: 18rpx;
		color: $zn-text-light;
		padding: 0 0 2rpx;
	}

	/* ==================== 4. 历史对话抽屉（左侧滑出） ==================== */
	.drawer {
		position: fixed;
		left: 0;
		right: 0;
		top: 0;
		bottom: 0;
		z-index: 1000;
	}

	.drawer__mask {
		position: absolute;
		left: 0;
		right: 0;
		top: 0;
		bottom: 0;
		background-color: $zn-mask;
		animation: ai-fade 0.2s ease;
	}

	.drawer__panel {
		position: absolute;
		left: 0;
		top: 0;
		bottom: 0;
		width: 640rpx;
		background-color: #ffffff;
		border-top-right-radius: $zn-radius-xl;
		border-bottom-right-radius: $zn-radius-xl;
		display: flex;
		flex-direction: column;
		animation: ai-drawer-in 0.24s ease;
	}

	@keyframes ai-drawer-in {
		from {
			transform: translateX(-100%);
		}

		to {
			transform: translateX(0);
		}
	}

	@keyframes ai-fade {
		from {
			opacity: 0;
		}

		to {
			opacity: 1;
		}
	}

	.drawer__head {
		flex-shrink: 0;
		padding: 20rpx $zn-page-padding 16rpx;
	}

	.drawer__search {
		height: 72rpx;
		background-color: $zn-bg-grey;
		border-radius: $zn-radius-pill;
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 0 20rpx;
	}

	.drawer__input {
		flex: 1;
		min-width: 0;
		font-size: 26rpx;
		color: $zn-text-main;
		margin-left: 10rpx;
	}

	.drawer__ph {
		font-size: 26rpx;
		color: $zn-text-light;
	}

	.drawer__clear {
		width: 40rpx;
		height: 40rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.drawer__count {
		display: block;
		font-size: 21rpx;
		color: $zn-text-light;
		margin: 14rpx 4rpx 0;
	}

	.drawer__body {
		flex: 1;
		min-height: 0;
		padding: 0 $zn-page-padding;
	}

	.group {
		margin-bottom: 20rpx;
	}

	.group__title {
		display: block;
		font-size: 22rpx;
		color: $zn-text-grey;
		padding: 12rpx 4rpx;
	}

	.conv {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 20rpx 16rpx;
		border-radius: $zn-radius;
		margin-bottom: 8rpx;
		background-color: #ffffff;

		&.zn-hover {
			background-color: $zn-bg-grey;
		}
	}

	.conv__main {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
	}

	.conv__row {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.conv__title {
		font-size: 27rpx;
		color: $zn-text-title;
		font-weight: 500;
		margin-left: 6rpx;
	}

	.conv__meta {
		font-size: 21rpx;
		color: $zn-text-light;
		margin-top: 8rpx;
		margin-left: 6rpx;
	}

	.conv__more {
		width: 56rpx;
		height: 56rpx;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.drawer__empty {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 80rpx 0;
	}

	.drawer__empty-text {
		font-size: 24rpx;
		color: $zn-text-light;
		margin-top: 16rpx;
	}

	.drawer__pad {
		height: 24rpx;
	}

	.drawer__foot {
		flex-shrink: 0;
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 20rpx $zn-page-padding 20rpx;
		border-top: 1rpx solid $zn-line;
	}

	.drawer__foot-info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin-left: 18rpx;
	}

	.drawer__nickname {
		font-size: 29rpx;
		font-weight: 600;
		color: $zn-text-title;
	}

	.drawer__level {
		font-size: 21rpx;
		color: $zn-theme-dark;
		margin-top: 6rpx;
	}

	/* ==================== 5.「+」上传面板（底部弹出） ==================== */
	.sheet {
		position: fixed;
		left: 0;
		right: 0;
		top: 0;
		bottom: 0;
		z-index: 1000;
	}

	.sheet__mask {
		position: absolute;
		left: 0;
		right: 0;
		top: 0;
		bottom: 0;
		background-color: $zn-mask;
		animation: ai-fade 0.2s ease;
	}

	.sheet__panel {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		background-color: #ffffff;
		border-top-left-radius: $zn-radius-xl;
		border-top-right-radius: $zn-radius-xl;
		padding: 32rpx $zn-page-padding 24rpx;
		animation: ai-sheet-up 0.24s ease;
	}

	@keyframes ai-sheet-up {
		from {
			transform: translateY(100%);
		}

		to {
			transform: translateY(0);
		}
	}

	.sheet__title {
		display: block;
		font-size: 32rpx;
		font-weight: 700;
		color: $zn-text-title;
		text-align: center;
	}

	.sheet__desc {
		display: block;
		font-size: 22rpx;
		color: $zn-text-grey;
		text-align: center;
		margin-top: 8rpx;
	}

	.sheet__grid {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-around;
		margin-top: 32rpx;
	}

	.sheet__item {
		width: 30%;
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.sheet__icon {
		width: 108rpx;
		height: 108rpx;
		border-radius: 32rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.sheet__label {
		font-size: 24rpx;
		color: $zn-text-main;
		margin-top: 14rpx;
	}

	.sheet__cancel {
		height: 84rpx;
		margin-top: 32rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.sheet__cancel-text {
		font-size: 28rpx;
		color: $zn-text-sub;
		font-weight: 500;
	}
</style>
