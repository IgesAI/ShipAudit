import type { ReactNode } from "react";

export function formatInline(text: string): ReactNode {
  const parts = text.split(/(`[^`]+`|\*\*[^*]+\*\*)/g);
  return parts.map((part, i) => {
    if (part.startsWith("`") && part.endsWith("`")) {
      return <code key={i}>{part.slice(1, -1)}</code>;
    }
    if (part.startsWith("**") && part.endsWith("**")) {
      return (
        <strong key={i} className="text-foreground">
          {part.slice(2, -2)}
        </strong>
      );
    }
    return part;
  });
}

export function renderSimpleMarkdown(content: string) {
  const lines = content.trim().split("\n");
  const elements: ReactNode[] = [];
  let i = 0;
  let key = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (line.startsWith("```")) {
      const codeLines: string[] = [];
      i++;
      while (i < lines.length && !lines[i].startsWith("```")) {
        codeLines.push(lines[i]);
        i++;
      }
      i++;
      elements.push(
        <pre key={key++}>
          <code>{codeLines.join("\n")}</code>
        </pre>,
      );
      continue;
    }

    if (line.startsWith("|")) {
      const tableLines: string[] = [];
      while (i < lines.length && lines[i].startsWith("|")) {
        tableLines.push(lines[i]);
        i++;
      }
      const rows = tableLines.filter((r) => !r.includes("---"));
      const [header, ...body] = rows;
      const headers = header.split("|").filter(Boolean).map((c) => c.trim());
      elements.push(
        <table key={key++}>
          <thead>
            <tr>
              {headers.map((h) => (
                <th key={h}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {body.map((row, ri) => {
              const cells = row.split("|").filter(Boolean).map((c) => c.trim());
              return (
                <tr key={ri}>
                  {cells.map((cell, ci) => (
                    <td key={ci}>{formatInline(cell.replace(/\\`/g, "`"))}</td>
                  ))}
                </tr>
              );
            })}
          </tbody>
        </table>,
      );
      continue;
    }

    if (line.startsWith("## ")) {
      elements.push(<h3 key={key++}>{line.slice(3)}</h3>);
      i++;
      continue;
    }

    if (line.startsWith("### ")) {
      elements.push(<h4 key={key++}>{line.slice(4)}</h4>);
      i++;
      continue;
    }

    if (line.startsWith("> ")) {
      elements.push(
        <blockquote
          key={key++}
          className="my-4 border-l-2 border-primary/50 pl-4 italic text-foreground/90"
        >
          {line.slice(2)}
        </blockquote>,
      );
      i++;
      continue;
    }

    if (line.startsWith("- ")) {
      const items: string[] = [];
      while (i < lines.length && lines[i].startsWith("- ")) {
        items.push(lines[i].slice(2));
        i++;
      }
      elements.push(
        <ul key={key++}>
          {items.map((item, idx) => (
            <li key={idx}>{formatInline(item)}</li>
          ))}
        </ul>,
      );
      continue;
    }

    if (/^\d+\.\s/.test(line)) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i])) {
        items.push(lines[i].replace(/^\d+\.\s/, ""));
        i++;
      }
      elements.push(
        <ol key={key++}>
          {items.map((item, idx) => (
            <li key={idx}>{formatInline(item)}</li>
          ))}
        </ol>,
      );
      continue;
    }

    if (line.trim() === "") {
      i++;
      continue;
    }

    elements.push(<p key={key++}>{formatInline(line)}</p>);
    i++;
  }

  return elements;
}
