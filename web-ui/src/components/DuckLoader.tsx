import { DuckLogo } from "./DuckLogo";

interface Props {
  label?: string;
}

export function DuckLoader({ label = "ducking…" }: Props) {
  return (
    <div className="duck-loader">
      <DuckLogo width={72} height={72} className="duck-levitate" />
      <p>{label}</p>
    </div>
  );
}
