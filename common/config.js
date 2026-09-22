/**
 * 全局运行配置
 *
 * ===================== 一劳永逸改造说明（2026-09-19） =====================
 *
 * 【旧做法的问题】
 *   曾经把电脑的局域网 IP 硬编码在 BASE_URL 里。路由器每次重新分配地址，
 *   前端就连不上后端（本项目已发生过 192.168.6.25 → .20 → .13 两次），
 *   表现为「页面一片空白、控制台却不报错」，必须手动改回来。
 *
 * 【新做法】
 *   H5 端不再写死 IP，而是**在运行时自动推断**后端地址：
 *   取浏览器地址栏里的主机名，拼上后端端口 8000。
 *     · 电脑打开 http://127.0.0.1:5173/     → 请求 http://127.0.0.1:8000
 *     · 电脑打开 http://localhost:5173/     → 请求 http://localhost:8000
 *     · 手机打开 http://192.168.6.13:5173/  → 请求 http://192.168.6.13:8000
 *   原理：**能打开页面的那个地址，必然就是能连到这台电脑的地址。**
 *   所以换 IP、换网段、换路由器、改用手机访问，都不需要再改这个文件。
 *
 * ⚠️ 前提：后端必须监听 0.0.0.0（server/start_server.bat 已经是这么启动的）。
 * ⚠️ 后端端口若有改动，只需同步改下面的 API_PORT —— 全项目只有这一处端口配置。
 * ⚠️ App / 小程序端没有 location，无法自动推断，仍用 APP_BASE_URL；
 *     只有做 App 真机调试且电脑换了网段时，才需要改那一行。
 *
 * 💡 临时把前端指向别的后端（例如后端跑在另一台机器）：
 *     在浏览器控制台执行
 *       localStorage.setItem('zn_api_base', 'http://10.0.0.5:8000/api/v1')
 *     然后刷新页面。清除：localStorage.removeItem('zn_api_base')
 */

/** 后端端口（必须与 server/start_server.bat 的 --port 一致） */
export const API_PORT = 8000

/**
 * 公网部署专用地址（留空 = 按上面的规则自动推断）
 * ⚠️ 将来把前端部署到公网时，把后端的公网地址填在这里；本地开发保持留空。
 *    详见 docs/部署方案-公网可访问.md
 */
const PROD_BASE_URL = ''

/**
 * App / 小程序端使用的后端地址（这两端没有 location，无法自动推断）
 * ⚠️ 只有做 App 真机调试、且电脑换了网段时，才需要改这一行。
 */
const APP_BASE_URL = 'http://192.168.6.13:8000/api/v1'

/** 运行时覆盖用的 localStorage key（仅 H5 生效） */
const OVERRIDE_KEY = 'zn_api_base'

/** 去掉末尾斜杠 */
function trimSlash(url) {
	return String(url).replace(/\/+$/, '')
}

/**
 * 计算后端基础地址（末尾不带斜杠）
 */
function resolveBaseUrl() {
	// #ifdef H5
	// 1) 公网部署时以 PROD_BASE_URL 为准
	if (PROD_BASE_URL) return trimSlash(PROD_BASE_URL)
	// 2) 允许运行时覆盖（调试用）
	try {
		const saved = localStorage.getItem(OVERRIDE_KEY)
		if (saved) return trimSlash(saved)
	} catch (e) {
		// 隐私模式等场景下 localStorage 不可用，忽略即可
	}
	// 3) 默认：用「打开页面的主机名」拼后端端口
	const host = (typeof location !== 'undefined' && location.hostname) ? location.hostname : '127.0.0.1'
	return 'http://' + host + ':' + API_PORT + '/api/v1'
	// #endif

	// #ifndef H5
	return APP_BASE_URL
	// #endif
}

/** 服务端接口基础地址（末尾不带斜杠） */
export const BASE_URL = resolveBaseUrl()

/** 单次请求超时时间（毫秒） */
export const TIMEOUT = 15000
