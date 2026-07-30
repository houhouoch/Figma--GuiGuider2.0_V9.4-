# 贡献指南

[English](CONTRIBUTING_EN.md) | 简体中文

## 修改范围

- 不得直接覆盖正式 GUI Guider 工程。
- 不得提交 NXP GUI Guider 安装内容、`platform/`、构建缓存或第三方字体。
- 单页面任务只能修改目标页面及必要的共享声明。
- GUI Guider 直接修复不应擅自重新运行 Figma 全量转换。

## 开发流程

1. 从固定 Manifest 和正式工程备份开始。
2. 生成独立候选工程。
3. 比较对象 ID、名称、类型、事件、变量、字体和非 UI 配置。
4. 验证资源闭包与字体引用/声明/定义。
5. 连续生成两次并比较哈希，确认幂等。
6. 进行视觉复核。
7. 获得用户明确批准后才可晋升。
8. 执行 GUI Guider 打开/保存/关闭往返。
9. Generate Code 后执行完整模拟器构建。

## 提交

- 每个提交只解决一个清晰问题。
- 使用英文 Conventional Commit，例如：

```text
fix: preserve GUI Guider font symbols
docs: document controlled promotion workflow
```

- PR 必须说明输入 Manifest、修改页面、验证结果和未完成的实机/人工验证。

## 验证

```bash
python tools/validate_repository.py
```

本地字体准备完成后再运行：

```bash
python skills/figma-to-guiguider-controlled-sync/scripts/audit_guiguider_project.py \
  --project project/guiguider_2.0.guiguider
```
