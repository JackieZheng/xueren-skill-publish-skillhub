---
id: xueren-skill-publish-skillhub
name: 雪人老师·Skill发布到SkillHub
title: 雪人老师·Skill发布到SkillHub
description: 把本地 WorkBuddy skill 一键打包并发布到 SkillHub 社区源。自动处理 zip 打包（排除 SkillHub 拒收的 .bat/LICENSE/README/.gitignore/.git 等，以及 cache/ 等运行期产物；支持 --exclude 自定义排除，绕过 png 等二进制被拒）、调用 skillhub CLI、429/5xx 限流自动退避、版本一致性校验、token 从 ~/.skillhub/credentials.json 自动加载、可选 --bump-version 自动 patch+1、支持 --dry-run 预检和 --json 结构化输出。用户提到"发布 skill 到 skillhub""更新 skillhub 上的 skill""publish skill to skillhub""推送到 skillhub"时触发。不适用于：GitHub 开源发布（走 xueren-skill-publish-github）、Skill.md 模板校验（走 xueren-skill-init-std）。
slug: xueren-skill-publish-skillhub
displayName: 雪人老师·Skill发布到SkillHub
summary: 把本地 WorkBuddy skill 一键打包并发布到 SkillHub 社区源（zip 打包 + CLI 调用 + 限流重试 + JSON 输出）。
description_zh: 把本地 WorkBuddy skill 一键打包并发布到 SkillHub 社区源。自动处理 zip 打包（排除 SkillHub 拒收的 .bat/LICENSE/README/.gitignore/.git 等，以及 cache/ 等运行期产物；支持 --exclude 自定义排除，绕过 png 等二进制被拒）、调用 skillhub CLI、429/5xx 限流自动退避、版本一致性校验、token 从 ~/.skillhub/credentials.json 自动加载、可选 --bump-version 自动 patch+1、支持 --dry-run 预检和 --json 结构化输出。用户提到"发布 skill 到 skillhub""更新 skillhub 上的 skill""publish skill to skillhub""推送到 skillhub"时触发。不适用于：GitHub 开源发布（走 xueren-skill-publish-github）、Skill.md 模板校验（走 xueren-skill-init-std）。
description_en: One-click package and publish WorkBuddy skills to SkillHub community.
version: 1.0.5
author: 雪人
license: MIT
github: https://github.com/JackieZheng/xueren-skill-publish-skillhub
skillhub: https://skillhub.cn/skills/indiv-xueren/xueren-skill-publish-skillhub
allowed-tools: ""
display_name: xueren-skill-publish-skillhub
display_name_zh: 雪人老师·Skill发布到SkillHub
trigger: ["发布 skill 到 skillhub", "更新 skillhub 上的 skill", "publish skill to skillhub", "推送到 skillhub", "skillhub 发布"]
examples: "用户：把 xueren-poster-maker 发布到 skillhub → 运行 scripts/publish_skillhub.py --skill xueren-poster-maker --changelog \"新增模板 X\" --bump-version，自动打包 + 调用 CLI + 处理 429 限流。"
platforms: [ima, WorkBuddy, QClaw]
metadata:
  author: 雪人
  category: 工具
---

# 雪人老师·Skill发布到SkillHub

## 概述

把本地自建的任意 WorkBuddy skill 发布到 SkillHub 社区源的一站式 skill。与 `xueren-skill-publish-github` 是**平行两条通道**——一个发 GitHub（开源仓库），一个发 SkillHub（社区 skill 市场）。

**核心场景**：修改了本地 skill 之后，把最新版本推送到 SkillHub 让用户能搜到 / 安装 / 升级。

**核心价值**：
- **零外部依赖**：只用 Python 标准库 + SkillHub 官方 CLI（`~/.skillhub/skills_store_cli.py`）。
- **打包即合规**：自动排除 SkillHub 拒收的文件（`.bat` / `LICENSE` / `README` / `.gitignore` / `.git` / `__pycache__` / `.venv` / `node_modules` 等），避免内容审核失败。
- **开发日志不外发**（用户约定，2026-10-01）：`DEVLOG.md` 一律不进 zip，与 GitHub 发布口径一致（常量 `NEVER_PUBLISH`）。
- **仓库专用文件不进包**：`.gitignore` / `.gitattributes` / `.gitmodules` / `LICENSE` / `README*` 都是仓库元数据，SkillHub 会以「不允许的文件类型」400 拒收（`.gitattributes` 是 2026-10-01 实测新增的）。
- **限流自动重试**：429 / 5xx 自动指数退避重试（默认 3 次），409「version already exists」明确报错退出。
- **版本管理**：默认读 SKILL.md frontmatter 的 `version`；`--bump-version` 自动 patch+1；`--version X.Y.Z` 手动覆盖。
- **零硬编码身份**：token 从 `~/.skillhub/credentials.json` 自动加载（`skillhub login --key skh_xxx` 一次性登录）；`--token` 可临时覆盖。
- **--json 友好**：`--json` 输出结构化 JSON，便于编排 skill（如 `xueren-skill-update`）作为流水线的一环调用。

## 你的工作方式

1. **前置**：SkillHub CLI 已安装（`~/.skillhub/skills_store_cli.py`）且已 `skillhub login --key skh_xxx` 登录过（token 落在 `~/.skillhub/credentials.json`）。
2. **确认 skill 目录存在**：脚本会先找 `~/.workbuddy/skills/<name>/SKILL.md`，或用 `--skill <dir>` 指定绝对路径。
3. **确认 version 是否要 bump**：默认取 SKILL.md 现有版本；用户说「升级发一次」用 `--bump-version`；说「补发同版本」直接用 SKILL.md 现值。
4. **写清 changelog**：`--changelog` 必填，简述本次改动（会显示在 SkillHub 版本页）。
5. **跑脚本**：拿到 skillId / versionId / html_url 或明确的失败原因。

## 执行流程

### Phase 1：前置检查

- SkillHub CLI 位置：`~/.skillhub/skills_store_cli.py`（缺失时提示执行官方安装命令）。
- Token：默认从 `~/.skillhub/credentials.json` 读取（优先级：`--token` > `SKILLHUB_TOKEN` env > credentials.json）。
- 目标 skill：路径存在且含 SKILL.md；SKILL.md 里有 `version` 字段。

### Phase 2：打包

- 遍历 skill 目录，写入 zip 前应用排除规则：
  - **目录**：`.git` / `__pycache__` / `.venv` / `venv` / `node_modules` / `.cache` / `.idea` / `.vscode` / `.pytest_cache`
  - **扩展名**：`.bat` / `.cmd` / `.exe` / `.msi` / `.sys` / `.dll` / `.ocx` / `.scr` / `.vbs` / `.ps1` / `.psm1`
  - **顶层文件名**：`.gitignore` / `LICENSE` / `LICENSE-MIT` / `LICENSE.txt` / `README` / `README.md` / `README.zh.md`
- 输出到 `<skill_dir>/../.tmp-publish-skillhub/<skill_name>.zip`（可用 `--workdir` 覆盖）。

### Phase 3：发布

- 调用：`python ~/.skillhub/skills_store_cli.py publish <zip> --version X --changelog "..."`
- 重试策略：`429` / `rate limit` / `5xx` 退避重试（默认 3 次）；`409 version already exists` / `4xx` 直接退出。
- 超时：单次 180s。

### Phase 4：输出

- 默认：人类可读文本（成功/失败 + zip 大小 + 打包/排除数量 + 排除样例）。
- `--json`：单行 JSON，字段含 `ok / stage / skill / slug / version / zip / zip_bytes / n_included / n_excluded / excluded_sample / token_source / cli / returncode / output_tail / timestamp_utc`。

## 配置与参数

| 参数 | 说明 | 默认 |
|---|---|---|
| `--skill` | skill 名或目录（必填）| — |
| `--version` | 覆盖版本（可选）| SKILL.md 现有 version |
| `--bump-version` | patch+1（与 `--version` 互斥优先）| 关闭 |
| `--changelog` | 本次发布说明（必填）| — |
| `--token` | 覆盖 SkillHub token | 从 credentials.json 读 |
| `--host` | API host 覆盖 | CLI 默认 |
| `--cli` | CLI 脚本路径 | `~/.skillhub/skills_store_cli.py` |
| `--workdir` | 临时 zip 目录 | `<skill_dir>/../.tmp-publish-skillhub/` |
| `--retries` | 失败重试次数 | 3 |
| `--dry-run` | 仅打包 + CLI `--dry-run`，不真推 | 关闭 |
| `--exclude` | 额外排除的 glob（相对 skill 根目录，可重复；如 `--exclude "assets/*.png"`）| 无 |
| `--json` | JSON 输出 | 关闭 |

## 资源目录

### scripts/
- **publish_skillhub.py** — 主脚本（打包 + 发布 + 重试 + 输出）。零外部依赖。

## 常见错误与处理

| 症状 | 原因 | 处理 |
|---|---|---|
| `SkillHub CLI 未找到` | 未安装 CLI | `curl -fsSL https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/install/latest.tar.gz \| tar` |
| `SkillHub 已存在该版本，拒绝覆盖` | 409 | 版本号 bump 后重发；或到 SkillHub 页面手动删除旧版本 |
| `429` / `rate limit` | 请求过快 | 脚本自动退避重试；仍失败时手动等 60s 后重发 |
| `不允许的文件类型` | zip 含 `.bat` / `.exe` 等 | 脚本默认已排除；若仍报，检查是否有非常规扩展名 |
| `请求失败 (400): 不允许的文件类型: assets/xxx.png` | **图片/二进制**（png/jpg/zip…）——**`--dry-run` 不校验类型，真发才拒** | 加 `--exclude "assets/*.png"` 排除图片后重发 |
| `SKILL.md 缺少 version 字段` | frontmatter 不全 | 先补齐 SKILL.md（走 xueren-skill-init-std）|
| `403 / 401` | token 无效或过期 | `skillhub login --key skh_xxx` 重新登录；或用 `--token skh_...` |
| `SKILL.md 未找到 slug` | frontmatter 无 slug | 脚本 fallback 到目录名；建议补齐避免混淆 |

## 与相关 skill 的分工

| Skill | 职责 |
|---|---|
| `xueren-skill-init-std` | 生成标准 SKILL.md（生） |
| `xueren-skill-backup` | 备份到 E 盘（存） |
| `xueren-skill-update` | 更新流水线编排（长） |
| `xueren-skill-publish-github` | GitHub 发布（出·GitHub 通道） |
| **本 skill** | **SkillHub 发布（出·SkillHub 通道）** |

## 使用示例

```bash
# 场景 1：常规发布（SKILL.md 已 bump 到目标版本）
python ~/.workbuddy/skills/xueren-skill-publish-skillhub/scripts/publish_skillhub.py \
  --skill xueren-poster-maker \
  --changelog "新增大一新生手册模板；调整边框留白"

# 场景 2：脚本自动 bump patch
python ~/.workbuddy/skills/xueren-skill-publish-skillhub/scripts/publish_skillhub.py \
  --skill xueren-poster-maker \
  --bump-version \
  --changelog "bug fix: 修正标题字体兜底"

# 场景 3：预检（不真推）
python ~/.workbuddy/skills/xueren-skill-publish-skillhub/scripts/publish_skillhub.py \
  --skill xueren-poster-maker \
  --changelog "预检" \
  --dry-run

# 场景 5：含图片资源（SkillHub 拒收 png，需显式排除）
python ~/.workbuddy/skills/xueren-skill-publish-skillhub/scripts/publish_skillhub.py \
  --skill xueren-workbuddy-live-progress \
  --exclude "assets/*.png" \
  --changelog "首次发布"

# 场景 4：结构化输出（给编排 skill 用）
python ~/.workbuddy/skills/xueren-skill-publish-skillhub/scripts/publish_skillhub.py \
  --skill xueren-poster-maker \
  --changelog "自动化流水线" \
  --json
```

> 本 skill 的版本演进历史维护在同目录 `DEVLOG.md`（拆分约定见 `xueren-skill-backup` SKILL.md）。
