/**
 * 通用工具函数（纯前端 Mock 项目，无需后端）
 */

/* ---------------- 渐变占位色板：用于「封面图 / 封面图占位」 ----------------
 * 项目为纯 Mock、不依赖任何图片资源，因此封面统一用渐变色块 + 文字水印渲染，
 * 接入真实图片时，只需把 zn-cover 组件的 src 传进来即可。
 */
export const coverGradients = [
	'linear-gradient(135deg, #4cd964 0%, #2bb14c 100%)',
	'linear-gradient(135deg, #43c6ac 0%, #191654 100%)',
	'linear-gradient(135deg, #3b9dff 0%, #3f5efb 100%)',
	'linear-gradient(135deg, #ffb75e 0%, #ed8f03 100%)',
	'linear-gradient(135deg, #f78ca0 0%, #f9748f 60%, #fe9a8b 100%)',
	'linear-gradient(135deg, #8a6cf6 0%, #5b3cc4 100%)',
	'linear-gradient(135deg, #00c6ff 0%, #0072ff 100%)',
	'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
	'linear-gradient(135deg, #13f1fc 0%, #0470dc 100%)',
	'linear-gradient(135deg, #fa709a 0%, #fee140 100%)'
]

/** 字符串简易哈希，保证同一文案每次拿到同一个渐变色 */
export function hashCode(str = '') {
	let hash = 0
	const s = String(str)
	for (let i = 0; i < s.length; i++) {
		hash = (hash << 5) - hash + s.charCodeAt(i)
		hash |= 0
	}
	return Math.abs(hash)
}

/** 按 key 取渐变色 */
export function gradientOf(key = '', offset = 0) {
	const idx = (hashCode(key) + offset) % coverGradients.length
	return coverGradients[idx]
}

/** 取文案首字，用于头像/封面水印 */
export function firstChar(str = '') {
	const s = String(str).trim()
	// ⚠️ 招聘改造：空文案默认字由「云」（网易云课堂）改为「聘」（直聘通），
	//    仅头像占位组件 zn-avatar 使用，影响面极小。
	if (!s) return '聘'
	// 中文取第一个字，英文取首字母
	return /[\u4e00-\u9fa5]/.test(s[0]) ? s[0] : s[0].toUpperCase()
}

/**
 * 安全 URI 解码：解码失败（如畸形 % 序列）时回退原值，绝不抛异常。
 *
 * 背景：uni-app 各端对 onLoad(options) 的传参编码行为不一致，页面里需要手动
 *       decodeURIComponent 还原中文/特殊字符。但若参数含孤立 %（如 "%" 后非两位
 *       十六进制），原生 decodeURIComponent 会抛 URIError，导致页面 onLoad 中断。
 * @param {string} str 待解码字符串
 * @returns {string} 解码成功返回明文，失败返回原值
 */
export function safeDecode(str) {
	try {
		return decodeURIComponent(String(str == null ? '' : str))
	} catch (e) {
		return str
	}
}

/** 价格格式化：99 -> 99，99.5 -> 99.5，null -> '免费' */
export function formatPrice(p) {
	if (p === 0 || p === '0') return '免费'
	if (p === null || p === undefined || p === '') return '价格待定'
	const num = Number(p)
	return Number.isInteger(num) ? String(num) : num.toFixed(2)
}

/** 价格小数部分，用于「¥99 .00」这种大小字混排 */
export function priceDecimal(p) {
	const num = Number(p)
	if (!num || Number.isInteger(num)) return ''
	return '.' + num.toFixed(2).split('.')[1]
}

/** 补零 */
export function padZero(n) {
	return String(n).padStart(2, '0')
}

/** 时间戳/日期 -> 相对时间文案 */
export function fromNow(time) {
	const t = new Date(time).getTime()
	if (isNaN(t)) return ''
	const diff = Date.now() - t
	const min = 60000
	const hour = 60 * min
	const day = 24 * hour
	if (diff < min) return '刚刚'
	if (diff < hour) return Math.floor(diff / min) + '分钟前'
	if (diff < day) return Math.floor(diff / hour) + '小时前'
	if (diff < 30 * day) return Math.floor(diff / day) + '天前'
	const d = new Date(t)
	return `${d.getFullYear()}-${padZero(d.getMonth() + 1)}-${padZero(d.getDate())}`
}

/** 状态栏高度 */
export function getStatusBarHeight() {
	const sys = uni.getSystemInfoSync()
	return sys.statusBarHeight || 0
}

/**
 * 底部安全区高度（px）
 *
 * ⚠️ 坐标系坑（2026-09-21 修复一个 H5 必现 bug）：
 *    浏览器运行时 uni.getSystemInfoSync() 返回的三者是**两个坐标系**：
 *      screenHeight    = 显示器/屏幕高度（无头 Chrome 实测 600）
 *      windowHeight    = 浏览器可视区高度（实测 482）
 *      safeArea.bottom = 以「可视区」为坐标系的底部 y（实测 482）
 *    旧实现统一用 `screenHeight - safeArea.bottom`，于是 600-482 = 118px 的**假安全区**，
 *    底部 tabBar 被从 108rpx(≈109px) 撑到 228px，中央凸起的「AI 助手」圆钮因此上移到
 *    页面中部，恰好盖住职位卡片 —— 点击职位时命中的是 tabBar，直接 reLaunch 到 AI 页，
 *    表象就是「点工作没反应、不弹岗位详情和投递简历按钮」。
 *
 * 修复原则：**只在同一坐标系内相减**。
 *    H5        → 用 windowHeight（与 safeArea 同坐标系）：浏览器无刘海得 0，iPhone Safari 得 34
 *    App/小程序 → 沿用 screenHeight（真机上 safeArea 以屏幕为坐标系，行为与修复前完全一致）
 */
export function getSafeAreaBottom() {
	const sys = uni.getSystemInfoSync()
	// 拿不到安全区信息（部分环境不提供）就直接按 0 处理，避免算出随机值把布局顶飞
	if (!sys.safeArea) return 0
	let gap
	// #ifdef H5
	// H5：screenHeight 是显示器高度，与 safeArea 不同源，必须改用 windowHeight
	gap = (sys.windowHeight || sys.screenHeight) - sys.safeArea.bottom
	// #endif
	// #ifndef H5
	// App / 小程序：safeArea 基于屏幕坐标，沿用屏幕高度相减（真机行为不变）
	gap = sys.screenHeight - sys.safeArea.bottom
	// #endif
	return gap > 0 ? gap : 0
}

/**
 * 模拟接口请求（纯前端 Mock，不需要后端）
 * @param {Any} data 要返回的数据
 * @param {Number} delay 模拟网络延迟
 */
export function mockRequest(data, delay = 300) {
	return new Promise(resolve => {
		setTimeout(() => {
			resolve({
				code: 0,
				msg: 'ok',
				data: typeof data === 'function' ? data() : data
			})
		}, delay)
	})
}

/** 轻提示 */
export function toast(title, icon = 'none') {
	uni.showToast({ title, icon, duration: 1600 })
}

/** 开发中占位提示（Mock 项目常用） */
export function todoTip(name = '该功能') {
	uni.showToast({ title: `${name}开发中（Mock）`, icon: 'none', duration: 1500 })
}

/** 本地存储封装 */
export const storage = {
	get(key, def = null) {
		try {
			const v = uni.getStorageSync(key)
			return v === '' || v === undefined ? def : v
		} catch (e) {
			return def
		}
	},
	set(key, val) {
		try {
			uni.setStorageSync(key, val)
		} catch (e) {}
	},
	remove(key) {
		try {
			uni.removeStorageSync(key)
		} catch (e) {}
	}
}

/** 防抖 */
export function debounce(fn, wait = 300) {
	let timer = null
	return function (...args) {
		if (timer) clearTimeout(timer)
		timer = setTimeout(() => fn.apply(this, args), wait)
	}
}
