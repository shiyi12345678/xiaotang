<template>
	<view class="zn-page zn-page--no-tabbar hredit">
		<zn-nav-bar :title="isEdit ? '编辑职位' : '发布职位'" :show-back="true" border />

		<!-- ==================== 一、加载中 ==================== -->
		<view v-if="loading" class="hredit__state">
			<text class="hredit__state-text">正在加载职位信息…</text>
		</view>

		<!-- ==================== 二、加载失败：可重试 ====================
			 ⚠️ 编辑模式下取不到完整职位内容时**不能进入表单**：
			    updateJob 是全量覆盖，拿摘要（descriptionText 只有 80 字）回填后提交
			    会把岗位职责 / 任职要求 / 招聘流程清空，所以这里宁可挡住保存。 -->
		<zn-empty v-else-if="failed" icon="info" text="职位信息加载失败" :desc="failedMsg"
			btn-text="重新加载" @action="init" />

		<!-- ==================== 三、表单 ==================== -->
		<block v-else>
			<!-- ---------- 1. 基本信息 ---------- -->
			<view class="sec">
				<zn-section-header title="基本信息" />
				<view class="field">
					<text class="field__label">职位名称<text class="field__req">*</text></text>
					<input class="field__input" v-model="form.title" :maxlength="80"
						placeholder="如：Java 后端开发工程师" placeholder-class="field__ph" />
					<text class="field__count">{{ form.title.length }}/80</text>
				</view>

				<view class="field">
					<text class="field__label">职能分类<text class="field__req">*</text></text>
					<picker mode="selector" :range="categoryLabels" :value="categoryIndex"
						@change="onCategoryChange">
						<view class="field__picker">
							<text class="field__picker-text" :class="{ 'is-ph': !form.categoryId }">
								{{ categoryText || '请选择二级职能' }}
							</text>
							<uni-icons type="right" :size="14" color="#bbbbbb"></uni-icons>
						</view>
					</picker>
					<!-- 服务端只接受**二级**职能（job.py 校验 category.level == 2，否则 40011），
						 所以一级分类只作为选择器里的分组前缀，绝不会作为 categoryId 提交。 -->
					<text class="field__tip">一级职能仅作分组，实际提交的是二级职能</text>
				</view>

				<view class="field">
					<text class="field__label">工作城市<text class="field__req">*</text></text>
					<view v-if="hotCities.length" class="chips">
						<view v-for="c in hotCities" :key="c.id" class="chip"
							:class="{ 'is-on': form.cityId === c.id }" hover-class="zn-hover"
							@tap="pickCity(c)">
							<text class="chip__text">{{ c.name }}</text>
						</view>
						<picker mode="selector" :range="cityNames" :value="cityIndex" @change="onCityChange">
							<view class="chip chip--more" hover-class="zn-hover">
								<text class="chip__text">其他城市</text>
							</view>
						</picker>
					</view>
					<picker v-else mode="selector" :range="cityNames" :value="cityIndex" @change="onCityChange">
						<view class="field__picker">
							<text class="field__picker-text" :class="{ 'is-ph': !form.cityId }">
								{{ cityText || '请选择城市' }}
							</text>
							<uni-icons type="right" :size="14" color="#bbbbbb"></uni-icons>
						</view>
					</picker>
					<text v-if="form.cityId" class="field__tip">已选：{{ cityText }}</text>
				</view>

				<view class="field">
					<text class="field__label">所在区域</text>
					<input class="field__input" v-model="form.district" :maxlength="30"
						placeholder="如：海淀区（选填）" placeholder-class="field__ph" />
				</view>
			</view>

			<!-- ---------- 2. 薪资与要求 ---------- -->
			<view class="sec">
				<zn-section-header title="薪资与要求" />
				<view class="field">
					<text class="field__label">薪资范围（K）<text class="field__req">*</text></text>
					<view class="salary">
						<input class="salary__input" v-model="form.salaryMin" type="number" :maxlength="3"
							placeholder="最低" placeholder-class="field__ph" />
						<text class="salary__dash">—</text>
						<input class="salary__input" v-model="form.salaryMax" type="number" :maxlength="3"
							placeholder="最高" placeholder-class="field__ph" />
						<picker mode="selector" :range="monthOptions" :value="monthsIndex"
							@change="onMonthsChange">
							<view class="salary__months">
								<text class="salary__months-text">{{ form.salaryMonths }} 薪</text>
								<uni-icons type="arrow-down" :size="12" color="#999999"></uni-icons>
							</view>
						</picker>
					</view>
					<text class="field__tip">单位 K（千元/月），下限必须小于上限</text>
				</view>

				<view class="field-row">
					<view class="field field--half">
						<text class="field__label">经验要求</text>
						<picker mode="selector" :range="experienceOptions" :value="experienceIndex"
							@change="onExperienceChange">
							<view class="field__picker">
								<text class="field__picker-text">{{ form.experience }}</text>
								<uni-icons type="arrow-down" :size="12" color="#999999"></uni-icons>
							</view>
						</picker>
					</view>
					<view class="field field--half">
						<text class="field__label">学历要求</text>
						<picker mode="selector" :range="educationOptions" :value="educationIndex"
							@change="onEducationChange">
							<view class="field__picker">
								<text class="field__picker-text">{{ form.education }}</text>
								<uni-icons type="arrow-down" :size="12" color="#999999"></uni-icons>
							</view>
						</picker>
					</view>
				</view>

				<view class="field-row">
					<view class="field field--half">
						<text class="field__label">职位形态</text>
						<picker mode="selector" :range="jobTypeLabels" :value="jobTypeIndex"
							@change="onJobTypeChange">
							<view class="field__picker">
								<text class="field__picker-text">{{ jobTypeText }}</text>
								<uni-icons type="arrow-down" :size="12" color="#999999"></uni-icons>
							</view>
						</picker>
					</view>
					<view class="field field--half">
						<text class="field__label">职位标签</text>
						<picker mode="selector" :range="kindLabels" :value="kindIndex" @change="onKindChange">
							<view class="field__picker">
								<text class="field__picker-text">{{ kindText }}</text>
								<uni-icons type="arrow-down" :size="12" color="#999999"></uni-icons>
							</view>
						</picker>
					</view>
				</view>
			</view>

			<!-- ---------- 3. 技能标签 ---------- -->
			<view class="sec">
				<zn-section-header title="技能标签" subtitle="最多 10 个" />
				<view v-if="form.tags.length" class="chips chips--wrap">
					<view v-for="(tag, i) in form.tags" :key="tag + i" class="chip chip--tag" hover-class="zn-hover"
						@tap="removeTag(i)">
						<text class="chip__text">{{ tag }}</text>
						<uni-icons type="clear" :size="12" color="#00A6A7"></uni-icons>
					</view>
				</view>
				<view class="adder">
					<input class="adder__input" v-model="tagInput" :maxlength="12" placeholder="如：Spring Boot"
						placeholder-class="field__ph" @confirm="addTag" />
					<view class="adder__btn" hover-class="zn-hover" @tap="addTag">
						<text class="adder__btn-text">添加</text>
					</view>
				</view>
			</view>

			<!-- ---------- 4. 岗位职责 ---------- -->
			<view class="sec">
				<zn-section-header title="岗位职责" />
				<textarea class="form__textarea" v-model="form.description" :maxlength="4000"
					placeholder="请按「1. 」「2. 」分条填写，如：&#10;1. 负责招聘业务后端的接口设计与开发&#10;2. 参与系统性能优化与线上问题排查"
					placeholder-class="field__ph" />
				<view class="form__textarea-foot">
					<text class="field__tip">每条以「1. 」「2. 」开头，详情页会自动渲染成列表</text>
					<text class="field__count">{{ form.description.length }}/4000</text>
				</view>
			</view>

			<!-- ---------- 5. 任职要求 ---------- -->
			<view class="sec">
				<zn-section-header title="任职要求" />
				<textarea class="form__textarea" v-model="form.requirements" :maxlength="4000"
					placeholder="请按「1. 」「2. 」分条填写，如：&#10;1. 本科及以上学历，3 年以上 Java 开发经验&#10;2. 熟悉 MySQL、Redis 与常用中间件"
					placeholder-class="field__ph" />
				<view class="form__textarea-foot">
					<text class="field__tip">同上，分条填写更易被候选人读完</text>
					<text class="field__count">{{ form.requirements.length }}/4000</text>
				</view>
			</view>

			<!-- ---------- 6. 招聘流程 ---------- -->
			<view class="sec">
				<zn-section-header title="招聘流程" subtitle="按顺序添加环节" />
				<view v-if="form.process.length" class="steps">
					<view v-for="(step, i) in form.process" :key="step + i" class="step">
						<text class="step__index">{{ i + 1 }}</text>
						<text class="step__text zn-ellipsis">{{ step }}</text>
						<view class="step__del" hover-class="zn-hover" @tap="removeStep(i)">
							<uni-icons type="clear" :size="14" color="#999999"></uni-icons>
						</view>
					</view>
				</view>
				<view class="chips chips--wrap">
					<view v-for="p in stepPresets" :key="p" class="chip" hover-class="zn-hover" @tap="addPresetStep(p)">
						<text class="chip__text">+ {{ p }}</text>
					</view>
				</view>
				<view class="adder">
					<input class="adder__input" v-model="stepInput" :maxlength="20" placeholder="自定义环节名称"
						placeholder-class="field__ph" @confirm="addStep" />
					<view class="adder__btn" hover-class="zn-hover" @tap="addStep">
						<text class="adder__btn-text">添加</text>
					</view>
				</view>
			</view>

			<!-- ---------- 7. 发布设置 ---------- -->
			<view class="sec">
				<zn-section-header title="发布设置" />
				<view class="modes">
					<view class="mode" :class="{ 'is-on': form.status === 1 }" hover-class="zn-hover"
						@tap="form.status = 1">
						<text class="mode__title">立即上架</text>
						<text class="mode__desc">求职者可以搜到并投递该职位</text>
					</view>
					<view class="mode" :class="{ 'is-on': form.status === 0 }" hover-class="zn-hover"
						@tap="form.status = 0">
						<text class="mode__title">存为草稿</text>
						<text class="mode__desc">先不上架，之后在职位管理里上架</text>
					</view>
				</view>
			</view>

			<!-- 底部留白，避免被固定操作条挡住 -->
			<view class="hredit__gap"></view>
		</block>

		<!-- ==================== 底部固定操作条 ==================== -->
		<view v-if="!loading && !failed" class="bar">
			<view class="bar__hint">
				<text class="bar__hint-text">{{ isEdit ? '编辑后保存立即生效' : '保存后可在职位管理中随时修改' }}</text>
			</view>
			<view class="bar__btn" :class="{ 'is-disabled': submitting }" hover-class="zn-hover" @tap="submit">
				<text class="bar__btn-text">{{ submitText }}</text>
			</view>
		</view>
	</view>
</template>

<script>
	/**
	 * 发布 / 编辑职位
	 *
	 * 接口：POST /hr/jobs（createJob）/ PUT /hr/jobs/{id}（updateJob）
	 *   两者入参完全一致，且**都是全量覆盖**（不是 PATCH）。
	 *
	 * ⚠️ 编辑时「怎么取到完整职位内容」——本页的做法与理由：
	 *    1. 职位管理列表（GET /hr/jobs）只回 descriptionText（正文前 80 字），
	 *       不含 requirements 与 process，而 updateJob 是全量覆盖，
	 *       拿列表数据回填再提交会把正文清空 —— 所以不能只用列表数据。
	 *    2. 因此：列表页把该条职位缓存到 uni.setStorageSync('zn_hr_editing_job')，
	 *       本页先读缓存**立即回填基础字段**（首屏不白屏），
	 *       再调公开只读接口 GET /job/detail/{id}（services/job.js → getJobDetail）
	 *       取权威数据（含 description/requirements/process）覆盖表单。
	 *    3. 代价（如实说明）：/job/detail 有「浏览量 +1」的副作用，HR 自己编辑也会涨一次；
	 *       本批次只能改 pages/hr 下的文件，HR 侧没有「取职位详情」的接口，
	 *       这是当前唯一能拿到正文的途径。
	 *    4. 若详情取不到（例如职位已被删除）→ 不进入表单，只给重试，
	 *       避免 HR 在内容不全的表单上点保存造成数据丢失。
	 *
	 * ⚠️ 前端校验只为即时反馈：服务端还会再校验一次
	 *    （schemas/hr.py 的 JobPostIn 长度/范围 + hr.py 的 _validate_job_input：
	 *     薪资 min<max、category 必须是 level==2、city 必须存在）。
	 *
	 * ⚠️ 不要传 companyId：职位归属只能来自你绑定的公司（服务端会忽略该字段）。
	 */
	import { createJob, updateJob } from '@/services/hr.js'
	import { getJobCategories, getCities, getJobDetail } from '@/services/job.js'

	/** 经验 / 学历枚举：必须与 services/hr.js 及服务端种子口径一致（中文枚举） */
	const EXPERIENCE = ['经验不限', '应届生', '1年以内', '1-3年', '3-5年', '5-10年', '10年以上']
	const EDUCATION = ['学历不限', '大专', '本科', '硕士', '博士']

	const JOB_TYPES = [
		{ label: '全职', value: 'fulltime' },
		{ label: '实习', value: 'intern' },
		{ label: '兼职', value: 'parttime' }
	]

	/** 职位形态角标 kind：普通职位不展示角标 */
	const KINDS = [
		{ label: '普通职位', value: 'normal' },
		{ label: '急招', value: 'urgent' },
		{ label: '名企内推', value: 'referral' },
		{ label: '实习', value: 'intern' },
		{ label: '校招', value: 'campus' }
	]

	/** 薪资月数 12~20（服务端 salaryMonths ge=12 le=20） */
	const MONTHS = [12, 13, 14, 15, 16, 17, 18, 19, 20]

	/** 招聘流程快捷步骤（可点选追加，也可自定义输入） */
	const STEP_PRESETS = ['简历筛选', '一面', '二面', 'HR面', '发offer']

	export default {
		data() {
			return {
				isEdit: false,
				jobId: '',
				loading: true,
				ready: false, // 首次加载完成为 true；重试时不再整屏转圈
				failed: false,
				failedMsg: '',
				submitting: false,

				experienceOptions: EXPERIENCE,
				educationOptions: EDUCATION,
				jobTypeLabels: JOB_TYPES.map(i => i.label),
				kindLabels: KINDS.map(i => i.label),
				monthOptions: MONTHS.map(m => m + ' 薪'),
				stepPresets: STEP_PRESETS,

				form: {
					title: '',
					categoryId: '',
					cityId: '',
					district: '',
					salaryMin: '',
					salaryMax: '',
					salaryMonths: 12,
					experience: EXPERIENCE[0],
					education: EDUCATION[0],
					jobType: 'fulltime',
					kind: 'normal',
					tags: [],
					description: '',
					requirements: '',
					process: [],
					status: 1
				},

				categoryOptions: [], // [{id,label}]，label 形如「技术 · 后端开发」
				cities: [], // getCities().all
				hotCities: [], // getCities().hot

				tagInput: '',
				stepInput: ''
			}
		},
		computed: {
			categoryLabels() {
				return this.categoryOptions.map(o => o.label)
			},
			categoryIndex() {
				const i = this.categoryOptions.findIndex(o => o.id === this.form.categoryId)
				return i < 0 ? 0 : i
			},
			categoryText() {
				const hit = this.categoryOptions.find(o => o.id === this.form.categoryId)
				return hit ? hit.label : ''
			},
			cityNames() {
				return this.cities.map(c => c.name)
			},
			cityIndex() {
				const i = this.cities.findIndex(c => c.id === this.form.cityId)
				return i < 0 ? 0 : i
			},
			cityText() {
				const hit = this.cities.find(c => c.id === this.form.cityId)
				return hit ? hit.name : ''
			},
			monthsIndex() {
				const i = MONTHS.indexOf(Number(this.form.salaryMonths))
				return i < 0 ? 0 : i
			},
			experienceIndex() {
				const i = EXPERIENCE.indexOf(this.form.experience)
				return i < 0 ? 0 : i
			},
			educationIndex() {
				const i = EDUCATION.indexOf(this.form.education)
				return i < 0 ? 0 : i
			},
			jobTypeIndex() {
				const i = JOB_TYPES.findIndex(t => t.value === this.form.jobType)
				return i < 0 ? 0 : i
			},
			jobTypeText() {
				const hit = JOB_TYPES.find(t => t.value === this.form.jobType)
				return hit ? hit.label : '全职'
			},
			kindIndex() {
				const i = KINDS.findIndex(k => k.value === this.form.kind)
				return i < 0 ? 0 : i
			},
			kindText() {
				const hit = KINDS.find(k => k.value === this.form.kind)
				return hit ? hit.label : '普通职位'
			},
			submitText() {
				if (this.submitting) return '保存中…'
				if (this.isEdit) return '保存修改'
				return this.form.status === 1 ? '发布职位' : '存为草稿'
			}
		},
		onLoad(options) {
			this.jobId = (options && options.id) || ''
			this.isEdit = !!this.jobId
			this.init()
		},
		methods: {
			/* ================= 初始化 ================= */
			async init() {
				this.loading = !this.ready
				this.failed = false
				try {
					// 选项数据（职能 / 城市）与职位详情互不依赖，并发拉取
					const [cats, cities, detail] = await Promise.all([
						getJobCategories(),
						getCities(),
						this.isEdit ? getJobDetail(this.jobId) : Promise.resolve(null)
					])
					this.applyCategories(cats)
					this.cities = (cities && cities.all) || []
					this.hotCities = (cities && cities.hot) || []
					if (this.isEdit) {
						// 编辑模式必须拿到完整职位内容，否则不允许进入表单（见文件头说明）
						if (!detail || !detail.job) {
							throw new Error('职位不存在或已下线')
						}
						// 先用列表页缓存把基础字段铺上，再让详情覆盖（详情是权威值）
						this.applyCache()
						this.applyDetail(detail.job)
					}
				} catch (e) {
					this.failed = true
					this.failedMsg = (e && e.message) || '请检查服务端是否已启动'
				} finally {
					this.loading = false
					this.ready = true
				}
			},
			/** 把两级职能摊平成「一级 · 二级」的可选项（一级只出现在文案里，不作为 id 提交） */
			applyCategories(res) {
				const list = (res && res.list) || []
				const flat = (res && res.flat) || []
				const parentName = {}
				list.forEach(p => { parentName[p.id] = p.name })
				const source = flat.length ? flat : list
				this.categoryOptions = source.map(c => ({
					id: c.id,
					label: parentName[c.parentId] ? parentName[c.parentId] + ' · ' + c.name : c.name
				}))
			},
			/** 列表页缓存：只用于首屏快速回填，字段不全（没有正文） */
			applyCache() {
				let cached = null
				try {
					cached = uni.getStorageSync('zn_hr_editing_job')
				} catch (e) {
					cached = null
				}
				if (!cached || cached.id !== this.jobId) return
				this.fillForm(cached)
				// 用完即清，避免下次编辑另一个职位时被旧缓存误导
				try {
					uni.removeStorageSync('zn_hr_editing_job')
				} catch (e) {}
			},
			/**
			 * 用职位详情（job_detail）覆盖表单
			 * ⚠️ description / requirements 在详情里已被服务端切成数组（text_lines），
			 *    这里再拼回带序号的文本 —— 服务端提交时会重新切分，往返稳定不丢内容。
			 */
			applyDetail(job) {
				if (!job) return
				const data = Object.assign({}, job)
				data.description = (job.description || []).map((t, i) => (i + 1) + '. ' + t).join('\n')
				data.requirements = (job.requirements || []).map((t, i) => (i + 1) + '. ' + t).join('\n')
				data.process = job.process || []
				this.fillForm(data)
			},
			fillForm(src) {
				const f = this.form
				// 服务端薪资是数字 / 输入框是字符串，统一成字符串喂给 v-model
				const numText = v => (v === null || v === undefined || v === '') ? '' : String(v)
				f.title = src.title || ''
				f.categoryId = src.categoryId || ''
				f.cityId = src.cityId || ''
				f.district = src.district || ''
				f.salaryMin = numText(src.salaryMin)
				f.salaryMax = numText(src.salaryMax)
				f.salaryMonths = Number(src.salaryMonths) || 12
				f.experience = src.experience || EXPERIENCE[0]
				f.education = src.education || EDUCATION[0]
				f.jobType = src.jobType || 'fulltime'
				f.kind = src.kind || 'normal'
				f.tags = Array.isArray(src.tags) ? src.tags.slice() : []
				if (typeof src.description === 'string') f.description = src.description
				if (typeof src.requirements === 'string') f.requirements = src.requirements
				if (Array.isArray(src.process)) f.process = src.process.slice()
				f.status = src.status === 0 ? 0 : 1
			},

			/* ================= 选择器事件 ================= */
			onCategoryChange(e) {
				const item = this.categoryOptions[Number(e.detail.value)]
				if (item) this.form.categoryId = item.id
			},
			onCityChange(e) {
				const item = this.cities[Number(e.detail.value)]
				if (item) this.form.cityId = item.id
			},
			pickCity(c) {
				this.form.cityId = c.id
			},
			onMonthsChange(e) {
				this.form.salaryMonths = MONTHS[Number(e.detail.value)]
			},
			onExperienceChange(e) {
				this.form.experience = EXPERIENCE[Number(e.detail.value)]
			},
			onEducationChange(e) {
				this.form.education = EDUCATION[Number(e.detail.value)]
			},
			onJobTypeChange(e) {
				this.form.jobType = JOB_TYPES[Number(e.detail.value)].value
			},
			onKindChange(e) {
				this.form.kind = KINDS[Number(e.detail.value)].value
			},

			/* ================= 标签 / 流程 增删 ================= */
			addTag() {
				const text = (this.tagInput || '').trim()
				if (!text) return
				if (this.form.tags.length >= 10) {
					uni.showToast({ title: '最多 10 个标签', icon: 'none' })
					return
				}
				if (this.form.tags.indexOf(text) > -1) {
					uni.showToast({ title: '标签重复', icon: 'none' })
					return
				}
				this.form.tags.push(text)
				this.tagInput = ''
			},
			removeTag(i) {
				this.form.tags.splice(i, 1)
			},
			addStep() {
				const text = (this.stepInput || '').trim()
				if (!text) return
				if (this.form.process.indexOf(text) > -1) {
					uni.showToast({ title: '该环节已存在', icon: 'none' })
					return
				}
				this.form.process.push(text)
				this.stepInput = ''
			},
			addPresetStep(text) {
				if (this.form.process.indexOf(text) > -1) {
					uni.showToast({ title: '该环节已存在', icon: 'none' })
					return
				}
				this.form.process.push(text)
			},
			removeStep(i) {
				this.form.process.splice(i, 1)
			},

			/* ================= 校验与提交 ================= */
			/**
			 * 前端校验（只为即时反馈，服务端仍会再校验一次）
			 * @returns {string} 错误文案，空串表示通过
			 */
			validate() {
				const f = this.form
				const title = (f.title || '').trim()
				if (title.length < 2 || title.length > 80) return '职位名称需 2~80 个字'
				if (!f.categoryId) return '请选择职能分类'
				if (!f.cityId) return '请选择工作城市'
				const min = Number(f.salaryMin)
				const max = Number(f.salaryMax)
				if (!min || !max) return '请填写薪资范围'
				if (!(min >= 1 && min <= 500) || !(max >= 1 && max <= 500)) return '薪资需在 1~500K 之间'
				if (min >= max) return '薪资下限必须小于上限'
				const months = Number(f.salaryMonths)
				if (!(months >= 12 && months <= 20)) return '薪资月数需在 12~20 之间'
				if ((f.description || '').length > 4000) return '岗位职责超过 4000 字'
				if ((f.requirements || '').length > 4000) return '任职要求超过 4000 字'
				return ''
			},
			buildPayload() {
				const f = this.form
				return {
					title: (f.title || '').trim(),
					categoryId: f.categoryId,
					cityId: f.cityId,
					district: (f.district || '').trim(),
					salaryMin: Number(f.salaryMin),
					salaryMax: Number(f.salaryMax),
					salaryMonths: Number(f.salaryMonths),
					experience: f.experience,
					education: f.education,
					jobType: f.jobType,
					kind: f.kind,
					tags: f.tags.slice(),
					description: f.description || '',
					requirements: f.requirements || '',
					process: f.process.slice(),
					status: Number(f.status)
					// 不传 companyId：归属由服务端按绑定的公司决定
				}
			},
			async submit() {
				if (this.submitting) return
				const err = this.validate()
				if (err) {
					uni.showToast({ title: err, icon: 'none' })
					return
				}
				this.submitting = true
				const payload = this.buildPayload()
				try {
					if (this.isEdit) {
						await updateJob(this.jobId, payload)
					} else {
						await createJob(payload)
					}
					uni.showToast({
						title: this.isEdit ? '已保存' : (payload.status === 1 ? '职位已发布' : '已存为草稿'),
						icon: 'none'
					})
					// 留出 toast 时间再返回，避免用户看不到反馈
					setTimeout(() => this.back(), 600)
				} catch (e) {
					if (e && (e.code === 40301 || e.status === 403)) {
						uni.reLaunch({ url: '/pages/hr/bind' })
						return
					}
					// 其它错误（40010 薪资非法 / 40011 职能非二级 / 40012 城市非法 等）
					// 已由 services/api.js 统一弹出服务端 msg，这里不再重复提示
				} finally {
					this.submitting = false
				}
			},
			back() {
				// 从工作台 reLaunch 进来时栈里只有本页，navigateBack 会失败，此时退回职位管理
				if (getCurrentPages().length > 1) {
					uni.navigateBack({ delta: 1 })
				} else {
					uni.reLaunch({ url: '/pages/hr/jobs' })
				}
			}
		}
	}
</script>

<style lang="scss" scoped>
	.hredit {
		padding-bottom: 200rpx; /* 底部固定操作条 */
	}

	.hredit__state {
		padding: 160rpx 0;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.hredit__state-text {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
	}

	.hredit__gap {
		height: 40rpx;
	}

	/* ---------------- 分区 ---------------- */
	.sec {
		margin: $zn-gap-sm $zn-page-padding 0;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: 0 $zn-gap $zn-gap;
	}

	/* ---------------- 表单字段 ---------------- */
	.field {
		margin-top: $zn-gap-sm;
		position: relative;
	}

	.field--half {
		width: 48%;
	}

	.field-row {
		display: flex;
		flex-direction: row;
		justify-content: space-between;
	}

	.field__label {
		font-size: $zn-font-sm;
		color: $zn-text-sub;
	}

	.field__req {
		color: $zn-red;
		margin-left: 4rpx;
	}

	.field__input {
		margin-top: 12rpx;
		height: 84rpx;
		padding: 0 $zn-gap-sm;
		border-radius: $zn-radius;
		background-color: $zn-bg-grey;
		font-size: $zn-font;
		color: $zn-text-main;
	}

	.field__ph {
		color: $zn-text-light;
		font-size: $zn-font-sm;
	}

	.field__picker {
		margin-top: 12rpx;
		height: 84rpx;
		padding: 0 $zn-gap-sm;
		border-radius: $zn-radius;
		background-color: $zn-bg-grey;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.field__picker-text {
		flex: 1;
		min-width: 0;
		font-size: $zn-font;
		color: $zn-text-main;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;

		&.is-ph {
			color: $zn-text-light;
			font-size: $zn-font-sm;
		}
	}

	.field__tip {
		display: block;
		margin-top: 10rpx;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	.field__count {
		position: absolute;
		right: 4rpx;
		top: 0;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	/* ---------------- 薪资 ---------------- */
	.salary {
		margin-top: 12rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.salary__input {
		flex: 1;
		min-width: 0;
		height: 84rpx;
		padding: 0 $zn-gap-sm;
		border-radius: $zn-radius;
		background-color: $zn-bg-grey;
		font-size: $zn-font;
		color: $zn-text-main;
		text-align: center;
	}

	.salary__dash {
		margin: 0 12rpx;
		color: $zn-text-light;
	}

	.salary__months {
		margin-left: 12rpx;
		height: 84rpx;
		padding: 0 $zn-gap-sm;
		border-radius: $zn-radius;
		background-color: $zn-theme-light;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.salary__months-text {
		font-size: $zn-font-sm;
		color: $zn-theme-deep;
		margin-right: 6rpx;
	}

	/* ---------------- 标签 / 流程 芯片 ---------------- */
	.chips {
		margin-top: 12rpx;
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
		align-items: center;

		&--wrap {
			margin-top: $zn-gap-sm;
		}
	}

	.chip {
		margin: 0 12rpx 12rpx 0;
		height: 60rpx;
		padding: 0 22rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-bg-grey;
		border: 1rpx solid transparent;
		display: flex;
		flex-direction: row;
		align-items: center;

		&.is-on {
			background-color: $zn-theme-light;
			border-color: $zn-theme;
		}

		&--tag {
			background-color: $zn-theme-light;
		}

		&--more {
			background-color: $zn-bg-card;
			border-color: $zn-line;
		}
	}

	.chip__text {
		font-size: $zn-font-xs;
		color: $zn-text-sub;
	}

	.chip.is-on .chip__text,
	.chip--tag .chip__text {
		color: $zn-theme-deep;
	}

	/* ---------------- 增加项 ---------------- */
	.adder {
		margin-top: 12rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.adder__input {
		flex: 1;
		min-width: 0;
		height: 76rpx;
		padding: 0 $zn-gap-sm;
		border-radius: $zn-radius;
		background-color: $zn-bg-grey;
		font-size: $zn-font-sm;
		color: $zn-text-main;
	}

	.adder__btn {
		margin-left: 14rpx;
		height: 76rpx;
		padding: 0 28rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-theme-light;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.adder__btn-text {
		font-size: $zn-font-sm;
		color: $zn-theme-deep;
		font-weight: 600;
	}

	/* ---------------- 长文本 ---------------- */
	.form__textarea {
		margin-top: 12rpx;
		width: 100%;
		min-height: 260rpx;
		padding: $zn-gap-sm;
		border-radius: $zn-radius;
		background-color: $zn-bg-grey;
		font-size: $zn-font-sm;
		color: $zn-text-main;
		line-height: 44rpx;
	}

	.form__textarea-foot {
		margin-top: 10rpx;
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	/* ---------------- 招聘流程步骤 ---------------- */
	.steps {
		margin-top: $zn-gap-sm;
		display: flex;
		flex-direction: column;
	}

	.step {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 16rpx 0;
		border-bottom: 1rpx solid $zn-line;
	}

	.step__index {
		width: 40rpx;
		height: 40rpx;
		border-radius: 50%;
		background: $zn-gradient;
		color: #ffffff;
		font-size: $zn-font-xs;
		text-align: center;
		line-height: 40rpx;
		flex-shrink: 0;
	}

	.step__text {
		flex: 1;
		min-width: 0;
		margin-left: $zn-gap-sm;
		font-size: $zn-font-sm;
		color: $zn-text-main;
	}

	.step__del {
		width: 56rpx;
		height: 56rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	/* ---------------- 发布设置 ---------------- */
	.modes {
		margin-top: $zn-gap-sm;
		display: flex;
		flex-direction: column;
	}

	.mode {
		padding: $zn-gap-sm;
		border-radius: $zn-radius;
		border: 2rpx solid $zn-line;
		background-color: $zn-bg-page;
		margin-bottom: 16rpx;
		display: flex;
		flex-direction: column;

		&.is-on {
			border-color: $zn-theme;
			background-color: $zn-theme-lighter;
		}
	}

	.mode__title {
		font-size: $zn-font;
		font-weight: 600;
		color: $zn-text-title;
	}

	.mode__desc {
		margin-top: 6rpx;
		font-size: $zn-font-xs;
		color: $zn-text-grey;
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

	.bar__hint {
		flex: 1;
		min-width: 0;
	}

	.bar__hint-text {
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	.bar__btn {
		flex-shrink: 0;
		height: 84rpx;
		padding: 0 56rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		box-shadow: $zn-shadow-theme;

		&.is-disabled {
			opacity: 0.6;
		}
	}

	.bar__btn-text {
		font-size: $zn-font;
		font-weight: 600;
		color: #ffffff;
	}
</style>
