import type { ID, TaskStatus, WorkflowTask } from "@/lib/api/types";

type TaskLike = Pick<WorkflowTask, "id" | "depends_on">;

export class InvalidWorkflowError extends Error {
  name = "InvalidWorkflowError";
}

/** Throws if a dependency is missing, a task depends on itself, or the graph has a cycle. */
export function validateDag(tasks: TaskLike[]): void {
  const ids = new Set(tasks.map((t) => t.id));
  if (ids.size !== tasks.length) throw new InvalidWorkflowError("Duplicate task ids");
  for (const task of tasks) {
    for (const dep of task.depends_on) {
      if (!ids.has(dep)) throw new InvalidWorkflowError(`Task ${task.id} depends on unknown task ${dep}`);
    }
  }
  dependencyLevels(tasks); // throws on cycles
}

/**
 * Level 0 = no dependencies; otherwise 1 + the deepest dependency.
 * Tasks on the same level can run at the same time — this is how the UI draws the plan.
 */
export function dependencyLevels(tasks: TaskLike[]): Map<ID, number> {
  const byId = new Map(tasks.map((t) => [t.id, t]));
  const levels = new Map<ID, number>();
  const visiting = new Set<ID>();

  const visit = (id: ID): number => {
    const known = levels.get(id);
    if (known !== undefined) return known;
    if (visiting.has(id)) throw new InvalidWorkflowError(`Dependency cycle through task ${id}`);
    visiting.add(id);
    const deps = byId.get(id)?.depends_on ?? [];
    const level = deps.length === 0 ? 0 : 1 + Math.max(...deps.map(visit));
    visiting.delete(id);
    levels.set(id, level);
    return level;
  };

  tasks.forEach((t) => visit(t.id));
  return levels;
}

/** Groups tasks by level, preserving the original order within each level. */
export function groupByLevel<T extends TaskLike>(tasks: T[]): T[][] {
  const levels = dependencyLevels(tasks);
  const groups: T[][] = [];
  for (const task of tasks) {
    const level = levels.get(task.id)!;
    (groups[level] ??= []).push(task);
  }
  return groups;
}

const TERMINAL: ReadonlySet<TaskStatus> = new Set(["completed", "failed", "skipped", "cancelled"]);
const BLOCKING: ReadonlySet<TaskStatus> = new Set(["failed", "skipped", "cancelled"]);

export const isTerminal = (status: TaskStatus) => TERMINAL.has(status);

/** Pending tasks whose dependencies have all completed. */
export function readyTasks(tasks: WorkflowTask[]): WorkflowTask[] {
  const status = new Map(tasks.map((t) => [t.id, t.status]));
  return tasks.filter((t) => t.status === "pending" && t.depends_on.every((d) => status.get(d) === "completed"));
}

/** Pending tasks that can never run because a dependency failed, was skipped or was cancelled. */
export function blockedTasks(tasks: WorkflowTask[]): { task: WorkflowTask; blocker: WorkflowTask }[] {
  const byId = new Map(tasks.map((t) => [t.id, t]));
  return tasks.flatMap((task) => {
    if (task.status !== "pending") return [];
    const blocker = task.depends_on.map((d) => byId.get(d)!).find((d) => BLOCKING.has(d.status));
    return blocker ? [{ task, blocker }] : [];
  });
}
