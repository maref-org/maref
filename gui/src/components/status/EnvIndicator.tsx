import { Monitor, Cloud, Terminal } from "lucide-react";

export function EnvIndicator() {
  return (
    <span className="flex items-center gap-1">
      <Monitor className="h-3 w-3 text-maref-success" />
      Local
    </span>
  );
}

export function CloudEnvIndicator() {
  return (
    <span className="flex items-center gap-1">
      <Cloud className="h-3 w-3 text-maref-info" />
      Cloud
    </span>
  );
}

export function SSHEnvIndicator() {
  return (
    <span className="flex items-center gap-1">
      <Terminal className="h-3 w-3 text-maref-warning" />
      SSH
    </span>
  );
}