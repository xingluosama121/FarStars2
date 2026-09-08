# -*- coding: utf-8 -*-
"""
norpagent.cnb.protocol — 中枢神经总线协议层 (Central Nervous Bus Protocol, CNB/1.0)

为 norpagent 多实例升级定义「神经树」通信协议：

1. 树状拓扑链
   每个实例是一个节点（node），有且仅有一个父节点；根节点即「大脑皮层」
   （最高等级 norpagent 实例）。父链构成一棵树，总线保证无环。

2. 分层等级
   level 表示等级，数字越小等级越高：
     level 0 = 大脑皮层（根，最高等级）
     level N = 第 N 层节点（数字越大等级越低）
   低等级无条件服从高等级通过中枢神经总线下达的指令（cmd.*），
   同时不允许改写高等级，只允许回传上报（report.*）。

3. 上行只读 / 下行控制（总线铁律，传输层强制）
   - 上行（uplink）：低 -> 高，只允许 report.*（心跳/事件/审计/请求），
     消息中任何控制性字段（cmd.* / perm.* / exec / config.set 等）都会被
     总线在传输层剥离或拒绝 —— 低层级永远无法控制上层。
   - 下行（downlink）：高 -> 低，只允许 cmd.*（指令），
     接收方必须无条件执行（执行前记录审计日志），且只接受祖先节点发来的指令。

4. 操作权限
   大脑皮层可对任意层级任意单位原子下发权限指令（cmd.perm.grant/revoke/set），
   控制该原子的操作权限（file_read / file_write / process_exec 等，与
   permission_cascade.Permission 枚举语义一致）。

原子指 norpbot、norpilot、norpmemory 等最小单位：每一个原子不仅可以独立
启动独立配置，还可以作为 CNB 树上的一个节点（node_kind 标明原子类型），
由大脑皮层统一调度与授权。
"""

import time
import uuid
from typing import Any, Dict, Optional

# ----------------------------------------------------------------------
# 版本与常量
# ----------------------------------------------------------------------

PROTO_VERSION = "cnb/1.0"

# 等级常量（数字越小等级越高）
LEVEL_CORTEX = 0       # 大脑皮层：最高等级，树根
LEVEL_DIRECTOR = 1     # 层级 1：指挥部 / 小组级
LEVEL_AGENT = 2        # 层级 2：智能体级
LEVEL_ATOM = 3         # 层级 3：原子级（norpbot / norpilot / norpmemory 等）
LEVEL_MAX = 63         # 等级上限（防止恶意注册超深层级）

# 默认端口
DEFAULT_CORTEX_PORT = 17800   # 大脑皮层默认总线端口
DEFAULT_HOST = "127.0.0.1"    # 默认仅本机回环（安全），跨机部署时显式配置

# 消息方向
DIR_UPLINK = "uplink"      # 低 -> 高：只读上报
DIR_DOWNLINK = "downlink"  # 高 -> 低：控制指令
DIR_ACK = "ack"            # 应答（同层双向，仅限应答本条消息）

# ----------------------------------------------------------------------
# 消息类型
# ----------------------------------------------------------------------

# 上行消息类型：只读上报，绝不允许携带控制字段
UPLINK_TYPES: Dict[str, str] = {
    "report.register":   "注册请求（节点上线，请求父节点确认）",
    "report.heartbeat":  "心跳/状态上报（运行中、任务数、资源）",
    "report.event":      "事件上报（任务完成/失败/异常/里程碑）",
    "report.audit":      "审计上报（权限拒绝/指令执行记录）",
    "report.request":    "请求（低等级只能请求，是否批准由高等级决定）",
    "report.deregister": "注销（节点下线）",
}

# 下行消息类型：控制指令，仅祖先节点可发
DOWNLINK_TYPES: Dict[str, str] = {
    "cmd.hello":          "注册确认（父节点批准注册）",
    "cmd.ping":           "探活（要求立即应答）",
    "cmd.exec":           "通用执行指令（action + args）",
    "cmd.stop":           "停止任务（立即终止本地正在执行的任务）",
    "cmd.reload":         "重载配置",
    "cmd.perm.set":       "设置权限（整体覆盖该目标的操作权限）",
    "cmd.perm.grant":     "授予权限",
    "cmd.perm.revoke":    "撤销权限",
    "cmd.topology.sync":  "拓扑同步（皮层广播当前拓扑视图）",
    "cmd.reroot":         "改挂父节点（父链断链救援：父下线/失联时由祖先把本节点提升到自身之下）",
    "cmd.freeze":         "冻结节点（隔离冻结态：拒新任务接单、进程/心跳保活取证、可审计可解除、不触发清扫判 dead）",
    "cmd.unfreeze":       "解除节点冻结（复核后康复回树；可携带 reason 审计）",
    "cmd.subpoena":       "传票取证（最高取证权限：level 0 专属签发，强制取中间层原始审计直传皮层裁决）",
}

# ----------------------------------------------------------------------
# 冻结态常量（隔离冻结态 quarantine）
# ----------------------------------------------------------------------

# 冻结期间仍放行的 exec 动作（只读取证面）。冻结语义 = 拒新任务（接单面
# 关闭：run_task 等变更性动作一律拒绝）+ 进程/心跳存活（取证面保全：
# 只读动作与审计/上下文可读）+ 可审计可解除 + 不触发清扫判 dead
# （冻结节点心跳照常，清扫只按心跳时效判定）。
FROZEN_ALLOWED_ACTIONS: frozenset = frozenset({
    "engine_state",   # 引擎状态（只读）
    "status",         # 节点/引擎状态（只读）
    "inspect",        # 节点全景检查（只读）
    "list_snapshots", # 快照列表（只读）
    "task_records",   # 已受理任务载荷与结果记录（只读，取证/验收回执）
})

# ----------------------------------------------------------------------
# 传票（subpoena）常量（最高取证权限）
# ----------------------------------------------------------------------

# 签发判据四类：签发前必须穷尽摘要裁决并记录判据。
SUBPOENA_BASIS: Dict[str, str] = {
    "confidence_low":     "① 皮层置信不足",
    "vote_tie":           "② 智囊投票平票",
    "evidence_conflict":  "③ 双方证据矛盾",
    "human_named":        "④ 人工点名取证",
}

# 容量分档（KB）：64 → 128 → 256 → 512 四档；
# ≤128KB level 0（皮层）自行批准；>128KB 需人工批准；512KB 只流式分卷裁决
# 不整喂；超 512KB 强制转人工终裁（传票尽头是人）。
SUBPOENA_TIERS_KB: tuple = (64, 128, 256, 512)
SUBPOENA_MAX_KB = 512

# 隔离帧（quarantine envelope）标记：直传包 = RAW/UNTRUSTED + 一次性裁决
# 实例用后销毁 + 裁决上下文不落长期记忆（防围栏反噬，注入面不转移）。
SUBPOENA_ENVELOPE = "RAW/UNTRUSTED"


def is_valid_subpoena_basis(basis: str) -> bool:
    return basis in SUBPOENA_BASIS


def is_valid_subpoena_tier(tier_kb: int) -> bool:
    return int(tier_kb) in SUBPOENA_TIERS_KB

# 上行方向严禁携带的控制字段前缀（传输层强制剥离/拒绝）。
# 语义：控制字段 = 指令/权限/配置类字段名。点分域（cmd.* / perm.* /
# config.set / topology.mutate / control.*）按前缀拦截；裸 exec 只精确
# 匹配或 exec.* 域——"executor"/"exec_count"/"execution" 等只读业务字段
# 名不是控制指令，不应误伤（白盒：误剥字段曾长期静默丢失）。
_CONTROL_PREFIXES = (
    "cmd.",
    "perm.",
    "config.set",
    "topology.mutate",
    "control.",
    "exec.",
)


def is_control_key(key: str) -> bool:
    """判断字段名是否属于控制性字段（上行方向严禁携带）。

    - 点分控制域（cmd.xxx / perm.xxx / config.set* / exec.xxx ...）拒绝；
    - 裸 "exec" 拒绝（下行动作字段名）；
    - "executor" / "exec_count" / "execution" 等普通业务字段放行。
    """
    k = str(key).strip().lower()
    if k == "exec":
        return True
    return any(k.startswith(p) for p in _CONTROL_PREFIXES)


def classify(msg_type: str) -> Optional[str]:
    """返回消息类型所属方向：uplink / downlink / None（未知类型）。"""
    if msg_type in UPLINK_TYPES:
        return DIR_UPLINK
    if msg_type in DOWNLINK_TYPES:
        return DIR_DOWNLINK
    return None


# ----------------------------------------------------------------------
# 权限原子（与 permission_cascade.Permission 语义对齐）
# ----------------------------------------------------------------------

PERMISSION_ATOMS: Dict[str, str] = {
    "file_read":     "读文件",
    "file_write":    "写文件",
    "file_delete":   "删文件",
    "file_list":     "列出目录",
    "process_exec":  "执行子进程",
    "process_shell": "执行 shell 命令",
    "network_out":   "出站网络",
    "network_in":    "入站网络",
    "system_info":   "读取系统信息",
    "plugin_call":   "调用其他插件",
}


def is_valid_perm(perm: str) -> bool:
    return perm in PERMISSION_ATOMS


# ----------------------------------------------------------------------
# 消息信封
# ----------------------------------------------------------------------

def make_envelope(kind: str,
                  from_node: Dict[str, Any],
                  to: str,
                  msg_type: str,
                  payload: Dict[str, Any],
                  msg_id: Optional[str] = None) -> Dict[str, Any]:
    """构造 CNB 消息信封。

    Args:
        kind:      DIR_UPLINK / DIR_DOWNLINK / DIR_ACK
        from_node: {"node_id": str, "level": int, "kind": str}
        to:        目标节点 id（"parent" 表示父节点；皮层发广播可用 "*"）
        msg_type:  消息类型（见 UPLINK_TYPES / DOWNLINK_TYPES）
        payload:   消息体（上行严禁包含控制字段，由总线校验）
        msg_id:    可选，缺省自动生成
    """
    return {
        "proto": PROTO_VERSION,
        "kind": kind,
        "msg_id": msg_id or uuid.uuid4().hex,
        "from": {
            "node_id": from_node.get("node_id", ""),
            "level": int(from_node.get("level", LEVEL_MAX)),
            "kind": from_node.get("kind", "node"),
        },
        "to": to,
        "ts": time.time(),
        "type": msg_type,
        "payload": payload or {},
    }


def sanitize_uplink_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    """上行净化：剥离 payload 中所有控制性字段。

    这是「低层级不可控制上层」的传输层最后一道闸门 —— 即使低等级节点
    恶意构造上行消息，任何控制字段也会在此被删除，只剩只读数据。
    """
    clean = {}
    for k, v in (payload or {}).items():
        if is_control_key(k):
            continue
        clean[k] = v
    return clean


def check_uplink_payload(payload: Dict[str, Any]) -> Optional[str]:
    """校验上行 payload 是否携带控制字段。

    Returns:
        携带的控制字段名；干净则返回 None。
    """
    for k in (payload or {}):
        if is_control_key(k):
            return str(k)
    return None
