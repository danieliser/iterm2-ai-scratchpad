interface Props {
  connected: boolean;
  onClear: () => void;
}

export function Header({ connected, onClear }: Props) {
  return (
    <div className="header">
      <h1>AI Scratchpad</h1>
      <span className={`status${connected ? "" : " disconnected"}`}>
        {connected ? "live" : "disconnected"}
      </span>
      <button className="btn" onClick={onClear}>
        Clear All
      </button>
    </div>
  );
}
