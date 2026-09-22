/**
 * 组件/约定自检：
 *  1) 模板里用到的 zn-* / uni-* 组件是否真实存在（zn-* 必须在 components/ 下，uni-* 必须在已知 uni-ui 名单里）
 *  2) 五个 tab 页是否都引入了 <zn-tab-bar>
 *  3) 页面 <script> 里 import 的 @/ 路径是否存在
 *  4) 模板里是否误用了 import 进来的函数（启发式：模板中出现「与 import 同名」的调用）
 * 用法：node check-components.js <项目根目录>
 */
const fs = require('fs')
const path = require('path')

const root = process.argv[2] || process.cwd()

const UNI_UI = new Set([
	'uni-badge', 'uni-breadcrumb', 'uni-calendar', 'uni-card', 'uni-collapse', 'uni-collapse-item',
	'uni-combox', 'uni-countdown', 'uni-data-checkbox', 'uni-data-picker', 'uni-data-select',
	'uni-dateformat', 'uni-datetime-picker', 'uni-drawer', 'uni-easyinput', 'uni-fab', 'uni-fav',
	'uni-file-picker', 'uni-forms', 'uni-forms-item', 'uni-goods-nav', 'uni-grid', 'uni-grid-item',
	'uni-group', 'uni-icons', 'uni-indexed-list', 'uni-link', 'uni-list', 'uni-list-item',
	'uni-list-chat', 'uni-load-more', 'uni-nav-bar', 'uni-notice-bar', 'uni-number-box',
	'uni-pagination', 'uni-popup', 'uni-popup-dialog', 'uni-popup-share', 'uni-rate', 'uni-row',
	'uni-col', 'uni-search-bar', 'uni-section', 'uni-segmented-control', 'uni-steps', 'uni-step',
	'uni-swipe-action', 'uni-swipe-action-item', 'uni-swiper-dot', 'uni-table', 'uni-tr', 'uni-th',
	'uni-td', 'uni-tag', 'uni-title', 'uni-tooltip', 'uni-transition', 'uni-stat', 'uni-data-select'
])

function walk(dir, out = []) {
	for (const name of fs.readdirSync(dir)) {
		if (['node_modules', 'unpackage', '.git', 'uni_modules', 'tools', 'uni-ui', 'h5-preview', 'server', '.h5build', '.dsh-plugins', '.wsl-cache', 'legacy'].includes(name)) continue
		const full = path.join(dir, name)
		const st = fs.statSync(full)
		if (st.isDirectory()) walk(full, out)
		else if (name.endsWith('.vue')) out.push(full)
	}
	return out
}

// 已存在的 zn-* 组件
const znComponents = new Set()
const compDir = path.join(root, 'components')
if (fs.existsSync(compDir)) {
	for (const name of fs.readdirSync(compDir)) {
		if (name.startsWith('zn-')) znComponents.add(name)
	}
}

// 已内置的 uni-* 组件（项目根 uni-ui/ 目录）
const uniVendored = new Set()
const uniDir = path.join(root, 'uni-ui')
if (fs.existsSync(uniDir)) {
	for (const name of fs.readdirSync(uniDir)) {
		if (name.startsWith('uni-') && fs.existsSync(path.join(uniDir, name, name + '.vue'))) {
			uniVendored.add(name)
		}
	}
}

const TAB_PAGES = ['index', 'category', 'ai', 'study', 'mine']
let problems = 0

for (const file of walk(root)) {
	const rel = path.relative(root, file)
	const content = fs.readFileSync(file, 'utf8')
	const tplMatch = content.match(/^[\s\S]*?<template(\s[^>]*)?>([\s\S]*?)<\/template>\s*(?=<script|<style|$)/)
	const tpl = tplMatch ? tplMatch[2] : (file.endsWith('App.vue') ? '' : content)
	const errs = []

	// 1) 组件存在性
	for (const m of tpl.matchAll(/<([a-z][a-z0-9]*(?:-[a-z0-9]+)+)[\s/>]/g)) {
		const tag = m[1]
		if (tag.startsWith('zn-')) {
			if (!znComponents.has(tag)) errs.push(`使用了不存在的组件 <${tag}>`)
		} else if (tag.startsWith('uni-')) {
			if (!UNI_UI.has(tag)) {
				errs.push(`使用了未知的 uni-ui 组件 <${tag}>`)
			} else if (uniVendored.size && !uniVendored.has(tag)) {
				// uni-ui/ 目录存在时，要求组件实体确实已内置（否则运行时找不到组件）
				errs.push(`<${tag}> 未内置到 uni-ui/ 目录（easycom 解析不到）`)
			}
		}
	}

	// 2) tab 页必须带 zn-tab-bar
	const base = path.basename(file, '.vue')
	const parent = path.basename(path.dirname(file))
	if (TAB_PAGES.includes(base) && TAB_PAGES.includes(parent) && ['index', 'category', 'ai', 'study', 'mine'].includes(parent)) {
		if (!/current="(index|category|ai|study|mine)"/.test(tpl)) {
			errs.push('tab 页未发现 <zn-tab-bar current="...">')
		}
	}

	// 3) import 路径存在性
	const scriptMatch = content.match(/<script[^>]*>([\s\S]*?)<\/script>/)
	if (scriptMatch) {
		const script = scriptMatch[1]
		for (const m of script.matchAll(/from\s+['"](@\/[^'"]+)['"]/g)) {
			const target = path.join(root, m[1].replace(/^@\//, ''))
			const candidates = [target, target + '.js', target + '.vue', path.join(target, 'index.js')]
			if (!candidates.some(c => fs.existsSync(c))) {
				errs.push(`import 路径不存在: ${m[1]}`)
			}
		}
		// 4) 模板里直接用 import 的函数（启发式）
		const importedFns = [...script.matchAll(/import\s*\{([^}]+)\}\s*from/g)]
			.flatMap(m => m[1].split(',').map(s => s.trim().split(/\s+as\s+/).pop()))
			.filter(Boolean)
		const methodKeys = new Set()
		const methodsStart = script.search(/methods\s*:\s*\{/)
		if (methodsStart >= 0) {
			// 用大括号配对扫描出 methods 块（depth 1 上的标识符即为方法名）
			let i = script.indexOf('{', methodsStart)
			let depth = 0
			let end = script.length
			for (let j = i; j < script.length; j++) {
				const c = script[j]
				if (c === '{') depth++
				else if (c === '}') {
					depth--
					if (depth === 0) {
						end = j
						break
					}
				}
			}
			const body = script.slice(i + 1, end)
			depth = 0
			const identRe = /([A-Za-z_$][\w$]*)\s*(?:[:(]|,\s*$)/gm
			let m
			while ((m = identRe.exec(body))) {
				// 只取处于最外层（depth 0）的标识符
				let d = 0
				for (let k = 0; k < m.index; k++) {
					if (body[k] === '{') d++
					else if (body[k] === '}') d--
				}
				if (d === 0) methodKeys.add(m[1])
			}
		}
		for (const fn of importedFns) {
			const re = new RegExp('(?:\\{\\{[^}]*|[":@][\\w.-]*="[^"]*)\\b' + fn + '\\s*\\(', 'g')
			if (re.test(tpl) && !methodKeys.has(fn)) {
				errs.push(`模板中调用了未挂到实例上的函数 ${fn}()（需在 methods 里挂一遍）`)
			}
		}
	}

	if (errs.length) {
		problems++
		console.log(`\n[WARN] ${rel}`)
		errs.forEach(e => console.log('   - ' + e))
	}
}
console.log(`\nzn-* 组件 ${znComponents.size} 个；检查完成，${problems} 个文件有提示。`)
