<template>
	<view class="zn-page zn-page--no-tabbar hrcomp">
		<zn-nav-bar title="企业主页维护" :show-back="true" border />

		<!-- ==================== 一、加载中 ==================== -->
		<view v-if="loading" class="hrcomp__state">
			<text class="hrcomp__state-text">正在加载公司信息…</text>
		</view>

		<!-- ==================== 二、加载失败：可重试 ==================== -->
		<zn-empty v-else-if="failed" icon="info" text="公司信息加载失败" :desc="failedMsg"
			btn-text="重新加载" @action="load" />

		<!-- ==================== 三、内容 ==================== -->
		<block v-else>
			<!-- ---------- 实时预览：企业主页长什么样 ---------- -->
			<view class="preview">
				<text class="preview__label">企业主页预览</text>
				<view class="preview__card">
					<zn-company-logo :text="form.logoText || form.shortName" :color="form.logoColor || '#00A6A7'"
						:size="104" />
					<view class="preview__main">
						<!-- 公司全称不可改（服务端 CompanyUpdateIn 没有 name 字段），这里展示真实全称 -->
						<text class="preview__name zn-ellipsis">{{ company.name || '公司全称' }}</text>
						<text v-if="form.shortName" class="preview__short zn-ellipsis">简称：{{ form.shortName }}</text>
						<text class="preview__meta zn-ellipsis">{{ previewMeta }}</text>
					</view>
				</view>
				<view v-if="form.benefits.length" class="preview__tags">
					<text v-for="(b, i) in form.benefits" :key="i" class="preview__tag">{{ b }}</text>
				</view>
				<text v-if="form.intro" class="preview__intro zn-ellipsis-2">{{ form.intro }}</text>
			</view>

			<!-- ---------- 基本信息 ---------- -->
			<view class="sec">
				<zn-section-header title="基本信息" />
				<view class="field">
					<text class="field__label">公司简称</text>
					<input class="field__input" v-model="form.shortName" :maxlength="30"
						placeholder="求职者列表上显示的名字，如：星野科技" placeholder-class="field__ph" />
				</view>

				<view class="field-row">
					<view class="field field--half">
						<text class="field__label">Logo 文字</text>
						<input class="field__input" v-model="form.logoText" :maxlength="4"
							placeholder="1~2 字，如：星野" placeholder-class="field__ph" />
					</view>
					<view class="field field--half">
						<text class="field__label">Logo 配色</text>
						<view class="colors">
							<view v-for="c in logoColors" :key="c" class="colors__item"
								:class="{ 'is-on': form.logoColor === c }" :style="{ backgroundColor: c }"
								hover-class="zn-hover" @tap="form.logoColor = c"></view>
						</view>
					</view>
				</view>
				<text class="field__tip">Logo 是零图片方案：主色底 + 文字占位（由 zn-company-logo 渲染）</text>

				<view class="field">
					<text class="field__label">所属行业</text>
					<input class="field__input" v-model="form.industry" :maxlength="30" placeholder="如：人工智能"
						placeholder-class="field__ph" />
					<view class="chips">
						<view v-for="it in industryPresets" :key="it" class="chip" hover-class="zn-hover"
							@tap="form.industry = it">
							<text class="chip__text">{{ it }}</text>
						</view>
					</view>
				</view>

				<view class="field-row">
					<view class="field field--half">
						<text class="field__label">公司规模</text>
						<picker mode="selector" :range="scaleOptions" :value="scaleIndex" @change="onScaleChange">
							<view class="field__picker">
								<text class="field__picker-text" :class="{ 'is-ph': !form.scale }">
									{{ form.scale || '请选择' }}
								</text>
								<uni-icons type="arrow-down" :size="12" color="#999999"></uni-icons>
							</view>
						</picker>
					</view>
					<view class="field field--half">
						<text class="field__label">融资阶段</text>
						<picker mode="selector" :range="stageOptions" :value="stageIndex" @change="onStageChange">
							<view class="field__picker">
								<text class="field__picker-text" :class="{ 'is-ph': !form.stage }">
									{{ form.stage || '请选择' }}
								</text>
								<uni-icons type="arrow-down" :size="12" color="#999999"></uni-icons>
							</view>
						</picker>
					</view>
				</view>

				<view class="field">
					<text class="field__label">所在城市</text>
					<picker mode="selector" :range="cityNames" :value="cityIndex" @change="onCityChange">
						<view class="field__picker">
							<text class="field__picker-text" :class="{ 'is-ph': !form.city }">
								{{ form.city || '请选择城市' }}
							</text>
							<uni-icons type="arrow-down" :size="12" color="#999999"></uni-icons>
						</view>
					</picker>
				</view>

				<view class="field">
					<text class="field__label">官网</text>
					<input class="field__input" v-model="form.website" :maxlength="120"
						placeholder="如：https://www.example.com" placeholder-class="field__ph" />
				</view>
			</view>

			<!-- ---------- 地址与介绍 ---------- -->
			<view class="sec">
				<zn-section-header title="办公地址与介绍" />
				<view class="field">
					<text class="field__label">详细地址</text>
					<input class="field__input" v-model="form.address" :maxlength="120"
						placeholder="如：北京市海淀区中关村大街 1 号 A 座 12 层" placeholder-class="field__ph" />
				</view>
				<view class="field">
					<text class="field__label">公司介绍</text>
					<textarea class="form__textarea" v-model="form.intro" :maxlength="4000"
						placeholder="主营业务、团队情况、发展历程…&#10;建议分段写，段落之间换行即可"
						placeholder-class="field__ph" />
					<view class="form__textarea-foot">
						<text class="field__tip">按段落换行，求职者端会逐段渲染</text>
						<text class="field__count">{{ form.intro.length }}/4000</text>
					</view>
				</view>
			</view>

			<!-- ---------- 福利标签 ---------- -->
			<view class="sec">
				<zn-section-header title="福利标签" subtitle="最多 12 个" />
				<view v-if="form.benefits.length" class="chips">
					<view v-for="(b, i) in form.benefits" :key="b + i" class="chip chip--on" hover-class="zn-hover"
						@tap="removeBenefit(i)">
						<text class="chip__text chip__text--on">{{ b }}</text>
						<uni-icons type="clear" :size="12" color="#008C8D"></uni-icons>
					</view>
				</view>
				<view class="adder">
					<input class="adder__input" v-model="benefitInput" :maxlength="12" placeholder="自定义福利，如：六险一金"
						placeholder-class="field__ph" @confirm="addBenefit" />
					<view class="adder__btn" hover-class="zn-hover" @tap="addBenefit">
						<text class="adder__btn-text">添加</text>
					</view>
				</view>
				<text class="field__tip">常用：</text>
				<view class="chips">
					<view v-for="b in benefitPresets" :key="b" class="chip" hover-class="zn-hover" @tap="addPresetBenefit(b)">
						<text class="chip__text">+ {{ b }}</text>
					</view>
				</view>
				<!-- 服务端 updateCompany 的写入条件是 `if payload.benefits:`，
					 空数组会被当成「不改这一项」，因此福利无法被清空 —— 如实告知，别让 HR 白试。 -->
				<text class="field__warn">提示：受接口约定限制，福利标签不能清空为空（至少保留 1 个）</text>
			</view>

			<!-- ---------- 服务端约定说明 ---------- -->
			<view class="notice">
				<uni-icons type="info-filled" :size="16" color="#00A6A7"></uni-icons>
				<text class="notice__text">
					服务端约定「空字符串表示不改这一项」：本页会把已有内容原样回填后再整体提交，
					所以留空的字段会保持原值，不会被清掉（想改内容就填新值）。
				</text>
			</view>

			<view class="hrcomp__gap"></view>
		</block>

		<!-- ==================== 四、底部保存条 ==================== -->
		<view v-if="!loading && !failed" class="bar">
			<view class="bar__hint">
				<text class="bar__hint-text">保存后立即生效，求职者端公司主页同步更新</text>
			</view>
			<view class="bar__btn" :class="{ 'is-disabled': saving }" hover-class="zn-hover" @tap="save">
				<text class="bar__btn-text">{{ saving ? '保存中…' : '保存' }}</text>
			</view>
		</view>
	</view>
</template>

<script>
	/**
	 * 企业主页维护
	 *
	 * 接口：
	 *   GET /hr/company    getCompany
	 *   PUT /hr/company    updateCompany
	 *
	 * ⚠️ 服务端约定「**空字符串表示不改这一项**」（hr.py 的 update_company 逐个 `if value:`）：
	 *    因此本页的做法是「先原样回填已有值，再整体提交」——
	 *    留空的字段提交空串等于没改，不会被清空。
	 *    代价：想把某个字段清空，当前接口做不到（只能填新的值），页面上已如实提示。
	 *    同理 benefits 传空数组也等于不改，福利无法全删。
	 *
	 * ⚠️ 公司全称（name）不在可改字段里（CompanyUpdateIn 没有 name），
	 *    所以预览区显示的是服务端返回的真实全称，只读。
	 *
	 * ⚠️ 数据隔离：服务端按当前账号绑定的公司取/写，前端不传 companyId。
	 */
	import { getCompany, updateCompany } from '@/services/hr.js'
	import { getCities } from '@/services/job.js'

	/** 规模枚举与种子数据口径一致 */
	const SCALES = ['0-20人', '20-99人', '100-499人', '500-999人', '1000-9999人', '10000人以上']

	/** 融资阶段枚举与种子数据口径一致 */
	const STAGES = ['不需要融资', '未融资', '天使轮', 'A轮', 'B轮', 'C轮', 'D轮及以上', '已上市']

	const INDUSTRY_PRESETS = [
		'人工智能', '企业服务', '金融科技', '电子商务', '在线教育',
		'医疗健康', '智能硬件', '新能源', '物流供应链', '文化传媒'
	]

	/** Logo 配色取自公司种子数据里在用的品牌色（这是写进数据里的值，不是设计令牌） */
	const LOGO_COLORS = [
		'#00A6A7', '#14B8A6', '#2B6DE5', '#0EA5E9', '#7C5CE6',
		'#E4572E', '#EC4899', '#F59E0B', '#16A34A', '#65A30D'
	]

	const BENEFIT_PRESETS = [
		'五险一金', '双休', '弹性工作', '免费三餐', '股票期权', '年度体检',
		'带薪年假', '补充医疗', '绩效奖金', '节日福利', '定期团建', '免费班车'
	]

	export default {
		data() {
			return {
				loading: true,
				ready: false,
				failed: false,
				failedMsg: '',
				saving: false,

				company: {},
				cities: [],
				logoColors: LOGO_COLORS,
				scaleOptions: SCALES,
				stageOptions: STAGES,
				industryPresets: INDUSTRY_PRESETS,
				benefitPresets: BENEFIT_PRESETS,

				benefitInput: '',

				form: {
					shortName: '',
					logoText: '',
					logoColor: '#00A6A7',
					industry: '',
					scale: '',
					stage: '',
					city: '',
					address: '',
					intro: '',
					benefits: [],
					website: ''
				}
			}
		},
		computed: {
			/** 预览副标题：行业 · 规模 · 阶段（缺哪项跳过哪项，与职位卡片同一口径） */
			previewMeta() {
				const f = this.form
				return [f.industry, f.scale, f.stage].filter(Boolean).join(' · ') || '行业 · 规模 · 融资阶段'
			},
			cityNames() {
				return this.cities.map(c => c.name)
			},
			cityIndex() {
				const i = this.cities.findIndex(c => c.name === this.form.city)
				return i < 0 ? 0 : i
			},
			scaleIndex() {
				const i = SCALES.indexOf(this.form.scale)
				return i < 0 ? 0 : i
			},
			stageIndex() {
				const i = STAGES.indexOf(this.form.stage)
				return i < 0 ? 0 : i
			}
		},
		onLoad() {
			this.load()
		},
		methods: {
			/* ---------------- 数据 ---------------- */
			async load() {
				this.loading = !this.ready
				this.failed = false
				try {
					// 城市列表只用于选择器，失败也不该挡住公司信息维护
					const [res, cities] = await Promise.all([
						getCompany(),
						getCities().catch(() => null)
					])
					this.company = (res && res.company) || {}
					this.fillForm(this.company)
					this.cities = (cities && cities.all) || []
				} catch (e) {
					if (this.handleUnbound(e)) return
					this.failed = true
					this.failedMsg = (e && e.message) || '请检查服务端是否已启动'
				} finally {
					this.loading = false
					this.ready = true
				}
			},
			handleUnbound(err) {
				if (!err || (err.code !== 40301 && err.status !== 403)) return false
				uni.reLaunch({ url: '/pages/hr/bind' })
				return true
			},
			/** 回填表单：原样保留服务端已有值（空串表示不改，所以不能自己造默认值） */
			fillForm(c) {
				this.form = {
					shortName: c.shortName || '',
					logoText: c.logoText || '',
					logoColor: c.logoColor || '#00A6A7',
					industry: c.industry || '',
					scale: c.scale || '',
					stage: c.stage || '',
					city: c.city || '',
					address: c.address || '',
					intro: c.intro || '',
					benefits: Array.isArray(c.benefits) ? c.benefits.slice() : [],
					website: c.website || ''
				}
			},

			/* ---------------- 选择器 ---------------- */
			onScaleChange(e) {
				this.form.scale = SCALES[Number(e.detail.value)]
			},
			onStageChange(e) {
				this.form.stage = STAGES[Number(e.detail.value)]
			},
			onCityChange(e) {
				const city = this.cities[Number(e.detail.value)]
				if (city) this.form.city = city.name
			},

			/* ---------------- 福利标签增删 ---------------- */
			addBenefit() {
				const text = (this.benefitInput || '').trim()
				if (!text) return
				if (this.form.benefits.length >= 12) {
					uni.showToast({ title: '最多 12 个福利标签', icon: 'none' })
					return
				}
				if (this.form.benefits.indexOf(text) > -1) {
					uni.showToast({ title: '该福利已存在', icon: 'none' })
					return
				}
				this.form.benefits.push(text)
				this.benefitInput = ''
			},
			addPresetBenefit(text) {
				if (this.form.benefits.indexOf(text) > -1) {
					uni.showToast({ title: '该福利已存在', icon: 'none' })
					return
				}
				if (this.form.benefits.length >= 12) {
					uni.showToast({ title: '最多 12 个福利标签', icon: 'none' })
					return
				}
				this.form.benefits.push(text)
			},
			removeBenefit(i) {
				if (this.form.benefits.length <= 1) {
					uni.showToast({ title: '至少要保留 1 个福利标签', icon: 'none' })
					return
				}
				this.form.benefits.splice(i, 1)
			},

			/* ---------------- 保存 ---------------- */
			async save() {
				if (this.saving) return
				const f = this.form
				if (f.website && !/^https?:\/\//i.test(f.website)) {
					uni.showToast({ title: '官网需以 http(s):// 开头', icon: 'none' })
					return
				}
				if (f.intro.length > 4000) {
					uni.showToast({ title: '公司介绍超过 4000 字', icon: 'none' })
					return
				}
				this.saving = true
				try {
					const res = await updateCompany({
						shortName: f.shortName.trim(),
						logoText: f.logoText.trim(),
						logoColor: f.logoColor,
						industry: f.industry.trim(),
						scale: f.scale,
						stage: f.stage,
						city: f.city,
						address: f.address.trim(),
						intro: f.intro,
						benefits: f.benefits.slice(),
						website: f.website.trim()
					})
					if (res && res.company) {
						this.company = res.company
						this.fillForm(res.company)
					}
					uni.showToast({ title: '已保存', icon: 'none' })
				} catch (e) {
					if (this.handleUnbound(e)) return
					// 其它错误由 services/api.js 弹出服务端原文
				} finally {
					this.saving = false
				}
			}
		}
	}
</script>

<style lang="scss" scoped>
	.hrcomp {
		padding-bottom: 200rpx;
	}

	.hrcomp__state {
		padding: 160rpx 0;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.hrcomp__state-text {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
	}

	.hrcomp__gap {
		height: 40rpx;
	}

	/* ---------------- 预览 ---------------- */
	.preview {
		margin: $zn-gap $zn-page-padding 0;
		padding: $zn-gap-lg $zn-gap;
		border-radius: $zn-radius-lg;
		background: $zn-gradient;
		box-shadow: $zn-shadow-theme;
	}

	.preview__label {
		font-size: $zn-font-xs;
		color: rgba(255, 255, 255, 0.85);
	}

	.preview__card {
		margin-top: $zn-gap-sm;
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.preview__main {
		flex: 1;
		min-width: 0;
		margin-left: $zn-gap;
		display: flex;
		flex-direction: column;
	}

	.preview__name {
		font-size: $zn-font-lg;
		font-weight: 700;
		color: #ffffff;
	}

	.preview__short {
		margin-top: 6rpx;
		font-size: $zn-font-xs;
		color: rgba(255, 255, 255, 0.86);
	}

	.preview__meta {
		margin-top: 8rpx;
		font-size: $zn-font-sm;
		color: rgba(255, 255, 255, 0.9);
	}

	.preview__tags {
		margin-top: $zn-gap-sm;
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
	}

	.preview__tag {
		margin: 0 12rpx 12rpx 0;
		padding: 4rpx 16rpx;
		border-radius: $zn-radius-pill;
		background-color: rgba(255, 255, 255, 0.22);
		font-size: $zn-font-xs;
		color: #ffffff;
	}

	.preview__intro {
		margin-top: 8rpx;
		font-size: $zn-font-xs;
		color: rgba(255, 255, 255, 0.85);
		line-height: 36rpx;
	}

	/* ---------------- 分区 / 字段 ---------------- */
	.sec {
		margin: $zn-gap-sm $zn-page-padding 0;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		box-shadow: $zn-shadow-sm;
		padding: 0 $zn-gap $zn-gap;
	}

	.field {
		margin-top: $zn-gap-sm;
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

	.field__input {
		margin-top: 12rpx;
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
		font-size: $zn-font-sm;
		color: $zn-text-main;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;

		&.is-ph {
			color: $zn-text-light;
		}
	}

	.field__tip {
		display: block;
		margin-top: 10rpx;
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	.field__warn {
		display: block;
		margin-top: $zn-gap-sm;
		font-size: $zn-font-xs;
		color: $zn-orange;
		line-height: 36rpx;
	}

	.field__count {
		font-size: $zn-font-xs;
		color: $zn-text-light;
	}

	/* ---------------- Logo 配色 ---------------- */
	.colors {
		margin-top: 14rpx;
		display: flex;
		flex-direction: row;
		flex-wrap: wrap;
	}

	.colors__item {
		width: 44rpx;
		height: 44rpx;
		border-radius: $zn-radius-sm;
		margin: 0 10rpx 10rpx 0;
		border: 3rpx solid transparent;

		&.is-on {
			border-color: $zn-text-main;
		}
	}

	/* ---------------- 芯片 ---------------- */
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
		flex-direction: row;
		align-items: center;

		&--on {
			background-color: $zn-theme-light;
		}
	}

	.chip__text {
		font-size: $zn-font-xs;
		color: $zn-text-sub;

		&--on {
			color: $zn-theme-deep;
			margin-right: 6rpx;
		}
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
		min-height: 240rpx;
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

	/* ---------------- 约定说明 ---------------- */
	.notice {
		margin: $zn-gap-sm $zn-page-padding 0;
		padding: $zn-gap-sm;
		border-radius: $zn-radius;
		background-color: $zn-theme-lighter;
		border: 1rpx solid $zn-theme-light;
		display: flex;
		flex-direction: row;
		align-items: flex-start;
	}

	.notice__text {
		flex: 1;
		min-width: 0;
		margin-left: 10rpx;
		font-size: $zn-font-xs;
		color: $zn-theme-dark;
		line-height: 38rpx;
	}

	/* ---------------- 底部保存条 ---------------- */
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
