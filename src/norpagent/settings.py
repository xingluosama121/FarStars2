# Copyright (c) 2026 xingluosama121, MIT Licensed
"""norpagent.settings — 内核动点全量设置清单（架构书 §5「内核动点全量设置化」）。

settings store（norpagent.evolution.store.SettingsStore）是设置的唯一注册 /
审计 / 继承入口；本模块提供：

- ``KERNEL_SCHEMA``：内核动点全量清单（Model / 循环 / 工具 / 会话与记忆 /
  神经 / 安全 / 插件 / 多模态 / 进化 / 前端 / 调度与恢复 十一域）——每项 =
  key / 标题 / 类别 / 类型 / 默认值 / 说明 / 可进化与锁定标记 / 危险级 /
  三视角可见性 / 运行态桥接键；
- ``register_kernel_schema(store)``：把清单注册进设置库（幂等）；
- ``ensure_schema(store)``：内核清单 + 进化域清单一次性注册（各入口调用）；
- ``schema_view(store)``：注册表合并视图（DB 行 + 本模块扩展元数据），
  面板渲染 / 校验 / 导出用；
- ``mirror_config_to_store(cfg)`` / ``apply_store_to_config(store, cfg)`` /
  ``config_patch_for_key(key)``：与既有 webui 运行配置的双向镜像桥。

设计口径（如实记录）：
- store 为「注册 / 审计 / 继承 / 面板」的唯一事实源；运行态存量配置
  （webui_config.json）经镜像桥保持同步，作为引擎装配的读取后端——键的
  映射列于每项的 ``config_key`` 字段（无映射 = 纯设置库键）。
- ``secret=True`` 的项（API key等）仅在既有配置链路（DPAPI 加密）流转，
  不写入设置库（避免明文落库）。
- 三视角：``user``（成品）/ ``frame``（框架）/ ``meta``（元框架）；
  面板按视角过滤呈现，同一事实源、多视角展示。
"""

from __future__ import annotations

import json as _json
from typing import Any, Dict, List, Optional

from norpagent.evolution.store import (
    SCOPE_GLOBAL,
    SCOPE_PRIORITY,
    SCOPE_PROFILE,
    SCOPE_SESSION,
    SCOPE_TEMP,
    SCOPE_TITLES,
    SettingsStore,
    get_store,
)
from norpagent.evolution.points import register_evolution_schema

V_USE = ("user", "frame", "meta")
V_FRAME = ("frame", "meta")
V_META = ("meta",)
V_USER = ("user", "frame", "meta")

# 无映射哨兵：区分「未设置」与「值就是 None」
_MISS = object()


def _s(key: str, title: str, category: str, *, type: str = "text",
       default: Any = None, description: str = "",
       evolvable: bool = False, locked: bool = False, danger: bool = False,
       views: tuple = V_USE, config_key: Optional[str] = None,
       secret: bool = False, options: Optional[List[Any]] = None,
       minimum: Optional[float] = None, maximum: Optional[float] = None,
       step: Optional[float] = None, unit: str = "",
       enable_when: Optional[List[Dict[str, Any]]] = None,
       greyed: bool = False) -> Dict[str, Any]:
    """一条内核动点清单记录（内部构造器）。

    ``enable_when``：总开关联动条件列表——全部满足时控件可用；否则面板置灰
    禁用（如 memory.enabled=false 时全部 memory.* 子项禁用；多模态 direct 路由
    时Service URL/密钥禁用）。条件项：``{"key": 其它设置键, "in": [允许值...]}``。

    ``greyed``：暂未接线 / 已废弃的项，面板永久置灰禁用（保留可见以说明规划，
    但明确标注「暂不可用」，避免用户以为改动生效）。
    """
    item: Dict[str, Any] = {
        "key": key,
        "title": title,
        "category": category,
        "type": type,
        "default": default,
        "description": description,
        "evolvable": bool(evolvable),
        "locked": bool(locked),
        "danger": bool(danger),
        "views": list(views),
        "config_key": config_key,
        "secret": bool(secret),
        "greyed": bool(greyed),
    }
    if options is not None:
        item["options"] = list(options)
    if minimum is not None:
        item["minimum"] = minimum
    if maximum is not None:
        item["maximum"] = maximum
    if step is not None:
        item["step"] = step
    if unit:
        item["unit"] = unit
    if enable_when is not None:
        item["enable_when"] = [dict(c) for c in enable_when]
    return item


def _on(*conditions: Dict[str, Any]) -> List[Dict[str, Any]]:
    """enable_when 条件简写：_on({"key": "memory.enabled", "in": [True]}, ...)。"""
    return [dict(c) for c in conditions]


# ══════════════════════════════════════════════════════════
# 内核动点全量清单（§5.2 盘点：十一域）
# ══════════════════════════════════════════════════════════

KERNEL_SCHEMA: List[Dict[str, Any]] = [
    # ── Model域 ─────────────────────────────────────────────
    _s("model.active", "Model", "model", type="text", default="",
       description="Model to use (empty = the engine preset default; a registry name or a remote model name)",
       config_key="model"),
    _s("model.title_model", "Session title model", "model", type="text", default="",
       description="Model that auto-summarizes the session title from the first round (a separate one-off call, never inside the chat loop); empty = the session's current model",
       config_key="title_model"),
    _s("model.context_token_budget", "Context token budget", "model", type="number",
       default=32000, minimum=0,
       description="Request budget (estimated tokens). Over budget the oldest history is compressed first (chain-of-thought and oversized tool results are folded away); only if it still exceeds the budget are the oldest whole turns dropped (tool_call / tool_call_id pairs are never split). 0 = unlimited (compression and truncation both off)",
       config_key="context_token_budget"),
    _s("runtime.session_isolation", "Session isolation", "runtime", type="enum",
       default="per_session",
       description="Concurrency isolation between sessions: per_session = one lock per session (different sessions run in parallel on the shared runtime, the same session stays serial); isolated_instance = each task runs on its own one-off runtime instance (strongest isolation)",
       config_key="session_isolation",
       options=["per_session", "isolated_instance"]),
    _s("model.api_base", "Service URL", "model", type="text",
       default="https://api.deepseek.com",
       description="OpenAI-compatible service endpoint",
       config_key="api_base"),
    _s("model.api_key", "API key", "model", type="password", default="",
       description="Model service secret (DPAPI-encrypted; never written to the settings store)",
       config_key="api_key", secret=True, danger=True),
    _s("model.name", "Remote model name", "model", type="text", default="",
       description="Remote model name (filled from the registry / fetched list; no model name is hardcoded)"),
    _s("model.temperature", "Temperature", "model", type="number", default=1.0,
       description="Sampling temperature; omitted by the adapter when reasoning mode is on",
       evolvable=True, config_key="temperature", minimum=0, maximum=2, step=0.05),
    _s("model.top_p", "Top-P", "model", type="number", default=1.0,
       description="Nucleus sampling threshold (1.0 = no truncation)",
       config_key="top_p", minimum=0, maximum=1, step=0.05),
    _s("model.max_tokens", "Max output tokens", "model", type="number",
       default=32767, description="Maximum output tokens for a single reply",
       config_key="max_tokens", minimum=1, maximum=2000000),
    _s("model.think_level", "Reasoning effort", "model", type="enum", default="high",
       description="Reasoning effort: off = disabled (uses temperature) / low / medium / high / max",
       config_key="think_level", options=["off", "low", "medium", "high", "max"]),
    _s("model.use_responses_api", "Use Responses API", "model", type="switch",
       default=False, description="OpenAI Responses API form (can be turned off for compatible services)",
       config_key="use_responses_api"),
    _s("model.system_prompt", "Custom system prompt", "model", type="textarea",
       default="", description="Replace the default system prompt (takes effect when enabled)",
       evolvable=True, config_key="custom_system_prompt",
       enable_when=_on({"key": "model.system_prompt_enabled", "in": [True]})),
    _s("model.system_prompt_enabled", "Enable custom prompt", "model", type="switch",
       default=False, description="When on, the custom system prompt below replaces the default",
       config_key="custom_system_prompt_enabled"),
    _s("model.system_prompt_file", "Prompt file", "model", type="text",
       default="", description="Load the system prompt from a file (alternative to the text field)",
       config_key="custom_system_prompt_file",
       enable_when=_on({"key": "model.system_prompt_enabled", "in": [True]})),
    _s("model.request_timeout", "Per-request timeout", "model", type="number",
       default=180, description="An API request that receives no data for this long is aborted",
       config_key="api_request_timeout", minimum=5, unit="s"),
    _s("model.call_timeout", "Per-call hard timeout", "model", type="number",
       default=0, description="Hard timeout for a single model call (0 = unlimited)",
       config_key="call_timeout", minimum=0, unit="s"),
    _s("model.fail_retry", "Failure retries", "model", type="number", default=2,
       description="Number of retries after a failed model call", minimum=0),
    _s("model.fallback_chain", "Fallback chain", "model", type="json", default=[],
       description="Model fallback chain tried in order after a failure"),
    _s("model.stream", "Streaming output", "model", type="switch", default=True,
       description="Enable streaming incremental output (content arrives in real time)"),

    # ── 循环域 ─────────────────────────────────────────────
    _s("loop.max_steps", "Max steps", "loop", type="number", default=128,
       description="Maximum steps per task (stops and reports honestly when exceeded)",
       config_key="max_steps", minimum=1, maximum=1000),
    _s("loop.max_rounds", "Max rounds", "loop", type="number", default=10,
       description="Maximum rounds of the multi-round tool-call loop",
       config_key="max_rounds", minimum=1, maximum=100),
    _s("loop.task_timeout", "Task timeout", "loop", type="number", default=0,
       description="Per-task timeout (0 = unlimited)", config_key="task_timeout", minimum=0),
    _s("loop.queue_max_size", "Task queue limit", "loop", type="number", default=200,
       description="In-flight task queue limit (rejects new tasks instead of piling up)",
       config_key="queue_max_size", minimum=0),
    _s("loop.turn_boundary_check", "Round-boundary check", "loop", type="switch",
       default=True, description="Run stop/cancel checks at round boundaries"),
    _s("loop.stop_conditions", "Additional stop conditions", "loop", type="json", default=[],
       description="List of custom stop-condition descriptions (consumed by extension subscribers)"),

    # ── 工具域 ─────────────────────────────────────────────
    _s("tools.enabled", "Tool enable list", "tools", type="json", default=[],
       description="Explicit tool list (empty + not explicit = the preset's full default set)",
       config_key="agent_tools"),
    _s("tools.explicit", "Explicit tool set", "tools", type="switch", default=False,
       description="True = the tool enable list is authoritative (including an empty set)",
       config_key="agent_tools_explicit"),
    _s("tools.allowlist", "Tool allowlist", "tools", type="json", default=[],
       description="Only the listed tools are allowed (empty = unrestricted)"),
    _s("tools.blocklist", "Tool denylist", "tools", type="json", default=[],
       description="Listed tools are forbidden"),
    _s("tools.approval", "Tool-call approval", "tools", type="switch", default=True,
       description="Require manual approval before sensitive tool calls",
       config_key="approval_enabled"),
    _s("tools.native_confirm", "Native tool confirmation", "tools", type="switch",
       default=False,
       description=("Require manual approval before native write / delete / exec tool "
                    "calls (write_file, replace_in_file, surgical_replace, copy_file, "
                    "move_file, init_project -> WRITE; delete_file -> DELETE; exec_cmd, "
                    "install_dependency, git_commit -> EXEC). OFF by default; when on, "
                    "the three sub-switches below decide per class."),
       config_key="native_confirm_enabled"),
    _s("tools.native_confirm_write", "Confirm writes", "tools", type="switch",
       default=True,
       description="Ask before write-class native tools (write_file / replace_in_file / surgical_replace / copy_file / move_file / init_project)",
       config_key="native_confirm_write",
       enable_when=_on({"key": "tools.native_confirm", "in": [True]})),
    _s("tools.native_confirm_delete", "Confirm deletes", "tools", type="switch",
       default=True,
       description="Ask before delete-class native tools (delete_file)",
       config_key="native_confirm_delete",
       enable_when=_on({"key": "tools.native_confirm", "in": [True]})),
    _s("tools.native_confirm_exec", "Confirm exec", "tools", type="switch",
       default=True,
       description="Ask before exec-class native tools (exec_cmd / install_dependency / git_commit)",
       config_key="native_confirm_exec",
       enable_when=_on({"key": "tools.native_confirm", "in": [True]})),
    _s("tools.sandbox", "Sandbox tier", "tools", type="text", default="pooled",
       description="Sandbox implementation (pooled / subprocess / custom address)"),
    _s("tools.network_policy", "Network policy (SSRF)", "tools", type="enum",
       default="deny", description="Tool network access policy (private addresses denied by default)",
       options=["deny", "audited_public", "public_only", "allow_all"]),

    # ── 会话与记忆域 ───────────────────────────────────────
    _s("memory.enabled", "Memory switch", "memory", type="switch", default=True,
       description="Cross-round session memory (off = single round, no history)",
       config_key="memory"),
    _s("memory.mode", "Memory mode", "memory", type="enum", default="full",
       description="full = full history; summary = compressed summary",
       config_key="memory_mode", options=["full", "summary"],
       enable_when=_on({"key": "memory.enabled", "in": [True]})),
    _s("memory.window_size", "Memory window", "memory", type="number", default=0,
       description="Number of recent messages kept (0 = no truncation)", minimum=0,
       enable_when=_on({"key": "memory.enabled", "in": [True]})),
    _s("memory.store", "Memory storage", "memory", type="text", default="fts5",
       description="Long-term memory storage (fts5 = full-text index)",
       enable_when=_on({"key": "memory.enabled", "in": [True]})),
    _s("memory.forget_policy", "Forgetting policy", "memory", type="enum",
       default="soft_delete",
       description="Long-term memory forgetting: off / soft_delete (recoverable) / curve (decay by forgetting curve)",
       evolvable=True, options=["off", "soft_delete", "curve"],
       enable_when=_on({"key": "memory.enabled", "in": [True]})),
    _s("memory.consolidate_threshold", "Consolidation threshold", "memory", type="number",
       default=3, description="A fact is promoted to long-term memory after appearing this many times",
       evolvable=True, minimum=1,
       enable_when=_on({"key": "memory.enabled", "in": [True]})),
    _s("memory.keep_forgotten_query", "Forgotten items searchable", "memory", type="switch",
       default=True, description="Keep a query channel for forgotten/soft-deleted entries (traceable in the whitebox)",
       enable_when=_on({"key": "memory.enabled", "in": [True]})),

    # ── 神经域（CNB） ──────────────────────────────────────
    _s("cnb.enabled", "CNB enable switch", "cnb", type="switch", default=False,
       description="Off by default; enable explicitly; the port must be set manually when enabled ",
       danger=True),
    _s("cnb.node_id", "Node id", "cnb", type="text", default="",
       description="This instance's node id in the neural tree",
       enable_when=_on({"key": "cnb.enabled", "in": [True]})),
    _s("cnb.kind", "Node kind", "cnb", type="text", default="agent",
       description="Atom kind (bot / pilot / memory / agent...)",
       enable_when=_on({"key": "cnb.enabled", "in": [True]})),
    _s("cnb.level", "Node level", "cnb", type="number", default=3,
       description="Neural-tree level (must be higher than the parent; the cortex is level 0)",
       minimum=1, maximum=63,
       enable_when=_on({"key": "cnb.enabled", "in": [True]})),
    _s("cnb.parent", "Parent address", "cnb", type="text",
       default="http://127.0.0.1:17800", description="Parent bus address",
       enable_when=_on({"key": "cnb.enabled", "in": [True]})),
    _s("cnb.port", "Node port", "cnb", type="number", default=None,
       description="This node's bus port (never hardcoded; required when enabled, a missing port raises)",
       danger=True, minimum=1, maximum=65535,
       enable_when=_on({"key": "cnb.enabled", "in": [True]})),
    _s("cnb.heartbeat", "Heartbeat interval", "cnb", type="number", default=5.0,
       description="Heartbeat report interval", minimum=0.5, maximum=3600, unit="s",
       enable_when=_on({"key": "cnb.enabled", "in": [True]})),
    _s("cnb.cleanup_timeout", "Sweep threshold", "cnb", type="number", default=30.0,
       description="Threshold for declaring a lost node dead (no heartbeat in time -> sweep)", minimum=1,
       unit="s", enable_when=_on({"key": "cnb.enabled", "in": [True]})),
    _s("cnb.freeze_policy", "Freeze policy", "cnb", type="enum", default="manual",
       description="Isolated-freeze issuance mode (manual = issued by a human)",
       options=["manual", "auto"],
       enable_when=_on({"key": "cnb.enabled", "in": [True]})),
    _s("cnb.baseline_granularity", "Baseline aggregation granularity", "cnb", type="enum",
       default="compressed",
       description="Behavior-baseline reporting granularity (compressed = aggregated, no raw stream)",
       options=["compressed", "full"],
       enable_when=_on({"key": "cnb.enabled", "in": [True]})),
    _s("cnb.exec_actions", "Action surface switch", "cnb", type="json", default=[],
       description="Allowed exec action surface (empty = all kernel actions)",
       enable_when=_on({"key": "cnb.enabled", "in": [True]})),
    _s("cnb.uplink", "Uplink switch", "cnb", type="switch", default=True,
       description="Uplink read-only reporting (heartbeat / events / audit)",
       enable_when=_on({"key": "cnb.enabled", "in": [True]})),
    _s("cnb.downlink", "Downlink switch", "cnb", type="switch", default=True,
       description="Accept downlink commands (stop / reload / exec, etc.)",
       enable_when=_on({"key": "cnb.enabled", "in": [True]})),
    _s("cnb.slots_per_node", "Node slot limit", "cnb", type="number", default=64,
       description="Generic slot limit per node (fixed cap)", locked=True,
       minimum=0, maximum=64),

    # ── 安全域 ─────────────────────────────────────────────
    _s("security.enabled", "Security system", "security", type="switch",
       default=True, danger=True,
       description="Master switch for the security system: mounts the norpagent.safe() suite so dangerous operations are intercepted. Default ON; turning it off is allowed but requires an explicit, non-dismissable confirmation because it removes a protection layer.",
       config_key="security_enabled"),
    _s("security.level", "Security level", "security", type="enum", default="standard",
       description="norpagent.safe() protection level: relaxed / basic / standard / high (applied to the always-on suite)",
       config_key="security_level",
       options=["relaxed", "basic", "standard", "high"],
       enable_when=_on({"key": "security.enabled", "in": [True]})),
    _s("security.audit_granularity", "Audit granularity", "security", type="enum",
       default="standard", description="Security audit trail granularity",
       options=["minimal", "standard", "verbose"],
       enable_when=_on({"key": "security.enabled", "in": [True]})),
    _s("security.jailbreak_guard", "Jailbreak protection", "security", type="switch",
       default=True, description="Intercept malicious-injection / jailbreak input",
       config_key="jailbreak_guard_enabled",
       enable_when=_on({"key": "security.enabled", "in": [True]},
                       {"key": "security.safe_enabled", "in": [True]})),
    _s("security.jailbreak_action", "Violation handling", "security", type="enum",
       default="warn", description="Action taken when a jailbreak signature is hit (notice = silent pass; warn = pass + log; block = veto)",
       config_key="jailbreak_guard_action", options=["block", "warn", "notice"],
       enable_when=_on({"key": "security.enabled", "in": [True]},
                       {"key": "security.safe_enabled", "in": [True]},
                       {"key": "security.jailbreak_guard", "in": [True]})),
    _s("security.safe_enabled", "Security kit", "security", type="switch",
       default=True, danger=True,
       description="Mount the full norpagent.safe() security policy. Default ON; turning it off is allowed but requires an explicit, non-dismissable confirmation.",
       config_key="norp_safe_enabled",
       enable_when=_on({"key": "security.enabled", "in": [True]})),
    _s("security.signature_verify", "Plugin signature check", "security", type="switch",
       default=True, danger=True,
       description="Plugin signature / provenance verification. Default ON; turning it off is allowed but requires an explicit, non-dismissable confirmation.",
       config_key="plugin_signature_verify",
       enable_when=_on({"key": "security.enabled", "in": [True]})),
    _s("security.unsigned_plugin_policy", "Unsigned-plugin policy", "security",
       type="enum", default="warn",
       description="Warn only for unsigned plugins, do not block by default ",
       options=["warn", "block"],
       enable_when=_on({"key": "security.enabled", "in": [True]})),
    _s("security.safe_mode", "Safe mode", "security", type="switch",
       default=False, locked=True,
       description="Safe-mode startup: minimal kernel only; no slot loads external code ",
       danger=True),
    _s("security.alert_level", "Security alert level", "security", type="enum",
       default="major",
       description=("How much the Security Kit surfaces in the UI. "
                    "major (default) = only real interceptions; "
                    "normal = interceptions + warnings; "
                    "all = everything including minor notices; "
                    "off = silent, audit log only."),
       options=["off", "major", "normal", "all"],
       config_key="norp_safe_alert_level",
       enable_when=_on({"key": "security.enabled", "in": [True]})),
    _s("security.rescue_enabled", "Rescue channel", "security", type="switch",
       default=True, description="Crash rescue / manual-takeover channel always on (right to informed intervention)"),
    _s("security.rescue_port", "Rescue port", "security", type="number", default=0,
       description="Rescue HTTP service port (0 = not started)", minimum=0, maximum=65535,
       enable_when=_on({"key": "security.rescue_enabled", "in": [True]})),

    # ── 插件域 ─────────────────────────────────────────────
    _s("plugins.enabled", "Plugin system", "plugins", type="switch", default=True,
       description="Master switch for external plugins (off = zero external code loaded)",
       config_key="plugins_enabled"),
    _s("plugins.isolation", "Isolation mode", "plugins", type="enum", default="auto",
       description="Plugin process isolation: auto = per plugin declaration / inproc / process",
       config_key="plugin_isolation", options=["auto", "inproc", "process"],
       enable_when=_on({"key": "plugins.enabled", "in": [True]})),
    _s("plugins.security_audit", "Load audit", "plugins", type="enum",
       default="warn",
       description=("Plugin security-audit level: off / notice (record only) / "
                    "warn (surface a warning) / block (block on critical issues)"),
       config_key="plugin_security_audit",
       options=["off", "notice", "warn", "block"],
       enable_when=_on({"key": "plugins.enabled", "in": [True]})),
    _s("plugins.import_restrict", "Import restrictions", "plugins", type="enum",
       default="soft",
       description=("Plugin import restriction level: off / soft (record only) / "
                    "safe (block dangerous imports) / strict (allowlist only)"),
       config_key="plugin_security_import_restrict",
       options=["off", "soft", "safe", "strict"],
       enable_when=_on({"key": "plugins.enabled", "in": [True]})),
    _s("plugins.require_permissions", "Capability declaration gate", "plugins", type="switch",
       default=True, description="Require plugins to declare capabilities (PLUGIN_CAPABILITIES)",
       config_key="plugin_security_require_permissions",
       enable_when=_on({"key": "plugins.enabled", "in": [True]})),
    _s("plugins.resource_limit", "Resource limits", "plugins", type="switch",
       default=False, description="Plugin resource usage limits",
       config_key="plugin_security_resource_limit",
       enable_when=_on({"key": "plugins.enabled", "in": [True]})),
    _s("plugins.dirs", "Plugin directories", "plugins", type="json", default=[],
       description="List of external plugin directories", config_key="plugin_dirs",
       enable_when=_on({"key": "plugins.enabled", "in": [True]})),
    _s("plugins.disabled", "Disabled plugins", "plugins", type="json", default=[],
       description="List of plugin names disabled by the user", config_key="plugin_disabled",
       enable_when=_on({"key": "plugins.enabled", "in": [True]})),
    _s("plugins.network_url_allowlist", "Network URL allowlist", "plugins",
       type="json", default=[], description="Plugin network URL allowlist",
       config_key="plugin_network_url_allowlist",
       enable_when=_on({"key": "plugins.enabled", "in": [True]})),
    _s("plugins.network_domain_allowlist", "Network domain allowlist", "plugins",
       type="json", default=[], description="Plugin network domain allowlist",
       config_key="plugin_network_domain_allowlist",
       enable_when=_on({"key": "plugins.enabled", "in": [True]})),

    # ── 多模态域 ───────────────────────────────────────────
    _s("mm.image_route", "Image routing", "multimodal", type="enum", default="direct",
       description="direct = pass natively to the model / service = relay via an external service",
       config_key="mm_image_route", options=["direct", "service"]),
    _s("mm.audio_route", "Audio routing", "multimodal", type="enum", default="direct",
       description="How audio (not just speech: music/ambience use the same protocol) is passed to the model",
       config_key="mm_audio_route", options=["direct", "service"]),
    _s("mm.video_route", "Video routing", "multimodal", type="enum", default="direct",
       description="How video (including streams) is passed to the model",
       config_key="mm_video_route", options=["direct", "service"]),
    _s("mm.text_attachment_limit", "Text attachment limit", "multimodal",
       type="number", default=1034324, minimum=512, maximum=2147483647,
       description=("Max characters of an uploaded / pasted text file handed to the "
                    "model; configurable from 512 to 2147483647, or turn on the "
                    "no-limit switch below to pass the whole body"),
       config_key="attachment_text_max_chars",
       enable_when=_on({"key": "mm.text_attachment_unlimited", "in": [False]})),
    _s("mm.text_attachment_unlimited", "No text attachment limit", "multimodal",
       type="switch", default=False,
       description=("When on, uploaded / pasted text files reach the model in full; "
                    "the character limit above is ignored"),
       config_key="attachment_text_unlimited"),
    _s("mm.vision_enabled", "Vision feature", "multimodal", type="switch",
       default=False, description="Image understanding switch",
       config_key="vision_enabled"),
    _s("mm.vision_service_url", "Vision service URL", "multimodal", type="text",
       default="", description="External vision service endpoint (used when routing via service)",
       config_key="vision_service_url",
       enable_when=_on({"key": "mm.vision_enabled", "in": [True]},
                       {"key": "mm.image_route", "in": ["service"]})),
    _s("mm.vision_service_key", "Vision service secret", "multimodal", type="password",
       default="", description="Vision service API key (DPAPI-encrypted; never written to the settings store)",
       config_key="vision_service_api_key", secret=True, danger=True,
       enable_when=_on({"key": "mm.vision_enabled", "in": [True]},
                       {"key": "mm.image_route", "in": ["service"]})),
    _s("mm.audio_service_url", "Audio service URL", "multimodal", type="text",
       default="", config_key="audio_service_url",
       description="External audio service endpoint (used when routing via service)",
       enable_when=_on({"key": "mm.audio_route", "in": ["service"]})),
    _s("mm.audio_service_key", "Audio service secret", "multimodal", type="password",
       default="", config_key="audio_service_api_key", secret=True, danger=True,
       description="Audio service API key (DPAPI-encrypted; never written to the settings store)",
       enable_when=_on({"key": "mm.audio_route", "in": ["service"]})),
    _s("mm.video_service_url", "Video service URL", "multimodal", type="text",
       default="", config_key="video_service_url",
       description="External video service endpoint (used when routing via service)",
       enable_when=_on({"key": "mm.video_route", "in": ["service"]})),
    _s("mm.video_service_key", "Video service secret", "multimodal", type="password",
       default="", config_key="video_service_api_key", secret=True, danger=True,
       description="Video service API key (DPAPI-encrypted; never written to the settings store)",
       enable_when=_on({"key": "mm.video_route", "in": ["service"]})),
    _s("mm.tts_enabled", "Voice playback", "multimodal", type="switch", default=True,
       description="Speech synthesis (TTS; backend-native, works offline)",
       config_key="tts_enabled"),
    _s("mm.tts_service_url", "TTS service URL", "multimodal", type="text",
       default="", description="OpenAI-compatible /audio/speech endpoint (optional)",
       config_key="tts_service_url",
       enable_when=_on({"key": "mm.tts_enabled", "in": [True]})),
    _s("mm.tts_service_key", "TTS service secret", "multimodal", type="password",
       default="", config_key="tts_service_api_key", secret=True, danger=True,
       description="TTS service API key (DPAPI-encrypted; never written to the settings store)",
       enable_when=_on({"key": "mm.tts_enabled", "in": [True]})),
    _s("mm.tts_voice", "Voice", "multimodal", type="text", default="",
       description="Voice name (e.g. Microsoft Huihui Desktop / alloy)",
       config_key="tts_voice",
       enable_when=_on({"key": "mm.tts_enabled", "in": [True]})),
    _s("mm.tts_rate", "Speech rate", "multimodal", type="number", default=1.0,
       description="Playback speed multiplier", config_key="tts_rate",
       minimum=0.5, maximum=2, step=0.05,
       enable_when=_on({"key": "mm.tts_enabled", "in": [True]})),
    _s("mm.stt_service_url", "STT service URL", "multimodal", type="text",
       default="", description="OpenAI-compatible /audio/transcriptions endpoint (optional)",
       config_key="stt_service_url"),
    _s("mm.stt_service_key", "STT service secret", "multimodal", type="password",
       default="", config_key="stt_service_api_key", secret=True, danger=True,
       description="STT service API key (DPAPI-encrypted; never written to the settings store)"),
    _s("mm.stt_language", "Recognition language", "multimodal", type="text",
       default="en-US", description="Local recognition engine language (zh-CN needs the Windows language pack)",
       config_key="stt_language"),
    _s("mm.sound_notify", "Sound effects", "multimodal", type="switch", default=True,
       description="New-message sound", config_key="sound_notify_enabled"),
    _s("mm.auto_speak", "Auto playback", "multimodal", type="switch", default=False,
       description="Read the reply aloud when a task completes", config_key="auto_speak_enabled"),

    # ── 进化域（顶层四键；逐点勾选键由 points 注册） ─────────
    _s("evolution.enabled", "Self-evolution master switch", "evolution", type="switch",
       default=True, description="When off, all evolvers stop "),
    _s("evolution.idle_policy", "Idle-time evolution policy", "evolution", type="enum",
       default="reduced", description="reduced = reduce or skip on idle; off = no evolution; auto = keep",
       options=["reduced", "off", "auto"],
       enable_when=_on({"key": "evolution.enabled", "in": [True]})),
    _s("evolution.idle_min_seconds", "Idle threshold", "evolution", type="number",
       default=600, description="No demand for this duration counts as idle ", minimum=0,
       unit="s", enable_when=_on({"key": "evolution.enabled", "in": [True]})),
    _s("evolution.candidate_threshold", "Evolution candidate trigger count", "evolution",
       type="number", default=3, minimum=1,
       description="Frequently used features (>=3 times) become evolution candidates "),
    _s("evolution.breaker_threshold", "Circuit-breaker threshold", "evolution", type="number",
       default=3, minimum=1,
       description="After this many consecutive failures on one evolvable point, pause evolution and notify (circuit breaker)"),
    _s("evolution.breaker_window", "Circuit-breaker window", "evolution", type="number",
       default=10, minimum=1,
       description="Observation window for consecutive failures in the circuit-breaker count (times)"),
    _s("evolution.breaker_auto_pause", "Auto-pause on breaker", "evolution", type="switch",
       default=True, description="Auto-pause evolution for the point on threshold (off = warn only)"),

    # ── 前端与体验 ─────────────────────────────────────────
    _s("ui.language", "UI language", "frontend", type="enum", default="zh_CN",
       description="UI language: zh_CN (Simplified) / en (English)",
       config_key="language", options=["zh_CN", "en"]),
    _s("ui.theme", "Theme", "frontend", type="theme", default=None,
       description="Theme system: mode (auto / light / dark), built-in presets and "
                   "user-defined themes with token overrides plus optional advanced CSS. "
                   "Edited from the theme designer (toolbar button or this row); persisted "
                   "as a single JSON document in the settings store."),
    _s("ui.console_view", "Console view", "frontend", type="enum", default="user",
       description="Settings panel view: user / frame / meta",
       options=["user", "frame", "meta"]),
    _s("ui.frame_advanced_json", "Frame view · JSON editing", "frontend", type="switch",
       default=False, description="Enable the JSON advanced-edit mode in the frame view",
       views=V_FRAME),

    # ── 调度与恢复 ─────────────────────────────────────────
    _s("runtime.snapshots_enabled", "Auto snapshot", "runtime", type="switch",
       default=True, description="Auto-snapshot on system-state change (rollback / rescue base)"),
    _s("runtime.snapshot_dir", "Snapshot directory", "runtime", type="text", default="",
       description="Snapshot storage directory (empty = default ~/.norpagent/snapshots/)",
       config_key="snapshot_dir"),
    _s("runtime.snapshot_keep", "Snapshot retention", "runtime", type="number",
       default=50, description="Snapshot timeline retention cap (prunes beyond it)", minimum=1),
    _s("runtime.undo_depth", "Undo depth", "runtime", type="number", default=20,
       description="Undo/Redo depth", minimum=1),
    _s("runtime.workspace_root", "Workspace root", "runtime", type="path",
       default="", description="Agent workspace root (the root for file operations)",
       config_key="project_root"),
    _s("runtime.async_loop", "Event loop", "runtime", type="text",
       default="norpagent.loops.nasyncio:NasyncioLoopRuntime",
       description="Scheduler-core implementation address (defaults to the in-house nasyncio)"),
    _s("web.port", "Web port", "runtime", type="number", default=8787,
       description="Web frontend listening port", minimum=1, maximum=65535),

    # ── 元框架（三视角 META；内核构件级） ─────────────────────
    _s("kernel.slot_table", "Slot table", "kernel", type="readonly", default=None,
       description="18 built-in slots + custom slots (register_slot hot-plug)", views=V_META),
    _s("kernel.hook_layers", "Hook layers", "kernel", type="readonly", default=None,
       description="9 standard layers + custom layers (register_layer / register_hook)", views=V_META),
    _s("kernel.event_bus", "Event bus", "kernel", type="readonly", default=None,
       description="Generic event bus (subscribe / intercept / veto)", views=V_META),
    _s("kernel.address_fn", "Address function", "kernel", type="readonly", default=None,
       description="Address resolver (module:attr -> dynamic load)", views=V_META),
]

_SCHEMA_BY_KEY: Dict[str, Dict[str, Any]] = {s["key"]: s for s in KERNEL_SCHEMA}


# ──────────────────────────────────────────────────────────
# 隐藏项（已注册但不在设置面板显示）
# ──────────────────────────────────────────────────────────
# 规则（2026-09-13）：灰化的设置项逐个核实后端是否真有功能——
#   * 后端确有功能且已接入运行态 → 配好 config_key 并重新启用（从本表移出）；
#   * 后端无对应实现 / 由面板之外的机制（profile / CLI / 控制台）控制，
#     面板值改了也不会生效 → 不再显示入口（本表隐藏），但仍登记在设置库中
#     以保留审计与未来接线空间，不做物理删除。
#
# 已接入运行态并从灰化中移出：security.level（→ security_level）、
# model.top_p（→ top_p）、model.call_timeout（→ call_timeout）、
# runtime.snapshot_dir（→ snapshot_dir）。
#
# 安全域「默认常开」项（security.enabled / security.safe_enabled /
# security.signature_verify）：不再 locked 灰化——允许关闭，但前端在关闭前弹
# 出不可通过点击外部/ESC 关闭的强制确认框；后端尊重开关（不再硬编码强制 True）。
HIDDEN_KEYS = frozenset({
    # 模型：无独立实现 / 与 model.active 重复 / 流式恒开
    "model.name", "model.fail_retry", "model.fallback_chain", "model.stream",
    # 循环：无对应消费点
    "loop.turn_boundary_check", "loop.stop_conditions",
    # 工具：无黑名单实现；白名单与 tools.enabled 重复；沙箱/网络策略由预设决定
    "tools.allowlist", "tools.blocklist", "tools.sandbox", "tools.network_policy",
    # 记忆：窗口与 loop.max_rounds 重复；其余无 panel 消费点
    "memory.window_size", "memory.store", "memory.forget_policy",
    "memory.consolidate_threshold", "memory.keep_forgotten_query",
    # 神经总线（CNB）：由 profile / 控制台一键拉起控制，非本面板接线
    "cnb.enabled", "cnb.node_id", "cnb.kind", "cnb.level", "cnb.parent",
    "cnb.port", "cnb.heartbeat", "cnb.cleanup_timeout", "cnb.freeze_policy",
    "cnb.baseline_granularity", "cnb.exec_actions", "cnb.uplink", "cnb.downlink",
    "cnb.slots_per_node",
    # 安全：审计粒度无实现；未签名策略/救援通道由安全套件与 CLI 管理
    "security.audit_granularity", "security.unsigned_plugin_policy",
    "security.safe_mode", "security.rescue_enabled", "security.rescue_port",
    # 进化：仅 breaker_threshold 被消费，观察窗口无消费点
    "evolution.breaker_window",
    # 前端：控制台视角不再提供面板入口（三视角由设置页头开关 + localStorage 记忆）；
    # 框架 JSON 编辑无实现
    "ui.console_view", "ui.frame_advanced_json",
    # 调度与恢复：启动期 / 无 panel 消费点
    "runtime.snapshots_enabled", "runtime.snapshot_keep",
    "runtime.undo_depth", "runtime.async_loop",
    "web.port",
})


# ══════════════════════════════════════════════════════════
# 注册 / 视图 / 镜像桥
# ══════════════════════════════════════════════════════════

def register_kernel_schema(store: Optional[SettingsStore] = None) -> int:
    """把内核动点全量清单注册进设置库（幂等：更新元数据不覆盖现值）。"""
    s = store or get_store()
    specs = [
        {
            "key": item["key"],
            "title": item["title"],
            "category": item["category"],
            "evolvable": item["evolvable"],
            "locked": item["locked"],
            "default": item["default"],
            "description": item["description"],
        }
        for item in KERNEL_SCHEMA
    ]
    n = s.register_schema(specs)
    _prune_removed_schema(s)
    return n


def _prune_removed_schema(s: SettingsStore) -> int:
    """清理设置库中已从内核清单移除的旧键（保留动态注册的 evolution.* 键）。"""
    prune = getattr(s, "prune_schema", None)
    if not callable(prune):
        return 0
    try:
        return int(prune(keep={it["key"] for it in KERNEL_SCHEMA},
                         keep_prefixes=("evolution.",)))
    except Exception:  # noqa: BLE001 — 清理尽力而为，不阻塞注册
        return 0


def ensure_schema(store: Optional[SettingsStore] = None) -> SettingsStore:
    """内核清单 + 进化域清单一次性注册（unbox / Web / CLI 入口共用；幂等）。"""
    s = store or get_store()
    register_kernel_schema(s)
    register_evolution_schema(s)
    return s


def schema_view(store: Optional[SettingsStore] = None) -> List[Dict[str, Any]]:
    """注册表合并视图：DB schema 行 + 本模块扩展元数据（type/options/views...）。"""
    s = store or get_store()
    rows = s.schema() or []
    out: List[Dict[str, Any]] = []
    for row in rows:
        key = str(row.get("key") or "")
        meta = _SCHEMA_BY_KEY.get(key, {})
        item: Dict[str, Any] = dict(row)
        default = None
        if row.get("default_json") is not None:
            try:
                default = _json.loads(row["default_json"])
            except Exception:  # noqa: BLE001
                default = row["default_json"]
        item["default"] = default
        if meta:
            item["type"] = meta.get("type", "json")
            item["views"] = meta.get("views", list(V_USE))
            item["danger"] = bool(meta.get("danger"))
            item["config_key"] = meta.get("config_key")
            item["secret"] = bool(meta.get("secret"))
            item["greyed"] = bool(meta.get("greyed"))
            for k in ("options", "minimum", "maximum", "step", "unit",
                      "enable_when"):
                if k in meta:
                    item[k] = meta[k]
        else:
            item["type"] = "json"
            item["views"] = list(V_USE)
            item["danger"] = False
            item["config_key"] = None
            item["secret"] = False
            item["greyed"] = False
            # 进化域逐点勾选 / 分类键（由 points 动态注册，非静态清单）：
            # 按语义给出控件类型，避免被当成 json 渲染成字符串输入框。
            if key.startswith("evolution.approval."):
                item["type"] = "switch"
                item["enable_when"] = [{"key": "evolution.enabled", "in": [True]}]
            elif key.startswith("evolution.category."):
                item["type"] = "enum"
                item["options"] = ["major", "normal"]
                item["enable_when"] = [{"key": "evolution.enabled", "in": [True]}]
        if key in HIDDEN_KEYS:
            # hidden: still registered in the settings store, but never shown.
            continue
        out.append(item)
    return out


def schema_item(key: str) -> Optional[Dict[str, Any]]:
    """静态清单中的单项元数据（未注册项返回 None）。"""
    return _SCHEMA_BY_KEY.get(str(key))


def mirror_config_to_store(cfg: Dict[str, Any],
                           store: Optional[SettingsStore] = None) -> int:
    """运行态配置 → 设置库镜像（仅声明的 config_key 映射；密钥跳过）。

    语义（保持「显式 vs 默认」可读）：
    - 值 ≠ schema 默认：写入全局层（值未变化不写，避免审计刷屏）；
    - 值 = schema 默认：若库里存在旧显式值则清除（恢复默认态），否则跳过。
    返回实际变更条数。
    """
    if not isinstance(cfg, dict):
        return 0
    s = store or get_store()
    n = 0
    for item in KERNEL_SCHEMA:
        ck = item.get("config_key")
        if not ck or item.get("secret") or ck not in cfg:
            continue
        value = cfg[ck]
        if value is None:
            continue
        cur = s.get_raw(item["key"], _MISS)
        if value == item.get("default"):
            if cur is not _MISS:
                s.delete(item["key"], actor="config-mirror",
                         reason=f"mirror: config key {ck} back to default")
                n += 1
            continue
        if cur == value:
            continue
        s.set(item["key"], value, actor="config-mirror",
              reason=f"mirror from webui config key {ck}")
        n += 1
    return n


def apply_store_to_config(store: Optional[SettingsStore] = None,
                          cfg: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """设置库 → 运行态配置的应用补丁（仅显式值；密钥跳过）。

    返回 {config_key: value} 补丁；调用方合并进配置并持久化 + 热应用。
    """
    s = store or get_store()
    patch: Dict[str, Any] = {}
    for item in KERNEL_SCHEMA:
        ck = item.get("config_key")
        if not ck or item.get("secret"):
            continue
        r = s.resolve(item["key"])
        if r.get("explicit"):
            patch[ck] = r["value"]
    return patch


def config_patch_for_key(key: str,
                         store: Optional[SettingsStore] = None) -> Dict[str, Any]:
    """单个设置键 → 运行态配置补丁（面板 / CLI 写入后的热应用用）。

    仅针对全局层：全局值存在 → 用全局值；否则回落到 schema 默认
    （恢复默认时让运行态配置同步回落）。作用域层（profile/session/temp）
    写入不桥接运行态配置（保持「全局 = 运行态配置镜像」的一致性）。
    """
    item = _SCHEMA_BY_KEY.get(str(key))
    if not item or not item.get("config_key") or item.get("secret"):
        return {}
    s = store or get_store()
    global_value = s.get_raw(item["key"], _MISS)
    if global_value is not _MISS:
        return {item["config_key"]: global_value}
    if item.get("default") is not None:
        return {item["config_key"]: item["default"]}
    return {}


__all__ = [
    "KERNEL_SCHEMA",
    "HIDDEN_KEYS",
    "register_kernel_schema",
    "ensure_schema",
    "schema_view",
    "schema_item",
    "mirror_config_to_store",
    "apply_store_to_config",
    "config_patch_for_key",
    # 分层继承（转发自 store）
    "SCOPE_GLOBAL",
    "SCOPE_PROFILE",
    "SCOPE_SESSION",
    "SCOPE_TEMP",
    "SCOPE_PRIORITY",
    "SCOPE_TITLES",
]
