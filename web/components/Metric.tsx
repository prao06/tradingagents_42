export default function Metric({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "green" | "red";
}) {
  return (
    <div className="card metric">
      <div className="label">{label}</div>
      <div className={"value" + (tone ? " " + tone : "")}>{value}</div>
    </div>
  );
}
