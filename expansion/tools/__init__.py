"""Policy-gated tool gateway — agents execute only after PolicyEngine authorizes."""
from __future__ import annotations

import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

from expansion.persist import read_json, update_json
from expansion.policy import PolicyEngine
from expansion.state_layout import StateLayout, resolve_layout


@dataclass
class ToolResult:
    ok: bool
    capability: str
    agent_id: str
    summary: str
    data: dict = field(default_factory=dict)
    error: str = ''
    action_id: str = ''
    disposition: str = 'authorize'
    at: float = 0.0

    def __post_init__(self):
        if not self.at:
            self.at = time.time()
        if not self.action_id:
            self.action_id = f'tool_{uuid.uuid4().hex[:10]}'


def _audit_path(layout: StateLayout):
    layout.user_jobs.mkdir(parents=True, exist_ok=True)
    return layout.user_jobs / 'tool_audit.json'


class ToolGateway:
    """Single entry: check policy → execute → audit."""

    def __init__(self, layout: Optional[StateLayout] = None):
        self.layout = layout or resolve_layout()
        self.policy = PolicyEngine(self.layout)

    def _record(self, result: ToolResult) -> None:
        def _mut(data):
            data = data or {'schema_version': 1, 'actions': []}
            actions = list(data.get('actions') or [])
            actions.append(asdict(result))
            data['actions'] = actions[-500:]
            return data

        update_json(_audit_path(self.layout), _mut, default={'schema_version': 1, 'actions': []})

    def recent(self, *, limit: int = 40) -> list:
        raw = read_json(_audit_path(self.layout), default={'actions': []})
        actions = list(raw.get('actions') or [])
        return actions[-limit:]

    def invoke(self, agent_id: str, capability: str, **kwargs: Any) -> ToolResult:
        decision = self.policy.check(agent_id, capability)
        if not decision.allowed:
            result = ToolResult(
                ok=False,
                capability=capability,
                agent_id=agent_id,
                summary=decision.reason,
                error=decision.reason,
                disposition=decision.disposition,
            )
            self._record(result)
            return result

        try:
            data, summary = self._dispatch(capability, agent_id=agent_id, **kwargs)
            data = data or {}
            ok = True
            # Normalize executor truthfulness: non-zero exit / passed=False is failure.
            if isinstance(data.get('exit_code'), int) and data['exit_code'] != 0:
                ok = False
            if data.get('passed') is False or data.get('ok') is False:
                ok = False
            if data.get('success') is False:
                ok = False
            result = ToolResult(
                ok=ok,
                capability=capability,
                agent_id=agent_id,
                summary=summary if ok else (data.get('error') or summary or f'{capability} failed'),
                data=data,
                error='' if ok else str(
                    data.get('error')
                    or data.get('stderr')
                    or f'{capability} reported failure'
                )[:500],
                disposition='authorize',
            )
        except Exception as exc:  # noqa: BLE001 — tool boundary
            result = ToolResult(
                ok=False,
                capability=capability,
                agent_id=agent_id,
                summary=f'{capability} failed',
                error=str(exc)[:500],
                disposition='authorize',
            )
        self._record(result)
        return result

    def _dispatch(self, capability: str, *, agent_id: str, **kwargs) -> tuple[dict, str]:
        if capability in ('web.search',):
            from expansion.tools.web import web_search
            return web_search(kwargs.get('query') or kwargs.get('q') or '')
        if capability in ('web.fetch',):
            from expansion.tools.web import web_fetch
            return web_fetch(kwargs.get('url') or '')
        if capability in ('docs.search', 'repo.search'):
            from expansion.tools.repo import repo_search
            return repo_search(
                kwargs.get('query') or kwargs.get('q') or '',
                root=kwargs.get('root'),
                layout=self.layout,
            )
        if capability == 'github.read':
            from expansion.tools.web import github_read
            return github_read(kwargs.get('url') or kwargs.get('path') or '')
        if capability == 'repo.read':
            from expansion.tools.repo import repo_read
            return repo_read(kwargs.get('path') or '', root=kwargs.get('root'), layout=self.layout)
        if capability == 'repo.write':
            from expansion.tools.repo import repo_write
            return repo_write(
                kwargs.get('path') or '',
                kwargs.get('content') or '',
                root=kwargs.get('root'),
                layout=self.layout,
            )
        if capability in ('files.read',):
            from expansion.tools.repo import repo_read
            return repo_read(kwargs.get('path') or '', root=kwargs.get('root'), layout=self.layout)
        if capability in ('files.write',):
            from expansion.tools.repo import repo_write
            return repo_write(
                kwargs.get('path') or '',
                kwargs.get('content') or '',
                root=kwargs.get('root'),
                layout=self.layout,
            )
        if capability == 'shell.execute':
            from expansion.tools.shell import shell_execute
            return shell_execute(kwargs.get('command') or kwargs.get('cmd') or '')
        if capability == 'tests.run':
            from expansion.tools.shell import run_tests
            return run_tests(kwargs.get('args') or '', layout=self.layout)
        if capability in ('git.branch', 'git.commit'):
            from expansion.tools.shell import git_op
            return git_op(capability, kwargs)
        if capability in ('docker.inspect', 'docker.manage'):
            from expansion.tools.docker_tools import docker_op
            return docker_op(capability, kwargs)
        if capability in ('services.inspect', 'services.restart'):
            from expansion.tools.services import service_op
            return service_op(capability, kwargs)
        if capability == 'logs.read':
            from expansion.tools.shell import read_logs
            return read_logs(kwargs.get('path') or kwargs.get('unit') or '')
        if capability == 'security.scan':
            from expansion.tools.security_tools import security_scan
            return security_scan(layout=self.layout, **kwargs)
        if capability == 'research.record':
            return {
                'recorded': True,
                'title': kwargs.get('title') or '',
                'url': kwargs.get('url') or '',
                'snippet': (kwargs.get('snippet') or '')[:400],
            }, 'research recorded'
        if capability == 'journal.write':
            from expansion.journal import JournalStore, new_journal_entry
            summary = (kwargs.get('summary') or kwargs.get('text') or kwargs.get('content') or '').strip()
            if not summary:
                raise ValueError('journal.write requires summary/text')
            event_ids = tuple(kwargs.get('evidence_ids') or kwargs.get('event_ids') or ())
            job_id = kwargs.get('job_id') or ''
            if not event_ids and not job_id:
                # Tool-originated durable write: mint a stable reference id.
                event_ids = (f'tool_{uuid.uuid4().hex[:12]}',)
            entry = JournalStore(self.layout).append(new_journal_entry(
                agent_id=agent_id,
                event_type=kwargs.get('event_type') or 'tool.journal.write',
                summary=summary[:500],
                objective_result=kwargs.get('result') or 'recorded',
                actor=agent_id,
                event_ids=event_ids,
                job_id=job_id,
                evidence_ids=tuple(kwargs.get('evidence_ids') or ()),
            ))
            return {
                'written': True,
                'entry_id': entry.entry_id,
                'agent_id': agent_id,
                'event_ids': list(entry.event_ids),
            }, f'journal entry {entry.entry_id} written'
        if capability in ('docs.update', 'continuity.update'):
            # Not yet implemented as durable writers — do not pretend success.
            raise ValueError(
                f'{capability} is not implemented as a durable write yet'
            )
        raise ValueError(f'no executor for capability {capability!r}')
