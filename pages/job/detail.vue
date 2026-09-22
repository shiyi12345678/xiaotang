<template>
	<view class="zn-page zn-page--no-tabbar jdetail">
		<zn-nav-bar title="职位详情" show-back border />

		<!-- ==================== 三态 ==================== -->
		<view v-if="loading" class="state">
			<text class="state__text">正在加载职位详情…</text>
		</view>

		<view v-else-if="loadFailed" class="state state--col">
			<view class="state__row" hover-class="zn-hover" @tap="loadDetail">
				<uni-icons type="refresh" :size="18" color="#00a6a7"></uni-icons>
				<text class="state__text">{{ failText }}</text>
			</view>
			<view class="state__btn" hover-class="zn-hover" @tap="goList">
				<text class="state__btn-text">去看看其它职位</text>
			</view>
		</view>

		<template v-else-if="job">
			<!-- 已关闭提示：职位下架后详情仍可看，但必须明确告知不能投递 -->
			<view v-if="!isOpen" class="closed">
				<uni-icons type="info-filled" :size="16" color="#ff4d4f"></uni-icons>
				<text class="closed__text">该职位{{ job.statusText || '已关闭' }}，暂无法投递；下方相似职位可以继续看看</text>
			</view>

			<!-- ==================== 职位头部 ==================== -->
			<view class="hero">
				<view class="hero__title-row">
					<text v-if="kindText" class="hero__kind" :class="'is-' + job.kind">{{ kindText }}</text>
					<text class="hero__title">{{ job.title }}</text>
				</view>
				<view class="hero__salary-row">
					<text class="hero__salary">{{ job.salaryText }}</text>
					<text v-if="job.referralBonus" class="hero__bonus">内推奖金 {{ job.referralBonus }}</text>
				</view>
				<view class="hero__metas">
					<text class="hero__meta">{{ job.experience }}</text>
					<text class="hero__dot">·</text>
					<text class="hero__meta">{{ job.education }}</text>
					<text class="hero__dot">·</text>
					<text class="hero__meta">{{ job.jobTypeText }}</text>
				</view>
				<view class="hero__metas">
					<text class="hero__meta">{{ job.location }}</text>
					<text v-if="job.isRemote" class="hero__dot">·</text>
					<text v-if="job.isRemote" class="hero__meta">支持远程</text>
				</view>
				<view v-if="job.tags && job.tags.length" class="hero__tags">
					<text v-for="(tag, i) in job.tags" :key="'tag' + i" class="hero__tag">{{ tag }}</text>
				</view>
				<view class="hero__foot">
					<text class="hero__foot-item">{{ job.publishText }}发布</text>
					<text class="hero__foot-item">浏览 {{ job.viewCount || 0 }}</text>
					<text class="hero__foot-item">已投递 {{ job.applicantCount || 0 }} 人</text>
				</view>
			</view>

			<!-- ==================== 招聘者 ==================== -->
			<view class="hr">
				<zn-company-logo :text="job.logoText" :color="job.logoColor" :size="88"></zn-company-logo>
				<view class="hr__info">
					<text v-if="job.hrName" class="hr__name">{{ job.hrName }}</text>
					<text class="hr__company zn-ellipsis">{{ job.companyName || job.companyFullName }}</text>
					<text class="hr__meta zn-ellipsis">{{ hrMeta }}</text>
				</view>
				<view class="hr__btn" hover-class="zn-hover" @tap="onChat">
					<uni-icons type="chat" :size="16" color="#ffffff"></uni-icons>
					<text class="hr__btn-text">{{ chatting ? '连接中…' : '立即沟通' }}</text>
				</view>
			</view>

			<!-- ==================== 三个 Tab ==================== -->
			<view class="tabs">
				<view v-for="(t, i) in tabs" :key="t" class="tabs__item" hover-class="zn-hover" @tap="tab = i">
					<text class="tabs__text" :class="{ 'is-active': tab === i }">{{ t }}</text>
					<view v-if="tab === i" class="tabs__bar"></view>
				</view>
			</view>

			<!-- ---------- Tab 1：职位描述 ---------- -->
			<view v-if="tab === 0" class="card">
				<template v-if="description.length || requirements.length || process.length">
					<view v-if="description.length" class="sec">
						<view class="sec__head">
							<view class="sec__bar"></view>
							<text class="sec__title">职位描述</text>
						</view>
						<view v-for="(line, i) in description" :key="'d' + i" class="bullet">
							<view class="bullet__dot"></view>
							<text class="bullet__text">{{ line }}</text>
						</view>
					</view>
					<!-- requirements 与 description 都是服务端切好的条目数组，同属「职位描述」语义，放在同一个 Tab 下 -->
					<view v-if="requirements.length" class="sec">
						<view class="sec__head">
							<view class="sec__bar"></view>
							<text class="sec__title">任职要求</text>
						</view>
						<view v-for="(line, i) in requirements" :key="'r' + i" class="bullet">
							<view class="bullet__dot"></view>
							<text class="bullet__text">{{ line }}</text>
						</view>
					</view>
					<view v-if="process.length" class="sec">
						<view class="sec__head">
							<view class="sec__bar"></view>
							<text class="sec__title">招聘流程</text>
						</view>
						<view class="steps">
							<view v-for="(step, i) in process" :key="'p' + i" class="steps__item">
								<view class="steps__no">{{ i + 1 }}</view>
								<text class="steps__text">{{ step }}</text>
								<uni-icons v-if="i < process.length - 1" type="right" :size="14" color="#cccccc"></uni-icons>
							</view>
						</view>
					</view>
				</template>
				<zn-empty v-else text="该职位暂未提供详细描述" desc="可以直接点「立即沟通」向招聘者了解" />
			</view>

			<!-- ---------- Tab 2：公司信息 ---------- -->
			<view v-else-if="tab === 1" class="card">
				<view class="coy">
					<zn-company-logo :text="company.logoText || job.logoText" :color="company.logoColor || job.logoColor"
						:size="104"></zn-company-logo>
					<view class="coy__info">
						<text class="coy__name">{{ company.name || job.companyFullName || job.companyName }}</text>
						<text class="coy__desc zn-ellipsis">{{ coyDesc }}</text>
					</view>
				</view>

				<view v-if="introParagraphs.length" class="sec">
					<view class="sec__head">
						<view class="sec__bar"></view>
						<text class="sec__title">公司介绍</text>
					</view>
					<text v-for="(p, i) in introParagraphs" :key="'intro' + i" class="para">{{ p }}</text>
				</view>

				<view v-if="benefits.length" class="sec">
					<view class="sec__head">
						<view class="sec__bar"></view>
						<text class="sec__title">福利待遇</text>
					</view>
					<view class="chips">
						<text v-for="(b, i) in benefits" :key="'b' + i" class="chips__item">{{ b }}</text>
					</view>
				</view>

				<view class="sec">
					<view class="sec__head">
						<view class="sec__bar"></view>
						<text class="sec__title">公司信息</text>
					</view>
					<view v-if="company.industry" class="row">
						<text class="row__k">所属行业</text>
						<text class="row__v">{{ company.industry }}</text>
					</view>
					<view v-if="company.scale" class="row">
						<text class="row__k">公司规模</text>
						<text class="row__v">{{ company.scale }}</text>
					</view>
					<view v-if="company.stage" class="row">
						<text class="row__k">融资阶段</text>
						<text class="row__v">{{ company.stage }}</text>
					</view>
					<view v-if="company.address" class="row">
						<text class="row__k">公司地址</text>
						<text class="row__v row__v--wrap">{{ company.address }}</text>
					</view>
					<!-- 官网用剪贴板而不是外链：App 内直接打开外部站点体验不可控 -->
					<view v-if="company.website" class="row" hover-class="zn-hover" @tap="copyWebsite">
						<text class="row__k">公司官网</text>
						<view class="row__link">
							<text class="row__v">{{ company.website }}</text>
							<uni-icons type="paperplane" :size="14" color="#00a6a7"></uni-icons>
						</view>
					</view>
				</view>
			</view>

			<!-- ---------- Tab 3：相似职位 ---------- -->
			<view v-else class="card">
				<template v-if="similar.length">
					<view v-for="item in similar" :key="item.id" class="jdetail__similar">
						<zn-job-card :job="item" compact @tap="goDetail" />
					</view>
				</template>
				<zn-empty v-else text="暂无相似职位" desc="可以回到列表页按职能筛选更多机会" />
			</view>

			<!-- 底部操作栏是固定定位的，这里留出等高的占位，避免遮住最后一个 Tab 的内容 -->
			<view class="jdetail__holder"></view>

			<!-- ==================== 底部固定操作栏 ==================== -->
			<view class="bar">
				<view class="bar__fav" hover-class="zn-hover" @tap="onFavorite">
					<uni-icons :type="job.isFavorite ? 'star-filled' : 'star'" :size="22"
						:color="job.isFavorite ? '#ff8f1f' : '#999999'"></uni-icons>
					<text class="bar__fav-text">{{ job.isFavorite ? '已收藏' : '收藏' }}</text>
				</view>
				<view class="bar__chat" hover-class="zn-hover" @tap="onChat">
					<text class="bar__chat-text">立即沟通</text>
				</view>
				<view class="bar__apply" :class="{ 'is-disabled': !isOpen }" hover-class="zn-hover" @tap="onApply">
					<text class="bar__apply-text">{{ isOpen ? '投递简历' : '已停止招聘' }}</text>
				</view>
			</view>

			<!-- ==================== 打招呼弹层（投递前的问候语，选填） ==================== -->
			<view v-if="greetShow" class="greet">
				<view class="greet__mask" @tap="greetShow = false"></view>
				<view class="greet__sheet">
					<text class="greet__title">和招聘者打个招呼</text>
					<text class="greet__tip">自我介绍或对岗位的理解能让简历更容易被看到（选填，最多 200 字）</text>
					<textarea v-model="greeting" class="greet__input" :maxlength="200" placeholder="例如：3 年后端经验，熟悉 Node/Python，对贵司的储能业务很感兴趣。"
						placeholder-class="greet__ph" />
					<text class="greet__count">{{ greeting.length }}/200</text>
					<view class="greet__actions">
						<view class="greet__cancel" hover-class="zn-hover" @tap="greetShow = false">
							<text class="greet__cancel-text">再想想</text>
						</view>
						<view class="greet__ok" hover-class="zn-hover" @tap="submitApply">
							<text class="greet__ok-text">{{ applying ? '投递中…' : '确认投递' }}</text>
						</view>
					</view>
				</view>
			</view>
		</template>
	</view>
</template>

<script>
	/**
	 * 职位详情
	 *
	 * 接口：
	 *   getJobDetail(id)   → {job, similar}（⚠️ 这个接口会让浏览量 +1，所以页面只在 onLoad 与手动重试时调）
	 *   toggleFavorite(id, favorited)
	 *   createConversation(jobId)  发起沟通 → 成功后带会话 id 进聊天页
	 *   applyJob({jobId, greeting}) 投递
	 *
	 * ⚠️ 错误码是本页的核心逻辑，不能一律吞掉：
	 *   40904 该职位暂未配置招聘者（种子里确有这样的职位）→ 沟通按钮要给出可读解释
	 *   40901 已经投递过该职位 → 提示并引导去「我的投递」
	 *   40902 该职位已停止招聘 → 本地同步成关闭态，禁用投递
	 *   40401 职位不存在或已下线 → 整页失败态 + 去列表页的出口
	 *
	 * ⚠️ 关于重复提示：services/api.js 对每个业务错误已经弹过一次轻提示，
	 *    这里只对「需要用户做下一步决定」的错误（40901/40902/40904）追加模态框，其余不再补提示。
	 */
	import { getJobDetail, toggleFavorite } from '@/services/job.js'
	import { createConversation } from '@/services/im.js'
	import { applyJob } from '@/services/apply.js'
	import { isLogined } from '@/services/user.js'

	/** 职位形态角标（与 zn-job-card 同一口径，避免同一条职位在两处角标不一致） */
	const KIND_TEXT = { urgent: '急招', referral: '内推', intern: '实习', campus: '校招' }

	export default {
		data() {
			return {
				id: '',
				job: null,
				similar: [],
				tabs: ['职位描述', '公司信息', '相似职位'],
				tab: 0,
				loading: false,
				loadFailed: false,
				failText: '职位详情加载失败，点击重试',
				chatting: false, // 沟通按钮的防重入（会话创建可能慢）
				applying: false, // 投递按钮的防重入
				greetShow: false, // 打招呼弹层
				greeting: ''
			}
		},
		computed: {
			/** status === 1 才是招聘中（服务端约定），其余一律按「不能投递」处理 */
			isOpen() {
				return !!this.job && Number(this.job.status) === 1
			},
			kindText() {
				return this.job ? KIND_TEXT[this.job.kind] || '' : ''
			},
			description() {
				return (this.job && this.job.description) || []
			},
			requirements() {
				return (this.job && this.job.requirements) || []
			},
			process() {
				return (this.job && this.job.process) || []
			},
			company() {
				return (this.job && this.job.company) || {}
			},
			hrMeta() {
				if (!this.job) return ''
				return [this.job.hrTitle, this.job.hrActive].filter(Boolean).join(' · ')
			},
			coyDesc() {
				const c = this.company
				return [c.industry, c.scale, c.stage].filter(Boolean).join(' · ')
			},
			/**
			 * 公司介绍段落
			 * 服务端优先给 introParagraphs（已切好段）；老数据只有 intro 时用它兜底。
			 * 这属于「同一字段的两种形态」，不是编造数据，所以允许回落。
			 */
			introParagraphs() {
				const c = this.company
				if (c.introParagraphs && c.introParagraphs.length) return c.introParagraphs
				return c.intro ? [c.intro] : []
			},
			benefits() {
				return this.company.benefits || []
			}
		},
		onLoad(options) {
			this.id = (options && options.id) ? String(options.id) : ''
			if (!this.id) {
				// 正常入口都会带 id；缺失多半是手改 URL，如实提示而不是去猜一个职位
				this.loadFailed = true
				this.failText = '缺少职位 ID，无法打开详情'
				return
			}
			this.loadDetail()
		},
		methods: {
			/* ---------------- 数据 ---------------- */
			async loadDetail() {
				if (!this.id) return
				this.loading = true
				this.loadFailed = false
				try {
					const res = await getJobDetail(this.id)
					this.job = res.job || null
					this.similar = res.similar || []
					this.tab = 0
					if (!this.job) {
						this.loadFailed = true
						this.failText = '职位数据为空，点击重试'
					}
				} catch (e) {
					this.loadFailed = true
					this.failText = (e && e.code === 40401)
						? '该职位不存在或已下线，点击重试'
						: '职位详情加载失败，点击重试'
				} finally {
					this.loading = false
				}
			},

			/* ---------------- 登录闸口 ---------------- */
			requireLogin(tip) {
				if (isLogined()) return true
				uni.showToast({ title: tip, icon: 'none' })
				setTimeout(() => uni.navigateTo({ url: '/pages/login/login' }), 800)
				return false
			},

			/* ---------------- 沟通 ---------------- */
			async onChat() {
				if (!this.job || this.chatting) return
				if (!this.requireLogin('登录后才能和招聘者沟通')) return
				this.chatting = true
				try {
					const res = await createConversation(this.job.id)
					const conv = res && res.conversation
					if (!conv || !conv.id) {
						uni.showToast({ title: '会话创建失败，请稍后重试', icon: 'none' })
						return
					}
					// created=false 表示之前聊过、复用原会话，同样直接进聊天页
					uni.navigateTo({ url: '/pages/chat/chat?id=' + conv.id + '&role=candidate' })
				} catch (e) {
					if (e && e.code === 40904) {
						uni.showModal({
							title: '暂时无法沟通',
							content: '该职位暂未配置招聘者，可以先把简历投递过去，HR 上线后会主动联系你。',
							showCancel: false,
							confirmText: '知道了'
						})
					}
					// 其余错误（网络 / 登录失效）请求层已提示，这里不再叠加
				} finally {
					this.chatting = false
				}
			},

			/* ---------------- 投递 ---------------- */
			onApply() {
				if (!this.job) return
				if (!this.isOpen) {
					uni.showToast({ title: '该职位已停止招聘', icon: 'none' })
					return
				}
				if (!this.requireLogin('登录后才能投递简历')) return
				this.greeting = ''
				this.greetShow = true
			},
			async submitApply() {
				if (!this.job || this.applying) return
				this.applying = true
				try {
					await applyJob({ jobId: this.job.id, greeting: (this.greeting || '').trim() })
					this.greetShow = false
					uni.showToast({ title: '投递成功', icon: 'success' })
					// 等 toast 展示完再跳，否则用户看不到成功反馈（交互上比立刻跳更稳）
					setTimeout(() => uni.navigateTo({ url: '/pages/seeker/applications' }), 900)
				} catch (e) {
					const code = e && e.code
					this.greetShow = false
					if (code === 40901) {
						uni.showModal({
							title: '已经投递过',
							content: '你已经投递过这个职位了，去看看投递进度？',
							confirmText: '查看投递',
							cancelText: '留在本页',
							success: r => {
								if (r.confirm) uni.navigateTo({ url: '/pages/seeker/applications' })
							}
						})
					} else if (code === 40902) {
						// 服务端说已停止招聘：本地立即同步成关闭态，避免用户继续点第二次
						this.job.status = 0
						this.job.statusText = '已停止招聘'
						uni.showModal({
							title: '无法投递',
							content: '该职位已停止招聘，可以看看下方的相似职位。',
							showCancel: false,
							confirmText: '知道了'
						})
					}
				} finally {
					this.applying = false
				}
			},

			/* ---------------- 收藏 ---------------- */
			async onFavorite() {
				if (!this.job) return
				if (!this.requireLogin('登录后才能收藏职位')) return
				try {
					const next = await toggleFavorite(this.job.id, this.job.isFavorite)
					this.job.isFavorite = next
					uni.showToast({ title: next ? '已收藏' : '已取消收藏', icon: 'none' })
				} catch (e) {
					// 请求层已提示；这里不改本地状态，保证「显示的收藏态＝服务端真实态」
				}
			},

			/* ---------------- 其它 ---------------- */
			copyWebsite() {
				const url = this.company.website
				if (!url) return
				uni.setClipboardData({
					data: url,
					success: () => uni.showToast({ title: '官网地址已复制', icon: 'none' })
				})
			},
			goDetail(job) {
				if (!job || !job.id) return
				// 相似职位继续往栈里推，返回键能一层层退回来
				uni.navigateTo({ url: '/pages/job/detail?id=' + encodeURIComponent(job.id) })
			},
			goList() {
				uni.reLaunch({ url: '/pages/index/index' })
			}
		}
	}
</script>

<style lang="scss" scoped>
	.jdetail {
		background-color: $zn-bg-page;
	}

	/* ==================== 状态块 ==================== */
	.state {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		margin: $zn-page-padding;
		padding: 40rpx $zn-gap;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;

		&--col {
			flex-direction: column;
		}
	}

	.state__row {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.state__text {
		font-size: 26rpx;
		color: $zn-text-sub;
		margin-left: 10rpx;
	}

	.state__btn {
		margin-top: $zn-gap;
		height: 64rpx;
		padding: 0 36rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.state__btn-text {
		font-size: 26rpx;
		color: #ffffff;
		font-weight: 600;
	}

	/* ==================== 已关闭提示 ==================== */
	.closed {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		background-color: #fff0f0;
		border-radius: $zn-radius;
		padding: 20rpx;
		margin: $zn-page-padding $zn-page-padding 0;
	}

	.closed__text {
		flex: 1;
		min-width: 0;
		font-size: 24rpx;
		color: $zn-red;
		line-height: 34rpx;
		margin-left: 10rpx;
	}

	/* ==================== 职位头部 ==================== */
	.hero {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: $zn-gap-lg $zn-page-padding;
		margin: $zn-page-padding $zn-page-padding 0;
		box-shadow: $zn-shadow-sm;
	}

	.hero__title-row {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.hero__kind {
		flex-shrink: 0;
		margin-right: 12rpx;
		padding: 0 10rpx;
		height: 34rpx;
		line-height: 34rpx;
		border-radius: $zn-radius-xs;
		font-size: $zn-font-xs;
		color: #ffffff;

		&.is-urgent {
			background-color: $zn-red;
		}

		&.is-referral {
			background-color: $zn-orange;
		}

		&.is-intern,
		&.is-campus {
			background-color: $zn-blue;
		}
	}

	.hero__title {
		flex: 1;
		min-width: 0;
		font-size: $zn-font-xl;
		font-weight: 700;
		color: $zn-text-title;
	}

	.hero__salary-row {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 16rpx;
	}

	.hero__salary {
		font-size: $zn-font-price;
		font-weight: 700;
		color: $zn-price;
	}

	.hero__bonus {
		margin-left: 16rpx;
		padding: 4rpx 14rpx;
		border-radius: $zn-radius-xs;
		background-color: #fff4e6;
		font-size: $zn-font-xs;
		color: $zn-orange;
	}

	.hero__metas {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 12rpx;
	}

	.hero__meta {
		font-size: $zn-font-sm;
		color: $zn-text-sub;
	}

	.hero__dot {
		margin: 0 8rpx;
		color: $zn-text-light;
	}

	.hero__tags {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		margin-top: 16rpx;
	}

	.hero__tag {
		margin: 0 12rpx 10rpx 0;
		padding: 4rpx 14rpx;
		border-radius: $zn-radius-xs;
		background-color: $zn-theme-light;
		font-size: $zn-font-xs;
		color: $zn-theme-dark;
	}

	.hero__foot {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 12rpx;
		padding-top: 16rpx;
		border-top: 1rpx solid $zn-line;
	}

	.hero__foot-item {
		font-size: $zn-font-xs;
		color: $zn-text-grey;
		margin-right: $zn-gap;
	}

	/* ==================== 招聘者 ==================== */
	.hr {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: $zn-gap;
		margin: $zn-gap $zn-page-padding 0;
		box-shadow: $zn-shadow-sm;
	}

	.hr__info {
		flex: 1;
		min-width: 0;
		margin-left: 16rpx;
		display: flex;
		flex-direction: column;
	}

	.hr__name {
		font-size: $zn-font-md;
		font-weight: 600;
		color: $zn-text-title;
	}

	.hr__company {
		font-size: $zn-font-sm;
		color: $zn-text-sub;
		margin-top: 6rpx;
	}

	.hr__meta {
		font-size: $zn-font-xs;
		color: $zn-text-grey;
		margin-top: 4rpx;
	}

	.hr__btn {
		flex-shrink: 0;
		height: 64rpx;
		padding: 0 22rpx;
		margin-left: 12rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;
	}

	.hr__btn-text {
		font-size: $zn-font-sm;
		color: #ffffff;
		font-weight: 600;
		margin-left: 6rpx;
	}

	/* ==================== Tabs ==================== */
	.tabs {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 0 $zn-page-padding;
		margin: $zn-gap $zn-page-padding 0;
		box-shadow: $zn-shadow-sm;
	}

	.tabs__item {
		flex: 1;
		height: 92rpx;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
	}

	.tabs__text {
		font-size: $zn-font;
		color: $zn-text-sub;

		&.is-active {
			color: $zn-text-title;
			font-weight: 700;
		}
	}

	.tabs__bar {
		width: 44rpx;
		height: 6rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		margin-top: 8rpx;
	}

	/* ==================== 内容卡片 ==================== */
	.card {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: $zn-gap $zn-page-padding $zn-gap-lg;
		margin: $zn-gap $zn-page-padding 0;
		box-shadow: $zn-shadow-sm;
	}

	.sec {
		margin-bottom: $zn-gap;
	}

	.sec__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-bottom: 16rpx;
	}

	.sec__bar {
		width: 8rpx;
		height: 30rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		margin-right: 14rpx;
	}

	.sec__title {
		font-size: $zn-font-md;
		font-weight: 700;
		color: $zn-text-title;
	}

	.bullet {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		margin-bottom: 14rpx;
	}

	.bullet__dot {
		width: 10rpx;
		height: 10rpx;
		border-radius: 50%;
		background-color: $zn-theme;
		margin: 16rpx 14rpx 0 0;
		flex-shrink: 0;
	}

	.bullet__text {
		flex: 1;
		min-width: 0;
		font-size: $zn-font;
		color: $zn-text-main;
		line-height: 46rpx;
	}

	.para {
		display: block;
		font-size: $zn-font;
		color: $zn-text-main;
		line-height: 48rpx;
		margin-bottom: 14rpx;
	}

	/* ---------- 招聘流程 ---------- */
	.steps {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		align-items: center;
	}

	.steps__item {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin: 0 10rpx 12rpx 0;
	}

	.steps__no {
		width: 36rpx;
		height: 36rpx;
		border-radius: 50%;
		background-color: $zn-theme-light;
		color: $zn-theme-dark;
		font-size: $zn-font-xs;
		line-height: 36rpx;
		text-align: center;
		margin-right: 8rpx;
	}

	.steps__text {
		font-size: $zn-font-sm;
		color: $zn-text-sub;
		margin-right: 8rpx;
	}

	/* ---------- 公司 ---------- */
	.coy {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-bottom: $zn-gap;
	}

	.coy__info {
		flex: 1;
		min-width: 0;
		margin-left: 18rpx;
		display: flex;
		flex-direction: column;
	}

	.coy__name {
		font-size: $zn-font-md;
		font-weight: 600;
		color: $zn-text-title;
	}

	.coy__desc {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
		margin-top: 8rpx;
	}

	.chips {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
	}

	.chips__item {
		margin: 0 14rpx 14rpx 0;
		padding: 8rpx 18rpx;
		border-radius: $zn-radius-sm;
		background-color: $zn-bg-grey;
		font-size: $zn-font-sm;
		color: $zn-text-sub;
	}

	.row {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		padding: 16rpx 0;
		border-bottom: 1rpx solid $zn-line;

		&:last-child {
			border-bottom: none;
		}
	}

	.row__k {
		width: 150rpx;
		flex-shrink: 0;
		font-size: $zn-font-sm;
		color: $zn-text-grey;
	}

	.row__v {
		flex: 1;
		min-width: 0;
		font-size: $zn-font-sm;
		color: $zn-text-main;

		&--wrap {
			line-height: 40rpx;
		}
	}

	.row__link {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	/* ---------- 相似职位 ---------- */
	.jdetail__similar {
		margin-bottom: $zn-gap;
	}

	/* ==================== 底部操作栏 ==================== */
	.jdetail__holder {
		height: 140rpx;
	}

	.bar {
		position: fixed;
		left: 0;
		right: 0;
		bottom: 0;
		z-index: 30;
		height: 120rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 0 $zn-page-padding;
		background-color: $zn-bg-card;
		border-top: 1rpx solid $zn-line;
		box-shadow: 0 -4rpx 20rpx rgba(20, 40, 30, 0.05);
	}

	.bar__fav {
		width: 120rpx;
		display: flex;
		flex-direction: column;
		align-items: center;
		justify-content: center;
	}

	.bar__fav-text {
		font-size: $zn-font-xs;
		color: $zn-text-grey;
		margin-top: 4rpx;
	}

	.bar__chat {
		flex: 1;
		height: 84rpx;
		margin: 0 16rpx;
		border-radius: $zn-radius-pill;
		border: 2rpx solid $zn-theme;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.bar__chat-text {
		font-size: $zn-font-md;
		color: $zn-theme;
		font-weight: 600;
	}

	.bar__apply {
		flex: 1;
		height: 84rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;

		&.is-disabled {
			background: #d9dde2;
			box-shadow: none;
		}
	}

	.bar__apply-text {
		font-size: $zn-font-md;
		color: #ffffff;
		font-weight: 600;
	}

	/* ==================== 打招呼弹层 ==================== */
	.greet {
		position: fixed;
		left: 0;
		right: 0;
		top: 0;
		bottom: 0;
		z-index: 900;
	}

	.greet__mask {
		position: absolute;
		left: 0;
		right: 0;
		top: 0;
		bottom: 0;
		background-color: $zn-mask;
	}

	.greet__sheet {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		background-color: $zn-bg-card;
		border-top-left-radius: $zn-radius-xl;
		border-top-right-radius: $zn-radius-xl;
		padding: $zn-gap-lg $zn-page-padding;
	}

	.greet__title {
		display: block;
		font-size: $zn-font-lg;
		font-weight: 700;
		color: $zn-text-title;
	}

	.greet__tip {
		display: block;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
		line-height: 34rpx;
		margin-top: 10rpx;
	}

	.greet__input {
		width: 100%;
		height: 200rpx;
		margin-top: 20rpx;
		padding: 18rpx;
		background-color: $zn-bg-grey;
		border-radius: $zn-radius;
		font-size: $zn-font;
		color: $zn-text-main;
	}

	.greet__ph {
		color: $zn-text-light;
		font-size: $zn-font-sm;
	}

	.greet__count {
		display: block;
		text-align: right;
		font-size: $zn-font-xs;
		color: $zn-text-light;
		margin-top: 8rpx;
	}

	.greet__actions {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 20rpx;
	}

	.greet__cancel {
		flex: 1;
		height: 84rpx;
		margin-right: 16rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.greet__cancel-text {
		font-size: $zn-font-md;
		color: $zn-text-sub;
	}

	.greet__ok {
		flex: 2;
		height: 84rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;
	}

	.greet__ok-text {
		font-size: $zn-font-md;
		color: #ffffff;
		font-weight: 600;
	}
</style>
