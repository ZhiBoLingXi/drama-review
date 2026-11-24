#!/usr/bin/env python3
"""drama-review：AI 剧本审查。脚本先查确定性硬伤，模型逐集写审查卡，脚本校验卡片再合成报告。只用标准库，不联网。

  review.py next   --dir review/                         下一步做什么（每一步先跑它）
  review.py lint   <剧本.md> --profile clone [--min-total 800]   只跑脚本层，打印每集问题
  review.py init   <剧本.md> --profile clone --out review/ [--bible bible.md] [--min-total 800]
                                                         脚本层 + 每集一份审查任务包 packet-NNN.md
  review.py check  review/ [--ep 7]                       校验审查卡 card-NNN.json（引文必须真在剧本里）
  review.py report review/ [--out 审查报告.md]            合成整体 + 逐集报告

退出码：0 通过；1 输入错误；2 有问题。
"""
import argparse
import glob
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scriptlib import DIMS, SCENE_HEAD, han, lint_script, norm, pick_bodies, speech_lines, split_episodes  # noqa: E402

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ME = os.path.abspath(__file__)
GRADES = {"A", "B", "C"}
VERDICTS = {"pass", "fix", "rewrite"}
VAGUE = re.compile(r"加强|增强|提升|优化|丰富|注意|适当|进一步|更加|更有|强化|突出")
LEVEL_TEXT = {"floor": "下限·必改", "ceiling": "上限·可提"}


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def read(path):
    with open(path, encoding="utf-8") as f:
        return f.read()


def resolve_profile(args):
    profiles = load(os.path.join(SKILL_DIR, "profiles.json"))
    if args.profile not in profiles or args.profile.startswith("_"):
        raise ValueError(f"没有剧本类型 {args.profile}，可选：{', '.join(k for k in profiles if not k.startswith('_'))}")
    p = dict(profiles[args.profile], name=args.profile)
    for k in ("min_total", "min_scenes", "max_locations", "max_line_han"):
        v = getattr(args, k, None)
        if v is not None:
            p[k] = v
    return p


def cmd_lint(args):
    p = resolve_profile(args)
    eps, issues, stats = lint_script(read(args.script), p)
    if not eps:
        print(json.dumps({"error": "没找到「第N集」标题，按集切不开。docx 先用 extract_docx.py 转成文本"}, ensure_ascii=False))
        return 1
    floor = [i for i in issues if i["level"] == "floor"]
    print(json.dumps({"profile": p["name"], "episodes": len(stats), "floor": len(floor), "ceiling": len(issues) - len(floor),
                      "issues": issues if args.full else issues[:40],
                      **({"more": f"还有 {len(issues) - 40} 条，加 --full 看全部，或跑 init 按集分开"} if len(issues) > 40 and not args.full else {})},
                     ensure_ascii=False, indent=1))
    return 2 if floor else 0


def _sections(text):
    secs = [s for s in re.split(r"(?m)^(?=#{2,4} )", text) if s.strip()]
    return secs if len(secs) > 1 else [b for b in re.split(r"\n\s*\n", text) if b.strip()]


def packet(n, lines, prev, issues, p, bible, cfg):
    names = {m.group(1).strip() for _, m in speech_lines(lines)}
    out = [f"# 第{n}集 审查任务包", "",
           "你只审这一集。按下面「怎么审」逐项看，把问题写成审查卡 JSON。整季的曲线、塌方区留给整季层，这里不评。", "",
           f"- **剧本类型**：{p['label']}。字数、场次、地点、单句长度这些数量项脚本已经查过（见「脚本已查出」），不要重复报。",
           f"- **写到**：`{os.path.join(cfg['dir'], f'card-{n:03d}.json')}`",
           f"- **写完跑**：`python3 {ME} check {cfg['dir']} --ep {n}`，没过就照提示改卡片。", ""]
    out += ["## 上一集结尾", "", prev or "（这是第一集，或上一集不在这份稿子里）", ""]
    if bible:
        secs = [s for s in _sections(bible) if any(x in s for x in names)]
        if secs:
            out += ["## 圣经：本集开口的人", "", "\n\n".join(secs)[:3000], ""]
    out += ["## 脚本已查出（不用重复报，确认是误报的可以在卡片 notes 里说明）", ""]
    out += [f"- [{LEVEL_TEXT[i['level']]}·{i['dim']}] {i['where']} {i['problem']}" + (f"：{i['quote']}" if i["quote"] else "")
            for i in issues] or ["- 无"]
    out += ["", "## 正文", "", "\n".join(lines).strip(), "", "---", "", read(os.path.join(SKILL_DIR, "references", "card-rubric.md"))]
    return "\n".join(out) + "\n"


def tail_of(lines, k=600):
    """上一集最后一场，接戏用。"""
    idx = [i for i, l in enumerate(lines) if SCENE_HEAD.match(l)]
    body = "\n".join(lines[idx[-1]:] if idx else lines).strip()
    return body[-k:]


def write_packet(cfg, n, by_ep, issues, bible):
    """上一集审过了就用它审查卡里的结尾状态（短、已经提炼过），没审过就附上一集最后一场原文。"""
    d = cfg["dir"]
    prev = None
    prev_card = os.path.join(d, f"card-{n - 1:03d}.json")
    if os.path.exists(prev_card):
        try:
            prev = "上一集审查卡记的结尾状态：" + load(prev_card).get("exit", "")
        except ValueError:
            prev = None
    if not prev and n - 1 in by_ep:
        prev = "上一集最后一场原文：\n\n" + tail_of(by_ep[n - 1])
    with open(os.path.join(d, f"packet-{n:03d}.md"), "w", encoding="utf-8") as f:
        f.write(packet(n, by_ep[n], prev, [i for i in issues if i["ep"] == n], cfg["profile"], bible, cfg))


def cmd_init(args):
    p = resolve_profile(args)
    text = read(args.script)
    eps, issues, stats = lint_script(text, p)
    if not eps:
        print(json.dumps({"error": "没找到「第N集」标题，按集切不开。docx 先用 extract_docx.py 转成文本"}, ensure_ascii=False))
        return 1
    d = os.path.abspath(args.out)
    os.makedirs(d, exist_ok=True)
    cfg = {"script": os.path.abspath(args.script), "profile": p, "dir": d,
           "bible": os.path.abspath(args.bible) if args.bible else None, "episodes": sorted(stats)}
    with open(os.path.join(d, "config.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=1)
    with open(os.path.join(d, "lint.json"), "w", encoding="utf-8") as f:
        json.dump({"issues": issues, "stats": stats}, f, ensure_ascii=False, indent=1)
    bible = read(args.bible) if args.bible else ""
    by_ep = {}
    for n, _, lines in eps:
        by_ep.setdefault(n, lines)
    for n in sorted(by_ep):
        write_packet(cfg, n, by_ep, issues, bible)
    floor = sum(1 for i in issues if i["level"] == "floor")
    print(json.dumps({"dir": d, "episodes": len(by_ep), "lintFloor": floor, "lintCeiling": len(issues) - floor,
                      "next": f"python3 {ME} next --dir {d}"}, ensure_ascii=False))
    return 0


def validate_card(path, n, ep_text, scene_names):
    """审查卡的机械校验。最要紧的一条：每条问题的引文必须一字不差出现在这一集里，编不出来。"""
    errs = []
    try:
        c = load(path)
    except ValueError as e:
        return [f"不是合法 JSON：{e}"], None
    if c.get("ep") != n:
        errs.append(f"ep 应该是 {n}")
    if c.get("verdict") not in VERDICTS:
        errs.append("verdict 只能是 pass / fix / rewrite")
    for k in ("hook", "emotion", "voice"):
        g = (c.get(k) or {}).get("grade")
        if g not in GRADES:
            errs.append(f"{k}.grade 只能是 A / B / C")
        if not (c.get(k) or {}).get("note"):
            errs.append(f"{k}.note 要写一句理由")
    if not (c.get("exit") or "").strip():
        errs.append("exit 要写本集结尾状态一句话，下一集接戏用")
    issues = c.get("issues")
    if not isinstance(issues, list):
        return errs + ["issues 要是数组（没问题就写 []）"], c
    body = norm(ep_text)
    for k, it in enumerate(issues, 1):
        tag = f"issues[{k}]"
        if it.get("level") not in LEVEL_TEXT:
            errs.append(f"{tag}.level 只能是 floor（下限·必改）或 ceiling（上限·可提）")
        if it.get("dim") not in DIMS:
            errs.append(f"{tag}.dim 只能是：{'、'.join(DIMS)}")
        w = re.sub(r"\s", "", it.get("where", ""))
        w = "场" + w if re.fullmatch(r"\d+[-－—]\d+", w) else w  # 「1-1」和「场1-1」都认
        if w != "全集" and w not in scene_names:
            errs.append(f"{tag}.where「{w}」不是本集的场号（可选：{'、'.join(scene_names) or '无'}，或写「全集」）")
        q = norm(it.get("quote", ""))
        if w != "全集" and len(q) < 4:
            errs.append(f"{tag}.quote 要从正文原样抄一句（至少 4 个字），定位用")
        elif q and q not in body:
            errs.append(f"{tag}.quote 在第{n}集正文里找不到：「{it.get('quote', '')[:30]}」。原样抄，不要改写")
        fix = it.get("fix", "")
        if han(fix) < 8:
            errs.append(f"{tag}.fix 太短，要写出改后的台词、动作或具体做法")
        elif VAGUE.search(fix) and han(fix) < 20:
            errs.append(f"{tag}.fix「{fix[:20]}」太泛，写出改成什么，不要只说加强、提升")
        if not it.get("problem"):
            errs.append(f"{tag}.problem 要写问题是什么")
    if any(it.get("level") == "floor" for it in issues) and c.get("verdict") == "pass":
        errs.append("有下限问题时 verdict 不能是 pass")
    return errs, c


def episode_map(cfg):
    eps = {}
    for n, _, lines in pick_bodies(split_episodes(read(cfg["script"]))):
        eps.setdefault(n, lines)
    return eps


def card_status(cfg, eps, n):
    path = os.path.join(cfg["dir"], f"card-{n:03d}.json")
    if not os.path.exists(path):
        return "missing", [], None
    lines = eps[n]
    names = [f"场{m.group(1)}-{m.group(2)}" for l in lines for m in [SCENE_HEAD.match(l)] if m]
    errs, card = validate_card(path, n, "\n".join(lines), names)
    return ("ok" if not errs else "bad"), errs, card


def cmd_check(args):
    cfg = load(os.path.join(args.dir, "config.json"))
    eps = episode_map(cfg)
    todo = [args.ep] if args.ep else sorted(eps)
    res, bad = {}, False
    for n in todo:
        st, errs, _ = card_status(cfg, eps, n)
        if args.ep or st != "missing":
            res[n] = {"status": st, "fix": errs[:20]}
            bad |= st != "ok"
    print(json.dumps({"passed": not bad, "cards": res}, ensure_ascii=False, indent=1))
    return 2 if bad else 0


def cmd_next(args):
    d = args.dir
    if not os.path.exists(os.path.join(d, "config.json")):
        print(json.dumps({"step": "1 准备", "todo": "还没初始化。docx 先用 extract_docx.py 转成文本，再跑 init。剧本类型：original / clone / continuation / polish。",
                          "cmd": f"python3 {ME} init <剧本.md> --profile <类型> --out {d} [--bible bible.md] [--min-total N]"},
                         ensure_ascii=False, indent=1))
        return 0
    cfg = load(os.path.join(d, "config.json"))
    eps = episode_map(cfg)
    pending, broken = [], []
    for n in sorted(eps):
        st, errs, _ = card_status(cfg, eps, n)
        if st == "bad":
            broken.append((n, errs))
        elif st == "missing":
            pending.append(n)
    if broken:
        n, errs = broken[0]
        print(json.dumps({"step": "2 逐集卡", "todo": f"第{n}集的审查卡没过校验，照下面改 card-{n:03d}.json，再跑 next。",
                          "fix": errs[:20]}, ensure_ascii=False, indent=1))
        return 0
    if pending:
        batch = pending[:args.parallel]
        issues = load(os.path.join(d, "lint.json"))["issues"]
        bible = read(cfg["bible"]) if cfg.get("bible") else ""
        for n in batch:  # 上一集刚审完的话，把它的结尾状态换进任务包
            write_packet(cfg, n, eps, issues, bible)
        print(json.dumps({"step": "2 逐集卡",
                          "todo": f"还有 {len(pending)} 集没审。下面这几集各读一份任务包、写一张卡，一集一个上下文；"
                                  "可以并行给几个子代理，每个只负责一集。中档模型就够，每集最多两轮：写卡、过 check。",
                          "episodes": [{"ep": n, "packet": os.path.join(d, f"packet-{n:03d}.md")} for n in batch]},
                         ensure_ascii=False, indent=1))
        return 0
    print(json.dumps({"step": "3 报告", "todo": "全部审完。合成报告，把报告文件交给用户。",
                      "cmd": f"python3 {ME} report {d} --out {os.path.join(d, '审查报告.md')}"}, ensure_ascii=False, indent=1))
    return 0


def cmd_report(args):
    d = args.dir
    cfg = load(os.path.join(d, "config.json"))
    eps = episode_map(cfg)
    lint = load(os.path.join(d, "lint.json"))
    stats = {int(k): v for k, v in lint["stats"].items()}
    issues = list(lint["issues"])
    cards, unreviewed, invalid = {}, [], []
    for n in sorted(eps):
        st, errs, card = card_status(cfg, eps, n)
        if st == "ok":
            cards[n] = card
            issues += [dict(i, ep=n, source="card") for i in card["issues"]]
        elif st == "bad":
            invalid.append(n)
        else:
            unreviewed.append(n)
    floor = [i for i in issues if i["level"] == "floor"]
    ceil = [i for i in issues if i["level"] == "ceiling"]
    p = cfg["profile"]
    from collections import Counter
    verdicts = Counter(c["verdict"] for c in cards.values())
    dims = Counter(i["dim"] for i in floor)
    out = [f"# 剧本审查报告", "",
           f"- 剧本：`{cfg['script']}`（剧本类型：{p['label']}）",
           f"- 共 {len(eps)} 集，逐集审完 {len(cards)} 集" + (f"，没审 {len(unreviewed)} 集（{_ranges(unreviewed)}）" if unreviewed else "")
           + (f"，审查卡没过校验 {len(invalid)} 集（{_ranges(invalid)}），这些集的模型意见没算进来" if invalid else ""),
           f"- **下限·必改 {len(floor)} 条**，上限·可提 {len(ceil)} 条。下限问题按维度：" + ("、".join(f"{k} {v}" for k, v in dims.most_common()) or "无"),
           f"- 逐集裁决：可过 {verdicts.get('pass', 0)} 集，要改 {verdicts.get('fix', 0)} 集，要重写 {verdicts.get('rewrite', 0)} 集",
           "- 整季层（留存曲线、在第几集塌、兑现重复、总弹簧）是第二期，这份报告还不含。", "",
           "## 逐集一览", "",
           "| 集 | 全文字数 | 场 | 地点 | 钩子 | 情绪 | 口吻 | 下限 | 上限 | 裁决 |", "|---|---|---|---|---|---|---|---|---|---|"]
    vt = {"pass": "可过", "fix": "要改", "rewrite": "要重写"}
    for n in sorted(eps):
        s, c = stats.get(n, {}), cards.get(n)
        fl = sum(1 for i in floor if i["ep"] == n)
        ce = sum(1 for i in ceil if i["ep"] == n)
        g = lambda k: (c or {}).get(k, {}).get("grade", "—")
        out.append(f"| {n} | {s.get('totalHan', '—')} | {s.get('scenes', '—')} | {s.get('locations', '—')} | {g('hook')} | {g('emotion')} | "
                   f"{g('voice')} | {fl} | {ce} | {vt.get((c or {}).get('verdict'), '没审')} |")
    for title, rows in (("下限·必改", floor), ("上限·可提", ceil)):
        out += ["", f"## {title}", ""]
        if not rows:
            out.append("无")
        for n in sorted({i["ep"] for i in rows}):
            out += [f"### 第{n}集", ""]
            for i in [x for x in rows if x["ep"] == n]:
                src = "脚本" if i.get("source") == "lint" else "审查卡"
                out.append(f"- **[{i['dim']}] {i['where']}**（{src}）{i['problem']}" + (f"\n  - 原文：{i['quote']}" if i.get("quote") else "")
                           + f"\n  - 改法：{i['fix']}")
            out.append("")
    best = [(n, c["best"]) for n, c in cards.items() if c.get("best")]
    if best:
        out += ["## 每集最强的一处（保住它）", ""] + [f"- 第{n}集：{b}" for n, b in best]
    text = "\n".join(out) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
    print(json.dumps({"out": args.out, "episodes": len(eps), "reviewed": len(cards), "floor": len(floor), "ceiling": len(ceil),
                      "unreviewed": unreviewed, "invalidCards": invalid}, ensure_ascii=False))
    return 0


def _ranges(ns):
    out, start = [], None
    for k, n in enumerate(ns):
        if start is None:
            start = n
        if k + 1 == len(ns) or ns[k + 1] != n + 1:
            out.append(f"{start}" if start == n else f"{start}-{n}")
            start = None
    return "、".join(out)


def main():
    ap = argparse.ArgumentParser(description="drama-review：AI 剧本审查")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("next", help="看审查进度，只给下一步")
    p.add_argument("--dir", default="review")
    p.add_argument("--parallel", type=int, default=1, help="一次给几集（有子代理时可以并行）")
    for name in ("lint", "init"):
        p = sub.add_parser(name, help="脚本层检查" if name == "lint" else "脚本层 + 每集审查任务包")
        p.add_argument("script")
        p.add_argument("--profile", required=True, help="original / clone / continuation / polish")
        p.add_argument("--min-total", type=int)
        p.add_argument("--min-scenes", type=int)
        p.add_argument("--max-locations", type=int)
        p.add_argument("--max-line-han", type=int)
        if name == "lint":
            p.add_argument("--full", action="store_true")
        else:
            p.add_argument("--out", required=True)
            p.add_argument("--bible")
    p = sub.add_parser("check", help="校验审查卡")
    p.add_argument("dir")
    p.add_argument("--ep", type=int)
    p = sub.add_parser("report", help="合成审查报告")
    p.add_argument("dir")
    p.add_argument("--out")
    args = ap.parse_args()
    try:
        return {"lint": cmd_lint, "init": cmd_init, "check": cmd_check, "next": cmd_next, "report": cmd_report}[args.cmd](args)
    except (OSError, ValueError, KeyError) as e:
        print(json.dumps({"error": str(e)}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    sys.exit(main())
