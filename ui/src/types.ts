export interface Note {
  id: string;
  text: string;
  source: string;
  timestamp: string;
}

export interface TodoItem {
  content: string;
  status: "pending" | "in_progress" | "completed";
  activeForm?: string;
  id?: string;
}

export interface TodoSession {
  file: string;
  session_id: string;
  summary?: string;
  items: TodoItem[];
  has_active: boolean;
  mtime: number;
}

export interface TaskItem {
  id: string;
  subject: string;
  description?: string;
  activeForm?: string;
  status: "pending" | "in_progress" | "completed";
  blocks?: string[];
  blockedBy?: string[];
}

export interface TaskTeam {
  team: string;
  summary?: string;
  tasks: TaskItem[];
  mtime: number;
}

export interface TodosResponse {
  sessions: TodoSession[];
  teams: TaskTeam[];
}

export interface ExecResult {
  status: "completed" | "timeout" | "started";
  exit_code?: number;
  output?: string;
  pid?: number;
  error?: string;
}
