/**
 * 用户体系接口封装（邮箱验证码体系）
 *
 * 对应服务端 /api/v1/user/*：
 *   发送邮箱验证码 / 注册 / 登录 / 查资料 / 改资料 / 改密码 / 退出登录 / 注销
 *
 * 页面只与本文件交互，不直接调用 request()，
 * 这样接口路径与字段名变化时只需改这里。
 */
import { request, USER_KEY, TOKEN_KEY } from '@/services/api.js'
import { storage } from '@/common/utils/format.js'

/** 上次登录信息存储 key：记录邮箱与是否已设密码，用于下次进登录页默认密码登录 */
const LAST_LOGIN_KEY = 'zn_last_login'

/* ==========================================================
 * 工具
 * ========================================================== */

/**
 * 邮箱脱敏：zhangsan@qq.com → zh***@qq.com
 *
 * 保留用户名前 2 位与完整域名，中间打码；
 * 目的：本地缓存与界面展示不出现完整邮箱。
 */
export function maskEmail(email) {
	const str = String(email || '')
	const at = str.indexOf('@')
	if (at <= 0) return str
	const name = str.slice(0, at)
	const domain = str.slice(at) // 含 @
	if (name.length <= 2) return name + '***' + domain
	return name.slice(0, 2) + '***' + domain
}

/* ==========================================================
 * 接口（与服务端一一对应）
 * ========================================================== */

/**
 * 发送邮箱验证码
 * @param {string} email 邮箱
 * @returns {Promise<{expires_in:number, dev_code?:string}>}
 *          dev_code 仅在服务端 EMAIL_DEBUG=true 时返回，供本地联调使用
 */
export function sendEmailCode(email) {
	return request('/user/email/code', { method: 'POST', data: { email } })
}

/**
 * 注册（邮箱验证码 + 可选密码）
 * @returns {Promise<{token:string, user:object}>}
 */
export function register(payload) {
	const { email, code, password, invite } = payload
	return request('/user/reg', {
		method: 'POST',
		data: { email, code, password, invite }
	})
}

/**
 * 登录
 * @param {{mode:'code'|'pwd', email:string, code?:string, password?:string}} payload
 * @returns {Promise<{token:string, user:object}>}
 */
export function login(payload) {
	const { mode, email, code, password } = payload
	return request('/user/login', {
		method: 'POST',
		data: { mode, email, code, password }
	})
}

/**
 * 查询我的资料（需登录）
 * ⚠️ showError=false：调用方通常只是静默刷新，失败时自行决定是否提示
 */
export async function getInfo() {
	const res = await request('/user/info', { auth: true, showError: false })
	return res.user || {}
}

/**
 * 更新我的资料（需登录）
 * @param {{nickname?:string, avatar?:string, signature?:string}} payload 传了的字段才会更新
 */
export async function updateInfo(payload) {
	const res = await request('/user/info', {
		method: 'PUT',
		data: payload,
		auth: true
	})
	return res.user || {}
}

/**
 * 修改密码（需登录）
 * @param {{verify:'old'|'code', old_password?:string, code?:string, new_password:string}} payload
 */
export function changePassword(payload) {
	return request('/user/password', {
		method: 'PUT',
		data: payload,
		auth: true
	})
}

/**
 * 退出登录（需登录）
 * ⚠️ 服务端 JWT 无状态，此接口仅用于语义完整性；
 *    真正的登出是客户端清除本地 token。
 */
export function logout() {
	return request('/user/logout', { method: 'POST', auth: true, showError: false })
}

/* ==========================================================
 * 登录态管理
 * ========================================================== */

/**
 * 写入登录态
 * @param {{token:string, user:object}} data 服务端登录/注册响应
 *
 * ⚠️ 同时把「是否已设密码」(hasPassword) 与「上次登录邮箱」落本地：
 *    - hasPassword 决定登录后是否弹「设置密码」引导；
 *    - 上次登录邮箱用于下次进登录页回填，并据此默认走密码标签页。
 */
export function saveLoginState(data) {
	const u = (data && data.user) || {}
	storage.set(TOKEN_KEY, (data && data.token) || '')
	storage.set(USER_KEY, {
		id: String(u.id || ''),
		nickname: u.nickname || '',
		// ⚠️ 本地缓存存脱敏邮箱，避免完整邮箱明文落地
		email: maskEmail(u.email),
		avatar: u.avatar || '',
		signature: u.signature || '',
		level: u.level || '',
		levelProgress: u.levelProgress || 0,
		points: u.points || 0,
		isVip: !!u.isVip,
		// ⚠️ 是否已有密码：由服务端返回，前端据此判断要不要引导设密码
		hasPassword: !!u.hasPassword,
		vipExpire: u.vipExpire || '',
		loginTime: Date.now()
	})
	// 记录本次登录邮箱（用真实邮箱，非脱敏）与密码状态，供下次默认密码登录
	setLastLogin(u.email || '', !!u.hasPassword)
}

/**
 * 记录上次登录信息（真实邮箱 + 是否已设密码）
 * @param {string} email 本次登录真实邮箱（未脱敏）
 * @param {boolean} hasPassword 该账号是否已设置密码
 */
export function setLastLogin(email, hasPassword) {
	if (!email) return
	try {
		storage.set(LAST_LOGIN_KEY, { email: String(email), hasPassword: !!hasPassword })
	} catch (e) {}
}

/**
 * 读取上次登录信息
 * @returns {{email:string, hasPassword:boolean}|null}
 */
export function getLastLogin() {
	try {
		const v = storage.get(LAST_LOGIN_KEY)
		if (v && typeof v === 'object' && v.email) return v
	} catch (e) {}
	return null
}

/**
 * 仅更新「上次登录」的已设密码标记（设置密码成功后调用，无需再传邮箱）
 * @param {boolean} value 是否已设置密码
 */
export function setLastLoginHasPassword(value) {
	try {
		const v = storage.get(LAST_LOGIN_KEY)
		if (v && v.email) {
			v.hasPassword = !!value
			storage.set(LAST_LOGIN_KEY, v)
		}
	} catch (e) {}
}

/**
 * 用服务端最新资料刷新本地缓存（保持 token 不变）
 * @param {object} user 服务端返回的 user 结构
 */
export function refreshCachedUser(user) {
	if (!user) return
	const cached = storage.get(USER_KEY) || {}
	storage.set(USER_KEY, Object.assign({}, cached, {
		id: String(user.id || cached.id || ''),
		nickname: user.nickname || cached.nickname || '',
		email: maskEmail(user.email) || cached.email || '',
		avatar: user.avatar === undefined ? (cached.avatar || '') : user.avatar,
		signature: user.signature || '',
		level: user.level || cached.level || '',
		levelProgress: typeof user.levelProgress === 'number' ? user.levelProgress : 0,
		points: typeof user.points === 'number' ? user.points : 0,
		isVip: !!user.isVip,
		// ⚠️ 服务端若回传 hasPassword 则同步；未回传时沿用本地旧值
		hasPassword: typeof user.hasPassword === 'boolean' ? user.hasPassword : cached.hasPassword,
		vipExpire: user.vipExpire || ''
	}))
}

/** 清除本地登录态（token + 用户信息） */
export function clearLoginState() {
	storage.remove(TOKEN_KEY)
	storage.remove(USER_KEY)
}

/**
 * 更新本地缓存用户的是否已设密码标记（设密成功后调用，避免刷新缓存才生效）
 * @param {boolean} value 是否已设置密码
 */
export function setCachedHasPassword(value) {
	const cached = storage.get(USER_KEY)
	if (!cached) return
	cached.hasPassword = !!value
	try {
		storage.set(USER_KEY, cached)
	} catch (e) {}
}

/** 当前是否已登录（需同时具备 user 与 token） */
export function isLogined() {
	return !!(storage.get(USER_KEY) && storage.get(TOKEN_KEY))
}

/** 读取本地缓存的用户信息（未登录返回 null） */
export function getCachedUser() {
	return storage.get(USER_KEY)
}

/** 读取本地 token（未登录返回 null） */
export function getToken() {
	return storage.get(TOKEN_KEY)
}
