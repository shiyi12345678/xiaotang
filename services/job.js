/**
 * 职位域接口封装（求职者端）
 *
 * 对应服务端 /api/v1/job/*（见 server/app/routers/job.py）：
 *   GET    /home                 首页聚合（轮播/职能入口/公告/热词/推荐/内推/急招）
 *   GET    /categories           职能分类（一级含子类 + 扁平子类 + 首页入口）
 *   GET    /cities               城市（热门 + 全量 + 首字母分组）
 *   GET    /filters              筛选条件（薪资档/经验/学历/职位形态）
 *   GET    /list                 职位列表 / 搜索（同一接口，有 keyword 即搜索）
 *   GET    /detail/{id}          职位详情（含公司与相似职位）
 *   GET    /favorite/ids         我收藏的职位 id 集合（🔒）
 *   GET    /favorite/list        我的收藏（🔒）
 *   POST   /favorite             收藏（🔒，幂等）
 *   DELETE /favorite/{id}        取消收藏（🔒，幂等）
 *
 * ⚠️ 字段纪律：服务端返回的键已是 camelCase（见 server/app/schemas/job.py），
 *    本层**不做字段改写与兜底**，拿到什么返回什么 —— 契约不一致要在联调阶段暴露。
 *
 * ⚠️ 收藏类接口必须登录（auth: true），未登录时服务端返回 401，
 *    本层不吞这个错误，由页面决定是提示登录还是隐藏入口。
 */
import { request } from '@/services/api.js'
import { toQuery } from '@/services/api.js'

/* ==========================================================
 * 浏览（公开）
 * ========================================================== */

/**
 * 首页聚合数据（一次请求拿全）
 *
 * @returns {Promise<object>} 服务端保证以下键**永远存在**（缺失给 [] 而不是 undefined）：
 *   banners       轮播 [{id,tag,title,subtitle,link}]
 *   entries       职能入口 [{id,name,icon,color,bg,link}]
 *   notices       公告文案数组
 *   hotKeywords   搜索热词数组
 *   listTabs      职位列表页顶部标签 [{id,name,kind}]
 *   recommend     推荐职位（10 条，卡片结构见 getList 的说明）
 *   referral      名企内推职位
 *   urgent        急招职位
 *   totalJobs     在招职位总数
 */
export function getJobHome() {
	return request('/job/home')
}

/**
 * 职能分类
 *
 * @returns {Promise<{list:Array,flat:Array,home:Array}>}
 *   list 一级分类（每项带 children 子类数组）
 *   flat 全部二级分类（筛选用）
 *   home 首页入口分类（kind=home）
 *
 * ⚠️ 分类元素同时带 name 与 title（服务端有意为之的兼容别名），
 *    分类页读 name、首页入口读 title，两边都不用改字段名。
 */
export function getJobCategories() {
	return request('/job/categories')
}

/**
 * 城市列表
 * @returns {Promise<{hot:Array,all:Array,groups:Array}>}
 *   groups 形如 [{initial:'B',cities:[...]}]，已按字母序排好，可直接渲染索引列表
 */
export function getCities() {
	return request('/job/cities')
}

/**
 * 筛选条件
 * @returns {Promise<{filters:object,kinds:Array}>}
 *   filters = {salary:[{label,min,max}], experience:[], education:[], jobType:[{label,value}]}
 */
export function getJobFilters() {
	return request('/job/filters')
}

/**
 * 职位列表 / 搜索
 *
 * @param {object} [params]
 * @param {string} [params.keyword]    关键词，匹配职位名或公司名（传了就是搜索）
 * @param {string} [params.category]   职能分类 id；传一级分类会自动展开为全部子类
 * @param {string} [params.city]       城市 id
 * @param {string} [params.salary]     薪资区间，形如 '10-20'（单位 K）
 * @param {number} [params.salaryMin]  薪资下限（与 salary 二选一）
 * @param {number} [params.salaryMax]  薪资上限
 * @param {string} [params.experience] 经验要求（中文枚举，如 '3-5年'）
 * @param {string} [params.education]  学历要求（中文枚举，如 '本科'）
 * @param {string} [params.kind]       normal/urgent/referral/intern/campus
 * @param {string} [params.jobType]    fulltime/intern/parttime
 * @param {string} [params.sort]       default/salary/new/hot（也接受中文，如 '薪资最高'）
 * @param {number} [params.page=1]
 * @param {number} [params.pageSize=10] 1~50
 * @returns {Promise<{list:Array,total:number,page:number,pageSize:number,hasMore:boolean}>}
 *
 * 卡片字段（list 元素）：
 *   id/title/kind/salaryText/salaryMin/salaryMax/salaryMonths
 *   cityName/district/location        location 是「北京·海淀区」合并文案
 *   experience/education/jobType/tags
 *   companyId/companyName/companyFullName/logoText/logoColor/industry/scale/stage
 *   hrName/hrTitle/hrActive
 *   viewCount/applicantCount/publishAt/publishText   publishText 如「3天前」
 *   isFavorite
 *
 * ⚠️ 薪资过滤是**区间重叠**语义：筛 20-30K 会命中 25-45K 的职位（因为二者有交集），
 *    这与招聘类产品的通行做法一致，页面文案上不要写成「薪资在此区间内」。
 */
export function getJobList(params) {
	return request('/job/list' + toQuery(params))
}

/**
 * 职位详情
 *
 * @param {string} id 职位ID，如 j2001
 * @returns {Promise<{job:object,similar:Array}>}
 *   job 在卡片字段基础上多出：description[]/requirements[]（已按条切好）、
 *   process[]（招聘流程步骤）、statusText/jobTypeText、company（完整公司信息）、
 *   referralBonus/isRemote
 *
 * ⚠️ 调用这个接口会让职位浏览量 +1（服务端行为），页面不要重复轮询详情。
 * ⚠️ 职位不存在或已下线 → 服务端 404（code 40401），Promise reject。
 */
export function getJobDetail(id) {
	return request('/job/detail/' + encodeURIComponent(String(id || '')))
}

/* ==========================================================
 * 收藏（需登录）
 * ========================================================== */

/**
 * 我收藏的职位 id 集合
 *
 * 用途：列表页一次性拿到集合，在本地给卡片打标，
 *       避免「每张卡片各发一个请求」造成几十个并发请求。
 * @returns {Promise<string[]>}
 */
export async function getFavoriteIds() {
	const res = await request('/job/favorite/ids', { auth: true, showError: false })
	return (res && res.ids) || []
}

/**
 * 我的收藏列表
 * @param {object} [params] {page, pageSize}
 * @returns {Promise<{list:Array,total:number,page:number,pageSize:number,hasMore:boolean}>}
 *   list 元素是职位卡片 + favoriteAt（收藏时间）
 */
export function getFavoriteList(params) {
	return request('/job/favorite/list' + toQuery(params), { auth: true })
}

/**
 * 收藏职位（幂等：重复收藏不报错，changed=false）
 * @param {string} jobId
 * @returns {Promise<{jobId:string,favorited:boolean,changed:boolean}>}
 */
export function addFavorite(jobId) {
	return request('/job/favorite', {
		method: 'POST',
		data: { jobId },
		auth: true
	})
}

/**
 * 取消收藏（幂等）
 * @param {string} jobId
 */
export function removeFavorite(jobId) {
	return request('/job/favorite/' + encodeURIComponent(String(jobId || '')), {
		method: 'DELETE',
		auth: true
	})
}

/**
 * 切换收藏状态（页面最常用的语义化封装）
 *
 * @param {string} jobId
 * @param {boolean} [favorited] 当前是否已收藏；不传则先查一次集合
 * @returns {Promise<boolean>} 切换后的收藏状态
 */
export async function toggleFavorite(jobId, favorited) {
	let current = favorited
	if (current === undefined || current === null) {
		const ids = await getFavoriteIds()
		current = ids.indexOf(jobId) > -1
	}
	if (current) {
		await removeFavorite(jobId)
		return false
	}
	await addFavorite(jobId)
	return true
}
