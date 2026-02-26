import type { ReactNode } from "react";
import {
  ProgressBar,
  Badge,
  Chart,
  Details,
  Timer,
  Diff,
  Todo,
  KeyValue,
  Log,
  LinkCard,
  FileTree,
  Metric,
  Clipboard,
  Deadline,
  PortMonitor,
  Mermaid,
  RunCommand,
} from "../components/widgets";
import DOMPurify from "dompurify";
import { escapeHtml } from "./format";

/**
 * Parse note text containing markdown + widget bracket syntax into React elements.
 *
 * Strategy: We process the raw text in two passes:
 *   1. Extract widgets (bracket syntax) and replace with placeholders
 *   2. Convert remaining markdown to HTML, then inject widget components
 *
 * This keeps widget content safe from markdown processing.
 */

let _widgetSeq = 0;

function nextPlaceholder(): string {
  return `\x00W${_widgetSeq++}\x00`;
}

function extractWidgets(
  raw: string,
): { text: string; widgets: Map<string, ReactNode> } {
  const widgets = new Map<string, ReactNode>();

  // Protect code blocks and inline code from widget parsing
  const codeSlots = new Map<string, string>();
  let codeSeq = 0;
  raw = raw.replace(/```[\s\S]*?```|`[^`]+`/g, (m) => {
    const ph = `\x01C${++codeSeq}\x01`;
    codeSlots.set(ph, m);
    return ph;
  });

  function replace(
    pattern: RegExp,
    fn: (...args: string[]) => ReactNode,
  ): void {
    raw = raw.replace(pattern, (...args) => {
      const ph = nextPlaceholder();
      widgets.set(ph, fn(...args));
      return ph;
    });
  }

  // Progress bars: [progress:75] or [progress:75:Building...]
  replace(
    /\[progress:(\d+)(?::([^\]]*))?]/g,
    (_, val, label) => (
      <ProgressBar value={parseInt(val)} label={label || undefined} />
    ),
  );

  // Status badges: [status:success] or [status:error:Deploy failed]
  replace(
    /\[status:(success|warning|error|info)(?::([^\]]*))?]/g,
    (_, type, label) => (
      <Badge type={type as "success" | "warning" | "error" | "info"} label={label || undefined} />
    ),
  );

  // Sparkline charts: [chart:10,45,30,80,60] or [chart:10,45,30:Requests/s]
  replace(
    /\[chart:([\d,]+)(?::([^\]]*))?]/g,
    (_, data, label) => (
      <Chart values={data.split(",").map(Number)} label={label || undefined} />
    ),
  );

  // Collapsible details: [details:Title]content[/details]
  replace(
    /\[details:([^\]]+)]([\s\S]*?)\[\/details]/g,
    (_, title, body) => (
      <Details title={title}>
        <span dangerouslySetInnerHTML={{ __html: DOMPurify.sanitize(renderInlineMarkdown(body.trim())) }} />
      </Details>
    ),
  );

  // Timers: [timer:5m:Label]
  replace(
    /\[timer:([^:\]]+)(?::([^\]]*))?]/g,
    (_, dur, label) => <Timer duration={dur} label={label || undefined} />,
  );

  // Diff blocks: [diff]...[/diff]
  replace(
    /\[diff]([\s\S]*?)\[\/diff]/g,
    (_, content) => <Diff content={content} />,
  );

  // Todo checklists: [todo]...[/todo]
  replace(
    /\[todo]([\s\S]*?)\[\/todo]/g,
    (_, content) => <Todo content={content} />,
  );

  // Key-value: [kv]...[/kv]
  replace(
    /\[kv]([\s\S]*?)\[\/kv]/g,
    (_, content) => <KeyValue content={content} />,
  );

  // Log blocks: [log:level]...[/log]
  replace(
    /\[log:(error|warn|info|debug)]([\s\S]*?)\[\/log]/g,
    (_, level, content) => <Log level={level as "error" | "warn" | "info" | "debug"} content={content} />,
  );

  // Link cards: [link:Label:https://...]
  replace(
    /\[link:([^:]+):([^\]]*?)]/g,
    (_, label, url) => <LinkCard label={label} url={url} />,
  );

  // File trees: [tree]...[/tree]
  replace(
    /\[tree]([\s\S]*?)\[\/tree]/g,
    (_, content) => <FileTree content={content} />,
  );

  // Metric cards: [metric:42ms:Latency:down]
  replace(
    /\[metric:([^:]+):([^:]+)(?::(up|down|flat))?]/g,
    (_, value, label, trend) => (
      <Metric value={value} label={label} trend={(trend || "flat") as "up" | "down" | "flat"} />
    ),
  );

  // Clipboard: [clip:label]content[/clip]
  replace(
    /\[clip:([^\]]+)]([\s\S]*?)\[\/clip]/g,
    (_, label, content) => <Clipboard label={label} content={content.trim()} />,
  );

  // Deadline: [deadline:2026-02-23T17:00:00:Sprint ends]
  replace(
    /\[deadline:([^:\]]+)(?::([^\]]*))?]/g,
    (_, iso, label) => <Deadline target={iso} label={label || undefined} />,
  );

  // Port monitor: [ports:3000,5432,9999]
  replace(
    /\[ports:([\d,]+)]/g,
    (_, portList) => (
      <PortMonitor ports={portList.split(",").map(Number)} />
    ),
  );

  // Mermaid diagrams: [mermaid]...[/mermaid]
  replace(
    /\[mermaid]([\s\S]*?)\[\/mermaid]/g,
    (_, code) => <Mermaid code={code.trim()} />,
  );

  // Run widget: [run:label]command[/run]
  replace(
    /\[run(?::([^\]]+))?]([\s\S]*?)\[\/run]/g,
    (_, label, cmd) => (
      <RunCommand command={cmd.trim()} label={label || undefined} />
    ),
  );

  // Restore protected code blocks in the main text
  for (const [ph, code] of codeSlots) {
    raw = raw.replace(ph, code);
  }

  // Also restore code placeholders inside widget content that was captured
  // before restoration (block widgets like [todo], [kv], [diff], etc.)
  for (const [key, node] of widgets) {
    if (node && typeof node === "object" && "props" in node) {
      const props = (node as React.ReactElement).props as Record<string, unknown>;
      const content = props.content as string | undefined;
      if (content) {
        let restored = content;
        for (const [ph, code] of codeSlots) {
          restored = restored.replaceAll(ph, code);
        }
        if (restored !== content) {
          // Clone the element with restored content
          const el = node as React.ReactElement;
          widgets.set(key, { ...el, props: { ...props, content: restored } });
        }
      }
    }
  }

  return { text: raw, widgets };
}

/** Render inline markdown (bold, italic, code) to HTML string */
function renderInlineMarkdown(s: string): string {
  s = escapeHtml(s);
  s = s.replace(/```([\s\S]*?)```/g, (_, code) => `<pre>${code.trim()}</pre>`);
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  s = s.replace(/\*(.+?)\*/g, "<em>$1</em>");
  return s;
}

/** Full markdown to HTML string (for text portions between widgets) */
function renderMarkdownToHtml(s: string): string {
  s = escapeHtml(s);
  // Code blocks
  s = s.replace(/```([\s\S]*?)```/g, (_, code) => `<pre>${code.trim()}</pre>`);
  // Inline code
  s = s.replace(/`([^`]+)`/g, "<code>$1</code>");
  // Bold
  s = s.replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>");
  // Italic
  s = s.replace(/\*(.+?)\*/g, "<em>$1</em>");
  // H3
  s = s.replace(/^### (.+)$/gm, "<h3>$1</h3>");
  // HR
  s = s.replace(/^---$/gm, "<hr>");
  // Unordered lists
  s = s.replace(/^- (.+)$/gm, "<li>$1</li>");
  s = s.replace(/(<li>.*<\/li>\n?)+/g, (m) => `<ul>${m}</ul>`);
  // Markdown tables
  s = s.replace(/(^\|.+\|$\n?)+/gm, (block) => {
    const rows = block.trim().split("\n").filter((r) => r.trim());
    if (rows.length < 2) return block;
    const sep = rows[1];
    if (!/^\|[\s\-:|]+\|$/.test(sep)) return block;
    const parseRow = (r: string) =>
      r.split("|").slice(1, -1).map((c) => c.trim());
    const headers = parseRow(rows[0]);
    let html =
      '<table class="widget-table"><thead><tr>' +
      headers.map((h) => `<th>${h}</th>`).join("") +
      "</tr></thead><tbody>";
    for (let i = 2; i < rows.length; i++) {
      const cells = parseRow(rows[i]);
      html += "<tr>" + cells.map((c) => `<td>${c}</td>`).join("") + "</tr>";
    }
    return html + "</tbody></table>";
  });
  // Paragraphs
  s = s.replace(/\n\n/g, "</p><p>");
  s = `<p>${s}</p>`;
  // Line breaks (not inside block elements)
  s = s.replace(/([^>])\n([^<])/g, "$1<br>$2");
  // Clean empty paragraphs
  s = s.replace(/<p>\s*<\/p>/g, "");
  return s;
}

/**
 * Parse a note's raw text into an array of React elements.
 * Widgets become React components, markdown becomes HTML spans.
 * Uses position-based keys to avoid stale widget state issues.
 */
export function parseNoteContent(raw: string): ReactNode[] {
  const { text, widgets } = extractWidgets(raw);

  if (widgets.size === 0) {
    return [
      <span
        key="0"
        dangerouslySetInnerHTML={{ __html: renderMarkdownToHtml(text) }}
      />,
    ];
  }

  // Split text by widget placeholders and interleave
  const parts: ReactNode[] = [];
  const regex = /\x00W\d+\x00/g;
  let lastIndex = 0;
  let match: RegExpExecArray | null;
  let partIndex = 0;

  while ((match = regex.exec(text)) !== null) {
    const before = text.slice(lastIndex, match.index);
    if (before) {
      parts.push(
        <span
          key={partIndex++}
          dangerouslySetInnerHTML={{ __html: renderMarkdownToHtml(before) }}
        />,
      );
    }
    const widget = widgets.get(match[0]);
    if (widget) {
      parts.push(<span key={partIndex++}>{widget}</span>);
    }
    lastIndex = match.index + match[0].length;
  }

  const trailing = text.slice(lastIndex);
  if (trailing) {
    parts.push(
      <span
        key={partIndex++}
        dangerouslySetInnerHTML={{ __html: renderMarkdownToHtml(trailing) }}
      />,
    );
  }

  return parts;
}
