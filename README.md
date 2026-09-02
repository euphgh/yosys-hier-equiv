# Yosys Hierarchical Equivalence

`yosys-hier-equiv` 是一个基于 Yosys 的层次化 Verilog 等价检查工具，用于判断两份
应当功能等价的 Verilog/SystemVerilog 设计（例如自动生成流程产出的 Gold 与 Gate
两份 RTL）是否真的等价。它是自包含的独立 Python 项目，不依赖任何外部工作区。

工具提供两条互补路径：

- `flatten-oracle`：完整展开两侧设计后做功能等价检查，作为简单、可信但可能较慢
  的 Golden Oracle。
- `hier-check`：从顶层建立模块对，递归执行组合证明；无法可靠匹配或组合证明不足
  时，只展开当前模块子树。可选用 Oracle 对照最终结论。

当前版本是可运行的开发原型。11 个手写 RTL 场景已经覆盖基础等价、模块改名、
连接错误、参数错误、时序错误、层次回退和模块对缓存；真实大型设计的性能边界
尚未建立。

## 环境要求

- [uv](https://docs.astral.sh/uv/)，用于创建和管理 Python 虚拟环境
- GNU Make，仅在运行仓库测试时需要

Yosys 由仓库自带的 OSS CAD Suite（`.local/`）提供，无需系统安装。在仓库根目录
执行：

```bash
source EnvSetup.sh
```

首次运行时脚本会用 `uv sync` 创建 `.venv` 并以 editable 模式安装本工具，然后把
`.venv/bin` 和 `.local/bin` 加入 `PATH`，并导出 `YOSYS` 环境变量。脚本可重复
source，幂等。

## 快速开始

推荐先运行层次化检查，并用完整展开 Oracle 对照：

以下示例使用 EnvSetup.sh 安装的 `yosys-hier-equiv` 命令，它与
`python3 -m yosys_hier_equiv` 等价。

推荐先运行层次化检查，并用完整展开 Oracle 对照：

```bash
yosys-hier-equiv hier-check \
  --gold path/to/gold.v \
  --gate path/to/gate.v \
  --top top \
  --validate-oracle \
  --work-dir build/my-check
```

只运行完整展开 Oracle：

```bash
yosys-hier-equiv flatten-oracle \
  --gold path/to/gold.v \
  --gate path/to/gate.v \
  --top top \
  --work-dir build/my-oracle
```

多个源码、公共源码、include 目录、SystemVerilog 和时序深度等用法见
[使用指南](docs/usage.md)。

## 查看结果

成功时命令返回 `0`，不等价或 Yosys 执行失败返回 `1`。`hier-check` 使用
`--validate-oracle` 时，如果层次化结果与 Oracle 不一致，会返回 `3`。

层次化检查在工作目录中保留：

- 两侧 JSON inventory 和生成日志
- 每个模块对的 Yosys 脚本、stub、证明日志和回退日志
- 汇总文件 `report.json`
- 可选的完整展开 Oracle 脚本和日志

建议每次运行使用新的 `--work-dir`，避免旧的调试产物干扰人工检查。

## 测试

```bash
source EnvSetup.sh
make test
```

Yosys 由 `.local/` 提供；如需使用其他 Yosys，可用 `make test YOSYS=/path/to/yosys`
覆盖。测试场景、预期结果和新增测试方法见 [测试指南](docs/testing.md)。

## 文档

- [文档入口](docs/index.md)：按任务选择阅读路径。
- [使用指南](docs/usage.md)：完整 CLI、输入组织、产物和结果分析。
- [架构与算法](docs/architecture.md)：Oracle、组合证明、模块对和回退语义。
- [测试指南](docs/testing.md)：当前测试矩阵和新增场景方法。
- [开发指南](docs/development.md)：代码地图、开发流程、调试路径和后续工作。
- [AGENTS.md](AGENTS.md)：下一个 agent 的最短启动说明和稳定约束。

## 当前限制

- 两侧必须使用同一个顶层模块名。
- 自动层次匹配只接受相同实例名和兼容接口；其他情况会局部展开。
- 工具依赖显式源码列表，不负责替代 Bender 或其他 HDL 依赖管理器。
- `equiv_simple -seq N` 不是任意时序设计的完备证明方法。
- 每个模块对目前都会重新启动 Yosys 并读取源码，尚未针对大型设计优化。

这些限制的背景和计划见 [开发指南](docs/development.md)。
