---
name: drama-review
description: 竖屏短剧 / 漫剧 AI 剧本审查：脚本先查确定性硬伤（体量、占位省略、△比喻腔、镜头外貌、单句长度、每场说话人数、出场走位、作者口吻穿帮、跨集套路反应、文学腔），再由模型逐集写审查卡（钩子、情绪兑现、冲突动机、人物口吻、接戏、节奏、可拍、合规），脚本校验每条意见的引文真在剧本里，最后合成整体加逐集的问题清单和修改建议，分「下限·必改」和「上限·可提」两档。按剧本类型（原创、高仿、续写、润色）取阈值。 USE WHEN 审查剧本、评审剧本、审稿、剧本质量、AI 剧本问题、每一集有什么问题、给修改建议、剧本过不过关、查 AI 味、下限问题、怎么提高上限、drama-clone 写完的剧本审一遍。 NOT FOR 写剧本或改稿（用 drama-clone、DramaContinuation、DramaPolish）、只出选题。
metadata:
  display_name: AI 剧本审查
  display_name_en: AI Script Review
  description_zh: 审查 AI 写的短剧剧本，逐集找出钩子、情绪、口吻、接戏等问题，每条定位到场次和原句并给出改法，分必改和可提两档。
  description_en: Reviews AI-written short drama scripts episode by episode, locating each problem in hooks, payoff, voice and continuity to the scene and line, with a concrete fix, split into must-fix and could-improve.
  examples_zh:
  - 帮我审一下这部剧本，每一集有什么问题、怎么改
  - 这是 drama-clone 写的 60 集高仿剧本，按高仿标准审一遍
  - 查查这个剧本的 AI 味和接戏问题，出一份审查报告
  examples_en:
  - Review this script and tell me what is wrong in each episode and how to fix it
  - Review this 60-episode clone script from drama-clone against clone standards
  - Check this script for AI-sounding writing and continuity breaks, and write a review report
  version: 0.1.0
  author: MaLiAI
---

# AI 剧本审查

审一部 AI 写的剧本：整体有哪些问题、每一集有哪些问题、每个问题怎么改。三层：

1. **脚本层**（`scripts/scriptlib.py`，零模型成本）：能数出来的硬伤，规则见 `references/lint-rules.md`。
2. **逐集卡**（一集一个上下文，中档模型即可）：脚本判不了的戏，标准见 `references/card-rubric.md`。
3. **报告**：脚本把两层合起来，出总览、逐集一览、下限清单、上限清单。

整季层（留存曲线、在第几集塌、兑现方式重复、总弹簧提前泄）是第二期，还没做。现在的报告会写明这一点。

## 怎么执行（每一步先跑 next）

```bash
python3 <技能目录>/scripts/review.py next --dir <审查目录> [--parallel 4]
```

它看审查目录里有什么，告诉你下一步做什么、跑哪条命令。

### 1 · 准备
- docx 先转文本：`python3 <技能目录>/scripts/extract_docx.py 剧本.docx > 剧本.md`（需要 python-docx）。
- **定剧本类型**，问用户一句，别猜：
  - `original` 原创：每集全文 ≥1200 字，单集地点 ≤3。
  - `clone` 高仿（drama-clone 写的）：字数用户定，用 `--min-total` 传；每场 ≤4 人开口、单句 ≤20 字、不写镜头和外貌。
  - `continuation` 续写、`polish` 润色。阈值和理由都在 `profiles.json`。
  - 用户或客户给了具体要求（字数、场数），用 `--min-total`、`--min-scenes`、`--max-locations`、`--max-line-han` 覆盖。竖屏快切项目要查场数就加 `--min-scenes 10`。
- 有设定圣经就用 `--bible` 带上，任务包会按本集开口的人摘人物小节，审口吻时有依据。

```bash
python3 <技能目录>/scripts/review.py init 剧本.md --profile clone --min-total 800 --out review/ [--bible bible.md]
```

它跑完脚本层，给每集写一份审查任务包 `review/packet-NNN.md`：上一集结尾、圣经摘录、脚本已查出的问题、本集正文、审查标准、卡片格式和校验命令，全在一个文件里。

### 2 · 逐集卡
- **一集一个上下文，只读这一集的任务包，读一次就写卡。** 每多读一个文件就多一轮，每轮都要重读整个上下文。
- 写 `review/card-NNN.json`，跑 `review.py check review/ --ep N`，没过就照提示改。`check` 会拦：引文在正文里找不到、场号不存在、改法太短或只说「加强」「提升」、有下限问题却判 `pass`。
- 有子代理就用 `next --parallel 4` 一次拿几集，每个子代理只负责一集，返回一行：第几集、过没过 check。主线程不读卡片内容，最后看报告。
- 中档模型就够。按顺序审时，`next` 会把上一集卡片里的「结尾状态」换进下一集的任务包，接戏核对更准；并行审时用上一集最后一场原文。

### 3 · 报告
```bash
python3 <技能目录>/scripts/review.py report review/ --out review/审查报告.md
```
把报告交给用户。汇报时直接用报告第一段的数（几集、下限几条、上限几条、按维度分布），不要转述成「整体不错」。

## 红线
- 卡片里每条意见都要指到场、抄原句、写出改成什么。指不出来的意见不写。
- 脚本已经查出的数量项不在卡片里重复报。脚本误报的，在卡片 `notes` 里说明，不改脚本阈值去凑。
- 没审的集、卡片没过校验的集，报告里会单独列出，不要说成「全部审完」。
- 审查不改剧本。要改稿交给写作技能（drama-clone、DramaPolish 等），把报告里的条目当改稿清单。

## 资源
- `scripts/review.py`：`next`、`lint`、`init`、`check`、`report`
- `scripts/scriptlib.py`：解析和确定性检查（规则大多来自 drama-clone 的 `clone_check.py`）
- `scripts/extract_docx.py`：docx 转文本（来自 DramaReview）
- `profiles.json`：四种剧本类型的阈值和理由
- `references/card-rubric.md`：逐集卡的审查标准和格式（会附进每份任务包）
- `references/lint-rules.md`：脚本层每条规则查什么、判哪一档
