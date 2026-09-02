# 文档入口

目标读者：工具使用者、开发者和接手项目的 agent。

文档类型：导航。

当前状态：与 `main` 分支当前实现同步。

`yosys-hier-equiv` 的文档按“入口、使用、架构、测试、开发”分层。代码和测试仍是
具体行为的最终权威来源；本文档负责帮助读者选择正确入口。

## 我只想运行一次等价检查

从 [使用指南](usage.md) 开始。它说明：

- 如何准备 Gold、Gate 和公共源码
- `flatten-oracle` 与 `hier-check` 应该如何选择
- 所有 CLI 参数、退出码和工作目录产物
- 如何从 `report.json` 和 Yosys 日志定位失败

第一次使用建议先在仓库根目录 `source EnvSetup.sh` 加载环境，然后运行：

```bash
yosys-hier-equiv hier-check \
  --gold gold.v \
  --gate gate.v \
  --top top \
  --validate-oracle \
  --work-dir build/first-check
```

## 我需要理解工具为什么可信

阅读 [架构与算法](architecture.md)。它定义：

- 工具所说的“等价”是什么
- 完整展开 Oracle 的职责
- JSON inventory 和 ModulePair 如何产生
- 共同 stub、递归证明与局部展开如何闭合
- black box、时序深度和 memory 的能力边界

## 我要增加或修改测试

阅读 [测试指南](testing.md)。它列出当前 17 个手写场景，以及新增 fixture、更新
断言和验证回退行为的方法。

## 我要继续开发算法或 CLI

先读 [开发指南](development.md)，再进入对应源码。该文档包含代码地图、调用链、
开发检查清单、调试方式和当前优先级。

接手项目的 agent 还必须先读根目录 [AGENTS.md](../AGENTS.md)。

## 文档职责

| 文件 | 主要读者 | 负责内容 |
| --- | --- | --- |
| `README.md` | 新用户 | 项目定位、环境、快速开始、能力边界 |
| `AGENTS.md` | Agent | 阅读顺序、稳定约束、验证和交付要求 |
| `docs/index.md` | 所有人 | 文档导航和任务入口 |
| `docs/usage.md` | 使用者 | 完整命令、输入、产物和故障分析 |
| `docs/architecture.md` | 开发者 | 等价语义、算法和正确性边界 |
| `docs/testing.md` | 开发者 | 当前测试矩阵和新增测试方法 |
| `docs/development.md` | 开发者 | 代码入口、开发流程和后续路线 |

## 当前能力摘要

当前已经实现并由手写测试验证：

- 完整展开 Gold/Gate 后进行等价检查
- 基于相同实例名发现层次模块对
- 参数派生模块名和不同模块名之间的递归证明
- 父模块共同 stub 抽象
- 两侧相同类型 black box 的共同假设
- ModulePair 缓存
- 实例集合变化、父证明失败和子证明失败时的局部展开
- 回退通过时的 Warning 报告
- 层次化结果与 Oracle 对照

当前尚未验证：

- 真实大型设计的时间和内存开销
- 不同实例名之间不依赖展开的自动匹配
- 大型 memory 和复杂时序设计的完备证明
- 长期驻留 Yosys 或多模块对批处理的性能收益
