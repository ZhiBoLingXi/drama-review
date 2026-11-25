# drama-review · AI 剧本审查

审查 AI 写的竖屏短剧 / 漫剧剧本：整体和每一集各有哪些问题、每条怎么改，分「下限·必改」和「上限·可提」两档。当前版本 **0.2.0**（第二期）。

- **脚本层**：能数出来的硬伤，零模型成本。
- **逐集卡**：一集一个上下文，模型判钩子、情绪、口吻、接戏这些戏的问题；脚本校验每条意见的引文真在剧本里，编不出来。
- **整季层**：只读逐集卡，脚本算留存曲线、塌方区、爽点复读、悬念线账；模型写一张整季卡说为什么塌、怎么改。
- **报告**：整季结论、逐集一览、下限清单、上限清单。
- **剧本类型**：原创、高仿、续写、润色各一套阈值（`profiles.json`）。

## 用法

```bash
python3 scripts/review.py next --dir review/          # 每一步先跑它
python3 scripts/review.py init 剧本.md --profile clone --min-total 800 --out review/ --bible bible.md
python3 scripts/review.py check review/ --ep 3
python3 scripts/review.py check review/ --season        # 整季卡
python3 scripts/review.py report review/ --out review/审查报告.md
python3 scripts/review.py lint 剧本.md --profile original   # 只跑脚本层
```

只用 Python 3 标准库；读 docx 需要 python-docx。

## 路线
- 第一期：脚本层、逐集卡、剧本类型、报告。
- 第二期（本版）：整季层。只读逐集卡，脚本算留存曲线、塌方区、疲软区、爽点复读、悬念线账、总弹簧前的大揭晓，模型写整季卡说原因和改法。
- 第三期：校准。拿编剧和客户的真实审稿意见当标准答案，量模型提的问题有几成对得上。

规则大多来自 [drama-clone](../drama-clone) 的 `clone_check.py`，docx 抽取来自 DramaReview。和 drama-clone 的公共检查代码目前是复制的，后面再统一。
