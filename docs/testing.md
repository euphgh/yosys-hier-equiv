# 测试指南

目标读者：修改等价算法、CLI 或测试基础设施的开发者。

文档类型：开发与验证指南。

当前状态：描述 `main` 分支现有 11 个手写场景。

## 1. 运行测试

```bash
make test
```

等价命令为：

```bash
PYTHONPATH=src YOSYS=yosys \
  python3 -m unittest discover -s tests -v
```

可以指定其他 Yosys：

```bash
make test YOSYS=/path/to/yosys
```

如果找不到 Yosys，测试类会被标记为 Skip。Skip 只能说明 Python 测试可以被
发现，不能证明工具行为正确。

## 2. 当前测试矩阵

| Fixture | 预期 | 主要覆盖内容 |
| --- | --- | --- |
| `pass_identical` | Pass | 完全相同的层次设计 |
| `pass_equivalent_rewrite` | Pass | AND 与德摩根形式功能等价 |
| `pass_renamed_hierarchy` | Pass | 实例名相同、子模块类型名不同，递归建立 ModulePair |
| `pass_hierarchy_fallback` | Pass | 实例名不同，顶层触发局部展开 |
| `pass_parent_context` | Pass | 子模块独立不等价，但在父级常量连接约束下顶层等价 |
| `pass_reused_pair` | Pass | 同一 ModulePair 被两个实例复用，只证明一次 |
| `fail_internal_logic` | Fail | 子模块内部 AND 被改为 OR |
| `fail_swapped_ports` | Fail | 非对称公共模块的两个输入交换 |
| `fail_missing_instance` | Fail | 可观察实例被删除 |
| `fail_parameter` | Fail | 参数化模块选择不同功能 |
| `fail_sequential_connection` | Fail | 寄存器数据输入从 `a` 接成 `b` |

所有场景都会运行完整展开 Oracle。层次化测试还会使用
`validate_oracle=True`，要求方案 3 与 Oracle 结论一致。

## 3. 测试代码结构

```text
tests/
  test_flatten_oracle.py
  cases/
    pass_<scenario>/
      gold.v
      gate.v
      common.v            # 可选
    fail_<scenario>/
      gold.v
      gate.v
      common.v            # 可选
```

`tests/test_flatten_oracle.py` 当前包含三组断言：

1. 所有 Pass fixture 必须被 Oracle 证明等价。
2. 所有 Fail fixture 必须由 Oracle 留下未证明的 `$equiv`。
3. 每个 fixture 的层次化结果必须符合预期，并与 Oracle 一致。

回退和缓存场景还检查 `PairResult.method` 或模块对数量。

## 4. 新增测试

### 4.1 建立最小 fixture

例如新增端口位宽错误：

```text
tests/cases/fail_port_width/
  gold.v
  gate.v
```

fixture 应只保留触发目标行为所需的最小模块和信号。不要直接复制大型生成 RTL，
否则失败原因和期望语义难以固定。

### 4.2 选择 `common.v`

只有两侧确实读取同一文件时才添加 `common.v`，例如公共 primitive 或参数化模块。
需要比较的生成模块必须分别放在 `gold.v` 和 `gate.v`。

### 4.3 更新测试列表

当前测试文件分别维护 Pass 列表、Fail 列表和层次化期望字典。新增 fixture 后需要
同步更新相关位置。

如果测试针对特定层次行为，还应增加定向断言，例如：

```python
self.assertEqual(result.pairs[-1].method, "flatten-fallback")
self.assertEqual(len(result.pairs), 2)
```

不要依赖 `pairs/0000` 对应某个固定模块；目录编号是内部实现细节。

### 4.4 运行完整回归

```bash
make test
python3 -m compileall -q src tests
```

测试通过后，检查新增场景是否真的经过预期路径。必要时保留一次非临时
`--work-dir`，读取 `report.json` 和模块对日志。

## 5. 测试设计原则

- Pass 场景验证可观察功能等价，而不是文本相同。
- Fail 场景中的差异必须能传播到顶层可观察输出或状态。
- 如果差异是死逻辑，Yosys 可能优化掉并正确判定 Pass。
- 测试层次匹配时，要区分模块类型名和实例名；当前只有相同实例名自动配对。
- 时序场景必须明确 `--seq` 深度和复位假设。
- black box 场景必须同时验证接口一致和共同假设边界。
- 算法 bug 应先固化为最小 fixture，再修改实现。

## 6. 尚需补充的验证

- 真实 REMUS `emu_system.v` 正确性与性能基线
- include 目录和混合 Verilog/SystemVerilog 工程
- 显式 black box 的正向和错误接口场景
- 多层参数派生模块和重复 ModulePair
- 大型 memory 的资源与证明行为
- 不同 `--seq` 深度的时序边界
- Yosys 执行中断、非法源码和报告生成失败等错误路径

实现路线和性能基线记录要求见 [开发指南](development.md)。
