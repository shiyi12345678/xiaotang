/**
 * .vue 静态自检脚本（纯本地，不依赖任何 npm 包）
 * 用途：在无法整体编译 uni-app 的情况下，快速发现
 *   1) <template> 标签未闭合 / 错配
 *   2) <script> 语法错误（调用 node --check）
 *   3) <style> 大括号不配对
 *   4) 缺少必备块
 * 用法：node check-vue.js <项目根目录>
 *
 * 说明：子进程输出写入临时文件而非管道（沙箱环境下管道 stdio 不可用）
 */
const fs = require('fs')
const path = require('path')
const os = require('os')
const { spawnSync } = require('child_process')

const root = process.argv[2] || process.cwd()
const VOID_TAGS = new Set(['image', 'input', 'br', 'hr', 'img', 'meta', 'link', 'source'])

function walk(dir, out = []) {
	for (const name of fs.readdirSync(dir)) {
		if (['node_modules', 'unpackage', '.git', '.hbuilderx', 'tools', 'uni-ui', 'h5-preview', 'server', '.h5build', '.dsh-plugins', '.wsl-cache', 'legacy'].includes(name)) continue
		const full = path.join(dir, name)
		const st = fs.statSync(full)
		if (st.isDirectory()) walk(full, out)
		else if (name.endsWith('.vue')) out.push(full)
	}
	return out
}

/** 按标签层级提取 SFC 顶层块（正确处理内部嵌套同名标签） */
function extractBlock(content, name) {
	const openRe = new RegExp('<' + name + '(\\s[^>]*)?>', 'i')
	const allTagRe = new RegExp('<(\\/?)' + name + '(\\s[^>]*)?(\\/?)>', 'gi')
	const first = openRe.exec(content)
	if (!first) return null
	if (first[0].endsWith('/>')) return ''
	let depth = 0
	let start = -1
	let m
	allTagRe.lastIndex = first.index
	while ((m = allTagRe.exec(content))) {
		const isClose = m[1] === '/'
		const selfClose = m[3] === '/'
		if (!isClose && !selfClose) {
			depth++
			if (depth === 1) start = m.index + m[0].length
		} else if (isClose) {
			depth--
			if (depth === 0) return content.slice(start, m.index)
		}
		// 自闭合标签不计入层级
		void selfClose
	}
	return null
}

function checkTemplate(tpl) {
	const errors = []
	const stack = []
	const tagRe = /<(\/?)([a-zA-Z][a-zA-Z0-9-]*)((?:"[^"]*"|'[^']*'|[^>"'])*?)(\/?)>/g
	let m
	while ((m = tagRe.exec(tpl))) {
		const closing = m[1] === '/'
		const tag = m[2]
		const selfClosed = m[4] === '/'
		if (VOID_TAGS.has(tag)) continue // image / input 等自闭合写法，忽略其开闭对
		if (closing) {
			if (!stack.length) {
				errors.push(`多余的闭合标签 </${tag}>`)
				continue
			}
			const top = stack.pop()
			if (top !== tag) errors.push(`标签错配：<${top}> 被 </${tag}> 闭合`)
		} else if (!selfClosed) {
			stack.push(tag)
		}
	}
	if (stack.length) errors.push(`未闭合标签：${stack.map(t => '<' + t + '>').join(', ')}`)
	return errors
}

/** 简单大括号配对检查（忽略字符串与注释中的括号） */
function checkBraces(css) {
	let depth = 0
	let inStr = null
	let inComment = false
	const errs = []
	for (let i = 0; i < css.length; i++) {
		const c = css[i]
		const n = css[i + 1]
		if (inComment) {
			if (c === '*' && n === '/') {
				inComment = false
				i++
			}
			continue
		}
		if (inStr) {
			if (c === '\\') i++
			else if (c === inStr) inStr = null
			continue
		}
		if (c === '/' && n === '*') {
			inComment = true
			i++
			continue
		}
		if (c === '"' || c === "'") {
			inStr = c
			continue
		}
		if (c === '{') depth++
		else if (c === '}') {
			depth--
			if (depth < 0) errs.push('多余的 }')
		}
	}
	if (depth > 0) errs.push(`有 ${depth} 个 { 未闭合`)
	return errs
}

const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'vuecheck-'))
const logPath = path.join(tmp, 'err.log')
let fail = 0
const files = walk(root)

for (const file of files) {
	const rel = path.relative(root, file)
	const content = fs.readFileSync(file, 'utf8')
	const isAppVue = path.basename(file).toLowerCase() === 'app.vue'
	const problems = []

	if (!isAppVue) {
		const tpl = extractBlock(content, 'template')
		if (tpl === null) problems.push('缺少 <template> 块')
		else problems.push(...checkTemplate(tpl))
	}

	const script = extractBlock(content, 'script')
	if (script === null) problems.push('缺少 <script> 块')
	else {
		const jsFile = path.join(tmp, 'x.mjs')
		fs.writeFileSync(jsFile, script.replace(/^\s*<script[^>]*>/, ''))
		const fd = fs.openSync(logPath, 'w')
		const res = spawnSync(process.execPath, ['--check', jsFile], { stdio: ['ignore', 'ignore', fd] })
		fs.closeSync(fd)
		if (res.status !== 0) {
			const msg = fs.readFileSync(logPath, 'utf8').trim()
			problems.push('script 语法错误：' + msg.split('\n').slice(0, 8).join(' | '))
		}
	}

	const style = extractBlock(content, 'style')
	if (style !== null) problems.push(...checkBraces(style))

	if (problems.length) {
		fail++
		console.log(`\n[FAIL] ${rel}`)
		problems.forEach(p => console.log('   - ' + p))
	} else {
		console.log(`[ ok ] ${rel}`)
	}
}

console.log(`\n共检查 ${files.length} 个 .vue 文件，${fail} 个有问题。`)
process.exit(fail ? 1 : 0)
