/**
 * SCSS 变量使用自检：确认 .vue / .scss 里用到的所有 $变量 都在 uni.scss 中有定义
 * 用法：node check-scss-vars.js <项目根目录>
 */
const fs = require('fs')
const path = require('path')

const root = process.argv[2] || process.cwd()
const UNI_SCSS = path.join(root, 'uni.scss')

function walk(dir, out = []) {
	for (const name of fs.readdirSync(dir)) {
		if (['node_modules', 'unpackage', '.git', 'uni_modules', 'docs', 'tools', 'h5-preview', 'server', '.h5build', '.dsh-plugins', '.wsl-cache', 'legacy'].includes(name)) continue
		const full = path.join(dir, name)
		const st = fs.statSync(full)
		if (st.isDirectory()) walk(full, out)
		else if (name.endsWith('.vue') || name.endsWith('.scss')) out.push(full)
	}
	return out
}

const uniContent = fs.readFileSync(UNI_SCSS, 'utf8')
const defined = new Set()
for (const m of uniContent.matchAll(/^\s*(\$[a-zA-Z0-9_-]+)\s*:/gm)) defined.add(m[1])

let bad = 0
const files = walk(root)
for (const file of files) {
	const rel = path.relative(root, file)
	const content = fs.readFileSync(file, 'utf8')
	// 只检查 <style> 块（或整个 .scss）
	let css = content
	if (file.endsWith('.vue')) {
		const m = content.match(/<style[^>]*>([\s\S]*?)<\/style>/)
		css = m ? m[1] : ''
	}
	const used = new Map()
	for (const m of css.matchAll(/(\$[a-zA-Z0-9_-]+)/g)) {
		const v = m[1]
		// 排除插值 #{...} 里已是变量的正常引用（也算使用）与非变量文本
		used.set(v, (used.get(v) || 0) + 1)
	}
	const missing = [...used.keys()].filter(v => !defined.has(v))
	if (missing.length) {
		bad++
		console.log(`[FAIL] ${rel}  未定义变量: ${missing.join(', ')}`)
	}
}
console.log(`\nuni.scss 中定义变量 ${defined.size} 个；检查 ${files.length} 个文件，${bad} 个存在未定义变量。`)
process.exit(bad ? 1 : 0)
