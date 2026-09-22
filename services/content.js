/**
 * 内容域接口封装（公开，无需登录）
 *
 * 对应服务端 /api/v1/content/*（见 server/app/routers/content.py）。
 *
 * ⚠️ 招聘改造说明：改造前本文件还封装了课程列表 / 课程详情 / 免费好课 / 搜索数据 /
 *    分类筛选等教育版接口。这些方法在招聘端已无任何页面引用（页面改走 job.js /
 *    interview.js），对应的后端路由 /content/{home,categories,courses} 也已废弃，
 *    故一并移除，只保留招聘端仍在用的 getConfig（读取 page_config 的 rc_ 前缀配置键）。
 *
 * 页面只与本文件交互，不直接调用 request()。
 */
import { request } from '@/services/api.js'

/* ==========================================================
 * 页面配置
 * ========================================================== */

/**
 * 读取一条页面配置的原始 JSON 值
 *
 * @param {string} key 配置键（招聘端均以 rc 前缀命名，如 rcMineGridGroups / rcAiWelcome）
 * @returns {Promise<any>} 该配置的原始值（不包一层 {key,value}，与后端返回形状一致）
 *
 * ⚠️ 配置不存在时服务端报 42001，本函数会让 Promise reject（不吞错）。
 *    调用方若是「可有可无」的配置，请自行 catch。
 */
export function getConfig(key) {
	return request('/content/config/' + encodeURIComponent(String(key || '')))
}
