/**
 * 沟通消息接口封装（求职者 ↔ 企业 HR）
 *
 * 对应服务端 /api/v1/chat/*（见 server/app/routers/chat.py）：
 *   GET  /conversations                     会话列表（按角色过滤）—— 🔒
 *   POST /conversations                     从职位发起沟通（已存在则返回原会话）—— 🔒
 *   GET  /conversations/{id}/messages       会话消息（倒序分页后反转为正序）—— 🔒
 *   POST /conversations/{id}/messages       发送消息 —— 🔒
 *   POST /conversations/{id}/read           标记已读（清当前角色未读）—— 🔒
 *   GET  /unread                            两个角色的未读合计 —— 🔒
 *
 * ⚠️ 命名说明：本文件是「人与人的沟通」，
 *    与 services/chat.js（AI 求职助手的对话，走 WebSocket 流式）是两回事，不要混用。
 *
 * ⚠️ role 参数决定「我是哪一方」：
 *    求职者端传 'candidate'，企业端传 'hr'。
 *    服务端据此选择按 candidate_id 还是 hr_id 过滤，
 *    因此同一个账号在两端看到的会话列表是**不同**的（这是正确行为，不是 bug）。
 */
import { request } from '@/services/api.js'
import { toQuery } from '@/services/api.js'

/**
 * 会话列表
 *
 * @param {object} params
 * @param {string} params.role 'candidate' | 'hr'
 * @param {number} [params.page=1]
 * @param {number} [params.pageSize=20]
 * @returns {Promise<{list:Array,total:number,page:number,pageSize:number,hasMore:boolean}>}
 *   list 元素：{id,jobId,jobTitle,companyId,companyName,lastMessage,lastTime,lastText,
 *              unread,role,contactName}
 *   contactName 是对方的名字（求职者看到 HR、HR 看到候选人）
 */
export function getConversations(params) {
	return request('/chat/conversations' + toQuery(params), { auth: true })
}

/**
 * 从职位发起沟通
 *
 * @param {string} jobId 职位ID
 * @returns {Promise<{conversation:object,created:boolean}>}
 *   created=false 表示之前已经聊过，直接复用原会话（**不是错误**）
 *
 * ⚠️ 服务端可能返回 40904「该职位暂未配置招聘者」：
 *    种子里有些职位没有绑定 HR，此时无法发起沟通，页面要给出可读提示。
 */
export function createConversation(jobId) {
	return request('/chat/conversations', {
		method: 'POST',
		data: { jobId },
		auth: true
	})
}

/**
 * 会话消息
 *
 * @param {number|string} conversationId
 * @param {object} [params] {page, pageSize}
 * @returns {Promise<{list:Array,total:number,page:number,pageSize:number,hasMore:boolean,role:string}>}
 *   list 已按时间**正序**返回，可直接渲染；
 *   hasMore=true 表示还有更早的消息，把 page+1 再请求一次即可向上加载历史。
 *   每条消息：{id,senderRole,senderId,content,msgType,extra,isRead,createdAt,timeText,mine}
 *   mine=true 表示这条是我发的（页面用于决定左右气泡）。
 */
export function getMessages(conversationId, params) {
	return request(
		'/chat/conversations/' + encodeURIComponent(String(conversationId || '')) + '/messages' +
			toQuery(params),
		{ auth: true }
	)
}

/**
 * 发送消息
 *
 * @param {number|string} conversationId
 * @param {string} content 内容（≤500 字）
 * @param {string} [msgType] 'text' | 'resume' 等
 * @returns {Promise<{message:object}>}
 *
 * ⚠️ 发送成功后服务端会同步更新会话行的「最后一条消息 / 时间 / 对方未读数」，
 *    因此页面不需要自己维护会话列表摘要 —— 回到列表页重新拉一次即可。
 */
export function sendMessage(conversationId, content, msgType) {
	return request(
		'/chat/conversations/' + encodeURIComponent(String(conversationId || '')) + '/messages',
		{
			method: 'POST',
			data: { content, msgType: msgType || 'text' },
			auth: true
		}
	)
}

/**
 * 标记会话已读（把当前角色那侧的未读数清零）
 * @param {number|string} conversationId
 */
export function markConversationRead(conversationId) {
	return request(
		'/chat/conversations/' + encodeURIComponent(String(conversationId || '')) + '/read',
		{ method: 'POST', auth: true }
	)
}

/**
 * 未读消息合计（底部 tabBar 角标 / 消息中心入口用）
 * @returns {Promise<{candidate:number,hr:number}>}
 */
export function getUnread() {
	return request('/chat/unread', { auth: true, showError: false })
}
