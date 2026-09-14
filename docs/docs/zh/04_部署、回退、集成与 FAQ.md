<!-- 由 docs/DEVELOPER_MANUAL.md 按部分拆分生成，正文与原文逐行一致 -->

> **开发手册 · 第 4 部分：部署、回退、集成与 FAQ** ｜ 覆盖：第 14-19 章 + 附录 A-C ｜ [返回总目录](../README.md)

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
即时更新。字符串地址在重挂载前自动失效模块缓存与 .pyc（见 25.2.6），
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

