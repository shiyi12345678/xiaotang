# 项目上传 GitHub · 详细方案

> 扫描时间：2026-09-17
> 结论：**项目当前不是 git 仓库，没有任何提交历史** —— 这是最理想的情况，意味着不存在"密钥已进入历史记录"的遗留问题，只要首次提交前把 `.gitignore` 配好，密钥永远不会进仓库。

---

## 一、上传前必做的安全检查（我已完成扫描）

### 1.1 扫描结果

| 检查项 | 结果 | 处置 |
| --- | --- | --- |
| 敏感文件 | **只有 `server/.env` 一个**（12,292 字节，含全部真实密钥） | ⚠️ 必须确保被忽略 |
| 项目根 `.gitignore` | ❌ **缺失** | ⚠️ 必须新建 |
| `server/.gitignore` | ✅ 存在且内容正确 | 已覆盖 `server/` 子目录 |
| `server/.venv/` | 1142 MB / 45589 文件 | 必须忽略 |
| `.h5build/node_modules/` | 154 MB / 17961 文件 | 必须忽略 |
| 其余全部源码 | 合计 < 2 MB | 可正常提交 |

**关键判断**：`server/.gitignore` 在其所在目录及所有子目录生效，所以 `server/.env`、`server/uploads/`、`server/docker/volumes/`、`server/.venv/` **已经会被自动忽略**。

**但项目根缺少 `.gitignore`**，导致 `.h5build/node_modules/`（154MB）、`unpackage/`、`.workbuddy/`、各类日志不会被排除。这是必须补上的。

### 1.2 `server/.env` 里到底有什么（按用途分类，不含值）

| 类别 | 配置项 | 泄露后果 |
| --- | --- | --- |
| 数据库 | `DB_HOST` `DB_PORT` `DB_USER` `DB_PASSWORD` `DB_NAME` | 数据库被直连、拖库 |
| 鉴权 | `JWT_SECRET` | **任何人可伪造登录 token 冒充任意用户** |
| AI | `AI_API_KEY` `RAG_EMBED_API_KEY` | 你的 API 余额被刷光 |
| 邮箱 | `SMTP_USER` `SMTP_PASSWORD` | 邮箱授权码泄露，可被冒用发信 |
| 向量库 | `MILVUS_TOKEN` `MILVUS_URI` | 向量库被非法访问 |

**结论：这个文件一旦进了公开仓库，等于把上面所有服务的控制权交出去。** 目前它已被 `server/.gitignore` 覆盖，安全。

---

## 二、第一步：创建项目根 `.gitignore`

在项目根目录 `D:\cheng du shi xi\ai she ji\` 新建 `.gitignore`，内容如下（可直接复制）：

```gitignore
# ==================== 依赖与虚拟环境 ====================
node_modules/
.venv/
venv/
env/

# ==================== Python ====================
__pycache__/
*.py[cod]
*$py.class
*.egg-info/
.pytest_cache/

# ==================== 敏感配置（最重要，勿删）====================
# 真实密钥文件，绝不能提交
.env
.env.*
# 但保留示例模板，供他人参考需要配哪些变量
!.env.example
*.key
*.pem
*.pfx
*.p12
*secret*
*credential*
*password*

# ==================== 数据库与本地数据 ====================
*.sqlite
*.sqlite3
*.db
*.sql

# ==================== 用户上传内容（含隐私）====================
uploads/
server/uploads/

# ==================== 容器数据卷（体积大且是本机态）====================
server/docker/volumes/

# ==================== 本地模型缓存 ====================
models_cache/
server/models_cache/

# ==================== 构建产物 ====================
unpackage/
.h5build/node_modules/
.h5build/src/
.h5build/dist/
*.local

# ==================== 编辑器与系统 ====================
.idea/
.vscode/
.DS_Store
Thumbs.db
desktop.ini

# ==================== 本地工具链与日志 ====================
*.log
.wsl-cache/
.hbuilderx/
.dsh-plugins/

# ==================== 工作区记忆（含对话记录，不建议公开）====================
.workbuddy/
```

> ⚠️ **两个需要你决策的条目**（我在上面采用了保守默认值）：
> - **`.workbuddy/`**：我已加入忽略。它包含工作日志（`memory/` 下 5 个文件），记录了你和我的对话摘要。公开它意味着别人能看到你的开发过程与决策记录——**有利有弊**：利是展示工程习惯，弊是暴露内部讨论。**建议忽略**。
> - **`h5-preview/`**：我**没有**加入忽略（因为体积仅 962KB）。如果你想用 GitHub Pages 直接托管前端演示，需要它；如果不想，可以加进忽略列表。**注意**：即使提交了，其中的 `BASE_URL` 仍是局域网 IP，托管后打开依然是白屏——原因见上次的部署方案。

---

## 三、第二步：创建 `.env.example` 模板（强烈建议）

既然 `.env` 不提交，别人（和未来的你）会不知道要配哪些变量。在 `server/` 下新建 `.env.example`：

```ini
# ==================== 数据库（MySQL 8）====================
DB_HOST=127.0.0.1
DB_PORT=3306
DB_USER=你的数据库账号
DB_PASSWORD=你的数据库密码
DB_NAME=sheji

# ==================== 鉴权 ====================
# ⚠️ 生产环境务必换成随机长字符串，不要复用开发环境的密钥
JWT_SECRET=请填入随机生成的密钥
JWT_EXPIRE_DAYS=7

# ==================== AI 助教 ====================
AI_API_KEY=你的DeepSeek密钥
AI_BASE_URL=https://api.deepseek.com
AI_MODEL=deepseek-chat

# ==================== 邮箱验证码 ====================
SMTP_HOST=smtp.qq.com
SMTP_PORT=465
SMTP_USER=你的邮箱
SMTP_PASSWORD=邮箱授权码

# ==================== 可选依赖开关 ====================
# 没有 Milvus / Neo4j 时置为 false
RAG_ENABLED=false
GRAPH_ENABLED=false
```

> 说明：这里只列了核心项。完整的配置键清单（共 60+ 项）我已在本次扫描中提取，如需全量模板告诉我。

---

## 四、第三步：初始化仓库并验证

在项目根目录依次执行：

```bash
# 1) 初始化仓库
git init

# 2) 【关键安全检查】确认 .env 已被忽略
#    预期输出：server/.env
git check-ignore -v server/.env

# 3) 【关键安全检查】确认 .env 没有被纳入跟踪
#    预期输出：为空（什么都不打印）
git ls-files | findstr /i ".env"

# 4) 查看将要提交的文件清单，人工过一遍
git add -A
git status --short

# 5) 再确认一次 .env 不在暂存区
#    预期：无输出
git diff --cached --name-only | findstr /i ".env"
```

> ⚠️ **第 2 步预期输出 `server/.env`，如果没有任何输出，说明忽略规则未生效，请立即停止，不要 commit。**
> ⚠️ 第 4 步务必人工浏览一遍文件清单。特别注意不要出现 `server/.env`、`uploads/` 下的图片、`.venv/` 下的文件。

确认无误后提交：

```bash
git config user.name "你的名字"
git config user.email "你的邮箱"
git commit -m "init: 仿网易云课堂教育类 App（uni-app 前端 + FastAPI 后端）"
```

---

## 五、第四步：在 GitHub 创建仓库并推送

### 5.1 创建远程仓库

1. 登录 GitHub → 右上角 `+` → `New repository`
2. **Repository name**：建议 `netease-cloud-class-app` 或 `uni-app-education-app`
3. **⚠️ 关键：不要勾选** `Add a README file`、`Add .gitignore`、`Choose a license`
   - 勾了会产生一个初始提交，与你本地历史冲突，push 时会被拒
4. 创建后拿到仓库地址，形如 `https://github.com/你的用户名/仓库名.git`

### 5.2 配置认证（GitHub 已不支持密码）

**方式 A：Personal Access Token（较简单）**

1. GitHub → `Settings` → `Developer settings` → `Personal access tokens` → `Tokens (classic)` → `Generate new token`
2. 勾选 `repo` 权限，设置有效期
3. 生成的 token **只显示一次**，立即复制保存
4. push 时用户名填 GitHub 用户名，**密码位置粘贴这个 token**

**方式 B：SSH Key（推荐，配置一次长期有效）**

```bash
# 生成密钥（一路回车即可，或设置 passphrase）
ssh-keygen -t ed25519 -C "你的邮箱"

# 查看公钥，复制输出内容
cat ~/.ssh/id_ed25519.pub
```

把公钥内容粘贴到 GitHub → `Settings` → `SSH and GPG keys` → `New SSH key`，然后远程地址用 SSH 形式。

### 5.3 推送

```bash
# 关联远程仓库（下面二选一）
git remote add origin https://github.com/你的用户名/仓库名.git   # HTTPS
git remote add origin git@github.com:你的用户名/仓库名.git        # SSH

# 推送
git branch -M main
git push -u origin main
```

---

## 六、上传前需要你自己判断的四件事

### 6.1 `docs/实习简历-APP开发实习生.md` 含个人信息 ⚠️

`docs/` 目录下有四个文件，其中：

| 文件 | 是否建议公开 | 理由 |
| --- | --- | --- |
| `设计规范.md` | ✅ 建议 | 展示工程规范，是加分项 |
| `代码审查报告.md` | ✅ 建议 | 展示代码审查能力，是加分项 |
| `部署方案-公网可访问.md` | ⚠️ 酌情 | 会暴露你的服务器/域名规划，但无密钥 |
| **`实习简历-APP开发实习生.md`** | ⚠️ **建议不公开** | 含你的实习单位、经历描述。如果你的 GitHub 会展示给面试官，这是刻意展示；如果是个人代码库，没必要放 |

### 6.2 `网易云客户端需求文档.md` 可能有版权问题 ⚠️

这个文件看起来是培训机构下发的需求材料。**公开它可能涉及材料版权**，建议：
- 仓库设为 **Private**，或
- 把该文件加入 `.gitignore`，或
- 精简为自写的功能说明后再提交

### 6.3 仓库公开还是私有

| 选项 | 适用场景 |
| --- | --- |
| **Public** | 作为作品集展示给面试官，需要代码可被查看 |
| **Private** | 仅作个人备份，或含不便公开的材料 |

简历放 GitHub 链接的话，**必须选 Public**。但如果含培训机构材料，建议先处理版权问题。

### 6.4 国内网络问题 ⚠️

`git push` 到 GitHub 在国内可能超时失败。备选：
- 配置代理后 push
- 使用 SSH over 443 端口
- 使用国内镜像（Gitee），但简历场景 GitHub 更通用

---

## 七、最坏情况：如果不小心把 `.env` 提交并推送了

**这不是"删掉文件再提交一次"就能解决的** —— git 保留完整历史，密钥依然存在于历史提交中，且 GitHub 会被爬虫扫描，密钥通常在几分钟内就会被利用。

**正确处置顺序**（按优先级）：

1. **立即作废所有泄露的凭据**（最重要，先做这个！）
   - DeepSeek：吊销旧 Key，生成新 Key
   - 数据库：修改密码
   - 邮箱：重置授权码
   - `JWT_SECRET`：换成新值（会让所有已签发的 token 失效，属预期行为）
2. 再清理 git 历史（`git filter-repo` 或 BFG Repo-Cleaner）
3. 强制推送覆盖远程历史
4. 联系 GitHub Support 清理缓存（如果仓库曾公开）

> 请记住：**作废凭据永远优先于清理历史**。历史清理是补救，凭据作废才是止损。

---

## 八、完整操作清单（可逐条打勾）

```
[ ] 1. 在项目根创建 .gitignore（内容见第二节）
[ ] 2. 在 server/ 创建 .env.example（内容见第三节）
[ ] 3. 决定 .workbuddy/ 与 docs/实习简历 是否公开，必要时加入 .gitignore
[ ] 4. git init
[ ] 5. 执行 git check-ignore -v server/.env   ← 必须输出 server/.env
[ ] 6. git add -A && git status --short      ← 人工检查文件清单
[ ] 7. git diff --cached --name-only | findstr /i ".env"   ← 必须无输出
[ ] 8. git config user.name / user.email
[ ] 9. git commit -m "..."
[ ] 10. GitHub 创建仓库（不勾 README/gitignore/license）
[ ] 11. 配置 PAT 或 SSH Key
[ ] 12. git remote add origin <仓库地址>
[ ] 13. git push -u origin main
```

---

## 附：本次方案未执行任何操作

- ❌ 未创建 `.gitignore`、`.env.example`
- ❌ 未执行 `git init`、`git add`、`git commit`
- ❌ 未读取或输出 `.env` 中的任何密钥值（仅提取了配置项名称）
- ❌ 未连接任何远程仓库

需要我代劳创建 `.gitignore` 和 `.env.example` 吗？这两个是纯新增文件，不改动任何现有代码。你确认后我再动手。

---

*本方案为只读分析产物，所有结论基于 2026-09-17 的实际扫描结果。*
