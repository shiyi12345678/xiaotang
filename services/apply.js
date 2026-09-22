/**
 * 投递与简历域接口封装（求职者端）
 *
 * 对应服务端：
 *   /api/v1/apply/*   （见 server/app/routers/apply.py）
 *     POST   /                     投递职位
 *     GET    /list                 我的投递
 *     GET    /stats                求职中心统计（漏斗 + 待办）
 *     GET    /detail/{id}          投递详情（含面试邀约）
 *     POST   /{id}/withdraw        撤回投递
 *   /api/v1/resume/*  （同文件的 resume_router）
 *     GET    /                     我的简历
 *     PUT    /                     保存简历
 *     GET    /report               求职报告
 *
 * ⚠️ 投递状态机（前后端必须一致，服务端唯一实现处是 server/app/schemas/hr.py）：
 *   submitted 已投递 → viewed 简历已查看 → chatting 沟通中 → interview 待面试
 *   → passed 面试通过 → hired 已入职；任意阶段可能走向 rejected 不合适；
 *   submitted/viewed/chatting 阶段求职者可 withdraw 撤回。
 *   页面拿到的 statusText 已由服务端按「求职者视角」翻译好，**不要在前端再写一套文案**。
 *
 * ⚠️ 全部接口都需要登录（auth: true）。
 */
import { request } from '@/services/api.js'
import { toQuery } from '@/services/api.js'

/* ==========================================================
 * 投递
 * ========================================================== */

/**
 * 投递职位
 *
 * @param {object} params
 * @param {string} params.jobId    职位ID
 * @param {string} [params.greeting] 打招呼语（≤200 字）
 * @returns {Promise<{application:object}>}
 *
 * ⚠️ 两种失败要分开处理（服务端错误码不同）：
 *   40901 已经投递过这个职位（HTTP 409）→ 前端应提示「已投递」并跳转到投递记录
 *   40902 该职位已停止招聘（HTTP 409）
 * ⚠️ 服务端会做职位名/公司名/薪资的**快照**，因此不要在前端传这些字段。
 */
export function applyJob(params) {
	return request('/apply', {
		method: 'POST',
		data: {
			jobId: params.jobId,
			greeting: params.greeting || ''
		},
		auth: true
	})
}

/**
 * 我的投递列表
 *
 * @param {object} [params] {status, page, pageSize}
 *   status 可选：submitted/viewed/chatting/interview/passed/hired/rejected/withdrawn
 * @returns {Promise<{list:Array,total:number,page:number,pageSize:number,hasMore:boolean}>}
 *   list 元素：id/jobId/jobTitle/companyId/companyName/salaryText/status/statusText/
 *             statusType(info|warning|success|danger)/greeting/createdAt/createdText
 */
export function getMyApplications(params) {
	return request('/apply/list' + toQuery(params), { auth: true })
}

/**
 * 投递详情（含面试邀约与职位快照）
 *
 * @param {number|string} id 投递ID
 * @returns {Promise<{application:object}>} application.interviews 为面试邀约数组
 */
export function getApplicationDetail(id) {
	return request('/apply/detail/' + encodeURIComponent(String(id || '')), { auth: true })
}

/**
 * 撤回投递
 *
 * ⚠️ 已进入面试流程（interview/passed/hired/rejected）后服务端会拒绝：
 *    40903 → HTTP 409。前端应在按钮上先做置灰，但**不能只靠置灰**。
 */
export function withdrawApplication(id) {
	return request('/apply/' + encodeURIComponent(String(id || '')) + '/withdraw', {
		method: 'POST',
		auth: true
	})
}

/**
 * 求职中心统计
 *
 * @returns {Promise<object>}
 *   delivered           累计投递数
 *   favorited           收藏数
 *   byStatus            各状态数量 {submitted:1, viewed:0, ...}
 *   funnel              漏斗 [{stage,label,count}]，5 个阶段
 *   upcomingInterviews  即将到来的面试（最多 5 场）
 *   interviewRate       面试转化率（整数百分比）
 *
 * ⚠️ funnel 是**累计**口径（进入面试的人必然先被查看），
 *    与 byStatus（当前状态快照）不是一回事，页面上别混用。
 */
export function getApplyStats() {
	return request('/apply/stats', { auth: true })
}

/* ==========================================================
 * 简历
 * ========================================================== */

/**
 * 我的简历
 *
 * @returns {Promise<{resume:object,exists:boolean}>}
 *   exists=false 时 resume 是一份**结构完整、值为空**的模板（不是 null），
 *   并已用账号信息预填 name/email/phone —— 表单可以直接双向绑定，无需判空。
 */
export function getResume() {
	return request('/resume', { auth: true })
}

/**
 * 保存简历（全量覆盖式）
 *
 * @param {object} data 简历字段，字段名用 camelCase：
 *   name, gender(0/1/2), birthYear, phone, email, city,
 *   educationLevel, school, major, graduationYear, workYears, currentStatus,
 *   expectedCity, expectedPosition, expectedSalaryMin, expectedSalaryMax,
 *   skills[], advantage, educations[], experiences[], projects[], isOpen
 * @returns {Promise<{resume:object}>} 返回保存后的简历（含服务端算好的 completeness）
 *
 * ⚠️ 是**全量覆盖**：表单里没带上来的字段会被置空。
 *    因此页面必须用 getResume() 的返回值初始化表单，再整体提交。
 */
export function saveResume(data) {
	return request('/resume', { method: 'PUT', data: data || {}, auth: true })
}

/**
 * 求职报告
 *
 * @returns {Promise<object>}
 *   funnel  [{stage,label,count}] 求职漏斗
 *   radar   [{name,value,desc}] 求职力雷达（5 个维度，value 为 0~100）
 *   tips    [string] 改进建议（规则算出来的，不是 AI 生成）
 *   summary {delivered,interviewed,passed,favorited,answered,completeness,interviewRate}
 *
 * ⚠️ 雷达与建议都由服务端按规则计算：它们要可解释、可复现，且不消耗 AI 额度；
 *    AI 的深度分析在 services/chat.js（求职助手）里单独提供。
 */
export function getResumeReport() {
	return request('/resume/report', { auth: true })
}
