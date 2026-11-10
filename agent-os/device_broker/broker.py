"""Device Broker facade — permission, policy, tools, audit."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Callable, Optional

from .audit import AuditLog, new_operation_id
from .paths import PathJailError, resolve_in_roots
from .permissions import PHASE3_MAX_GRANTABLE, PermissionLevel, level_allowed
from .policy import BrokerPolicy
from .tools.registry import ToolRegistry, build_default_registry
from .types import AuditStatus, CallContext, ToolResult


class DeviceBroker:
    def __init__(
        self,
        policy: BrokerPolicy,
        *,
        audit: AuditLog | None = None,
        project_resolver: Callable[[], Optional[dict[str, Any]]] | None = None,
    ):
        self.policy = policy
        self.policy.ensure_base_dirs()
        audit_path = self.policy.work_root / "broker_audit.db"
        self.audit = audit or AuditLog(audit_path)
        self._project_resolver = project_resolver
        self._extra_read_roots: list[Path] = list(policy.extra_roots)
        self._forced_project_id: Optional[str] = None
        self.registry: ToolRegistry = build_default_registry(self)

    def close(self) -> None:
        self.audit.close()

    def set_project_resolver(self, fn: Callable[[], Optional[dict[str, Any]]]) -> None:
        self._project_resolver = fn

    def add_extra_root(self, path: Path | str) -> None:
        self._extra_read_roots.append(Path(path).expanduser().resolve())

    def current_project(self) -> Optional[dict[str, Any]]:
        if self._project_resolver:
            try:
                return self._project_resolver()
            except Exception:
                return None
        return None

    def current_project_id(self) -> Optional[str]:
        if self._forced_project_id:
            return self._forced_project_id
        proj = self.current_project()
        return proj["id"] if proj else None

    def approved_roots(self, *, write: bool = False) -> list[Path]:
        """
        Resolve filesystem roots for the current call.

        Write roots: active project workspace (+ explicit extra roots if writable).
        Read roots: project workspace, project tree, global/, extra roots.
        """
        roots: list[Path] = []
        proj = self.current_project()
        if proj:
            ws = Path(proj.get("workspace_path") or "")
            if ws:
                ws.mkdir(parents=True, exist_ok=True)
                roots.append(ws.resolve())
            proj_root = self.policy.projects_root() / proj["id"]
            if proj_root.exists():
                if write:
                    # Phase 4: allow engineering artifacts/reports under the active project
                    for sub in ("artifacts", "reports"):
                        d = proj_root / sub
                        d.mkdir(parents=True, exist_ok=True)
                        roots.append(d.resolve())
                else:
                    roots.append(proj_root.resolve())

        global_root = self.policy.global_root()
        global_root.mkdir(parents=True, exist_ok=True)
        if write:
            # Global is writable for controlled shared assets when no project — or always as secondary root
            roots.append(global_root.resolve())
        else:
            roots.append(global_root.resolve())

        for r in self._extra_read_roots:
            rp = Path(r).resolve()
            if rp not in roots:
                roots.append(rp)

        # Deduplicate while preserving order
        seen: set[str] = set()
        out: list[Path] = []
        for r in roots:
            key = str(r)
            if key not in seen:
                seen.add(key)
                out.append(r)
        return out

    def list_tools(self) -> list[dict[str, Any]]:
        return self.registry.mcp_list()

    def invoke(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        ctx: CallContext | None = None,
    ) -> ToolResult:
        ctx = ctx or CallContext()
        args = dict(arguments or {})
        op_id = new_operation_id()
        project_id = ctx.project_id or self.current_project_id()
        self._forced_project_id = project_id

        self.audit.record(
            operation_id=op_id,
            status=AuditStatus.REQUESTED,
            principal=ctx.principal,
            client=ctx.client,
            tool=tool_name,
            level="?",
            args=args,
            project_id=project_id,
            approval_id=ctx.approval_id,
        )

        spec = self.registry.get(tool_name)
        if spec is None:
            # Explicit denial for dangerous reserved names
            denied = self._deny(
                op_id, ctx, tool_name, "L3", args, project_id,
                f"unknown or unregistered tool: {tool_name}",
            )
            return denied

        required = spec.level
        try:
            max_level = PermissionLevel.parse(ctx.max_level)
        except ValueError:
            max_level = PermissionLevel.L0

        # Cap claimed max_level at Phase 3 ceiling
        if max_level > PHASE3_MAX_GRANTABLE:
            max_level = PHASE3_MAX_GRANTABLE

        if not level_allowed(required, max_level):
            return self._deny(
                op_id, ctx, tool_name, required.label(), args, project_id,
                f"permission denied: {tool_name} requires {required.label()}, "
                f"caller max_level={max_level.label()} (Phase 3 ceiling {PHASE3_MAX_GRANTABLE.label()})",
            )

        self.audit.record(
            operation_id=op_id,
            status=AuditStatus.VALIDATED,
            principal=ctx.principal,
            client=ctx.client,
            tool=tool_name,
            level=required.label(),
            args=args,
            project_id=project_id,
            approval_id=ctx.approval_id,
        )
        self.audit.record(
            operation_id=op_id,
            status=AuditStatus.EXECUTING,
            principal=ctx.principal,
            client=ctx.client,
            tool=tool_name,
            level=required.label(),
            args=args,
            project_id=project_id,
        )

        started = time.monotonic()
        try:
            data = spec.handler(**args)
            duration_ms = (time.monotonic() - started) * 1000.0
            self.audit.record(
                operation_id=op_id,
                status=AuditStatus.COMPLETED,
                principal=ctx.principal,
                client=ctx.client,
                tool=tool_name,
                level=required.label(),
                args=args,
                project_id=project_id,
                result={"ok": True, "keys": list(data.keys()) if isinstance(data, dict) else []},
                duration_ms=duration_ms,
            )
            speech = self._speech_ok(tool_name, data)
            return ToolResult(
                ok=True,
                tool=tool_name,
                status="completed",
                level=required.label(),
                data=data if isinstance(data, dict) else {"value": data},
                operation_id=op_id,
                project_id=project_id,
                speech=speech,
            )
        except (PathJailError, PermissionError, FileExistsError, ValueError, FileNotFoundError, TimeoutError) as exc:
            duration_ms = (time.monotonic() - started) * 1000.0
            msg = str(exc)
            is_deny = isinstance(exc, (PathJailError, PermissionError))
            self.audit.record(
                operation_id=op_id,
                status=AuditStatus.DENIED if is_deny else AuditStatus.FAILED,
                principal=ctx.principal,
                client=ctx.client,
                tool=tool_name,
                level=required.label(),
                args=args,
                project_id=project_id,
                error=msg,
                duration_ms=duration_ms,
            )
            status = "denied" if is_deny else "failed"
            return ToolResult(
                ok=False,
                tool=tool_name,
                status=status,
                level=required.label(),
                error=msg,
                operation_id=op_id,
                project_id=project_id,
                speech=f"Device Broker {status}: {msg}",
            )
        except Exception as exc:  # noqa: BLE001
            duration_ms = (time.monotonic() - started) * 1000.0
            msg = f"{type(exc).__name__}: {exc}"
            self.audit.record(
                operation_id=op_id,
                status=AuditStatus.FAILED,
                principal=ctx.principal,
                client=ctx.client,
                tool=tool_name,
                level=required.label(),
                args=args,
                project_id=project_id,
                error=msg,
                duration_ms=duration_ms,
            )
            return ToolResult(
                ok=False,
                tool=tool_name,
                status="failed",
                level=required.label(),
                error=msg,
                operation_id=op_id,
                project_id=project_id,
                speech=f"Device Broker failed: {msg}",
            )
        finally:
            self._forced_project_id = None

    def _deny(
        self,
        op_id: str,
        ctx: CallContext,
        tool_name: str,
        level: str,
        args: dict,
        project_id: Optional[str],
        message: str,
    ) -> ToolResult:
        self.audit.record(
            operation_id=op_id,
            status=AuditStatus.DENIED,
            principal=ctx.principal,
            client=ctx.client,
            tool=tool_name,
            level=level,
            args=args,
            project_id=project_id,
            error=message,
            approval_id=ctx.approval_id,
        )
        return ToolResult(
            ok=False,
            tool=tool_name,
            status="denied",
            level=level,
            error=message,
            operation_id=op_id,
            project_id=project_id,
            speech=f"Denied: {message}",
        )

    def _speech_ok(self, tool_name: str, data: Any) -> str:
        if tool_name == "list_directory" and isinstance(data, dict):
            return f"Listed {data.get('count', 0)} entries in {data.get('path')}."
        if tool_name == "read_text_file" and isinstance(data, dict):
            return f"Read {data.get('bytes_read', 0)} bytes from {data.get('path')}."
        if tool_name == "create_directory" and isinstance(data, dict):
            return f"Created directory {data.get('path')}."
        if tool_name == "write_text_file" and isinstance(data, dict):
            return f"Wrote {data.get('bytes_written', 0)} bytes to {data.get('path')}."
        if tool_name == "get_system_info" and isinstance(data, dict):
            return f"Host OS: {data.get('system')} {data.get('release')} ({data.get('machine')})."
        if tool_name == "get_available_toolchains" and isinstance(data, dict):
            return f"Found {len(data.get('found') or [])} toolchain binaries on PATH."
        if tool_name == "run_allowed_command" and isinstance(data, dict):
            return f"Command exited {data.get('exit_code')} in {data.get('duration_ms')} ms."
        return f"Tool {tool_name} completed."

    def _run_command_impl(
        self,
        argv: list[str],
        *,
        cwd: str | None,
        level_override: str | None = None,
    ) -> dict[str, Any]:
        # Block obvious privilege escalation / shell wrappers
        blocked = {"sudo", "su", "doas", "bash", "sh", "zsh", "fish", "dash", "env", "xargs"}
        if not argv:
            raise ValueError("empty argv")
        if Path(argv[0]).name in blocked:
            raise PermissionError(f"command not permitted: {argv[0]}")

        spec = self.policy.match_command(argv)
        if spec is None:
            raise PermissionError(
                f"command not on allowlist: {argv!r}. "
                "Device Broker does not provide an unrestricted shell."
            )

        required = PermissionLevel.parse(level_override or spec.level)
        if required > PHASE3_MAX_GRANTABLE:
            raise PermissionError(f"command level {required.label()} not granted in Phase 3")

        workdir: Optional[Path] = None
        if cwd:
            roots = self.approved_roots(write=False)
            workdir = resolve_in_roots(cwd, roots, must_exist=True)
            if not workdir.is_dir():
                raise PathJailError(f"cwd is not a directory: {cwd}")
        else:
            # Prefer active workspace
            roots = self.approved_roots(write=False)
            workdir = roots[0] if roots else self.policy.work_root

        exe = argv[0]
        resolved = shutil.which(exe) if "/" not in exe else exe
        if not resolved or not Path(resolved).exists():
            raise FileNotFoundError(f"executable not found: {exe}")
        # Re-bind argv[0] to absolute path to avoid PATH tricks after check
        final_argv = [resolved, *argv[1:]]

        started = time.monotonic()
        try:
            proc = subprocess.run(
                final_argv,
                cwd=str(workdir),
                capture_output=True,
                timeout=self.policy.command_timeout_s,
                check=False,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise TimeoutError(
                f"command timed out after {self.policy.command_timeout_s}s: {argv}"
            ) from exc

        duration_ms = round((time.monotonic() - started) * 1000.0, 2)
        out_limit = self.policy.max_command_output_bytes
        stdout = proc.stdout[:out_limit]
        stderr = proc.stderr[:out_limit]
        return {
            "argv": argv,
            "resolved_argv": final_argv,
            "cwd": str(workdir),
            "exit_code": proc.returncode,
            "duration_ms": duration_ms,
            "stdout": stdout.decode("utf-8", errors="replace"),
            "stderr": stderr.decode("utf-8", errors="replace"),
            "stdout_truncated": len(proc.stdout) > out_limit,
            "stderr_truncated": len(proc.stderr) > out_limit,
            "allowlist": spec.name,
            "level": required.label(),
        }
