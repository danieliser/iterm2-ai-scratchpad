import { useEffect, useRef, useState } from "react";

interface Props {
  code: string;
}

let mermaidPromise: Promise<any> | null = null;
let _renderCount = 0;

function loadMermaid() {
  if (!mermaidPromise) {
    mermaidPromise = import(
      /* @vite-ignore */ "https://cdn.jsdelivr.net/npm/mermaid@10/dist/mermaid.esm.min.mjs"
    ).then((mod) => {
      mod.default.initialize({
        theme: "dark",
        themeVariables: {
          darkMode: true,
          background: "#1e1e1e",
          primaryColor: "#569cd6",
          primaryTextColor: "#d4d4d4",
          lineColor: "#808080",
        },
      });
      return mod;
    });
  }
  return mermaidPromise;
}

export function Mermaid({ code }: Props) {
  const ref = useRef<HTMLDivElement>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    const id = `mermaid-${++_renderCount}`;

    loadMermaid()
      .then((mod) => {
        if (cancelled) return;
        return mod.default.render(id, code);
      })
      .then((result: any) => {
        if (cancelled || !result || !ref.current) return;
        // Mermaid returns SVG as a string; this is safe since it comes
        // from the mermaid renderer, not user input.
        ref.current.textContent = "";
        ref.current.insertAdjacentHTML("afterbegin", result.svg);
      })
      .catch((err: any) => {
        if (!cancelled) setError(String(err));
      });

    return () => {
      cancelled = true;
    };
  }, [code]);

  if (error) {
    return (
      <div className="widget-mermaid">
        <pre style={{ color: "#f44747", fontSize: 10 }}>
          Diagram error: {error}
        </pre>
      </div>
    );
  }

  return (
    <div className="widget-mermaid" ref={ref}>
      <pre style={{ color: "#808080", fontSize: 10 }}>Loading diagram...</pre>
    </div>
  );
}
