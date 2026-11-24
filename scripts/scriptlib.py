"""剧本解析和确定性检查。只用标准库，不联网。

规则大多从 drama-clone 的 clone_check.py 抽出来，按「剧本类型」(profile) 取阈值。
每条问题是一个 dict：ep / level(floor 下限·必改 | ceiling 上限·可提) / dim / where / line / quote / problem / fix / source。
"""
import re

CN_NUM = {"零": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
# 集标题后面可以跟集名：「## 第1集  我等的新娘就是你」
EP_HEAD = re.compile(r"^\s*#{0,4}\s*第\s*([0-9一二两三四五六七八九十百零]+)\s*集(?:\s+.*)?$", re.M)
# 场头两种写法都认：「场1-1 地点 日 内」和「1-1  日  内  地点」（加粗已在读入时去掉）
SCENE_HEAD = re.compile(r"^\s*场?\s*(\d+)\s*[-－—]\s*(\d+)(?:\s+(.*?))?\s*$")
# 说话人最多 6 个字、不带标点；「苏念、顾晏」同时开口可以。「顾晏摘下领带，看了她两秒：」这种动作夹在冒号前的不当台词认
SPEECH = re.compile(r"^((?![△场人#<>|*\-—【\[◎※（(〔0-9])[^：（:，。！？\s、]{1,6}(?:、[^：（:，。！？\s、]{1,6})*)(（[^）]*）)?[：:](.*)$")
CAST_LINE = re.compile(r"^人物\s*[:：](.*)")
COMMENT = re.compile(r"^\s*<!--.*-->\s*$", re.M)
HAN = re.compile("[一-鿿]")

DIMS = ["体量", "完整", "格式", "可拍", "接戏", "穿帮", "活人感", "钩子", "情绪", "冲突", "口吻", "节奏", "合规", "其他"]

# △ 里写比喻：导演不知道拍什么（DramaReview 的「△比喻腔」）
METAPHOR = ["像", "如同", "仿佛", "宛如", "等于", "意味着", "象征"]
# 虚写和文学腔：不影响能不能拍，影响像不像人写的
LITERARY = ["似乎", "心理侧写", "难以察觉", "闪过一丝", "掠过一丝", "一丝弧度", "格外", "显得", "眼底", "嘴角勾起",
            "唇角", "意味深长", "空气凝固", "空气中弥漫", "一字一顿"]
# 剧中人说「上一集」「观众」是穿帮；△ 里写「承上一集」是给导演的接戏标注，只有「等了N集」「观众」才算
# 「观众」不进自动检查：观众席、直播间观众都是剧里的东西，交给审查卡判
META_SPEECH = re.compile(r"等了\s*[0-9一二两三四五六七八九十百]+\s*集|这一集|上一集|下一集|本集|第四面墙")
META_ACTION = re.compile(r"等了\s*[0-9一二两三四五六七八九十百]+\s*集|第四面墙")
# 集内的元数据行（「规格：」「备注：」）长得像台词，不算
NOT_SPEAKER = {"规格", "备注", "说明", "注", "时长", "字数", "集名", "钩子", "看点", "梗概", "爽点", "场景", "地点", "时间",
               "道具", "音效", "BGM", "字幕", "镜头", "站位", "人物", "本集", "上接", "下接", "锚点", "位置", "情绪", "节拍"}
PLACEHOLDER = re.compile(
    r"(?:以下|此处|其余|余下|中间|后续|下文|后文|具体|台词|对白|内容|细节|过程|[下后]|^|[（(【\[…。，\s])略(?=[）)】\]。，、…\s]|$)"
    r"|省略(?!号)|从略|(?:同上|同前)(?![一面任来去天年次级])|以此类推|依此类推|若干(?:轮|句|回合|行|场)"
    r"|(?:以下|后续|下同|其余|余下)同理|篇幅(?:所限|原因|有限)|限于篇幅|不再赘述|不一一(?:列出|写出|展开|赘述)"
    r"|未完待续|待补|待写|TODO|TBD|(?:同|参照|参考|照搬|照)第\s*[0-9一二两三四五六七八九十百]+\s*集"
    r"|^\s*(?:…+|\.{3,}|。{3,}|\[\.\.\.\])\s*$", re.M)
CAMERA = ["画左", "画右", "镜头", "特写", "近景", "中景", "远景", "全景", "俯拍", "仰拍", "航拍", "推近", "拉远",
          "摇镜", "机位", "景别", "分镜", "定格", "淡出", "淡入"]
LOOK = ["身穿", "穿着", "一身", "外形", "外貌", "长相", "相貌", "发型", "发髻", "妆容", "旗袍", "西装", "连衣裙",
        "高跟鞋", "白发", "银发", "长发", "短发", "浓眉", "瓜子脸", "面容"]
OFFSCREEN = re.compile(r"画外|电话|话筒|喊声|远处|门外|窗外|录音|广播|信里|OS|os|旁白|内心|视频|语音|对讲|屏幕|手机里|直播|机械音|播报|弹幕")
STOCK = {
    "攥紧": "攥紧|攥着|攥住|握紧拳|捏紧", "冷笑": "冷笑|嗤笑|冷哼", "愣住": "愣住|一愣|愣在|怔住|怔了",
    "叹气": "叹了口气|叹口气|长叹", "脸一沉": "脸一沉|脸色一沉|沉下脸", "脸白": "脸色一白|脸色煞白|脸色发白|脸白了",
    "喉结": "喉结", "咬牙": "咬牙|咬紧牙", "手抖": "手一抖|手抖", "倒吸凉气": "倒吸一口|倒吸了口|凉气",
    "后退": "后退一步|连连后退|退了一步|往后退", "苦笑": "苦笑", "瞪眼": "瞪大|瞪圆", "瘫坐": "瘫坐|瘫软|瘫在",
    "红眼眶": "眼眶一红|眼眶泛红|红了眼眶|眼圈一红", "深吸气": "深吸一口气|深吸了口气", "沉默": "沉默片刻|沉默了几秒|沉默半晌",
    "身子一僵": "身子一僵|浑身一僵|僵在原地|浑身一震", "顿了顿": "顿了顿",
}
STOCK_RE = {k: re.compile(v) for k, v in STOCK.items()}
STOCK_GAP = 10
PER_RULE_CAP = 3  # 同一条规则一集最多列 3 处，其余合成一句“同类还有 N 处”，任务包和报告才不会被一条规则刷屏


def cn_to_int(s):
    if s.isdigit():
        return int(s)
    total, cur = 0, 0
    for ch in s:
        if ch == "百":
            total += (cur or 1) * 100
            cur = 0
        elif ch == "十":
            total += (cur or 1) * 10
            cur = 0
        else:
            cur = CN_NUM[ch]
    return total + cur


def han(s):
    return len(HAN.findall(s))


def norm(s):
    return re.sub(r"\s+", "", s)


def clean(text):
    """去掉 HTML 注释和 Markdown 加粗：「**苏念（低声）：**台词」读成「苏念（低声）：台词」。"""
    return COMMENT.sub("", text).replace("**", "")


def split_episodes(text):
    """[(集号, 标题行号, 正文行列表)]，按出现顺序；重复集号也保留，交给检查报出来。"""
    lines = clean(text).splitlines()
    heads = [(i, cn_to_int(m.group(1))) for i, l in enumerate(lines) for m in [EP_HEAD.match(l)] if m]
    out = []
    for k, (i, n) in enumerate(heads):
        end = heads[k + 1][0] if k + 1 < len(heads) else len(lines)
        out.append((n, i + 1, lines[i + 1:end]))
    return out


def scenes(lines):
    """[(场号, 地点, 日夜, 内外, 起始行下标, 人物集合或 None, 行列表)]。场头之前的行算一个无名场。"""
    out, cur = [], None
    for i, l in enumerate(lines):
        m = SCENE_HEAD.match(l)
        if m:
            rest = (m.group(3) or "").split()
            day = next((t for t in rest if t in ("日", "夜", "晨", "傍晚", "黄昏", "午", "清晨", "深夜")), None)
            io = next((t for t in rest if t in ("内", "外", "内外", "外内", "内/外", "外/内", "内／外", "外／内")), None)
            loc = " ".join(t for t in rest if t not in (day, io)) or "?"
            cur = [f"场{m.group(1)}-{m.group(2)}", loc, day, io, i, None, []]
            out.append(cur)
            continue
        if cur is None:
            cur = ["(场头前)", "?", None, None, i, None, []]
            out.append(cur)
        c = CAST_LINE.match(l.strip())
        if c and cur[5] is None:
            spec = c.group(1).strip()
            if re.fullmatch(r"(同上|同前|同上场)[。．]?", spec):  # 「人物：同上」沿用上一场
                prev = next((s[5] for s in reversed(out[:-1]) if s[5] is not None), None)
                cur[5] = set(prev) if prev is not None else None
            else:
                cur[5] = {x for x in re.split(r"[\s、，,]+", spec) if x}
        cur[6].append((i, l))
    return out


def speak(line):
    """台词行的 match；元数据行（规格：…）、人物行不算。"""
    m = SPEECH.match(line.strip())
    return m if m and m.group(1).strip() not in NOT_SPEAKER else None


def speech_lines(lines):
    return [(i, m) for i, l in enumerate(lines) for m in [speak(l)] if m]


def stock_uses(lines):
    """{组名: 次数}，只看 △ 行和括注。"""
    out = {}
    for l in lines:
        s = l.strip()
        for spot in ([s] if s.startswith("△") else re.findall(r"（[^）]*）", s)):
            for k, rx in STOCK_RE.items():
                c = len(rx.findall(spot))
                if c:
                    out[k] = out.get(k, 0) + c
    return out


def episode_stats(lines):
    sp = speech_lines(lines)
    acts = [l for l in lines if l.strip().startswith("△")]
    sc = [s for s in scenes(lines) if s[0] != "(场头前)"]
    parens = [m.group(2) for _, m in sp if m.group(2)]
    return {"totalHan": han("\n".join(lines)), "speechLines": len(sp),
            "speechHan": sum(han(re.sub(r"（[^）]*）", "", m.group(3))) for _, m in sp),
            "actionLines": len(acts), "scenes": len(sc), "locations": len({s[1] for s in sc}),
            "twoPartParenRatio": round(sum(1 for p in parens if p.count("，") == 1) / len(parens), 2) if len(parens) >= 8 else None}


def _issue(ep, level, dim, where, line, quote, problem, fix):
    return {"ep": ep, "level": level, "dim": dim, "where": where, "line": line, "quote": quote[:60],
            "problem": problem, "fix": fix, "source": "lint"}


def _capped(found):
    """同一规则只留前 PER_RULE_CAP 条，最后一条后面注明还有几处。"""
    if len(found) <= PER_RULE_CAP:
        return found
    keep = found[:PER_RULE_CAP]
    keep[-1] = dict(keep[-1], problem=keep[-1]["problem"] + f"（同类还有 {len(found) - PER_RULE_CAP} 处）")
    return keep


def lint_episode(n, head_line, lines, p):
    """一集的确定性检查。p 是解析好的剧本类型阈值。行号是整份文件里的行号。"""
    issues = []
    L = lambda i: head_line + 1 + i
    st = episode_stats(lines)
    if p.get("min_total") and st["totalHan"] < p["min_total"]:
        issues.append(_issue(n, "floor", "体量", "全集", None, "", f"全文 {st['totalHan']} 字，低于 {p['min_total']}",
                             "多写一轮交锋、一个围观插话或一个道具推进，不靠环境描写和心理旁白凑"))
    if p.get("min_scenes") and st["scenes"] < p["min_scenes"]:
        issues.append(_issue(n, "floor", "体量", "全集", None, "", f"只有 {st['scenes']} 场，低于 {p['min_scenes']}",
                             "把压成大段的强戏（堵现行、签字、审判）拆成几场，一场一个推进"))
    if p.get("max_locations") and st["locations"] > p["max_locations"]:
        issues.append(_issue(n, p.get("locations_level", "floor"), "可拍", "全集", None, "",
                             f"用了 {st['locations']} 个不同地点，多于 {p['max_locations']}，每换一个地点就多一套背景",
                             "把相邻、功能相近的场并到同一个地点，次要地点改成台词交代"))
    if st["speechLines"] == 0:
        issues.append(_issue(n, "floor", "完整", "全集", None, "", "这一集没有一句台词", "补写正文"))
    elif p.get("min_action_ratio") and st["actionLines"] / st["speechLines"] < p["min_action_ratio"]:
        issues.append(_issue(n, "floor", "可拍", "全集", None, "",
                             f"△ 只有 {st['actionLines']} 行，台词 {st['speechLines']} 行，几乎全是对话，导演和生成都没有画面锚点",
                             "在情绪节点补 △：每 4-5 句台词补 1 行动作、表情或道具"))
    if st["twoPartParenRatio"] is not None and st["twoPartParenRatio"] > 0.7:
        issues.append(_issue(n, "ceiling", "活人感", "全集", None, "",
                             f"括注 {st['twoPartParenRatio']:.0%} 是「（情绪，动作）」两段式，读起来像填表",
                             "括注只在演员需要提示时写，长短错开：有的只写动作，有的只写语气，平铺的接话不写"))

    found = {k: [] for k in ("placeholder", "meta", "metaphor", "literary", "camera", "look", "long", "who", "head")}
    for sc in scenes(lines):
        name, loc, day, io, start, cast, body = sc
        if name != "(场头前)" and (not day or not io):
            found["head"].append(_issue(n, "floor", "格式", name, L(start), lines[start].strip(),
                                        "场头缺「日/夜」或「内/外」", "场头写成「场N-M 地点 日/夜 内/外」"))
        speakers, remote = set(), set()
        for i, l in body:
            s = l.strip()
            if not s:
                continue
            # 站位说明里「同上会议室」、人物行「同上」是正常简写
            m = PLACEHOLDER.search(s) if not (s.startswith("◎") or s.startswith("人物")) else None
            if m:
                found["placeholder"].append(_issue(n, "floor", "完整", name, L(i), s,
                                                   f"用「{m.group(0).strip() or '……'}」代替正文", "把这段戏写成台词和 △"))
            sp = speak(s)
            if (sp and META_SPEECH.search(sp.group(3))) or (s.startswith("△") and META_ACTION.search(s)):
                found["meta"].append(_issue(n, "floor", "穿帮", name, L(i), s,
                                            "作者口吻穿帮（剧中人不会按集计时，也不知道有观众）", "删掉，或改成剧中人自己的说法"))
            act = s.startswith("△")
            zone = s if act else "".join(re.findall(r"（[^）]*）", s))
            t = next((x for x in METAPHOR if x in zone), None) if act else None
            if t:
                found["metaphor"].append(_issue(n, "floor", "可拍", name, L(i), s,
                                                f"△ 里写比喻「{t}」，导演不知道拍什么", "换成镜头拍得到的动作、道具或事件"))
            t = next((x for x in LITERARY if x in zone), None)
            if t:
                found["literary"].append(_issue(n, "ceiling", "活人感", name, L(i), s,
                                                f"文学腔「{t}」", "删掉虚写，换成一个具体动作或一句话"))
            if p.get("forbid_camera"):
                t = next((x for x in CAMERA if x in zone), None)
                if t:
                    found["camera"].append(_issue(n, "floor", "格式", name, L(i), s, f"写了镜头「{t}」，这个剧本类型不写镜头",
                                                  "删掉镜头和景别，只写人做了什么"))
            if p.get("forbid_appearance") and (act or s.startswith("人物")):
                t = next((x for x in LOOK if x in s), None)
                if t:
                    found["look"].append(_issue(n, "floor", "格式", name, L(i), s, f"写了外貌「{t}」，形象以资产为准",
                                                "删掉外貌描写"))
            if sp:
                who = sp.group(1).strip()
                speakers.add(who)
                k = han(re.sub(r"（[^）]*）", "", sp.group(3)))
                if p.get("max_line_han") and k > p["max_line_han"]:
                    found["long"].append(_issue(n, "floor", "可拍", name, L(i), s,
                                                f"{who} 一句 {k} 字，超过 {p['max_line_han']}", "拆成两句，中间插一个动作或对方接话"))
                if OFFSCREEN.search(sp.group(2) or ""):
                    remote.add(who)  # 电话那头的人：本场后面的台词不再每句标「电话」，也算不在场
                # 「苏念、顾晏」同时开口逐个查；「导演」对上人物行的「项目导演」也算在场
                if cast is not None and who not in remote \
                        and any(not any(w in c for c in cast) for w in who.split("、") if w):
                    found["who"].append(_issue(n, "floor", "接戏", name, L(i), s,
                                               f"{who} 开口了，但不在本场「人物：」里", "补进人物行，或改成画外音并在括注里标明"))
        if p.get("max_speakers") and len(speakers) > p["max_speakers"]:
            issues.append(_issue(n, "floor", "可拍", name, L(start), "",
                                 f"这一场 {len(speakers)} 个人说话：{'、'.join(sorted(speakers))}", "高潮戏拆成两场，每场不超过 4 个人开口"))
    for k in found:
        issues += _capped(found[k])

    run, prev, start_i = 0, None, 0
    for i, l in enumerate(lines):
        m = speak(l)
        if m:
            who = m.group(1).strip()
            run, start_i = (run + 1, start_i) if who == prev else (1, i)
            prev = who
            if run == 4:
                issues.append(_issue(n, "ceiling", "活人感", "全集", L(start_i), lines[start_i].strip(),
                                     f"{who} 连说 4 行以上，中间没有动作也没人接话", "中间插一个动作，或让对方打断、抢话"))
        elif l.strip():
            prev, run = None, 0
    for k, c in stock_uses(lines).items():
        if c > 1:
            issues.append(_issue(n, "ceiling", "活人感", "全集", None, "", f"「{k}」这类反应一集用了 {c} 次",
                                 "一集只留一次，其余换成这个人自己的动作或一句话"))
    return issues, st


def pick_bodies(eps):
    """整本稿常常前面是集纲、后面是正文，两处都有「第1集」。同一集号出现多次时，没有台词的那份当集纲丢掉；
    都有台词才算真重复，留给检查报。"""
    talk = {}
    for n, _, lines in eps:
        talk.setdefault(n, []).append(len(speech_lines(lines)))
    out = []
    for n, h, lines in eps:
        k = len(speech_lines(lines))
        if k == 0 and max(talk[n]) > 0:
            continue
        out.append((n, h, lines))
    return out


def lint_script(text, p):
    """整份剧本：逐集检查 + 跨集检查（缺集、重复集、10 集内重复的套路反应）。"""
    eps = pick_bodies(split_episodes(text))
    issues, stats, seen, stock_at = [], {}, {}, {}
    for n, head_line, lines in eps:
        if n in seen:
            issues.append(_issue(n, "floor", "完整", "全集", head_line, f"第{n}集", f"第{n}集出现了两次（第 {seen[n]} 行和第 {head_line} 行）",
                                 "删掉重复的一份，或改正集号"))
            continue
        seen[n] = head_line
        got, st = lint_episode(n, head_line, lines, p)
        issues += got
        stats[n] = st
        for k in stock_uses(lines):
            near = [m for m in stock_at.get(k, []) if 0 < n - m < STOCK_GAP]
            if near:
                issues.append(_issue(n, "ceiling", "活人感", "全集", None, "",
                                     f"又用了「{k}」这类反应，第{near[-1]}集刚用过（{STOCK_GAP} 集内不重复）",
                                     "换成这个人自己的反应：手上停住的动作、迁怒旁人、突然不吭声"))
            stock_at.setdefault(k, []).append(n)
    if seen:
        missing = [k for k in range(min(seen), max(seen) + 1) if k not in seen]
        if missing:
            issues.append(_issue(min(missing), "floor", "完整", "全集", None, "", f"缺集：第 {'、'.join(map(str, missing))} 集",
                                 "补齐，或确认这些集本来就不在这份稿子里"))
    return eps, issues, stats
