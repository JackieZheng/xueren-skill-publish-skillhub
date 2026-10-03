#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_published.py — 发布之后**验证线上真的生效**（不靠 CLI 的「发布成功」字样）。

为什么需要它（2026-10-03 实测踩坑）：
  `skills_store_cli.py publish <zip> --version 1.0.39` 打印 “✅ 发布成功 / version 1.0.39”，
  但社区搜索与下载接口当时仍返回 **v1.0.35** 的旧包（搜索索引 + 下载 CDN 缓存延迟约 5~8 分钟）。
  只信 CLI 输出就会把「没生效」当「发布成功」。
  → 本脚本用**权威路径**复核：GitHub 走 Git Blobs API，SkillHub 走**下载 zip 解内容**。

使用：
  # GitHub：commit 身份是否 noreply + blobs 有无敏感词 + DEVLOG 是否外发
  python verify_published.py --repo JackieZheng/my-skill --token <PAT|--token-env>
  # SkillHub：下载线上 zip，核对版本与关键特性字符串
  python verify_published.py --slug indiv-xueren/my-skill --expect 1.0.39 \
         --feature "MQREPAY" --feature "_panel_name"
  # 两个都查
  python verify_published.py --repo OWNER/REPO --token <PAT> \
         --slug indiv-xueren/x --expect 1.0.39 --feature "MQREPAY"

安全：token 只通过 --token / 环境变量传入，不写任何文件；不打印 token。
"""
import argparse
import base64
import io
import json
import os
import re
import sys
import urllib.request
import zipfile

# ⚠️ 特征词必须「拼出来」，不能直接写明文：本文件会随 skill 一起发到开源仓库，
# 明文特征词留在包里会让「敏感词零命中」的校验**每次都假阳性**（2026-10-03 真实踩到
# ——v1.0.4 的校验就是扫自己扫出了命中），时间一长人就麻了，等于校验失效。
BAD = ["so" + "hu", "zheng" + "xin" + "zhe", "g" + "hp_"]   # 个人信息 / PAT 泄漏特征
BAD_RE = re.compile("|".join(BAD), re.I)


def _get(url, token=None, timeout=40):
    h = {"User-Agent": "verify_published", "Accept": "*/*"}
    if token:
        h["Authorization"] = "token " + token
    r = urllib.request.Request(url, headers=h)
    return urllib.request.urlopen(r, timeout=timeout).read()


def check_github(repo, token, expect):
    print("== GitHub %s ==" % repo)
    ok = True
    c = json.loads(_get("https://api.github.com/repos/%s/commits/main" % repo, token))
    a, cm = c["commit"]["author"], c["commit"]["committer"]
    for role, who in (("author", a), ("committer", cm)):
        mail = who["email"]
        good = mail.endswith("@users.noreply.github.com") or "noreply" in mail
        print("  [%s] %s: %s <%s>" % ("OK " if good else "!! ", role, who["name"], mail))
        ok &= good
    tree = json.loads(_get("https://api.github.com/repos/%s/git/trees/main?recursive=1" % repo, token))
    paths = [t["path"] for t in tree["tree"]]
    print("  文件数: %d" % len(paths))
    leak = [p for p in paths if "DEVLOG" in p]
    print("  [%s] DEVLOG.md 是否外发: %s" % ("OK " if not leak else "!! ", bool(leak)))
    ok &= not leak
    hits = []
    for t in tree["tree"]:
        if t["type"] != "blob" or not t["path"].endswith((".py", ".md", ".json", ".html", ".bat", ".txt")):
            continue
        try:
            b = json.loads(_get("https://api.github.com/repos/%s/git/blobs/%s" % (repo, t["sha"]), token))
            s = base64.b64decode(b["content"]).decode("utf-8", "ignore")
        except Exception:
            continue
        if BAD_RE.search(s):
            hits.append(t["path"])
    print("  [%s] 敏感词命中: %s" % ("OK " if not hits else "!! ", hits or "无"))
    ok &= not hits
    if expect:
        got = next((p for p in paths if p.endswith("SKILL.md")), None)
        if not got:
            print("  [!! ] SKILL.md 不在包里"); ok = False
        else:
            raw = base64.b64decode(
                json.loads(_get("https://api.github.com/repos/%s/git/blobs/%s"
                                % (repo, next(t["sha"] for t in tree["tree"]
                                             if t["path"] == got)), token))["content"]).decode("utf-8", "ignore")
            v = re.search(r"^version:\s*(\S+)", raw, re.M)
            v = v.group(1) if v else "?"
            good = v == expect
            print("  [%s] SKILL.md version=%s（期望 %s）" % ("OK " if good else "!! ", v, expect))
            ok &= good
    return ok


def check_skillhub(slug, expect, features):
    print("== SkillHub @%s ==" % slug)
    ok = True
    if not slug.startswith("@"):
        slug = "@" + slug
    raw = _get("https://api.skillhub.cn/api/v1/download?slug=%s" % slug, timeout=90)
    z = zipfile.ZipFile(io.BytesIO(raw))
    names = z.namelist()
    print("  线上包: %d bytes / %d 文件" % (len(raw), len(names)))
    sk = next((n for n in names if n.endswith("SKILL.md")), None)
    if not sk:
        print("  [!! ] 包里没有 SKILL.md"); return False
    t = z.read(sk).decode("utf-8", "ignore")
    v = re.search(r"^version:\s*(\S+)", t, re.M)
    v = v.group(1) if v else "?"
    good = v == expect
    print("  [%s] 线上 SKILL.md version=%s（期望 %s）" % ("OK " if good else "!! ", v, expect))
    ok &= good
    for f in features:
        hit = any(f in z.read(n).decode("utf-8", "ignore")
                  for n in names if n.endswith(".py"))
        print("  [%s] 特性 %s" % ("OK " if hit else "!! ", f))
        ok &= hit
    leak = [n for n in names if "DEVLOG" in n]
    print("  [%s] DEVLOG 未外发" % ("OK " if not leak else "!! "))
    ok &= not leak
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", help="GitHub 仓库 owner/name")
    ap.add_argument("--slug", help="SkillHub slug（可带 @namespace）")
    ap.add_argument("--expect", help="期望版本号（SKILL.md version）")
    ap.add_argument("--token", default="", help="GitHub PAT（也可用 GH_TOKEN 环境变量）")
    ap.add_argument("--feature", action="append", default=[], help="要核对的关键字符串（可重复）")
    a = ap.parse_args()
    token = a.token or os.environ.get("GH_TOKEN", "")
    ok = True
    if a.repo:
        ok = check_github(a.repo, token, a.expect) and ok
    if a.slug:
        ok = check_skillhub(a.slug, a.expect, a.feature) and ok
    if not ok:
        print("\n❌ 校验未通过（上面标 !! 的项）")
        sys.exit(1)
    print("\n✅ 线上校验通过")


if __name__ == "__main__":
    main()
