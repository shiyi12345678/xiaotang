<template>
	<view class="zn-page zn-page--no-tabbar prac">
		<zn-nav-bar :title="navTitle" show-back border />

		<!-- ==================== 顶部：掌握进度 ==================== -->
		<view class="prac__prog">
			<view class="prac__prog-head">
				<text class="prac__prog-text">{{ progressText }}</text>
				<!-- 未登录：给一个明确的登录入口，但**不**打断当前刷题 -->
				<text v-if="!isLogin" class="prac__prog-link" @tap="goLogin">去登录</text>
				<text v-else-if="progressError" class="prac__prog-link" @tap="loadProgress">重试</text>
			</view>
			<view class="prac__prog-bar">
				<zn-progress :percent="localPercent" :height="10" />
			</view>
			<text class="prac__prog-sub">{{ localText }}</text>
		</view>

		<!-- ==================== 加载中 ==================== -->
		<view v-if="loading" class="prac__state">
			<uni-icons type="spinner-cycle" :size="22" color="#00a6a7"></uni-icons>
			<text class="prac__state-text">正在加载题目…</text>
		</view>

		<!-- ==================== 加载失败（可重试） ==================== -->
		<view v-else-if="loadError" class="prac__state prac__state--error" hover-class="zn-hover"
			@tap="loadQuestions">
			<uni-icons type="info-filled" :size="22" color="#ff4d4f"></uni-icons>
			<text class="prac__state-text">{{ loadError }}</text>
			<text class="prac__state-retry">点击重试</text>
		</view>

		<!-- ==================== 空数据 ==================== -->
		<zn-empty v-else-if="!questions.length" icon="list" text="这个方向还没有题目"
			desc="换个职能分类看看吧" btn-text="返回题库" @action="backToList" />

		<!-- ==================== 本轮小结 ==================== -->
		<view v-else-if="finished" class="sum">
			<view class="sum__card">
				<view class="sum__badge">
					<uni-icons type="medal-filled" :size="40" color="#ffffff"></uni-icons>
				</view>
				<text class="sum__title">{{ sumTitle }}</text>
				<text class="sum__sub">{{ navTitle }} · 本轮 {{ questions.length }} 题</text>

				<view class="sum__stats">
					<view class="sum__stat">
						<text class="sum__num sum__num--ok">{{ okCount }}</text>
						<text class="sum__label">答对</text>
					</view>
					<view class="sum__stat">
						<text class="sum__num sum__num--bad">{{ badCount }}</text>
						<text class="sum__label">答错</text>
					</view>
					<view class="sum__stat">
						<text class="sum__num">{{ skipCount }}</text>
						<text class="sum__label">未作答</text>
					</view>
					<view class="sum__stat">
						<text class="sum__num">{{ totalTimeText }}</text>
						<text class="sum__label">用时</text>
					</view>
				</view>

				<view class="sum__btns">
					<view class="sum__btn sum__btn--ghost" hover-class="zn-hover" @tap="goWrong">
						<text class="sum__btn-text sum__btn-text--ghost">去薄弱点复盘</text>
					</view>
					<view class="sum__btn sum__btn--main" hover-class="zn-hover" @tap="restart">
						<text class="sum__btn-text">再刷一遍</text>
					</view>
				</view>

				<view class="sum__back" hover-class="zn-hover" @tap="backToList">
					<text class="sum__back-text">返回题库首页</text>
				</view>

				<text class="sum__saved">{{ savedTip }}</text>
			</view>
		</view>

		<!-- ==================== 题目 ==================== -->
		<view v-else class="qcard">
			<!-- 题号进度 + 难度 + 来源 -->
			<view class="qcard__head">
				<text class="qcard__index">第 {{ index + 1 }} / {{ questions.length }} 题</text>
				<zn-tag :text="current.difficultyText || '基础'" :type="difficultyTag" size="sm" />
				<text v-if="current.source" class="qcard__source zn-ellipsis">{{ current.source }}</text>
			</view>

			<!-- 知识点标签 -->
			<view v-if="(current.tags || []).length" class="qcard__tags">
				<text v-for="tag in current.tags" :key="tag" class="qcard__tag">{{ tag }}</text>
			</view>

			<!-- 题干 -->
			<text class="qcard__stem">{{ current.question }}</text>

			<!-- 岗位（题库按职能分类，岗位是题目自带的一句话语境） -->
			<view v-if="current.position" class="qcard__pos">
				<uni-icons type="staff-filled" :size="14" color="#008c8d"></uni-icons>
				<text class="qcard__pos-text">适用岗位：{{ current.position }}</text>
			</view>

			<!-- 背诵模式的回忆提示 -->
			<text v-if="isMemory && !revealed" class="qcard__recall">
				先自己回忆一遍答题要点，再点下方「查看答案」对照
			</text>

			<!-- ---------- 答案区（按需拉详情） ---------- -->
			<view v-if="revealed" class="answer">
				<view class="answer__head">
					<uni-icons type="checkbox-filled" :size="18" color="#00a6a7"></uni-icons>
					<text class="answer__title">参考答案 / 答题要点</text>
				</view>
				<view v-if="answerLoading" class="answer__loading">
					<uni-icons type="spinner-cycle" :size="18" color="#00a6a7"></uni-icons>
					<text class="answer__loading-text">正在获取答案…</text>
				</view>
				<text v-else-if="answerError" class="answer__error" @tap="reveal">
					{{ answerError }}（点击重试）
				</text>
				<text v-else class="answer__text">{{ answerText }}</text>
			</view>

			<!-- 自评结果回显 -->
			<view v-if="answered" class="qcard__done" :class="isRight ? 'is-ok' : 'is-bad'">
				<uni-icons :type="isRight ? 'checkmarkempty' : 'closeempty'" :size="18"
					:color="isRight ? '#008c8d' : '#ff4d4f'"></uni-icons>
				<text class="qcard__done-text">
					{{ isRight ? '已记为「会了」' : '已记为「不会」，本题已进入薄弱点复盘' }}
				</text>
			</view>
		</view>

		<!-- ==================== 底部操作条 ==================== -->
		<view v-if="!loading && !loadError && questions.length && !finished" class="bar">
			<!-- 主操作：查看答案 → 会了/不会 → 下一题（练习模式自动跳，这里作为兜底） -->
			<view v-if="!revealed" class="bar__main" hover-class="zn-hover" @tap="reveal">
				<uni-icons type="eye" :size="18" color="#ffffff"></uni-icons>
				<text class="bar__main-text">查看答案</text>
			</view>

			<view v-else-if="!answered" class="bar__judge">
				<view class="bar__btn bar__btn--bad" hover-class="zn-hover" @tap="judge(0)">
					<uni-icons type="closeempty" :size="18" color="#ff4d4f"></uni-icons>
					<text class="bar__btn-text bar__btn-text--bad">不会</text>
				</view>
				<view class="bar__btn bar__btn--ok" hover-class="zn-hover" @tap="judge(1)">
					<uni-icons type="checkmarkempty" :size="18" color="#ffffff"></uni-icons>
					<text class="bar__btn-text">会了</text>
				</view>
			</view>

			<view v-else class="bar__main" hover-class="zn-hover" @tap="next">
				<text class="bar__main-text">{{ isLast ? '查看本轮小结' : '下一题' }}</text>
			</view>

			<!-- 手动切换（背诵模式的主要导航方式） -->
			<view class="bar__nav">
				<view class="bar__nav-btn" :class="{ 'is-disabled': index === 0 }" hover-class="zn-hover"
					@tap="prev">
					<uni-icons type="left" :size="15" color="#666666"></uni-icons>
					<text class="bar__nav-text">上一题</text>
				</view>
				<text class="bar__nav-count">{{ index + 1 }} / {{ questions.length }}</text>
				<view class="bar__nav-btn" hover-class="zn-hover" @tap="next">
					<text class="bar__nav-text">下一题</text>
					<uni-icons type="right" :size="15" color="#666666"></uni-icons>
				</view>
			</view>
		</view>

		<!-- 底部操作条占位（避免遮挡题干最后几行） -->
		<view v-if="!loading && !loadError && questions.length && !finished" class="bar__holder"></view>
	</view>
</template>

<script>
	/**
	 * 刷题 / 背诵
	 *
	 * onLoad 参数：
	 *   category  二级职能分类 id（如 cat-tech-backend），不传即全库顺序刷
	 *   mode      practice=顺序刷题（默认） / memory=背诵模式
	 *   id        可选：题库首页点某道热门题进来时，直接从该题开始
	 *
	 * 数据来源（services/interview.js）：
	 *   GET  /interview/questions?category=&pageSize=50   题目列表（**不含 answer**）
	 *   GET  /interview/questions/{id}                     题目详情（唯一返回 answer 的接口）
	 *   POST /interview/questions/{id}/record              记录「会了/不会」（🔒）
	 *   GET  /interview/progress                           掌握进度（🔒）
	 *
	 * ⚠️ 为什么答案要按题拉详情：
	 *    列表接口刻意不返回 answer（一次 50 题全带答案会让响应体大几倍），
	 *    而刷题是「一题一题看」的交互 —— 按需拉详情正好只付当前这一题的代价。
	 *    详情返回的是 {question: {...}} 一层包装（与 /job/detail 的 {job,...} 同风格），
	 *    因此取值必须写 res.question.answer，不能直接取 res.answer。
	 *
	 * ⚠️ 未登录时不提交作答记录：
	 *    recordQuestion 需要登录，401 会被 services/api.js 统一 toast 并清本地登录态。
	 *    所以在页面上先拦一道：弹确认框引导登录，**保留本题进度**（答案仍展开、不跳下一题），
	 *    避免用户点了「会了」结果白答一题、还得重刷。
	 *
	 * ⚠️ 背诵模式（memory）与顺序刷题的唯一差别：
	 *    背诵是自定节奏的回忆训练，自评后**不自动跳题**（留给用户对照答案的时间）；
	 *    顺序刷题则是看完答案自评即自动进入下一题（省一次点击）。
	 *    两种模式都默认不显示答案，先给题干。
	 */
	import { getQuestions, getQuestionDetail, recordQuestion, getPracticeProgress } from '@/services/interview.js'
	import { isLogined } from '@/services/user.js'
	import { padZero, safeDecode } from '@/common/utils/format.js'

	/** 一次拉取的题量上限：接口 pageSize 最大 50，一个分类的题量基本都在这之内 */
	const PAGE_SIZE = 50

	/** 练习模式自评后自动跳下一题的延迟（毫秒）：留一点时间让用户看到「已记录」反馈 */
	const AUTO_NEXT_DELAY = 600

	export default {
		data() {
			return {
				category: '',
				mode: 'practice',
				startQuestionId: '', // 入口指定的起始题目 id（题库首页点某道热门题进来时用）
				// ---------- 题目 ----------
				questions: [],
				index: 0,
				loading: false,
				loadError: '',
				// ---------- 逐题状态（按题目 id 存，来回切题不丢） ----------
				revealedMap: {}, // 已展开答案的题目 id
				answerMap: {}, // 题目 id → 参考答案（详情接口的缓存）
				resultMap: {}, // 题目 id → 1 会了 / 0 不会
				answerLoading: false,
				answerError: '',
				// ---------- 计时 ----------
				sessionStart: 0, // 本轮开始时间戳
				questionStart: 0, // 当前题进入时间戳（算 durationSec）
				elapsed: 0, // 本轮已用时（秒），每 5 秒刷新一次用于展示与小结
				timer: null,
				nextTimer: null,
				// ---------- 进度 ----------
				isLogin: false,
				progress: null,
				progressError: '',
				// ---------- 流程 ----------
				finished: false
			}
		},
		computed: {
			current() {
				return this.questions[this.index] || {}
			},
			navTitle() {
				return this.mode === 'memory' ? '背诵模式' : '刷题'
			},
			isMemory() {
				return this.mode === 'memory'
			},
			revealed() {
				return !!this.revealedMap[this.current.id]
			},
			answerText() {
				return this.answerMap[this.current.id] || ''
			},
			answered() {
				return this.resultMap[this.current.id] !== undefined
			},
			isRight() {
				return this.resultMap[this.current.id] === 1
			},
			isLast() {
				return this.index >= this.questions.length - 1
			},
			/** 难度标签配色：基础绿 / 进阶橙 / 困难红 */
			difficultyTag() {
				const d = Number(this.current.difficulty) || 1
				if (d >= 3) return 'red'
				return d === 2 ? 'orange' : 'green'
			},
			/* ---------------- 本轮统计 ---------------- */
			okCount() {
				return this.questions.filter(q => this.resultMap[q.id] === 1).length
			},
			badCount() {
				return this.questions.filter(q => this.resultMap[q.id] === 0).length
			},
			answeredCount() {
				return this.okCount + this.badCount
			},
			skipCount() {
				return this.questions.length - this.answeredCount
			},
			localPercent() {
				if (!this.questions.length) return 0
				return Math.round((this.answeredCount / this.questions.length) * 100)
			},
			localText() {
				return '本轮已答 ' + this.answeredCount + ' / ' + this.questions.length + ' 题'
			},
			/** 顶部进度文案：登录后展示服务端的全局进度，未登录只说明「不保存」 */
			progressText() {
				if (!this.isLogin) return '登录后可记录刷题进度'
				if (this.progressError) return '掌握进度加载失败'
				if (!this.progress) return '掌握进度加载中…'
				return '已刷 ' + this.progress.answered + ' / 共 ' + this.progress.total +
					' 题 · 掌握率 ' + this.progress.accuracy + '%'
			},
			totalTimeText() {
				const m = Math.floor(this.elapsed / 60)
				const s = this.elapsed % 60
				return padZero(m) + ':' + padZero(s)
			},
			sumTitle() {
				const rate = this.answeredCount ? Math.round((this.okCount / this.answeredCount) * 100) : 0
				if (rate >= 90) return '这一轮表现很好'
				if (rate >= 60) return '还不错，薄弱点再复盘一遍'
				return '答对率偏低，建议去薄弱点复盘'
			},
			savedTip() {
				if (!this.isLogin) return '本次作答未记录：登录后刷题记录与薄弱点才会保存到账号'
				if (!this.badCount) return '本轮作答已记录到你的账号，没有新增薄弱点'
				return '本轮作答已记录；答错的 ' + this.badCount + ' 道题已进入薄弱点复盘'
			}
		},
		onLoad(options) {
			const opt = options || {}
			this.category = opt.category ? safeDecode(opt.category) : ''
			// 只有 memory 走背诵模式，其余（含未传 / review）一律按顺序刷题处理
			this.mode = opt.mode === 'memory' ? 'memory' : 'practice'
			this.startQuestionId = opt.id ? safeDecode(opt.id) : ''
			this.isLogin = isLogined()
			this.startTimer()
			this.loadAll()
		},
		onUnload() {
			if (this.timer) clearInterval(this.timer)
			if (this.nextTimer) clearTimeout(this.nextTimer)
		},
		onShow() {
			// 未登录时点「会了/不会」会引导去登录，登录后返回本页要刷新登录态与全局进度，
			// 否则顶栏会一直停在「登录后可记录刷题进度」。
			const logined = isLogined()
			const changed = this.isLogin !== logined
			this.isLogin = logined
			if (changed && logined) this.loadProgress()
		},
		methods: {
			/* ================= 加载 ================= */
			async loadAll() {
				await Promise.all([this.loadQuestions(), this.loadProgress()])
			},
			/** 题目列表：不含答案，答案在 reveal() 里按题拉详情 */
			async loadQuestions() {
				this.loading = true
				this.loadError = ''
				try {
					const res = await getQuestions({ category: this.category, pageSize: PAGE_SIZE })
					this.questions = res.list || []
					this.index = 0
					this.finished = false
					// 从题库首页点某道热门题进来：定位到该题（找不到就从头开始，不算错误）
					if (this.startQuestionId) {
						const i = this.questions.findIndex(q => q.id === this.startQuestionId)
						if (i > -1) this.index = i
					}
					this.questionStart = Date.now()
				} catch (e) {
					this.questions = []
					this.loadError = e.message || '题目加载失败'
				} finally {
					this.loading = false
				}
			},
			async loadProgress() {
				this.isLogin = isLogined()
				if (!this.isLogin) {
					this.progress = null
					this.progressError = ''
					return
				}
				this.progressError = ''
				try {
					this.progress = await getPracticeProgress()
				} catch (e) {
					this.progress = null
					this.progressError = e.message || '进度加载失败'
				}
			},
			/* ================= 答案 ================= */
			/**
			 * 展开答案：首次展开时才请求详情并缓存，同一题来回切换不再重复请求
			 * 拉取失败时把错误文案留在答案区，点一下即可重试（不静默吞掉）
			 */
			async reveal() {
				const q = this.current
				if (!q.id) return
				if (this.answerMap[q.id] !== undefined) {
					// 已有缓存：直接展开，不再打一次网络请求
					this.revealedMap[q.id] = true
					return
				}
				this.revealedMap[q.id] = true
				this.answerLoading = true
				this.answerError = ''
				try {
					const res = await getQuestionDetail(q.id)
					// ⚠️ 详情接口返回 {question: {...}} 包装层，答案在 res.question.answer
					const detail = (res && res.question) || {}
					this.answerMap[q.id] = detail.answer || '该题暂未录入参考答案'
				} catch (e) {
					this.answerError = e.message || '答案加载失败'
				} finally {
					this.answerLoading = false
				}
			},
			/* ================= 自评 ================= */
			/**
			 * 提交作答结果
			 * @param {number} result 1=会了 / 0=不会（不会的题会进薄弱点）
			 */
			async judge(result) {
				const q = this.current
				if (!q.id || this.resultMap[q.id] !== undefined) return

				// 未登录：先拦下并引导登录，保留本题进度（答案保持展开、不跳题）
				if (!isLogined()) {
					uni.showModal({
						title: '登录后记录刷题进度',
						content: '刷题记录与薄弱点复盘需要登录后同步到账号，本次作答不会保存。',
						confirmText: '去登录',
						cancelText: '继续刷题',
						confirmColor: '#00a6a7',
						success: res => {
							if (res.confirm) this.goLogin()
						}
					})
					return
				}

				const durationSec = Math.max(1, Math.round((Date.now() - this.questionStart) / 1000))
				try {
					await recordQuestion(q.id, { result, mode: this.mode, durationSec })
				} catch (e) {
					// 失败提示由请求层统一弹出；这里不改本地状态，用户可再点一次
					return
				}
				this.resultMap[q.id] = result
				uni.showToast({ title: result === 1 ? '已记为会了' : '已记为不会', icon: 'none', duration: 900 })

				// 顺序刷题：自评后自动进入下一题；背诵模式：停在原地对照答案
				if (!this.isMemory) {
					if (this.nextTimer) clearTimeout(this.nextTimer)
					this.nextTimer = setTimeout(() => {
						this.nextTimer = null
						this.next()
					}, AUTO_NEXT_DELAY)
				}
			},
			/* ================= 切题 ================= */
			prev() {
				if (this.index === 0) {
					uni.showToast({ title: '已经是第一题', icon: 'none' })
					return
				}
				this.goto(this.index - 1)
			},
			next() {
				if (this.nextTimer) {
					clearTimeout(this.nextTimer)
					this.nextTimer = null
				}
				if (this.isLast) {
					this.finish()
					return
				}
				this.goto(this.index + 1)
			},
			goto(i) {
				this.index = i
				// 换题后重置计时基准：durationSec 是「本题耗时」而不是累计耗时
				this.questionStart = Date.now()
				this.answerError = ''
				uni.pageScrollTo({ scrollTop: 0, duration: 200 })
			},
			finish() {
				this.finished = true
				this.stopTimer()
				// 小结里的「本轮用时」用真实总时长，而不是那个 5 秒跳一次的展示值
				this.elapsed = Math.max(1, Math.round((Date.now() - this.sessionStart) / 1000))
				// 本轮作答已入库，刷新一次全局掌握进度
				this.loadProgress()
				uni.pageScrollTo({ scrollTop: 0, duration: 200 })
			},
			/* ================= 计时 ================= */
			startTimer() {
				this.sessionStart = Date.now()
				this.questionStart = Date.now()
				this.elapsed = 0
				if (this.timer) clearInterval(this.timer)
				// 5 秒一跳：只用于界面上「用时」的展示，不需要秒级精度，避免频繁 setData
				this.timer = setInterval(() => {
					this.elapsed = Math.round((Date.now() - this.sessionStart) / 1000)
				}, 5000)
			},
			stopTimer() {
				if (this.timer) {
					clearInterval(this.timer)
					this.timer = null
				}
			},
			/* ================= 跳转 ================= */
			goLogin() {
				uni.navigateTo({
					url: '/pages/login/login',
					fail: () => uni.showToast({ title: '登录页打开失败，请稍后重试', icon: 'none' })
				})
			},
			goWrong() {
				uni.navigateTo({ url: '/pages/bank/wrong' })
			},
			backToList() {
				// 从题库首页点进来时直接返回上一页；没有上一页（如被 reLaunch 进来）才新开页面，
				// 避免在同一栈里叠出第二个题库首页
				const pages = getCurrentPages()
				if (pages.length > 1) {
					uni.navigateBack({ delta: 1 })
					return
				}
				uni.reLaunch({
					url: '/pages/bank/list',
					fail: () => uni.showToast({ title: '题库页打开失败', icon: 'none' })
				})
			},
			/** 再刷一遍：清空逐题状态并重新拉题（重新拉是为了拿到题库的最新数据） */
			restart() {
				this.revealedMap = {}
				this.answerMap = {}
				this.resultMap = {}
				this.finished = false
				this.startQuestionId = ''
				this.startTimer()
				this.loadQuestions()
			}
		}
	}
</script>

<style lang="scss" scoped>
	.prac {
		padding-bottom: 40rpx;
	}

	/* ==================== 顶部进度 ==================== */
	.prac__prog {
		background-color: $zn-bg-card;
		padding: 22rpx $zn-page-padding 20rpx;
		border-bottom: 1rpx solid $zn-line;
	}

	.prac__prog-head {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.prac__prog-text {
		font-size: 24rpx;
		font-weight: 600;
		color: $zn-text-title;
	}

	.prac__prog-link {
		font-size: 24rpx;
		color: $zn-theme-deep;
	}

	.prac__prog-bar {
		margin-top: 14rpx;
	}

	.prac__prog-sub {
		display: block;
		font-size: 21rpx;
		color: $zn-text-grey;
		margin-top: 10rpx;
	}

	/* ==================== 状态块 ==================== */
	.prac__state {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 60rpx 24rpx;
		margin: $zn-gap $zn-page-padding 0;
	}

	.prac__state--error {
		border: 2rpx solid #ffe0e0;
	}

	.prac__state-text {
		font-size: 24rpx;
		color: $zn-text-sub;
		margin-left: 12rpx;
	}

	.prac__state-retry {
		font-size: 24rpx;
		color: $zn-theme-deep;
		margin-left: 16rpx;
	}

	/* ==================== 题干卡片 ==================== */
	.qcard {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: 28rpx 24rpx;
		margin: $zn-gap $zn-page-padding 0;
	}

	.qcard__head {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.qcard__index {
		font-size: 26rpx;
		font-weight: 700;
		color: $zn-theme-deep;
		flex-shrink: 0;
		margin-right: 14rpx;
	}

	.qcard__source {
		flex: 1;
		min-width: 0;
		text-align: right;
		font-size: 21rpx;
		color: $zn-text-light;
		margin-left: 14rpx;
	}

	.qcard__tags {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		margin-top: 16rpx;
	}

	.qcard__tag {
		font-size: 20rpx;
		color: $zn-theme-dark;
		background-color: $zn-theme-light;
		border-radius: 6rpx;
		padding: 4rpx 12rpx;
		margin: 0 12rpx 10rpx 0;
	}

	.qcard__stem {
		display: block;
		font-size: 34rpx;
		font-weight: 600;
		color: $zn-text-title;
		line-height: 54rpx;
		margin-top: 14rpx;
	}

	.qcard__pos {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 18rpx;
	}

	.qcard__pos-text {
		font-size: 21rpx;
		color: $zn-theme-dark;
		margin-left: 8rpx;
	}

	.qcard__recall {
		display: block;
		font-size: 22rpx;
		color: $zn-orange;
		line-height: 36rpx;
		margin-top: 20rpx;
	}

	.qcard__done {
		display: flex;
		flex-direction: row;
		align-items: center;
		border-radius: $zn-radius-sm;
		padding: 14rpx 18rpx;
		margin-top: 22rpx;

		&.is-ok {
			background-color: $zn-theme-light;
		}

		&.is-bad {
			background-color: #fff0f0;
		}
	}

	.qcard__done-text {
		font-size: 22rpx;
		color: $zn-text-sub;
		margin-left: 10rpx;
	}

	/* ==================== 答案区 ==================== */
	.answer {
		margin-top: 26rpx;
		padding-top: 24rpx;
		border-top: 1rpx solid $zn-line;
	}

	.answer__head {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.answer__title {
		font-size: 26rpx;
		font-weight: 600;
		color: $zn-text-title;
		margin-left: 8rpx;
	}

	.answer__loading {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 16rpx;
	}

	.answer__loading-text {
		font-size: 23rpx;
		color: $zn-text-grey;
		margin-left: 10rpx;
	}

	.answer__error {
		display: block;
		font-size: 23rpx;
		color: $zn-red;
		margin-top: 16rpx;
	}

	.answer__text {
		display: block;
		font-size: 27rpx;
		color: $zn-text-main;
		line-height: 48rpx;
		margin-top: 16rpx;
		white-space: pre-wrap;
	}

	/* ==================== 底部操作条 ==================== */
	.bar {
		position: fixed;
		left: 0;
		right: 0;
		bottom: 0;
		z-index: 985;
		background-color: $zn-bg-card;
		border-top: 1rpx solid $zn-line;
		padding: 18rpx $zn-page-padding calc(18rpx + env(safe-area-inset-bottom));
	}

	.bar__holder {
		height: 200rpx;
	}

	.bar__main {
		height: 84rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;
	}

	.bar__main-text {
		font-size: 30rpx;
		font-weight: 600;
		color: #ffffff;
		margin-left: 8rpx;
	}

	.bar__judge {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.bar__btn {
		flex: 1;
		height: 84rpx;
		border-radius: $zn-radius-pill;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;

		&--bad {
			background-color: #fff0f0;
			border: 2rpx solid #ffd9d9;
			margin-right: 20rpx;
		}

		&--ok {
			background: $zn-gradient;
			box-shadow: $zn-shadow-theme;
		}
	}

	.bar__btn-text {
		font-size: 30rpx;
		font-weight: 600;
		color: #ffffff;
		margin-left: 8rpx;

		&--bad {
			color: $zn-red;
		}
	}

	.bar__nav {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		margin-top: 14rpx;
	}

	.bar__nav-btn {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 8rpx 16rpx;

		&.is-disabled {
			opacity: 0.4;
		}
	}

	.bar__nav-text {
		font-size: 24rpx;
		color: $zn-text-sub;
		margin: 0 4rpx;
	}

	.bar__nav-count {
		font-size: 22rpx;
		color: $zn-text-grey;
	}

	/* ==================== 小结 ==================== */
	.sum {
		padding: 60rpx $zn-page-padding 0;
	}

	.sum__card {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-xl;
		box-shadow: $zn-shadow;
		padding: 48rpx 32rpx 40rpx;
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.sum__badge {
		width: 120rpx;
		height: 120rpx;
		border-radius: 50%;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;
	}

	.sum__title {
		font-size: 36rpx;
		font-weight: 700;
		color: $zn-text-title;
		margin-top: 26rpx;
	}

	.sum__sub {
		font-size: 24rpx;
		color: $zn-text-grey;
		margin-top: 12rpx;
	}

	.sum__stats {
		display: flex;
		flex-direction: row;
		width: 100%;
		margin-top: 36rpx;
		padding: 24rpx 0;
		border-top: 1rpx solid $zn-line;
		border-bottom: 1rpx solid $zn-line;
	}

	.sum__stat {
		flex: 1;
		display: flex;
		flex-direction: column;
		align-items: center;
	}

	.sum__num {
		font-size: 36rpx;
		font-weight: 700;
		color: $zn-text-title;

		&--ok {
			color: $zn-theme-deep;
		}

		&--bad {
			color: $zn-red;
		}
	}

	.sum__label {
		font-size: 21rpx;
		color: $zn-text-grey;
		margin-top: 8rpx;
	}

	.sum__btns {
		display: flex;
		flex-direction: row;
		width: 100%;
		margin-top: 36rpx;
	}

	.sum__btn {
		flex: 1;
		height: 84rpx;
		border-radius: $zn-radius-pill;
		display: flex;
		align-items: center;
		justify-content: center;

		&--ghost {
			background-color: $zn-bg-grey;
			margin-right: 20rpx;
		}

		&--main {
			background: $zn-gradient;
			box-shadow: $zn-shadow-theme;
		}
	}

	.sum__btn-text {
		font-size: 28rpx;
		font-weight: 600;
		color: #ffffff;

		&--ghost {
			color: $zn-text-sub;
		}
	}

	.sum__back {
		margin-top: 26rpx;
		padding: 10rpx 20rpx;
	}

	.sum__back-text {
		font-size: 24rpx;
		color: $zn-text-grey;
	}

	.sum__saved {
		display: block;
		font-size: 21rpx;
		color: $zn-text-light;
		text-align: center;
		line-height: 34rpx;
		margin-top: 14rpx;
	}
</style>
