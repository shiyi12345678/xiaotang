<template>
	<view class="zn-page jlist">
		<!-- ==================== 顶部：返回 + 搜索 + 筛选栏 ==================== -->
		<view class="jlist__nav" :style="{ paddingTop: statusBarHeight + 'px' }">
			<view class="jlist__navrow">
				<view class="jlist__back" hover-class="zn-hover" @tap="goBack">
					<uni-icons type="left" :size="22" color="#222222"></uni-icons>
				</view>
				<!-- 列表页不直接输入关键词，点进搜索页（那里有热词与历史） -->
				<view class="jlist__search" hover-class="zn-hover" @tap="goSearch">
					<uni-icons type="search" :size="17" color="#9aa0a6"></uni-icons>
					<text class="jlist__search-text" :class="{ 'is-ph': !keyword }">{{ searchText }}</text>
				</view>
			</view>

			<!-- 筛选栏横向可滚动：6 个维度在小屏上放不下，横向滚动比压缩字号更好用 -->
			<scroll-view class="jlist__bar" scroll-x :show-scrollbar="false">
				<view class="jlist__barrow">
					<view v-for="item in filterDefs" :key="item.key" class="jlist__filter"
						:class="{ 'is-active': isFilterActive(item.key) }" hover-class="zn-hover"
						@tap="openPanel(item.key)">
						<text class="jlist__filter-text zn-ellipsis">{{ filterLabel(item.key) }}</text>
						<uni-icons type="arrow-down" :size="12"
							:color="isFilterActive(item.key) ? '#00a6a7' : '#999999'"></uni-icons>
					</view>
				</view>
			</scroll-view>
		</view>

		<!-- ==================== 结果概要 ==================== -->
		<view class="jlist__summary">
			<text class="jlist__count">共 {{ total }} 个职位</text>
			<!-- 从首页标签进来的 kind 是一个独立筛选维度，用可移除的 chip 显示，避免用户找不到怎么取消 -->
			<view v-if="kind" class="jlist__chip" hover-class="zn-hover" @tap="clearKind">
				<text class="jlist__chip-text">{{ kindText }}</text>
				<uni-icons type="closeempty" :size="12" color="#00a6a7"></uni-icons>
			</view>
			<view v-if="hasAnyFilter" class="jlist__reset" hover-class="zn-hover" @tap="resetAll">
				<text class="jlist__reset-text">重置筛选</text>
			</view>
		</view>

		<!-- ==================== 列表三态 ==================== -->
		<view class="jlist__body">
			<view v-if="loading" class="state">
				<text class="state__text">正在加载职位…</text>
			</view>

			<view v-else-if="loadFailed" class="state" hover-class="zn-hover" @tap="refresh">
				<uni-icons type="refresh" :size="18" color="#00a6a7"></uni-icons>
				<text class="state__text">职位加载失败，点击重试</text>
			</view>

			<zn-empty v-else-if="!list.length" icon="search" text="没有符合条件的职位"
				desc="试试放宽薪资或经验要求，或换一个职能方向" btn-text="重置筛选" @action="resetAll" />

			<template v-else>
				<view v-for="job in list" :key="job.id" class="jlist__item">
					<zn-job-card :job="job" show-favorite @tap="goDetail" @favorite="onFavorite" />
				</view>
				<!-- 加载更多 / 没有更多：触底加载失败时不把整页变成失败态，只在这里提示 -->
				<view class="more">
					<text v-if="loadingMore" class="more__text">正在加载更多…</text>
					<text v-else-if="loadMoreFailed" class="more__text more__text--tap" @tap="loadMore">
						加载更多失败，点击重试
					</text>
					<text v-else-if="hasMore" class="more__text">上拉加载更多</text>
					<text v-else class="more__text">没有更多职位了</text>
				</view>
			</template>
		</view>

		<!-- ==================== 筛选弹层 ==================== -->
		<view v-if="panel" class="panel">
			<view class="panel__mask" @tap="closePanel"></view>
			<view class="panel__sheet">
				<view class="panel__head">
					<text class="panel__title">{{ panelTitle }}</text>
					<view class="panel__close" hover-class="zn-hover" @tap="closePanel">
						<uni-icons type="closeempty" :size="20" color="#999999"></uni-icons>
					</view>
				</view>

				<!-- 选项数据加载失败：弹层内单独给重试，不影响已加载的职位列表 -->
				<view v-if="optionsFailed && panel !== 'sort'" class="state" hover-class="zn-hover"
					@tap="loadOptions">
					<uni-icons type="refresh" :size="18" color="#00a6a7"></uni-icons>
					<text class="state__text">筛选项加载失败，点击重试</text>
				</view>

				<!-- ---------- 职能：一级 + 二级两级联动 ---------- -->
				<view v-else-if="panel === 'category'" class="cat">
					<scroll-view class="cat__left" scroll-y>
						<view class="cat__l1" :class="{ 'is-active': !categoryId }" hover-class="zn-hover"
							@tap="pickCategory('', '')">
							<text class="cat__l1-text">职能不限</text>
						</view>
						<view v-for="c in categoryList" :key="c.id" class="cat__l1"
							:class="{ 'is-active': activeParentId === c.id }" hover-class="zn-hover"
							@tap="selectParent(c)">
							<text class="cat__l1-text">{{ c.name }}</text>
						</view>
					</scroll-view>
					<scroll-view class="cat__right" scroll-y>
						<!-- 选一级分类＝让服务端把该一级下的全部二级展开（服务端行为，见 job.py），
						     所以这里给一个「该职能全部」的显式入口，用户不必逐个勾子类 -->
						<view class="cat__l2" :class="{ 'is-active': categoryId === activeParentId && !!activeParentId }"
							hover-class="zn-hover" @tap="pickCategory(activeParentId, activeParentName)">
							<text class="cat__l2-text">{{ activeParentName }}（全部）</text>
						</view>
						<view v-for="c in subList" :key="c.id" class="cat__l2"
							:class="{ 'is-active': categoryId === c.id }" hover-class="zn-hover"
							@tap="pickCategory(c.id, c.name)">
							<text class="cat__l2-text">{{ c.name }}</text>
						</view>
					</scroll-view>
				</view>

				<!-- ---------- 城市：热门 + 首字母分组 ---------- -->
				<scroll-view v-else-if="panel === 'city'" class="panel__scroll" scroll-y>
					<view class="city__block">
						<view class="panel__sub">热门城市</view>
						<view class="grid">
							<view class="grid__item" :class="{ 'is-active': !cityId }" hover-class="zn-hover"
								@tap="pickCity(null)">
								<text class="grid__text">不限</text>
							</view>
							<view v-for="c in cities.hot" :key="c.id" class="grid__item"
								:class="{ 'is-active': cityId === c.id }" hover-class="zn-hover" @tap="pickCity(c)">
								<text class="grid__text">{{ c.name }}</text>
							</view>
						</view>
					</view>
					<view v-for="g in cities.groups" :key="g.initial" class="city__block">
						<view class="panel__sub">{{ g.initial }}</view>
						<view class="grid">
							<view v-for="c in g.cities" :key="c.id" class="grid__item"
								:class="{ 'is-active': cityId === c.id }" hover-class="zn-hover" @tap="pickCity(c)">
								<text class="grid__text">{{ c.name }}</text>
							</view>
						</view>
					</view>
					<zn-empty v-if="!cities.hot.length && !cities.groups.length" text="暂无城市数据" />
				</scroll-view>

				<!-- ---------- 薪资 / 经验 / 学历 / 排序：单列选项 ---------- -->
				<scroll-view v-else class="panel__scroll" scroll-y>
					<view v-for="(opt, i) in currentOptions" :key="'opt' + i" class="opt"
						:class="{ 'is-active': isOptionActive(opt) }" hover-class="zn-hover"
						@tap="pickOption(opt)">
						<text class="opt__text">{{ opt.label }}</text>
						<uni-icons v-if="isOptionActive(opt)" type="checkmarkempty" :size="18"
							color="#00a6a7"></uni-icons>
					</view>
				</scroll-view>
			</view>
		</view>

		<!-- 本页是 tabBar 上的「职位」页（原「分类」）：key 沿用 category，
		     含义已映射到职位列表，见 components/zn-tab-bar/zn-tab-bar.vue 的说明 -->
		<zn-tab-bar current="category" />
	</view>
</template>

<script>
	/**
	 * 职位列表 / 职能筛选
	 *
	 * 入口：首页轮播与职能入口（category）、搜索页（keyword）、首页标签（kind）、城市页（city）
	 * 接口：getJobList(params)（分页 + 筛选 + 排序共用一个接口）
	 *       getJobCategories() / getCities() / getJobFilters() 取筛选面板的可选项
	 *
	 * ⚠️ 三个筛选数据的取舍：
	 *    1. 筛选面板的可选项是「展示型配置」，可能被后台改，所以每次进页面拉一次（不做本地硬编码），
	 *       但**不在切筛选时重复拉**，只在面板首次打开时用已缓存的数据。
	 *    2. 薪资档位的单位统一是 **K**（与 /job/list 的 salaryMin/salaryMax 同口径）：
	 *       「5-10K」存的就是 min=5 / max=10，页面**不要**再做单位换算 ——
	 *       换算逻辑散落在页面里，多一个页面就多一处漏算的风险。
	 *       这个口径由服务端与种子数据共同保证（/job/filters 的兜底默认值本来就是 K）。
	 *       历史坑：种子曾用「元」存 5000/10000，透传会让「5-10K」变成「5000-10000K」，
	 *       筛出来永远是全部职位；已在**数据侧**修正，而不是在页面里除 1000。
	 *    3. 薪资是**区间重叠**语义（服务端 25-45K 的职位也会命中 20-30K 的筛选），
	 *       因此面板里不写「薪资在此区间内」这类会引发误解的文案。
	 *
	 * ⚠️ 三态齐全：首屏失败给整页重试，触底加载失败只在底部提示（已加载的数据不清空）。
	 */
	import { getJobList, getJobCategories, getCities, getJobFilters, toggleFavorite } from '@/services/job.js'
	import { isLogined } from '@/services/user.js'

	/** 排序项：服务端接受 default/salary/new/hot 四个值 */
	const SORT_OPTIONS = [
		{ label: '综合排序', value: 'default' },
		{ label: '薪资最高', value: 'salary' },
		{ label: '最新发布', value: 'new' },
		{ label: '最热职位', value: 'hot' }
	]

	/** kind → 中文（服务端只给值不给名，列表标签的名字在首页接口里，这里按同一口径复述） */
	const KIND_TEXT = {
		all: '全部职位',
		normal: '社招全职',
		urgent: '急招',
		referral: '名企内推',
		intern: '实习',
		campus: '校招'
	}

	export default {
		data() {
			return {
				statusBarHeight: 0,
				// ---------- 筛选条件（初始值来自 onLoad 的 options） ----------
				keyword: '',
				categoryId: '',
				categoryName: '',
				activeParentId: '',
				activeParentName: '',
				cityId: '',
				cityName: '',
				kind: '',
				salaryLabel: '',
				salaryMin: 0, // 单位 K
				salaryMax: 0, // 单位 K，0 表示不限
				experience: '',
				education: '',
				sort: 'default',
				// ---------- 列表数据 ----------
				list: [],
				total: 0,
				page: 1,
				pageSize: 10,
				hasMore: false,
				loading: false,
				loadingMore: false,
				loadFailed: false,
				loadMoreFailed: false,
				// ---------- 筛选项数据 ----------
				categoryList: [],
				cities: { hot: [], groups: [] },
				filters: { salary: [], experience: [], education: [] },
				optionsLoaded: false,
				optionsFailed: false,
				// ---------- 弹层 ----------
				panel: '', // '' | category / city / salary / experience / education / sort
				filterDefs: [
					{ key: 'category', label: '职能' },
					{ key: 'city', label: '城市' },
					{ key: 'salary', label: '薪资' },
					{ key: 'experience', label: '经验' },
					{ key: 'education', label: '学历' },
					{ key: 'sort', label: '排序' }
				]
			}
		},
		computed: {
			searchText() {
				return this.keyword || '搜索职位 / 公司'
			},
			kindText() {
				return KIND_TEXT[this.kind] || this.kind
			},
			hasAnyFilter() {
				return !!(this.categoryId || this.cityId || this.kind || this.salaryLabel ||
					this.experience || this.education || this.sort !== 'default')
			},
			panelTitle() {
				return {
					category: '选择职能',
					city: '选择城市',
					salary: '期望薪资',
					experience: '工作经验',
					education: '学历要求',
					sort: '排序方式'
				}[this.panel] || ''
			},
			/** 当前一级分类下的二级分类 */
			subList() {
				const parent = this.categoryList.filter(c => c.id === this.activeParentId)[0]
				return (parent && parent.children) || []
			},
			/** 当前弹层要渲染的选项列表（薪资/经验/学历用接口数据，排序用本地常量） */
			currentOptions() {
				if (this.panel === 'salary') return this.salaryOptions
				if (this.panel === 'experience') return this.toOptions(this.filters.experience)
				if (this.panel === 'education') return this.toOptions(this.filters.education)
				if (this.panel === 'sort') return SORT_OPTIONS
				return []
			},
			/**
			 * 薪资档位：原样透传（单位已是 K，与 /job/list 同口径）
			 *
			 * ⚠️ 这里刻意不做单位换算，原因见文件头注释第 2 条。
			 */
			salaryOptions() {
				const rows = this.filters.salary || []
				return rows.map(row => ({
					label: row.label,
					min: Number(row.min) || 0,
					max: Number(row.max) || 0
				}))
			}
		},
		onLoad(options) {
			this.statusBarHeight = uni.getSystemInfoSync().statusBarHeight || 0
			const q = options || {}
			// 四个初始筛选条件都由入口页面通过 query 带过来；uni 已对 query 做了解码
			this.keyword = q.keyword ? String(q.keyword) : ''
			this.cityId = q.city ? String(q.city) : ''
			this.cityName = q.cityName ? String(q.cityName) : ''
			this.kind = q.kind ? String(q.kind) : ''
			if (q.category) {
				this.categoryId = String(q.category)
				this.categoryName = q.categoryName ? String(q.categoryName) : ''
			}
			this.loadOptions()
			this.refresh()
		},
		async onPullDownRefresh() {
			try {
				await this.refresh()
			} finally {
				uni.stopPullDownRefresh()
			}
		},
		onReachBottom() {
			this.loadMore()
		},
		methods: {
			/* ---------------- 列表数据 ---------------- */
			buildParams(page) {
				const p = { page: page, pageSize: this.pageSize }
				if (this.keyword) p.keyword = this.keyword
				if (this.categoryId) p.category = this.categoryId
				if (this.cityId) p.city = this.cityId
				if (this.kind && this.kind !== 'all') p.kind = this.kind
				// 0 表示「不限」，不要发出去（服务端也只是把 0 当不限，发了纯属噪音）
				if (this.salaryMin) p.salaryMin = this.salaryMin
				if (this.salaryMax) p.salaryMax = this.salaryMax
				// 「不限」类选项服务端会忽略，但没必要发
				if (this.experience && this.experience !== '经验不限') p.experience = this.experience
				if (this.education && this.education !== '学历不限') p.education = this.education
				if (this.sort && this.sort !== 'default') p.sort = this.sort
				return p
			},
			async refresh() {
				this.loading = true
				this.loadFailed = false
				this.loadMoreFailed = false
				try {
					const res = await getJobList(this.buildParams(1))
					this.list = res.list || []
					this.total = Number(res.total) || 0
					this.page = Number(res.page) || 1
					this.hasMore = !!res.hasMore
				} catch (e) {
					// 首屏失败：整页进入失败态（错误提示已由请求层统一弹出）
					this.list = []
					this.total = 0
					this.hasMore = false
					this.loadFailed = true
				} finally {
					this.loading = false
				}
			},
			async loadMore() {
				if (this.loading || this.loadingMore || !this.hasMore) return
				this.loadingMore = true
				this.loadMoreFailed = false
				try {
					const next = this.page + 1
					const res = await getJobList(this.buildParams(next))
					this.list = this.list.concat(res.list || [])
					this.page = Number(res.page) || next
					this.hasMore = !!res.hasMore
				} catch (e) {
					// 触底失败：保留已加载的职位，只在底部给重试，避免把用户已经看的内容清掉
					this.loadMoreFailed = true
				} finally {
					this.loadingMore = false
				}
			},

			/* ---------------- 筛选项 ---------------- */
			async loadOptions() {
				this.optionsFailed = false
				// 三个接口互相独立：用 allSettled 语义分别兜住，避免一个挂了整组不可用
				const [cat, city, filter] = await Promise.all([
					getJobCategories().catch(() => null),
					getCities().catch(() => null),
					getJobFilters().catch(() => null)
				])
				if (cat) this.categoryList = cat.list || []
				if (city) this.cities = { hot: city.hot || [], groups: city.groups || [] }
				if (filter && filter.filters) this.filters = filter.filters
				this.optionsLoaded = true
				if (!cat && !city && !filter) this.optionsFailed = true
				this.resolveNames()
			},
			/**
			 * 补齐筛选栏文案
			 * 从首页轮播/职能入口进来时只有 category id（链接里不带名字），
			 * 若不补齐，筛选栏会显示成默认的「职能」而看不出当前选中了什么。
			 */
			resolveNames() {
				if (this.categoryId && !this.categoryName) {
					const all = this.categoryList.reduce(
						(acc, c) => acc.concat([c], c.children || []),
						[]
					)
					const hit = all.filter(c => c.id === this.categoryId)[0]
					if (hit) this.categoryName = hit.name
				}
				if (this.cityId && !this.cityName) {
					const all = this.cities.hot.concat(
						this.cities.groups.reduce((acc, g) => acc.concat(g.cities || []), [])
					)
					const hit = all.filter(c => c.id === this.cityId)[0]
					if (hit) this.cityName = hit.name
				}
			},
			/** 字符串枚举 → {label} 选项（薪资档位结构不同，走 salaryOptions 计算属性） */
			toOptions(list) {
				return (list || []).map(label => ({ label: label }))
			},

			/* ---------------- 弹层交互 ---------------- */
			openPanel(key) {
				this.panel = key
				// 打开职能面板时，默认展开当前已选中的一级分类，减少一次点击
				if (key === 'category' && !this.activeParentId && this.categoryList.length) {
					const hit = this.categoryList.filter(c => (c.children || []).some(s => s.id === this.categoryId))[0]
					this.activeParentId = hit ? hit.id : this.categoryList[0].id
					this.activeParentName = hit ? hit.name : this.categoryList[0].name
				}
				if (key !== 'sort' && !this.optionsLoaded) this.loadOptions()
			},
			closePanel() {
				this.panel = ''
			},
			selectParent(c) {
				this.activeParentId = c.id
				this.activeParentName = c.name
			},
			pickCategory(id, name) {
				// id 为空＝不限职能；一级分类 id 交给服务端自动展开为全部子类
				this.categoryId = id || ''
				this.categoryName = name || ''
				this.closePanel()
				this.refresh()
			},
			pickCity(c) {
				this.cityId = c ? c.id : ''
				this.cityName = c ? c.name : ''
				this.closePanel()
				this.refresh()
			},
			pickOption(opt) {
				if (this.panel === 'salary') {
					this.salaryLabel = opt.label
					this.salaryMin = opt.min || 0
					this.salaryMax = opt.max || 0
				} else if (this.panel === 'experience') {
					this.experience = opt.label
				} else if (this.panel === 'education') {
					this.education = opt.label
				} else if (this.panel === 'sort') {
					this.sort = opt.value
				}
				this.closePanel()
				this.refresh()
			},
			isOptionActive(opt) {
				if (this.panel === 'salary') return this.salaryLabel === opt.label
				if (this.panel === 'experience') return this.experience === opt.label
				if (this.panel === 'education') return this.education === opt.label
				if (this.panel === 'sort') return this.sort === opt.value
				return false
			},
			clearKind() {
				this.kind = ''
				this.refresh()
			},
			resetAll() {
				this.categoryId = ''
				this.categoryName = ''
				this.activeParentId = ''
				this.activeParentName = ''
				this.cityId = ''
				this.cityName = ''
				this.kind = ''
				this.salaryLabel = ''
				this.salaryMin = 0
				this.salaryMax = 0
				this.experience = ''
				this.education = ''
				this.sort = 'default'
				this.closePanel()
				this.refresh()
			},

			/* ---------------- 筛选栏文案 ---------------- */
			isFilterActive(key) {
				if (key === 'category') return !!this.categoryId
				if (key === 'city') return !!this.cityId
				if (key === 'salary') return !!this.salaryLabel && this.salaryLabel !== '薪资不限'
				if (key === 'experience') return !!this.experience && this.experience !== '经验不限'
				if (key === 'education') return !!this.education && this.education !== '学历不限'
				if (key === 'sort') return this.sort !== 'default'
				return false
			},
			filterLabel(key) {
				if (key === 'category') return this.categoryName || '职能'
				if (key === 'city') return this.cityName || '城市'
				if (key === 'salary') return this.salaryLabel || '薪资'
				if (key === 'experience') return this.experience || '经验'
				if (key === 'education') return this.education || '学历'
				if (key === 'sort') {
					const hit = SORT_OPTIONS.filter(s => s.value === this.sort)[0]
					return hit && this.sort !== 'default' ? hit.label : '排序'
				}
				return ''
			},

			/* ---------------- 跳转与收藏 ---------------- */
			goBack() {
				if (getCurrentPages().length > 1) {
					uni.navigateBack({ delta: 1 })
				} else {
					uni.reLaunch({ url: '/pages/index/index' })
				}
			},
			goSearch() {
				const q = this.keyword ? '?keyword=' + encodeURIComponent(this.keyword) : ''
				uni.navigateTo({ url: '/pages/job/search' + q })
			},
			goDetail(job) {
				if (!job || !job.id) return
				uni.navigateTo({ url: '/pages/job/detail?id=' + encodeURIComponent(job.id) })
			},
			async onFavorite(job) {
				if (!isLogined()) {
					uni.showToast({ title: '登录后才能收藏职位', icon: 'none' })
					setTimeout(() => uni.navigateTo({ url: '/pages/login/login' }), 800)
					return
				}
				try {
					const next = await toggleFavorite(job.id, job.isFavorite)
					job.isFavorite = next
					uni.showToast({ title: next ? '已收藏' : '已取消收藏', icon: 'none' })
				} catch (e) {
					// 提示已由请求层给出，本地状态保持不变
				}
			}
		}
	}
</script>

<style lang="scss" scoped>
	.jlist {
		background-color: $zn-bg-page;
	}

	/* ==================== 顶部 ==================== */
	.jlist__nav {
		position: sticky;
		top: 0;
		z-index: 20;
		background-color: $zn-bg-card;
		box-shadow: $zn-shadow-sm;
	}

	.jlist__navrow {
		height: 88rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 0 $zn-page-padding;
	}

	.jlist__back {
		width: 56rpx;
		height: 56rpx;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-right: 8rpx;
	}

	.jlist__search {
		flex: 1;
		min-width: 0;
		height: 64rpx;
		background-color: $zn-bg-grey;
		border-radius: $zn-radius-pill;
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 0 20rpx;
	}

	.jlist__search-text {
		flex: 1;
		min-width: 0;
		margin-left: 10rpx;
		font-size: 26rpx;
		color: $zn-text-main;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;

		&.is-ph {
			color: $zn-text-light;
		}
	}

	.jlist__bar {
		white-space: nowrap;
		padding-bottom: 14rpx;
	}

	.jlist__barrow {
		display: flex;
		flex-direction: row;
		padding: 0 $zn-page-padding;
	}

	.jlist__filter {
		display: flex;
		flex-direction: row;
		align-items: center;
		flex-shrink: 0;
		max-width: 220rpx;
		height: 56rpx;
		padding: 0 18rpx;
		margin-right: 14rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;

		&.is-active {
			background-color: $zn-theme-light;
		}
	}

	.jlist__filter-text {
		font-size: 24rpx;
		color: $zn-text-sub;
		margin-right: 6rpx;
		max-width: 170rpx;
	}

	.jlist__filter.is-active .jlist__filter-text {
		color: $zn-theme;
		font-weight: 600;
	}

	/* ==================== 概要 ==================== */
	.jlist__summary {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 20rpx $zn-page-padding 12rpx;
	}

	.jlist__count {
		font-size: 24rpx;
		color: $zn-text-sub;
	}

	.jlist__chip {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-left: 16rpx;
		padding: 4rpx 12rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-theme-light;
	}

	.jlist__chip-text {
		font-size: 22rpx;
		color: $zn-theme-dark;
		margin-right: 4rpx;
	}

	.jlist__reset {
		margin-left: auto;
	}

	.jlist__reset-text {
		font-size: 22rpx;
		color: $zn-theme;
	}

	/* ==================== 列表 ==================== */
	.jlist__body {
		padding: 0 $zn-page-padding 20rpx;
	}

	.jlist__item {
		margin-bottom: $zn-gap;
	}

	.state {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 28rpx $zn-gap;
		box-shadow: $zn-shadow-sm;
	}

	.state__text {
		font-size: 26rpx;
		color: $zn-text-sub;
		margin-left: 10rpx;
	}

	.more {
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 10rpx 0 30rpx;
	}

	.more__text {
		font-size: 24rpx;
		color: $zn-text-light;

		&--tap {
			color: $zn-theme;
		}
	}

	/* ==================== 弹层 ==================== */
	.panel {
		position: fixed;
		left: 0;
		right: 0;
		top: 0;
		bottom: 0;
		z-index: 900;
	}

	.panel__mask {
		position: absolute;
		left: 0;
		right: 0;
		top: 0;
		bottom: 0;
		background-color: $zn-mask;
	}

	.panel__sheet {
		position: absolute;
		left: 0;
		right: 0;
		bottom: 0;
		background-color: $zn-bg-card;
		border-top-left-radius: $zn-radius-xl;
		border-top-right-radius: $zn-radius-xl;
		padding-bottom: 40rpx;
		overflow: hidden;
	}

	.panel__head {
		height: 96rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		padding: 0 $zn-page-padding;
		border-bottom: 1rpx solid $zn-line;
	}

	.panel__title {
		font-size: $zn-font-lg;
		font-weight: 600;
		color: $zn-text-title;
	}

	.panel__close {
		width: 56rpx;
		height: 56rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.panel__sub {
		font-size: 24rpx;
		color: $zn-text-grey;
		padding: 20rpx $zn-page-padding 10rpx;
	}

	/* 城市面板要能滚：给固定高度，scroll-y 才有可视区域做滚动 */
	.panel__scroll {
		height: 640rpx;
	}

	/* ---------- 职能两级 ---------- */
	.cat {
		display: flex;
		flex-direction: row;
		height: 640rpx;
	}

	.cat__left {
		width: 220rpx;
		height: 640rpx;
		background-color: $zn-bg-grey;
	}

	.cat__l1 {
		height: 96rpx;
		display: flex;
		align-items: center;
		padding: 0 24rpx;

		&.is-active {
			background-color: $zn-bg-card;
		}
	}

	.cat__l1-text {
		font-size: 26rpx;
		color: $zn-text-sub;
	}

	.cat__l1.is-active .cat__l1-text {
		color: $zn-theme-dark;
		font-weight: 600;
	}

	.cat__right {
		flex: 1;
		min-width: 0;
		height: 640rpx;
	}

	.cat__l2 {
		height: 92rpx;
		display: flex;
		align-items: center;
		padding: 0 $zn-page-padding;
		border-bottom: 1rpx solid $zn-line;

		&.is-active {
			background-color: $zn-theme-lighter;
		}
	}

	.cat__l2-text {
		font-size: 26rpx;
		color: $zn-text-main;
	}

	.cat__l2.is-active .cat__l2-text {
		color: $zn-theme;
		font-weight: 600;
	}

	/* ---------- 城市网格 ---------- */
	.city__block {
		padding-bottom: 10rpx;
	}

	.grid {
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		padding: 0 14rpx;
	}

	.grid__item {
		width: 30.6%;
		margin: 0 1.3% 14rpx;
		height: 68rpx;
		border-radius: $zn-radius-sm;
		background-color: $zn-bg-grey;
		display: flex;
		align-items: center;
		justify-content: center;

		&.is-active {
			background-color: $zn-theme-light;
		}
	}

	.grid__text {
		font-size: 24rpx;
		color: $zn-text-main;
	}

	.grid__item.is-active .grid__text {
		color: $zn-theme-dark;
		font-weight: 600;
	}

	/* ---------- 单列选项 ---------- */
	.opt {
		height: 92rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		padding: 0 $zn-page-padding;
		border-bottom: 1rpx solid $zn-line;
	}

	.opt__text {
		font-size: 26rpx;
		color: $zn-text-main;
	}

	.opt.is-active .opt__text {
		color: $zn-theme;
		font-weight: 600;
	}
</style>
