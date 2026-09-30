# 雪人老师·Skill发布到SkillHub

> One-click package and publish WorkBuddy skills to SkillHub community (zip + CLI + retry + JSON output).

本 skill 遵循通用 SKILL 规范（`SKILL.md` + `meta.json` + 资源目录），可装入任何支持 skill 的 AI 工具（WorkBuddy、Claude Code、Cursor 等）。

## 安装（作为 AI 工具的 skill）

1. 克隆仓库：

   ```bash
   git clone https://github.com/JackieZheng/xueren-skill-publish-skillhub.git
   ```

2. 把目录放进你的 AI 工具 skills 目录（以 WorkBuddy 为例）：

   ```bash
   # Windows
   xcopy /E /I 雪人老师·Skill发布到SkillHub %USERPROFILE%\.workbuddy\skills\雪人老师·Skill发布到SkillHub
   # macOS / Linux
   cp -r 雪人老师·Skill发布到SkillHub ~/.workbuddy/skills/
   ```

3. 如有依赖，进入目录安装：

   ```bash
   cd 雪人老师·Skill发布到SkillHub && npm install   # 或 pip install -r requirements.txt（视 skill 而定）
   ```

## 使用方式

装好后使用就是普通的对话形式——在 AI 工具里说出对应意图，它会按 `SKILL.md` 的流程引导你完成。详细流程见 `SKILL.md`。

## 项目结构

```
xueren-skill-publish-skillhub/
scripts/
.gitignore
DEVLOG.md
LICENSE
SKILL.md
meta.json
    publish_skillhub.py
```

## License

[MIT](./LICENSE) © 2026 雪人

---

GitHub: https://github.com/JackieZheng/xueren-skill-publish-skillhub
