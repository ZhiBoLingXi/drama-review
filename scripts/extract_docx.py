#!/usr/bin/env python3
"""Extract a .docx into clean, structured text so the model can read it
and faithfully reproduce its format.

Why this exists: the user's source documents (对标剧集纲 / 目标剧细纲 / 剧本正文)
are real production files with messy, inconsistent internal formatting. Before
we can imitate a format we have to *see* it clearly — both the prose and the
paragraph styles. This tool dumps that, plus a quick structural summary.

Usage:
  python extract_docx.py FILE.docx                 # clean text to stdout
  python extract_docx.py FILE.docx --analyze       # structure summary only
  python extract_docx.py FILE.docx --styles        # annotate each line w/ style
  python extract_docx.py FILE.docx --episode 34    # just episode 34's block
  python extract_docx.py FILE.docx --wordcount     # per-episode正文字数 (flags <1200)

Requires python-docx (pip install python-docx). Falls back to pandoc if the
package is unavailable.
"""
import argparse
import re
import subprocess
import sys

EP_PATTERNS = [
    re.compile(r"^\s*第\s*([0-9]{1,3})\s*集"),                      # 第34集 / 第 34 集
    re.compile(r"^\s*第\s*([一二三四五六七八九十百零两]+)\s*集\s*$"),  # 第三十四集
]

CN_NUM = {c: i for i, c in enumerate("零一二三四五六七八九")}


def cn_to_int(s):
    """Convert a Chinese numeral (up to 百) to int. Best-effort."""
    s = s.strip()
    if not s:
        return None
    total, section, ok = 0, 0, False
    i = 0
    while i < len(s):
        ch = s[i]
        if ch in CN_NUM:
            section = section * 10 + CN_NUM[ch]
            ok = True
        elif ch == "十":
            section = (section or 1) * 10
            ok = True
        elif ch == "百":
            section = (section or 1) * 100
            ok = True
        else:
            return None
        i += 1
    return (total + section) if ok else None


def episode_number(line):
    for pat in EP_PATTERNS:
        m = pat.match(line)
        if not m:
            continue
        tok = m.group(1)
        return int(tok) if tok.isdigit() else cn_to_int(tok)
    return None


def read_paragraphs(path):
    """Return list of (text, style_name). Prefer python-docx; fall back to pandoc."""
    try:
        import docx  # type: ignore
        doc = docx.Document(path)
        return [(p.text.rstrip(), p.style.name if p.style else "") for p in doc.paragraphs]
    except ImportError:
        out = subprocess.run(
            ["pandoc", path, "-t", "plain"], capture_output=True, text=True
        )
        return [(ln.rstrip(), "") for ln in out.stdout.splitlines()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--analyze", action="store_true", help="print structure summary only")
    ap.add_argument("--styles", action="store_true", help="annotate each line with its paragraph style")
    ap.add_argument("--episode", type=int, help="print only this episode's block")
    ap.add_argument("--wordcount", action="store_true", help="per-episode正文字数; flags <1200 as 情节单薄")
    args = ap.parse_args()

    paras = read_paragraphs(args.path)

    # Build episode index: episode_number -> first paragraph idx
    index = []  # (ep_no, para_idx, header_text)
    for i, (text, _style) in enumerate(paras):
        ep = episode_number(text)
        if ep is not None:
            index.append((ep, i, text.strip()))

    if args.analyze:
        from collections import Counter
        style_counts = Counter(s for _t, s in paras if _t.strip() and s)
        field_labels = Counter()
        for t, _s in paras:
            for label in ["剧情框架", "核心爽点", "核心看点", "结尾钩子",
                          "核心期待", "一句话简介", "人物定位", "人物：", "场"]:
                if t.strip().startswith(label) or ("：" in t and t.split("：")[0].strip() == label.rstrip("：")):
                    field_labels[label] += 1
        eps = sorted({e for e, _i, _h in index})
        print(f"# 结构分析: {args.path}")
        print(f"非空段落数: {sum(1 for t, _s in paras if t.strip())}")
        print(f"识别到的集编号: {eps[:3]}{'...' if len(eps) > 6 else ''}{eps[-3:] if len(eps) > 6 else eps[3:]}")
        print(f"集数范围: {min(eps) if eps else '-'} → {max(eps) if eps else '-'}  (共 {len(eps)} 个唯一集号)")
        print("\n## 高频段落样式 (用于格式克隆)")
        for s, c in style_counts.most_common(12):
            print(f"  {c:>4}  {s}")
        print("\n## 检测到的字段标签 (判断文档类型/格式)")
        for label, c in field_labels.most_common():
            print(f"  {c:>4}  {label}")
        print("\n## 集标题样例 (前6)")
        for ep, _i, h in index[:6]:
            print(f"  第{ep}集 :: {h}")
        return

    if args.wordcount:
        # Segment by consecutive episode headers (robust to duplicate ep numbers),
        # count non-whitespace chars per block — this is the "撑不撑得起2分钟" proxy.
        if not index:
            print("(未识别到分集，无法逐集统计字数；该稿可能是集纲或单集)", file=sys.stderr)
            sys.exit(1)
        bounds = sorted(((e, i) for e, i, _h in index), key=lambda x: x[1])
        print(f"# 逐集正文字数: {args.path}  (阈值 1200 字)")
        thin = []
        for k, (ep, start) in enumerate(bounds):
            end = bounds[k + 1][1] if k + 1 < len(bounds) else len(paras)
            chars = sum(len(re.sub(r"\s", "", t)) for t, _s in paras[start:end])
            flag = "  🔴 情节单薄(<1200)" if chars < 1200 else ""
            print(f"  第{ep}集: {chars:>5} 字{flag}")
            if chars < 1200:
                thin.append((ep, chars))
        if thin:
            print(f"\n## ⚠ {len(thin)} 集低于 1200 字（撑不起 2 分钟，建议加戏而非拖时长）:")
            print("  " + "、".join(f"第{e}集({c}字)" for e, c in thin))
        else:
            print("\n所有集均 ≥1200 字。")
        return

    if args.episode is not None:
        # collect paragraphs from this episode header up to the next episode header
        starts = [i for _e, i, _h in index if _e == args.episode]
        if not starts:
            print(f"(未找到第{args.episode}集)", file=sys.stderr)
            sys.exit(1)
        start = starts[0]
        later = [i for _e, i, _h in index if i > start]
        end = min(later) if later else len(paras)
        for t, s in paras[start:end]:
            if not t.strip():
                continue
            print(f"[{s}] {t}" if args.styles else t)
        return

    for t, s in paras:
        if not t.strip():
            print()
            continue
        print(f"[{s}] {t}" if args.styles else t)


if __name__ == "__main__":
    main()
