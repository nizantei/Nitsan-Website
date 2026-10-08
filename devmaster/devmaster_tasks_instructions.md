# devmaster_tasks.json — Field Reference

## Structure
The file has two top-level keys:

### milestones (array)
Each milestone groups related tasks together:
- **id** (string): Unique identifier (any string, e.g. "m1")
- **title** (string): Milestone name (e.g. "MVP", "V2")
- **description** (string): What this milestone covers
- **targetDate** (string): Optional target date (YYYY-MM-DD)
- **status**: One of: completed | in-progress | planned
- **tasks** (array): List of tasks in this milestone

### Task fields (within milestones or currentTasks)
- **id** (string): Unique within the file
- **title** (string): What needs to be done
- **status**: One of: done | in-progress | todo
- **category**: One of: feature | bugfix | refactor | devops | design | testing | docs
- **priority**: One of: critical | high | medium | low

### currentTasks (array)
Quick standalone tasks not tied to any milestone. Same fields as tasks above.

## Tips
- Use milestones for phases of work
- Use currentTasks for quick one-off items
- Task IDs just need to be unique within the file
