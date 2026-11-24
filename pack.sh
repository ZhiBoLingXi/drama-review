#!/usr/bin/env bash
# 打 WorkBuddy 技能包到 dist/drama-review-v<版本>.zip：zip 顶层是 drama-review/ 目录，里面是 SKILL.md 和子资源。
# 规范见 https://open.workbuddy.cn/docs/skill（技能基础结构、子资源目录说明）。
set -euo pipefail
cd "$(dirname "$0")"

ver=$(sed -n 's/^  version: *//p' SKILL.md | head -1)
[ -n "$ver" ] || { echo "SKILL.md 里没找到 version" >&2; exit 1; }
SKILL_FILES=(SKILL.md profiles.json references scripts)

rm -rf dist/build
mkdir -p dist/build/drama-review
cp -R "${SKILL_FILES[@]}" dist/build/drama-review/
find dist/build \( -name __pycache__ -o -name .DS_Store \) -prune -exec rm -rf {} +

# 源 SKILL.md 按 Agent Skills 规范把展示字段放在 metadata 下；WorkBuddy 市场只认顶层字段，打包时提到顶层，并核对必填项。
python3 -B - dist/build/drama-review/SKILL.md <<'PY'
import sys
p = sys.argv[1]
lines = open(p, encoding="utf-8").read().split("\n")
end = lines.index("---", 1)
head, out, i = lines[1:end], [], 0
while i < len(head):
    if head[i] == "metadata:":
        i += 1
        while i < len(head) and (head[i].startswith("  ") or not head[i]):
            out.append(head[i][2:])
            i += 1
    else:
        out.append(head[i])
        i += 1
need = ("name:", "display_name:", "display_name_en:", "description:", "description_zh:", "description_en:", "version:", "author:")
miss = [k for k in need if not any(l.startswith(k) for l in out)]
if miss:
    sys.exit(f"{p} 拍平后缺 WorkBuddy 必填字段：{miss}")
open(p, "w", encoding="utf-8").write("\n".join(["---", *out, *lines[end:]]))
PY

python3 -B scripts/review.py --help >/dev/null  # 脚本跑不起来就不打包

(cd dist/build && rm -f "../drama-review-v$ver.zip" && zip -qr "../drama-review-v$ver.zip" drama-review)
rm -rf dist/build
ls -l "dist/drama-review-v$ver.zip"
