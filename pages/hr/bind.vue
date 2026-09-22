<template>
	<view class="zn-page zn-page--no-tabbar hrbind">
		<zn-nav-bar title="绑定公司" :show-back="true" border />

		<!-- ==================== 一、加载中 ==================== -->
		<view v-if="loading" class="hrbind__state">
			<text class="hrbind__state-text">正在加载…</text>
		</view>

		<!-- ==================== 二、加载失败：可重试 ==================== -->
		<zn-empty v-else-if="failed" icon="info" text="加载失败" :desc="failedMsg" btn-text="重新加载"
			@action="init" />

		<block v-else>
			<!-- ==================== 三、已绑定：显示当前绑定信息 ==================== -->
			<view v-if="bound && !changing" class="bound">
				<view class="bound__head">
					<zn-company-logo :text="company.logoText" :color="company.logoColor" :size="104" />
					<view class="bound__main">
						<text class="bound__name zn-ellipsis">{{ company.name || company.shortName }}</text>
						<text class="bound__meta zn-ellipsis">{{ companyMeta }}</text>
					</view>
					<zn-tag text="已绑定" type="green" size="sm" />
				</view>
				<view class="bound__kv">
					<text class="bound__k">我的招聘职位</text>
					<text class="bound__v">{{ hrTitle || '招聘负责人' }}</text>
				</view>
				<view class="bound__kv">
					<text class="bound__k">在招职位数</text>
					<text class="bound__v">{{ company.jobCount || 0 }} 个</text>
				</view>
				<view class="bound__actions">
					<view class="bound__btn" hover-class="zn-hover" @tap="goDashboard">
						<text class="bound__btn-text">回工作台</text>
					</view>
					<view class="bound__btn bound__btn--plain" hover-class="zn-hover" @tap="startChange">
						<text class="bound__btn-text bound__btn-text--plain">更换公司</text>
					</view>
				</view>
			</view>

			<!-- ==================== 四、选择公司 ==================== -->
			<block v-else>
				<!-- 顶部说明 -->
				<view class="intro">
					<view class="intro__icon">
						<uni-icons type="staff-filled" :size="28" color="#ffffff"></uni-icons>
					</view>
					<view class="intro__main">
						<text class="intro__title">{{ bound ? '更换绑定的公司' : '选择你要招聘的公司' }}</text>
						<text class="intro__desc">
							演示环境下直接选择一家公司即可完成绑定；真实产品需要提交企业资质并等待平台审核。
							绑定后你只能看到这家公司的职位与收到的简历。
						</text>
					</view>
				</view>

				<!-- 搜索 -->
				<view class="search">
					<uni-icons type="search" :size="18" color="#999999"></uni-icons>
					<input class="search__input" v-model="keyword" :maxlength="30" placeholder="搜索公司名称"
						placeholder-class="search__ph" confirm-type="search" @confirm="search" />
					<view v-if="keyword" class="search__clear" hover-class="zn-hover" @tap="clearKeyword">
						<uni-icons type="clear" :size="16" color="#bbbbbb"></uni-icons>
					</view>
					<view class="search__btn" hover-class="zn-hover" @tap="search">
						<text class="search__btn-text">搜索</text>
					</view>
				</view>

				<!-- 公司列表 -->
				<view v-if="listLoading" class="hrbind__state">
					<text class="hrbind__state-text">正在加载公司列表…</text>
				</view>
				<zn-empty v-else-if="listFailed" icon="info" text="公司列表加载失败" :desc="listFailedMsg"
					btn-text="重新加载" @action="loadCompanies" />
				<zn-empty v-else-if="!companies.length" icon="search" text="没有找到匹配的公司"
					:desc="keyword ? '换个关键词试试，比如「科技」' : '公司列表为空，请检查种子数据'" />

				<view v-else class="list">
					<view v-for="c in companies" :key="c.id" class="comp"
						:class="{ 'is-on': selectedId === c.id }" hover-class="zn-hover" @tap="select(c)">
						<zn-company-logo :text="c.logoText" :color="c.logoColor" :size="88" />
						<view class="comp__main">
							<text class="comp__name zn-ellipsis">{{ c.name }}</text>
							<text class="comp__meta zn-ellipsis">{{ metaOf(c) }}</text>
						</view>
						<view class="comp__right">
							<text class="comp__jobs">{{ c.jobCount || 0 }} 个在招</text>
							<uni-icons :type="selectedId === c.id ? 'checkbox-filled' : 'checkbox'" :size="20"
								:color="selectedId === c.id ? '#00A6A7' : '#cccfd6'"></uni-icons>
						</view>
					</view>
				</view>

				<!-- 招聘职位填写 -->
				<view class="sec">
					<zn-section-header title="你的招聘职位" />
					<input class="field__input" v-model="hrTitleInput" :maxlength="30"
						placeholder="如：招聘经理 / 技术招聘专家" placeholder-class="field__ph" />
					<view class="chips">
						<view v-for="t in titlePresets" :key="t" class="chip" hover-class="zn-hover"
							@tap="hrTitleInput = t">
							<text class="chip__text">{{ t }}</text>
						</view>
					</view>
					<text class="field__tip">该职位会显示在求职者看到的职位卡片上</text>
				</view>

				<view class="hrbind__gap"></view>
			</block>
		</block>

		<!-- ==================== 五、底部操作条 ==================== -->
		<view v-if="!loading && !failed && (!bound || changing)" class="bar">
			<view class="bar__cancel" hover-class="zn-hover" @tap="goSeekerHome">
				<text class="bar__cancel-text">暂不绑定</text>
			</view>
			<view class="bar__btn" :class="{ 'is-disabled': !selectedId || binding }" hover-class="zn-hover"
				@tap="onBind">
				<text class="bar__btn-text">{{ binding ? '绑定中…' : (bound ? '确认更换' : '确认绑定') }}</text>
			</view>
		</view>
	</view>
</template>

<script>
	/**
	 * 绑定公司（成为企业招聘方）
	 *
	 * 接口：
	 *   GET  /hr/me          getHrMe      —— 判断是否已绑定
	 *   GET  /hr/companies   getCompanies —— 可选公司列表（关键词搜索）
	 *   POST /hr/bind        bindCompany  —— 绑定（返回 adoptedJobs）
	 *
	 * ⚠️ 为什么这里是「直接选一家公司」：
	 *    服务端 schemas/hr.py 的 BindCompanyIn 注释已写明 ——
	 *    真实产品需要企业资质审核（营业执照、对公验证、招聘人授权），
	 *    演示环境简化为从公司表里选一家绑定。本页按这个前提实现，
	 *    并在页面上如实告知用户「真实产品需要审核」。
	 *
	 * ⚠️ adoptedJobs 的含义（服务端 bind_company）：
	 *    绑定后会把该公司「hr_id 为空」的种子职位挂到当前账号名下，
	 *    否则求职者点「立即沟通」找不到聊天对象。所以要提示「接管了多少个职位」。
	 */
	import { getHrMe, getCompanies, bindCompany } from '@/services/hr.js'

	/** 招聘职位常用值（服务端 hrTitle 最长 30，不传默认「招聘经理」） */
	const TITLE_PRESETS = ['招聘经理', '高级招聘专员', '技术招聘专家', 'HRBP', '用人部门负责人']

	export default {
		data() {
			return {
				loading: true,
				ready: false,
				failed: false,
				failedMsg: '',

				bound: false,
				company: {},
				hrTitle: '',
				changing: false, // 已绑定时是否切到「更换公司」视图

				keyword: '',
				companies: [],
				listLoading: false,
				listFailed: false,
				listFailedMsg: '',

				selectedId: '',
				hrTitleInput: '招聘经理',
				binding: false,
				titlePresets: TITLE_PRESETS
			}
		},
		computed: {
			companyMeta() {
				const c = this.company
				return [c.industry, c.scale, c.stage, c.city].filter(Boolean).join(' · ') || '公司信息待完善'
			}
		},
		onLoad() {
			this.init()
		},
		methods: {
			/* ---------------- 初始化 ---------------- */
			async init() {
				this.loading = !this.ready
				this.failed = false
				try {
					const me = await getHrMe()
					this.bound = !!(me && me.bound)
					this.company = (me && me.company) || {}
					this.hrTitle = (me && me.role && me.role.hrTitle) || ''
					if (this.hrTitle) this.hrTitleInput = this.hrTitle
					if (!this.bound || this.changing) {
						await this.loadCompanies()
					}
				} catch (e) {
					this.failed = true
					this.failedMsg = (e && e.message) || '请检查服务端是否已启动'
				} finally {
					this.loading = false
					this.ready = true
				}
			},

			/* ---------------- 公司列表 ---------------- */
			async loadCompanies() {
				this.listLoading = !this.companies.length
				this.listFailed = false
				try {
					const res = await getCompanies({
						keyword: this.keyword.trim(),
						limit: 20
					})
					this.companies = (res && res.list) || []
					// 选中项若已不在列表里（换了关键词），清掉选择避免误绑
					if (this.selectedId && !this.companies.some(c => c.id === this.selectedId)) {
						this.selectedId = ''
					}
				} catch (e) {
					this.listFailed = true
					this.listFailedMsg = (e && e.message) || '请检查服务端是否已启动'
					this.companies = []
				} finally {
					this.listLoading = false
				}
			},
			search() {
				this.loadCompanies()
			},
			clearKeyword() {
				this.keyword = ''
				this.loadCompanies()
			},
			metaOf(c) {
				return [c.industry, c.scale, c.city].filter(Boolean).join(' · ') || '公司信息待完善'
			},
			select(c) {
				this.selectedId = c.id
			},

			/* ---------------- 绑定 ---------------- */
			async onBind() {
				if (this.binding) return
				if (!this.selectedId) {
					uni.showToast({ title: '请先选择一家公司', icon: 'none' })
					return
				}
				const hrTitle = this.hrTitleInput.trim()
				if (!hrTitle) {
					uni.showToast({ title: '请填写你的招聘职位', icon: 'none' })
					return
				}
				this.binding = true
				try {
					const res = await bindCompany({ companyId: this.selectedId, hrTitle })
					const adopted = (res && res.adoptedJobs) || 0
					// 提示接管职位数：这解释了「为什么工作台里突然多了几个职位」
					uni.showModal({
						title: '绑定成功',
						content: '已接管该公司 ' + adopted + ' 个职位，现在可以在工作台管理职位与简历了。',
						showCancel: false,
						confirmText: '去工作台',
						confirmColor: '#00A6A7',
						// 用 complete 而不是 success：只要弹窗关掉就一定进工作台，
						// 不会出现「点了确认却停在绑定页」的半成品状态
						complete: () => {
							// 企业端首页：用 reLaunch 清掉绑定页，返回键不会退回绑定流程
							uni.reLaunch({ url: '/pages/hr/dashboard' })
						}
					})
				} catch (e) {
					// 40403 公司不存在等错误由 services/api.js 弹出服务端原文
				} finally {
					this.binding = false
				}
			},

			/* ---------------- 跳转 ---------------- */
			startChange() {
				this.changing = true
				this.selectedId = ''
				this.loadCompanies()
			},
			goDashboard() {
				uni.reLaunch({ url: '/pages/hr/dashboard' })
			},
			goSeekerHome() {
				uni.reLaunch({ url: '/pages/index/index' })
			}
		}
	}
</script>

<style lang="scss" scoped>
	.hrbind {
		padding-bottom: 200rpx;
	}

	.hrbind__state {
		padding: 140rpx 0;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.hrbind__state-text {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
	}

	.hrbind__gap {
		height: 40rpx;
	}

	/* ---------------- 已绑定 ---------------- */
	.bound {
		margin: $zn-gap $zn-page-padding 0;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: $zn-gap-lg $zn-gap;
	}

	.bound__head {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.bound__main {
		flex: 1;
		min-width: 0;
		margin-left: $zn-gap;
		display: flex;
		flex-direction: column;
	}

	.bound__name {
		font-size: $zn-font-md;
		font-weight: 700;
		color: $zn-text-title;
	}

	.bound__meta {
		margin-top: 8rpx;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
	}

	.bound__kv {
		margin-top: $zn-gap-sm;
		padding-top: $zn-gap-sm;
		border-top: 1rpx solid $zn-line;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.bound__k {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
	}

	.bound__v {
		font-size: $zn-font-sm;
		color: $zn-text-main;
		font-weight: 600;
	}

	.bound__actions {
		margin-top: $zn-gap-lg;
		display: flex;
		flex-direction: row;
	}

	.bound__btn {
		flex: 1;
		height: 84rpx;
		margin-right: $zn-gap-sm;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;

		&:last-child {
			margin-right: 0;
		}

		&--plain {
			background: none;
			background-color: $zn-bg-grey;
		}
	}

	.bound__btn-text {
		font-size: $zn-font;
		font-weight: 600;
		color: #ffffff;

		&--plain {
			color: $zn-text-sub;
		}
	}

	/* ---------------- 说明 ---------------- */
	.intro {
		margin: $zn-gap $zn-page-padding 0;
		padding: $zn-gap;
		border-radius: $zn-radius-lg;
		background-color: $zn-theme-lighter;
		border: 1rpx solid $zn-theme-light;
		display: flex;
		flex-direction: row;
		align-items: flex-start;
	}

	.intro__icon {
		width: 72rpx;
		height: 72rpx;
		border-radius: $zn-radius;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}

	.intro__main {
		flex: 1;
		min-width: 0;
		margin-left: $zn-gap-sm;
		display: flex;
		flex-direction: column;
	}

	.intro__title {
		font-size: $zn-font;
		font-weight: 700;
		color: $zn-theme-dark;
	}

	.intro__desc {
		margin-top: 8rpx;
		font-size: $zn-font-xs;
		color: $zn-text-sub;
		line-height: 38rpx;
	}

	/* ---------------- 搜索 ---------------- */
	.search {
		margin: $zn-gap-sm $zn-page-padding 0;
		height: 84rpx;
		padding: 0 $zn-gap-sm;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-card;
		box-shadow: $zn-shadow-sm;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.search__input {
		flex: 1;
		min-width: 0;
		margin-left: 12rpx;
		font-size: $zn-font-sm;
		color: $zn-text-main;
	}

	.search__ph {
		color: $zn-text-light;
		font-size: $zn-font-sm;
	}

	.search__clear {
		width: 48rpx;
		height: 48rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.search__btn {
		flex-shrink: 0;
		margin-left: 12rpx;
		height: 60rpx;
		padding: 0 26rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-theme-light;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.search__btn-text {
		font-size: $zn-font-xs;
		color: $zn-theme-deep;
		font-weight: 600;
	}

	/* ---------------- 公司列表 ---------------- */
	.list {
		padding: $zn-gap $zn-page-padding 0;
	}

	.comp {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		border: 2rpx solid transparent;
		padding: $zn-gap;
		margin-bottom: $zn-gap-sm;
		display: flex;
		flex-direction: row;
		align-items: center;

		&.is-on {
			border-color: $zn-theme;
			background-color: $zn-theme-lighter;
		}
	}

	.comp__main {
		flex: 1;
		min-width: 0;
		margin-left: $zn-gap-sm;
		display: flex;
		flex-direction: column;
	}

	.comp__name {
		font-size: $zn-font;
		font-weight: 600;
		color: $zn-text-title;
	}

	.comp__meta {
		margin-top: 8rpx;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
	}

	.comp__right {
		flex-shrink: 0;
		display: flex;
		flex-direction: column;
		align-items: flex-end;
	}

	.comp__jobs {
		font-size: $zn-font-xs;
		color: $zn-theme-deep;
		margin-bottom: 10rpx;
	}

	/* ---------------- 招聘职位 ---------------- */
	.sec {
		margin: $zn-gap-sm $zn-page-padding 0;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: 0 $zn-gap $zn-gap;
	}

	.field__input {
		margin-top: $zn-gap-sm;
		height: 84rpx;
		padding: 0 $zn-gap-sm;
		border-radius: $zn-radius;
		background-color: $zn-bg-grey;
		font-size: $zn-font-sm;
		color: $zn-text-main;
	}

	.field__ph {
		color: $zn-text-light;
		font-size: $zn-font-sm;
	}

	.field__tip {
		display: block;
		margin-top: 12rpx;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	.chips {
		margin-top: 12rpx;
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
	}

	.chip {
		margin: 0 12rpx 12rpx 0;
		height: 56rpx;
		padding: 0 20rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.chip__text {
		font-size: $zn-font-xs;
		color: $zn-text-sub;
	}

	/* ---------------- 底部操作条 ---------------- */
	.bar {
		position: fixed;
		left: 0;
		right: 0;
		bottom: 0;
		padding: $zn-gap-sm $zn-page-padding calc(#{$zn-gap-sm} + env(safe-area-inset-bottom));
		background-color: $zn-bg-card;
		box-shadow: 0 -4rpx 16rpx rgba(20, 40, 30, 0.06);
		display: flex;
		flex-direction: row;
		align-items: center;
		z-index: 30;
	}

	.bar__cancel {
		flex-shrink: 0;
		height: 84rpx;
		padding: 0 32rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-right: $zn-gap-sm;
	}

	.bar__cancel-text {
		font-size: $zn-font-sm;
		color: $zn-text-sub;
	}

	.bar__btn {
		flex: 1;
		height: 84rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;

		&.is-disabled {
			opacity: 0.5;
		}
	}

	.bar__btn-text {
		font-size: $zn-font;
		font-weight: 600;
		color: #ffffff;
	}
</style>
