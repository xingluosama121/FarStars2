<!-- Split by part from docs/DEVELOPER_MANUAL.EN.md; body is line-for-line identical -->

> **Developer Manual - Part 8: Multimodal and the Central Nervous Bus** | Covers: Chapters 29-30 | [Back to index](../README.md)

---

## Chapter 29 Multimodal: Vision and Sound

> New in v0.9.9. Code: `builtin/ui/multimodal.py` (stdlib-only backend) +
> `builtin/ui/web.py` (`/api/vision` `/api/tts` `/api/stt` `/api/beep`) +
> `front.html` (image attach / voice input / read-aloud / notification tone).
>
> Multimodal = vision (image understanding) + sound (TTS read-aloud, STT
> speech input, notification tone) + **native multimodal input (image / audio /
> video passthrough, v2.x)**. **Design rule: all capability lives on the
> backend; the browser only captures and plays** — nothing depends on
> browser-native speech APIs (SpeechSynthesis / SpeechRecognition). The
> backend engines work offline (Windows SAPI / macOS say / Linux espeak-ng),
> and OpenAI-compatible cloud services can be configured instead.
>
> **New in v2.x (R-021 / R-022)**: multimodal input supports **native
> passthrough** — each modality (image / audio / video) follows its own route
> (`direct` = passed to the model; `service` = converted to text by an external
> service), **direct by default**; adds the video chain, the vision-service API
> key, and the audio service (not limited to speech). See 29.2.5.

### 29.1 Overview: three channels

| Channel | Direction | Backend | Frontend duty |
|---|---|---|---|
| Vision: image understanding | image → description → conversation | `/api/vision` → external vision service | pick / paste / drag images, preview, merge the description into the message |
| Sound: TTS read-aloud | text → audio | `/api/tts` → OS-native synthesizer / OpenAI-compatible service | play the returned wav (🔊 button / auto-speak) |
| Sound: STT input | recording → text | `/api/stt` → Windows local recognizer / OpenAI-compatible service | MediaRecorder capture → WAV(16k) encode → upload → fill the input box |
| Sound: notification tone | — | `/api/beep` → stdlib-generated short WAV | play (new message / task done) |

Layering:

```
front.html (capture / play / interaction)
   │  HTTP
   ▼
web.py  ui.vision_describe / ui.tts_speak / ui.stt_transcribe / ui.beep_notify
   │
   ▼
multimodal.py (stdlib only)
   ├─ describe_image()   external vision service (JSON protocol, compatible with standalone vision.py)
   ├─ text_to_speech()   service first → OS-native (Windows SAPI / macOS say / Linux espeak-ng)
   ├─ speech_to_text()   service first → Windows SAPI local recognizer
   └─ beep_wav()         stdlib RIFF/WAV sine tone
```

### 29.2 Vision: image understanding

#### 29.2.1 Architecture and flow

A text-only model cannot read images directly. v0.9.9 image understanding
follows a "**describe then talk**" route:

```
user uploads an image ──▶ /api/upload (kind="image", base64 kept)
     │
     ▼
on send: /api/vision  {images:[{name,type,data}], prompt}
     │
     ▼
external vision service (vision_service_url) returns a text description
     │
     ▼
frontend composes: 【用户上传了图片】\n图片1：<description>… \n\n <user text>
     │
     ▼
POST /chat to the model — the model "sees" the image
```

- `/api/upload` returns `kind="image"` + raw base64 for images (mime
  `image/*` or a known image extension); text files behave as before;
- three frontend entries: the 🖼️ button (file picker, multiple), Ctrl+V
  paste, drag & drop; thumbnail preview before sending, removable one by one
  (max 6 images);
- on failure (disabled / not configured / service error) a toast explains the
  reason and **the images are kept** so they can be resent after fixing the
  configuration.

#### 29.2.2 REST endpoint: `POST /api/vision`

Request:

```json
{
  "images": [
    {"name": "shot.png", "type": "image/png", "data": "<base64 without data: prefix>"}
  ],
  "prompt": "请详细描述这张图片的内容，包括画面主体、文字与关键细节。"
}
```

Response:

```json
{
  "ok": true,
  "descriptions": [
    {"name": "shot.png", "description": "画面主体是一台笔记本……"}
  ]
}
```

- `ok=false` carries an `error` reason (disabled / not configured / service error);
- one failed image does not break the batch: it gets an `error` field, the rest return normally;
- prerequisite: enable "Vision API" in settings and fill `vision_service_url`.

#### 29.2.3 External vision service protocol (for self-hosted services)

The backend POSTs `application/json` to `vision_service_url`:

```json
{
  "image_base64": "<base64>",
  "ext": "png",
  "mime": "image/png",
  "prompt": "请详细描述这张图片的内容……"
}
```

Accepted responses (any of the three shapes):

```json
{"description": "……"}
{"ok": true, "description": "……"}
{"text": "……"}
```

> Compatible with the standalone `vision.py` / `vision_adapters.py`
> `describe_with_provider` adapters: wrap one of the built-in providers
> (openai_compatible / anthropic / llama_cpp) behind a thin HTTP service.

#### 29.2.4 Frontend interaction

- paper-clip button: file picker (image / audio / video / text, multiple);
- paste: Ctrl+V of an image adds it to the pending attachment bar;
- drag & drop: dropping files anywhere adds them;
- attachment bar: thumbnail / type icon + file name + remove; cleared after a
  successful send;
- sending: attachments ride the `POST /chat` `attachments` field and are routed
  by the backend (29.2.5); plain-text files are merged into the prompt;
- user bubbles echo image thumbnails (sent here) / type chips (restored history).

#### 29.2.5 Native passthrough and per-modality routing (v2.x, R-021 / R-022)

Attachments are passed **natively** by default — the payload itself becomes a
native content part of the model message (no forced text transcription first);
each modality can be switched to an external service:

| Modality | direct (default) form | service route |
|---|---|---|
| image | `{"type":"image_url","image_url":{"url":"data:image/png;base64,…"}}` | `vision_service_url` (29.2.3 protocol, Bearer key supported) |
| audio | `{"type":"input_audio","input_audio":{"data":"…","format":"wav"}}` | `audio_service_url` (understanding / transcription; **not limited to speech** — music / environment audio accepted) |
| video | `{"type":"video_url","video_url":{"url":"data:video/mp4;base64,…"}}` (compatible extension; actual video support depends on the endpoint) | `video_service_url` |

- Routing switches (Settings → Multimodal, per modality): `mm_image_route` /
  `mm_audio_route` / `mm_video_route`, values `direct` / `service`;
- text-like attachments (txt / md / json / code) are always merged into the
  prompt (routing not involved);
- media service protocol: POST JSON `{"kind": "audio"|"video",
  "data_base64": …, "ext": …, "mime": …, "prompt": …}`; responses accept
  `description` / `text` / `transcript` / `content` / `result`, optional
  `Authorization: Bearer <key>` (`media_describe`, `builtin/ui/multimodal.py`);
- attachments persist with the message (SQLite attachment column; memory stores
  objects directly) and are re-sent with history on replay (standard multimodal
  chat behavior);
- size caps: image 10MB / audio 20MB / video 32MB; service keys are
  DPAPI-encrypted.

### 29.3 Sound: TTS read-aloud

#### 29.3.1 Architecture

```
frontend clicks 🔊 / auto-speak
   │  POST /api/tts  {text, voice, rate}
   ▼
multimodal.text_to_speech()
   ├─ tts_service_url set → OpenAI-compatible /audio/speech (optional Bearer key)
   └─ otherwise OS-native synthesizer (zero config, offline):
        Windows → PowerShell System.Speech (SAPI) → WAV
        macOS   → say --data-format=LEI16@22050 → WAV
        Linux   → espeak-ng / espeak -w → WAV
   ▼
returns {ok, audio_base64, mime:"audio/wav"}
   ▼
frontend plays with new Audio(data:audio/wav;base64,…)
```

- **Windows SAPI**: `Add-Type System.Speech` via PowerShell
  `-EncodedCommand` (UTF-16LE base64, no quoting issues) synthesizes WAV;
  `SelectVoice` selects the voice (e.g. "Microsoft Huihui Desktop" Chinese /
  "Microsoft David Desktop" English), `Rate` (-10..10) maps from 0.5–2.0×;
- **macOS**: `say -v <voice> -r <wpm> -o out.wav --data-format=LEI16@22050`;
- **Linux**: `espeak-ng -w out.wav -s <wpm> -v <voice>` (clear error when not installed);
- **OpenAI-compatible service** (`tts_service_url`): POST JSON
  `{"model":"tts-1","input":text,"voice":voice,"response_format":"wav","speed":rate}`,
  optional `Authorization: Bearer <tts_service_api_key>`.

#### 29.3.2 Endpoint: `POST /api/tts`

```json
request  {"text": "你好", "voice": "", "rate": 1.0}
response {"ok": true, "audio_base64": "<wav base64>", "mime": "audio/wav"}
```

- empty `voice` = system default; `rate` 0.5–2.0 (defaults to config `tts_rate`);
- `tts_enabled=false` or empty text → `{ok:false, error}`.

#### 29.3.3 Frontend

- every assistant reply has a 🔊 read-aloud button (click to speak, click again to stop; becomes ⏸ while playing);
- with "auto-read replies" enabled, the full reply is read aloud when the task finishes;
- a rate slider (0.5–2.0×) and a voice-name text field (e.g. "Microsoft Huihui Desktop").

### 29.4 Sound: STT speech input

#### 29.4.1 Architecture

```
frontend clicks 🎤 → getUserMedia capture → MediaRecorder(webm)
   │
   ▼ frontend decode: AudioContext.decodeAudioData → 16kHz mono PCM → encode WAV
POST /api/stt  {audio:"<wav base64>", mime:"audio/wav"}
   │
   ▼
multimodal.speech_to_text()
   ├─ stt_service_url set → OpenAI-compatible /audio/transcriptions (multipart)
   └─ otherwise Windows local recognizer (SAPI DictationGrammar; en-US built in;
        zh-CN needs the Chinese speech language pack; clear error otherwise)
   ▼
returns {ok, text}
   ▼
frontend fills the recognized text into the input box (editable before sending)
```

- the frontend always converts the recording to **16 kHz mono WAV** — the
  common format accepted by both local engines and cloud services (webm would
  not be decodable by the local engine);
- **Windows local recognition**: PowerShell System.Speech.Recognition +
  `DictationGrammar` + `SetInputToWaveFile`; `stt_language` (default en-US)
  selects the engine language; timeout follows `api_request_timeout`;
- **OpenAI-compatible service** (`stt_service_url`): multipart
  `file=audio.wav` + `model=whisper-1` + `language=<stt_language>`,
  optional Bearer key;
- non-Windows without a configured service →
  `{ok:false, error:"当前平台没有本地语音识别引擎，请在设置中配置 STT 服务地址"}`.

#### 29.4.2 Endpoint: `POST /api/stt`

```json
request  {"audio": "<wav base64>", "mime": "audio/wav"}
response {"ok": true, "text": "recognized text"}
```

- audio limit 10MB; empty recognition → `{ok:false, error:"没有识别到语音内容"}`.

### 29.5 Notification tone: `POST /api/beep`

- the backend synthesizes an 880 Hz sine short tone (RIFF/WAV with fade in/out
  to avoid clicks) using the standard library; the frontend caches it after
  the first fetch;
- trigger: task completion with a reply, when "new-message tone" is enabled;
- returns `{ok, audio_base64, mime:"audio/wav"}`.

### 29.6 Configuration reference

| Key | Default | Description |
|---|---|---|
| `vision_enabled` | false | enable the vision API (image understanding) |
| `vision_service_url` | "" | external vision service URL (protocol in 29.2.3) |
| `vision_service_api_key` | "" | vision service key (DPAPI-encrypted; R-022) |
| `tts_enabled` | true | enable TTS read-aloud |
| `tts_service_url` | "" | optional OpenAI-compatible `/audio/speech` endpoint (empty = OS native) |
| `tts_service_api_key` | "" | TTS service key (DPAPI-encrypted on disk) |
| `tts_voice` | "" | voice name (e.g. "Microsoft Huihui Desktop" / "alloy") |
| `tts_rate` | 1.0 | speech rate multiplier 0.5–2.0 |
| `stt_service_url` | "" | optional OpenAI-compatible `/audio/transcriptions` endpoint (empty = Windows local) |
| `stt_service_api_key` | "" | STT service key (DPAPI-encrypted on disk) |
| `stt_language` | "en-US" | local recognition language (zh-CN needs a Windows Chinese language pack) |
| `sound_notify_enabled` | true | new-message notification tone |
| `auto_speak_enabled` | false | auto-read assistant replies |
| `mm_image_route` | "direct" | image route: `direct` (model) / `service` (external, 29.2.5) |
| `mm_audio_route` | "direct" | audio route (not limited to speech) |
| `mm_video_route` | "direct" | video route |
| `audio_service_url` | "" | audio understanding / transcription service URL (29.2.5 protocol) |
| `audio_service_api_key` | "" | audio service key (DPAPI-encrypted) |
| `video_service_url` | "" | video service URL |
| `video_service_api_key` | "" | video service key (DPAPI-encrypted) |

> Sound preferences (auto-speak / tone / voice / rate) are saved into the
> backend config via the settings panel's "🔊 Sound" section; service URLs and
> keys are stored there too (keys share the DPAPI encryption path of `api_key`,
> see 22.4 and `_SECRET_KEYS`).

### 29.7 Privacy and security

- **images** are sent base64-encoded to the configured vision service; local
  services (e.g. llama.cpp) are fully offline; the page notes that images are
  sent to the vision provider;
- **native passthrough (v2.x)**: under the `direct` route the attachment itself
  is sent to the configured model endpoint (and re-sent with history); under
  `service` it is sent to the configured service. Choose local models / services
  when egress matters, or route that modality more conservatively;
- **recordings** are processed locally by default (Windows SAPI local
  recognition, no data leaves the machine); they are uploaded only when an STT
  service is configured;
- **TTS** native path is fully offline; the cloud path sends only text;
- service keys are DPAPI-encrypted on Windows (0600 file elsewhere);
  `/api/config` masks secret fields;
- multimodal calls reuse `api_request_timeout` as the hard timeout.

### 29.8 Developer access: calling multimodal directly

```python
from norpagent.builtin.ui import multimodal as mm

# vision: image → description (external service)
desc = mm.describe_image(
    image_base64="iVBOR...", ext="png", mime="image/png",
    service_url="http://127.0.0.1:9000/vision", prompt="describe this image",
)

# TTS: text → wav (OS-native synthesizer when no service is configured)
audio, mime = mm.text_to_speech(
    "Hello", voice="Microsoft David Desktop", rate=1.0,
)
assert mime == "audio/wav" and audio[:4] == b"RIFF"

# STT: wav → text (Windows local recognition or the configured service)
text = mm.speech_to_text(audio, "audio/wav", language="en-US")

# notification tone
beep = mm.beep_wav()
```

All errors surface as `MultimodalError` (human-readable messages); handle them
with the `ok=false` semantics.

### 29.9 FAQ

| Symptom | Cause | Fix |
|---|---|---|
| sending an image reports "视觉 API 未启用" | not enabled | Settings → Vision API → enable + fill the service URL |
| image reports "未配置视觉服务地址" | enabled but no URL | fill `vision_service_url` (self-host protocol in 29.2.3) |
| read-aloud fails: Windows TTS error | SAPI unavailable / bad voice name | use an installed voice (PowerShell: `Add-Type -AssemblyName System.Speech; (New-Object System.Speech.Synthesis.SpeechSynthesizer).GetInstalledVoices()`) |
| Linux read-aloud: espeak not found | not installed | `apt install espeak-ng`, or configure a TTS service URL |
| speech input: no speech content | noise / language mismatch | speak closer to the mic; en-US works out of the box, zh-CN needs the Windows Chinese language pack or an STT service |
| speech input: no local engine on this platform | macOS/Linux without a service | Settings → Sound → STT service URL (OpenAI compatible) |
| tone does not play | `sound_notify_enabled=false` | Settings → Sound → new-message tone |

---

## Chapter 30 Central Nervous Bus: Multi-Instance and the Neural Tree

> Module: `src/nervous_bus/` (shipped inside the PyPI package as the top-level package `nervous_bus` since v1.0.2; before 1.0.1 it lived at the repository root as `nervous_bus/`) | Protocol: CNB/1.0 | Standalone design doc: `NERVOUS_BUS.md`
>
> **Core rule**: the cortex (the highest norpagent instance) controls the operation permissions of any atom at any level through the Central Nervous Bus; lower levels may only report upward and can never control upper levels; the neural tree is a tree-shaped topology chain; lower levels obey higher-level commands unconditionally and are forbidden to rewrite higher levels — they may only report back.

### 30.1 Overview and Core Rules

The Central Nervous Bus (CNB) adds **multi-instance** capability to norpagent: any number of norpagent processes form a "neural tree" whose root is the **cortex** (the highest-level instance); every other instance is a **node** (an atomic unit: norpbot / norpilot / norpmemory ... or any custom instance). Each atom can not only start and configure itself independently, but can also join the CNB tree as a node (`node_kind` marks the atom type), centrally scheduled and authorized by the cortex.

```
                    ┌──────────────────────────┐
                    │  Cortex (level 0)           │  highest level, tree root
                    │  最高级 norpagent 实例      │  full topology + control over every level
                    └────────────┬─────────────┘
                                 │  downlink cmd.* (high -> low, unconditional obedience)
                                 │  uplink report.* (low -> high, read-only)
                    ┌────────────┴─────────────┐
                    │   中枢神经总线 CNB          │  protocol + topology + permissions + transport
                    └────────────┬─────────────┘
              ┌──────────────────┼──────────────────┐
       ┌──────┴──────┐    ┌──────┴──────┐    ┌──────┴──────┐
       │ level 3 原子  │    │ level 3 原子  │    │ level 3 原子  │
       │ norpbot-01   │    │ norpmemory-01│    │   ...        │
       └──────┬──────┘    └─────────────┘    └─────────────┘
       ┌──────┴──────┐
       │ level 4 原子  │   ← tree topology chain: every node has exactly one parent
       │ norpilot-01  │
       └─────────────┘
```

Requirements map one-to-one to implementation mechanisms:

| Requirement | Mechanism | Code location |
|---|---|---|
| Tree topology chain | one unique parent per node; cycle check + level check at registration; deep registration forwards level by level up to the cortex | `topology.py` `Topology.register` / `_forward_uplink` |
| Layered instances, layer = level | the smaller the `level` number, the higher the rank; `0` = cortex; children must exceed their parent's level; a registered level can never be altered | `protocol.py` LEVEL_*; `topology.py` anti-rewrite |
| Cortex controls any atom's permissions at any level | `cmd.perm.grant/revoke/set`; targets support exact `node_id` / `node_kind` wildcard / `*` full wildcard | `cortex.py` `perm_grant/perm_revoke/perm_set`; `permissions.py` |
| Lower levels only report, never control upper levels | uplink allows only `report.*`; the transport layer forcibly strips/rejects any control field | `protocol.py` `check_uplink_payload`; `node.py` `_handle_uplink` |
| Lower levels obey higher-level commands unconditionally | downlink `cmd.*` is accepted only from ancestors; legal commands execute unconditionally with an audit record | `node.py` `_handle_downlink` + ancestor-chain check |
| Rewriting higher levels is forbidden | the topology layer forbids level/kind/parent rewrites; uplink has no control channel | `topology.py` anti-rewrite; `protocol.py` control-field blacklist |
| Report back only | heartbeat/event/audit/request all travel through the `report.*` uplink; approval is decided by higher levels | `node.py` `report_*` |

### 30.2 Tree Topology and Layered Levels

A **node** is one atomic unit on the neural tree: at startup each instance declares its `node_id`, `kind` (atom type) and `level`, and points at its single `parent` (the parent node's bus URL). The root is the cortex, with `parent=None`. The whole-tree shape comes from an **explicit definition** (§30.19: no preset shape; every required parameter — per-level LEVEL / count / lower-level parent / port — is validated, and a missing one is reported explicitly).

Level constants (the smaller the number, the higher the rank):

| Constant | Value | Meaning |
|---|---|---|
| `LEVEL_CORTEX` | 0 | the cortex: highest level, tree root |
| `LEVEL_DIRECTOR` | 1 | level 1: directorate / group level |
| `LEVEL_AGENT` | 2 | level 2: agent level |
| `LEVEL_ATOM` | 3 | level 3: atom level (norpbot / norpilot / norpmemory ...) |
| `LEVEL_MAX` | 63 | level ceiling (blocks malicious ultra-deep registration) |

The `Topology` layer provides thread-safe tree management:

| Method | Description |
|---|---|
| `register(node_id, level, kind, parent_id, meta)` | register a node: cycle check (walk up the parent chain) + level check (child level must exceed parent's); a registered node's level/kind/parent are **immutable** (raises `ValueError`) |
| `unregister(node_id)` | deregister a node (**cascades to all descendants**, keeping the tree intact) |
| `is_ancestor(a, n)` / `is_descendant(d, n)` | ancestor/descendant checks (self is never an ancestor: same-level nodes cannot control each other) |
| `ancestor_chain(n)` | ancestor chain (parent -> root, includes parent, excludes self) |
| `subtree(n)` | descendant node-id list (DFS, includes self) |
| `render_ascii()` / `render_tree()` | readable tree rendering (for the cortex console / CLI) |
| `heartbeat(node_id)` / `sweep_dead(timeout=30)` | heartbeat refresh / sweep nodes silent past the timeout (marked dead, not unregistered) |

### 30.3 The CNB/1.0 Message Protocol

Every message uses one envelope (`protocol.make_envelope`):

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

**Uplink (low -> high, read-only)**, only `report.*` allowed:

| Type | Description |
|---|---|
| `report.register` | registration request (forwarded level by level to the cortex, with a `via` anti-loop marker) |
| `report.heartbeat` | heartbeat/status report (every 5 s by default; carries the descendant liveness overview) |
| `report.event` | event report (task done/failed/exception/milestone) |
| `report.audit` | audit report (permission denials / command executions) |
| `report.request` | request (lower levels may only ask; approval is decided by higher levels) |
| `report.deregister` | deregistration (node going offline) |

**Downlink (high -> low, control)**, accepted only from ancestor nodes:

| Type | Description |
|---|---|
| `cmd.hello` | registration confirmation (parent approves, carries the ancestor chain) |
| `cmd.ping` | liveness probe (must answer immediately) |
| `cmd.exec` | generic execution command (action + args; the neural permission table is checked first) |
| `cmd.stop` | stop tasks (immediately terminate locally running tasks) |
| `cmd.reload` | reload configuration |
| `cmd.perm.set` | set permissions (overwrite the target's permission set) |
| `cmd.perm.grant` / `cmd.perm.revoke` | grant / revoke a permission |
| `cmd.topology.sync` | topology sync (the cortex broadcasts its topology view) |

**Permission atoms** (aligned with `permission_cascade.Permission` semantics):

`file_read` `file_write` `file_delete` `file_list` `process_exec` `process_shell` `network_out` `network_in` `system_info` `plugin_call`

### 30.4 Module Layout

**v1.0.7 kernel integration**: the neural implementation lives in
`src/norpagent/cnb/` (a norpagent kernel submodule — ready with
`import norpagent`; version merged into norpagent, no separate version); the old
standalone top-level package `src/nervous_bus/` remains as a **compatibility
shim** (re-export + submodule injection + thin cli/demo files) so 1.0.6 and
earlier scripts keep working.

```
src/norpagent/cnb/           # implementation location since v1.0.7
??? __init__.py      # package entry and exports (protocol/topology/permissions/node/cortex/engine)
??? protocol.py      # protocol layer: envelope, directions, levels, permission atoms, uplink control-field blacklist
??? topology.py      # tree topology chain: register/unregister/cascade, ancestor checks, cycle and anti-rewrite validation
??? permissions.py   # neural permission table: node_id/node_kind/* three-level matching, last write wins
??? bus.py           # transport layer: zero-dependency HTTP (one bus endpoint per node) + client
??? node.py          # CNB node: register/heartbeat/event report/command execution/action registry/audit
??? cortex.py        # the cortex: root node + any-level control API + REPL console
??? engine.py        # engine binding (new in v1.0.7): CnbAdapter kernel action surface + env auto-mount
??? cli.py           # command line: cortex/node/topo/ping/exec/stop/reload/perm/reports/audit/sync
??? demo.py          # quick demo (simulates a neural tree in-process)
src/nervous_bus/             # compatibility shim since v1.0.7 (re-exports norpagent.cnb)
??? __init__.py      # symbol re-export + sys.modules submodule injection + version follows norpagent
??? cli.py / demo.py # physical thin files (python -m entries run through the file path)
```

The transport layer (`bus.py`) is zero-dependency (stdlib only): each node runs a `ThreadingHTTPServer` as its bus access point and the client delivers via `urllib`. Bus endpoints:

| Endpoint | Method | Description |
|---|---|---|
| `/cnb/msg` | POST | deliver a CNB message envelope (JSON) |
| `/cnb/ctrl` | POST | cortex control endpoint (cortex only; CLI / REPL drive the cortex through it) |
| `/cnb/health` | GET | health check (returns node identity and level) |
| `/cnb/reports` | GET | reports received by this node |

### 30.5 Quick Start

**Start the cortex** (GUI-less background process; bypasses the single-instance lock; instances run in parallel). Since v1.0.7 the cortex process **assembles a full norpagent engine by default** (the cortex is the top-level norpagent instance; `--bare` returns to the plain nervous shell):

```bash
# repository source (root main.py)
python main.py --norp-cortex --port 17800 --repl

# all three entries are equivalent; with a PyPI install (v1.0.2+) both
# `python -m` and the `norpagent` subcommand are available.
# v1.0.7 kernel integration: commands run through norpagent.cnb.cli
# (nervous_bus is a compatibility shim; the old path keeps working)
python -m norpagent.cnb.cli cortex --port 17800 --repl
norpagent cortex --port 17800 --repl
```

> Note: `python main.py --norp-cortex ...` is the **repository-source** entry (a PyPI install has no repository main.py — use the `norpagent` / `python -m` forms there). Ordinary GUI / embedded / np() instances join the neural tree without any subcommand — just set the `NORP_CNB_*` env vars and start normally (see 30.8; per-instance **opt-in**: no env vars, no mount).

**Mount nodes** (tree topology chain, level by level; shown with the `norpagent node` subcommand — `python main.py --norp-node ...` is equivalent). Since v1.0.7 node processes also **assemble a full kernel engine by default** — every atom is a real task-capable agent instance (`--bare` returns to the plain probe shell):

```bash
# level-1 atom: cortex -> norpbot-01
norpagent node --id norpbot-01 --kind bot \
    --parent http://127.0.0.1:17800 --port 17801 --level 3
#    (repository-source equivalent: python main.py --norp-node --id norpbot-01 ...)

# level-2 atom: cortex -> norpbot-01 -> norpilot-01 (chained)
norpagent node --id norpilot-01 --kind pilot \
    --parent http://127.0.0.1:17801 --port 17802 --level 4

# another branch: cortex -> norpmemory-01
norpagent node --id norpmemory-01 --kind memory \
    --parent http://127.0.0.1:17800 --port 17803 --level 3
```

**Cortex command-line control** (`--root` points at the cortex bus URL; `norpagent topo ...` is equivalent to `python -m norpagent.cnb.cli topo ...` — shown with `python -m` below):

```bash
# topology
python -m norpagent.cnb.cli topo --root http://127.0.0.1:17800

# commands (any atom at any level)
python -m norpagent.cnb.cli ping   --root ... --node norpilot-01
python -m norpagent.cnb.cli exec   --root ... --node norpbot-01 --action run_task
python -m norpagent.cnb.cli stop   --root ... --node norpbot-01
python -m norpagent.cnb.cli reload --root ... --node norpbot-01

# permission control (node_id / node_kind / * targets)
python -m norpagent.cnb.cli perm --root ... --grant  --target-type node_id   --target norpbot-01 --perm file_write
python -m norpagent.cnb.cli perm --root ... --revoke --target-type node_kind --target bot       --perm process_shell
python -m norpagent.cnb.cli perm --root ... --set    --target-type node_kind --target bot --allows '{"file_delete": false}'

# reports, audit and topology broadcast
python -m norpagent.cnb.cli reports --root ... --n 50
python -m norpagent.cnb.cli audit   --root ... --n 50
python -m norpagent.cnb.cli sync    --root ...          # cortex broadcasts the topology
```

**Cortex REPL console** (type commands after starting with `--repl`):

```
cortex> topo                            # view the topology tree
cortex> ping norpbot-01                 # probe liveness
cortex> exec norpbot-01 run_task        # issue an execution command
cortex> stop norpbot-01                 # stop tasks
cortex> reload norpbot-01               # reload configuration
cortex> grant node_kind bot file_write  # grant a permission
cortex> revoke node_id norpbot-01 process_shell   # revoke a permission
cortex> set node_kind bot '{"process_shell": false}'  # overwrite permissions
cortex> sync                            # broadcast the topology
cortex> reports / audit                 # view reports / audit
```

### 30.6 The Cortex Control API (Cortex)

`Cortex` inherits `NervousNode` and is the neural-tree root (level 0, no parent). Start and control it programmatically:

```python
from norpagent.cnb import Cortex

cortex = Cortex(node_id="cortex", host="127.0.0.1", port=17800)
cortex.start()

# probe / execute / stop / reload (any atom at any level)
print(cortex.ping("norpbot-01"))
print(cortex.exec_cmd("norpbot-01", "run_task", {"n": 3}, perm="process_exec"))
print(cortex.stop_node("norpbot-01"))
print(cortex.reload_node("norpbot-01"))

# permission control: exact node_id / node_kind wildcard / * full
cortex.perm_grant("node_kind", "bot", "file_write")
cortex.perm_revoke("node_id", "norpbot-01", "process_shell")
cortex.perm_set("node_kind", "bot", {"file_delete": False, "network_out": False})

# topology broadcast and view
cortex.sync_topology()
print(cortex.topology_view()["tree"])

# interactive console (blocking)
cortex.repl()
```

Method signatures at a glance:

| Method | Signature | Description |
|---|---|---|
| `ping` | `ping(node_id) -> dict` | liveness probe |
| `exec_cmd` | `exec_cmd(node_id, action, args=None, perm="process_exec", path="") -> dict` | issue an execution command (neural permission table checked first) |
| `stop_node` / `reload_node` | `(node_id) -> dict` | stop tasks / reload configuration |
| `perm_grant` | `perm_grant(target_type, target, perm, scope=None) -> dict` | grant a permission |
| `perm_revoke` | `perm_revoke(target_type, target, perm) -> dict` | revoke a permission |
| `perm_set` | `perm_set(target_type, target, allows) -> dict` | overwrite permissions |
| `sync_topology` | `sync_topology() -> dict` | broadcast the topology to all descendants |
| `topology_view` | `topology_view() -> dict` | topology view (size / tree / nodes) |

The cortex also exposes the HTTP control endpoint `/cnb/ctrl` (for the CLI / external consoles; loopback-only by default):

```python
from norpagent.cnb import BusClient
cli = BusClient(timeout=15.0)
r = cli.post_ctrl("http://127.0.0.1:17800", {"op": "topo"})
r = cli.post_ctrl("http://127.0.0.1:17800", {"op": "ping", "node": "norpbot-01"})
r = cli.post_ctrl("http://127.0.0.1:17800", {"op": "grant", "target_type": "node_kind",
                                             "target": "bot", "perm": "file_write"})
```

Supported `/cnb/ctrl` operations: `topo` `nodeinfo` `ping` `exec` `stop` `reload` `grant` `revoke` `set` `sync` `reports` `audit`.

### 30.7 The Node API (NervousNode)

Every norpagent instance can embed a `NervousNode` and join the neural tree as an atom:

```python
from norpagent.cnb import NervousNode

node = NervousNode(
    node_id="norpbot-01", kind="bot", level=3,
    parent_url="http://127.0.0.1:17800", port=17801,
    meta={"desc": "terminal-operation atom"}, heartbeat_interval=5.0,
)

# register callbacks (where cortex commands land)
node.on("exec", lambda p: {"echo": p.get("action"), "node": node.node_id})
node.on("stop", lambda: {"stopped": True})
node.on("reload", lambda: {"reloaded": True})
node.on("perm_changed", lambda summary: print("permissions changed by cortex:", summary))
node.on("registered", lambda parent_id: print("registration confirmed, parent:", parent_id))

node.start()   # start the bus + register + heartbeat (5 s default)
# ...
node.stop()    # deregister + stop heartbeat + close the bus
```

Callback events:

| `exec` | `(payload: dict) -> dict` | cortex `cmd.exec`; **since v1.0.7 only the fallback when the action registry misses**; the neural permission table is checked first |
|---|---|---|
| `exec` | `(payload: dict) -> dict` | cortex `cmd.exec`; the return value becomes the receipt detail; the neural permission table is checked first |
| `stop` | `() -> dict` | cortex `cmd.stop` (stop local tasks) |
| `reload` | `() -> dict` | cortex `cmd.reload` (reload configuration) |

**Kernel action registry (v1.0.7 kernel integration)**: cortex `cmd.exec` actions
route to registered handlers first; only misses fall back to the `exec` callback;
when neither exists the node rejects the action directly (`ok=False` + top-level
`error`; contract upgrade over 1.0.6 — see 30.16). The engine binding layer
(`norpagent.cnb.engine.CnbAdapter`) registers the NorpEngine public API as a
**14-action kernel surface**; bare nodes may register placeholder actions:

```python
node.register_action("my_action", lambda payload: {"echo": payload.get("args", {})})
node.has_action("my_action")      # True
node.list_actions()               # registered action names (visible to cortex inspect)
node.unregister_action("my_action")
```

**Heartbeat status provider (v1.0.7)**: after registering a `(status, extra_dict)`
provider the heartbeat carries kernel state automatically (the engine binding
injects `engine_state` / `active_tasks` / `version` / `actions` — visible in
cortex `reports`):

```python
node.set_heartbeat_provider(lambda: ("busy", {"task_count": 2, "note": "..."}))
node.set_heartbeat_provider(None)   # back to the basic heartbeat
```
| `perm_changed` | `(summary: dict) -> None` | cortex `cmd.perm.*` changed this node's permission table |
| `registered` | `(parent_id: str) -> None` | registration confirmed by the parent |

Uplink report methods (sent to the parent only, converging level by level at the cortex; a middle layer records locally and then forwards, so deep nodes' heartbeats / events / requests are all visible at the cortex):

```python
node.report_heartbeat()                              # heartbeat and status (running by default)
node.report_heartbeat(status="busy", task_count=3)   # custom status fields (busy/idle/metrics; visible at the cortex)
node.report_event("task_done", {"task": "t1"})
node.report_audit("perm_denied", "process_shell")
node.report_request("network_out", "need access to an external API")   # lower levels may only ask
```

**Deep-tree self-healing**: when a heartbeat is rejected by the parent (typical: the parent restarted under the same id, or the cortex rebuilt its view after rescue/sweep), the node re-registers automatically; parent-chain rescue is driven from above with `cmd.reroot` (see 30.14).

### 30.8 A GUI Instance as a Node (env-var auto-mount, implemented since v1.0.2)

A normally launched GUI / embedded / np() norpagent instance can also join the neural tree as a node: **set the `NORP_CNB_*` env vars and start it normally** (no subcommand, no change to how you start it). Mounting runs on a background thread and never delays startup; any mounting failure **degrades to a plain single instance** (a warning is printed, the main program is untouched); the engine shutdown path unmounts automatically. **2026-09-12 feedback round (final error semantics)**: config errors (missing port / missing node id / a tree definition with missing required parameters) also never block startup — the host starts normally, the error is printed explicitly and **the tree is not loaded**; query it via `engine.cnb_status` (`config-error`) and `engine.cnb_error` (see §30.19.6).

> Contract (prevents double mounting): auto-mount is the kernel's default path; `NORP_CNB_MANAGED=1` makes the **kernel skip mounting** (an upper layer builds its own node in managed mode). The contract reads **environment variables only — config.json is NOT consulted** (the early manual's "same keys in config.json" claim was never implemented and has been removed).

| Env var | Default | Description |
|---|---|---|
| `NORP_CNB_NODE` | (empty = disabled) | node id; **setting it enables auto-mount** |
| `NORP_CNB_KIND` | `agent` | atom type (bot / pilot / memory / ...) |
| `NORP_CNB_LEVEL` | `3` | level (must exceed the parent's; 1–63) |
| `NORP_CNB_PARENT` | `http://127.0.0.1:17800` | parent bus URL |
| `NORP_CNB_PORT` | `17801` | this node's bus port (1–65535) |
| `NORP_CNB_HEARTBEAT` | `5.0` | heartbeat interval in seconds (0.5–3600) |
| `NORP_CNB_DESC` | (empty) | optional node meta description |
| `NORP_CNB_MANAGED` | unset | `1` = kernel mounting skipped (managed mode; the upper layer builds its own node) |
| `NORP_CNB_TREE` | (empty) | neural-tree definition (JSON / PY file path or JSON text); NODE/PORT are then carried by the definition (see §30.19) |

```bash
set NORP_CNB_NODE=norpbot-gui
set NORP_CNB_KIND=bot
set NORP_CNB_LEVEL=3
set NORP_CNB_PARENT=http://127.0.0.1:17800
set NORP_CNB_PORT=17801
python main.py            # repository-source entry; with a PyPI install use norpagent / python -m norpagent
```

**Implementation location**: `NorpEngine.start()` → `runtime/engine.py` `_setup_cnb()` → `runtime/cnb.py` (a forwarding layer since v1.0.7) → **`norpagent.cnb.engine.setup_cnb()`** (the implementation). The mount thread calls `NervousNode.start()` + registration retries (every 5 s, budget ≈ 30 s; an unreachable parent degrades to a plain instance); try-import degradation if CNB is unavailable (since v1.0.7 CNB ships inside norpagent, so this path only triggers in stripped environments). Status: `engine.cnb` (adapter; `status`: `mounting` / `mounted` / `failed` / `stopped`) and `engine.cnb_status` (also `not-mounted` / `managed-skip` / `config-error` — a config error is reported explicitly while the tree is not loaded and the host keeps running); config / mount error details are read via `engine.cnb_error`.

**The cortex downlink surface (kernel action registry since v1.0.7)**:

| Downlink | Landing | Semantics |
|---|---|---|
| `cmd.exec` | **kernel action registry** (14 kernel actions registered by the engine binding — see the action table in 30.16; a miss falls back to the legacy `exec` callback, and with neither the node rejects: `ok=False` + top-level `error`) | task: `run_task` / `status` / `stop_task`; state: `engine_state` / `inspect`; snapshot: `snapshot` / `rollback` / `undo` / `redo` / `list_snapshots` / `mark_good`; ops: `remount` / `reload_plugins` / `stop_engine`. Each action calls the NorpEngine public API directly; the receipt returns up the tree |
| `cmd.stop` | `engine.stop_all_tasks()` | stops all in-flight session tasks of this instance (loop-level interrupt + handle cancellation); **the instance stays RUNNING** |
| `cmd.reload` | re-reads `NORP_CNB_*` + plugin hot reload | hot-updates the hot-swappable runtime knobs (heartbeat / meta description; kind / level / parent / port are fixed after registration — nervous-tree identity protection); with external plugins declared, re-runs `engine.remount(plugins=...)` (module cache invalidated, edited files picked up); otherwise reports honestly |
| `cmd.perm.*` | `perm_changed` callback | the cortex permission command first lands in this node's neural permission table (enforced before every `cmd.exec`), then the callback records the summary and audits it. Syncing cortex permissions into the in-process tool-call chain is left to a future `permission_cascade` integration (see design boundaries in 30.12) |


Every exec / stop / reload / perm event is written to the node-local audit log (`node.get_audit()`); the cortex can query uplink records with the `reports` / `audit` commands.

### 30.9 The Neural Permission Table (NeuralPermissionTable)

Every node holds a local neural permission table: cortex `cmd.perm.*` commands land here as rules, and local actions call `check()` before executing.

```python
from norpagent.cnb import NeuralPermissionTable

tbl = NeuralPermissionTable("norpbot-01", "bot")

# cortex-command landing (normally driven by downlink cmd.perm.*, not called directly)
tbl.apply("node_kind", "bot", "process_shell", allow=False, source="cortex")
tbl.set_all("node_kind", "bot", {"file_delete": False, "network_out": False})

# decision (before a local action)
tbl.check("process_shell")   # False (revoked by the cortex)
tbl.check("file_read")       # True (allowed by default)
```

Decision rules (B4 revision — pure time order):

1. **Pure time order**: among every rule that matches this node and the same permission atom (`node_id` exact / `node_kind` type / `*` full all participate), the **most recently written one wins** (last write wins, **across target granularities too**). The cortex issues commands in time order, and the latest command is the latest management intent: special-case a `node_id` first and then tighten `node_kind` — the tightening applies; tighten first and then special-case — the grant applies. No revoke can be shadowed by an older grant;
2. **Allow by default**: with no rule matched, `check()` returns `True` (the cortex tightens explicitly; `cmd.perm.set` can overwrite a target's whole set for whitelist tightening);
3. **Scope**: a rule may carry `scope={"whitelist": [...], "blacklist": [...]}` matched by path prefix (a whitelist miss or a blacklist hit denies).

### 30.10 Security Model (bus iron rules, enforced in code)

1. **Uplink control-field gate**: `protocol.check_uplink_payload` strips/rejects every control field at the transport layer (prefix blacklist: `cmd.` `perm.` `exec` `config.set` `topology.mutate` `control.`) — even a maliciously crafted lower-level node cannot control upper levels through the uplink.
2. **Downlink ancestor check**: the receiver verifies the sender is in its ancestor chain (told level by level by the parent at registration confirmation + a double check against the local topology parent chain); commands from non-ancestors are rejected and audited.
3. **Topology anti-rewrite**: a registered node's level, kind and parent are immutable (prevents identity forgery, re-parenting and cycles).
4. **Level constraint**: a child level must exceed its parent's; level ceiling 63; registration cycle detection walks the parent chain.
5. **Same level cannot control each other**: ancestor checks exclude self; peer-to-peer commands are rejected.
6. **Loopback by default**: binds `127.0.0.1`; cross-machine deployment needs an explicit host and a trusted network (TLS/signing recommended).
7. **Cortex cannot be controlled from below**: the cortex (level 0) has no parent, so no downlink can pass the ancestor check — lower levels can never rewrite higher levels.

### 30.12 Integration Points with the norpagent Core (actual locations, v1.0.2+)

| File | Change | Description |
|---|---|---|
| `norpagent/cnb/` (kernel-integrated since v1.0.7; the old standalone `nervous_bus` package moved in whole) | `protocol` / `topology` / `permissions` / `bus` / `node` / `cortex` / `cli` / `demo` + a new `engine` binding layer; version merged into norpagent (no separate version) | `import norpagent` makes CNB ready; top-level `norpagent.cnb` exports `NervousNode` / `Cortex` / `CnbAdapter` / `setup_cnb` / `KERNEL_ACTIONS` |
| `nervous_bus/` (compatibility shim) | re-export + sys.modules submodule injection + physical thin `cli.py`/`demo.py` files | `from nervous_bus import ...` / `python -m nervous_bus.cli ...` from 1.0.6 and earlier keep working unchanged |
| `norpagent/cli.py` | CNB subcommand forwarding branch (`_CNB_SUBCOMMANDS`: cortex/node/topo/ping/exec/stop/reload/perm/reports/audit/sync) to **`norpagent.cnb.cli`**; legacy `--norp-cortex` / `--norp-node` forwarded; `--help` shows the branch | PyPI: `norpagent cortex ...` / `python -m norpagent --norp-cortex ...` both work |
| `main.py` (repository-source entry) | src-path bootstrap at the top + CNB branch (same forwarding path as cli.py, to `norpagent.cnb.cli`) | repository source: `python main.py --norp-cortex/--norp-node ...` |
| `norpagent/runtime/engine.py` | `NorpEngine.start()` mounts the auto-mount hook (`_setup_cnb()`); `request_stop()` unmounts (`_teardown_cnb()`); task-level cancellation API (`submit_async` / `cancel_task` / `stop_all_tasks` / `active_tasks` / `forget_task`, see 30.13) | GUI / embedded / np() instances; since v1.0.7 engine.py is untouched (the hook points at the `runtime/cnb.py` forwarding layer) |
| `norpagent/runtime/cnb.py` (forwarding layer) | re-exports `norpagent.cnb.engine` (`CnbAdapter` / `setup_cnb` / `KERNEL_ACTIONS` / legacy `EXEC_ACTIONS`) | `NorpEngine._setup_cnb()` keeps importing `setup_cnb` from this path (zero engine changes) |
| `norpagent/cnb/engine.py` (new since v1.0.7) | `CnbAdapter`: env reading → NervousNode assembly → **14 kernel actions registered** (KERNEL_ACTIONS) → background mount (retries / degrade / unmount); heartbeat provider (engine_state / active_tasks / version / actions) | full implementation of 30.8 / 30.16; includes the `NORP_CNB_MANAGED` skip switch |
| `norpagent/loops/nasyncio.py` | optional extension `submit_async` (`NasyncTaskHandle`, per-task cancellable handle) | the loop-layer foundation for task cancellation (the engine probes it with hasattr; degrades when missing) |

Design boundaries (recorded honestly): this release is designed for **same-machine multi-instance** (loopback transport, no encryption); cross-machine deployment needs TLS and node signing. ① The auto-mount contract reads the `NORP_CNB_*` env vars only (config.json is not consulted); ② the `cmd.exec` action surface is a whitelist (`run_task` / `status` / `stop_task`) — unknown actions and missing prompts are rejected and audited; ③ cortex permission commands take effect immediately on the **CNB command surface** (the node permission table is checked before every `cmd.exec`); pushing cortex permissions into the **in-process tool-call chain** is a future `permission_cascade.PermissionCascade` integration (the `perm_changed` callback is already reserved); ④ kind / level / parent / port are immutable after registration (identity anti-forgery); `reload` only hot-updates runtime knobs and external plugins.

### 30.13 Task-Level Cancellation (EngineTaskHandle, v1.0.2+)

`NorpEngine` provides non-blocking, cancellable task APIs (the CNB `exec run_task` / `stop_task` actions are built on them):

```python
import norpagent as np
from norpagent.loops.cancel import cancel_requested

engine = np(mode="minimal", ui="headless")          # engine reaches RUNNING
handle = engine.submit_async("write a short note", session_id="s1")  # returns immediately
print(handle.task_id)                                # task id (32 hex chars)

# inside the task body you can poll the cancel signal at any time:
#   if cancel_requested(): return  # exit ASAP (sandbox force-kills children / streams interrupt)

engine.cancel_task(handle.task_id)   # cancel exactly this task (deep: the body sees the cancel event)
engine.stop_all_tasks()              # cancel every in-flight task (the instance stays RUNNING; cmd.stop landing point)
engine.active_tasks()                # in-flight snapshot [task_id / text / session_id / degraded / cancelled]
result = handle.result()             # wait for completion and fetch the result (timeout/exception semantics match submit())
engine.forget_task(handle.task_id)   # drop a finished task from the registry (bookkeeping)
```

Handle surface (`EngineTaskHandle`): `cancel()` / `cancelled()` / `done()` / `wait(timeout)` / `result(timeout)`; `handle.degraded=True` means the current loop runtime does not implement the `submit_async` extension (or this task carries a task-level `async_loop` override), so cancellation degrades to a request flag (engine-level `stop()` / `stop_all_tasks()` still cancel everything through loop.interrupt).

**Deep semantics**: the default nasyncio loop's `submit_async` gives every task its own cancel event (injected into the task body via contextvars, readable with `cancel_requested()`); cancelling one task does not affect other in-flight tasks; these tasks remain members of the loop's in-flight set, so Ctrl+C / engine-stop `interrupt()` cancels them too. The engine `request_stop()` shutdown path first unmounts the CNB node and cancels the remaining task handles.

### 30.14 Deep-Tree Fix: Shallow-Self-Consistent, Deep-Broken Remediation (2026-09-05)

**Background**: an audit of a cortex → tech → rnd → dev four-level chain found 9 defects on the registration / uplink / link-loss paths, 3 of them high severity. This section records the fixes one by one.

#### B1 (high) deep-registration collapse — `via` overwritten at every hop

- Symptom: the cortex view showed `dev.parent = tech` (it should be `rnd`) — while forwarding registrations, each hop ran `fwd["via"] = self.node_id`, replacing the "original direct parent" with the last forwarder, so every deep node was re-parented wrongly.
- Fix (`node.py _forward_uplink`): `fwd.setdefault("via", self.node_id)` — `via` records the forwarder closest to the sender and is then kept untouched; the loop guard (`via == self` means already forwarded) is unaffected.

#### B2 (high) middle layers swallowed uplinks — the cortex went blind to deep nodes

- Symptom: after three heartbeat periods the cortex only saw tech's direct heartbeats; dev's events/heartbeats/requests never reached it (middle layers only called `_record_report`, never forwarded).
- Fix (`node.py _handle_uplink`): the heartbeat / event / audit / request branch now **forwards upward after recording locally** (`_forward_uplink`), so the cortex's reports converge from every depth. Addition: when an upper layer rejects a forwarded uplink (typical: this node was removed from the cortex topology), **the verdict is echoed back to the sender** — the child's heartbeat loop detects `not my descendant` and re-registers automatically (heartbeat self-healing, below).

#### B3 (high) a middle layer exiting cascade-killed a live subtree (rescue)

- Symptom: `tech.stop()` made the cortex cascade-deregister the whole live subtree (rnd/dev became orphans); a restart on the same port never re-attached.
- Fix (`node.py _rescue_children` + `cortex.py` sweep thread):
  1. **Clean-exit path**: on `report.deregister(X)`, rescue first — promote each direct child of X **under this node** (`topology.set_parent`, maintaining children lists on both sides) and send **`cmd.reroot`** (new downlink: carries the new parent id / bus URL / grandparent chain) telling the child to re-parent; the child updates `parent_url` / `parent_node_id` / `_ancestors` and **re-registers immediately** (heartbeats and reports then go straight to the new parent). Only then is X deregistered (its children already moved; only X itself is removed). Every level of the chain runs the same logic, so the cortex converges to the authoritative view.
  2. **Crash path** (no deregister): the cortex gained a **lost-node sweep thread** (`Cortex(sweep_interval / dead_timeout / drop_grace)`, `_sweep_loop` finally calls the previously dead `sweep_dead`): no heartbeat beyond `dead_timeout` → marked dead; dead with children → rescue-promote; an entire branch past `drop_grace` → cascade-deregister; a dead leaf past `drop_grace` → deregister (the grace window protects live leaves whose report path broke because their parent died — once the parent is rescued and forwarding resumes, their heartbeats continue).
  3. **Heartbeat self-healing**: any node whose heartbeat is rejected by its parent (parent restarted / cortex view rebuilt / misjudged by the sweep) re-registers automatically: a crashed middle layer's live subtree is rescued and keeps reporting, a forgotten node re-attaches, and truly dead nodes are swept away.
- Attached fixes: `topology.set_parent` used to append to the new parent's children **without removing the node from the old parent's children** (the old parent's cascade DFS then wrongly deleted already re-parented children) — it now maintains both sides; `Topology.register` raises an explicit `ValueError` when the parent is missing (previously a KeyError while maintaining children).

#### B4 type-level revoke shadowed — permission decisions now pure time order

- Symptom: after `grant node_id` then `revoke node_kind`, `check()` still returned True — the old "exact-match priority" layering let an old node_id grant shadow a type-level tightening.
- Fix (`permissions.py check`): **pure time order** — among the rules matching this node for the same permission atom, the most recently written one wins (last write wins across node_id / node_kind / * granularities). The cortex's latest command is the latest management intent: special-case first, tighten after → tightened; tighten first, special-case after → granted. Every existing shallow-tree test stays compatible (same-target time-order semantics unchanged).

#### B5 lost-node detection was unwired

- `sweep_dead` / `mark_dead` had no call sites (dead code). They are now wired into the cortex sweep thread (see the B3 crash path); the REPL `sweep` command and the cortex control endpoint `op=sweep` trigger a manual pass.

#### B6 hello ancestor chains duplicated

- Symptom: `dev._ancestors = ['rnd','rnd','tech','tech','cortex','cortex']` — hello carried a chain that already contained the parent itself (`_ancestor_chain()`), and the child prepended its direct parent again.
- Fix (`node.py _accept_register`): hello's `ancestors` now carries only the **grandparent side** (`self._ancestors`, parent excluded); the child prepends its direct parent and gets a single clean chain `[parent, grandparent, ...]`.

#### B7 heartbeat payload was fixed

- Fix (`node.py report_heartbeat`): new `status` parameter (running / busy / idle / degraded ...) and `**extra` custom fields (control-key prefixes are filtered out); the cortex REPL reports show the status. Busy/idle reporting serves the P1D scheduling surface.

#### B8 topology broadcasts were manual only

- Symptom: middle-layer subtree caches could only be refreshed by a manual `sync` after register/deregister.
- Fix (`cortex.py _maybe_auto_sync`): after register / deregister / rescue the cortex **auto-broadcasts debounced** (0.5 s Timer merges bursts), pushing the full topology via `sync_topology()`; on plain nodes the hook is a no-op.

#### B9 duplicate implementation cleanup

- Redundant lines in `NervousNode.__init__` (duplicate `base_url` assignment etc.) removed; `Cortex` reuses the node implementation through inheritance (registration / uplink / rescue / permissions live in the node layer; the cortex adds root semantics only: the control API, the sweep thread, auto-broadcast, REPL).

**New downlink `cmd.reroot`** (registered in protocol.DOWNLINK_TYPES): reserved for parent-chain rescue — sent by an ancestor (typically the cortex) with payload `{parent_id, parent_url, ancestors}`; the receiving node updates its local parent pointer and ancestor chain, then re-registers immediately. It is still subject to the downlink ancestor check (non-ancestors are rejected).


### 30.15 Convergence Closure and Permission-Plane Audit (v1.0.6, 2026-09-05)

**Background**: after the B1–B9 remediation, a live multi-level demo tree exposed two closing gaps — receivers did not converge even though the sweep path broadcast (Gap A), and permission-plane audit stayed on the node locally instead of reaching the cortex (Gap B).

#### Gap A: middle-layer cache does not converge after sweep removal — `cmd.topology.sync` becomes an authoritative snapshot mirror

- Evidence (running tree: cortex → tech → rnd → dev + atoms): after probe-x was force-killed, the cortex's `_sweep_once` deregistered it and fired the debounced broadcast (cortex audit: `lost leaf past grace, deregister: probe-x` → `topology broadcast: 11 ok`); still, middle-layer rnd's heartbeat `descendants` kept listing probe-x for 150s+ (observed through tech's report records). The root cause is not the broadcast trigger (the B8 hook already covers the sweep path) but the **receiver semantics**: the `cmd.topology.sync` handler only `register`s snapshot nodes (add-only) — nodes removed from the cortex view never disappear from a middle layer's local topology; parent-pointer mismatches on existing nodes raised `ValueError` and were swallowed, so local views could drift from the cortex for a long time (the same live tree showed rnd listing the four atoms under itself while the cortex view had them under dev).
- Fix (`node.py _exec_downlink`, `cmd.topology.sync` = **authoritative snapshot mirror**):
  1. **Prune**: cascade-deregister every local node absent from the snapshot (self excluded) — the convergence path after cortex sweep / deregistration;
  2. **Parent-pointer convergence**: when a snapshot node exists locally with a different parent, align via `topology.set_parent` to the cortex's authoritative view (level / kind tamper checks are kept as a defensive rejection);
  3. **Self-healing fallback**: transient gaps caused by pruning (in-flight registration uplinks, a slightly stale snapshot) recover through "heartbeat rejected → auto re-register"; live nodes are never lost.

#### Gap B: permission-plane audit uplink (kernel-side, converging on the cortex)

- Evidence: a `cmd.exec` permission denial only wrote a line in the target node's in-memory audit ring; `cmd.perm.grant/revoke/set` effects only fired the local `perm_changed` callback (runtime/cnb.py records it with a local `node.audit`); the cortex kept only its own textual audit of issued permission operations — **there was no permission-plane audit view on the cortex**, so same-permission audit reads saw nothing.
- Fix (three places):
  1. **Node uplinks** (`node.py`): a `cmd.exec` rejected by the permission table uplinks `report.audit(event="perm.denied", detail={action, perm, path})`; a `cmd.perm.*` that takes effect uplinks `report.audit(event="perm.changed", detail={op, target_type, target, perm/allows, source})` (`_perm_uplink_audit`) and also records a local effect-audit line. Both climb hop by hop (middle layers record and forward, per the B2 semantics) and land in the cortex's reports ring.
  2. **Cortex records** (`cortex.py`): `_note_perm_op` writes the cortex's own grant/revoke/set into a structured permission-operation ring (500); `perm_audit(n)` merges cortex operations (`perm.op.*`) with uplinked node events (`perm.denied` / `perm.changed`) in reverse time order.
  3. **Read surface**: cortex REPL gains the `perm_audit [n]` command; the control endpoint gains `op=perm_audit` (`/cnb/ctrl`) — consumed directly by same-permission audit readers.

**Version**: norpagent **1.0.6**; the CNB protocol stays CNB/1.0 (semantic additions only: `cmd.topology.sync` snapshot-mirror convergence, and the `report.audit` permission-plane event convention).

### 30.16 CNB Kernel Integration (v1.0.7): Internalized as a Kernel Submodule

**Positioning**: v1.0.7 turns CNB from a standalone package beside norpagent into
a **kernel submodule plus a native engine capability surface** — the cortex can
drive **kernel-level actions** (snapshot / rollback / remount / ops) on any atom
at any level, atom heartbeats carry **deep kernel state**, and every neural atom
started by `norpagent cortex/node` is by default a **full kernel instance**.

#### 30.16.1 Package Layout: `nervous_bus` → `norpagent.cnb`

| Item | 1.0.6 and earlier | v1.0.7 |
|---|---|---|
| Neural implementation | `src/nervous_bus/` (standalone top-level package, own version 1.0.0) | `src/norpagent/cnb/` (kernel submodule; version merged into norpagent) |
| Engine binding | `norpagent/runtime/cnb.py` (external adapter) | `norpagent/cnb/engine.py` (binding layer owned by the CNB module) |
| Import | `from nervous_bus import NervousNode` | `import norpagent` includes CNB; `from norpagent.cnb import NervousNode, Cortex, CnbAdapter, setup_cnb, KERNEL_ACTIONS` |
| CLI | `python -m nervous_bus.cli ...` | `python -m norpagent.cnb.cli ...` (equivalent); `nervous_bus` stays as a shim |

The `nervous_bus/` shim: `__init__.py` re-exports every symbol (version follows
norpagent) + injects submodules into `sys.modules` (`protocol` / `topology` /
`permissions` / `bus` / `node` / `cortex` / `engine`) + physical thin
`cli.py`/`demo.py` files (so `python -m nervous_bus.cli` / `.demo` run through
the file path). **Scripts, commands and tests from 1.0.6 and earlier keep
working unchanged.**

#### 30.16.2 exec Routing Upgrade (Action Registry First)

`NervousNode._exec_downlink` routes cortex `cmd.exec` in three tiers:

1. **kernel action registry** (handlers registered with `register_action`;
   the v1.0.7 main path) → receipt `source="kernel"`;
2. **legacy callback hook** (`on("exec")`; fallback for unregistered actions) → `source="callback"`;
3. neither → the node rejects directly: `ok=False` + top-level
   `error="unknown action: ... (registered: [...])"`.

> **Contract upgrade**: 1.0.6 and earlier returned unknown actions through the
> callback as `ok=True` + `detail.error`; v1.0.7 rejects them node-side with
> `ok=False` (explicit, programmable). Callers relying on the old shape must
> adapt (the automount acceptance test follows the new contract).

API: `register_action(action, handler)` / `unregister_action(action)` /
`has_action(action)` / `list_actions()` / `set_heartbeat_provider(provider)`.

#### 30.16.3 The Kernel Action Surface (KERNEL_ACTIONS, 14 actions → 15 since v2.0.0)

The engine binding (`CnbAdapter.bind_actions`) registers the **NorpEngine public
API** as node actions; the cortex runs
`exec --node X --action <action> --args '<json>'` straight into the target
atom's kernel:

| Surface | Action | args notes | Direct API |
|---|---|---|---|
| Task | `run_task` | `prompt` required; `session_id` / `task_params` | `submit_async` (uplinks `task_started` on accept, `task_done` on finish) |
| Task | `status` | — | mount / engine state / version / permission summary / active tasks |
| Task | `stop_task` | `task_id` | `cancel_task` |
| State | `engine_state` | — | `state` / `is_running` / `should_stop` / task count / version |
| State | `inspect` | — | node identity + `preset` / `preset_model` / slot table / `last_result` / action face |
| Snapshot | `snapshot` | `description` / `tag` (default `cnb`) | `engine.snapshot` (work-rollback / crash-rescue system) |
| Snapshot | `rollback` | `snap_id` (empty = default) | `engine.rollback` |
| Snapshot | `undo` / `redo` | — | `engine.undo` / `engine.redo` |
| Snapshot | `list_snapshots` | — | `engine.list_snapshots` (summarized, first 20) |
| Snapshot | `mark_good` | `snap_id` (empty = default) | `engine.mark_good` |
| Ops | `remount` | args passed as slot values: `{"model": "openai_compat", ...}` | `engine.remount(**slots)` (hot-swap model / tools / plugins) |
| Ops | `reload_plugins` | — | remount the current plugins slot value (module cache invalidated, edits picked up) |
| Ops | `stop_engine` | — | **replies first**, then `engine.request_stop()` after 1 s: stop tasks → deregister node → stop engine; CLI processes exit naturally |

Receipts are JSON-serialization protected (long fields truncated); the neural
permission table is still enforced before every exec (a cortex `perm revoke`
strips the atom of exec capability). `cmd.stop` (stops session tasks, instance
stays RUNNING) and `cmd.reload` (env re-read + plugin hot reload) keep their
semantics and stay on the event callbacks.

#### 30.16.4 CLI Runtime: the Atom Is the Real Instance

`norpagent cortex/node` (and `main.py --norp-cortex/--norp-node`) **assemble a
full kernel engine by default** since v1.0.7:

- assembly: `launch(preset=...)` + headless frontend (output discarded); default
  `minimal` / `mock`, zero third-party deps; `--mode <preset>` / `--model <model>`
  selectable;
- double-mount protection: `NORP_CNB_MANAGED=1` is set before assembly (the
  engine's env auto-mount is skipped; the CLI mounts the node explicitly through
  `CnbAdapter`), and `NORP_CNB_CLI=1` marks the process;
- the cortex = the top-level norpagent instance (engine bound to the Cortex, can
  run tasks locally); a node = a real atom (cortex `run_task` drives a full agent
  kernel);
- `--bare`: back to the 1.0.6 plain nervous shell (probe / placeholder echo, no
  engine);
- shutdown chain: cortex `exec stop_engine` → reply first → engine stops after 1 s
  → node deregisters → the CLI main loop sees `should_stop()` → the process exits
  naturally (the cortex topology converges).

#### 30.16.5 Uplink Fusion: Heartbeats and Events Carry Kernel State

- heartbeat provider: `node.set_heartbeat_provider(...)`; the engine binding
  injects `engine_state` / `active_tasks` / `version` / `mount` / `actions` into
  every heartbeat payload — cortex `reports` (CLI included) show each atom's
  kernel busy/idle and task count;
- task events: `run_task` uplinks `task_started` on accept and `task_done` on
  finish (the cortex sees the whole task lifecycle);
- unknown-action rejections and permission denials (`perm.denied`) keep uplinking
  as audits (Gap-B mechanism unchanged).

---

### 30.17 Kernel Feature Extensions: Task-Molecule Channel / Quarantine Freeze / Behavior Baselines / Subpoena Evidence (v2.0.0 · FarStars 远星)

> This section covers the four feature groups added in v2.0.0: the
> task-molecule (mol) structured dispatch channel with acceptance receipts,
> the node quarantine freeze (freeze/unfreeze), behavior-baseline grading,
> and subpoena evidence (level-0-only highest evidence privilege). Brand:
> the official marketing name is **FarStars (远星)** — the `norpagent` call
> convention and kernel name stay unchanged (`__brand_cn__="远星"` /
> `__brand_en__="FarStars"` / `__display_name__="FarStars（远星）· norpagent"`).

#### 30.17.1 Task-Molecule Channel: structured task_params + task_records acceptance receipts

**Background**: the cortex dispatches work to tree atoms through CNB `exec
run_task`, whose `task_params` previously carried only a flat string
(`mock_script`). When the dispatched payload is structured JSON (a mol with
six elements, including acceptance / depends_on / budget / model_tier), the
channel must carry the structured data in full and support acceptance
receipts traveling back up the tree.

**Implementation (structured extension of the CNB exec channel; no new bus)**:

- `args.task_params` of `run_task` is now a **full carrier for arbitrary
  structured JSON**: the mol six elements (`mol_id` / `objective` /
  `acceptance` / `context_capsule` / `depends_on` / `budget` /
  `model_tier`) reach the absorbing atom (the engine task) unchanged — no
  field loss, no summary degradation;
- new kernel action **`task_records`** (surface 14 → 15): the cortex runs
  `exec task_records` on any atom to read the last 100 accepted task-load
  records — the original `task_params` (the full mol) plus the completion
  receipt (`status` / `error` / `content_len` / `acceptance`); supports
  `args.task_id` / `args.mol_id` / `args.n`;
- **mol_id threads end-to-end**: acceptance audits (node audit with mol_id),
  the `task_started` uplink event and the `task_done` uplink event all carry
  `mol_id`; the `acceptance` spec is echoed back to the cortex verbatim with
  `task_done` (pass/fail judgement stays with the cortex/upper policy —
  the kernel does not adjudicate); the cortex reports ring becomes the full
  mol lifecycle view.


#### 30.17.2 Quarantine Freeze (freeze / unfreeze)

**Background**: the disposal matrix "black / suspected malicious" tier
requires quarantine = freeze order intake + preserve evidence + audit — do
not kill, do not let die; the previous per-node commands (launch/stop/
perm.revoke) either revoked intake or stopped the process, both destroying
the forensic scene.

**Implementation (node-level freeze bit + permission-plane integration +
heartbeat marking)**:

- new downlinks **`cmd.freeze`** / **`cmd.unfreeze`** (cortex
  `freeze_node`/`unfreeze_node`; ctrl `op=freeze|unfreeze`; CLI `norpagent
  freeze/unfreeze`; REPL `freeze/unfreeze`):
  - frozen = **new tasks rejected (intake closed)**: exec actions pass only
    the `FROZEN_ALLOWED_ACTIONS` whitelist (read-only evidence face:
    `engine_state` / `status` / `inspect` / `list_snapshots` /
    `task_records`); `run_task` (new orders), `stop_engine` (scene
    preservation), rollback/remount and other mutating actions are rejected
    and audited (`frozen.reject` uplinks to the cortex);
  - **process/heartbeat stay alive (forensics preserved)**: heartbeats keep
    running and carry `status=frozen` + `frozen=true` (the cortex scheduler
    drains the node);
  - **never triggers sweep-dead**: the sweep only judges heartbeat
    freshness; a frozen node's heartbeats keep it alive (verified: still
    alive past `dead_timeout`);
  - **auditable and reversible**: `unfreeze` recovers the node back to the
    tree (intake restored); a review that fails must destroy-and-rebuild
    instead (never reuse a sick node); cortex perm_audit records freeze /
    unfreeze operations;
  - paired with subpoena evidence: freeze first (prevent destruction /
    further contamination), then collect evidence.

#### 30.17.3 Behavior Baselines (kernel-side aggregation, compressed into heartbeats)

**Background**: behavior grading needs mechanical behavior baselines
(heartbeat loss / audit anomaly / task failure rates beyond thresholds →
yellow degraded / black suspected malicious); which side aggregates decides
whether the protocol surface grows.

**Implementation (kernel-side aggregation; raw streams are not uplinked)**:

- nodes accumulate behavior counters locally (`_behavior`: hb_sent/hb_ok/
  hb_fail, audit_total/audit_anomaly, task_total/task_ok/task_fail);
  anomaly classification is automatic (error fields or error/denied/reject/
  failure keywords);
- **heartbeats carry the aggregate** (`behavior`: counts + anomaly_rate /
  task_fail_rate / hb_fail_rate) — compressed uplink (no raw audit stream);
  the engine-binding task watcher calls `note_task_result(ok)` on
  completion;
- **cortex grading view**: `behavior_view()` (ctrl `op=behavior`; CLI
  `norpagent behavior`; REPL `behavior`) grades every node
  **yellow (degraded, human review)** / **black (suspected malicious,
  quarantine)** with evidence; thresholds live in
  `cortex.behavior_thresholds` (cortex-side policy, adjustable);
- accounting aligns with the kernel's raw events (same counters; sampling
  checks show no bias), and the two event kinds (uplink audit stream vs
  heartbeat reports) share the same accounting definitions.

Verified (S301~S303): heartbeat reports carry behavior fields; the
yellow→black escalation fires.

#### 30.17.4 Subpoena Evidence (level-0-only highest evidence privilege)

**Background**: the untrusted-fence forced-summary policy (structured
summaries ≤2KB enter the LLM; raw text is read-to-burn) may deprive
adjudicators of the Raw Context they need — summaries are second-hand, and
a compromised middle layer makes summaries unverifiable; uplink audits were
structured summaries only, and no raw-audit uplink existed.
CONFLICT_UNRESOLVED (insufficient evidence for adjudication) needed a raw
evidence channel.

**Implementation (a new downlink fetch command `cmd.subpoena`)**:

- **Issuance**: `Cortex.subpoena(node, basis, scope, tier_kb, ...)` (ctrl
  `op=subpoena`; CLI `norpagent subpoena`; REPL `subpoena`). Issuer-side
  **five gates**:
  ① **basis prerequisite** — one of the four accepted bases
  (`confidence_low` cortex confidence insufficient / `vote_tie` council tie /
  `evidence_conflict` contradictory evidence / `human_named` a human names
  a target), and `summary_exhausted` must be declared (summary
  adjudication exhausted: 2KB → on-demand fragments → still undecidable);
  ② **isolation frame** — the package is marked `RAW/UNTRUSTED`, held in a
  one-shot isolation box (`_subpoena_box`: read-to-burn / 300s TTL auto
  expiry / purge); adjudication context never enters long-term memory
  (records never land in audit/perm_audit bodies — issuance metadata only);
  ③ **fetch channel** — `cmd.subpoena` downlinks straight to the target
  node, which streams its raw local audit/report records verbatim (not the
  2KB summary); scope = audit/reports/both, time window and event-type
  filters;
  ④ **capacity tiers** — 64/128/256/512KB: ≤128KB level-0 (cortex) decides
  alone; >128KB needs `approved_by_human=True`; 512KB is streamed in
  volumes only (auto-pagination, the cortex fetches all volumes into the
  box); **above 512KB is forced to human adjudication** (the subpoena ends
  at a human);
  ⑤ **issuance leaves a trail** — `subpoena_audit()` (who/when/basis/scope/
  actual bytes), recorded as a **black**-level event;
- **non-delegable**: the node validates the issuer level == 0 (the true
  envelope sender is injected as `_sender_level`, immune to payload
  forgery); lower-level impersonation is rejected and uplink-audited
  (`subpoena.forged`, visible in cortex reports);
- **typical flow**: black node → freeze → subpoena → review →
  recover/rebuild.

Verified (S401~S419): basis/approval/over-limit rejections, isolation-frame
marking, volume pagination, read-to-burn, impersonation rejection and
issuance records all pass.

### 30.18 Universal Slots and the Complete-Instance Module (R-024 / R-025, 2026-09-11)

> 2026-09-11 decree revision: a neural-bus node no longer hard-wires a fixed agent-instance shape; it offers **up to 64 universal slots**. The norpagent complete instance is **not abandoned** — it is wrapped as the standard module `NorpAgentModule`, insertable into any free slot of any node.

#### 30.18.1 Design points and compatibility

| Item | Description |
|---|---|
| Slot surface | Up to **64 universal slots per node** (`MAX_SLOTS=64`); slots run over the nervous bus — models / tools / plugins / custom modules can all be mounted |
| Connector extension | CNB is the multi-instance extension of the "slot connector": one instance connects local parts locally, many instances connect across processes over the neural tree under one slot protocol |
| Complete-instance module | `NorpAgentModule` (kind=`norpagent-instance`): a standard wrapper for a live NorpEngine — pluggable, removable, describable, replaceable; the instance action surface (`KERNEL_ACTIONS`, 15 actions) is reachable through second-level slot routing |
| Auto-mount | `CnbAdapter.bind_actions()` auto-mounts the engine instance into the default slot `norpagent` (shared by CLI neural processes / env auto-mount / `unbox --cnb`) |
| Limit | The 65th slot is rejected (`SlotError`) |

**Compatibility note**: this is a breaking change to the node's internal shape (no more hard-wired instance), but the instance itself is kept — CLI neural processes, env auto-mount and `unbox --cnb` all perform the "instance to standard module" assembly automatically; existing commands and protocol are unchanged.

#### 30.18.2 Module protocol (MountableModule)

| Method | Purpose |
|---|---|
| `describe()` | White-box description (uplinked with slot snapshots) |
| `ok()` | Module health self-report |
| `on_mount(node)` | Mount callback; a raise = mount failure, no commit (transactional, zero state change) |
| `on_unmount(node)` | Unmount callback (best-effort; errors are audited, never block unmount) |
| `actions()` | Exec action table (name -> handler) the module provides |
| `heartbeat()` | Heartbeat contribution (compressed uplink with the node heartbeat) |

Two built-ins:

- `GenericModule(kind, label, payload)` — anything mountable; the payload is self-describing JSON (no preset fields, no semantic trimming; reports what is mounted);
- `NorpAgentModule(engine, adapter=None)` — the complete instance:
  - `actions()`: exports all of `KERNEL_ACTIONS` (task / molecule / state / snapshot / ops — 15 actions);
  - `describe()`: engine_state / active_tasks / preset / version / actions white-box snapshot;
  - `heartbeat()`: instance busy state (engine_state / active_tasks) uplinked.

```python
from norpagent.cnb.slots import NorpAgentModule, GenericModule

node.mount_module("norpagent", NorpAgentModule(engine))     # complete instance
node.mount_module("tools-1", GenericModule(                 # arbitrary payload
    kind="tools", label="custom toolset",
    payload={"entry": "my_tools.py", "count": 3}))
print(node.describe_slots())                                # white-box slot view
```

#### 30.18.3 SlotBay and bus actions

`SlotBay` manages mounts: capacity ≤64, unique `slot_id`, no action-name conflicts with existing slots, transactional (a failed `on_mount` does not commit); every mount / unmount enters the node audit ring. Four node slot actions are reachable over the bus:

| Action | Type | Description |
|---|---|---|
| `slot_list` | read-only | slot count / free / summaries (count / free / max_slots / slots) |
| `slot_describe` | read-only | one slot (`args.slot_id`) or all slots in full |
| `slot_mount` | mutating | mount a self-describing JSON-spec module (model / tools / plugins / custom) |
| `slot_unmount` | mutating | unmount (callback + action-surface withdrawal + audit) |

Two notes:

1. **Frozen whitelist**: a quarantine-frozen node (§30.17.2) allows the read-only evidence surface (`slot_list` / `slot_describe`) and rejects the mutating surface (`slot_mount` / `slot_unmount`);
2. **Complete-instance modules cannot be built from JSON specs**: `slot_mount` needs a live engine object, so `norpagent-instance` modules are refused there — mount `NorpAgentModule` from code instead.

```bash
# Cortex-side bus view of an atom's slots (examples)
norpagent exec --node norpbot-01 --action slot_list --args '{}'
norpagent exec --node norpbot-01 --action slot_describe \
    --args '{"args": {"slot_id": "norpagent"}}'
```

#### 30.18.4 Auto-mount and heartbeat fusion

`CnbAdapter.bind_actions()` does both: direct kernel-action registration (source=kernel) + the complete-instance module mounted into the default slot `norpagent` (source=slot, fallback action surface — even a manual assembly without direct registration keeps the full instance operation surface); the heartbeat carries slot usage (`slots.count` / `slots.free`), so the cortex `reports` view shows each atom's slot usage and free capacity.

---

### 30.19 Explicit Neural-Tree Definitions: No Preset Shape (2026-09-12 feedback round)

> Core rule: **CNB ships no preset neural-tree shape** — the whole-tree definition must be passed explicitly at startup; per-level `LEVEL`, counts, lower-level parent, ports and other required parameters are validated **one by one, and every missing one is reported explicitly**; on the npa startup path a config error **never blocks the main thread** (explicit error, tree not loaded).

#### 30.19.1 Definition shape (format `farstars-cnb-tree/1`)

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

Required parameters and semantics (validated item by item; any missing one is an explicit error):

| Field | Required | Meaning |
|---|---|---|
| `levels[].level` | yes | level 0–63; level 0 is the cortex (tree root, `count` must be 1) |
| `levels[].count` | yes | number of nodes on this level (>= 1) |
| `levels[].port` / `ports` / `base_port` | yes (one of three) | ports are explicit, never hard-wired (R-025); `port` requires `count=1`, `ports` has length `count`, `base_port` allocates consecutively |
| `levels[].parent` | required for lower levels | parent in three forms: **parent port number** (int or digit string) / parent node id / `"level:N"` (attach to level N, rotating in definition order) |
| `levels[].kind` | no | atom type; level 0 must be `cortex` |
| `levels[].node_id` | no | node id or template (may contain `{i}`); defaults to `cortex` / `<kind>-<index>` |
| `levels[].engine` | no | `true` = this node carries a full kernel engine (spawn mode only; explicitly rejected in-process) |
| `levels[].heartbeat` / `desc` / `args` | no | heartbeat interval / description / extra spawn-mode args (string list) |
| `auto.watch` / `auto.reconcile` | no | file-watch auto-reshape / auto-reconcile switches and intervals (seconds) |

Unknown fields, duplicate ports, duplicate node ids, unresolvable parent references, a parent level not lower than the child's, or a bad format — all are listed item by item (no silence, no guessing, no default topology).

#### 30.19.2 Three definition sources

| Source | Usage |
|---|---|
| direct parameters (dict) | `np(cnb={"tree": {...}})` / `norpagent tree up --def '{"levels": [...]}'` |
| JSON file | `--def tree.json`, `NORP_CNB_TREE=tree.json`, `np.remount(cnb={"tree": "tree.json"})` |
| PY file | module-level `TREE` / `SPEC` / `tree` / `spec` (possibly callables returning a dict), or `build()` / `build_tree()` — the shape may be generated programmatically |

#### 30.19.3 Two assembly shapes

| Shape | Meaning |
|---|---|
| in-process (inproc, default) | the cortex plus every bare neural node is assembled in one process (each with its own bus port); `np(cnb={"tree": ...})` binds the host engine onto the root node as a module |
| multi-process (spawn) | every node starts via a `norpagent cortex/node` child process; `engine=true` nodes carry a full kernel engine, others run `--bare` |

#### 30.19.4 Runtime reshaping (manual / automatic)

- **manual**: `np.remount(cnb={"tree": <new definition>})` diff-reshapes (unchanged nodes are kept, added/removed/changed nodes are applied; a root change rebuilds the whole tree);
- **file watch (automatic)**: `norpagent tree up --def tree.json --watch` or `auto.watch=true` — a definition-file change triggers an automatic reshape; on error the current shape is kept and the error is explicit;
- **auto-reconcile**: `--reconcile SECONDS` or `auto.reconcile=true` — lost/stopped nodes are restored per the definition automatically.

#### 30.19.5 Entries and commands

```bash
norpagent tree validate --def tree.json      # validate (item-by-item errors; exit 0/2)
norpagent tree show --def tree.json [--json] # show the resolved node table
norpagent tree up --def tree.json --mode inproc|spawn [--watch] [--reconcile 5]
```

```python
import norpagent as np

engine = np(cnb={"tree": "tree.json"})          # explicit definition at startup (in-process tree)
np.remount(cnb={"tree": {"levels": [...]}})     # runtime reshape
np.remount(cnb=False)                           # detach the whole tree
```

The `unbox` product entry supports it too: `norpagent unbox --cnb-tree tree.json` (or the profile key `cnb.tree`); the same source as the `NORP_CNB_TREE` env var.

#### 30.19.6 Error semantics (startup is never blocked)

- `np()` startup path: config errors (missing port / missing node id / a tree definition missing required parameters) **never block the main thread** — the host starts normally, the error is printed explicitly and the tree is not loaded; status `engine.cnb_status == "config-error"`, details in `engine.cnb_error`;
- direct validation surfaces (`validate_cnb_config` / `np.remount`) keep their strict "explicit error" semantics for immediate handling;
- the port rule is unchanged: no hard-wired default port (R-025); silent degradation is forbidden.

