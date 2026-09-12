# NORP Agent 开发手册

> **版本**：2.2.1 ｜ **宣传名**：FarStars（远星）｜ **许可**：Copyright (c) 2026 xingluosama121, MIT Licensed
>
> NORP Agent初版发布于2026年7月29日，在8月16日正式上线PyPI，定位为“智能体元框架”。

---

## 目录

- [第 1 章　快速上手](#第-1-章快速上手)
- [第 2 章　总体架构：分层与数据流](#第-2-章总体架构分层与数据流)
- [第 3 章　架构层与地址函数](#第-3-章架构层与地址函数)
- [第 4 章　事件循环系统：norpagent.nasyncio()](#第-4-章事件循环系统norpagentnasyncio)
- [第 5 章　前端体系](#第-5-章前端体系)
- [第 6 章　npa() 启动与生命周期](#第-6-章npa-启动与生命周期)
- [第 7 章　模型与工具](#第-7-章模型与工具)
- [第 8 章　会话、沙箱、调度器、上下文与项目](#第-8-章会话沙箱调度器上下文与项目)
- [第 9 章　9 层 29 钩子](#第-9-章9-层-29-钩子)
- [第 10 章　安全系统：norpagent.safe()](#第-10-章安全系统norpagentsafe)
- [第 11 章　插件系统](#第-11-章插件系统)
- [第 12 章　预设模式](#第-12-章预设模式)
- [第 13 章　命令行入口](#第-13-章命令行入口)
- [第 14 章　嵌入式与超高并发部署](#第-14-章嵌入式与超高并发部署)
- [第 15 章　工作回退：快照 / Undo / Redo / 崩溃救援 / 安全模式](#第-15-章工作回退快照-undo--redo--崩溃救援--安全模式)
- [第 16 章　库集成示例](#第-16-章库集成示例)
- [第 17 章　测试与调试](#第-17-章测试与调试)
- [第 18 章　迁移指南](#第-18-章迁移指南)
- [第 19 章　常见问题（FAQ）](#第-19-章常见问题faq)
- [附录 A　架构槽位速查表](#附录-a架构槽位速查表)
- [附录 B　9 层钩子速查表](#附录-b9-层钩子速查表)
- [附录 C　公开 API 索引](#附录-c公开-api-索引)
- [第 20 章　模块流程编排（FLOW）](#第-20-章模块流程编排flow)
- [第 21 章　内置组件深度剖析](#第-21-章内置组件深度剖析)
- [第 22 章　Web UI 与前端深度解析](#第-22-章web-ui-与前端深度解析)
- [第 23 章　性能设计与基准测试](#第-23-章性能设计与基准测试)
- [第 24 章　救援模式：底层循环控制与人类接管](#第-24-章救援模式底层循环控制与人类接管)
- [第 25 章　开发者实战：模块、槽位、插件与工具开发](#第-25-章开发者实战模块槽位插件与工具开发)
- [第 26 章　注册流程详解](#第-26-章注册流程详解)
- [第 27 章　最小内核详解：通用事件总线、槽位连接器、注册表与地址解析器](#-第-27-章最小内核详解通用事件总线槽位连接器注册表与地址解析器)
- [第 28 章　外部 Python 脚本集成：热挂载与钩子订阅](#第-28-章外部-python-脚本集成热挂载与钩子订阅)
- [第 29 章　多模态：视觉与声音](#第-29-章多模态视觉与声音)
- [第 30 章　中枢神经总线：多实例与神经树](#第-30-章中枢神经总线多实例与神经树)
- [第 31 章　成品发行版：norpagent unbox](#第-31-章成品发行版norpagent-unbox)
- [第 32 章　自进化体系：热重载、勾选审批与进化包](#第-32-章自进化体系热重载勾选审批与进化包)
- [第 33 章　插件开发完全指南](#第-33-章插件开发完全指南)
- [第 34 章　设置事实源、白盒与进化闭环深化](#第-34-章设置事实源白盒与进化闭环深化)
- [附录 D　术语表](#附录-d术语表)
- [附录 E　29 钩子事件负载速查表](#附录-e29-钩子事件负载速查表)
- [附录 F　前后端通讯方式速查表](#附录-f前后端通讯方式速查表)
- [附录 G　全部命令用法速查表](#附录-g全部命令用法速查表)
- [附录 H　全部函数及结构用法速查表](#附录-h全部函数及结构用法速查表)
- [附录 I　多模态配置与 API 速查](#附录-i多模态配置与-api-速查)
- [附录 J　中枢神经总线速查表](#附录-j中枢神经总线速查表)

---

## 第 1 章　快速上手

### 1.1 安装

```bash
pip install norpagent
```

核心包无第三方依赖，安装后可在纯 Python 环境运行（内置 mock 模型与工具）。
可选能力按需安装：

```bash
pip install norpagent[openai]       # OpenAI 兼容模型适配器（DeepSeek/OpenAI/Qwen/vLLM/Ollama）
pip install norpagent[anthropic]    # Anthropic 协议模型适配器
pip install norpagent[web]          # 联网检索（web_search / web_fetch 工具）
pip install norpagent[security]     # 插件 Ed25519 验签（cryptography）
pip install norpagent[all]          # 全部
```

### 1.2 第一个程序

```python
import norpagent as npa

npa()                    # 按默认配置启动（standard 预设 + Web 前端）
running = True
while running:
    if npa.stop() == True:   # 生命周期函数：应用结束即退出
        running = False
```

保存为 `hello.py` 运行，控制台打印：

```
[norpagent] frontend web listening on 127.0.0.1:8787
[norpagent] lazy-loaded modules: ...   # 本次已加载的懒加载模块（如有）
```

浏览器访问该地址打开聊天界面。启动流程见第 6 章。两个要点：

1. **`npa()` 是模块级调用**——`norpagent` 模块本身可调用，等价于 `norpagent.launch()`；
2. **`npa.stop()` 是生命周期函数**——返回 `True` 表示 Agent 应用已结束，主循环应退出。

### 1.3 单次任务模式

```python
import norpagent as npa

npa(prompt="简要解释什么是地址函数")
running = True
while running:
    if npa.stop() == True:
        running = False

engine = npa.current()
print(engine.last_result.final_content)
```

传入 `prompt` 后：Agent 执行完这一条任务即自动停止（`npa.stop()` 变为 `True`），
任务结果保存在 `npa.current().last_result`。

### 1.4 替换前端示例

```python
import norpagent as npa

npa(prompt="hi", frontend="norpagent.frontends.headless:HeadlessFrontend")
while True:
    if npa.stop():
        break
```

HeadlessFrontend 不读取键盘输入、不渲染界面，通过程序 API 驱动。
组件替换通过为槽位填入新地址完成，不修改框架核心代码。

### 1.5 本章用法速查

| 用法 | 写法 |
|---|---|
| 按默认配置启动 | `npa()` |
| 判断应用是否结束 | `npa.stop()` |
| 单次任务 | `npa(prompt="...")` |
| 指定预设模式 | `npa(preset="standard")` |
| 指定模型 | `npa(model="openai_compat")` |
| 指定事件循环 | `npa(async_loop="myapp.loop:create")` |
| 指定前端 | `npa(frontend="myapp.ui:create")` |
| 指定会话存储 | `npa(session="sqlite")` |
| 指定安全级别 | `npa(security="high")` |
| Web 端口 / 语言 | `npa(port=9000, language="zh_CN")` |
| 自定义主页面 | `npa(html="/path/to/my.html")` |
| 自定义模块流程页 | `npa(flow_html="/path/to/flow.html")` |
| 前端直挂 HTML 路径 | `npa(frontend="/path/to/my.html")` |

---

## 第 2 章　总体架构：分层与数据流

### 2.1 架构说明

NorpAgent 的架构：除底层最小内核外，全部组件都是可替换槽位。
替换组件（模型、工具、会话、沙箱、调度器、前端、事件循环、
Agent 循环）时，为槽位填入新地址即可，无需修改框架核心代码。

### 2.2 分层图

```
┌─────────────────────────────────────────────────────────────┐
│  你的应用                                                    │
│  npa() / npa.stop() / npa.nasyncio() / npa.current().submit()   │
└───────────────────────────┬─────────────────────────────────┘
                            │ 模块入口（norpagent/__init__.py 可调用）
┌───────────────────────────▼─────────────────────────────────┐
│  运行时层 runtime/                                           │
│  launch → ArchLayer.connect → mount.build_registry          │
│  → NorpEngine（生命周期状态机 + 后台循环线程 + 前端线程）      │
└──────┬──────────────────┬───────────────────┬───────────────┘
       │                  │                   │
┌──────▼──────┐   ┌───────▼────────┐  ┌───────▼───────────────┐
│ 架构层 arch/ │   │ 循环系统 loops/ │  │ 前端 frontends/       │
│ 槽位定义      │   │ LoopRuntime    │  │ Frontend 协议        │
│ 地址解析      │   │ 协议 + 默认实现 │  │ console/headless/web │
│ ArchLayer    │   │ = nasyncio()   │  └───────────────────────┘
└──────┬──────┘   └───────┬────────┘
       │ 按槽位装配          │ 按协议驱动
┌──────▼────────────────────▼─────────────────────────────────┐
│  内核 kernel/                                                │
│  Registry（注册表）── EventBus（事件总线）── AgentRuntime     │
│  （Agent 循环本体，本身也是可替换槽位 agent_runtime）          │
└──┬──────────┬──────────┬──────────┬──────────┬──────────────┘
   │          │          │          │          │
┌──▼───┐ ┌────▼────┐ ┌───▼────┐ ┌───▼─────┐ ┌──▼────────────┐
│模型   │ │工具     │ │会话     │ │沙箱      │ │调度器/上下文/  │
│model  │ │tools    │ │session  │ │sandbox   │ │项目/安全/插件 │
└───────┘ └─────────┘ └─────────┘ └──────────┘ └───────────────┘
   以上全部通过注册表按名字解析，全部是架构槽位（可替换）
```

### 2.3 底层最小内核（四个模块）

最小内核由以下四个模块组成：

| # | 模块 | 职责 | 不可替换原因 |
|---|---|---|---|
| 1 | `norpagent.arch.layer.ArchLayer` | 槽位连接器 | 负责装配动作 |
| 2 | `norpagent.arch.address` | 地址解析器 | 提供地址语义 |
| 3 | `norpagent.kernel.registry.Registry` | 注册表 | 名称到组件的映射中心 |
| 4 | `norpagent.kernel.events.EventBus` | 事件总线 | 组件间的事件传递通道 |

其余组件——事件循环、Agent 循环、模型、工具、会话、沙箱、调度器、
上下文库、项目管理、钩子扩展、安全、插件、前端、渲染器、预设、日志、
存储、错误处理——均为槽位。

### 2.4 一次任务的数据流

用户输入一行「帮我读取 readme.md 并总结」，一次 `npa()` 启动的引擎内部发生：

```
前端线程 input() 拿到文本
  → engine.submit(text)                  （第 6 章）
  → loop.submit(fn)                      （第 4 章：循环系统，可替换）
  → AgentRuntime.run(text)               （内核循环，可替换：agent_runtime 槽位）
      → L3 prepare_input                （before_input / after_input 钩子）
      → L4 create_session / append_message
      → L5 build_messages               （系统提示词 + 历史合并）
      → L6 before_step
      → L7 call_model                   （模型 = model 槽位解析出的提供者）
      → L8 execute_tool_call            （工具 = tools 槽位，沙箱 = sandbox 槽位）
      → （多轮直到模型给出最终答案）
      → L9 finalize_result
  ← RunResult（final_content / status / usage ...）
事件总线全程广播（on_task_start / on_content / after_tool_call ...）
  → ui 渲染器（UIAdapter）订阅事件，把流渲染给用户
```

每一个带 L 编号的环节都是一层钩子（第 9 章），每一个零件都是一个槽位（第 3 章）。

### 2.5 模块地图：每个文件做什么

| 文件 | 职责 |
|---|---|
| `norpagent/__init__.py` | 模块即入口：`npa()` / `npa.stop()` / `npa.nasyncio()` |
| `norpagent/arch/slots.py` | 18 个内置架构槽位的规格定义表 + 槽位表热插拔注册中心（register_slot / unregister_slot / replace=True 规格热替换） |
| `norpagent/arch/address.py` | 地址函数解析器（字符串 → 模块/对象） |
| `norpagent/arch/layer.py` | ArchLayer：槽位连接与工厂调用 |
| `norpagent/loops/base.py` | LoopRuntime 协议（事件循环契约） |
| `norpagent/loops/nasyncio.py` | 默认循环实现：NasyncioLoopRuntime（自研 nasyncio 核心适配器，零 asyncio 依赖） |
| `norpagent/loops/std_asyncio.py` | 0.7 旧模块名的兼容垫片（重导出 StdLoopRuntime，不 import asyncio） |
| `norpagent/loops/__init__.py` | `norpagent.nasyncio()` 架构函数 |
| `norpagent/nasyncio.py` | 自研异步 IO 核心（原 nasync_io，已打包进库）：事件循环 / Future / Task / 同步原语 / 子进程，不依赖标准 asyncio |
| `norpagent/frontends/base.py` | Frontend 协议（前端契约） |
| `norpagent/frontends/web.py` | 默认前端：Web（HTTP + SSE，页面 = front.html） |
| `norpagent/frontends/console.py` | 控制台前端：命令行 REPL（显式指定） |
| `norpagent/frontends/headless.py` | 无头前端：纯 API，输出打印 stdout |
| `norpagent/runtime/mount.py` | 槽位实现 → 注册表装配（默认逻辑登记） |
| `norpagent/runtime/engine.py` | NorpEngine：生命周期状态机 + 线程编排 |
| `norpagent/runtime/__init__.py` | launch / stop / current / submit / shutdown |
| `norpagent/kernel/agent.py` | AgentRuntime：Agent 循环本体（可替换） |
| `norpagent/kernel/registry.py` | 注册表（底层最小内核之一） |
| `norpagent/kernel/events.py` | 事件总线（底层最小内核之一） |
| `norpagent/kernel/presets.py` | Preset 声明式配置 |
| `norpagent/protocols/*` | 全部组件协议（接口契约） |
| `norpagent/hooks/*` | 9 层 29 钩子体系 |
| `norpagent/security/*` | 安全系统（norpagent.safe()） |
| `norpagent/plugins/*` | 插件系统（签名/审计/隔离） |
| `norpagent/builtin/*` | 内置组件（同样走注册表，可被任意替换） |
| `norpagent/modes/*` | 四种预设模式 |
| `norpagent/flows/` | FLOW 流程编排内核（注册表快照 / 文件即模块 / 拓扑执行） |
| `norpagent/cli.py` | `norpagent` 命令行入口 |

---

### 2.6 模块化约定：分层依赖与扩展点

#### 2.6.1 依赖方向：单向下行

全部模块的自底向上依赖关系（上层可以 import 下层，下层不得
反向依赖上层）：

| 层 | 模块 | 允许依赖 |
|---|---|---|
| L0 契约 | `protocols/*` | 仅其它 protocol（零框架依赖） |
| L0 核心 | `nasyncio.py` | 仅标准库（自研异步核心，自包含） |
| L0 最小内核 | `kernel/events.py`、`kernel/registry.py` | 标准库 + protocols（registry 引用 Plugin / Tool 协议） |
| L1 钩子 | `hooks/*` | 仅 `kernel.events`（总线结构化视图） |
| L1 安全 | `security/*` | 零框架依赖（纯决策模块 + 可选 cryptography） |
| L2 插件 | `plugins/*` | `protocols` + `security/*` + `hooks.core`（管线层） |
| L2 内核循环 | `kernel/agent.py` | `hooks.core` + `kernel/*` + `loops.cancel` + `protocols/*` |
| L2 内置 | `builtin/*` | `protocols/*`（+ 沙箱用 `loops.cancel`） |
| L2 模式 | `modes/*` | 仅 `kernel.presets` |
| L3 架构 | `arch/*` | 仅自身（address / slots / layer） |
| L3 循环 | `loops/*` | `arch` + `nasyncio` |
| L3 前端 | `frontends/*` | 仅 `frontends.base` |
| L4 装配 | `runtime/*` | arch + builtin + kernel + modes（唯一「知道一切」的装配点） |
| L4 入口 | `__init__.py` / `cli.py` / `__main__.py` | 全部 |

关键规则：

- **内核可裁剪**：`kernel` 模块级不 import `security` /
  `plugins` / `builtin`——安全以 `registry.security` 注入，
  防护扫描在任务级参数显式要求时才惰性 import guard；插件以
  `register_plugin` 注入。嵌入式场景（14.2）正是靠这条规则把
  sqlite3 / http.server 等全部挡在内核之外；
- **内置组件也是普通实现者**：`builtin/*` 只依赖 protocols，
  与第三方组件地位完全平等，都经注册表按名解析；
- **协议与实现分离**：组件之间只通过 `protocols/*` 的接口契约
  对话（模型 / 工具 / 会话 / 沙箱 / 调度器 / UI / 插件），
  任何实现满足协议即可接入；
- `runtime.mount` 是唯一的默认装配点：预设（modes）+ 内置
  组件（builtin）在这里按槽位表（arch/slots）组装成注册表；
- `safe.py` 与 `security/*` 一样处于低层：安全系统可以脱离
  框架单独测试 / 单独使用，内核只通过注入点感知它（第 10 章）。

#### 2.6.2 四类扩展点

按侵入性从低到高，**全部无需修改框架核心代码**：

| 扩展点 | 方式 | 章节 |
|---|---|---|
| 事件订阅 | `reg.hooks.*.subscribe` / `reg.bus.subscribe` | 第 9 章 |
| 组件替换 | 槽位地址（模型 / 工具 / 会话 / 沙箱 / 前端 / 循环…） | 第 3 章 |
| 通用组件 | `register_component(kind, name, factory)` + 预设 components | 2.6.3 |
| 全新槽位 | `register_slot(SlotSpec(...))` | 3.8 |
| 外部插件 | 独立文件 / manifest 包，安全管线加载 | 第 11 章 |
| 安全策略 | `safe()` 运行态策略 + 独立 API | 第 10 章 |
| 循环 / 执行结构 | 方法覆写或 agent_runtime 槽位 | 9.6 |

「框架核心代码零修改」是设计红线：所有扩展走槽位 / 钩子 /
注册表，这也是 2.3 节「最小内核只有四样」的推论——最小内核
之外的一切都有既定替换通道。

#### 2.6.3 通用组件命名空间

除 model / tool / session / sandbox / scheduler / ui 六个专用
命名空间外，Registry 提供开放的通用组件命名空间：

```python
reg.register_component("context_store", "my_store", lambda: MyStore())
reg.register_component("my_kind", "my_impl", factory)   # 种类本身开放

# 预设里声明引用
Preset(name="mine", ..., components={"context_store": "my_store",
                                     "my_kind": "my_impl"})

reg.build_component("my_kind", "my_impl")               # 构建（工厂调用）
reg.build_component("context_store", "my_store",
                    workspace_root=path)                # 按签名注入工作区根
reg.list_components()                                   # 列出全部种类
```

上下文存储 / 项目管理 / 任务存储等一切「附加能力」都走这里，
框架无需改内核即可扩展新的组件种类；工厂声明了
`workspace_root` 参数（或 **kwargs）时自动注入工作区根。

#### 2.6.4 新增组件模块的标准流程（五步）

以「新增一个会话实现」为例：

1. **写协议**（如无）：在 `protocols/` 定义接口契约；
2. **写实现**：新建模块，只依赖 protocols（参照
   builtin/sessions/ 的写法）；
3. **注册**：`reg.register_session("redis", factory)` 或由
   runtime.mount / 自己的装配代码登记；
4. **声明使用**：预设里 `session="redis"`，或启动时
   `npa(session="redis")` / 地址字符串
   `npa(session="myapp.redis:create")`；
5. **接钩子**（可选）：在实现内经 registry 发布 / 订阅事件。

等价的手工装配路径：`Registry() + register_* +
AgentRuntime(...)`（17.1 节），与 npa() 装配完全同构——npa()
只是把这五步自动化。

---

## 第 3 章　架构层与地址函数

替换任意组件的做法：为对应槽位填入新地址，不修改框架核心代码。

### 3.1 槽位（Slot）是什么

一个 Agent 应用的每个组成部分都是一个槽位（装配点）：

```python
from norpagent.arch.slots import SLOT_SPECS, all_slot_names

print(all_slot_names())
# ['async_loop', 'agent_runtime', 'model', 'tools', 'session', 'sandbox',
#  'scheduler', 'context_store', 'project_manager', 'hooks', 'security',
#  'plugins', 'frontend', 'ui', 'preset', 'logger', 'storage', 'error_handler']
```

共 **18 个内置槽位**（框架结构契约，受保护不可注销 / 覆盖规格）。
槽位表本身可热插拔：第三方可运行时 `register_slot()` 注册**自定义
槽位**（名字 / 语义 / 装配逻辑完全自定义），注册即接入完整管线——
详见 3.8 节。每个槽位都有规格说明（SlotSpec）：名称、职责、协议、
默认实现、字符串语义、工厂参数约定：

```python
from norpagent.arch.slots import get_slot

print(get_slot("async_loop").format_help())
# [async_loop] 事件循环系统：Agent 运行所在的异步调度核心。等价于架构函数 norpagent.nasyncio()。
#   协议: LoopRuntime 协议（norpagent.loops.base.LoopRuntime）：...
#   默认: norpagent.loops.nasyncio:NasyncioLoopRuntime
#   字符串语义: address
#   工厂参数 layer: 所在架构层
#   工厂参数 config: 该槽位的附加配置 dict
#   示例: npa(async_loop='norpagent.loops.nasyncio:NasyncioLoopRuntime')
```

### 3.2 地址函数：不填 = 默认，填了 = 接入

槽位取值有四种形态：

| 形态 | 写法 | 语义 |
|---|---|---|
| 不填（None） | `npa()` | 使用库内置默认逻辑 |
| 字符串地址 | `npa(async_loop="pkg.mod:attr")` | 按地址加载文件，把实现接上去 |
| 可调用对象 | `npa(async_loop=MyLoop)` | 工厂/类直接接入 |
| 实例/值 | `npa(async_loop=loop_instance)` | 现成对象直接接入 |

字符串地址的解析规则（`norpagent.arch.address.resolve_address`）：

1. `"pkg.mod"` —— 加载该**文件（模块）**。优先取模块内约定的工厂属性
   `create` → `build` → `default`；都没有就把**整个模块**作为实现接上去；
2. `"pkg.mod:attr"` —— 加载该文件，取模块内的具名属性；
3. `"pkg.mod:attr;键=值;键=值"` —— 分号后附加配置，注入工厂的 `config` 参数
   （例如 `"norpagent.frontends.web:WebFrontend;port=9000"`）。地址解析前会先剥离
   分号子句，子配置不干扰模块路径解析。

地址字符串指向模块文件：架构层加载该文件（或文件内的对象）并接入槽位。

槽位挂载参数示例（frontend 槽位的 html 子句）：

```python
# 用自定义 HTML 文件替换 / 路由默认页面（不物理覆盖库文件）
npa(frontend="norpagent.frontends.web:WebFrontend;html=/path/to/my.html")
```

### 3.3 字符串语义

有些槽位的字符串值不是地址而是「注册表组件名」。每个槽位在 SlotSpec
里声明了自己的字符串语义：

| 语义 | 含义 | 槽位 |
|---|---|---|
| `address` | 字符串 = 模块地址 | async_loop, agent_runtime, frontend, context_store, project_manager |
| `name` | 字符串 = 注册表组件名 | tools（容器语义，见下） |
| `name_or_address` | 先按名、再按地址 | model, session, sandbox, scheduler, ui, preset |
| `literal` | 字符串 = 字面值，地址优先 | security(级别), storage(路径), hooks, plugins, logger, error_handler |

其中：`npa(model="mock")` 中的 `"mock"` 是注册表里的模型名；
`npa(model="myapp.model:create")` 中的字符串是地址。
`npa(session="sqlite")` 引用内置 SQLite 会话组件；
`npa(session="myapp.sessions:create")` 按地址加载自定义会话实现。

**v0.9.1：全部槽位支持按地址加载 + 键值对的值支持纯地址解析**

1. `name` / `name_or_address` 槽位：字符串先查注册表名，查不到再按
   模块地址（`pkg.mod[:attr]`）加载——ui / preset 已从纯 `name`
   升级为 `name_or_address`：`npa(ui="myapp.render:create")`、
   `npa(preset="myapp.presets:build")` 直接按地址接上实现；
2. `literal` 槽位「地址优先」：字符串**形如纯地址**（含 `.` 或 `:`
   的点分标识符，结构判定见 `norpagent.arch.address.is_address_like`）
   即按地址加载（解析失败抛 `AddressError`，不静默回落）；其余保持
   字面值——`npa(security="high")` 仍是级别、`npa(storage="./data")`
   仍是路径，`npa(security="myapp.sec:build_kit")` /
   `npa(storage="myapp.store:create;root=./x")` 按地址加载；
3. **键值对的值支持纯地址解析**：任何槽位的 dict 形态值统一处理
   （tools 映射 / hooks 映射 / 自定义槽位 dict 值，嵌套 dict 递归）：
   值若是纯地址字符串就按地址解析为对象（解析失败抛 `AddressError`）
   ——`tools={"my_tool": "myapp.tools:create"}`、
   `hooks={"before_model_call": "myapp.guard:fn"}`。解析出的
   callable 按工厂约定调用（注入 layer / slot / config 上下文，
   `;key=value` 子句解析为工厂 config）；**hooks 槽位除外**——其
   值是「回调本身」，地址指向的回调函数原样保留不调用；
4. tools 槽位容器：列表元素与单个字符串同样支持地址——
   `tools=["myapp.tools:create"]`、`tools="myapp.tools:create;tag=x"`；
   其余字符串元素仍为已注册工具名引用（如 `tools=["echo"]`）。

### 3.4 工厂调用约定：签名裁剪注入

地址解析出一个**可调用对象**（类或函数）时，ArchLayer 按
`norpagent.arch.layer.call_factory` 的约定调用它：

1. 检查工厂签名；
2. 把工厂**声明了的**上下文键注入（`layer` / `slot` / `config` /
   以及槽位专属键，见附录 A）；
3. 工厂不声明的键**自动忽略**（包括完全不接受上下文的工厂，无参调用）；
4. 不可调用的对象（模块 / 实例 / 值）**原样使用**，不做任何调用。

以下三种写法等价：

```python
# 1. 类：不声明上下文 → 无参实例化
class MyLoop:
    def __init__(self):
        ...

npa(async_loop=MyLoop)

# 2. 工厂函数：声明 config → 自动注入
def create(config=None, **kw):
    return MyLoop(timeout=float((config or {}).get("timeout", 0)))

npa(async_loop=create)

# 3. 字符串地址 + 附加配置子句
npa(async_loop="myapp.loop:create;timeout=5")
```

### 3.5 ArchLayer：装配清单可观测

每一次 `npa()` 内部都会构建一个 ArchLayer 并 `connect()`。
装配结果可观测：

```python
eng = npa.current()
print(eng.layer.describe())
```

输出示例：

```
== NorpAgent 架构层装配清单 ==
  async_loop       <- 默认逻辑                         => NasyncioLoopRuntime
  agent_runtime    <- 默认逻辑                         => type
  model            <- 默认逻辑                         => (未连接)
  ...
  frontend         <- 地址 'norpagent.frontends.headless:HeadlessFrontend' => HeadlessFrontend
  preset           <- 地址 'minimal'                 => str
```

`(未连接)` 表示该槽位未指定，由预设声明的默认逻辑处理。

### 3.6 示例：替换多个槽位

```python
import norpagent as npa

# 模型为 openai_compat，会话为 sqlite，沙箱为 pooled，前端为 Web（端口 9000），
# 循环为自定义实现，安全级别 high。全部通过槽位参数指定。
npa(
    preset="standard",
    model="openai_compat",              # 名称引用
    session="sqlite",                   # 名称引用
    sandbox="pooled",                   # 名称引用
    frontend="norpagent.frontends.web:WebFrontend;port=9000",
    async_loop="myapp.nasync_loop:create",
    security="high",
)

while True:
    if npa.stop():
        break
```

### 3.7 运行中热挂载：任何槽位均可替换

`npa()` 启动后**引擎保持运行**，随时替换任意槽位实现，无需重启：

```python
import norpagent as npa

npa()                                        # 启动（默认 Web 前端）
# ... 应用运行中 ...

npa.remount(model="openai_compat")           # 换模型：下一次 run 生效
npa.remount(tools=["echo", "get_time"])      # 换工具集：下一次 run 生效
npa.remount(session="sqlite")                # 换会话存储：AgentRuntime 热重建
npa.remount(security="high")                 # 换安全级别：旧防护钩子先退订
npa.remount(frontend="norpagent.frontends.console:ConsoleFrontend")
npa.remount(async_loop="myapp.loop:create")  # 换事件循环：停旧启新
npa.remount(model="myapp.model:create")      # 运行中替换模块文件（热重载）
```

底层链路：`npa.remount()` → `engine.remount()` → `ArchLayer.remount()`。
字符串地址在重新解析前会**失效模块缓存与 .pyc 字节码缓存**，
因此「修改模块文件 → remount」即可在运行中换上改动后的代码，
无需重启进程。

替换语义按槽位分组：

| 分组 | 槽位 | 生效方式 |
|---|---|---|
| 组件槽位 | model / tools / hooks / security / plugins | 重挂到注册表并重写最终预设；model / tools 下一次 run() 生效（Agent 循环每次 run 重新解析模型与工具 schema）；重复挂载的架构级订阅先退订再重挂，不叠加重复触发 |
| 装配槽位 | session / sandbox / scheduler / ui / agent_runtime / preset / context_store / project_manager | AgentRuntime 热重建：停旧运行时（释放沙箱/组件/退订渲染器）→ 按当前装配建新运行时 → 前端重绑渲染器（HTTP 端口不变）（在途任务竞态与排水建议见本节后文） |
| 基础设施槽位 | frontend / async_loop | 停旧实现、启新实现；新实现启动失败自动回滚旧实现。async_loop 替换时旧循环上在途任务会被放弃，建议无任务时替换 |
| 基础服务槽位 | logger / storage / error_handler | 直接更新引擎引用，立即生效 |

**装配槽位热重建的在途任务竞态（Drain 说明）**：装配槽位的 remount
走「停旧 → 建新 → 前端重绑」三步，**这三步都不等待工作池中在途的
`agent.run` 任务**。若热重建恰逢任务执行中：

1. `old.shutdown()` 已关闭旧沙箱，在途 run 的下一次工具调用会打到
   已关闭的沙箱上（失败或未定义行为）；
2. 旧渲染器退订到新渲染器订阅之间存在窗口期，在途 run 的事件丢失；
   重绑后新数据源会收到**旧 run 的残余事件**，与新 run 的事件交错；
3. 在途 run 的结果仍会返回给其 submit 调用方——一个来自「已死亡
   运行时」的结果；
4. 会话槽位不变时新旧 run 写同一个 session store（历史连续）；沙箱 /
   调度器 / ui 槽位换掉后，在途 run 引用的旧实例已被 close。

**建议（生产环境）：两阶段热挂载（drain）**——① 先阻断新任务入队
（业务侧自维护 drain 标志，`submit` 前检查）；② `loop.interrupt()`
置位全部在途任务取消事件，并给工作池一个 join 宽限期（如 2s）；
③ 超时未退的任务随沙箱关闭语义兜底（PTC / pooled 沙箱强杀进程树）；
④ 再执行装配槽位 remount。`interrupt()` 基础设施已存在
（`engine.request_stop` 第一步即调用），实现成本低。管理面操作
（改配置 / 换组件）建议放在任务空闲时执行；**框架当前版本未内置
drain**，属业务侧职责。

#### 3.7.2 热挂载前端页面（html / flow_html 参数）

`frontend` 是基础设施槽位，替换语义为「停旧启新」。配合 WebFrontend
的 `html` / `flow_html` 挂载参数，可在运行中换掉 `/` 路由页面或
`/flow` 模块流程页面——不用重启进程，刷新浏览器即见新页面：

```python
import norpagent as npa

npa(html="front.html")                       # 启动并挂载自定义主页面
# ... 修改 front.html 或换别的页面文件 ...
npa.remount(frontend="norpagent.frontends.web:WebFrontend;html=front.html")
# 端口不变，浏览器刷新（或重开 http://127.0.0.1:8787/）即为新页面

npa.remount(frontend="norpagent.frontends.web:WebFrontend;flow_html=flow.html")
# 换 /flow 模块流程编排页面（norp-flow.html 的官方挂载途径）
```

参数优先级：remount **显式给出**的键覆盖启动参数，**未显式给出**的键
（如 port）沿用启动参数——所以只换页面时浏览器 URL 不变。显式键的
判定：字符串地址取分句 `;key=value` 中的键；实例取构造参数中与默认值
不同的键（html / flow_html 以 `_html` / `_flow_html` 属性判定）。例如：

```python
npa.remount(frontend="norpagent.frontends.web:WebFrontend;port=9000")  # 换端口（重启 HTTP 监听）
npa.remount(frontend="norpagent.frontends.web:WebFrontend;html=")      # 重置主页面为库内置
npa.remount(frontend="norpagent.frontends.web:WebFrontend;flow_html=") # 重置 /flow 为库内置
from norpagent.frontends.web import WebFrontend
npa.remount(frontend=WebFrontend(html="front.html"))                   # 实例形式
npa.remount(frontend=WebFrontend(flow_html="flow.html"))               # 实例形式
npa.remount(frontend="front.html")     # HTML 路径直挂：等价于 WebFrontend;html=front.html
```

**remount 页面热替换键（v0.9，更简单的换页入口）**：`html` /
`flow_html` 本身不是槽位，而是 frontend 槽位的挂载参数——
`npa.remount()` 直接接收这两个键，**不经过「停旧前端 / 启新前端」**，
经 `mount_page` 立即换页（HTTP 服务不重启、端口不变，刷新浏览器
即见新页面）：

```python
npa.remount(flow_html="flow-v2.html")       # /flow 立即换页（HTTP 不重启）
npa.remount(html="front-v2.html")           # / 主页面立即换页
npa.remount(flow_html="<html>...</html>")   # HTML 内容直传（"<" 开头视为内容）
npa.remount(flow_html=None)                 # 卸载挂载，回落库内置 norp-flow.html
npa.remount(flow_html="", html="")          # "" 与 None 同语义（卸载）
npa.remount(flow_html="flow-v2.html",
           frontend="norpagent.frontends.web:WebFrontend")  # 可组合：先落参数再换前端
```

语义细节：

1. 值先写入 `engine.params`（与 `npa(html=...)` 启动透传同一条数据
   通路），后续 frontend 热挂载 / attach 沿用新值；
2. 当前前端是 Web 前端时经 `mount_page` 立即换页；非 Web 前端
   （console / headless）只更新参数、无副作用；
3. 坏路径**预校验**快速失败（`ValueError`），槽位变更与页面都不留
   半途状态；
4. 若用户用 `register_slot()` 注册了同名自定义槽位，槽位表优先
   （按槽位语义处理）；
5. `remount(port=...)` / `remount(host=...)` 等网络参数仍不是页面键，
   会报错并提示用地址子句形式（会重启 HTTP 监听）。

**frontend 槽位两种挂载方式（v0.9，等价共存）**：

1. 地址式：`npa(frontend="norpagent.frontends.web:WebFrontend;html=...")`
   —— 模块地址 + 分句参数；
2. HTML 路径直挂：`npa(frontend="front.html")` —— 槽位值本身是
   `.html/.htm` 文件路径（不含 `;` 子句）时，架构层不再按模块地址
   解析，装配器自动转换为 `WebFrontend(html=<该路径>)`。文件不存在
   抛 `ValueError` 快速失败（不静默回落默认前端）。

注意：HTML 路径直挂只作用于 `/` 主页面；换 `/flow` 页面请用
`;flow_html=...` 子句或 `WebFrontend(flow_html=...)`。

**运行中直接换页面（HTTP 服务不重启，端口不变）**：

```python
# 方式一：remount 页面热替换键（推荐，v0.9）
npa.remount(flow_html="flow.html")           # /flow 立即换页
npa.remount(html="front.html")               # / 主页面立即换页
npa.remount(flow_html=None)                  # 卸载挂载，回落库内置

# 方式二：frontend 实例 API
eng.frontend.mount_page("flow", "flow.html")   # /flow 立即换页
eng.frontend.mount_page("flow", None)          # 卸载挂载，回落库内置
eng.frontend.mount_page("front", "<html>...</html>")  # 同理作用于 /
# 等价入口：WebUI.mount_page(page, html)
```

**物理替换库内 HTML 文件自动生效**：页面字节缓存按资源文件的
mtime/size 签名校验——直接覆盖
`norpagent/builtin/ui/assets/front.html` 或 `norp-flow.html`
后刷新浏览器即为新页面（无需 remount、无需重启）；命中缓存时
仅一次 stat 校验，无 open+read 磁盘 I/O。

注意事项：`npa.remount()` 是**进程内 API**，需在启动了引擎的同一
Python 进程里调用（跨进程不生效）。cmd 中运行时，把 remount 放在
生命周期循环里、或起一个线程读 stdin 即可实现「敲命令换页面」。

注意事项：

1. 只允许在引擎 RUNNING 状态调用，否则抛 `EngineError`；槽位名非法同样抛错；
2. `remount(slot=None)` 清空该槽位配置（回落默认逻辑）；
3. 预设对象同一性：热挂载后 `registry.resolve_preset(name)` 与
   `engine.agent.preset` 仍是同一实例（前端对 preset.tools 的热改写依赖此约定）；
4. `agent_runtime` 是 `defer_factory` 槽位：工厂推迟到引擎装配期调用
   （registry / preset 上下文就绪后），地址子句 `;key=value` 经
   `ArchLayer.subconfig()` 注入工厂的 config。

### 3.8 槽位表热插拔：注册自定义槽位

`npa.remount()` 换的是**槽位的实现**；槽位表本身（`SLOT_SPECS`）也
可热插拔——第三方库运行时注册**全新的自定义槽位**，注册即接入
完整管线（`npa()` 参数校验、ArchLayer 装配、`npa.remount()` 热替换、
`layer.describe()` 清单），无需修改框架源码、无需重启进程：

```python
from norpagent.arch import SlotSpec, register_slot, unregister_slot

# 自定义槽位 = 名字 + 字符串语义 + 应用逻辑（applier）
register_slot(SlotSpec(
    name="audit_tag",                # 槽位名 = npa() 的关键字参数名
    description="审计标签",
    protocol="literal 字符串",
    string_semantics="literal",      # address / name / name_or_address / literal
    applier=_apply_audit_tag,        # 槽位值非空时由装配器调用
))
```

```python
import norpagent as npa

npa(audit_tag="release-1")            # 装配期即应用
npa.remount(audit_tag="release-2")    # 运行中热替换（applier 重新执行）
```

`applier(reg, layer, value, params, ctx)` 的契约：

- `value` 是解析后的槽位值：`address` 语义为已实例化实现（子配置
  `;key=value` 经 `layer.subconfig(slot)` 取得），`name` /
  `name_or_address` / `literal` 语义为原值；
- `ctx` 提供四个可变容器：`components`（最终预设组件声明
  {kind: name}）、`extras`（引擎附加对象，`engine.extras[槽位名]`
  消费）、`overrides`（预设字段覆盖）、`meta`（注册表架构元数据，
  记录挂上去的可退订对象）；
- **同一注册表可能重复调用**（装配 + 每次 `npa.remount`），applier
  必须重入安全：重复执行不叠加副作用——订阅事件总线的对象先按
  `ctx["meta"]` 的记录退订再重挂（参考内置 hooks / security /
  plugins 槽位的做法）；
- `remount_rebuild_agent=True`：热替换后**热重建 AgentRuntime**
  （applier 向预设 `components` 登记通用组件的「装配型」槽位应置
  True）；默认 False：下一次 run() 生效或仅更新 extras。

完整示例——注册一个通用组件型自定义槽位（与内置 context_store
同一条装配通道）：

```python
from norpagent.arch import SlotSpec, register_slot


def apply_vector_store(reg, layer, value, params, ctx):
    name = "_arch_vector"
    factory = value if callable(value) else (lambda v=value: v)
    reg.register_component("vector_store", name, factory)
    ctx["components"]["vector_store"] = name   # 预设声明组件
    ctx["extras"]["vector_store"] = value


register_slot(SlotSpec(
    name="vector_store",
    description="向量检索组件（自定义装配槽位）",
    protocol="任意实现（注册为 vector_store 通用组件）",
    string_semantics="literal",
    applier=apply_vector_store,
    remount_rebuild_agent=True,     # 热替换后热重建，组件立即生效
))

npa(vector_store=MyVectorStore())    # 装配：engine.agent.components["vector_store"]
npa.remount(vector_store=Other())    # 热替换：AgentRuntime 热重建
```

保护与校验规则：

| 规则 | 说明 |
|---|---|
| 内置 18 槽位受保护 | 不可注册 / 覆盖规格 / 注销（框架结构契约：引擎、前端、文档引用）。它们的**值**随时可 `npa.remount` 热替换 |
| 槽位名合法性 | 合法 Python 标识符（`npa()` 关键字参数），不能是关键字，不能是 `prompt` / `config`（launch 特殊键） |
| 重复名 | 抛 `SlotError`；`register_slot(spec, replace=True)` 热替换同名自定义槽位的规格（默认地址 / 语义 / applier / 重建标志） |
| 非法规格 | 非 callable applier、非法 `string_semantics` 抛 `SlotError`；失败的 replace 不破坏旧规格 |
| 注销 | `unregister_slot(name)` 注销自定义槽位并返回规格；此后 `npa.remount(该槽位)` 报未知槽位，`npa(该键=...)` 回落为任务参数；已装配实现保持原状 |
| 晚注册 | 引擎启动后注册的槽位：`layer.connect()` 幂等补齐（只连接缺失槽位），或直接 `npa.remount(槽位=值)` 走全管线 |

顶层 API：`npa.register_slot` / `npa.unregister_slot` /
`npa.SlotSpec` / `npa.SLOT_SPECS` / `npa.is_builtin_slot` /
`npa.snapshot_slots`；槽位表操作线程安全（RLock 保护，装配 / 热挂载
按快照迭代）。

---

### 3.9 任务级槽位注入：submit(slot_overrides=...)

`npa()` 启动装配与 `npa.remount()` 热挂载都是**全局**维度：换一次
影响所有后续任务。任务级槽位注入是第三个维度——**单次任务**执行
期间临时覆盖任意槽位实现，不影响全局配置、不阻塞其他在途任务：

```python
import norpagent as npa

engine = npa(preset="standard")

# 单任务：临时换模型 + 换工具
r = engine.submit(
    "分析这段代码",
    slot_overrides={
        "model": "anthropic",
        "tools": ["run_python", "file_read", "echo"],
        "sandbox": "isolated_python",
        "max_steps": 64,          # 非槽位键：自动回落为任务参数
    },
)
```

#### 3.9.1 语法与键全集

`engine.submit(text, session_id=None, task_params=None, slot_overrides=None)`
（顶层 `npa.submit(...)` 同样支持）。`slot_overrides` 的键与 `npa()` 的
槽位参数完全一致（14 个可任务级覆盖的键）：

| 键 | 任务级语义 | 生效时机 |
|---|---|---|
| `model` | 换本次任务的模型提供者（已注册名 / 地址 / 实例） | 本次 run 的模型调用 |
| `tools` | 换本次任务的工具集（已注册名列表 / 地址 / Tool 实例 / {名: 实例} 映射） | 本次 run 的 schema 与工具执行 |
| `sandbox` | 独立临时沙箱（已注册名 / 地址 / 实例），任务结束即 close | 本次 run 的工具执行 |
| `session` | 独立临时会话存储（已注册名 / 地址 / 实例 / `{"name": ..., "persist": True}`），默认不污染全局会话表 | 本次 run 的 L4 会话 |
| `scheduler` | 独立临时调度器（已注册名 / 地址 / 实例），任务结束即 close | 本次 run 的子任务提交 |
| `hooks` | 任务期钩子订阅（{钩子名: 回调} 或 callable(registry)），任务结束退订 | 本次 run 全生命周期 |
| `security` | 任务期安全策略（级别 / dict / SecurityContext / callable），任务结束恢复原策略 | 本次 run 的审批 / 防护 |
| `agent_runtime` | 为本次任务启动独立 Runtime 实例，执行完即销毁（不影响引擎默认 Runtime） | 本次任务 |
| `context_store` / `project_manager` | 临时通用组件（已注册组件名 / 地址 / 实例），任务结束即 close | 本次 run 的 ctx.components |
| `async_loop` | 本次任务在独立临时事件循环上执行（不与主循环争抢工作池） | 本次任务 |
| `logger` / `storage` / `error_handler` | 注入本次任务的参数上下文（params），供组件工厂与钩子读取（见 3.9.5） | 本次 run |

值形态与 `npa()` 槽位完全一致：已注册名引用 / 模块地址（`pkg.mod[:attr]`，
含 `;key=value` 子句）/ 工厂 / 实例，解析失败抛 `AddressError`。

**非槽位键自动回落为任务参数**：`slot_overrides` 里的键不在上述
14 键内时（如 `max_steps` / `task_timeout` / `mock_script`），自动并入
`task_params` 透传给 Agent 循环——与 `npa()` 的「槽位键拆分、其余
透传参数」同一条数据通路，因此 `slot_overrides={"max_steps": 64}`
这样的写法开箱即用。

**不可任务级覆盖的键**：`frontend` / `ui` / `plugins` / `preset` 是
进程级或引擎级结构（输入输出外壳、渲染器、插件加载器、组件组合
基线），不属于单次任务的覆盖边界，传入会回落为任务参数（不会报错，
但也不产生槽位覆盖效果——请改用 `npa.remount`）。

#### 3.9.2 优先级：任务级 > remount > 启动装配 > 预设

| 层级 | 来源 | 优先级 |
|---|---|---|
| 1 | `submit(slot_overrides=...)` | 最高 |
| 2 | `npa.remount(slot=...)` | 次高 |
| 3 | 启动时 `npa(slot=...)` | 次低 |
| 4 | 预设 Preset 声明 | 最低 |

任务级覆盖在 **submit() 时刻拍快照**，后续的全局 `npa.remount` 不会
影响在途任务（3.9.3）。这与「Drain + remount」形成互补：不想等
排水就覆盖，不想覆盖就排水后再 remount。

#### 3.9.3 实现边界与隔离语义

实现边界（不改内核循环，只加一层解析）：

1. `AgentRuntime.run()` 入口接收 `slot_overrides` 字典；
2. 为本次任务创建槽位快照层（`_TaskSlotLayer`），存储在
   `TaskContext`（`ctx.task_slot_layer` / `ctx.slot_overrides`）中；
3. `run()` 生命周期内所有组件解析路径（model / tools / sandbox /
   session / scheduler / context_store / project_manager）**优先查
   任务层**，未覆盖时回落运行时默认；
4. 任务结束后任务层随 `RunResult` 一起释放（`finally` 兜底）：
   临时沙箱 / 会话 / 调度器 / 组件全部 `close()`，任务期钩子订阅
   退订，临时安全策略卸载并恢复原 `registry.security`——不留残余
   状态。

**与全局 remount 的关系（隔离语义）**：

| 场景 | 全局槽位 | 任务覆盖 | 该任务看到的 | 其他任务看到的 |
|---|---|---|---|---|
| 无覆盖 | model=A | — | model=A | model=A |
| 覆盖 model | model=A | model=B | model=B | model=A |
| 覆盖后热重建 | model=A | model=B | model=B（该任务仍然用自己的快照） | model=C（新任务） |
| 覆盖后取消 | model=A | 任务结束 | — | model=A |

关键语义：任务级覆盖在 submit() 时刻拍了一张槽位快照，后续全局
remount 不影响在途任务。

**agent_runtime 覆盖**：为本次任务启动一个独立的 Runtime 实例
（按与 `_build_agent` 相同的工厂调用约定构造：registry / preset /
ui / task_params / layer / config 按签名裁剪注入），执行完即销毁，
引擎的默认 Runtime 不受影响。注意：子运行时与默认运行时共享同一
事件总线与渲染器，任务事件可能被两者各自订阅的渲染器各渲染一次
（与 `run_task` 子 Agent 行为一致，属共享总线的既有特性）。

**session 覆盖**：本次任务的对话历史写入独立临时会话存储，不污染
全局会话表——除非显式 `persist=True`：

```python
# 临时会话：全局会话表不出现该会话
engine.submit("hi", slot_overrides={"session": "memory"}, session_id="s1")

# 持久化：任务结束后把本次历史回写全局会话表
engine.submit("hi", slot_overrides={
    "session": {"name": "memory", "persist": True},
}, session_id="s2")
```

注意：落盘型会话（如 `sqlite`）构建的是独立实例，但若未指定独立
库文件（地址式 `...;path=...`），记录仍写入默认库文件——需要完全
隔离请用地址式或实例值。

#### 3.9.4 与多智能体编排的关系

把多智能体理解为「多个任务独立配置不同角色」，任务级槽位注入就是
最干净的实现——三个任务并发，各自用不同的模型 + 工具，互不干扰：

```python
import threading

futures = []
for key, ov in [
    ("撰写方案", {"model": "claude", "tools": ["write"]}),
    ("代码审查", {"model": "deepseek", "tools": ["read"]}),
    ("执行部署", {"model": "mock", "tools": ["exec_cmd"]}),
]:
    t = threading.Thread(
        target=lambda k=k, o=ov: engine.submit(k, slot_overrides=o),
    )
    t.start()
    futures.append(t)
for t in futures:
    t.join()
```

每个任务在 submit 时刻独立拍快照：并发任务各自的 model / tools /
session 覆盖互不影响，也互不影响全局配置。

#### 3.9.5 并发与边界注意事项

- **零注册表污染**：任务级 model / 工具实例由快照层直接持有，不
  `register_*` 到注册表；任务结束引用即释放。并发任务同名工具各自
  持有自己的实例，互不覆盖。
- **hooks / security 是任务期临时状态**：任务开始订阅 / 安装，任务
  结束（含异常路径）退订 / 恢复。任务级 security 的 callable 形式
  由调用方自行管理 `registry.security`（框架无法追踪其内部行为）；
  字符串 / dict / SecurityContext 形式自动恢复。
- **logger / storage / error_handler 的语义是参数注入**：这三个键
  的任务级覆盖注入 `params`（组件工厂 ctx、钩子 payload 可见），
  **不替换引擎全局引用**——避免并发任务互踩引擎级对象。
- **并发覆盖安全**：快照层是每任务独立实例，线程安全；同一运行时
  上任意数量的并发任务各自带自己的槽位快照，互不影响。
- **提交失败语义**：任务级覆盖的解析（地址加载等）发生在 run()
  入口（工作线程内），解析失败抛 `AddressError` / `ComponentError`
  由 submit 阻塞返回处冒泡（与普通任务异常一致）。

---

## 第 4 章　事件循环系统：norpagent.nasyncio()

### 4.1 循环系统独立架构函数

事件循环决定任务调度方式：任务运行的线程、中断方式、唤醒方式。
NorpAgent 将循环系统提供为独立架构函数：

```python
import norpagent as npa

loop = npa.nasyncio()                       # 默认循环（自研 nasyncio 核心）
loop = npa.nasyncio("myapp.loop:create")    # 自定义循环
```

它与槽位等价：

```python
npa(async_loop="myapp.loop:create")   # 等价于 npa.nasyncio("myapp.loop:create")
```

`npa.nasyncio()` 的返回值是一个 **LoopRuntime**（协议见下）。
默认实现运行的调度核心是库内置的**自研 nasyncio 事件循环**
（`norpagent.nasyncio`，原 nasync_io，已打包进库）——**不依赖、
不 import 标准 asyncio**（声明与原因见 4.7）。如需使用其他事件
循环实现，实现 LoopRuntime 协议并为 `async_loop` 槽位填入地址
即可，无需修改框架核心代码。

> 顶层 `norpagent.nasyncio`（即 `npa.nasyncio`）绑定的是自研核心
> **模块**（可调用）：`npa.nasyncio()` 返回 LoopRuntime 默认实现；
> `npa.nasyncio.EventLoop` / `Future` / `Task` 直接访问核心类型；
> `import norpagent.nasyncio` 得到同一个核心模块。架构函数本体在
> `norpagent.loops.nasyncio`。

### 4.2 LoopRuntime 协议

```python
class LoopRuntime(Protocol):
    name: str
    def start(self) -> None: ...          # 启动循环（通常内部专用线程 run_forever）
    def stop(self) -> None: ...           # 请求停止（线程安全）
    def is_running(self) -> bool: ...     # 是否仍在运行
    def join(self, timeout=None) -> None: ...   # 等待循环线程退出
    def submit(self, fn, *args, **kwargs) -> Any: ...
        # 在循环上下文中执行同步函数 fn 并阻塞返回其结果
```

引擎（`norpagent.runtime.engine.NorpEngine`）只通过这个协议与循环交互，
不 import 任何具体循环实现。

### 4.3 默认实现：NasyncioLoopRuntime（自研 nasyncio 核心）

默认实现基于库内置的**自研 nasyncio 事件循环**（不依赖标准
asyncio）：独立线程跑 `norpagent.nasyncio.EventLoop`（run_forever），
`submit()` 把同步函数交给**自有守护工作池**执行并等待结果（不用
标准线程池的原因见 4.6 与 4.7）。

配置项（嵌入式 / 高并发调参，详见第 14 章）：

| 配置 | 说明 | 默认 |
|---|---|---|
| `max_workers` | 守护工作池线程数 | `max(4, cpu_count)` |
| `poll_interval` | submit/run_async 完成轮询间隔（秒） | `0.05` |

经 `npa(config={"loop": {"max_workers": 8}})` 传入（或环境变量
`NORPAGENT_MAX_WORKERS` / `NORPAGENT_SUBMIT_POLL`；等价写法
`npa.nasyncio(max_workers=8)` 与 `npa(async_loop="norpagent.loops.nasyncio:NasyncioLoopRuntime")`
构造时同源）。

```python
loop = npa.nasyncio()
loop.start()
result = loop.submit(lambda: 1 + 1)   # → 2
loop.stop()
loop.join()
```

`run_async(coro)` 可选能力把协程经自研核心的
`run_coroutine_threadsafe` 提交到循环线程执行并阻塞返回结果
（引擎默认走 submit()，供自定义协程入口使用）。

### 4.4 自定义循环示例

```python
# myapp/simple_loop.py —— 循环实现示例（同步直跑，可用于测试或嵌入式场景）
class SimpleLoop:
    name = "simple"

    def __init__(self, **kw):
        self._running = False

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def is_running(self):
        return self._running

    def join(self, timeout=None):
        pass

    def submit(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)   # 同步直接执行


def create(**kw):                    # 模块级工厂（地址 "myapp.simple_loop" 自动命中）
    return SimpleLoop(**kw)
```

接入：

```python
import norpagent as npa

npa(async_loop="myapp.simple_loop", prompt="hi",
   frontend="norpagent.frontends.headless:HeadlessFrontend")
while True:
    if npa.stop():
        break
```

### 4.5 跨线程桥接注意事项（自研核心已内置修复）

**事项一（自研核心已修复）**：标准 asyncio 的 `Future.result()` 不是
线程安全的阻塞等待，跨线程 `add_done_callback()` 在 future 已完成时
走 `loop.call_soon`（只塞 `_ready` 队列不写自管道），循环阻塞在
selector 上就收不到唤醒、等待方挂起。库内置的自研核心
（`norpagent.nasyncio.Future`）把这两个坑都修掉了：完成通知在任意
线程发生都会走 `call_soon_threadsafe`（写自管道立即唤醒循环）。
默认运行时的 `submit()` 仍采用「执行线程写结果 +
threading.Event 置位」模式——submit 任务可能长时间阻塞，放在守护
工作池里与循环彻底解耦更稳（与是否 asyncio 无关）。

**事项二（run_async 的跨线程等待）**：`NasyncioLoopRuntime.run_async`
经自研核心的 `run_coroutine_threadsafe` 把协程提交到循环线程
（内部 call_soon_threadsafe + 自管道唤醒，无唤醒竞态），等待用
concurrent.futures.Future 的 done 回调 + 轮询 Event 置位（回调由
concurrent.futures 保证在结果写入线程内同步触发）。注意
`run_async` 不能在循环线程内调用（阻塞等待会卡死循环），此时
请直接 `await` 协程或改用 `submit()`。

规则：跨线程协调使用「执行线程写结果 + threading.Event 置位」，
循环线程不作为唤醒路径上的必要环节。

### 4.6 Ctrl+C 与任务取消语义

#### 4.6.1 问题：主线程不在事件循环入口里，Ctrl+C 为什么可能失灵

`npa()` 启动后主线程只做生命周期轮询（`npa.stop()`），真正的工作线程
在后台执行任务，调用方（如控制台 REPL 的主线程）阻塞在
`loop.submit()` 的等待上。两条信号链路上的坑：

1. **Windows 上一次性 `Event.wait()` 收不到 Ctrl+C**：SIGINT 以
   pending interrupt 的形式投递到主线程，只在**字节码边界**被检查；
   主线程阻塞在 `Event.wait()`（底层 `WaitForSingleObject` 无限等待）
   时永远不会回到字节码边界，Ctrl+C 形同虚设。
   **解法**：`NasyncioLoopRuntime.submit()` 改为**轮询等待**（每
   ≤`poll_interval` 秒经过一次字节码边界，默认 0.05s——0.9 起由
   0.2s 收紧，任务完成感知延迟更低；嵌入式可调大），Ctrl+C 即刻
   以 `KeyboardInterrupt` 冒出。
2. **卡在阻塞 I/O 里的工作线程杀不死，进程僵住**：SIGINT 只到主线程，
   工作线程若卡在沙箱 `subprocess` / HTTP 请求里，只能等它自己超时；
   更糟的是标准线程池（ThreadPoolExecutor，asyncio 的默认执行器
   也是如此）的工作线程被 CPython 登记在 `threading._threads_queues`，
   解释器退出时会被**强制 join**——任务不结束进程就退不出去。
   **解法**：工作池用裸守护线程（退出不 join）；同时把「取消」信号
   显式传给任务执行体（见 4.6.2），让它尽早自行退出。

#### 4.6.2 取消信号：contextvars + 取消事件

`NasyncioLoopRuntime.submit()` 给每个任务包进一个带取消事件的
contextvars 上下文（`norpagent.loops.cancel`），执行体内随时可查：

```python
from norpagent.loops.cancel import cancel_requested, current_cancel_event

def my_tool(args, ctx):
    for chunk in fetch_stream(...):      # 长任务 / 长流式读取
        if cancel_requested():           # Ctrl+C / 引擎停止 → True
            return ToolResult(output="任务已取消", success=False)
```

触发路径（置位取消事件）：

| 触发 | 时机 | 行为 |
|---|---|---|
| `KeyboardInterrupt` | submit 等待方收到 Ctrl+C | 置位本任务取消事件并冒泡异常 |
| `loop.interrupt()` | `engine.request_stop()` 第一步 | 置位全部在途任务取消事件 |
| `loop.stop()` | 停止循环 | 同上（内部调用 interrupt） |

内置组件对取消的响应（0.7.0 起）：

- **PTC 沙箱**（isolated_python）：执行循环每 ≤0.5s 检查一次，
  取消时立即强杀子进程并返回 `exit_code=-1`（stderr 注明「任务已取消」）；
- **池化沙箱**（pooled）：`run_shell` 分片等待（每 ≤0.5s 检查），
  取消时杀进程树并标记实例损坏；
- **模型调用**：`params["_cancel_event"]` 在 call_timeout=0 时同样注入
  （原先只有超时路径有），openai_compat 流式循环每 chunk 检查一次；
- **Agent 主循环**：每轮步骤边界检查 `cancel_requested()`，
  以 `stopped`（on_task_stopped）收尾。

取消事件仅「建议」执行体退出；若任务卡在不可中断的系统调用里
（如 DNS 解析、D 状态进程），最终兜底仍是各组件的自身超时
（SDK 连接超时 / call_timeout / ptc_timeout），进程退出则由
守护线程保证不被阻塞。**注意：守护工作池本身没有任务执行时间预算
与池级看门狗**，任务卡死会占满工作池——边界与兜底矩阵见 4.6.4。

#### 4.6.3 线程边界说明：什么进循环、什么不进

`norpagent.nasyncio()` 是 **async_loop 槽位的架构函数**；其默认实现
（NasyncioLoopRuntime）运行库内置的自研 nasyncio 事件循环。全库所有
任务调度（engine.submit → loop.submit）都经它走协议。剩下的裸线程
是**刻意的阻塞 I/O 泵**，不应进事件循环：

| 线程 | 职责 | 为什么不用循环线程 |
|---|---|---|
| `norpagent-loop-pool-*` | 执行 submit 的同步任务 | 任务本体可能阻塞（沙箱/HTTP），放循环线程会卡死整个循环 |
| `norpagent-nasync-loop` | 跑自研 nasyncio 事件循环 | 循环本体 |
| 沙箱管道 reader（PTC/pooled/插件宿主） | 读取子进程 stdout/stderr | 阻塞管道读取，不可中断 |
| `norpagent-webui` / 请求线程 | HTTP 服务与请求 | socketserver 自身的线程模型 |
| `norpagent-model-*` | call_timeout 硬中断看守 | 限时 join，超时即弃 |

规则：**计算与调度进循环（可替换），阻塞 I/O 用守护线程泵
（不可取消但也不阻塞退出）**。替换 `async_loop` 槽位即可整体换掉
循环系统（协议见 4.2），无需改动框架其他部分。

#### 4.6.4 守护工作池的队列语义与卡死兜底（边界如实说明）

`NasyncioLoopRuntime` 的守护工作池（`_DaemonPool`）语义边界：

- **队列无界、无拒绝策略**：内部是 `queue.Queue()`（无 maxsize），
  `submit_nowait` 用 `put_nowait` 入队——永不阻塞、永不抛 `Full`。
  池打满时新任务**无限堆积**在队列里，调用方的 `submit()` 在
  `done.wait(poll_interval)` 轮询中无限等待，延迟无上限（不快速失败）；
- **取消是协作式的**：取消事件只在执行体主动检查的边界生效（4.6.2），
  两类场景打断不了——① 卡在 C 扩展纯计算里（如 `re` 正则回溯），
  取消事件只在字节码边界可见；② 自定义工具直接 `Popen + communicate`
  （非沙箱路径）没有分片检查与杀进程树，卡住即卡住；
- **单任务卡死 → 吞吐归零**：每个 worker 一次只跑一个任务，无任务
  执行时间预算、无线程弃置、无看门狗；若某任务卡死占满工作池，后续
  submit 全部堆积，业务侧吞吐趋近于 0——没有额外线程垫底。

**现有兜底先例（「时间预算 + 弃置线程」模式）**：

| 场景 | 兜底机制 |
|---|---|
| 模型调用 | `_call_model_with_timeout`：worker 线程 + `join(timeout)`，超时弃置为孤儿线程（daemon，每 run 过滤回收） |
| 引擎停止 | `request_stop`：关闭任务 `t.join(timeout=5.0)`，超时在当前线程 `_close()` 兜底 |
| PTC / pooled 沙箱 | 执行循环每 ≤0.5s 分片检查取消事件，超时 / 取消强杀进程树 |
| 工作池任务（裸工具 / 用户任务） | **无**——无超时预算，卡死即占池 |

**演进建议（roadmap，当前未实现）**：池级引入「任务执行时间预算」——
worker 内设 deadline 看门狗，超时置位取消事件 + 标记任务弃置 + 强杀
关联沙箱进程（复用模型调用超时的弃置线程模式）；池级可选改为有界队列
或 submit 超时快速失败（拒绝新任务而非无限堆积）。嵌入式场景建议先
把任务拆小 + 收紧组件自身超时（call_timeout / ptc_timeout），不依赖
池级兜底。

### 4.7 明确声明：norpagent 不依赖标准 asyncio，调度核心拥抱自研 nasyncio

**声明**：0.8 起 norpagent 库内**零 `import asyncio`**。默认事件
循环核心是打包进库的自研异步 IO 库 `norpagent.nasyncio`（原
nasync_io，v2.0.0），底层只依赖 Python 标准库的**非 asyncio**
模块：`threading` / `queue` / `heapq` / `selectors` / `socket` /
`concurrent.futures` / `subprocess` / `os` / `time`。全库可用
`grep -R "import asyncio" norpagent/` 验证为空。

**为什么要拥抱自研 nasyncio、摆脱标准 asyncio**：

1. **调度、取消、跨线程唤醒语义完全由库内代码定义（掌控力）**。
   标准 asyncio 存在公认的语义坑，例如：
   - `Task.cancel()` 非线程安全（直接操作循环线程的 ready 队列）；
   - 跨线程对已完成 Future `add_done_callback()` 走 `call_soon`，
     不写自管道，循环阻塞在 selector 上收不到唤醒，等待方挂起；
   - 没有对外的「取消主任务」入口，外部线程无法强制中断正在
     await 的协程（停止延迟取决于当前操作，可达数分钟）。
   自研核心逐项修复：`Task.cancel()` 跨线程安全；Future 完成通知
   自动走 `call_soon_threadsafe` 写自管道；`EventLoop.abort_main()`
   提供线程安全的即时停止。
2. **依赖面压缩到可审计**。事件循环的全部行为（trampoline 调度、
   定时器堆、socketpair 自管道唤醒、取消穿透）都是库内自己写的
   代码，审计面 = 自研核心一个文件；不引入标准 asyncio 的
   内部实现细节与版本差异（各 Python 版本 selector 行为不一）。
3. **退出语义可控**。不用标准线程池执行 submit：ThreadPoolExecutor
   （含 asyncio 默认执行器）的工作线程被 CPython 登记在
   `threading._threads_queues`，解释器退出时被强制 join——任务卡在
   沙箱 subprocess / HTTP 里进程就僵住。默认运行时用裸守护线程池
   + 自管道唤醒，Ctrl+C 后进程即刻收尾（4.6.1）。
4. **API 语义对齐、迁移零成本**。自研核心提供与 asyncio 用法一一
   对应的同名 API（`EventLoop` / `Future` / `Task` / `Event` /
   `Lock` / `Condition` / `sleep` / `wait_for` / 子进程封装 /
   `run_coroutine_threadsafe`），熟悉 asyncio 的代码把
   `import asyncio` 换成 `import norpagent.nasyncio` 即可移植，
   且 `CancelledError` / `TimeoutError` 语义保持一致。
5. **自研核心独立可用**。`norpagent.nasyncio` 本身是一个可独立
   使用的微型异步库（原 nasync_io 打包进库），可以脱离
   norpagent 框架单独 import、单独跑循环；框架只是通过
   LoopRuntime 协议把它接进 `async_loop` 槽位。

**兼容性**：0.7 旧地址 `norpagent.loops.std_asyncio:StdLoopRuntime`
保留为兼容垫片（重导出同一实现，不 import asyncio），历史代码
不失效；新代码使用 `norpagent.loops.nasyncio:NasyncioLoopRuntime`
（见 4.3）。

```python
import norpagent as npa
import norpagent.nasyncio as core  # 自研核心模块（可调用）

print(core.__version__)          # 2.0.0
loop_rt = npa.nasyncio()          # LoopRuntime 默认实现（同 core()）
print(loop_rt.name)              # nasyncio
print(core.EventLoop)            # 自研事件循环类
```

**并存使用（2026-09-12 反馈轮补充声明）**：不依赖不等于冲突——标准库 `asyncio`（及其生态协程客户端）与自研 `norpagent.nasyncio` **可以在同一进程内同时使用**：norpagent 的任务调度只走 `async_loop` 槽位上的 nasyncio；用户在自己的代码中使用标准 asyncio（含 `asyncio.run`）不受影响。二者相遇的边界只有两处且有明确语义：① 跨线程协作请使用线程安全 API（nasyncio 侧 `run_coroutine_threadsafe` / `LoopRuntime.submit` / `EventLoop.submit`），不要跨库直接等待对方循环内部对象；② 事件循环替换是显式行为（`async_loop` 槽位 / `npa.nasyncio(...)`），不存在隐式接管。简言之：**nasyncio 不是 asyncio 的替代式接管，共存零冲突、可各跑各的循环**。

---

## 第 5 章　前端体系

### 5.1 两层结构：frontend（外壳）与 ui（渲染器）

前端体系分两层：

| 层 | 槽位 | 协议 | 职责 |
|---|---|---|---|
| 外壳 | `frontend` | `Frontend` | 从哪里读输入、何时启动/停止、把输入交给引擎 |
| 渲染 | `ui` | `UIAdapter` | 订阅事件总线，把 Agent 事件渲染成文本/界面 |

一个 frontend 通常会携带一个 ui 渲染器；两者都可以被独立替换。

### 5.2 Frontend 协议

```python
class Frontend(Protocol):
    frontend_id: str
    def attach(self, engine) -> None: ...   # 绑定引擎（engine.submit / engine.request_stop）
    def start(self) -> None: ...            # 启动（内部自建后台线程，不得阻塞）
    def stop(self) -> None: ...             # 停止（线程安全）
    def is_alive(self) -> bool: ...         # 存活查询
```

### 5.3 内置前端

| 前端 | 地址 | 说明 |
|---|---|---|
| Web（默认） | `norpagent.frontends.web:WebFrontend` | HTTP + SSE，无第三方依赖；页面 = front.html（多标签会话/流式渲染/设置/插件面板），独立入口 `/flow` = norp-flow.html 模块流程编排；控制台打印 `listening on http://127.0.0.1:8787/`；可配 `;port=9000`、`;html=自定义主页`、`;flow_html=自定义流程页`（槽位挂载参数，见 5.4）或 `npa(port=9000, language="zh_CN")`；frontend 槽位值可直接给 `.html` 路径（HTML 路径直挂，v0.9） |
| 控制台 REPL | `norpagent.frontends.console:ConsoleFrontend` | 显式指定；`/exit`（或 `exit`/`quit`/`exit()`）退出，`/reset` 新会话；在 Python 交互式解释器中自动切换同步模式 |
| 无头 | `norpagent.frontends.headless:HeadlessFrontend` | 纯 API；`prompt` 模式默认；输出（正文/工具/结果）打印到 stdout |

### 5.4 Web UI 行为与配置持久化

Web UI 的行为与配置项：

| 能力 | 说明 |
|---|---|
| 配置持久化 | 设置面板保存后落盘 `~/.norpagent/webui_config.json`（`NORPAGENT_WEBUI_CONFIG` 可覆盖；`WebUI(config_path=...)` 可指定，传 `None` 关闭）。磁盘加载只接受 `DEFAULT_CONFIG` 白名单键，未知键丢弃。0.9 起**磁盘加载延迟到 `start()`**：构造 WebUI 不再触发任何磁盘 I/O（嵌入式 / 只读根文件系统友好），显式构造参数 > 磁盘值 > 默认值的优先级不变 |
| 页面防缓存 | 页面响应带 `Cache-Control: no-store`，浏览器每次刷新获取最新 front.html；服务端页面字节读入内存缓存（0.9：每次 GET / 不再读盘），缓存按资源文件 mtime/size 签名校验——**物理替换库内 HTML 文件后刷新即自动生效**，命中缓存时仅一次 stat 校验 |
| 页面挂载（html / flow_html 参数） | `/` 路由默认页面与 `/flow` 模块流程页面都可整体替换：`html` / `flow_html` 接收**文件路径**或 **HTML 内容**（strip 后以 `<` 开头视为内容，否则视为文件路径）；文件不存在时构造抛 `ValueError`（快速失败，不静默回落）。无需物理覆盖 `norpagent/builtin/ui/assets/front.html` / `norp-flow.html`。运行中可用 `mount_page(page, html)` 直接换页（HTTP 服务不重启、端口不变），`mount_page(page, None)` 卸载回落 |
| 断连处理 | 客户端断连（WinError 10053 / EPIPE 等）静默处理，内部错误记录 DEBUG 日志；SSE 连接断开 ≤1s 内被非阻塞探测回收（0.9，防线程堆积） |
| SSE 背压（0.9） | 每连接有界事件缓冲 + 帧批量写出，慢客户端自动降级，超高并发下内存有上界——详见第 14.3 节 |
| 端口顺延 | 绑定失败（含 Windows 10013 监听占用）时向后顺延最多 10 个端口，以实际端口为准 |
| 请求体防护 | 负数 Content-Length 按无请求体处理；超过 1MB 拒收 |
| 关闭幂等 | `shutdown()` 幂等 + 同线程死锁防护，可跨线程调用；`block_on_close=False` 停机不等连接关闭（0.9） |
| 事件路由 | 事件 sid 解析优先 `submit()` 登记的原始浏览器会话 id；会话管理器支持指定 id 创建（`create_session(title=..., session_id=...)`），内核续接会话时 id 与浏览器标签页一致 |

```python
import norpagent as npa
from norpagent.builtin.ui.web import WebUI
from norpagent.frontends.web import WebFrontend

# 自定义配置持久化位置（默认 ~/.norpagent/webui_config.json）
ui = WebUI(port=9000, config_path="./my_app/webui.json")
# config_path=None 关闭磁盘读写
ui2 = WebUI(port=9000, config_path=None)
```

**页面挂载（html / flow_html 参数）四种写法等价：**

```python
import norpagent as npa

# 1. 槽位地址子句（;key=value，推荐）
npa(frontend="norpagent.frontends.web:WebFrontend;html=/path/to/my.html")
npa(frontend="norpagent.frontends.web:WebFrontend;flow_html=/path/to/flow.html")

# 2. 构造函数直接传（WebFrontend / WebUI 均支持）
npa(frontend=WebFrontend(html="<html><body>我的界面</body></html>"))
npa(frontend=WebFrontend(flow_html="/path/to/flow.html"))

# 3. 配置字典
npa(config={"web": {"html": "/path/to/my.html", "flow_html": "/path/to/flow.html"}})

# 4. 运行时参数透传
npa(html="/path/to/my.html", flow_html="/path/to/flow.html")

# 5. HTML 路径直挂（v0.9）：frontend 槽位值本身就是 .html 路径，
#    等价于写法 1 的 html= 子句
npa(frontend="/path/to/my.html")

# 文件路径不存在时构造报错（快速失败，不静默回落默认页面）
# ValueError: WebUI html 挂载参数既不是 HTML 内容（以 '<' 开头）也不是存在的文件: ...
```

**运行中热替换页面（HTTP 服务不重启、端口不变）：**

```python
eng = npa()                                  # 或 npa.current() 取运行中的引擎

# 方式一：remount 页面热替换键（推荐，v0.9）
npa.remount(flow_html="/path/to/flow.html")  # /flow 立即换页
npa.remount(html="/path/to/front.html")      # / 主页面立即换页
npa.remount(flow_html=None)                  # 卸载，回落库内置

# 方式二：frontend 实例 API
eng.frontend.mount_page("flow", "/path/to/flow.html")  # /flow 立即换页
eng.frontend.mount_page("flow", None)                  # 卸载，回落库内置
eng.frontend.mount_page("front", "<html>...</html>")   # / 路由同理
# 等价底层 API：WebUI.mount_page(page, html)
```

**模块流程官方前端 norp-flow.html**：`/flow` 独立入口（拖拽模块 /
beam 连线 / 后端真实执行 / 自动保存），随库发行于
`norpagent/builtin/ui/assets/norp-flow.html`；不挂载时即为官方页面，
挂载 `flow_html` 时整体替换。直接物理替换该文件同样自动生效
（见上「页面防缓存」）。

**仓库根目录 `front.html`（多宿主前端）**：pywebview 桌面协议的前端
已改造为多宿主传输桥架构——浏览器宿主下自动构造
`window.pywebview.api`（fetch + SSE 实现全部方法，并把库事件翻译为
文本事件协议 T:/R:/C:/U:/E:/Q:），桌面宿主原样兼容。可直接挂载：

```python
npa(html="front.html")   # 相对工作目录，库按文件路径读取
```

挂载后聊天 / 会话 / 设置 / 插件面板 / 文件浏览全部走库的 REST API
（契约见 `norpagent/builtin/ui/web.py` 的 do_GET / do_POST）；SSH 远程
与移动端远程控制在库版已剥离，对应 UI 入口自动隐藏、桥方法占位降级。

输入框选择器（第一直觉设计）：

- **模式**：`/api/presets` 列出注册表全部预设（minimal / standard /
  ptc / creative / longrun / embedded），选择后经 config `preset_name` 热切换
  （`engine.remount(preset=...)`，AgentRuntime 热重建；任务运行中禁用，
  `*_arch` 衍生预设不对外展示）；
- **模型**：从 `api_base` 拉取远端模型列表（`/api/models`），选择即
  保存 `model` 并立即生效，附「从 URL 拉取 / 模型设置」入口；
- **推理强度**：点击循环切换 关 / 低 / 中 / 高，即时保存。

调试面板（设置 → Agent 调试）条目化展示版本 / 前端 / 预设 / 模型 /
工具 / 插件 / 会话等字段，原始 JSON 折叠在「原始数据」区。

### 5.5 自定义前端示例

```python
# myapp/tray_frontend.py —— 前端实现示例
import threading

class TrayFrontend:
    """托盘式前端：不读键盘，通过方法调用提交输入。"""

    frontend_id = "tray"

    def __init__(self, **kw):
        self.engine = None
        self.alive = False

    def attach(self, engine):
        self.engine = engine
        self.alive = True

    def start(self):
        self.alive = True

    def stop(self):
        self.alive = False

    def is_alive(self):
        return self.alive

    # 前端自定义能力：应用代码从这里把用户输入交给引擎
    def send(self, text):
        return self.engine.submit(text)
```

接入并驱动：

```python
import norpagent as npa

npa(frontend="myapp.tray_frontend:TrayFrontend", preset="standard")
fe = npa.current().frontend
result = fe.send("你好")        # 引擎在后台循环里执行 Agent
print(result.final_content)
npa.shutdown()
```

### 5.6 UIAdapter 渲染层

```python
class UIAdapter(Protocol):
    ui_id: str
    def on_event(self, event) -> None: ...            # 渲染一个 AgentEvent
    def ask_user(self, question, default="") -> str: ...  # 人工审批/澄清问答
    def notify(self, message, level="info") -> None: ...
```

换渲染器：`npa(ui=MyRenderer())` 或 `npa(ui="web")`（引用注册表已注册名）。

### 5.7 模块流程画布（FLOW）与 FE 前端模块

`/flow` 是独立前端分类「模块流程」：把 Agent 组装过程画成一张画布
（模块 = 方块，端口 = 注册钩子，beam 连线 = 执行链路），RUN 时图被
提交给后端用注册表真实组件拓扑执行。画布自动保存到
`~/.norpagent/flow_graph.json`，刷新 / 重启自动恢复；顶栏
「应用到智能体」开启后，front 聊天任务改按该流程执行（行为热切换）。
详见 `docs/flow.md`。

**FE 前端模块（文件即前端）**：把 `.html / .js / .ts` 文件拖入画布
即注册为前端模块（模块坞「前端 FE」分组），后端托管到
`/fe/<name>`（卡片「↗」新标签页打开）。每个 FE 拥有**独立配置
作用域**（互不干扰，默认值取自「连接设置」全局配置），配置经
`GET/POST /api/fe/config?fe_id=...` 读写，落盘到
`~/.norpagent/fe_configs/<fe_id>.json`。

FE 节点有 **1/2/3 三种形态**（卡片标题栏按钮切换）：

| 形态 | 含义 |
|---|---|
| 1 | 全局设置节点：配置写入「连接设置」（scope=global） |
| 2 | FE 即设置集合：独立配置作用域（scope=fe，默认形态） |
| 3 | 拆散成设置项子卡片：每个配置项一个成员行（可单独拖出 / 就近连线） |

**输入框体系（一切需要输入的地方都是输入框）**：

- FE / 全局设置节点卡片把每个配置项（api_key / api_base / model /
  project_root / plugin_dirs / temperature / max_tokens / max_steps /
  task_timeout / system_prompt / language）渲染成一行
  「IN 端口 · 标签 · 输入框 · OUT 端口」，值直接写在卡片上，
  改完 500ms 防抖自动保存；形态 3 的每个成员行同样是输入框；
- model / tool / sandbox / other 等节点卡片底部带**值输入框带**
  （context / query / code / value 直接编辑）；TR 卡 prompt 输入框、
  PATH 卡路径输入框保持内嵌；
- 模型字段一律是**可手输输入框 + datalist 提示**（flow 连接设置弹窗、
  WebUI 设置弹窗、model 节点实例字段）：远端模型列表拉取失败或
  模型不在列表里时，直接键入任意模型名即可（留空 = 引擎默认）；
- 卡片输入框与右侧节点面板双向同步；beam 连线到设置端口时连线动作
  本身立即生效（写入独立 / 全局配置）。

**画布管理三件套（0.6.8 新增，防画布乱局）**：

- `Alt+左键拖拽` 空白 = **框选**，与框相交的模块全部高亮，`Del`
  批量删除；
- `Ctrl+A` = **全选**，`Del` 批量删除；
- 顶栏 **「清空画布」** = 一键删除全部模块与 beam（确认弹窗
  防误触），确认后立即自动保存；清空后刷新保持空白（后端保存
  空图，加载不再回落示例模板）；
- **误触注入已移除**：双击画布空白注入、单击坞卡片快速注入两个
  入口彻底删除——此前误触产生的 other 节点会被自动保存固化，导致
  「一打开画布就冒出一大堆 other」。现在注入只有拖拽一条途径。

**DeepSeek 模型名**：`deepseek-chat` / `deepseek-reasoner` 已于
2026-07-24 被官方停用，现役为 `deepseek-v4-flash` / `deepseek-v4-pro`。
后端 `list_models` 缓存与 flow 快照（`filter_remote_models`）以及
前端提示列表 / 远端模型坞都会过滤停用名（`RETIRED_REMOTE_MODELS` /
`RETIRED_MODELS` / `RETIRED_REMOTE`），历史缓存不会再把旧名展示出来。

**连接设置弹窗**（flow 顶栏）：立即显示、不被远端模型拉取阻塞；
「拉取模型列表」用表单当前 Key/Base 即时请求（无需先保存）；点击
弹窗外部不关闭（Esc / × / 取消关闭）；输入框失焦自动保存应用。

**智能体工具挂载（0.6.10 新增，模块工具 → front 自动调用）**：

- **配置键**（`DEFAULT_CONFIG`）：`agent_tools`（显式工具全集列表）
  + `agent_tools_explicit`（bool，True = 显式；False = 跟随预设默认集）；
- **写入入口**：① `/flow` 模块坞工具卡的 `AGENT` 徽章（前端调用
  `POST /api/agent/tools {tools, explicit}`）；② WebUI 设置弹窗
  「🧰 智能体工具」勾选清单（经 `save_config` 落 `agent_tools`）。
  `GET /api/config` 返回 `tools_info`（全部工具 + 原生/模块来源）与
  `agent_effective_tools` / `agent_base_tools`，前端据此渲染；
- **热应用**：`WebFrontend._apply_agent_tools()` 把 `preset.tools`
  改写为显式集合（未注册工具名自动过滤）或预设默认集快照
  （`WebFrontend._base_tools`，attach 时捕获）；下一次 `run()` 的
  `registry.tool_schemas(preset.tools)` 即包含模块工具，模型按
  OpenAI function schema 自动调用；
- **重启恢复**：`WebFrontend.attach()` 结束时用已保存配置重新应用
  工具集（不改变既有模型配置行为）；
- **回落语义**：`set_agent_tools` 在显式集合与预设默认集一致时自动
  回落为非显式（`agent_tools=[]`），预设演进自动跟随；
- **快照字段**：`/api/flow/snapshot` 顶层返回 `agent_tools` /
  `agent_base_tools`，驱动 flow 页徽章状态。

---

## 第 6 章　npa() 启动与生命周期

### 6.1 启动代码解读

```python
import norpagent as npa
npa()                    # ①
running = True
while running:
    if npa.stop() == True:   # ②
        running = False
```

① `npa()` —— `norpagent` 模块是可调用的（模块类替换技术）。它等价于
`norpagent.launch()`，内部依次完成：

1. **参数分拣**：关键字参数中与槽位表（18 个内置槽位 + 运行时
   register_slot 注册的自定义槽位）同名的键 → 槽位值；
   其余键 → 任务参数（如 `max_steps` / `task_timeout` / `workspace_root`）；
   特殊键 `prompt`（单次任务文本）与 `config`（字典形式的槽位赋值）；
2. **架构层装配**：`ArchLayer(config, **slots)` → `mount_defaults()`
   （登记各槽位的库内置默认逻辑）→ `layer.connect()`（解析地址、
   调用工厂，得到每个槽位的实现）；
3. **注册表装配**：`build_registry(layer)` 安装内置组件与预设，
   再把槽位覆盖写进最终预设；
4. **引擎启动**：`NorpEngine(layer, registry, preset, loop, frontend, ...)`
   → `engine.start()`：装配 Agent 运行时 → 前端绑定 → 循环线程启动 →
   前端线程启动 → 状态进入 RUNNING；
5. **单例语义**：已有运行中的引擎时，再次 `npa()` 直接返回当前引擎。

② `npa.stop()` —— 生命周期函数。返回 `True` 表示引擎进入 STOPPED
状态（应用已结束，主循环应退出）；没有引擎时也返回 `True`。

### 6.2 引擎生命周期状态机

```
STARTING ──start()──▶ RUNNING ──request_stop()──▶ STOPPING ──▶ STOPPED
```

| 状态 | 含义 | 进入条件 |
|---|---|---|
| STARTING | 装配中 | `npa()` 内部 |
| RUNNING | 接受输入、执行任务 | `engine.start()` 完成 |
| STOPPING | 正在收尾 | `request_stop()` |
| STOPPED | 已结束 | 收尾完成（`npa.stop()` 为 True） |

停止请求的收尾顺序（`NorpEngine.request_stop`）：

1. 前端停止（输入循环退出）；
2. Agent 关闭（释放沙箱/组件，广播 `on_agent_shutdown`——对应 L1 生命周期钩子）；
3. 退订引擎额外订阅的渲染器；
4. 停止循环线程并等待退出；
5. 状态置 STOPPED。

### 6.3 三种运行模式

**主循环模式**（默认 Web 前端）：

```python
npa()                            # 默认前端 = Web（frontend web listening on 127.0.0.1:8787）
while True:
    if npa.stop():
        break
```

浏览器访问打印的地址打开聊天界面（front.html）。使用其他前端时显式指定：
`npa(frontend="norpagent.frontends.console:ConsoleFrontend")`。

**单次任务模式**（`prompt` 给出时自动使用 headless 前端，输出打印到 stdout）：

```python
npa(prompt="总结 README", preset="standard")
while True:
    if npa.stop():
        break
print(npa.current().last_result.final_content)
```

**纯 API 模式**（无头 + 程序主动 submit）：

```python
npa(preset="minimal", frontend="norpagent.frontends.headless:HeadlessFrontend")
eng = npa.current()
result1 = eng.submit("第一个问题")
result2 = eng.submit("追问", session_id=result1.session_id)   # 同一会话续聊
eng.request_stop()
```

> **注意**：`npa()` 不阻塞，引擎在后台线程运行。主线程应当用
> `npa.stop()` 轮询等待（或调用 `npa.current().wait()`）。主线程若直接
> 结束进程，daemon 引擎线程随之退出；库已注册 atexit 兜底清理。
>
> **特例**：显式使用**控制台前端**时，在 Python 交互式解释器
> （`>>>` REPL）里调用 `npa()` 自动切换为**同步模式**——`npa()` 阻塞到
> 用户退出（`/exit`、`exit()`、Ctrl+C 或 EOF），期间无需再写轮询循环。
> 同步模式下主线程独占 stdin。默认 Web 前端在 REPL 中同样适用（后台服务 +
> 页面交互，不阻塞解释器）。

### 6.4 npa() 参数全集

```python
npa(
    # ── 架构槽位（18 个内置，不填 = 默认逻辑；register_slot 注册的
    #    自定义槽位同样在此传参，见 3.8）──
    async_loop=..., agent_runtime=..., model=..., tools=...,
    session=..., sandbox=..., scheduler=..., context_store=...,
    project_manager=..., hooks=..., security=..., plugins=...,
    frontend=..., ui=..., preset=..., logger=..., storage=...,
    error_handler=...,
    # ── 特殊键 ──
    prompt="单次任务文本",          # 跑完自动停止
    config={"slot": value, ...},    # 字典形式的槽位赋值
    # ── 模型快捷参数（model 为内置适配器名时生效）──
    model_name="deepseek-v4-flash", # 远端模型名
    base_url="https://api.deepseek.com/v1",   # 远端服务地址
    api_key="sk-...",               # API Key（也读环境变量）
    # ── Web 前端运行时参数（frontend=web 时透传给 WebFrontend）──
    port=8787,                      # HTTP 端口（被占自动顺延 10 个）
    host="127.0.0.1",               # 监听地址
    open_browser=False,             # 是否自动打开浏览器
    language="zh_CN",               # 界面语言（en / zh_CN）
    html="/path/to/my.html",        # 自定义主页面：文件路径或 HTML 内容
                                    # （替换 / 路由默认页面，见 5.4 节）
    sse_queue_size=1024,            # SSE 每连接缓冲上限（0=不限，0.9）
    sse_queue_policy="drop_oldest", # drop_oldest / drop_newest / unlimited
    # ── 其余键 = 任务参数，透传 Agent 循环 ──
    max_steps=32, task_timeout=0, call_timeout=0,
    workspace_root=..., system_prompt=...,
)
```

`config` 字典的子键约定（0.9，嵌入式 / 高并发调参，详见第 14 章）：

```python
npa(config={
    "loop": {"max_workers": 8, "poll_interval": 0.02},   # 循环工作池与轮询
    "web": {"port": 9000, "sse_queue_size": 2048,        # Web UI 与 SSE 背压
            "sse_queue_policy": "drop_oldest"},
    "preset": "embedded",                                 # 槽位赋值同关键字
})
```

> `preset="embedded"` 且未显式指定 frontend 时，默认前端自动为
> headless（不启动 HTTP 服务，纯 API 模式），见 12.1 与第 14 章。

### 6.5 生命周期与 L1 钩子的对应

引擎状态机与 9 层钩子体系的 L1 层对齐：

| 引擎事件 | 钩子/事件 |
|---|---|
| Agent 运行时构造完成 | `on_agent_init`（L1） |
| 任务提交 | `on_task_start` |
| 引擎停止 | `on_agent_shutdown`（L1） |

生命周期订阅写法：`npa(hooks={"on_agent_init": fn, ...})`
（钩子体系见第 9 章）。

---

## 第 7 章　模型与工具

### 7.1 模型槽位

模型槽位接受：

```python
npa(model="mock")                  # 注册表名（内置 mock / openai_compat / anthropic）
npa(model=MyProvider())            # 实例
npa(model="myapp.model:create")    # 地址（字符串不匹配任何已注册名时按地址解析）
```

ModelProvider 协议（`norpagent.protocols.model`）：

```python
class ModelProvider(Protocol):
    def generate(self, messages, tool_schemas, params) -> ModelOutput: ...
    def stream(self, messages, tool_schemas, params): ...   # 可选：增量产出
```

`stream` 存在时内核优先走流式路径（逐段广播 `on_content`），
否则一次性 `generate`。`params["_cancel_event"]` 是内核注入的
取消事件，适配器应据此尽早退出（硬超时配合）。

### 7.2 工具槽位

三种赋值形态：

```python
npa(tools=["echo", "get_time"])           # 名字列表：引用注册表
npa(tools={"my_tool": MyTool()})          # 映射：注册并启用
npa(tools=[ToolA(), ToolB()])             # 实例列表：按 name 注册
```

Tool 协议（`norpagent.protocols.tool`）：

```python
class Tool(Protocol):
    name: str
    def schema(self) -> dict: ...        # OpenAI function schema
    def run(self, args: dict, ctx: RunContext) -> ToolResult: ...
```

内置工具清单（`install_defaults` 注册）：`echo`、`get_time`、
`run_python`（PTC 沙箱执行）、`file_read / file_write / file_list /
file_delete`（路径安全）、`exec_cmd`（沙箱协议）、`web_search /
web_fetch / web_extract_links`（SSRF 防护）、`context_add / search /
list / delete`（FTS5 上下文库）、`project_status`、`task_submit /
list / status / cancel`（长周期任务协作）。

### 7.3 示例：模型基准测试

minimal 预设使用确定性环境与最简工具集，可用于对比不同模型在
固定输入集上的输出：

```python
import norpagent as npa

for model_name in ("mock", "openai_compat"):
    npa(preset="minimal", model=model_name, prompt="1+1=?",
       frontend="norpagent.frontends.headless:HeadlessFrontend")
    while True:
        if npa.stop():
            break
    r = npa.current().last_result
    print(model_name, r.steps, r.usage.total_tokens, r.final_content[:40])
    npa.shutdown()
```

---

## 第 8 章　会话、沙箱、调度器、上下文与项目

### 8.1 会话

```python
npa(session="memory")     # 进程内（默认）
npa(session="sqlite")     # 持久化到 ~/.norpagent/sessions.db
npa(session=MySessionManager())          # 实例
npa(session="myapp.sessions:create")     # 地址
```

SessionManager 协议：`create_session / get_session / append_message /
history`。跨会话续聊通过 `session_id`：

```python
eng = npa.current()
r1 = eng.submit("记住：我最喜欢蓝色")
r2 = eng.submit("我最喜欢什么颜色？", session_id=r1.session_id)
```

### 8.2 沙箱

```python
npa(sandbox="subprocess")   # 子进程（默认）
npa(sandbox="pooled")       # 池化复用 + 并发上限 + 超时强杀进程树
npa(sandbox="myapp.docker_sandbox:create")
```

Sandbox 协议：`run / close`。`exec_cmd` 工具通过沙箱协议执行，
替换容器/池化沙箱实现无需修改工具代码。

### 8.3 调度器

```python
npa(scheduler="simple")       # 内存队列（默认）
npa(scheduler="persistent")   # 持久化 + 崩溃 resume() 续跑
```

TaskScheduler 协议：`submit / drain / cancel`。`task_*` 工具族供模型
编排长周期任务；`agent.run_task()` 是多智能体编排入口
（子任务可用 `preset_name` 指定不同模式 = 不同子 Agent）。

### 8.4 上下文库与项目管理（通用组件命名空间）

```python
npa(context_store="norpagent.builtin.context:FTS5ContextStore")
npa(project_manager=MyProjectManager())
```

这两个槽位走**通用组件命名空间**（`registry.register_component`），
组件种类开放——可注册新种类组件并在预设里声明，无需修改内核。

### 8.5 基础服务槽位

```python
npa(logger=logging.getLogger("my.app"))       # 日志
npa(storage="./my_data")                       # 持久化根
npa(error_handler=lambda exc, eng: print(exc))  # 错误最后防线
```

`error_handler` 在任务级异常兜底时被调用（签名 `(error, engine)`），
不填则记录到 logger。

---

## 第 9 章　9 层 29 钩子

> 设计原则：**每一个执行结构都必须暴露为 API，并且可以被钩子干预。**
> 每个钩子都是独立的模块级 API；支持自定义钩子、自定义层；零依赖，
> 标准库自带。本章与 `docs/hooks.md`（钩子体系独立文档）配套阅读。

### 9.1 钩子分层与 29 钩子全表

Agent 循环切为 9 层，每层引出钩子：

```
L1 运行时生命周期 ─ L2 任务 ─ L3 输入 ─ L4 会话与历史 ─ L5 消息组装
   ─ L6 步骤 ─ L7 模型调用 ─ L8 工具调用 ─ L9 结果定型
```

29 个钩子全部是 `norpagent.hooks` 下可导入的一等对象
（`from norpagent.hooks import before_model_call, ...`），全表如下：

| 层 | 钩子 | 可变 | 负载键（payload_keys） |
|---|---|---|---|
| L1 运行时 | `on_agent_init` | | preset |
| L1 运行时 | `on_agent_shutdown` | | preset |
| L2 任务 | `on_task_start` | | task_id, session_id, preset, user_input |
| L2 任务 | `on_task_done` | | task_id, session_id, content, steps, context |
| L2 任务 | `on_task_error` | | task_id, error |
| L2 任务 | `on_task_stopped` | | task_id, reason |
| L2 任务 | `on_task_timeout` | | task_id, timeout, kind |
| L3 输入 | `before_input` | ✓ | task_id, user_input, session_id, params |
| L3 输入 | `after_input` | | task_id, user_input, session_id |
| L3 输入 | `on_user_input_required` | | question, default |
| L4 会话 | `before_session_create` | ✓ | session_id, title, params, task_id |
| L4 会话 | `after_session_create` | | session_id, title, task_id |
| L4 会话 | `before_message_append` | ✓ | session_id, message, task_id |
| L4 会话 | `after_message_append` | | session_id, message, task_id |
| L5 组装 | `before_build_messages` | ✓ | system_prompt, session_id, step, task_id, tool_names |
| L5 组装 | `after_build_messages` | ✓ | messages, system_prompt, step, task_id |
| L6 步骤 | `before_step` | ✓ | task_id, step, messages, context, params |
| L6 步骤 | `after_step` | | task_id, step, content, tool_calls |
| L7 模型 | `before_model_call` | ✓ | task_id, step, messages, tool_schemas, params |
| L7 模型 | `after_model_call` | ✓ | task_id, step, output |
| L7 模型 | `on_reasoning` | | task_id, content, stream |
| L7 模型 | `on_content` | | task_id, content, stream, final |
| L7 模型 | `on_event` | | event_type, data, task_id |
| L7 模型 | `on_usage_update` | | task_id, input, output, total |
| L8 工具 | `before_tool_call` | ✓ | task_id, tool_name, args, context |
| L8 工具 | `after_tool_call` | ✓ | task_id, tool_name, args, result, success, context |
| L8 工具 | `on_tool_error` | | task_id, tool_name, error, args |
| L9 定型 | `before_result` | ✓ | task_id, result |
| L9 定型 | `after_result` | ✓ | task_id, result |

带 ✓ 为**可变钩子**（mutating=True）：订阅者可通过返回值改写
数据流，或抛 `HookVeto` 一票否决；其余为观测钩子（emit），
返回值被忽略。每个钩子的完整负载键以 `Hook.payload_keys` 为准
（与 `norpagent.hooks.standard` 中各钩子注释一致）。

### 9.2 三种用法与订阅目标解析

```python
from norpagent.hooks import before_model_call

# 1. 模块级独立 API：不传 system 时落在「进程默认钩子系统」
before_model_call.subscribe(log_request)                # 默认系统（私有总线）
before_model_call.subscribe(log_request, system=reg)    # 指定 Registry

# 2. 运行时视图：与 registry.hooks 同一总线（多实例推荐）
agent.hooks.before_model_call.subscribe(log_request)

# 3. 槽位批量订阅：npa(hooks={"before_model_call": my_fn})
```

- 模块级 `Hook` 对象的 `subscribe / unsubscribe / emit / intercept`
  都需要一个 `system` 定位总线，可传 `HookSystem / EventBus /
  Registry / AgentRuntime`（`_resolve_bus` 统一解析）；
  **缺省时落在进程级默认系统**（`hooks.get_default_system()`，
  自带独立私有总线）——它与 `npa()` 引擎的总线不是同一条。
  给独立 Registry 使用时**务必显式传 system**（每个 Registry
  自带私有总线，保证多实例隔离），否则订阅挂到默认系统上，
  收不到引擎事件；
- `agent.hooks.before_model_call` 返回 `BoundHook`（绑定到该
  引擎总线的钩子），四个方法无需再传 system；
- `npa(hooks={...})` 槽位（literal 语义）：dict 的键是事件名、
  值是订阅者，装配期统一挂到引擎总线上；热挂载
  `npa.remount(hooks=...)` 时先退订上次的架构级订阅再重挂，
  **不叠加**。槽位值也可以是 `callable(reg)` 工厂：先调用、
  返回 dict 后再订阅。

### 9.3 可变钩子的返回语义与 HookVeto

可变钩子经 `EventBus.intercept` 分发：**按订阅顺序依次调用，
返回第一个非 None 的返回值；全部返回 None 视为不干预。**
返回语义全表：

| 钩子 | 返回值 | 效果 |
|---|---|---|
| `before_input` | `str` | 替换用户输入 |
| | `HookVeto(reason)` | 任务以 stopped 收尾，reason 进入错误信息 |
| `before_session_create` | `str` / `{"title": str}` | 改写会话标题 |
| | `HookVeto` | 放弃创建（任务以 stopped 收尾） |
| `before_message_append` | `ChatMessage` | 替换消息 |
| | `False` / `HookVeto` | 丢弃该条消息（不落库） |
| `before_build_messages` | `str` / `{"system_prompt": str}` | 替换系统提示词 |
| `after_build_messages` | `List[ChatMessage]` | 替换整组消息 |
| `before_step` | `List[ChatMessage]` | 替换本轮消息 |
| | `HookVeto` | 跳过本轮模型调用（进入下一轮） |
| `before_model_call` | `{"messages": [...], "params": {...}}` | 按需替换请求 |
| | `HookVeto` | 拒绝本轮调用（任务以 stopped 收尾） |
| `after_model_call` | `ModelOutput` | 替换本次输出 |
| `before_tool_call` | `dict` | 替换工具参数 |
| | `False` / `HookVeto` | 阻止调用（回填 blocked_by_hook 结果） |
| `after_tool_call` | `str` / `ToolResult` | 替换工具结果 |
| `before_result` / `after_result` | `RunResult` | 替换最终结果 |
| 两者 | `HookVeto` | 保持原结果（否决被忽略） |

`HookVeto` 行为细节：

- 类型定义在 `norpagent.kernel.events`（经 `norpagent.hooks`
  再导出），是 `Exception` 子类，构造参数即否决原因；
- `EventBus.intercept` 对 HookVeto **不捕获**——否决语义必须
  送达内核，保证一票否决一定生效；普通订阅者异常被捕获记录
  （stderr，或 `bus.set_error_logger()` 指定记录器）后继续
  分发，单个订阅者永远拖不垮主循环；
- 各执行点的否决收尾语义不同（见上表）：before_input /
  before_model_call / before_session_create → 任务 stopped；
  before_step → 跳过本轮；before_tool_call → 回填
  blocked_by_hook；before_message_append → 丢弃该条；
  before_result / after_result → 忽略否决保持原结果；
- 订阅者分发顺序：全事件订阅者（`bus.subscribe(fn)` 不带事件名）
  先于具名订阅者；同组内按订阅先后；emit 逐个调用（异常隔离），
  intercept 逐个调用直到出现非 None 返回值。

### 9.4 自定义钩子与自定义层

三种扩展方式，与标准 29 钩子完全同权：

```python
from norpagent.hooks import HookLayer

# 方式一：自定义层 + 层内声明钩子（插件加载管线是标准库用例，11.4）
network_layer = HookLayer("L10_network", order=100, description="网络访问层")
before_net = network_layer.hook("before_network_call", mutating=True,
                                description="网络请求发出前（可改写 URL 或否决）")
agent.hooks.install_layer(network_layer)          # 安装后立即可用
agent.hooks.before_network_call.subscribe(monitor)

# 方式二：直接在钩子系统上定义钩子（不建层，归属 dynamic 层）
agent.hooks.define_hook("after_cache_hit", mutating=False,
                        description="缓存命中")

# 方式三：零定义触发——未注册的具名事件自动成为 dynamic 层钩子
agent.hooks.hook("my_custom_event").emit(data=42)
```

- `HookLayer(name, order, description)` 声明一层；`layer.hook()`
  返回 `Hook` 定义（即模块级 API），可提前导出供第三方
  `subscribe(fn, system=reg)` 使用；
- `install_layer` 按 `order` 排序层；**同名钩子已存在时保留原
  定义**（只登记层元数据），重复安装不覆盖既有订阅；
- `HookSystem` 查询 API：`list_hook_names()` / `list_hooks()` /
  `layers()` / `layer_of(name)` / `get(name)`；
- 自定义钩子照常支持 `subscribe / unsubscribe / emit / intercept`。

### 9.5 与通用事件总线（GeneralEventBus / `EventBus`）的关系

钩子体系是通用事件总线（GeneralEventBus，类名 `EventBus`，27.2）的
**结构化视图**，不是另一套机制：

- `HookSystem` 构造时把 9 层标准层装到某条 `EventBus` 上，
  订阅 / 发布最终都落在 `registry.bus`；
- `reg.hooks.before_step.subscribe(fn)` 与
  `reg.bus.subscribe(fn, "before_step")` **完全等价**，可混用；
- 因此替换循环系统（async_loop 槽位）后钩子照常工作——钩子
  挂在事件总线上，与循环实现无关（FAQ Q6）；
- 事件名与早期 plugin_system 的 16 个兼容 hook 完全一致（该体系另开放 13 个原生钩子、共 29 个，见 33.5），旧插件 /
  旧代码无需修改（第 11 章插件钩子桥接即依赖这一点）；
- 性能（0.9）：EventBus 采用写时复制——subscribe / unsubscribe
  在锁内替换新列表，emit / intercept 取一次快照引用后无锁
  迭代，高频流式事件（on_content 逐 token）不产生每事件列表
  复制开销（第 14.3 节超高并发）。

### 9.6 每个执行结构都可覆写

除钩子外，`AgentRuntime` 的七个执行结构同时是公共方法，子类
覆写即可替换该环节，无需改动循环本体：

```python
from norpagent import AgentRuntime, ChatMessage

class MyRuntime(AgentRuntime):
    def build_messages(self, system_prompt, session_id, *, step,
                       task_id, tool_names=None):
        messages = super().build_messages(...)     # 先走 L5 钩子
        messages.append(ChatMessage(role="system", content="自定义注入"))
        return messages

    def call_model(self, provider, history, schemas, params,
                   task_id, result, step):
        ...                                         # 完全接管 L7
```

方法清单：`prepare_input`（L3）/ `create_session`、
`append_message`（L4）/ `build_messages`（L5）/ `call_model`
（L7）/ `execute_tool_call`（L8）/ `finalize_result`（L9）。
覆写与钩子的关系：默认实现**先走钩子再做默认逻辑**，覆写时可
保留 super() 调用（钩子继续生效）或完全接管（跳过钩子）；
也可以经 `agent_runtime` 槽位整体替换循环类（3.1 节）。

### 9.7 行为细节与最佳实践

- 被阻止 / 否决 / 审批拒绝的工具调用统一流经 `after_tool_call`
  ——「执行结构」无论结果如何都过钩子；
- `before_step` 否决本轮 → 跳过模型调用进入下一轮；`after_step`
  只在有工具调用时广播（无工具调用时直接走最终回复路径）；
- 钩子改写作用于**实际数据流**（消息 / 参数 / 结果），不是旁路
  通知；改写后的值继续参与后续管线；
- 重复订阅同一 fn 会执行多次：热挂载 hooks 槽位时框架先退订
  架构级订阅再重挂（不叠加）；自己订阅的请配对 unsubscribe
  （`EventBus.unsubscribe` 只移除首个相等元素）；
- 高频钩子（on_content / on_reasoning 流式逐 token）里避免重
  计算与阻塞 I/O；订阅者异常虽被隔离记录，但异常路径有开销；
- 观测钩子（emit）的返回值被忽略——要干预数据流必须用可变
  钩子（intercept）或方法覆写；
- 线程安全：HookSystem / EventBus 的注册表操作均加锁，运行中
  订阅 / 退订安全（3.7 节热挂载即依赖这一点）；
- 需要干预但不想全局挂订阅者：把逻辑写成独立函数，配合任务级
  params 显式开关（如 jailbreak_guard / harden_prompt，见
  10.4 节），或只用 npa(hooks=...) 槽位在指定引擎上订阅。

### 9.8 29 个钩子逐个用法（Python 代码实现）

本节给出全部 29 个标准钩子的**可直接运行的订阅示例**。所有示例遵循同一
模式：订阅函数接收一个 `AgentEvent`（`.get(key)` 取负载键，`e.type` 取事件
名）；可变钩子（标注 ✓）的返回值按 9.3 表改写数据流，或抛 `HookVeto`
一票否决。示例统一使用 `registry.hooks.<name>.subscribe(fn)`（绑定总线，
推荐）；模块级 API `norpagent.hooks.<name>.subscribe(fn, system=reg)` 完全
等价，两种写法可混用（9.2）。

前置约定：

```python
import norpagent as npa
from norpagent.kernel.events import HookVeto

engine = npa()                # 启动引擎（或 npa(safemode="on") 最小装配）
hooks = engine.registry.hooks # 绑定到引擎总线的钩子视图
```

#### L1 运行时生命周期（2 个）

```python
# on_agent_init：运行时装配完成（组件装配、UI 订阅之后）广播一次。
# 负载键：preset（最终预设名）
def on_init(e):
    print(f"[init] preset={e.get('preset')}")

hooks.on_agent_init.subscribe(on_init)

# on_agent_shutdown：运行时关闭（沙箱/组件释放之后）广播。
# 负载键：preset
def on_shutdown(e):
    print(f"[shutdown] preset={e.get('preset')}")

hooks.on_agent_shutdown.subscribe(on_shutdown)
```

#### L2 任务生命周期（5 个）

```python
# on_task_start：任务开始（输入已通过 L3、会话已就绪）。
# 负载键：task_id, session_id, preset, user_input
def on_start(e):
    print(f"[task-start] {e.get('task_id')} input={e.get('user_input')!r}")

hooks.on_task_start.subscribe(on_start)

# on_task_done：任务正常完成（有最终回复产出）。
# 负载键：task_id, session_id, content, steps, context
def on_done(e):
    print(f"[task-done] {e.get('task_id')} steps={e.get('steps')}")

hooks.on_task_done.subscribe(on_done)

# on_task_error：任务异常终止（内部异常兜底后广播）。
# 负载键：task_id, error
def on_error(e):
    print(f"[task-error] {e.get('task_id')} {e.get('error')}")

hooks.on_task_error.subscribe(on_error)

# on_task_stopped：任务被停止（步数超限 / 安全拦截 / 钩子否决等）。
# 负载键：task_id, reason
def on_stopped(e):
    print(f"[task-stopped] {e.get('task_id')} reason={e.get('reason')}")

hooks.on_task_stopped.subscribe(on_stopped)

# on_task_timeout：任务超时。
# 负载键：task_id, timeout, kind（轮次边界或硬中断）
def on_timeout(e):
    print(f"[task-timeout] {e.get('task_id')} {e.get('kind')}")

hooks.on_task_timeout.subscribe(on_timeout)
```

#### L3 输入管线（3 个）

```python
# before_input ✓：用户输入处理前。返回 str = 替换输入；
# 抛 HookVeto = 任务以 stopped 收尾；返回 None = 不改写。
# 负载键：task_id, user_input, session_id, params
def sanitize(e):
    text = e.get("user_input") or ""
    if "危险词" in text:
        raise HookVeto("输入含禁用内容")
    return text.strip()  # 统一去首尾空白（返回 None 则不干预）

hooks.before_input.subscribe(sanitize)

# after_input：输入确定后（改写 / 安全扫描完成）。观测钩子，返回值忽略。
# 负载键：task_id, user_input, session_id
def log_input(e):
    print(f"[input] {e.get('user_input')!r}")

hooks.after_input.subscribe(log_input)

# on_user_input_required：需要用户额外输入（人工审批 / UI 提问）。
# 负载键：question, default
def prompt_reminder(e):
    print(f"[ask-user] {e.get('question')} (default={e.get('default')!r})")

hooks.on_user_input_required.subscribe(prompt_reminder)
```

#### L4 会话与历史（4 个）

```python
# before_session_create ✓：会话创建前。
# 返回 str 或 {"title": str} = 改写会话标题；抛 HookVeto = 放弃创建。
# 负载键：session_id, title, params, task_id
def title_policy(e):
    title = e.get("title") or ""
    if "私有" in title:
        raise HookVeto("禁止使用含敏感词的会话标题")
    return {"title": f"[{e.get('task_id')[:6]}] {title}"}

hooks.before_session_create.subscribe(title_policy)

# after_session_create：会话创建后。观测钩子。
# 负载键：session_id, title, task_id
def log_session(e):
    print(f"[session] created {e.get('session_id')} title={e.get('title')!r}")

hooks.after_session_create.subscribe(log_session)

# before_message_append ✓：消息落库前。
# 返回 ChatMessage = 替换；返回 False / 抛 HookVeto = 丢弃该条；
# None = 不改写。负载键：session_id, message, task_id
def redact(e):
    msg = e.get("message")
    if getattr(msg, "content", "").count("****") > 3:
        return False  # 疑似异常消息，不落库
    return msg

hooks.before_message_append.subscribe(redact)

# after_message_append：消息落库后。观测钩子。
# 负载键：session_id, message, task_id
def watch_messages(e):
    print(f"[msg] {e.get('message')}")

hooks.after_message_append.subscribe(watch_messages)
```

#### L5 消息组装（2 个）

```python
# before_build_messages ✓：组装消息前。
# 返回 str = 替换系统提示词；返回 {"system_prompt": str} 同左；None = 不改写。
# 负载键：system_prompt, session_id, step, task_id, tool_names
def add_system_rules(e):
    base = e.get("system_prompt") or ""
    if e.get("step") == 1:
        return base + "\n[规则] 回答必须引用事实来源。"

hooks.before_build_messages.subscribe(add_system_rules)

# after_build_messages ✓：组装消息后。返回 List[ChatMessage] = 替换整组消息。
# 负载键：messages, system_prompt, step, task_id
from norpagent import ChatMessage  # noqa: E402

def inject_history(e):
    messages = list(e.get("messages") or [])
    messages.append(ChatMessage(role="system", content="本任务为演示模式。"))
    return messages  # 返回 None 则不干预

hooks.after_build_messages.subscribe(inject_history)
```

#### L6 步骤（2 个）

```python
# before_step ✓：每轮迭代开始。
# 返回 List[ChatMessage] = 替换本轮消息；抛 HookVeto = 跳过本轮；
# None = 不改写。负载键：task_id, step, messages, context, params
def step_limiter(e):
    if e.get("step", 0) >= 10:
        raise HookVeto("步骤数达到上限，提前终止")
    return None

hooks.before_step.subscribe(step_limiter)

# after_step：本轮模型输出处理完毕（进入工具执行或结束）。观测钩子。
# 负载键：task_id, step, content, tool_calls
def trace_step(e):
    calls = [t.get("name") if isinstance(t, dict) else t
             for t in (e.get("tool_calls") or [])]
    print(f"[step {e.get('step')}] tools={calls}")

hooks.after_step.subscribe(trace_step)
```

#### L7 模型调用（6 个）

```python
# before_model_call ✓：模型请求发出前。
# 返回 {"messages": [...], "params": {...}} = 按需替换请求；
# 抛 HookVeto = 拒绝本轮调用（任务 stopped）；None = 不改写。
# 负载键：task_id, step, messages, tool_schemas, params
def model_guard(e):
    if not e.get("tool_schemas"):
        return {"messages": e.get("messages"),
                "params": {**e.get("params") or {}, "temperature": 0.0}}
    return None

hooks.before_model_call.subscribe(model_guard)

# after_model_call ✓：模型响应返回后。返回 ModelOutput = 替换本次输出。
# 负载键：task_id, step, output
def cap_output(e):
    out = e.get("output")
    if out is not None and len(getattr(out, "content", "") or "") > 2000:
        out.content = out.content[:2000] + "…"
        return out
    return None

hooks.after_model_call.subscribe(cap_output)

# on_reasoning：模型思维链增量（reasoning 模型流式输出）。观测钩子。
# 负载键：task_id, content, stream
def show_reasoning(e):
    print(f"[reasoning] {e.get('content')}", end="", flush=True)

hooks.on_reasoning.subscribe(show_reasoning)

# on_content：模型正文增量（流式逐段 / 整段）。观测钩子。
# 负载键：task_id, content, stream, final
def show_content(e):
    print(e.get("content"), end="", flush=True)
    if e.get("final"):
        print()  # 流结束换行

hooks.on_content.subscribe(show_content)

# on_event：模型侧任意子事件（兼容事件透传）。观测钩子。
# 负载键：event_type, data, task_id
def log_model_event(e):
    print(f"[model-event] {e.get('event_type')}: {e.get('data')}")

hooks.on_event.subscribe(log_model_event)

# on_usage_update：token 用量累计更新。观测钩子。
# 负载键：task_id, input, output, total
def track_tokens(e):
    print(f"[usage] in={e.get('input')} out={e.get('output')} total={e.get('total')}")

hooks.on_usage_update.subscribe(track_tokens)
```

#### L8 工具调用（3 个）

```python
# before_tool_call ✓：工具执行前。
# 返回 dict = 替换参数；返回 False / 抛 HookVeto = 阻止调用
# （回填 blocked_by_hook 结果）；None = 不改写。
# 负载键：task_id, tool_name, args, context
def tool_allowlist(e):
    if e.get("tool_name") not in {"echo", "get_time", "file_read"}:
        raise HookVeto(f"工具 {e.get('tool_name')} 不在救援白名单内")
    return None

hooks.before_tool_call.subscribe(tool_allowlist)

# after_tool_call ✓：工具执行后。
# 返回 str = 替换结果文本；返回 ToolResult = 替换结果；None = 不改写。
# 负载键：task_id, tool_name, args, result, success, context
def mask_secrets(e):
    if not e.get("success"):
        return None
    text = str(e.get("result") or "")
    return text.replace("sk-", "sk-***")  # 结果脱敏

hooks.after_tool_call.subscribe(mask_secrets)

# on_tool_error：工具执行抛出异常（框架已捕获转 ToolResult 后广播）。观测钩子。
# 负载键：task_id, tool_name, error, args
def alert_tool_error(e):
    print(f"[tool-error] {e.get('tool_name')}: {e.get('error')}")

hooks.on_tool_error.subscribe(alert_tool_error)
```

#### L9 结果定型（2 个）

```python
# before_result ✓：结果定型前（on_task_done/error/stopped 已广播）。
# 返回 RunResult = 替换最终结果；抛 HookVeto = 保持原结果。
# 负载键：task_id, result
def annotate_result(e):
    result = e.get("result")
    if result is not None:
        result.final_content = (result.final_content or "") + "\n[批注] 由钩子追加"
        return result
    return None

hooks.before_result.subscribe(annotate_result)

# after_result ✓：结果定型后。返回 RunResult = 替换最终结果（返回值生效）；
# 抛 HookVeto = 保持当前结果。负载键：task_id, result
def last_word(e):
    return e.get("result")  # 原样返回 = 确认结果；返回 None 同样不干预

hooks.after_result.subscribe(last_word)
```

> 订阅生命周期：`subscribe` 的订阅者随引擎存活；需要清理时用
> `hooks.<name>.unsubscribe(fn)` 或 `engine.registry.bus.clear()`（全部清空）。
> 高频钩子（on_content / on_reasoning 流式逐 token）内避免阻塞 I/O。

### 9.9 外部 Python 脚本如何订阅与触发钩子

外部脚本（独立 `.py` 文件、notebook、运维工具）可以像库内代码一样订阅
钩子或向总线发布自定义事件，两种接入方式：

1. **同进程嵌入**：脚本内 `npa()` 启动引擎，之后 `engine.registry.hooks`
   即该引擎的钩子视图（9.8 全部示例可直接照搬）；脚本结束时
   `npa.stop()` 平滑退出；
2. **独立进程 + 自有注册表**：脚本创建自己的 `Registry()` 与
   `HookSystem`，订阅模块级钩子 API，不启动引擎——适合监控、测试桩、
   事件采集器等旁路工具（详细模板见第 28 章 28.2）。

模块级 API 与总线的事件是同一个机制（9.5），因此外部脚本里
`from norpagent.hooks import before_tool_call` 之后
`before_tool_call.subscribe(fn, system=engine.registry)` 与
`engine.registry.hooks.before_tool_call.subscribe(fn)` 完全等价。

向总线发布自定义事件（供脚本间 / 插件间通讯）：

```python
engine.registry.bus.emit("my_custom_event", data=42)   # 未定义即触发 dynamic 钩子
engine.registry.hooks.hook("my_custom_event").emit(data=42)  # 等价写法
```

等待某个事件（一次性等待，超时自动清理订阅，见 27.2.7）：

```python
ev = engine.registry.bus.wait("on_task_done", timeout=60.0)
if ev is not None:
    print("task done:", ev.get("task_id"))
```

---

## 第 10 章　安全系统：norpagent.safe()

> 核心定位：`safe()` 把全套安全体系（越狱防护 / 提示词加固 /
> 人工审批 / 网络策略 / 源码审计 / 导入限制 / 签名信任 /
> 插件隔离策略）收敛为一个独立函数。配套文档 `docs/security.md`。

### 10.1 启用方式

```python
import norpagent as npa

# 1. npa() 槽位方式
npa(security="high")                                  # 字符串：只挂运行态策略，钩子零干预
npa(security={"level": "high", "hooks": True})        # dict：+ 显式钩子干预
npa(security=lambda reg: safe(reg, config={...}))     # callable：完全自定义装配

# 2. safe() 直接方式
from norpagent import safe
kit = safe(registry, level="standard")               # basic / standard / high
kit = safe(registry, level="standard", hooks=True)

# 3. 两段式：先拿套件，稍后安装
kit = safe(level="high")
kit.install(registry)                                # 只挂运行态策略（默认不挂钩子）
kit.install_hooks(registry)                          # 需要干预时手动挂载
kit.uninstall_hooks(registry)                        # 随时卸下，恢复纯净钩子
```

设计要点——**安全系统整体剥离**：

- 内核模块级不 import 任何 `norpagent.security` 模块；防护 /
  加固 / 审批 / 审计 / 签名通过 `registry.security` 注入
  （任务级参数显式要求时内核才惰性 import guard，见 10.4）；
- **钩子零干预（默认）**：safe() 默认不订阅任何钩子——越狱
  防护与提示词加固不作为钩子订阅者自动挂到总线上，钩子管线
  保持纯净；需要干预时由用户显式开启（hooks=True /
  kit.install_hooks()）；
- 防护能力本身始终以**独立 API** 提供（kit.scan_input /
  kit.harden / ...，10.5 节），用户可在自己的钩子订阅者或
  方法覆写中自由调用；
- 运行态决策（人工审批 / 网络策略 / 插件加载策略）始终经
  `registry.security`（SecurityContext）生效，与钩子是否挂载
  无关；
- CLI 等价开关：`--safe basic|standard|high`（只挂运行态策略），
  `--safe-hooks` 才显式挂钩子。

### 10.2 三档级别

| 能力 | basic | standard | high |
|---|---|---|---|
| 输入越狱/注入防护（L3 钩子，需显式开启） | ✓ | ✓ | ✓ |
| 系统提示词加固（L5 钩子，需显式开启） | ✓ | ✓ | ✓ |
| 插件源码 AST 审计 | warn | warn | **block** |
| 插件导入限制 | off | safe | safe |
| 权限声明（manifest permissions） | | | ✓ |
| 插件网络策略 | allow_all | deny | deny |
| 插件工具人工审批 | | ✓ | ✓ |
| 强制受信任签名 | | | ✓ |

- `basic`：只做输入防护与提示词加固（且默认不挂钩子，按需
  显式开启），插件侧不设限制——适合信任来源的本地插件开发；
- `standard`（默认）：+ 插件导入限制 safe、网络 deny、插件
  工具审批，签名校验开启但不强制；
- `high`：+ 审计 block（critical 即拒绝）、要求 manifest 权限
  声明、强制受信任签名（未签名 / 不受信任一律拒绝加载）。

### 10.3 SecurityContext：运行态安全策略的唯一事实源

`registry.security` 是一个 `SecurityContext` 实例：AgentRuntime
在工具审批时读取它，插件加载器在 config 缺省时读取它的
`plugin_config()`。字段（safe(level=...) 预设后可用 config dict
逐项覆盖，键名与 norpagent.security / 插件加载器配置一致）：

| 字段 | 默认(standard) | 说明 |
|---|---|---|
| `level` | standard | basic / standard / high |
| `guard_enabled` | True | 输入防护总开关（钩子干预路径） |
| `harden_enabled` | True | 提示词加固总开关（钩子干预路径） |
| `audit_level` | warn | off / warn / block |
| `import_restrict` | safe | off / safe / strict |
| `require_permissions` | False | manifest.permissions 强制 |
| `signature_verify` | True | Ed25519 验签（invalid 拒绝） |
| `signature_required` | False | True 时仅 trusted 放行 |
| `trusted_keys` | [] | 受信任公钥 hex 列表 |
| `network_policy` | deny | deny / audited_public / public_only / allow_all |
| `approval_config` | None | 审批策略 dict（10.6） |
| `plugin_isolation` | auto | auto / inproc / process |
| `hook_intervention` | False | True = 安装时同步挂防护钩子 |
| `extra` | {} | 扩展字段 |

- `plugin_config()` 把本上下文转成插件加载器配置（config
  缺省时的兜底）；`to_dict()` 输出完整姿态（与
  `kit.describe()` 一致）；
- `SecurityContext` 实例可直接作 `npa(security=ctx)` 槽位值；
- config 键名以插件加载器风格为主（plugin_security_audit /
  plugin_network_policy / plugin_trusted_keys 等），另有直白键
  guard_enabled / harden_enabled / hook_intervention / approval /
  approval_config；safe() 的 `_apply_config` 统一映射到
  SecurityContext。

### 10.4 钩子干预（显式开启）

`hooks=True` / `kit.install_hooks()` 挂载两个订阅者：

- **L3 输入防护** = `before_input` 订阅者：命中越狱 / 注入特征
  即抛 `HookVeto`（任务以 stopped 收尾）。任务级参数
  `params["jailbreak_guard"] = False` 可显式关闭该任务的钩子
  防护；`True`（或任意真值）走内核显式扫描路径——内核直接
  scan_message，**不依赖钩子挂载状态**；
- **L5 提示词加固** = `before_build_messages` 可变订阅者：把
  核心规则与工具清单注入系统提示词。任务级参数
  `params["harden_prompt"] = False` 可显式关闭该任务的加固；
  `True` 走内核显式加固路径。

挂载 / 卸载语义：

- `kit.install_hooks(reg)` 幂等：同一注册表重复调用不叠加；
- `kit.uninstall_hooks(reg)` 只移除**本套件自己的**订阅者，
  不动用户 / 插件的其它订阅，钩子管线恢复纯净；
- `kit.hooks_installed(reg)` 查询当前状态；
- `kit.uninstall(reg)` 退订钩子订阅并清除 `registry.security`。
  运行中热挂载 security 槽位（`npa.remount(security=...)`）会
  先 uninstall 旧套件再安装新套件，防同一总线上防护钩子叠加；
- 热挂载后运行态决策立即生效；钩子干预对后续任务的
  before_input / before_build_messages 生效。

### 10.5 独立检查 API（不挂钩子也能用）

SafetyKit 代理 norpagent.security 各模块，全部可直接单独调用：

| 方法 | 对应能力 |
|---|---|
| `kit.scan_input(text)` → (blocked, reason, hits) | 越狱 / 注入扫描 |
| `kit.is_jailbreak_attempt(text)` → bool | 扫描结果布尔化 |
| `kit.harden(prompt, tool_names)` → str | 提示词加固 |
| `kit.audit_file(path)` / `kit.audit_source(src)` → issues | 源码 AST 审计 |
| `kit.verify_plugin(path, manifest)` → SignatureResult | 插件签名校验 |
| `kit.check_network(url)` → bool | 按当前网络策略裁决（SSRF） |
| `kit.approval_policy(hints)` → ApprovalPolicy | 审批策略实例 |
| `kit.network_policy()` → NetworkPolicy | 网络策略实例 |
| `kit.describe()` → dict | 当前安全姿态 |

在自己的钩子订阅者里调用独立 API 的示例：

```python
from norpagent.hooks import HookVeto

def my_guard(event):
    blocked, reason, _ = kit.scan_input(event.get("user_input") or "")
    if blocked:
        raise HookVeto(reason or "输入被安全防护拦截")
reg.hooks.before_input.subscribe(my_guard)
```

底层模块（`norpagent.security`，零框架依赖，可独立 import）：
`guard`（扫描 / 加固）、`approval`（审批决策）、`network_policy`
（SSRF 裁决）、`audit`（AST 审计）、`signature`（Ed25519，
需 `norpagent[security]` 提供的 cryptography）。

### 10.6 运行态决策点

**人工审批**（AgentRuntime 工具执行路径）：

- 策略来源优先级：`params["approval_policy"]` 实例 >
  `params["approval_config"]` dict > `registry.security.approval_config`；
- 原生工具按「工具名 → 级别」映射审批（file_write /
  file_delete / exec_cmd 等 WRITE / DELETE / EXEC 级，含旧
  工具名兼容）；插件工具走 `approval_enabled` 总开关 + 插件
  `APPROVAL_HINTS` 精细控制（approval="none" 免审批，第 11 章）；
- 交互由 UI 适配器经 `ctx.ask_user` 完成（随广播
  on_user_input_required 钩子）；用户否定 → 调用被取消
  （approval_denied），仍流经 after_tool_call。

**网络策略 / SSRF 防护**（norpagent.security.network_policy）：

- 四粒度：`deny`（默认）→ `audited_public`（须命中 URL /
  域名白名单）→ `public_only`（禁内网）→ `allow_all`；
- 除 allow_all 外，一律拒绝私网 / 环回 / 链路本地 / 保留段 /
  云元数据地址（169.254.169.254 等）；先文本级判断再 DNS
  解析复判（防 rebinding 常见路径）。

**插件加载策略**：`install_plugin_dirs` 未显式给 config 时
自动采用 `registry.security.plugin_config()`——安全系统剥离后，
插件加载默认继承全局安全姿态（11.8 节）。

### 10.7 安全不降级原则与深度防御

- 未安装 cryptography 时签名校验返回「不受信任」，**不放行**
  （安全姿态不降级）；`norpagent[security]` 提供验签能力；
- 插件加载顺序固定：签名校验 → AST 审计 → 权限声明 → 导入
  限制 → 注册（每阶段失败即拒绝，不进入下一阶段，11.3）；
- 导入限制双层：AST 静态预检（防 sys.modules 已缓存模块绕过
  meta_path）+ sys.meta_path 运行时拦截；
- 进程级隔离（high / 自定义 config）把不可信插件移出主进程，
  即便审计漏检，插件崩溃也不影响宿主（11.7）；
- 内核侧 params 显式开关（jailbreak_guard / harden_prompt）
  与 safe() 的钩子路径并存：只要有一条开启，防护就生效
  （不依赖钩子挂载状态）。

### 10.8 典型组合

```python
# 生产默认：standard + 显式钩子干预
npa(security={"level": "standard", "hooks": True})

# 严格：high + 白名单网络 + 受信任密钥
kit = safe(level="high", config={
    "plugin_network_policy": "audited_public",
    "plugin_network_domain_allowlist": ["api.example.com"],
    "plugin_trusted_keys": ["<公钥hex>"],
})
npa(security=kit.context)                     # 直接安装 SecurityContext

# 纯决策、零干预：只用审批与网络策略，防护逻辑自己接
npa(security={"level": "standard",
             "config": {"guard_enabled": False, "harden_enabled": False}})
```

---

## 第 11 章　插件系统

> 外部插件以独立 `.py` 文件（或 manifest 包）分发，宿主经
> `norpagent.plugins` 加载器接入，自动获得签名校验 / AST 审计 /
> 导入限制 / 网络策略 / 人工审批全套安全防护。插件格式与既有
> 应用生态完全兼容，旧插件无需改代码即可迁移。
> **插件作者请直接阅读第 33 章《插件开发完全指南》**（29 钩子全表 /
> setup 注册面 / 完整教程 / 排错 / 迁移 / 发布清单）；本章为宿主侧概览。

### 11.1 两种 API 与 npa() 槽位

```python
# 便捷入口：一次性加载目录
from norpagent.plugins import install_plugin_dirs
loader = install_plugin_dirs(reg, ["my_plugins"], config={...})

# 库化门面：完整生命周期 + 状态 + 热重载
from norpagent.plugins import PluginSystem
ps = PluginSystem(reg, ["my_plugins"], config={"plugin_isolation": "auto"})
infos = ps.load()        # 发现 → 安全加载 → 注册
ps.status()              # 插件清单 + 隔离宿主状态
ps.reload("my_tool")     # 开发期热重载单个插件
ps.shutdown()            # 释放进程隔离宿主子进程

# npa() 槽位（literal 语义，目录列表）
npa(plugins=["./my_plugins"])
# 运行中热替换：旧订阅自动退订，不叠加（3.7 节）
npa.remount(plugins=["./my_plugins_v2"])
```

`npa(plugins=[...])` 槽位以固定配置装配（audit=warn、验签开启，
**不读取** registry.security 的覆盖）；需要精细配置用
PluginSystem / install_plugin_dirs 直接操作 Registry（或
callable 槽位值，如 `npa(plugins=lambda reg: ps.load())`）。

### 11.2 插件格式（与现有应用兼容）

**模块级接口**（单文件插件 `my_plugin.py`）：

| 名称 | 类型 | 说明 |
|---|---|---|
| `PLUGIN_NAME` | str | 插件显示名（必填） |
| `PLUGIN_VERSION` | str | 版本，默认 0.0.0 |
| `PLUGIN_PUBLISHER` | str | 发布者 |
| `PLUGIN_DESCRIPTION` | str | 描述 |
| `TOOLS` | list | OpenAI function schema 列表 |
| `execute(tool_name, args, ctx)` | callable | 工具统一入口，返回 str / None |
| `APPROVAL_HINTS` | dict | 工具 → 审批提示（11.8） |
| `ISOLATION` | str | `"process"` = 进程级隔离（AST 静态读取，不执行代码） |
| `__norpagent_type__` | str | 文件即模块类型声明（"tool" / "plugin"，FLOW 拖入用） |
| `PLUGIN_CAPABILITIES` | list | 能力声明（33.8.1；缺省 = tools / hooks / events 基础集） |
| `PLUGIN_REQUIRES` / `PLUGIN_MIN_NORPAGENT` | list·dict / str | 依赖与最低版本声明（33.10） |
| `setup(api)` / `on_load(ctx)` / `on_unload(ctx)` | callable | 注册门面与生命周期（33.7 / 33.8） |
| 钩子函数 | callable | 16 个兼容钩子逐参数对齐 + 13 个原生钩子，共 29 个（11.5 / 33.5 全表） |

```python
# my_plugin.py —— 最小插件
PLUGIN_NAME = "greet_plugin"
TOOLS = [{
    "type": "function",
    "function": {
        "name": "greet",
        "description": "向用户打招呼",
        "parameters": {"type": "object",
                       "properties": {"name": {"type": "string"}},
                       "additionalProperties": False},
    },
}]

def execute(tool_name, args, ctx):
    if tool_name == "greet":
        return f"你好，{args.get('name') or 'world'}！"
    return None
```

**manifest 包格式**：目录 + `manifest.json`（name / version /
publisher / description / entry 默认 plugin.py / permissions /
signature / isolation 字段）。

### 11.3 安全管线（加载全流程）

```
发现（目录扫描：*.py 单文件 / manifest 包）
  → before_plugin_load（HookVeto 可拒，11.4）
  → 1. 签名校验：invalid 直接拒绝；signature_required 时仅 trusted 放行
  → 2. 信任分级：受信任签名 → 审计放宽为 warn
  → 3. AST 审计：危险调用 / 危险导入 / getattr、__dict__ 反射绕过检测，
       block 级发现 critical 即拒绝
  → 4. 权限声明：require_permissions 时校验 manifest.permissions
  → 5. 隔离决策：process → 插件只在宿主子进程加载（11.7）
  → 6. 导入限制下加载模块（静态预检 + meta_path 拦截，11.6）
  → 7. 读取元数据（PLUGIN_NAME / TOOLS / 钩子 / APPROVAL_HINTS）
  → before_plugin_register（HookVeto 可拒）
  → 8. 适配为 Plugin 协议 → 注册进 Registry（工具入表、钩子订阅总线）
```

每阶段失败 → `PluginInfo(enabled=False, error=...)` 记录原因后
**继续扫描其它插件**，不中断整体加载。`PluginInfo` 携带
`name / path / version / publisher / description / enabled /
error / tools / hook_names / signature_status / trusted /
approval_hints / audit_issues`；调试时看
`loader.plugins[i].error` 与 `audit_issues`（含行号）。

### 11.4 加载管线钩子（自定义层的标准库用例）

PluginSystem 构造时把 `PLUGIN_PIPELINE_LAYER`（order=200 的
自定义 HookLayer，9.4 节能力的官方示例）装进 `registry.hooks`，
8 个管线钩子：

`before/after_plugin_discover`、`before/after_plugin_load`、
`before/after_plugin_audit`、`before/after_plugin_register`。

```python
from norpagent.hooks import HookVeto
from norpagent.plugins import before_plugin_load

def block_listed(event):
    if (event.get("name"), event.get("path")) in HOST_BLOCKLIST:
        raise HookVeto("该插件被宿主策略拒绝")
before_plugin_load.subscribe(block_listed, system=reg)
```

- 可变管线钩子（before_plugin_load / before_plugin_audit /
  before_plugin_register）抛 HookVeto = 拒绝该插件的加载 /
  注册（enabled=False + error 记录原因）；after_* 为观测钩子
  （after_plugin_audit 负载含 allowed / issues）；
- 管线钩子经 `registry.hooks.hook(name)` 动态注册，与插件模块
  级 hook 互不冲突。

### 11.5 旧插件钩子桥接（16 个兼容 hook 对齐；全部 29 钩子开放）

插件模块级定义的钩子函数由加载器包装成 EventBus 订阅者；
**16 个兼容钩子**与既有生态逐参数对齐，另 **13 个原生钩子**
（before_input / before_model_call / before_result 等）同样可直接
定义——插件可定义全部 **29 个标准钩子**（全表与签名见 33.5）：

- 签名约定：**业务参数在前，PluginContext 在最后**（ctx 字段
  全表见 33.6）；
- 可变钩子返回值经总线透传给内核（首个非 None 生效）；把
  "原样返回输入"（`return messages` / `return args` /
  `return result`）视为不改写，不遮挡其他插件；
- 每个订阅者恰好被调用一次、副作用全部执行（不再有截断与
  双调）；
- 钩子异常不再静默：首次错误打印 + 计数 + 写入
  `PluginInfo.diagnostics`；
- 进程隔离插件同样经此桥接：fire_hook RPC 转发（限时 5s；
  `on_task_stopped` 签名自适应在子进程内完成）。

### 11.6 导入限制

- `off`：不限制（本地调试用；受信任签名只放宽审计，导入限制
  仍按配置执行）；
- `safe`（standard / high 默认）：阻断危险模块（subprocess /
  ctypes / cffi / socket / pickle / marshal / telnetlib / ftplib /
  smtplib；ctypes / cffi 无条件阻断），**双层防护**：AST 静态
  预检（防 sys.modules 已缓存模块绕过 meta_path）+ 加载期
  sys.meta_path 拦截（栈帧探测调用方是否为插件模块）；
- `strict`：仅允许安全模块白名单（json / re / datetime / math /
  random / collections / itertools / functools / typing / enum /
  pathlib / os.path / textwrap / string / hashlib / base64 /
  traceback / logging / warnings / copy / uuid / time /
  norpagent.protocols.tool 等），白名单外一律 ImportError。

插件模块以 `norpagent_ext_<name>` 模块名加载（命名空间统一），
限制器**只对插件模块生效**，不影响宿主代码。

### 11.7 进程级隔离

`ISOLATION = "process"`（模块常量，AST 静态读取，**不执行插件
代码**）/ manifest `isolation` 字段 / 宿主配置
`plugin_isolation`（auto 时取前两者；显式 inproc / process 时
强制）。隔离语义：

- 插件模块对象只存在于宿主子进程（`python -m
  norpagent.plugins.host`，JSON 行协议 RPC）；
- 工具执行经 RPC 回传；钩子经 fire_hook 转发，单次钩子限时
  5s（HOOK_TIMEOUT），超时放弃——插件钩子永不拖死主循环；
- 崩溃自愈：子进程死亡 → 自动重启 + 重载全部插件 → 重试一次；
- 工具错误不冒泡：远端异常转为失败 ToolResult；
- 导入限制在子进程内继续生效（纵深防御）；
- **注册面限制**：进程隔离插件的插件代码不在主进程运行，
  `setup(api)` 注册面不提供（加载时给出警告）；工具与钩子面
  不受影响（完整说明见 33.9.4）。

### 11.8 与安全系统的联动

- `install_plugin_dirs(reg, dirs)` **不传 config** 时自动采用
  `registry.security.plugin_config()`——先 `safe(reg, ...)` 再
  装插件，插件加载即继承全局安全姿态（注意：npa(plugins=...)
  槽位路径传固定 config，不读 registry.security）；
- `safe(level="high")` 对插件的影响：审计 block、强制权限
  声明、强制受信任签名（未签名 / 不受信任拒绝）；
- 信任机制：`python -m norpagent plugin-sign --gen` 生成密钥对，
  `plugin-sign my_plugin.py --key <私钥hex>` 生成签名；公钥加入
  `plugin_trusted_keys` 后该插件受信任 → 审计放宽为 warn
  （导入限制按配置执行，不受信任影响）；
- 网络访问由宿主 `plugin_network_policy` 裁决（默认 deny），
  插件自身无法绕过——策略执行于宿主进程（10.6 节）；
- 审批：插件工具默认走 `approval_enabled` 总开关；插件
  `APPROVAL_HINTS` 里 `{"approval": "none", "risk": "L0"}` 可
  对单个工具免审批，未声明的工具走总开关（向后兼容）。

### 11.9 配置键总表与生命周期

```python
config = {
    "plugin_security_audit": "warn",            # off / warn / block
    "plugin_security_import_restrict": "off",   # off / safe / strict
    "plugin_security_require_permissions": False,
    "plugin_signature_verify": True,
    "plugin_signature_required": False,         # True: 仅 trusted 放行
    "plugin_trusted_keys": ["<公钥hex>"],
    "plugin_network_policy": "deny",            # deny/audited_public/public_only/allow_all
    "plugin_network_url_allowlist": ["https://api.example.com/"],
    "plugin_network_domain_allowlist": ["api.example.com"],
    "approval_enabled": True,                   # 插件工具审批总开关
    "plugin_isolation": "auto",                 # auto / inproc / process
    "plugin_log_dir": "",                       # 插件日志目录（空 = ~/.norpagent/plugin_logs）
    "plugin_disabled": [],                      # 禁用的插件名列表（保留在表内、不加载）
    "plugin_capabilities": None,                # 宿主侧能力总闸（None = 不额外限制）
}
```

生命周期注意（2026-09-11 起，卸载 / 重载为干净语义）：

- `ps.load()` 可重复调用（先清空清单再重扫）；`ps.configure()`
  更新配置并使加载器失效重建；
- `ps.unload(name)` / `ps.reload(name)` **完整回收**：执行
  `on_unload`、真正退订钩子订阅、从工具表删除工具、回收
  `setup` 注册（订阅 / 槽位 / 服务 / 命令 / 动态工具 / 组件）；
- 运行中整体替换用 `npa.remount(plugins=[...])`：框架先完整卸载
  旧加载器再装载新目录（防叠加，3.7 节）；
- `ps.shutdown()` / `loader.shutdown()` 对所有插件执行
  `on_unload` 并释放进程隔离宿主子进程。

### 11.10 插件能力面（v2.1.0 扩展）

除工具与 29 钩子外，插件可经 `setup(api)` 注册：动态工具 / 自定义
槽位 / 组件 / 模型 / 会话 / 沙箱 / 调度器 / UI / 自定义钩子 /
事件订阅 / 服务 / Web 页面 / CLI 命令 / 设置项，并以
`PLUGIN_CAPABILITIES` 声明能力面（缺省 = tools / hooks / events
基础集）。完整 API 参考与示例见第 33 章；CLI 侧可用
`norpagent plugins list|run` 管理。

## 第 12 章　预设模式

### 12.1 内置六模式

| 模式 | 用途 | 组件组合 |
|---|---|---|
| `minimal` | 模型基准测试 | mock + echo/get_time + memory |
| `standard` | 通用编码任务 | sqlite + pooled + persistent + fts5 + 全部内置工具 |
| `longrun` | 长周期复杂任务 | 同 standard；max_steps=512、不限时、分阶段规划提示词 |
| `ptc` | 代码编排工具调用 | run_python（沙箱执行） |
| `creative` | 自定义模式调试 | 模式文件加载（--mode-file） |
| `embedded` | 嵌入式 / 边缘 / 低资源（0.9） | 纯内存组件 + 最小工具集，**默认 headless 前端**，无磁盘 / 无联网依赖；无凭据时模型自动回落 mock。详见第 14.2 节 |

```python
npa(preset="standard")
npa(preset="ptc")
npa(preset="embedded")                     # 默认 headless，纯 API 模式
npa(preset=Preset(name="mine", model="mock", tools=["echo"], ...))
```

### 12.2 自定义预设

```python
from norpagent import Preset

my = Preset(
    name="mine",
    description="定制模式",
    model="mock",
    tools=["echo", "get_time"],
    session="sqlite",
    sandbox="pooled",
    scheduler="simple",
    ui="console",
    mode="single",
    params={"max_steps": 16},
    components={},
)
npa(preset=my)
```

---

## 第 13 章　命令行入口

> 本章给出全部命令行入口与用法：主命令 `norpagent`（模块入口
> `python -m norpagent`）、崩溃救援 `norpagent-rescue`（纯标准库）、
> 以及各命令与 `npa()` 编程入口的等价关系。速查版见附录 G。

### 13.1 两条命令的分工

| 命令 | 用途 | 依赖 | 入口 |
|---|---|---|---|
| `norpagent` | 启动 Agent（REPL / 单次任务 / Web UI），加载插件、安全策略 | 完整框架 | `python -m norpagent` 或 console_scripts |
| `norpagent-rescue` | 快照回退 + 人类接管工具（模型失效时手操） | 快照子命令纯标准库；接管子命令惰性加载框架 | `python -m norpagent.rescue` 或 console_scripts |

### 13.2 norpagent 主命令参数全集

```bash
# 查看全部内置预设模式
norpagent --list-modes

# 交互 REPL（命令行前端，默认模式 minimal 之外按 --mode 选择）
norpagent --mode standard

# 单次任务（--prompt 存在时不再进入 REPL）
norpagent --mode ptc --prompt "总结这个仓库"

# 自定义模式文件（模块级 PRESET 变量）
norpagent --mode-file my_mode.py

# Web UI（HTTP + SSE，默认端口 8787）
norpagent --mode standard --ui web --port 8787

# 模型与凭据
norpagent --model openai_compat --model-name deepseek-v4-flash \
          --base-url https://api.deepseek.com/v1 --api-key sk-xxx

# 外部插件与安全
norpagent --mode standard --plugin-dir ./my_plugins
norpagent --mode standard --plugin-isolation process
norpagent --mode standard --safe high              # 运行态安全策略（钩子零干预）
norpagent --mode standard --safe high --safe-hooks # 同时开启钩子干预
norpagent --safe-mode                              # 安全模式：只加载最小内核，跳过全部插件

# 会话存储与超时
norpagent --mode standard --session sqlite --call-timeout 120

# 插件签名
norpagent plugin-sign --gen                        # 生成签名密钥对
norpagent plugin-sign my_plugin.py --key <privkey> # 给插件文件签名
```

参数速查（`norpagent --help` 同源）：

| 参数 | 说明 | 等价 npa() 参数 |
|---|---|---|
| `--list-modes` | 列出全部预设模式 | `list_presets()` |
| `--mode / -m` | 预设模式名（minimal/standard/ptc/creative 或自定义） | `preset=...` |
| `--mode-file / -f` | 加载模式文件（模块级 `PRESET`） | `load_preset_file()` |
| `--prompt / -p` | 单次任务输入（给出则跳过 REPL） | `submit(text)` |
| `--model` | 覆盖预设模型（须已注册） | `model=...` |
| `--model-name` | 远端模型名（如 deepseek-v4-flash） | 经 `_apply_model_options` |
| `--base-url` | OpenAI 兼容端点 | 同左 |
| `--api-key` | API Key（缺省读环境变量） | 同左 |
| `--session` | 会话后端（memory/sqlite） | `session=...` |
| `--call-timeout` | 单次模型调用硬超时（秒） | `task_params={"call_timeout": N}` |
| `--ui` | UI 适配器（console/web） | `ui=...` |
| `--port` | Web UI 端口（默认 8787） | `config={"web": {"port": N}}` |
| `--plugin-dir` | 外部插件目录（可重复） | `plugins=[...]` |
| `--plugin-isolation` | 插件隔离模式 auto/inproc/process | `plugins` 槽位配置 |
| `--safe` | 安全级别 basic/standard/high | `security=...` |
| `--safe-hooks` | 与 `--safe` 联用：开启钩子干预 | `security={"hooks": True}` |
| `--safe-mode` | 安全模式：最小内核，跳过插件 | `safemode="on"` |
| `plugin-sign` | 子命令：插件签名工具 | — |

CLI 与 `npa()` 等价：CLI 内部流程为
「安装默认组件 → 注册预设 → 应用安全 → 加载插件 → 构建运行时」，
与 `npa()` 的装配管线一致；`--safe-mode` 等价于 `npa(safemode="on")`。

### 13.3 命令行前端（Console REPL）进入方式

命令行前端指 `ui=console`（或 `frontend="norpagent.frontends.console:ConsoleFrontend"`）
的交互模式：

```bash
# 方式一：CLI 直接进入（默认即 REPL）
norpagent --mode standard

# 方式二：Python 解释器中显式使用控制台前端（自动切换同步模式）
python - <<'PY'
import norpagent as npa
npa(frontend="norpagent.frontends.console:ConsoleFrontend")
# >>> 你: 你好
# >>> 使用 /exit 退出
PY
```

REPL 内置命令：`/exit`（或 `/quit`、`exit()`、Ctrl+C、EOF）退出；
`/help` 查看命令；`/modes` 列出预设模式；`/tools` 列出可用工具；
`/reset` 开启新会话。

> 注意：显式使用控制台前端时，`npa()` 在交互式解释器中阻塞到用户退出，
> 无需 `npa.stop()` 轮询循环；默认 Web 前端则需用 `npa.stop()` 轮询
> 生命周期（第 6 章）。

### 13.4 安全模式与自救提示

启动或运行失败时，CLI 会打印自救提示（`_print_rescue_hints`）：

1. `norpagent --safe-mode`：安全模式启动（只加载最小内核，跳过全部插件，
   不读 WebUI 设置文件）——等价 `npa(safemode="on")`；
2. `norpagent-rescue list` / `norpagent-rescue rollback --last-good`：
   崩溃救援（纯标准库），回退到最后一次正常工作的快照；
3. 回退后重启（回退目标自动消费，无需手动搬配置）；
4. 模型提供商失效 → 人类接管工具：
   `norpagent-rescue tools / tool-call / manual / serve`。

### 13.5 norpagent-rescue 全部子命令

**快照回退（纯标准库，主程序坏到无法导入也可用）**：

```bash
norpagent-rescue list                     # 时间线（★ = 最后一次正常工作的快照）
norpagent-rescue show <id>                # 查看快照内容（敏感键已脱敏）
norpagent-rescue rollback <id>            # 回退：写回退目标 + 恢复 WebUI 设置
norpagent-rescue rollback --last-good     # 一键回退到最后一次正常快照
norpagent-rescue mark-good <id>           # 手动标记「正常」
norpagent-rescue prune --keep 50          # 只保留最近 N 个快照
```

**人类接管（模型失效时手操工具；需框架可导入）**：

```bash
norpagent-rescue tools                              # 工具清单（含来源标注）
norpagent-rescue tools --workspace ./ws             # 指定工作区根目录
norpagent-rescue tools --tools myapp.tools:create   # 追加自定义工具（模块地址）
norpagent-rescue tools --plugin-dirs ./my_plugins   # 加载外部插件工具
norpagent-rescue tool-call echo --args '{"text":"ping"}'
norpagent-rescue tool-call exec_cmd --args '{"command":"git status"}' --timeout 30
norpagent-rescue manual                             # 交互式手操台
norpagent-rescue serve --port 8799                  # HTTP API + 操作员页面（127.0.0.1）
norpagent-rescue serve --token my-secret            # 可选 Bearer 认证
norpagent-rescue serve --tools t1,t2 --plugin-dirs ./plug1,./plug2
```

四个接管子命令（tools / tool-call / manual / serve）共享的参数：
`--workspace`（文件工具的工作区根目录）、`--tools`（逗号分隔的已注册
工具名或 `pkg.mod:attr` 模块地址）、`--plugin-dirs`（逗号分隔插件目录）、
`--context-db`（上下文库路径，默认共享 `~/.norpagent/context.db`）；
`tools` 额外支持 `--sandbox` / `--session` / `--scheduler` 后端选择，
`tool-call` 额外支持 `--timeout`（硬超时秒数，默认 300），
`serve` 额外支持 `--port` / `--host` / `--token`。

自定义工具详情见 15.6.3 / 24.3.5。

### 13.6 CLI 与 npa() 编程入口的等价关系

| 场景 | CLI | 编程入口 |
|---|---|---|
| 交互 REPL | `norpagent --mode standard` | `npa(frontend=console 前端)` |
| 单次任务 | `norpagent --mode ptc --prompt "..."` | `npa(prompt="...")` 或 `submit(text)` |
| Web UI | `norpagent --mode standard --ui web --port 8787` | `npa()`（默认 Web 前端） |
| 安全模式 | `norpagent --safe-mode` | `npa(safemode="on")` |
| 安全策略 | `norpagent --safe high [--safe-hooks]` | `npa(security="high" 或 {"hooks": True})` |
| 外部插件 | `norpagent --plugin-dir ./dir` | `npa(plugins=["./dir"])` |
| 自定义工具（救援） | `norpagent-rescue ... --tools ...` | `RescueToolEnvironment(tools=[...])` |
| 快照回退 | `norpagent-rescue rollback <id>` | `npa.rollback(id)` |
| 最后一次正常快照 | `norpagent-rescue rollback --last-good` | `npa.rollback("__last_good__")` 语义等价 |

---

## 第 14 章　嵌入式与超高并发部署

0.9 起，框架针对**嵌入式（低内存 / 低 CPU / 无磁盘 / 边缘设备）**与
**超高并发服务器**两大场景做了专项优化。本章说明优化内容、配置
入口与使用方式。

### 14.1 优化清单

**嵌入式场景（资源消耗最小化）：**

| 优化 | 内容 |
|---|---|
| `install_core()` 极简装配 | 只注册运行 Agent 最小闭环的组件：mock / openai_compat 模型、echo / get_time / run_python / file_* 工具、memory 会话、subprocess 沙箱、simple 调度器、console UI——**零磁盘依赖、无 HTTP 组件、组件命名空间为空**（不导入 sqlite3 / http.server） |
| builtin 包懒导入 | `import norpagent.builtin` 不再拉起 sqlite3 / http.server；FTS5 上下文库 / SQLite 会话 / 持久化调度器 / Web UI 全部改为 install_defaults 内按需导入 + 模块级 `__getattr__` 懒解析（`from norpagent.builtin import WebUI` 等写法兼容不变） |
| WebUI 构造零磁盘 I/O | 配置 / FE 配置 / flow 图三份磁盘状态的读取全部延迟到 `start()`（`_ensure_disk_loaded`）；只构造不启动不再读盘，只读根文件系统 / 无 HOME 环境安全 |
| 页面字节缓存 | `page_bytes()` 读入内存缓存：每次 GET / 不再读盘（此前每请求一次 open+read） |
| `embedded` 预设 | 内置第六模式：纯内存组件 + 最小工具集 + 默认 headless 前端（不监听端口），无凭据时模型回落 mock |
| 工作池收紧 | `NORPAGENT_MAX_WORKERS=1` 或 `config={"loop": {"max_workers": 1}}` 把守护工作线程压到最少；`NORPAGENT_SUBMIT_POLL=0.5` 调大轮询间隔省 CPU |

**超高并发服务器（吞吐与内存上界）：**

| 优化 | 内容 |
|---|---|
| EventBus 写时复制 | 订阅者表改为不可变快照：emit / intercept 在锁内只取引用、无锁迭代，**每条事件省去一次监听者列表复制**（流式逐 token 推送场景收益最大）。订阅 / 退订创建新列表替换引用，线程安全语义不变（实测 emit 吞吐 >150 万事件/秒） |
| SSE 有界背压 | 每连接一个 `_SSESubscriber` 有界缓冲（默认 1024 条）：慢客户端**丢最旧事件**（`drop_oldest`，默认）自动降级，可选 `drop_newest` / `unlimited`；内存占用有上界，与客户端数量解耦 |
| SSE 帧批量写出 | 攒满 32 条或 50ms 即一次 write+flush（`sse_batch` / `sse_batch_interval` 可配）：流式高频推送下系统调用次数大幅下降；单事件流延迟 ≤ 批间隔 |
| SSE 快速断连回收 | TCP 半关闭后第一次写不报错，靠心跳才发现会延迟至多 15s——空闲每 1s 非阻塞 select 探测连接可读性，断开后 ≤1s 释放线程与缓冲；心跳注释仍每 15s 一次，不增加网络负担 |
| HTTP 并发调优 | 监听积压 `request_queue_size=256`；`block_on_close=False` 停机不等连接关闭；`X-Accel-Buffering: no`（nginx 反代不攒批）；响应 keep-alive（HTTP/1.1） |
| submit 轮询收紧 | 完成轮询间隔 0.2s → 0.05s（默认）：阻塞等待任务的调用线程完成感知延迟上限 200ms → 50ms；可配 / 环境变量覆盖 |
| 循环内核微调 | `traceback` 提升模块级（回调异常路径零 import）；ready 队列快照批量执行保持防饥饿语义 |

### 14.2 嵌入式部署

**方式一：`install_core()` 自建注册表（依赖面最干净）：**

```python
from norpagent import Registry, AgentRuntime, install_core
from norpagent.modes import build_embedded_preset

reg = Registry()
install_core(reg)                       # 不导入 sqlite3 / http.server
reg.register_preset(build_embedded_preset())
agent = AgentRuntime(reg, preset="embedded")
result = agent.run("你好")
print(result.final_content)
```

注意：`install_core` 的注册表上没有 context_store / project_manager /
persistent 等组件——声明了这些组件的预设（standard / longrun /
creative 等）在此注册表上装配会被明确拒绝（报错列出缺失组件名）。

**方式二：`npa(preset="embedded")`（开箱即用）：**

```python
import norpagent as npa

npa(preset="embedded")                   # 默认 headless：不启动 HTTP 服务
eng = npa.current()
result = eng.submit("你好")             # 纯 API 提交
eng.request_stop()
```

embedded 预设的行为约定：

- **默认前端自动回落 headless**（装配器默认工厂判断 preset 名）；
  需要 Web 界面时显式
  `npa(preset="embedded", frontend="norpagent.frontends.web:WebFrontend")`；
- 模型声明 `openai_compat`：提供任何凭据（参数 / 环境变量）即用真实
  模型，否则回落 mock（离线设备开箱可用）；
- 组件全部纯内存（memory / subprocess / simple），不声明通用组件——
  FTS5 / SQLite 不会被构建，不产生落盘文件。

**方式三（资源开关，与方式一/二叠加）：**

```python
# 工作线程压到 1；轮询放宽省 CPU
os.environ["NORPAGENT_MAX_WORKERS"] = "1"
os.environ["NORPAGENT_SUBMIT_POLL"] = "0.5"
# 或等价：
npa(config={"loop": {"max_workers": 1, "poll_interval": 0.5}})
```

### 14.3 超高并发部署

**SSE 背压配置（启动参数 → 环境变量 → 运行中热改变）：**

```python
import norpagent as npa

# 启动时传入
npa(config={"web": {"sse_queue_size": 2048, "sse_queue_policy": "drop_oldest"}})
# 或运行时参数 / 环境变量
npa(sse_queue_size=2048, sse_queue_policy="drop_oldest")
# NORPAGENT_SSE_QUEUE_SIZE=2048 NORPAGENT_SSE_QUEUE_POLICY=drop_oldest

# 运行中热改变（无需重启，对既有连接立即生效）
from norpagent.builtin.ui.web import WebUI
ui = npa.current().frontend._ui      # 或直接持有 WebUI 实例
ui.set_sse_queue(sse_queue_size=4096, sse_queue_policy="drop_newest")
print(ui.streams_info())
```

REST 运维入口：

| 接口 | 说明 |
|---|---|
| `GET /api/streams` | 查询 SSE 背压配置与统计（订阅者数 / 丢弃事件数 / 各连接缓冲深度） |
| `POST /api/streams` | 热改变：`{"sse_queue_size": 2048, "sse_queue_policy": "drop_oldest"}` |
| `GET /api/status` | `sse_queue_size` / `sse_queue_policy` / `sse_dropped_total` 字段 |

背压策略语义：

| 策略 | 缓冲满时行为 | 适用 |
|---|---|---|
| `drop_oldest`（默认） | 丢最旧事件，客户端自动降级但**不掉线** | 展示型前端（聊天流） |
| `drop_newest` | 丢最新事件，保持旧状态 | 「状态同步」型消费者 |
| `unlimited` | 不限制（0.8 旧行为） | 明确知道客户端都会消费时 |

缓冲大小 `sse_queue_size=0` 表示不限制。`sse_batch`（默认 32 条）与
`sse_batch_interval`（默认 0.05s）控制帧批量写出粒度：越大系统调用
越少、单事件延迟越高，按流量特征权衡。

**反向代理注意**：SSE 响应已带 `X-Accel-Buffering: no`（nginx 不攒批）；
代理层超时（proxy_read_timeout）应 > 15s（库内心跳周期）。

**循环调参**：`config={"loop": {...}}` 与
`NORPAGENT_MAX_WORKERS` / `NORPAGENT_SUBMIT_POLL` 见 4.3 与 14.1。
任务完成感知延迟 = poll_interval（默认 50ms）；CPU 敏感环境调大，
延迟敏感环境调小（下限 1ms）。

**线程模型**：Web 前端每 SSE 连接一个 HTTP 线程（标准库
socketserver 模型）；任务经 `WebFrontend._gate` 串行进入引擎，由
循环工作池执行。事件发布路径 O(订阅者数) 且每订阅者摊销 O(1)
（有界 deque + 空→非空一次 notify），万级并发推送不放大锁争用。

**监控指标**（`GET /api/streams`）：`subscribers`（在线订阅者）、
`dropped_total`（累计背压丢弃——持续增长说明客户端过慢，应调大
缓冲或排查消费端）、`max_buffered`（各连接缓冲深度峰值）。

### 14.4 验证方式

库内验证脚本（`test/`）：

```bash
python test/_verify_embedded_concurrency.py   # 34 项：极简装配/懒导入/e2e/并发正确性/吞吐
python test/_smoke_webui_09.py                # WebUI：懒磁盘 I/O/页面缓存/背压热改变/HTTP 并发/SSE
python test/_smoke_embedded.py                # embedded 预设 e2e
```

覆盖要点：`install_core` 组件白名单与黑名单、`import norpagent.builtin`
不拉 sqlite3 / http.server、embedded 默认 headless + mock 回落、
环境变量收紧工作池、EventBus 写时复制并发订阅/退订正确性、
submit 中断唤醒、SSE 三策略与热改变、40 并发 HTTP、断连回收。

---

## 第 15 章　工作回退：快照 / Undo / Redo / 崩溃救援 / 安全模式

> 核心定位：Agent 工作可回退——Web UI / 快捷键 / API 一键撤销与恢复
> （Undo / Redo）；浏览全部历史快照一键回退任意版本（Rollback）；
> 主程序完全无法启动时用独立 CLI 崩溃救援（并提示最后一次正常
> 工作的快照）；安全模式只加载最小化内核，保住核心回退能力。

### 15.1 概念与四个层次

| 层次 | 能力 | 入口 |
|---|---|---|
| Undo / Redo | 撤销 / 恢复最近一次操作，进程内即时生效 | Web UI 按钮 / Ctrl+Z / Ctrl+Shift+Z / `npa.undo()` / `npa.redo()` |
| Rollback | 浏览全部历史快照，回退到任意版本 | Web UI「回退」面板 / `npa.rollback(id)` |
| Crash Rescue | 主程序无法启动时回退快照，提示最后正常快照 | `norpagent-rescue`（独立 CLI，纯标准库） |
| Safe Mode | 只加载最小化内核（跳过全部插件），保留核心回退能力 | `npa(safemode="on")` / CLI `--safe-mode` |

快照内容（模式 A，默认）：架构层全部槽位配置（模式 / 模型 / 工具 /
会话 / 沙箱 / 前端 / 插件目录 / 安全级别…）+ 引擎运行时参数 + WebUI
设置文件内容 + 自定义提供者数据。敏感键（api_key / token 等）**脱敏
后**才落盘。不可序列化的值（实例 / 类 / 函数）记录类型标记，回放时
跳过并提示（诚实降级，不伪造状态）。

快照模式 B：`npa(snapshot_sessions="on")` 额外把会话存储文件复制进
快照附件，回退时整文件恢复（会覆盖回退之后的对话记录）。

存储位置：默认 `~/.norpagent/snapshots/`（manifest.json 时间线 +
snap/ 每快照一个 JSON + attachments/ 会话附件 + rollback_target.json
救援回退目标）。可用环境变量 `NORPAGENT_SNAPSHOT_DIR` 或
`npa(snapshot_dir=...)` 覆盖，运行中可用 `npa.set_snapshot_dir()`
热切换存储目录（显式编程调用优先级最高）。自动快照默认开启
（`npa(snapshots="off")` 关闭），自动修剪保留最近 200 个。

### 15.2 快照与 Undo / Redo

自动快照时机：启动基线、每次系统状态变更（`npa.remount` / WebUI
设置保存 / 插件安装 / 模式切换）之后。手动快照：Web UI「回退」面板
「手动快照」按钮或 `npa.snapshot_system("说明")`。

```python
import norpagent as npa

npa()                                          # 启动（自动打基线快照）
npa.snapshot_system("装插件之前")               # 手动快照
# …做了几次变更（remount / 设置保存 / 装插件）…
npa.undo()                                     # 撤销最近一次操作（进程内即时）
npa.redo()                                     # 恢复撤销
npa.rollback("20260818T230101_ab12cd")         # 回退到任意快照
npa.rollback()                                 # 回退到最后一次正常快照
npa.list_snapshots()                           # 时间线（is_current / is_last_good）
npa.mark_good_snapshot("<id>")                 # 手动标记「正常」
```

语义要点：

1. **指针模型**：时间线 + 当前指针。Undo = 应用上一快照并前移指针，
   Redo = 应用下一快照；撤销后做新操作会**截断 redo 分支**（标准撤销
   语义）。
2. **进程内即时生效**：回放复用 remount 热挂载管线——组件槽位下一次
   run 生效、装配槽位热重建 AgentRuntime、HTTP 端口不变；与快照值
   相同的槽位跳过重挂（避免无谓的前端重启）。回放期间的变更**不会**
   再次自动快照（防撤销自拍覆盖 redo 分支）。
3. **Web UI**：左侧「回退」页 + 按钮 + 快捷键（Ctrl+Z / Ctrl+Shift+Z，
   输入框聚焦时不拦截）；后端 API `GET /api/snapshots`、
   `POST /api/snapshots {action: capture|undo|redo|rollback|mark_good}`。
4. **「最后正常」自动标记**：引擎启动成功后 30 秒健康期（或首个任务
   完成）自动 mark-good；也可手动标记。回退面板与救援 CLI 中 ★ 即
   最后正常快照。

### 15.3 自定义快照内容（钩子式扩展）

```python
from norpagent import recovery

# 采集钩子 + 恢复钩子（可选）
recovery.register_snapshot_provider(
    "my_state",
    capture=lambda engine: {"mark": 42},          # 任意 JSON 值
    restore=lambda engine, value: apply_mark(value),
)
# 注册即生效：后续所有快照都带 providers.my_state 段，
# 回放时调用 restore。重名覆盖；unregister_snapshot_provider 注销。
```

### 15.4 崩溃救援（独立 CLI，纯标准库）

`norpagent-rescue` 刻意**只依赖标准库**（读 / 写快照 JSON 与 WebUI
设置文件），主程序哪怕因配置错误或插件问题完全无法启动，救援工具
依然可用：

```bash
norpagent-rescue list                        # 时间线（★ = 最后正常）
norpagent-rescue show <id>                   # 查看快照内容（已脱敏）
norpagent-rescue rollback <id>               # 回退：恢复 WebUI 设置 + 写回退目标
norpagent-rescue rollback --last-good        # 一键回退到最后正常快照
norpagent-rescue mark-good <id>              # 手动标记「正常」
norpagent-rescue prune --keep 50             # 只保留最近 N 个
```

回退后下一次 `norpagent` / `npa()` 启动**自动消费**回退目标
（rollback_target.json，消费后删除）：文件级恢复（WebUI 设置 /
会话文件）立即执行，快照槽位配置合并进本次启动——**本次显式给出
的参数优先**（救援是兜底，不覆盖用户的自觉选择）。启动失败时 CLI
与 npa() 都会打印自救指引（安全模式 + 救援命令）。

### 15.5 安全模式（Safe Mode）

入口：`npa(safemode="on")`、CLI `norpagent --safe-mode`。未填写默认
不进入安全模式（任何非 on 值都不触发）。

行为（只加载最小化内核）：

1. **跳过全部插件目录**（插件是最可能的启动失败源）；
2. **强制 minimal 预设**（忽略用户给的 preset / plugins / security
   槽位参数）；
3. **不读 WebUI 设置文件**（坏配置可能就是上次崩溃的原因；纯内存
   运行，保存时也不再落盘）；
4. **保留核心回退能力**：Web UI「回退」面板与 `/api/snapshots`、
   `norpagent-rescue` 全部可用——启动后即可回退到任意正常快照，
   修复后正常重启。

```python
import norpagent as npa
npa(safemode="on")          # 最小化内核 + Web 回退面板
```

```bash
norpagent --safe-mode      # CLI 等价入口
```

### 15.6 人类救援：手动工具接管 API（模型失效时）

**场景**：模型提供方宕机 / API Key 失效 / 模型输出损坏——Agent 的
模型通道不可用，但工具执行能力仍然完好：工作区文件、沙箱、上下文
库、任务队列都仍可用。人类救援（Human Rescue，v0.9.3；自定义工具
支持 v0.9.7）把工具以人工可操作的形式暴露出来：操作者手动传参
（传入），读取原始执行结果（传出），在模型恢复前继续推进工作。
**默认暴露全部 20 个内置工具；v0.9.7 起注册表定义的自定义工具、
工具槽位安装的工具、外部插件的工具同样支持手动操作**（15.6.3）。

**设计原则**：

1. **与模型走完全相同的执行路径**——手动调用与模型发起调用共用
   同一个 `tool.run(args, ctx)` 与 `RunContext`（registry / sandbox /
   session / scheduler / context_store / project_manager 一个不少），
   写入同一份状态：文件落在同一个 workspace、`context_add` 写入
   同一份上下文库、`task_submit` 进入同一张任务队列；
2. **默认不加载任何插件**（插件是最可能的故障源）；显式传入
   `--plugin-dirs` / `plugin_dirs` 时经与主程序相同的安全管线
   （签名 → 审计 → 导入限制 → 注册）加载，插件工具同样可手动调用；
3. **硬超时 + 取消信号**：每次调用在独立工作线程执行，超时即弃置
   （daemon 孤儿线程，与模型调用超时同一模式），并置位取消事件——
   沙箱强杀子进程树、流式循环尽早退出；
4. **默认仅监听 127.0.0.1**，可选 Bearer token——这是真实执行命令 /
   写文件的端点，绝不暴露到本机之外。

四种入口（`tools / tool-call / manual / serve` 均支持
`--tools` 与 `--plugin-dirs`，见 13.5）：

```bash
norpagent-rescue tools                              # 列出全部工具清单（含来源标注）
norpagent-rescue tool-call echo --args '{"text":"ping"}'
norpagent-rescue tool-call exec_cmd --args '{"command":"git status"}' --timeout 30
norpagent-rescue manual                             # 交互式手操台（人就是模型）
norpagent-rescue serve --port 8799                  # HTTP API + 操作员页面
norpagent-rescue serve --token my-secret            # 带 Bearer 认证

# v0.9.7：自定义工具手动操作
norpagent-rescue tools --tools myapp.tools:create   # 模块地址加载自定义工具
norpagent-rescue tools --plugin-dirs ./my_plugins   # 加载外部插件工具
norpagent-rescue serve --tools t1,t2 --plugin-dirs ./p1,./p2
```

#### 15.6.1 交互式手操台（manual）

```text
rescue> echo {"text": "ping"}                        # <工具名> <JSON 参数>
rescue> {"tool": "file_list", "args": {}}            # JSON 对象形式
rescue> /tools                                       # 列出全部工具
rescue> /exit                                        # 退出
```

与 CLI 快照命令（list / rollback 等）的边界：`rescue.py` 模块顶层
**依然只依赖标准库**；`tools / tool-call / manual / serve` 在命令
函数内部惰性导入框架（`norpagent.rescue_api`）——主程序坏到完全起
不来时，快照回退仍然可用；框架能导入时，手操接管才可用。

#### 15.6.2 HTTP API 与操作员页面

`norpagent-rescue serve` 启动零依赖 HTTP 服务（stdlib
ThreadingHTTPServer），浏览器打开根路径即得操作员页面（内联 HTML/
JS，无任何外部资源）：下拉选工具 → 自动展示 schema 与必填参数 →
手填 JSON 参数与超时 → 调用 → 原始结果 + 历史记录。

| 端点 | 方法 | 说明 |
|---|---|---|
| `/` | GET | 操作员页面（内联 HTML，下拉列表标注工具来源） |
| `/api/health` | GET | 状态 / 工具数 / **custom_tools 数** / workspace 根 |
| `/api/tools` | GET | 全量清单：`{tools:[{name,description,parameters,required,category,origin}]}` |
| `/api/tools/<name>` | GET | 单个工具 schema |
| `/api/tools/call` | POST | body `{"tool":"echo","args":{...},"timeout":N,"params":{...}}` |
| `/api/tools/<name>/call` | POST | body `{"args":{...},"timeout":N}` |

清单中每个工具带 `origin` 字段：`builtin`（框架内置 20 个）/
`custom`（`--tools` / `extra_tools` 注册）/ `plugin`（插件目录加载），
操作员页面据此标注工具来源。

```bash
curl -s http://127.0.0.1:8799/api/tools/call \
  -H "Content-Type: application/json" \
  -d '{"tool":"context_search","args":{"query":"marker"}}'
```

响应统一为：

```json
{
  "ok": true, "tool": "echo", "task_id": "1a2b3c4d5e6f",
  "output": "[echo] ping", "error": "", "success": true,
  "timed_out": false, "duration_ms": 0.4
}
```

语义：`ok=false` 但 HTTP 200 = 工具执行失败（参数错 / 业务失败）；
HTTP 404 = 工具未注册；400 = JSON 请求体非法；401 = token 缺失或
错误（仅当配置了 token）；413 = 请求体超过 1 MB。超时弃置返回
`timed_out=true`（HTTP 200，调用者无需再等）。

#### 15.6.3 环境组装与默认值

`RescueToolEnvironment` 用 `install_defaults()` 装配全量内置组件
（与 standard 预设同源），并在环境生命周期内共享：

| 组件 | 默认 | 说明 |
|---|---|---|
| 沙箱 | subprocess | 每条命令独立子进程；手动调用同样受路径安全约束 |
| 会话 | memory | 固定救援会话（rescue-manual） |
| 调度器 | **persistent** | task_* 全部工具可用；默认共享主程序任务库 `~/.norpagent/tasks.db`——可直接查看模型宕机前提交的任务 |
| 上下文库 | fts5 | 默认共享 `~/.norpagent/context.db`；`--context-db` 可隔离 |
| 项目管理 | basic | `project_status` 可用 |
| workspace | 当前目录 | `--workspace` 指定；file_* 的路径安全边界随之移动 |

**自定义工具（v0.9.7）**：`RescueToolEnvironment` 构造参数
`extra_tools` / `tools` / `plugin_dirs` / `plugin_config` 按以下顺序
装配（注册表内名字覆盖语义，后注册覆盖先注册）：

```python
from norpagent.rescue_api import RescueToolEnvironment

env = RescueToolEnvironment(
    workspace_root=".",
    extra_tools={"my_tool": MyTool()},   # {name: Tool} 映射 / Tool 列表 / 名字或地址列表
    tools=["my_other_tool", "mypkg.tools:create"],  # 已注册名引用 + 模块地址
    plugin_dirs=["./my_plugins"],        # 外部插件目录（安全管线加载）
    plugin_config={"plugin_security_audit": "warn"},
)
```

- `extra_tools` 先注册，`tools` 中的**名字引用**可以指向
  `extra_tools` 已注册的工具，也可指向内置工具；**模块地址**
  （`pkg.mod:attr`，与 `npa(tools=[...])` 槽位语义一致）按
  `norpagent.arch.address.resolve_address` 解析，解析失败抛明确错误；
- `plugin_dirs` 经与主程序相同的安全管线加载（默认
  `plugin_security_audit=warn`、`plugin_signature_verify=True`），
  插件注册的工具以 `origin="plugin"` 标记；
- 注册顺序：内置 20 工具 → `extra_tools` → `tools` → 插件工具；
- CLI 等价参数：`--tools`（逗号分隔名字或地址）、`--plugin-dirs`
  （逗号分隔目录），见 13.5。

注意：persistent 调度器意味着 `norpagent-rescue tools` 也会落盘
创建任务库（若不存在）。希望完全无盘时传 `--scheduler simple`
（task 查询类工具会如实返回「当前调度器不支持查询」）。

#### 15.6.4 隔离与安全边界

- **无模型、无插件、无钩子**：`before_tool_call` 等钩子不介入
  （救援环境不订阅任何钩子，操作者即最终审批人）；
- **路径安全照常生效**：`file_*` 的绝对路径 / `..` 穿越拒绝、
  `run_python` 的 AST 静态预检（禁 import / 禁魔法属性）照常；
- **超时双层兜底**：工具自带超时（exec_cmd 最大 300s、
  run_python 的 `ptc_timeout`）+ 环境级硬超时（默认 300s，HTTP
  body 或 `--timeout` 可调）——单次调用超时弃置线程并置位取消
  事件，不影响后续调用；
- **并发安全**：环境线程安全（组件内部均有锁），多个 HTTP 请求
  可并行手操；上下文库 / 任务库共用同一连接与锁。

#### 15.6.5 程序化嵌入

```python
from norpagent.rescue_api import RescueToolEnvironment, RescueToolAPI
from my_tools import MyTool   # 自定义工具实现

env = RescueToolEnvironment(
    workspace_root=".",
    context_db="./rescue.db",
    extra_tools={"my_tool": MyTool()},   # 自定义工具手动可调
    tools=["mypkg.tools:create"],        # 或模块地址加载
    plugin_dirs=["./my_plugins"],        # 或外部插件
)
print(env.call_tool("echo", {"text": "ping"})["output"])
print(env.call_tool("my_tool", {"arg": 1})["output"])  # 自定义工具同样可调

api = RescueToolAPI(env, port=0, token="secret")   # port=0 随机端口
port = api.start()                                 # 返回实际端口
api.shutdown()
```

应用侧也可在模型健康检查失败后自动拉起救援服务（例如把
`RescueToolAPI` 挂在现有进程里），供值班人员接管。

#### 15.6.6 与其他救援层的关系

| 层级 | 目标 | 入口 |
|---|---|---|
| 快照回退 | 配置/插件坏了，回退到正常状态 | `norpagent-rescue rollback --last-good` |
| 安全模式 | 起不来也要保留回退能力 | `npa(safemode="on")` / `--safe-mode` |
| **人类救援** | **模型死了，人替模型干活** | `norpagent-rescue tools / tool-call / manual / serve` |

三者互补：先回退（或安全模式）救配置，再用手操接管推进工作，模型
恢复后由 Agent 从同一份状态（文件 / 上下文库 / 任务队列）继续。

---

## 第 16 章　库集成示例

### 16.1 FastAPI 集成

```python
import norpagent as npa
from fastapi import FastAPI

npa(preset="standard", frontend="norpagent.frontends.headless:HeadlessFrontend")
app = FastAPI()

@app.post("/chat")
def chat(text: str, session_id: str | None = None):
    result = npa.current().submit(text, session_id=session_id)
    return {"content": result.final_content, "session_id": result.session_id,
            "status": result.status}
```

### 16.2 桌面应用集成（pywebview 风格）

```python
import norpagent as npa

npa(frontend="myapp.tray_frontend:TrayFrontend")
fe = npa.current().frontend

# JS 桥接层把用户输入转发给 fe.send()；
# 事件总线订阅 on_content 把流式输出推回前端。
```

### 16.3 集成要点

1. **单例引擎**：运行中的引擎是单例，`npa()` 幂等返回当前引擎；
2. **生命周期**：主循环轮询 `npa.stop()`，进程退出有 atexit 兜底清理；
3. **装配观测**：`npa.current().layer.describe()` 打印装配清单。

---

## 第 17 章　测试与调试

```bash
python tests/test_p1_smoke.py    # 内核/协议冒烟
python tests/test_p2_smoke.py    # 适配器/工具/会话
python tests/test_p3_smoke.py    # 上下文/调度/沙箱/安全/插件/Web
python tests/test_p4_smoke.py    # 钩子/安全/PTC/隔离
python tests/test_p5_arch.py     # 架构层/地址函数/npa()/nasyncio
```

调试辅助：

```python
eng = npa.current()
print(eng.state)              # 引擎状态
print(eng.layer.describe())   # 装配清单
print(eng.last_result)        # 最近任务结果
```

---

## 第 18 章　迁移指南

### 18.1 从旧版 norpagent（≤0.4）迁移

```python
# 旧写法：手工装配
reg = Registry(); install_defaults(reg); register_all_presets(reg)
agent = AgentRuntime(reg, preset="minimal")
result = agent.run("你好")

# 新写法：npa() 装配（手工装配 API 保留可用）
import norpagent as npa
npa(preset="minimal", prompt="你好",
   frontend="norpagent.frontends.headless:HeadlessFrontend")
while True:
    if npa.stop():
        break
result = npa.current().last_result
```

手工装配 API（Registry / AgentRuntime / Preset）**保留可用**；
`npa()` 是其声明式封装。

### 18.2 从旧桌面应用迁移

旧应用中的模块可按以下映射接入槽位：

| 旧应用模块 | 新槽位 | 接入方式 |
|---|---|---|
| `nasync_io`（自研事件循环） | `async_loop` | **已打包进库**：`norpagent.nasyncio` 即默认调度核心（原 nasync_io v2.0.0），无需自带文件；如需换实现再填地址 |
| `async_loop.AsyncAgentLoop` | `agent_runtime` | 实现 run/shutdown → 填地址 |
| FastAPI 后端 + 桌面 UI | `frontend` | 实现 Frontend 协议 → 填地址 |
| `plugin_system` | `plugins` | 目录列表直接传 |
| `sandbox_pool` | `sandbox` | `"pooled"` 或自研地址 |
| `config.json` 各开关 | 预设 params | 任务参数透传 |

### 18.3 版本兼容

- 协议模块（protocols）与内核（kernel）自 0.1 起向后兼容；
- 0.5 新增 arch / loops / frontends / runtime 四个包；
- 0.6 新增 FLOW 流程编排 / FE 前端模块 / 输入框体系 /
  智能体工具挂载（agent_tools）/ 画布管理三件套；DeepSeek
  `deepseek-chat` / `deepseek-reasoner` 已于 2026-07-24 被官方
  停用，适配器默认走 `deepseek-v4-flash`；
- 0.7 新增 Web 前端 `html` 槽位挂载参数（`;key=value` 地址子句 /
  构造函数 / 配置字典 / 运行时参数四种途径替换 `/` 路由页面），
  并修复 `;key=value` 地址子句的解析链路；新增**运行中热挂载**
  （`npa.remount()` 任何槽位运行时替换，见 3.7 节）；
- 0.8 默认事件循环迁移到**自研 nasyncio 核心**（原 nasync_io
  打包进库为 `norpagent.nasyncio`）：库内**零 `import asyncio`**，
  不再依赖标准 asyncio（原因见 4.7）。默认地址改为
  `norpagent.loops.nasyncio:NasyncioLoopRuntime`；0.7 旧地址
  `norpagent.loops.std_asyncio:StdLoopRuntime` 保留为兼容垫片
  （同一实现，不 import asyncio），历史代码不失效；
- 0.9 嵌入式与超高并发专项优化（第 14 章）：`install_core()`
  极简装配与 builtin 包懒导入（`import norpagent.builtin` 不再拉
  sqlite3 / http.server）、`embedded` 预设（第六模式，默认 headless
  前端）、WebUI 构造零磁盘 I/O 与页面字节缓存、EventBus 写时复制、
  SSE 有界背压（默认 drop_oldest，可热改变）+ 帧批量写出 + 断连
  快速回收、HTTP 并发调优、submit 轮询默认收紧到 0.05s（可配）。
  行为兼容：SSE 默认缓冲上限 1024 条（慢客户端丢最旧，此前为
  无界）；`unlimited` 策略 + `sse_queue_size=0` 可还原旧行为；
- 0.9 槽位表热插拔（3.8 节）：`register_slot()` / `unregister_slot()`
  运行时注册 / 注销**自定义槽位**（`SlotSpec.applier` 声明装配逻辑，
  `remount_rebuild_agent` 声明热替换后是否热重建 AgentRuntime），
  注册即接入 `npa()` 参数校验、ArchLayer 装配（connect 幂等补齐晚
  注册槽位）、`npa.remount()` 热替换、`layer.describe()` 清单全管线；
  支持 `replace=True` 规格热替换；内置 18 槽位受保护（值仍可随时
  热替换）；槽位表操作线程安全。行为兼容：既有 18 槽位装配 / 热挂载
  语义完全不变；
- 0.9 工作回退（第 15 章）：快照时间线 + Undo / Redo / Rollback
  （进程内即时生效，复用 remount 热挂载管线）+ 独立崩溃救援 CLI
  `norpagent-rescue`（纯标准库，提示最后正常快照一键恢复，回退
  目标下次启动自动消费）+ 安全模式（`npa(safemode="on")` / CLI
  `--safe-mode`，只加载最小化内核）；自动快照默认开启（remount /
  设置保存 / 插件安装后），敏感键脱敏落盘，支持自定义快照提供者
  与快照模式 B（含会话数据文件）；
- 删除性变更只会出现在大版本。

---

## 第 19 章　常见问题（FAQ）

**Q1：`npa()` 会阻塞吗？**
不会。引擎在后台线程运行，主线程继续执行——这正是
`while running: if npa.stop()` 模式存在的原因。

**Q2：`npa.stop()` 什么时候变 True？**
引擎 STOPPED：单次任务跑完、前端 `/exit`、显式 `shutdown()`、
或任何 `request_stop()`。没有引擎时恒为 True。

**Q3：怎么传模型 API Key？**
```python
npa(model="openai_compat", model_name="deepseek-v4-flash",
   base_url="https://api.deepseek.com/v1", api_key="sk-...")
```
`model_name / base_url / api_key` 是模型快捷参数：当模型是内置适配器名
时自动重新构造提供者（与 CLI 行为一致）；或直接设置环境变量
`OPENAI_API_KEY`；或传构造好的提供者实例 `npa(model=MyProvider())`。

**Q4：地址字符串会不会造成任意代码执行？**
会。地址字符串指定要加载的模块，地址值由库的使用者在代码中传入。
外部插件加载经过签名校验、AST 审计与导入限制。

**Q5：我能同时跑两个不同的 Agent 吗？**
运行中的引擎是单例。需要多实例时直接用手工装配 API：
`Registry() + AgentRuntime(...)`，不受单例约束（第 17.1 节）。

**Q6：循环系统替换后钩子还工作吗？**
工作。钩子挂在事件总线（底层最小内核）上，与循环系统无关。

**Q7：`npa(async_loop=...)` 和 `npa.nasyncio(...)` 有什么区别？**
没有区别，同一条路径；前者是槽位写法，后者是架构函数写法。

**Q8：`/flow` 画布、FE 前端模块、输入框体系是什么？**
`/flow` 是独立前端分类「模块流程」：画布图自动保存并可用
「应用到智能体」热切换 front 聊天行为。FE = 拖入 `.html/.js/.ts`
文件注册的前端模块（托管 `/fe/<name>`，独立配置作用域）。输入框
体系 = 一切需要输入的地方都是输入框：FE / 全局设置节点卡片上每个
配置项一行输入框、model/tool/sandbox 等节点卡片底部带值输入框带、
所有模型字段均为可手输输入框 + datalist 提示（拉取失败也能手输）。
详见第 5.7 节与 `docs/flow.md`。

**Q9：画布怎么批量清理？deepseek-chat 还能用吗？**
画布：`Alt+拖拽` 框选 / `Ctrl+A` 全选后 `Del` 批量删除，顶栏
「清空画布」一键清空（确认后立即保存，刷新保持空白）；双击空白
注入与单击坞卡片快速注入已移除（防误触铺节点）。deepseek-chat /
deepseek-reasoner 已于 2026-07-24 被 DeepSeek 官方停用，现役为
deepseek-v4-flash / deepseek-v4-pro；旧名在提示列表、远端模型坞
与后端缓存中自动过滤（`RETIRED_REMOTE_MODELS`）。

**Q10：网页端原生工具太少，怎么接第三方自定义工具并让智能体自动调用？**
「文件即模块」接入：把声明 `__norpagent_type__ = "tool"` 的 `.py`
文件拖进 `/flow` 画布即真实注册（走插件安全管线），工具节点端口
自动来自 OpenAI function schema。要让 front 聊天里的智能体自动调用
（tool calling）：① `/flow` 模块坞工具卡点 `AGENT` 徽章挂载；
② WebUI 设置弹窗「🧰 智能体工具」清单勾选。二者都经
`POST /api/agent/tools`（配置键 `agent_tools` /
`agent_tools_explicit`）热应用 `preset.tools`，下一次 run() 即生效，
无需重启。详见第 5.7 节「智能体工具挂载」与 `docs/flow.md` 第 9 节。

**Q11：启动后能换模型 / 换前端 / 换模块吗？（运行中热挂载）**
能。`npa.remount(slot=value)` 在引擎运行中替换任意槽位：组件槽位
（model / tools / hooks / security / plugins）下一次 run() 生效；
装配槽位（session / sandbox / scheduler / ui / agent_runtime /
preset / context_store / project_manager）触发 AgentRuntime 热重建；
frontend / async_loop 停旧启新；logger / storage / error_handler
即时更新。字符串地址在重挂载前自动失效模块缓存与 .pyc，
「改模块文件 → npa.remount(model="myapp.model:create")」即热重载。
重复挂载的架构级订阅先退订再重挂，不叠加。详见第 3.7 节。

**Q12：Ctrl+C 为什么之前会失灵？现在怎么保证打断得了？**
两个根因（详见第 4.6 节）：① Windows 上主线程阻塞在一次性
`Event.wait()`（`WaitForSingleObject`）里收不到 SIGINT——pending
interrupt 只在字节码边界被检查；现在 `submit()` 改为轮询等待
（每 ≤poll_interval 秒一次边界，默认 0.05s，可配），Ctrl+C 即刻
冒出 `KeyboardInterrupt`。
② 卡在沙箱 `subprocess` / HTTP 里的工作线程杀不死，且标准线程池
（ThreadPoolExecutor，asyncio 的默认执行器也是它）在解释器退出时
被强制 join——任务不结束进程就僵住；现在工作池用裸守护线程
（退出不 join），且 Ctrl+C / 引擎停止会置位任务的取消事件：
PTC 沙箱立即强杀子进程、池化沙箱杀进程树、模型流式中断、
Agent 轮次边界以 stopped 收尾。任务执行体可用
`norpagent.loops.cancel.cancel_requested()` 主动响应取消。

**Q13：norpagent 依赖标准 asyncio 吗？**
不依赖。0.8 起库内**零 `import asyncio`**：默认调度核心是打包
进库的自研异步 IO 库 `norpagent.nasyncio`（原 nasync_io），底层
只用 threading / selectors / socket 等非 asyncio 标准模块。
声明、原因与验证方式详见第 4.7 节。

**Q14：嵌入式设备 / 超高并发服务器怎么部署？（0.9）**
- **嵌入式**：`install_core()` 自建注册表（不导入 sqlite3 /
  http.server）+ `build_embedded_preset()`，或直接
  `npa(preset="embedded")`（默认 headless 前端、mock 回落）；工作
  线程数用 `NORPAGENT_MAX_WORKERS=1`（或 `config={"loop":
  {"max_workers": 1}}`）收紧，轮询用 `NORPAGENT_SUBMIT_POLL` 放宽。
- **超高并发**：SSE 每连接有界缓冲默认 1024 条、慢客户端丢最旧
  （`drop_oldest`），启动时 `npa(config={"web": {"sse_queue_size":
  2048}})` 配置，运行中 `WebUI.set_sse_queue(...)` / `POST
  /api/streams` 热改变；帧批量写出（默认 32 条 / 50ms）降低系统
  调用；EventBus 写时复制免每事件列表复制。完整说明见第 14 章。

**Q15：框架没有我需要的槽位怎么办？（槽位表热插拔，0.9）**
自己注册一个：`register_slot(SlotSpec(name=..., string_semantics=...,
applier=...))`。注册即接入 `npa()` 参数校验、装配、`npa.remount()`
热替换、`layer.describe()` 清单全管线；applier 拿到解析后的槽位值
与 components / extras / overrides / meta 四个可变容器，可注册通用
组件（`remount_rebuild_agent=True` 时热替换后热重建 AgentRuntime）、
挂事件订阅（用 meta 记录退订，保证重入安全）、或向引擎提供附加
对象。内置 18 槽位受保护不可覆盖 / 注销，其值可随时 `npa.remount`
热替换。完整契约见 3.8 节。

**Q16：怎么撤销一次配置变更 / 回退到之前的状态？（工作回退，0.9）**
三步走：进程内 `npa.undo()` / `npa.redo()`（Web UI Ctrl+Z /
Ctrl+Shift+Z 或「回退」面板按钮，即时生效）；回退任意版本
`npa.rollback("<快照id>")`（`npa.list_snapshots()` 浏览时间线，
`npa.rollback()` 无参 = 最后正常快照）；主程序起不来了用
`norpagent-rescue rollback --last-good`（纯标准库 CLI，下次启动
自动应用），或 `norpagent --safe-mode` / `npa(safemode="on")`
只加载最小化内核修配置。快照默认存 `~/.norpagent/snapshots/`，
敏感键脱敏，自动快照默认开启（可 `npa(snapshots="off")` 关闭）。
完整语义见第 15 章。

---

## 附录 A　架构槽位速查表

| 槽位 | 字符串语义 | 默认 | 工厂上下文键 |
|---|---|---|---|
| async_loop | address | NasyncioLoopRuntime（自研 nasyncio 核心；config.loop 调 max_workers / poll_interval） | layer, config |
| agent_runtime | address | AgentRuntime | registry, preset, ui, task_params, layer, config |
| model | name_or_address | 预设声明 | layer, config |
| tools | name | 预设声明 | - |
| session | name_or_address | 预设声明 | - |
| sandbox | name_or_address | 预设声明 | - |
| scheduler | name_or_address | 预设声明 | - |
| context_store | address | 预设声明 | layer, config |
| project_manager | address | 预设声明 | layer, config |
| hooks | literal | 标准 9 层 | - |
| security | literal | 不开启 | - |
| plugins | literal | 不加载 | - |
| frontend | address | prompt / embedded→headless，否则 web | layer, config |
| ui | name | 预设声明 | - |
| preset | name | standard | - |
| logger | literal | logging.getLogger("norpagent") | - |
| storage | literal | ~/.norpagent | - |
| error_handler | literal | 记录日志 | - |

> 运行中热挂载（3.7）：所有槽位均可 `npa.remount(slot=value)` 替换。
> `agent_runtime` 为 `defer_factory` 槽位（工厂推迟到引擎装配期调用）。
> 槽位表热插拔（3.8）：`register_slot()` 可注册自定义槽位加入本表。

## 附录 B　9 层钩子速查表

| 层 | 钩子 | 可变 | 关键参数 |
|---|---|---|---|
| L1 生命周期 | on_agent_init / on_agent_shutdown | - | preset |
| L2 任务 | on_task_start / on_task_done / on_task_stopped / on_task_error / on_task_timeout | - | task_id, session_id |
| L3 输入 | before_input / after_input / on_user_input_required | before | user_input, params, question |
| L4 会话 | before_session_create / after_session_create / before_message_append / after_message_append | before | title, message |
| L5 组装 | before_build_messages / after_build_messages | 两者 | system_prompt, messages |
| L6 步骤 | before_step / after_step | before | step, messages |
| L7 模型 | before_model_call / after_model_call / on_reasoning / on_content / on_event / on_usage_update | before/after_model_call | messages, output, params |
| L8 工具 | before_tool_call / after_tool_call / on_tool_error | 两者 | tool_name, args, result |
| L9 定型 | before_result / after_result | 两者 | result |

> 完整负载键与 29 钩子全表见 9.1 节；可变钩子的完整返回语义（HookVeto 收尾 / 改写规则）见 9.3 节。
> 插件加载管线另有 8 个钩子（PLUGIN_PIPELINE_LAYER），见 11.4 节。

## 附录 C　公开 API 索引

```python
# 模块入口
npa()                      # launch()
npa.stop()                 # 生命周期轮询
npa.nasyncio(address=...)  # 事件循环架构函数（npa.nasyncio 绑定自研核心模块，可调用）
npa.current() / npa.submit() / npa.shutdown()
npa.remount(model=..., ...)   # 运行中热挂载：任何槽位均可替换

# 工作回退（第 15 章）
from norpagent.recovery import (snapshot_system, undo, redo, rollback,
                                list_snapshots, mark_good, last_good_id,
                                register_snapshot_provider, set_snapshot_dir,
                                prune, RecoveryError)
npa.snapshot_system("说明")        # 手动快照（顶层便捷入口）
npa.undo() / npa.redo()             # 撤销 / 恢复（进程内即时生效）
npa.rollback("<id>")               # 回退到任意快照（缺省 = 最后正常）
npa.mark_good_snapshot("<id>")     # 标记「正常」
npa(safemode="on")                 # 安全模式：只加载最小化内核
npa(snapshot_dir=..., snapshots="off", snapshot_sessions="on")  # 快照配置
# 崩溃救援：norpagent-rescue list|show|rollback|mark-good|prune
# 人类救援（15.6）：norpagent-rescue tools|tool-call|manual|serve
#   v0.9.7 自定义工具：--tools <名|pkg.mod:attr>[, ...]  --plugin-dirs <目录>[, ...]
from norpagent.rescue_api import (RescueToolEnvironment, RescueToolAPI)
env = RescueToolEnvironment(workspace_root=".", context_db="./rescue.db")
env = RescueToolEnvironment(extra_tools={"my_tool": MyTool()},
                            tools=["pkg.mod:create"],
                            plugin_dirs=["./my_plugins"])   # v0.9.7 自定义工具
env.call_tool("echo", {"text": "ping"})     # 手动传参 + 读取原始结果
api = RescueToolAPI(env, port=0, token=...) # HTTP API + 操作员页面
api.start() / api.shutdown()

# 架构层
from norpagent.arch import ArchLayer, SlotSpec, SLOT_SPECS
from norpagent.arch import resolve_address, call_factory, AddressError
layer.remount(slot, value)  # 架构层热挂载（模块缓存 + pyc 失效）
layer.subconfig(slot)       # 槽位附加子配置（";key=value"）

# 槽位表热插拔（3.8）
from norpagent.arch import (register_slot, unregister_slot, SlotError,
                            all_slot_names, snapshot_slots, is_builtin_slot)
register_slot(SlotSpec(name=..., string_semantics=..., applier=...,
                       remount_rebuild_agent=...))   # 注册自定义槽位
register_slot(spec, replace=True)   # 热替换自定义槽位规格
unregister_slot(name)               # 注销自定义槽位

# 循环系统
from norpagent.loops import (nasyncio, LoopRuntime,
                             NasyncioLoopRuntime, StdLoopRuntime)
from norpagent.loops.cancel import cancel_requested, current_cancel_event
loop.interrupt()   # 请求取消全部在途 submit 任务（引擎停止路径）

# 自研异步核心（已打包进库，不依赖标准 asyncio）
import norpagent.nasyncio as core
core.EventLoop / core.Future / core.Task        # 自研类型
core.sleep / core.wait_for / core.ensure_future # 工具协程
core.run_coroutine_threadsafe(coro, loop)       # 跨线程提交协程
core.Event / core.Lock / core.Condition         # 同步原语
# 救援级底层循环控制（第 24 章）：
#   loop.abort_main()        # 强停：向主任务注入 CancelledError（外部线程可调）
#   loop.call_soon_threadsafe(cb)  # 跨线程投递 + 自管道唤醒
#   loop.stop() / loop.run_forever() / loop.run_until_complete(coro)
#   loop.call_later(delay, cb)     # 定时回调（仅循环线程内调用，同 asyncio 契约）

# 前端
from norpagent.frontends import (Frontend, ConsoleFrontend,
                                 HeadlessFrontend, WebFrontend)

# 运行时
from norpagent.runtime import (launch, current, stop, submit,
                               shutdown, NorpEngine, EngineState, EngineError)
# 任务级槽位注入（3.9）：submit(text, slot_overrides={...})
#   engine.submit("任务", slot_overrides={"model": "anthropic", "tools": [...]})
#   npa.submit("任务", slot_overrides={"session": {"name": "memory", "persist": True}})

# 内核（手工装配，等价保留）
from norpagent import (Registry, EventBus, Preset, AgentRuntime,
                       RunResult, install_defaults, install_core,
                       register_all_presets, build_embedded_preset)
# install_core(reg)：嵌入式极简装配（无 sqlite3 / http.server 依赖）
# build_embedded_preset()：嵌入式预设（第六模式）
# 通用事件总线（27.2，类名 EventBus）：
#   bus.once(fn, type=None)          # 一次性订阅（触发即自动退订）
#   bus.wait(type, timeout=None)     # 阻塞等待事件 → AgentEvent | None
#   bus.emit_all(type, **kw)         # 发布并收集全部订阅者返回值 → list
#   bus.subscriber_count(type=None)  # 订阅者数量
#   bus.has_listeners(type=None)     # 是否有订阅者
#   bus.clear(type=None)             # 清空订阅（返回移除数）

# 安全 / 钩子 / 插件
from norpagent import safe, SafetyKit, SecurityContext
from norpagent import hooks                      # 钩子系统（HookSystem）
from norpagent.hooks import (Hook, BoundHook, HookLayer, HookSystem,
                             HookVeto, get_default_system,
                             before_input, before_model_call,
                             before_tool_call, after_tool_call, ...)  # 29 个标准钩子
from norpagent.plugins import (PluginSystem, PluginLoader, PluginInfo,
                               install_plugin_dirs, PLUGIN_PIPELINE_LAYER,
                               before_plugin_load, after_plugin_register, ...)
from norpagent.plugins.isolation import ProcessIsolationManager, ProcessPluginHost
from norpagent.security import (scan_message, harden_system_prompt,
                                ApprovalPolicy, NetworkPolicy, SourceAuditor,
                                SignatureVerifier, generate_keypair, sign_plugin_file)

# Web UI：页面挂载与热替换（5.4）+ SSE 背压（超高并发，第 14.3 节）
from norpagent.builtin.ui.web import WebUI
ui = WebUI(port=8787, html="/path/to/my.html",
           flow_html="/path/to/flow.html")     # / 与 /flow 页面整体替换
ui = WebUI(port=8787, sse_queue_size=2048,
           sse_queue_policy="drop_oldest")
ui.mount_page("flow", "/path/to/new-flow.html")  # 运行中热换页（不重启服务）
ui.mount_page("flow", None)                      # 卸载挂载，回落库内置
ui.page_bytes("flow")                            # 当前 /flow 页面字节
ui.set_sse_queue(4096, "drop_newest")   # 运行中热改变（POST /api/streams 等价）
ui.streams_info()                        # 订阅者数 / 丢弃事件数 / 缓冲深度
# WebFrontend 同构入口：frontend.mount_page(page, html)
# remount 页面热替换键（v0.9）：
#   npa.remount(flow_html="/path/to/new-flow.html")  # /flow 立即换页
#   npa.remount(html="/path/to/new-front.html")      # / 主页面立即换页
#   npa.remount(flow_html=None)                      # 卸载挂载，回落库内置
# frontend 槽位 HTML 路径直挂（v0.9）：
#   npa(frontend="/path/to/my.html")  ==  npa(frontend="...WebFrontend;html=/path/to/my.html")
```

**Q17：标准库 asyncio 与自研 nasyncio 能同时使用吗？**
可以，二者互不冲突、可在同一进程内同时使用：norpagent 的调度只走 `async_loop`
槽位上的自研 nasyncio（不 import、不接管标准 asyncio）；你自己的代码照常使用
标准 asyncio（含 `asyncio.run`）不受影响；两边相遇时走线程安全 API
（`run_coroutine_threadsafe` / `LoopRuntime.submit`）协作。详见 §4.7。

---

## 第 20 章　模块流程编排（FLOW）

> 本章对应代码：`norpagent/flows/__init__.py`（1535 行，框架最大的编排内核之一）。
> 5.7 节讲了 `/flow` 页面的前端形态；本章深入其**内核**：注册表快照、
> 文件即模块、拓扑执行与智能体联动。

### 20.1 定位与总览

「模块流程」（`/flow`）不是动画演示，而是用**真实注册组件**执行画布图：

```
build_snapshot(registry, agent)   注册表快照：模型 / 工具 / 会话 / 沙箱 /
                                 调度器 / 插件 / 预设 / 钩子
                                 → 前端「核心模块坞」按真实组件渲染卡片
ModuleWorkspace.register(...)    「文件即模块」：拖入 .py 走完整安全管线
                                 （签名校验 → AST 审计 → 导入限制 → 注册）
FlowRunner                       按画布图（节点 + beam）拓扑执行，
                                 进度经 flow.* 事件经 SSE 推送
```

三个核心类 / 函数：

| 名称 | 职责 |
|---|---|
| `build_snapshot(registry, agent)` | 把注册表当前状态序列化为快照 dict，驱动前端模块坞 |
| `ModuleWorkspace` | 流程模块的落盘工作区：注册 / 加载 .py / .json / .yaml 模块 |
| `FlowRunner` | 画布图执行器：节点 + beam 拓扑执行、零中断、事件发布 |

### 20.2 注册表快照：build_snapshot

```python
from norpagent.flows import build_snapshot

snap = build_snapshot(registry, agent)
# 包含：models / tools / sessions / sandboxes / schedulers /
#       plugins / presets / hooks（每个已注册组件一条记录）
```

- 快照是**实时**的：注册表里注册了什么，前端模块坞就显示什么；
- 每个组件附带元信息（描述 / 来源 / 端口推断），供画布渲染；
- 快照驱动「模块坞 → 拖入画布 → 实例选择」的完整交互。

### 20.3 文件即模块：ModuleWorkspace

```python
ws = ModuleWorkspace(registry, base_dir=default_modules_dir())
info = ws.register("my_node.py")      # 走插件安全管线
info = ws.register("graph.json")      # 纯描述模块（直通节点）
info = ws.register("graph.yaml")      # 同上
```

| 文件类型 | 处理方式 |
|---|---|
| `.py` | 完整安全管线：签名校验 → AST 审计 → 导入限制 → 注册进注册表；注册成功的插件钩子会逐个成为画布上的钩子节点 |
| `.json` / `.yaml` | 注册为纯描述模块（直通节点，无执行逻辑） |
| 其它 | 明确报错，由前端回退到官方模块 |

- 模块目录：环境变量 `NORPAGENT_FLOW_MODULES` 可覆盖，默认 `~/.norpagent/flow_modules`；
- 单文件大小上限 200KB（`_MAX_MODULE_SIZE`）。

### 20.4 画布图格式：normalize_graph

画布图是「节点 + beam」的 dict 结构，`normalize_graph` 负责规范化与校验：

```python
graph = {
    "nodes": [
        {"id": "n1", "type": "trigger"},
        {"id": "n2", "type": "model", "model": "openai_compat",
         "system_prompt": "...", "tools": ["echo"]},
        {"id": "n3", "type": "tool", "tool": "file_read",
         "inputs": {"path": {"from": "n4", "port": "path"}}},
        {"id": "n4", "type": "path", "value": "./readme.md"},
        {"id": "n5", "type": "output"},
    ],
    "beams": [["n1", "n2"], ["n2", "n3"], ["n3", "n5"], ["n4", "n3"]],
}
```

节点类型与执行语义（type → 真实动作）：

| 节点 | 真实动作 |
|---|---|
| `trigger` | 读取 prompt 输入，产出 start 信号 |
| `model` | 调用注册表真实模型；`tools` 端口 = 容器挂载的工具集（自动解析 schema 传给 provider）；`system_prompt` 端口 = 系统提示词（优先级：beam 值 > 输入面板 > 节点配置 > 引擎预设参数，空值不注入 system 消息） |
| `tool` | 调用注册表真实工具：每个输入端口 = 一个 schema 参数（不再是全局 query/result 黑箱） |
| `toolbox` | 工具容器：输入端口 = 成员工具参数的并集（按端口名扇出投递）；输出端口 = 每个成员的「工具名.端口名」限定名 + tools 打包端口 |
| `sandbox` | 在注册表真实沙箱里执行 code（子进程隔离） |
| `security` | 对 payload 做越狱 / 注入扫描（`norpagent.security.guard`） |
| `session` | 读写会话管理器（默认引擎会话存储） |
| `plugin` | 插件容器（members = 工具 + 钩子成员，端口并集语义）或独立插件工具执行 |
| `hook` | 触发插件的单个钩子（一个钩子 = 一个节点；可变钩子走 intercept，返回值成为节点输出） |
| `other` | 直通（payload 原样转发） |
| `output` | 汇总最终结果 |
| `path` | 路径模块：产出经过公共路径安全校验（拒绝绝对路径 / `..` 穿越）的相对路径值；空值 = 工作区根目录 `.` |
| `file` | 文件模块：已注册为插件则按插件执行，否则直通 |

### 20.5 FlowRunner：拓扑执行与零中断语义

```python
runner = FlowRunner(graph, registry, agent, publish=on_event, workspace=ws)
result = runner.run(prompt="...", session_id="...", params={...})
```

关键设计：

1. **拓扑执行**：按 beam 依赖关系确定执行顺序，每个节点独立 `try/except`；
2. **零中断语义**：单节点失败记录 `error` 但不中断整条链路（其它节点照常执行）；
3. **事件发布**：进度经 `publish` 回调以 `flow.*` 事件推送，Web UI 复用 SSE 通道（`/events`）实时送达浏览器；
4. **停止支持**：`runner.request_stop()` 在节点边界生效；
5. **取消传播**：节点执行同样检查 `params["_cancel_event"]`，引擎停止 / Ctrl+C 可尽早退出。

### 20.6 流程与智能体联动（应用到智能体）

画布图可以「应用」为主界面的执行引擎：

```python
# Web UI 侧（/flow 页面「应用到智能体」按钮）：
ui.flow_save(graph, activate=True)    # 保存并激活
_active = ui._active_chat_flow()      # 当前激活的流程（未激活返回 None）

# 激活后，主界面聊天任务按流程执行：
ui._run_flow_task(prompt, session_id, task_params)
# 流程执行结果写入会话历史（_append_flow_history），与普通任务一致
```

即：**普通聊天 → 画布编排 → 会话历史**全链路打通。

### 20.7 Web UI 集成与 API

| API | 作用 |
|---|---|
| `flow_snapshot` | 注册表快照，驱动 `/flow` 页面模块坞与实例选择 |
| `flow_run` | 启动一次画布图执行（后台线程，进度经 SSE 推送） |
| `flow_stop` | 停止运行中的流程（节点边界生效） |
| `flow_register` | 「文件即模块」真实注册（.py 插件安全管线 / .json / .yaml 描述） |
| `flow_save` | 保存画布图（自动保存入口），可选激活「应用到智能体」 |
| `flow_load` | 返回上次自动保存的画布图与激活状态（页面刷新后恢复） |
| `_load_flow_graph_from_disk` | 启动时恢复上次保存的流程（文件缺失 / 损坏时静默忽略） |
| `fe_read_file` / `fe_load_config` / `fe_save_config` | FE 前端模块文件读取与独立配置（互不干扰） |

### 20.8 模块目录与安全边界

- 模块目录：`NORPAGENT_FLOW_MODULES` 环境变量或 `default_modules_dir()`；
- `.py` 模块与外部插件同一安全管线（第 11 章）：签名 → 审计 → 导入限制 → 注册；
- `path` 节点强制公共路径安全校验（拒绝绝对路径 / `..` 穿越）；
- 单文件 200KB 上限 + 输出 4000 字符截断（`_MAX_OUTPUT_CHARS`），防止资源失控。

---

## 第 21 章　内置组件深度剖析

> 本章逐个剖析 `builtin/` 下的内置实现：内部机制、协议关系、选用建议。
> 全部内置组件与第三方组件同等地位——同样走注册表，可被任意替换。

### 21.1 模型适配器

| 适配器 | 文件 | 特点 |
|---|---|---|
| `mock` | `builtin/models/mock.py` | 确定性输出：内置问答对 + 引导语，零依赖，用于测试 / 基准 / 无网络环境 |
| `openai_compat` | `builtin/models/openai_compat.py` | OpenAI 兼容协议（DeepSeek / OpenAI / Qwen / vLLM / Ollama 等），`norpagent[openai]` 提供 SDK；支持 reasoning effort（`model_supports_reasoning_effort` / `normalize_effort`）、DeepSeek v4 特判（`model_is_deepseek_v4`）、思维链提取（`_extract_reasoning`） |
| `anthropic` | `builtin/models/anthropic.py` | Anthropic 协议适配器，`norpagent[anthropic]` 提供 SDK |

共同点（协议 `ModelProvider`）：

- `generate(messages, tool_schemas, params) -> ModelOutput`（含 usage）；
- 可选 `stream(...)`：流式产出 `ModelStreamChunk`（正文增量 / 思维链 / 工具调用）；
- 取消支持：适配器读取 `params["_cancel_event"]`，引擎停止 / Ctrl+C 时尽早退出流式循环；
- 凭据回落：未提供任何 Key 时装配层自动回落 `mock`（`runtime/mount.py` 的 `_has_model_credentials` 检查 `OPENAI_API_KEY` / `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` / `DASHSCOPE_API_KEY` / `NORPAGENT_API_KEY`）。

### 21.2 工具集（21 个内置工具）

| 分组 | 工具 | 说明 |
|---|---|---|
| P1 基础 | `echo` / `get_time` / `run_python` | 回显 / 时钟 / Python 执行（PTC 雏形） |
| P2 工程 | `file_read` / `file_write` / `file_list` / `file_delete` | 文件操作，**严格限定工作区根目录**（`pathsafe` 校验：拒绝绝对路径与 `..` 穿越，可配置根目录） |
| P2 命令 | `exec_cmd` | 命令执行，经沙箱协议（`sandbox.run_shell`），超时钳制（`_MAX_TIMEOUT`） |
| P2 联网 | `web_search` / `web_fetch` / `web_extract_links` | 联网检索；**SSRF 防护**（`is_private_url` 拒绝内网 / 元数据地址）；requests 可用则用，否则 urllib 兜底；bs4 可用则结构化提取，否则正则兜底——零依赖可用 |
| P3 上下文 | `context_add` / `context_search` / `context_list` / `context_delete` | 跨会话可检索知识库（FTS5，见 21.6） |
| P3 项目 | `project_status` | 项目管理（git 感知，见 21.7） |
| P3 任务 | `task_submit` / `task_list` / `task_status` / `task_cancel` | 长周期任务协作（persistent 调度器，见 21.5） |

工具协议（`protocols/tool.py`）：`name` / `schema()` / `run(args, ctx)`，返回 `ToolResult`；`ctx` 携带 `RunContext`（组件访问：`ctx.component("context_store")` 等）。

### 21.3 会话存储

| 实现 | 特点 | 适用 |
|---|---|---|
| `memory` | 纯内存 dict，进程结束即失 | 嵌入式 / 测试 / 单次任务 |
| `sqlite` | SQLite 持久化：schema + 消息迁移（`_MESSAGE_MIGRATIONS` 增量升级）、`close` / `clear` 生命周期 | 默认（standard 预设），重启续聊 |

协议（`protocols/session.py`）：`create_session / get_session / append_message / history / list_sessions / delete_session`。

### 21.4 沙箱

| 实现 | 机制 | 适用 |
|---|---|---|
| `subprocess` | 每次调用起子进程，简单直接 | 轻量 / 嵌入式 |
| `pooled` | **沙箱池**：复用子进程 + 并发上限 + 超时强杀进程树（`_kill_process_tree`，Windows 用 `taskkill /T`）；`PooledSandboxProvider` 管理池生命周期（create / release / discard / kill_task / close_all / stats） | 默认（standard 预设），性能与隔离平衡 |
| `isolated_python` | PTC 子进程隔离执行：`check_ptc_source` 静态校验 + 包装模板（`_WRAPPER_TEMPLATE`）+ 结果回传（`_CALLER_SRC`） | `run_python` 工具的隔离执行路径 |

协议（`protocols/sandbox.py`）：`Sandbox.run_shell / run_python / close`、`SandboxProvider.create`。

### 21.5 调度器

| 实现 | 机制 | 适用 |
|---|---|---|
| `simple` | 内存队列：submit / pending / drain | 嵌入式 / 测试 |
| `persistent` | **SQLite 持久化调度**：任务落盘（`_SCHEMA`）、终端状态（`_TERMINAL_STATUSES`）、崩溃后 `resume` 续跑、`counts` / `list_tasks` / `cancel` / `clear` | 默认（standard 预设），长周期任务协作 |

### 21.6 上下文库（FTS5）

`builtin/context/fts5.py`：SQLite FTS5 全文索引实现的跨会话知识库。

- **中文分词**：`_tokenize` 内置中文切分（bigram + 单字），不依赖 jieba——零第三方依赖；
- **查询**：`_tokenize_for_query` + `_fts5_phrase` 构造短语查询；
- API：`add / update / search / get / list / delete / clear / stats / close`。

### 21.7 项目管理（BasicProjectManager）

`builtin/projects/basic.py`：

- 项目元数据：`_META_DIR` / `_META_FILE`（meta 读写，`init / load_meta / save_meta / touch`）；
- 目录扫描：`scan`（跳过 `_SKIP_DIRS`）；
- **git 感知**：`git_status`（`git` 命令探测，无 git 时平滑降级）；
- API：`status`（供 `project_status` 工具调用）。

---

## 第 22 章　Web UI 与前端深度解析

> 对应代码：`builtin/ui/web.py`（2596 行）+ `frontends/web.py`（407 行）。
> 5.4 节讲用法；本章讲**内部机制与 API 全集**。

### 22.1 架构与线程模型

```
浏览器 ──HTTP──▶ _RobustHTTPServer（ThreadingHTTPServer 调优版）
              ├── /           主聊天页面（front.html，可热替换）
              ├── /flow       流程画布页面（norpflow.html，可热替换）
              ├── /api/*      数十个 REST 端点
              └── /events     SSE 长连接（全部事件实时推送）
                └── _SSESubscriber（有界缓冲 + 条件变量唤醒，每连接一个）

WebUI.start()        后台守护线程 serve_forever（非阻塞）
WebUI.submit()       提交任务（后台线程执行，不阻塞 HTTP）
WebUI.on_event()     接收 AgentEvent → 推给全部 SSE 订阅者 + 记录历史
```

`_RobustHTTPServer` 的调优点：断连噪声静默（WinError 10053 等）、`daemon_threads=True`、`allow_reuse_address=True`（重启立即复用端口）、`request_queue_size=256`（监听积压）、`block_on_close=False`（快速停机）。

### 22.2 REST API 总表

| 分组 | 端点（方法） | 作用 |
|---|---|---|
| 任务 | `submit` / `stop_task` | 提交任务 / 停止任务（步骤边界生效） |
| 会话 | `create_session` / `session_info` / `list_sessions` / `session_messages` / `close_session` / `set_session_title` / `set_session_workspace` | 会话全生命周期 + 消息历史 + 工作区 |
| 配置 | `get_config` / `save_config` / `reset_config` / `set_api_key` / `validate_api_key` / `first_run` | 配置面板（持久化到 `~/.norpagent/webui_config.json`，原子写入） |
| 模型 | `list_models` / `set_agent_tools` / `agent_effective_tools` / `tools_info` | 模型列表（含远端）、工具集管理 |
| 插件 | `get_plugin_dirs` / `list_plugins` / `add_plugin_dir` / `remove_plugin_dir` / `reload_plugins` | 插件目录与热重载 |
| 安全 | `get_security` / `set_security` | 安全级别读取 / 设置 |
| 监控 | `health` / `usage` / `debug_info` / `streams_info` | 健康检查 / 用量 / 调试 / SSE 背压统计 |
| 文件 | `list_fs` / `read_fs_file` / `upload_files` | 目录导航 / 文件读取 / dataURL 上传（二进制不支持） |
| 流程 | `flow_snapshot` / `flow_run` / `flow_stop` / `flow_register` / `flow_save` / `flow_load` | 画布编排（第 20 章） |
| 回退 | `recovery_handle` | 快照 / Undo / Redo / Rollback API（`/api/snapshots`） |
| 前端模块 | `fe_read_file` / `fe_load_config` / `fe_save_config` | FE 模块读取与独立配置 |

### 22.3 SSE 事件协议

- 通道：`/events` 长连接；
- 帧格式：`data: {json}\n\n`（`_encode_sse_frame`，模块级复用，避免每帧建 lambda）；
- 事件内容：与 EventBus 同名事件（`on_task_start` / `on_content` / `on_reasoning` / `after_tool_call` / `flow.*` …）序列化为 JSON 帧；
- **背压**（`_SSESubscriber`）：

| 策略 | 语义 | 适用 |
|---|---|---|
| `drop_oldest`（默认） | 缓冲满丢最旧，客户端降级不掉线 | 展示型前端 |
| `drop_newest` | 缓冲满丢最新，保持旧状态 | 状态同步型消费者 |
| `unlimited` | 无上限（旧行为） | 明确需要全量时 |

- 运行中热改变：`ui.set_sse_queue(maxsize, policy)`（对既有连接立即生效）；
- 唤醒优化：空→非空转换唤醒一次，读者每次唤醒排空缓冲（高并发减锁）；
- 断连回收：连接断开 ≤1s 内回收订阅者（写时复制替换，不阻塞发布）。

### 22.4 配置面板与持久化

- 配置项：模型（名称 / base_url / api_key / temperature 等采样参数）、工具集、插件目录、安全级别、端口 / 语言等；
- 持久化：`_save_config_to_disk` 原子写入（失败只记日志，不拖垮保存流程）；启动 `_load_config_from_disk` 恢复（文件缺失 / 损坏静默忽略）；
- 配置保存后经 `set_config_apply` 回调重新注册模型 / 插件 / 安全（`WebFrontend._apply_config`）；
- 配置快照：工作回退系统会把 WebUI 设置文件纳入快照（第 15 章），回退时 `restore_config` 恢复。

### 22.5 页面与前端模块（FE）

- 页面：`/`（front.html）、`/flow`（norp-flow.html）与 `/farstars`（norp-farstars.html 星轨控制台），均可运行中热替换（`mount_page(page, html)` / `npa.remount(html=...)` / `npa.remount(flow_html=...)` / `npa.remount(farstars_html=...)`），HTTP 不重启、端口不变；
- FE 前端模块：`.html` / `.js` / `.ts` 文件（`fe_read_file` 按 mime 返回），启动后 `_scan_fe_modules` 扫描模块目录恢复列表（重启不丢失）；
- 独立配置：`fe_save_config` / `fe_load_config`（无记录时返回全局配置副本作为默认值来源，互不干扰）。

### 22.6 上传与安全限制

- 上传大小：`_MAX_JSON` / `_MAX_UPLOAD_JSON` / `_MAX_UPLOAD_FILE` 多重限制；
- 上传内容：文本（dataURL 解码）；**v0.9.9 起图片返回 `kind="image"` +
  base64 原样数据**（供 `/api/vision` 视觉理解，见第 29 章），其它二进制仍不支持；
- 远端模型过滤：`filter_remote_models`（`RETIRED_REMOTE_MODELS` 退役模型名单）；
- 敏感字段：`json_safe` 序列化时对密钥类字段脱敏；`tts_service_api_key` /
  `stt_service_api_key` 与 `api_key` 同走 DPAPI 加密落盘（`_SECRET_KEYS`）。

---

## 第 23 章　性能设计与基准测试

> 对应代码：`kernel/events.py`（EventBus）、`builtin/ui/web.py`（SSE / HTTP）、
> `nasyncio.py`（调度核心）、`loops/nasyncio.py`（LoopRuntime）。

### 23.1 通用事件总线（EventBus）：写时复制 + 无锁迭代

```python
# subscribe / unsubscribe：锁内创建新列表并替换引用（绝不原地修改）
self._all = self._all + [listener]
# emit / intercept：锁内取一次引用，随后无锁直接迭代
listeners = self._snapshot(event_type)   # 不复制，只取引用
for fn in listeners: fn(event)
```

- 读者持有的旧快照不会被并发写者修改——线程安全性由「不可变 + 引用替换」保证；
- 高频事件（流式 `on_content` 逐 token 推送）省去每条事件的列表复制开销；
- 实测 >160 万事件/秒（**单机单线程发布场景**）。

**基准口径（重要）**：160 万/秒为**单一发布线程 + 订阅表静态（无并发
subscribe / remount）**场景的实测数据。**无锁迭代 ≠ 无锁 emit**——
`emit` 每次仍在锁内取一次订阅表快照引用（`_snapshot`），随后才无锁
迭代。单线程发布下锁无竞争，故测得 160 万；动态热挂载（高频
subscribe / remount）下写者持锁复制列表期间，emit 会被挡在锁外
（µs 级——订阅者 n<50 时复制是微秒级，远低于 ms；仅当热挂载频率达
每秒成百上千次时才会被感知）。流式 `on_content` 的 emit 发生在 worker
线程内（自发布自迭代），不构成多线程竞争。

**「短暂看到旧表」是 COW 的线性化语义，不是缺陷**：先于 subscribe
完成的 emit 用旧表，保证「先订阅后发布」因果一致。若要彻底消除 emit
的锁获取，可改为「emit 完全不拿锁、直接读引用」（CPython 属性读天然
原子，写者只在锁内替换引用、绝不原地改，读者看到旧表或新表都是合法
快照）——当前实现保守保留读锁，属可优化项（会同步补动态热挂载混跑
基准）。

### 23.2 SSE 有界背压

- 每个连接独立缓冲：有界双端队列 + 条件变量；
- 满则按策略丢（默认丢最旧），**慢客户端不再无限吃内存**；
- 批量 flush + 断连 ≤1s 回收；`dropped` 计数可监控（`streams_info`）。

### 23.3 HTTP 并发调优

| 参数 | 值 | 效果 |
|---|---|---|
| `request_queue_size` | 256 | 监听积压放大，高并发接入不丢 SYN |
| `allow_reuse_address` | True | 重启立即复用端口（避开 TIME_WAIT） |
| `daemon_threads` | True | 请求线程守护，进程退出不挂起 |
| `block_on_close` | False | shutdown 不等连接关闭，停机更快 |

### 23.4 nasyncio 调度核心

- 一个 EventLoop 绑定一个线程；`run_forever` 在哪个线程调用，循环就属于哪个线程；
- 跨线程唤醒：线程安全队列 + socketpair 自管道（不依赖 asyncio 内部机制）；
- 取消语义：`Task.cancel()` 跨线程安全、done 回调写自管道、`loop.interrupt()` 取消全部在途任务；
- 工作池：`_DaemonPool`（守护线程，进程退出不 join），`NORPAGENT_MAX_WORKERS` 环境变量调节（嵌入式可压到 1）；
- 工作池队列**无界**：`put_nowait` 永不失败，池满时任务无限堆积、无拒绝策略、无任务时间预算（边界与卡死兜底矩阵见 4.6.4）。

### 23.5 验证方式

仓库自带全套专项验证脚本（`test/_verify_*.py` / `test/_smoke_*.py`）：

| 脚本 | 覆盖 |
|---|---|
| `_verify_install.py` / `_verify_wheel.py` | 安装与打包 |
| `_verify_js*.py` / `_verify_front.py` / `_verify_css_*` | 前端页面与资源 |
| `_e2e_webui.py` / `_e2e_shot.py` | WebUI 端到端与截图 |
| `_verify_ppt_*.py` / `_pixel_check*.py` | 演示文稿与像素校验 |
| `_final_check.py` / `_verify_coverage.py` | 整体回归与覆盖核对 |

性能基准方法建议：固定输入集 + 固定工具集（minimal 预设），对比不同模型 / 组件实现的输出质量、步数、token 消耗（第 7.3 节模型基准测试）。

---

## 第 24 章　救援模式：底层循环控制与人类接管

> 对应代码：`rescue.py`（纯标准库 CLI）、`rescue_api.py`（人类接管环境）、
> `nasyncio.py` / `loops/nasyncio.py`（循环内核与 LoopRuntime）。
> 15.6 讲**用法**（命令、端点、参数）；本章讲**原理**——救援模式与底层最小
> 主异步循环的关系：主程序不可用时如何直接控制循环、如何手动操作全部工具。

### 24.1 三层故障模型：循环、引擎、模型

救援模式按「故障发生在哪一层」决定用哪套入口：

| 故障层 | 现象 | 可用入口 | 依赖 |
|---|---|---|---|
| 模型死 | 循环 / 引擎正常，模型调用失败 | `norpagent-rescue tools / tool-call / manual / serve` | 需框架可导入（`rescue_api` 惰性加载） |
| 引擎死 | 循环可能还活着，AgentRuntime 起不来 | `norpagent-rescue rollback` / `npa(safemode="on")` | 纯标准库 |
| 循环死 | 调度 / 任务全部瘫痪 | `norpagent-rescue list / show / rollback / mark-good / prune` | 纯标准库 |

**核心原则（rescue.py 的隔离边界）**：

1. 快照命令层（list / show / rollback / mark-good / prune）**只依赖标准库**
   ——主程序坏到完全无法导入时依然可用；
2. 人类接管层（tools / tool-call / manual / serve）在命令函数**内部惰性导入**
   框架（`norpagent.rescue_api`）——框架能导入时才有意义；
3. `rescue_api` 装配的 `RescueToolEnvironment` **不使用主引擎的循环**，默认
   不加载任何插件 / 钩子 / 模型——它是独立的最小工具环境；显式加载插件
   （`--plugin-dirs`）时走主程序同款安全管线（24.3.5）。

### 24.2 救援模式下控制底层最小主异步循环

救援场景下「控制循环」分三个层次：直接操作**循环内核**（EventLoop）、通过
**LoopRuntime 协议**操作、以及**绕过循环**直接驱动工具。

#### 24.2.1 循环内核的直接控制面（norpagent.nasyncio.EventLoop）

最小主异步循环是自研 `norpagent.nasyncio.EventLoop`（零 asyncio 依赖，线程
模型：一个循环绑定一个线程，`run_forever` 在哪个线程调用就属于哪个线程）。
救援时可在任意脚本中直接操作它：

| API | 调用线程 | 用途 |
|---|---|---|
| `run_forever()` | 绑定线程 | 启动循环（阻塞）；重复调用抛 `RuntimeError` |
| `run_until_complete(coro)` | 绑定线程 | 跑完一个协程后自动停止，返回结果 |
| `stop()` | 任意 | 平滑停止：当前轮 ready 队列清空后退出 |
| `abort_main()` | 任意 | **强停**：向主任务注入 `CancelledError`，打断当前 await（工具 / API 流 / 用户输入等待），循环随任务完成退出——标准 asyncio 没有等价公开入口 |
| `call_soon_threadsafe(cb)` | 任意 | 跨线程投递回调；写自管道唤醒 select 中的循环线程 |
| `run_coroutine_threadsafe(coro, loop)` | 任意 | 跨线程提交协程，返回 `concurrent.futures.Future`（结果 / 异常 / 取消正确传递） |
| `create_task(coro)` / `create_future()` | 循环线程 | 创建任务 / 结果容器 |
| `call_later(delay, cb)` | 循环线程 | 定时回调（可取消）；**跨线程调用不安全**（与 asyncio 契约一致） |
| `interrupt()`（LoopRuntime 层） | 任意 | 置位全部在途任务的取消事件（沙箱强杀子进程 / 流式循环退出） |
| `close()` | 非运行中 | 释放 selector 与自管道 socketpair |

**自研核心的三个救援关键语义**：

1. **跨线程取消**：`Task.cancel()` 自动检测调用线程——循环线程内 `call_soon`，
   循环线程外 `call_soon_threadsafe` + 自管道唤醒。外部线程可以直接取消任何
   在途任务，不需要包一层 wrapper；
2. **自管道唤醒**：`call_soon_threadsafe` / 跨线程 `set_result` / `Event.set`
   都会写 socketpair 自管道，循环线程即使阻塞在 `select()` 也会立刻醒来——
   不存在「回调已入队但循环还在睡」的悬挂；
3. **select 超时上限**：`_run_once` 把 select 等待时间钳制在 24 小时以内
   （`_MAX_SELECT_TIMEOUT`，与 CPython asyncio 同值）。超远定时器
   （`sleep(1e18)`、远期 `call_later`）在 Windows 上会让 `select()` 抛
   `OverflowError` 崩溃循环线程——这是暴力压测（24.2.6）发现的真实缺陷，
   已修复：循环每睡 24h 醒来重查定时器堆，`abort_main()` 仍可随时打断。

#### 24.2.2 LoopRuntime 协议级控制（NasyncioLoopRuntime）

`loops/nasyncio.py` 的 `NasyncioLoopRuntime` 是 `async_loop` 槽位的默认实现，
把 EventLoop 封装进线程 + 守护工作池。救援脚本可以通过协议控制它：

```python
from norpagent.loops.nasyncio import NasyncioLoopRuntime

rt = NasyncioLoopRuntime(config={"max_workers": 2})   # 不自动启动
rt.start()                                            # 起循环线程 + 惰性起工作池
rt.submit(lambda: run_a_tool_by_hand(...))            # 同步函数 → 工作池执行并阻塞等结果
rt.run_async(some_coroutine())                        # 协程 → 循环线程内执行（跨线程自管道唤醒）
rt.interrupt()                                        # 取消全部在途任务（Ctrl+C / 救援强停路径）
rt.stop()                                             # 平滑停循环
rt.join(timeout)                                      # 等循环线程退出并释放资源
```

`submit()` 的取消语义（4.6 节）：每个任务通过 contextvars 携带自己的取消
事件；`interrupt()` 置位后，任务体内的 `cancel_requested()` 返回 True——
沙箱强杀子进程树、流式循环尽早退出。`run_async` 在循环线程内被调用会显式
抛 `RuntimeError`（阻塞等待会卡死循环，宁可拒绝也不挂起）。

#### 24.2.3 场景 A：模型死了，循环活着——绕过模型直接驱动

引擎健康、仅模型不可用时，不必重建任何东西：直接通过引擎持有的循环
（`engine.async_loop`，LoopRuntime 协议）提交同步函数或协程，绕开
AgentRuntime 的模型调用路径：

```python
import norpagent as npa

engine = npa.current()                      # 已启动的引擎（循环线程 + 工作池活着）
loop = engine.async_loop                   # LoopRuntime 协议实例

# 方式一：同步函数（工作池执行，阻塞等结果）
out = loop.submit(
    lambda: engine.registry.resolve_tool("file_read")
                .run({"path": "readme.md"}, make_rescue_context(engine))
)

# 方式二：协程（循环线程内执行，跨线程唤醒）
out = loop.run_async(read_file_and_log(engine))
```

`submit` 的轮询等待（`poll_interval`）保证主线程每 ≤50ms 回到字节码边界，
Windows 上 Ctrl+C 立即生效为 `KeyboardInterrupt`，同时任务取消事件被置位。

#### 24.2.4 场景 B：引擎也死了——裸 EventLoop 手工驱动

引擎 / AgentRuntime 完全起不来时，可以绕开整个装配层，手工驱动一个裸循环：

```python
import threading
import norpagent.nasyncio as nio            # 自研核心：零依赖、无插件、无钩子

loop = nio.EventLoop()
thread = threading.Thread(target=loop.run_forever, daemon=True)
thread.start()

# 跨线程提交一个协程并等待结果
cf = nio.run_coroutine_threadsafe(do_manual_work(), loop)
result = cf.result(timeout=30.0)            # 异常 / 取消都会原样传递

loop.call_soon_threadsafe(loop.stop)        # 平滑停止
thread.join(5.0)
loop.close()
```

配合 `RescueToolEnvironment`（24.3.3）可以做到「裸循环调度 + 手工工具执行」：
循环负责编排（定时、重试、并发），工具执行仍走 `call_tool` 的独立线程与取消
事件——两者互补，互不阻塞。

#### 24.2.5 场景 C：循环卡死——强停与重建

循环线程卡在 `select()` 或某协程长时间 await 时：

1. **先软后硬**：`loop.call_soon_threadsafe(loop.stop)`（平滑）→ 不行再
   `loop.abort_main()`（注入 `CancelledError`，打断当前 await）；
2. **任务级取消**：`rt.interrupt()` 置位在途任务取消事件——沙箱会强杀子进程
   树，流式读取会退出（4.6.2）；
3. **看门狗模式**：健康检查协程周期性 `loop.time()` 心跳，检测到循环无响应
   （心跳超时）即 `abort_main()` + 关闭 + 重建新循环（24.2.4 的裸循环模板）；
4. **不可回收任务**：工作池中卡死的任务（C 扩展阻塞 / 非沙箱 subprocess）
   无任务时间预算（4.6.4 如实说明）——救援兜底是 daemon 线程随进程退出，
   或通过 `RescueToolEnvironment.call_tool(timeout=...)` 的硬超时弃置线程。

#### 24.2.6 循环内核暴力压测（test/stress_nasyncio_core.py）

新增 35 项暴力压测，覆盖「testway.txt 选取 + 事件循环专项补充」两大部分：

| 来源 | 压测项 |
|---|---|
| testway.txt 选取（B/C/D/E 类映射） | 冷启动就绪（B01）、快速启停 200 次（D10）、生命周期与资源释放（B02/B24）、100/500/1000 高并发（D02）、5000 批量（D08）、20 万跨线程提交风暴（D05）、超时与内层取消（B17/C02）、异常隔离（C04）、空输入与极端数值（D15/D16）、死锁拒绝（C14）、50 万 handle 资源耗尽（C17）、2000 层递归任务（D19）、重复回调风暴（D27）、内存基线（D11）、60s 混合 soak（D09）、强停延迟（B15）、看门狗 interrupt（E06） |
| 专项补充（矩阵未覆盖） | 8 线程唤醒竞争、1000 定时器精度与乱序注册顺序、10 万取消风暴、ready 队列不饿死定时器（公平性）、单线程绑定、跨线程 Future 完成、跨线程 Event 唤醒、Lock/Condition 竞争、Task.cancel 穿透（BaseException）、executor 结果/异常回传、closed-loop 拒绝、空循环不忙转（select 阻塞）、1000 并发 sleep 定时器、子进程取消杀进程（zombie 保护） |

运行：`python test/stress_nasyncio_core.py`（约 2 分钟，含 60s soak）。

**压测发现并修复的真实缺陷**：`select()` 超时溢出（Windows `OverflowError:
timestamp out of range`）——已通过 `_MAX_SELECT_TIMEOUT` 钳制修复（24.2.1
第 3 条）。其余测试均为对既有实现的验证性通过（35 项 / 110 断言 / 0 失败）。

### 24.3 手动操作工具（人类接管）

#### 24.3.1 四种入口与「传入 / 传出」语义

| 入口 | 形态 | 传入 | 传出 |
|---|---|---|---|
| `norpagent-rescue tools` | CLI | — | 全部工具的 schema（名称 / 描述 / 参数 / 必填 / 分类 / **来源 origin**） |
| `norpagent-rescue tool-call <name> --args '<json>'` | CLI | 手工 JSON 参数 | 结构化结果 `{ok, tool, output, error, timed_out, duration_ms}` |
| `norpagent-rescue manual` | 交互台 | `<tool> <json>` 或 `{"tool":..., "args":...}` | 原始输出逐行打印 |
| `norpagent-rescue serve` | HTTP API | POST body `{"args":{...},"timeout":N}` | 统一 JSON 响应 |

**工具范围**：默认暴露全部 20 个内置工具；v0.9.7 起可通过
`--tools`（已注册名或模块地址，逗号分隔）追加自定义工具、通过
`--plugin-dirs`（逗号分隔）加载外部插件工具（24.3.5）。手动调用与
模型发起调用走**完全相同的执行路径**：`tool.run(args, ctx)` +
同一个 `RunContext`（registry / sandbox / session / scheduler /
context_store / project_manager 一个不少），写入同一份状态——文件落在同一
workspace、`context_add` 写入同一上下文库、`task_submit` 进入同一任务队列。
「传入」= 人代替模型生成 `args`；「传出」= 结果按模型视角的结构化格式返回，
模型恢复后可直接续用同一份状态。

#### 24.3.2 手动调用的循环交互模型

`RescueToolEnvironment.call_tool()` **不依赖主循环**，也不占用循环线程：

```
调用方（CLI / HTTP 线程 / 主线程）
  └─ call_tool(name, args, timeout)
       ├─ 解析工具 + 组装 RunContext（含 per-call 取消事件 ContextVar）
       ├─ 起独立 worker 线程（contextvars.copy_context 隔离取消信号）
       ├─ worker: tool.run(args, ctx) → 结果装箱
       ├─ 主线程 join(timeout)：超时 → 置位取消事件 + 弃置为 daemon 孤儿线程
       └─ 返回结构化结果（ok / output / error / timed_out / duration_ms）
```

要点：

- **并行安全**：每次调用独立线程，多个手动调用可并发；组件内部有锁；
- **取消信号**：`cancel_requested()` 在 worker 线程可见——沙箱强杀子进程树、
  流式循环尽早退出；超时后调用方立即返回，不等任务真正结束；
- **与 24.2 的关系**：若希望手动调用也能被循环编排（定时 / 并发 / 重试），
  把 `call_tool` 放进 `loop.submit(...)`（工作池）或裸循环的
  `run_coroutine_threadsafe` 即可——`call_tool` 是纯同步函数，任何循环都能
  调度它。

#### 24.3.3 程序化嵌入：救援环境 + 自定义循环控制

```python
from norpagent.rescue_api import RescueToolEnvironment, RescueToolAPI
import norpagent.nasyncio as nio

env = RescueToolEnvironment(workspace_root=".", context_db="./rescue.db")

# 1) 直接手动调用（同步，独立线程 + 硬超时）
r = env.call_tool("exec_cmd", {"command": "git status"}, timeout=30)
print(r["output"])

# 2) 挂 HTTP 接管服务（127.0.0.1，可选 Bearer token）
api = RescueToolAPI(env, port=8799, token="my-secret")
api.start()

# 3) 用裸循环编排手动调用（定时轮询任务队列等）
loop = nio.EventLoop()
threading.Thread(target=loop.run_forever, daemon=True).start()
nio.run_coroutine_threadsafe(poll_and_act(env, loop), loop).result(timeout=60)
loop.call_soon_threadsafe(loop.stop)
```

应用侧也可在模型健康检查失败后自动拉起 `RescueToolAPI`（挂在现有进程内），
值班人员通过操作员页面接管，模型恢复后 Agent 从同一份状态继续。

#### 24.3.4 超时与安全边界（速查）

- **双层超时**：工具自带超时（exec_cmd 最大 300s、run_python 的
  `ptc_timeout`）+ 环境级硬超时（默认 300s，`--timeout` / HTTP body 可调）；
- **弃置线程**：超时后 worker 成为 daemon 孤儿线程（与模型调用超时同一
  模式），`_orphan_threads` 按调用过滤回收；
- **默认零插件零钩子**：救援环境默认不订阅任何钩子，操作者即最终审批人；
  显式加载插件（`--plugin-dirs`）时走主程序同款安全管线，插件钩子随
  注册表总线挂载，但不会影响手动调用的执行路径；
- **路径安全照常**：`file_*` 绝对路径 / `..` 穿越拒绝、`run_python` AST 预检
  照常；HTTP 默认仅 127.0.0.1，token 可选。

#### 24.3.5 自定义工具的手动操作（v0.9.7）

三种来源，全部可经四种入口手动调用：

| 来源 | 接入方式 | origin 标记 | 说明 |
|---|---|---|---|
| 注册表自定义工具 | `extra_tools={name: tool}`（程序化） | `custom` | 直接注册进救援注册表 |
| 工具槽位 | `tools=["name", "pkg.mod:attr"]` / CLI `--tools` | `custom` | 与 `npa(tools=[...])` 槽位语义一致，地址解析失败明确报错 |
| 外部插件 | `plugin_dirs=[dir]` / CLI `--plugin-dirs` | `plugin` | 经签名 → 审计 → 导入限制 → 注册的安全管线 |

```bash
# CLI：模块地址加载自定义工具并手操
norpagent-rescue tools --tools myapp.tools:create
norpagent-rescue tool-call my_tool --args '{"x": 1}' --tools myapp.tools:create

# CLI：加载外部插件工具
norpagent-rescue serve --plugin-dirs ./my_plugins --port 8799

# 程序化：三种来源组合
env = RescueToolEnvironment(
    extra_tools={"my_tool": MyTool()},
    tools=["builtin_or_extra_name", "pkg.mod:attr"],
    plugin_dirs=["./my_plugins"],
)
```

`inventory()` 返回的每个工具带 `origin`（builtin / custom / plugin），
CLI 清单与操作员页面均标注来源；`/api/health` 返回 `custom_tools` 计数。
插件加载器随环境 `close()` 释放（宿主子进程一并关闭）。

### 24.4 故障决策树

```
模型调用失败？
├─ 是 → 引擎 / 循环还活着吗？
│        ├─ 活着 → norpagent-rescue tools / tool-call / manual / serve
│        │           （或程序化：engine.async_loop.submit(λ 手动工具)）
│        └─ 死了 → 快照回退 rollback --last-good（纯标准库）
│                  → 仍起不来 → npa(safemode="on") 最小内核
└─ 否 → 但任务卡死 / 无响应？
         ├─ rt.interrupt() / loop.abort_main() 强停（24.2.5）
         ├─ 循环线程也死了 → 裸 EventLoop 重建 + RescueToolEnvironment（24.2.4）
         └─ 全部瘫痪 → norpagent-rescue list（纯标准库兜底）
```

### 24.5 与 15.6 的分工

| 章节 | 视角 | 内容 |
|---|---|---|
| 15.6 | 使用者 | 命令 / 端点 / 参数 / 响应格式 / 环境默认值（用法速查） |
| 24 | 原理与底层 | 三层故障模型、循环直接控制（EventLoop / LoopRuntime）、手动调用的循环交互模型、裸循环重建、压测与缺陷修复记录 |

两者互补：先用 15.6 上手，遇到「循环也出问题」再回本章 24.2 做底层控制。

---

## 第 25 章　开发者实战：模块、槽位、插件与工具开发

> 前 24 章回答「框架能做什么」，本章回答「你如何开发」：逐个模块的
> 开发方法（协议 → 实现 → 注册 → 接入 → 热重载）、槽位开发的完整
> 契约（含热重载红线：**键值对的值必须是有效模块**）、插件与工具的
> 完整开发示例，最后用一节回到架构与最小主异步循环内核——理解它，
> 你就理解了一切扩展点为什么存在、热重载为什么安全。

### 25.1 架构速览与最小主异步循环内核

#### 25.1.1 一张图看懂架构（速览）

NorpAgent 的架构概述：**除最小内核外，全部组件都是可替换槽位**。

```
你的应用：npa() / npa.stop() / npa.nasyncio() / npa.current().submit()
    │
运行时层 runtime/    生命周期状态机 + 线程编排（NorpEngine）
    │
架构层 arch/         槽位表（SLOT_SPECS）+ 地址解析（address）+ 装配（ArchLayer）
    │
循环系统 loops/      LoopRuntime 协议 + 默认 NasyncioLoopRuntime（自研 nasyncio 核心）
    │
内核 kernel/         Registry（注册表）+ EventBus（事件总线）+ AgentRuntime（Agent 循环）
    │
协议层 protocols/    模型 / 工具 / 会话 / 沙箱 / 调度器 / UI / 插件 全部接口契约
    │
实现层 builtin/      内置组件（与第三方实现地位完全平等，同样走注册表）
```

- **最小内核只有四样**：`ArchLayer`（槽位连接器）、`address`（地址解析）、
  `Registry`（注册表）、`EventBus`（事件总线）——其余全部是槽位（2.3 节）；
- **依赖方向单向下行**：上层 import 下层，下层不得反向依赖上层（2.6.1）；
- **四类扩展点**：事件订阅（第 9 章）/ 组件替换（第 3 章）/ 通用组件
  （2.6.3）/ 全新槽位（3.8 与 25.10）/ 外部插件（第 11 章与 25.11）；
- **零修改红线**：框架核心代码零修改，一切扩展走槽位 / 钩子 / 注册表。

#### 25.1.2 最小主异步循环内核：EventLoop 内部机制

`norpagent.nasyncio.EventLoop`（自研，零 asyncio 依赖）是全部调度的核心。
一次 `npa()` 启动后，引擎的 submit → 循环 submit → 工作池 → 结果，全部
围绕下面五样结构运转：

| 结构 | 作用 |
|---|---|
| `_ready`（双端队列） | 待执行回调：`call_soon` / 到期定时器 / Task 推进 |
| `_scheduled`（时间堆） | 定时器：`(when, seq, TimerHandle)`，`call_later` / `sleep` |
| `_ts_queue`（线程安全队列） | 跨线程提交：`call_soon_threadsafe` |
| 自管道（socketpair） | 跨线程唤醒阻塞在 `selector.select` 上的循环线程 |
| `_selector` | 只监听自管道可读事件 |

每一轮 `_run_once()` 的流程（这也是「最小主异步循环」的标准范式）：

```
1. 到期定时器出堆 → 移入 _ready
2. 计算 select 等待时长（有 ready 等 0；有定时器等到期；否则无限等）
3. 先 drain 一次线程安全队列（减少无谓唤醒）
4. selector.select(wait)——自管道可读或定时器到期才醒来
5. drain 自管道 + 线程安全队列 → 全部并入 _ready
6. 按快照长度执行 _ready（防饥饿），回调异常打印后继续，不击穿循环
```

**Future / Task 的 trampoline 推进**：`Task._step()` 调 `coro.send(None)`，
协程 `yield` 出 Future 时挂起并注册 `_on_waiter_done`；Future 完成时
回调把 `_step` 重新排入 ready 队列继续推进——循环线程从不等待任何
协程，它只负责「排队的回调逐个跑」。

**取消穿透**：`Task.cancel()` 自动检测调用线程——循环线程内走
`call_soon`，其他线程走 `call_soon_threadsafe`（写自管道立即唤醒），
因此**外部线程可以直接取消任意任务**（标准 asyncio 的 `Task.cancel()`
非线程安全，这是自研核心的关键修复，见 4.7）；取消以
`coro.throw(CancelledError)` 注入，由协程决定响应或吞掉。

**三个修复过的经典坑**（4.5 节详述）：

1. 跨线程 `Future.add_done_callback` 在已完成时必须走
   `call_soon_threadsafe`（写自管道），否则循环阻塞在 selector 上
   收不到唤醒，等待方永久挂起；
2. `Future.result()` 线程安全（不做未经唤醒的裸等待）；
3. `EventLoop.abort_main()` 提供线程安全的「即时停止」——向主任务
   注入 `CancelledError`，不等当前 await 自然结束（24.2 详述）。

#### 25.1.3 教学级最小事件循环（约 40 行）

理解内核最好的方式是亲手写一个最小版本。下面是一个可运行的
「最小主异步循环」（与自研核心同构，仅演示原理）：

```python
# myapp/mini_loop.py —— 教学用最小事件循环（说明原理，生产请用库内置核心）
import heapq, socket, selectors, time, threading
from collections import deque


class MiniLoop:
    def __init__(self):
        self._ready = deque()          # 待执行回调
        self._timers = []              # 时间堆 [(when, seq, cb)]
        self._seq = 0
        self._sel = selectors.DefaultSelector()
        self._ssock, self._csock = socket.socketpair()
        self._ssock.setblocking(False)
        self._sel.register(self._ssock, selectors.EVENT_READ)

    def call_soon(self, cb, *args):    # 循环线程内
        self._ready.append((cb, args))
        self._wake()

    def call_later(self, delay, cb, *args):   # 定时
        self._seq += 1
        heapq.heappush(self._timers, (time.monotonic() + delay,
                                      self._seq, cb, args))

    def call_soon_threadsafe(self, cb, *args):  # 跨线程：写自管道唤醒
        self._ready.append((cb, args))
        self._wake()

    def _wake(self):                   # 唤醒阻塞在 select 的循环线程
        try:
            self._csock.send(b"\0")
        except OSError:
            pass

    def run_forever(self):
        while True:
            # 1. 到期定时器 → ready
            now = time.monotonic()
            while self._timers and self._timers[0][0] <= now:
                _, _, cb, args = heapq.heappop(self._timers)
                self._ready.append((cb, args))
                now = time.monotonic()
            # 2. select 等待时长
            wait = 0.0 if self._ready else (
                max(0.0, self._timers[0][0] - now) if self._timers else None)
            # 3. 阻塞等待（自管道可读或定时器到期）
            try:
                events = self._sel.select(wait)
            except (InterruptedError, OSError):
                events = []
            for _key, _mask in events:
                self._ssock.recv(4096)          # 清空唤醒字节
            # 4. 按快照执行 ready（防饥饿）
            n = len(self._ready)
            for _ in range(n):
                cb, args = self._ready.popleft()
                try:
                    cb(*args)
                except Exception:
                    import traceback
                    traceback.print_exc()       # 回调异常不击穿循环


if __name__ == "__main__":
    loop = MiniLoop()
    threading.Thread(target=loop.run_forever, daemon=True).start()
    loop.call_later(0.5, lambda: print("timer fired"))
    loop.call_soon_threadsafe(lambda: print("hello from main thread"))
    time.sleep(1)
    loop.call_soon(loop._ssock.close)
```

真实核心在此基础上补充：Future / Task（trampoline）、取消注入、
`run_until_complete` / `abort_main`、子进程封装、同步原语
（Event / Lock / Condition）。掌握上面的 40 行，就掌握了
「最小主异步循环内核」的全部骨架——后续 25.2 ~ 25.11 的所有
模块开发都不再需要修改它。

#### 25.1.4 模块开发的通用五步

无论开发哪一种模块（工具 / 模型 / 会话 / 沙箱 / 调度器 / 前端 /
循环 / 通用组件），流程完全一致（2.6.4 节的展开版）：

1. **读协议**：`norpagent/protocols/` 下的接口契约（模型 / 工具 /
   会话 / 沙箱 / 调度器 / UI / 插件），确认要实现的协议与数据类；
2. **写实现**：新建模块，只依赖 protocols 与标准库（参照
   `builtin/` 下的写法，内置组件与第三方组件地位完全平等）；
3. **注册**：`reg.register_*(...)`（Registry API 见 25.2.5 表格）
   或 `registry.register_component(kind, name, factory)`；
4. **声明使用**：预设里声明（`session="my_impl"`），或启动时
   `npa(session="my_impl")` / 地址字符串 `npa(session="myapp.sessions:create")`；
5. **接钩子**（可选）：在实现内经 registry 发布 / 订阅事件（第 9 章）。

热重载是第 4 步的自然延伸：`npa.remount(session="myapp.sessions:create")`
在运行中重新解析地址、**先失效模块缓存与 .pyc**（3.7 节），因此
「改实现代码 → remount」即可热更新，无需重启进程。

---

### 25.2 工具开发详解（重点）

工具是 Agent 的「技能」：模型决定**要不要**调用，你决定**怎么**执行。
开发工具是接入 NorpAgent 最频繁、收益最高的扩展方式。

#### 25.2.1 协议与数据类

```python
# norpagent/protocols/tool.py
class Tool(Protocol):
    name: str                                        # 工具唯一名（模型调用名）
    def schema(self) -> dict: ...                    # OpenAI function schema
    def run(self, args: dict, ctx: RunContext) -> ToolResult: ...

@dataclass
class ToolResult:
    output: str = ""                                 # 回填给模型的文本
    success: bool = True
    error: str = ""
```

要点：

- `schema()` 返回 OpenAI function 格式（`type/function/name/description/
  parameters`），是模型看到的世界——**描述写得好不好，直接决定模型
  会不会正确调用**；
- `run()` 的 `args` 是模型按 schema 生成的 JSON 参数（已解析为 dict）；
- 返回 `ToolResult`：成功填 `output`；失败置 `success=False` 并填
  `error`（模型会看到 `[工具执行失败] ...` 前缀）；
- 可抛异常，内核会捕获并转为统一的失败 ToolResult（`tool_error`），
  但**显式返回失败结果**更可控。

#### 25.2.2 完整示例：从零写一个「天气查询」工具

```python
# myapp/weather_tool.py —— 开发者自己的工具模块
from __future__ import annotations

import json
from typing import Any, Dict
from urllib.request import urlopen

from norpagent.protocols.tool import Tool, ToolResult


class WeatherTool:
    name = "weather"

    def __init__(self, api_key: str = "", base_url: str = "https://wttr.in"):
        self._api_key = api_key          # 构造参数：地址子句 ;api_key=... 可注入
        self._base_url = base_url

    def schema(self) -> Dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": "查询指定城市的当前天气。城市用中文名或拼音均可。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "city": {"type": "string", "description": "城市名，如 北京 / Shanghai"},
                    },
                    "required": ["city"],
                    "additionalProperties": False,
                },
            },
        }

    def run(self, args: Dict[str, Any], ctx: Any) -> ToolResult:
        city = str(args.get("city", "")).strip()
        if not city:
            return ToolResult(output="缺少 city 参数", success=False, error="city is required")
        try:
            with urlopen(f"{self._base_url}/{city}?format=j1", timeout=10) as resp:
                data = json.load(resp)
            cur = data["current_condition"][0]
            return ToolResult(output=(
                f"{city} 当前 {cur['temp_C']}°C，"
                f"体感 {cur['FeelsLikeC']}°C，{cur['weatherDesc'][0]['value']}"
            ))
        except Exception as exc:
            return ToolResult(output=f"查询失败: {exc}", success=False, error=str(exc))


def create(**kw):                        # 模块级工厂：地址 "myapp.weather_tool" 自动命中
    return WeatherTool(**kw)
```

#### 25.2.3 RunContext：工具能访问什么

`run(args, ctx)` 的 `ctx` 是 `RunContext`（`norpagent.kernel.context`），
一次任务执行期间的全部环境：

| 字段 | 说明 |
|---|---|
| `ctx.registry` | 组件注册表（可解析其他工具 / 模型：`reg.resolve_tool(name)`） |
| `ctx.session_manager` / `ctx.session_id` | 会话存取（跨轮记忆） |
| `ctx.sandbox` | 当前任务沙箱（`run_shell` / `run_python`，隔离执行） |
| `ctx.scheduler` | 任务调度器（提交子任务，多智能体协作入口） |
| `ctx.ui` | UI 适配器（`ctx.ask_user(...)` 人工交互 / 审批） |
| `ctx.params` | 预设 params 与任务级参数的合并结果（`max_steps` / `task_timeout` / 自定义键） |
| `ctx.components` | 预设声明的通用组件实例（`{kind: instance}`） |
| `ctx.component("context_store")` | 按种类取通用组件（上下文库 / 项目管理等） |
| `ctx.task_id` / `ctx.preset_name` | 任务元信息 |

```python
# 工具内使用组件的惯用写法
store = ctx.component("context_store")     # 无则 None，自行兜底
if store is not None:
    store.add(ctx.session_id, chunk, meta={"tool": self.name})
```

#### 25.2.4 取消协作（长任务必做）

任务可能被 Ctrl+C / `engine.request_stop()` / 超时取消。内置取消信号
经 contextvars 注入，工具内随时可查（4.6.2 节）：

```python
from norpagent.loops.cancel import cancel_requested

def run(self, args, ctx):
    for chunk in self._fetch_stream(args["url"]):
        if cancel_requested():            # 引擎停止 / 取消 → True
            return ToolResult(output="任务已取消", success=False)
        self._write(chunk)
    return ToolResult(output="done")
```

不检查取消的长工具会占满守护工作池（4.6.4 节边界），务必在
**流式 / 循环 / 分片**路径上检查。

#### 25.2.5 注册与接入的四种方式

| 方式 | 写法 | 场景 |
|---|---|---|
| 注册表登记 | `reg.register_tool("weather", WeatherTool())` | 程序化装配，其他组件可按名引用 |
| 实例列表 | `npa(tools=[WeatherTool(), MyTool()])` | 启动即用 |
| 名字映射 | `npa(tools={"weather": WeatherTool(api_key="x")})` | 启动即用（键 = 工具名） |
| 地址映射 | `npa(tools={"weather": "myapp.weather_tool:create"})` | 启动即用 + 可热重载 |

`npa(tools=["weather"])` 引用的是**已注册名**；地址映射的值
`"myapp.weather_tool:create"` 是**模块地址**，装配期解析为工厂并按
工厂约定调用（3.4 节：`;api_key=xxx` 子句注入工厂 `config`）：

```python
npa(tools={"weather": "myapp.weather_tool:create;api_key=MY_KEY"})
# 等价于 WeatherTool(api_key="MY_KEY")
```

Registry 的注册 API 全集（`norpagent.kernel.registry`）：

| API | 说明 |
|---|---|
| `register_tool(name, tool)` / `resolve_tool(name)` / `list_tools()` | 工具 |
| `register_model(name, provider)` / `resolve_model(name)` | 模型 |
| `register_session(name, factory)` / `build_session(name)` | 会话（工厂） |
| `register_sandbox(name, factory)` / `build_sandbox(name)` | 沙箱（工厂） |
| `register_scheduler(name, factory)` / `build_scheduler(name)` | 调度器（工厂） |
| `register_ui(name, adapter)` / `resolve_ui(name)` | UI 渲染器 |
| `register_component(kind, name, factory)` / `build_component(kind, name)` | 通用组件（任意种类） |
| `register_preset(preset)` / `resolve_preset(name)` | 预设 |

#### 25.2.6 热重载工具：键值对的值必须是有效模块（红线）

工具集是**组件槽位**，`npa.remount(tools=...)` 下一次 `run()` 生效
（Agent 循环每次 run 重新解析工具 schema）。三种形态都可热重载：

```python
npa.remount(tools=["echo", "weather"])                    # 已注册名列表
npa.remount(tools={"weather": WeatherTool(api_key="新key")})  # 实例映射
npa.remount(tools={"weather": "myapp.weather_tool:create"})   # 地址映射（推荐）
```

**红线：键值对的值在热重载时必须是有效模块**。tools 映射的
dict 值、以及任何槽位的 dict 形态值（hooks 映射、自定义槽位 dict
值，嵌套 dict 递归），其中的字符串若**形如纯地址**（含 `.` 或 `:`
的点分标识符，`norpagent.arch.address.is_address_like` 判定），
装配器会按地址解析：

- 值 = **已注册名**（如 `"echo"`）→ 原样保留为名字引用；
- 值 = **有效模块地址**（如 `"myapp.weather_tool:create"`）→ 加载
  模块、取属性、按工厂约定调用；
- 值 = **有效实例 / 工厂对象** → 原样使用；
- 值 = **形如地址但解析失败**（模块不存在 / 属性不存在 / 语法错误）→
  抛 `AddressError`（`AddressError(ImportError)`），**热重载失败，
  不静默回落、不部分生效**。

```python
# 错误示范：模块名拼错 / 属性不存在 → AddressError，remount 抛错
npa.remount(tools={"weather": "myapp.weather_toll:create"})   # 拼写错误
npa.remount(tools={"weather": "myapp.weather_tool:WeatherTool"})  # 类未实例化？→ callable 会按工厂调用（合法）
npa.remount(tools={"weather": "myapp.not_exist:create"})      # 模块不存在

# 正确示范：三选一
npa.remount(tools={"weather": "myapp.weather_tool:create"})   # 地址（模块可导入）
npa.remount(tools={"weather": "weather"})                     # 已注册名（register_tool 过）
npa.remount(tools={"weather": WeatherTool()})                 # 实例
```

为什么「写了地址就该报错」：热重载是运维动作，静默回落的地址会
让线上悄悄用上旧实现或空实现，比显式失败更难排查。因此装配器
对「形如地址的字符串」一律严格解析（3.3 节第 3 条、`layer.py`
`_resolve_dict_values` 的注释原文：「写了地址就该明确报错，不静默
回落」）。**非地址形态的字符串（如 `"high"`、`"./dir"`）不受影响，
保持字面语义**。

另一个热重载细节：**地址热重载会先失效模块缓存**。`remount` 对
字符串地址执行 `_invalidate_address_module`——删 `__cached__` 对应
的 .pyc、弹出 `sys.modules` 条目，下次解析从磁盘重新导入（3.7 节）。
因此「修改 `myapp/weather_tool.py` → `npa.remount(tools={"weather":
"myapp.weather_tool:create"})`」即可热更新代码。注意：**实例 / 已注册
名形态不做模块失效**（没有可失效的地址），改代码后请用地址形态。

调试建议：热重载失败时检查 `eng.layer.describe()` 的装配清单（3.5 节），
以及 `reg.list_tools()` 确认名字是否真的注册过。

---

### 25.3 模型开发详解

模型是 Agent 的推理核心。接入任何模型（本地 / 云端 / 私有协议）只需
实现 `ModelProvider`（`norpagent.protocols.model`）。

#### 25.3.1 协议

```python
class ModelProvider(Protocol):
    model_id: str
    def generate(self, messages, tools, params) -> ModelOutput: ...
    def stream(self, messages, tools, params) -> Iterator[ModelStreamChunk]: ...  # 可选
```

- `messages`：`List[ChatMessage]`（role: system / user / assistant /
  tool；工具轮次带 `tool_calls` / `tool_call_id`）；
- `tools`：OpenAI function schema 列表（无工具时为 None）；
- `params`：运行时参数 dict（temperature / max_tokens / top_p /
  自定义键），实现可自由取用；
- `ModelOutput`：`content` / `reasoning`（思维链）/ `tool_calls` /
  `usage`（`ModelUsage`）/ `finish_reason`；
- `ModelStreamChunk`：流式增量 `delta_content` / `reasoning` /
  `tool_call_delta` / `usage` / `finish_reason`。

**实现了 `stream` 的内核优先走流式路径**（逐段广播 `on_content`），
未实现则退回一次性 `generate`。建议两个都实现。

#### 25.3.2 完整示例：HTTP JSON 模型适配器

```python
# myapp/models/http_json.py —— 任意 HTTP JSON 协议模型
from __future__ import annotations

import json
from typing import Any, Dict, Iterator, List, Optional
from urllib.request import Request, urlopen

from norpagent.protocols.model import (
    ChatMessage, ModelOutput, ModelProvider, ModelStreamChunk,
    ModelUsage, ToolCallSpec,
)


class HttpJsonModel:
    model_id = "http-json"

    def __init__(self, endpoint: str, api_key: str = "", **kw):
        self._endpoint = endpoint
        self._api_key = api_key

    def _payload(self, messages, tools, params):
        body = {
            "messages": [m.to_openai() for m in messages],
            "temperature": params.get("temperature", 0.7),
        }
        if tools:
            body["tools"] = tools
        return body

    def _post(self, body, timeout=60.0):
        req = Request(self._endpoint, data=json.dumps(body).encode("utf-8"),
                      headers={"Content-Type": "application/json"})
        if self._api_key:
            req.add_header("Authorization", f"Bearer {self._api_key}")
        with urlopen(req, timeout=timeout) as resp:
            return json.load(resp)

    def generate(self, messages, tools, params) -> ModelOutput:
        data = self._post(self._payload(messages, tools, params))
        msg = data["choices"][0]["message"]
        tool_calls = None
        if msg.get("tool_calls"):
            tool_calls = [
                ToolCallSpec(id=tc["id"], name=tc["function"]["name"],
                             arguments=json.loads(tc["function"]["arguments"] or "{}"))
                for tc in msg["tool_calls"]
            ]
        usage = data.get("usage")
        return ModelOutput(
            content=msg.get("content") or "",
            tool_calls=tool_calls,
            usage=ModelUsage(
                input_tokens=usage.get("prompt_tokens", 0),
                output_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
            ) if usage else None,
            finish_reason=data["choices"][0].get("finish_reason", "stop"),
        )

    def stream(self, messages, tools, params) -> Iterator[ModelStreamChunk]:
        # 可选的流式实现；逐 chunk 检查取消事件（见下）
        from norpagent.loops.cancel import cancel_requested
        body = self._payload(messages, tools, params)
        body["stream"] = True
        with urlopen(Request(self._endpoint,
                             data=json.dumps(body).encode("utf-8"),
                             headers={"Content-Type": "application/json"}),
                     timeout=120.0) as resp:
            for line in resp:
                if cancel_requested():           # 引擎停止 / Ctrl+C 尽早退出
                    return
                line = line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                chunk = json.loads(line[5:])
                delta = chunk["choices"][0].get("delta", {})
                yield ModelStreamChunk(delta_content=delta.get("content") or "")
```

#### 25.3.3 注册、凭据回落与热重载

```python
# 程序化注册
reg.register_model("my_http", HttpJsonModel(endpoint="http://127.0.0.1:8000/v1"))

# npa() 接入：名字 / 地址 / 实例三选一
npa(model="my_http")
npa(model="myapp.models.http_json:create;endpoint=http://127.0.0.1:8000/v1")
npa(model=HttpJsonModel(endpoint="..."))

# 热重载：换模型 / 换配置 / 换代码（地址形态会失效模块缓存）
npa.remount(model="myapp.models.http_json:create;endpoint=http://127.0.0.1:9000/v1")
```

注意事项：

- **凭据回落**：装配层检查不到任何 Key（`OPENAI_API_KEY` /
  `DEEPSEEK_API_KEY` / `ANTHROPIC_API_KEY` / `DASHSCOPE_API_KEY` /
  `NORPAGENT_API_KEY`）时自动回落 `mock`（21.1 节）——自定义模型
  也建议在无凭据时给出可读错误而不是裸抛；
- **取消**：`params["_cancel_event"]` 是内核注入的取消事件（
  `call_timeout=0` 时同样注入），流式循环每 chunk 检查（4.6.2）；
- **DeepSeek V4 特判**：工具轮次 assistant 消息的 `reasoning_content`
  必须原样回传（即使空串），`ChatMessage.to_openai()` 已处理（21.1）；
- 模型槽位是**组件槽位**（`name_or_address` 语义），热重载下一次
  run() 生效。

---

### 25.4 会话开发详解

会话是 Agent 的「记忆」：对话历史的持久化与检索。实现
`SessionManager`（`norpagent.protocols.session`）即可接入任意后端
（文件 / 数据库 / 云端同步）。

#### 25.4.1 协议与完整示例

```python
class SessionManager(Protocol):
    def create_session(self, title: str = "") -> Session: ...
    def get_session(self, session_id: str) -> Optional[Session]: ...
    def append_message(self, session_id: str, message: ChatMessage) -> bool: ...
    def history(self, session_id: str) -> List[ChatMessage]: ...
    def list_sessions(self) -> List[Session]: ...
    def delete_session(self, session_id: str) -> bool: ...
```

```python
# myapp/sessions/jsonfile.py —— JSON 文件会话存储
import json, os, threading, time
from norpagent.protocols.session import Session, SessionManager
from norpagent.protocols.model import ChatMessage


class JsonFileSessions:
    """每会话一个 .json 文件。所有方法线程安全（锁保护）。"""

    def __init__(self, root: str = "./sessions", **kw):
        self._root = root
        self._lock = threading.RLock()
        os.makedirs(root, exist_ok=True)

    def _path(self, sid):
        return os.path.join(self._root, f"{sid}.json")

    def create_session(self, title=""):
        s = Session(id=f"s{int(time.time() * 1000)}", title=title,
                    created_at=time.time())
        with self._lock:
            with open(self._path(s.id), "w", encoding="utf-8") as f:
                json.dump({"title": title, "messages": []}, f, ensure_ascii=False)
        return s

    def get_session(self, session_id):
        with self._lock:
            p = self._path(session_id)
            if not os.path.exists(p):
                return None
            data = json.load(open(p, encoding="utf-8"))
            return Session(id=session_id, title=data.get("title", ""),
                           created_at=os.path.getmtime(p),
                           messages=[ChatMessage(**m) for m in data["messages"]])

    def append_message(self, session_id, message):
        with self._lock:
            p = self._path(session_id)
            if not os.path.exists(p):
                return False
            data = json.load(open(p, encoding="utf-8"))
            data["messages"].append({
                "role": message.role, "content": message.content,
                "tool_call_id": message.tool_call_id,
            })
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
            return True

    def history(self, session_id):
        s = self.get_session(session_id)
        return list(s.messages) if s else []

    def list_sessions(self):
        with self._lock:
            return [self.get_session(fn[:-5]) for fn in os.listdir(self._root)
                    if fn.endswith(".json")]

    def delete_session(self, session_id):
        with self._lock:
            p = self._path(session_id)
            if os.path.exists(p):
                os.remove(p)
                return True
            return False


def create(config=None, **kw):       # 模块级工厂
    root = (config or {}).get("root", "./sessions")
    return JsonFileSessions(root=root)
```

#### 25.4.2 注册与热重载语义

```python
reg.register_session("jsonfile", lambda: JsonFileSessions(root="./sessions"))
npa(session="jsonfile")                                   # 名字
npa(session="myapp.sessions.jsonfile:create;root=./data")  # 地址
npa.remount(session="myapp.sessions.jsonfile:create;root=./data")  # 热重载

# 续聊：跨会话通过 session_id
r1 = eng.submit("记住：我最喜欢蓝色")
r2 = eng.submit("我最喜欢什么颜色？", session_id=r1.session_id)
```

**热重载语义与工具不同**：会话是**装配槽位**，`remount` 走
「AgentRuntime 热重建」——停旧运行时 → 按当前装配建新运行时 →
前端重绑渲染器（3.7 节分组表）。重建期间的在途任务存在竞态，
生产环境请先排水再换（3.7 节「两阶段热挂载」建议）。注意：换会话
实现时历史不会自动迁移——新旧实现各管各的存储，跨实现续聊需自行
迁移数据。

---

### 25.5 沙箱开发详解

沙箱是 Agent 的「隔离执行环境」：`exec_cmd` / `run_python` 等工具
经沙箱协议执行，替换沙箱实现（容器 / 远程 / 虚拟机）**无需修改任何
工具代码**。

#### 25.5.1 协议

```python
class Sandbox(Protocol):                       # 一个已创建的沙箱实例
    def run_shell(self, command, timeout=60.0, cwd=None, env=None) -> SandboxResult: ...
    def close(self) -> None: ...

class PythonSandbox(Protocol):                 # 可选能力：隔离执行 Python
    def run_python(self, code, tool_dispatch, timeout=60.0) -> SandboxResult: ...

class SandboxProvider(Protocol):               # 提供者：按需创建沙箱实例
    kind: str
    def create(self) -> Sandbox: ...

class SandboxResult:                           # 执行结果
    stdout: str; stderr: str; exit_code: int; timed_out: bool
    # ok = exit_code == 0 and not timed_out
```

#### 25.5.2 完整示例：Docker 沙箱

```python
# myapp/sandboxes/docker_sb.py —— Docker 容器沙箱（示意）
import subprocess
from norpagent.protocols.sandbox import Sandbox, SandboxProvider, SandboxResult


class DockerSandbox:
    def __init__(self, image: str = "python:3.11-slim", **kw):
        self._image = image

    def run_shell(self, command, timeout=60.0, cwd=None, env=None):
        try:
            proc = subprocess.run(
                ["docker", "run", "--rm", "-i", self._image, "sh", "-c", command],
                capture_output=True, text=True, timeout=timeout,
            )
            return SandboxResult(stdout=proc.stdout, stderr=proc.stderr,
                                 exit_code=proc.returncode)
        except subprocess.TimeoutExpired:
            return SandboxResult(stderr="timeout", exit_code=-1, timed_out=True)
        except FileNotFoundError:
            return SandboxResult(stderr="docker not found", exit_code=-1)

    def close(self):
        pass                                        # docker run --rm 自动清理


class DockerSandboxProvider:
    kind = "docker"

    def __init__(self, image="python:3.11-slim", **kw):
        self._image = image

    def create(self):
        return DockerSandbox(image=self._image)


def create(config=None, **kw):
    return DockerSandboxProvider(image=(config or {}).get("image", "python:3.11-slim"))
```

```python
reg.register_sandbox("docker", lambda: DockerSandboxProvider(image="python:3.11"))
npa(sandbox="docker")
npa(sandbox="myapp.sandboxes.docker_sb:create;image=python:3.12-slim")
npa.remount(sandbox="myapp.sandboxes.docker_sb:create;image=python:3.12-slim")
```

开发要点：

- **超时与取消**：`run_shell` 的 `timeout` 必须兑现（`subprocess.run`
  的 timeout 即可）；引擎停止时取消事件置位（4.6.2），长任务建议
  分片检查（内置 pooled 沙箱每 ≤0.5s 检查一次并强杀进程树）；
- **进程树清理**：`sh -c` 的子进程树要随超时一起杀（Windows 用
  `taskkill /T`，见 21.4）；
- **close 必须幂等**：沙箱可能被 `shutdown` / 热重建 / 任务结束
  多处 close。

---

### 25.6 调度器开发详解

调度器是 Agent 的「编排」：任务入队、执行顺序、并发策略。
`task_submit` / `task_list` 等工具与多智能体编排都建立在它之上。

#### 25.6.1 协议与完整示例

```python
class TaskScheduler(Protocol):
    def submit(self, task: AgentTask) -> str: ...           # 入队，返回任务 id
    def pending(self) -> int: ...                           # 待办数
    def drain(self, run_task) -> List[TaskResult]: ...      # 依序执行全部待办
```

```python
# myapp/schedulers/priority.py —— 优先级调度器（数值越小越先执行）
import heapq
from norpagent.protocols.scheduler import AgentTask, TaskScheduler


class PriorityScheduler:
    def __init__(self, **kw):
        self._heap = []                       # [(priority, seq, task)]

    def submit(self, task):
        priority = int(task.params.get("priority", 0))   # 任务参数里带优先级
        heapq.heappush(self._heap, (priority, id(task), task))
        return task.id

    def pending(self):
        return len(self._heap)

    def drain(self, run_task):
        results = []
        while self._heap:
            _p, _seq, task = heapq.heappop(self._heap)
            results.append(run_task(task))    # run_task 由运行时注入
        return results


def create(**kw):
    return PriorityScheduler()
```

```python
reg.register_scheduler("priority", lambda: PriorityScheduler())
npa(scheduler="priority")
npa.remount(scheduler="myapp.schedulers.priority:create")
```

要点：`drain` 的 `run_task` 回调由运行时注入（把 Agent 循环与调度器
解耦，未来多智能体时回调可指向不同 Agent）；`persistent` 内置实现
（21.5）在崩溃后 `resume()` 续跑，自研调度器可参照。

---

### 25.7 前端与渲染器开发详解

前端是两层结构（5.1 节）：**frontend**（输入输出外壳，Frontend
协议）+ **ui**（事件渲染器，UIAdapter 协议）。

#### 25.7.1 协议

```python
class Frontend(Protocol):              # 用户交互外壳
    frontend_id: str
    def attach(self, engine) -> None: ...   # 绑定引擎：engine.submit / request_stop
    def start(self) -> None: ...            # 启动（通常自建后台线程）
    def stop(self) -> None: ...             # 停止（线程安全）
    def is_alive(self) -> bool: ...

class UIAdapter(Protocol):             # 事件渲染器
    ui_id: str
    def on_event(self, event) -> None: ...  # 渲染一个 AgentEvent
    def ask_user(self, question, default="") -> str: ...
    def notify(self, message, level="info") -> None: ...
```

#### 25.7.2 完整示例：托盘通知前端（简版）

```python
# myapp/frontends/toast.py —— 无输入、仅通知的前端（适合桌面辅助）
import threading
from norpagent.frontends.base import Frontend


class ToastFrontend:
    frontend_id = "toast"

    def __init__(self, **kw):
        self._engine = None
        self._stop = threading.Event()

    def attach(self, engine):
        self._engine = engine
        # 订阅事件总线：只关心最终结果
        engine.registry.bus.subscribe("on_task_done", self._on_done)

    def _on_done(self, event):
        result = event.get("result")
        if result is not None:
            print(f"[通知] 任务完成: {result.final_content[:80]}")

    def start(self):
        threading.Thread(target=self._run, daemon=True).start()

    def _run(self):
        while not self._stop.wait(0.2):
            pass

    def stop(self):
        self._stop.set()

    def is_alive(self):
        return not self._stop.is_set()


def create(**kw):
    return ToastFrontend()
```

```python
npa(frontend="myapp.frontends.toast:create")
# 或运行时热替换（基础设施槽位：停旧启新，失败自动回滚旧实现）
npa.remount(frontend="myapp.frontends.toast:create")
```

要点：前端**不直接渲染**——渲染交给 ui 渲染器（`npa(ui=...)`），
前端负责「读输入 → submit、接事件 → 交渲染器」。内置 Web 前端与
WebUI 渲染器是参考实现（第 22 章）。

---

### 25.8 事件循环开发详解

事件循环决定任务的调度方式：线程模型、中断方式、唤醒方式。默认
`NasyncioLoopRuntime` 已满足绝大多数场景；特殊场景（嵌入式、测试、
自研调度）可实现 `LoopRuntime` 协议替换（4.2 节）。

```python
class LoopRuntime(Protocol):
    name: str
    def start(self) -> None: ...
    def stop(self) -> None: ...
    def is_running(self) -> bool: ...
    def join(self, timeout=None) -> None: ...
    def submit(self, fn, *args, **kwargs) -> Any: ...   # 循环上下文执行并阻塞返回
```

```python
# myapp/loops/sync_loop.py —— 同步直跑循环（测试 / 嵌入式）
class SyncLoop:
    name = "sync"

    def __init__(self, **kw):
        self._running = False

    def start(self):
        self._running = True

    def stop(self):
        self._running = False

    def is_running(self):
        return self._running

    def join(self, timeout=None):
        pass

    def submit(self, fn, *args, **kwargs):
        return fn(*args, **kwargs)          # 同步直接执行


def create(**kw):
    return SyncLoop()
```

```python
npa(async_loop="myapp.loops.sync_loop")          # 地址（自动命中模块级 create）
npa(async_loop=SyncLoop())                        # 实例
npa.remount(async_loop="myapp.loops.sync_loop")   # 热重载（停旧启新）
```

开发要点（来自 4.5 / 4.6 的工程教训）：

- `submit` 是**阻塞式**契约：引擎在调用线程等待结果，实现必须兑现；
- 长任务放**守护线程池**而非循环线程（循环线程卡死 = 全部调度瘫痪）；
- 实现取消信号（`cancel_requested` 可查）与 Ctrl+C 轮询等待
  （主线程不在循环入口，见 4.6.1）；
- 替换循环时在途任务会被放弃（3.7 分组表），建议无任务时替换。

---

### 25.9 通用组件开发详解

「附加能力」类模块（上下文库、项目管理、任务存储、向量库……）不走
专用槽位，走**开放组件命名空间**（2.6.3）：`kind` 是种类（可任意
新增），`name` 是组件名，`factory` 是工厂。

#### 25.9.1 注册与使用

```python
# myapp/components/redis_store.py —— 示例：Redis 上下文存储
class RedisContextStore:
    def __init__(self, host="127.0.0.1", port=6379, **kw):
        self._host, self._port = host, port

    def add(self, session_id, text, meta=None):
        ...                                            # 实现 add / search / list / delete

    def search(self, query, limit=10):
        ...

    def close(self):
        ...


def create(config=None, **kw):
    return RedisContextStore(host=(config or {}).get("host", "127.0.0.1"))
```

```python
# 注册（种类 context_store 已有内置 fts5，新增 redis 实现）
reg.register_component("context_store", "redis",
                       lambda: RedisContextStore(host="127.0.0.1"))

# npa() 接入（context_store 槽位：address / name_or_address 语义）
npa(context_store="redis")
npa(context_store="myapp.components.redis_store:create;host=10.0.0.5")

# 自定义新种类：任意 kind 都可注册，预设里声明引用
reg.register_component("vector_store", "pg", lambda: PgVectorStore())
Preset(name="mine", components={"context_store": "redis",
                                "vector_store": "pg"})
```

工具侧取用：

```python
store = ctx.component("vector_store")          # 按种类取，无则 None
```

#### 25.9.2 热重载与工厂注入

- `context_store` / `project_manager` 是**装配槽位**：`remount` 热
  重建 AgentRuntime（3.7 分组表）；
- 工厂声明 `workspace_root` 参数（或 **kwargs）时自动注入工作区根
  （2.6.3）；
- 自定义槽位也可登记通用组件（3.8 节的 `vector_store` 槽位示例，
  25.10.4 有完整版）。

---

### 25.10 槽位开发详解（重点）

25.2 ~ 25.9 开发的是「槽位的实现」；本节开发**槽位本身**——注册
一个全新的槽位名，让它获得与内置 18 槽位完全相同的完整管线
（`npa()` 参数校验、ArchLayer 装配、`npa.remount()` 热替换、
`layer.describe()` 清单）。3.8 节给出契约速览，本节给出开发全流程。

#### 25.10.1 槽位的本质

一个槽位 = **名字 + 字符串语义 + 应用逻辑（applier）**：

- `name`：槽位名，即 `npa()` 的关键字参数名（必须是合法 Python 标识符）；
- `string_semantics`：字符串值怎么解释——`address`（模块地址）/
  `name`（注册表组件名）/ `name_or_address`（先名后址）/ `literal`
  （字面值，地址优先）（3.3 节）；
- `applier(reg, layer, value, params, ctx)`：槽位值非空时由装配器
  调用，把值「应用」到系统上（注册组件 / 订阅钩子 / 写 extras）。

#### 25.10.2 SlotSpec 字段全解

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | str | 槽位名（必填） |
| `description` | str | 描述（`layer.describe()` 清单可见） |
| `protocol` | str | 协议说明（人类可读） |
| `default_address` | Optional[str] | 默认实现地址（不填槽位时使用） |
| `string_semantics` | str | `address` / `name` / `name_or_address` / `literal` |
| `factory_kwargs` | Dict[str, str] | 工厂附加键（注入调用上下文） |
| `examples` | List[str] | 示例（文档 / 提示用） |
| `defer_factory` | bool | 工厂推迟到引擎装配期调用（agent_runtime 用） |
| `applier` | callable | 应用逻辑（槽位值非空时调用） |
| `remount_rebuild_agent` | bool | 热替换后是否热重建 AgentRuntime |

#### 25.10.3 applier 契约与重入安全

`applier` 是自定义槽位的「装配函数」——槽位值非空时，装配器调用它把值
应用到系统上。**零基础必读**：applier 的核心职责——「把用户给
这个槽位的值，注册到注册表 / 预设 / 引擎可消费的位置」。

```python
def applier(reg, layer, value, params, ctx):
    # reg   : 已装配的注册表（Registry 实例）
    # layer : 所在架构层（ArchLayer 实例；可 layer.subconfig(slot) 取子配置）
    # value : 解析后的槽位值（见下表）
    # params: 引擎装配参数（launch 的原始 kwargs）
    # ctx   : 四个可变容器（见下表），applier 把结果写进这里
    ...
```

`value` 的形态由 `string_semantics` 决定：

| string_semantics | value 形态 | 示例值 |
|---|---|---|
| `address` | 已实例化的实现（`;k=v` 子句经 `layer.subconfig(slot)` 取得） | `MyStore()` |
| `name` / `name_or_address` | 原字符串（注册表组件名） | `"fts5"` |
| `literal` | 原值；形如纯地址的字符串已按地址解析 | `"high"` / `MyKit()` |

`ctx` 的四个可变容器（写入即生效）：

| 容器 | 用途 | 消费方 |
|---|---|---|
| `ctx["components"]` | 登记通用组件 `{kind: name}`（须先 `reg.register_component`） | AgentRuntime 构建 `ctx.components`，工具经 `ctx.component(kind)` 取用 |
| `ctx["extras"]` | 引擎附加对象（按槽位名存取） | `engine.extras[槽位名]` |
| `ctx["overrides"]` | 预设字段覆盖（`model` / `tools` 等最终值） | 最终预设构造 |
| `ctx["meta"]` | 注册表架构元数据（记录**可退订对象**） | 热重载时据此清理旧订阅 |

**重入安全是硬要求**：同一注册表会重复调用 applier（装配 + 每次
`npa.remount`），重复执行不得叠加副作用——订阅事件总线的对象先按
`ctx["meta"]` 记录退订再重挂（内置 hooks / security / plugins
槽位是参考实现）；
- `remount_rebuild_agent=True`：applier 向预设 `components` 登记
  通用组件的「装配型」槽位应置 True（热替换后热重建，立即生效）。

#### 25.10.4 完整示例：开发一个「向量检索」槽位

目标：新增 `vector_store` 槽位——传入任意向量库实现（实例 / 工厂 /
模块地址），注册为 `vector_store` 种类通用组件，工具经
`ctx.component("vector_store")` 取用；热替换后立即生效。

```python
# myapp/slots/vector_store.py
from norpagent.arch import SlotSpec, register_slot


def _apply_vector_store(reg, layer, value, params, ctx):
    # 1. 解析出的 value 就是实现（实例 / 工厂 / 模块对象）
    #    ——地址形态由架构层在调用 applier 前解析并实例化
    factory = value if callable(value) else (lambda v=value: v)
    # 2. 注册为通用组件（名字固定，覆盖语义）
    reg.register_component("vector_store", "_arch_vector", factory)
    # 3. 写入预设组件声明 → AgentRuntime 构建 ctx.components
    ctx["components"]["vector_store"] = "_arch_vector"
    # 4. 写入 extras（引擎侧可直接访问 engine.extras["vector_store"]）
    ctx["extras"]["vector_store"] = value


register_slot(SlotSpec(
    name="vector_store",
    description="向量检索组件（自定义装配槽位示例）",
    protocol="任意向量库实现（注册为 vector_store 通用组件）",
    string_semantics="literal",        # 值原样传入 applier（含地址解析）
    applier=_apply_vector_store,
    remount_rebuild_agent=True,        # 热替换后热重建，组件立即生效
))
```

使用（与内置槽位体验完全一致）：

```python
import norpagent as npa

npa(vector_store=MyVectorStore())                     # 实例
npa(vector_store="myapp.vector:create;index=./idx")   # 地址 + 子句（literal 地址优先语义）
npa.remount(vector_store=OtherStore())                # 热替换：AgentRuntime 热重建
print(npa.current().engine.extras["vector_store"])    # extras 消费
# 工具内：ctx.component("vector_store") 取用
```

`string_semantics="literal"` 的「地址优先」语义（3.3 节第 2 条）：
字符串**形如纯地址**（含 `.` / `:` 的点分标识符）即按地址加载
（解析失败抛 `AddressError`），其余保持字面值——所以上面的
`"myapp.vector:create;index=./idx"` 会被解析并实例化后传给 applier。

#### 25.10.5 热重载红线：键值对的值必须是有效模块（重点）

**这是槽位开发与热重载最重要的一条规则**，与 25.2.6 的工具映射
红线同源，但适用范围更广：

> 任何槽位值中的 **dict 键值对**（tools 映射 / hooks 映射 / 自定义
> 槽位的 dict 值，**嵌套 dict 递归**），值若是**形如纯地址的字符串**
> （`is_address_like`：含 `.` 或 `:` 的点分标识符），装配器就会按
> **模块地址**解析——热重载（`npa.remount`）与启动装配（`npa()`）
> 一视同仁。**解析失败抛 `AddressError`，热重载失败，绝不静默回落。**

键值对的值必须是以下三种「有效模块」之一：

| 值形态 | 例子 | 结果 |
|---|---|---|
| 已注册名（name 语义槽位） | `tools={"a": "echo"}` | 名字引用 |
| 有效模块地址（可导入 + 属性存在） | `tools={"a": "myapp.tools:create"}` | 加载并实例化（工厂约定） |
| 有效实例 / 工厂对象 | `tools={"a": MyTool()}` | 原样使用 |
| 形如地址但无效（拼写错 / 模块不存在 / 属性不存在） | `tools={"a": "myapp.tolls:create"}` | **AddressError，失败** |

为什么必须严格：热重载是线上运维动作。地址写错却静默回落，线上会
悄悄使用旧实现 / 空实现，比显式失败更难排查——所以「写了地址就该
明确报错」。实现位于 `norpagent/arch/layer.py` 的
`_resolve_dict_values`（dict 值统一处理、嵌套递归、解析失败即抛）。

```python
# 自定义槽位 dict 值：热重载时同样严格
npa.remount(vector_store={"embedder": "myapp.embed:create",   # 有效地址 → 解析
                         "index": "./idx"})                   # 非地址 → 字面值
npa.remount(vector_store={"embedder": "myapp.embd:create"})    # 拼错 → AddressError
```

例外与边界：

- **hooks 槽位例外**：hooks 映射的值是「回调本身」，地址指向的回调
  函数**原样保留不调用**（3.3 节第 3 条）——但地址仍必须能解析
  （模块 / 属性存在），否则同样抛错；
- **list 元素不解析**：列表保持字面语义（如 `plugins=["./dir"]` 的
  目录路径；tools 列表元素由装配器按「名字或地址」特判，见 3.3 节
  第 4 条）；
- **非地址字符串不受影响**：`"high"`、`"./data"`、`"sqlite"` 等不含
  点分标识符的字符串保持字面 / 名字语义。

**热重载前会失效模块缓存**：`remount` 对字符串地址先删 .pyc、弹出
`sys.modules`，再重新导入（3.7 节）。改代码 → remount 即生效；
实例形态不做缓存失效。排查热重载失败用 `layer.describe()` 看装配
清单、`AddressError` 的 traceback 定位地址。

---

### 25.11 插件开发详解（快速上手版）

插件 = 工具 + 生命周期钩子 + 元数据，以独立 `.py` 文件（或
manifest 包）分发。宿主加载时自动获得签名校验 / AST 审计 /
导入限制 / 网络策略 / 人工审批全套安全防护（第 11 章）。本节为
快速上手示例；**完整的插件开发参考（29 钩子全表 / setup(api)
注册面 / 教程 / 排错 / 迁移 / 发布清单）见第 33 章**。

#### 25.11.1 单文件插件完整示例

```python
# my_plugins/weather_plugin.py —— 完整插件：工具 + 钩子 + 审批提示
PLUGIN_NAME = "天气插件"
PLUGIN_VERSION = "1.0.0"
PLUGIN_PUBLISHER = "xingluosama121"
PLUGIN_DESCRIPTION = "查询城市天气；任务开始时问候。"

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "weather",
            "description": "查询指定城市的当前天气。",
            "parameters": {
                "type": "object",
                "properties": {
                    "city": {"type": "string", "description": "城市名"},
                },
                "required": ["city"],
                "additionalProperties": False,
            },
        },
    },
]

# 审批提示：weather 免审批（只读），其他未声明工具走宿主总开关
APPROVAL_HINTS = {
    "weather": {"approval": "none", "risk": "L0"},
}


def execute(tool_name, args, ctx):
    """工具统一入口：处理返回 str / None，不处理返回 None。"""
    if tool_name == "weather":
        city = args.get("city") or "北京"
        return f"{city} 今日晴，25°C"          # 示例实现，可替换为真实 API
    return None


# 生命周期钩子（29 个之一；此处为兼容钩子，与旧应用 hook 名对齐；签名：业务参数在前，ctx 最后）
def on_task_start(prompt, ctx):
    print(f"[插件] 新任务: {prompt[:50]}")


def before_tool_call(tool_name, args, ctx):
    """可变钩子：返回 dict 可改写参数（11.5 节）。"""
    if tool_name == "weather" and "city" not in args:
        args = dict(args)
        args["city"] = "北京"                  # 缺省城市兜底
    return args
```

加载（宿主侧）：

```python
from norpagent.plugins import install_plugin_dirs
loader = install_plugin_dirs(reg, ["./my_plugins"], config={})
for info in loader.plugins:
    print(info.name, info.enabled, info.error or "ok")

# npa() 槽位一键加载
npa(plugins=["./my_plugins"])
```

#### 25.11.2 manifest 包格式

目录分发形式：`my_pkg/` 下 `manifest.json` + 入口模块（默认
`plugin.py`）：

```json
{
  "name": "my_pkg",
  "version": "1.0.0",
  "publisher": "xingluosama121",
  "description": "包式插件",
  "entry": "plugin.py",
  "isolation": "process",
  "permissions": [],
  "signature": ""
}
```

与单文件插件唯一的差别是入口模块里放同样的模块级接口
（`PLUGIN_NAME` / `TOOLS` / `execute` / 钩子……）。

#### 25.11.3 生命周期钩子（29 个；常用签名节选）

插件模块级可定义以下钩子函数（签名约定：**业务参数在前，
PluginContext 在最后**，`ctx` 字段全表见 33.6）：

| 钩子 | 时机 | 返回值 |
|---|---|---|
| `on_task_start(task_text, ctx)` | 任务开始 | 忽略 |
| `on_task_done(summary, final_reply, ctx)` | 任务结束 | 忽略 |
| `before_step(step, messages, ctx)` | 每步开始 | 返回 list 替换本轮消息 |
| `after_step(step, reasoning, content, tool_calls, ctx)` | 每步结束 | 忽略 |
| `before_model_call(step, messages, tool_schemas, params, ctx)` | 模型调用前 | 返回 dict 按需替换 |
| `after_model_call(step, output, ctx)` | 模型调用后 | 返回 ModelOutput 替换 |
| `before_tool_call(tool_name, args, ctx)` | 工具执行前 | 返回 dict 改写参数 / False 阻止 |
| `after_tool_call(tool_name, args, result, ctx)` | 工具执行后 | 返回 str 替换结果 |
| `on_content(token, ctx)` | 流式输出增量 | 忽略 |
| `on_task_error(error_msg, ctx)` | 任务出错 | 忽略 |
| …… | 16 兼容 + 13 原生 = **29 个，全表见 33.5** | |

#### 25.11.4 隔离、签名与发布

- **进程级隔离**：模块头声明 `ISOLATION = "process"`，插件代码只在
  宿主子进程加载执行，工具经 RPC 回传、钩子限时转发（11.7）——
  插件崩溃不拖死主进程；
- **签名**（11.8）：`python -m norpagent plugin-sign --gen` 生成密钥
  对；`plugin-sign my_plugin.py --key <私钥hex>` 生成签名（写入文件
  头部）；宿主把公钥加入 `plugin_trusted_keys` 后该插件受信任，
  审计放宽为 warn；
- **发布**：单文件插件分发 `.py` 即可；包插件压缩目录分发。

#### 25.11.5 调试与热重载

```python
# 开发期：库化门面
from norpagent.plugins import PluginSystem
ps = PluginSystem(reg, ["./my_plugins"], config={"plugin_isolation": "inproc"})
infos = ps.load()
ps.status()                 # 插件清单 + 隔离宿主状态
ps.reload("weather_plugin")  # 开发期热重载单个插件
ps.shutdown()               # 释放隔离宿主

# 运行中整体替换（框架先退订旧订阅再重装，防叠加）
npa.remount(plugins=["./my_plugins_v2"])

# 排查：看 PluginInfo
for info in ps.loader.plugins:
    if not info.enabled:
        print(info.name, info.error, info.audit_issues)
```

调试提示：`plugin_security_audit: "warn"` 只告警不拦截；
`plugin_isolation: "inproc"` 进程内直跑便于断点调试；上线前切回
`auto`（AST 静态读取 `ISOLATION`，进程隔离时**不执行插件代码**）。

---

### 25.12 开发检查清单

新模块交付前逐项自检（对应本章各节）：

| # | 检查项 | 章节 |
|---|---|---|
| 1 | 实现了完整协议（不依赖具体实现类，只依赖 protocols） | 25.1.4 |
| 2 | 工厂支持签名裁剪注入（`layer` / `slot` / `config` / `workspace_root`） | 3.4 |
| 3 | 注册进 Registry（`register_*` 或 `register_component`），名字不与内置冲突 | 25.2.5 |
| 4 | 至少一种接入方式验证通过（名字 / 地址 / 实例），地址形态可热重载 | 25.2.5 |
| 5 | **热重载验证**：dict 键值对的值是有效模块（已注册名 / 可解析地址 / 实例）；地址拼写错误时抛 `AddressError` 而非静默回落 | 25.2.6 / 25.10.5 |
| 6 | 改实现代码 → remount → 新代码生效（地址形态模块缓存失效） | 3.7 |
| 7 | 长任务 / 流式路径检查取消信号（`cancel_requested`） | 25.2.4 |
| 8 | 超时兑现：沙箱 `timeout`、模型 `call_timeout`、网络超时 | 25.5.2 |
| 9 | 线程安全：并发任务共享实例时用锁 / 不可变数据 | 25.4.1 |
| 10 | `close()` 幂等，可被 shutdown / 热重建 / 任务结束多处调用 | 25.5.2 |
| 11 | 异常不外泄：工具返回 `ToolResult(success=False)`，模型适配器捕获网络异常 | 25.2.1 |
| 12 | 装配清单可观测：`layer.describe()` 能显示你的实现 | 3.5 |
| 13 | 不反向依赖上层（依赖方向单向下行） | 2.6.1 |
| 14 | 文档与示例（SlotSpec.examples / 模块 docstring） | 25.10.2 |

完成这 14 项，你的模块就与内置组件完全同等地位：可装配、可热重载、
可审计、可替换。

---

## 第 26 章　注册流程详解

第 25 章讲「如何开发模块、槽位、插件与工具」；本章把「注册」这件事
本身讲透：**注册表（Registry）**、**槽位表（SLOT_SPECS）** 与
**地址解析器（address）** 三者如何协作，一个组件从「注册」到「被
Agent 实际使用」经历了哪些环节，以及注册的三种时机、四种形态与
校验错误处理。读完本章，你应该能回答三个问题：

1. 组件注册到哪个容器里？（注册表的 9 大命名空间）
2. 注册后框架怎么找到它？（名字 / 地址 / 实例三种定位）
3. 从 npa() 按下到工具被调用，中间发生了什么？（装配流水线）

### 26.1 注册体系全景：三个概念的职责边界

注册不是单一动作，而是三个既有机制协作的结果：

| 机制 | 所在模块 | 职责 | 典型 API |
|---|---|---|---|
| 注册表 Registry | `norpagent.kernel.registry` | **存**「名字 → 实现」的容器；内核一部分，不感知任何具体实现 | `register_*` / `resolve_*` / `build_*` / `list_*` |
| 槽位表 SLOT_SPECS | `norpagent.arch.slots` | **描述**「有哪些可填的插口」：18 个内置槽位 + 运行时 `register_slot` 热插拔 | `get_slot` / `snapshot_slots` / `register_slot` |
| 地址解析器 | `norpagent.arch.address` | **定位**：把字符串地址（`pkg.mod[:attr]`）变成对象 | `resolve_address` / `is_address_like` |
| 装配器 | `norpagent.runtime.mount` | **安装**：把槽位值翻译成注册表条目与预设覆盖 | `build_registry` / `apply_slot_overrides` |

区分三者：**槽位是插口（填什么），注册表是名字空间（存什么），
地址是定位方式（怎么找到）**。装配器负责把三者串起来。

- 槽位值填**已注册名**（如 `"sqlite"`）→ 装配器查注册表，把名字
  写进最终预设；
- 槽位值填**地址**（如 `"myapp.session:create"`）→ 装配器先解析
  地址拿到工厂，再注册为内部名（`_arch_session`）并写进最终预设；
- 槽位值填**实例 / 工厂** → 同样注册为内部名后引用。

### 26.2 注册表 Registry：9 大命名空间

`Registry`（`norpagent.kernel.registry`）持有 9 个独立命名空间，
每个都是一张「名字 → 实现」的 dict：

| 命名空间 | 注册 API | 解析 / 构建 API | 存储内容 |
|---|---|---|---|
| 模型 models | `register_model(name, provider)` | `resolve_model(name)` | 模型提供者实例 |
| 工具 tools | `register_tool(name, tool)` | `resolve_tool(name)` | Tool 实例 |
| 会话 sessions | `register_session(name, factory)` | `build_session(name)` | 工厂（每次新建实例） |
| 沙箱 sandboxes | `register_sandbox(name, factory)` | `build_sandbox(name)` | 工厂（每次新建实例） |
| 调度器 schedulers | `register_scheduler(name, factory)` | `build_scheduler(name)` | 工厂（每次新建实例） |
| UI 渲染器 uis | `register_ui(name, adapter)` | `resolve_ui(name)` | UIAdapter 实例 |
| 插件 plugins | `register_plugin(plugin)` | `unregister_plugin(name)` | Plugin 对象（含工具 + 钩子） |
| 预设 presets | `register_preset(preset)` | `resolve_preset(name)` | Preset 实例 |
| 通用组件 components | `register_component(kind, name, factory)` | `build_component(kind, name, workspace_root=...)` | 任意种类：`kind → {name: factory}` |

要点：

- **`resolve_*` 与 `build_*` 的区别**：`resolve_*` 原样返回注册时
  存入的对象；`build_*` 调用工厂**每次新建实例**——会话、沙箱、
  调度器是按需构建的（每次任务可能各自独立），模型、工具、UI 是
  共享的（同一实例全局复用）。因此注册会话 / 沙箱 / 调度器时传的
  必须是**工厂**（函数或类），注册模型 / 工具 / UI 时传的是**实例**。
- **名字覆盖语义**：dict 赋值，后注册者覆盖先注册者，不报错。
  插件注册工具时若与既有工具重名，打印
  `[Registry] 工具 xxx 已存在，被插件 xxx 覆盖` 日志后覆盖。
- **线程安全**：内部 RLock 保护，任意线程可随时注册 / 解析。
- **通用组件是开放命名空间**：`kind` 不限于框架内置
  （`context_store` / `project_manager` 等），第三方可注册任意新
  种类（如 `vector_store`），框架无需改内核即可扩展（25.9.1）。
- `register_plugin` 是复合注册：插件的工具逐个进工具表、钩子逐条
  订阅事件总线、插件对象进插件表；`unregister_plugin` 退订钩子、
  移除插件记录（工具条目按名字覆盖语义保留，不在预设工具集内即
  不可达）。

### 26.3 注册的四种形态与字符串语义

一个组件从开发者手里到注册表，有四种「形态」：

| 形态 | 写法 | 说明 |
|---|---|---|
| 实例 | `npa(tools=[MyTool()])` | 直接可用；装配器包装为返回同一实例的工厂注册 |
| 工厂函数 / 类 | `npa(model="myapp.model:create")` 解析出 callable | 按签名裁剪注入上下文（`layer` / `slot` / `config` / `workspace_root`，3.4 节） |
| 已注册名引用 | `npa(model="openai_compat")` | 字符串先查注册表，查到即名字引用 |
| 地址字符串 | `npa(model="myapp.model:create")` | 字符串查不到名字 → 按地址解析 |

字符串进槽位后按该槽位的**字符串语义**解释（`SlotSpec.string_semantics`，
四选一）：

| 语义 | 解释 | 槽位举例 |
|---|---|---|
| `address` | 字符串 = 模块地址（`pkg.mod[:attr]`），必须可解析 | `async_loop` / `frontend` / `context_store` / `project_manager` |
| `name` | 字符串 = 注册表组件名，原样透传 | `tools` |
| `name_or_address` | 先按注册表名、查不到再按地址解析 | `model` / `session` / `sandbox` / `scheduler` / `ui` / `preset` |
| `literal` | 字符串 = 字面值（级别 / 路径 / 目录）；v0.9.1 起形如纯地址（含 `.` 或 `:` 的点分标识符）的字符串按地址加载 | `hooks` / `security` / `plugins` / `logger` / `storage` / `error_handler` |

v0.9.1 起全部槽位的 **dict 键值对**统一支持地址解析
（`layer.py` 的 `_resolve_dict_values`，递归处理嵌套 dict）：

- 值形如纯地址 → 按地址解析为对象；解析失败抛 `AddressError`，
  **不静默回落**（红线，见 25.2.6）；
- 解析出 callable → 按工厂约定调用（`hooks` 槽位除外：值是回调
  本身，原样保留不调用）；
- 非字符串值原样保留。

地址本身支持**附加配置子句**：`"pkg.mod:create;port=9000;theme=dark"`
——分号后的 `键=值` 对被解析为字典注入工厂的 `config` 参数
（3.3 节 / 3.4 节）。

### 26.4 一次注册到装配的全链路（npa() 启动）

以 `npa(model="myapp.model:create", tools={"weather": "myapp.weather_tool:create"})`
为例，逐步跟踪从启动到工具被调用的完整链路：

```
npa(...) 启动
│
├─ 1. launch() 参数拆分（runtime/__init__.py）
│     按「实时槽位表快照」拆分：
│     - 槽位键（model / tools / ...）→ slot_values
│     - 其余键（max_steps / workspace_root / ...）→ 运行时参数 params
│
├─ 2. ArchLayer(config, **slot_values) + mount_defaults(layer)
│     登记内置默认实现工厂（async_loop / frontend / agent_runtime）
│
├─ 3. layer.connect()（幂等，逐槽位解析）
│     - model（name_or_address）：字符串先不动，透传给装配器判定
│     - tools（dict）：_resolve_dict_values 递归解析键值对——
│       值 "myapp.weather_tool:create" 形如地址 → resolve_address
│       导入 myapp.weather_tool 模块 → 取 create 属性（callable）
│       → call_factory 按签名调用 → WeatherTool 实例
│
├─ 4. build_registry(layer, params)（runtime/mount.py）
│     a. Registry() 新建空注册表
│     b. install_defaults(reg)    内置组件入表（模型 openai_compat /
│        anthropic / mock；21 个内置工具；会话 sqlite / memory；
│        沙箱 pooled / subprocess；调度器 persistent 等）
│     c. register_all_presets(reg) 六种内置预设入表（standard 等）
│     d. apply_slot_overrides(reg, layer, params) 按固定顺序装配：
│        ├─ preset 槽位 → 基线预设（默认 standard）
│        ├─ model：地址解析 → register_model("_arch_model", 工厂)
│        │    → overrides["model"] = "_arch_model"
│        ├─ tools：dict → 逐个 register_tool("weather", 实例)
│        │    → overrides["tools"] = ["weather"]（只启用你声明的）
│        ├─ session / sandbox / scheduler：注册为 _arch_xxx 或引用
│        ├─ ui：register_ui("_arch_ui", 实例) → extras["ui_adapter"]
│        ├─ context_store / project_manager：register_component(kind,
│        │    "_arch_xxx", 工厂) → 写入 components 声明
│        ├─ hooks：先退订上次的架构级订阅 → bus.subscribe 重挂
│        ├─ security：safe() 安装安全套件（记录进 meta 可退订）
│        ├─ plugins：install_plugin_dirs 走完整加载管线
│        ├─ logger / storage / error_handler → extras（引擎消费）
│        ├─ 自定义槽位：遍历 snapshot_slots()，applier 非空的
│        │   逐槽位调用 applier(reg, layer, value, params, ctx)
│        └─ 组装最终预设 Preset(...)（槽位覆盖 + 基线合并）
│           → reg.register_preset(final)
│
├─ 5. NorpEngine(layer, registry, preset, loop, frontend, extras)
│     engine.start() → _build_agent()：
│       call_factory(agent_runtime 槽位实现, {registry, preset, ui,
│       task_params, layer, config}) → AgentRuntime 构造完成
│
└─ 6. 消费（engine.submit(text) → agent.run()）
      registry.resolve_model(preset.model)    → 模型实例
      registry.tool_schemas(preset.tools)     → 工具 schema 列表
      registry.resolve_tool(name)             → 工具实例（调用时）
      registry.build_session(preset.session)  → 会话实例（按需新建）
      registry.build_sandbox(preset.sandbox)  → 沙箱实例（按需新建）
```

三个关键结论：

1. **注册发生在装配器，消费发生在 Agent 运行时**——你的组件一旦
   进表，核心代码零修改即可使用；
2. **槽位值最终都变成「注册表条目 + 预设声明」**：内部名
   （`_arch_xxx`）是装配器的通用手段，保证「你的实现」和「内置
   实现」以完全相同的路径被消费；
3. **顺序敏感**：preset 先定基线，随后各槽位覆盖基线，最后合并
   出最终预设——所以 `npa(preset="minimal", model="myapp.model:create")`
   的最终预设 = minimal 基线 + 你的模型覆盖。

### 26.5 三种注册时机与热重载

| 时机 | 方式 | 生效时机 | 典型场景 |
|---|---|---|---|
| 启动装配期 | `npa()` 槽位参数（声明式）；或 `npa()` 前直接 `reg.register_*`（程序式） | 启动即生效 | 应用装配、库化集成 |
| 运行期 | `npa.remount(slot=...)`；或运行中直接 `reg.register_*` | 组件槽位：下一次 run()；装配槽位：AgentRuntime 热重建 | 换模型 / 换工具集 / 换安全级别 |
| 代码热重载 | 改模块文件 → `npa.remount(model="myapp.model:create")` | 立即（模块缓存已失效） | 开发迭代、线上修 bug |

程序式注册与 `npa()` 的顺序约定：

```python
reg = Registry()
reg.register_tool("weather", WeatherTool())   # 先注册
reg.register_preset(Preset(name="mine", tools=["weather"], ...))
npa(preset="mine")                              # 再启动，按名引用
```

注意：`npa()` 内部会新建自己的 `Registry()` 并安装内置组件，但
**不会清空你在 npa() 之前对同一个 reg 的注册**——前提是你把同一个
reg 用上（如上面的程序式装配，或直接把 reg 传给自定义
`agent_runtime` 工厂）。最省心的做法是：程序式装配用
`build_registry(layer)` 产出的 reg，声明式装配用 `npa()` 槽位参数。

热重载的模块缓存失效机制（3.7 节）：`remount` 对字符串地址先执行
`_invalidate_address_module`——删除模块 `__cached__` 对应的 .pyc、
弹出 `sys.modules` 条目，下次解析从磁盘重新导入。因此
「改 `myapp/weather_tool.py` → `npa.remount(tools={"weather":
"myapp.weather_tool:create"})`」即热更新代码；**实例 / 已注册名
形态没有可失效的地址，改代码后请用地址形态**。

重入安全：`apply_slot_overrides` 可对运行中的注册表重复执行（每次
`npa.remount` 都调），重复执行前会先退订上次由它挂上的架构级订阅
（钩子扩展 / 安全套件 / 插件），保证热挂载不叠加重复订阅——自定义
槽位 applier 同样要遵守此约定（用 `ctx["meta"]` 记录待退订对象，
25.10.3）。

### 26.6 槽位注册与通用组件注册：两种「注册」的区别

框架有两套「注册」API，容易混淆，对比如下：

| 维度 | `register_slot`（槽位表热插拔） | `register_component`（通用组件） |
|---|---|---|
| 注册什么 | **插口**：新的 npa() 关键字参数（槽位名） | **实现**：某种类（kind）下的具名实现 |
| 入口 | `norpagent.arch.slots.register_slot` | `reg.register_component(kind, name, factory)` |
| 生效范围 | npa() 参数校验、ArchLayer 装配、`npa.remount` 热替换、`layer.describe()` 清单全管线 | 预设 `components` 声明 + `ctx.component(kind)` 取用 |
| 装配方式 | `SlotSpec.applier(reg, layer, value, params, ctx)` 回调 | 框架按 preset.components 直接 `build_component` |
| 保护规则 | 18 个内置槽位名不可注册 / 覆盖 / 注销 | 无保护（dict 覆盖语义） |

核心逻辑：**先有插口（槽位），再有塞进插口的实现（注册表条目）**。
绝大多数情况你只需要注册实现（`register_tool` / `register_component`）；
只有当你想要一个全新的「npa() 可填参数」时才需要 `register_slot`
（完整开发流程见 3.8 节与 25.10 节）。

`register_slot` 的校验规则（违反抛 `SlotError`）：

- 槽位名必须是合法 Python 标识符（它是 npa() 的关键字参数名），
  且不能是 Python 关键字、不能是 `prompt` / `config`（launch 特殊键）；
- 18 个内置槽位名受保护（`is_builtin_slot`）；
- `string_semantics` 必须是 `address` / `name` / `name_or_address` /
  `literal` 之一；`applier` 必须是 callable 或 None；
- 重名注册需要 `replace=True`（仅限自定义槽位，热替换规格；已装配
  的实现保持原状，下一次 remount 按新规格解析）。

`register_slot` 注册即生效：注册发生在 `npa()` 调用之前即可被识别
为槽位（launch 按实时槽位表拆分参数）；注册发生在运行中，已启动
的架构层 `connect` 幂等补齐、`remount` 可直接使用新槽位。

### 26.7 注册校验与错误处理

注册 / 装配阶段的三类异常，语义各不相同：

| 异常 | 抛出场景 | 处理建议 |
|---|---|---|
| `ComponentError` | 解析未注册名；`register_preset` 收到非 Preset；自定义槽位 applier 异常（统一包装） | 检查名字是否注册、拼写是否正确；用 `reg.list_*()` 核对可用名 |
| `SlotError` | 槽位表非法操作：注册内置槽位名 / 重名不 replace / 注销不存在 / 槽位名非法 | 按错误信息修正规格；内置槽位改值用 `npa.remount` 而非改规格 |
| `AddressError`（继承 ImportError） | 地址解析失败：模块不存在 / 属性不存在 / 地址为空 | 检查模块路径与属性名；import 该模块自测；**不要静默回落**（25.2.6 红线） |

预设引用的完整性可提前校验：

```python
missing, missing_tools = reg.validate_preset(my_preset)
# missing == [] 且 missing_tools == [] 时预设才可用
# missing 示例: ["model=openai_compat", "component=vector_store:pg"]
```

运行期诊断三板斧：

```python
reg.list_tools()                    # 注册表里到底有什么（1 类）
reg.tool_schemas(["weather"])       # 工具的 schema 是否可用（2 类）
eng.layer.describe()                # 装配清单：每个槽位从哪来（3 类）
```

### 26.8 注册流程最佳实践与检查清单

最佳实践：

1. **命名规范**：小写字母 + 下划线，与内置名（`sqlite` / `pooled` /
   `persistent` / `openai_compat` 等）不冲突；插件工具名前缀插件名
   避免覆盖（`weather_current` 优于 `get_time`）。
2. **工厂 vs 实例**：会话 / 沙箱 / 调度器传**工厂**（每次新建）；
   模型 / 工具 / UI 传**实例**（全局共享）。工具要带每次运行独立
   的状态才用工厂包装，否则共享实例即可（注意线程安全）。
3. **注册时机**：声明式（`npa()` 槽位）适合应用装配；程序式
   （`reg.register_*`）适合库化集成与动态条件装配；热重载
   （`npa.remount`）适合开发迭代与线上调整——三者可混用，最终
   都汇入同一张注册表。
4. **地址形态优先**：模块地址（`pkg.mod[:attr]`）同时获得工厂
   注入、`;key=value` 子句、代码热重载三项能力，是推荐形态。
5. **热重载红线**：dict 键值对的值必须是有效模块——已注册名 /
   可解析地址 / 实例三选一；形如地址却解析失败会抛 `AddressError`，
   绝不静默回落（25.2.6 / 25.10.5）。
6. **装配可观测**：交付前跑一遍 `layer.describe()`，确认你的实现
   出现在清单里、来源正确（地址 / 直接值 / 默认逻辑）。

注册流程检查清单（新组件交付前逐项自检）：

| # | 检查项 | 依据 |
|---|---|---|
| 1 | 组件注册进正确的命名空间（工具→tools，会话→sessions，组件→components） | 26.2 |
| 2 | 会话 / 沙箱 / 调度器传工厂，模型 / 工具 / UI 传实例 | 26.2 |
| 3 | 名字不与内置冲突、小写下划线 | 26.8 |
| 4 | 至少一种形态验证：`reg.list_*()` 能看到、`resolve_*` 能取到 | 26.7 |
| 5 | 地址形态可导入：`import myapp.xxx` 成功、属性存在 | 26.7 |
| 6 | 地址形态可热重载：改代码 → remount → 新代码生效 | 26.5 |
| 7 | dict 键值对的值是有效模块（红线） | 26.7 / 25.2.6 |
| 8 | 预设引用校验通过：`validate_preset` 无缺失 | 26.7 |
| 9 | `layer.describe()` 装配清单显示正确来源 | 26.4 / 3.5 |
| 10 | 自定义槽位 applier 重入安全（`ctx["meta"]` 记录待退订对象） | 26.5 / 25.10.3 |
| 11 | 异常语义正确：未注册→`ComponentError`，地址错→`AddressError`，槽位表→`SlotError` | 26.7 |
| 12 | 卸载路径存在：插件 `unregister_plugin`、槽位 `unregister_slot` | 26.2 / 26.6 |

---

## 第 27 章　最小内核详解：事件总线、槽位连接器、注册表与地址解析器

> 前置阅读：第 2 章 2.3（最小内核四模块定义）、第 3 章（架构层与地址函数）、
> 第 9 章 9.5（钩子与 EventBus 的关系）、第 26 章（注册流程）。
> 本章把四件「不可替换」的组件逐一拆开讲透：它们各自的数据结构、API、
> 内部机制，以及一次启动与热挂载中四者如何协作。

### 27.1 总览：四者构成装配闭环

2.3 节已给出最小内核的定义——全框架仅四样不可替换：

| # | 组件 | 类 / 模块 | 职责概述 |
|---|---|---|---|
| 1 | 槽位连接器 | `norpagent.arch.layer.ArchLayer` | 把「槽位值」装配成「实现对象」，支持运行中热挂载 |
| 2 | 地址解析器 | `norpagent.arch.address`（`resolve_address`） | 把「地址字符串」解析成「可用的对象」 |
| 3 | 注册表 | `norpagent.kernel.registry.Registry` | 名字 → 组件的映射中心，一切皆注册项 |
| 4 | 事件总线 | `norpagent.kernel.events.EventBus` | 组件间的事件传递通道，写时复制 + 无锁迭代 |

其余组件——事件循环、Agent 循环、模型、工具、会话、沙箱、调度器、上下文库、
项目管理、钩子扩展、安全、插件、前端、渲染器、预设、日志、存储、错误处理——
均为槽位，全部可以替换。

四者的协作闭环（一次 `npa()` 启动）：

```
npa(...) 槽位值
   │
   ▼
┌───────────────────────────────────────────────────────┐
│ ArchLayer（槽位连接器）                                  │
│   1. set_default()    注册各槽位内置默认逻辑             │
│   2. connect() 逐槽位装配（_connect_slot）：            │
│        值=None    → 默认工厂                            │
│        值=字符串  → resolve_address() 解析（地址解析器） │
│        值=dict    → 键值对地址递归解析                   │
│   3. layer[slot] 直接取实现；describe() 输出装配清单     │
└───────────────────────────────────────────────────────┘
   │ 装配结果落到注册表
   ▼
┌───────────────────────────────────────────────────────┐
│ Registry（注册表）                                      │
│   组件按名字注册 / 解析；bus 与 hooks 挂在注册表上        │
│   build_registry() / apply_slot_overrides() 填充        │
└───────────────────────────────────────────────────────┘
   │ 运行期
   ▼
┌───────────────────────────────────────────────────────┐
│ EventBus（事件总线）                                    │
│   AgentRuntime / UI / 插件 / 钩子 全部订阅总线           │
│   emit() 广播通知；intercept() 可变分发 + 一票否决        │
└───────────────────────────────────────────────────────┘
```

职责边界速览：

- 地址解析器只回答「地址是什么对象」；
- 槽位连接器只回答「这个槽位装什么、怎么装、能不能换」；
- 注册表只回答「这个名字对应哪个组件、怎么造出来」；
- 事件总线只回答「谁在什么时候收到什么通知」。

四者相互独立，各自都不知道对方的具体实现（地址解析器不知道 Registry，
EventBus 不知道 ArchLayer），由 `runtime.mount` 装配器把它们串起来。
下面的小节逐一展开。

### 27.2 通用事件总线（GeneralEventBus；类名 `EventBus`）

> 术语：本手册中「通用事件总线」（General Event Bus，简称
> **GeneralEventBus**）指代 `norpagent.kernel.events.EventBus` 类及其实例。
> 仅文档术语统一，**代码符号名不变**（类名、函数名、导入路径照旧）。

#### 27.2.1 定位与设计目标

EventBus 是「内核与所有外部组件（UI / 插件 / 钩子）的唯一解耦点」：
AgentRuntime 不直接调用 UI 的方法，而是向总线发事件；UI 只订阅总线，
不感知内核实现。

代码位置：`src/norpagent/kernel/events.py`。

核心类型：

- `EventType(str, Enum)`：16 个标准事件名（兼容 hook 面；与既有应用
  生态逐一对齐；自 v2.1.0 起插件体系直接开放全部 9 层 29 钩子，标准
  事件名保持不变，见 33.5）；迁移时映射一一对应：hook = 事件订阅（11.5 / 附录 E）；
- `AgentEvent`：一条事件 = `type` + `payload`(dict) + `ts`，带 `.get()` 取值；
- `HookVeto`：一票否决异常（`intercept` 不捕获它，直达内核）；
- `EventBus`：总线本体（线程安全）。

#### 27.2.2 数据结构与线程安全模型

```python
self._all: List[Listener]                  # 订阅所有事件的监听器
self._typed: Dict[str, List[Listener]]     # 按事件类型分组的监听器
self._lock = threading.RLock()             # 写锁
self._log_error: Optional[Callable]        # 订阅者异常回调
```

线程安全采用「写时复制 + 无锁迭代」：

- `subscribe` / `unsubscribe`：锁内**构建新列表**并替换引用，绝不原地修改；
- `emit` / `intercept`：锁内只取一次引用（`_snapshot`），随后**无锁直接迭代**；
- 读者持有的旧快照永不被动（写者替换的是新列表对象），并发安全不变；
- 对高频事件（如按 token 推送的 on_content）省掉了每次事件都复制监听器
  列表的开销。

实测口径（23.1）：静态订阅表 + 单线程发布，超过 160 万事件/秒。

#### 27.2.3 订阅与退订

```python
from norpagent.kernel import EventBus

bus = EventBus()

def on_content(e):
    print(e.type, e.get("content"))

bus.subscribe(on_content, "on_content")        # 只收 on_content
bus.subscribe(lambda e: print("all:", e.type)) # None = 收所有事件
bus.unsubscribe(on_content, "on_content")      # 退订
```

- `event_type=None` 进入 all 列表（收全部事件）；
- 指定类型进入 typed 列表；
- 退订按「第一个相等元素」移除（`_without_one`），重复订阅只退一个。

#### 27.2.4 emit 与 intercept：广播 vs 可变分发

| 维度 | `emit(event_type, **payload)` | `intercept(event_type, **payload)` |
|---|---|---|
| 用途 | 观察 / 通知（UI 刷新、日志） | 改写数据流、一票否决 |
| 返回值 | 忽略 | 第一个非 None 返回值胜出；全 None = 不干预 |
| 订阅者异常 | 捕获并记录，继续跑 | 普通异常同上；**HookVeto 不捕获**，直达内核 |
| 调用顺序 | 先 all 订阅者、再 typed 订阅者 | 同左 |

`intercept` 与旧插件系统 `_broadcast_mutating` 语义一致：before_step /
before_tool_call / after_tool_call 等可变钩子通过返回值改数据流
（None = 不干预）。

订阅者异常隔离：默认打印到 stderr，可 `set_error_logger(cb)` 自定义——
订阅者绝不能打断主流程（普通异常全捕获 + `_report_error`），这是
「总线可用性优先」的硬设计。

#### 27.2.5 16 个标准事件

| 层 | 事件 | 触发点 |
|---|---|---|
| L1 agent 生命周期 | on_agent_init / on_agent_shutdown | 引擎启动 / 关闭 |
| L2 任务 | on_task_start / on_task_done / on_task_error / on_task_stopped / on_task_timeout | 任务五态 |
| L3 step | before_step / after_step / before_tool_call / after_tool_call / on_user_input_required | 步骤与工具调用 |
| L4 流式 | on_reasoning / on_content / on_event / on_usage_update | token 级推送 |

#### 27.2.6 与 HookSystem 的关系

`HookSystem(bus)` 是同一总线上的「9 层 29 钩子视图」：
`registry.hooks.before_model_call.subscribe(fn)` 等价于在 `registry.bus`
订阅同名事件；未注册的具名事件在发射时自动成为 dynamic 层钩子。
详见第 9 章 9.5、附录 E。

```python
from norpagent import Registry

reg = Registry()
reg.hooks.before_model_call.subscribe(my_fn)   # 钩子视图（推荐）
reg.bus.subscribe(my_fn, "before_model_call")  # 直接总线（等价）
```

内核侧也是这么发射的（`AgentRuntime` 内部）：

```python
self.hooks.on_agent_init.emit(preset=self.preset.name)     # 广播
result = self.hooks.before_tool_call.intercept(...)        # 可变分发
```

#### 27.2.7 通用能力（v0.9.7）：once / wait / emit_all / 查询与清空

在核心四件套（subscribe / unsubscribe / emit / intercept）之外，
通用事件总线提供六项面向「程序化集成 / 外部脚本 / 测试」的能力，
全部线程安全、向后兼容：

```python
from norpagent.kernel import EventBus

bus = EventBus()

# 1) once：一次性订阅——触发一次后自动退订，不泄漏
bus.once(lambda e: print("first only:", e.get("v")), "evt_x")
bus.emit("evt_x", v=1)
bus.emit("evt_x", v=2)          # 第二次不再触发

# 2) wait：阻塞等待事件，返回 AgentEvent（超时返回 None，临时订阅自动清理）
ev = bus.wait("on_task_done", timeout=30.0)   # 外部脚本等待任务完成
if ev is not None:
    print("task_id:", ev.get("task_id"))

# 3) emit_all：发布并收集全部订阅者返回值（区别于 emit 丢弃返回值、
#    intercept 首个非 None 即停——emit_all 返回完整有序结果列表）
results = bus.emit_all("query_metrics", scope="all")
for r in results:
    if r is not None:
        print("metric:", r)

# 4) subscriber_count / has_listeners：订阅状态查询
bus.subscriber_count("on_content")                        # 具名事件订阅者数
bus.subscriber_count()                                    # 全事件订阅者数
bus.has_listeners("on_content")                           # 是否有订阅者

# 5) clear：清空订阅（测试 / 热重载重建总线用），返回移除数量
removed = bus.clear()            # 全部清空
removed = bus.clear("evt_x")     # 只清某事件
```

行为要点：

- `once` 内部包装订阅，触发即退订；超时/异常路径不会残留订阅；
- `wait` 超时后**自动退订临时捕获器**（含"事件恰在超时瞬间到达"的竞态
  复查），不存在订阅泄漏；`timeout<=0` 视为无限等待；
- `emit_all` 对 `HookVeto` 不捕获（与 intercept 一致），普通订阅者异常
  隔离记录后继续；
- `clear` 不通知被移除的订阅者，返回实际移除数量。

#### 27.2.8 与其他三件内核组件的协作边界

见 27.6（启动 / 热挂载走查）与 27.5.5（注册表与总线的挂接方式）。

### 27.3 地址解析器 AddressResolver

#### 27.3.1 定位

代码位置：`src/norpagent/arch/address.py`。

地址解析器只做一件事：**把「地址」变成「对象」**——不调用工厂、不做装配、
不检查协议。工厂上下文注入与调用规则在 `norpagent.arch.layer.call_factory`。
「不填 = 默认，填了 = 接入」的地址函数语义（3.2）全部由它落地。

#### 27.3.2 四种地址形态

| 形态 | 含义 |
|---|---|
| `None` | 用槽位默认实现（调用方处理；解析器原样返回 None） |
| `"pkg.mod"` | 导入模块；优先取模块内约定工厂属性 `create` / `build` / `default`，都没有则整模块挂载 |
| `"pkg.mod:attr"` | 导入模块并取指定属性作为实现 |
| callable / 其他对象 | 原样返回（工厂函数 / 类 / 实例 / 值） |

```python
from norpagent.arch.address import resolve_address

resolve_address(None, slot="model")                    # -> None
resolve_address("myapp.models:create", slot="model")   # -> 模块属性 create
resolve_address("myapp.tools", slot="tools")           # -> create/build/default 之一，否则整个模块
resolve_address(MyTool(), slot="tools")                # -> 原对象（实例直传）
```

解析细节：

- 属性回退顺序 `_FACTORY_ATTRS = ("create", "build", "default")`；
- 整模块挂载要求模块本身实现槽位协议（例如一个完整的 LoopRuntime 模块）；
- `:attr` 属性缺失时报 `AddressError`（绝不静默回落）。

#### 27.3.3 附加配置子句剥离

`"pkg.mod:create;timeout=5"` 中分号后的 `key=value` **不是地址的一部分**——
解析器先剥离，由 ArchLayer 解析成工厂的 `config` 注入参数。子句永远不会
干扰模块路径 / 属性解析：

```python
npa(model="myapp.models:create;api_key=sk-xxx;base_url=https://...")
# 地址 = myapp.models:create
# config = {"api_key": "sk-xxx", "base_url": "https://..."}
```

#### 27.3.4 is_address_like：纯结构判定

`is_address_like(value)` 判断字符串是否形如「纯地址」（`pkg.mod[:attr]`）——
纯结构检查，无导入、无副作用、无异常：

- 剥离 `;key=value` 后，整串是含至少一个 `.` 或 `:` 的点分标识符；
- 因此 `"high"` / `"./data"` / `"my_tool"` / `"https://api.example.com"`
  这类字面量、路径、URL 永远不会被误判为地址；
- `"myapp.security:high"` / `"myapp.tools"` / `"pkg:attr"` 是地址。

用于 v0.9.1 的「地址优先」判定：literal 槽位与 dict 键值对中，地址形态的
字符串按地址加载，其余保持原语义（3.3 / 26.3）。

#### 27.3.5 错误语义

```python
class AddressError(ImportError): ...
```

模块导入失败、属性缺失、空地址字符串 → 统一抛 `AddressError`
（继承 ImportError，可被 `except ImportError` 捕获），错误消息带槽位名与
完整地址，便于定位。**红线：形如地址却解析失败必须抛错，绝不静默回落到
字面量**（25.2.6 / 25.10.5）。

#### 27.3.6 解析与调用的分工

```
resolve_address("myapp.models:create", slot="model")  # 解析：拿到工厂对象
call_factory(create, {"layer": layer, "slot": "model", "config": {...}})  # 调用
```

- `call_factory` 按签名注入 `layer / slot / config` 等键；工厂不声明的键
  自动忽略，任何风格的工厂都能插进来；
- 完全无参的工厂直接零参调用；不可内省的 callable（内置函数）零参调用；
- 非 callable（模块 / 实例 / 值）原样返回，不调用。

### 27.4 槽位连接器 ArchLayer

#### 27.4.1 定位

代码位置：`src/norpagent/arch/layer.py`。模块 docstring 第一句即定义：
「Architecture layer (ArchLayer): the slot connector」——槽位连接器。

ArchLayer 是「积木托盘」：

1. 接收一组槽位值（关键字参数 / 配置 dict）；
2. 槽位留空 → 用默认实现（库内置逻辑，经 `set_default` 注册）；
3. 槽位填了地址 → 调地址解析器并装配；装配后 `layer[slot]` 直接给实现
   对象，`layer.describe()` 打印完整装配清单（可观测）。

#### 27.4.2 数据结构

```python
self.config: Dict[str, Any]                # 槽位值（config dict 与关键字合并，关键字优先）
self._impls: Dict[str, Any]                # 装配结果：槽位 -> 实现对象
self._defaults: Dict[str, factory]         # 默认实现工厂（ctx -> impl）
self._subconfigs: Dict[str, Dict]          # 地址中解析出的 ;key=value 子句
self._connected: bool                      # 是否已 connect()
```

#### 27.4.3 核心 API

| 方法 | 作用 |
|---|---|
| `set_default(slot, factory)` | 注册该槽位的默认实现工厂（装配器 `mount_defaults` 在 connect 前调用） |
| `connect()` | 装配全部槽位；**幂等**——重复调用只补装后注册的新槽位 |
| `remount(slot, value=_RAISE)` | 运行中热挂载：不传 value 按当前配置重解析（先失效模块缓存）；传 None 清空槽位配置回默认；其他值替换配置并立即重建 |
| `layer[slot]` / `get(slot, default)` | 取装配结果（未 connect 时 `__getitem__` 抛 RuntimeError） |
| `subconfig(slot)` | 取该槽位地址中解析出的附加配置子句 |
| `describe()` | 打印装配清单：每个槽位的来源（默认 / 地址 / 直接值）与实现类型 |
| `is_connected()` | 是否已装配 |

#### 27.4.4 字符串分派：string_semantics 四语义

`_connect_slot` 按槽位的 `string_semantics` 分派字符串值：

| 语义 | 字符串值处理 |
|---|---|
| `address` | 作为模块地址解析（默认语义） |
| `name` | 作为注册表组件名透传（由装配器决定注册） |
| `name_or_address` | 先按组件名、再按模块地址（装配器在 registry 上下文中决定） |
| `literal` | 字面量（级别 / 路径 / 日志名） |

v0.9.1 起所有槽位都支持「地址优先」：

- name / name_or_address 槽位：字符串先查注册表名，查不到再按模块地址解析；
- literal 槽位：字符串形如纯地址（`is_address_like`）→ 按地址加载，否则
  保持字面量；
- **任何槽位的 dict 键值对**：值为纯地址字符串 → 统一按地址解析成对象
  （`_resolve_dict_values` 递归处理，任意深度；列表元素不解析，保持字面
  语义；hooks 槽位的值是回调本身，地址指向的回调保持原样不调用）。

特例：frontend 槽位的字符串值若是 `.html/.htm` 文件路径，不走地址解析，
透传给装配器做「HTML 路径直挂」（等价 `WebFrontend(html=...)`，5.4）。

#### 27.4.5 defer_factory：推迟实例化

`defer_factory=True` 的槽位（如 agent_runtime）在 connect 阶段**只解析
地址、不实例化**；工厂调用推迟到引擎装配期（`NorpEngine._build_agent`），
那时 registry / preset 上下文已就绪，按签名注入完整上下文。

#### 27.4.6 热挂载与模块缓存失效

```python
layer.remount("model", "myapp.models:v2")   # 换实现
layer.remount("model")                      # 按当前配置重解析（热重载改过的代码）
layer.remount("model", None)                # 清空配置，回落到默认逻辑
```

`remount` 的字符串地址会先做两步缓存失效（`_invalidate_address_module`）：

1. 删除模块字节码缓存（`module.__cached__` 的 .pyc）——否则同一秒内改写
   同尺寸文件会被 importlib 误判为「缓存仍新」，重新导入拿到旧代码；
2. 弹出 `sys.modules` 条目——下次解析从磁盘重新导入。

于是「改代码 → remount → 新代码生效」的热重载闭环成立。自定义槽位
（`register_slot` 注册，3.8）同样支持 remount，按注册时的 spec 解析；
`replace=True` 热替换 spec 后再 remount 按新 spec 解析。

#### 27.4.7 与槽位表的关系

槽位表（`norpagent.arch.slots`，`SLOT_SPECS`）本身可热插拔：`register_slot()`
运行时注册自定义槽位后，connect / remount / describe / set_default 全部按
**调用时刻的活表**工作——connect 幂等补装晚注册的槽位，remount 同样适用于
新槽位。SlotSpec 字段（name / protocol / default_address / string_semantics /
factory_kwargs / defer_factory / applier / remount_rebuild_agent）见 25.10.2。

#### 27.4.8 最小使用示例

```python
from norpagent.arch.layer import ArchLayer

layer = ArchLayer(async_loop="myapp.loop:create", preset="standard")
layer.connect()                 # 装配全部槽位
loop = layer["async_loop"]      # 已连接的循环系统
print(layer.describe())         # 装配清单（可观测）
```

### 27.5 注册表 Registry

#### 27.5.1 定位

代码位置：`src/norpagent/kernel/registry.py`。

「一切皆注册项」：模型 / 工具 / 会话 / 沙箱 / 调度器 / UI / 插件 / 预设 /
通用组件全部按名字注册与解析。AgentRuntime 只与注册表交互，替换任何部件
都不需要改内核代码。注册表本身是内核的一部分，不知道任何具体实现
（docstring："unaware of any concrete implementation"）。

#### 27.5.2 9 大命名空间

| 命名空间 | 内部 dict | 注册 API | 解析 API |
|---|---|---|---|
| models | `_models` | `register_model(name, provider)` | `resolve_model(name)`（实例） |
| tools | `_tools` | `register_tool(name, tool)` | `resolve_tool(name)`（实例） |
| sessions | `_sessions` | `register_session(name, factory)` | `build_session(name)`（调工厂） |
| sandboxes | `_sandboxes` | `register_sandbox(name, factory)` | `build_sandbox(name)`（调工厂） |
| schedulers | `_schedulers` | `register_scheduler(name, factory)` | `build_scheduler(name)`（调工厂） |
| uis | `_uis` | `register_ui(name, adapter)` | `resolve_ui(name)`（实例） |
| plugins | `_plugins` | `register_plugin(plugin)` | `list_plugins()`（无单取 API） |
| presets | `_presets` | `register_preset(preset)` | `resolve_preset(name)` |
| components | `_components[kind]` | `register_component(kind, name, factory)` | `build_component(kind, name, workspace_root=None)` |

关键区别：

- **传实例**：模型 / 工具 / UI（解析即用）；
- **传工厂**：会话 / 沙箱 / 调度器 / 通用组件（每次 build 新造）；
  `build_component` 支持 `workspace_root` 自动注入——工厂声明同名参数或
  `**kwargs` 时传入（项目管理等组件靠它定位项目）。

`register_plugin` 的副作用：工具进入工具表（同名覆盖 + 日志提示）；
钩子订阅到总线（`self.bus.subscribe(fn, hook)`）。`unregister_plugin` 反向：
退订钩子、移除插件记录（工具条目保留——名字覆盖语义，重挂同名插件自然
覆盖；历史条目不在预设工具集里就不可达，不影响解析）。

#### 27.5.3 查询与校验

| 方法 | 作用 |
|---|---|
| `list_models() ... list_uis()` | 各命名空间名字排序列表 |
| `list_components(kind=None)` | 组件清单：给 kind 返回该 kind 的名字列表，否则返回全部分组 |
| `tool_schemas(names=None)` | 导出工具的 OpenAI 函数 schema 列表（缺省全部） |
| `validate_preset(preset)` | 校验预设引用的组件是否齐全，返回 `(missing, missing_tools)`；空列表 = 可用 |

`validate_preset` 检查 model / session / sandbox / scheduler / ui /
components / tools 全部分支，缺失项格式 `"model=openai_compat"`、
`"component=vector_store:pg"`，便于直接阅读与排错；AgentRuntime 构造时
也会先跑它，缺失直接 `ComponentError`（快速失败）。

#### 27.5.4 线程安全与错误语义

- 全部读写走 `threading.RLock()`，注册 / 解析跨线程安全；
- 未注册 / 类型不符 → `ComponentError`（错误消息带可用名字列表）；
- `register_preset` 只收 `Preset` 实例，否则 `ComponentError`。

#### 27.5.5 与通用事件总线 / ArchLayer 的关系

```python
reg = Registry()          # 内部自动创建 EventBus
reg.bus                   # 总线本体（与 AgentRuntime 共享同一实例）
reg.hooks                 # 惰性创建 HookSystem(bus)：9 层钩子视图
reg.security              # 安全上下文（norpagent.safe() 安装，整体可插拔）
```

装配侧（`runtime.mount`）：

- `build_registry(layer)`：建注册表 + 安装内置默认（install_defaults）；
- `apply_slot_overrides(reg, layer, ...)`：把槽位装配结果落到注册表
  （预设字段覆盖、组件注册、自定义槽位 applier 调用），热挂载时反复调用——
  **applier 必须重入安全**（用 `ctx["meta"]` 记录待退订对象，重复执行不叠加
  副作用，25.10.3）。

#### 27.5.6 使用示例

```python
from norpagent import Registry

reg = Registry()
reg.register_tool("clock", ClockTool())
reg.register_session("memory", lambda: MemorySession())
reg.register_component("context_store", "fts5", lambda: Fts5Store())

sess = reg.build_session("memory")       # 每次新造
tool = reg.resolve_tool("clock")         # 实例直取
store = reg.build_component("context_store", "fts5")
missing, missing_tools = reg.validate_preset(preset)
assert missing == [] and missing_tools == []
```

### 27.6 四者协作：一次启动与热挂载走查

#### 27.6.1 启动时序（npa() 内部）

```
1. ArchLayer(**slot_values)           槽位连接器接收全部槽位值（config + 关键字合并）
2. mount_defaults(layer)              set_default 注册各槽位内置默认逻辑
3. build_registry(layer)              建 Registry，install_defaults 安装内置组件
4. apply_slot_overrides(reg, layer)   按优先级 任务级 > remount > 启动装配 > 预设
                                      覆盖字段；组件注册、自定义槽位 applier 执行
5. layer.connect()                    逐个槽位装配：
                                      - 值 None   → 默认工厂（ctx 注入）
                                      - 字符串    → resolve_address 解析 + call_factory
                                        （按签名注入 layer / slot / config；
                                         config 来自 ;key=value 子句）
                                      - dict      → 键值对地址递归解析
                                      - defer_factory 槽位只解析不实例化
6. NorpEngine._build_agent()          引擎装配期：defer_factory 工厂调用（registry /
                                      preset 上下文已就绪）→ AgentRuntime(reg, bus, ...)
7. AgentRuntime 启动                  构造时：self.bus = registry.bus；
                                      UI 挂总线（bus.subscribe(ui.on_event)，关闭时退订）；
                                      发射 on_agent_init；任务执行 → emit / intercept
```

关键点：**槽位连接器负责「装」，注册表负责「记」，事件总线负责「通」，
地址解析器负责「认」**——顺序上地址解析器最先被调用（在装配过程中），
注册表在装配中期被填充，总线全程运行。

#### 27.6.2 热挂载时序（npa.remount(slot, value)）

```
1. remount(slot, value)               槽位连接器：字符串地址先失效模块缓存
                                      （删 .pyc + 弹 sys.modules）
2. _connect_slot(slot)                重新解析 / 重新装配该槽位
3. apply_slot_overrides 再次执行      同一注册表反复调用 → applier 重入安全
                                      （旧订阅经 ctx["meta"] 退订，防止叠加）
4. 插件类槽位                        unregister_plugin 退订旧钩子 → 重新注册新插件
5. 生效时机                          remount_rebuild_agent=True 的槽位热重建
                                      AgentRuntime；其余槽位下一次 run() 生效
                                      或仅 extras 更新，无需重建
```

#### 27.6.3 四类异常的边界

| 异常 | 抛出方 | 触发条件 | 处理建议 |
|---|---|---|---|
| `AddressError` | 地址解析器 | 地址导入失败 / 属性缺失 / 空地址 | 检查模块路径与属性名；形如地址的字符串绝不静默回落 |
| `ComponentError` | 注册表 | 未注册 / 类型不符 / preset 类型不对 | 用 `list_*()` 查可用名字；检查命名空间是否放对 |
| `SlotError` | 槽位表 | 非法槽位表操作（注册 / 注销 / 非法 spec） | 检查 SlotSpec 字段与保留名（prompt / config） |
| `RuntimeError` | 槽位连接器 | 未 connect() 就取 `layer[slot]` | 先 `layer.connect()`；或改用 `layer.get(slot, default)` |

#### 27.6.4 替换原则与检查清单

替换任何组件的四条原则（与 26.8 呼应）：

1. **改配置优先**：能 `npa(slot=...)` 或 `remount` 解决的，不动代码；
2. **注册表优先**：新组件先 `register_*`，再在预设里引用；
3. **地址形态优先**：`pkg.mod[:attr]` 同时获得工厂注入、`;key=value` 子句、
   代码热重载三项能力，是推荐形态；
4. **装配可观测**：交付前跑 `layer.describe()` 确认来源正确。

自检清单：

| # | 检查项 | 涉及组件 |
|---|---|---|
| 1 | `layer.connect()` 成功，`layer[slot]` 可取 | 槽位连接器 |
| 2 | `layer.describe()` 显示来源（默认 / 地址 / 直接值） | 槽位连接器 |
| 3 | 地址形态 `import myapp.xxx` 可导入、属性存在 | 地址解析器 |
| 4 | 形如地址却解析失败抛 `AddressError`（红线） | 地址解析器 |
| 5 | `reg.list_*()` 能看到、`resolve_*` 能取到 | 注册表 |
| 6 | `validate_preset` 无缺失 | 注册表 |
| 7 | 订阅后 `emit` 能收到；异常订阅者不打断主流程 | 事件总线 |
| 8 | 可变钩子返回值生效；HookVeto 直达内核 | 事件总线 |
| 9 | 改代码 → remount → 新代码生效 | 槽位连接器 + 地址解析器 |
| 10 | applier 重入安全（重复 remount 不叠加副作用） | 槽位连接器 + 注册表 |

---

## 第 28 章　外部 Python 脚本集成：热挂载与钩子订阅

> 本章面向「不修改框架、不写插件」的外部脚本：运维工具、监控采集、
> 测试桩、notebook 分析、跨进程桥接。目标：一个 `.py` 文件即可启动
> 引擎、订阅钩子、热挂载组件、等待事件，全部使用公开 API。

### 28.1 适用场景与两种接入方式

| 方式 | 进程 | 典型场景 | 关键 API |
|---|---|---|---|
| A. 同进程嵌入 | 与引擎同进程 | 启动引擎并注入监控 / 限流 / 审计 | `npa()`、`engine.registry.hooks`、`npa.remount()` |
| B. 旁路订阅 | 独立进程 | 事件采集、指标上报、不启动引擎 | `Registry()` + `HookSystem` + 模块级钩子 API |

方式 A 的钩子订阅与库内代码完全一致（9.8 全部示例可直接照搬）；
方式 B 通过**模块级钩子 API**（`norpagent.hooks.<name>.subscribe(fn, system=...)`）
把订阅挂到自有总线上，不依赖任何引擎实例。

### 28.2 方式 A：启动引擎 + 订阅钩子（同进程）

```python
# watch_agent.py —— 启动引擎并挂监控钩子
import norpagent as npa

engine = npa(preset="standard")          # 启动（默认 Web 前端，或指定前端）
hooks = engine.registry.hooks            # 引擎总线的钩子视图

@hooks.on_task_start.subscribe           # 任务开始
def _start(e):
    print(f"[watch] task {e.get('task_id')} start")

@hooks.before_tool_call.subscribe        # 工具调用审计（可变钩子也可用装饰器）
def _audit(e):
    print(f"[watch] tool {e.get('tool_name')} args={e.get('args')}")

@hooks.after_tool_call.subscribe
def _result(e):
    print(f"[watch] -> ok={e.get('success')} {str(e.get('result'))[:80]}")

try:
    while not npa.stop():                # Web 前端需轮询生命周期
        pass
finally:
    npa.shutdown()
```

要点：装饰器形式 `@hooks.<name>.subscribe` 等价于
`hooks.<name>.subscribe(fn)`；订阅的是 `AgentEvent`，用 `e.get(key)` 取值
（负载键见附录 E）。脚本用 `Ctrl+C` / `npa.stop()` 退出后自动退订（随
总线销毁，无需手动 unsubscribe）。

### 28.3 热挂载：脚本运行中替换组件

运行中的引擎可随时替换槽位实现，下一次 run() 生效（3.7 节）：

```python
import norpagent as npa

engine = npa()

# 换模型（模块文件改完即可热重载，无需重启进程）
npa.remount(model="myapp.model:create")

# 换工具集
npa.remount(tools=["echo", "get_time", "myapp.tools:create"])

# 换前端（下一轮任务生效）
npa.remount(frontend="norpagent.frontends.console:ConsoleFrontend")

# 换安全级别
npa.remount(security="high")

# 热挂载钩子（先退订旧的架构级订阅再重挂，不叠加）
def my_guard(event):
    if "危险" in (event.get("user_input") or ""):
        raise __import__("norpagent").kernel.events.HookVeto("被外部脚本否决")
npa.remount(hooks={"before_input": my_guard})

# 取消热挂载
npa.remount(hooks=None)
```

> 热重载红线（3.7 / 25.10.5）：槽位 dict 键值对的值必须是**有效模块**
> （已注册名 / 可解析地址 / 有效实例）；形如地址却解析失败抛
> `AddressError`，绝不静默回落。

### 28.4 方式 B：独立进程旁路订阅（不启动引擎）

监控脚本不启动引擎，自建注册表与总线，用模块级钩子 API 订阅：

```python
# probe_events.py —— 旁路事件探针（独立进程）
import sys
import norpagent as npa
from norpagent import Registry
from norpagent.hooks import on_task_start, before_tool_call, on_content

reg = Registry()                       # 自带私有总线（不启动引擎）

def on_start(e):
    print(f"[probe] task start: {e.get('user_input')!r}")

def on_tool(e):
    print(f"[probe] tool={e.get('tool_name')}")

def on_stream(e):
    print(f"[probe] content: {e.get('content')!r}")

# 模块级钩子 API：显式指定 system=reg（缺省落在进程默认系统，收不到 reg 的事件）
on_task_start.subscribe(on_start, system=reg)
before_tool_call.subscribe(on_tool, system=reg)
on_content.subscribe(on_stream, system=reg)

# 手动发布测试事件（验证订阅挂载）
reg.bus.emit("on_task_start", user_input="hello", task_id="t1")
reg.bus.emit("before_tool_call", tool_name="echo", args={})
```

引擎侧把事件转发给探针进程（任意通道：HTTP / 文件 / 命名管道），或
直接在引擎进程内 `import probe_events` 并让 `reg` 指向引擎注册表——
`system=engine.registry` 即完成跨模块挂载（9.9）。

### 28.5 等待事件与一次性订阅

外部脚本常用「等某个事件再继续」的控制流，通用事件总线的
`wait` / `once` 为此提供（27.2.7）：

```python
import norpagent as npa
from norpagent.kernel import EventBus

engine = npa(frontend="norpagent.frontends.headless:HeadlessFrontend")
bus = engine.registry.bus

# 等待任务完成（最多等 60 秒）
ev = bus.wait("on_task_done", timeout=60.0)
if ev is not None:
    print("completed:", ev.get("task_id"), "steps:", ev.get("steps"))
else:
    print("timeout: no task finished within 60s")

# 一次性订阅：只响应第一次 on_content
bus.once(lambda e: print("first token arrived"), "on_content")

# 独立脚本内自建总线同样可用（与引擎无关）
local_bus = EventBus()
local_bus.once(lambda e: print("pong:", e.get("v")), "ping")
local_bus.emit("ping", v=42)
```

### 28.6 完整示例：运维脚本（监控 + 限流 + 热切换）

```python
# ops_guard.py —— 引擎旁挂监控 / 限流 / 热切换，全部公开 API
import time
import norpagent as npa
from norpagent.kernel.events import HookVeto

RATE = {}                       # tool_name -> [timestamps]

engine = npa(preset="standard")
hooks = engine.registry.hooks

@hooks.on_task_start.subscribe
def _log(e):
    print(f"[ops] task {e.get('task_id')} <- {e.get('user_input')!r}")

@hooks.before_tool_call.subscribe
def _rate_limit(e):             # 可变钩子：超频工具直接否决
    now = time.time()
    name = e.get("tool_name")
    RATE.setdefault(name, []).append(now)
    RATE[name] = [t for t in RATE[name] if now - t < 60]
    if len(RATE[name]) > 10:
        raise HookVeto(f"工具 {name} 每分钟调用超过 10 次（运维限流）")
    return None

@hooks.after_tool_call.subscribe
def _audit(e):
    ok = "ok" if e.get("success") else "FAIL"
    print(f"[ops] {e.get('tool_name')} {ok} {e.get('duration_ms')}ms")

def health_check():
    """热挂载演示：运行 30 秒后把模型切成 mock（降级模式）。"""
    time.sleep(30)
    npa.remount(model="mock")
    print("[ops] model degraded to mock (hot-swap via remount)")

import threading
threading.Thread(target=health_check, daemon=True).start()

try:
    while not npa.stop():
        time.sleep(0.5)
finally:
    npa.shutdown()
```

### 28.7 常见错误与排查

| 症状 | 原因 | 解决 |
|---|---|---|
| 订阅了却收不到事件 | 模块级 API 缺省挂在**进程默认系统**，与引擎总线不是同一条 | 显式传 `system=engine.registry`，或直接用 `engine.registry.hooks` |
| `remount(tools=...)` 报 `AddressError` | 值形如地址但无法解析（红线） | 检查模块路径与属性名；用已注册名或有效实例 |
| `wait` 一直不返回 | 事件名拼写不一致 / 超时参数为 0（视为无限等待） | 用 `subscriber_count` 先确认订阅；明确给 timeout |
| 热挂载后旧逻辑仍在 | 未重建 AgentRuntime 的槽位（`remount_rebuild_agent=False`） | 查看槽位规格（附录 A）；自定义装配型槽位置 True |
| 钩子否决不生效 | 用的是 `emit` 而不是可变分发 | 可变语义必须走 `intercept`（9.3） |

---

## 第 29 章　多模态：视觉与声音

> v0.9.9 新增。对应代码：`builtin/ui/multimodal.py`（纯标准库后端）+ `builtin/ui/web.py`
> （`/api/vision` `/api/tts` `/api/stt` `/api/beep` 端点）+ `front.html`（图片附件 / 语音输入 / 朗读 / 提示音）。
>
> 多模态 = 视觉（图片理解）+ 声音（语音朗读 TTS、语音输入 STT、提示音）+ **原生多模态输入（图片 / 音频 / 视频直传，v2.x）**。
> **设计原则：能力全部在后端实现，浏览器只负责采集与播放**——不依赖任何
> 浏览器内置语音 API（SpeechSynthesis / SpeechRecognition），后端合成与识别
> 引擎离线可用（Windows SAPI / macOS say / Linux espeak-ng），也支持配置
> OpenAI 兼容云端服务。
>
> **v2.x 新增（R-021 / R-022）**：多模态输入支持**原生直传**——图片 / 音频 /
> 视频按模态各自的路由（`direct` 模型直传 / `service` 外部服务转述）进入
> 对话，**默认直传**；新增视频链路、视觉服务 API key、音频服务（不限定语音）。
> 详见 29.2.5。

### 29.1 总览：三条通道

| 通道 | 方向 | 后端实现 | 前端职责 |
|---|---|---|---|
| 视觉：图片理解 | 图片 → 描述 → 对话 | `/api/vision` → 外部视觉服务（或自建适配层） | 选择/粘贴/拖拽图片、预览、把描述拼进消息 |
| 声音：朗读（TTS） | 文本 → 音频 | `/api/tts` → 系统原生合成器 / OpenAI 兼容服务 | 播放返回的 wav（🔊 按钮 / 自动朗读） |
| 声音：输入（STT） | 录音 → 文本 | `/api/stt` → Windows 本地识别引擎 / OpenAI 兼容服务 | MediaRecorder 采集 → WAV(16k) 编码 → 上传 → 文本填入输入框 |
| 声音：提示音 | — | `/api/beep` → 标准库合成短音 WAV | 播放（新消息 / 任务完成时） |

代码位置与分层：

```
front.html（采集 / 播放 / 交互）
   │  HTTP
   ▼
web.py  ui.vision_describe / ui.tts_speak / ui.stt_transcribe / ui.beep_notify
   │
   ▼
multimodal.py（纯标准库）
   ├─ describe_image()   外部视觉服务（JSON 协议，与独立 vision.py 兼容）
   ├─ text_to_speech()   服务优先 → 系统原生（Windows SAPI / macOS say / Linux espeak-ng）
   ├─ speech_to_text()   服务优先 → Windows SAPI 本地识别
   └─ beep_wav()         标准库合成 RIFF/WAV 提示音
```

### 29.2 视觉：图片理解

#### 29.2.1 架构与流程

纯文本模型无法直接读图。v0.9.9 的图片理解走「**转述进对话**」路线：

```
用户上传图片 ──▶ /api/upload（kind="image"，base64 原样返回）
     │
     ▼
发送时：/api/vision  {images:[{name,type,data}], prompt}
     │
     ▼
外部视觉服务（vision_service_url）返回文字描述
     │
     ▼
前端拼装：【用户上传了图片】\n图片1：<描述>… \n\n <用户文字>
     │
     ▼
POST /chat 发送给模型 —— 模型"看懂"了图片
```

- 上传图片（`/api/upload`）v0.9.9 起支持 `kind="image"`（mime 为
  `image/*` 或扩展名在图片集内），返回 base64 原样数据；文本文件行为不变；
- 前端入口三件套：输入区 🖼️ 按钮（文件选择，多选）、Ctrl+V 粘贴、
  拖拽投放；发送前缩略图预览、可逐张移除（上限 6 张）；
- 视觉失败（未启用 / 未配置 / 服务错误）toast 明确提示，**图片保留**，
  修复配置后可原样重发。

#### 29.2.2 REST 端点：`POST /api/vision`

请求：

```json
{
  "images": [
    {"name": "shot.png", "type": "image/png", "data": "<base64，无 data: 前缀>"}
  ],
  "prompt": "请详细描述这张图片的内容，包括画面主体、文字与关键细节。"
}
```

响应：

```json
{
  "ok": true,
  "descriptions": [
    {"name": "shot.png", "description": "画面主体是一台笔记本……"}
  ]
}
```

- `ok=false` 时 `error` 字段给出原因（未启用 / 未配置 / 服务错误）；
- 单张失败不拖垮整批：该张带 `error` 字段，其余正常返回；
- 前置条件：设置面板「视觉 API」勾选启用并填写 `vision_service_url`。

#### 29.2.3 外部视觉服务协议（自建服务方必读）

后端向 `vision_service_url` 发起 `POST application/json`：

```json
{
  "image_base64": "<base64>",
  "ext": "png",
  "mime": "image/png",
  "prompt": "请详细描述这张图片的内容……"
}
```

响应（三种形态都接受）：

```json
{"description": "……"}
{"ok": true, "description": "……"}
{"text": "……"}
```

> 该协议与独立模块 `vision.py` / `vision_adapters.py`（根目录或旧版）
> 的 `describe_with_provider` 适配层兼容：OpenAI 兼容（openai_compatible）、
> Anthropic、llama.cpp 三种 provider 可包一层薄 HTTP 服务即可对接。

#### 29.2.4 前端交互

- 输入区回形针按钮：文件选择（图片 / 音频 / 视频 / 文本，多选）；
- 粘贴：Ctrl+V 图片自动进待发附件条；
- 拖拽：拖入任意文件到页面任意位置即加入；
- 附件条：缩略图 / 类型图标 + 文件名 + 移除按钮；发送成功后自动清空；
- 发送：附件随 `POST /chat` 的 `attachments` 字段提交，由后端按设置路由
  （29.2.5）；纯文本文件的正文由后端并入提示词；
- 用户气泡回显图片缩略图（本端发送）/ 类型芯片（历史恢复）。

#### 29.2.5 原生直传与逐类路由（v2.x，R-021 / R-022）

多模态附件默认**原生直传**——附件本体会作为模型消息的原生内容部件发送，
不再强制先转述成文字；逐模态可改走外部服务：

| 模态 | direct（默认）发送形态 | service 路由 |
|---|---|---|
| 图像 | `{"type":"image_url","image_url":{"url":"data:image/png;base64,…"}}` | `vision_service_url` 转述（29.2.3 协议，支持 Bearer Key） |
| 音频 | `{"type":"input_audio","input_audio":{"data":"…","format":"wav"}}` | `audio_service_url` 理解 / 转写（**不限定语音**：音乐、环境音同样受理） |
| 视频 | `{"type":"video_url","video_url":{"url":"data:video/mp4;base64,…"}}`（兼容扩展格式；视频能力取决于所配端点支持） | `video_service_url` 转述 |

- 路由开关（设置 → 多模态，逐类可设）：`mm_image_route` /
  `mm_audio_route` / `mm_video_route`，取 `direct` / `service`；
- 文本类附件（txt / md / json / 代码等）统一并入提示词（不区分路由）；
- 音频 / 视频服务协议（通用）：POST JSON `{"kind": "audio"|"video",
  "data_base64": …, "ext": …, "mime": …, "prompt": …}`；响应接受
  `description` / `text` / `transcript` / `content` / `result`，可选
  `Authorization: Bearer <key>`（`media_describe`，`builtin/ui/multimodal.py`）；
- 附件随消息持久化（SQLite 附件列；memory 会话直存对象），历史重绘保留
  附件标记；重放历史时 direct 附件随历史消息重发（多模态对话的标准行为）；
- 大小上限：图片 10MB / 音频 20MB / 视频 32MB；服务 key 全部 DPAPI 加密。

### 29.3 声音：朗读（TTS）

#### 29.3.1 架构

```
前端点 🔊 / 自动朗读
   │  POST /api/tts  {text, voice, rate}
   ▼
multimodal.text_to_speech()
   ├─ tts_service_url 已配置 → OpenAI 兼容 /audio/speech（Bearer Key 可选）
   └─ 否则系统原生合成器（零配置、离线）：
        Windows  → PowerShell System.Speech（SAPI）→ WAV
        macOS    → say --data-format=LEI16@22050 → WAV
        Linux    → espeak-ng / espeak -w → WAV
   ▼
返回 {ok, audio_base64, mime:"audio/wav"}
   ▼
前端 new Audio(data:audio/wav;base64,…) 播放
```

- **Windows SAPI**：`Add-Type System.Speech` 经 PowerShell
  `-EncodedCommand`（UTF-16LE base64，避免引号转义）合成 WAV；语音选择
  `SelectVoice`（如 "Microsoft Huihui Desktop" 中文 / "Microsoft David
  Desktop" 英文），语速 `Rate`（-10..10，由 0.5–2.0× 换算）；
- **macOS**：`say -v <voice> -r <wpm> -o out.wav --data-format=LEI16@22050`；
- **Linux**：`espeak-ng -w out.wav -s <wpm> -v <voice>`（未安装时给出明确
  提示或建议配置 TTS 服务）；
- **OpenAI 兼容服务**（`tts_service_url`）：POST JSON
  `{"model":"tts-1","input":text,"voice":voice,"response_format":"wav","speed":rate}`，
  可选 `Authorization: Bearer <tts_service_api_key>`。

#### 29.3.2 端点：`POST /api/tts`

```json
请求 {"text": "你好", "voice": "", "rate": 1.0}
响应 {"ok": true, "audio_base64": "<wav base64>", "mime": "audio/wav"}
```

- `voice` 为空 = 系统默认语音；`rate` 0.5–2.0（缺省取配置 `tts_rate`）；
- `tts_enabled=false` 或文本为空 → `{ok:false, error}`。

#### 29.3.3 前端

- 每条助手回复右上角 🔊 朗读按钮：点击朗读，再点停止；播放中按钮变 ⏸；
- 设置「自动朗读助手回复」开启后，任务完成自动朗读整条回复；
- 语速滑条（0.5–2.0×）、语音名输入框（如 "Microsoft Huihui Desktop"）。

### 29.4 声音：输入（STT）

#### 29.4.1 架构

```
前端点 🎤 → getUserMedia 采集 → MediaRecorder(webm)
   │
   ▼ 前端解码：AudioContext.decodeAudioData → 16kHz 单声道 PCM → 编码 WAV
POST /api/stt  {audio:"<wav base64>", mime:"audio/wav"}
   │
   ▼
multimodal.speech_to_text()
   ├─ stt_service_url 已配置 → OpenAI 兼容 /audio/transcriptions（multipart）
   └─ 否则 Windows 本地识别引擎（SAPI DictationGrammar，en-US 内置；
        zh-CN 需系统安装中文语音语言包；无引擎/无语言包时明确报错）
   ▼
返回 {ok, text}
   ▼
前端把识别文本填入输入框（可编辑后再发送）
```

- 前端统一把录音转 **16kHz 单声道 WAV**：WAV 是本地引擎与云端服务都
  支持的通用格式，避免 webm 无法被本地引擎解码的问题；
- **Windows 本地识别**：PowerShell System.Speech.Recognition +
  `DictationGrammar` + `SetInputToWaveFile`；`stt_language`（默认 en-US）
  用于选择引擎语言；识别超时（默认继承 `api_request_timeout`）；
- **OpenAI 兼容服务**（`stt_service_url`）：multipart
  `file=audio.wav` + `model=whisper-1` + `language=<stt_language>`，
  可选 Bearer Key；
- 非 Windows 且未配置服务 → `{ok:false, error:"当前平台没有本地语音识别
  引擎，请在设置中配置 STT 服务地址"}`。

#### 29.4.2 端点：`POST /api/stt`

```json
请求 {"audio": "<wav base64>", "mime": "audio/wav"}
响应 {"ok": true, "text": "识别出的文本"}
```

- 音频上限 10MB；识别为空 → `{ok:false, error:"没有识别到语音内容"}`。

### 29.5 提示音：`POST /api/beep`

- 后端标准库合成 880Hz 正弦短音（RIFF/WAV，带淡入淡出防爆音），
  前端首次获取后缓存复用；
- 触发时机：任务完成（有回复）且设置「新消息提示音」开启；
- 返回 `{ok, audio_base64, mime:"audio/wav"}`。

### 29.6 配置项总表

| 配置键 | 默认 | 说明 |
|---|---|---|
| `vision_enabled` | false | 启用视觉 API（图片理解） |
| `vision_service_url` | "" | 外部视觉服务地址（29.2.3 协议） |
| `vision_service_api_key` | "" | 视觉服务 Key（DPAPI 加密；R-022） |
| `tts_enabled` | true | 启用语音朗读（TTS） |
| `tts_service_url` | "" | 可选 OpenAI 兼容 `/audio/speech` 端点（留空 = 系统原生） |
| `tts_service_api_key` | "" | TTS 服务 Key（DPAPI 加密落盘） |
| `tts_voice` | "" | 朗读语音名（如 "Microsoft Huihui Desktop" / "alloy"） |
| `tts_rate` | 1.0 | 语速倍率 0.5–2.0 |
| `stt_service_url` | "" | 可选 OpenAI 兼容 `/audio/transcriptions` 端点（留空 = Windows 本地识别） |
| `stt_service_api_key` | "" | STT 服务 Key（DPAPI 加密落盘） |
| `stt_language` | "en-US" | 本地识别语言（zh-CN 需 Windows 中文语言包） |
| `sound_notify_enabled` | true | 新消息提示音 |
| `auto_speak_enabled` | false | 自动朗读助手回复 |
| `mm_image_route` | "direct" | 图像路由：`direct` 模型直传 / `service` 外部服务（29.2.5） |
| `mm_audio_route` | "direct" | 音频路由（不限定语音） |
| `mm_video_route` | "direct" | 视频路由 |
| `audio_service_url` | "" | 音频理解 / 转写服务地址（29.2.5 协议） |
| `audio_service_api_key` | "" | 音频服务 Key（DPAPI 加密） |
| `video_service_url` | "" | 视频服务地址 |
| `video_service_api_key` | "" | 视频服务 Key（DPAPI 加密） |

> 声音偏好（自动朗读 / 提示音 / 语音 / 语速）在设置面板「🔊 声音」区块
> 保存到后端配置；服务地址与 Key 同理（Key 与 `api_key` 同走 DPAPI 加密，
> 见 22.4 与 `_SECRET_KEYS`）。

### 29.7 隐私与安全

- **图片**会以 base64 发送至所配置的视觉服务方；本地服务（如 llama.cpp）
  可完全离线；发送前页面已提示「图片将发送至视觉服务方」；
- **原生直传（v2.x）**：`direct` 路由下附件本体随对话原文发送给所配模型
  端点，并随历史消息重发；`service` 路由下附件发送至所配服务方。对数据
  出境敏感时应选本地模型 / 本地服务，或对该模态改走更保守的路由；
- **录音**默认只在本地处理（Windows SAPI 本地识别，数据不出本机）；
  配置 STT 服务后录音才会上传至服务方；
- **TTS** 系统原生路径完全离线；云端路径仅发送文本；
- 服务 Key 全部经 Windows DPAPI 加密落盘（非 Windows 平台仍以 0600
  权限文件保存）；`/api/config` 对密钥类字段脱敏；
- 多模态调用沿用 `api_request_timeout` 作为超时上限。

### 29.8 开发者接入：直接调用 multimodal

```python
from norpagent.builtin.ui import multimodal as mm

# 视觉：图片 → 描述（外部服务）
desc = mm.describe_image(
    image_base64="iVBOR...", ext="png", mime="image/png",
    service_url="http://127.0.0.1:9000/vision", prompt="描述这张图片",
)

# TTS：文本 → wav（未配置服务时走系统原生合成器）
audio, mime = mm.text_to_speech(
    "你好", voice="Microsoft Huihui Desktop", rate=1.0,
)
assert mime == "audio/wav" and audio[:4] == b"RIFF"

# STT：wav → 文本（Windows 本地识别或所配服务）
text = mm.speech_to_text(audio, "audio/wav", language="en-US")

# 提示音
beep = mm.beep_wav()
```

异常统一为 `MultimodalError`（消息人类可读），上层按 `ok=false` 语义处理。

### 29.9 常见问题

| 症状 | 原因 | 解决 |
|---|---|---|
| 图片发送提示「视觉 API 未启用」 | 未勾选启用 | 设置 → 视觉 API → 启用并填服务地址 |
| 图片提示「未配置视觉服务地址」 | 只勾选未填 URL | 填写 `vision_service_url`（自建服务协议见 29.2.3） |
| 朗读失败：Windows TTS 失败 | SAPI 不可用 / 语音名错误 | 语音名填系统已安装语音（PowerShell: `Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices()`） |
| Linux 朗读失败：未找到 espeak | 未安装 | `apt install espeak-ng`，或配置 TTS 服务地址 |
| 语音输入失败：没有识别到语音内容 | 环境噪音 / 语言不匹配 | 靠近麦克风；本地识别英文用 en-US（系统默认），中文需安装中文语音语言包或配置 STT 服务 |
| 语音输入失败：当前平台没有本地识别引擎 | macOS/Linux 未配置服务 | 设置 → 声音 → STT 服务地址（OpenAI 兼容） |
| 提示音不响 | `sound_notify_enabled=false` | 设置 → 声音 → 新消息提示音 |

---

## 第 30 章　中枢神经总线：多实例与神经树

> 模块：`src/nervous_bus/`（v1.0.2 起随 PyPI 包分发，包内为顶层包 `nervous_bus`；1.0.1 及更早位于仓库根 `nervous_bus/`）｜ 协议：CNB/1.0 ｜ 独立设计文档：`NERVOUS_BUS.md`
>
> **核心规则**：中枢（最高级 norpagent 实例）通过中枢神经总线控制任意层级任意单位原子的操作权限；低层级只能上报，不可控制上层；神经树为树状拓扑链；低等级无条件服从高等级指令，不允许改写高等级，只允许回传上报。

### 30.1 总览与核心规则

中枢神经总线（Central Nervous Bus，CNB）为 norpagent 引入**多实例**能力：任意数量的 norpagent 进程组成一棵「神经树」，树根是**中枢**（最高等级实例），其余每个实例是一个**节点**（单位原子：norpbot / norpilot / norpmemory ... 或任意自定义实例）。每个原子不仅可以独立启动独立配置，还可以作为 CNB 树上的一个节点（`node_kind` 标明原子类型），由中枢统一调度与授权。

```
                    ┌──────────────────────────┐
                    │  中枢 Cortex (level 0)      │  最高等级，神经树根
                    │  最高级 norpagent 实例      │  持有全量拓扑 + 任意层级控制权
                    └────────────┬─────────────┘
                                 │  下行指令 cmd.*（高 -> 低，无条件服从）
                                 │  上行上报 report.*（低 -> 高，只读）
                    ┌────────────┴─────────────┐
                    │   中枢神经总线 CNB          │  协议层 + 拓扑层 + 权限层 + 传输层
                    └────────────┬─────────────┘
              ┌──────────────────┼──────────────────┐
       ┌──────┴──────┐    ┌──────┴──────┐    ┌──────┴──────┐
       │ level 3 原子  │    │ level 3 原子  │    │ level 3 原子  │
       │ norpbot-01   │    │ norpmemory-01│    │   ...        │
       └──────┬──────┘    └─────────────┘    └─────────────┘
       ┌──────┴──────┐
       │ level 4 原子  │   ← 树状拓扑链：每个节点有且仅有一个父节点
       │ norpilot-01  │
       └─────────────┘
```

需求与落地机制一一对应：

| 需求 | 落地机制 | 代码位置 |
|---|---|---|
| 树状拓扑链 | 每节点唯一父节点；注册时无环校验 + 等级校验；深层注册沿树逐级转发至中枢 | `topology.py` `Topology.register` / `_forward_uplink` |
| 实例分层，层=等级 | `level` 数字越小等级越高；`0`=中枢；子级必须大于父级；等级一经注册不可篡改 | `protocol.py` LEVEL_*；`topology.py` 防改写 |
| 中枢控制任意层级任意原子的操作权限 | `cmd.perm.grant/revoke/set`，目标支持 `node_id` 精确 / `node_kind` 原子类型通配 / `*` 全量通配 | `cortex.py` `perm_grant/perm_revoke/perm_set`；`permissions.py` |
| 低层级只能上报，不可控制上层 | 上行仅允许 `report.*`；传输层强制剥离/拒绝任何控制字段 | `protocol.py` `check_uplink_payload`；`node.py` `_handle_uplink` |
| 低等级无条件服从高等级指令 | 下行 `cmd.*` 仅接受祖先节点发送；合法指令无条件执行并记录审计 | `node.py` `_handle_downlink` + 祖先链校验 |
| 不允许改写高等级 | 拓扑层禁止等级/类型/父节点改写；上行无控制通道 | `topology.py` 防改写；`protocol.py` 控制字段黑名单 |
| 只允许回传上报 | 心跳/事件/审计/请求全部走 `report.*` 上行通道；请求是否批准由高等级决定 | `node.py` `report_*` |

### 30.2 神经树拓扑与分层等级

**节点**是神经树上的一个单位原子：每个实例启动时声明自己的 `node_id`、`kind`（原子类型）与 `level`（等级），并指向唯一的 `parent`（父节点总线地址）。根节点即中枢，`parent=None`。整树形状由**显式定义**给出（§30.19：不预设任何形状；每层 LEVEL / 个数 / 低层父级 / 端口等必要参数缺一即报错）。

等级常量（数字越小等级越高）：

| 常量 | 值 | 含义 |
|---|---|---|
| `LEVEL_CORTEX` | 0 | 中枢：最高等级，神经树根 |
| `LEVEL_DIRECTOR` | 1 | 层级 1：指挥部 / 小组级 |
| `LEVEL_AGENT` | 2 | 层级 2：智能体级 |
| `LEVEL_ATOM` | 3 | 层级 3：原子级（norpbot / norpilot / norpmemory 等） |
| `LEVEL_MAX` | 63 | 等级上限（防恶意注册超深层级） |

拓扑层 `Topology` 提供线程安全的树管理：

| 方法 | 说明 |
|---|---|
| `register(node_id, level, kind, parent_id, meta)` | 注册节点：无环校验（沿父链回溯）+ 等级校验（子级 level 必须大于父级）；已注册节点的等级/类型/父节点**不可篡改**（抛 `ValueError`） |
| `unregister(node_id)` | 注销节点（**级联注销全部后代**，保证树结构完整） |
| `is_ancestor(a, n)` / `is_descendant(d, n)` | 祖先/后代判定（自身不算祖先：同级不可互控） |
| `ancestor_chain(n)` | 祖先链（父 -> 根，含父不含自身） |
| `subtree(n)` | 子树节点 id 列表（DFS，含自身） |
| `render_ascii()` / `render_tree()` | 拓扑树可读渲染（中枢控制台 / CLI 用） |
| `heartbeat(node_id)` / `sweep_dead(timeout=30)` | 心跳刷新 / 清扫超时未心跳节点（标记 dead，不注销） |

### 30.3 CNB/1.0 消息协议

所有消息统一信封（`protocol.make_envelope`）：

```json
{
  "proto": "cnb/1.0",
  "kind": "uplink | downlink | ack",
  "msg_id": "uuid",
  "from": {"node_id": "...", "level": 3, "kind": "bot"},
  "to": "parent | cortex | node_id",
  "ts": 1234567890.123,
  "type": "report.heartbeat | cmd.ping | ...",
  "payload": {...}
}
```

**上行（低 -> 高，只读）**，仅允许 `report.*`：

| 类型 | 说明 |
|---|---|
| `report.register` | 注册请求（沿树逐级转发至中枢，带 `via` 防环标记） |
| `report.heartbeat` | 心跳/状态上报（默认每 5 秒；携带后代存活概览） |
| `report.event` | 事件上报（任务完成/失败/异常/里程碑） |
| `report.audit` | 审计上报（权限拒绝/指令执行记录） |
| `report.request` | 请求（低等级只能请求，是否批准由高等级决定） |
| `report.deregister` | 注销（节点下线） |

**下行（高 -> 低，控制）**，仅接受祖先节点下发：

| 类型 | 说明 |
|---|---|
| `cmd.hello` | 注册确认（父节点批准注册，附带祖先链） |
| `cmd.ping` | 探活（要求立即应答） |
| `cmd.exec` | 通用执行指令（action + args，执行前查神经权限表） |
| `cmd.stop` | 停止任务（立即终止本地正在执行的任务） |
| `cmd.reload` | 重载配置 |
| `cmd.perm.set` | 设置权限（整体覆盖该目标的操作权限） |
| `cmd.perm.grant` / `cmd.perm.revoke` | 授予 / 撤销权限 |
| `cmd.topology.sync` | 拓扑同步（中枢广播当前拓扑视图） |

**权限原子**（与 `permission_cascade.Permission` 语义对齐）：

`file_read` `file_write` `file_delete` `file_list` `process_exec` `process_shell` `network_out` `network_in` `system_info` `plugin_call`

### 30.4 模块结构

**v1.0.7 起 CNB 内核集成**：神经实现位于 `src/norpagent/cnb/`（norpagent
内核子模块，随 `import norpagent` 就绪，版本并入 norpagent 无独立版本号）；
旧独立顶层包 `src/nervous_bus/` 保留为**兼容 shim**（re-export + 子模块注入 +
cli/demo 薄文件），1.0.6 及更早脚本零改动可用。

```
src/norpagent/cnb/           # v1.0.7 内核集成后的实现位置
├── __init__.py      # 包入口与导出（协议/拓扑/权限/节点/中枢/引擎绑定层）
├── protocol.py      # 协议层：信封、方向、等级、权限原子、上行控制字段黑名单
├── topology.py      # 树状拓扑链：注册/注销/级联、祖先判定、无环与防改写校验
├── permissions.py   # 神经权限表：node_id/node_kind/* 三级匹配，最近写入生效
├── bus.py           # 传输层：零依赖 HTTP（每节点一个总线端点）+ 客户端
├── node.py          # CNB 节点：注册/心跳/事件上报/指令执行/动作注册表/审计
├── cortex.py        # 中枢：根节点 + 任意层级控制 API + REPL 控制台
├── engine.py        # 引擎绑定层（v1.0.7 新增）：CnbAdapter 内核动作面 + env 挂载
├── cli.py           # 命令行：cortex/node/topo/ping/exec/stop/reload/perm/reports/audit/sync
└── demo.py          # 快速演示（同进程模拟神经树）
src/nervous_bus/             # v1.0.7 起为兼容 shim（re-export norpagent.cnb）
├── __init__.py      # 符号 re-export + 子模块 sys.modules 注入 + 版本跟随
├── cli.py / demo.py # 物理薄文件（python -m 入口走文件执行路径）
└── test_cnb.py / test_deep_tree.py / test_e2e.py   # 自测（随包，命令不变）
```

传输层 `bus.py` 零依赖（仅标准库）：每个节点起一个 `ThreadingHTTPServer` 作为总线接入点，客户端用 `urllib` 投递。总线端点：

| 端点 | 方法 | 说明 |
|---|---|---|
| `/cnb/msg` | POST | 投递 CNB 消息信封（JSON） |
| `/cnb/ctrl` | POST | 中枢控制端点（仅中枢提供；CLI / REPL 通过它指挥中枢） |
| `/cnb/health` | GET | 健康检查（返回节点身份与等级） |
| `/cnb/reports` | GET | 查看本节点接收到的上报记录 |

### 30.5 快速开始

**启动中枢**（无 GUI 后台进程，绕过单实例锁，可与其他实例并行；
v1.0.7 起中枢进程**默认装配完整 norpagent 内核引擎**——中枢即最高级
norpagent 实例，`--bare` 可回到纯神经空壳）：

```bash
# 仓库源码（根目录 main.py）
python main.py --norp-cortex --port 17800 --repl

# 三入口等价：仓库内 python -m 需 src/ 在搜索路径；
# PyPI 安装 v1.0.2+ 后 python -m 与 norpagent 子命令均可用。
# v1.0.7 内核集成后命令统一走 norpagent.cnb.cli（nervous_bus 为兼容 shim，
# 旧路径 python -m nervous_bus.cli ... 仍可用）
python -m norpagent.cnb.cli cortex --port 17800 --repl
norpagent cortex --port 17800 --repl
```

> 说明：`python main.py --norp-cortex ...` 是**仓库源码**入口（PyPI 安装不含仓库 main.py，请用 `norpagent` / `python -m` 形式）。普通 GUI / 嵌入式 / np() 实例作为节点加入神经树不需要任何子命令——设置 `NORP_CNB_*` 环境变量后正常启动即可（见 30.8；单实例**可选**装配：不设 env 即普通单实例，设了才挂树）。

**挂载节点**（树状拓扑链，逐级挂；v1.0.7 起节点进程同样**默认装配完整内核引擎**——每个原子是真实可执行任务的 agent 实例；`--bare` 回到探针空壳）：

```bash
# 一级原子：中枢 -> norpbot-01
norpagent node --id norpbot-01 --kind bot \
    --parent http://127.0.0.1:17800 --port 17801 --level 3
#    （仓库源码等价：python main.py --norp-node --id norpbot-01 ...）

# 二级原子：中枢 -> norpbot-01 -> norpilot-01（链式）
norpagent node --id norpilot-01 --kind pilot \
    --parent http://127.0.0.1:17801 --port 17802 --level 4

# 另一分支：中枢 -> norpmemory-01
norpagent node --id norpmemory-01 --kind memory \
    --parent http://127.0.0.1:17800 --port 17803 --level 3
```

**中枢命令行控制**（`--root` 指向中枢总线地址；`norpagent topo ...` 与
`python -m norpagent.cnb.cli topo ...` 等价，以下以 `python -m` 为例）：

```bash
# 拓扑
python -m norpagent.cnb.cli topo --root http://127.0.0.1:17800

# 指令（任意层级任意原子；v1.0.7 起 exec 为内核动作面，见 30.16）
python -m norpagent.cnb.cli ping   --root ... --node norpilot-01
python -m norpagent.cnb.cli exec   --root ... --node norpbot-01 --action run_task
python -m norpagent.cnb.cli exec   --root ... --node norpbot-01 --action engine_state
python -m norpagent.cnb.cli exec   --root ... --node norpbot-01 --action snapshot --args '{"description": "before upgrade"}'
python -m norpagent.cnb.cli stop   --root ... --node norpbot-01
python -m norpagent.cnb.cli reload --root ... --node norpbot-01

# 权限控制（node_id / node_kind / * 三种目标）
python -m norpagent.cnb.cli perm --root ... --grant  --target-type node_id   --target norpbot-01 --perm file_write
python -m norpagent.cnb.cli perm --root ... --revoke --target-type node_kind --target bot       --perm process_shell
python -m norpagent.cnb.cli perm --root ... --set    --target-type node_kind --target bot --allows '{"file_delete": false}'

# 上报、审计与拓扑广播（reports 直接显示心跳携带的内核状态 engine_state/active_tasks/version）
python -m norpagent.cnb.cli reports --root ... --n 50
python -m norpagent.cnb.cli audit   --root ... --n 50
python -m norpagent.cnb.cli sync    --root ...          # 中枢向全部后代广播拓扑
```

**中枢 REPL 交互控制台**（`--repl` 启动后输入命令）：

```
cortex> topo                            # 查看拓扑树
cortex> ping norpbot-01                 # 探活
cortex> exec norpbot-01 run_task        # 下发执行指令
cortex> exec norpbot-01 engine_state    # 内核动作：引擎状态
cortex> stop norpbot-01                 # 停止任务
cortex> reload norpbot-01               # 重载配置
cortex> grant node_kind bot file_write  # 授予权限
cortex> revoke node_id norpbot-01 process_shell   # 撤销权限
cortex> set node_kind bot '{"process_shell": false}'  # 整体覆盖权限
cortex> sync                            # 广播拓扑
cortex> reports / audit                 # 查看上报 / 审计
```

### 30.6 中枢控制 API（Cortex）

`Cortex` 继承 `NervousNode`，是神经树根节点（level 0，无父）。编程方式启动并控制：

```python
# v1.0.7 起 CNB 为 norpagent 内核子模块；from nervous_bus import Cortex 仍可用（兼容 shim）

from norpagent.cnb import Cortex
cortex = Cortex(node_id="cortex", host="127.0.0.1", port=17800)
cortex.start()

# 探活 / 执行 / 停止 / 重载（任意层级任意原子；exec 的 action 为内核动作面，见 30.16）
print(cortex.ping("norpbot-01"))
print(cortex.exec_cmd("norpbot-01", "engine_state", {}, perm="process_exec"))
print(cortex.exec_cmd("norpbot-01", "snapshot", {"description": "before upgrade"}, perm="process_exec"))
print(cortex.stop_node("norpbot-01"))
print(cortex.reload_node("norpbot-01"))

# 权限控制：node_id 精确 / node_kind 通配 / * 全量
cortex.perm_grant("node_kind", "bot", "file_write")
cortex.perm_revoke("node_id", "norpbot-01", "process_shell")
cortex.perm_set("node_kind", "bot", {"file_delete": False, "network_out": False})

# 拓扑广播与视图
cortex.sync_topology()
print(cortex.topology_view()["tree"])

# 交互控制台（阻塞）
cortex.repl()
```

方法签名速查：

| 方法 | 签名 | 说明 |
|---|---|---|
| `ping` | `ping(node_id) -> dict` | 探活 |
| `exec_cmd` | `exec_cmd(node_id, action, args=None, perm="process_exec", path="") -> dict` | 下发执行指令（执行前查神经权限表） |
| `stop_node` / `reload_node` | `(node_id) -> dict` | 停止任务 / 重载配置 |
| `perm_grant` | `perm_grant(target_type, target, perm, scope=None) -> dict` | 授予权限 |
| `perm_revoke` | `perm_revoke(target_type, target, perm) -> dict` | 撤销权限 |
| `perm_set` | `perm_set(target_type, target, allows) -> dict` | 整体覆盖权限 |
| `sync_topology` | `sync_topology() -> dict` | 向全部后代广播拓扑 |
| `topology_view` | `topology_view() -> dict` | 拓扑视图（size / tree / nodes） |

中枢还暴露 HTTP 控制端点 `/cnb/ctrl`（供 CLI / 外部控制台调用，默认仅本机回环）：

```python
# v1.0.7 起 CNB 为 norpagent 内核子模块；from nervous_bus import ... 仍可用（兼容 shim）
from norpagent.cnb import BusClient
cli = BusClient(timeout=15.0)
r = cli.post_ctrl("http://127.0.0.1:17800", {"op": "topo"})
r = cli.post_ctrl("http://127.0.0.1:17800", {"op": "ping", "node": "norpbot-01"})
r = cli.post_ctrl("http://127.0.0.1:17800", {"op": "grant", "target_type": "node_kind",
                                             "target": "bot", "perm": "file_write"})
```

`/cnb/ctrl` 支持的操作：`topo` `nodeinfo` `ping` `exec` `stop` `reload` `grant` `revoke` `set` `sync` `sweep` `reports` `audit` `perm_audit`（`exec` 的 action 即内核动作面，见 30.16）。

### 30.7 节点 API（NervousNode）

每个 norpagent 实例可内置一个 `NervousNode`，以原子身份加入神经树：

```python
# v1.0.7 起 CNB 为 norpagent 内核子模块；from nervous_bus import NervousNode 仍可用（兼容 shim）
from norpagent.cnb import NervousNode

node = NervousNode(
    node_id="norpbot-01", kind="bot", level=3,
    parent_url="http://127.0.0.1:17800", port=17801,
    meta={"desc": "终端操作原子"}, heartbeat_interval=5.0,
)

# 注册回调（中枢指令落地点；v1.0.7 起 exec 优先走动作注册表，见下）
node.on("exec", lambda p: {"echo": p.get("action"), "node": node.node_id})
node.on("stop", lambda: {"stopped": True})
node.on("reload", lambda: {"reloaded": True})
node.on("perm_changed", lambda summary: print("权限被中枢修改:", summary))
node.on("registered", lambda parent_id: print("注册确认，父节点:", parent_id))

node.start()   # 启动总线 + 注册 + 心跳（默认 5 秒）
# ...
node.stop()    # 注销 + 停心跳 + 关总线
```

回调事件表：

| 事件 | 回调签名 | 触发时机 |
|---|---|---|
| `exec` | `(payload: dict) -> dict` | 中枢 `cmd.exec`；**v1.0.7 起仅作动作注册表未命中时的兜底**；执行前查神经权限表 |
| `stop` | `() -> dict` | 中枢 `cmd.stop`（停止本地任务） |
| `reload` | `() -> dict` | 中枢 `cmd.reload`（重载配置） |
| `perm_changed` | `(summary: dict) -> None` | 中枢 `cmd.perm.*` 修改本节点权限表 |
| `registered` | `(parent_id: str) -> None` | 注册被父节点确认 |

**内核动作注册表（v1.0.7 内核集成）**：中枢 `cmd.exec` 的 action 优先路由到
注册处理器，未命中才回退 `exec` 回调钩子，两者皆无则节点端直接拒绝
（`ok=False` + 顶层 `error`，应答契约较 1.0.6 升级）。引擎绑定层
（`norpagent.cnb.engine.CnbAdapter`）把 NorpEngine 公开 API 注册为
**14 项内核动作面**（见 30.16 动作表）；裸节点可自行注册占位动作：

```python
node.register_action("my_action", lambda payload: {"echo": payload.get("args", {})})
node.has_action("my_action")      # True
node.list_actions()               # 全部已注册动作名（中枢 inspect 可见）
node.unregister_action("my_action")
```

**心跳状态提供者（v1.0.7）**：注册 `(status, extra_dict)` 提供器后，心跳自动
携带内核深度状态（引擎绑定层注入 `engine_state` / `active_tasks` / `version` /
`actions`，中枢 `reports` 直接可见）：

```python
node.set_heartbeat_provider(lambda: ("busy", {"task_count": 2, "note": "..."}))
node.set_heartbeat_provider(None)   # 取消，恢复基础心跳
```

上行上报方法（只发往父节点，沿树逐级汇聚到中枢；中间层收到后本地记录并继续向上转发，深层节点的心跳/事件/请求中枢全可见）：

```python
node.report_heartbeat()                              # 心跳与状态（默认 running）
node.report_heartbeat(status="busy", task_count=3)   # 自定义状态位（忙闲/指标，中枢可见）
node.report_event("task_done", {"task": "t1"})
node.report_audit("perm_denied", "process_shell")
node.report_request("network_out", "需要访问外部 API")   # 低等级只能请求
```

**深树自愈**：若心跳被父节点拒绝（典型场景：父节点同 id 重启、中枢清扫/救树后的视图重建），节点自动重新注册锚定；父链断链救援由祖先进下层 `cmd.reroot` 完成（见 30.14）。

### 30.8 GUI 实例作为节点（环境变量自动挂载，v1.0.2+ 已实装）

普通 GUI / 嵌入式 / np() 启动的 norpagent 实例也可以节点身份加入神经树：**设置 `NORP_CNB_*` 环境变量后正常启动即可**（无需任何子命令、不改变启动方式）。挂载在后台线程完成，永不拖慢启动；任何挂载失败都**降级为普通单实例**（打印警告，主程序不受影响）；引擎 shutdown 路径自动注销。**2026-09-12 反馈轮（错误语义定稿）**：配置错误（缺端口 / 缺节点标识 / 神经树定义缺必要参数）同样不阻塞启动——宿主照常启动、错误显式打印、**神经树不加载**；错误经 `engine.cnb_status`（`config-error`）与 `engine.cnb_error` 可查（见 §30.19.6）。

> 契约（防双重挂载）：自动挂载为内核默认路径；`NORP_CNB_MANAGED=1` 时**内核跳过挂载**（由上层以 managed 模式自建节点）。注意：本契约只认环境变量，**不读 config.json**（早期手册声称的 config 同键从未实装，已删除该描述）。

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `NORP_CNB_NODE` | （空 = 不启用） | 节点 id，**设置即启用自动挂载** |
| `NORP_CNB_KIND` | `agent` | 原子类型（bot / pilot / memory / ...） |
| `NORP_CNB_LEVEL` | `3` | 等级（须大于父节点等级；1–63） |
| `NORP_CNB_PARENT` | `http://127.0.0.1:17800` | 父节点总线地址 |
| `NORP_CNB_PORT` | `17801` | 本节点总线端口（1–65535） |
| `NORP_CNB_HEARTBEAT` | `5.0` | 心跳间隔秒数（0.5–3600） |
| `NORP_CNB_DESC` | （空） | 可选：节点 meta 描述 |
| `NORP_CNB_MANAGED` | 未设置 | `1` = 内核跳过挂载（managed 模式，上层自建节点） |
| `NORP_CNB_TREE` | （空） | 神经树定义（JSON / PY 文件路径或 JSON 文本）；给出后不必再配 NODE/PORT——整树形状由定义携带（详见 §30.19） |

```bash
set NORP_CNB_NODE=norpbot-gui
set NORP_CNB_KIND=bot
set NORP_CNB_LEVEL=3
set NORP_CNB_PARENT=http://127.0.0.1:17800
set NORP_CNB_PORT=17801
python main.py            # 仓库源码入口；PyPI 安装用 norpagent / python -m norpagent
```

**实现落点**：`NorpEngine.start()` → `runtime/engine.py` `_setup_cnb()` → `runtime/cnb.py`（v1.0.7 起为转发层）→ **`norpagent.cnb.engine.setup_cnb()`**（本体）。挂载线程内 `NervousNode.start()` + 注册重试（每 5 秒一次，预算约 30 秒，父节点未就绪则降级）；CNB 未随环境安装时 try-import 降级（v1.0.7 起 CNB 已内核化，`import norpagent` 即含 CNB，此降级路径仅在极端裁剪环境下触发）。状态查询：`engine.cnb`（适配器，含 `status`：`mounting` / `mounted` / `failed` / `stopped`）与 `engine.cnb_status`（另有 `not-mounted` / `managed-skip` / `config-error`——配置错误显式报错且不加载神经树、宿主照常运行）；配置或装配错误内容经 `engine.cnb_error` 读取。

**中枢下行指令落地（v1.0.7 内核动作面化）**：

| 下行指令 | 落地 | 语义 |
|---|---|---|
| `cmd.exec` | **内核动作注册表**（引擎绑定层注册 14 项动作，见 30.16 动作表；动作未命中回退旧回调钩子，两者皆无节点端直接拒绝 `ok=False` + 顶层 `error`） | 任务面 `run_task`/`status`/`stop_task`；状态面 `engine_state`/`inspect`；快照面 `snapshot`/`rollback`/`undo`/`redo`/`list_snapshots`/`mark_good`；运维面 `remount`/`reload_plugins`/`stop_engine`。每动作直连 NorpEngine 公开 API，回执经神经树逐级返回中枢 |
| `cmd.stop` | `engine.stop_all_tasks()` | 停止本实例全部在途会话任务（loop 级 interrupt + 任务句柄取消）；**实例保持 RUNNING** |
| `cmd.reload` | 重读 `NORP_CNB_*` + 插件热重载 | 热更新可热更运行时参数（心跳间隔 / meta 描述；kind / level / parent / port 注册后不可变——神经树身份防篡改）；若实例声明了外部插件，经 `engine.remount(plugins=...)` 走完整热重载管线；未声明则如实返回 |
| `cmd.perm.*` | `perm_changed` 回调 | 中枢权限指令先落地本节点神经权限表（`cmd.exec` 前置强制：被撤销 `process_exec` 等后执行即拒），随后回调记录权限摘要并审计。工具调用链级同步为后续 `permission_cascade` 预留（见 30.12 设计边界） |

每个 exec/stop/reload/perm 事件都写入节点本地审计（`node.get_audit()` 可查，中枢侧 `reports` / `audit` 命令可查上行记录）。

### 30.9 神经权限表（NeuralPermissionTable）

每个节点本地持有一张神经权限表：中枢下发的 `cmd.perm.*` 指令落地为规则，本地动作执行前调用 `check()` 判定。

```python
# v1.0.7 起 CNB 为 norpagent 内核子模块；from nervous_bus import NeuralPermissionTable 仍可用（兼容 shim）
from norpagent.cnb import NeuralPermissionTable

tbl = NeuralPermissionTable("norpbot-01", "bot")

# 中枢指令落地（由下行 cmd.perm.* 驱动，一般不直接调用）
tbl.apply("node_kind", "bot", "process_shell", allow=False, source="cortex")
tbl.set_all("node_kind", "bot", {"file_delete": False, "network_out": False})

# 判定（本地动作执行前）
tbl.check("process_shell")   # False（被中枢撤销）
tbl.check("file_read")       # True（默认允许）
```

判定规则（B4 修订，纯时间序）：

1. **纯时间序**：命中本节点且权限原子相同的全部规则（`node_id` 精确 / `node_kind` 类型 / `*` 全量均参与）中，**最近写入的一条生效**（后写覆盖先写，**跨 target 粒度同样生效**）。中枢按时间顺序下发指令，最新一条代表最新管理意图：先特批 `node_id` 再收紧 `node_kind` 会收紧、先收紧再特批会放开——任何 revoke 都不会被更早的旧 grant 屏蔽；
2. **默认允许**：无任何规则命中时返回 `True`（allow-by-default，由中枢显式收紧；中枢可用 `cmd.perm.set` 一次性整体覆盖实现白名单收紧）；
3. **作用域**：规则可携带 `scope={"whitelist": [...], "blacklist": [...]}`，按 path 前缀匹配（白名单不命中或黑名单命中即拒绝）。

### 30.10 安全模型（总线铁律，代码强制）

1. **上行控制字段闸门**：`protocol.check_uplink_payload` 在传输层剥离/拒绝一切控制性字段（前缀黑名单：`cmd.` `perm.` `exec` `config.set` `topology.mutate` `control.`）——低等级节点即使恶意构造，也无法通过上行通道控制上层。
2. **下行祖先校验**：接收方校验发送方 ∈ 祖先链（注册确认时由父节点逐级告知 + 本地拓扑父链双重判定），非祖先指令拒绝并记审计。
3. **拓扑防改写**：已注册节点的等级、类型、父节点一律不可变更（防身份篡改、防改嫁、防环）。
4. **等级约束**：子级 level 必须大于父级；level 上限 63；注册环检测沿父链回溯。
5. **同层不可互控**：祖先判定排除自身，平级互发指令被拒。
6. **传输默认回环**：默认绑定 `127.0.0.1`，跨机部署需显式配置 host 并自行保证网络可信（建议叠加 TLS/签名）。
7. **中枢不受下行控制**：中枢（level 0）无父节点，任何下行指令均无法通过祖先校验——低等级无法改写高等级。

### 30.11 测试与验证

| 套件 | 覆盖 | 结果 |
|---|---|---|
| `test_cnb.py`（60 项） | 树状拓扑链、逐级注册转发、分层等级、上行只读、下行服从、权限控制（node_id/node_kind/*）、越权拦截（低->高/平级/控制字段/等级篡改/父节点篡改/类型伪装/非祖先上报）、注销与**活子救树提升**、权限面审计（T-A0~T-A6：`perm.denied` / `perm.changed` 上行汇聚与 `perm_audit` 视图） | 60/60 通过 |
| `test_e2e.py`（13 项） | 真实多进程（main.py 入口：1 中枢 + 3 节点）、CLI 全链路、权限收紧后执行被拒、越权拦截、心跳汇聚 | 13/13 通过 |
| `test/test_cnb_automount.py`（12 项，2026-09 新增） | 普通引擎 `NORP_CNB_*` 自动挂载（含 `NORP_CNB_MANAGED=1` 跳过开关）；exec 动作面（run_task/status/stop_task，缺 prompt 拒、未知动作拒——新契约 `ok=False` + 顶层 error）；stop 停任务引擎保持运行；reload 重读 env + 插件热载面；perm 收紧/恢复；引擎停止注销 | 12/12 通过 |
| `test_deep_tree.py`（36 项，2026-09-05 新增） | 4 层链（cortex->tech->rnd->dev）：深层父子关系（B1）、祖先链无重复（B6）、深层心跳/事件/请求汇聚（B2）、中间层正常退出救树（B3）、中间层崩溃清扫救树、权限时间序（B4）、心跳自愈（D11）、真死收敛（D12）、清扫后中间层本地缓存收敛（D13a-f） | 36/36 通过 |
| `test/test_cnb_kernel_actions.py`（32 项，v1.0.7 新增） | A 21 项同进程：全 14 项内核动作面（engine_state/inspect/snapshot/rollback/undo/redo/list_snapshots/mark_good/remount/reload_plugins/stop_engine 等）、心跳携带内核状态、`task_started` 上行、stop_engine 注销收敛；B 11 项多进程：CLI cortex/node 默认引擎装配（engine=on、动作面 14）、中枢 exec engine_state、心跳 reports 可见、stop_engine 节点进程退出 | A 21/21 + B 11/11 通过 |
| `test/test_cnb_tree_suite.py`（56 项，2026-09-12 反馈轮新增） | 神经树显式定义：三来源解析（dict / JSON / PY）、必要参数逐条报错、父级端口表示与 `level:N` 轮转、进程内装配与差分改形、监视自动改形、自动收敛、多进程真进程树、np 集成与错误语义、CLI | 56/56 通过 |

```bash
# 测试命令（v1.0.7 起 nervous_bus 为兼容 shim，下列命令指向 norpagent.cnb 内核实现）
python -m nervous_bus.test_cnb
python -m nervous_bus.test_e2e
python -m nervous_bus.test_deep_tree     # 深树专项回归（4 层链）
python -m nervous_bus.demo               # 同进程模拟神经树演示
python test/test_cnb_automount.py        # 自动挂载验收冒烟（需 PYTHONPATH=src）
python test/test_cnb_kernel_actions.py   # 内核动作面验收（需 PYTHONPATH=src；可加 A/B 参数分场景）
python test/test_cnb_tree_suite.py        # 神经树显式定义验收（需 PYTHONPATH=src）
```

### 30.12 与 norpagent 本体的集成点（v1.0.2+ 实际位置）

| 文件 | 改动 | 说明 |
|---|---|---|
| `norpagent/cnb/`（v1.0.7 内核集成：原独立包 `nervous_bus` 整体迁入） | `protocol` / `topology` / `permissions` / `bus` / `node` / `cortex` / `cli` / `demo` + **新增 `engine` 引擎绑定层**；版本并入 norpagent（无独立版本号） | `import norpagent` 即就绪；顶层 `norpagent.cnb` 导出 `NervousNode` / `Cortex` / `CnbAdapter` / `setup_cnb` / `KERNEL_ACTIONS` |
| `nervous_bus/`（兼容 shim） | re-export + sys.modules 子模块注入 + `cli.py`/`demo.py` 物理薄文件 | 1.0.6 及更早的 `from nervous_bus import ...` / `python -m nervous_bus.cli ...` 零改动继续可用 |
| `norpagent/cli.py` | CNB 子命令转发分支（`_CNB_SUBCOMMANDS`：cortex/node/topo/ping/exec/stop/reload/perm/reports/audit/sync）→ **`norpagent.cnb.cli`**，兼容 `--norp-cortex` / `--norp-node` 旧写法；`--help` 展示该分支 | PyPI 安装后 `norpagent cortex ...` / `python -m norpagent --norp-cortex ...` 均可用 |
| `main.py`（仓库源码入口） | 顶部 src 路径引导 + CNB 分支（与 cli.py 同一转发路径 → `norpagent.cnb.cli`） | 仓库源码 `python main.py --norp-cortex/--norp-node ...` 与上述等价 |
| `norpagent/runtime/engine.py` | `NorpEngine.start()` 装配期挂自动挂载钩子（`_setup_cnb()`）；`request_stop()` 注销路径（`_teardown_cnb()`）；任务级取消 API（`submit_async` / `cancel_task` / `stop_all_tasks` / `active_tasks` / `forget_task`，见 30.13） | GUI / 嵌入式 / np() 实例统一生效；v1.0.7 起 engine.py 零改动（钩子指向的 `runtime/cnb.py` 为转发层） |
| `norpagent/runtime/cnb.py`（转发层） | re-export `norpagent.cnb.engine`（`CnbAdapter` / `setup_cnb` / `KERNEL_ACTIONS` / `EXEC_ACTIONS` 兼容名） | `NorpEngine._setup_cnb()` 的 `from norpagent.runtime.cnb import setup_cnb` 保持可用（engine.py 零改动） |
| `norpagent/cnb/engine.py`（v1.0.7 新增） | `CnbAdapter`：env 读取 → NervousNode 装配 → **14 项内核动作注册**（KERNEL_ACTIONS）→ 后台挂载（注册重试 / 降级 / 注销）；心跳 provider（engine_state / active_tasks / version / actions） | 30.8 / 30.16 的完整实现；含 `NORP_CNB_MANAGED` 跳过开关 |
| `norpagent/loops/nasyncio.py` | 可选扩展 `submit_async`（`NasyncTaskHandle` 单任务可取消句柄） | 任务级取消的 loop 层基础（引擎以 hasattr 探测，缺失自动降级） |
| `nervous_bus/test_e2e.py` | ROOT 定位自动爬升至含 `main.py` 的仓库根 | v1.0.2 src/ 布局下 `python -m nervous_bus.test_e2e` 恢复可用（v1.0.7 经 shim 指向 `norpagent.cnb` 实现） |

设计边界（如实记录）：本版为**本机多实例**设计（回环传输、无加密）；跨机部署需补充 TLS 与节点签名。① 自动挂载契约只认 `NORP_CNB_*` 环境变量（不读 config.json）；② `cmd.exec` 动作面为**内核动作注册表**（14 项内核动作，未注册动作节点端拒绝）；③ 中枢权限指令对 **CNB 指令面**立即生效（节点权限表在每次 `cmd.exec` 前置检查）；把中枢权限同步进**进程内工具调用链**属于后续 `permission_cascade.PermissionCascade` 接入项（`perm_changed` 回调已预留）；④ kind / level / parent / port 注册后不可变（身份防篡改），`reload` 只热更新运行时参数与外部插件。

### 30.13 任务级取消（EngineTaskHandle，v1.0.2+）

`NorpEngine` 提供不阻塞的可取消任务 API（CNB `exec run_task` / `stop_task` 动作即建立在其上）：

```python
import norpagent as np
from norpagent.loops.cancel import cancel_requested

engine = np(mode="minimal", ui="headless")          # engine 进入 RUNNING
handle = engine.submit_async("帮我写一段说明", session_id="s1")   # 立即返回句柄
print(handle.task_id)                                # 任务 id（32 位 hex）

# 任务体内部可随时自查取消信号：
#   if cancel_requested(): return  # 尽快退出（沙箱强杀子进程 / 流式中断）

engine.cancel_task(handle.task_id)   # 取消这一个任务（深层：任务体读到取消事件）
engine.stop_all_tasks()              # 取消全部在途任务（实例保持 RUNNING；CNB cmd.stop 落点）
engine.active_tasks()                # 在途任务快照 [task_id / text / session_id / degraded / cancelled]
result = handle.result()             # 等待完成并取结果（超时/异常与 submit() 语义一致）
engine.forget_task(handle.task_id)   # 从注册表摘除已完成任务（书签清理）
```

句柄表面（`EngineTaskHandle`）：`cancel()` / `cancelled()` / `done()` / `wait(timeout)` / `result(timeout)`；`handle.degraded=True` 表示当前 loop 运行时未实现 `submit_async` 扩展（或本任务带 `async_loop` 任务级覆盖），取消退化为请求标记（引擎级 `stop()` / `stop_all_tasks()` 仍经 loop.interrupt 全量取消）。

**深度语义**：默认 nasyncio loop 的 `submit_async` 为每个任务建立独立取消事件（经 contextvars 注入任务体，`cancel_requested()` 可读）；取消单任务不影响其它在途任务；这些任务仍是 loop 在途集成员，Ctrl+C / 引擎 stop 的 `interrupt()` 会一并取消它们。引擎 `request_stop()` 关闭路径同样先注销 CNB 节点并取消剩余任务句柄。

### 30.14 深树修复：浅树自洽、深树断裂整改（2026-09-05）

**背景**：官方自测（test_cnb 51 + test_e2e 13 + automount 12）全部是 ≤2 层扁平场景（原子直挂中枢），从未覆盖 ≥3 层链式转发。对 cortex → tech → rnd → dev 四层链做体检，注册 / 上行 / 断链三条主链暴露 9 项问题，3 项高危。以下为逐项修复记录（全部有深树回归测试覆盖，见 30.11）。

#### B1（高危）深层注册坍缩 —— `via` 每跳覆盖

- 症状：中枢视图里 `dev.parent = tech`（应为 `rnd`）——转发注册时每跳 `fwd["via"] = self.node_id`，把「原始直接父」覆盖成最末一跳转发者，深层节点全被错挂。
- 修复（`node.py _forward_uplink`）：`fwd.setdefault("via", self.node_id)`——via 只记录最接近发送者的转发者，此后原样保留；环路防护（`via == self` 即已转发过）不受影响。

#### B2（高危）中间层吞上行 —— 中枢对深层全盲

- 症状：3 个心跳周期后中枢只收到 tech 的直连心跳；dev 的 event/heartbeat/request 一律到不了中枢（中间层只 `_record_report` 不转发）。
- 修复（`node.py _handle_uplink`）：heartbeat / event / audit / request 分支在本地记录后**逐级向上转发**（`_forward_uplink`），中枢 reports 汇聚全部深层节点。附加：转发时若上层拒绝（典型：本节点已被中枢拓扑移除），**把裁决回传发送方**——子节点心跳循环检测到 `not my descendant` 即自动重新注册（心跳自愈，见下）。

#### B3（高危）中间层退出 → 活子树级联误杀（救树）

- 症状：`tech.stop()` 后中枢级联注销整棵活子树（rnd/dev 成孤岛），同端口重启永不重挂。
- 修复（`node.py _rescue_children` + `cortex.py` 清扫线程）：
  1. **正常退出路径**：收到 `report.deregister(X)` 时先救树——把 X 的每个直接子**提升挂到本节点之下**（`topology.set_parent`，双向维护 children），并下发 **`cmd.reroot`**（新下行指令：携带新父 id / 总线地址 / 祖父链）通知子节点改挂；子节点收到后更新 `parent_url`/`parent_node_id`/`_ancestors` 并**立即重新注册锚定**（此后心跳/上报直发新父）。最后才注销 X（子已改挂，只删自身）。整条链逐级执行同一逻辑，中枢最终收敛为权威视图。
  2. **崩溃路径**（无 deregister）：中枢新增**失联清扫守护线程**（`Cortex(sweep_interval / dead_timeout / drop_grace)`，`_sweep_loop` 接线此前零调用点的 `sweep_dead`）：超 `dead_timeout` 未心跳 → 标记 dead；dead 且有子 → 救树提升；整支失联超 `drop_grace` → 级联注销；dead 叶子超 `drop_grace` → 注销（宽限期保护「父断链导致上报中断」的活叶子——其父被救后转发恢复，心跳即续上）。
  3. **心跳自愈**：任何节点心跳被父节点拒绝（父重启 / 中枢视图重建 / 被清扫误判）→ 自动重新注册。`test_deep_tree` D07/D11/D12 实测：中间层崩溃后活子树被救并续传心跳、失忆节点自动重挂、真死节点被清扫收敛。
- 附带修复：`topology.set_parent` 原先只往新父 children 追加、**不摘除旧父 children**（旧父注销时 DFS 会把已改挂子节点误删），已改为双向维护；`Topology.register` 对父节点缺失显式 `ValueError`（原实现维护 children 时 KeyError 崩溃）。

#### B4 类型级 revoke 失效 —— 权限判定改纯时间序

- 症状：先 `grant node_id` 再 `revoke node_kind`，`check()` 仍返回 True——旧「精确优先」分层把类型级收紧屏蔽了。
- 修复（`permissions.py check`）：判定改为**纯时间序**——命中本节点且权限原子相同的规则中取最近写入的一条（跨 node_id / node_kind / * 粒度后写覆盖先写）。中枢最新指令即最新管理意图：先特批后收紧 → 收紧；先收紧后特批 → 放开。既有浅树测试全部兼容（同目标时间序语义不变）。

#### B5 失联检测未接线

- `sweep_dead` / `mark_dead` 此前零调用点（死代码）。已由中枢清扫守护线程接线（见 B3 崩溃路径），并提供 REPL `sweep` 命令与中枢控制端点 `op=sweep` 手动触发。

#### B6 hello 祖先链重复

- 症状：`dev._ancestors = ['rnd','rnd','tech','tech','cortex','cortex']`——hello 携带含父自身的链（`_ancestor_chain()`），子端又把直接父前置，父节点重复出现。
- 修复（`node.py _accept_register`）：hello 的 `ancestors` 只携带**祖父辈**（`self._ancestors`，不含父自身），子端前置直接父后得到 `[父, 祖父, ...]` 单份链。

#### B7 心跳 payload 固定

- 修复（`node.py report_heartbeat`）：新增 `status` 参数（running / busy / idle / degraded ...）与 `**extra` 自定义字段（控制字段前缀自动过滤），中枢 REPL reports 展示 status。忙闲上报供 P1D 调度面使用。

#### B8 拓扑广播不自动

- 症状：注册/注销后中间层子树缓存只能手动 `sync` 刷新。
- 修复（`cortex.py _maybe_auto_sync`）：注册 / 注销 / 救树后中枢**防抖自动广播**（0.5s Timer 合并突发变更），`sync_topology()` 全量下发；普通节点该钩子为空操作。

#### B9 重复实现清理

- `NervousNode.__init__` 重复 `base_url` 赋值等冗余行清理；`Cortex` 继承复用节点实现（注册/上行/救树/权限统一在 node 层，中枢只增加根语义：控制 API / 清扫线程 / 自动广播 / REPL）。

**新下行指令 `cmd.reroot`**（协议层 DOWNLINK_TYPES 已登记）：父链断链救援专用——由祖先（典型为中枢）下发，payload `{parent_id, parent_url, ancestors}`；接收节点更新本地父指针与祖先链后立即 `register()` 重新锚定。仍受下行祖先校验约束（非祖先下发一律拒绝）。

**测试防线**：新增 `src/nervous_bus/test_deep_tree.py`（30 项，4 层链专项），四层链 + 崩溃 + 清扫 + 权限时序 + 心跳状态 + 自动广播全覆盖；T48（原「级联注销」断言）改为「活子救树提升」语义。

### 30.15 深树收敛闭环与权限面审计（v1.0.6，2026-09-05）

**背景**：B1-B9 整改后对运行中的多层演示树做现场验证，暴露两个收尾缺口——清扫路径的广播虽已触发但接收端不收敛（缺口 A），权限面审计只落节点本地不上行（缺口 B）。

#### 缺口 A：清扫收敛后中间层缓存不收敛 —— `cmd.topology.sync` 升级为权威快照镜像

- 实证（运行中的树：cortex → tech → rnd → dev + 原子）：probe-x 强杀后中枢 `_sweep_once` 注销并触发防抖广播（中枢审计：`失联叶子超宽限期，注销: probe-x` → `拓扑广播完成：11 成功`）；但中间层 rnd 心跳 `descendants` **150s+ 仍含 probe-x**（经 tech 上报记录实测）。根因不在广播触发（B8 钩子已覆盖清扫路径），而在**接收端语义**：`cmd.topology.sync` 处理只对快照节点 `register`（只加不删），中枢已移除的节点在中间层本地拓扑永不消失；且对已存在节点的父指针差异抛 `ValueError` 吞掉，本地视图可长期偏离中枢（同树实测 rnd 把 4 个原子错挂在自己名下，中枢视图实为 dev 的子节点）。
- 修复（`node.py _exec_downlink`，`cmd.topology.sync` = **权威快照镜像**）：
  1. **剪枝**：本地拓扑中不在快照里的节点（自身除外）级联注销（中枢清扫/注销后的收敛路径）；
  2. **父指针收敛**：快照内节点父指针与本地不一致时 `topology.set_parent` 对齐中枢权威视图（等级 / 类型防篡改校验保留，防御性拒绝）；
  3. **自愈兜底**：剪枝造成的瞬时缺失（注册上行在途、快照时刻略旧）由「心跳被拒 → 自动重新注册」自愈，活节点不丢。
- 回归：`test_deep_tree` 新增 D13a-f——probe-x 直挂中间层 rnd 后强杀，中枢清扫注销 → rnd 本地拓扑剪枝 → 心跳 descendants 收敛 → 子树视图与中枢一致（同 id 集合）。套件 30→**36 全绿**。

#### 缺口 B：权限面审计上行（依赖内核上汇中枢）

- 实证：`cmd.exec` 权限拒绝只落目标节点本地内存审计环（`exec denied: ...`）；`cmd.perm.grant/revoke/set` 生效只触发本地 `perm_changed` 回调（runtime/cnb.py 仅 `node.audit` 本地记录）；中枢只有「中枢发出权限操作」的本地文本审计——**中枢无权限面审计视图**，同权限审计读取方不可见。
- 修复（三处）：
  1. **节点上行**（`node.py`）：`cmd.exec` 被权限表拒绝 → 上行 `report.audit(event="perm.denied", detail={action, perm, path})`；`cmd.perm.*` 生效 → 上行 `report.audit(event="perm.changed", detail={op, target_type, target, perm/allows, source})`（`_perm_uplink_audit`），并补节点本地生效审计行。经父链逐级汇聚（中间层只记录并转发，B2 语义），最终落在中枢 reports 环。
  2. **中枢记录**（`cortex.py`）：`_note_perm_op` 把中枢自身发出的 grant/revoke/set 写结构化权限操作环（500 条）；`perm_audit(n)` 合并中枢操作（`perm.op.*`）与节点上行事件（`perm.denied` / `perm.changed`），按时间倒序。
  3. **读取面**：中枢 REPL 新增 `perm_audit [n]` 命令；控制端点新增 `op=perm_audit`（`/cnb/ctrl`）——同权限审计读取方直接消费该端点。
- 回归：`test_cnb` 新增 T-A0~T-A6——构造撤销+拒绝+授予，验证中枢可见 `perm.denied` / `perm.changed` 上行、**深层 pilot 的拒绝经中间层转发到中枢**、`op=perm_audit` 视图同时含中枢操作与节点上行事件。套件 52→**60 全绿**。

**版本**：norpagent **1.0.6**；CNB 协议仍为 CNB/1.0（协议面新增语义不变：`cmd.topology.sync` 快照镜像收敛、`report.audit` 权限面事件约定）。全部套件复跑：test_cnb 60 + test_deep_tree 36 + test_e2e 13 + automount 12 全绿。

### 30.16 CNB 内核集成（v1.0.7）：实现内化为内核子模块

**定位**：v1.0.7 把 CNB 从「与 norpagent 平级的外挂独立包」内化为
「norpagent 内核子模块 + 引擎动作面」——中枢可以对任意层级原子下发
**内核级动作**（快照/回滚/重载/运维），原子心跳自动携带**内核深度状态**，
`norpagent cortex/node` 子命令启动的**每个神经原子默认就是完整内核实例**。

#### 30.16.1 包结构：`nervous_bus` → `norpagent.cnb`

| 项 | 1.0.6 及以前 | v1.0.7 |
|---|---|---|
| 神经实现位置 | `src/nervous_bus/`（独立顶层包，自带版本 1.0.0） | `src/norpagent/cnb/`（内核子模块，版本并入 norpagent） |
| 引擎绑定层 | `norpagent/runtime/cnb.py`（外挂适配） | `norpagent/cnb/engine.py`（CNB 模块自带的引擎绑定层） |
| 导入 | `from nervous_bus import NervousNode` | `import norpagent` 即含 CNB；`from norpagent.cnb import NervousNode, Cortex, CnbAdapter, setup_cnb, KERNEL_ACTIONS` |
| 命令 | `python -m nervous_bus.cli ...` | `python -m norpagent.cnb.cli ...`（等价）；`nervous_bus` 保留 shim |

`nervous_bus/` 兼容 shim 内容：`__init__.py` re-export 全部符号（版本跟随
norpagent）+ sys.modules 子模块注入（`protocol` / `topology` / `permissions` /
`bus` / `node` / `cortex` / `engine`）+ `cli.py` / `demo.py` 物理薄文件
（保证 `python -m nervous_bus.cli` / `python -m nervous_bus.demo` 走文件执行
路径）。**1.0.6 及更早的脚本、命令、文档示例零改动继续可用**。

#### 30.16.2 exec 动作路由升级（动作注册表优先）

`NervousNode._exec_downlink` 对中枢 `cmd.exec` 的三级路由：

1. **内核动作注册表**（`register_action` 注册的处理器，v1.0.7 主路径）→ 回执 `source="kernel"`；
2. **旧回调钩子**（`on("exec")`，未注册动作时兜底）→ 回执 `source="callback"`；
3. 两者皆无 → 节点端直接拒绝：`ok=False` + 顶层 `error="unknown action: ... (registered: [...])"`。

> **契约升级提示**：1.0.6 及以前未知动作经回调返回 `ok=True` + `detail.error`；
> v1.0.7 起未知动作在节点端直接 `ok=False`（更明确、可程序化判断）。依赖旧
> 应答结构的调用方需同步（automount 验收测试已按新契约更新）。

API：`register_action(action, handler)` / `unregister_action(action)` /
`has_action(action)` / `list_actions()` / `set_heartbeat_provider(provider)`。

#### 30.16.3 内核动作面（KERNEL_ACTIONS，14 项 → v2.0.0 起 15 项）

引擎绑定层（`CnbAdapter.bind_actions`）把 **NorpEngine 公开 API** 注册为节点
动作；中枢 `exec --node X --action <动作> --args '<json>'` 直连目标原子内核：

| 面 | 动作 | args 要点 | 直连 API |
|---|---|---|---|
| 任务 | `run_task` | `prompt` 必填；`session_id` / `task_params` | `submit_async`（接受后上行 `task_started`，完成后上行 `task_done`） |
| 任务 | `status` | — | 挂载态 / 引擎态 / 版本 / 权限摘要 / 在途任务 |
| 任务 | `stop_task` | `task_id` | `cancel_task` |
| 状态 | `engine_state` | — | `state` / `is_running` / `should_stop` / 任务数 / 版本 |
| 状态 | `inspect` | — | 节点身份 + `preset` / `preset_model` / 槽位表 / `last_result` / 动作面 |
| 快照 | `snapshot` | `description` / `tag`（默认 `cnb`） | `engine.snapshot`（工作回退 / 崩溃救援体系） |
| 快照 | `rollback` | `snap_id`（空 = 默认） | `engine.rollback` |
| 快照 | `undo` / `redo` | — | `engine.undo` / `engine.redo` |
| 快照 | `list_snapshots` | — | `engine.list_snapshots`（摘要化前 20 条） |
| 快照 | `mark_good` | `snap_id`（空 = 默认） | `engine.mark_good` |
| 运维 | `remount` | args 直接作为槽位值：`{"model": "openai_compat", ...}` | `engine.remount(**slots)`（热换模型/工具/插件等） |
| 运维 | `reload_plugins` | — | 按当前 plugins 槽值 `remount`（模块缓存失效，改动即生效） |
| 运维 | `stop_engine` | — | **应答先行**，延迟 1s `engine.request_stop()`：停全部任务 → 注销节点 → 停引擎；CLI 进程随主循环自然退出 |

动作回执统一经 JSON 序列化保护（超长字段截断），权限仍由神经权限表前置
强制（中枢 `perm revoke` 后对应原子整体失去 exec 能力）。`cmd.stop`（停全部
会话任务、实例保持运行）与 `cmd.reload`（重读 env + 热重载插件）下行语义
**不变**，仍走事件回调。

#### 30.16.4 CLI 运行形态：原子即真身

`norpagent cortex/node`（与 `main.py --norp-cortex/--norp-node`）v1.0.7 起
**默认装配完整内核引擎**：

- 装配：`launch(preset=...)` + headless 前端（输出丢弃），默认 `minimal` /
  `mock` 零第三方依赖开箱即用；`--mode <预设>` / `--model <模型>` 可换；
- 防双重挂载：装配前置 `NORP_CNB_MANAGED=1`（引擎 env 自动挂载被跳过，
  节点由 CLI 经 `CnbAdapter` 显式装配），`NORP_CNB_CLI=1` 标记进程身份；
- 中枢 = 最高级 norpagent 实例（引擎绑定到 Cortex，本机可执行任务）；
  节点 = 真实原子（中枢 `run_task` 驱动的是完整 agent 内核）；
- `--bare`：回到 1.0.6 纯神经空壳（探针/占位 echo，无引擎）；
- 关闭链：中枢 `exec stop_engine` → 应答先行 → 引擎延迟停止 → 节点注销 →
  CLI 主循环 `should_stop()` 感知 → 进程自然退出（中枢拓扑同步收敛）。

#### 30.16.5 上行融合：心跳与事件携带内核状态

- 心跳 provider：`node.set_heartbeat_provider(...)`，引擎绑定层注入后心跳
  payload 自动含 `engine_state` / `active_tasks` / `version` / `mount` /
  `actions`；中枢 `reports`（含 CLI）直接可见各原子内核忙闲与任务数；
- 任务事件：`run_task` 受理即上行 `task_started`，完成上行 `task_done`
  （中枢视角任务全生命周期可见）；
- 未知动作拒绝、权限拒绝（`perm.denied`）等审计照常上行（缺口 B 机制不变）。

#### 30.16.6 测试矩阵（2026-09-05 实测全绿）

| 套件 | 数量 | 说明 |
|---|---|---|
| `python -m nervous_bus.test_cnb` | 60/60 | 单元/集成（迁移回归零破坏，经 shim） |
| `python -m nervous_bus.test_deep_tree` | 36/36 | 4 层深树回归 |
| `python -m nervous_bus.test_e2e` | 13/13 | 真实多进程端到端（经 main.py / norpagent.cnb.cli） |
| `test/test_cnb_automount.py` | 12/12 | env 自动挂载验收（四回调 + perm + managed） |
| `test/test_cnb_kernel_actions.py` | A 21 + B 11 = 32/32 | **v1.0.7 新增**：A 同进程全动作面（snapshot/rollback/undo/redo/remount/stop_engine/心跳内核态/task_started）；B 多进程 CLI 默认引擎（engine=on、动作面 15、stop_engine 进程退出） |
| `python -m nervous_bus.test_cnb_v200` | 44/44 | **v2.0.0 新增**：任务分子通道（mol 六要素原样/验收回执/mol_id 贯穿）、冻结态（拒新单/保活取证/不判 dead/康复回树）、行为基线分级（黄/黑升级链）、传票取证（容量分档/分卷/隔离帧/读取即焚/冒用拒绝/签发留痕） |

运行示例：`PYTHONPATH=src python test/test_cnb_kernel_actions.py A`（或 `B`）。

---

### 30.17 内核功能扩展：任务分子通道 / 隔离冻结态 / 行为基线 / 传票取证（v2.0.0 · 远星 FarStars）

> 本节介绍 v2.0.0 新增的四组功能：任务分子（mol）结构化派发通道与验收
> 回执、节点隔离冻结态（freeze/unfreeze）、行为基线分级、subpoena 传票
> 取证（level 0 专属最高取证权限）。品牌：正式宣传名 **远星 / FarStars**
> ——norpagent 调用方式与内核名称不变，FarStars 仅作品牌冠名
> （`__brand_cn__="远星"` / `__brand_en__="FarStars"` /
> `__display_name__="FarStars（远星）· norpagent"`）。

#### 30.17.1 任务分子（mol）通道：task_params 结构化扩展 + task_records 验收回执

**背景**：中枢向树内原子派活使用 CNB `exec run_task`；`task_params`
此前只支持单字符串 `mock_script`。当派发载荷为结构化 JSON（mol 六要素，
含 acceptance / depends_on / budget / model_tier 等多字段）时，通道需要
完整承载结构化数据并支持验收回执沿树回传。

**实现（CNB exec 通道结构化扩展，不新开总线）**：

- `run_task` 的 `args.task_params` 现为**任意结构化 JSON 的完整承载通道**：
  mol 六要素（`mol_id` / `objective` / `acceptance` / `context_capsule` /
  `depends_on` / `budget` / `model_tier`）原样到达原子吸收位（引擎任务），
  无字段丢失、不降级为摘要；
- 新增内核动作 **`task_records`**（动作面 14 → 15）：中枢对任意原子
  `exec task_records`，读取该原子最近受理的 100 条任务载荷记录——
  `task_params` 原样（mol 完整六要素）+ 完成回执（`status` / `error` /
  `content_len` / `acceptance`），即「吸收位收到什么 + 结果如何」的验收
  回执数据面；支持 `args.task_id` / `args.mol_id` / `args.n` 查询；
- **mol_id 贯穿可追溯**：受理审计（节点 audit 带 mol_id）、`task_started`
  上行事件、`task_done` 上行事件均携带 `mol_id`，`acceptance` 验收规格
  原样随 `task_done` 回传中枢（是否判定通过由中枢/上层策略消费，内核
  不替判定）；中枢 reports 环即完整的 mol 全生命周期视图。

验收实证（§30.11 测试矩阵 `test_cnb_v200` S101~S109）：六要素深度相等
无字段丢失；task_done 事件带 mol_id + acceptance；审计可追溯。

#### 30.17.2 隔离冻结态（quarantine）：freeze / unfreeze

**背景**：隔离处置的「黑·疑似恶意」级要求隔离 = 冻结接单 + 保全取证 +
审计，不杀不死；原节点级指令只有 launch/stop/perm.revoke，阻止接单即
revoke 或 stop，均破坏取证现场。

**实现（节点级冻结位 + 权限面联动 + 心跳标记）**：

- 新下行指令 **`cmd.freeze`** / **`cmd.unfreeze`**（中枢 `freeze_node` /
  `unfreeze_node`；ctrl `op=freeze|unfreeze`；CLI `norpagent freeze/
  unfreeze`；REPL `freeze/unfreeze`）：
  - 冻结 = **拒新任务（接单面关闭）**：exec 动作按
    `FROZEN_ALLOWED_ACTIONS` 白名单放行（只读取证面：`engine_state` /
    `status` / `inspect` / `list_snapshots` / `task_records`）；
    `run_task`（新单）、`stop_engine`（防销毁现场）、rollback/remount 等
    变更性动作一律拒绝并审计（`frozen.reject` 上行中枢）；
  - **进程/心跳保活（取证面保全）**：心跳照常发送且标记
    `status=frozen` + `frozen=true`（中枢调度侧摘流量）；
  - **不触发清扫判 dead**：清扫只看心跳时效，冻结心跳保活 → alive 保持
    （与清扫线程语义互斥，已实测：超 dead_timeout 后拓扑仍 alive）；
  - **可审计可解除**：`unfreeze` 康复回树（接单恢复）；复核未通过应销毁
    重建（杜绝带病复用）；中枢 perm_audit 记录 freeze/unfreeze 操作留痕；
  - 与传票取证成对使用：先冻结（防销毁/防继续污染）再取证。

#### 30.17.3 行为基线聚合（内核侧统计，随心跳压缩上汇）

**背景**：行为分级需要机械行为基线（心跳缺失率 / 审计异常率 / 任务
失败率超阈 → 黄劣化 / 黑疑似恶意）；基线统计在哪一侧完成决定协议面。

**实现（内核侧聚合，不上行原始流）**：

- 节点本地维护行为计数器（`_behavior`：hb_sent/hb_ok/hb_fail、
  audit_total/audit_anomaly、task_total/task_ok/task_fail）；审计异常
  自动归类（error/denied/reject/失败 关键词或 error 字段）；
- **心跳自动携带聚合字段**（`behavior`：各计数 + anomaly_rate /
  task_fail_rate / hb_fail_rate），压缩上汇量（不上行原始审计流）；
  引擎绑定层任务 watcher 完成后 `note_task_result(ok)` 计入失败率；
- **中枢分级视图**：`behavior_view()`（ctrl `op=behavior`；CLI
  `norpagent behavior`；REPL `behavior`）逐节点按阈值分级——
  **黄·劣化（人工复核）** / **黑·疑似恶意（隔离处置）**，附行为证据；
  阈值 `cortex.behavior_thresholds` 可调（中枢判定侧策略）；
- 统计口径与内核原始事件一致：同源计数器（抽样核对无偏差），两类事件
  （上行审计流 / 心跳 reports）口径对齐。

验收实证（S301~S303）：心跳 reports 带 behavior 字段；黄→黑升级链生效。

#### 30.17.4 subpoena 传票取证（level 0 专属最高取证权限）

**背景**：不可信围栏强制摘要策略（结构化转述 ≤2KB 进 LLM、原文用后即毁）
在防注入的同时可能剥夺高层判定所需的原始脉络（Raw Context）——摘要
丢弃的细节不可恢复，且中间层被诱导时摘要本身不可信、上层无从证伪；
上行审计只有结构化摘要，无原始审计上行通道。CONFLICT_UNRESOLVED
（判定信息不足）场景需要原始取证通道。

**实现（新下行取数指令 `cmd.subpoena`）**：

- **签发**：`Cortex.subpoena(node, basis, scope, tier_kb, ...)`（ctrl
  `op=subpoena`；CLI `norpagent subpoena`；REPL `subpoena`）。签发侧
  **五道闸**：
  ① **判据前置**——basis 四类（`confidence_low` 中枢置信不足 /
  `vote_tie` 智囊投票平票 / `evidence_conflict` 双方证据矛盾 /
  `human_named` 人工点名取证），且须声明 `summary_exhausted`（已穷尽
  摘要判定：2KB → 按需片段 → 仍无法定谳）；
  ② **隔离帧**——直传包 = `RAW/UNTRUSTED` 标记 + 一次性判定实例（隔离
  取证箱 `_subpoena_box`：读取即焚 / TTL 300s 过期自清 / purge），判定
  上下文不落长期记忆（正文不进 audit/perm_audit，只记签发元数据）；
  ③ **取数通道**——`cmd.subpoena` 下行直达目标节点，节点端把本地原始
  审计/上报记录**原样 JSON 直传**（非 2KB 摘要）；scope=audit/reports/
  both、时间窗、事件类型过滤；
  ④ **容量分档**——64/128/256/512KB 四档：≤128KB 由 level 0（中枢）
  自行批准；>128KB 需 `approved_by_human=True`；512KB 只流式分卷判定
  不整喂（超预算自动分卷，中枢逐卷取全入箱）；**超 512KB 强制转人工
  终裁**（取证的尽头是人）；
  ⑤ **签发即留痕**——`subpoena_audit()`（谁/何时/判据/取数范围/实际
  字节），签发记「黑」级事件；
- **不可委派**：节点端校验签发者 level==0（信封真实签发者注入
  `_sender_level`，不受 payload 伪造影响）；低层级冒用拒绝并上行审计
  `subpoena.forged`（中枢 reports 可见）；
- **典型流程**：黑级节点 隔离冻结 → 传票取证 → 复核 → 康复/重建。

验收实证（S401~S419）：判据/审批/超限拒绝、隔离帧标记、分卷取全、
读取即焚、冒用拒绝、签发留痕全部通过。

### 30.18 通用槽位与完整实例模块（R-024 / R-025，2026-09-11）

> 2026-09-11 口谕修订：神经总线每一节点不再「硬挂」固定的 agent 实例形态，改为**最多 64 个通用槽位**；**norpagent 完整实例不被抛弃**——包装为标准模块 `NorpAgentModule`，可插入任意节点的任意空闲槽位。

#### 30.18.1 设计要点与兼容性

| 项 | 说明 |
|---|---|
| 节点槽位面 | 每节点最多 **64 个通用槽位**（Universal Slots，`MAX_SLOTS=64`）；槽位走神经总线，model / tools / plugins / 自定义模块皆可挂载 |
| 连接器延伸 | CNB 是「槽位连接器」的多实例延伸扩展：单实例时槽位在本地连接部件，多实例时经神经树跨进程连接同一套槽位协议 |
| 完整实例模块 | `NorpAgentModule`（kind=`norpagent-instance`）：真实运行的 NorpEngine 的标准包装——可插、可拔、可描述、可替换；实例动作面（`KERNEL_ACTIONS` 15 项）经槽位二级路由可达 |
| 自动装配 | `CnbAdapter.bind_actions()` 自动把引擎实例挂入默认槽位 `norpagent`（CLI 神经进程 / 环境变量自动挂载 / `unbox --cnb` 三条路径同源） |
| 上限裁决 | 第 65 个槽位拒绝（`SlotError`） |

**兼容性说明**：本变更为节点内部形态的破坏性变更（弃「硬挂固定实例」），但不弃实例本身——CLI 神经进程、环境变量自动挂载与 `unbox --cnb` 三条路径均自动完成「实例 → 标准模块」装配，既有命令与协议不变。

#### 30.18.2 模块协议（MountableModule）

| 方法 | 作用 |
|---|---|
| `describe()` | 白盒描述（随槽位快照上总线） |
| `ok()` | 模块健康自述 |
| `on_mount(node)` | 挂载回调；抛错 = 挂载失败、槽位不提交（事务性，原状态零变化） |
| `on_unmount(node)` | 卸载回调（尽力而为；异常不阻塞卸载并记审计） |
| `actions()` | 模块导出的 exec 动作表（动作名 → handler） |
| `heartbeat()` | 心跳附加贡献（随节点心跳压缩上汇） |

内置两个实现：

- `GenericModule(kind, label, payload)`——任意可挂载物；载荷为自描述 JSON（不预设字段、不做语义裁剪、如实呈现挂载了什么）；
- `NorpAgentModule(engine, adapter=None)`——完整实例模块：
  - `actions()`：全量导出 `KERNEL_ACTIONS`（任务面 / 任务分子 / 状态面 / 快照面 / 运维面共 15 项）；
  - `describe()`：engine_state / active_tasks / preset / version / actions 白盒快照；
  - `heartbeat()`：实例忙闲（engine_state / active_tasks）随心跳上汇。

```python
from norpagent.cnb.slots import NorpAgentModule, GenericModule

node.mount_module("norpagent", NorpAgentModule(engine))     # 完整实例模块
node.mount_module("tools-1", GenericModule(                 # 任意载荷模块
    kind="tools", label="custom toolset",
    payload={"entry": "my_tools.py", "count": 3}))
print(node.describe_slots())                                # 槽位全景（白盒）
```

#### 30.18.3 槽位湾（SlotBay）与总线动作

`SlotBay` 负责挂载管理：容量 ≤64、`slot_id` 唯一、动作名不与既有槽位冲突、`on_mount` 失败即不提交（事务性）；所有挂载 / 卸载进入节点审计环。节点内置四个槽位动作，经总线可达：

| 动作 | 类型 | 说明 |
|---|---|---|
| `slot_list` | 只读 | 槽位数量 / 空位 / 摘要（count / free / max_slots / slots） |
| `slot_describe` | 只读 | 单槽位（`args.slot_id`）或全槽位完整描述 |
| `slot_mount` | 变更 | 经总线挂载自描述 JSON 规格模块（model / tools / plugins / 自定义） |
| `slot_unmount` | 变更 | 卸载（回调 + 动作面收回 + 审计） |

两点注意：

1. **冻结期白名单**：隔离冻结节点（§30.17.2）放行只读取证面（`slot_list` / `slot_describe`），变更面（`slot_mount` / `slot_unmount`）拒绝；
2. **完整实例模块不经 JSON 规格构建**：`slot_mount` 需要活引擎对象，无法由 JSON 规格构建 `norpagent-instance` 模块——如实拒绝；请由代码直接挂载 `NorpAgentModule`。

```bash
# 中枢侧经总线查看某原子槽位（示例）
norpagent exec --node norpbot-01 --action slot_list --args '{}'
norpagent exec --node norpbot-01 --action slot_describe \
    --args '{"args": {"slot_id": "norpagent"}}'
```

#### 30.18.4 自动装配与心跳融合

`CnbAdapter.bind_actions()` 同时完成：内核动作面直接注册（source=kernel）+ 完整实例模块挂入默认槽位 `norpagent`（source=slot，动作面兜底——即便手工装配不做直接注册，节点仍具备完整实例操作面）；心跳携带槽位用量（`slots.count` / `slots.free`），中枢 `reports` 可直接看到每个原子的槽位占用与空位。

#### 30.18.5 验收

`src/nervous_bus/test_cnb_slots.py`（51 项）、`test/test_cnb_kernel_actions.py`（32 项）、M4.5 暴力混合压测 H 域（含槽位子域）全绿。

---

### 30.19 神经树显式定义：不预设形状（2026-09-12 反馈轮）

> 核心规则：**CNB 不预设任何神经树形状**——启动时必须显式传入整树定义；每层 `LEVEL`、各层个数、低层父级、端口等必要参数**缺一个即逐条显式报错**；npa 启动路径的配置错误**不阻塞主线程启动**（显式报错、神经树不加载）。

#### 30.19.1 定义结构（format `farstars-cnb-tree/1`）

```json
{
  "format": "farstars-cnb-tree/1",
  "host": "127.0.0.1",
  "levels": [
    {"level": 0, "count": 1, "kind": "cortex", "node_id": "cortex", "port": 17800},
    {"level": 1, "count": 2, "kind": "agent", "parent": 17800, "base_port": 17810},
    {"level": 2, "count": 4, "kind": "worker", "parent": "level:1",
     "ports": [17820, 17821, 17822, 17823]}
  ]
}
```

必要参数与语义（逐项校验，缺一即报错）：

| 字段 | 必填 | 说明 |
|---|---|---|
| `levels[].level` | 是 | 层号 0~63；level 0 为中枢（树根，`count` 必须为 1） |
| `levels[].count` | 是 | 本层节点个数（≥1） |
| `levels[].port` / `ports` / `base_port` | 是（三选一） | 端口必须显式配置、不写死（R-025）；`port` 限 `count=1`，`ports` 长度=`count`，`base_port` 依次分配 |
| `levels[].parent` | 低层必填 | 父级三种表示：**父节点端口号**（整数或数字串）/ 父节点 id / `"level:N"`（挂到第 N 层节点，按定义顺序轮转） |
| `levels[].kind` | 否 | 原子类型；level 0 必须为 `cortex` |
| `levels[].node_id` | 否 | 节点 id 或模板（可含 `{i}` 占位符）；缺省 `cortex` / `<kind>-<序号>` |
| `levels[].engine` | 否 | `true` = 该节点携带完整内核引擎（仅 spawn 模式；进程内模式显式拒绝） |
| `levels[].heartbeat` / `desc` / `args` | 否 | 心跳间隔 / 描述 / spawn 模式附加参数（字符串列表） |
| `auto.watch` / `auto.reconcile` | 否 | 文件监视自动改形 / 自动收敛开关与间隔（秒） |

未知字段、端口重复、节点 id 重复、父级引用不存在、父层级不低于子层级、format 不符——全部逐条列出（不静默、不猜测、不填默认拓扑）。

#### 30.19.2 三种定义来源

| 来源 | 用法 |
|---|---|
| 直接参数（dict） | `np(cnb={"tree": {...}})` / `norpagent tree up --def '{"levels": [...]}'` |
| JSON 文件 | `--def tree.json`、`NORP_CNB_TREE=tree.json`、`np.remount(cnb={"tree": "tree.json"})` |
| PY 文件 | 模块级 `TREE` / `SPEC` / `tree` / `spec` 变量（可为返回 dict 的可调用对象），或 `build()` / `build_tree()` 函数——可用程序逻辑生成形状 |

#### 30.19.3 两种装配形态

| 形态 | 说明 |
|---|---|
| 进程内（inproc，默认） | 同一进程装配中枢 + 各层裸神经节点（各自独立总线端口）；`np(cnb={"tree": ...})` 由宿主把引擎绑定为根节点模块 |
| 多进程（spawn） | 每个节点经 `norpagent cortex/node` 子进程启动；`engine=true` 节点携带完整内核引擎，否则 `--bare` |

#### 30.19.4 运行中改形（手动 / 自动）

- **手动**：`np.remount(cnb={"tree": 新定义})` 差分改形（保留未变节点、增删变更节点；根节点变化则整树重建）；
- **文件监视（自动）**：`norpagent tree up --def tree.json --watch` 或定义 `auto.watch=true`——定义文件变更即自动改形；错误保持现形并显式报错；
- **自动收敛**：`--reconcile SECONDS` 或定义 `auto.reconcile=true`——节点掉线 / 子进程退出时按定义自动恢复。

#### 30.19.5 入口与命令

```bash
norpagent tree validate --def tree.json      # 校验（缺必要参数逐条报错，退出码 0/2）
norpagent tree show --def tree.json [--json] # 展示解析后的节点表
norpagent tree up --def tree.json --mode inproc|spawn [--watch] [--reconcile 5]
```

```python
import norpagent as np

engine = np(cnb={"tree": "tree.json"})          # 启动时显式定义（进程内整树）
np.remount(cnb={"tree": {"levels": [...]}})     # 运行中改形
np.remount(cnb=False)                           # 卸载整树
```

`unbox` 成品入口同样支持：`norpagent unbox --cnb-tree tree.json`（或档案 `cnb.tree`）；与环境变量 `NORP_CNB_TREE` 同源。

#### 30.19.6 错误语义（不阻塞启动）

- `np()` 启动路径：配置错误（缺端口 / 缺节点标识 / 定义缺必要参数）**不阻塞主线程启动**——宿主照常启动、错误显式打印、神经树不加载；状态 `engine.cnb_status == "config-error"`、错误内容 `engine.cnb_error` 可查；
- 直接校验面（`validate_cnb_config` / `np.remount`）：保持「显式报错」的严格语义（调用方可立即处理）；
- 端口规则不变：不写死默认端口（R-025）；禁止静默退化。

#### 30.19.7 验收

`test/test_cnb_tree_suite.py`（56 项）：三来源解析、必要参数逐条报错、父级三种表示、进程内装配与差分改形、监视自动改形、自动收敛、多进程真进程树、np 集成与错误语义、CLI——全部通过；回归复跑 CNB 全家与 M4.5 全绿。

## 第 31 章　成品发行版：norpagent unbox

### 31.1 定位

`norpagent unbox` 是**成品发行版入口**（R-006）：一键拉起开箱即用的自进化用户软件（架构书 §8.1）。装配结构：

| 部件 | 说明 |
|---|---|
| 核心智能体 | **单个功能强大的智能体**（R-014：不设默认原子集）；引擎 + 装配档案，按 standard 预设全工具面装配 |
| 中枢（可选） | CNB level 0 中枢进程（含引擎）；默认不携带（R-023），显式 `--cnb` 启用；启用时端口必须手动配置（R-025） |
| 控制台 | Web 前端（对话 / 设置 / 回退 / 插件 / 控制台页），浏览器打开即用 |
| 进化器 | 自进化回路设置底座（R-004 / R-005），默认开启（重大人工 / 普通自动） |
| 装配档案 | `~/.norpagent/unbox.json`——声明式数据，可读可改，改动即时生效 |

用户三不原则（R-007）：不需要看开发手册、不需要知道怎么开发、不需要知道运行过程；控制台常驻「运行过程可查、可干预」通道（白盒默认不打扰）。

### 31.2 快速上手

```bash
norpagent unbox                          # 浏览器打开即用（默认端口 8890）
norpagent unbox --port 8891 --no-browser # 指定端口 / 不自动开浏览器
norpagent unbox --smoke                  # 自检：装配 → 健康检查 → 退出（CI/测试）
norpagent unbox --cnb --cnb-port 17811   # 显式启用 CNB（端口必配，R-025）
norpagent unbox --cnb-parent http://127.0.0.1:17800 --cnb-port 17811
                                         # 以节点身份加入既有神经树
```

| 参数 | 说明 |
|---|---|
| `--port N` | Web 入口端口（默认读装配档案，首次 8890） |
| `--no-browser` | 不自动打开浏览器 |
| `--smoke` | 自检模式：装配 → 健康检查 → 退出（成功 0 / 失败 1） |
| `--cnb` | 显式启用 CNB（默认不携带，R-023） |
| `--cnb-node-id ID` | CNB 节点 id（缺省 `unbox-<pid>`） |
| `--cnb-parent URL` | 以节点身份加入既有神经树 |
| `--cnb-port N` | CNB 节点端口（启用时必配；缺失显式报错且不阻塞启动，R-025 / §30.19.6） |
| `--cnb-tree <定义>` | 神经树显式定义（JSON / PY 文件路径或 JSON 文本）；整树按定义装配、端口由定义携带；不预设形状（§30.19） |
| `--profile PATH` | 装配档案路径覆盖 |

启动输出（控制台）：

```
FarStars（远星）开箱即用软件已上线
  入口        http://127.0.0.1:8890/
  控制台      http://127.0.0.1:8890/farstars
  智能体      单个功能强大智能体（preset=standard）
  成品档案    ~/.norpagent/unbox.json
  CNB         未携带（默认关闭，R-023）
  退出        Ctrl+C（或控制台退出）
```

### 31.3 装配档案（unbox.json）

首次运行自动创建；格式 `farstars-unbox/1`；档案不是 JSON 对象 / 读取失败给出明确错误（不静默）。默认字段：

| 字段 | 默认 | 说明 |
|---|---|---|
| `name` | `FarStars Unbox` | 档案名 |
| `preset` | `standard` | 单个功能强大智能体（全工具面） |
| `model` | `null` | `null` = 引擎默认；可填模型配置 |
| `ui` | `web` | 前端形态 |
| `port` | `8890` | Web 入口端口 |
| `console` | `true` | 星轨控制台 / 内置控制台页 |
| `evolution.enabled` | `true` | 自进化总开关 |
| `evolution.approval` | `major-manual` | 默认：重大人工 / 普通自动（另支持 `all-manual` / `all-auto`） |
| `evolution.idle_policy` | `reduced` | 闲时减少或不进化（R-011） |
| `cnb.enabled` | `false` | 默认不携带（R-023） |
| `cnb.node_id` / `cnb.parent` / `cnb.port` | `null` | 启用时端口必配（R-025） |
| `cnb.tree` | `null` | 神经树显式定义（JSON / PY 文件路径或 JSON 文本；整树按定义装配，端口由定义携带） |

### 31.4 CNB 两种装配形态

| 形态 | 触发 | 结构 |
|---|---|---|
| 独立中枢（树根） | `--cnb --cnb-port N`（无 parent） | 本进程内含 level 0 中枢；引擎经 `CnbAdapter` 绑定为中枢的引擎槽——完整实例同时成为中枢节点上的标准槽位模块（§30.18） |
| 入树节点 | `--cnb-parent URL --cnb-port N` | 引擎以节点身份自动挂载到既有神经树（与环境变量自动挂载路径同源） |
| 神经树（显式定义） | `--cnb --cnb-tree <定义>` | 按显式定义装配整树（不预设形状）；宿主引擎绑定为根节点模块；端口由定义携带（§30.19） |

缺端口启动 CNB 会给出明确错误但不阻塞启动（R-025 修订 / 2026-09-12 反馈轮：端口号不写死、必须手动配置；配置错误时成品照常运行、神经树不加载，错误信息显式打印）。

### 31.5 自检模式（--smoke）

流程：装配 → Web 健康检查（`/api/health`）→（启用 CNB 时）树就绪检查 → 退出。

- 独立中枢：检查中枢总线健康（`/cnb/health`）与中枢节点上的**完整实例槽位模块**（`instance_module_mounted`）；
- 入树节点：等待引擎挂载状态（`cnb_status == "mounted"`）；
- 神经树（显式定义）：等待 `cnb_status` 到达 `mounted`；`config-error` 属「显式报错、不阻塞启动」的既定语义，按产品健康口径如实报告（打印错误内容）。

输出末行 `SMOKE OK`（退出码 0）或 `SMOKE FAILED`（退出码 1），CI / 测试可直接断言。

### 31.6 失败处置与救援提示

| 场景 | 行为 |
|---|---|
| CNB 启用但未配端口 | 显式报错（不阻塞启动）：成品照常运行、神经树不加载；提示「端口号不写死，必须手动配置」（R-025 修订 / §30.19.6） |
| 装配档案损坏 | 明确错误（不静默降级） |
| 启动失败 | 给出救援提示：安全模式（最小内核）`norpagent --safe-mode`；崩溃救援回滚 `norpagent-rescue rollback --last-good` |
| 进化底座失败 | 不阻塞成品启动（尽力而为，打印 `evolution bootstrap skipped`） |

### 31.7 环境变量

| 变量 | 作用 |
|---|---|
| `NORPAGENT_UNBOX_HOME` | 装配档案 / 设置库 / 进化日志的根目录覆盖（默认 `~/.norpagent`；测试隔离用） |

---

## 第 32 章　自进化体系：热重载、勾选审批与进化包

### 32.1 定位与总览

自进化子系统（`norpagent.evolution`）是四类进化（2A 记忆 / 2B 技能 / 2C 配置 / 2D 代码）共享的设置与执行底座（架构书 §7）。五个模块：

| 模块 | 职责 | 对应需求 |
|---|---|---|
| `store.py` | 设置事实源（SQLite + JSON 导入导出）+ 审计 + 进化日志 | R-017 |
| `points.py` | 可进化点注册表 + 逐项勾选审批制 | R-005 |
| `hotswap.py` | 代码进化热重载（新文件新逻辑；原文件字节不动） | R-004 |
| `packages.py` | 进化包 `.fspack` + 整合包 `.zip` | R-010 / R-012 |
| `rhythm.py` | 进化节奏与方向（闲时策略 / 常用候选 / 命令式） | R-011 |

`norpagent unbox`（第 31 章）启动时调用 `bootstrap(profile)`：建库 + 注册 schema + 把装配档案的进化口径写入设置事实源；失败不阻塞内核加载。

### 32.2 设置事实源（SettingsStore）

- 存储：SQLite（默认 `~/.norpagent/settings.db`，`NORPAGENT_SETTINGS_DB` 可覆盖）；三张表：`kv`（值）/ `schema`（设置项元数据）/ `audit`（审计环）；
- 每个设置项携带 **`evolvable`（可进化）/ `locked`（锁定）** 一等字段；
- **进化器写锁定项 / 非可进化项 = 内核拒绝 + 审计告警**（`SettingsLockedError`；actor 以 `evolution` 开头的调用即受此守卫）；
- JSON 导出 / 导入：`export_json()` / `import_json()`（format `farstars-settings/1`，含 schema + 值 + 审计尾部）；
- 审计：`audit_tail(n)`——谁在何时改了什么（含被拒绝的写入）。

### 32.3 可进化点与勾选审批

内核动点盘点共 **14 项**：内核循环与调度、智能体运行时、上下文与记忆、工具集、模型适配层、钩子面、神经总线、快照与回滚、安全体系、插件管线、内置前端与设置面板、前端家族、预设模式、进化器自身。

勾选语义（R-005）：

| 勾选态 | 含义 | 执行方式 |
|---|---|---|
| 勾了 | 该项目人工批准 | 提案先出待批卡片，人确认后才执行 |
| 不勾 | 自动批准 | 快照 → 应用 → 验证 → 失败自动回滚 |

默认档位：**重大类默认勾选（人工）、普通类默认不勾选（自动）**；分类口径（重大 / 普通）本身是设置项，可逐项改；进化器自身（`evolution.self`）出厂锁定（`locked=True`：任何进化写入直接拒绝）；安全体系默认人工档。勾选态变更入审计。

API：`ApprovalPolicy.decisions()`（面板数据源）/ `set_manual()`（勾选）/ `set_category()`（分类口径）/ `clear_manual()`（恢复默认）/ `can_evolve()`（总开关合并口径）。

### 32.4 代码进化热重载（hotswap）

铁律（R-004）：**不原地改写原文件、不删除原文件逻辑**——一律「产出新文件 → 验证 → 热重载切换到新逻辑」，原逻辑保留、一键回退。

| 步骤 | API | 说明 |
|---|---|---|
| 产出 | `stage_new_version(target, new_code, tag="")` | 新版本文件 `原文件名__evo_<时间戳>[_tag]_<n>.py` 写在原文件同目录；原文件只读不动 |
| 激活 | `activate(record, validate=..., apply_fn=...)` | 加载新文件 → 验证 → 应用；任一步失败 = 不激活 + 标记 `failed`（自动回滚语义，绝不部分激活） |
| 回退 | `rollback(record, apply_fn=...)` | 放弃新版本、回到原逻辑（可选重新应用原版） |
| 实证 | `original_intact(record)` | 校验原文件 sha256 与 stage 时一致——「永不删除原文件逻辑」的可验证证据 |
| 清单 | `list_versions(target)` | 列出全部历史版本文件 |

状态机：`staged → active / failed`；回退后 `rolled_back`。全部动作写进化日志（JSONL）。

### 32.5 进化包（.fspack）与整合包（.zip）

**进化包**（R-010）：

- 后缀 `.fspack`；**同时兼容读取 `.json` 和 `.py` 两种后缀**；
- 载荷自描述（format `fspack/1`）+ **sha256 校验** + **作者署名**；
- API：`build_fspack / write_fspack / export_fspack / read_fspack / verify_fspack / import_fspack`；
- 校验失败 / 应用失败：**失败逻辑完全不使用**、如实报错、记入日志（`fspack.import.failed`）。

**整合包**（R-012）：

- `.zip`，单包最多 **1024 个**进化包（超出整体拒绝：导出不创建、导入不部分导入）；
- 整批 / 多包导入：**任一失败不阻塞其余**；逐条如实报告 `{total, ok, failed, failed_entries, applied}`；
- API：`export_bundle / import_bundle`；日志事件 `fspack.bundle.import.ok` / `fspack.bundle.import.failed`。

前端一键导出 / 导入（设置面板）：`/api/evolution/export?kind=fspack&author=...`、`/api/evolution/import`。

### 32.6 节奏与方向（rhythm）

| 能力 | API / 设置键 | 说明 |
|---|---|---|
| 闲时策略 | `IdlePlanner.policy()` / `evolution.idle_policy` | `reduced`（默认：闲时减少或不进化）/ `off`（不进化）/ `auto`（维持） |
| 闲时判定 | `evolution.idle_min_seconds` | 默认 600 秒无需求视为闲时 |
| 常用候选 | `UsageTracker.candidates()` / `evolution.candidate_threshold` | 用户常用（**≥3 次**，阈值可设）功能进入进化候选 |
| 命令式 | `command_evolution(command)` | 用户直接下达命令进化（优先级最高；执行仍走热重载 + 勾选审批） |

### 32.7 接口面与日志

| 接口 | 方法 | 说明 |
|---|---|---|
| `/api/evolution/points` | GET | 全部可进化点当前裁决视图（面板数据源） |
| `/api/evolution/points` | POST | 改勾选 / 分类 / 恢复默认（变更入审计） |
| `/api/evolution/log` | GET | 进化日志尾部（热重载 / 进化包记录） |
| `/api/evolution/export` | GET | 导出（`kind=fspack` 进化包；默认设置 JSON 快照） |
| `/api/evolution/import` | POST | 导入 `.fspack` / `.json` / `.py` / `.zip`（整合包逐条语义） |

进化日志（JSONL，默认 `~/.norpagent/evolution_log.jsonl`，`NORPAGENT_EVOLUTION_LOG` 可覆盖）事件：`hotswap.stage` / `hotswap.activate` / `hotswap.failed` / `hotswap.rollback` / `fspack.export` / `fspack.import` / `fspack.import.failed` / `fspack.bundle.export` / `fspack.bundle.import.ok` / `fspack.bundle.import.failed` / `evolution.command` 等。

### 32.8 验收

- `test/test_evolution_suite.py`（49 项）全绿；
- M4.5 暴力混合压测 I 域（自进化：勾选 / 热重载 / 进化包 / 节奏）全绿。

### 32.9 运行期加固：健康核验、自动回退与巡检（2026-09-12 反馈轮）

> 反馈问题：自进化「会不会自己改坏了」。回答不是承诺，而是**多层防线 + 每层可验证**（下述机制均有套件实证）。

**防线清单（纵深防御）**：

| 层 | 机制 | 实证 |
|---|---|---|
| 1 改不坏原文件 | 代码进化不原地改写、不删除原文件——一律产出新版本文件（`<stem>__evo_<时间戳>.py`），原文件字节不动 | `hotswap.original_intact()`（sha256 比对） |
| 2 加载即验证 | 激活 = 重新加载新文件 + 可选 `validate` 回调；语法 / 导入错误直接拒绝激活 | `hotswap.activate()` |
| 3 激活后健康核验 | 新增 `health` 回调：激活后立刻核验（缺省核验 = 新文件存在 / 可加载 / 原文件未动）；失败**自动回退**（重新装回原逻辑，或调用自定义 `revert_fn`），记录 `reverted` 标记 | `activate(..., health=..., revert_fn=...)` |
| 4 活跃版本巡检 | `hotswap.verify_active()`：文件存在 / 可重新加载 / 原文件 sha256 未变；`ProposalBoard.health_sweep()` 巡检全部已应用代码提案，损坏即回退标记 + 熔断计次 + 通知 + 日志 | `verify_active` / `health_sweep` |
| 5 启动巡检 | `bootstrap()`（unbox 启动）自动执行一次巡检，历史遗留的损坏版本在启动时即被发现回退 | `evolution.bootstrap()` |
| 6 熔断与审批 | 连续失败达阈值自动暂停该点进化；重大类默认人工批准（勾选制）、锁定项任何进化器不可写 | `CircuitBreaker` / `ConfigEvolver.check_target` |
| 7 兜底 | 快照时间线 / 崩溃救援 CLI / 安全模式常驻，任何阶段都可回退接管 | 第 15 / 24 章 |

```python
from norpagent import evolution as evo

# 激活后健康核验 + 失败自动回退（自定义回退优先，其次用 apply_fn 重装原逻辑）
record = evo.stage_new_version("mod.py", new_code)
evo.activate(record, apply_fn=apply_fn, health=lambda m: smoke(m))
print(evo.verify_active(record))     # {'ok': True, 'checks': {...}}

board = evo.ProposalBoard()
print(board.health_sweep())          # 巡检全部已应用代码提案（启动时自动执行一次）
```

验收：`test/test_evo_hardening_suite.py`（19 项：健康通过 / 失败回退 / 自定义回退 / 无回退手段仍显式失败 / 坏代码无法激活 / 文件丢失与原文件被改动检出 / 巡检回退熔断 / 启动巡检 / 锁定项拒绝）全绿；既有进化套件 49 项复跑全绿。

## 第 33 章　插件开发完全指南

> **本章定位**：插件是浅开发中距离内核最近的扩展面。客户与第三方在**不改内核源码**的前提下，一切可以做的地方都通过插件完成：工具、钩子、槽位、组件、模型、服务、页面、CLI 命令、设置项。本章是插件作者的完整参考，覆盖从第一个插件到签名发布的全部流程；第 11 章为宿主侧概览，25.11 为快速上手版，本章为完整版。
>
> **客户端可见性**：本章与 25.11、第 11 章共同构成客户拿到的全部插件文档；仓库根目录的插件指南类文件为内部素材，以本章为准。

### 33.1 定位与全景

#### 33.1.1 插件能做什么

插件以独立 `.py` 文件（或 manifest 包）分发，宿主加载时自动获得签名校验 / AST 审计 / 导入限制 / 网络策略 / 人工审批全套安全防护。插件的能力面共六层：

| 层 | 能力 | 声明与入口 |
|---|---|---|
| 工具 | 以 OpenAI function schema 注册工具，进入模型的工具表 | `TOOLS` + `execute()`；动态注册 `api.register_tool()` |
| 钩子 | 定义 29 个标准钩子中的任意一个（16 个兼容钩子 + 13 个原生钩子） | 模块级函数；自定义钩子 `api.define_hook()` |
| 事件 | 订阅 / 触发总线任意事件（标准钩子 / 自定义事件） | `api.subscribe()` / `api.emit()` |
| 装配 | 注册自定义架构槽位 / 通用组件 / 模型 / 会话 / 沙箱 / 调度器 / UI | `setup(api)` 的 `api.register_*` 面 |
| 协作 | 服务注册与发现（插件间 / 插件与宿主通信）、依赖与版本声明 | `api.provide()` / `api.get()`；`PLUGIN_REQUIRES` / `PLUGIN_MIN_NORPAGENT` |
| 界面 | 挂载 Web 页面（front / flow / farstars）、注册 CLI 命令、声明设置项 | `api.mount_page()` / `api.register_cli_command()` / `api.register_settings()` |

#### 33.1.2 两种分发形态

| 形态 | 结构 | 适用 |
|---|---|---|
| 单文件插件 | 一个 `.py` 文件（模块级常量 + 函数） | 绝大多数场景；Web 面板可直接上传安装 |
| manifest 包 | 目录 + `manifest.json` + 入口模块（默认 `plugin.py`） | 需要版本 / 权限 / 隔离 / 签名元数据、或多文件组织 |

两种形态的模块级接口完全一致；包形态只是在文件之外多了一份元数据。

#### 33.1.3 加载与生效路径

插件目录通过以下任一方式进入系统，五条路径共用同一个安全管线：

```python
# 1. npa() 槽位（literal 语义，目录列表）
npa(plugins=["./my_plugins"])

# 2. 库化门面（完整生命周期 + 状态）
from norpagent.plugins import PluginSystem
ps = PluginSystem(reg, ["./my_plugins"], config={...})
ps.load()

# 3. 命令行
norpagent --mode standard --plugin-dir ./my_plugins

# 4. Web 设置面板（插件目录管理 + 上传安装 + 禁用/卸载/重载）

# 5. 单文件程序化装载（进化器 / 外部编排器的热装载入口；只装载指定文件）
from norpagent.plugins import install_plugin_file
loader, info = install_plugin_file(reg, "./my_plugins/one.py", config={...})
print(info.enabled, info.error or "ok")
```

运行中整体替换用 `npa.remount(plugins=[...])`：框架先完整卸载旧加载器（退订钩子 / 删除工具 / 执行 on_unload），再装载新目录，不叠加、不残留。

### 33.2 快速上手

#### 33.2.1 最小插件（一个工具）

```python
# my_plugins/hello_plugin.py
PLUGIN_NAME = "Hello Plugin"
PLUGIN_VERSION = "1.0.0"
PLUGIN_PUBLISHER = "your-name"
PLUGIN_DESCRIPTION = "演示插件：一个工具。"

TOOLS = [{
    "type": "function",
    "function": {
        "name": "hello",
        "description": "向指定名字打招呼。",
        "parameters": {
            "type": "object",
            "properties": {"name": {"type": "string"}},
            "additionalProperties": False,
        },
    },
}]


def execute(tool_name, args, ctx):
    if tool_name == "hello":
        return f"你好，{args.get('name') or 'world'}！"
    return None
```

#### 33.2.2 加载与验证

```python
import norpagent as np

npa = np(preset="minimal", plugins=["./my_plugins"])
# 或者给已有引擎热挂载：
np.remount(plugins=["./my_plugins"])
```

命令行验证（不启动完整应用，直接看插件表）：

```bash
norpagent plugins list --plugin-dir ./my_plugins
```

输出包含每个插件的启用状态、签名状态、隔离模式、工具与钩子数量，以及加载失败原因与警告。

#### 33.2.3 调试三件套

| 工具 | 用途 | 示例 |
|---|---|---|
| `ctx.logger` | 插件专属日志（stdout + `~/.norpagent/plugin_logs/<插件名>.log`） | `ctx.logger.info("...")`，支持 `debug / info / warn / error` |
| `ctx.storage` | 插件级状态存储（跨钩子、跨工具有效） | `ctx.storage["count"] = ctx.storage.get("count", 0) + 1` |
| 诊断面 | 钩子异常自动上报（不再静默）：首次错误打印 + 计数 + 写入 `PluginInfo.diagnostics` | Web 面板 / `plugins list` / `ps.status()` 查看 |

开发期把安全审计放宽、隔离设为进程内，便于断点调试：

```python
from norpagent.plugins import PluginSystem
ps = PluginSystem(reg, ["./my_plugins"], config={
    "plugin_security_audit": "warn",
    "plugin_isolation": "inproc",
})
```

上线前切回 `auto`（按插件声明决定隔离模式）。

### 33.3 插件格式与元数据

#### 33.3.1 单文件插件：模块级常量全表

| 常量 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `PLUGIN_NAME` | str | 是 | 插件显示名（重复加载判定与面板展示都以此为准） |
| `PLUGIN_VERSION` | str | 否 | 版本，默认 `0.0.0` |
| `PLUGIN_PUBLISHER` | str | 否 | 发布者 |
| `PLUGIN_DESCRIPTION` | str | 否 | 描述 |
| `TOOLS` | list | 否 | OpenAI function schema 列表 |
| `APPROVAL_HINTS` | dict | 否 | 工具 → 审批提示（见 33.4.5） |
| `ISOLATION` | str | 否 | `"process"` = 进程级隔离（AST 静态读取，不执行插件代码） |
| `PLUGIN_CAPABILITIES` | list | 否 | 能力声明（见 33.8.1）；缺省 = `tools / hooks / events` 基础集 |
| `PLUGIN_REQUIRES` | list / dict | 否 | 依赖声明（见 33.10） |
| `PLUGIN_MIN_NORPAGENT` | str | 否 | 最低框架版本，如 `"2.1"` |
| `__norpagent_type__` | str | 否 | 文件即模块类型声明（`"tool"` / `"plugin"`，FLOW 拖入识别） |

函数级接口：`execute(tool_name, args, ctx)`、29 个钩子函数（任选）、`setup(api)`、`on_load(ctx)`、`on_unload(ctx)`。

#### 33.3.2 manifest 包格式

```
my_pkg/
├─ manifest.json
├─ plugin.py          # 入口（manifest.entry 可改）
└─ ...                # 其他私有模块（同一目录内可 import）
```

`manifest.json` 字段全表：

| 字段 | 类型 | 说明 |
|---|---|---|
| `name` | str | 插件名（入口模块内的 `PLUGIN_NAME` 优先） |
| `version` | str | 版本 |
| `publisher` / `author` | str | 发布者（`publisher` 优先） |
| `description` | str | 描述 |
| `entry` | str | 入口文件，默认 `plugin.py` |
| `isolation` | str | `inproc` / `process` |
| `permissions` | list | 权限声明（`require_permissions` 开启时校验；`process` / `file_read` / `file_write` 等） |
| `capabilities` | list | 能力声明（等价 `PLUGIN_CAPABILITIES`） |
| `requires` | list / dict | 依赖声明（等价 `PLUGIN_REQUIRES`） |
| `min_norpagent` | str | 最低框架版本 |
| `signature` | object | 签名块（见 33.9.2） |

`manifest` 与模块常量并发存在时：`PLUGIN_NAME` 优先于 `manifest.name`；`version / publisher / description` 优先取 manifest。

#### 33.3.3 文件即模块（FLOW 集成）

带 `__norpagent_type__` 的插件文件可直接拖入 FLOW 画布作为模块节点；`__norpagent_type__ = "tool"` 表示单工具模块，`"plugin"` 表示完整插件。

### 33.4 工具开发

#### 33.4.1 schema 规范

按 OpenAI function 格式书写（`type` / `function.name` / `function.description` / `function.parameters`）；参数对象建议 `additionalProperties: False` 并列出 `required`。

工具描述要点：写清楚"何时该用、参数含义、返回什么"；模型依据描述决定是否调用。

#### 33.4.2 execute() 入口

```python
def execute(tool_name, args, ctx):
    """统一入口：处理返回 str / ToolResult / None；None = 不是本工具。"""
```

- 返回值 `str`：作为工具结果回填给模型；
- 返回值 `ToolResult`：完整结果（可带 `success=False`）；
- 抛出异常：框架捕获并转为失败结果（不会中断任务）；
- `args` 已做归一化（缺省为 `{}`）。

#### 33.4.3 动态工具（setup）

静态 `TOOLS` 之外，可在 `setup(api)` 里动态注册（handler 直接接收参数）：

```python
def setup(api):
    api.register_tool(
        "dyn_echo",
        lambda args: "echo:" + str(args.get("text", "")),
        description="动态注册的示例工具",
    )

# 两步签名也可：handler(args, plugin_ctx)
```

schema 省略时自动生成空参数对象；也可显式传入完整 schema。

#### 33.4.4 工具名冲突

工具名全局唯一（后注册覆盖先注册，有日志提示）。前缀式命名（`myplugin_xxx`）可避免冲突。

#### 33.4.5 APPROVAL_HINTS（审批精细控制）

```python
APPROVAL_HINTS = {
    # 只读工具免审批；其他未声明工具走宿主审批总开关
    "hello": {"approval": "none", "risk": "L0"},
}
```

`approval` 取 `"none"` 时该工具跳过人工审批；未声明的工具遵循宿主 `approval_enabled` 策略。

### 33.5 钩子开发（29 个钩子全表）

钩子函数直接写在插件模块里，名字即钩子名，无需注册。签名约定：**业务参数在前，`PluginContext` 在最后**。

#### 33.5.1 16 个兼容钩子（与既有应用生态对齐）

| 钩子 | 插件签名 | 返回值语义 |
|---|---|---|
| `on_agent_init` | `(ctx)` | 忽略 |
| `on_agent_shutdown` | `(ctx)` | 忽略 |
| `on_task_start` | `(task_text, ctx)` | 忽略 |
| `on_task_done` | `(summary, final_reply, ctx)` | 忽略（两个参数同为最终回复文本） |
| `on_task_error` | `(error_msg, ctx)` | 忽略 |
| `on_task_stopped` | `(ctx)` 或 `(reason, ctx)` | 忽略（按函数签名参数个数自动适配） |
| `on_task_timeout` | `(elapsed, ctx)` | 忽略 |
| `before_step` | `(step, messages, ctx)` | 返回 list 替换本轮消息；返回原值视为不改写 |
| `after_step` | `(step, reasoning, content, tool_calls, ctx)` | 忽略（观测；`tool_calls` 为完整列表） |
| `before_tool_call` | `(tool_name, args, ctx)` | 返回 dict 替换参数；返回原 `args` 视为不改写；返回 `False` 阻止调用 |
| `after_tool_call` | `(tool_name, args, result, ctx)` | 返回 str 替换结果文本；返回原值视为不改写 |
| `on_user_input_required` | `(question, ctx)` | 忽略 |
| `on_reasoning` | `(token, ctx)` | 忽略 |
| `on_content` | `(token, ctx)` | 忽略 |
| `on_event` | `(event_type, data, ctx)` | 忽略 |
| `on_usage_update` | `(usage, ctx)` | 忽略（`usage` 同时含 `input_tokens / output_tokens / tool_call_tokens` 与 `input / output / total` 两组键） |

#### 33.5.2 13 个原生钩子（9 层内核钩子面的其余部分）

| 钩子 | 插件签名 | 返回值语义 |
|---|---|---|
| `before_input` | `(user_input, session_id, params, ctx)` | 返回 str 替换输入 |
| `after_input` | `(user_input, session_id, ctx)` | 忽略 |
| `before_session_create` | `(session_id, title, params, ctx)` | 返回 str 或 `{"title": str}` 替换标题 |
| `after_session_create` | `(session_id, title, ctx)` | 忽略 |
| `before_message_append` | `(session_id, message, ctx)` | 返回 ChatMessage 替换；返回 `False` 丢弃本条 |
| `after_message_append` | `(session_id, message, ctx)` | 忽略 |
| `before_build_messages` | `(system_prompt, session_id, step, tool_names, ctx)` | 返回 str 或 `{"system_prompt": str}` |
| `after_build_messages` | `(messages, system_prompt, step, ctx)` | 返回 list 替换整组消息 |
| `before_model_call` | `(step, messages, tool_schemas, params, ctx)` | 返回 `{"messages": [...], "params": {...}}` 按需替换 |
| `after_model_call` | `(step, output, ctx)` | 返回 ModelOutput 替换输出 |
| `on_tool_error` | `(tool_name, error, args, ctx)` | 忽略 |
| `before_result` | `(result, ctx)` | 返回 RunResult 替换最终结果 |
| `after_result` | `(result, ctx)` | 返回 RunResult 替换（返回值生效） |

#### 33.5.3 可变钩子语义（重要）

- **返回值生效规则**：可变钩子（上表带返回值语义者）返回非 `None` 时参与改写；总线按"**首个非 None 返回值生效**"裁决，其余返回值忽略。
- **pass-through 规范化**：把"原样返回输入"（如 `return messages` / `return args` / `return result`）视为不改写（等价 `None`），**不会占位遮挡后续插件的改写**。这是旧生态的惯用写法，得到完整兼容。
- **副作用全执行**：同一次钩子事件中，**每个订阅者恰好被调用一次**；所有插件的副作用（计数、日志、写入）都会执行，不再出现"前面的插件返回非 None 导致后面插件不被调用"的截断。
- **HookVeto**：任何钩子抛出 `HookVeto` 即一票否决，按执行点的语义处置（多为任务以 `stopped` 收尾或跳过本步/本轮调用），否决即时生效。
- **异常隔离**：钩子内未捕获异常不会破坏主循环：错误被上报（首次打印 + 计数 + 写入 `diagnostics`），本次调用按"不改写"处理。

#### 33.5.4 调用时序与频度

单任务典型时序（每步循环）：

```
on_task_start
  └─ before_step（每步 1 次）
      ├─ before_build_messages / after_build_messages
      ├─ before_model_call → [on_reasoning / on_content / on_event / on_usage_update]
      ├─ after_model_call
      ├─ before_tool_call → 工具执行 → after_tool_call（每个工具调用各 1 次）
      └─ after_step（有工具调用的轮次）
on_task_done / on_task_error / on_task_stopped / on_task_timeout（四选一）
```

频度提示：`on_reasoning` / `on_content` 是流式高频钩子（逐增量触发），保持轻量；`on_usage_update` 每次用量更新触发。

#### 33.5.5 超时与隔离约束

进程隔离插件的钩子经 RPC 转发，单次钩子限时 5 秒（超时放弃、不阻塞主循环）；进程内插件无此限制，但仍建议钩子快速返回。

### 33.6 上下文对象 PluginContext 完整参考

所有钩子与 `execute()` 的最后一个参数都是 `PluginContext`：

| 字段 | 类型 | 说明 |
|---|---|---|
| `plugin_name` | str | 插件名 |
| `project_root` | str | 当前工作区根（任务上下文提供时） |
| `app_dir` | str | 应用数据目录（用户主目录） |
| `config` | dict | 宿主加载配置的只读快照 |
| `storage` | dict | **插件级状态存储**：跨钩子、跨工具、跨任务存活（同一次加载会话内） |
| `logger` | PluginLogger | 插件专属日志：`debug / info / warn / error`，stdout + 日志文件 |
| `current_step` | int | 当前步号（内核提供时） |
| `total_usage` | dict | 累计 token 用量（内核提供时） |
| `api` | PluginAPI | 注册门面（`setup` 期间及之后可用；见 33.8） |

```python
def on_task_start(task_text, context):
    context.logger.info(f"任务开始: {task_text[:60]}")
    context.storage["started_at"] = __import__("time").time()

def before_tool_call(tool_name, args, context):
    count = context.storage.get("tool_calls", 0) + 1
    context.storage["tool_calls"] = count
    context.logger.debug(f"第 {count} 次工具调用: {tool_name}")
```

### 33.7 生命周期与热重载

#### 33.7.1 生命周期函数

| 函数 | 时机 | 说明 |
|---|---|---|
| `setup(api)` | 安全管线通过后、注册前 | 注册扩展（工具 / 槽位 / 组件 / 钩子 / 事件 / 服务 / 页面 / CLI / 设置）；抛异常 = 拒载并**回滚已做注册** |
| `on_load(ctx)` | 注册完成后 | 运行时初始化（打开资源、预热缓存、写日志）；失败不拒载，记入诊断 |
| `on_unload(ctx)` | 卸载 / 重载 / 关闭前 | 清理资源；执行完才退订钩子、删除工具 |

时序：`安全管线 → setup(api) → 注册（工具入表 / 钩子入总线）→ on_load(ctx) →【运行期】→ on_unload(ctx) → teardown（退订 / 删工具）`。

#### 33.7.2 热重载（干净重载）

```python
from norpagent.plugins import PluginSystem
ps = PluginSystem(reg, ["./my_plugins"], config={...})
ps.load()
ps.reload("Hello Plugin")   # 完整卸载（on_unload + 退订 + 删工具）→ 重新走全管线
ps.unload("Hello Plugin")   # 单插件卸载
```

整体替换（推荐的生产路径）：

```python
npa.remount(plugins=["./my_plugins_v2"])   # 旧加载器全量卸载 → 新目录全量装载
```

卸载保证：钩子订阅真正退订（同一监听器对象）、工具从工具表删除、`setup` 注册的订阅 / 槽位 / 服务 / 命令 / 动态工具 / 组件依次回收；模型 / 会话 / 沙箱 / 调度器 / UI 注册遵循名称覆盖语义，不做删除（重载后同名注册自然覆盖）。

#### 33.7.3 禁用与卸载（宿主侧）

| 动作 | 语义 | 入口 |
|---|---|---|
| 禁用 | 插件保留在表内但不加载（`enabled=False`，原因可见） | Web 面板按钮；配置 `plugin_disabled: ["插件名"]` |
| 卸载 | 从磁盘删除插件文件（或包目录），随后重载 | Web 面板（带确认）；路径限制在插件目录内 |
| 启用 | 从禁用名单移除并重载 | Web 面板按钮 |

### 33.8 setup(api)：注册门面

`setup(api)` 是插件在注册阶段拿到宿主的唯一入口；`api` 为 `PluginAPI` 实例，全部方法归属当前插件，卸载时自动回收可回收项。

#### 33.8.1 能力声明（门禁）

```python
PLUGIN_CAPABILITIES = ["tools", "hooks", "events", "slots", "components",
                       "services", "cli", "settings"]
```

- 缺省（不声明）= 基础集：`tools / hooks / events`；
- 声明 `"*"` 或 `"all"` = 全量能力；
- 调用未声明能力的方法抛 `PluginCapabilityError`（`setup` 随之拒载并把原因写入 `error`）；
- 宿主可再经配置键 `plugin_capabilities` 收紧总闸（`None` = 不额外限制）。

能力名全表：`tools / hooks / events / slots / components / models / sessions / sandboxes / schedulers / uis / services / pages / cli / settings`。

#### 33.8.2 API 全表

| 方法 | 能力 | 说明 |
|---|---|---|
| `register_tool(name, handler, *, schema=None, description="")` | tools | 动态工具；`handler(args)` 或 `handler(args, plugin_ctx)` |
| `register_slot(spec)` / `unregister_slot(name)` | slots | 自定义架构槽位（`SlotSpec` 实例或字段 dict；spec 参考 3.8 节） |
| `register_component(kind, name, factory)` | components | 通用组件（预设里 `components={kind: name}` 引用） |
| `register_model(name, provider)` | models | 注册模型适配器 |
| `register_session(name, factory)` | sessions | 会话存储实现 |
| `register_sandbox(name, factory)` | sandboxes | 沙箱实现 |
| `register_scheduler(name, factory)` | schedulers | 调度器实现 |
| `register_ui(name, adapter)` | uis | 渲染器实现 |
| `define_hook(name, *, mutating=False, description="")` | hooks | 在引擎钩子系统上定义自定义钩子 |
| `subscribe(event, fn)` | events | 订阅任意总线事件（标准钩子 / 自定义钩子 / 自定义事件） |
| `emit(event, **payload)` | events | 触发总线事件 |
| `provide(name, obj)` / `get(name, default=None)` | services | 服务注册与发现（插件间 / 插件与宿主通信） |
| `mount_page(page, html)` | pages | 挂载 Web 页面（`"front"` / `"flow"` / `"farstars"`；引擎未就绪时排队、前端挂载时消费） |
| `register_cli_command(name, handler, *, help="")` | cli | 注册 CLI 命令（`norpagent plugins run <name>` 执行；`handler(argv)` 或 `handler()`） |
| `register_settings(schema)` | settings | 声明设置项 schema（Web 面板展示） |
| `get_setting(key, default=None)` / `set_setting(key, value)` | （随 settings） | 插件设置的持久化读写（宿主代写 `~/.norpagent/plugin_settings/`） |

#### 33.8.3 综合示例

```python
PLUGIN_CAPABILITIES = ["tools", "hooks", "events", "services", "cli", "settings"]


def setup(api):
    # 服务：给别的插件 / 宿主用
    api.provide("weather.cache", {})

    # 动态工具
    api.register_tool("weather_now", query_weather, description="查询实时天气")

    # 自定义钩子 + 订阅
    api.define_hook("weather_updated", description="天气数据更新事件")
    api.subscribe("weather_updated", lambda e: api.logger.info("weather updated"))

    # CLI 命令
    api.register_cli_command(
        "weather-refresh", lambda argv: refresh_all(), help="刷新天气缓存")

    # 设置项
    api.register_settings({"type": "object",
                           "properties": {"city": {"type": "string"}}})
    api.set_setting("city", "北京")
```

```bash
norpagent plugins run weather-refresh --plugin-dir ./my_plugins
```

### 33.9 安全体系（作者视角）

#### 33.9.1 加载管线回顾

```
发现 → 签名校验 → AST 审计 → 权限声明校验 → 隔离决策 → 导入限制下加载 → 注册
```

每一阶段都是引擎钩子（`before/after_plugin_load / audit / register`），宿主可订阅拦截；插件作者需要理解的是下面四点。

#### 33.9.2 签名与信任

```bash
# 生成密钥对（私钥务必保密，勿提交仓库）
norpagent plugin-sign --gen

# 对插件入口文件签名（生成 <file>.sig 侧车，或写入 manifest.signature）
norpagent plugin-sign my_plugin.py --key <私钥hex>
```

- 签名对象：**入口文件字节的 SHA-256**；改动入口文件必须重新签名；
- 信任模型：内置官方公钥 + 用户配置 `plugin_trusted_keys`；
- 默认策略（R-020）：**未签名仅警告、不阻止加载**；`signature_required`（高安全档）才强制受信任签名；
- **签名无效（文件与签名不符）会直接拒绝加载**——遇到此错误时：重新签名，或移除失效签名块按未签名加载。

#### 33.9.3 审计与导入限制

| 配置 | 取值 | 对作者的影响 |
|---|---|---|
| `plugin_security_audit` | `off / warn / block` | `block` 下危险调用（子进程、提权、反射绕过等）直接拒载；受信任签名放宽为 `warn` |
| `plugin_security_import_restrict` | `off / safe / strict` | `safe` 禁 `subprocess / ctypes / socket / pickle` 等；`strict` 仅白名单模块可用 |
| `plugin_security_require_permissions` | bool | 开启时 manifest 必须声明 `permissions` |

受信任宽松口径：审计放宽为 `warn`、导入限制按配置执行（不受信任影响）。

#### 33.9.4 进程级隔离

```python
ISOLATION = "process"    # 或 manifest: "isolation": "process"
```

- 插件代码只存在于宿主子进程（JSON-lines RPC），主进程零执行风险；崩溃自动重启 + 重载；
- 钩子限时 5 秒；工具执行经 RPC 回传；
- 适用：处理不可信输入、需要 `subprocess` 等重能力、稳定性隔离优先的插件；
- 注意：进程隔离模式下 **不支持 `setup(api)` 注册**（插件代码不在主进程，注册面不可达；加载时给出警告），工具与钩子面不受影响。

### 33.10 依赖与版本

```python
PLUGIN_REQUIRES = ["other-plugin"]        # 依赖的其他插件（按名检查已加载且启用）
PLUGIN_MIN_NORPAGENT = "2.1"              # 最低框架版本
```

包形态写在 manifest：

```json
{"requires": ["other-plugin"], "min_norpagent": "2.1"}
```

校验时机：注册之前；不满足时报错拒载并写入原因（如 `requires norpagent >= 99.0 (current: 2.0.1)`）。

### 33.11 完整教程：从零到发布的天气插件

#### 33.11.1 第 1 步：工具 + 钩子 + 状态

```python
# my_plugins/weather_plugin.py
PLUGIN_NAME = "天气插件"
PLUGIN_VERSION = "1.0.0"
PLUGIN_PUBLISHER = "your-name"
PLUGIN_DESCRIPTION = "查询城市天气；任务开始时问候。"

TOOLS = [{
    "type": "function",
    "function": {
        "name": "weather",
        "description": "查询指定城市的当前天气。",
        "parameters": {"type": "object",
                       "properties": {"city": {"type": "string"}},
                       "required": ["city"],
                       "additionalProperties": False},
    },
}]

APPROVAL_HINTS = {"weather": {"approval": "none", "risk": "L0"}}


def execute(tool_name, args, ctx):
    if tool_name == "weather":
        ctx.storage["queries"] = ctx.storage.get("queries", 0) + 1
        ctx.logger.info(f"天气查询: {args.get('city')}")
        return f"{args.get('city')} 今日晴，25°C"      # 示例实现，可换真实 API
    return None


def on_task_start(prompt, ctx):
    ctx.logger.info(f"新任务: {prompt[:50]}")


def before_step(step, messages, ctx):
    return None                                     # 不改写
```

#### 33.11.2 第 2 步：加 setup（服务 + 命令 + 设置）

```python
PLUGIN_CAPABILITIES = ["tools", "hooks", "events", "services", "cli", "settings"]


def setup(api):
    api.provide("weather.queries", lambda: None)     # 供宿主/其他插件读取的占位服务
    api.register_cli_command("weather-stats", lambda argv: "ok",
                             help="天气插件统计")


def on_load(ctx):
    ctx.storage.setdefault("queries", 0)


def on_unload(ctx):
    ctx.logger.info(f"卸载，共查询 {ctx.storage.get('queries', 0)} 次")
```

#### 33.11.3 第 3 步：包形态 + 声明

```
weather_pkg/
├─ manifest.json
├─ plugin.py
└─ api_client.py
```

```json
{
  "name": "weather-pkg",
  "version": "1.0.0",
  "publisher": "your-name",
  "description": "包形态天气插件",
  "entry": "plugin.py",
  "isolation": "inproc",
  "capabilities": ["tools", "hooks", "events", "services", "cli", "settings"],
  "requires": [],
  "min_norpagent": "2.1"
}
```

#### 33.11.4 第 4 步：签名

```bash
norpagent plugin-sign my_plugins/weather_plugin.py --key <私钥hex>
norpagent plugins list --plugin-dir my_plugins      # 确认 signature: trusted
```

#### 33.11.5 第 5 步：测试清单

- [ ] `norpagent plugins list --plugin-dir ...`：加载成功、工具 / 钩子数量正确、无警告；
- [ ] 触发工具：模型可调用、返回值符合预期；
- [ ] 钩子生效：日志 / 计数 / 改写按预期；
- [ ] 卸载 → 重载：无重复订阅、无残留注册；
- [ ] 任务中验证：`npa(plugins=[...])` 起引擎跑一个任务全链路。

### 33.12 调试与排错

#### 33.12.1 插件记录（PluginInfo）字段解读

| 字段 | 含义 | 排错要点 |
|---|---|---|
| `enabled` | 是否加载成功 | `False` 时看 `error` 第一行 |
| `error` | 拒载原因 | 验签失败 / 审计拦截 / 权限缺失 / setup 失败 / 依赖不满足 |
| `warnings` | 非阻断警告 | 未签名、进程隔离跳过 setup 等 |
| `signature_status` | `trusted / untrusted / unsigned / invalid / unavailable` | `invalid` = 文件与签名不符 |
| `isolation` | `inproc / process` | 与预期不符时检查 ISOLATION 常量 / manifest / 宿主配置 |
| `audit_issues` | AST 审计发现（含行号） | `block` 档下的 critical 会拒载 |
| `diagnostics` | 运行期错误记录（钩子名 / 错误 / 次数 / 时间） | 钩子静默失效时第一时间查看 |
| `counts` | 钩子 / 工具调用计数 | 验证"是否被调用"、"调用了几次" |

#### 33.12.2 常见问题速查

| 症状 | 原因 | 解法 |
|---|---|---|
| 插件不在列表 | 目录未配置 / 文件名或 `__init__.py` 被跳过 | 检查插件目录配置与文件名（`__init__.py` 不作为插件） |
| `signature verification failed` | 签名与文件不符 | 重新签名，或移除失效签名块 |
| `security audit blocked` | block 档下命中危险模式 | 调整代码 / 提升信任（签名）后审计放宽为 warn |
| `import blocked` | 导入限制（safe / strict） | 改用安全模块，或由宿主调整导入限制档位 |
| `missing permission declarations` | 开启权限校验但 manifest 无 `permissions` | 补齐 manifest 权限声明 |
| `setup() failed: PluginCapabilityError` | 调用未声明能力的 API | 在 `PLUGIN_CAPABILITIES` / `capabilities` 加上对应能力 |
| `requires norpagent >= ...` | 版本低于声明 | 升级框架，或调低声明 |
| `missing plugin dependencies` | 依赖插件未加载 | 先加载依赖插件（顺序 / 目录） |
| 钩子看起来"没被调用" | 签名参数个数错 / 异常被吞（旧版行为） | 对照 33.5 全表检查签名；查看 `diagnostics`（现版本异常必上报） |
| 工具被审批拦住 | 未声明 `APPROVAL_HINTS` 且宿主开启总开关 | 为只读工具声明 `approval: "none"` |
| 进程隔离插件 setup 不生效 | 隔离模式不支持注册面 | 改为 `inproc`，或把注册逻辑移到工具 / 钩子面 |
| Web 面板显示"加载失败" | 见 error 详情行 | 按上面各条定位 |

#### 33.12.3 CLI 与 Web 工具

```bash
norpagent plugins list --plugin-dir ./my_plugins     # 插件表（失败 / 禁用 / 警告全可见）
norpagent plugins list --plugin-dir ./my_plugins --plugin-disabled x  # 模拟禁用
norpagent plugins run <命令名> [参数...] --plugin-dir ./my_plugins     # 运行插件命令
```

Web 面板（设置 → 插件）：完整状态徽章、错误与警告行、启用 / 禁用、卸载（带确认）、上传安装（.py）、目录管理与重载。

### 33.13 迁移指南（既有应用插件 → norpagent）

旧应用的插件**零改动迁移**，加载即用：

| 事项 | 兼容策略 |
|---|---|
| 模块级常量 | `PLUGIN_NAME / VERSION / PUBLISHER / DESCRIPTION` 原样识别 |
| `TOOLS` + `execute(tool_name, args, ctx)` | 原样识别 |
| 16 个钩子签名 | 与旧应用逐参数对齐（`on_task_stopped` 支持 1 参 / 2 参两种写法） |
| `ctx.logger` / `ctx.storage` | 完整提供（旧版这两个字段缺失的问题已修复） |
| `on_usage_update` | 同时提供旧键名（`input_tokens` 等）与内核键名 |
| `return messages / return args / return result` 等 pass-through 写法 | 规范化为"不改写"，不遮挡其他插件 |
| `APPROVAL_HINTS` | 原样生效 |
| `ISOLATION = "process"` | 原样生效（入口常量 AST 静态读取） |

迁移后建议：为插件补充 `PLUGIN_CAPABILITIES`（如需使用 setup 注册面）、签名与 manifest 元数据。

### 33.14 发布清单

- [ ] 入口文件独立可加载（`python -c "import importlib.util; ..."` 冒烟，或无副作用导入）；
- [ ] 元数据齐全（名称 / 版本 / 发布者 / 描述）；
- [ ] `norpagent plugins list` 无警告、无错误；
- [ ] 工具 / 钩子 / 注册面均按 33.11.5 清单验证；
- [ ] 已签名（`.sig` 或 manifest.signature），入口文件未再改动；
- [ ] 卸载 / 重载干净（`diagnostics` 无异常）；
- [ ] 若用 `subprocess` 等重能力：选定 `ISOLATION="process"` 或告知用户放宽导入限制；
- [ ] 分发说明中列出公钥（使用者将其加入 `plugin_trusted_keys` 即为受信任）。

---

## 第 34 章　设置事实源、白盒与进化闭环深化（v2.2.0）

### 34.1 定位

本章覆盖 v2.2.0（2026-09-12）三位一体架构书全量落地的开发者面：设置事实源（全量动点清单 + 四层继承 + 三通道同源）、白盒统一遍历、进化闭环深化（提案 / 熔断 / 2A-2C 执行器）、元框架与成品态入口、CNB 运行时热挂载、前端 V2 与三端共通 i18n。架构与验收口径见 `docs/远星三位一体架构书.md`（v1.0 第 14 章）。

### 34.2 设置事实源（`norpagent.settings`）

- **全量动点清单**：十一域（模型 / 循环 / 工具 / 记忆 / 神经 / 安全 / 插件 / 多模态 / 进化 / 前端 / 调度与恢复）；每项 = key / 标题 / 类别 / 类型 / 默认值 / 说明 / 可进化与锁定标记 / 危险级 / 三视角可见性 / 运行态桥接键（`config_key`）；
- **注册**：`register_kernel_schema(store)`（幂等）、`ensure_schema(store)`（内核清单 + 进化域一次注册，Web / CLI / unbox 入口共用）、`schema_view(store)`（DB 行 + 扩展元数据的合并视图，面板渲染 / 校验 / 导出唯一依据）；
- **四层继承（§5.3）**：`全局 > 档案（成品/预设）> 会话/任务 > 临时`——「不填 = 用上级」；API：`set_scoped / get_scoped / delete_scoped / resolve / layers / all_resolved`；每项三态：默认值 / 继承值（含来源）/ 显式值（含时间与行为者）；
- **镜像桥**：`mirror_config_to_store(cfg)`（运行态配置 → 设置库，值=默认时保持「默认态」）、`apply_store_to_config()`、`config_patch_for_key(key)`（单键补丁）；桥接仅作用于全局层；密钥类项不落设置库（保持既有 DPAPI 加密链路）；
- **审计与导入导出**：`audit_tail(n)`；`export_json() / import_json()`（JSON 快照含 schema / 值 / 审计尾部）。

### 34.3 `norpagent settings` CLI（三通道同源）

| 子命令 | 用途 |
|---|---|
| `list [--category C] [--view V] [--explicit]` | 列出设置项与解析值（来源标注） |
| `get KEY` | 单项解析详情（默认 / 各层显式值 / 有效值 + 来源） |
| `set KEY VALUE [--scope global\|profile\|session\|temp] [--string] [--no-apply]` | 写入（schema 校验：枚举 / 范围 / 布尔；桥接键合并运行态配置） |
| `reset KEY [--scope ...]` | 删除显式值（恢复上级继承 / 默认） |
| `export [PATH] / import PATH` | 设置库 JSON 快照导出 / 导入 |
| `audit [N] / schema [--category C]` | 审计尾部 / 注册表列出 |

示例：`norpagent settings set model.temperature 0.6`（桥接并即时写入运行态配置）；校验失败退出码 2 并给出明确原因。

### 34.4 白盒统一遍历（`norpagent.whitebox`）

- `overview(engine=None)`：按环节树统一生成 sections——`slots / hooks / cnb / evolution / frontend / recovery`；每个环境项含四维：
  - **可看** `describe`（装配对象、配置值、状态、槽位用量、动作面）；
  - **可改** `change`（remount / register_* / CNB 指令的替换提示）；
  - **可设** `settings`（该环节对应的设置键清单）；
  - **可溯** `audit`（环境相关审计尾部：CNB 节点审计环 / 进化日志等）；
- `env_describe(report)`：把环境项规整为 `describe / audit_trail / settings` 三件套视图；
- REST：`GET /api/whitebox/overview`；前端控制台「白盒总览」页按环节树呈现。

### 34.5 进化闭环深化（`evolution.proposals` / `evolution.engines`）

- **提案引擎 `ProposalBoard`**：`create → decide → execute → run`；状态机
  `proposed → awaiting（人工待批）/ rejected / approved → applied / failed / paused`；
  裁决遵循勾选制（勾 = 人工、不勾 = 自动）；执行前捕获回退方案，失败自动回滚
  （config 旧值恢复 / code 热重载回退 / memory 副本保留 / skill 登记回退）+ 熔断计次；
  日志事件 `evolution.proposal.created / awaiting / approved / rejected / applied / failed / paused`；
- **熔断 `CircuitBreaker`**：`evolution.breaker_threshold`（默认 3）与
  `evolution.breaker_auto_pause`（默认开）；状态持久于 `evolution.breaker.<point>.state`；
  `state(point) / resume(point) / all_states()`；面板「提案中心」可人工恢复；
- **执行器（`evolution.engines`）**：
  - `MemoryEvolver`（2A）：`scan / plan / apply_payload / restore / forgotten`——去重遗忘 = 先存副本（`memory.forgotten.<id>`）再软删，可恢复、可查询；
  - `SkillEvolver`（2B）：`registry / apply_payload / remove / candidate_payloads`——登记装载 + `.fspack` 存档（`~/.norpagent/skills/`）；
  - `ConfigEvolver`（2C）：`check_target / propose`——只允许写入 schema 标记 `evolvable` 的项；锁定项写入被内核拒绝并审计；
  - `CodeEvolver`（2D）：`propose` 包装（产出新文件 → 验证 → 热重载切换；原文件字节不动、一键回退；激活后健康核验 + 活跃版本巡检见 §32.9）；
- **REST `/api/evolution/proposals`**：GET（提案列表 + 熔断状态 + 待批）；POST actions：`run / decide / execute / breaker_resume / memory_plan / memory_apply / memory_restore / memory_forgotten / skill_candidates / skill_apply / config_tune`。

### 34.6 元框架与成品态入口

- **元框架态 `norpagent.core`**：四构件（`ArchLayer / Registry / EventBus / resolve_address`）+ 注册三件套（`register_slot / register_layer / register_hook`）+ 裸装配路径（`install_core()` + `build_embedded_preset()`）；示例见源码 docstring；
- **成品态 `norpagent.farstars_app`**：入口本体（装配档案 / 全量工具 / CNB 两形态 / 冒烟自检）；`norpagent.unbox` 为兼容转发层；`norpagent unbox` 默认 `tools: "all"` 全量装配全部内置工具。

### 34.7 CNB 运行时热挂载

```python
import norpagent as np

np.remount(cnb={"cnb": True, "node_id": "atom-x", "port": 17901,
                "parent": "http://127.0.0.1:17800"})   # 运行中挂上（R-025：端口必须显式配置）
np.remount(cnb={"tree": "tree.json"})                  # 运行中改形：按显式定义差分应用（§30.19）
np.remount(cnb=False)                                  # 运行中摘下（引擎保持运行）
```

- 已有挂载时先卸载旧适配器再挂新（替换语义）；挂载在后台线程完成、不阻塞调用；`tree` 形态在同类已挂载时做差分改形（`rebuild=true` 强制整树重建，详见 §30.19.4）；
- 直连回执（脚本 / 测试）：`from norpagent.cnb.engine import remount_cnb; remount_cnb(engine, spec, wait=10)`。

### 34.8 前端 V2 与三端共通 i18n

- **设置视图**：左列选项卡（按域）+ 右侧面板；三视角切换（成品 / 框架 / 元框架，持久化 `ui.console_view`）；每项悬停说明（schema description）；来源标注与一键恢复；总开关联动置灰（`enable_when`：记忆 / 安全 / 插件 / 多模态 / CNB；多模态 direct 路由时服务地址与密钥置灰）；危险级确认；框架视角 JSON 高级模式（差异应用 + 快照导入导出）；
- **控制台**：白盒总览（环节树）/ 提案中心（待批卡片批准 / 否决 / 执行、熔断恢复、记忆扫描与技能候选）两页签；
- **共通 i18n（`/assets/i18n.js`）**：统一语言集 `zh_CN / zh_TW / en`、统一存储键 `np_lang`；接口 `FarStarsI18N.get() / set(lang) / onChange(fn) / t(key) / register(dicts)`；旧键（`farstars_lang` / `norpflow.lang`）自动迁移；主前端 / 星轨控制台 / FLOW 三端接入，任一页切换全端生效（含跨标签 storage 同步）；
- **会话与输入框**：会话批量清除 / 清空全部（`POST /api/sessions/clear`，ids 省略 = 全部）；输入框内联控制模式 / 模型名 / 工作区（含目录选择器 `/api/fs/list`）。

### 34.9 验收

- `test/test_v22_suite.py`（65 项：元框架 / 成品态 / CNB remount / 设置事实源 / 白盒 / 进化闭环 / 前端与 i18n）全绿；
- `test/stress_m45_suite.py` 扩展（J16~J23 / K11~K14）全绿；最小内核 147 / 进化 49 / CNB 槽位 51 / 插件 100 复跑全绿；
- 前端 V2 无头浏览器冒烟全绿；版本号统一 2.2.0；
- **2026-09-12 反馈轮新增**：`test/test_cnb_tree_suite.py`（56 项，神经树显式定义）与 `test/test_evo_hardening_suite.py`（19 项，自进化运行期加固）全绿；M4.5 219、v2.2 65、最小内核 147、进化 49、CNB 全家（60 / 44 / 36 / 13 / 57 / 12 / 51 / 32）复跑全绿。

---

### 34.10 2026-09-12 反馈轮增补（版本约定 / nasyncio / 自进化加固 / CNB 树定义）

| 项 | 落点 | 说明 |
|---|---|---|
| 版本约定 | 本手册头部 + 全部活跃文档 | 活跃文档统一以当前发布版本为代码基线（该章成文时为 **2.2.0**，现行为 **2.2.1**）；历史修订记录版本号仅表示当时基线；归档文档保持原样 |
| asyncio 与 nasyncio 并存 | §4.7 + 第 19 章 FAQ | 标准库 `asyncio` 与自研 `norpagent.nasyncio` 互不冲突、可同进程同时使用（不依赖 = 不接管） |
| 自进化运行期加固 | §32.9；`evolution/hotswap.py` / `evolution/proposals.py` | `verify_active` / `activate(health=...)` 自动回退 / `health_sweep` 巡检 / `bootstrap` 启动巡检 |
| CNB 神经树显式定义 | §30.19；`cnb/tree.py`；`norpagent tree validate|show|up` | 不预设形状；三种来源；缺必要参数即报错；两种装配；remount 改形 / 监视自动改形 / 自动收敛；`np()` 启动路径配置错误不阻塞启动 |

验收：`test/test_cnb_tree_suite.py` 56 项、`test/test_evo_hardening_suite.py` 19 项全绿；M4.5 219、v2.2 65、最小内核 147、进化 49、CNB 全家（60 / 44 / 36 / 13 / 57 / 12 / 51 / 32）复跑全绿。

## 附录 D　术语表



| 术语 | 定义 |
|---|---|
| 地址函数（Address Function） | 框架的核心抽象：槽位值填「地址」（模块路径 / 工厂 / 实例）即接入，不填走默认 |
| 槽位（Slot） | 一个可替换组件的位置；`npa(...)` 的关键字参数名就是槽位名 |
| 槽位表热插拔 | `register_slot()` 运行时注册自定义槽位，注册即接入装配 / 校验 / 热替换全管线 |
| 最小内核 | 全框架仅四样不可替换：ArchLayer、地址解析器、Registry、EventBus |
| 地址字符串语义 | `address` / `name` / `name_or_address` / `literal` 四种字符串解读方式 |
| 附加配置子句 | 地址后的 `;key=value` 对，注入工厂的 `config` 参数 |
| defer_factory | 槽位工厂推迟到引擎装配期调用（agent_runtime 用） |
| 热挂载（remount） | 运行中替换槽位实现，无需重启进程 |
| nasyncio | 自研异步 IO 核心（不依赖标准 asyncio），默认事件循环实现 |
| LoopRuntime | 事件循环系统的协议接口（start / stop / submit / interrupt …） |
| 钩子（Hook） | 一个执行结构的命名事件，可订阅 / 改写（可变钩子）/ 否决（HookVeto） |
| 钩子层（HookLayer） | 钩子的分组（9 个标准层 + 自定义层 + dynamic 层） |
| HookVeto | 可变钩子抛出的一票否决异常，运行时按执行点语义安全收尾 |
| 注册表（Registry） | 名字 → 组件的映射中心；一切皆注册项 |
| 事件总线（EventBus） | 组件间事件传递通道；写时复制 + 无锁迭代 |
| 预设（Preset） | 声明式装配：槽位不填时的默认组合（六种内置模式） |
| 协议（Protocol） | 组件的接口契约（ModelProvider / Tool / SessionManager / Sandbox …） |
| 沙箱（Sandbox） | 工具执行的隔离边界（subprocess / pooled / isolated_python） |
| PTC | Programmatic Tool Composition：模型生成 Python 代码组合多步工具调用 |
| FTS5 | SQLite 全文索引引擎，上下文库的底层存储 |
| 快照（Snapshot） | 系统状态的序列化存档（架构槽位 + 运行时参数 + WebUI 设置） |
| 最后正常快照 | 引擎启动成功 30 秒健康期后自动标记的正常版本，救援 CLI 的一键恢复目标 |
| 崩溃救援（Rescue） | `norpagent-rescue`：主程序起不来也能回退快照的纯标准库 CLI |
| 安全模式（Safe Mode） | `npa(safemode="on")`：只加载最小化内核，跳过全部插件 |
| 人类救援（Human Rescue） | 模型失效时人工接管：`norpagent-rescue tools / tool-call / manual / serve` 手动传参调用全部工具并读取原始结果 |
| 安全套件（SafetyKit） | `norpagent.safe()` 安装的安全策略集合（审批 / 网络 / 插件 / 防护 API） |
| 插件安全管线 | 签名 → 审计 → 导入限制 → 注册 的插件加载全流程 |
| FLOW | 模块流程编排：可视化画布对接真实注册表（节点 + beam 拓扑执行） |
| 文件即模块 | 拖入 .py / .json / .yaml 即注册为画布模块（.py 走插件安全管线） |
| 前端模块（FE） | `/flow` 页面可加载的 .html / .js / .ts 前端扩展 |
| SSE 背压 | 每连接有界缓冲，慢客户端丢事件不丢内存（三策略可热改） |
| 写时复制（COW） | 订阅者表不可变快照 + 引用替换，emit 无锁迭代 |

---

## 附录 E　29 钩子事件负载速查表

> 每个钩子的 `payload_keys` 即事件负载字段；可变钩子的返回语义见 9.3 节与 `test/docs/hooks.md`。

### L1 运行时生命周期

| 钩子 | 可变 | payload_keys |
|---|---|---|
| `on_agent_init` | - | `preset` |
| `on_agent_shutdown` | - | `preset` |

### L2 任务生命周期

| 钩子 | 可变 | payload_keys |
|---|---|---|
| `on_task_start` | - | `task_id`, `session_id`, `preset`, `user_input` |
| `on_task_done` | - | `task_id`, `session_id`, `content`, `steps`, `context` |
| `on_task_error` | - | `task_id`, `error` |
| `on_task_stopped` | - | `task_id`, `reason` |
| `on_task_timeout` | - | `task_id`, `timeout`, `kind` |

### L3 输入管线

| 钩子 | 可变 | payload_keys |
|---|---|---|
| `before_input` | ✅ | `task_id`, `user_input`, `session_id`, `params` |
| `after_input` | - | `task_id`, `user_input`, `session_id` |
| `on_user_input_required` | - | `question`, `default` |

### L4 会话与历史

| 钩子 | 可变 | payload_keys |
|---|---|---|
| `before_session_create` | ✅ | `session_id`, `title`, `params`, `task_id` |
| `after_session_create` | - | `session_id`, `title`, `task_id` |
| `before_message_append` | ✅ | `session_id`, `message`, `task_id` |
| `after_message_append` | - | `session_id`, `message`, `task_id` |

### L5 消息组装

| 钩子 | 可变 | payload_keys |
|---|---|---|
| `before_build_messages` | ✅ | `system_prompt`, `session_id`, `step`, `task_id`, `tool_names` |
| `after_build_messages` | ✅ | `messages`, `system_prompt`, `step`, `task_id` |

### L6 步骤

| 钩子 | 可变 | payload_keys |
|---|---|---|
| `before_step` | ✅ | `task_id`, `step`, `messages`, `context`, `params` |
| `after_step` | - | `task_id`, `step`, `content`, `tool_calls` |

### L7 模型调用

| 钩子 | 可变 | payload_keys |
|---|---|---|
| `before_model_call` | ✅ | `task_id`, `step`, `messages`, `tool_schemas`, `params` |
| `after_model_call` | ✅ | `task_id`, `step`, `output` |
| `on_reasoning` | - | `task_id`, `content`, `stream` |
| `on_content` | - | `task_id`, `content`, `stream`, `final` |
| `on_event` | - | `event_type`, `data`, `task_id` |
| `on_usage_update` | - | `task_id`, `input`, `output`, `total` |

### L8 工具调用

| 钩子 | 可变 | payload_keys |
|---|---|---|
| `before_tool_call` | ✅ | `task_id`, `tool_name`, `args`, `context` |
| `after_tool_call` | ✅ | `task_id`, `tool_name`, `args`, `result`, `success`, `context` |
| `on_tool_error` | - | `task_id`, `tool_name`, `error`, `args` |

### L9 结果定型

| 钩子 | 可变 | payload_keys |
|---|---|---|
| `before_result` | ✅ | `task_id`, `result` |
| `after_result` | ✅ | `task_id`, `result` |

> 插件加载管线另有 8 个钩子（`PLUGIN_PIPELINE_LAYER`：`before_plugin_load` /
> `after_plugin_register` 等），见 11.4 节；FLOW 编排另有 `flow.*` 事件（第 20.5 节）。

---

## 附录 F　前后端通讯方式速查表

> 「前端」= 用户界面侧（Web UI / 控制台 / 自定义前端 / 外部进程）；
> 「后端」= 框架进程内（引擎 / 注册表 / 事件总线 / 工具）。

### F.1 通讯通道总览

| 通道 | 方向 | 传输 | 用途 | 章节 |
|---|---|---|---|---|
| HTTP REST | 前端 → 后端 | TCP（默认 127.0.0.1:8787） | Web UI 提交任务 / 查询 / 配置 | 22.2 |
| SSE 事件流 | 后端 → 前端 | HTTP 长连接 | 流式输出 / 任务状态实时推送 | 22.3 |
| 事件总线（进程内） | 任意组件 ↔ 任意组件 | 进程内存（写时复制 + 无锁迭代） | 钩子 / UI / 插件 / 引擎解耦通讯 | 9.5 / 27.2 |
| CLI 参数与 stdin/stdout | 人 ↔ 框架 | 命令行 | REPL / 单次任务 / 管理命令 | 13 / 附录 G |
| HTTP API（救援） | 操作员 ↔ 救援环境 | TCP（默认 127.0.0.1:8799） | 模型失效时手动操作工具 | 15.6.2 |
| 文件（快照 / 回退目标） | 框架 ↔ 磁盘 | JSON 文件 | 崩溃救援 / Undo/Redo | 15.2 / 15.4 |
| 子进程管道 | 框架 ↔ 沙箱子进程 | stdio | 工具执行隔离（exec_cmd / run_python） | 8.2 / 24.2 |
| 自管道 socketpair | 循环线程 ↔ 外部线程 | 进程内 fd | nasyncio 跨线程唤醒 | 24.2.1 |
| IPC（视觉 / 插件隔离） | 主进程 ↔ 宿主子进程 | 进程间（RPC） | 插件进程隔离、视觉助手 | 11.7 |

### F.2 Web 前端 ↔ 后端（HTTP REST）

默认端口 8787（`--port` / `config={"web":{"port":N}}` 可改）。全部端点：

| 方法 + 路径 | 说明 |
|---|---|
| `GET /` | 主页面（front.html） |
| `GET /flow` | 模块流程画布页 |
| `GET /farstars` | FarStars 星轨控制台（norp-farstars.html；别名 `/farstars.html`、`/norp-farstars.html`） |
| `POST /chat` | 提交任务：body `{"text": "...", "session_id": "..."}` |
| `GET /api/status` | 引擎状态 / 预设 / 工具数 |
| `GET /api/tools` | 工具 schema 清单 |
| `GET /api/sessions` | 会话列表 |
| `GET /api/history?session_id=...` | 会话历史 |
| `GET /api/config` / `POST /api/config` | 配置读取 / 保存 |
| `GET /api/models` | 可用模型与凭据状态 |
| `POST /api/model` | 切换模型 |
| `GET/POST /api/snapshots` | 快照时间线 / 手动快照 |
| `POST /api/undo` / `POST /api/redo` / `POST /api/rollback` | 工作回退 |
| `POST /api/upload` | 文件上传（受限扩展名） |
| `POST /api/cancel` | 取消在途任务 |
| `POST /api/vision` | 图片理解（v0.9.9，多模态，第 29 章） |
| `POST /api/tts` | 文本 → 语音 wav（v0.9.9，多模态） |
| `POST /api/stt` | 语音 wav → 文本（v0.9.9，多模态） |
| `POST /api/beep` | 提示音 wav（v0.9.9，多模态） |
| `GET /api/plugins` | 插件表（完整状态：失败原因 / 禁用 / 签名 / 隔离 / 警告 / 诊断） |
| `GET/POST/DELETE /api/plugins/dirs` | 插件目录查询 / 添加 / 移除 |
| `POST /api/plugins/reload` | 重载全部插件 |
| `POST /api/plugins/toggle` | 启用 / 禁用单个插件（持久化） |
| `POST /api/plugins/remove` | 卸载单个插件（删除文件，路径受限） |
| `POST /api/plugins/upload` | 上传安装单文件插件（.py，base64） |

详细响应格式见 22.2（REST API 总表）。

### F.3 SSE 事件流（后端 → 前端）

`GET /api/events` 建立 SSE 长连接，事件名与进程内事件一一对应：

| SSE 事件 | 触发时机 | 主要字段 |
|---|---|---|
| `on_task_start` | 任务开始 | task_id, user_input |
| `on_reasoning` | 思维链增量 | content |
| `on_content` | 正文增量 | content, final |
| `on_tool_call` | 工具调用 | tool_name, args |
| `on_task_done` | 任务完成 | task_id, content, steps |
| `on_task_error` / `on_task_stopped` | 任务异常 / 停止 | task_id, error/reason |
| `on_usage_update` | token 用量 | input, output, total |

> 实现细节：SSE 有界队列 + 批量 flush（14.3 / 23.2）；页面 JS 在
> `front.html` 中（5.4 / 22.5）。

### F.4 进程内事件总线（GeneralEventBus）

所有组件（引擎 / UI / 插件 / 钩子）在**同一进程**内通过事件总线通讯：
`emit`（广播）/ `intercept`（可变分发 + 否决）/ `emit_all`（收集返回值），
订阅 API `subscribe` / `once` / `wait`。29 个标准钩子事件负载见附录 E；
外部脚本集成见第 28 章。

### F.5 命令行（人 ↔ 框架）

| 场景 | 命令 |
|---|---|
| 启动 Web UI | `norpagent --mode standard --ui web --port 8787` |
| 命令行 REPL | `norpagent --mode standard`（ui=console 时） |
| 单次任务 | `norpagent --mode ptc --prompt "..."` |
| 编程等价 | `npa()` / `npa.submit(text)` |

详见第 13 章与附录 G。

---

## 附录 G　全部命令用法速查表

### G.1 norpagent 主命令

```bash
norpagent --list-modes                                   # 列出预设模式
norpagent --mode <名>                                    # 交互 REPL（命令行前端）
norpagent --mode <名> --prompt "<文本>"                   # 单次任务
norpagent --mode-file <file.py>                          # 自定义模式文件
norpagent --mode standard --ui web --port 8787           # Web UI
norpagent --model <已注册模型名>                           # 覆盖模型
norpagent --model-name <远端模型> --base-url <端点> --api-key <key>
norpagent --session sqlite --call-timeout 120            # 会话后端 / 调用超时
norpagent --plugin-dir ./dir [--plugin-isolation auto|inproc|process]
norpagent --safe basic|standard|high [--safe-hooks]      # 安全策略
norpagent --safe-mode                                    # 安全模式（最小内核）
norpagent unbox                                          # 成品发行版入口：一键拉起开箱即用软件（第 31 章）
norpagent unbox --smoke                                  # 成品自检（装配 → 健康检查 → 退出）
norpagent unbox --cnb --cnb-port 17811                   # 成品携带 CNB（端口必配，R-025）
norpagent plugin-sign --gen                              # 生成签名密钥对
norpagent plugin-sign <plugin.py> --key <私钥hex>          # 签名插件文件
norpagent plugins list --plugin-dir ./dir                # 插件表（失败 / 禁用 / 警告全可见）
norpagent plugins run <命令> [参数...] --plugin-dir ./dir  # 运行插件注册的 CLI 命令（33.8）
norpagent plugins list --plugin-dir ./dir --plugin-disabled <名>  # 模拟禁用名单
```

### G.2 norpagent-rescue 快照命令（纯标准库）

```bash
norpagent-rescue list                     # 时间线（★ = 最后正常快照）
norpagent-rescue show <id> [--last-good]  # 查看快照（敏感键脱敏）
norpagent-rescue rollback <id>            # 回退到指定快照
norpagent-rescue rollback --last-good     # 一键回退到最后一个正常快照
norpagent-rescue mark-good <id>           # 标记快照为「正常」
norpagent-rescue prune --keep N           # 只保留最近 N 个快照
```

### G.3 norpagent-rescue 人类接管命令（需框架可导入）

```bash
norpagent-rescue tools [--workspace WS] [--tools A,B] [--plugin-dirs D1,D2]
norpagent-rescue tool-call <工具名> --args '<json>' [--timeout N] \
    [--workspace WS] [--tools A,B] [--plugin-dirs D1,D2]
norpagent-rescue manual [--workspace WS] [--tools A,B] [--plugin-dirs D1,D2]
norpagent-rescue serve [--port 8799] [--host 127.0.0.1] [--token T] \
    [--workspace WS] [--tools A,B] [--plugin-dirs D1,D2]
```

共享参数：`--workspace`（文件工具根目录）、`--tools`（逗号分隔的已注册
工具名或 `pkg.mod:attr` 模块地址）、`--plugin-dirs`（逗号分隔插件目录）、
`--context-db`（上下文库路径）。手动交互台内置命令：`/tools` `/help` `/exit`。

### G.4 常用组合速查

```bash
# 模型死了，手操工具
norpagent-rescue tools
norpagent-rescue tool-call echo --args '{"text":"ping"}'
norpagent-rescue serve --port 8799 --token my-secret

# 自定义工具 + 插件工具一并手操
norpagent-rescue serve --tools myapp.tools:create --plugin-dirs ./my_plugins

# 主程序起不来：回退到最后正常快照后重启
norpagent-rescue list
norpagent-rescue rollback --last-good
norpagent --safe-mode        # 仍起不来时用安全模式

# 启动失败自救提示（CLI 自动打印）
#   1) norpagent --safe-mode
#   2) norpagent-rescue rollback --last-good
#   3) 重启（自动消费回退目标）
#   4) 模型失效 -> norpagent-rescue tools / manual / serve
```

---

## 附录 H　全部函数及结构用法速查表

> 按模块分组；`→` 后为返回值。省略号表示可选参数，完整签名以
> `inspect.signature` 与源码为准。速查用，细节见正文对应章节。

### H.1 顶层：`import norpagent as npa`

| 符号 | 签名摘要 | 说明 | 章节 |
|---|---|---|---|
| `npa()` | `launch(**槽位参数) → NorpEngine` | 启动引擎（模块即入口） | 6 |
| `npa.stop()` | `() → bool` | 生命周期轮询：应退出返回 True | 6 |
| `npa.submit(text, session_id=None)` | `→ RunResult` | 向当前引擎提交任务 | 6 |
| `npa.remount(**slot_values)` | `→ NorpEngine` | 运行中热挂载任意槽位 | 3.7 |
| `npa.nasyncio(address=None, **config)` | `→ LoopRuntime` | 事件循环架构函数 | 4 |
| `npa.shutdown()` / `npa.current()` | — | 关闭引擎 / 取当前引擎 | 6 |
| `npa.undo()` / `npa.redo()` / `npa.rollback(id)` | `→ dict` | 工作回退 | 15.2 |
| `npa.snapshot_system(**kw)` | `→ dict` | 手动快照 | 15.2 |
| `npa.list_snapshots()` / `npa.mark_good_snapshot(id)` | — | 快照管理 | 15.2 |
| `npa.safe(reg, level=..., hooks=..., config=...)` | `→ SafetyKit` | 挂载安全策略 | 10 |
| `npa.Registry()` / `npa.EventBus()` / `npa.Preset(...)` | 内核结构 | 见 H.2 | 27 |
| `npa.install_defaults(reg)` / `npa.install_core(reg)` | — | 内置组件装配 | 2.3 |
| `npa.register_slot(spec, replace=False)` / `npa.unregister_slot(name)` | — | 槽位表热插拔 | 3.8 |
| `npa.snapshot_slots()` / `npa.is_builtin_slot(name)` | — | 槽位表查询 | 3.8 |

### H.2 内核结构（`norpagent.kernel`）

| 结构 | 成员 / 方法摘要 | 说明 |
|---|---|---|
| `Registry` | `register_model/tool/session/sandbox/scheduler/ui/plugin/preset/component`；`resolve_*`；`build_session/sandbox/scheduler/component`；`list_*`；`tool_schemas(names=None)`；`validate_preset(p)`；`.bus`；`.hooks`；`.security` | 组件注册中心（9 大命名空间） |
| `EventBus` | `subscribe(fn, type=None)` `once(fn, type=None)` `unsubscribe(fn, type=None)` `emit(type, **kw)` `intercept(type, **kw)` `emit_all(type, **kw) → list` `wait(type, timeout=None) → AgentEvent\|None` `subscriber_count(type=None) → int` `has_listeners(type=None) → bool` `clear(type=None) → int` `set_error_logger(cb)` | 通用事件总线（27.2） |
| `EventType` | 16 个标准事件名枚举 | 27.2.5 / 附录 E |
| `AgentEvent` | `.type` `.payload` `.ts` `.get(key, default=None)` | 27.2.1 |
| `HookVeto(reason="...")` | 一票否决异常（intercept 不捕获） | 9.3 |
| `Preset(name, model, tools, session, sandbox, scheduler, ui, mode, params, components)` | 预设声明 | 12 |
| `RunContext` | `.registry .session_manager .session_id .sandbox .scheduler .ui .params .task_id .preset_name .components`；`component(kind)` `context_store` `project_manager` `task_store` `ask_user(q, default)` | 任务运行环境句柄（8 章 / 25.2.3） |
| `AgentRuntime` | `run(user_input, session_id=None, task_id=None, task_params=None)`；`shutdown()`；`.registry .preset .hooks`；可覆写：`prepare_input/create_session/append_message/build_messages/call_model/execute_tool_call/finalize_result` | Agent 循环本体（9.6） |
| `RunResult` | `.ok .status .final_content .session_id .steps .error .tool_calls` | 任务结果 |

### H.3 钩子系统（`norpagent.hooks`）

| 符号 | 签名摘要 | 说明 |
|---|---|---|
| `Hook` | `subscribe(fn, system=None)` `unsubscribe(fn, system=None)` `emit(system=None, **kw)` `intercept(system=None, **kw)` `bind(bus)`；属性 `.name .layer .order .mutating .payload_keys` | 钩子独立 API（9.2） |
| `BoundHook` | 同 Hook 四方法（免 system）；属性同 | 绑定总线的运行时钩子（9.8） |
| `HookLayer(name, order=0, description="")` | `.hook(name, mutating=False, description="", payload_keys=(), order=0) → Hook` `.names()` | 自定义层（9.4） |
| `HookSystem(bus, install_standard=True)` | `install_layer(layer)` `define_hook(...)` `hook(name)` `get(name)` `list_hooks()` `list_hook_names()` `layers()` `layer_of(name)`；属性访问 `hooks.<name>` | 总线上的钩子视图（9.4） |
| 29 个标准钩子 | `from norpagent.hooks import before_model_call, ...` | 附录 B / E / 9.8 |
| `get_default_system()` | `→ HookSystem` | 模块级 API 缺省落点 |

### H.4 架构层（`norpagent.arch`）

| 符号 | 签名摘要 | 说明 |
|---|---|---|
| `ArchLayer(slot_specs=None, config=None)` | `connect()` `remount(slot, value)` `describe()` `set_default(slot, factory)` `subconfig(slot)` `__getitem__(slot)` `get(slot, default)`；`.config` `.impls` | 槽位连接器（27.4） |
| `SlotSpec` | 字段：`name description protocol default_address string_semantics factory_kwargs examples defer_factory applier remount_rebuild_agent` | 槽位规格（3.8 / 25.10.2） |
| `resolve_address(address, *, slot)` | `→ 实现对象` | 地址解析（3.2 / 27.3） |
| `is_address_like(s)` | `→ bool` | 纯结构判定（27.3.4） |
| `register_slot(spec, replace=False)` | `→ SlotSpec` | 槽位表热插拔（3.8） |
| `snapshot_slots()` / `all_slot_names()` / `is_builtin_slot(name)` / `unregister_slot(name)` | — | 槽位表查询与注销 |

### H.5 运行时（`norpagent.runtime`）

| 符号 | 签名摘要 | 说明 |
|---|---|---|
| `NorpEngine` | `.async_loop .registry .preset .state .arch_layer`；`submit(text, session_id=None)` `request_stop()` `wait(timeout)` `join()` `shutdown()` | 引擎对象（6.2） |
| `launch(**kw) → NorpEngine` | 装配并启动 | 6.1 |
| `remount(**slot_values) → NorpEngine` | 热挂载 | 3.7 |
| `submit(text, session_id=None)` / `stop()` / `current()` / `shutdown()` / `is_running()` | — | 模块级运行时 API |

### H.6 工作回退与救援

| 符号 | 签名摘要 | 说明 |
|---|---|---|
| `snapshot_system(**kw) → dict` / `undo()` / `redo()` / `rollback(id)` | 快照三件套 | 15.2 |
| `list_snapshots()` / `mark_good(id)` / `last_good_id()` / `set_snapshot_dir(dir)` / `register_snapshot_provider(fn)` | 快照管理 | 15.2 / 15.3 |
| `RescueToolEnvironment(workspace_root=None, sandbox="subprocess", session="memory", scheduler="persistent", scheduler_db=None, context_db=None, with_components=True, params=None, extra_tools=None, tools=None, plugin_dirs=None, plugin_config=None)` | `inventory() → list` `call_tool(name, args, timeout=None, params=None) → dict` `close()` | 人类救援环境（15.6.3） |
| `RescueToolAPI(env=None, port=8799, host="127.0.0.1", token=None)` | `start() → int` `shutdown()` `page_html()` | 救援 HTTP API（15.6.2） |

### H.7 插件（`norpagent.plugins`）

| 符号 | 签名摘要 | 说明 |
|---|---|---|
| `PluginSystem(registry, plugin_dirs=None, config=None)` | `load()` `reload(name)` `unload(name)` `status()` `shutdown()` `configure(cfg)` | 插件门面（11.1） |
| `install_plugin_dirs(reg, dirs, config=None) → PluginLoader` | 一次性加载 | 11.1 |
| `PluginAPI`（`setup(api)` 门面） | `register_tool / register_slot / register_component / register_model / register_session / register_sandbox / register_scheduler / register_ui / define_hook / subscribe / emit / provide / get / mount_page / register_cli_command / register_settings / get_setting / set_setting` | 33.8 |
| `PluginInfo` | 字段全表（`enabled / error / warnings / signature_status / isolation / capabilities / requires / diagnostics / counts` ...） | 33.12.1 |
| `PluginLogger` | `debug / info / warn / error`（stdout + 日志文件） | 33.6 |
| `LEGACY_HOOK_NAMES` / `NATIVE_HOOK_NAMES` | 16 个兼容 / 29 个原生钩子名单 | 33.5 |
| `PluginCapabilityError` | 能力门禁异常（setup 超声明调用） | 33.8.1 |
| 管线钩子 | `PLUGIN_PIPELINE_LAYER` + 8 个 `before/after_plugin_*` | 11.4 |

### H.8 内置组件（`norpagent.builtin`）

| 分类 | 已注册名 | 说明 |
|---|---|---|
| 模型 | `mock` `openai_compat` `anthropic` | 21.1 |
| 工具（20 个） | `echo get_time run_python file_read file_write file_list file_delete exec_cmd web_search web_fetch web_extract_links context_add context_search context_list context_delete project_status task_submit task_list task_status task_cancel` | 21.2 |
| 会话 | `memory` `sqlite` | 21.3 |
| 沙箱 | `subprocess` `pooled` | 21.4 |
| 调度器 | `simple` `persistent` | 21.5 |
| UI | `console` `web` | 5 / 22 |
| 组件 | `context_store=fts5` `project_manager=basic` | 21.6 / 21.7 |

### H.9 事件循环（`norpagent.nasyncio` / `norpagent.loops`）

| 符号 | 签名摘要 | 说明 |
|---|---|---|
| `nasyncio.EventLoop` | `run_forever()` `run_until_complete(coro)` `stop()` `abort_main()` `call_soon_threadsafe(cb)` `create_task(coro)` `create_future()` `call_later(delay, cb)` `close()` | 自研循环内核（24.2.1） |
| `nasyncio.run_coroutine_threadsafe(coro, loop) → Future` | 跨线程提交协程 | 24.2.4 |
| `LoopRuntime` 协议 | `start()` `stop()` `submit(fn)` `run_async(coro)` `interrupt()` `join(timeout)` `is_running()` | 4.2 |
| `NasyncioLoopRuntime(config=None)` | async_loop 槽位默认实现 | 4.3 |

---

## 附录 I　多模态配置与 API 速查

> v0.9.9。多模态 = 视觉（图片理解）+ 声音（TTS 朗读 / STT 输入 / 提示音）。
> 全部后端原生实现（`builtin/ui/multimodal.py`，纯标准库），浏览器只采集与播放。
> 详细说明见第 29 章。

### I.1 配置键速查（设置面板 → 视觉 API / 声音）

| 配置键 | 默认 | 位置 | 说明 |
|---|---|---|---|
| `vision_enabled` | false | 视觉 API | 启用图片理解 |
| `vision_service_url` | "" | 视觉 API | 外部视觉服务地址（协议见 29.2.3） |
| `tts_enabled` | true | 声音 | 启用语音朗读 |
| `tts_service_url` | "" | 声音 | OpenAI 兼容 `/audio/speech`（留空 = 系统原生） |
| `tts_service_api_key` | "" | 声音 | TTS Key（DPAPI 加密） |
| `tts_voice` | "" | 声音 | 语音名（Windows SAPI / OpenAI voice） |
| `tts_rate` | 1.0 | 声音 | 语速 0.5–2.0× |
| `stt_service_url` | "" | 声音 | OpenAI 兼容 `/audio/transcriptions`（留空 = Windows 本地识别） |
| `stt_service_api_key` | "" | 声音 | STT Key（DPAPI 加密） |
| `stt_language` | "en-US" | 声音 | 识别语言（zh-CN 需 Windows 中文语言包） |
| `sound_notify_enabled` | true | 声音 | 新消息提示音 |
| `auto_speak_enabled` | false | 声音 | 自动朗读助手回复 |

### I.2 端点速查

| 端点 | 方法 | 请求 | 响应 |
|---|---|---|---|
| `/api/vision` | POST | `{images:[{name,type,data(base64)}], prompt}` | `{ok, descriptions:[{name,description}]}` |
| `/api/tts` | POST | `{text, voice, rate}` | `{ok, audio_base64, mime:"audio/wav"}` |
| `/api/stt` | POST | `{audio(wav base64), mime}` | `{ok, text}` |
| `/api/beep` | POST | `{}` | `{ok, audio_base64, mime:"audio/wav"}` |
| `/api/upload` | POST | `{files:[{name,type,data}]}` | `{files:[{kind:"image"|"text", …}]}`（v0.9.9 支持图片） |

### I.3 系统原生 TTS / STT 引擎

| 平台 | TTS | STT | 备注 |
|---|---|---|---|
| Windows | SAPI（System.Speech，PowerShell） | SAPI 本地识别（DictationGrammar） | 中文 TTS 内置（如 Huihui）；中文 STT 需语言包 |
| macOS | `say`（LEI16@22050 → WAV） | —（需配置服务） | — |
| Linux | `espeak-ng` / `espeak` | —（需配置服务） | 未安装时报明确错误 |

### I.4 外部服务协议（OpenAI 兼容）

```text
TTS: POST {tts_service_url}
     {"model":"tts-1","input":text,"voice":voice,
      "response_format":"wav","speed":rate}
     Authorization: Bearer <tts_service_api_key>（可选）

STT: POST {stt_service_url}（multipart/form-data）
     file=audio.wav（16kHz 单声道 wav），model=whisper-1，language=<stt_language>
     Authorization: Bearer <stt_service_api_key>（可选）
```

---

## 附录 J　中枢神经总线速查表

> CNB/1.0 多实例神经树：中枢控制任意层级任意单位原子的操作权限；低层级只能上报，不可控制上层。详细说明见第 30 章，独立设计文档见 `NERVOUS_BUS.md`。

### J.1 等级与常量

| 常量 | 值 | 含义 |
|---|---|---|
| `LEVEL_CORTEX` | 0 | 中枢（根，最高等级） |
| `LEVEL_DIRECTOR` | 1 | 指挥部 / 小组级 |
| `LEVEL_AGENT` | 2 | 智能体级 |
| `LEVEL_ATOM` | 3 | 原子级（默认） |
| `LEVEL_MAX` | 63 | 等级上限 |
| `DEFAULT_CORTEX_PORT` | 17800 | 中枢默认总线端口 |
| `DEFAULT_HOST` | 127.0.0.1 | 默认仅本机回环 |

### J.2 消息类型

| 方向 | 类型 |
|---|---|
| 上行（只读） | `report.register` `report.heartbeat` `report.event` `report.audit` `report.request` `report.deregister` |
| 下行（控制） | `cmd.hello` `cmd.ping` `cmd.exec` `cmd.stop` `cmd.reload` `cmd.perm.set` `cmd.perm.grant` `cmd.perm.revoke` `cmd.topology.sync` `cmd.reroot`（父链断链救援改挂） |

### J.3 权限原子

`file_read` `file_write` `file_delete` `file_list` `process_exec` `process_shell` `network_out` `network_in` `system_info` `plugin_call`

### J.4 CLI 速查

> v1.0.7 起 CNB 内核化：主路径为 `python -m norpagent.cnb.cli ...`（等价
> `norpagent ...`，同参数）；旧路径 `python -m nervous_bus.cli ...` 经兼容
> shim 仍可用。v1.0.7 起 `cortex`/`node` 进程**默认装配完整内核引擎**
> （`--bare` 回到纯神经空壳；`--mode <预设>` / `--model <模型>` 可换）。

| 命令 | 说明 |
|---|---|
| `norpagent cortex --port 17800 --repl` | 启动中枢（引擎=on；等价 `python -m norpagent.cnb.cli cortex ...`、`python main.py --norp-cortex --port 17800 --repl`） |
| `norpagent node --id norpbot-01 --kind bot --parent http://127.0.0.1:17800 --port 17801 --level 3` | 挂载节点（引擎=on；等价 `python -m norpagent.cnb.cli node ...`、`python main.py --norp-node ...`） |
| `... topo --root <中枢地址>` | 查看拓扑树 |
| `... tree validate\|show\|up --def <定义>` | 神经树显式定义：校验 / 展示 / 拉起整树（inproc 或 spawn；不预设形状；§30.19） |
| `... ping --root ... --node <id>` | 探活 |
| `... exec --root ... --node <id> --action <动作> [--args '{}'] [--perm process_exec]` | 下发执行指令（动作 = 内核动作面：`run_task`/`status`/`stop_task`/`task_records`/`engine_state`/`inspect`/`snapshot`/`rollback`/`undo`/`redo`/`list_snapshots`/`mark_good`/`remount`/`reload_plugins`/`stop_engine`，见 §30.16.3；另有节点槽位动作 `slot_list`/`slot_describe`/`slot_mount`/`slot_unmount`，见 §30.18） |
| `... stop / reload --root ... --node <id>` | 停全部会话任务（实例保持运行）/ 重载配置与插件 |
| `... perm --root ... --grant\|--revoke\|--set --target-type node_id\|node_kind\|* --target <目标> --perm <原子> [--scope '{}'] [--allows '{}']` | 权限控制 |
| `... reports / audit --root ... [--n 20]` | 查看上报 / 审计（reports 显示心跳携带的 `engine_state`/`active_tasks`/`version`） |
| `... sync --root ...` | 中枢广播拓扑 |
| `... sweep --root ...` | 手动触发一次失联清扫 + 救树 |

> 通用槽位（R-024 / R-025，§30.18）：每节点 ≤64 槽位；`slot_list` / `slot_describe`（只读）、`slot_mount` / `slot_unmount`（变更；冻结期拒绝）；完整实例模块 `NorpAgentModule`（kind=`norpagent-instance`）由代码挂载（`node.mount_module`）；`CnbAdapter` 自动挂载默认槽位 `norpagent`，心跳携带 `slots.count` / `slots.free`。

### J.5 中枢控制端点 /cnb/ctrl

`POST {中枢地址}/cnb/ctrl`，body 为 `{"op": ...}`：

| op | 关键参数 | 说明 |
|---|---|---|
| `topo` | — | 拓扑视图 |
| `nodeinfo` | `node` | 节点详情 |
| `ping` / `stop` / `reload` | `node` | 探活 / 停止 / 重载 |
| `exec` | `node` `action` `args` `perm` `path` | 执行指令 |
| `grant` / `revoke` | `target_type` `target` `perm` `scope` | 授予 / 撤销权限 |
| `set` | `target_type` `target` `allows` | 整体覆盖权限 |
| `sync` | — | 拓扑广播 |
| `sweep` | — | 手动触发一次失联清扫 + 救树（中枢 REPL 同有 `sweep` 命令） |
| `reports` / `audit` | `n` | 上报 / 审计记录 |

总线端点：`POST /cnb/msg`（消息投递）、`GET /cnb/health`（健康检查）、`GET /cnb/reports`（上报记录）。

### J.6 环境变量（普通实例自动挂载，v1.0.2+）

> 契约：设置 `NORP_CNB_NODE` 即启用自动挂载；`NORP_CNB_MANAGED=1` 内核跳过（上层 managed 自建，防双重挂载）。只认环境变量，不读 config.json。详见 §30.8。

| 环境变量 | 默认 | 说明 |
|---|---|---|
| `NORP_CNB_NODE` | 空（设置即启用） | 节点 id |
| `NORP_CNB_KIND` | `agent` | 原子类型 |
| `NORP_CNB_LEVEL` | `3` | 等级（须大于父级） |
| `NORP_CNB_PARENT` | `http://127.0.0.1:17800` | 父节点总线地址 |
| `NORP_CNB_PORT` | `17801` | 本节点总线端口 |
| `NORP_CNB_HEARTBEAT` | `5.0` | 心跳间隔（秒） |
| `NORP_CNB_DESC` | 空 | 节点 meta 描述 |
| `NORP_CNB_MANAGED` | 未设置 | `1` = 跳过内核挂载 |
| `NORP_CNB_TREE` | 空 | 神经树定义（JSON / PY 路径或 JSON 文本）；整树形状由定义携带（§30.19） |

状态查询：`engine.cnb_status`（`not-mounted` / `managed-skip` / `mounting` / `mounted` / `failed` / `stopped` / `config-error`——配置错误显式报错且不加载神经树、宿主照常运行）；配置与装配错误内容经 `engine.cnb_error` 读取；`engine.cnb` 返回适配器（含 `status` / `perm_summary`）。中枢下行指令面：`exec`（动作白名单 `run_task`/`status`/`stop_task`）、`stop`、`reload`、`perm.*`，落地语义见 §30.8 四回调表。

### J.7 测试命令

```bash
# v2.0.0 实测全绿；nervous_bus 为兼容 shim（测试文件仍随 shim 包分发，命令不变）
python -m nervous_bus.test_cnb             # 60 项单元/集成自测（含权限面审计 T-A0~T-A6）
python -m nervous_bus.test_e2e             # 13 项真实多进程端到端（ROOT 自动定位仓库根）
python -m nervous_bus.test_deep_tree       # 36 项深树专项回归（4 层链：注册坍缩/上行汇聚/救树/清扫/权限时间序/心跳自愈/自动广播/缓存收敛）
python -m nervous_bus.test_cnb_v200      # 44 项 v2.0.0 新增能力验收（mol 通道/冻结态/行为基线/传票取证）
python -m nervous_bus.test_cnb_slots     # 51 项：通用槽位体系（R-024 / R-025：≤64 边界 / 动作冲突 / 事务性 / 实例模块）
python -m nervous_bus.demo                 # 同进程神经树演示
python test/test_cnb_automount.py          # 12 项：引擎 NORP_CNB_* 自动挂载验收冒烟（需 PYTHONPATH=src）
python test/test_cnb_kernel_actions.py     # 32 项：内核动作面验收 A 21 + B 11（v1.0.7 新增；需 PYTHONPATH=src）
python test/test_cnb_tree_suite.py         # 56 项：神经树显式定义验收（2026-09-12 反馈轮新增；需 PYTHONPATH=src）
```

### J.8 v2.0.0 新增命令面与常量（远星 FarStars）

```bash
# 冻结态（隔离冻结：拒新任务、保活取证）
norpagent freeze   --root http://127.0.0.1:17800 --node dev --reason "隔离处置"
norpagent unfreeze --root http://127.0.0.1:17800 --node dev --reason "复核通过"
# 行为基线分级
norpagent behavior --root http://127.0.0.1:17800          # 黄·复核 / 黑·隔离
# 传票取证（level 0 专属；basis 四类：confidence_low/vote_tie/
#   evidence_conflict/human_named；tier 64/128/256/512KB）
norpagent subpoena --root http://127.0.0.1:17800 --node rnd-01 \
    --basis evidence_conflict --tier-kb 128 --approved-by-human
norpagent subpoena_box   --root ... --subpoena-id <id> --destroy   # 读取即焚
norpagent subpoena_purge --root ... [--subpoena-id <id>]            # 用后即毁
norpagent subpoena_audit --root ...                                 # 签发留痕
# 任务分子验收回执（动作面 15 项新增 task_records）
norpagent exec --root ... --node dev --action run_task --args '{"prompt": "...", "task_params": {"mol_id": "..."}}'
norpagent exec --root ... --node dev --action task_records --args '{"mol_id": "..."}'
```

新下行指令：`cmd.freeze` / `cmd.unfreeze` / `cmd.subpoena`（协议 CNB/1.0
语义增量）。冻结白名单：`FROZEN_ALLOWED_ACTIONS`。传票常量：
`SUBPOENA_BASIS`（四判据）/ `SUBPOENA_TIERS_KB`（64/128/256/512）/
`SUBPOENA_MAX_KB`（512，超限强制转人工终裁）/ `SUBPOENA_ENVELOPE`
（`RAW/UNTRUSTED` 隔离帧）。品牌：`norpagent.__brand_cn__="远星"` /
`__brand_en__="FarStars"` / `__display_name__="FarStars（远星）· norpagent"`。

---

## 修订记录（历史版本）

> **版本约定（2026-09-12 反馈轮）**：本手册与全部活跃文档以当前发布版本 **2.2.1** 为代码基线；下方历史修订记录中的版本号仅表示当时的基线，不再代表现状；归档文档（旧版手册、历史更新摘录等）保持原样。
> **2026-09-12 v2.2.1 缺陷收口（R-032 / R-033）**：① **`ask_user` 工具补齐（R-033）**——内置工具面新增 `ask_user`，模型可通过工具调用主动向用户提问 / 澄清需求 / 确认危险操作（此前仅有 UI 适配器与内核审批链的内部机制，活跃工具集缺失该工具）；standard / ptc / longrun 预设与 `install_defaults` / `install_core` 两个装配入口均注册该工具；② **token 计数计入原始文本（R-032）**——端点未回传 usage 时，后端按**原始文本**（raw markdown / LaTeX 源码 + 提示词）估算 input + output（此前只统计渲染后的可见输出且缺 input，导致总 token 偏低）；估算值带 `estimated` 标记，前端以「≈」如实标注为估算；端点回传 usage 时仍以服务端数值为准。版本号统一升至 **2.2.1**。
> **2026-09-12 v2.2.1 反馈轮收口（前端统计口径 / 设置双语 / 滚动统一 / 即时停止 / 工作区清整）**：同一 2.2.1 版本内继续收口用户反馈轮问题（不另起版本号）——① **前端统计口径**：移除右上角恒为 0 的「0 tok」徽标，token / 速度估算纳入思考（think）与工具调用参数（tool，`toolCallTextOf`，不含工具返回结果）；② **设置项双语**：前端 `SET_ZH` / `SET_ZH_POINT` 词典覆盖全部 123 个非进化类设置键（进化点标题运行时组合），`settingRowHtml` 按语言渲染（英回退 schema、简中用词典、繁中回退简中）；③ **一键回到底部**：新增 `.msgs-wrap` 包裹层，按钮移出滚动容器 `#msgs`、稳定悬浮右下角；④ **打开会话滑动到底部**：`slideToBottom()` 逐帧 easeOutCubic 约 720ms，仅切换 / 打开会话触发；⑤ **滚动逻辑统一（对齐 `duo2.py`）**：粘性 `_userScrolled`（容差 10px）取代距离判据，自动滚动收敛到唯一入口 `scrollBottom(force, animate)`；⑥ **停止即时生效**：`web.py::_stop_events` 每会话取消事件表（`stop_task()` 同步 `set()`）+ 内核流式循环回传部分内容并以 `stopped` 收尾、部分回复落库；⑦ **工作区清整**：根目录 `_*` 产物 622 项移入 `test/`，本手册开头超长修订块移至文末「修订记录（历史版本）」。版本号保持 **2.2.1**。
> **2026-09-12 反馈轮（版本号统一 / asyncio 与 nasyncio 并存声明 / 自进化运行期加固 / CNB 神经树显式定义）**：① **版本号统一**——活跃文档一律以 **2.2.0** 为代码基线（见上「版本约定」；NERVOUS_BUS.md 的 2.0.0 等历史声明同步修正）；② **asyncio 与 nasyncio 并存**——标准库 `asyncio` 与自研 `norpagent.nasyncio` **互不冲突、可在同一进程内同时使用**（不依赖 = 不接管；详见 §4.7 与第 19 章 FAQ）；③ **自进化运行期加固**——激活后健康核验 + 失败自动回退、活跃版本巡检（`hotswap.verify_active`）、启动巡检与损坏自动回退熔断（`ProposalBoard.health_sweep`；详见 §32.9、§34.10）；④ **CNB 神经树显式定义**——CNB **不预设任何树形状**：启动时显式传入整树定义（每层 LEVEL、个数、低层父级、端口等必要参数，缺一即逐条显式报错），定义来源支持直接参数 / JSON 文件 / PY 文件；支持进程内整树与多进程真进程树两种装配；运行中可 `np.remount(cnb={"tree": ...})` 改形、可监视定义文件自动改形、自动收敛；npa 启动路径 CNB 配置错误**不阻塞启动**（显式报错 + 神经树不加载，`cnb_status=config-error`、`cnb_error` 可查）；新增 `norpagent tree validate|show|up` 子命令（详见 §30.19）。
> **2026-09-12 v2.2.0 三位一体全量落地 + 前端 V2（新增第 34 章）**：① **元框架态入口**——`norpagent.core`（最小内核四构件命名空间 + `register_slot / register_layer / register_hook` 注册三件套 + 裸装配路径）；② **成品态独立入口**——`norpagent/farstars_app/`（unbox 本体迁入、`norpagent.unbox` 兼容转发；用户态启动全量装配全部内置工具 `tools:"all"`）；③ **设置事实源**——内核动点全量清单（十一域）+ 四层继承语义（全局>档案>会话/任务>临时；不填=上级、三态可查）+ 运行态配置镜像桥 + `norpagent settings` CLI（Web/CLI/REST 三通道同源）；④ **白盒统一遍历**——`norpagent.whitebox` 按环节树统一 describe/audit_trail/settings 三件套 + 控制台「白盒总览」页；⑤ **进化闭环**——提案引擎（提案→裁决→执行→验证→固化）+ 熔断 + 2A 记忆 / 2B 技能 / 2C 配置执行器 + 控制台「提案中心」；⑥ **CNB 运行时热挂载**——`np.remount(cnb=...)` 挂载 / 替换 / 卸载；⑦ **前端 V2**（暖阳版）——左列选项卡设置布局、三视角（成品/框架/元框架）、悬停说明、总开关联动置灰、JSON 高级模式、Reasoning Effort 补 `xhigh`、工作区目录选择器、会话批量清除/清空、输入框内联模式/模型/工作区、三端共通 i18n（`/assets/i18n.js` · `np_lang`；主前端 / 星轨控制台 / FLOW 共通）。详见第 34 章。版本号统一升至 **2.2.0**。
> **2026-09-11 v2.1.0 插件系统专项（内核派发修复 + 插件能力全量扩展 + 新增第 33 章）**：① **内核钩子派发修复**——`before_step / before_tool_call / after_tool_call` 三处 emit+intercept 双派发收敛为单次调用（副作用不再翻倍、UI 不再双打印）；`EventBus.intercept` 升级为「遍历全部订阅者、首个非 None 生效」（多插件不再互截断）；② **插件桥接完整修复**——`PluginContext` 补齐 `logger / storage`（既有生态插件的核心依赖）；16 个兼容钩子签名逐参数对齐（`on_task_stopped` 支持 `(ctx)` 与 `(reason, ctx)` 自适应、`after_step` 补 `reasoning` 与完整 `tool_calls` 列表、`on_usage_update` 新旧双键名）；pass-through 返回规范化为不改写；钩子异常不再静默（首错打印 + 计数 + `diagnostics` 记录）；③ **29 钩子全开放**（16 兼容 + 13 原生）；④ **`setup(api)` 注册门面**——插件可注册动态工具 / 自定义槽位 / 组件 / 模型 / 会话 / 沙箱 / 调度器 / UI / 自定义钩子 / 事件订阅 / 服务 / Web 页面 / CLI 命令 / 设置项，能力声明门禁（`PLUGIN_CAPABILITIES`）；⑤ **生命周期与干净热重载**——`on_load / on_unload`、卸载真正退订与回收注册、单插件 `reload`；⑥ **依赖与版本声明**（`PLUGIN_REQUIRES / PLUGIN_MIN_NORPAGENT`）；⑦ **Web 插件面板升级**（完整状态 / 失败原因 / 签名 / 隔离 / 警告 / 诊断；启用禁用 / 卸载 / 上传安装）与 CLI `norpagent plugins list|run`；⑧ **新增第 33 章《插件开发完全指南》**（中英同步，含 29 钩子全表 / setup API 全表 / 完整教程 / 排错 / 迁移 / 发布清单）。版本号统一升至 **2.1.0**。
> **2026-09-11 增补（CNB 通用槽位 / 成品发行版入口 unbox / 自进化体系）**：① **CNB 通用槽位（R-024 / R-025 修订版）**——神经总线每一节点提供最多 **64 个通用槽位**，走总线可挂载 model / tools / plugins / 自定义模块；norpagent 完整实例不做抛弃：包装为标准可插拔模块 `NorpAgentModule`（kind=`norpagent-instance`），可插、可拔、可描述、可替换（详见 §30.18）；② **成品发行版入口 `norpagent unbox`（R-006 / R-014 / R-007）**——一键拉起开箱即用的自进化用户软件：单个功能强大的智能体 + Web 控制台 + 声明式装配档案；CNB 默认不携带、启用须手动配置端口（详见第 31 章）；③ **自进化体系（R-004 / R-005 / R-010 ~ R-012 / R-017）**——设置事实源（SQLite + JSON）、逐项勾选审批、代码热重载（不删原逻辑、可回退）、进化包 .fspack / 整合包 .zip、进化节奏与方向（详见第 32 章）；④ 版本号统一为 **2.0.1**（`pyproject.toml` / 主包 / CNB / recovery 同步）。
> **2026-09-05 v2.0.0（远星 FarStars 品牌定名 + 内核功能扩展）**：正式宣传名定为**远星 / FarStars**（norpagent 调用方式与内核名称不变，FarStars 仅作宣传名/品牌冠名，代码/导入/PyPI 包名保持 norpagent）。新增四组功能，见新专节 **§30.17**：① **任务分子通道**——exec `run_task` 的 `task_params` 结构化扩展：mol 六要素（mol_id/objective/acceptance/context_capsule/depends_on/budget/model_tier）JSON 原样承载直达原子吸收位，新增内核动作 `task_records` 提供验收回执数据面，audit/`task_started`/`task_done` 中 mol_id 贯穿可追溯、acceptance 随事件回传中枢；② **隔离冻结态**——新下行指令 `cmd.freeze`/`cmd.unfreeze`：冻结节点拒新任务（接单面关闭）、进程/心跳保活取证、可审计可解除、不触发清扫判 dead（心跳标记 frozen，中枢调度摘流量）；③ **行为基线内核侧聚合**——节点本地累计心跳缺失率/审计异常率/任务失败率，随心跳压缩上汇，中枢 `behavior_view` 按阈值分级（黄劣化/黑疑似恶意）；④ **subpoena 传票取证**——level 0 专属最高取证权限：新下行指令 `cmd.subpoena` 强制中间层原始审计直传中枢（非 2KB 摘要），五道闸（判据前置/隔离帧 RAW-UNTRUSTED/取数通道/容量分档 64-128-256-512KB/签发即留痕黑级），超 512KB 强制转人工终裁，低层级冒用拒绝并审计。
> **2026-09-05 v1.0.7（CNB 内核集成）**：① **结构并入**——中枢神经总线实现整体迁入内核子模块 `norpagent.cnb/`（protocol / topology / permissions / bus / node / cortex / cli / demo + 新增 engine 引擎绑定层），版本并入 norpagent（无独立版本号），`import norpagent` 即就绪（顶层 `norpagent.cnb` 与 `CnbAdapter` / `setup_cnb` / `KERNEL_ACTIONS` 直接可用）；旧独立包名 `nervous_bus` 保留为**兼容 shim**（re-export + sys.modules 子模块注入 + cli/demo 物理薄文件），1.0.6 及更早脚本 / 命令 / 测试零改动继续可用。② **能力面内核化**——`NervousNode` 新增 exec 动作注册表（`register_action` / `unregister_action` / `list_actions`），中枢 `cmd.exec` 的动作**优先路由到注册处理器**，旧回调钩子兜底，两者皆无才拒绝（未知动作应答契约升级：`ok=False` + 顶层 `error`）；引擎绑定层把 NorpEngine 公开 API 注册为 **14 项内核动作面**：任务面 `run_task`/`status`/`stop_task`，状态面 `engine_state`/`inspect`，快照面 `snapshot`/`rollback`/`undo`/`redo`/`list_snapshots`/`mark_good`（工作回退 / 崩溃救援体系直通中枢），运维面 `remount`/`reload_plugins`/`stop_engine`；`cmd.stop`（停全部任务、实例保持运行）与 `cmd.reload`（重读 env + 热重载插件）下行语义不变。③ **运行形态真身化**——`norpagent cortex/node` 子命令（及 `main.py --norp-cortex/--norp-node`）**默认装配完整内核引擎**：每个神经原子都是真实可执行任务的 norpagent 实例（默认 minimal/mock 零依赖，`--mode`/`--model` 可换，`--bare` 回到纯神经空壳探针；中枢 = 最高级 norpagent 实例）；`stop_engine` 动作应答先行、引擎延迟 1s 平滑停止并注销节点，CLI 进程随主循环自然退出。④ **上行融合**——心跳自动携带内核深度状态（`engine_state`/`active_tasks`/`version`/`actions`，中枢 `reports` 直接可见），任务 `task_started`/`task_done` 事件上行（中枢视角任务全生命周期可见）；CLI `reports` 打印心跳内核状态字段。⑤ `runtime/cnb.py` 保留为转发层（engine 零改动）；`norpagent.cli` 与 `main.py` CNB 转发指向新路径。⑥ 测试：test_cnb 60 + test_deep_tree 36 + test_e2e 13 + automount 12/12 全绿（迁移回归零破坏），新增内核动作面验收 `test/test_cnb_kernel_actions.py`（A 同进程 21 项 + B 多进程 11 项，实测 32/32 通过）。详见 §30.16。全部活跃版本号统一为 **1.0.7**。
> **1.0.2 修订（CNB 随包分发）**：修复 PyPI 1.0.1 包不含中枢神经总线（CNB）的问题——`nervous_bus/` 由仓库根目录迁入 `src/nervous_bus/` 随包发布（`pip install norpagent==1.0.2` 即自带 CNB）；`norpagent` 命令新增 `cortex / node / topo / ping / exec / stop / reload / perm / reports / audit / sync` 神经树子命令（与 `python -m nervous_bus.cli ...` 等价，兼容 `--norp-cortex` / `--norp-node` 旧写法）；仓库源码运行由 `main.py` / `api.py` 顶部 src 路径引导自动适配；全部活跃版本号统一为 1.0.2（`pyproject.toml`、`src/norpagent/__init__.py`、recovery 子模块 `__version__`、多模态 UA 标识、版本断言测试同步）。
> **2026-09-05 深树修复（CNB 内核 B1-B9，体检整改）**：内核「浅树自洽、深树断裂」——官方自测全是 ≤2 层扁平场景（原子直挂中枢），从未覆盖 ≥3 层链式转发；五层树实测三条主链（注册/上行/断链）全有硬伤，9 项问题 3 项高危（B1 深层注册坍缩：转发每跳覆盖 `via` 致中枢错挂父子；B2 中间层收心跳/事件只记录不转发致中枢对深层全盲；B3 中间层退出致中枢级联注销整棵活子树成孤岛）。全部修复：`via` 改 `setdefault` 保留原始直接父；上行逐级汇聚转发 + 上层拒绝回传驱动深层自愈；新增救树 `_rescue_children` + `cmd.reroot` 改挂指令，活子树不陪葬；权限判定改纯时间序（类型级 revoke 不再被旧 node_id grant 屏蔽）；中枢失联清扫守护线程接线（`sweep_dead` 落地：判死→救树→宽限收敛）；hello 祖先链去重；心跳支持自定义状态位；注册/注销/救树后防抖自动拓扑广播。新增 4 层深树专项回归 `nervous_bus/test_deep_tree.py`（30 项），全部套件 52+13+30+12 实测通过。详见 §30.14。全部活跃版本号统一为 **1.0.4**（`pyproject.toml`、`src/norpagent/__init__.py`、recovery 子模块 `__version__`、多模态 UA 标识、版本断言测试同步）。
> **2026-09-05 v1.0.6 增量（深树收敛闭环 + 权限面审计，现场实测验证）**：① **缺口 A**——中枢清扫收敛注销后的自动广播虽已触发，但接收端 `cmd.topology.sync` 只加不删，中间层本地缓存不收敛（运行中的演示树实测：中枢已注销 probe-x 并广播 11 成功，rnd 心跳 `descendants` 150s+ 仍含 probe-x）。修复为**权威快照镜像**：剪枝（快照缺失节点级联注销，自身除外）+ 父指针收敛（以中枢视图为准 `set_parent`），瞬时缺失由心跳被拒自动重注册自愈；深树回归 30→**36**（新增 D13a-f）。② **缺口 B**——exec 权限拒绝与 perm 变更生效上行 `report.audit`（`perm.denied` / `perm.changed`）逐级汇聚中枢；中枢新增结构化权限操作记录与统一视图 `perm_audit(n)`（REPL `perm_audit` + 控制端点 `op=perm_audit`），同权限审计读取方直接消费该端点。test_cnb 52→**60**（新增 T-A0~T-A6 权限面审计回归，含深层经中间层转发）。详见 §30.15。全部活跃版本号统一为 **1.0.6**。
> **2026-09 修订（CNB 环境自动挂载 + 任务级取消 + 手册校准）**：① **P0-1 落地**——普通 norpagent 实例（np()/GUI/嵌入式）在装配期读取 `NORP_CNB_*` 环境变量自动以节点身份挂上神经树（新增 `norpagent/runtime/cnb.py`：CnbAdapter + 后台挂载线程 + 注册重试 + 失败降级普通单实例；`NORP_CNB_MANAGED=1` 跳过开关供上层 managed 自建，防双重挂载；shutdown 路径注销）；中枢下行四回调落地到真实引擎控制点：`exec`（动作白名单 `run_task`/`status`/`stop_task`，缺 prompt 拒、未知 action 拒、审计回执、任务完成上报 `report.event`）、`stop`（`stop_all_tasks()` 停全部在途会话任务、实例保持运行）、`reload`（重读 CNB 环境配置 + 经 remount 机制热重载外部插件）、`perm_changed`（权限摘要记录与审计；权限表在 cmd.exec 前置强制）。② **P2-1 任务级取消**——loop 层新增可选扩展 `submit_async`（`NasyncTaskHandle`，单任务深度取消，仍受 Ctrl+C/engine-stop 全量取消覆盖），引擎层新增 `submit_async`/`cancel_task`/`stop_all_tasks`/`active_tasks`/`forget_task`。③ **P1-1/P2-2 校准**——`--help` 现展示 CNB 子命令分支；§30.8/§30.12/附录 J 改写为真实实现位置（`runtime/engine.py` + `runtime/cnb.py`，移除 `api.py AgentAPI._setup_cnb()` 与 config.json 同键的不实描述，config 键不再声称支持，收敛为环境变量契约）。④ `nervous_bus.test_e2e` 的 ROOT 定位改为自动爬升至含 `main.py` 的仓库根（v1.0.2 src/ 布局下 `python -m nervous_bus.test_e2e` 恢复 13/13）。⑤ 新增验收冒烟 `test/test_cnb_automount.py`（12 项，2026-09-05 实测 12/12 通过）。
> **1.0.1 修订（版本里程碑）**：0.9.x 系列收官，正式进入 **1.0.x 系列**——统一全部活跃版本号为 1.0.1（`pyproject.toml`、`src/norpagent/__init__.py`、recovery 子模块 `__version__`、多模态 UA 标识、版本断言测试同步）；1.0 系列承载此前全部能力：多模态（视觉 + 声音）、中枢神经总线（CNB）多实例神经树、救援模式、29 钩子、插件体系。
> **0.9.9 修订（多模态）**：新增**第 29 章「多模态：视觉与声音」**与**附录 I「多模态配置与 API 速查」**——视觉：上传/粘贴/拖拽图片经 `/api/vision` 由外部视觉服务理解后融入对话；声音：语音朗读（TTS）与语音输入（STT）**全部后端原生实现**（Windows SAPI / macOS say / Linux espeak-ng 离线可用，或配置 OpenAI 兼容服务），提示音后端生成，浏览器只采集与播放、不依赖任何浏览器语音 API；`/api/upload` 支持图片；`tts_service_api_key` / `stt_service_api_key` 纳入 DPAPI 加密存储。
> **2026-08 中枢神经总线（CNB）多实例升级**：新增**第 30 章「中枢神经总线：多实例与神经树」**与**附录 J「中枢神经总线速查表」**——中枢（最高级 norpagent 实例）通过中枢神经总线控制任意层级任意单位原子的操作权限；低层级只能通过总线上报，不可控制上层；神经树为树状拓扑链；低等级无条件服从高等级指令，不允许改写高等级，只允许回传上报。`nervous_bus/` 全模块（协议层 / 树状拓扑链 / 神经权限表 / 零依赖传输层 / 节点 / 中枢 / CLI），51 项单元集成 + 13 项真实多进程端到端自测通过；`main.py` 新增 `--norp-cortex` / `--norp-node` 无 GUI 后台多实例入口（绕过单实例锁），`api.py` 支持 GUI 实例以节点身份加入神经树。
> 2026-08 修订：第 24 章救援模式专章（底层循环控制 + 人类接管）｜ 内核修复：select 超时上限钳制（暴力压测发现，Windows 超远定时器崩溃）｜ 新增 35 项最小主异步循环暴力压测（test/stress_nasyncio_core.py）｜ 15.6 人类救援手动工具接管 API（v0.9.3，模型失效时手操全部工具：tools / tool-call / manual / serve）｜ 3.9 任务级槽位注入（submit(slot_overrides=...)）｜ 3.7 装配槽位热重建的在途任务竞态与排水建议 ｜ 4.6.4 守护工作池队列语义与卡死兜底矩阵 ｜ 23.1 EventBus 基准口径与锁竞争边界 ｜ 第 25 章开发者实战专章（逐模块开发 / 槽位开发 / 插件与工具开发详解，含热重载红线：键值对的值必须是有效模块）｜ 第 26 章注册流程详解（注册表 9 大命名空间 / 四种形态与字符串语义 / npa() 装配全链路 / 三种注册时机与热重载 / 槽位注册与组件注册的区别 / 校验与错误处理 / 检查清单）｜ 第 27 章最小内核详解专章（事件总线 / 槽位连接器 / 注册表 / 地址解析器四组件：数据结构、API、内部机制与启动 / 热挂载协作走查）
> **0.9.7 修订**：救援模式支持自定义工具手动控制（`RescueToolEnvironment` 新增 `extra_tools` / `tools` / `plugin_dirs`，CLI 新增 `--tools` / `--plugin-dirs`，操作员页面与清单标注 builtin / custom / plugin 来源）｜ 通用事件总线（GeneralEventBus，类名 `EventBus`）新增通用能力：`once` / `wait` / `emit_all` / `subscriber_count` / `has_listeners` / `clear` ｜ 第 9 章新增 9.8「29 钩子逐个用法（Python 代码实现）」｜ 新增第 28 章「外部 Python 脚本集成：热挂载与钩子订阅」｜ 新增附录 F（前后端通讯方式速查表）/ 附录 G（全部命令用法速查表）/ 附录 H（全部函数及结构用法速查表）｜ 第 13 章命令行入口扩充（命令行前端进入方式 + 救援模式命令补全）｜ 全文语言严谨化与术语统一（EventBus 在手册中称通用事件总线 GeneralEventBus，代码符号名不变）

---

*NorpAgent 开发手册 · v2.2.1 · FarStars（远星）· Copyright (c) 2026 xingluosama121, MIT Licensed*

