# 层次化等价工具实现方案

## 1. 文档定位

本文档面向工具开发者，记录 `yosys-hier-equiv` 的问题定义、全展开 Golden
Oracle 和层次化递归检查的实现约束。

当前状态：

- 方案 2 / Phase 1：全展开 Golden Oracle，已实现并通过手写用例。
- 方案 3 / Phase 2：自顶向下层次化等价，第一版已实现并由 Oracle 对照验证。

## 2. 问题

REMUS transform 生成的 `emu_system.v` 同时包含顶层和大量生成模块。不同 Yosys
构建环境可能改变临时网络名、端口输出顺序和参数化模块名，因此文本 diff 不能
可靠地区分功能变化与无意义的文本变化。

只比较顶层也不充分。如果 `emu_system.v` 中实例化了一个没有被读入的外部模块，
Yosys 无法获知端口方向和功能，端口交换或实例删除可能不会形成可证明的功能差异。
如果最终等价设计只复制 Gold 和 Gate 顶层，`emu_system.v` 中定义的子模块也会被
错误地排除在检查之外。

本工具需要回答：

1. Gold 和 Gate 展开后的功能是否等价。
2. 在不完整展开大设计的情况下，能否递归证明对应的层次模块。
3. 当层次匹配失败时，能否使用全展开结果作为判断基准。

## 3. 目标与非目标

目标：

- 独立于 REMUS transform 和 `examples/` 目录。
- 使用显式源码列表，不自行实现 HDL 依赖解析。
- 保留 Yosys 脚本和日志，确保失败可复现。
- 先提供简单、可信但较慢的全展开 Oracle。
- 使用 Oracle 验证未来层次化实现的结果。

当前非目标：

- 取代 Bender 等依赖管理工具。
- 对任意两个完全不同结构的网表推导最优层次映射。
- 把功能等价解释为 Verilog 文本或实例结构完全相同。
- 在第一版中优化大型 memory 和复杂时序设计的证明性能。

## 4. 目录结构

```text
yosys-hier-equiv/
  README.md
  Makefile
  pyproject.toml
  docs/
    design.md
  src/yosys_hier_equiv/
    __init__.py
    __main__.py
    cli.py
    hierarchy.py
    oracle.py
  tests/
    test_flatten_oracle.py
    cases/
      ... handwritten Verilog fixtures ...
```

所有文档、实现和测试均位于该目录下，避免形成对 REMUS 仓库内部 Python 包的
依赖，为后续迁移成子仓库保留边界。

## 5. Phase 1：全展开 Golden Oracle

### 5.1 输入

- 一组 Gold Verilog 文件。
- 一组 Gate Verilog 文件。
- 可选的公共 Verilog 文件。公共文件会在两侧分别读入。
- Gold 和 Gate 共用的顶层模块名。
- include 目录和 `equiv_simple` 时序深度。

第一版要求顶层名是普通 Verilog identifier，路径中不允许换行。路径由 Python
转义后写入 Yosys 脚本。

### 5.2 算法

Gold 和 Gate 分别执行：

```text
read_verilog common + side sources
hierarchy -check -top <top>
flatten
proc
memory
opt_clean
rename top -> gold/gate
design -stash
```

随后构造等价设计：

```text
design -copy-from gold gold
design -copy-from gate gate
equiv_make -inames gold gate equiv
hierarchy -top equiv
equiv_simple -seq <N>
equiv_status -assert
```

`flatten` 使两侧 `emu_system.v` 中定义的全部可达模块进入比较，也消除了生成模块
名称无法直接对应的问题。公共模块同样被展开，因此公共模块的端口方向、参数和
行为都能参与检查。

### 5.3 Oracle 语义

Oracle 判断的是可观察功能等价，而不是结构完全一致。因此：

- 模块改名但功能不变，应通过。
- 德摩根变换等功能等价重写，应通过。
- 可观察的端口交换、逻辑变化、参数变化和实例删除，应失败。
- 完全不可观察的冗余实例或死逻辑可能被优化掉并通过。

这一边界必须保留。后续如果需要严格检查实例集合，应增加独立结构规则，而不能
改变“等价”的定义。

### 5.4 已知代价

- 完整展开会增大组合逻辑和状态空间。
- `memory` 可能把较大 memory 映射为寄存器和 mux，显著增加时间和内存。
- `equiv_simple -seq N` 不是任意时序设计的完备证明方法。
- 第一版优先用于小型测试和作为层次化实现的 Oracle，不承诺大型 REMUS 设计的
  运行时间。

## 6. Phase 2：自顶向下层次化等价

### 6.1 设计隔离与 Inventory

Gold 和 Gate 由两个独立的 Yosys design 分别读取，执行 `hierarchy`、`proc`、
`memory` 和 `opt_clean` 后导出 JSON inventory。Inventory 记录可达模块、端口和
cell type，用来发现模块对。

每个证明义务也分别读取两侧设计，再通过 `design -stash` 隔离。工具不会用 Gold
侧模块补齐 Gate 侧生成模块，也不对 Verilog 文本做模块重命名。这样避免两个设计
中的同名模块互相覆盖，同时支持 `$paramod...` 等 Yosys 派生模块名。

### 6.2 自顶向下发现 ModulePair

入口模块对由用户明确给出：

```text
ModulePair(gold_top, gate_top)
```

比较父模块时，根据对应实例建立子模块对。例如：

```text
Gold: u_fifo -> gold__generated_A
Gate: u_fifo -> gate__generated_X

ModulePair(gold__generated_A, gate__generated_X)
```

这样模块对应关系来自父模块中的实例关系，不依赖生成模块名称或参数哈希。

第一版层次匹配规则保持保守：

1. 只自动匹配相同的公开实例名。
2. 检查端口名称、方向和位宽是否兼容；派生参数的功能由子模块证明覆盖。
3. 相同 black box 只能按相同 cell type 形成共同假设，不递归证明其内部。
4. 实例集合或接口无法唯一匹配时不猜测，改为局部展开。

同一个 Gold 模块可以在不同上下文中形成多个 ModulePair。缓存键应是
`(gold_module, gate_module)`，不应强制全局一对一映射。

### 6.3 组合证明

证明父模块时，为每个待证明子模块对生成一个共同的抽象模块接口：

```text
gold child instance -> __equiv_stub_pair_N
gate child instance -> __equiv_stub_pair_N
```

抽象模块保留端口名称、方向和位宽。同一个父模块中的每个对应实例使用独立 stub，
防止不同实例被错误地当成同一状态。父模块等价检查验证：在对应子模块功能等价的
假设下，两侧子模块输入连接、输出连接和父模块局部逻辑是否等价。

之后递归证明每个 ModulePair。只有所有子模块假设均被证明，顶层结果才能判定为
通过。这是组合证明的闭合条件，不能把未证明子模块当作永久公共模块。

### 6.4 局部展开回退

出现以下情况时，对当前 ModulePair 使用全展开比较：

- 两侧层次实例集合无法按实例名建立唯一对应。
- 两侧层次被合并或拆分。
- 端口接口发生无法自动映射的变化。
- 组合证明产生无法解释的未证明等价点。

回退只展开当前子树，而不是整个 `emu_system`。全展开 Oracle 用于验证局部回退和
层次化最终结论是否一致。

### 6.5 结果与 Oracle 对照

`hier-check --validate-oracle` 在层次化检查完成后运行一次方案 2。两者结论不一致
时返回独立退出码 `3`，不能把层次化结果当作通过。`report.json` 记录每个模块对的
方法、子模块对、结论、原因和日志路径。

第一版仍有以下限制：

- 不根据任意结构签名猜测不同实例名之间的对应关系，而是回退到局部展开。
- 每个模块对会重新读取源码，尚未优化为长期驻留的 Yosys 进程。
- 参数、memory 和复杂时序设计的规模上限尚未用真实 `emu_system.v` 建立基线。
- 证明能力仍受 `equiv_simple -seq N` 的边界约束。

## 7. 测试策略

Phase 1 手写测试至少覆盖：

| 场景 | 预期 |
| --- | --- |
| 完全相同设计 | Pass |
| 子模块名称不同但功能相同 | Pass |
| 不同结构的等价逻辑 | Pass |
| 子模块内部 AND/OR 变化 | Fail |
| 非对称公共模块端口交换 | Fail |
| 可观察实例被删除 | Fail |
| 参数选择变化 | Fail |
| 时序数据输入接错 | Fail |
| 实例名变化但子树功能相同 | Pass，局部展开回退 |
| 子模块独立不等价，但在父级连接约束下等价 | Pass，父级局部展开回退 |
| 同一模块对被重复实例化 | Pass，只递归证明一次 |

Phase 2 测试复用同一组输入，并要求层次化结果与 Oracle 一致。当前额外覆盖了参数
派生模块名、重复模块实例、模块对缓存和局部展开回退。多对多映射和大型真实设计
仍需后续补充。

## 8. 开发顺序

- [x] 建立独立目录和文档。
- [x] 实现全展开 Golden Oracle CLI。
- [x] 添加手写小型测试。
- [ ] 使用真实 `emu_system.v` 建立性能基线。
- [x] 使用独立 Yosys design 和 JSON inventory 隔离 Gold/Gate。
- [x] 实现保守的 ModulePair 发现和缓存。
- [x] 实现抽象子模块与组合证明。
- [x] 实现局部展开回退。
- [x] 使用 Golden Oracle 对照验证层次化结果。
- [ ] 使用真实设计补充多对多模块对和性能测试。
