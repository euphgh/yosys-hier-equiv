# 架构与算法

目标读者：需要理解等价语义、正确性边界或修改算法的开发者。

文档类型：稳定技术专题。

当前状态：描述 `main` 分支当前实现；未来工作单独记录在 `development.md`。

## 1. 问题定义

Yosys 生成的层次化 Verilog 可能因为构建环境或 pass 行为发生以下无功能变化：

- 临时网络名改变
- 参数化派生模块名改变
- 模块输出顺序或文本格式改变
- 子模块类型名改变，但逻辑保持等价

因此文本 diff 不能可靠回答“两个 transform 产物是否功能等价”。

只读取并比较顶层也不充分。如果一个被实例化模块没有定义，Yosys 不知道它的端口
方向和功能，端口交换、实例删除或模块内部错误可能不会进入真实证明。如果只复制
Gold 和 Gate 顶层，生成文件中定义的子模块也可能被排除。

本工具需要同时提供：

1. 不依赖层次名称映射的完整展开 Golden Oracle。
2. 能在保留层次的情况下递归证明模块对的实现。
3. 层次匹配不可靠时的保守回退。

## 2. 等价语义

工具判断的是经过当前 Yosys 预处理后的可观察功能等价，不是文本或结构一致。

应该 Pass：

- 模块或内部网络改名
- 德摩根变换等逻辑等价重写
- 不可观察死逻辑被删除
- 子模块在父级输入约束下表现等价

应该 Fail：

- 能传播到顶层输出的连接交换
- 可观察实例删除
- 参数导致的功能变化
- 可观察状态更新输入变化

如果未来需要检查实例集合或连接风格严格一致，应增加独立结构规则，不应改变当前
“功能等价”的定义。

## 3. 输入模型

一次检查包含：

- Gold 源码列表
- Gate 源码列表
- 可选 common 源码列表
- include 目录
- 两侧共同的顶层模块名
- `equiv_simple` 时序深度
- Yosys 路径和工作目录

Gold 和 Gate 必须分别读取。common 源码也会在两侧各读一次，因此它不是直接跳过
证明的可信库声明。

## 4. 完整展开 Golden Oracle

实现位于 `src/yosys_hier_equiv/oracle.py`。

### 4.1 单侧准备

Gold 和 Gate 分别执行：

```text
design -reset-vlog
read_verilog common + side sources
hierarchy -check -top <top>
flatten
proc
memory
opt_clean
rename <top> gold/gate
design -stash gold/gate
```

两侧在不同 design snapshot 中处理，避免同名模块覆盖。

### 4.2 等价构造

```text
design -copy-from gold gold
design -copy-from gate gate
equiv_make -inames gold gate equiv
hierarchy -top equiv
equiv_simple -seq <N>
equiv_status -assert
```

`flatten` 使所有可达实现模块进入同一个比较模块，也消除了生成模块类型名映射问题。
Yosys 返回成功时 Oracle 判定等价，否则保留脚本和日志并判定未证明。

### 4.3 Oracle 的角色

Oracle 实现简单，主要用于：

- 小型回归的直接结论
- 层次化实现开发时的 Golden 对照
- 层次自动匹配失败时确认局部或全局功能

它不是数学意义上对任意 Verilog 的完备判定器。证明能力仍受 Yosys pass、memory
处理和 `equiv_simple -seq N` 限制。

## 5. 层次化检查总体流程

实现位于 `src/yosys_hier_equiv/hierarchy.py`。

```text
Gold sources -> Yosys JSON inventory --+
                                      +-> prove ModulePair(top, top)
Gate sources -> Yosys JSON inventory --+       |
                                               +-> parent proof with stubs
                                               +-> recursive child proofs
                                               +-> local flatten fallback
                                                        |
                                                        v
                                                   report.json
                                                        |
                                      optional full-flatten Oracle
```

## 6. JSON Inventory

两侧分别执行：

```text
read_verilog
hierarchy -check -top <top>
proc
memory
opt_clean
write_json
```

Inventory 记录当前顶层可达的：

- 模块
- 端口名称、方向和位宽
- cell 名称和 type
- 参数化后产生的 `$paramod...` 模块

如果一个 cell 的 type 也存在于 inventory 的 modules 中，它被视为可递归的层次
实例。Yosys 内部 primitive 不会形成 ModulePair。

## 7. ModulePair 发现

入口固定为：

```text
ModulePair(gold_top, gate_top)
```

对于父模块，第一版只自动匹配相同实例名。例如：

```text
Gold: u_fifo -> gold_generated_A
Gate: u_fifo -> gate_generated_X
```

产生：

```text
ModulePair(gold_generated_A, gate_generated_X)
```

模块 type 名不需要相同。建立模块对前会比较子模块端口名称、方向和位宽。

以下情况不做猜测：

- 两侧层次实例名称集合不同
- 对应实例接口不兼容
- 一侧是 black box，另一侧不是
- 两侧 black box type 不同

这些情况直接对当前模块对执行局部展开。

ModulePair 使用 `(gold_module, gate_module)` 作为缓存键。同一模块对被多个实例使用
时只证明一次；不同上下文可以形成不同模块对。

## 8. 父级组合证明

对于每个匹配的子实例，工具生成一个共同 black-box stub：

```text
Gold child cell -> __hier_equiv_stub_N
Gate child cell -> __hier_equiv_stub_N
```

stub 保留子模块端口的名称、方向和位宽。每个实例拥有独立 stub type，避免两个
实例被错误关联为同一个抽象状态或输出。

替换完成后，父模块证明检查：

- 两侧实例输入连接是否等价
- 两侧实例输出如何连接到父级逻辑
- 父模块自身 primitive 和状态逻辑是否等价

该步骤只是在“子模块对功能相同”的假设下证明父级，不能单独闭合顶层结论。

## 9. 递归闭合

父级组合证明通过后，工具递归证明每个实现子模块对。只有父级和所有递归义务都
通过，当前 ModulePair 才以 `compositional` 通过。

叶子模块没有实现子模块，直接比较自身 primitive 和状态逻辑，以 `leaf` 通过。

两侧相同 type 的显式 black box 可以形成共同 stub，但不会递归证明内部。该结论
依赖用户提供的 black-box 接口和共同实现假设。

## 10. 局部展开回退

当前 ModulePair 在以下情况进入 `flatten-fallback`：

1. 层次实例集合或接口无法可靠匹配。
2. 父级共同 stub 证明失败。
3. 任意递归子模块义务失败。

回退会把当前模块作为顶层，完整展开其可达子树后重新比较，而不是立即展开整个
原始设计。

第三种情况是避免假阴性的关键。例如：

```text
Gold child: y = a | b
Gate child: y = a ^ b
Parent:      b = 0
```

两个 child 模块独立不等价，但在父级连接约束下都得到 `y = a`。递归 child 证明会
失败，父级子树展开则能证明顶层等价。报告会同时保留失败 child 和通过的父级回退，
因此最终结果必须读取顶层 `equivalent`，不能要求所有 pair 都为 true。

### 10.1 回退通过时的 Warning

回退证明通过且最终结论为 Pass，但该模块对没有组合证明闭合时，工具为该模块对记录
Warning。Warning 同时出现在 `report.json` 和 CLI 输出中。三种触发路径：

1. 层次无法可靠匹配，规划期直接进入回退并通过。
2. 父级共同 stub 证明失败，局部展开通过。
3. 递归子模块义务失败（例如子模块独立不等价，但父级将其输入接常量掩蔽），
   局部展开通过。此时每个失败的子对各产生一条 Warning，点名该子对。

Warning 只说明该 Pass 的证明强度弱于组合证明，不改变结论，也不影响退出码。
判断整个设计时仍以顶层 `equivalent` 为准。

## 11. Oracle 对照

`hier-check --validate-oracle` 在层次化结果完成后运行一次全设计 Oracle：

```text
hierarchical_result == oracle_result
```

不一致时：

- `oracle_consistent` 为 `false`
- CLI 返回退出码 `3`
- 两套脚本和日志都保留

这表示层次算法、回退逻辑或证明能力存在需要分析的差异，不能静默采用任一结果。

## 12. 报告模型

每个 `PairResult` 记录：

- Gold/Gate 模块名
- 当前模块对结论
- `leaf`、`compositional` 或 `flatten-fallback`
- 进入该方法的原因
- 递归 child ModulePair
- 最终使用的 Yosys 日志
- 回退通过时的 Warning 列表

`HierarchicalResult` 记录顶层结论、全部模块对、报告路径、可选 Oracle 结果，以及
全部模块对 Warning 的聚合。

## 13. 正确性边界

当前实现需要明确保留以下限制：

- 顶层模块名必须相同。
- 不同实例名不会自动建立对应关系，而会回退。
- black box 内部不会被证明。
- 每个模块对重新读取源码，性能尚未针对大型设计优化。
- `memory` 可能把 memory 转为寄存器和 mux，显著放大设计。
- `equiv_simple -seq N` 不是任意复杂时序系统的完备证明。
- 完整展开 Oracle 目前只在手写小型场景上作为 Golden 验证，真实大型设计
  基线仍未建立。

后续实现路线见 [开发指南](development.md)，当前验证覆盖见
[测试指南](testing.md)。
