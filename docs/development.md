# 开发指南

目标读者：继续开发 CLI、Oracle、层次算法和验证基础设施的开发者或 agent。

文档类型：开发导航。

当前状态：区分当前实现与后续计划。

## 1. 开发前阅读

推荐顺序：

1. 根目录 `AGENTS.md`
2. `README.md`
3. [架构与算法](architecture.md)
4. [测试指南](testing.md)
5. 本次修改对应的源码

行为细节以当前源码和通过的测试为准。

## 2. 代码地图

```text
src/yosys_hier_equiv/
  __main__.py
  cli.py
  oracle.py
  hierarchy.py
tests/
  test_flatten_oracle.py
  cases/
```

### `cli.py`

负责：

- 定义 `flatten-oracle` 和 `hier-check`
- 把命令行参数转换为配置 dataclass
- 把结果转换为退出码和一行用户输出

CLI 不解析 Yosys 日志，也不包含证明算法。

### `oracle.py`

主要入口：

- `OracleConfig`
- `OracleResult`
- `render_flatten_oracle_script()`
- `run_flatten_oracle()`

该模块负责输入检查、Yosys 字符串转义、两侧完整展开、`equiv_make` 和日志保留。

### `hierarchy.py`

主要入口：

- `HierarchicalConfig`
- `PairResult`
- `HierarchicalResult`
- `run_hierarchical_check()`

内部职责包括：

- 为两侧生成 JSON inventory
- 计算模块端口签名和层次 cell 集合
- 产生 `_PairPlan`
- 为每个对应实例生成共同 stub
- 执行父级证明和递归子证明
- 必要时执行当前模块子树展开
- 缓存 ModulePair 并写出 `report.json`

## 3. 调用链

`flatten-oracle`：

```text
cli.main
  -> OracleConfig
  -> run_flatten_oracle
     -> validate inputs
     -> render equiv.ys
     -> run Yosys
     -> OracleResult
```

`hier-check`：

```text
cli.main
  -> HierarchicalConfig
  -> run_hierarchical_check
     -> build Gold/Gate inventory
     -> _HierarchyRunner.prove(top, top)
        -> plan child pairs
        -> prove parent with common stubs
        -> recursively prove child pairs
        -> locally flatten when required
     -> optional run_flatten_oracle
     -> write report.json
```

## 4. 开发流程

### 4.1 修改前

1. 确认修改的是用户接口、证明语义、性能还是错误处理。
2. 找到现有最接近的 fixture。
3. 明确一组应 Pass 和应 Fail 的可观察行为。
4. 如果改变稳定算法约束，先更新 `docs/architecture.md`。

### 4.2 实现

- 保持 Python 3.10 兼容。
- 默认只使用标准库。
- 路径使用 `pathlib.Path`。
- Yosys 对象信息从 JSON inventory 获取，不对生成 Verilog 做文本解析。
- 所有证明运行都应保留脚本和日志。
- 不要让 Gold 和 Gate 在同一个未隔离的 Yosys design 中覆盖同名模块。

### 4.3 验证

```bash
make test
python3 -m compileall -q src tests
PYTHONPATH=src python3 -m yosys_hier_equiv --help
```

CLI 或产物变化还应手动运行一个 Pass 和一个 Fail fixture，检查退出码、
`report.json` 和日志路径。

## 5. 调试路径

### Inventory 失败

查看：

```text
inventory-gold.ys
inventory-gold.log
inventory-gate.ys
inventory-gate.log
```

常见原因是源码遗漏、顶层名称错误、include 路径缺失或 Yosys 不支持输入语法。

### 模块对证明失败

从 `report.json` 找到模块对的 `log_path`，再同时检查：

- `equiv.ys` 是否读入了正确源码
- `stubs.v` 的端口方向和位宽
- 日志中哪些 `$equiv` 未证明
- `method` 是否已经进入 `flatten-fallback`

### 层次结果与 Oracle 不一致

退出码 `3` 是算法问题或证明能力差异，不能当作普通 Fail。处理顺序：

1. 保留整个工作目录。
2. 比较顶层、失败模块对和 `oracle/equiv.log`。
3. 将问题缩减为最小 Gold/Gate fixture。
4. 先新增回归测试，再修改层次算法。

## 6. 当前性能特征

当前实现为了隔离和可复现性，每个模块对都会重新启动 Yosys并重新读取源码。这一
策略实现简单，但模块对较多时会重复支付 frontend、`hierarchy`、`proc` 和
`memory` 的成本。

在优化前，应先对真实设计记录：

- Git commit 和 Yosys 版本
- Gold、Gate、common 源码列表
- 顶层和 `--seq`
- 总模块数、ModulePair 数和回退数
- Oracle 与层次化结果
- wall time 和最大 RSS
- 完整工作目录或可重现命令

没有基线前，不应仅凭小型 fixture 宣称方案 3 比完整展开更快。

## 7. 后续工作

### 优先级 1：真实设计基线

使用同一组真实 `emu_system.v` 输入分别运行：

1. `flatten-oracle`
2. `hier-check`
3. `hier-check --validate-oracle`

先证明结果一致和日志可分析，再讨论性能优化。

### 优先级 2：测试缺口

补充：

- black box 正反例
- include 和 SystemVerilog 输入
- 非法源码与执行失败路径
- 多层参数派生和更深时序状态
- 报告 schema 的稳定断言

### 优先级 3：减少重复 Yosys 工作

候选方向包括：

- 在一个 Yosys 进程内批量执行模块对证明
- 缓存已经完成 frontend 和 hierarchy 的设计快照
- 只为回退子树构造最小设计

任何优化都必须继续由 `flatten-oracle` 和现有 fixture 对照，不能改变功能结论。

### 优先级 4：更丰富的层次映射

当前不同实例名直接回退。未来可以评估保守结构签名，但必须满足：

- 映射唯一时才自动采用
- 歧义时继续回退
- 不要求生成模块类型名相同
- 映射错误必须能由 Oracle 对照发现

多对多层次拆分与合并应作为独立设计问题，不应混入简单实例名匹配。

## 8. 文档维护

- 用户参数变化：更新 `README.md` 和 `docs/usage.md`。
- 算法语义变化：更新 `docs/architecture.md`。
- fixture 或断言变化：更新 `docs/testing.md`。
- 代码地图、限制或优先级变化：更新本文件和 `AGENTS.md`。
- 新文档必须从 `docs/index.md` 可达。

本仓库当前没有 Sphinx 配置。文档验证以 Markdown 相对链接、命令示例和真实测试
为主。
