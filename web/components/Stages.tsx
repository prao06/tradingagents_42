import { Stage } from "@/lib/api";

// Render the agent pipeline as grouped, collapsible stages with persona framing.
export default function Stages({ stages }: { stages: Stage[] }) {
  const groups: { name: string; items: Stage[] }[] = [];
  for (const s of stages) {
    const last = groups[groups.length - 1];
    if (!last || last.name !== s.group) groups.push({ name: s.group, items: [s] });
    else last.items.push(s);
  }

  return (
    <>
      {groups.map((g) => (
        <div key={g.name}>
          <h2>{g.name}</h2>
          {g.items.map((s) => (
            <details key={s.label} className="stage card" open={g.name === "Analysts"}>
              <summary>
                <span>
                  {s.icon} {s.label}
                </span>
              </summary>
              <div className="persona">{s.persona}</div>
              <div className="body">{s.content || "(no output recorded)"}</div>
            </details>
          ))}
        </div>
      ))}
    </>
  );
}
