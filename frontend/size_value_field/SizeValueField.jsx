import { useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";

import { convertLength } from "./length.js";

const suggestionCache = new Map();

function defaultFormat(measurement, context) {
  const fromBrand = context?.formats?.[measurement.kind];
  if (
    fromBrand &&
    measurement.formats.some((item) => item.value === fromBrand)
  ) {
    return fromBrand;
  }
  return measurement.storage_format;
}

function filterValues(values, query) {
  const needle = query.trim().toLowerCase();
  if (!needle) {
    return values;
  }
  return values.filter((item) => {
    const input = item.input.toLowerCase();
    const stored = item.stored.toLowerCase();
    return input.startsWith(needle) || stored.startsWith(needle);
  });
}

function csrfToken() {
  const match = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/);
  return match ? decodeURIComponent(match[1]) : "";
}

function resolveStoredValue({ context, attributeSlug, format, text }) {
  const url = context?.resolve_url;
  if (!url || !attributeSlug || !text.trim()) {
    return Promise.resolve(null);
  }
  return fetch(url, {
    method: "POST",
    credentials: "same-origin",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      "X-CSRFToken": csrfToken(),
    },
    body: JSON.stringify({
      attribute: attributeSlug,
      format,
      value: text,
      age_group: context.age_group || "",
      gender: context.gender || "",
      brand: context.brand_id || null,
      product_type_group: context.product_type_group_id || null,
    }),
  })
    .then((response) => (response.ok ? response.json() : null))
    .then((payload) => payload?.value || null)
    .catch(() => null);
}

function identitySuggestions(choices) {
  return {
    values: choices.filter(Boolean).map((choice) => ({
      input: choice,
      stored: choice,
    })),
    chart: null,
  };
}

function caseHeading(context) {
  const demographic = context?.demographic_label || "";
  const productType = context?.product_type_name || "";
  const group = context?.product_type_group_name || "";
  const typeLine =
    productType && group && productType !== group
      ? `${productType} · ${group}`
      : productType || group;
  return [demographic, typeLine].filter(Boolean).join(" · ");
}

function rowMatchesStored(row, stored, storageFormat) {
  const cell = String(row?.[storageFormat] || "")
    .trim()
    .toLowerCase();
  const needle = String(stored || "")
    .trim()
    .toLowerCase();
  if (!cell || !needle) {
    return false;
  }
  return needle === cell || needle.endsWith(` ${cell}`);
}

function localStored({ measurement, bundles, format, text }) {
  const typed = text.trim();
  if (!typed) {
    return "";
  }
  if (measurement.length) {
    return convertLength(typed, format, measurement.storage_format);
  }
  const bundle = bundles?.[format];
  const exact = bundle?.values?.find(
    (item) => item.input.toLowerCase() === typed.toLowerCase()
  );
  if (exact) {
    return exact.stored;
  }
  const row = bundle?.chart?.rows?.find(
    (item) =>
      String(item?.[format] || "")
        .trim()
        .toLowerCase() === typed.toLowerCase()
  );
  const cell = row?.[measurement.storage_format];
  if (cell != null && String(cell).trim()) {
    return String(cell);
  }
  if (!bundle?.chart && format === measurement.storage_format) {
    return typed;
  }
  return null;
}

async function loadSuggestions({ measurement, format, context, choices, bundles }) {
  if (bundles && Object.prototype.hasOwnProperty.call(bundles, format)) {
    const bundle = bundles[format] || { values: [], chart: null };
    return {
      values: Array.isArray(bundle.values) ? bundle.values : [],
      chart: bundle.chart || null,
    };
  }
  const url = context?.suggestions_url;
  if (!url) {
    return identitySuggestions(choices);
  }
  const params = new URLSearchParams();
  params.set("kind", measurement.kind);
  params.set("format", format);
  params.set("storage", measurement.storage_measurement);
  if (context.age_group) {
    params.set("age_group", context.age_group);
  }
  if (context.gender) {
    params.set("gender", context.gender);
  }
  if (context.brand_id) {
    params.set("brand", String(context.brand_id));
  }
  if (context.product_type_group_id) {
    params.set("product_type_group", String(context.product_type_group_id));
  }
  choices.forEach((choice) => {
    if (choice) {
      params.append("choice", choice);
    }
  });
  const full = `${url}?${params.toString()}`;
  const cached = suggestionCache.get(full);
  if (cached) {
    return cached;
  }
  const pending = fetch(full, {
    credentials: "same-origin",
    headers: { Accept: "application/json" },
  }).then(async (response) => {
    if (!response.ok) {
      throw new Error("Could not load sizes.");
    }
    const data = await response.json();
    return {
      values: Array.isArray(data.values) ? data.values : [],
      chart: data.chart || null,
    };
  });
  suggestionCache.set(full, pending);
  try {
    return await pending;
  } catch (error) {
    suggestionCache.delete(full);
    throw error;
  }
}

export function SizeValueField({
  measurement,
  context,
  bundles,
  choices,
  storedValue,
  attributeSlug,
  disabled,
  ariaLabel,
  onChange,
  onEntry,
}) {
  const listId = useId();
  const rootRef = useRef(null);
  const inputRef = useRef(null);
  const [format, setFormat] = useState(() =>
    defaultFormat(measurement, context)
  );
  const [values, setValues] = useState([]);
  const [chart, setChart] = useState(null);
  const [text, setText] = useState(storedValue || "");
  const [open, setOpen] = useState(false);
  const [chartOpen, setChartOpen] = useState(false);
  const [chartBox, setChartBox] = useState(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [menuBox, setMenuBox] = useState(null);
  const [resolveError, setResolveError] = useState("");
  const focused = useRef(false);

  useEffect(() => {
    let cancelled = false;
    loadSuggestions({ measurement, format, context, choices, bundles })
      .then((next) => {
        if (!cancelled) {
          setValues(next.values);
          setChart(next.chart);
        }
      })
      .catch(() => {
        if (!cancelled) {
          const fallback =
            format === measurement.storage_format
              ? identitySuggestions(choices)
              : { values: [], chart: null };
          setValues(fallback.values);
          setChart(fallback.chart);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [measurement, format, context, choices, bundles]);

  useEffect(() => {
    if (focused.current) {
      return;
    }
    const match = values.find((item) => item.stored === storedValue);
    if (match) {
      setText(match.input);
      return;
    }
    if (
      measurement.length &&
      storedValue &&
      format !== measurement.storage_format
    ) {
      setText(
        convertLength(storedValue, measurement.storage_format, format, {
          display: true,
        }) || storedValue
      );
      return;
    }
    setText(storedValue || "");
  }, [storedValue, values, format, measurement]);

  const query = text.trim();
  const matches = useMemo(
    () => (query ? filterValues(values, query) : []),
    [values, query]
  );

  useEffect(() => {
    setActiveIndex(0);
  }, [text, format, open]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const place = () => {
      const node = rootRef.current;
      if (!node) {
        return;
      }
      const rect = node.getBoundingClientRect();
      setMenuBox({
        top: rect.bottom + 4,
        left: rect.left,
        width: rect.width,
      });
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [open, matches.length]);

  useEffect(() => {
    if (!open) {
      return undefined;
    }
    const onPointer = (event) => {
      if (rootRef.current?.contains(event.target)) {
        return;
      }
      if (event.target?.closest?.(".size-value__list")) {
        return;
      }
      setOpen(false);
    };
    document.addEventListener("mousedown", onPointer);
    return () => document.removeEventListener("mousedown", onPointer);
  }, [open]);

  const publish = (stored, entryText) => {
    onChange(stored);
    onEntry?.({ text: entryText, format });
  };

  const commit = (item, { focus = false } = {}) => {
    setText(item.input);
    setOpen(false);
    setResolveError("");
    if (focus) {
      inputRef.current?.focus();
    }
    if (bundles || measurement.length) {
      const value = localStored({
        measurement,
        bundles,
        format,
        text: item.input,
      });
      publish(value || item.stored, item.input);
      return;
    }
    resolveStoredValue({
      context,
      attributeSlug,
      format,
      text: item.input,
    }).then((value) => {
      publish(value || item.stored, item.input);
    });
  };

  const commitTyped = (raw) => {
    const typed = raw.trim();
    if (!typed) {
      setResolveError("");
      publish("", "");
      return;
    }
    const exact = values.find(
      (item) => item.input.toLowerCase() === typed.toLowerCase()
    );
    if (exact) {
      commit(exact);
      return;
    }
    if (bundles || measurement.length) {
      const value = localStored({ measurement, bundles, format, text: typed });
      if (value) {
        setResolveError("");
        setText(typed);
        publish(value, typed);
        return;
      }
      setResolveError(
        measurement.length
          ? "Enter a length from 5 to 150 inches."
          : "That size is not on the chart."
      );
      return;
    }
    resolveStoredValue({
      context,
      attributeSlug,
      format,
      text: typed,
    }).then((value) => {
      if (value) {
        setResolveError("");
        setText(typed);
        publish(value, typed);
        return;
      }
      setResolveError("That size is not on the chart.");
    });
  };

  const onKeyDown = (event) => {
    if (event.key === "ArrowDown") {
      if (!query) {
        return;
      }
      event.preventDefault();
      setOpen(true);
      setActiveIndex((index) =>
        Math.min(index + 1, Math.max(matches.length - 1, 0))
      );
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActiveIndex((index) => Math.max(index - 1, 0));
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const item = open ? matches[activeIndex] : null;
      if (item) {
        commit(item, { focus: true });
      } else {
        commitTyped(text);
      }
      return;
    }
    if (event.key === "Escape") {
      setOpen(false);
      setChartOpen(false);
    }
  };

  useEffect(() => {
    if (!chartOpen) {
      return undefined;
    }
    const place = () => {
      const node = rootRef.current;
      if (!node) {
        return;
      }
      const rect = node.getBoundingClientRect();
      const width = Math.min(380, window.innerWidth - 16);
      let left = rect.right - width;
      if (left < 8) {
        left = 8;
      }
      const spaceBelow = window.innerHeight - rect.bottom;
      const openUp = spaceBelow < 260 && rect.top > spaceBelow;
      setChartBox({
        top: openUp ? undefined : rect.bottom + 6,
        bottom: openUp ? window.innerHeight - rect.top + 6 : undefined,
        left,
        width,
      });
    };
    place();
    window.addEventListener("scroll", place, true);
    window.addEventListener("resize", place);
    return () => {
      window.removeEventListener("scroll", place, true);
      window.removeEventListener("resize", place);
    };
  }, [chartOpen, chart]);

  useEffect(() => {
    if (!chartOpen) {
      return undefined;
    }
    const onPointer = (event) => {
      if (rootRef.current?.contains(event.target)) {
        return;
      }
      if (event.target?.closest?.(".size-value__chart-popover")) {
        return;
      }
      setChartOpen(false);
    };
    const onKey = (event) => {
      if (event.key === "Escape") {
        setChartOpen(false);
      }
    };
    document.addEventListener("mousedown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [chartOpen]);

  useEffect(() => {
    if (!chartOpen) {
      return undefined;
    }
    const row = document.querySelector(
      ".size-value__chart-popover .is-current"
    );
    row?.scrollIntoView({ block: "nearest" });
    return undefined;
  }, [chartOpen, storedValue, chart, format]);

  useEffect(() => {
    onEntry?.({ text, format });
  }, [text, format, onEntry]);

  const side = measurement.format_side === "right" ? "right" : "left";
  const formatSelect = (
    <select
      className="size-value__format"
      value={format}
      disabled={disabled}
      aria-label={`${measurement.label} format`}
      onChange={(event) => {
        setFormat(event.target.value);
        setOpen(false);
      }}
    >
      {measurement.formats.map((item) => (
        <option key={item.value} value={item.value}>
          {item.label}
        </option>
      ))}
    </select>
  );

  return (
    <div
      ref={rootRef}
      className={`size-value size-value--${side}${
        disabled ? " is-disabled" : ""
      }`}
    >
      <div className="size-value__control">
        {side === "left" ? formatSelect : null}
        <input
          ref={inputRef}
          className="size-value__input"
          type="text"
          role="textbox"
          aria-autocomplete="list"
          aria-expanded={open}
          aria-controls={listId}
          aria-label={ariaLabel || measurement.label}
          placeholder={measurement.label}
          value={text}
          disabled={disabled}
          autoComplete="off"
          onChange={(event) => {
            const next = event.target.value;
            setText(next);
            setOpen(Boolean(next.trim()));
            if (!next.trim()) {
              publish("", "");
            }
          }}
          onFocus={() => {
            focused.current = true;
            if (text.trim()) {
              setOpen(true);
            }
          }}
          onBlur={() => {
            focused.current = false;
            commitTyped(text);
            window.setTimeout(() => setOpen(false), 120);
          }}
          onKeyDown={onKeyDown}
        />
        {chart ? (
          <button
            type="button"
            className="size-value__chart"
            aria-expanded={chartOpen}
            aria-label={`Show ${chart.name}`}
            onMouseDown={(event) => event.preventDefault()}
            onClick={() => {
              setOpen(false);
              setChartOpen((current) => !current);
            }}
          >
            Chart
          </button>
        ) : null}
        {side === "right" ? formatSelect : null}
      </div>
      {resolveError ? (
        <p className="size-value__error" role="alert">
          {resolveError}
        </p>
      ) : null}
      {open && query && menuBox && matches.length
        ? createPortal(
            <ul
              id={listId}
              className="size-value__list"
              role="listbox"
              style={{
                position: "fixed",
                top: menuBox.top,
                left: menuBox.left,
                width: menuBox.width,
              }}
            >
              {matches.map((item, index) => (
                <li key={`${item.stored}-${item.input}`} role="presentation">
                  <button
                    type="button"
                    role="option"
                    aria-selected={index === activeIndex}
                    className={`size-value__option${
                      index === activeIndex ? " is-active" : ""
                    }`}
                    onMouseDown={(event) => {
                      event.preventDefault();
                      commit(item, { focus: true });
                    }}
                    onMouseEnter={() => setActiveIndex(index)}
                  >
                    <span>{item.input}</span>
                    {item.stored !== item.input ? (
                      <span className="size-value__stored">{item.stored}</span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>,
            document.body
          )
        : null}
      {chartOpen && chart && chartBox
        ? createPortal(
            <div
              className="size-value__chart-popover"
              role="dialog"
              aria-label={chart.name}
              style={{
                position: "fixed",
                top: chartBox.top,
                bottom: chartBox.bottom,
                left: chartBox.left,
                width: chartBox.width,
              }}
            >
              <p className="size-value__chart-case">
                {caseHeading(context) || chart.demographic}
              </p>
              <p className="size-value__chart-name">{chart.name}</p>
              {chart.fallback_note ? (
                <p className="size-value__chart-note">{chart.fallback_note}</p>
              ) : null}
              <p className="size-value__chart-meta">
                <span>Source</span>
                {/^https?:\/\//i.test(chart.source || "") ? (
                  <a href={chart.source} target="_blank" rel="noreferrer">
                    {chart.source}
                  </a>
                ) : (
                  <span>{chart.source}</span>
                )}
              </p>
              {chart.notes ? (
                <p className="size-value__chart-meta">
                  <span>Notes</span>
                  <span>{chart.notes}</span>
                </p>
              ) : null}
              <p className="size-value__chart-meta">
                <span>Covers</span>
                <span>
                  {chart.groups?.length
                    ? chart.groups.join(", ")
                    : "Every product type"}
                </span>
              </p>
              <div className="size-value__chart-table-wrap">
                <table className="size-value__chart-table">
                  <thead>
                    <tr>
                      {chart.columns.map((column) => (
                        <th
                          key={column.key}
                          className={
                            column.key === format ? "is-format" : undefined
                          }
                        >
                          {column.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {chart.rows.map((row) => {
                      const current = rowMatchesStored(
                        row,
                        storedValue,
                        measurement.storage_format
                      );
                      return (
                        <tr
                          key={chart.columns
                            .map((column) => row[column.key])
                            .join("|")}
                          className={current ? "is-current" : undefined}
                        >
                          {chart.columns.map((column) => (
                            <td
                              key={column.key}
                              className={
                                column.key === format ? "is-format" : undefined
                              }
                            >
                              {row[column.key]}
                            </td>
                          ))}
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>,
            document.body
          )
        : null}
    </div>
  );
}
