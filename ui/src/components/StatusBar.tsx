import type { SessionStatus, PanelStatus } from "../hooks/useSessionStatus";
import { activateSession } from "../lib/api";

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

function PanelRow({ panel, compact }: { panel: PanelStatus; compact: boolean }) {
  const { cwd, job, git } = panel;
  const isAgent = /claude/i.test(job);

  if (compact) {
    return (
      <button
        className="status-bar-panel-row"
        onClick={() => activateSession(panel.session_id)}
        title={`Switch to: ${cwd}`}
      >
        <span className={`status-bar-job-dot${isAgent ? " agent" : ""}`} />
        <span className="status-bar-panel-cwd">{shortenPath(cwd)}</span>
        {git && (
          <span className="status-bar-panel-branch">⎇ {git.branch}</span>
        )}
        {git && git.dirty > 0 && (
          <span className="status-bar-dirty">●{git.dirty}</span>
        )}
        <span className="status-bar-panel-job">{job}</span>
      </button>
    );
  }

  // Full single-panel view
  return (
    <>
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
          {isAgent && <span className="status-bar-working">working</span>}
        </div>
      )}
    </>
  );
}

export function StatusBar({ status }: Props) {
  if (!status || status.panels.length === 0) return null;

  // Unified: all panels in same cwd — show single full view using first panel's data
  if (status.unified) {
    return (
      <div className="status-bar">
        <PanelRow panel={status.panels[0]} compact={false} />
      </div>
    );
  }

  // Multi-panel: different cwds — compact stacked rows with jump links
  return (
    <div className="status-bar status-bar-multi">
      {status.panels.map((panel) => (
        <PanelRow key={panel.session_id} panel={panel} compact />
      ))}
    </div>
  );
}
