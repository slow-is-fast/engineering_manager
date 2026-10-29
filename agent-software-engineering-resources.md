# Agent 软件工程与研发管理知识库：推荐资料清单

> 更新：2026-10-23  
> 用途：供 Claude Code、Codex、Pi 等 Coding Agent 查阅软件项目开发、软件工程实践、项目管理、研发效能和多 Agent 治理相关知识。  
> 范围：仅整理学习资料与检索结构；**不包含实战任务、测试任务或 Skill 实现**。

## 使用说明

- 优先使用官方文档、开放获取的书籍和组织公开手册。
- **阅读资料不等于模型权重训练**：Agent 可以通过上下文和外部检索运用资料，但不会因阅读自动永久更新底层模型。
- 检索时保留原始 URL、标题、版本、查阅日期及适用场景；对于随时间变化的工具文档要复查。
- 优先全文可访问的 HTML 和 Markdown；PDF 应确认获取和使用权限。不要未经许可镜像受版权保护的整本书。
- 将“标准/研究证据”“组织实践”“Agent 具体工作方法”分开，避免把特定公司的做法当成通用原则。

## 一、优先导入的 10 套核心资料

| 优先级 | 资料 | 适合学习的内容 | 官方入口 |
|---|---|---|---|
| P0 | Software Engineering at Google | 长期维护、工程文化、测试、规模化协作 | https://abseil.io/resources/swe-book |
| P0 | GitLab Handbook | 产品与研发协作、工作流、角色、团队运营 | https://handbook.gitlab.com/handbook/ |
| P0 | Google Engineering Practices | Code Review、变更提交规范 | https://google.github.io/eng-practices/ |
| P0 | IEEE SWEBOK | 软件工程完整知识分类框架 | https://www.computer.org/education/bodies-of-knowledge/software-engineering |
| P0 | Google SRE Books | SLI/SLO、可用性、事故响应、可靠性工程 | https://sre.google/books/ |
| P1 | DORA | 软件交付效能、改善策略、度量局限 | https://dora.dev/ |
| P1 | Scrum Guide | Scrum 角色、事件、工件与迭代管理 | https://scrumguides.org/ |
| P1 | Team Topologies | 团队边界、协作模式、认知负荷 | https://teamtopologies.com/key-concepts |
| P1 | Matt Pocock Skills | 面向 Coding Agent 的任务规范、开发/评审工作流 | https://github.com/mattpocock/skills |
| P1 | OWASP GenAI Security | Agent 工具权限、提示注入、AI 应用安全 | https://genai.owasp.org/ |

## 二、按 Agent 能力层级分类

### L1：软件工程师基础

**目标：** 理解需求、架构、实现、验证与长期可维护性。

| 主题 | 推荐资料 | URL |
|---|---|---|
| 软件工程原理 | SWEBOK | https://www.computer.org/education/bodies-of-knowledge/software-engineering |
| 规模化软件工程 | Software Engineering at Google | https://abseil.io/resources/swe-book/html/toc |
| 需求与产品工作流 | GitLab Product Handbook | https://handbook.gitlab.com/handbook/product/ |
| 架构可视化 | C4 Model | https://c4model.com/ |
| 架构文档 | arc42 | https://arc42.org/ |
| 决策记录 | ADR | https://adr.github.io/ |
| 代码审查 | Google Engineering Practices | https://google.github.io/eng-practices/review/ |
| 测试原则 | Martin Fowler — Testing | https://martinfowler.com/testing/ |
| 软件构造课程 | MIT 6.005 Software Construction | https://ocw.mit.edu/courses/6-005-software-construction-spring-2016/ |

**关键知识：** 软件生命周期、验收条件、内聚与耦合、决策权衡、测试层次、代码健康。

### L2：软件项目管理

**目标：** 理解需求如何被拆解、排期、跟踪和交付。

| 主题 | 推荐资料 | URL |
|---|---|---|
| Scrum | Scrum Guide | https://scrumguides.org/ |
| Kanban | Kanban Guides | https://kanbanguides.org/ |
| Issue/里程碑与协作 | GitLab Handbook | https://handbook.gitlab.com/handbook/ |
| 敏捷方法与估算 | Atlassian Agile | https://www.atlassian.com/agile |
| 软件工程管理 | SWEBOK | https://www.computer.org/education/bodies-of-knowledge/software-engineering |
| 研发与产品职责 | GitLab Engineering / Product Handbooks | https://handbook.gitlab.com/handbook/engineering/ |

**关键知识：** Backlog、DoR/DoD、任务依赖、风险、交付预测、变更管理、干系人沟通。

### L3：技术负责人和工程质量管理

**目标：** 在单项编码之外判断整个项目的质量、可靠性与交付能力。

| 主题 | 推荐资料 | URL |
|---|---|---|
| 工程标准 | Software Engineering at Google | https://abseil.io/resources/swe-book |
| 持续交付 | Continuous Delivery | https://continuousdelivery.com/ |
| 分支与集成策略 | Trunk Based Development | https://trunkbaseddevelopment.com/ |
| SRE 与运维 | Google SRE Books | https://sre.google/books/ |
| 软件交付度量 | DORA | https://dora.dev/ |
| 开发者生产力 | SPACE 论文，Microsoft Research | https://www.microsoft.com/en-us/research/publication/the-space-of-developer-productivity-theres-more-to-it-than-you-think/ |
| CI/CD 实现参考 | GitHub Actions Docs | https://docs.github.com/en/actions |

**关键知识：** 质量门禁、Review、持续集成、部署风险、SLO、事故复盘、DORA 与 SPACE 的局限。

### L4：研发经理及组织管理

**目标：** 辅助项目统筹、技术协调、组织结构分析；不自动做人员绩效和重大组织决策。

| 主题 | 推荐资料 | URL |
|---|---|---|
| 工程管理运营 | GitLab Engineering Handbook | https://handbook.gitlab.com/handbook/engineering/ |
| 人员与组织制度 | GitLab People Group Handbook | https://handbook.gitlab.com/handbook/people-group/ |
| 团队拓扑 | Team Topologies | https://teamtopologies.com/key-concepts |
| 技术趋势与评估 | Thoughtworks Technology Radar | https://www.thoughtworks.com/radar |
| 组织中的工程文化 | Software Engineering at Google | https://abseil.io/resources/swe-book |
| 技术领导力文章 | LeadDev | https://leaddev.com/ |

**关键知识：** 团队边界、依赖管理、沟通与授权、管理节奏、技术路线图、投资与风险。

### L5：AI Agent 工作流与治理

**目标：** 让不同 Agent 在明确的工程规则、权限和审核制度下协作。

| 主题 | 推荐资料 | URL |
|---|---|---|
| Agent 工作方法与 Skills | Matt Pocock Skills | https://github.com/mattpocock/skills |
| Software Factory 概念设计 | Matt Pocock PR #1316 | https://github.com/mattpocock/skills/pull/1316 |
| Claude Code 官方指南 | Claude Code Docs | https://code.claude.com/docs/en/overview |
| Codex 官方指南 | OpenAI Codex Docs | https://developers.openai.com/codex/ |
| Agent 安全 | OWASP GenAI Security | https://genai.owasp.org/ |
| 隔离开发工作区 | Git Worktree | https://git-scm.com/docs/git-worktree.html |
| 代码合并管控 | GitHub Branch Protection | https://docs.github.com/en/repositories/configuring-branches-and-merges-in-your-repository/managing-protected-branches/about-protected-branches |
| Pi Agent | Pi Docs | https://pi.dev/ |

**关键知识：** Task/Run/Trigger、独立上下文、权限、可观测性、重试、Review、人工审批、Agent 间责任边界。

**注意：** Software Factory PR 是设计讨论/方法资料，不应视为已经提供完整可运行的自动研发管理系统。对于第三方 Skills，也要核实更新日期、依赖和适配的运行环境。

## 三、可选高级补充

| 资料 | 重点 | URL |
|---|---|---|
| NASA Systems Engineering Handbook | 系统工程、需求追踪、验证与风险 | https://www.nasa.gov/reference/systems-engineering-handbook/ |
| OWASP Software Security | 安全工程资料 | https://owasp.org/ |
| Google SRE Workbook | SRE 实施细则 | https://sre.google/workbook/table-of-contents/ |
| Diátaxis | 技术文档类型与组织原则 | https://diataxis.fr/ |
| The Good Docs Project | 文档模板和技术写作 | https://www.thegooddocsproject.dev/ |

## 四、推荐的资料导入顺序

1. **工程基础：** SWEBOK → Software Engineering at Google → Google Engineering Practices。
2. **项目管理：** Scrum Guide → Kanban Guides → GitLab Handbook。
3. **工程治理：** Google SRE → DORA → SPACE → Team Topologies。
4. **Agent 专项：** Matt Pocock Skills → Software Factory PR → Claude Code/Codex 文档 → OWASP GenAI Security。

不需要强迫 Agent 一次读完全部资料。更有效的方式是保留一个可检索知识源，根据当前任务读取相关章节，回答时附带来源。

## 五、推荐的知识库分类

```text
software-engineering-knowledge/
├── 00-foundations/
│   ├── swebok/
│   └── software-engineering-at-google/
├── 01-requirements-and-design/
│   ├── requirements/
│   ├── architecture/
│   └── technical-decisions/
├── 02-project-management/
│   ├── scrum/
│   ├── kanban/
│   ├── estimation/
│   └── risk-management/
├── 03-engineering-practices/
│   ├── coding-standards/
│   ├── testing/
│   ├── code-review/
│   └── continuous-delivery/
├── 04-engineering-effectiveness/
│   ├── dora/
│   ├── sre/
│   └── developer-productivity/
├── 05-engineering-management/
│   ├── team-topologies/
│   ├── gitlab-handbook/
│   └── technology-strategy/
├── 06-agent-engineering/
│   ├── mattpocock-skills/
│   ├── software-factory/
│   ├── claude-code/
│   ├── codex/
│   └── agent-security/
└── index.md
```

## 六、文档元数据建议

对每个外部知识源保存以下信息，方便 Agent 判断时效与可信度：

```yaml
title: Software Engineering at Google
source_url: https://abseil.io/resources/swe-book
source_type: official_book
knowledge_areas:
  - software-engineering
  - testing
  - maintenance
access: free_online
language: en
retrieved_at: 2026-10-23
version: check_source
notes: 参考来源；不要把书中的所有建议自动升级为项目强制规则
```

**采纳原则：** 原文是证据，知识笔记是解释，工程规范是经过审核的决策。不要把 Agent 自动总结的内容不经审核就写入全局规则。

---

## 七、长期阅读的书籍（补充，不保证免费全文）

- *The Mythical Man-Month* — Frederick Brooks：工期、沟通成本、软件项目复杂性。
- *The Manager's Path* — Camille Fournier：Tech Lead 到研发管理者的成长路径。
- *Accelerate* — Nicole Forsgren、Jez Humble、Gene Kim：软件交付效能。
- *An Elegant Puzzle* — Will Larson：工程组织与管理系统。
- *Team Topologies* — Matthew Skelton、Manuel Pais：团队交互与架构边界。
- *Continuous Delivery* — Jez Humble、David Farley：构建、测试、部署、发布。
- *Peopleware* — Tom DeMarco、Timothy Lister：人的因素与团队生产力。

这些书主要用于延伸理解；自动化摄取时需遵守著作权与授权条件。
