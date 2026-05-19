"""Diff two ComponentSnapshots and produce a human-readable delta."""

from __future__ import annotations

from dataclasses import dataclass

from .store import ComponentSnapshot


@dataclass
class SnapshotDiff:
    component_id: str
    added_classes: list[str]
    removed_classes: list[str]
    added_functions: list[str]
    removed_functions: list[str]
    added_ports: list[str]
    removed_ports: list[str]
    todo_delta: int  # positive = more TODOs

    @property
    def is_empty(self) -> bool:
        return not (
            self.added_classes
            or self.removed_classes
            or self.added_functions
            or self.removed_functions
            or self.added_ports
            or self.removed_ports
            or self.todo_delta != 0
        )

    def to_markdown_lines(self) -> list[str]:
        lines = [f"### `{self.component_id}`"]
        if self.added_classes:
            lines.append(f"- **New classes:** {', '.join(f'`{c}`' for c in self.added_classes)}")
        if self.removed_classes:
            lines.append(f"- **Removed classes:** {', '.join(f'`{c}`' for c in self.removed_classes)}")
        if self.added_functions:
            lines.append(f"- **New functions:** {', '.join(f'`{f}`' for f in self.added_functions)}")
        if self.removed_functions:
            lines.append(f"- **Removed functions:** {', '.join(f'`{f}`' for f in self.removed_functions)}")
        if self.added_ports:
            lines.append(f"- **New ports:** {', '.join(f'`{p}`' for p in self.added_ports)}")
        if self.removed_ports:
            lines.append(f"- **Removed ports:** {', '.join(f'`{p}`' for p in self.removed_ports)}")
        if self.todo_delta > 0:
            lines.append(f"- **TODOs added:** +{self.todo_delta}")
        elif self.todo_delta < 0:
            lines.append(f"- **TODOs resolved:** {self.todo_delta}")
        return lines


def diff_snapshots(old: ComponentSnapshot | None, new: ComponentSnapshot) -> SnapshotDiff:
    if old is None:
        return SnapshotDiff(
            component_id=new.component_id,
            added_classes=new.class_names,
            removed_classes=[],
            added_functions=new.function_names,
            removed_functions=[],
            added_ports=new.port_names,
            removed_ports=[],
            todo_delta=new.todo_count,
        )

    old_classes = set(old.class_names)
    new_classes = set(new.class_names)
    old_fns = set(old.function_names)
    new_fns = set(new.function_names)
    old_ports = set(old.port_names)
    new_ports = set(new.port_names)

    return SnapshotDiff(
        component_id=new.component_id,
        added_classes=sorted(new_classes - old_classes),
        removed_classes=sorted(old_classes - new_classes),
        added_functions=sorted(new_fns - old_fns),
        removed_functions=sorted(old_fns - new_fns),
        added_ports=sorted(new_ports - old_ports),
        removed_ports=sorted(old_ports - new_ports),
        todo_delta=new.todo_count - old.todo_count,
    )
