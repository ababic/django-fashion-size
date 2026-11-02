import { useCallback } from "react";

import { bundlesFor } from "./bundles";
import { SizeValueField } from "./SizeValueField";

/**
 * Controlled size field for a ``build_size_value_config`` payload.
 *
 * ``onChange`` receives the stored token and the entry that produced it.
 * ``unit`` overrides ``config.initialUnit`` when the host switches units.
 * ``selection`` is ``autocomplete`` or ``select`` (a dropdown of the same
 * values). ``unavailable`` lists stored tokens that stay visible with an
 * `` (n/a)`` suffix and cannot be chosen.
 */
export function SizeValueControl({
  config,
  value = "",
  unit,
  disabled = false,
  showChartLink,
  selection,
  unavailable,
  onChange,
}) {
  const unitSlug = unit || config?.initialUnit || "";
  const selected = config?.units?.[unitSlug];
  const chartLink = showChartLink ?? config?.showChartLink !== false;
  const report = useCallback(
    (token, entry) => {
      onChange?.(token ?? "", {
        text: entry?.text ?? "",
        format: entry?.format ?? "",
        unit: unitSlug,
      });
    },
    [onChange, unitSlug]
  );
  if (!selected) {
    return null;
  }
  const customValues = Array.isArray(config.customValues) ? config.customValues : [];
  return (
    <SizeValueField
      key={unitSlug}
      measurement={selected.measurement}
      context={selected.context}
      bundles={bundlesFor(selected, config.charts)}
      choices={selected.choices || []}
      storedValue={value ?? ""}
      disabled={Boolean(disabled || config.disabled)}
      ariaLabel={config.label || selected.measurement.label}
      customValues={customValues}
      customLabel={config.customLabel || "Custom"}
      showChartLink={chartLink}
      selection={selection || config?.selection || "autocomplete"}
      unavailable={unavailable ?? selected.unavailable ?? config?.unavailable ?? []}
      unavailableSuffix={config?.unavailableSuffix || " (n/a)"}
      unavailableMessage={config?.unavailableMessage || "That size is not available."}
      onChange={report}
    />
  );
}
