# GUI Guider 2.0 重复项目身份导致打开旧工程

## 状态

- 缺陷条件：**已验证**
- 本地准备脚本修复：**已验证**
- 新独立工程中的“删除、保存、关闭、重开”人工验证：**待确认**
- 日期：2026-07-30

## 问题现象

复制或发布一个 `.guiguider` 工程后，即使用户尝试打开新文件，GUI
Guider 2.0 仍回到旧工程。用户删除控件后再次打开，控件重新出现，看起来像
工程被锁住或修改不能保存。

这个问题会造成：

- 修改落到错误的工程路径；
- 用户误判为文件只读或 GUI Guider 锁定；
- 新旧工程内容相互混淆；
- 删除、移动和样式修改的验证结果不可信；
- 后续生成代码可能来自错误工程。

## 复现条件

以下条件同时成立时可以复现：

1. 复制一个 GUI Guider 工程到新目录；
2. 新旧工程保留相同的 `projectId`；
3. GUI Guider 的最近工程记录仍关联旧路径；
4. 通过快捷方式、双击副本或已运行的单实例进程尝试打开新工程。

仅修改文件名或 `projectPath` 不能形成独立工程身份。

## 证据

本次检查得到：

- 旧正式工程：
  - `projectId = project-MRWWUBKD5NV0`
  - `projectPath = D:\figma\V2.0\guiguider_2.0\guiguider_2.0`
- 首版公开仓库本地副本：
  - `projectId = project-MRWWUBKD5NV0`
  - `projectPath = D:\figma\Figma--GuiGuider2.0_V9.4-\project`
- GUI Guider 主进程命令行实际指向旧正式工程；
- `%APPDATA%\GUIGuider\2.0.0\project_history.json` 当时只记录旧正式路径；
- 工程文件 `IsReadOnly = False`，Windows ACL 允许修改；
- 以读写模式打开工程文件成功；
- 工程 JSON 中没有项目级 `locked`、`readOnly` 或 `editable=false` 字段；
- GUI Guider 日志没有 `EACCES`、`EPERM` 或写入失败记录。

因此，“文件被锁住”不是直接原因。

## 直接原因与根本原因

### 直接原因

新旧 `.guiguider` 文件使用了相同 `projectId`。GUI Guider 2.0 的最近工程和
单实例打开逻辑把它们当作同一个项目，继续关联或恢复旧路径。

### 根本原因

原 `tools/prepare_local_project.py` 只替换本机 `projectPath`，没有生成独立
`projectId`。脚本还会直接覆盖已有输出，存在误重置本地手工修改的风险。

这属于 GUI Guider 2.0 对重复项目身份处理不透明的产品限制/缺陷，同时也是
本地工程准备流程缺少身份隔离门禁。

## 尝试过但无效的方法

### 只改变文件名或目录

无效。GUI Guider 使用内部项目身份，不只依赖文件名。

### 只改变 `projectPath`

无效。重复 `projectId` 仍可能让最近工程记录关联旧项目。

### 排查或解除 Windows 文件只读

不是本次原因。文件属性、ACL 和读写句柄检查均通过。

### 直接启动 GUI Guider 快捷方式

不能证明打开了目标工程。GUI Guider 会恢复最近工程，窗口出现也不等于目标
`.guiguider` 已加载。

## 最终解决方案

提交 `d78232159ab7c67b1ab95a103bd29787045f63be` 完成：

1. 本机工程根据 `projectName + 绝对输出路径` 生成独立 `projectId`；
2. 默认项目名改为 `Figma_GuiGuider2_V9_4_local`；
3. `projectPath` 指向当前本机输出目录；
4. 已存在输出时默认拒绝覆盖；
5. 只有明确传入 `--force` 才允许从模板重建；
6. 增加跨目录项目 ID 不同的回归测试；
7. 中英文 README 补充独立身份与覆盖保护说明。

当前本机生成结果：

```text
projectId   = project-B397CA321030A415
projectName = Figma_GuiGuider2_V9_4_local
projectPath = D:\figma\Figma--GuiGuider2.0_V9.4-\project
```

## 验证方法与结果

已验证：

- Python 语法检查通过；
- 5 项受控同步测试通过，1 项因外部资产未安装跳过；
- 仓库验证通过；
- GUI Guider 只读审计通过；
- 34 个工程条目；
- 1735 个对象；
- 50 个引用资源，无缺失；
- 新 ID 与旧正式工程 ID 不同；
- 两个不同本地目录生成不同 ID；
- 重复运行准备脚本会拒绝覆盖已有工程；
- GitHub Actions `Validate` 运行成功。

待确认：

1. 完全关闭 GUI Guider；
2. 打开
   `D:\figma\Figma--GuiGuider2.0_V9.4-\project\guiguider_2.0.guiguider`；
3. 确认项目名显示 `Figma_GuiGuider2_V9_4_local`；
4. 删除一个可恢复的测试控件；
5. 按 `Ctrl+S`；
6. 关闭后重新打开同一文件；
7. 确认删除仍然生效。

在第 7 步完成前，不将“GUI Guider 保存持久化已修复”写成已验证结论。

## 防止复发的检查项

- [ ] 克隆、候选、审核和正式工程的 `projectId` 必须不同；
- [ ] `projectName` 必须能在窗口中区分工程；
- [ ] `projectPath` 必须等于当前工程所在目录；
- [ ] 不用不同文件名代替项目身份隔离；
- [ ] 打开后检查 GUI Guider 页面树和项目名，不只看进程参数；
- [ ] 必要时检查 `%APPDATA%\GUIGuider\2.0.0\project_history.json`；
- [ ] 手工修改后的验证必须包含“保存、关闭、重开”；
- [ ] 本地准备脚本默认不得覆盖已存在工程；
- [ ] `--force` 只能用于明确放弃本地修改并重新生成的场景。
