# NORP Agent 文档索引

> 本目录是 `docs/DEVELOPER_MANUAL.md`（中文）与 `docs/DEVELOPER_MANUAL.EN.md`（English）的**按部分拆分版本**，
> 用于降低单次加载体积、便于定位与检索。正文与原文逐行一致，未做改写。
>
> 另含由开发手册迁出的独立文档：**测试套件**（[`测试套件.md`](测试套件.md) / [`TEST_SUITES.EN.md`](TEST_SUITES.EN.md)）。

---

## 中文版（docs/docs/zh/）

| 部分 | 覆盖范围 | 行数 | 文件 |
| --- | --- | --- | --- |
| 第 1 部分：快速上手与总体架构 | 第 1-3 章 | 978 | [01_快速上手与总体架构.md](zh/01_快速上手与总体架构.md) |
| 第 2 部分：内核运行核心 | 第 4-8 章 | 892 | [02_内核运行核心.md](zh/02_内核运行核心.md) |
| 第 3 部分：钩子、安全、插件与命令行 | 第 9-13 章 | 1247 | [03_钩子、安全、插件与命令行.md](zh/03_钩子、安全、插件与命令行.md) |
| 第 4 部分：部署、回退、集成与 FAQ | 第 14-19 章 + 附录 A-C | 886 | [04_部署、回退、集成与 FAQ.md](zh/04_部署、回退、集成与 FAQ.md) |
| 第 5 部分：流程编排与深度解析 | 第 20-24 章 | 658 | [05_流程编排与深度解析.md](zh/05_流程编排与深度解析.md) |
| 第 6 部分：开发者实战与注册流程 | 第 25-26 章 | 1688 | [06_开发者实战与注册流程.md](zh/06_开发者实战与注册流程.md) |
| 第 7 部分：最小内核与外部脚本集成 | 第 27-28 章 | 791 | [07_最小内核与外部脚本集成.md](zh/07_最小内核与外部脚本集成.md) |
| 第 8 部分：多模态与中枢神经总线 | 第 29-30 章 | 1237 | [08_多模态与中枢神经总线.md](zh/08_多模态与中枢神经总线.md) |
| 第 9 部分：发行、自进化与附录 | 第 31-34 章 + 附录 D-J + 修订记录 | 1589 | [09_发行、自进化与附录.md](zh/09_发行、自进化与附录.md) |

## English version (docs/docs/en/)

| Part | Covers | Lines | File |
| --- | --- | --- | --- |
| Part 1: Quick Start and Architecture | Chapters 1-3 | 1043 | [01_quick_start_and_architecture.md](en/01_quick_start_and_architecture.md) |
| Part 2: Kernel Runtime Core | Chapters 4-8 | 953 | [02_kernel_runtime_core.md](en/02_kernel_runtime_core.md) |
| Part 3: Hooks, Security, Plugins and CLI | Chapters 9-13 | 1292 | [03_hooks_security_plugins_and_cli.md](en/03_hooks_security_plugins_and_cli.md) |
| Part 4: Deployment, Rollback, Integration and FAQ | Chapters 14-19 + Appendices A-C | 957 | [04_deployment_rollback_integration_and_faq.md](en/04_deployment_rollback_integration_and_faq.md) |
| Part 5: Flow Orchestration and Deep Dive | Chapters 20-24 | 761 | [05_flow_orchestration_and_deep_dive.md](en/05_flow_orchestration_and_deep_dive.md) |
| Part 6: Developer Practice and Registration Flow | Chapters 25-26 | 1809 | [06_developer_practice_and_registration_flow.md](en/06_developer_practice_and_registration_flow.md) |
| Part 7: Minimal Kernel and External Script Integration | Chapters 27-28 | 861 | [07_minimal_kernel_and_external_script_integration.md](en/07_minimal_kernel_and_external_script_integration.md) |
| Part 8: Multimodal and the Central Nervous Bus | Chapters 29-30 | 1295 | [08_multimodal_and_the_central_nervous_bus.md](en/08_multimodal_and_the_central_nervous_bus.md) |
| Part 9: Distribution, Self-Evolution and Appendices | Chapters 31-34 + Appendices D-J + Revision History | 1591 | [09_distribution_self_evolution_and_appendices.md](en/09_distribution_self_evolution_and_appendices.md) |

---

## 独立文档

| 文档 | 说明 |
| --- | --- |
| [测试套件.md](测试套件.md) | 开发手册迁出的全部测试套件内容（原第 17 章 / 各章验证与验收节 / 测试矩阵 / 测试命令） |
| [TEST_SUITES.EN.md](TEST_SUITES.EN.md) | English version of the test-suite material |
| [USER_MANUAL.md](../USER_MANUAL.md) | 用户手册 |

## 完整单文件（原文，未改动）

- 中文：[../DEVELOPER_MANUAL.md](../DEVELOPER_MANUAL.md)
- English: [../DEVELOPER_MANUAL.EN.md](../DEVELOPER_MANUAL.EN.md)

## 拆分说明

- 拆分粒度：按"部分"（共 9 个部分），每部分为独立 Markdown 文件。
- 中英两版部分划分一致，便于对照阅读。
- 测试套件章节已从开发手册整体移除，内容见 `测试套件.md` / `TEST_SUITES.EN.md`。
