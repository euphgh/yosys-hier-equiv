# 使用指南

目标读者：需要比较两份 Verilog/SystemVerilog 设计的工具使用者。

文档类型：用户指南。

当前状态：覆盖 `main` 分支当前 CLI。

## 1. 前置条件

需要：

- [uv](https://docs.astral.sh/uv/)，用于创建和管理 Python 虚拟环境

Yosys 由仓库自带的 OSS CAD Suite（`.local/`）提供，无需系统安装。在仓库根目录
加载环境，首次运行会自动创建 `.venv` 并以 editable 模式安装本工具：

```bash
source EnvSetup.sh
```

检查环境：

```bash
yosys -V
yosys-hier-equiv --help
```

后续示例统一使用 `yosys-hier-equiv` 命令，它与 `python3 -m yosys_hier_equiv`
完全等价。

## 2. 选择检查模式

### 2.1 `hier-check`

默认推荐路径。工具从顶层递归证明模块对，只在必要时展开当前模块子树。

开发阶段建议总是添加 `--validate-oracle`：

```bash
yosys-hier-equiv hier-check \
  --gold gold.v \
  --gate gate.v \
  --top top \
  --validate-oracle \
  --work-dir build/hier-check
```

### 2.2 `flatten-oracle`

完整展开两侧设计后检查等价。它不依赖层次模块映射，适合作为 Golden Oracle，
但大型设计可能消耗更多时间和内存。

```bash
yosys-hier-equiv flatten-oracle \
  --gold gold.v \
  --gate gate.v \
  --top top \
  --work-dir build/flatten-oracle
```

## 3. 输入组织

### 3.1 Gold 和 Gate 源码

每个 `--gold` 或 `--gate` 只接收一个文件，多个文件需要重复参数：

```bash
yosys-hier-equiv hier-check \
  --gold gold/pkg.v \
  --gold gold/generated_cells.v \
  --gold gold/design.v \
  --gate gate/pkg.v \
  --gate gate/generated_cells.v \
  --gate gate/design.v \
  --top design \
  --validate-oracle \
  --work-dir build/multi-source-check
```

同一侧的参数顺序就是 `read_verilog` 的读取顺序。

### 3.2 公共源码

两侧使用同一份库文件时，用重复的 `--common` 指定：

```bash
  --common rtl/FIFO.v \
  --common rtl/EmuSysCtrl.v
```

公共源码会先于该侧源码，分别读入 Gold 和 Gate design。`--common` 只是减少 CLI
重复，不会让工具跳过这些模块的功能：

- 有实现体的公共模块仍可能被展开或递归证明。
- 两侧相同类型的显式 black box 才会作为共同假设，不检查内部。

不要把需要参与比较的 Gold/Gate 生成模块错误地放入 `--common`。

### 3.3 include 目录

每个 include 目录重复使用 `-I` 或 `--include-dir`：

```bash
  -I rtl/include \
  -I generated/include
```

工具不自动搜索依赖。`hierarchy -check` 要求所有可达模块都有定义或显式 black-box
声明，否则 inventory 阶段会失败。

### 3.4 SystemVerilog

使用 `--sv` 后，所有 Gold、Gate 和公共源码都会通过 `read_verilog -sv` 读取：

```bash
  --sv
```

当前不能只对部分文件启用 `-sv`。

### 3.5 顶层模块

`--top` 指定两侧共同的顶层模块名：

```bash
  --top design
```

当前要求 Gold 和 Gate 顶层同名，并且名称是普通 Verilog identifier。子模块名称
可以不同。

## 4. 参数参考

两个子命令共用以下参数：

| 参数 | 是否必需 | 含义 |
| --- | --- | --- |
| `--gold FILE` | 是，可重复 | Gold 侧源码 |
| `--gate FILE` | 是，可重复 | Gate 侧源码 |
| `--common FILE` | 否，可重复 | 两侧分别读入的公共源码 |
| `-I DIR` | 否，可重复 | Verilog include 目录 |
| `--top NAME` | 否 | 顶层模块，默认 `top` |
| `--seq N` | 否 | `equiv_simple` 时序深度，默认 `2` |
| `--work-dir DIR` | 否 | 脚本、日志和报告目录 |
| `--yosys PATH` | 否 | Yosys 可执行文件，默认读取 `YOSYS` 环境变量或使用 `yosys` |
| `--sv` | 否 | 将全部源码按 SystemVerilog 读取 |

`hier-check` 额外支持：

| 参数 | 含义 |
| --- | --- |
| `--validate-oracle` | 完成层次化检查后，再运行一次完整展开 Oracle |

实时参数以命令帮助为准：

```bash
yosys-hier-equiv hier-check --help
yosys-hier-equiv flatten-oracle --help
```

## 5. 工作目录产物

`flatten-oracle` 生成：

```text
<work-dir>/
  equiv.ys
  equiv.log
```

`hier-check` 生成：

```text
<work-dir>/
  inventory-gold.ys
  inventory-gold.log
  inventory-gold.json
  inventory-gate.ys
  inventory-gate.log
  inventory-gate.json
  report.json
  pairs/
    0000/
      equiv.ys
      equiv.log
      stubs.v             # 该模块对有抽象子模块时存在
      fallback/           # 组合证明后又回退时可能存在
        equiv.ys
        equiv.log
  oracle/                 # 使用 --validate-oracle 时存在
    equiv.ys
    equiv.log
```

`pairs/NNNN` 是内部编号，不应被脚本当作稳定模块标识。自动化程序应读取
`report.json`。

## 6. `report.json`

顶层字段：

- `equivalent`：层次化最终结果。
- `oracle_equivalent`：Oracle 结果；未运行时为 `null`。
- `oracle_consistent`：两种算法是否一致。
- `oracle_log_path`：Oracle 日志路径。
- `pairs`：已处理模块对。

每个模块对包含：

- `gold_module`、`gate_module`
- `equivalent`
- `method`
- `reason`
- `children`
- `log_path`

`method` 可能为：

- `leaf`：模块没有需要递归证明的实现模块。
- `compositional`：父级 stub 证明和所有子证明均闭合。
- `flatten-fallback`：当前模块子树使用局部展开。

报告中的子模块结果可能失败，但父模块经过上下文约束后的局部展开仍然通过。判断
整个设计时必须使用顶层 `equivalent`，不能简单要求 `pairs` 中所有条目都为
`true`。

## 7. 退出码

| 退出码 | 含义 |
| --- | --- |
| `0` | 等价检查通过 |
| `1` | 不等价，输入无效，或者 Yosys 执行失败 |
| `2` | `argparse` 命令行参数错误 |
| `3` | `hier-check` 与 Golden Oracle 结论不一致 |

退出码 `1` 同时包含功能不等价和工具错误。区分方法：

- CLI 输出 `FAIL:`：Yosys 完成但未证明等价。
- CLI 输出 `error:`：输入检查、inventory 或 Yosys 执行出现错误。
- 最终判断仍应查看对应日志。

## 8. 推荐运行流程

1. 使用新的工作目录运行 `hier-check --validate-oracle`。
2. 先检查退出码和 `report.json`。
3. 如果 inventory 失败，查看 `inventory-gold.log` 或 `inventory-gate.log`。
4. 如果某个模块对失败，从报告中的 `log_path` 查看 `$equiv` 未证明点。
5. 查看同目录 `equiv.ys`，确认实际读取的源码、顶层和 Yosys pass。
6. 如果两种算法不一致，保留完整工作目录并构造最小 RTL fixture，不要直接忽略
   退出码 `3`。

详细算法背景见 [架构与算法](architecture.md)。
