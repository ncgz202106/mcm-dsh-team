# GitHub 私有仓库与后续维护

远程仓库：<https://github.com/ncgz202106/mcm-dsh-team>。

当前目录已经是 Git 源码仓库，不需要重新创建副本。源码、角色提示词、模板、测试、科研图表、示范 PDF 和过滤后的验收证据一并维护。DSH 安装目录仍由正式更新器管理；GitHub 推送不会热替换正在运行的 Agent。

用户已授权后续改动同步 GitHub。今后由 Codex 修改这套项目时，先执行相应检查，再提交并推送，核对本地与远程 SHA。仓库根 AGENTS.md 保存该约定，跨聊天继续维护时也应先读取。没有后台自动提交服务；用户自行改动的半成品不会因为保存文件而被自动上传。

## 手动查看与同步

在本仓库根运行：

```powershell
git status --short --branch
git fetch origin
git log -5 --oneline --decorate
```

确认变更与检查完成后，明确暂存本次相关文件，再提交和推送：

```powershell
git add -- <本次相关文件或目录>
git diff --cached --stat
git commit -m 'Describe the completed change'
git push
git rev-parse HEAD
git ls-remote origin refs/heads/main
```

最后两项 SHA 一致才代表 main 已同步。远程有新提交时先读取并整合，不使用强制推送覆盖。认证失败时使用 Git/GitHub 正常登录流程，不把 token 放进仓库、脚本、远程 URL 或聊天。

## 字节与验收证据

`.gitattributes` 保留原字节，避免 CRLF/LF 自动转换导致哈希不符。`.gitignore` 排除依赖、缓存、原始会话和本机备份，保留已经审阅的 PDF、图像和过滤检查日志。

`SHA256SUMS.txt` 对应冻结的 v0.2.0 交付快照；本次 GitHub 维护文件不追写历史验收报告。后续修改涉及已登记源码或制品时，应重新执行相应验证并生成新的版本证据，不能用旧报告证明新代码。
