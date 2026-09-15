"""Reporting-hierarchy validation for Otacon Expansion agents.

Agents form a directed graph via Agent.reporting_to. This module keeps that
graph a valid hierarchy: no cycles, and no agent left pointing at a deleted
parent.
"""
from __future__ import annotations


class HierarchyError(ValueError):
    pass


def find_cycle(agents_by_id: dict) -> list:
    """agents_by_id: {agent_id: reporting_to_or_None}.
    Returns the cycle as a list of agent_ids if one exists, else None.
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {aid: WHITE for aid in agents_by_id}
    path = []

    def visit(aid):
        color[aid] = GRAY
        path.append(aid)
        parent = agents_by_id.get(aid)
        if parent is not None and parent in agents_by_id:
            if color.get(parent) == GRAY:
                return path[path.index(parent):] + [parent]
            if color.get(parent) == WHITE:
                found = visit(parent)
                if found:
                    return found
        color[aid] = BLACK
        path.pop()
        return None

    for aid in agents_by_id:
        if color[aid] == WHITE:
            found = visit(aid)
            if found:
                return found
    return None


def assert_acyclic(agents_by_id: dict) -> None:
    cycle = find_cycle(agents_by_id)
    if cycle:
        raise HierarchyError(f'reporting hierarchy cycle: {" -> ".join(cycle)}')


def reassign_orphans(agents_by_id: dict, deleted_agent_id: str, fallback_id: str) -> dict:
    """When an agent is deleted, its direct reports must not be left
    pointing at a dead agent_id. Returns a NEW mapping with orphans
    repointed at fallback_id; never mutates the input.
    """
    out = dict(agents_by_id)
    for aid, parent in agents_by_id.items():
        if parent == deleted_agent_id and aid != fallback_id:
            out[aid] = fallback_id
    out.pop(deleted_agent_id, None)
    return out
