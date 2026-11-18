import type { ReactNode } from "react";

/**
 * The small subset of Markdown the agent writes: paragraphs, bullet and
 * numbered lists, headings, **bold** and `code`. Builds React elements, never
 * HTML strings, so model output cannot inject markup.
 */
function inline(text: string): ReactNode[] {
  return text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).map((part, i) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) return <strong key={i}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`") && part.length > 2)
      return <code key={i} className="bg-board px-1 text-[0.95em]">{part.slice(1, -1)}</code>;
    return part;
  });
}

const BULLET = /^\s*[-*•]\s+/;
const NUMBERED = /^\s*\d+[.)]\s+/;

export default function Markdown({ text }: { text: string }) {
  const blocks: ReactNode[] = [];
  const lines = text.replace(/\r\n/g, "\n").split("\n");
  let i = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i++;
      continue;
    }
    if (BULLET.test(line) || NUMBERED.test(line)) {
      const ordered = NUMBERED.test(line);
      const pattern = ordered ? NUMBERED : BULLET;
      const items: string[] = [];
      while (i < lines.length && pattern.test(lines[i])) items.push(lines[i++].replace(pattern, ""));
      const List = ordered ? "ol" : "ul";
      blocks.push(
        <List key={i} className={`my-2 flex flex-col gap-1 pl-6 ${ordered ? "list-decimal" : "list-disc"}`}>
          {items.map((item, j) => <li key={j}>{inline(item)}</li>)}
        </List>,
      );
      continue;
    }
    const heading = line.match(/^#{1,4}\s+(.*)$/);
    if (heading) {
      blocks.push(<p key={i} className="mt-3 font-semibold">{inline(heading[1])}</p>);
      i++;
      continue;
    }
    const para: string[] = [];
    while (i < lines.length && lines[i].trim() && !BULLET.test(lines[i]) && !NUMBERED.test(lines[i]) && !/^#{1,4}\s/.test(lines[i]))
      para.push(lines[i++]);
    blocks.push(<p key={i} className="my-2">{inline(para.join(" "))}</p>);
  }
  return <div className="leading-relaxed">{blocks}</div>;
}
