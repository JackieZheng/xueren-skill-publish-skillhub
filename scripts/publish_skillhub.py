#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
publish_skillhub.py — 把本地 WorkBuddy skill 打包并发布到 SkillHub 社区源（一键机械流程）。

用法：
  python publish_skillhub.py --skill xueren-my-skill --changelog "本次变更摘要"
  python publish_skillhub.py --skill xueren-my-skill --version 1.2.0 --changelog "..."
  python publish_skillhub.py --skill xueren-my-skill --bump-version --changelog "..."
  python publish_skillhub.py --skill xueren-my-skill --changelog "..." --dry-run
  python publish_skillhub.py --skill xueren-my-skill --changelog "..." --json

设计原则：
- 零外部依赖：只依赖 Python 标准库 + 已安装的 SkillHub CLI（~/.skillhub/skills_store_cli.py）。
- 打包即排除：SkillHub 拒收 .bat / LICENSE / .gitignore / .git / __pycache__ / .venv / node_modules 等。
- **面向用户、不做开发者仓库**（2026-10-03）：SkillHub 的读者是「用 skill 的人」，因此
  ① `README.md` **进包**（承担功能介绍 / 安装 / 快速上手，README 必须写成用户向）；
  ② `docs/` 与 `_test_*` / `_probe_*` / `_demo_*` 等**开发 / 测试脚本一律不进包**（只发 GitHub，见 publish-github skill）。
- 版本一致：默认从 SKILL.md frontmatter 读 version；--version 可覆盖；--bump-version 自动 patch+1。
- 幂等重试：对 SkillHub 429 限流自动退避重试；对 409 "version already exists" 明确报错退出。
- 无 token 硬编码：Token 从 ~/.skillhub/credentials.json 读取（skillhub login 后自动生成）；--token 可覆盖。
- 输出：默认人类可读文本；--json 时仅 stdout 输出 JSON 一行，stderr 写日志。
"""

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import re
import subprocess
import sys
import time
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

SKIP_DIRS = {".git", "__pycache__", ".venv", "venv", "node_modules", ".cache", "cache",
             ".idea", ".vscode", ".pytest_cache", ".tmp_verify", ".tmp-publish-skillhub",
             # playwright 持久化 profile：调试遗留（含 .db / localStorage / Session Storage），
             # 既占体积又容易被 SkillHub 内容审核判为「不允许的文件类型」而 400 拒收。
             # 2026-10-03 实测：`scripts/.pwprofile/Default/declarative_performance_observer.db`
             # 会把整个发布打成失败。与 xueren-skill-backup 的 EXCLUDE_DIRS 口径保持一致。
             ".pwprofile",
             # 2026-10-03 用户约定：docs/ = 开发 / 排障手册（三层分工里的第三层），
             # 读者是开发者不是普通用户 → 只发 GitHub，不进 SkillHub 用户包。
             "docs"}
# SkillHub 拒收的扩展名（会触发内容审核失败）
SKIP_EXT = {".bat", ".cmd", ".exe", ".msi", ".sys", ".dll", ".ocx", ".scr", ".vbs", ".ps1", ".psm1"}
# 运行期产物扩展名：日志/截图缓存不上传（避免把本机路径、调试图带进社区包）
SKIP_EXT.update({".log", ".pyc", ".pyo"})
# 风险扩展名：SkillHub 内容审核可能拒收（实测 png 会被 400 拒绝）。
# 不默认排除（有的 skill 的图片是运行必需资源），只在打包后提示，由调用方用 --exclude 决定。
RISKY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".ico",
             ".mp4", ".mov", ".avi", ".zip", ".7z", ".tar", ".gz",
             ".pdf", ".docx", ".xlsx", ".pptx"}
# SkillHub 拒收的顶层文件名（大小写敏感 + 大写忽略）
# `.gitattributes` / `.gitmodules` 是**仓库专用元数据**，SkillHub 会以
# 「不允许的文件类型」400 拒收（实测 2026-10-01）——与 .gitignore 同类，一律不进包。
# ⚠️ README **不在此列**（2026-10-03 用户约定放宽）：SkillHub 面向终端用户，
# 带一份 README 正好承担「功能介绍 / 安装 / 快速上手」——但 README 必须写成
# 用户向的功能介绍；开发 / 测试内容放 docs/ 或 DEVLOG.md，不进用户包。
SKIP_TOP_LEVEL_NAMES = {".gitignore", ".gitattributes", ".gitmodules",
                        "LICENSE", "LICENSE-MIT", "LICENSE.txt"}
# 按用户约定（2026-10-01）：**开发日志不随发布物外发**——SkillHub 与 GitHub 口径一致。
NEVER_PUBLISH = {"devlog.md"}      # 用户约定（2026-10-01）；小写存放，判定见 _is_never_publish()

# 按用户约定（2026-10-03 修订）：**SkillHub 与 GitHub 都算「产品分发」，开发 / 测试内容两边一律不外发**
# （原口径「GitHub 面向开发者、开发脚本是价值」已被用户否定：Release 不是二次开发源码站）。
# 本侧只做「不进用户包」；github 侧 publish_skill.py 用同一套前缀 / 后缀规则严格对齐。
# 匹配「相对 skill 根目录的路径」中的文件名（小写、忽略目录层级）：
SKIP_NAME_PREFIXES = ("_test_", "test_", "_probe_", "_debug_", "_demo_", "_selftest_", "_bench_")
SKIP_NAME_SUFFIXES = ("_test.py", "_tests.py", "_probe.py", "_check.py", "_debug.py")


def _is_never_publish(name_lower: str) -> bool:
    """开发日志等「绝对不进用户包」文件名判定（小写入参，见 NEVER_PUBLISH 注释）。"""
    return name_lower in NEVER_PUBLISH


def _is_dev_test_script(inner: str) -> bool:
    """inner = 相对 skill 根目录的路径（如 `scripts/_test_check_update.py`）。"""
    name = os.path.basename(inner).lower()
    return name.startswith(SKIP_NAME_PREFIXES) or name.endswith(SKIP_NAME_SUFFIXES)

HOME = Path(os.path.expanduser("~"))
DEFAULT_CLI = HOME / ".skillhub" / "skills_store_cli.py"
CREDENTIALS_FILE = HOME / ".skillhub" / "credentials.json"

# 版本正则
VERSION_RE = re.compile(r"^version:\s*[\"']?([0-9]+\.[0-9]+\.[0-9]+(?:[-+][0-9A-Za-z.-]+)?)", re.MULTILINE)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def _log(msg: str, quiet_json: bool) -> None:
    if not quiet_json:
        print(msg, file=sys.stderr)


def read_text(fp: Path) -> str:
    return fp.read_text(encoding="utf-8")


def get_fm_field(text: str, key: str) -> Optional[str]:
    """从 SKILL.md frontmatter 读单个字段。"""
    m = re.search(rf"(?m)^{re.escape(key)}:\s*(.*)$", text)
    if not m:
        return None
    v = m.group(1).strip().strip("\"'")
    return v or None


def bump_patch(ver: str) -> str:
    """1.2.3 -> 1.2.4；仅处理 X.Y.Z 形式；若版本带 prerelease 直接丢弃 prerelease。"""
    m = re.match(r"^([0-9]+)\.([0-9]+)\.([0-9]+)", ver)
    if not m:
        return ver
    return f"{int(m.group(1))}.{int(m.group(2))}.{int(m.group(3)) + 1}"


def get_token(cli_token: Optional[str]) -> Tuple[str, str]:
    """获取 SkillHub token。优先级：--token 参数 > 环境变量 SKILLHUB_TOKEN > ~/.skillhub/credentials.json。"""
    if cli_token:
        return cli_token, "arg"
    env = os.environ.get("SKILLHUB_TOKEN")
    if env:
        return env, "env:SKILLHUB_TOKEN"
    if CREDENTIALS_FILE.exists():
        try:
            data = json.loads(read_text(CREDENTIALS_FILE))
            # credentials.json 的常见结构（skillhub login 产出）：
            # {"user": {"token": "skh_..."}, "tokens": {"personal": "skh_..."}, ...}
            for path in [
                ("user", "token"),
                ("tokens", "personal"),
                ("token",),
            ]:
                cur: dict = data
                for k in path:
                    if isinstance(cur, dict) and k in cur:
                        cur = cur[k]
                    else:
                        cur = None
                        break
                if isinstance(cur, str) and cur.startswith("skh_"):
                    return cur, "file:credentials.json"
        except Exception as e:
            _log(f"[warn] 读取 credentials.json 失败: {e}", quiet_json=False)
    # 找不到 token 也允许继续（skillhub CLI 会用默认 host 的匿名凭证或交互式登录），但会打印警告
    _log("[warn] 未找到 SkillHub token，将依赖 skillhub CLI 本地已登录状态", quiet_json=False)
    return "", "none"


def find_skill_dir(skill_arg: str) -> Path:
    """解析 --skill 参数：可能是目录、可能是 skill 名（在 ~/.workbuddy/skills/ 下查找）。"""
    p = Path(skill_arg)
    if p.is_dir():
        return p.resolve()
    if not p.suffix:
        # 按 skill 名解析
        candidate = HOME / ".workbuddy" / "skills" / skill_arg
        if candidate.is_dir():
            return candidate.resolve()
    raise SystemExit(f"[error] skill 路径不存在: {skill_arg}")


def find_cli(cli_path: Optional[str]) -> Path:
    """定位 SkillHub CLI Python 脚本。"""
    if cli_path:
        p = Path(cli_path)
        if not p.exists():
            raise SystemExit(f"[error] --cli 指定的文件不存在: {cli_path}")
        return p
    if DEFAULT_CLI.exists():
        return DEFAULT_CLI
    raise SystemExit(
        "[error] SkillHub CLI 未找到，请先执行 "
        "`curl -fsSL https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/install/latest.tar.gz | tar` "
        f"安装（期望位置 {DEFAULT_CLI}）"
    )


# ---------------------------------------------------------------------------
# 打包
# ---------------------------------------------------------------------------

# 包内 markdown 的图片引用（用于查「资源没进包 → 裂图」）
MD_IMAGE_RE = re.compile(r"!\[[^\]]*\]\(([^)\s]+)")


def _inner_rel(skill_dir: Path, rel: str) -> str:
    """把 rel（含 skill 目录名前缀，zip 内写的是这个）转成相对 skill 根的路径。"""
    parts = rel.split("/")
    return "/".join(parts[1:]) if len(parts) > 1 else rel


def _dirname(rel: str) -> Path:
    """markdown 所在目录（相对 skill 根），用于解析相对图片路径。"""
    p = Path(rel)
    return p.parent if str(p.parent) not in (".", "") else Path(".")


def build_zip(skill_dir: Path, out_zip: Path,
              extra_exclude: Optional[List[str]] = None) -> Tuple[int, List[str], List[str], List[str]]:
    """打包 skill 目录为 zip。返回 (总文件数, 已包含路径, 已排除路径, 风险文件)。

    extra_exclude: 额外的排除 glob（相对 skill 根目录，如 "assets/*.png"）。
    """
    if out_zip.exists():
        out_zip.unlink()

    pats = [p for p in (extra_exclude or []) if p]
    included: List[str] = []
    excluded: List[str] = []
    risky: List[str] = []
    in_pkg_inner: set = set()          # 已进包的「相对 skill 根」路径，用于查裂图引用
    md_docs: List[str] = []            # 已进包的 markdown（后面离块扫描图片引用）

    with zipfile.ZipFile(out_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(skill_dir.rglob("*")):
            if not f.is_file():
                continue
            rel = f.relative_to(skill_dir.parent).as_posix()  # 含 skill 目录名前缀
            parts = rel.split("/")
            inner = "/".join(parts[1:])                      # 相对 skill 根目录

            # 排除目录内嵌（.git/ 之类）
            if any(p in SKIP_DIRS for p in parts[1:-1]):
                excluded.append(rel)
                continue
            # 排除开发 / 测试文档（docs/ 等用户用不到的排障手册，只发 GitHub）
            if parts[1].lower() in SKIP_DIRS:
                excluded.append(f"{rel} [dir:dev-doc]")
                continue
            # 排除开发 / 测试脚本（_test_* / _probe_* / _demo_*，只发 GitHub）
            if _is_dev_test_script(inner):
                excluded.append(f"{rel} [dev-script]")
                continue
            # 排除扩展名（SkillHub 内容审核）
            if f.suffix.lower() in SKIP_EXT:
                excluded.append(f"{rel} [ext:{f.suffix}]")
                continue
            # 排除顶层特定文件名（LICENSE/README/.gitignore）
            if len(parts) == 2 and parts[1] in SKIP_TOP_LEVEL_NAMES:
                excluded.append(f"{rel} [top:{parts[1]}]")
                continue
            # 开发日志等「不外发」文件（用户约定，与 GitHub 发布口径一致）
            # v1.0.9：改为按**文件名**匹配（不限层级）—— 2026-10-03 用户约定 DEVLOG.md 归入
            # docs/ 目录（开发级文档统一住 docs），路径变成 docs/DEVLOG.md，旧判定会漏。
            if _is_never_publish(os.path.basename(parts[1]).lower()):
                excluded.append(f"{rel} [never-publish]")
                continue
            # 用户显式 --exclude 的 glob
            if pats and any(fnmatch.fnmatch(inner, p) or fnmatch.fnmatch(rel, p) for p in pats):
                excluded.append(f"{rel} [exclude]")
                continue
            # 风险类型：SkillHub 内容审核可能拒收（如 png 图片），放行但提示
            if f.suffix.lower() in RISKY_EXT:
                risky.append(f"{inner} [risk:{f.suffix}]")
            in_pkg_inner.add(inner)
            if inner.lower().endswith((".md", ".markdown")):
                md_docs.append(rel)
            z.write(f, rel)
            included.append(rel)

    # 包内 md 引用的本地资源若没进包 → 用户装完看 README 会裂图，明确提示改外链。
    # 必须在 with 块**外**扫描：zip 处于写状态时读条目不可靠。
    broken_img: List[str] = []
    if md_docs:
        try:
            with zipfile.ZipFile(out_zip, "r") as zr:
                for rel in md_docs:
                    md_rel = _inner_rel(skill_dir, rel)
                    try:
                        text = zr.read(rel).decode("utf-8", "replace")
                    except Exception:
                        continue
                    for src in MD_IMAGE_RE.findall(text):
                        if src.lower().startswith(("http://", "https://", "data:", "//")):
                            continue          # 外链图：SkillHub / GitHub 都能显示，不告警
                        resolved = (_dirname(md_rel) / src).as_posix().lstrip("/")
                        if resolved not in in_pkg_inner:
                            broken_img.append(f"{md_rel} -> {src}")

        except Exception:
            pass

    return len(included), included, excluded, risky, broken_img


# ---------------------------------------------------------------------------
# 发布
# ---------------------------------------------------------------------------

def run_skillhub_publish(
    cli: Path,
    zip_path: Path,
    version: str,
    changelog: str,
    token: str,
    host: Optional[str],
    dry_run: bool,
    retries: int,
    base_delay: float,
    quiet_json: bool,
) -> Tuple[int, str]:
    """调用 skillhub CLI 发布，返回 (rc, combined_output)。"""
    cmd = [
        sys.executable, str(cli), "publish", str(zip_path),
    ]
    if version:
        cmd += ["--version", version]
    if changelog:
        cmd += ["--changelog", changelog]
    if token:
        cmd += ["--token", token]
    if host:
        cmd += ["--host", host]
    if dry_run:
        cmd.append("--dry-run")

    last_rc = -1
    last_out = ""
    for attempt in range(1, retries + 1):
        _log(f"[publish attempt {attempt}/{retries}] skillhub publish {zip_path.name} --version {version}", quiet_json)
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
            rc = r.returncode
            combined = (r.stdout or "") + "\n" + (r.stderr or "")
            last_rc = rc
            last_out = combined
            if rc == 0:
                return rc, combined
            # 429 限流 / 5xx 重试
            low = combined.lower()
            if "429" in low or "rate limit" in low or "too many" in low or "503" in low or "502" in low:
                delay = base_delay * attempt
                _log(f"[warn] rate-limited/5xx, sleeping {delay:.1f}s", quiet_json)
                time.sleep(delay)
                continue
            # 409 version exists — 不重试
            if "409" in low or "version exists" in low or "already exists" in low:
                _log("[error] SkillHub 已存在该版本，拒绝覆盖（SkillHub 版本号不可回滚/覆盖）", quiet_json)
                return rc, combined
            # 其他 4xx 也不重试
            if "403" in low or "401" in low or "400" in low:
                return rc, combined
        except subprocess.TimeoutExpired:
            last_rc = -1
            last_out = "[timeout] skillhub CLI 180s 超时"
            _log(f"[warn] attempt {attempt} timeout", quiet_json)
            time.sleep(base_delay * attempt)
    return last_rc, last_out


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------

def main() -> int:
    ap = argparse.ArgumentParser(description="把本地 WorkBuddy skill 发布到 SkillHub 社区源")
    ap.add_argument("--skill", required=True, help="skill 目录或 skill 名（如 xueren-my-skill）")
    ap.add_argument("--version", default="", help="覆盖 version（默认读 SKILL.md；也可用 --bump-version 自动 +1 patch）")
    ap.add_argument("--changelog", required=True, help="本次发布 changelog 文本")
    ap.add_argument("--bump-version", action="store_true", help="自动 patch+1（默认 1.2.3 -> 1.2.4）")
    ap.add_argument("--token", default="", help="覆盖已登录 SkillHub token（skh_...）")
    ap.add_argument("--host", default="", help="API host 覆盖（默认用 CLI 默认）")
    ap.add_argument("--cli", default="", help="SkillHub CLI 脚本路径（默认 ~/.skillhub/skills_store_cli.py）")
    ap.add_argument("--workdir", default="", help="临时 zip 输出目录（默认 <skill_dir>/../.tmp-publish-skillhub/）")
    ap.add_argument("--retries", type=int, default=3, help="失败重试次数（默认 3）")
    ap.add_argument("--dry-run", action="store_true", help="仅打包并跑 --dry-run，不真的推送")
    ap.add_argument("--exclude", action="append", default=[],
                    help="额外排除的 glob（相对 skill 根目录，可重复；如 --exclude \"assets/*.png\"）")
    ap.add_argument("--json", action="store_true", help="以 JSON 单行输出结果")
    args = ap.parse_args()

    quiet_json = bool(args.json)

    # 1) 定位 skill 目录
    skill_dir = find_skill_dir(args.skill)
    skill_md = skill_dir / "SKILL.md"
    if not skill_md.exists():
        return _emit(args.json, {
            "ok": False,
            "stage": "preflight",
            "error": f"SKILL.md 缺失: {skill_md}",
        })

    skill_md_text = read_text(skill_md)

    # 2) 解析 version
    m = VERSION_RE.search(skill_md_text)
    if not m:
        return _emit(args.json, {
            "ok": False,
            "stage": "preflight",
            "error": "SKILL.md 缺少 version 字段",
        })
    base_version = m.group(1)
    if args.bump_version:
        version = bump_patch(base_version)
    elif args.version:
        version = args.version
    else:
        version = base_version

    # 3) slug 校验（SkillHub 以 slug 作为唯一标识）
    slug = get_fm_field(skill_md_text, "slug") or skill_dir.name
    name = get_fm_field(skill_md_text, "name") or skill_dir.name

    # 4) 定位 CLI
    cli = find_cli(args.cli or None)

    # 5) 打包
    if args.workdir:
        workdir = Path(args.workdir)
    else:
        workdir = skill_dir.parent / ".tmp-publish-skillhub"
    workdir.mkdir(parents=True, exist_ok=True)
    zip_path = workdir / f"{skill_dir.name}.zip"

    n_included, included, excluded, risky, broken_img = build_zip(skill_dir, zip_path,
                                                                  extra_exclude=args.exclude)
    if n_included == 0:
        return _emit(args.json, {
            "ok": False,
            "stage": "pack",
            "error": "打包后无文件（检查目录内容与排除规则）",
        })

    _log(f"[pack] {n_included} 文件, {len(excluded)} 排除 → {zip_path}", quiet_json)
    if risky:
        _log("[pack] ⚠️ 含风险类型文件（SkillHub 可能拒收，如 png）：%s" % ", ".join(risky[:5]),
             quiet_json)
        _log("       如需排除请加：--exclude \"assets/*.png\"（可多次）", quiet_json)
    if broken_img:
        _log("[pack] ⚠️ %d 处图片引用指向**没进包**的本地资源，装完看文档会裂图：%s"
             % (len(broken_img), "; ".join(broken_img[:5])), quiet_json)
        _log("       修法：把图片改成**外链 URL**（SkillHub / GitHub 都支持外链图片）或"
             "把资源打进包（注意 png 会被拒收，外链更稳）", quiet_json)

    # 6) 获取 token
    token, token_src = get_token(args.token or None)

    # 7) 发布
    rc, out = run_skillhub_publish(
        cli=cli, zip_path=zip_path, version=version, changelog=args.changelog,
        token=token, host=args.host or None, dry_run=args.dry_run,
        retries=args.retries, base_delay=5.0, quiet_json=quiet_json,
    )

    ok = rc == 0
    result = {
        "ok": ok,
        "stage": "publish" if ok else "publish",
        "dry_run": args.dry_run,
        "skill": skill_dir.name,
        "skill_dir": str(skill_dir),
        "slug": slug,
        "name": name,
        "version": version,
        "zip": str(zip_path),
        "zip_bytes": zip_path.stat().st_size,
        "n_included": n_included,
        "n_excluded": len(excluded),
        "excluded_sample": excluded[:10],
        "risky": risky[:10],
        "token_source": token_src,
        "cli": str(cli),
        "returncode": rc,
        "output_tail": out[-2000:] if out else "",
        "timestamp_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    return _emit(args.json, result)


def _emit(json_mode: bool, payload: dict) -> int:
    if json_mode:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        # 人类可读
        if payload.get("ok"):
            print("=== ✅ SkillHub 发布成功 ===")
            print(f"  skill    : {payload['skill']}")
            print(f"  slug     : {payload['slug']}")
            print(f"  version  : {payload['version']}")
            print(f"  dry-run  : {payload.get('dry_run', False)}")
            print(f"  zip      : {payload['zip']} ({payload['zip_bytes']} bytes)")
            print(f"  files    : {payload['n_included']} 打包 / {payload['n_excluded']} 排除")
            if payload.get("excluded_sample"):
                print(f"  excluded : {payload['excluded_sample']}")
        else:
            print("=== ❌ SkillHub 发布失败 ===")
            print(f"  stage  : {payload.get('stage')}")
            print(f"  error  : {payload.get('error', '')}")
            if payload.get("output_tail"):
                print(f"  output : {payload['output_tail']}")
    return 0 if payload.get("ok") else 1


if __name__ == "__main__":
    sys.exit(main())
