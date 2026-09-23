# services · 前端接口封装层

页面不直接拼接接口 URL，统一经此目录调用后端：

- `api.js`：网络请求封装（`uni.request`），统一注入 `BASE_URL` 与 JWT 鉴权头，归一化 `{code, msg, data}` 响应
- `user.js` / `apply.js` / `job.js` / `chat.js` / `im.js` / `interview.js` / `content.js` / `hr.js`：各业务域接口封装
