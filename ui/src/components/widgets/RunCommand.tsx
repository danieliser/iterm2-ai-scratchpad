import { useState } from "react";
import { execCommand } from "../../lib/api";

interface Props {
  command: string;
  label?: string;
}

export function RunCommand({ command, label }: Props) {
  const [output, setOutput] = useState<string | null>(null);
  const [outputClass, setOutputClass] = useState("");
  const [running, setRunning] = useState(false);

  const run = async (bg: boolean) => {
    if (bg) {
      try {
        const data = await execCommand(command, true);
        setOutput(`Started in background (PID ${data.pid})`);
        setOutputClass("success");
      } catch (err: any) {
        setOutput(`Failed: ${err.message}`);
        setOutputClass("error");
      }
      return;
    }

    setRunning(true);
    setOutput(null);
    try {
      const data = await execCommand(command, false);
      if (data.status === "completed") {
        setOutputClass(data.exit_code === 0 ? "success" : "error");
        let text = data.output || "(no output)";
        if (data.exit_code !== 0) text += `\nExit code: ${data.exit_code}`;
        setOutput(text);
      } else if (data.status === "timeout") {
        setOutputClass("error");
        setOutput(data.error || "Command timed out");
      } else {
        setOutputClass("error");
        setOutput(`Unexpected: ${JSON.stringify(data)}`);
      }
    } catch (err: any) {
      setOutputClass("error");
      setOutput(`Failed: ${err.message}`);
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="widget-run">
      <div className="widget-run-header">
        <span className="widget-run-prompt">{label || "$"}</span>
        <span className="widget-run-cmd">{command}</span>
        <button
          className="widget-run-btn"
          disabled={running}
          onClick={() => run(false)}
        >
          &#9654; Run
        </button>
        <button
          className="widget-run-btn bg"
          disabled={running}
          onClick={() => run(true)}
        >
          BG
        </button>
      </div>
      {(output !== null || running) && (
        <div className={`widget-run-output ${outputClass}`}>
          {running ? (
            <>
              <span className="widget-run-spinner" /> Running...
            </>
          ) : (
            output
          )}
        </div>
      )}
    </div>
  );
}
