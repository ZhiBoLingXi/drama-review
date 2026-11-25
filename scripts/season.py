"""整季层：只读逐集审查卡和脚本统计，不读正文。

脚本先算能算的（留存曲线、塌方区、兑现重复、悬念线账、大揭晓位置），写成一页整季摘要；
模型读这一页写整季卡，判断为什么塌、该怎么改；脚本再校验整季卡。
"""
import glob
import json
import os
import re
from collections import Counter

GRADE = {"A": 3, "B": 2, "C": 1}
PAYOFFS = ["即时打脸", "倒计时引信", "信息差反讽", "民心审判", "因果回旋镖", "降维破局", "数字对称报应", "情感兑现", "其他", "无"]
REVEAL_LEVELS = {"major", "minor"}
THREAD_ID = re.compile(r"^T(\d+)-(\d+)$")
COLLAPSE_MAX = 3     # 钩子+情绪 ≤3（一个 B 一个 C，或两个 C）连着 2 集以上 = 塌方区
SAG_MAX, SAG_RUN = 4, 4  # 钩子+情绪 ≤4 且没有 A，连着 4 集以上 = 疲软区
REPEAT_RUN = 3        # 同一种爽点连着 3 集
DOMINANT = 0.4        # 一种爽点占已审集数的 40% 以上（至少 10 集时才判）
END_WINDOW = 5        # 最后 5 集还没收的线，算结局没收


def load_cards(d, eps=None):
    """{集号: 卡片}，只要能解析的；校验由 review.py 负责。"""
    out = {}
    for p in sorted(glob.glob(os.path.join(d, "card-*.json"))):
        try:
            c = json.load(open(p, encoding="utf-8"))
        except ValueError:
            continue
        if isinstance(c.get("ep"), int) and (eps is None or c["ep"] in eps):
            out[c["ep"]] = c
    return out


def thread_ledger(cards):
    """所有悬念线：{id: {"ep": 开的集, "what": 内容, "closed": 收的集或 None}}，外加引用了不存在的线的收线记录。"""
    threads, bad = {}, []
    for n in sorted(cards):
        for k, what in enumerate((cards[n].get("threads") or {}).get("opened") or [], 1):
            threads[f"T{n}-{k}"] = {"ep": n, "what": what, "closed": None}
    for n in sorted(cards):
        for tid in (cards[n].get("threads") or {}).get("closed") or []:
            t = threads.get(tid)
            if t is None or t["ep"] >= n:
                bad.append({"ep": n, "id": tid})
            elif t["closed"] is None:
                t["closed"] = n
    return threads, bad


def open_threads_before(d, n):
    """第 n 集之前开了、还没收的线，任务包里列出来，审查卡收线时照 id 写。"""
    cards = {k: v for k, v in load_cards(d).items() if k < n}
    threads, _ = thread_ledger(cards)
    return [(tid, t) for tid, t in threads.items() if t["closed"] is None]


def _runs(eps, bad):
    """连续集号里满足 bad 的最长段：[(起, 止)]。集号不连续（中间没审）就断开。"""
    out, start, prev = [], None, None
    for n in eps:
        if bad(n) and (start is None or n == prev + 1):
            start = n if start is None else start
        elif bad(n):
            out.append((start, prev))
            start = n
        else:
            if start is not None:
                out.append((start, prev))
            start = None
        prev = n
    if start is not None:
        out.append((start, prev))
    return out


def compute(cards, stats, all_eps, spring_ep=None):
    eps = sorted(cards)
    score = {n: GRADE.get(cards[n]["hook"]["grade"], 0) + GRADE.get(cards[n]["emotion"]["grade"], 0) for n in eps}
    has_a = {n: "A" in (cards[n]["hook"]["grade"], cards[n]["emotion"]["grade"]) for n in eps}
    collapse = [r for r in _runs(eps, lambda n: score[n] <= COLLAPSE_MAX) if r[1] > r[0]]
    sag = [r for r in _runs(eps, lambda n: score[n] <= SAG_MAX and not has_a[n]) if r[1] - r[0] + 1 >= SAG_RUN]
    opening = [n for n in eps if n <= 3 and cards[n]["hook"]["grade"] == "C"]

    pay = {n: cards[n].get("payoff") for n in eps}
    repeats = []
    for p in set(pay.values()) - {None, "无", "其他"}:
        for a, b in _runs(eps, lambda n: pay[n] == p):
            if b - a + 1 >= REPEAT_RUN:
                repeats.append({"payoff": p, "from": a, "to": b})
    dist = Counter(v for v in pay.values() if v)
    dominant = [{"payoff": k, "count": v, "share": round(v / len(eps), 2)}
                for k, v in dist.items() if len(eps) >= 10 and k not in ("无", "其他") and v / len(eps) > DOMINANT]

    threads, bad_refs = thread_ledger(cards)
    last = max(all_eps) if all_eps else 0
    unpaid = [{"id": k, **v} for k, v in threads.items() if v["closed"] is None]
    unpaid_end = [t for t in unpaid if last - max(eps or [0]) < END_WINDOW]  # 审到了结尾附近才判「结局没收」

    majors = [{"ep": n, "what": r["what"]} for n in eps for r in cards[n].get("reveals") or [] if r.get("level") == "major"]
    early = [m for m in majors if spring_ep and m["ep"] < spring_ep]

    return {
        "reviewed": eps, "missing": [n for n in all_eps if n not in cards],
        "curve": [{"ep": n, "hook": cards[n]["hook"]["grade"], "emotion": cards[n]["emotion"]["grade"],
                   "voice": cards[n]["voice"]["grade"], "score": score[n], "payoff": pay[n],
                   "totalHan": (stats.get(n) or {}).get("totalHan")} for n in eps],
        "collapse": [{"from": a, "to": b} for a, b in collapse],
        "sag": [{"from": a, "to": b} for a, b in sag],
        "weakOpening": opening,
        "payoffDist": dict(dist.most_common()), "payoffRepeats": sorted(repeats, key=lambda x: x["from"]),
        "payoffDominant": dominant,
        "threads": {"opened": len(threads), "closed": sum(1 for t in threads.values() if t["closed"]),
                    "unpaid": unpaid, "unpaidAtEnd": bool(unpaid_end), "badRefs": bad_refs},
        "majorReveals": majors, "springEp": spring_ep, "revealsBeforeSpring": early,
    }


def spark(curve):
    """留存曲线一行字：▁▃▅▇ 对应 钩子+情绪 2..6。"""
    bars = "▁▂▃▅▆▇"
    return "".join(bars[min(max(c["score"] - 1, 0), 5)] for c in curve)


def digest(s, cards, dir_, me, rubric):
    """整季摘要：模型写整季卡只读这一份。"""
    L = [f"# 整季审查任务包", "",
         "你只读这一份，不读正文。下面是脚本按逐集审查卡算好的整季数据，和每集一行的摘要。"
         "你要判断：观众会在第几集划走、为什么；兑现方式是不是在复读；悬念线有没有收；总弹簧落得对不对。把结论写成整季卡。", "",
         f"- **写到**：`{os.path.join(dir_, 'season-card.json')}`",
         f"- **写完跑**：`python3 {me} check {dir_} --season`", "",
         "## 脚本算好的", "",
         f"- 已审 {len(s['reviewed'])} 集" + (f"，没审 {len(s['missing'])} 集：{s['missing'][:20]}{'…' if len(s['missing']) > 20 else ''}" if s["missing"] else ""),
         f"- 留存曲线（钩子+情绪，▁ 最弱 ▇ 最强，按集号顺序）：`{spark(s['curve'])}`",
         f"- 塌方区（连续 2 集以上 钩子+情绪 ≤3）：{_rng(s['collapse']) or '无'}",
         f"- 疲软区（连续 4 集以上 钩子+情绪 ≤4 且没有一项 A）：{_rng(s['sag']) or '无'}",
         f"- 开篇钩子 C 档：{s['weakOpening'] or '无'}",
         f"- 爽点类型分布：{'、'.join(f'{k} {v}' for k, v in s['payoffDist'].items()) or '无'}",
         "- 同一种爽点连用 3 集以上：" + ("；".join("%s 第%d-%d集" % (r["payoff"], r["from"], r["to"]) for r in s["payoffRepeats"]) or "无"),
         "- 一种爽点占四成以上：" + ("；".join("%s %d 集" % (d["payoff"], d["count"]) for d in s["payoffDominant"]) or "无"),
         f"- 悬念线：开 {s['threads']['opened']} 条，收 {s['threads']['closed']} 条，没收 {len(s['threads']['unpaid'])} 条"
         + ("（已经审到结尾，这些就是结局没收的线）" if s["threads"]["unpaidAtEnd"] else ""),
         "- 大揭晓（major）：" + ("；".join("第%d集 %s" % (m["ep"], m["what"]) for m in s["majorReveals"]) or "无")
         + (f"；总弹簧计划落在第 {s['springEp']} 集，之前的大揭晓要核对是不是提前泄了" if s["springEp"] else ""), ""]
    if s["threads"]["unpaid"]:
        L += ["## 没收的线", ""] + [f"- {t['id']}（第{t['ep']}集开）{t['what']}" for t in s["threads"]["unpaid"][:40]] + [""]
    L += ["## 逐集一行", "", "| 集 | 钩子 | 情绪 | 口吻 | 爽点 | 裁决 | 结尾状态 | 最要紧的问题 |", "|---|---|---|---|---|---|---|---|"]
    for c in s["curve"]:
        card = cards[c["ep"]]
        top = next((i for i in card["issues"] if i["level"] == "floor"), card["issues"][0] if card["issues"] else None)
        L.append(f"| {c['ep']} | {c['hook']} | {c['emotion']} | {c['voice']} | {c['payoff'] or ''} | {card['verdict']} | "
                 f"{_cell(card.get('exit', ''))} | {_cell((top['dim'] + '：' + top['problem']) if top else '')} |")
    L += ["", "---", "", rubric]
    return "\n".join(L) + "\n"


def _cell(t, k=40):
    t = re.sub(r"\s+", " ", t).replace("|", "/")
    return t[:k] + ("…" if len(t) > k else "")


def _rng(rs):
    return "、".join(f"第{r['from']}-{r['to']}集" for r in rs)


def validate_season(card, s, han, vague):
    """整季卡的机械校验：引用的集号要真审过，改法要具体，脚本算出的塌方区每一段都要有交代。"""
    errs = []
    reviewed = set(s["reviewed"])
    for k in ("verdict", "summary", "zones", "repetition", "spring", "top"):
        if k not in card:
            errs.append(f"缺 {k}")
    if errs:
        return errs
    if card["verdict"] not in ("投", "改后投", "大改", "不投"):
        errs.append("verdict 只能是：投 / 改后投 / 大改 / 不投")
    if han(card.get("summary", "")) < 20:
        errs.append("summary 至少写 20 个字：这部剧整季能不能打、卡在哪")

    def check_fix(tag, it):
        f = it.get("fix", "")
        if han(f) < 8:
            errs.append(f"{tag}.fix 太短，写出改成什么")
        elif vague.search(f) and han(f) < 20:
            errs.append(f"{tag}.fix「{f[:20]}」太泛，写出改成什么")

    covered = set()
    for i, z in enumerate(card["zones"], 1):
        a, b = z.get("from"), z.get("to")
        if not (isinstance(a, int) and isinstance(b, int) and a <= b and a in reviewed and b in reviewed):
            errs.append(f"zones[{i}] 的 from/to 要是审过的集号，且 from ≤ to")
            continue
        if not z.get("why"):
            errs.append(f"zones[{i}].why 要写为什么在这里塌")
        check_fix(f"zones[{i}]", z)
        covered |= set(range(a, b + 1))
    for r in s["collapse"]:
        if not set(range(r["from"], r["to"] + 1)) & covered:
            errs.append(f"脚本算出第{r['from']}-{r['to']}集是塌方区，zones 里没有交代（同意就写改法，不同意就写一条 why 说明为什么不算塌）")
    for i, it in enumerate(card["repetition"], 1):
        eps = it.get("eps") or []
        if not eps or any(e not in reviewed for e in eps):
            errs.append(f"repetition[{i}].eps 要列审过的集号")
        check_fix(f"repetition[{i}]", it)
    sp = card["spring"]
    if not isinstance(sp, dict) or "ep" not in sp or not sp.get("note"):
        errs.append("spring 要写 {ep: 总弹簧该落在第几集（不知道写 null）, note: 理由, premature: [...]}")
    else:
        for i, it in enumerate(sp.get("premature") or [], 1):
            if it.get("ep") not in reviewed:
                errs.append(f"spring.premature[{i}].ep 要是审过的集号")
            check_fix(f"spring.premature[{i}]", it)
        # 总弹簧计划集之前的大揭晓，每一条都要表态：算提前泄（写进 premature），或者在 note 里说明为什么不算
        named = {it.get("ep") for it in sp.get("premature") or []}
        for m in s.get("revealsBeforeSpring") or []:
            if m["ep"] not in named and f"第{m['ep']}集" not in sp["note"] and f"第 {m['ep']} 集" not in sp["note"]:
                errs.append(f"第{m['ep']}集有大揭晓「{m['what']}」，在总弹簧（第{s['springEp']}集）之前："
                            "算提前泄就写进 spring.premature，不算就在 spring.note 里写明第几集为什么不算")
    if not (1 <= len(card["top"]) <= 5):
        errs.append("top 写 1-5 条整季最该先改的")
    for i, it in enumerate(card["top"], 1):
        if not it.get("what"):
            errs.append(f"top[{i}].what 要写改什么")
        check_fix(f"top[{i}]", it)
    return errs


def report_section(s, card):
    """报告里的整季部分。"""
    L = ["## 整季", ""]
    if card:
        L += [f"**整季裁决：{card['verdict']}**。{card['summary']}", ""]
    L += [f"- 留存曲线（钩子+情绪，按集号）：`{spark(s['curve'])}`",
          f"- 塌方区：{_rng(s['collapse']) or '无'}；疲软区：{_rng(s['sag']) or '无'}；开篇钩子 C 档：{s['weakOpening'] or '无'}",
          f"- 爽点分布：{'、'.join(f'{k} {v}' for k, v in s['payoffDist'].items()) or '无'}",
          f"- 悬念线：开 {s['threads']['opened']} 条，收 {s['threads']['closed']} 条，没收 {len(s['threads']['unpaid'])} 条"
          + ("，已经审到结尾，这些是结局没收的线" if s["threads"]["unpaidAtEnd"] else ""), ""]
    if not card:
        L += ["（整季卡还没写或没过校验，下面只有脚本算出的数据，没有原因和改法。）", ""]
        return L
    if card["top"]:
        L += ["### 整季最该先改的", ""] + [f"{i}. **{t['what']}** 改法：{t['fix']}" for i, t in enumerate(card["top"], 1)] + [""]
    if card["zones"]:
        L += ["### 塌方区和疲软区", ""] + [f"- 第{z['from']}-{z['to']}集：{z['why']} 改法：{z['fix']}" for z in card["zones"]] + [""]
    if card["repetition"]:
        L += ["### 兑现复读", ""] + [f"- 第{'、'.join(map(str, r['eps']))}集：{r.get('what', '')} 改法：{r['fix']}" for r in card["repetition"]] + [""]
    sp = card["spring"]
    L += ["### 总弹簧", "", f"- 应该落在：{('第' + str(sp['ep']) + '集') if sp.get('ep') else '没定'}。{sp['note']}"]
    L += [f"- 第{p['ep']}集提前泄了：{p.get('what', '')} 改法：{p['fix']}" for p in sp.get("premature") or []]
    if s["threads"]["unpaid"]:
        L += ["", "### 没收的线", ""] + [f"- {t['id']}（第{t['ep']}集开）{t['what']}" for t in s["threads"]["unpaid"]]
    return L + [""]
