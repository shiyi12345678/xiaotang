<template>
	<view class="zn-page zn-page--no-tabbar">
		<zn-nav-bar title="设置" show-back border />

		<view class="settings__body">
			<!-- ---------- 账号卡 ---------- -->
			<view class="profile" hover-class="zn-hover" @tap="onEditProfile">
				<zn-avatar :name="user.nickname" :size="120" :border="true" />
				<view class="profile__info">
					<text class="profile__name">{{ user.nickname || '未设置昵称' }}</text>
					<text v-if="profileLoading" class="profile__sub">正在加载账号资料…</text>
					<text v-else class="profile__sub">{{ user.email || '未绑定邮箱' }}</text>
				</view>
				<uni-icons type="right" :size="15" color="#c8ced6"></uni-icons>
			</view>

			<!-- 资料拉取失败：页面内提示 + 点击重试，不把用户踢回上一页 -->
			<view v-if="profileError" class="retry" hover-class="zn-hover" @tap="refreshProfile">
				<uni-icons type="info" :size="16" color="#ff4d4f"></uni-icons>
				<text class="retry__text">{{ profileError }}，点击重试</text>
			</view>

			<!-- 求职偏好数据（简历）拉取失败：本区块单独提示，不影响其它设置项 -->
			<view v-if="resumeState === 'error'" class="retry" hover-class="zn-hover" @tap="refreshResume">
				<uni-icons type="info" :size="16" color="#ff4d4f"></uni-icons>
				<text class="retry__text">求职偏好加载失败，点击重试</text>
			</view>

			<!-- ---------- 设置分组（分组与文案优先来自 rcSettingGroups） ---------- -->
			<view v-for="(group, gi) in groups" :key="group.title + '-' + gi" class="group">
				<text class="group__title">{{ group.title }}</text>
				<view class="group__card">
					<view v-for="item in group.items" :key="item.id" class="row"
						:class="{ 'row--button': item.type === 'button' }" hover-class="zn-hover"
						@tap="onItemTap(item)">
						<!-- 按钮项（清除缓存 / 退出登录）：整行就是一颗按钮，不再重复左侧标题 -->
						<view v-if="item.type === 'button'" class="row__btn"
							:class="{ 'is-danger': isDangerItem(item) }">
							<text class="row__btn-text" :class="{ 'is-danger': isDangerItem(item) }">{{ item.name }}</text>
						</view>
						<template v-else>
							<text class="row__label">{{ item.name }}</text>
							<view class="row__right">
								<!-- 开关：本地偏好，不伪造「已同步服务端」 -->
								<switch v-if="item.type === 'switch'" :checked="!!item.value" color="#00A6A7"
									@change="onSwitchChange(item, $event)" />
								<!-- 只读文字 -->
								<text v-else-if="item.type === 'text'" class="row__value">{{ item.value }}</text>
								<!-- 跳转项：右侧可带一个说明值 -->
								<template v-else>
									<text v-if="item.value" class="row__value">{{ item.value }}</text>
									<uni-icons type="right" :size="15" color="#c8ced6"></uni-icons>
								</template>
							</view>
						</template>
					</view>
				</view>
			</view>

			<text class="version">{{ version }} · 直聘通招聘平台</text>
		</view>
	</view>
</template>

<script>
	/**
	 * 设置（账号与安全 / 求职偏好 / 关于与协议）
	 *
	 * ⚠️⚠️ 配置与功能的分界线（后来者务必先读这一段）⚠️⚠️
	 *   `rcSettingGroups` 只负责「有哪些分组、每组的标题、每行的文案、右侧展示什么类型」，
	 *   也就是**纯展示层**。真正的功能一律由本文件内的本地逻辑 + services/user.js 接口实现：
	 *     - 配置项的 id 只是「这一行对应哪个功能」的键，通过 ACTION_BY_ID 映射到本地方法；
	 *     - 配置里的 link 字段**不参与跳转**（种子里还留着 /pages/setting/password 之类旧路由，
	 *       直接跳会打开不存在的页面），跳转目标同样写死在本地映射里；
	 *     - 因此在后台改配置只会改变页面长相，**永远不会**改变行为。
	 *       想改行为请改这里的 ACTION_BY_ID / 对应方法，或者在服务端新增接口。
	 *
	 * 数据来源：
	 *   getInfo()                        services/user.js   账号资料
	 *   updateInfo() / changePassword()  services/user.js   改昵称/头像/密码
	 *   logout()                         services/user.js   退出登录（本地清 token 才是真登出）
	 *   getConfig('rcSettingGroups')     services/content.js 分组与文案
	 *   getResume()                      services/apply.js  求职偏好（期望城市/职位/薪资）
	 *
	 * 三态：账号资料与简历各自维护「加载中 / 失败可重试 / 空（未填写）」，
	 *      失败时绝不显示上一个账号的残留值，也不编造默认值。
	 */
	import { todoTip } from '@/common/utils/format.js'
	import { getConfig } from '@/services/content.js'
	import { getResume } from '@/services/apply.js'
	import {
		getInfo,
		updateInfo,
		changePassword,
		logout,
		clearLoginState,
		isLogined,
		getCachedUser,
		maskEmail,
		setCachedHasPassword,
		setLastLoginHasPassword
	} from '@/services/user.js'

	/** 账号资料骨架（不复用学习端 mock 里的假昵称/等级/积分） */
	const DEFAULT_USER = {
		id: '',
		nickname: '',
		email: '',
		avatar: '',
		signature: '',
		hasPassword: false
	}

	const VERSION = 'v1.0.0'

	/**
	 * 本地兜底分组（配置不可用时的降级数据）
	 *
	 * 为什么设置页也允许兜底：与宫格同理，「有哪些设置项」属于导航结构而非业务事实。
	 * 配置读不到就把整页设置项清空，等于让用户连退出登录/改密码都找不到，
	 * 这比「分组标题退回默认文案」糟糕得多。注意兜底里**没有任何业务数据**，
	 * 展示值（昵称/邮箱/期望城市…）仍然只能来自接口。
	 */
	const FALLBACK_GROUPS = [
		{
			title: '账号与安全',
			items: [
				{ id: 'set-nickname', name: '昵称', value: '', type: 'text', link: '' },
				{ id: 'set-email', name: '邮箱', value: '', type: 'text', link: '' },
				{ id: 'set-avatar', name: '更换头像', value: '', type: 'link', link: '' },
				{ id: 'set-password', name: '修改登录密码', value: '', type: 'link', link: '' },
				{ id: 'set-bind', name: '第三方账号绑定', value: '未绑定', type: 'link', link: '' }
			]
		},
		{
			title: '简历与隐私',
			items: [
				{ id: 'set-resume-public', name: '简历公开（允许 HR 搜索到我）', value: true, type: 'switch', link: '' },
				{ id: 'set-hide-company', name: '对当前公司隐藏简历', value: true, type: 'switch', link: '' },
				{ id: 'set-privacy', name: '隐私政策', value: '', type: 'link', link: '' },
				{ id: 'set-agreement', name: '用户服务协议', value: '', type: 'link', link: '' },
				{ id: 'set-safety', name: '求职安全提示', value: '', type: 'link', link: '' }
			]
		},
		{
			title: '消息与提醒',
			items: [
				{ id: 'set-job-push', name: '职位推荐推送', value: true, type: 'switch', link: '' },
				{ id: 'set-referral-push', name: '内推机会提醒', value: false, type: 'switch', link: '' }
			]
		},
		{
			title: '关于',
			items: [
				{ id: 'set-cache', name: '清除缓存', value: '', type: 'button', link: '' },
				{ id: 'set-feedback', name: '意见反馈', value: '', type: 'link', link: '' },
				{ id: 'set-about', name: '关于直聘通', value: VERSION, type: 'text', link: '' },
				{ id: 'set-logout', name: '退出登录', value: '', type: 'button', link: '' }
			]
		}
	]

	/** 求职偏好组（本地常量，配置里没有时补上，保证这项展示永远存在） */
	const RESUME_GROUP = {
		title: '求职偏好',
		items: [
			{ id: 'set-city', name: '期望城市', value: '', type: 'text', link: '' },
			{ id: 'set-position', name: '期望职位', value: '', type: 'text', link: '' },
			{ id: 'set-salary', name: '期望薪资', value: '', type: 'text', link: '' }
		]
	}

	/** 求职偏好三项的 id（这三项统一跳简历页，值统一来自 getResume） */
	const RESUME_ITEM_IDS = ['set-city', 'set-position', 'set-salary']

	/**
	 * 配置项 id → 本地功能
	 * ⚠️ 这是本页唯一的行为映射表；配置里出现未登记的 id 一律走 todoTip（明确告知暂未开放），
	 *    绝不会因为「配置写了 link」就去跳一个没人维护的地址。
	 */
	const ACTION_BY_ID = {
		'set-nickname': 'nickname',
		'set-email': 'email',
		'set-phone': 'email', // 种子用的是手机号项，本端账号体系是邮箱，就地统一口径
		'set-avatar': 'avatar',
		'set-password': 'password',
		'set-bind': 'bind',
		'set-resume-public': 'switch',
		'set-hide-company': 'switch',
		'set-privacy': 'privacy',
		'set-agreement': 'agreement',
		'set-safety': 'safety',
		'set-city': 'resume',
		'set-position': 'resume',
		'set-salary': 'resume',
		'set-job-push': 'switch',
		'set-referral-push': 'switch',
		'set-cache': 'cache',
		'set-feedback': 'feedback',
		'set-about': 'about',
		'set-logout': 'logout'
	}

	/**
	 * 可本地持久化的开关项
	 * ⚠️ 这些开关服务端**没有**对应接口（简历公开的真实开关在简历页的 isOpen 字段上），
	 *    所以它们只写本地存储、明确属于「本机偏好」，不伪装成已同步到服务端。
	 */
	const PERSIST_KEYS = ['set-resume-public', 'set-hide-company', 'set-job-push', 'set-referral-push']

	/**
	 * 本地存储 key
	 * ⚠️ 与学习端时期的 'zn_settings' 分开命名：旧值里的 push/download/speed/quality
	 *    在招聘端已无意义，混用会让「清除缓存后仍有旧键残留」变得难以排查。
	 */
	const SETTINGS_KEY = 'zn_recruit_settings'

	/** 清除缓存时**必须保留**的键：登录态与上次登录信息，清掉会把用户直接踢下线 */
	const KEEP_STORAGE_KEYS = ['zn_token', 'zn_user', 'zn_last_login']

	export default {
		data() {
			return {
				version: VERSION,
				user: Object.assign({}, DEFAULT_USER),
				groups: [],
				profileLoading: true,
				profileError: '', // 账号资料失败提示
				resume: {},
				resumeExists: false,
				resumeState: 'loading' // loading / ready / error
			}
		},
		async onLoad() {
			// 登录守卫：本页内容全部依赖登录态，未登录直接退回
			if (!isLogined()) {
				uni.showToast({ title: '请先登录', icon: 'none' })
				setTimeout(() => this.back(), 600)
				return
			}

			// 先用本地缓存渲染账号卡，再拉服务端最新资料
			this.user = Object.assign({}, DEFAULT_USER, getCachedUser() || {})

			await this.loadGroups()
			this.applyDisplayValues()
			this.restoreSettings()

			// 两个请求互不依赖，并发发出；各自维护失败态，一个失败不影响另一个
			this.refreshProfile()
			this.refreshResume()
		},
		methods: {
			/** 返回上一页；无上一页时回到个人中心 */
			back() {
				const pages = getCurrentPages()
				if (pages.length > 1) {
					uni.navigateBack({ delta: 1 })
				} else {
					uni.reLaunch({ url: '/pages/mine/mine' })
				}
			},

			/* ---------------- 分组配置 ---------------- */
			/**
			 * 读取分组配置；失败或结构异常时用本地兜底
			 * 配置只影响「长什么样」，见文件头说明。
			 */
			async loadGroups() {
				let groups = null
				try {
					const value = await getConfig('rcSettingGroups')
					if (Array.isArray(value) && value.length) groups = value
				} catch (e) {
					groups = null
				}
				const source = groups || FALLBACK_GROUPS
				this.groups = source.map((group, gi) => ({
					title: group.title || ('设置 ' + (gi + 1)),
					items: (group.items || []).map((item, ii) => ({
						id: item.id || ('set-' + gi + '-' + ii),
						// 配置里的 name/value 属于文案，可以照用；行为由 ACTION_BY_ID 决定
						name: item.name || '设置项',
						value: item.value === undefined ? '' : item.value,
						type: ['switch', 'text', 'link', 'button'].indexOf(item.type) > -1 ? item.type : 'link'
					}))
				}))
				this.ensureResumeGroup()
			},
			/** 保证「求职偏好」组一定存在（配置里没有就补本地默认，避免这项展示被配置改丢） */
			ensureResumeGroup() {
				const hasResumeItems = RESUME_ITEM_IDS.some(id => !!this.findItem(id))
				if (hasResumeItems) return
				this.groups.push({
					title: RESUME_GROUP.title,
					items: RESUME_GROUP.items.map(item => Object.assign({}, item))
				})
			},
			/** 在分组里按 id 找到设置项 */
			findItem(id) {
				for (const group of this.groups) {
					const hit = group.items.find(item => item.id === id)
					if (hit) return hit
				}
				return null
			},

			/* ---------------- 展示值回填 ---------------- */
			/**
			 * 把真实数据写进各行的展示值
			 * ⚠️ 这些值全部来自接口（账号资料 / 简历），配置里的同名 value 只是默认文案，会被真实值覆盖。
			 */
			applyDisplayValues() {
				const nick = this.findItem('set-nickname')
				if (nick) nick.value = this.user.nickname || '未设置'

				// 邮箱项：种子里叫 set-phone「手机号」，本端统一按邮箱口径展示（脱敏）
				const email = this.findItem('set-email') || this.findItem('set-phone')
				if (email) {
					email.name = '邮箱'
					email.value = this.user.email || '未绑定'
				}

				const about = this.findItem('set-about')
				if (about) about.value = VERSION

				const bind = this.findItem('set-bind')
				if (bind) bind.value = '未绑定'
			},
			/** 求职偏好三项：值来自 getResume()，并按加载状态如实显示 */
			applyResumeValues() {
				const r = this.resume || {}
				const read = field => {
					if (this.resumeState === 'loading') return '加载中…'
					if (this.resumeState === 'error') return '加载失败'
					if (!this.resumeExists) return '未填写'
					return r[field] || '未填写'
				}
				const city = this.findItem('set-city')
				if (city) city.value = read('expectedCity')
				const position = this.findItem('set-position')
				if (position) position.value = read('expectedPosition')
				const salary = this.findItem('set-salary')
				if (salary) salary.value = read('expectedSalaryText')
			},

			/* ---------------- 数据加载 ---------------- */
			/**
			 * 拉取账号资料
			 * ⚠️ 只有「登录态确实失效」才退回上一页（请求层已在鉴权失败时清除本地登录态）；
			 *    网络抖动等其它错误保留页面，改为行内提示 + 点击重试，避免把用户踢走。
			 */
			async refreshProfile() {
				this.profileError = ''
				this.profileLoading = true
				try {
					const data = await getInfo()
					// ⚠️ 接口返回的是完整邮箱，展示口径统一脱敏
					this.user = Object.assign({}, DEFAULT_USER, data, { email: maskEmail(data.email) })
					this.applyDisplayValues()
				} catch (e) {
					if (!isLogined()) {
						uni.showToast({ title: '登录已失效，请重新登录', icon: 'none' })
						setTimeout(() => this.back(), 800)
						return
					}
					this.profileError = '账号资料加载失败'
				} finally {
					this.profileLoading = false
				}
			},
			/** 拉取简历（只为「求职偏好」展示，不在此页修改简历内容） */
			async refreshResume() {
				this.resumeState = 'loading'
				this.applyResumeValues()
				try {
					const res = await getResume()
					this.resume = (res && res.resume) || {}
					this.resumeExists = !!(res && res.exists)
					this.resumeState = 'ready'
				} catch (e) {
					this.resume = {}
					this.resumeExists = false
					this.resumeState = 'error'
				}
				this.applyResumeValues()
			},

			/* ---------------- 本地偏好持久化 ---------------- */
			/** 读取本地保存的偏好并回填（没保存过的项保留配置/兜底里的默认值） */
			restoreSettings() {
				const saved = this.readSettings()
				PERSIST_KEYS.forEach(id => {
					const item = this.findItem(id)
					if (item && saved[id] !== undefined) item.value = saved[id]
				})
			},
			readSettings() {
				try {
					const raw = uni.getStorageSync(SETTINGS_KEY)
					if (raw && typeof raw === 'object' && !Array.isArray(raw)) return raw
				} catch (e) {}
				return {}
			},
			/** 写入单个开关（按 id 合并，避免只改一项时覆盖其它项） */
			saveSetting(id, value) {
				if (PERSIST_KEYS.indexOf(id) === -1) return
				const saved = this.readSettings()
				saved[id] = value
				try {
					uni.setStorageSync(SETTINGS_KEY, saved)
				} catch (e) {}
			},

			/* ---------------- 展示辅助 ---------------- */
			/** 危险操作（退出登录）用红色文案，与普通按钮区分开 */
			isDangerItem(item) {
				return item.id === 'set-logout'
			},

			/* ---------------- 点击分发 ---------------- */
			onItemTap(item) {
				// 开关项由 switch 的 change 事件处理，避免重复触发
				if (item.type === 'switch') return
				const action = ACTION_BY_ID[item.id]
				switch (action) {
					case 'nickname':
						this.onChangeNickname()
						break
					case 'email':
						uni.showToast({ title: '当前账号 ' + (this.user.email || '未绑定邮箱'), icon: 'none' })
						break
					case 'avatar':
						this.onChangeAvatar()
						break
					case 'password':
						this.onChangePassword()
						break
					case 'bind':
						uni.showToast({ title: '第三方账号绑定暂未开放', icon: 'none' })
						break
					case 'privacy':
						this.goAgreement('privacy')
						break
					case 'agreement':
						this.goAgreement('agreement')
						break
					case 'safety':
						this.goAgreement('safety')
						break
					case 'resume':
						this.goResume()
						break
					case 'cache':
						this.onClearCache(item)
						break
					case 'feedback':
						this.onFeedback()
						break
					case 'about':
						this.onAbout()
						break
					case 'logout':
						this.onLogout()
						break
					default:
						// 配置里新增了本页未登记的功能：如实提示，不猜、不硬跳
						todoTip(item.name)
				}
			},

			/* ---------------- 账号类操作（走 services/user.js） ---------------- */
			onEditProfile() {
				uni.showToast({ title: '点击下方「昵称 / 更换头像」即可修改资料', icon: 'none' })
			},
			/** 头像：服务端本期没有图片上传接口，上传项如实给出提示 */
			onChangeAvatar() {
				uni.showActionSheet({
					itemList: ['拍照', '从相册选择', '恢复默认头像'],
					success: async res => {
						if (res.tapIndex === 2) {
							// 清除头像：服务端 avatar 置空串，前端回退为昵称首字占位
							try {
								const data = await updateInfo({ avatar: '' })
								this.user = Object.assign({}, this.user, data, { email: maskEmail(data.email) })
								uni.showToast({ title: '已恢复默认头像', icon: 'none' })
							} catch (e) {}
							return
						}
						uni.showToast({ title: '头像上传接口暂未开放', icon: 'none' })
					}
				})
			},
			/** 昵称：弹窗输入并提交服务端 */
			onChangeNickname() {
				uni.showModal({
					title: '修改昵称',
					editable: true,
					placeholderText: '请输入新的昵称（1~20 字）',
					confirmColor: '#00A6A7',
					success: async res => {
						if (!res.confirm) return
						const name = (res.content || '').trim()
						if (!name) {
							uni.showToast({ title: '昵称不能为空', icon: 'none' })
							return
						}
						// 本地预校验：与服务端限制（1~20 字）保持一致，减少无效请求
						if (name.length > 20) {
							uni.showToast({ title: '昵称需 1~20 字', icon: 'none' })
							return
						}
						try {
							const data = await updateInfo({ nickname: name })
							this.user = Object.assign({}, this.user, data, { email: maskEmail(data.email) })
							this.applyDisplayValues()
							uni.showToast({ title: '昵称修改成功', icon: 'none' })
						} catch (e) {
							// 失败提示已由请求层统一弹出
						}
					}
				})
			},
			/**
			 * 修改密码：按账号是否已有密码分流
			 *  - 已有密码（hasPassword=true）：两步弹窗，先校验原密码（verify=old）；
			 *  - 未设密码（多为验证码首次登录）：单步直接设新密码（verify=set），免去再收一次验证码的割裂体验。
			 */
			onChangePassword() {
				if (!this.user.hasPassword) {
					uni.showModal({
						title: '设置登录密码',
						editable: true,
						placeholderText: '请输入 6~20 位新密码',
						confirmColor: '#00A6A7',
						success: async res => {
							if (!res.confirm) return
							const newPwd = (res.content || '').trim()
							if (newPwd.length < 6 || newPwd.length > 20) {
								uni.showToast({ title: '密码需 6~20 位', icon: 'none' })
								return
							}
							try {
								await changePassword({ verify: 'set', new_password: newPwd })
								setCachedHasPassword(true)
								setLastLoginHasPassword(true)
								this.user.hasPassword = true
								uni.showToast({ title: '密码设置成功', icon: 'success' })
							} catch (e) {}
						}
					})
					return
				}

				uni.showModal({
					title: '修改密码',
					editable: true,
					placeholderText: '请输入原密码',
					confirmColor: '#00A6A7',
					success: res => {
						if (!res.confirm) return
						const oldPwd = (res.content || '').trim()
						if (!oldPwd) {
							uni.showToast({ title: '原密码不能为空', icon: 'none' })
							return
						}
						uni.showModal({
							title: '设置新密码',
							editable: true,
							placeholderText: '请输入 6~20 位新密码',
							confirmColor: '#00A6A7',
							success: async res2 => {
								if (!res2.confirm) return
								const newPwd = (res2.content || '').trim()
								if (newPwd.length < 6 || newPwd.length > 20) {
									uni.showToast({ title: '新密码需 6~20 位', icon: 'none' })
									return
								}
								try {
									await changePassword({ verify: 'old', old_password: oldPwd, new_password: newPwd })
									uni.showToast({ title: '密码修改成功', icon: 'none' })
								} catch (e) {
									// ⚠️ 原密码错误会返回 40008，服务端文案已足够清晰
								}
							}
						})
					}
				})
			},

			/* ---------------- 其它操作 ---------------- */
			/** 协议与政策：type = agreement / privacy / jobinfo / safety */
			goAgreement(type) {
				uni.navigateTo({
					url: '/pages/mine/agreement?type=' + type,
					fail: () => uni.showToast({ title: '协议页面打开失败，请稍后重试', icon: 'none' })
				})
			},
			/** 求职偏好：统一回到简历管理页修改（本页只做展示） */
			goResume() {
				uni.navigateTo({
					url: '/pages/seeker/resume',
					fail: () => uni.showToast({ title: '简历页面打开失败，请稍后重试', icon: 'none' })
				})
			},
			/**
			 * 清除缓存
			 * ⚠️ 只清理业务缓存键，**保留登录态**（zn_token / zn_user / zn_last_login），
			 *    否则「清缓存」会变成一次意外的退出登录。
			 * ⚠️ 会一并清掉本页的偏好开关，下次进入回到默认值 —— 这是清缓存的应有语义。
			 */
			onClearCache(item) {
				uni.showModal({
					title: '清除缓存',
					content: '将清理已缓存的职位与图片数据（不会退出登录），确定继续吗？',
					confirmColor: '#00A6A7',
					success: res => {
						if (!res.confirm) return
						const count = this.clearBusinessStorage()
						item.value = ''
						uni.showToast({
							title: count > 0 ? '已清理 ' + count + ' 项缓存' : '暂无缓存可清理',
							icon: 'none'
						})
					}
				})
			},
			clearBusinessStorage() {
				try {
					const info = uni.getStorageInfoSync()
					let count = 0
					;(info.keys || []).forEach(key => {
						if (KEEP_STORAGE_KEYS.indexOf(key) > -1) return
						uni.removeStorageSync(key)
						count++
					})
					return count
				} catch (e) {
					return 0
				}
			},
			onFeedback() {
				// 演示环境没有工单系统：如实告知渠道，不伪造「已提交」的假成功
				uni.showModal({
					title: '意见反馈',
					content: '演示环境暂未接入工单系统。正式环境请通过「设置 - 关于直聘通 - 客服邮箱」反馈，或在使用帮助中提交问题。',
					showCancel: false,
					confirmColor: '#00A6A7'
				})
			},
			onAbout() {
				uni.showModal({
					title: '关于直聘通',
					content: '版本 ' + VERSION + '\n直聘通是面向求职者与招聘方的招聘平台：找工作直接和 HR 谈，发布职位、筛选简历、安排面试一站完成。',
					confirmText: '查看协议',
					cancelText: '知道了',
					confirmColor: '#00A6A7',
					success: res => {
						if (res.confirm) this.goAgreement('agreement')
					}
				})
			},
			/** 开关项：改本地数据并写入本地存储，保证重进页面仍然生效 */
			onSwitchChange(item, e) {
				item.value = e.detail.value
				this.saveSetting(item.id, item.value)
				uni.showToast({
					title: item.name + (item.value ? '已开启' : '已关闭'),
					icon: 'none'
				})
			},

			/* ---------------- 退出登录 ---------------- */
			onLogout() {
				uni.showModal({
					title: '提示',
					content: '确定要退出当前账号吗？退出后需重新登录才能查看投递与面试信息。',
					confirmColor: '#00A6A7',
					success: async res => {
						if (!res.confirm) return
						try {
							// ⚠️ JWT 无状态，该调用仅为语义完整性；失败（如 token 已过期）不阻塞本地登出
							await logout()
						} catch (e) {}
						clearLoginState()
						uni.showToast({ title: '已退出登录', icon: 'none' })
						setTimeout(() => this.back(), 800)
					}
				})
			}
		}
	}
</script>

<style lang="scss" scoped>
	.settings__body {
		padding: $zn-gap $zn-page-padding 60rpx;
	}

	/* ---------- 账号卡 ---------- */
	.profile {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: $zn-gap-lg $zn-gap;
		box-shadow: $zn-shadow-sm;
	}

	.profile__info {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		margin-left: $zn-gap;
	}

	.profile__name {
		font-size: $zn-font-lg;
		font-weight: 700;
		color: $zn-text-title;
	}

	.profile__sub {
		font-size: $zn-font-sm;
		color: $zn-text-grey;
		margin-top: 10rpx;
	}

	/* ---------- 失败重试行 ---------- */
	.retry {
		display: flex;
		flex-direction: row;
		align-items: center;
		background-color: #fff1f0;
		border-radius: $zn-radius-sm;
		padding: 18rpx 20rpx;
		margin-top: $zn-gap;
	}

	.retry__text {
		font-size: $zn-font-sm;
		color: $zn-red;
		margin-left: 10rpx;
		flex: 1;
		min-width: 0;
	}

	/* ---------- 设置分组 ---------- */
	.group {
		margin-top: $zn-gap-lg;
	}

	.group__title {
		display: block;
		font-size: $zn-font-sm;
		color: $zn-text-grey;
		padding-left: 8rpx;
		margin-bottom: 14rpx;
	}

	.group__card {
		background-color: $zn-bg-card;
		border-radius: $zn-radius-lg;
		padding: 0 $zn-gap;
		box-shadow: $zn-shadow-sm;
	}

	.row {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: space-between;
		min-height: 104rpx;
		border-bottom: 1rpx solid $zn-line;

		&:last-child {
			border-bottom: none;
		}

		/* 按钮项整行居中 */
		&--button {
			justify-content: center;
		}
	}

	.row__label {
		font-size: $zn-font-md;
		color: $zn-text-main;
		flex-shrink: 1;
		padding-right: 16rpx;
	}

	.row__right {
		display: flex;
		flex-direction: row;
		align-items: center;
		justify-content: flex-end;
		flex: 1;
		min-width: 0;
	}

	.row__value {
		font-size: $zn-font;
		color: $zn-text-grey;
		margin-right: 12rpx;
		max-width: 360rpx;
		overflow: hidden;
		white-space: nowrap;
		text-overflow: ellipsis;
	}

	/* 按钮项（清除缓存 / 退出登录）：整行一颗胶囊按钮 */
	.row__btn {
		height: 60rpx;
		padding: 0 40rpx;
		border-radius: $zn-radius-pill;
		background-color: $zn-theme-light;
		display: flex;
		align-items: center;
		justify-content: center;

		&.is-danger {
			background-color: #fff1f0;
		}
	}

	.row__btn-text {
		font-size: $zn-font;
		font-weight: 600;
		color: $zn-theme-deep;

		&.is-danger {
			color: $zn-red;
		}
	}

	/* ---------- 版本号 ---------- */
	.version {
		display: block;
		text-align: center;
		font-size: $zn-font-xs;
		color: $zn-text-light;
		margin-top: $zn-gap-lg;
	}
</style>
