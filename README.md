# Skills

这是一个用于存放 AI Agent 可复用技能的代码仓库，聚焦于结构化、可复用、可组合的工作流能力。

## 概述

该仓库的目标是把常见的 Agent 工作模式封装成独立的 skill 模块。每个 skill 都包含自己的 `SKILL.md` 定义，以及相关的资源、脚本和参考资料，以便在不同的 Agent 工作流中直接复用。

## 已包含的 skill

- `paper-idea-generator`
  - 根据研究课题和可行性研究报告，检索并核实相关文献。
  - 输出值得研究的方向、候选论文选题、技术路线、创新点与实验设计。
  - 注重证据驱动的筛选、创新性评估和风险分析。

## 仓库结构

```text
skills/
├── README.md
├── paper-idea-generator/
│   ├── SKILL.md
│   ├── assets/
│   ├── references/
│   └── scripts/
└── ...
```

## 使用方式

可以将每个 skill 当作一个独立的能力模块在 AI Agent 环境中使用。`SKILL.md` 中定义了该技能的适用场景、输入输出要求以及执行流程。

## 说明

这个项目主要用于 AI 辅助研究与开发场景中的实验、复用和扩展。



