<template>
	<view class="zn-page zn-page--no-tabbar login">
		<!-- ==================== 顶部：品牌区（主色渐变） ==================== -->
		<view class="login__bg">
			<zn-nav-bar show-back type="transparent" text-color="#ffffff" />

			<view class="brand">
				<view class="brand__logo">
					<uni-icons type="staff-filled" :size="42" color="#ffffff"></uni-icons>
				</view>
				<text class="brand__name">直聘通</text>
				<text class="brand__slogan">{{ brandSlogan }}</text>
			</view>
		</view>

		<!-- ==================== 表单区 ==================== -->
		<view class="login__body">
			<view class="card">
				<!-- ---------- 演示账号一键登录（仅演示环境） ---------- -->
				<view v-if="demoAccounts.length" class="demo">
					<view class="demo__head">
						<text class="demo__title">演示账号一键登录</text>
						<text class="demo__flag">演示环境</text>
					</view>
					<view v-for="acc in demoAccounts" :key="acc.role" class="demo__item" hover-class="zn-hover"
						@tap="onDemo(acc)">
						<view class="demo__icon" :class="acc.role === 'hr' ? 'is-hr' : 'is-candidate'">
							<uni-icons :type="demoIcon(acc)" :size="22"
								:color="acc.role === 'hr' ? '#008c8d' : '#ff5c1a'"></uni-icons>
						</view>
						<view class="demo__body">
							<text class="demo__label">{{ acc.label || '演示账号' }}</text>
							<text class="demo__desc zn-ellipsis-2">{{ acc.desc || '' }}</text>
						</view>
						<view class="demo__btn">
							<text class="demo__btn-text">{{ demoing === acc.role ? '登录中' : '一键登录' }}</text>
						</view>
					</view>
					<!-- 真实可用的凭据必须写清楚：配置里的 desc 由种子数据提供，可能与演示账号的实际登录方式不一致 -->
					<text class="demo__cred">演示邮箱：demo@zhipin.com（求职者）/ hr@zhipin.com（HR），密码 demo123456</text>
				</view>

				<!-- ---------- 登录方式切换（注册模式展示标题） ---------- -->
				<view v-if="!isRegister" class="seg">
					<view v-for="(tab, i) in modeTabs" :key="tab.key" class="seg__item"
						:class="{ 'is-active': modeIndex === i }" hover-class="zn-hover" @tap="switchMode(i)">
						<text class="seg__text">{{ tab.text }}</text>
						<view v-if="modeIndex === i" class="seg__bar"></view>
					</view>
				</view>
				<view v-else class="reg-head">
					<text class="reg-head__title">注册新账号</text>
					<text class="reg-head__desc">邮箱验证码 + 密码即可开通，注册后自动登录，可投递职位、与 HR 直接沟通</text>
				</view>

				<!-- 邮箱 -->
				<view class="field">
					<uni-icons type="email" :size="19" color="#9aa0a6"></uni-icons>
					<input class="field__input" type="text" :value="form.email" placeholder="请输入邮箱，用于接收验证码"
						placeholder-class="field__ph" @input="onInput('email', $event)" @blur="onBlur('email')" />
					<text v-if="form.email" class="field__clear" @tap="clearField('email')">
						<uni-icons type="clear" :size="17" color="#c8ced6"></uni-icons>
					</text>
				</view>
				<text v-if="emailError" class="field__error">{{ emailError }}</text>

				<!-- 验证码区：验证码登录，以及注册（服务端 /user/reg 的 code 为必填） -->
				<view v-if="showCodeField" class="mode">
					<view class="field">
						<uni-icons type="checkbox" :size="19" color="#9aa0a6"></uni-icons>
						<input class="field__input" type="number" maxlength="6" :value="form.code"
							placeholder="请输入 4~6 位验证码" placeholder-class="field__ph"
							@input="onInput('code', $event)" @blur="onBlur('code')" />
						<view class="field__code" :class="{ 'is-disabled': counting }" hover-class="zn-hover"
							@tap="onSendCode">
							<text class="field__code-text">{{ codeBtnText }}</text>
						</view>
					</view>
					<text v-if="codeError" class="field__error">{{ codeError }}</text>
				</view>

				<!-- 密码区：密码登录，以及注册（注册时额外有确认密码 / 邀请码） -->
				<view v-if="showPasswordField" class="mode">
					<view class="field">
						<uni-icons type="locked" :size="19" color="#9aa0a6"></uni-icons>
						<input class="field__input" :password="!showPwd" maxlength="20" :value="form.password"
							placeholder="请输入密码（不少于 6 位）" placeholder-class="field__ph"
							@input="onInput('password', $event)" @blur="onBlur('password')" />
						<!-- ⚠️ 图标白名单里没有 eye-slash，这里用同一个 eye 图标 + 颜色区分明/密文状态 -->
						<view class="field__eye" hover-class="zn-hover" @tap="showPwd = !showPwd">
							<uni-icons type="eye" :size="19" :color="showPwd ? '#00a6a7' : '#c8ced6'"></uni-icons>
						</view>
					</view>
					<text v-if="passwordError" class="field__error">{{ passwordError }}</text>

					<view v-if="isRegister" class="mode">
						<view class="field">
							<uni-icons type="locked" :size="19" color="#9aa0a6"></uni-icons>
							<input class="field__input" :password="!showConfirmPwd" maxlength="20"
								:value="form.confirm" placeholder="请再次输入密码" placeholder-class="field__ph"
								@input="onInput('confirm', $event)" @blur="onBlur('confirm')" />
							<view class="field__eye" hover-class="zn-hover" @tap="showConfirmPwd = !showConfirmPwd">
								<uni-icons type="eye" :size="19"
									:color="showConfirmPwd ? '#00a6a7' : '#c8ced6'"></uni-icons>
							</view>
						</view>
						<text v-if="confirmError" class="field__error">{{ confirmError }}</text>

						<view class="field">
							<uni-icons type="gift" :size="19" color="#9aa0a6"></uni-icons>
							<input class="field__input" maxlength="12" :value="form.invite"
								placeholder="内推码（选填）" placeholder-class="field__ph"
								@input="onInput('invite', $event)" />
						</view>
					</view>

					<!-- 忘记密码 -->
					<view v-if="!isRegister" class="forgot" hover-class="zn-hover" @tap="onForgot">
						<text class="forgot__text">忘记密码？</text>
					</view>
				</view>

				<!-- 协议勾选（自绘勾选框） -->
				<view class="agree">
					<view class="agree__box" :class="{ 'is-checked': agree }" hover-class="zn-hover"
						@tap="agree = !agree">
						<uni-icons v-if="agree" type="checkmarkempty" :size="14" color="#ffffff"></uni-icons>
					</view>
					<text class="agree__text" @tap="agree = !agree">同意</text>
					<text class="agree__link" @tap="onAgreement('agreement')">《用户服务协议》</text>
					<text class="agree__text">与</text>
					<text class="agree__link" @tap="onAgreement('privacy')">《隐私政策》</text>
				</view>

				<!-- 主按钮 -->
				<view class="submit" :class="{ 'is-disabled': !canSubmit }" hover-class="zn-hover" @tap="onSubmit">
					<text class="submit__text">{{ submitText }}</text>
				</view>

				<!-- 注册 / 登录 切换 -->
				<view class="switch-row" hover-class="zn-hover" @tap="toggleRegister">
					<text class="switch-row__text">{{ isRegister ? '已有账号？去登录' : '还没有账号？立即注册' }}</text>
				</view>

				<!-- 验证码说明 + 服务端页面配置里的登录提示 -->
				<view class="mock-tip">
					<uni-icons type="info" :size="14" color="#008c8d"></uni-icons>
					<text class="mock-tip__text">验证码由服务端发送到邮箱；服务端开启 EMAIL_DEBUG 时会直接显示在提示中</text>
				</view>
				<view v-if="tips.length" class="tips">
					<view v-for="(tip, i) in tips" :key="i" class="tips__item">
						<view class="tips__dot"></view>
						<text class="tips__text">{{ tip }}</text>
					</view>
				</view>
			</view>

			<!-- ==================== 第三方登录（配置里有才显示） ==================== -->
			<view v-if="thirdParty.length" class="third">
				<view class="third__divider">
					<view class="third__line"></view>
					<text class="third__label">其他登录方式</text>
					<view class="third__line"></view>
				</view>
				<view class="third__list">
					<view v-for="item in thirdParty" :key="item.key" class="third__item" hover-class="zn-hover"
						@tap="onThirdParty(item)">
						<view class="third__circle" :style="{ backgroundColor: item.color }">
							<uni-icons :type="item.icon" :size="24" color="#ffffff"></uni-icons>
						</view>
						<text class="third__name">{{ item.label }}</text>
					</view>
				</view>
			</view>
		</view>

		<!-- ==================== 登录后设置密码浮层 ==================== -->
		<view v-if="showSetPwd" class="setpwd-mask" @tap="onSetPwdSkip">
			<view class="setpwd" @tap.stop>
				<text class="setpwd__title">设置登录密码</text>
				<text class="setpwd__desc">为账号 {{ maskedEmail }} 设置密码，下次即可密码登录</text>

				<view class="field">
					<uni-icons type="locked" :size="19" color="#9aa0a6"></uni-icons>
					<input class="field__input" :password="!setPwdShow" maxlength="20" :value="setPwd.password"
						placeholder="请输入密码（不少于 6 位）" placeholder-class="field__ph"
						@input="onSetPwdInput('password', $event)" @blur="onSetPwdBlur" />
					<view class="field__eye" hover-class="zn-hover" @tap="setPwdShow = !setPwdShow">
						<uni-icons type="eye" :size="19" :color="setPwdShow ? '#00a6a7' : '#c8ced6'"></uni-icons>
					</view>
				</view>
				<view class="field">
					<uni-icons type="locked" :size="19" color="#9aa0a6"></uni-icons>
					<input class="field__input" :password="!setPwdShow" maxlength="20" :value="setPwd.confirm"
						placeholder="请再次输入密码" placeholder-class="field__ph"
						@input="onSetPwdInput('confirm', $event)" @blur="onSetPwdBlur" />
				</view>
				<text v-if="setPwdError" class="field__error">{{ setPwdError }}</text>

				<view class="setpwd__btns">
					<view class="setpwd__btn setpwd__btn--skip" hover-class="zn-hover" @tap="onSetPwdSkip">
						<text class="setpwd__btn-text">跳过</text>
					</view>
					<view class="setpwd__btn setpwd__btn--ok" :class="{ 'is-disabled': !canSetPwd }"
						hover-class="zn-hover" @tap="onSetPwdSubmit">
						<text class="setpwd__btn-text">设置并登录</text>
					</view>
				</view>
			</view>
		</view>
	</view>
</template>

<script>
	/**
	 * 登录 / 注册（邮箱验证码 / 密码）
	 *
	 * 已接入真实服务端：验证码、注册、登录全部走 /api/v1/user/*（services/user.js），
	 * 登录成功后由 services/user.js 写入本地登录态（zn_token + zn_user）。
	 *
	 * 本次改造只动了「文案 / 视觉 / 演示入口」，两种登录方式的**校验逻辑一行未改**：
	 *   邮箱正则、验证码 4~6 位、密码不少于 6 位、两次密码一致、协议勾选、
	 *   验证码 60 秒倒计时、注册必须邮箱验证码（服务端 /user/reg 的 code 是必填）……
	 *   这些都保留原样，避免在改文案时动到已验证过的逻辑。
	 *
	 * ⚠️⚠️ 演示账号一键登录是**演示环境专用**入口：
	 *     demo@zhipin.com / hr@zhipin.com 这两个账号由 server/app/seed_recruit.py 的
	 *     _ensure_demo_accounts() 创建，密码固定为 demo123456。
	 *     **生产环境必须删除本入口**（连同页面里的 DEMO_LOGIN 常量与 demoAccounts 渲染块），
	 *     否则任何人点一下就能拿到一个求职者 / HR 账号。
	 *
	 * ⚠️ 登录成功后的分流：
	 *     演示账号的角色来自按钮本身（config 里的 role 字段），是明确已知的，因此按角色分流：
	 *       candidate → /pages/index/index（职位首页）
	 *       hr        → /pages/hr/dashboard（企业端工作台）
	 *     表单登录（邮箱 + 验证码 / 密码）**不做角色分流**，仍按原逻辑返回上一页：
	 *     登录响应里没有可靠的角色字段（user.level 是中文展示文案，不能当权限用），
	 *     猜错会把 HR 用户丢进求职者首页，反而不如返回他刚才所在的页面。
	 *
	 * ⚠️ 展示型配置的取法：招聘端的配置键统一以 rc 开头，因此这里读 rcLoginConfig
	 *    （旧学习端键名 loginConfig 已废弃）；配置拉不到时演示区与第三方登录区不显示，
	 *    邮箱登录不受影响 —— 展示型配置属于「可有可无」，缺失时不阻塞主流程。
	 */
	import {
		sendEmailCode,
		login,
		register,
		saveLoginState,
		changePassword,
		getLastLogin,
		setLastLogin,
		setCachedHasPassword,
		maskEmail
	} from '@/services/user.js'
	import { getConfig } from '@/services/content.js'

	/** 验证码倒计时秒数 */
	const COUNTDOWN = 60
	/** 邮箱 / 验证码正则 */
	const EMAIL_RE = /^[^@\s]+@[^@\s]+\.[^@\s]+$/
	const CODE_RE = /^\d{4,6}$/

	/**
	 * 演示账号的角色 → 登录凭据映射（⚠️ 仅演示环境，生产必须删除本常量）
	 * 与 server/app/seed_recruit.py 的 _ensure_demo_accounts() 保持一致：
	 * 两个账号的密码都是 demo123456。
	 */
	const DEMO_LOGIN = {
		candidate: { email: 'demo@zhipin.com', password: 'demo123456' },
		hr: { email: 'hr@zhipin.com', password: 'demo123456' }
	}

	export default {
		data() {
			return {
				modeTabs: [
					{ key: 'code', text: '验证码登录' },
					{ key: 'password', text: '密码登录' }
				],
				modeIndex: 0, // 0 验证码登录 / 1 密码登录
				isRegister: false, // 是否注册模式
				form: { email: '', code: '', password: '', confirm: '', invite: '' },
				touched: { email: false, code: false, password: false, confirm: false },
				showPwd: false,
				showConfirmPwd: false,
				agree: false,
				countdown: 0,
				submitting: false, // 提交中标记：防止重复点击登录按钮
				timer: null, // 验证码倒计时定时器
				backTimer: null, // 登录成功后的跳转定时器
				// ---------- 来自 rcLoginConfig 的展示型配置 ----------
				brandSlogan: '找工作直接和 HR 谈 · 平均 2 小时收到回复',
				demoAccounts: [], // [{role,label,desc}] 演示账号（仅演示环境）
				thirdParty: [], // 第三方登录按钮（配置里有才显示）
				tips: [], // 登录页提示文案
				// ---------- 演示登录状态 ----------
				demoing: '', // 正在登录的演示账号 role（用于按钮文案与防重复点击）
				loginRole: '', // 本次登录已知的角色（仅演示入口会赋值，决定成功后的分流）
				// ---------- 登录后设密码浮层（首次验证码登录且未设密码时弹出） ----------
				showSetPwd: false,
				setPwdShow: false,
				setPwdTouched: false,
				setPwd: { password: '', confirm: '' }
			}
		},
		computed: {
			/** 验证码登录模式（注册模式下不走该模式） */
			isCodeMode() {
				return !this.isRegister && this.modeIndex === 0
			},
			/** 是否展示验证码输入区：验证码登录，或注册（注册同样必须邮箱验证码） */
			showCodeField() {
				return this.isCodeMode || this.isRegister
			},
			/** 是否展示密码输入区：密码登录，或注册 */
			showPasswordField() {
				return !this.isCodeMode
			},
			counting() {
				return this.countdown > 0
			},
			codeBtnText() {
				return this.counting ? this.countdown + 's 后重发' : '获取验证码'
			},
			submitText() {
				return this.isRegister ? '注册并登录' : '登录'
			},
			/** 行内校验：邮箱（未输入且未触碰时不提示，避免一进页面就报错） */
			emailError() {
				if (!this.form.email) return this.touched.email ? '请输入邮箱' : ''
				return EMAIL_RE.test(this.form.email) ? '' : '邮箱格式不正确'
			},
			/** 行内校验：验证码 4~6 位（验证码登录与注册都要） */
			codeError() {
				if (!this.showCodeField) return ''
				if (!this.form.code) return this.touched.code ? '请输入验证码' : ''
				return CODE_RE.test(this.form.code) ? '' : '验证码为 4~6 位数字'
			},
			/** 行内校验：密码不少于 6 位 */
			passwordError() {
				if (!this.showPasswordField) return ''
				if (!this.form.password) return this.touched.password ? '请输入密码' : ''
				return this.form.password.length >= 6 ? '' : '密码不少于 6 位'
			},
			/** 行内校验：注册时两次密码需一致 */
			confirmError() {
				if (!this.isRegister) return ''
				if (!this.form.confirm) return this.touched.confirm ? '请再次输入密码' : ''
				return this.form.confirm === this.form.password ? '' : '两次输入的密码不一致'
			},
			/** 所有字段是否合法（决定主按钮是否置灰） */
			canSubmit() {
				if (!EMAIL_RE.test(this.form.email)) return false
				// 验证码登录与注册都要求填写验证码（服务端 /user/reg 的 code 为必填）
				if (this.showCodeField && !CODE_RE.test(this.form.code)) return false
				if (this.isCodeMode) return true
				if (this.form.password.length < 6) return false
				if (this.isRegister && this.form.confirm !== this.form.password) return false
				return true
			},
			/** 设密码浮层中展示的脱敏邮箱 */
			maskedEmail() {
				return maskEmail(this.form.email)
			},
			/** 设密码浮层：行内校验（未触碰不提示，避免一打开就报红） */
			setPwdError() {
				const pwd = this.setPwd.password
				const confirm = this.setPwd.confirm
				if (!this.setPwdTouched) return ''
				if (!pwd) return '请输入密码'
				if (pwd.length < 6) return '密码不少于 6 位'
				if (!confirm) return '请再次输入密码'
				if (pwd !== confirm) return '两次输入的密码不一致'
				return ''
			},
			/** 设密码信息是否齐全（决定「设置并登录」按钮是否置灰） */
			canSetPwd() {
				const pwd = this.setPwd.password
				return pwd.length >= 6 && pwd === this.setPwd.confirm
			}
		},
		async onLoad() {
			// 回填上次登录邮箱：提升体验，避免每次重新输入
			try {
				const last = getLastLogin()
				if (last && last.email) {
					this.form.email = last.email
					// ⚠️ 上次登录已设密码 → 默认切到「密码登录」标签页，实现「下次直接密码登录」
					if (last.hasPassword) this.modeIndex = 1
				}
			} catch (e) {}

			// 登录页展示型配置（rcLoginConfig）：演示账号 / 第三方入口 / 标语 / 提示
			try {
				const cfg = await getConfig('rcLoginConfig')
				if (cfg && typeof cfg === 'object') {
					if (cfg.subtitle) this.brandSlogan = cfg.subtitle
					if (Array.isArray(cfg.demoAccounts)) this.demoAccounts = cfg.demoAccounts
					if (Array.isArray(cfg.thirdParty)) this.thirdParty = cfg.thirdParty
					if (Array.isArray(cfg.tips)) this.tips = cfg.tips
				}
			} catch (e) {
				// 配置缺失不算错误：演示区 / 第三方区不显示，邮箱登录照常可用
				this.demoAccounts = []
				this.thirdParty = []
				this.tips = []
			}
		},
		onUnload() {
			// 定时器必须在页面卸载时清理
			if (this.timer) {
				clearInterval(this.timer)
				this.timer = null
			}
			if (this.backTimer) {
				clearTimeout(this.backTimer)
				this.backTimer = null
			}
		},
		methods: {
			/* ---------------- 表单输入 ---------------- */
			onInput(key, e) {
				this.form[key] = e.detail.value
			},
			onBlur(key) {
				this.touched[key] = true
			},
			clearField(key) {
				this.form[key] = ''
			},
			/** 切换登录方式 */
			switchMode(i) {
				if (this.modeIndex === i) return
				this.modeIndex = i
			},
			/**
			 * 登录 / 注册模式切换
			 * ⚠️ 不清空 form.code，也不重置倒计时：验证码按邮箱下发、注册与登录共用同一个码，
			 *    清空会迫使重发，而服务端 60 秒内只允许发一次（40004 发送过于频繁）
			 */
			toggleRegister() {
				this.isRegister = !this.isRegister
				this.form.confirm = ''
				this.touched.confirm = false
			},

			/* ---------------- 验证码倒计时 ---------------- */
			/** 获取验证码：先本地校验邮箱格式，再请求服务端下发邮件 */
			async onSendCode() {
				if (this.counting) return
				if (!EMAIL_RE.test(this.form.email)) {
					this.touched.email = true
					uni.showToast({ title: '请先输入正确的邮箱', icon: 'none' })
					return
				}
				try {
					const res = await sendEmailCode(this.form.email)
					// 调试模式（服务端 EMAIL_DEBUG=true）下验证码随响应返回，便于联调；
					// 真实模式下响应不含 dev_code，需提示用户去邮箱查收
					const tip =
						res && res.dev_code
							? '验证码已发送（' + res.dev_code + '）'
							: '验证码已发送，请查收邮件'
					uni.showToast({ title: tip, icon: 'none', duration: 2500 })
					this.startCountdown()
				} catch (e) {
					// 失败提示已由请求层统一弹出，此处不启动倒计时，便于用户立即重试
				}
			},
			/** 启动验证码倒计时（倒计时期间按钮不可点） */
			startCountdown() {
				this.countdown = COUNTDOWN
				if (this.timer) clearInterval(this.timer)
				this.timer = setInterval(() => {
					this.countdown--
					if (this.countdown <= 0) {
						this.countdown = 0
						clearInterval(this.timer)
						this.timer = null
					}
				}, 1000)
			},

			/* ---------------- 协议与第三方 ---------------- */
			/**
			 * 协议详情：跳转协议页
			 *
			 * ⚠️ 路径以冻结路由表为准（/pages/mine/agreement）；
			 *    rcLoginConfig.agreement 里配的 link 指向旧学习端路径，不能直接用。
			 */
			onAgreement(type) {
				uni.navigateTo({
					url: '/pages/mine/agreement?type=' + type,
					fail: () => uni.showToast({ title: '协议页面打开失败，请稍后重试', icon: 'none' })
				})
			},
			onForgot() {
				// ⚠️ 服务端的修改密码接口需要登录态，未登录时无法直接重置密码，
				//    因此这里引导用户先用验证码登录，再在「设置」中改密
				uni.showToast({
					title: '请用验证码登录后，在「设置」中修改密码',
					icon: 'none',
					duration: 2200
				})
			},
			onThirdParty(item) {
				uni.showToast({ title: '第三方登录暂未开放', icon: 'none' })
			},
			/**
			 * 协议确认（表单登录与演示登录共用）
			 * 未勾选时弹一次确认框，同意后继续；取消则中止本次登录。
			 */
			ensureAgree(cb) {
				if (this.agree) {
					cb()
					return
				}
				uni.showModal({
					title: '提示',
					content: '请先阅读并同意《用户服务协议》与《隐私政策》',
					confirmText: '同意',
					confirmColor: '#00a6a7',
					success: res => {
						if (!res.confirm) return
						this.agree = true
						cb()
					}
				})
			},

			/* ---------------- 演示账号一键登录（⚠️ 仅演示环境） ---------------- */
			/**
			 * 演示账号图标
			 *
			 * ⚠️ 为什么抽成方法而不是在模板里写三元表达式：
			 *    模板里的 `:type="acc.role === 'hr' ? 'staff-filled' : 'person-filled'"`
			 *    会被 tools/check-icons.js 当成图标名字面量逐个校验，
			 *    其中 'hr' 是角色名不是图标名 → 误报「图标名不存在」。
			 *    抽成方法后模板里没有字符串字面量，误报随之消失。
			 */
			demoIcon(acc) {
				return acc && acc.role === 'hr' ? 'staff-filled' : 'person-filled'
			},
			/**
			 * 演示账号一键登录
			 * @param {object} acc rcLoginConfig.demoAccounts 里的一项 {role,label,desc}
			 *
			 * 用固定邮箱 + 密码走 mode:'pwd' 登录，成功后按 role 分流到求职端 / 企业端。
			 * 生产环境必须删除本方法与其入口（见文件头说明）。
			 */
			onDemo(acc) {
				const conf = DEMO_LOGIN[acc && acc.role]
				if (!conf) {
					uni.showToast({ title: '该演示账号暂不可用', icon: 'none' })
					return
				}
				if (this.submitting) return
				this.ensureAgree(() => this.doDemoLogin(acc.role, conf))
			},
			async doDemoLogin(role, conf) {
				if (this.submitting) return
				this.submitting = true
				this.demoing = role
				uni.showLoading({ title: '正在登录…', mask: true })
				try {
					const res = await login({ mode: 'pwd', email: conf.email, password: conf.password })
					saveLoginState(res)
					// 演示入口的角色是明确的，记下来供成功后的分流使用
					this.loginRole = role

					// 与表单登录一致：未设密码时先引导设置密码（演示账号一般已有密码，不会走到这里）
					const user = (res && res.user) || {}
					if (user.hasPassword === false) {
						uni.hideLoading()
						this.setPwd = { password: '', confirm: '' }
						this.setPwdTouched = false
						this.setPwdShow = false
						this.showSetPwd = true
						return
					}

					uni.hideLoading()
					uni.showToast({ title: role === 'hr' ? '已进入企业端' : '已进入求职端', icon: 'success' })
					this.backTimer = setTimeout(() => {
						this.backTimer = null
						this.enterByRole()
					}, 700)
				} catch (e) {
					// 失败提示已由请求层统一弹出（如密码被改过会返回密码错误），这里只做收尾
					uni.hideLoading()
				} finally {
					this.submitting = false
					this.demoing = ''
				}
			},

			/* ---------------- 提交 ---------------- */
			onSubmit() {
				if (!this.canSubmit) {
					// 置灰状态下点击：把所有字段标记为已触碰，展示行内红色错误提示
					this.touched.email = true
					this.touched.code = true
					this.touched.password = true
					this.touched.confirm = true
					const first =
						this.emailError || this.codeError || this.passwordError || this.confirmError
					uni.showToast({ title: first || '请完善登录信息', icon: 'none' })
					return
				}
				this.ensureAgree(() => this.doLogin())
			},
			/** 登录 / 注册：调用服务端接口，成功后写入本地登录态并返回上一页 */
			async doLogin() {
				if (this.submitting) return
				this.submitting = true
				uni.showLoading({ title: '请稍候...', mask: true })
				try {
					let res
					if (this.isRegister) {
						// 注册：邮箱验证码 + 密码（密码留空即为纯验证码账号）
						res = await register({
							email: this.form.email,
							code: this.form.code,
							password: this.form.password,
							invite: this.form.invite
						})
					} else if (this.isCodeMode) {
						// 验证码登录：服务端对未注册邮箱会自动完成注册
						res = await login({
							mode: 'code',
							email: this.form.email,
							code: this.form.code
						})
					} else {
						// 密码登录
						res = await login({
							mode: 'pwd',
							email: this.form.email,
							password: this.form.password
						})
					}

					// 写入登录态（token + 用户信息；邮箱在 services 层做脱敏）
					saveLoginState(res)
					// 表单登录不认角色：清掉可能残留的演示角色，避免上一次演示登录影响本次分流
					this.loginRole = ''

					// ⚠️ 关键：验证码首次登录（或注册留空密码）的账号 hasPassword=false，
					//    此时不自动返回，而是弹出「设置登录密码」浮层，
					//    引导用户设密码，之后即可走密码登录、无需再收验证码。
					const user = (res && res.user) || {}
					if (user.hasPassword === false) {
						uni.hideLoading()
						this.setPwd = { password: '', confirm: '' }
						this.setPwdTouched = false
						this.setPwdShow = false
						this.showSetPwd = true
						// submitting 在 finally 中复位，浮层按钮可正常点击
						return
					}

					uni.hideLoading()
					uni.showToast({
						title: this.isRegister ? '注册成功' : '登录成功',
						icon: 'success'
					})
					this.backTimer = setTimeout(() => {
						this.backTimer = null
						this.back()
					}, 800)
				} catch (e) {
					// 失败提示已由请求层统一弹出，这里只做收尾
					uni.hideLoading()
				} finally {
					this.submitting = false
				}
			},
			/* ---------------- 登录后设置密码浮层 ---------------- */
			/** 设密码输入：绑定到 setPwd 对象 */
			onSetPwdInput(key, e) {
				this.setPwd[key] = e.detail.value
			},
			/** 设密码失焦：标记已触碰，触发行内错误提示 */
			onSetPwdBlur() {
				this.setPwdTouched = true
			},
			/** 跳过设置：直接进入下一步（下次仍可用验证码登录） */
			onSetPwdSkip() {
				this.showSetPwd = false
				this.afterLogin()
			},
			/** 提交设置密码：调服务端 verify=set，成功后标记本地状态并进入下一步 */
			async onSetPwdSubmit() {
				// 提交前强制标记已触碰，确保不完整输入也会展示错误
				this.setPwdTouched = true
				if (!this.canSetPwd) {
					const first = this.setPwdError || '请完善密码信息'
					uni.showToast({ title: first, icon: 'none' })
					return
				}
				if (this.submitting) return
				this.submitting = true
				uni.showLoading({ title: '设置中...', mask: true })
				try {
					// verify=set：已登录上下文直接设密码，无需原密码、不用再收验证码
					await changePassword({
						verify: 'set',
						new_password: this.setPwd.password
					})
					// 更新本地状态：缓存 hasPassword 置 true，并把上次登录标记为已设密码
					setCachedHasPassword(true)
					setLastLogin(this.form.email || (DEMO_LOGIN[this.loginRole] || {}).email || '', true)
					uni.hideLoading()
					uni.showToast({ title: '密码设置成功', icon: 'success' })
					this.showSetPwd = false
					this.backTimer = setTimeout(() => {
						this.backTimer = null
						this.afterLogin()
					}, 600)
				} catch (e) {
					// 失败提示已由请求层统一弹出
					uni.hideLoading()
				} finally {
					this.submitting = false
				}
			},

			/* ---------------- 登录成功后的去向 ---------------- */
			/** 已知角色（演示入口）走分流，否则按原逻辑返回上一页 */
			afterLogin() {
				if (this.loginRole) {
					this.enterByRole()
					return
				}
				this.back()
			},
			/** 按角色分流：求职者 → 职位首页；HR → 企业端工作台 */
			enterByRole() {
				const url = this.loginRole === 'hr' ? '/pages/hr/dashboard' : '/pages/index/index'
				uni.reLaunch({
					url,
					fail: () => uni.showToast({ title: '目标页面打开失败', icon: 'none' })
				})
			},
			/** 返回上一页；没有上一页时回到个人中心 */
			back() {
				const pages = getCurrentPages()
				if (pages.length > 1) {
					uni.navigateBack({ delta: 1 })
				} else {
					uni.reLaunch({ url: '/pages/mine/mine' })
				}
			}
		}
	}
</script>

<style lang="scss" scoped>
	.login {
		padding-bottom: 0;
	}

	/* ==================== 顶部渐变 + 品牌 ==================== */
	.login__bg {
		background: $zn-gradient;
		padding-bottom: 90rpx;
	}

	.brand {
		display: flex;
		flex-direction: column;
		align-items: center;
		padding: 30rpx $zn-page-padding 0;
	}

	.brand__logo {
		width: 132rpx;
		height: 132rpx;
		border-radius: $zn-radius-xl;
		background-color: rgba(255, 255, 255, 0.24);
		border: 2rpx solid rgba(255, 255, 255, 0.5);
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.brand__name {
		font-size: 46rpx;
		font-weight: 700;
		color: #ffffff;
		letter-spacing: 4rpx;
		margin-top: 24rpx;
	}

	.brand__slogan {
		font-size: 24rpx;
		color: rgba(255, 255, 255, 0.9);
		margin-top: 12rpx;
		text-align: center;
	}

	/* ==================== 表单区 ==================== */
	.login__body {
		position: relative;
		z-index: 2;
		margin-top: -60rpx;
		background-color: $zn-bg-card;
		border-top-left-radius: 40rpx;
		border-top-right-radius: 40rpx;
		padding: 36rpx $zn-page-padding 60rpx;
	}

	.card {
		background-color: $zn-bg-card;
	}

	/* ---------- 演示账号一键登录 ---------- */
	.demo {
		background-color: $zn-theme-lighter;
		border: 2rpx solid $zn-theme-light;
		border-radius: $zn-radius-lg;
		padding: 22rpx;
		margin-bottom: 36rpx;
	}

	.demo__head {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
	}

	.demo__title {
		font-size: 28rpx;
		font-weight: 700;
		color: $zn-theme-dark;
	}

	.demo__flag {
		font-size: 19rpx;
		color: $zn-theme-dark;
		background-color: $zn-theme-light;
		border-radius: 6rpx;
		padding: 2rpx 12rpx;
	}

	.demo__item {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius;
		padding: 18rpx 20rpx;
		margin-top: 16rpx;
	}

	.demo__icon {
		width: 68rpx;
		height: 68rpx;
		border-radius: $zn-radius-sm;
		display: flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;

		&.is-candidate {
			background-color: #fff2e8;
		}

		&.is-hr {
			background-color: $zn-theme-light;
		}
	}

	.demo__body {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin: 0 16rpx;
	}

	.demo__label {
		font-size: 27rpx;
		font-weight: 600;
		color: $zn-text-title;
	}

	.demo__desc {
		font-size: 20rpx;
		color: $zn-text-grey;
		line-height: 30rpx;
		margin-top: 6rpx;
	}

	.demo__btn {
		flex-shrink: 0;
		height: 56rpx;
		padding: 0 22rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.demo__btn-text {
		font-size: 23rpx;
		font-weight: 600;
		color: #ffffff;
	}

	.demo__cred {
		display: block;
		font-size: 19rpx;
		color: $zn-text-grey;
		line-height: 30rpx;
		margin-top: 16rpx;
	}

	/* ---------- 登录方式切换 ---------- */
	.seg {
		display: flex;
		flex-direction: row;
		align-items: center;
		padding: 0 6rpx;
	}

	.seg__item {
		display: flex;
		flex-direction: column;
		align-items: center;
		margin-right: 44rpx;
	}

	.seg__text {
		font-size: 30rpx;
		color: $zn-text-grey;
	}

	.seg__item.is-active .seg__text {
		font-size: 34rpx;
		font-weight: 700;
		color: $zn-text-title;
	}

	.seg__bar {
		width: 44rpx;
		height: 6rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		margin-top: 10rpx;
	}

	/* ---------- 注册标题 ---------- */
	.reg-head {
		display: flex;
		flex-direction: column;
	}

	.reg-head__title {
		font-size: 38rpx;
		font-weight: 700;
		color: $zn-text-title;
	}

	.reg-head__desc {
		font-size: 23rpx;
		color: $zn-text-grey;
		line-height: 34rpx;
		margin-top: 10rpx;
	}

	/* ---------- 输入行 ---------- */
	.field {
		display: flex;
		flex-direction: row;
		align-items: center;
		height: 100rpx;
		border-bottom: 1rpx solid $zn-line;
		margin-top: 22rpx;
	}

	.field__input {
		flex: 1;
		min-width: 0;
		height: 100rpx;
		font-size: 30rpx;
		color: $zn-text-main;
		margin-left: 16rpx;
	}

	.field__ph {
		font-size: 28rpx;
		color: $zn-text-light;
	}

	.field__clear {
		width: 52rpx;
		height: 52rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.field__eye {
		width: 60rpx;
		height: 60rpx;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.field__code {
		flex-shrink: 0;
		height: 60rpx;
		padding: 0 24rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-left: 12rpx;

		&.is-disabled {
			background: #e3e7eb;
		}
	}

	.field__code-text {
		font-size: 24rpx;
		font-weight: 600;
		color: #ffffff;
	}

	.field__error {
		display: block;
		font-size: 22rpx;
		color: $zn-red;
		margin-top: 10rpx;
		padding-left: 4rpx;
	}

	/* ---------- 忘记密码 ---------- */
	.forgot {
		display: flex;
		flex-direction: row;
		margin-top: 20rpx;
	}

	.forgot__text {
		font-size: 24rpx;
		color: $zn-theme-deep;
	}

	/* ---------- 协议勾选 ---------- */
	.agree {
		display: flex;
		flex-direction: row;
		align-items: center;
		flex-wrap: wrap;
		margin-top: 36rpx;
	}

	.agree__box {
		width: 32rpx;
		height: 32rpx;
		border-radius: 50%;
		border: 2rpx solid #cfd5db;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-right: 12rpx;
		flex-shrink: 0;

		&.is-checked {
			background: $zn-gradient;
			border-color: transparent;
		}
	}

	.agree__text {
		font-size: 22rpx;
		color: $zn-text-grey;
	}

	.agree__link {
		font-size: 22rpx;
		color: $zn-theme-deep;
	}

	/* ---------- 主按钮 ---------- */
	.submit {
		height: 88rpx;
		border-radius: $zn-radius-pill;
		background: $zn-gradient;
		display: flex;
		align-items: center;
		justify-content: center;
		margin-top: 40rpx;
		box-shadow: $zn-shadow-theme;

		&.is-disabled {
			background: #dfe3e8;
			box-shadow: none;
		}
	}

	.submit__text {
		font-size: 32rpx;
		font-weight: 600;
		color: #ffffff;
	}

	/* ---------- 注册 / 登录切换 ---------- */
	.switch-row {
		display: flex;
		align-items: center;
		justify-content: center;
		margin-top: 32rpx;
	}

	.switch-row__text {
		font-size: 26rpx;
		color: $zn-theme-deep;
	}

	/* ---------- 验证码说明 ---------- */
	.mock-tip {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: $zn-theme-light;
		border-radius: $zn-radius-sm;
		padding: 16rpx 20rpx;
		margin-top: 36rpx;
	}

	.mock-tip__text {
		font-size: 21rpx;
		color: $zn-theme-dark;
		margin-left: 10rpx;
		flex: 1;
		min-width: 0;
	}

	/* ---------- 配置里的登录提示 ---------- */
	.tips {
		margin-top: 20rpx;
	}

	.tips__item {
		display: flex;
		flex-direction: row;
		align-items: flex-start;
		margin-bottom: 12rpx;
	}

	.tips__dot {
		width: 8rpx;
		height: 8rpx;
		border-radius: 50%;
		background-color: $zn-text-light;
		margin: 14rpx 12rpx 0 0;
		flex-shrink: 0;
	}

	.tips__text {
		flex: 1;
		min-width: 0;
		font-size: 21rpx;
		color: $zn-text-grey;
		line-height: 34rpx;
	}

	/* ==================== 第三方登录 ==================== */
	.third {
		margin-top: 60rpx;
	}

	.third__divider {
		display: flex;
		flex-direction: row;
		align-items: center;
	}

	.third__line {
		flex: 1;
		height: 1rpx;
		background-color: $zn-line;
	}

	.third__label {
		font-size: 22rpx;
		color: $zn-text-light;
		padding: 0 20rpx;
	}

	.third__list {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: center;
		margin-top: 40rpx;
	}

	.third__item {
		display: flex;
		flex-direction: column;
		align-items: center;
		margin: 0 44rpx;
	}

	.third__circle {
		width: 88rpx;
		height: 88rpx;
		border-radius: 50%;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.third__name {
		font-size: 21rpx;
		color: $zn-text-grey;
		margin-top: 12rpx;
	}

	/* ==================== 登录后设置密码浮层 ==================== */
	.setpwd-mask {
		position: fixed;
		left: 0;
		top: 0;
		right: 0;
		bottom: 0;
		background-color: rgba(0, 0, 0, 0.45);
		display: flex;
		align-items: flex-end;
		z-index: 999;
	}

	.setpwd {
		width: 100%;
		background-color: $zn-bg-card;
		border-top-left-radius: 32rpx;
		border-top-right-radius: 32rpx;
		padding: 44rpx $zn-page-padding 60rpx;
	}

	.setpwd__title {
		display: block;
		font-size: 36rpx;
		font-weight: 700;
		color: $zn-text-title;
	}

	.setpwd__desc {
		display: block;
		font-size: 23rpx;
		color: $zn-text-grey;
		margin-top: 14rpx;
	}

	/* 复用 .field 输入行样式（页面已定义），这里只补浮层内的间距 */
	.setpwd .field {
		margin-top: 28rpx;
	}

	.setpwd__btns {
		display: flex;
		flex-direction: row;
		align-items: center;
		margin-top: 44rpx;
	}

	.setpwd__btn {
		flex: 1;
		height: 88rpx;
		border-radius: $zn-radius-pill;
		display: flex;
		align-items: center;
		justify-content: center;
	}

	.setpwd__btn--skip {
		background-color: $zn-bg-grey;
		margin-right: 20rpx;
	}

	.setpwd__btn--ok {
		background: $zn-gradient;
		box-shadow: $zn-shadow-theme;

		&.is-disabled {
			background: #dfe3e8;
			box-shadow: none;
		}
	}

	.setpwd__btn-text {
		font-size: 30rpx;
		font-weight: 600;
		color: $zn-text-grey;
	}

	.setpwd__btn--ok .setpwd__btn-text {
		color: #ffffff;
	}

	.setpwd__btn--ok.is-disabled .setpwd__btn-text {
		color: #ffffff;
	}
</style>
