<template>
	<view class="zn-page zn-page--no-tabbar">
		<!-- ==================== 顶部导航 ==================== -->
		<zn-nav-bar title="面试日程" show-back border />

		<!-- ==================== 三态 ==================== -->
		<zn-empty v-if="!isLogin" icon="person" text="登录后查看面试日程"
			desc="面试邀约与待办提醒都跟随账号" btn-text="去登录" @action="goLogin" />

		<view v-else-if="loading" class="state">
			<text class="state__text">正在加载面试日程…</text>
		</view>

		<view v-else-if="loadFailed" class="state state--fail" hover-class="zn-hover" @tap="refresh()">
			<uni-icons type="refresh" :size="18" color="#ff4d4f"></uni-icons>
			<text class="state__text state__text--fail">面试日程加载失败，点击重试</text>
		</view>

		<!-- 一条面试、一个待面试投递都没有：给整页空态，而不是「三个空区块 + 两行占位说明」 -->
		<zn-empty v-else-if="isEmpty" icon="calendar" text="暂无面试安排"
			desc="投递进入面试阶段后，面试邀约与时间安排会显示在这里" btn-text="去看看我的投递"
			@action="goApplications" />

		<!-- ==================== 内容（按行渲染：区块标题 / 提示 / 面试卡 / 投递行） ==================== -->
		<view v-else class="iv__body">
			<template v-for="row in rows" :key="row.key">
				<zn-section-header v-if="row.type === 'header'" :title="row.title" :subtitle="row.subtitle"
					:more="row.more" @more="onHeaderMore(row)" />

				<view v-else-if="row.type === 'note'" class="note" hover-class="zn-hover" @tap="onNote(row)">
					<text class="note__text" :class="{ 'is-action': row.action }">{{ row.text }}</text>
				</view>

				<!-- ---------- 面试卡片（即将面试 / 已过去的面试 / 展开的投递都复用同一段） ---------- -->
				<view v-else-if="row.type === 'iv'" class="iv">
					<view class="iv__head">
						<text class="iv__round zn-ellipsis">{{ row.iv.roundName || '面试' }}</text>
						<zn-tag :text="row.iv.statusText" :type="ivTagType(row.iv.status)" size="xs" />
					</view>
					<text v-if="row.iv.jobTitle" class="iv__job zn-ellipsis">
						{{ row.iv.jobTitle }}<text v-if="row.iv.companyName"> · {{ row.iv.companyName }}</text>
					</text>
					<view class="iv__meta">
						<uni-icons type="calendar" :size="15" color="#00a6a7"></uni-icons>
						<text class="iv__time">{{ row.iv.timeText }}</text>
						<text class="iv__dot">·</text>
						<text class="iv__mode">{{ row.iv.modeText }}</text>
						<text v-if="row.iv.durationMin" class="iv__dot">·</text>
						<text v-if="row.iv.durationMin" class="iv__mode">{{ row.iv.durationMin }} 分钟</text>
					</view>
					<!-- 现场面试给地址，视频面试给链接（服务端只会给其中一个，两个都为空就不显示这一行） -->
					<view v-if="row.iv.address" class="iv__line">
						<text class="iv__key">地点</text>
						<text class="iv__val">{{ row.iv.address }}</text>
					</view>
					<view v-if="row.iv.onlineLink" class="iv__line">
						<text class="iv__key">链接</text>
						<text class="iv__val zn-ellipsis">{{ row.iv.onlineLink }}</text>
						<view class="iv__copy" hover-class="zn-hover" @tap.stop="copyLink(row.iv.onlineLink)">
							<uni-icons type="pyq" :size="14" color="#008c8d"></uni-icons>
							<text class="iv__copy-text">复制链接</text>
						</view>
					</view>
					<view v-if="row.iv.interviewer" class="iv__line">
						<text class="iv__key">面试官</text>
						<text class="iv__val">{{ row.iv.interviewer }}</text>
					</view>
					<view v-if="row.iv.contact" class="iv__line">
						<text class="iv__key">联系方式</text>
						<text class="iv__val">{{ row.iv.contact }}</text>
					</view>
					<view v-if="row.iv.remark" class="iv__line">
						<text class="iv__key">备注</text>
						<text class="iv__val">{{ row.iv.remark }}</text>
					</view>
				</view>

				<!-- ---------- 待面试的投递（点开加载它的 interviews） ---------- -->
				<view v-else class="app">
					<view class="app__head" hover-class="zn-hover" @tap="toggleApp(row.app)">
						<zn-company-logo :text="logoText(row.app.companyName)" size="76"></zn-company-logo>
						<view class="app__info">
							<text class="app__title zn-ellipsis">{{ row.app.jobTitle }}</text>
							<text class="app__company zn-ellipsis">{{ row.app.companyName }}</text>
							<view class="app__meta">
								<zn-tag :text="row.app.statusText" :type="tagType(row.app.statusType)" size="xs" />
								<text class="app__time">{{ appMeta(row.app) }}</text>
							</view>
						</view>
						<view class="app__arrow" :class="{ 'is-open': expandedId === String(row.app.id) }">
							<uni-icons type="arrow-down" :size="16" color="#bbbbbb"></uni-icons>
						</view>
					</view>
				</view>
			</template>

			<view class="iv__foot">
				<text class="iv__foot-text">面试安排以 HR 的最新通知为准；临时调整请及时与面试官沟通</text>
			</view>
		</view>
	</view>
</template>

<script>
	/**
	 * 面试日程（求职者端）
	 *
	 * ⚠️ 数据来源：求职者端**没有**独立的「我的面试列表」接口（后端只提供了
	 *    /apply/stats、/apply/list、/apply/detail/{id} 三个含面试信息的接口），
	 *    所以本页用两个已有接口组合出完整日程，而不是新增接口或前端伪造数据：
	 *
	 *    1) getApplyStats().upcomingInterviews
	 *       → 「即将面试」的权威来源：服务端已按「未来 + 待确认/已确认」筛好并排好序（最多 5 场）。
	 *         局限：只给未来、最多 5 场，且 interview_out 里**没有职位名**（只有 jobId / applicationId）。
	 *
	 *    2) getMyApplications({status:'interview'})
	 *       → 拿到「进入面试阶段的投递」，用于：
	 *         a. 给上面那批面试补上职位名与公司名（按 jobId/applicationId 对上）；
	 *         b. 作为「待面试的投递」列表，用户点开某条时用它自己的 id 调 getApplicationDetail(id)
	 *            拿到那一份投递的全部 interviews（包含**已过去**的场次与备注/联系人等完整字段）。
	 *
	 *    3) getApplicationDetail(id)（按需）
	 *       → 展开某条投递时调用；进页面时会自动为最上面 MAX_DETAIL_APPS 条投递预取，
	 *         这样「已过去的面试」不用手点也有一部分内容。
	 *         限流的原因：投递条数无上限，全量预取会瞬间打出几十个请求；
	 *         超出部分在用户展开时按需请求（见 toggleApp），不静默丢失。
	 *
	 * ⚠️ 已知的信息缺口（不猜、不编）：
	 *    - 若某场面试所属投递的状态已经不是 interview（例如已 passed / 已 rejected），
	 *      它不会出现在 (2) 的列表里，因此拿不到职位名 —— 卡片上就只显示轮次与时间；
	 *    - 面试时间服务端可能为空（timeText 为「待定」），这类场次排在「即将面试」的末尾。
	 *
	 * ⚠️ 排序：未来的在前（按时间正序），「已过去的面试」折叠展示（按时间倒序，最近的在前）。
	 */
	import { isLogined } from '@/services/user.js'
	import { getApplyStats, getMyApplications, getApplicationDetail } from '@/services/apply.js'

	/** 进页面时自动预取详情的投递条数上限（限制请求并发；其余按需加载） */
	const MAX_DETAIL_APPS = 6

	/** 投递 statusType → zn-tag 配色（与「我的投递」页保持同一套映射） */
	const TAG_TYPE = {
		info: 'gray',
		warning: 'orange',
		success: 'green',
		danger: 'red'
	}

	/** 面试状态 → zn-tag 配色 */
	const IV_TAG_TYPE = {
		pending: 'orange',
		confirmed: 'green',
		finished: 'gray',
		canceled: 'red'
	}

	/** 未来的在前（时间正序），时间待定的排在最后 */
	function byTimeAsc(a, b) {
		if (!a._ms && !b._ms) return 0
		if (!a._ms) return 1
		if (!b._ms) return -1
		return a._ms - b._ms
	}

	/** 已过去的面试：最近的在前 */
	function byTimeDesc(a, b) {
		return b._ms - a._ms
	}

	export default {
		data() {
			return {
				isLogin: false,
				loading: true,
				loadFailed: false,
				// 两个接口的失败标记分开记：任一成功都还能给出部分信息，不整页报错
				upcomingFailed: false,
				appsFailed: false,
				statsUpcoming: [],
				apps: [],
				// 投递详情缓存：appId(字符串) → application（含 interviews）
				detailMap: {},
				detailLoading: {},
				detailFailed: {},
				expandedId: '',
				pastCollapsed: true
			}
		},
		computed: {
			/** 全部已获知的面试（详情里的 + stats 里的去重合并） */
			allInterviews() {
				const map = {}
				const push = (iv, app) => {
					if (!iv || iv.id === undefined || iv.id === null) return
					const key = String(iv.id)
					const item = this.decorateInterview(iv, app)
					const existing = map[key]
					// 同一场面试可能既在详情里又在 stats 里：保留信息更全的那份（有职位名/备注的优先）
					if (!existing || (!existing.jobTitle && item.jobTitle)) map[key] = item
				}

				Object.keys(this.detailMap).forEach(appId => {
					const app = this.detailMap[appId]
					if (!app) return
					const list = app.interviews || []
					list.forEach(iv => push(iv, app))
				})
				// stats 的「即将面试」可能属于状态已推进的投递（详情没预取到），这里补进来
				this.statsUpcoming.forEach(iv => push(iv, this.appById(iv.applicationId)))

				return Object.keys(map).map(key => map[key])
			},
			futureInterviews() {
				return this.allInterviews.filter(iv => !iv._past).sort(byTimeAsc)
			},
			pastInterviews() {
				return this.allInterviews.filter(iv => iv._past).sort(byTimeDesc)
			},
			futureSubtitle() {
				const list = this.futureInterviews
				if (!list.length) return ''
				return '共 ' + list.length + ' 场待办'
			},
			appsSubtitle() {
				return this.apps.length ? '进入面试阶段 ' + this.apps.length + ' 个职位' : ''
			},
			/** 整页空态：既没有已知面试，也没有待面试的投递，且两个接口都是成功的（失败走失败态） */
			isEmpty() {
				return !this.allInterviews.length && !this.apps.length &&
					!this.upcomingFailed && !this.appsFailed
			},
			/**
			 * 页面行模型：区块标题 / 提示 / 面试卡 / 投递行按顺序排成一行行，
			 * 这样三种列表能复用同一段面试卡模板（避免同一张卡片在页面里写三遍后各自漂移）。
			 */
			rows() {
				const rows = []
				const future = this.futureInterviews
				const past = this.pastInterviews

				// ---------- 1. 即将面试 ----------
				rows.push({
					type: 'header',
					key: 'h-future',
					title: '即将面试',
					subtitle: this.futureSubtitle,
					more: '',
					moreAction: ''
				})
				if (!future.length) {
					rows.push({
						type: 'note',
						key: 'n-future',
						text: this.upcomingFailed ? '待办面试加载失败，点击重试' : '暂时没有待办的面试安排',
						action: this.upcomingFailed ? 'reload' : ''
					})
				} else {
					future.forEach(iv => rows.push({ type: 'iv', key: 'f-' + iv.id, iv }))
				}

				// ---------- 2. 待面试的投递（点开加载详情） ----------
				rows.push({
					type: 'header',
					key: 'h-apps',
					title: '待面试的投递',
					subtitle: this.appsSubtitle,
					more: '',
					moreAction: ''
				})
				if (this.appsFailed) {
					rows.push({ type: 'note', key: 'n-apps', text: '待面试的投递加载失败，点击重试', action: 'reload' })
				} else if (!this.apps.length) {
					rows.push({ type: 'note', key: 'n-apps', text: '当前没有处于「待面试」状态的投递' })
				} else {
					this.apps.forEach(app => {
						rows.push({ type: 'app', key: 'a-' + app.id, app })
						const key = String(app.id)
						if (this.expandedId !== key) return
						if (this.detailLoading[key]) {
							rows.push({ type: 'note', key: 'al-' + key, text: '正在加载该投递的面试安排…' })
							return
						}
						if (this.detailFailed[key]) {
							rows.push({
								type: 'note',
								key: 'af-' + key,
								text: '面试安排加载失败，点击重试',
								action: 'detail',
								appId: app.id
							})
							return
						}
						const detail = this.detailMap[key]
						const list = (detail && detail.interviews) || []
						if (!list.length) {
							rows.push({ type: 'note', key: 'an-' + key, text: '这个投递还没有收到面试邀约' })
							return
						}
						list.forEach(iv => rows.push({
							type: 'iv',
							key: 'ai-' + key + '-' + iv.id,
							iv: this.decorateInterview(iv, detail)
						}))
					})
				}

				// ---------- 3. 已过去的面试（默认折叠） ----------
				if (past.length) {
					rows.push({
						type: 'header',
						key: 'h-past',
						title: '已过去的面试',
						subtitle: past.length + ' 场',
						more: this.pastCollapsed ? '展开' : '收起',
						moreAction: 'past'
					})
					if (!this.pastCollapsed) {
						past.forEach(iv => rows.push({ type: 'iv', key: 'p-' + iv.id, iv }))
					}
				}

				return rows
			}
		},
		onLoad() {
			this.refresh()
		},
		onShow() {
			// 从投递/职位页返回时重新拉：HR 可能刚发了新邀约
			if (this.isLogin) this.refresh()
		},
		onPullDownRefresh() {
			this.refresh(true)
		},
		methods: {
			/* ==========================================================
			 * 数据
			 * ========================================================== */
			async refresh(fromPull) {
				this.isLogin = isLogined()
				if (!this.isLogin) {
					this.loading = false
					this.loadFailed = false
					this.reset()
					if (fromPull) uni.stopPullDownRefresh()
					return
				}

				this.loading = true
				// 两个接口分别 catch：任一成功就还能展示一部分，两个都失败才算整页失败
				const [statsRes, appsRes] = await Promise.all([
					getApplyStats().then(data => ({ ok: true, data })).catch(() => ({ ok: false })),
					getMyApplications({ status: 'interview', page: 1, pageSize: 50 })
						.then(data => ({ ok: true, data })).catch(() => ({ ok: false }))
				])

				if (!statsRes.ok && !appsRes.ok) {
					this.reset()
					this.loading = false
					this.loadFailed = true
					if (fromPull) {
						uni.stopPullDownRefresh()
						uni.showToast({ title: '刷新失败', icon: 'none' })
					}
					return
				}

				this.loadFailed = false
				this.upcomingFailed = !statsRes.ok
				this.appsFailed = !appsRes.ok
				this.statsUpcoming = statsRes.ok ? ((statsRes.data && statsRes.data.upcomingInterviews) || []) : []
				this.apps = appsRes.ok ? ((appsRes.data && appsRes.data.list) || []) : []
				this.detailMap = {}
				this.detailLoading = {}
				this.detailFailed = {}
				this.expandedId = ''

				// 预取前若干条投递的详情：为了拿全每场的字段，以及「已过去的面试」
				const targets = this.apps.slice(0, MAX_DETAIL_APPS)
				await Promise.all(targets.map(app => this.loadDetail(app.id)))

				this.loading = false
				if (fromPull) {
					uni.stopPullDownRefresh()
					uni.showToast({ title: '已更新', icon: 'none' })
				}
			},

			reset() {
				this.statsUpcoming = []
				this.apps = []
				this.detailMap = {}
				this.detailLoading = {}
				this.detailFailed = {}
				this.expandedId = ''
				this.upcomingFailed = false
				this.appsFailed = false
			},

			/**
			 * 拉取某条投递的详情（含它的全部面试）
			 * ⚠️ 失败只影响这一条：标记 detailFailed[id]，列表里给出「点击重试」，
			 *    不让一条详情失败把整页拖成错误态。
			 */
			async loadDetail(id) {
				const key = String(id)
				if (this.detailLoading[key]) return
				this.patch('loading', key, true)
				try {
					const res = await getApplicationDetail(id)
					this.patch('detail', key, (res && res.application) || null)
					this.patch('failed', key, false)
				} catch (e) {
					this.patch('failed', key, true)
				} finally {
					this.patch('loading', key, false)
				}
			},

			/** 按投递 id 找到列表里的那条投递（找不到返回 null：例如它的状态已推进到面试之后） */
			appById(applicationId) {
				const key = String(applicationId === undefined || applicationId === null ? '' : applicationId)
				if (!key) return null
				const hit = this.apps.filter(app => String(app.id) === key)[0]
				return hit || null
			},

			/**
			 * 给对象型状态打补丁并整体替换
			 * 为什么不用 this.detailMap[key] = x：对象整体替换的响应式行为更明确，
			 * 也避免缓存对象被别处引用后「一处改、处处变」。name 用字符串指定，避免依赖引用比较。
			 */
			patch(name, key, value) {
				const map = {
					detail: this.detailMap,
					loading: this.detailLoading,
					failed: this.detailFailed
				}[name] || {}
				const next = Object.assign({}, map)
				next[key] = value
				if (name === 'detail') this.detailMap = next
				else if (name === 'loading') this.detailLoading = next
				else if (name === 'failed') this.detailFailed = next
			},

			/**
			 * 给面试补上本页需要的派生字段
			 * ⚠️ 只做「解析与关联」，不改写服务端给的任何文案（timeText / modeText / statusText 原样展示）
			 */
			decorateInterview(iv, app) {
				const ms = this.parseTime(iv.time)
				return Object.assign({}, iv, {
					_ms: ms,
					// 有明确时间且已过去 → 归入「已过去的面试」；时间待定的不算过去
					_past: ms > 0 && ms < Date.now(),
					jobTitle: (app && app.jobTitle) || '',
					companyName: (app && app.companyName) || '',
					applicationId: iv.applicationId || (app && app.id) || ''
				})
			},

			/**
			 * 解析服务端时间
			 * ⚠️ 服务端给的是 'YYYY-MM-DD HH:MM:SS'（空格分隔）：
			 *    iOS / Safari 不接受这种写法（new Date 会得到 Invalid Date），
			 *    换成 ISO 的 'T' 分隔才是各端都能解析的形式。
			 *    解析失败返回 0，页面按「时间待定」处理，不猜时间。
			 */
			parseTime(text) {
				const str = String(text || '').trim()
				if (!str) return 0
				const ms = new Date(str.replace(' ', 'T')).getTime()
				return isNaN(ms) ? 0 : ms
			},

			/* ==========================================================
			 * 交互
			 * ========================================================== */
			onHeaderMore(row) {
				if (row.moreAction === 'past') this.pastCollapsed = !this.pastCollapsed
			},

			onNote(row) {
				if (row.action === 'reload') {
					this.refresh()
					return
				}
				if (row.action === 'detail') this.loadDetail(row.appId)
			},

			/** 展开 / 收起某条投递：首次展开时才去拉它的面试列表 */
			toggleApp(app) {
				const key = String(app.id)
				if (this.expandedId === key) {
					this.expandedId = ''
					return
				}
				this.expandedId = key
				if (!this.detailMap[key] && !this.detailLoading[key]) this.loadDetail(app.id)
			},

			/** 视频面试链接：复制到剪贴板（各端 setClipboardData 自带「已复制」提示，这里不重复弹） */
			copyLink(link) {
				const data = String(link || '')
				if (!data) return
				uni.setClipboardData({
					data,
					fail: () => {
						// 复制失败时给出可执行的办法，而不是只说失败
						uni.showToast({ title: '复制失败，请长按链接手动复制', icon: 'none' })
					}
				})
			},

			/* ==========================================================
			 * 展示辅助
			 * ========================================================== */
			tagType(statusType) {
				return TAG_TYPE[statusType] || 'gray'
			},

			ivTagType(status) {
				return IV_TAG_TYPE[status] || 'gray'
			},

			logoText(companyName) {
				const str = String(companyName || '').trim()
				return str ? str.slice(0, 2) : '公'
			},

			/** 投递行右侧的一句话：已加载详情就报场次数，否则提示可点击 */
			appMeta(app) {
				const key = String(app.id)
				if (this.detailLoading[key]) return '加载中…'
				const detail = this.detailMap[key]
				if (detail) {
					const count = (detail.interviews || []).length
					return count ? count + ' 场面试安排' : '暂无面试邀约'
				}
				return '点击查看面试安排'
			},

			goApplications() {
				uni.navigateTo({ url: '/pages/seeker/applications' })
			},

			goLogin() {
				uni.navigateTo({ url: '/pages/login/login' })
			}
		}
	}
</script>

<style lang="scss" scoped>
	.iv__body {
		padding: 0 $zn-page-padding 40rpx;
	}

	.state {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		padding: 100rpx 0;
	}

	.state--fail {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 40rpx 24rpx;
		margin: 40rpx $zn-page-padding 0;
		box-shadow: $zn-shadow-sm;
	}

	.state__text {
		font-size: 26rpx;
		color: $zn-text-grey;
	}

	.state__text--fail {
		color: $zn-red;
		margin-left: 10rpx;
	}

	/* ==================== 提示行 ==================== */
	.note {
		background-color: $zn-bg-card;
		border-radius: $zn-radius;
		padding: 22rpx 24rpx;
		margin-bottom: 16rpx;
	}

	.note__text {
		font-size: 24rpx;
		color: $zn-text-light;

		&.is-action {
			color: $zn-theme-dark;
		}
	}

	/* ==================== 面试卡片 ==================== */
	.iv {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 24rpx;
		margin-bottom: 20rpx;
		box-shadow: $zn-shadow-sm;
	}

	.iv__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.iv__round {
		flex: 1;
		min-width: 0;
		font-size: 30rpx;
		font-weight: 600;
		color: $zn-text-title;
	}

	.iv__job {
		display: block;
		font-size: 24rpx;
		color: $zn-theme-dark;
		margin-top: 10rpx;
	}

	.iv__meta {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 12rpx;
	}

	.iv__time {
		font-size: 25rpx;
		color: $zn-text-main;
		margin-left: 8rpx;
	}

	.iv__dot {
		font-size: 22rpx;
		color: $zn-text-light;
		margin: 0 8rpx;
	}

	.iv__mode {
		font-size: 23rpx;
		color: $zn-text-sub;
	}

	.iv__line {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 12rpx;
	}

	.iv__key {
		flex-shrink: 0;
		width: 110rpx;
		font-size: 22rpx;
		color: $zn-text-grey;
	}

	.iv__val {
		flex: 1;
		min-width: 0;
		font-size: 23rpx;
		color: $zn-text-sub;
		line-height: 34rpx;
	}

	.iv__copy {
		flex-shrink: 0;
		display: flex;
		flex-direction: row;
		align-items: center;
		height: 52rpx;
		padding: 0 18rpx;
		margin-left: 12rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-theme-light;
	}

	.iv__copy-text {
		font-size: 22rpx;
		color: $zn-theme-dark;
		margin-left: 6rpx;
	}

	/* ==================== 待面试的投递 ==================== */
	.app {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 22rpx;
		margin-bottom: 20rpx;
		box-shadow: $zn-shadow-sm;
	}

	.app__head {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.app__info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin: 0 12rpx 0 20rpx;
	}

	.app__title {
		font-size: 29rpx;
		font-weight: 600;
		color: $zn-text-title;
	}

	.app__company {
		font-size: 23rpx;
		color: $zn-text-sub;
		margin-top: 8rpx;
	}

	.app__meta {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 12rpx;
	}

	.app__time {
		font-size: 21rpx;
		color: $zn-text-light;
		margin-left: 12rpx;
	}

	.app__arrow {
		flex-shrink: 0;
		width: 44rpx;
		height: 44rpx;
		display: flex;
		align-items: center;
		justify-content: center;
		transition: transform 0.2s ease;

		&.is-open {
			transform: rotate(180deg);
		}
	}

	/* ==================== 底部说明 ==================== */
	.iv__foot {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: $zn-gap-lg 0 10rpx;
	}

	.iv__foot-text {
		font-size: 21rpx;
		color: $zn-text-light;
		text-align: center;
		line-height: 32rpx;
	}
</style>
