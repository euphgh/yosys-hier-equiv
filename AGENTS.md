# AGENTS

本文件是 agent 进入 `yosys-hier-equiv` 仓库后的启动说明。目标是让后续工作从当前
真实实现继续，而不是重新推导已经确定的算法边界。

## 1. 项目定位

- 本项目是自包含的独立 Yosys 层次化 Verilog 等价检查工具，不依赖任何外部
  工作区、私有包或系统级 Yosys 安装。
- 当前默认分支是 `main`。
- 开发环境由仓库内 `EnvSetup.sh`、`.local/`（OSS CAD Suite）和 uv 管理的
  `.venv` 提供。
- `flatten-oracle` 是完整展开 Golden Oracle；`hier-check` 是层次化递归实现。
- 当前代码已经通过 16 个手写 RTL 场景。真实大型设计的时间和内存
  基线尚未验证。

## 2. 优先阅读顺序

收到任务后按以下顺序补上下文：

1. 本文件
2. [README.md](README.md)
3. [docs/index.md](docs/index.md)
4. 与任务相关的专题文档
5. 对应源码和测试

按任务选择专题：

- CLI、输入或产物：`docs/usage.md`、`src/yosys_hier_equiv/cli.py`
- 算法或等价语义：`docs/architecture.md`、`oracle.py`、`hierarchy.py`
- 测试：`docs/testing.md`、`tests/test_flatten_oracle.py`、`tests/cases/`
- 后续开发：`docs/development.md`

## 3. 当前权威来源

信息优先级如下：

1. 当前分支上的源码
2. `tests/` 中实际执行的断言和 RTL fixture
3. `docs/architecture.md` 中的稳定算法约束
4. `docs/development.md` 中的后续计划

如果文档与代码冲突，以代码和通过的测试为准，同时修正文档。不要把计划中的
能力写成当前已经支持。

## 4. 仓库地图

- `src/yosys_hier_equiv/cli.py`
  两个子命令的参数解析、退出码和用户输出。
- `src/yosys_hier_equiv/oracle.py`
  完整展开 Oracle 的配置、Yosys 脚本生成和执行。
- `src/yosys_hier_equiv/hierarchy.py`
  JSON inventory、ModulePair 发现、stub 生成、递归证明、局部展开回退和报告。
- `tests/test_flatten_oracle.py`
  Oracle 与层次化结果的自动化断言。
- `tests/cases/`
  手写 Gold、Gate 和可选公共 RTL。
- `docs/`
  用户使用、架构、测试和开发导航。

## 5. 稳定算法约束

修改实现时必须保持以下边界，除非用户明确要求改变设计：

1. Gold 和 Gate 必须在独立 Yosys design 中读取，不能用 Gold 侧模块定义补齐
   Gate 侧生成模块。
2. `--common` 表示两侧分别读取同一源码，不表示跳过该源码的功能检查。
3. Oracle 比较完整展开后的可观察功能，不要求文本或实例结构相同。
4. 层次化实现从用户指定的顶层开始，只自动匹配相同实例名和兼容端口接口。
5. 每个匹配实例使用独立共同 stub，不能让不同实例共享一个抽象状态。
6. 顶层通过需要闭合所有递归子模块证明；未证明子模块不能永久视为公共实现。
7. 层次无法唯一匹配、父证明失败或子证明失败时，对当前模块子树局部展开。
8. ModulePair 缓存键是 `(gold_module, gate_module)`，允许模块名不同。
9. 两侧相同类型的显式 black box 可以作为共同假设，但不递归检查其内部。
10. `--validate-oracle` 发现两种算法结论不一致时必须独立报错，不能静默选择一侧。
11. Pass 但非组合证明闭合（回退通过）的模块对必须产生英文 Warning；Warning 不
    改变结论和退出码，判断仍以顶层 `equivalent` 为准。

## 6. 开发流程

进入仓库后先在根目录加载环境（首次运行会自动用 `uv sync` 创建 `.venv` 并以
editable 模式安装本工具）：

```bash
source EnvSetup.sh
```

修改前：

1. 确认改动属于 CLI、Oracle、层次算法、测试还是文档。
2. 阅读对应源码和已有 fixture。
3. 对算法改动，先确定应通过和应失败的可观察行为。

修改后至少运行：

```bash
make test
python3 -m compileall -q src tests
python3 -m yosys_hier_equiv --help
```

如果环境中没有 Yosys，单元测试会被跳过。这不能作为有效验证；交付时必须明确
说明测试没有真实执行。

## 7. 测试规则

- 修复 bug 或修改算法时，优先增加最小手写 RTL fixture。
- 目录名使用 `pass_<scenario>` 或 `fail_<scenario>` 表达预期。
- 每个场景至少包含 `gold.v` 和 `gate.v`；两侧共用定义放入 `common.v`。
- 等价场景必须由 Oracle 和层次化实现都判定 Pass。
- 不等价场景必须由两者都判定 Fail。
- 回退、缓存、Warning 或报告相关改动还需要检查 `PairResult.method`、
  `PairResult.warnings`、模块对数量或 `report.json`，不能只看进程退出码。
- 新测试应证明一个明确语义，不要用大型生成 RTL 替代最小复现。

## 8. 编码与文档规则

- Python 保持无第三方运行时依赖，除非有明确收益并同步更新安装说明。
- 使用 `pathlib.Path` 和结构化 JSON，不用临时字符串解析替代现有数据模型。
- 生成的 Yosys 脚本和日志是公共调试接口；修改文件布局时同步更新文档和测试。
- README 只保留项目入口和快速开始；详细内容放入 `docs/`。
- 文档必须区分当前支持、已知限制和未来计划。
- 本仓库目前不使用 Sphinx。新增 Markdown 后应检查相对链接，而不是依赖外部
  文档构建系统。

## 9. 已知限制

- CLI 只支持 Gold/Gate 共用一个顶层模块名。
- 不同实例名之间没有结构签名匹配，直接触发局部展开。
- 每个模块对重新读取源码并启动 Yosys，性能开销较大。
- `memory` 和 `equiv_simple -seq N` 对大型 memory、复杂状态机并不完备。
- 尚未用真实大型设计建立正确性和性能回归。
- black box 依赖用户提供正确且一致的接口定义。

## 10. 后续工作优先级

默认优先级：

1. 选择一个真实大型设计，建立 Oracle 与 `hier-check` 的时间、内存和结果基线。
2. 针对真实失败补最小 fixture，不直接围绕大型样例反复修改算法。
3. 评估模块对批处理或长期驻留 Yosys，减少重复读取源码的成本。
4. 再考虑不同实例名的保守结构签名匹配和多对多层次映射。
5. 扩充时序证明策略前，先定义其完备性边界和回归 Oracle。

## 11. 交付要求

每次交付至少说明：

- 修改基于哪个分支
- 修改了哪些算法或用户接口
- 实际运行了哪些测试
- 哪些结论来自测试，哪些仍是推断
- 是否改变了已知限制或后续优先级
