import { DuckLogo } from "./DuckLogo";

interface Props {
  label?: string;
}

export function DuckLoader({ label = "quack-quack" }: Props) {
  return (
    <div className="duck-loader">
      <DuckLogo width={72} height={72} className="duck-levitate" />
      <p>{label}</p>
    </div>
  );
}
