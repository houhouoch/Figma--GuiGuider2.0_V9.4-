# Figma → GUI Guider 2.0 全流程工程复盘

日期：2026-07-30
工程：`D:\figma\V2.0\guiguider_2.0\guiguider_2.0`
Figma 文件：`UDP3900 design`
GUI Guider：2.0
目标 LVGL：9.4

## 1. 复盘范围

本文覆盖本次 Figma → GUI Guider 任务从最初基线建立到当前现场的完整过程：

1. 建立可回退的 GUI Guider 基线；
2. 修复初次转换中的资源、图层、坐标和文本问题；
3. 建立完整 Manifest、语义差异和字段所有权；
4. 生成独立候选工程，而不是直接覆盖正式工程；
5. 处理本地 Figma MCP 限流并完成远程分块抓取；
6. 完成结构、资源、字体、视觉、幂等和 V8 回归验证；
7. 修复独立审核工程的项目身份和字体资源问题；
8. 经用户授权后晋升正式 GUI Guider 工程；
9. 验证 GUI Guider 打开、保存、关闭往返；
10. 处理后续 `screen_file`、自定义字体代码生成和 Label 高度问题；
11. 判断哪些经验进入项目文档、`AGENTS.md`、通用 Skill、Obsidian 或待验证假设。

本文不包含 MDK 业务接入。该任务边界已经由用户明确确认：Figma 转 GUI Guider 阶段不应修改 MDK。

## 2. 检查过的证据

### 2.1 Git 历史

| 提交 | 作用 |
|---|---|
| `677615a` | Figma 导入前 GUI Guider 2.0 基线 |
| `63359f5` | 恢复可打开的 GUI Guider 工程及初始资源 |
| `d05dcc5` | 恢复字体资源加载 |
| `7873804` | 修复转换页面层级 |
| `4a248a9` | 调整目标页面，使视觉更接近 Figma |
| `b110974` | 固化用户手工调整后的 GUI Guider 基线 |
| `8de6915` | 修复 Home 列表状态并建立完整转换器 |
| `0bcf5a0` | 对 Figma 图片资源做 SHA-256 去重 |
| `1e80a23` | 优先使用已审核的本地透明图片资源 |
| `e19715e` | 生成 V9 受控候选、Manifest、差异与验证报告 |
| `1057cee` | 创建独立 GUI Guider 审核工作区 |
| `cb67784` | 经用户授权后晋升正式 UI |
| `e3db457` | 记录字体符号和 Label 高度经验 |

### 2.2 转换、校验和晋升工具

- `tools/refresh_figma_local_snapshot.py`
- `tools/compare_figma_manifests.py`
- `tools/sync_completed_figma_to_guiguider.py`
- `tools/validate_figma_guider_sync.py`
- `tools/check_v8_regression.py`
- `tools/finalize_controlled_sync.py`
- `tools/prepare_guiguider_review_workspace.py`
- `tools/audit_guiguider_typography.py`
- `tools/promote_guiguider_candidate.py`
- `tools/verify_guiguider_roundtrip.py`
- `tools/test_controlled_sync.py`

### 2.3 结构化报告

- `tools/sync_reports/v9_all_20260729_context/controlled_sync_summary.*`
- `manifest_diff.*`
- `field_ownership.md`
- `warnings.json`
- `typography_audit.*`
- `visual_comparison_report.*`
- `v8_regression_report.*`
- `promotion_gate.*`
- `formal_promotion_report.*`
- `formal_validation_report.*`

### 2.4 当前现场

- 当前正式 `guiguider_2.0.guiguider`；
- 当前 `generated/screens/*.c`；
- `generated/assets/fonts/gg_font.h`；
- `generated/assets/fonts/lv_font_AlibabaPuHuiTi2_*.c`；
- 当前 Git diff 和未提交清理状态；
- 用户提供的 GUI Guider 编译错误和实际修复确认；
- 用户确认正式候选能够在 GUI Guider 中保存；
- 用户确认字体资源导入后显示恢复正常。

## 3. 最终采用的受控同步模型

```text
Figma
  ↓ 只读抓取
版本化 Manifest + 页面截图 + SHA-256
  ↓
V8 → V9 语义差异 + 字段所有权
  ↓
独立候选 .guiguider
  ↓
结构 / 资源 / 字体 / 视觉 / 幂等 / 回归验证
  ↓
独立 GUI Guider 审核工程
  ↓ 用户人工审核
正式工程备份
  ↓ 显式授权
只晋升 UI 树，保留正式工程配置
  ↓
GUI Guider 打开 / 保存 / 关闭往返
  ↓
重新生成 C + 模拟器构建
```

核心原则：

- Figma 是视觉来源，不是 GUI Guider 项目配置和业务字段的所有者；
- 候选工程通过验证前不得写入正式工程；
- 自动视觉相似度不能替代 GUI Guider 实际打开和人工检查；
- GUI Guider 打开正常不能替代生成 C 和完整模拟器构建；
- 单页面手工修复不应触发全量 Figma 重转换。

## 4. 阶段复盘

## 4.1 阶段 A：建立基线并修复首次转换

### 问题现象

初始 Figma 转换结果存在：

- GUI Guider 工程无法可靠打开；
- 字体和图片资源加载不完整；
- 页面层级与 Figma 不一致；
- 坐标、文本框和图标出现明显视觉偏差；
- 静态文本、动态文本和业务对象没有清晰边界。

### 直接原因

- 转换结果没有完整满足 GUI Guider JSON Schema；
- 资源路径和工程资源目录没有形成完整闭包；
- Figma 绝对坐标没有正确转换为 GUI Guider 父子相对坐标；
- Figma 图层语义与 GUI Guider 控件类型不是一一对应。

### 根本原因

当时缺少四个正式契约：

1. 可回退的正式工程基线；
2. Figma 节点到 GUI Guider 对象的稳定身份映射；
3. Figma、GUI Guider、业务字段之间的字段所有权；
4. 结构、资源、视觉和生成代码的分层验收门槛。

### 最终处理

- 先建立 Git 基线；
- 分阶段修复资源、层级和坐标；
- 将用户在 GUI Guider 中完成的手工视觉调整固化为新基线；
- 后续同步优先保留已有对象 ID、名称和业务字段。

### 验证

对应 Git 提交按顺序建立了可回退检查点，避免继续在单一未提交工程上反复覆盖。

## 4.2 阶段 B：资源去重和透明图片选择

### 问题现象

- Figma 同一图片被重复导出为多个文件；
- 图标可能带不需要的黑色或深色矩形背景；
- GUI Guider 中图标资源数量膨胀，难以审核。

### 直接原因

- 转换器按节点输出图片，没有按内容去重；
- 将带 image fill 的矩形或 Frame 整体渲染为图标，会把节点背景一起烘焙进 PNG。

### 根本原因

图标、控件背景和控件状态没有分离：

- 图标应是透明图片资源；
- 背景、边框、聚焦和按下状态应由 GUI Guider/LVGL 样式负责。

### 最终处理

- 图片按 SHA-256 去重；
- 有经过人工审核的本地透明原件时，优先使用本地原件；
- GUI 状态继续由对象样式实现。

### 验证

- `0bcf5a0` 固化图片去重；
- `1e80a23` 固化本地透明资源优先级；
- 受控同步单测 `test_beep_off_uses_reviewed_transparent_asset` 当前通过。

## 4.3 阶段 C：全量 V9 Manifest 和本地 MCP 限流

### 问题现象

本地 Figma MCP 首轮全量刷新时：

- 18 页成功；
- 4 个大页面超时；
- 其余页面返回当日限流；
- 产生了一个不完整 V9 目录。

### 直接原因

- 单次大页面响应体较大；
- 本地 MCP 有当日调用限制；
- 首版刷新流程没有把“半完成目录”与“有效版本”严格隔离。

### 根本原因

全量抓取流程缺少：

- 可续传分块；
- 节点总数校验；
- 分片连续性校验；
- 节点 ID 唯一性校验；
- 最终原子完成标记。

### 失败方法

#### 继续重试本地 MCP

失败原因：限流是外部状态，继续重试只会浪费调用配额。

#### 接受截断的整页远程响应

失败原因：响应在大约 20 KB 处截断，不能证明节点树完整。

### 最终处理

- 改用远程 Figma MCP 的分块只读采集；
- 每块记录 `rootId/start/total`；
- 本地合并时检查分片连续性、总节点数和 ID 唯一性；
- 31 个页面、1756 个节点全部通过校验后才生成正式 V9 Manifest；
- 不完整的本地目录保留为诊断证据，不作为输入。

### 验证

- 页面数：31；
- SourceNode：1756；
- 自动匹配旧节点：1615；
- 身份不确定节点：0。

## 4.4 阶段 D：Manifest 差异和字段所有权

### 问题现象

V8 → V9 存在大量变化：

- 新增节点 141；
- 改名 25；
- 父节点变化 388；
- 图层顺序变化 381；
- 几何变化 331；
- 样式变化 292；
- 控件语义或类型变化 1；
- 可能影响事件、焦点或业务的变化 414。

仅凭页面截图不能判断哪些字段可以覆盖。

### 直接原因

设计更新同时包含视觉变化、层级变化、对象新增和潜在业务影响。

### 根本原因

Figma 和 GUI Guider 对同一个对象拥有不同字段：

- Figma 拥有视觉层级和几何；
- GUI Guider 拥有项目配置、对象身份和运行时字段；
- 手写业务层拥有事件、焦点、回调和动态状态。

### 最终处理

建立字段所有权：

- `projectId/projectName/projectPath/projectSettings/lvConf`：保留正式 GUI Guider；
- `UI.event_list/UI.variable_setting`：保留业务/GUI Guider；
- `figma_id`：稳定映射主键；
- 已存在的 `id/name`：优先保留；
- `children/x/y/width/height/style`：由 Figma 视觉层更新；
- `type` 变化：必须人工审核；
- 动态文本、事件、焦点和回调：不得由 Figma 示例值覆盖。

### 验证

受控同步单测当前结果：

```text
test_compact_manifest_builds_parent_tree ... ok
test_name_allocator_preserves_existing_owner ... ok
test_object_contract_keeps_identity_and_business_fields ... ok
test_beep_off_uses_reviewed_transparent_asset ... ok
Ran 4 tests ... OK
```

注意：测试必须在 `tools` 目录运行。直接从仓库根运行会因为模块搜索路径错误而失败。

## 4.5 阶段 E：候选工程和晋升门禁

### 问题现象

直接更新正式 `.guiguider` 会带来不可控风险：

- 用户手工调整可能被覆盖；
- GUI Guider 项目配置可能被替换；
- 类型变化可能破坏后续事件或业务引用；
- 部分页面的滚动、弹层和实体键盘语义不能从 Figma 自动判断。

### 最终处理

先生成独立候选，并设置门禁：

- 正式工程哈希守卫；
- 结构校验；
- 资源引用校验；
- 名称、对象 ID、Figma ID 唯一性校验；
- 页面和局部区域视觉对比；
- 两次生成 SHA-256 一致性；
- V8 转换器回归；
- 人工审核清单；
- 明确用户授权；
- GUI Guider 打开保存往返。

### 验证

受控候选结果：

- 候选 SHA-256：`9e297c7cc62d302fbf307471e28826fd5cdc6bf4ba893d20980a149c7816fd51`；
- 幂等二次生成 SHA-256 相同；
- 结构阻断项：0；
- 最低整页相似度：0.944107；
- 既有基线：0.940617；
- 最低局部相似度：0.680751；
- 局部失败：0；
- 图片控件：112；
- 唯一图片资源：49；
- V8 回归：PASS；
- V8 对象契约差异：0。

自动通过不代表允许自动晋升。Home 控件类型变化、滚动页面、弹层和高层级变更页面仍被列入人工审核。

## 4.6 阶段 F：独立审核工程打开了错误项目

### 问题现象

用户打开候选时，GUI Guider 仍显示旧正式工程。

### 直接原因

候选 JSON 仍保留正式工程的：

- `projectId`；
- `projectName`；
- `projectPath`。

GUI Guider 单实例进程根据这些字段恢复了正式项目。

### 根本原因

“候选文件路径不同”不等于“GUI Guider 项目身份已经隔离”。

### 失败方法

仅双击候选文件或从命令行把候选路径传给 GUI Guider。

失败原因：只能证明进程接收了路径，不能证明软件内部加载了候选项目。

### 最终处理

创建独立审核工作区：

- 独立项目 ID；
- 独立项目名；
- 独立项目路径；
- 独立资源目录；
- 仅复制候选实际引用的资源。

### 验证

进程路径和 GUI Guider 工程名均指向独立审核工程，避免与正式工程混淆。

## 4.7 阶段 G：独立审核工程字体缺失

### 问题现象

用户在审核工程中看到：

- 字体缺失；
- 字体错位；
- 字号不正确；
- 基线变化；
- 文本裁剪。

### 直接原因

第一版审核工作区只复制了 JSON 中显式路径引用的图片，没有复制并注册字体资源。

### 根本原因

GUI Guider 的 `text_family` 只保存字体文件名，不一定包含完整资源路径。仅扫描路径字符串无法得到完整资源闭包。

缺失字体后，GUI Guider 使用回退字体；一旦发生回退，字宽、字高、基线和裁剪比较全部失去意义。

### 失败方法

#### 根据截图继续调坐标

失败原因：当底层字体已经回退时，任何位置和尺寸补偿都建立在错误字体度量上。

#### 只验证 `text_family` 值

失败原因：字段正确不等于字体文件存在，也不等于 GUI Guider 已注册该资源。

### 最终处理

- 审核工程加入 `resources/font/AlibabaPuHuiTi2.0.ttf`；
- 审计每个 Figma 文本、旧 GUI Label 和候选 Label；
- 确认字体文件、字号、对齐、尺寸和位置变化。

### 验证

字体审计：

- Figma 文本节点：664；
- 旧 GUI Label：647；
- 候选 Label：664；
- 已匹配旧/新 Label：647；
- 新 Label：17；
- 已匹配字体变化：0；
- 已匹配字号变化：0；
- Figma → GUI 字体映射错误：0；
- Figma → GUI 字号映射错误：0；
- 缺失字体文件：0。

用户补充导入字体后确认显示恢复正常。

## 4.8 阶段 H：正式晋升和 GUI Guider 往返

### 处理过程

经用户显式授权后：

1. 备份正式 `.guiguider`；
2. 验证备份 SHA-256；
3. 保留正式项目 ID、路径、项目配置和非 UI 字段；
4. 只替换已验证候选的 UI 树；
5. 验证全部图片和字体资源存在；
6. 用户在 GUI Guider 中打开、保存并关闭正式工程；
7. 比较保存前后的 JSON。

### 验证

- 非 UI 配置保持不变；
- 正式 UI 与候选一致；
- 资源存在：50/50；
- GUI Guider 打开/保存/关闭：PASS；
- 保存后只有 `lastModified` 改变；
- UI 树和资源引用没有改变；
- MDK 未修改。

## 4.9 阶段 I：`screen_file` 的后续定向修改

### 已验证现场

当前正式工程包含：

- `screen_file`：Figma `366:777`；
- `cont_File_Operation_Page`：Figma `781:40`；
- `cont_File_Operation_Panel`：Figma `781:41`；
- 生成头文件包含 Delete、Save As、Save、New、Open 等操作按钮对象。

这证明文件操作页面已经进入当前 GUI Guider 工程和生成结构。

### 待确认

用户希望把 `cont_file_btnm_1` 从 Button Matrix 改成符合实体键盘的按钮组，但当前正式工程中该对象仍为：

```text
name = cont_file_btnm_1
type = buttonmatrix
```

因此不能把“Button Matrix 已完全替换为按钮组”记录为已完成。需要后续在 GUI Guider 中确认最终控件类型和实体键盘操作语义。

### 可复用结论

只调整单个既有 GUI Guider 页面时，应直接修改正式 `.guiguider` 的目标页面或通过 GUI Guider 编辑器完成，不应重新执行全量 Figma 转换。

如果新增的是 Figma 子树，则只抓取明确的节点 ID，并把改动限制到对应 Screen；完成后比较其他 Screen 的规范化哈希。

## 4.10 阶段 J：自定义字体生成 C 符号不一致

完整专项证据见：

`docs/2026-07-29_GUI_GUIDER_FONT_AND_LABEL_RETROSPECTIVE.md`

### 问题现象

GUI Guider 点击“生成代码”后出现：

```text
lv_font_AlibabaPuHuiTi2_0_20 undeclared
lv_font_AlibabaPuHuiTi2_0_13 undeclared
lv_font_AlibabaPuHuiTi2_0_16 undeclared
lv_font_AlibabaPuHuiTi2_0_23 undeclared
lv_font_AlibabaPuHuiTi2_0_18 undeclared
```

### 直接原因

页面引用符号带 `_2_0_`，而 `gg_font.h` 和字体 C 定义使用 `_2_`。

### 根本原因

- 字体文件基本名包含额外点号 `AlibabaPuHuiTi2.0.ttf`；
- 页面生成器和字体转换器对额外点号使用不同的 C 标识符归一化规则；
- 重命名字体文件后，没有同步所有 `text_family` 字段。

### 失败方法

- 只重命名 TTF；
- 只修一个页面；
- 只补一个字体声明；
- 只修一个字号。

问题覆盖 27 个页面、670 处引用和 17 个字号，必须按全局契约修复。

### 最终处理

- 字体改为 `AlibabaPuHuiTi2.ttf`；
- 正式工程所有 `text_family` 同步更新；
- 生成页面旧 `_2_0_` 引用同步为 `_2_`；
- 比较页面引用、`gg_font.h` 声明和字体 C 定义三个集合。

### 验证

- 引用字号：17；
- 声明字号：17；
- 定义字号：17；
- 旧 `_2_0_` 引用：0；
- 模拟器完成 `[704/704]` 链接；
- 用户重新打开 GUI Guider 后确认成功。

## 4.11 阶段 K：单行 Label 高度不一致

### 问题现象

相同字号 Label 存在多种高度。例如：

```text
23 px -> 28 / 30 / 33 / 34 / 36 / 40 / 42 / 54 / 77 px
26 px -> 30 / 35 / 37 px
```

用户明确指定当前视觉标准：

```text
23 px 字体 -> 28 px Label 高度
26 px 字体 -> 31 px Label 高度
```

### 直接原因

转换器保留了不同来源的 Figma 文本框高度或完整字体行框，没有统一为 GUI Guider 所需的紧凑单行框。

### 根本原因

以下三个量被混为一谈：

- Figma 文本边界；
- TTF ascent/descent；
- GUI Guider/LVGL Label 的可视紧凑高度。

### 失败或未采用方法

#### 再次修改 Figma 转换脚本

未采用原因：用户要求直接修改当前 GUI Guider，不重新覆盖已完成的手工调整。

#### 用父容器高度限制目标高度

失败原因：导致少数 26 px Label 仍只能保持 30 px，不符合用户指定的 31 px。

### 当前项目处理

当前项目对普通单行 Label 采用：

```text
Label 高度 = 字号 + 5 px
```

静态结果：

- 普通单行 Label：666；
- 23 px → 28 px：165；
- 26 px → 31 px：66；
- 违反静态规则：0。

### 待确认

- GUI Guider 全页面视觉检查；
- 重新生成 C 后的全部页面裁剪和基线；
- 该规则能否适用于其他字体和其他 GUI Guider 版本。

因此“字号 + 5 px”只能记录为当前项目规则，不能进入跨项目通用 Skill。

## 4.12 阶段 L：项目目录清理

### 当前现场

当前工作区存在大量未提交变化：

- 模拟器构建缓存删除；
- 旧图片资源删除；
- 正式 `.guiguider` 的后续手工变化；
- 新 `generated/` 目录；
- 新字体和预览资源；
- 若干未提交工具和报告。

### 结论

这些变化可能来自用户后续 GUI Guider 生成和目录清理，但当前没有一个完整提交或清理后的全量构建证据，不能把它们写成“清理已验证完成”。

### 待确认

- 当前被删除资源是否全部不再被正式工程引用；
- `generated/` 是否应纳入版本控制；
- 清理后的模拟器是否能从空构建目录完整重建；
- 哪些 `artifacts/` 应保留为审计证据，哪些应忽略。

本次经验沉淀不会修改、恢复或提交这些现场变化。

## 5. 直接原因与根本原因汇总

| 问题 | 直接原因 | 根本原因 |
|---|---|---|
| 初次工程不稳定 | JSON/资源/层级不完整 | 没有基线、Schema 和分层验收 |
| 图层/坐标错误 | 绝对坐标和父子关系映射错误 | 没有稳定 SourceNode Tree |
| 资源重复 | 按节点生成图片 | 没有内容寻址和资源所有权 |
| 图标带黑底 | 整体渲染 image-fill Frame | 图标资源与控件样式未分离 |
| 本地 MCP 全量失败 | 限流和大页面超时 | 抓取流程不可续传、非原子 |
| 候选打开成旧工程 | 共用项目 ID、名称和路径 | 文件隔离不等于项目身份隔离 |
| 审核字体错乱 | 审核工程漏复制/注册字体 | 资源扫描只覆盖显式路径 |
| 自动同步可能破坏业务 | Figma 变化覆盖稳定对象 | 没有字段所有权和类型门禁 |
| 字体 C 编译失败 | 引用、声明、定义符号不同 | 文件名额外点号被不同生成器不同归一化 |
| Label 高度不统一 | 未统一单行几何 | Figma 边界、TTF 行框和 LVGL Label 高度混淆 |

## 6. 失败方法清单

- 未冻结基线就直接覆盖正式工程；
- 把半完成 Manifest 当作有效版本；
- 限流后持续重试同一个本地 MCP；
- 接受被截断的大响应；
- 只根据候选文件路径判断 GUI Guider 已打开正确项目；
- 审核工程只复制图片，不复制字体；
- 字体回退时继续调坐标；
- 只看 `text_family`，不检查实际字体文件；
- 只重命名 TTF，不同步工程字段和生成符号；
- 只修一个页面或一个字号；
- 把 Figma Frame 整体导出为图标；
- 用自动相似度替代人工高风险页面审核；
- 用 GUI Guider 打开成功替代 C 生成和构建；
- 单页修复时重新执行全量转换；
- 把当前项目的 Label 高度规则直接推广到所有字体和版本。

## 7. 最终验证矩阵

| 验证项 | 结果 | 证据边界 |
|---|---|---|
| V9 页面完整性 | PASS | 31 页、1756 SourceNode |
| 稳定身份匹配 | PASS | 1615/1615，身份不确定 0 |
| 受控同步单测 | PASS | 4/4 |
| 候选幂等 | PASS | 两次 SHA-256 相同 |
| 结构阻断 | PASS | 0 |
| 整页视觉 | PASS | 最低 0.944107，高于既有基线 |
| 局部视觉 | PASS | 失败 0 |
| V8 回归 | PASS | 契约差异 0 |
| 字体审计 | PASS | 664 文本，字体/字号映射错误 0 |
| 审核资源闭包 | PASS | 晋升时 50/50 |
| GUI Guider 往返 | PASS | 只改变 `lastModified` |
| 正式晋升 | PASS | 用户显式授权，备份存在 |
| 字体 C 符号契约 | PASS | 引用/声明/定义 17/17/17 |
| 模拟器字体修复构建 | PASS | `[704/704]` |
| `cont_File_Operation_Page` 存在 | PASS | 正式工程和生成结构均存在 |
| Button Matrix 已替换为按钮组 | 待确认 | 当前对象仍是 `buttonmatrix` |
| Label `字号 + 5` 视觉通用性 | 待确认 | 只有当前项目静态验证 |
| 清理后空目录全量重建 | 待确认 | 当前工作区无最终构建证据 |

## 8. 防回归检查清单

### 8.1 开始同步前

- [ ] 确认任务是全量同步、单页同步还是直接 GUI Guider 修复。
- [ ] 记录正式 `.guiguider` SHA-256。
- [ ] 创建 Git 检查点。
- [ ] 确认 GUI Guider 已关闭。
- [ ] 明确正式工程、候选工程和审核工程路径。

### 8.2 Figma 抓取

- [ ] 使用明确 file key 和 node ID。
- [ ] 大页面使用分块抓取。
- [ ] 校验 `start/total` 连续。
- [ ] 校验根节点数量。
- [ ] 校验节点 ID 唯一。
- [ ] 每页保存截图和 SHA-256。
- [ ] 半完成目录不得命名为有效版本。

### 8.3 转换

- [ ] 比较旧/新 Manifest。
- [ ] Figma ID 优先作为身份映射。
- [ ] 保留稳定 GUI Guider `id/name`。
- [ ] 保留项目配置、事件、变量和业务字段。
- [ ] 类型变化必须阻断并人工审核。
- [ ] 动态文本不得被 Figma 示例值覆盖。
- [ ] 图片按 SHA-256 去重。
- [ ] 优先使用已审核透明原件。

### 8.4 候选工程

- [ ] 不直接写正式工程。
- [ ] 两次生成结果必须幂等。
- [ ] 审核工程使用独立 ID、名称和路径。
- [ ] 复制所有图片和字体资源。
- [ ] 验证字体已注册，不只验证文件存在。
- [ ] 比较 31 页结构和关键局部区域。
- [ ] 高变更页面执行人工检查。

### 8.5 正式晋升

- [ ] 必须有用户显式授权。
- [ ] 先创建并校验备份。
- [ ] 只更新获批 UI 树。
- [ ] 保留全部非 UI 配置。
- [ ] GUI Guider 打开、保存、关闭。
- [ ] 保存后只允许已知易变元数据变化。
- [ ] 比较正式 UI 与候选 UI。

### 8.6 代码生成

- [ ] 自定义字体基本名只含字母、数字和下划线。
- [ ] `text_family` 与实际字体文件名一致。
- [ ] 字体引用、声明和定义集合完全相同。
- [ ] 从干净模拟器构建目录全量构建。
- [ ] 逐页检查字体回退、裁剪、基线和字号。

### 8.7 单页直接修复

- [ ] 不重跑全量转换。
- [ ] 只修改目标 Screen。
- [ ] 比较其他 Screen 规范化哈希。
- [ ] 保留对象 ID、名称和业务字段。
- [ ] 重新生成对应页面并构建。

## 9. 经验归属

| 目的地 | 内容 |
|---|---|
| 项目复盘文档 | 本文完整时间线、项目路径、提交、统计和待确认项 |
| 当前项目 `AGENTS.md` | 候选优先、原子 Manifest、字段所有权、完整资源闭包、晋升往返、字体符号契约 |
| 跨项目 Codex Skill | 受控 Figma → GUI Guider 同步工作流和通用审计脚本 |
| Obsidian | 候选晋升门禁、资源闭包、字段所有权、原子抓取等原子知识 |
| 待验证假设 | Label `字号 + 5 px` 的跨字体/跨版本适用性；Button Matrix 是否已替换；清理后能否全量重建 |

## 10. 本次经验沉淀的边界

- 不修改业务代码；
- 不修改正式 `.guiguider`；
- 不修改 MDK；
- 不修改生产配置；
- 不执行目录清理；
- 不把当前未提交资源删除纳入经验提交；
- 只新增/更新文档、项目规则、通用 Skill 和 Obsidian 原子笔记。
