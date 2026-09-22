<template>
	<view class="zn-page zn-page--no-tabbar hrjobs">
		<zn-nav-bar title="职位管理" :show-back="true" border />

		<!-- ==================== 状态筛选 ==================== -->
		<view class="hrjobs__tabs">
			<view v-for="(tab, i) in tabs" :key="tab.key" class="hrjobs__tab"
				:class="{ 'is-active': tabIndex === i }" hover-class="zn-hover" @tap="switchTab(i)">
				<text class="hrjobs__tab-text">{{ tab.text }}</text>
				<view v-if="tabIndex === i" class="hrjobs__tab-bar"></view>
			</view>
		</view>

		<view class="hrjobs__body">
			<!-- ---------- 加载中 ---------- -->
			<view v-if="loading" class="hrjobs__state">
				<text class="hrjobs__state-text">正在加载职位…</text>
			</view>

			<!-- ---------- 加载失败：可重试 ---------- -->
			<zn-empty v-else-if="failed" icon="info" text="职位列表加载失败" :desc="failedMsg"
				btn-text="重新加载" @action="reload" />

			<!-- ---------- 空态 ---------- -->
			<zn-empty v-else-if="!items.length" icon="list"
				:text="tabIndex === 0 ? '还没有发布职位' : '该状态下没有职位'"
				:desc="tabIndex === 0 ? '发布第一个职位，开始接收简历' : '换个筛选条件看看'"
				:btn-text="tabIndex === 0 ? '发布第一个职位' : ''" @action="goCreate" />

			<!-- ---------- 列表 ---------- -->
			<block v-else>
				<view v-for="item in items" :key="item.id" class="job">
					<!-- 状态行：HR 自己发布的职位，先看「在招/已关闭」和「收到几份简历」 -->
					<view class="job__head">
						<zn-tag :text="item.statusText" :type="item.status === 1 ? 'green' : 'gray'" size="xs" />
						<view class="job__count" hover-class="zn-hover" @tap="goApplications(item)">
							<uni-icons type="email" :size="14" color="#ff5c1a"></uni-icons>
							<text class="job__count-text">{{ item.applicationCount }} 份简历</text>
						</view>
						<text class="job__publish">{{ item.publishText }}</text>
					</view>

					<!-- 职位卡片统一用共享组件渲染字段，避免 HR 端与求职者端字段口径漂移；
						 compact 隐藏卡片底部的「招聘者」行（就是自己，没必要显示）。
						 卡片里的公司块对 HR 也是冗余信息，这里用父级作用域样式隐藏。 -->
					<zn-job-card class="job__card" :job="item" :compact="true" @tap="goApplications(item)" />

					<!-- 列表页给的职位描述摘要，帮 HR 认出自家的哪个岗位 -->
					<text v-if="item.descriptionText" class="job__desc zn-ellipsis-2">{{ item.descriptionText }}</text>

					<!-- 操作区 -->
					<view class="job__actions">
						<view class="job__btn" hover-class="zn-hover" @tap="goApplications(item)">
							<text class="job__btn-text">查看简历</text>
							<text v-if="item.applicationCount > 0" class="job__btn-badge">{{ item.applicationCount }}</text>
						</view>
						<view class="job__btn" hover-class="zn-hover" @tap="goEdit(item)">
							<text class="job__btn-text">编辑</text>
						</view>
						<view class="job__btn" :class="{ 'is-disabled': busyId === item.id }" hover-class="zn-hover"
							@tap="onToggleStatus(item)">
							<text class="job__btn-text">{{ item.status === 1 ? '下架' : '上架' }}</text>
						</view>
						<view class="job__btn job__btn--danger" :class="{ 'is-disabled': busyId === item.id }"
							hover-class="zn-hover" @tap="onDelete(item)">
							<text class="job__btn-text job__btn-text--danger">删除</text>
						</view>
					</view>
				</view>

				<!-- 触底加载提示 -->
				<view class="hrjobs__foot">
					<text class="hrjobs__foot-text">{{ footText }}</text>
				</view>
			</block>
		</view>

		<!-- ==================== 发布职位悬浮按钮 ==================== -->
		<view class="fab" hover-class="zn-hover" @tap="goCreate">
			<uni-icons type="plusempty" :size="22" color="#ffffff"></uni-icons>
			<text class="fab__text">发布职位</text>
		</view>
	</view>
</template>

<script>
	/**
	 * 职位管理（HR 发布的职位列表）
	 *
	 * 数据来源：
	 *   列表     GET /hr/jobs?status=&page=&pageSize=   （services/hr.js → getMyJobs）
	 *   上下架   POST /hr/jobs/{id}/status               （setJobStatus）
	 *   删除     DELETE /hr/jobs/{id}                    （deleteJob）
	 *
	 * ⚠️ 删除是**逻辑删除**（服务端只写 deleted_at 并把 status 置 0）：
	 *    因此列表刷新后这条会消失，但数据库里还在，误删可由服务端恢复。
	 *    更重要的是：投递行里存了职位快照（job_title / salary_text 等），
	 *    所以删职位**不会**让候选人的投递记录失联 —— 这一点必须让 HR 知道，
	 *    否则 HR 会以为「删了职位就把候选人简历弄丢了」而不敢删。
	 *
	 * ⚠️ 数据隔离：服务端按当前账号绑定的公司过滤职位，前端不传 companyId。
	 */
	import { getMyJobs, setJobStatus, deleteJob } from '@/services/hr.js'

	/** 顶部状态筛选：status 为空即「全部」（toQuery 会跳过空值） */
	const TABS = [
		{ key: 0, text: '全部', status: '' },
		{ key: 1, text: '招聘中', status: 1 },
		{ key: 2, text: '已关闭', status: 0 }
	]

	/** 每页条数（服务端 pageSize 上限 50） */
	const PAGE_SIZE = 10

	export default {
		data() {
			return {
				tabs: TABS,
				tabIndex: 0,
				items: [],
				total: 0,
				page: 1,
				hasMore: false,
				loading: true,
				ready: false, // 首次加载完成为 true；重试 / 切 tab 时不再整屏转圈
				loadingMore: false,
				failed: false,
				failedMsg: '',
				busyId: '' // 正在执行上下架/删除的职位 id，防止连点重复提交
			}
		},
		computed: {
			currentStatus() {
				return this.tabs[this.tabIndex].status
			},
			footText() {
				if (this.loadingMore) return '正在加载更多…'
				if (this.hasMore) return '上拉加载更多'
				return '已到底部 · 共 ' + this.total + ' 个职位'
			}
		},
		onLoad() {
			this.reload()
		},
		onShow() {
			// 从编辑页返回时职位内容可能已变，重新拉第一页（列表很短，代价可接受）
			if (this.ready) this.reload()
		},
		async onPullDownRefresh() {
			try {
				await this.reload()
			} finally {
				uni.stopPullDownRefresh()
			}
		},
		onReachBottom() {
			this.loadMore()
		},
		methods: {
			/* ---------------- 数据 ---------------- */
			async reload() {
				this.loading = !this.ready
				this.failed = false
				this.page = 1
				try {
					const res = await getMyJobs({ status: this.currentStatus, page: 1, pageSize: PAGE_SIZE })
					this.items = (res && res.list) || []
					this.total = (res && res.total) || 0
					this.hasMore = !!(res && res.hasMore)
				} catch (e) {
					if (this.handleUnbound(e)) return
					this.failed = true
					this.failedMsg = (e && e.message) || '请检查服务端是否已启动'
					this.items = []
				} finally {
					this.loading = false
					this.ready = true
				}
			},
			async loadMore() {
				if (this.loadingMore || !this.hasMore || this.loading) return
				this.loadingMore = true
				const next = this.page + 1
				try {
					const res = await getMyJobs({ status: this.currentStatus, page: next, pageSize: PAGE_SIZE })
					const list = (res && res.list) || []
					// 按 id 去重：翻页期间若有职位被删/被改状态，服务端分页可能出现重复行
					const exists = {}
					this.items.forEach(it => { exists[it.id] = true })
					this.items = this.items.concat(list.filter(it => !exists[it.id]))
					this.total = (res && res.total) || this.total
					this.hasMore = !!(res && res.hasMore)
					this.page = next
				} catch (e) {
					this.handleUnbound(e)
				} finally {
					this.loadingMore = false
				}
			},
			/** 40301 / HTTP 403：账号已不是企业招聘方 → 回绑定页 */
			handleUnbound(err) {
				if (!err || (err.code !== 40301 && err.status !== 403)) return false
				uni.reLaunch({ url: '/pages/hr/bind' })
				return true
			},

			/* ---------------- 交互 ---------------- */
			switchTab(i) {
				if (this.tabIndex === i) return
				this.tabIndex = i
				this.items = []
				this.reload()
			},

			/**
			 * 上架 / 下架
			 * ⚠️ 服务端只回 {jobId,status,changed}，不回整条职位（也没有 statusText），
			 *    所以本地按与服务端 hr.py 相同的口径补文案：1=招聘中 / 0=已关闭。
			 */
			async onToggleStatus(item) {
				if (this.busyId) return
				const target = item.status === 1 ? 0 : 1
				this.busyId = item.id
				try {
					await setJobStatus(item.id, target)
					uni.showToast({ title: target === 1 ? '已上架' : '已下架', icon: 'none' })
					if (this.currentStatus === '') {
						// 全部 tab：就地更新这一条，不打断 HR 的浏览位置
						const row = this.items.find(it => it.id === item.id)
						if (row) {
							row.status = target
							row.statusText = target === 1 ? '招聘中' : '已关闭'
						}
					} else {
						// 状态 tab：这条已不属于当前筛选，必须重新拉取
						this.reload()
					}
				} catch (e) {
					this.handleUnbound(e)
				} finally {
					this.busyId = ''
				}
			},

			/** 删除：二次确认后调接口（服务端逻辑删除，见文件头注释） */
			onDelete(item) {
				if (this.busyId) return
				uni.showModal({
					title: '删除职位',
					content: '确定删除「' + item.title + '」吗？删除后求职者将搜不到该职位，但已投递的简历不会丢失。',
					confirmText: '删除',
					confirmColor: '#ff4d4f',
					success: async res => {
						if (!res.confirm) return
						this.busyId = item.id
						try {
							await deleteJob(item.id)
							this.items = this.items.filter(it => it.id !== item.id)
							this.total = Math.max(0, this.total - 1)
							uni.showToast({ title: '已删除', icon: 'none' })
						} catch (e) {
							this.handleUnbound(e)
						} finally {
							this.busyId = ''
						}
					}
				})
			},

			/* ---------------- 跳转 ---------------- */
			goApplications(item) {
				uni.navigateTo({ url: '/pages/hr/applications?jobId=' + item.id })
			},
			/**
			 * 编辑：把这条职位对象缓存给编辑页做首屏回填
			 * ⚠️ 列表接口不返回职位正文（只有 descriptionText 摘要 80 字），
			 *    而 updateJob 是全量覆盖 —— 编辑页必须再去取一次完整正文，
			 *    否则提交会把岗位职责/任职要求/招聘流程清空。详见 job-edit.vue 的说明。
			 */
			goEdit(item) {
				try {
					uni.setStorageSync('zn_hr_editing_job', item)
				} catch (e) {
					// 缓存失败不影响编辑：编辑页会自己取一次详情
				}
				uni.navigateTo({ url: '/pages/hr/job-edit?id=' + item.id })
			},
			goCreate() {
				uni.navigateTo({ url: '/pages/hr/job-edit' })
			}
		}
	}
</script>

<style lang="scss" scoped>
	.hrjobs {
		padding-bottom: 180rpx; /* 给悬浮按钮留出空间 */
	}

	/* ---------------- 状态筛选 ---------------- */
	.hrjobs__tabs {
		display: flex;
		flex-direction: row;
		background-color: $zn-bg-card;
		padding: 0 $zn-page-padding;
	}

	.hrjobs__tab {
		flex: 1;
		height: 88rpx;
		display: flex;
		align-items: center;
		justify-content: center;
		position: relative;
	}

	.hrjobs__tab-text {
		font-size: $zn-font;
		color: $zn-text-sub;
	}

	.hrjobs__tab.is-active .hrjobs__tab-text {
		color: $zn-theme;
		font-weight: 700;
	}

	.hrjobs__tab-bar {
		position: absolute;
		bottom: 8rpx;
		width: 48rpx;
		height: 6rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
	}

	.hrjobs__body {
		padding: $zn-gap $zn-page-padding 0;
	}

	.hrjobs__state {
		padding: 120rpx 0;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.hrjobs__state-text {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
	}

	/* ---------------- 职位卡 ---------------- */
	.job {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: $zn-gap;
		margin-bottom: $zn-gap;
	}

	.job__head {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.job__count {
		margin-left: $zn-gap-sm;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.job__count-text {
		margin-left: 6rpx;
		font-size: $zn-font-xs;
		color: $zn-price;
		font-weight: 600;
	}

	.job__publish {
		flex: 1;
		text-align: right;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	/* 复用 zn-job-card 但抹掉它的卡片外壳：外层 .job 已经提供了白底/圆角/阴影，
	   否则会出现「卡片里再套一张卡片」的双层阴影。
	   ⚠️ 为什么写成 `.job .job__card`（多一层祖先）：
	      Vue 3 会把父组件的 scoped 属性打在子组件根节点上，选择器本可生效，
	      但它与组件内部 `.zn-job-card` 的优先级相同（都是 2），只能靠样式文件顺序决胜 ——
	      多带一个祖先类把优先级提到 3，才能稳定覆盖，不依赖打包顺序。 */
	.job .job__card {
		display: block;
		padding: $zn-gap-sm 0 0;
		box-shadow: none;
		border-radius: 0;
		background-color: transparent;
	}

	/* 自家职位卡片上不需要再显示一次自己公司 */
	.job__card :deep(.zn-job-card__company) {
		display: none;
	}

	.job__desc {
		margin-top: 12rpx;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
		line-height: 36rpx;
	}

	/* ---------------- 操作区 ---------------- */
	.job__actions {
		margin-top: $zn-gap-sm;
		padding-top: $zn-gap-sm;
		border-top: 1rpx solid $zn-line;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.job__btn {
		flex: 1;
		height: 64rpx;
		margin-right: 14rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;

		&:last-child {
			margin-right: 0;
		}

		&.is-disabled {
			opacity: 0.5;
		}

		&--danger {
			background-color: #fff0f0;
		}
	}

	.job__btn-text {
		font-size: $zn-font-sm;
		color: $zn-text-sub;

		&--danger {
			color: $zn-red;
		}
	}

	.job__btn-badge {
		margin-left: 6rpx;
		min-width: 30rpx;
		height: 30rpx;
		padding: 0 8rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-red;
		color: #ffffff;
		font-size: 18rpx;
		line-height: 30rpx;
		text-align: center;
	}

	.hrjobs__foot {
		padding: $zn-gap 0 $zn-gap-lg;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.hrjobs__foot-text {
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	/* ---------------- 悬浮发布按钮 ---------------- */
	.fab {
		position: fixed;
		right: $zn-page-padding;
		bottom: 60rpx;
		height: 92rpx;
		padding: 0 36rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		box-shadow: $zn-shadow-theme;
		display: flex;
		flex-direction: row;
		align-items: center;
		z-index: 20;
	}

	.fab__text {
		margin-left: 10rpx;
		font-size: $zn-font;
		font-weight: 600;
		color: #ffffff;
	}
</style>
