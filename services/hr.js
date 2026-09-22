/**
 * 企业 HR 端接口封装
 *
 * 对应服务端 /api/v1/hr/*（见 server/app/routers/hr.py）。
 *
 * ⚠️ 使用前提：当前账号必须**已绑定公司**（POST /hr/bind）。
 *    未绑定时除 me / companies / bind 之外的接口都会返回 403（code 40301）。
 *    页面进入企业端前应先调 getHrMe()，bound=false 就引导去绑定。
 *
 * ⚠️ 数据隔离：服务端一律按「你绑定的公司」过滤，
 *    前端**不要也不必传 companyId**（职位发布、简历查询都如此）。
 *
 * ⚠️ 全部接口都需要登录（auth: true）。
 */
import { request } from '@/services/api.js'
import { toQuery } from '@/services/api.js'

/* ==========================================================
 * 身份
 * ========================================================== */

/**
 * 我的招聘方身份
 * @returns {Promise<{bound:boolean,role:object|null,company:object|null}>}
 *   bound=false → 还没绑定公司，引导到绑定页
 */
export function getHrMe() {
	return request('/hr/me', { auth: true })
}

/**
 * 可选公司列表（演示环境直接选一家绑定，不做企业资质审核）
 * @param {object} [params] {keyword, limit}
 */
export function getCompanies(params) {
	return request('/hr/companies' + toQuery(params), { auth: true })
}

/**
 * 绑定公司，成为招聘方
 *
 * @param {object} params {companyId, hrTitle}
 * @returns {Promise<{bound:boolean,company:object,adoptedJobs:number}>}
 *
 * ⚠️ adoptedJobs 是**接管过来的职位数**：绑定后会把该公司「没有归属招聘者」的
 *    职位挂到当前账号名下，否则求职者点「立即沟通」会找不到聊天对象。
 */
export function bindCompany(params) {
	return request('/hr/bind', {
		method: 'POST',
		data: {
			companyId: params.companyId,
			hrTitle: params.hrTitle || '招聘经理'
		},
		auth: true
	})
}

/* ==========================================================
 * 工作台
 * ========================================================== */

/**
 * 工作台概览
 *
 * @returns {Promise<object>}
 *   company             {id,name,shortName,logoText,logoColor}
 *   hrTitle             当前 HR 的职位
 *   stats               {openJobs,totalJobs,totalApplications,pending,interviewing,hired,todayApplications}
 *   recentApplications  最近 5 条投递（已按 HR 视角翻译状态文案）
 *   upcomingInterviews  即将到来的面试（最多 5 场）
 */
export function getHrDashboard() {
	return request('/hr/dashboard', { auth: true })
}

/* ==========================================================
 * 职位管理
 * ========================================================== */

/**
 * 我发布的职位
 * @param {object} [params] {status, page, pageSize}
 *   status: 1=在招 / 0=已关闭；不传返回全部
 * @returns {Promise<{list:Array,total:number,page:number,pageSize:number,hasMore:boolean}>}
 *   list 元素是职位卡片 + status/statusText/applicationCount（收到简历数）/descriptionText
 */
export function getMyJobs(params) {
	return request('/hr/jobs' + toQuery(params), { auth: true })
}

/**
 * 发布职位
 *
 * @param {object} data
 *   title, categoryId（必须是**二级**职能分类）, cityId, district,
 *   salaryMin, salaryMax（单位 K，min 必须小于 max）, salaryMonths（12~20）,
 *   experience, education, jobType, kind,
 *   tags[], description, requirements, process[]（招聘流程步骤）, status（1 上架 / 0 存草稿）
 * @returns {Promise<{job:object}>} 新职位的 id 由服务端生成（j + 递增编号）
 *
 * ⚠️ 不要传 companyId：归属只能来自你绑定的公司（服务端会忽略）。
 */
export function createJob(data) {
	return request('/hr/jobs', { method: 'POST', data: data || {}, auth: true })
}

/**
 * 编辑职位（字段与 createJob 相同，同样是全量覆盖）
 * @param {string} jobId
 * @param {object} data
 */
export function updateJob(jobId, data) {
	return request('/hr/jobs/' + encodeURIComponent(String(jobId || '')), {
		method: 'PUT',
		data: data || {},
		auth: true
	})
}

/**
 * 职位上下架
 * @param {string} jobId
 * @param {number} status 1=招聘中 / 0=关闭
 */
export function setJobStatus(jobId, status) {
	return request('/hr/jobs/' + encodeURIComponent(String(jobId || '')) + '/status', {
		method: 'POST',
		data: { status },
		auth: true
	})
}

/**
 * 删除职位（服务端是逻辑删除）
 *
 * ⚠️ 删除不会让候选人的投递记录失联：投递行里存了职位快照。
 */
export function deleteJob(jobId) {
	return request('/hr/jobs/' + encodeURIComponent(String(jobId || '')), {
		method: 'DELETE',
		auth: true
	})
}

/* ==========================================================
 * 收到的简历
 * ========================================================== */

/**
 * 收到的简历列表
 * @param {object} [params] {jobId, status, page, pageSize}
 * @returns {Promise<{list:Array,total:number,page:number,pageSize:number,hasMore:boolean,counts:object}>}
 *   counts 是各状态数量（列表页筛选标签的角标用），如 {submitted:3, viewed:1}
 *   list 元素：投递信息 + candidate（候选人简历摘要：姓名/学历/经验/期望/技能/完整度）
 *
 * ⚠️ HR 视角的状态文案与求职者不同（同一份 submitted，求职者看「已投递」、
 *    HR 看「待处理」），服务端已按角色翻译，前端直接用 statusText。
 */
export function getApplications(params) {
	return request('/hr/applications' + toQuery(params), { auth: true })
}

/**
 * 候选人详情
 *
 * @param {number|string} id 投递ID
 * @returns {Promise<{application:object}>}
 *   application.candidate        简历摘要
 *   application.candidateDetail  简历完整内容（含教育/工作/项目经历）
 *   application.interviews       该候选人的面试邀约
 *   application.job              职位快照
 *
 * ⚠️ 调这个接口会**把投递状态从「待处理」推进为「已查看」**（服务端副作用，只做一次）。
 *    因此不要在列表页预加载详情，否则状态会被批量刷成已查看。
 */
export function getHrApplicationDetail(id) {
	return request('/hr/applications/' + encodeURIComponent(String(id || '')), { auth: true })
}

/**
 * 变更候选人状态
 *
 * @param {number|string} id 投递ID
 * @param {object} data {status, remark, rating}
 *   status 只能是 viewed / chatting / passed / hired / rejected
 *   （「待面试 interview」必须走 inviteInterview，保证状态与邀约记录一致）
 * @returns {Promise<{application:object}>}
 *
 * ⚠️ 状态流转由服务端状态机单点校验，非法流转返回 409（code 40910）。
 *    前端应把不允许的按钮置灰，但不能只靠置灰。
 */
export function updateApplicationStatus(id, data) {
	return request('/hr/applications/' + encodeURIComponent(String(id || '')) + '/status', {
		method: 'POST',
		data: data || {},
		auth: true
	})
}

/**
 * 发出面试邀约
 *
 * @param {number|string} id 投递ID
 * @param {object} data
 *   roundNo, roundName, interviewTime（**格式必须是 'YYYY-MM-DD HH:MM'**）,
 *   durationMin, mode('onsite'|'video'|'phone'), address, onlineLink,
 *   interviewer, contact, remark
 * @returns {Promise<{interview:object,applicationStatus:string}>}
 *
 * ⚠️ 时间格式由服务端严格校验，格式不对返回 400（code 40014）。
 *    uni-app 的日期选择器给的是时间戳或 'YYYY-MM-DD'，页面需要自己补上时分。
 * ⚠️ 调用成功后投递状态会自动推进为「待面试」（仅当状态机允许时）。
 */
export function inviteInterview(id, data) {
	return request('/hr/applications/' + encodeURIComponent(String(id || '')) + '/interview', {
		method: 'POST',
		data: data || {},
		auth: true
	})
}

/* ==========================================================
 * 面试安排 / 公司信息
 * ========================================================== */

/**
 * 面试安排（按时间正序，HR 关心「接下来面谁」）
 * @param {object} [params] {status, page, pageSize}
 *   status: pending/confirmed/finished/canceled
 * @returns {Promise<{list:Array,total:number,page:number,pageSize:number,hasMore:boolean}>}
 *   list 元素是面试邀约 + jobTitle + candidate（候选人摘要）
 */
export function getInterviews(params) {
	return request('/hr/interviews' + toQuery(params), { auth: true })
}

/**
 * 公司信息（企业主页）
 */
export function getCompany() {
	return request('/hr/company', { auth: true })
}

/**
 * 更新公司信息
 *
 * @param {object} data 只传要改的字段即可；**空字符串表示「不改这一项」**，
 *   所以清空某个字段要传具体的新值，不能靠传空串。
 */
export function updateCompany(data) {
	return request('/hr/company', { method: 'PUT', data: data || {}, auth: true })
}
