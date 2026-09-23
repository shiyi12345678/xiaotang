# tools · 项目自检工具

前端静态检查与工程校验脚本：

- `check-components.js` / `check-routes.js` / `check-scss-vars.js` / `check-icons.js` / `check-vue.js`：专项检查
- `verify.ps1`：一键自检（模板配平 / JS 语法 / SCSS 括号 / 变量 / 路由 / 组件 / 图标）

用法（项目根目录）：

```powershell
powershell -File tools\verify.ps1
```
