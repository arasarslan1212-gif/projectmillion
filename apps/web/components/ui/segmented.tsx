"use client";

import { Button } from "./button";

export function Segmented<T extends string>({
  value,
  options,
  onChange,
  label,
}: {
  value: T;
  options: { value: T; label: string }[];
  onChange: (v: T) => void;
  label: string;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex rounded-lg bg-surface-2 p-0.5">
      {options.map((o) => (
        <Button
          key={o.value}
          variant="segment"
          active={value === o.value}
          onClick={() => onChange(o.value)}
          className="min-h-7 rounded-md px-2.5"
        >
          {o.label}
        </Button>
      ))}
    </div>
  );
}
