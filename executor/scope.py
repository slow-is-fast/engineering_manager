# -*- coding: utf-8 -*-
"""executor.scope —— 项目/租户数据边界守卫（ISO-01）。

规则（v1.1.1 §4 记忆生命周期与项目数据隔离 / AUD-016）：
- Run 必须绑定 project_id / repository_id / tenant_id；
- **默认拒绝**跨项目、跨租户访问并告警；
- 未分类数据按**最高敏感级别**处理（不因为"没标"就放宽）。

守卫语义：
  1. 未绑定的 Run 不得访问任何数据（fail closed）；
  2. 访问目标的 project/tenant 必须与 Run 绑定值完全一致；
  3. 通配范围（"*"）不得用于跨项目访问——越权常见手法；
  4. 数据未分类 → 按最高敏感级别处理，且不得跨项目；
  5. 每次拒绝都写审计事件（boundary_violation），可告警、可复现。

诚实边界：本模块是**进程内的边界判定**；真正的隔离还要靠存储层权限、
独立租户存储与网络策略（AUD-016 的完整范围）。不得据本模块宣称"已实现租户隔离"。
"""
from .audit import AuditLog

# 敏感级别：数值越大越敏感；未分类按最高处理
SENSITIVITY = {"public": 0, "internal": 1, "confidential": 2, "restricted": 3}
MAX_SENSITIVITY = "restricted"


class Denied(Exception):
    pass


class ScopeGuard:
    def __init__(self, audit_path):
        self.audit = AuditLog(audit_path)
        self.runs = {}

    def bind(self, run_id, project_id, repository_id, tenant_id):
        self.runs[run_id] = {"run_id": run_id, "project_id": project_id,
                             "repository_id": repository_id,
                             "tenant_id": tenant_id}
        self.audit.append("run.bound", run_id=run_id, project_id=project_id,
                          tenant_id=tenant_id)
        return self.runs[run_id]

    def _deny(self, run_id, reason, **extra):
        self.audit.append("boundary_violation", run_id=run_id, reason=reason,
                          **extra)
        raise Denied(f"{reason}: {extra}")

    def access(self, run_id, artifact, data_class=None):
        """artifact: {project_id, repository_id, tenant_id, path}"""
        binding = self.runs.get(run_id)
        if binding is None:
            self._deny(run_id, "unbound_run")

        for field in ("project_id", "tenant_id"):
            want = artifact.get(field)
            if want is None:
                self._deny(run_id, "artifact_missing_scope", field=field)
            if want == "*":
                self._deny(run_id, "wildcard_scope_denied", field=field)
            if want != binding[field]:
                self._deny(run_id, "cross_boundary_denied", field=field,
                           run_value=binding[field], requested=want)

        # 仓库可不绑定（同一项目多仓库场景），但若提供则必须一致
        repo = artifact.get("repository_id")
        if repo not in (None, binding["repository_id"]):
            self._deny(run_id, "cross_repository_denied",
                       run_value=binding["repository_id"], requested=repo)

        # 未分类数据按最高敏感级别处理
        cls = data_class or MAX_SENSITIVITY
        if data_class is None:
            self.audit.append("data.unclassified_defaults_to_max", run_id=run_id,
                              path=artifact.get("path"))
        if SENSITIVITY.get(cls, 3) >= SENSITIVITY["confidential"]:
            self.audit.append("access.sensitive", run_id=run_id,
                              data_class=cls, path=artifact.get("path"))

        self.audit.append("access.allowed", run_id=run_id,
                          project_id=binding["project_id"],
                          path=artifact.get("path"), data_class=cls)
        return "ALLOWED"
