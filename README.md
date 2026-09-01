# Yosys Hierarchical Equivalence

`yosys-hier-equiv` 是一个独立的 Yosys 等价检查工具原型，用于比较两份由
Yosys 生成的层次化 Verilog。它与 `examples/` 中的 transform golden 回归
解耦，后续可以迁移为独立子仓库。

当前提供两种检查方式：

- `flatten-oracle`：分别完整展开 Gold 和 Gate，作为简单、可信但开销较大的
  Golden Oracle。
- `hier-check`：从顶层实例关系建立模块对，递归执行组合证明；无法唯一匹配的
  模块对局部展开。可同时运行 Oracle 检查两种结论是否一致。

算法边界和回退规则详见 [docs/design.md](docs/design.md)。

## 使用方法

直接从源码运行：

```bash
PYTHONPATH=src python3 -m yosys_hier_equiv flatten-oracle \
  --gold path/to/gold.v \
  --gate path/to/gate.v \
  --common path/to/common.v \
  --top top \
  --work-dir build/example
```

层次化检查并同时运行 Golden Oracle：

```bash
PYTHONPATH=src python3 -m yosys_hier_equiv hier-check \
  --gold path/to/gold.v \
  --gate path/to/gate.v \
  --common path/to/common.v \
  --top top \
  --validate-oracle \
  --work-dir build/hier-example
```

也可以安装命令行入口：

```bash
python3 -m pip install -e .
yosys-hier-equiv flatten-oracle --gold gold.v --gate gate.v --top top
```

退出码：

- `0`：等价检查通过。
- `1`：等价检查未通过，或 Yosys 执行失败。
- `2`：命令行参数错误。
- `3`：层次化结果与 Golden Oracle 不一致。

Oracle 生成的 `equiv.ys` 和 `equiv.log` 保存在 `--work-dir` 中。层次化检查还会
保留两侧 inventory、每个模块对的 Yosys 脚本与日志，以及汇总用的
`report.json`。

## 测试

```bash
make test
```

测试使用手写 Verilog，覆盖等价重写、层次模块改名、子模块逻辑错误、端口交换、
实例缺失、参数错误、时序连接错误、层次回退和重复模块对缓存。层次化检查对每个
场景都与 Golden Oracle 对照。
