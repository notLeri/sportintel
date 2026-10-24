import { useTranslation } from "react-i18next";

import { Button, Checkbox, Label, Popover, PopoverContent, PopoverTrigger } from "@/shared/ui";

import { useListSearchParam } from "./useListSearchParam";

export interface Option {
  value: string;
  label: string;
}

export function MultiSelectFilter({
  name,
  label,
  options,
}: {
  name: string;
  label: string;
  options: Option[];
}) {
  const { t } = useTranslation();
  const [values, setValues] = useListSearchParam(name);
  const toggle = (v: string) =>
    setValues(values.includes(v) ? values.filter((x) => x !== v) : [...values, v]);
  return (
    <Popover>
      <PopoverTrigger asChild>
        <Button variant="outline" size="sm" aria-label={label}>
          {label}
          {values.length ? ` (${values.length})` : ""}
        </Button>
      </PopoverTrigger>
      <PopoverContent className="w-64">
        <fieldset className="space-y-2">
          <legend className="sr-only">{label}</legend>
          {options.map((o) => {
            const id = `${name}-${o.value}`;
            return (
              <div key={o.value} className="flex items-center gap-2">
                <Checkbox
                  id={id}
                  checked={values.includes(o.value)}
                  onCheckedChange={() => toggle(o.value)}
                />
                <Label htmlFor={id}>{o.label}</Label>
              </div>
            );
          })}
          {values.length ? (
            <Button variant="ghost" size="sm" onClick={() => setValues([])}>
              {t("filters.clear")}
            </Button>
          ) : null}
        </fieldset>
      </PopoverContent>
    </Popover>
  );
}
