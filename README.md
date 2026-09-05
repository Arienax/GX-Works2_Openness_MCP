# GX Works2 Openness MCP

面向三菱 FX 系列 PLC 的 AI 辅助工程工作台。项目可以根据自然语言需求生成梯形图或 ST 程序，并通过本地确定性规则完成指令、软元件、I/O、时序和程序结构校验。

## 主要功能

- PLC 程序生成、版本管理、差异预览、评审与故障调试
- GX Works2 CSV 与软元件注释导入导出、双向同步
- GX Simulator2 自动化回归测试与可读测试报告
- FX3U 手册 RAG 检索、模型工具调用和图片需求输入
- DeepSeek、智谱及自定义 OpenAI-compatible 模型配置

## 技术栈

- Python、PyQt、PyInstaller
- 统一 ModelProvider 与 MCP 风格 ToolRuntime
- PLC IR、静态校验器及 SVG/CSV/ST 确定性渲染
- SQLite FTS5、BM25、Dense Vector 与混合重排
- pywinauto、MX Component 与本地 C# 仿真网关

API Key 仅保存在当前 Windows 用户的凭据管理器中，不写入源码仓库。
