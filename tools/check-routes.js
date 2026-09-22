/**
 * 路由引用自检：确认代码/数据里出现的 /pages/xxx 跳转路径都在 pages.json 中注册
 * 用法：node check-routes.js <项目根目录>
 */
const fs = require('fs')
const path = require('path')

const root = process.argv[2] || process.cwd()

function readJsonLike(file) {
	// pages.json 允许 // 注释，这里先做一次去注释
	const raw = fs.readFileSync(file, 'utf8')
	return JSON.parse(raw.replace(/^\s*\/\/.*$/gm, ''))
}

const pagesJson = readJsonLike(path.join(root, 'pages.json'))
const registered = new Set(pagesJson.pages.map(p => '/' + p.path))

function walk(dir, out = []) {
	for (const name of fs.readdirSync(dir)) {
		if (['node_modules', 'unpackage', '.git', 'uni_modules', 'tools', 'h5-preview', 'server', '.h5build', '.dsh-plugins', '.wsl-cache', 'legacy'].includes(name)) continue
		const full = path.join(dir, name)
		const st = fs.statSync(full)
		if (st.isDirectory()) walk(full, out)
		else if (['.vue', '.js', '.json'].includes(path.extname(name))) out.push(full)
	}
	return out
}

const routeRe = /['"`](\/pages\/[A-Za-z0-9_\-/]+)/g
const found = new Map() // route -> files
for (const file of walk(root)) {
	const rel = path.relative(root, file)
	if (rel === 'pages.json') continue
	const content = fs.readFileSync(file, 'utf8')
	for (const m of content.matchAll(routeRe)) {
		const route = m[1].replace(/\/$/, '')
		if (!found.has(route)) found.set(route, new Set())
		found.get(route).add(rel)
	}
}

let bad = 0
for (const [route, files] of [...found.entries()].sort()) {
	// 允许带查询串的形如 /pages/xxx/yyy? 已被正则截断
	if (!registered.has(route)) {
		bad++
		console.log(`[FAIL] 未注册路由 ${route}   ← ${[...files].join(', ')}`)
	}
}
const unused = [...registered].filter(r => !found.has(r))
console.log(`\npages.json 注册页面 ${registered.size} 个；代码中引用路由 ${found.size} 个，未注册 ${bad} 个。`)
if (unused.length) console.log(`未被任何跳转引用的页面（可为 tab 页或正常）: ${unused.join(', ')}`)
process.exit(bad ? 1 : 0)
