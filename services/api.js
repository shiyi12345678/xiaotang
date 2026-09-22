/**
 * 网络请求封装（基于 uni.request）
 *
 * 职责：
 *   1. 统一拼接 BASE_URL；
 *   2. 需要鉴权的接口自动注入 Authorization: Bearer <token>；
 *   3. 把服务端的 { code, msg, data } 归一化：
 *        code === 0  → resolve(data)
 *        code !== 0  → reject(Error)，错误对象上附带 code
 *   4. 鉴权失败（40100/40101/40102 或 HTTP 401）自动清除本地登录态；
 *   5. 网络异常统一转为友好提示，不把原始异常抛给页面。
 *
 * ⚠️ 与服务端的约定（不可更改）：
 *    成功码是 0（不是 200），消息字段是 msg（不是 message）。
 *    这与项目原有的 common/utils/format.js 中 mockRequest 的结构完全一致。
 */
import { BASE_URL, TIMEOUT } from '@/common/config.js'
import { storage } from '@/common/utils/format.js'

/** 登录态存储 key（与登录页、我的页、设置页共用） */
export const USER_KEY = 'zn_user'
export const TOKEN_KEY = 'zn_token'

/** 需要清除登录态的鉴权错误码 */
const AUTH_CODES = [40100, 40101, 40102]

/** 防止并发请求同时触发多次「登录失效」提示 */
let authNotified = false

/**
 * 拼装完整请求地址
 * @param {string} url 形如 '/user/login'，也允许直接传完整 http(s) 地址
 */
function buildUrl(url) {
	if (/^https?:\/\//i.test(url)) return url
	return BASE_URL + (url.charAt(0) === '/' ? url : '/' + url)
}

/**
 * 构造统一错误对象
 * @param {string} msg  提示文案
 * @param {number} code 业务错误码（-1 表示非业务错误）
 * @param {number} status HTTP 状态码
 */
function makeError(msg, code, status) {
	const err = new Error(msg || '请求失败')
	err.code = typeof code === 'number' ? code : -1
	err.status = status || 0
	return err
}

/** 轻提示（错误文案） */
function toastError(err) {
	uni.showToast({ title: err.message || '请求失败', icon: 'none', duration: 1800 })
}

/**
 * 处理鉴权失败：清除本地登录态并提示一次
 * ⚠️ 这里不主动跳转登录页——由各页面自行决定引导方式，
 *    避免用户在浏览其他页面时被强制打断。
 */
function handleAuthFail(msg) {
	storage.remove(TOKEN_KEY)
	storage.remove(USER_KEY)
	if (authNotified) return
	authNotified = true
	uni.showToast({ title: msg || '登录已失效，请重新登录', icon: 'none', duration: 1800 })
	setTimeout(() => {
		authNotified = false
	}, 1500)
}

/**
 * 发起请求
 *
 * @param {string} url  接口路径，如 '/user/login'
 * @param {object} [options]
 * @param {string}  [options.method='GET']    请求方法
 * @param {object}  [options.data={}]         请求体
 * @param {boolean} [options.auth=false]      是否携带 token
 * @param {boolean} [options.showError=true]  失败时是否自动弹提示
 * @returns {Promise<any>} resolve 服务端 data 字段
 */
export function request(url, options = {}) {
	const {
		method = 'GET',
		data = {},
		auth = false,
		showError = true
	} = options

	return new Promise((resolve, reject) => {
		const header = { 'Content-Type': 'application/json' }

		// 需要登录的接口：注入 token
		if (auth) {
			const token = storage.get(TOKEN_KEY)
			if (token) header.Authorization = 'Bearer ' + token
		}

		uni.request({
			url: buildUrl(url),
			method,
			data,
			header,
			timeout: TIMEOUT,
			success: res => {
				const body = res.data
				const httpOk = res.statusCode >= 200 && res.statusCode < 300

				// ---------- HTTP 层异常 ----------
				if (!httpOk) {
					const bizCode = body && typeof body === 'object' ? body.code : -1
					const bizMsg = body && typeof body === 'object' ? body.msg : ''
					if (res.statusCode === 401 || AUTH_CODES.indexOf(bizCode) > -1) {
						handleAuthFail(bizMsg)
					}
					const err = makeError(
						bizMsg || ('请求失败(' + res.statusCode + ')'),
						bizCode,
						res.statusCode
					)
					if (showError) toastError(err)
					reject(err)
					return
				}

				// ---------- 响应体格式异常 ----------
				if (!body || typeof body !== 'object') {
					const err = makeError('服务端返回格式异常', -1, res.statusCode)
					if (showError) toastError(err)
					reject(err)
					return
				}

				// ---------- 业务成功 ----------
				if (body.code === 0) {
					resolve(body.data === undefined ? {} : body.data)
					return
				}

				// ---------- 业务失败 ----------
				if (AUTH_CODES.indexOf(body.code) > -1) handleAuthFail(body.msg)
				const err = makeError(body.msg || '操作失败', body.code, res.statusCode)
				if (showError) toastError(err)
				reject(err)
			},
			fail: () => {
				// uni.request 的网络层失败（超时、连接被拒绝等）
				const err = makeError('网络连接失败，请确认服务端已启动', -1, 0)
				if (showError) toastError(err)
				reject(err)
			}
		})
	})
}

/**
 * 把对象拼成查询串（值为空则跳过）
 *
 * 为什么收敛到公共服务层：
 *   招聘域有 20 多个带筛选条件的列表接口，若每个 service 各写一遍拼串逻辑，
 *   「空值要不要发」「要不要 encodeURIComponent」这类细节必然出现不一致。
 *
 * @param {object} params 参数对象；null / undefined / '' 的键会被跳过
 * @returns {string} 形如 '?a=1&b=x'；无有效参数时返回空串
 */
export function toQuery(params) {
	const parts = []
	const source = params || {}
	Object.keys(source).forEach(key => {
		const value = source[key]
		if (value === null || value === undefined || value === '') return
		// 布尔值统一转成 1/0：服务端按数字解析，'false' 字符串反而会被当成真
		const text = typeof value === 'boolean' ? (value ? '1' : '0') : String(value)
		parts.push(encodeURIComponent(key) + '=' + encodeURIComponent(text))
	})
	return parts.length ? '?' + parts.join('&') : ''
}
