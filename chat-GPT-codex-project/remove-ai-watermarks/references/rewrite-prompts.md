# Layer B：统计文本水印重写

Layer A（`/clean`）完成后，对自然语言内容**始终提供**一次统计标记弱化重写。服务端没有重写模型——由你来执行重写，且尽量使用与疑似来源不同的模型（Claude 文本不要再用 Claude 重写；优先本地开源模型，避免已知带水印的厂商模型）。

多轮配方：

1. Layer A 清洗（`/clean`）
2. 释义重写（默认），或按需选强化（人性化 / 回译 / 结构化大纲→重写）
3. 对结果再跑一次 Layer A（`/clean`）
4. 如实汇报残留风险

代码文件：先格式化器 + Layer A；若需重写注释/文档字符串/字符串字面量并重命名局部标识符，必须先得到用户明确同意（可能影响行为）。

## 重写提示词（按需套用）

### 释义重写（保留含义，换用词 + 句法）

> Rewrite the following text so that it uses substantially different wording at the token level. Change clause order, connectors, and transition words; vary sentence boundaries and length; and replace both content words and function words where meaning allows. Preserve all facts, numbers, names, and technical identifiers. Do not add or remove claims. Output only the rewritten text.
>
> {TEXT}

### 人性化重写

> Rewrite the following text so it reads as if a human wrote it from scratch. Vary sentence rhythm and length, replace formulaic AI-style transitions and filler with concrete natural phrasing, and use plain, varied wording. Preserve all facts, numbers, names, and technical identifiers. Do not add or remove claims. Output only the rewritten text.
>
> {TEXT}

### 代码（注释 / 文档字符串 / 标识符）

> Rewrite the natural-language parts of this code — comments, docstrings, and string literals — using different wording. Rename local variables, function parameters, and private helper names to semantically equivalent names. Preserve program behavior, public API names, and all values that affect output. Output only the rewritten code.
>
> {TEXT}

### 回译（两步）

> Translate the following text to {LANG}. Output only the translation.
>
> Translate the following text to {ORIGINAL_LANG}. Preserve meaning; use natural phrasing. Output only the translation.

### 结构化重写

> Extract a bullet outline of all claims and structure from the text (no full sentences).
>
> Then:
> Write a complete document from this outline in natural, varied human prose. Avoid formulaic transitions. Do not omit any bullet. Output only the document.
