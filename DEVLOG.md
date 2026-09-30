# xueren-skill-publish-skillhub 版本演进记录

## v1.0.1（2026-09-30）

首版公开发布。frontmatter 补齐 `github:` / `skillhub:` 白名单标记，使本 skill 首次纳入双通道发布流水线。

**变更**：
- frontmatter 新增：
  - `github: https://github.com/JackieZheng/xueren-skill-publish-skillhub`
  - `skillhub: https://skillhub.cn/skills/indiv-xueren/xueren-skill-publish-skillhub`
- version：1.0.0 → 1.0.1
- 无脚本改动；本轮只是补齐发布白名单标记并首次推 GitHub + SkillHub 远端。

**发布**：
- GitHub：`JackieZheng/xueren-skill-publish-skillhub`（新建仓库 + v1.0.1 Release）。
- SkillHub：`xueren-skill-publish-skillhub` slug 首次上线。
- 脱敏：走 `xueren-skill-publish-github` 的 sensitive_paths 规则（`references/sensitive_paths.json` + `sensitive_paths.local.json`）；提交身份走 GitHub noreply；PAT 只作命令行参数不入库。

## v1.0.0（2026-09-30）

首版。SKILL.md 只保留业务/操作内容，版本演进归档到本文件。

**功能**：
- zip 打包：自动排除 SkillHub 拒收的文件（`.bat` / `LICENSE` / `README` / `.gitignore` / `.git` / `__pycache__` / `.venv` / `node_modules` 等）。
- 调用 `~/.skillhub/skills_store_cli.py publish`，封装为 `publish_skillhub.py`。
- 429 / 5xx 指数退避重试（默认 3 次）；409「version already exists」明确退出。
- 版本：默认读 SKILL.md frontmatter `version`；`--version X.Y.Z` 覆盖；`--bump-version` 自动 patch+1。
- Token：优先级 `--token` > `SKILLHUB_TOKEN` env > `~/.skillhub/credentials.json`；脚本不硬编码。
- 支持 `--dry-run` 预检、`--json` 结构化输出。

**背景**：
- 之前发 SkillHub 都在 tmp 里临时写 zip 打包脚本 + 裸调 `skillhub publish`，未沉淀。
- 与 `xueren-skill-publish-github` 平行两条公开渠道，需一一对齐的封装 skill。

**依赖**：
- 前置：SkillHub CLI 已安装（`~/.skillhub/skills_store_cli.py`）且已 `skillhub login`。
- 无 GitHub PAT / 无其它凭据；仅依赖 SkillHub token（在 credentials.json 里）。
