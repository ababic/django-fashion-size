import { useCallback } from "react";
import { createRoot } from "react-dom/client";

import { SizeValueField } from "./SizeValueField";

const roots = new WeakMap();

function readConfig(mount) {
  const id = mount.getAttribute("data-config");
  const node = id ? document.getElementById(id) : null;
  if (!node) {
    return null;
  }
  return JSON.parse(node.textContent);
}

function writeField(mount, name, value) {
  const node = mount.querySelector(`[data-size-value-${name}]`);
  if (node) {
    node.value = value ?? "";
  }
}

function bundlesFor(unit, charts) {
  const chart = unit.chartKey ? charts?.[unit.chartKey] || null : null;
  const bundles = {};
  unit.measurement.formats.forEach((item) => {
    bundles[item.value] = {
      values: unit.values?.[item.value] || [],
      chart,
    };
  });
  return bundles;
}

function BoundSize({ mount, input, config, unitSlug }) {
  const unit = config.units?.[unitSlug];
  const onEntry = useCallback(
    (entry) => {
      writeField(mount, "entry", entry.text);
      writeField(mount, "format", entry.format);
      writeField(mount, "unit", unitSlug);
    },
    [mount, unitSlug]
  );
  const onChange = useCallback(
    (value) => {
      input.value = value;
      input.dispatchEvent(new Event("input", { bubbles: true }));
      input.dispatchEvent(new Event("change", { bubbles: true }));
    },
    [input]
  );
  if (!unit) {
    return null;
  }
  return (
    <SizeValueField
      measurement={unit.measurement}
      context={unit.context || {}}
      bundles={bundlesFor(unit, config.charts)}
      choices={unit.choices || []}
      storedValue={input.value}
      disabled={Boolean(config.disabled || input.disabled)}
      ariaLabel={config.label || unit.measurement.label}
      onChange={onChange}
      onEntry={onEntry}
    />
  );
}

function renderMount(mount) {
  const config = readConfig(mount);
  const input = mount.querySelector("[data-size-value-input]");
  const rootNode = mount.querySelector("[data-size-value-root]");
  if (!config || !input || !rootNode) {
    return;
  }
  const unitNow = config.units?.[config.initialUnit] || null;
  writeField(mount, "entry", input.value);
  writeField(mount, "format", unitNow?.measurement?.storage_format || "");
  writeField(mount, "unit", config.initialUnit || "");
  writeField(mount, "active", "1");
  writeField(mount, "age-group", config.ageGroup || "");
  writeField(mount, "gender", config.gender || "");
  writeField(mount, "brand", config.brand || "");
  writeField(mount, "product-type", config.productType || "");

  let root = roots.get(rootNode);
  if (!root) {
    root = createRoot(rootNode);
    roots.set(rootNode, root);
  }
  const form = input.form;
  const unitInput =
    config.sizeUnitField && form
      ? form.elements.namedItem(config.sizeUnitField)
      : null;
  const currentUnit = () => {
    if (unitInput && "value" in unitInput && unitInput.value) {
      return unitInput.value;
    }
    return config.initialUnit || "";
  };
  const draw = () => {
    const unitSlug = currentUnit();
    const unit = config.units?.[unitSlug];
    if (!unit) {
      mount.classList.remove("is-ready");
      input.hidden = false;
      root.render(null);
      return;
    }
    mount.classList.add("is-ready");
    input.hidden = true;
    root.render(
      <BoundSize
        key={unitSlug}
        mount={mount}
        input={input}
        config={config}
        unitSlug={unitSlug}
      />
    );
  };
  draw();
  if (unitInput) {
    unitInput.addEventListener("change", draw);
  }
  const syncDemographics = () => {
    const linked = [
      ["age-group", "age_group"],
      ["gender", "gender"],
      ["brand", "brandField" in config ? config.brandField : "brand"],
      ["product-type", "productTypeField" in config ? config.productTypeField : "product_type"],
    ];
    linked.forEach(([hidden, source]) => {
      if (!source) {
        return;
      }
      const field = form?.elements.namedItem(source);
      if (field && "value" in field) {
        writeField(mount, hidden, field.value);
      }
    });
  };
  form?.addEventListener("submit", syncDemographics);
  form?.addEventListener("change", syncDemographics);
}

function boot() {
  document
    .querySelectorAll("[data-size-value-field]:not([data-mounted])")
    .forEach((node) => {
      node.setAttribute("data-mounted", "1");
      renderMount(node);
    });
}

boot();
new MutationObserver(boot).observe(document.documentElement, {
  childList: true,
  subtree: true,
});
