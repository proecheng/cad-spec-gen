# SolidWorks 集成方案已合并

> 状态: 已迁移
> 日期: 2026-04-28

SolidWorks 集成不再单独维护执行方案。原本文档中的材质库、Toolbox、COM 导出、模型决策通道、用户交互和数据一致性内容，已合并到 [`../PARTS_LIBRARY.md`](../PARTS_LIBRARY.md)。

后续实现、审查和验收只以 `docs/PARTS_LIBRARY.md` 为准，避免模型库与 SolidWorks 子方案出现数据、函数、路径或术语漂移。

历史引用到本文或旧类名、旧 adapter key 的 `docs/superpowers/` 规格文档只表示当时的设计来源；新工作请改看 `docs/PARTS_LIBRARY.md` 的以下章节：

- `文档定位`
- `Overview`
- `Architecture`
- `Mapping rule vocabulary`
- `Target contract: geometry decisions`
- `SolidWorks integration`
- `Implementation milestones`
- `Required tests`
