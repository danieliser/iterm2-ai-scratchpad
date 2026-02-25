import { useState } from "react";

interface Props {
  content: string;
}

interface TodoItem {
  text: string;
  done: boolean;
}

function parseItems(content: string): TodoItem[] {
  return content
    .trim()
    .split("\n")
    .filter((l) => l.trim())
    .map((line) => {
      const done = /^\[x\]/i.test(line);
      const text = done ? line.slice(3).trim() : line.trim();
      return { text, done };
    });
}

export function Todo({ content }: Props) {
  const [items, setItems] = useState(() => parseItems(content));

  const toggle = (idx: number) => {
    setItems((prev) =>
      prev.map((item, i) =>
        i === idx ? { ...item, done: !item.done } : item,
      ),
    );
  };

  const handleKeyDown = (idx: number, e: React.KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      toggle(idx);
    }
  };

  return (
    <div className="widget-todo">
      {items.map((item, i) => (
        <div
          key={i}
          className={`widget-todo-item${item.done ? " done" : ""}`}
          onClick={() => toggle(i)}
          onKeyDown={(e) => handleKeyDown(i, e)}
          role="checkbox"
          aria-checked={item.done}
          tabIndex={0}
        >
          <span className="widget-todo-check">
            {item.done ? "\u2713" : ""}
          </span>
          <span className="widget-todo-text">{item.text}</span>
        </div>
      ))}
    </div>
  );
}
