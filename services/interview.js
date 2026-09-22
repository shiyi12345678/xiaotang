/**
 * 面试题库接口封装（求职者的「备考侧」）
 *
 * 对应服务端 /api/v1/interview/*（见 server/app/routers/interview.py）：
 *   GET  /banks                题库分类（按二级职能聚合，只返回有题的分类）—— 公开
 *   GET  /questions            题目列表（分类/难度/关键词过滤 + 分页）—— 公开
 *   GET  /questions/{id}       题目详情（含参考答案）—— 公开
 *   POST /questions/{id}/record 提交作答结果（🔒）
 *   GET  /wrong                薄弱点（答错过的题，同题去重取最近）—— 🔒
 *   GET  /progress             刷题进度统计（🔒）
 *
 * ⚠️ 列表接口**不返回 answer**（答案在详情接口才给）：
 *    这是服务端刻意的取舍 —— 一次列表 20 题，把答案一起带回来会让响应体大好几倍。
 *    因此「刷题」这类需要即时看答案的页面，要么按题拉详情，要么预先取一次详情。
 *
 * ⚠️ 「薄弱点」的口径（服务端取舍，页面文案要跟着走）：
 *    进入薄弱点的条件 = 这道题**曾经答错过**（不是「最近一次答错」），
 *    因此列表里会包含「曾经答错、最近已经答对」的题 —— 此时 lastResult=1，
 *    页面可以据此显示「已攻克」。这与旧学习端错题本的语义一致。
 *    因此 weakTotal 可能**大于** getPracticeProgress().wrong（后者只算最近一次答错的题），
 *    这是有意的差别，不是数据不一致。
 */
import { request } from '@/services/api.js'
import { toQuery } from '@/services/api.js'

/* ==========================================================
 * 题库浏览（公开）
 * ========================================================== */

/**
 * 题库分类
 *
 * @returns {Promise<{banks:Array,total:number,hot:number}>}
 *   banks 元素：{id, name, count, position}（只含有题目的分类）
 *   total 题库总题数 / hot 热门题数
 */
export function getBanks() {
	return request('/interview/banks')
}

/**
 * 题目列表
 *
 * @param {object} [params]
 * @param {string} [params.category]   二级职能分类 id，如 cat-tech-backend
 * @param {number} [params.difficulty] 1=基础 / 2=进阶 / 3=困难
 * @param {string} [params.keyword]    关键词（匹配题干）
 * @param {number} [params.page=1]
 * @param {number} [params.pageSize=20] 1~50
 * @returns {Promise<{list:Array,total:number,page:number,pageSize:number,hasMore:boolean}>}
 *   list 元素：{id,categoryId,position,question,difficulty,difficultyText,tags,source,frequency,isHot}
 */
export function getQuestions(params) {
	return request('/interview/questions' + toQuery(params))
}

/**
 * 题目详情（唯一返回 answer 的接口）
 *
 * @param {string} id 题目ID，如 q3001
 * @returns {Promise<{question:object}>} question 含 answer（参考答案/答题要点）
 *
 * ⚠️ 返回的是 {question: {...}} 这一层包装，不是扁平的题目对象 ——
 *    与 /job/detail 返回 {job, similar}、/apply/detail 返回 {application} 的风格一致。
 *    页面取值要写 res.question.answer。
 */
export function getQuestionDetail(id) {
	return request('/interview/questions/' + encodeURIComponent(String(id || '')))
}

/* ==========================================================
 * 刷题与统计（需登录）
 * ========================================================== */

/**
 * 提交作答结果
 *
 * @param {string} id 题目ID
 * @param {object} params
 * @param {number} params.result 1=会 / 0=不会（0 会进薄弱点）
 * @param {string} [params.mode] practice=顺序刷题 / memory=背诵模式 / review=薄弱点复盘
 * @param {number} [params.durationSec] 本题耗时（秒）
 */
export function recordQuestion(id, params) {
	return request('/interview/questions/' + encodeURIComponent(String(id || '')) + '/record', {
		method: 'POST',
		data: {
			result: params.result,
			mode: params.mode || 'practice',
			durationSec: params.durationSec || 0
		},
		auth: true
	})
}

/**
 * 薄弱点列表（曾经答错过的题）
 *
 * @param {object} [params] {category, page, pageSize}
 * @returns {Promise<{list:Array,total:number,page:number,pageSize:number,hasMore:boolean}>}
 *   list 元素是题目字段 + lastResult（最近一次作答结果）+ lastTime + wrongCount（答错次数）
 *
 * ⚠️ 过滤条件是「曾经答错」（wrongCount > 0），所以 lastResult=1 的题也会出现，
 *    表示「已攻克」。口径细节见本文件顶部说明。
 */
export function getWrongQuestions(params) {
	return request('/interview/wrong' + toQuery(params), { auth: true })
}

/**
 * 刷题进度
 *
 * @returns {Promise<object>}
 *   total       题库总题数
 *   answered    已作答的不同题目数
 *   mastered    最近一次作答为「会」的题数
 *   wrong       最近一次作答为「不会」的题数
 *   accuracy    掌握率（整数百分比）
 *   byCategory  [{categoryId, name, answered, total}]
 *
 * ⚠️ mastered / wrong 按「每题最近一次结果」判定，
 *    因此 answered ≠ mastered + wrong 只会在数据异常时出现。
 */
export function getPracticeProgress() {
	return request('/interview/progress', { auth: true })
}
