/**
 * uni-icons 图标名自检：
 * 扫描所有 .vue/.js 中的图标名（<uni-icons type="xxx">、:type 表达式里的字符串、数据里的 icon: 'xxx'），
 * 校验是否属于 uni-icons 官方图标集（写错会导致图标空白且无报错）
 * 用法：node check-icons.js <项目根目录>
 */
const fs = require('fs')
const path = require('path')

const root = process.argv[2] || process.cwd()

// uni-icons 官方图标全集（共 161 个）
// 权威来源：本项目内置的 uni-ui/uni-icons/uniicons_file_vue.js 里的 fontData
const ICONS = new Set(('arrow-down arrow-left arrow-right arrow-up auth auth-filled back bars bottom ' +
	'calendar calendar-filled camera camera-filled cart cart-filled chat chatboxes chatboxes-filled ' +
	'chatbubble chatbubble-filled chat-filled checkbox checkbox-filled checkmarkempty circle circle-filled ' +
	'clear close closeempty cloud-download cloud-download-filled cloud-upload cloud-upload-filled color ' +
	'color-filled compose contact contact-filled down download download-filled email email-filled eye ' +
	'eye-filled eye-slash eye-slash-filled fire fire-filled flag flag-filled folder-add folder-add-filled ' +
	'font forward gear gear-filled gift gift-filled hand-down hand-down-filled hand-up hand-up-filled ' +
	'headphones heart heart-filled help help-filled home home-filled image image-filled images images-filled ' +
	'info info-filled left link list location location-filled locked locked-filled loop mail-open ' +
	'mail-open-filled map map-filled map-pin map-pin-ellipse medal medal-filled mic mic-filled micoff ' +
	'micoff-filled minus minus-filled more more-filled navigate navigate-filled notification notification-filled ' +
	'paperclip paperplane paperplane-filled person personadd personadd-filled personadd-filled-copy person-filled ' +
	'phone phone-filled plus plusempty plus-filled pulldown pyq qq redo redo-filled refresh refreshempty ' +
	'refresh-filled reload right scan search settings settings-filled shop shop-filled smallcircle ' +
	'smallcircle-filled sound sound-filled spinner-cycle staff staff-filled star star-filled starhalf top ' +
	'trash trash-filled tune tune-filled undo undo-filled up upload upload-filled videocam videocam-filled ' +
	'vip vip-filled wallet wallet-filled weibo weixin').split(/\s+/))

function walk(dir, out = []) {
	for (const name of fs.readdirSync(dir)) {
		if (['node_modules', 'unpackage', '.git', 'uni_modules', 'tools', 'h5-preview', 'server', '.h5build', '.dsh-plugins', '.wsl-cache', 'legacy'].includes(name)) continue
		const full = path.join(dir, name)
		const st = fs.statSync(full)
		if (st.isDirectory()) walk(full, out)
		else if (name.endsWith('.vue') || name.endsWith('.js')) out.push(full)
	}
	return out
}

let bad = 0
let checked = 0
const stat = new Map()

for (const file of walk(root)) {
	const rel = path.relative(root, file)
	const content = fs.readFileSync(file, 'utf8')
	const errs = []

	// a) <uni-icons ... type="xxx" ...>：静态 type 校验字面量；:type 动态绑定只校验其中的字符串字面量
	for (const m of content.matchAll(/<uni-icons\b[^>]*>/g)) {
		const tag = m[0]
		const literals = []
		const attr = tag.match(/([:@]?)type="([^"]*)"/)
		if (attr) {
			const isDynamic = attr[1] === ':' || attr[1] === '@'
			const value = attr[2]
			if (isDynamic) {
				for (const s of value.matchAll(/'([a-zA-Z0-9-]+)'/g)) literals.push(s[1])
			} else if (/^[a-zA-Z0-9-]+$/.test(value)) {
				literals.push(value)
			}
		}
		for (const name of literals) {
			if (!name) continue
			checked++
			stat.set(name, (stat.get(name) || 0) + 1)
			if (!ICONS.has(name)) errs.push(`图标名不存在：type="${name}"`)
		}
	}

	// b) 数据里的 icon: 'xxx'（toast 的 icon 选项 none/success/error/loading 不是图标名，跳过）
	const TOAST_ICONS = new Set(['none', 'success', 'error', 'loading', 'fail', 'exception'])
	for (const m of content.matchAll(/\bicon\s*:\s*'([a-zA-Z0-9-]+)'/g)) {
		if (TOAST_ICONS.has(m[1])) continue
		checked++
		stat.set(m[1], (stat.get(m[1]) || 0) + 1)
		if (!ICONS.has(m[1])) errs.push(`数据中的图标名不存在：icon: '${m[1]}'`)
	}
	for (const m of content.matchAll(/\bicon="([a-zA-Z0-9-]+)"/g)) {
		if (TOAST_ICONS.has(m[1])) continue
		checked++
		stat.set(m[1], (stat.get(m[1]) || 0) + 1)
		if (!ICONS.has(m[1])) errs.push(`属性中的图标名不存在：icon="${m[1]}"`)
	}

	if (errs.length) {
		bad++
		console.log(`\n[FAIL] ${rel}`)
		;[...new Set(errs)].forEach(e => console.log('   - ' + e))
	}
}

console.log(`\n共校验图标引用 ${checked} 处，用到 ${stat.size} 种图标，${bad} 个文件存在非法图标名。`)
process.exit(bad ? 1 : 0)
