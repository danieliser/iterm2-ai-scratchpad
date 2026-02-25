import { useState } from "react";
import type { TodoSession, TaskTeam, TodoItem, TaskItem } from "../types";

interface Props {
  sessions: TodoSession[];
  teams: TaskTeam[];
}

function StatusIcon({ status }: { status: string }) {
  if (status === "in_progress") {
    return <span className="todo-status-icon spinning" title="In progress">&#9881;</span>;
  }
  if (status === "completed") {
    return <span className="todo-status-icon done" title="Done">&#10003;</span>;
  }
  return <span className="todo-status-icon pending" title="Pending">&#9675;</span>;
}

function ProgressSummary({ items }: { items: { status: string }[] }) {
  const total = items.length;
  const completed = items.filter((i) => i.status === "completed").length;
  const inProgress = items.filter((i) => i.status === "in_progress").length;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;

  return (
    <div className="todo-progress">
      <div className="todo-progress-bar">
        <div
          className="todo-progress-fill"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="todo-progress-label">
        {completed}/{total}
        {inProgress > 0 && <span className="todo-active-count"> ({inProgress} active)</span>}
      </span>
    </div>
  );
}

function SessionPanel({ session }: { session: TodoSession }) {
  const [open, setOpen] = useState(session.has_active);
  const label = session.summary || `Session ${session.session_id.slice(0, 8)}`;

  return (
    <div className="todo-panel">
      <button
        className="todo-panel-header"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span className={`todo-panel-arrow${open ? " open" : ""}`}>&#9654;</span>
        <span className="todo-panel-title" title={session.session_id}>{label}</span>
        <ProgressSummary items={session.items} />
      </button>
      {open && (
        <div className="todo-panel-body">
          {session.items.map((item: TodoItem, i: number) => (
            <div
              key={item.id || i}
              className={`todo-item${item.status === "completed" ? " done" : ""}${item.status === "in_progress" ? " active" : ""}`}
            >
              <StatusIcon status={item.status} />
              <span className="todo-item-text">
                {item.status === "in_progress" && item.activeForm
                  ? item.activeForm
                  : item.content}
              </span>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function TeamPanel({ team }: { team: TaskTeam }) {
  const [open, setOpen] = useState(
    team.tasks.some((t) => t.status === "in_progress" || t.status === "pending"),
  );
  const label = team.summary || `Team ${team.team.slice(0, 8)}`;

  return (
    <div className="todo-panel">
      <button
        className="todo-panel-header"
        onClick={() => setOpen(!open)}
        aria-expanded={open}
      >
        <span className={`todo-panel-arrow${open ? " open" : ""}`}>&#9654;</span>
        <span className="todo-panel-title" title={team.team}>{label}</span>
        <ProgressSummary items={team.tasks} />
      </button>
      {open && (
        <div className="todo-panel-body">
          {team.tasks.map((task: TaskItem) => (
            <div
              key={task.id}
              className={`todo-item${task.status === "completed" ? " done" : ""}${task.status === "in_progress" ? " active" : ""}`}
            >
              <StatusIcon status={task.status} />
              <span className="todo-item-text">
                {task.status === "in_progress" && task.activeForm
                  ? task.activeForm
                  : task.subject}
              </span>
              {task.status !== "completed" && task.blockedBy && task.blockedBy.length > 0 && (
                <span className="todo-blocked" title={`Blocked by: ${task.blockedBy.join(", ")}`}>
                  &#128274;
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function TodoBoard({ sessions, teams }: Props) {
  // Filter to only show sessions/teams with activity
  const activeSessions = sessions.filter((s) => s.items.length > 0);
  const activeTeams = teams.filter((t) => t.tasks.length > 0);

  if (activeSessions.length === 0 && activeTeams.length === 0) {
    return null;
  }

  return (
    <div className="todo-board">
      <div className="todo-board-header">
        <span className="todo-board-title">Tasks</span>
      </div>
      {activeTeams.map((team) => (
        <TeamPanel key={team.team} team={team} />
      ))}
      {activeSessions.map((session) => (
        <SessionPanel key={session.file} session={session} />
      ))}
    </div>
  );
}
