import { useEffect, useRef, useState } from "react";
import DOMPurify from "dompurify";

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
          background: "var(--bg-base)",
          primaryColor: "var(--accent-blue)",
          primaryTextColor: "var(--text-primary)",
          lineColor: "var(--text-muted)",
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
        ref.current.insertAdjacentHTML("afterbegin", DOMPurify.sanitize(result.svg, { USE_PROFILES: { svg: true } }));
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
        <pre style={{ color: "var(--accent-red)", fontSize: 10 }}>
          Diagram error: {error}
        </pre>
      </div>
    );
  }

  return (
    <div className="widget-mermaid" ref={ref}>
      <pre style={{ color: "var(--text-muted)", fontSize: 10 }}>Loading diagram...</pre>
    </div>
  );
}
