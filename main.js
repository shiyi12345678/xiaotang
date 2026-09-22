/**
 * 入口文件（HBuilderX 标准模板：Vue2 / Vue3 条件编译，两种项目都能直接用）
 * 你的 manifest.json 里 vueVersion 为 "3"，因此实际生效的是下面的 VUE3 分支。
 */
import App from './App'

// #ifndef VUE3
import Vue from 'vue'
import './uni.promisify.adaptor'
Vue.config.productionTip = false
App.mpType = 'app'
const app = new Vue({
	...App
})
app.$mount()
// #endif

// #ifdef VUE3
import {
	createSSRApp
} from 'vue'
export function createApp() {
	const app = createSSRApp(App)
	return {
		app
	}
}
// #endif
