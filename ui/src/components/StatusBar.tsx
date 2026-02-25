import type { SessionStatus } from "../hooks/useSessionStatus";

interface Props {
  status: SessionStatus | null;
}

function shortenPath(cwd: string): string {
  const home = "/Users/";
  const idx = cwd.indexOf("/", home.length);
  if (idx > 0 && cwd.startsWith(home)) {
    return "~" + cwd.slice(idx);
  }
  return cwd;
}

export function StatusBar({ status }: Props) {
  if (!status) return null;

  const { cwd, job, git } = status;
  const isAgent = /claude/i.test(job);

  return (
    <div className="status-bar">
      {cwd && (
        <div className="status-bar-row status-bar-cwd" title={cwd}>
          {shortenPath(cwd)}
        </div>
      )}
      {git && (
        <div className="status-bar-row status-bar-git">
          <span className="status-bar-branch">⎇ {git.branch}</span>
          {git.dirty > 0 && (
            <span className="status-bar-dirty">
              <span className="status-bar-dot" />
              {git.dirty} dirty
            </span>
          )}
          {git.ahead > 0 && (
            <span className="status-bar-ahead">↑{git.ahead}</span>
          )}
          {git.behind > 0 && (
            <span className="status-bar-behind">↓{git.behind}</span>
          )}
        </div>
      )}
      {job && (
        <div className="status-bar-row status-bar-job">
          <span className={`status-bar-job-dot${isAgent ? " agent" : ""}`} />
          {job}
          {isAgent && (
            <span className="status-bar-working">working</span>
          )}
        </div>
      )}
    </div>
  );
}
