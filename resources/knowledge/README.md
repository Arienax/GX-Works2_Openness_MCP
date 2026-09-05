# FX3U RAG 知识库

当前知识库使用 schema v3。运行时使用 SQLite/FTS5 与随程序打包、按需加载的
NumPy LSA 向量索引；PDF 解析和向量构建只在离线构建时使用，不进入启动关键路径。

## 知识源

- JY997D16601 Rev.R：FX3S/FX3G/FX3GC/FX3U/FX3UC Basic & Applied Instruction
- JY997D16801 Rev.K：FX3S/FX3G/FX3GC/FX3U/FX3UC Positioning Control
- JY997D26001 Rev.L：FXCPU Structured Programming [Device & Common]
- JY997D34701 Rev.M：FXCPU Structured Programming [Basic & Applied Instruction]
- JY997D34801 Rev.K：FXCPU Structured Programming [Application Functions]
- SH-080781ENG Rev.AG：GX Works2 Structured Project
- SH-080782ENG Rev.O：Structured Programming Fundamentals

源文件、官方地址和 SHA-256 记录在 `sources.json`。构建时会强制校验文件哈希。

## 构建流程

```text
PDF
 ├─ plain text
 ├─ word geometry / layout reconstruction
 ├─ table rows + bounding boxes
 └─ ladder/diagram text windows
          ↓
section / instruction-aware chunks
          ↓
SQLite + FTS5 + structured tables
          ↓
local dense LSA embeddings
```

主要结构化表：`instructions`、`instruction_aliases`、`device_records`、`error_records`、`debug_cases`。

`S1/S2` 根据上下文分为 `operand_placeholder` 或 `device`；例如 PLSY 的 `S1/S2` 是 operand，而状态继电器章节中的 `S1` 是设备地址。

## 检索

当前运行时链路：

```text
Query understanding
  ├─ instruction/device/error/debug structured lookup
  ├─ entity lookup
  ├─ BM25/FTS5
  └─ dense vector search
          ↓
weighted reciprocal-rank fusion
          ↓
deterministic cross-signal reranker + source priority + task-aware ranking
```

当前内置 `fx3u_multilingual_lsa_v1` dense embedding，维度、语料摘要、构建时间、
产物 SHA-256 和 benchmark 指标均记录在 `manifest.json`。向量文件仅在首次实际检索时
加载，以免拖慢程序启动。

## 重建与评估

```powershell
python tools/build_fx3u_knowledge.py
python tools/build_dense_embeddings.py
python tools/build_rag_benchmark.py --target 220
python tools/evaluate_rag_benchmark.py --fail-under-recall-10 0.98
```

基准集位于 `benchmarks/fx3u_rag_benchmark.jsonl`，包含指令、设备、错误码、调试案例、伺服/步进定位、结构化编程和负例。
