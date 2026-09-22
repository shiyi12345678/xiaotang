/**
 * AI 助教服务封装
 *
 * 组成：
 *   1. HTTP 部分：会话列表 / 消息列表 / 删除会话（复用 services/api.js）
 *   2. HTTP 部分：图片上传（multipart/form-data，走 uni.uploadFile）
 *   3. WebSocket 部分：流式对话
 *
 * ⚠️ 为什么用 SocketTask 而不是全局 socket：
 *    uni-app 的全局 socket 只能有一个，一旦被占用就无法再开启，
 *    因此分布式业务一律使用 uni.connectSocket 返回的 SocketTask。
 *    参考：https://uniapp.dcloud.net.cn/api/request/socket-task.html
 */
import { request, TOKEN_KEY } from '@/services/api.js'
import { storage } from '@/common/utils/format.js'
import { BASE_URL } from '@/common/config.js'

/* ==========================================================
 * 内部工具
 * ========================================================== */

/**
 * 构造统一错误对象（与 services/api.js 保持同一口径）
 * @param {string} msg  提示文案
 * @param {number} code 业务错误码（-1 表示非业务错误）
 * @param {number} [status] HTTP 状态码
 */
function makeError(msg, code, status) {
	const err = new Error(msg || '请求失败')
	err.code = typeof code === 'number' ? code : -1
	err.status = status || 0
	return err
}

/* ==========================================================
 * HTTP：会话管理（均需登录）
 * ========================================================== */

/**
 * 会话列表
 * @returns {Promise<Array>} [{ id, title, preview, updatedAt }]
 */
export async function listSessions() {
	const res = await request('/ai/sessions', { auth: true, showError: false })
	return res.list || []
}

/**
 * 会话消息列表
 * @param {string|number} sessionId 会话ID
 * @returns {Promise<{list:Array, title:string}>}
 */
export async function listMessages(sessionId) {
	const res = await request('/ai/sessions/' + sessionId + '/messages', { auth: true })
	return res
}

/**
 * 删除会话（级联删除其消息）
 * @param {string|number} sessionId 会话ID
 */
export function deleteSession(sessionId) {
	return request('/ai/sessions/' + sessionId, { method: 'DELETE', auth: true })
}

/* ==========================================================
 * HTTP：图片上传（拍照 / 相册 / 文件）
 * ========================================================== */

/**
 * 上传一张图片
 *
 * ⚠️ 为什么不复用 services/api.js 的 request：
 *    上传必须走 multipart/form-data，uni.request 在 H5 端拿不到本地文件对象，
 *    只能用 uni.uploadFile（它自带 filePath 上传能力）。
 *    因此这里手动复刻一遍 { code, msg, data } 信封的解析规则：
 *    code === 0 成功、msg 为错误文案 —— 与 services/api.js 的约定完全一致。
 *
 * 失败时 reject 一个 Error：error.code 是服务端业务码（-1 表示网络层失败），
 * error.message 直接就是服务端 msg，页面可以原样展示，不必再翻译。
 *
 * @param {string} filePath 本地临时文件路径（uni.chooseImage / chooseFile 返回）
 * @returns {Promise<{id:string, url:string, name:string, size:number, mime:string}>}
 *          url 为「相对源站」的路径（如 /uploads/ai/xxx.png），展示前需拼源站
 */
export function uploadImage(filePath) {
	const token = storage.get(TOKEN_KEY) || ''
	return new Promise((resolve, reject) => {
		uni.uploadFile({
			url: BASE_URL + '/ai/upload',
			filePath,
			// ⚠️ 字段名必须与服务端一致，改这里会导致后端取不到文件（41011）
			name: 'file',
			header: token ? { Authorization: 'Bearer ' + token } : {},
			success: res => {
				const httpOk = res.statusCode >= 200 && res.statusCode < 300
				let body = null
				try {
					body = JSON.parse(res.data)
				} catch (e) {
					body = null
				}

				if (!httpOk) {
					const bizCode = body && typeof body === 'object' ? body.code : -1
					const bizMsg = body && typeof body === 'object' ? body.msg : ''
					reject(makeError(bizMsg || ('上传失败(' + res.statusCode + ')'), bizCode, res.statusCode))
					return
				}
				if (!body || typeof body !== 'object') {
					reject(makeError('服务端返回格式异常', -1, res.statusCode))
					return
				}
				if (body.code !== 0) {
					// 41009 不是有效图片 / 41010 超过大小上限 / 41011 文件为空：
					// 服务端已给出准确文案，原样抛出交由页面展示
					reject(makeError(body.msg || '上传失败', body.code, res.statusCode))
					return
				}
				resolve(body.data || {})
			},
			fail: () => {
				reject(makeError('网络连接失败，请确认服务端已启动', -1, 0))
			}
		})
	})
}

/* ==========================================================
 * WebSocket：流式对话
 * ========================================================== */

/**
 * 由 BASE_URL 推导 WebSocket 地址
 * http://  → ws://     https:// → wss://
 * token 通过 query 传递（WebSocket 无法自定义请求头）
 */
function buildWsUrl() {
	const base = String(BASE_URL).replace(/^http/, 'ws')
	const token = encodeURIComponent(storage.get(TOKEN_KEY) || '')
	return base + '/ai/chat?token=' + token
}

/**
 * 创建一条对话连接
 *
 * @param {object} handlers 事件回调
 * @param {Function} handlers.onSession 收到 session 帧（懒建会话回传）
 * @param {Function} handlers.onDelta   收到增量文本 (text)
 * @param {Function} handlers.onDone    本轮正常结束
 * @param {Function} handlers.onError   出错 (code, msg)
 * @param {Function} handlers.onClose   连接关闭 (closeCode)
 * @returns {object} 控制器 { chat, stop, close }
 */
export function createChat(handlers) {
	const h = handlers || {}
	let opened = false   // 连接已就绪，可立即发送
	let closed = false   // 连接已彻底关闭，不可再发送
	// 连接尚未就绪时先缓存的待发帧，onOpen 后补发
	const pending = []

	const task = uni.connectSocket({
		url: buildWsUrl(),
		complete: () => {}
	})

	task.onOpen(() => {
		opened = true
		while (pending.length) {
			task.send({ data: JSON.stringify(pending.shift()) })
		}
	})

	task.onMessage(res => {
		let frame = null
		try {
			frame = JSON.parse(res.data)
		} catch (e) {
			return // 非 JSON 帧直接忽略
		}
		const type = frame.type
		if (type === 'session') {
			if (h.onSession) h.onSession(frame)
		} else if (type === 'delta') {
			if (h.onDelta) h.onDelta(frame.content || '')
		} else if (type === 'done') {
			if (h.onDone) h.onDone(frame)
		} else if (type === 'error') {
			if (h.onError) h.onError(frame.code, frame.msg || '对话失败')
		}
	})

	task.onError(() => {
		opened = false
		closed = true
		// 清空待发队列：残留帧若在「意外重连」时被补发，会产生用户看不见的幽灵提问
		pending.length = 0
		if (h.onError) h.onError(-1, '网络连接失败，请确认服务端已启动')
	})

	task.onClose(res => {
		opened = false
		closed = true
		pending.length = 0
		if (h.onClose) h.onClose(res ? res.code : 0)
	})

	/**
	 * 发送一帧
	 *
	 * - 连接未就绪（尚在握手）：先入队，onOpen 后补发；
	 * - 连接已彻底关闭：立即回调 onError，**绝不静默丢弃**。
	 *
	 * ⚠️ 为什么关闭后不能继续入队：
	 *    入队后永远等不到 onOpen，帧就消失了，
	 *    页面的「正在生成」动画会一直转下去，用户看到的现象就是 AI 不回答。
	 */
	function send(frame) {
		if (closed) {
			if (h.onError) h.onError(-1, '连接已断开，请重试')
			return
		}
		if (opened) {
			task.send({ data: JSON.stringify(frame) })
		} else {
			pending.push(frame)
		}
	}

	return {
		/**
		 * 发送提问
		 * @param {string} content 问题文本
		 * @param {string|number} [sessionId] 会话ID；不传则由服务端懒建新会话
		 * @param {Array<string>} [images] 已上传图片的 id 列表（uploadImage 返回的 id）；
		 *        为空时**不下发 images 字段**，文本消息与旧版帧完全一致
		 */
		chat(content, sessionId, images) {
			const frame = { type: 'chat', content: content }
			if (sessionId) frame.session_id = String(sessionId)
			if (images && images.length) frame.images = images
			send(frame)
		},
		/** 中途停止本轮生成 */
		stop() {
			send({ type: 'stop' })
		},
		/** 主动关闭连接 */
		close() {
			try {
				task.close({})
			} catch (e) {
				// 已关闭时忽略
			}
		}
	}
}
