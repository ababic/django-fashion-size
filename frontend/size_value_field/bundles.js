export function bundlesFor(unit, charts) {
  const chart = unit.chartKey ? charts?.[unit.chartKey] || null : null;
  const bundles = {};
  // Keep the storage format when the select is locked to another region, so a
  // saved token is still recognised and is not treated as a custom value.
  const names = new Set(unit.measurement.formats.map((item) => item.value));
  if (unit.measurement.storage_format) {
    names.add(unit.measurement.storage_format);
  }
  names.forEach((value) => {
    bundles[value] = {
      values: unit.values?.[value] || [],
      chart,
    };
  });
  return bundles;
}
