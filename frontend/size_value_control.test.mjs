import assert from "node:assert/strict";
import { mkdirSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { tmpdir } from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

import * as esbuild from "esbuild";
import { JSDOM } from "jsdom";

const require = createRequire(import.meta.url);
const outDir = path.join(tmpdir(), "django-fashion-size-size-value-control");
mkdirSync(outDir, { recursive: true });

const reactPath = (specifier) => pathToFileURL(require.resolve(specifier)).href;

await esbuild.build({
  entryPoints: ["size_value_field/SizeValueControl.jsx"],
  bundle: true,
  format: "esm",
  jsx: "automatic",
  outfile: path.join(outDir, "SizeValueControl.mjs"),
  define: { "process.env.NODE_ENV": '"development"' },
  plugins: [
    {
      name: "external-runtime",
      setup(build) {
        build.onResolve({ filter: /^(react|react-dom)(\/.*)?$/ }, (args) => ({
          path: reactPath(args.path),
          external: true,
        }));
      },
    },
  ],
});

const dom = new JSDOM("<!doctype html><html><body><div id='root'></div></body></html>", {
  pretendToBeVisual: true,
});
const { window } = dom;
function expose(name, value) {
  Object.defineProperty(globalThis, name, {
    value,
    configurable: true,
    writable: true,
  });
}
expose("window", window);
expose("document", window.document);
expose("HTMLElement", window.HTMLElement);
expose("Element", window.Element);
expose("Node", window.Node);
expose("DocumentFragment", window.DocumentFragment);
expose("Event", window.Event);
expose("InputEvent", window.InputEvent);
expose("FocusEvent", window.FocusEvent);
expose("getComputedStyle", window.getComputedStyle.bind(window));
expose("requestAnimationFrame", (callback) => setTimeout(callback, 0));
expose("cancelAnimationFrame", (id) => clearTimeout(id));
expose("IS_REACT_ACT_ENVIRONMENT", true);
writeFileSync(path.join(outDir, "package.json"), JSON.stringify({ type: "module" }));

const React = await import("react");
const { createRoot } = await import("react-dom/client");
const { act } = React;
const { SizeValueControl } = await import(pathToFileURL(path.join(outDir, "SizeValueControl.mjs")).href);

function letterConfig() {
  return {
    initialUnit: "letter",
    label: "Size",
    showChartLink: false,
    customValues: [],
    customLabel: "Custom",
    units: {
      letter: {
        measurement: {
          kind: "letter",
          label: "Letter",
          storage_format: "letter",
          storage_measurement: "letter",
          format_side: "left",
          formats: [{ value: "letter", label: "Letter" }],
          length: false,
        },
        context: {},
        chartKey: "",
        values: {
          letter: [
            { input: "Small", stored: "S" },
            { input: "One size", stored: "ONE" },
          ],
        },
        choices: [],
      },
    },
    charts: {},
  };
}

function dressConfig(showChartLink) {
  return {
    initialUnit: "uk-dress-size",
    label: "Dress",
    showChartLink,
    customValues: [],
    customLabel: "Custom",
    units: {
      "uk-dress-size": {
        measurement: {
          kind: "dress",
          label: "Dress",
          storage_format: "uk",
          storage_measurement: "uk-dress-size",
          format_side: "left",
          formats: [
            { value: "uk", label: "UK" },
            { value: "eu", label: "EU" },
          ],
          format_locked: false,
          length: false,
        },
        context: {},
        chartKey: "dress",
        values: {
          uk: [{ input: "10", stored: "10" }],
          eu: [{ input: "38", stored: "10" }],
        },
        choices: [],
      },
    },
    charts: {
      dress: {
        name: "Dress chart",
        source: "",
        columns: [
          { key: "uk", label: "UK" },
          { key: "eu", label: "EU" },
        ],
        rows: [{ uk: "10", eu: "38" }],
      },
    },
  };
}

async function render(node) {
  const host = globalThis.document.createElement("div");
  globalThis.document.body.appendChild(host);
  const root = createRoot(host);
  await act(async () => {
    root.render(node);
    await Promise.resolve();
  });
  await act(async () => {
    await Promise.resolve();
  });
  return {
    host,
    input: () => host.querySelector("input.size-value__input"),
    unmount() {
      act(() => root.unmount());
      host.remove();
    },
  };
}

test("changing the controlled value updates the input", async () => {
  let setValue;
  function Harness() {
    const [value, update] = React.useState("S");
    setValue = update;
    return React.createElement(SizeValueControl, { config: letterConfig(), value });
  }
  const view = await render(React.createElement(Harness));
  assert.equal(view.input().value, "Small");
  await act(async () => {
    setValue("ONE");
    await Promise.resolve();
  });
  assert.equal(view.input().value, "One size");
  view.unmount();
});

test("onChange reports the stored token and the entry", async () => {
  const seen = [];
  const view = await render(
    React.createElement(SizeValueControl, {
      config: letterConfig(),
      value: "S",
      onChange(token, entry) {
        seen.push([token, entry]);
      },
    })
  );
  const input = view.input();
  await act(async () => {
    input.focus();
    const descriptor = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, "value");
    descriptor.set.call(input, "One size");
    input.dispatchEvent(new window.InputEvent("input", { bubbles: true }));
  });
  await act(async () => {
    input.dispatchEvent(new window.FocusEvent("focusout", { bubbles: true }));
    await Promise.resolve();
  });
  assert.deepEqual(seen.at(-1), [
    "ONE",
    { text: "One size", format: "letter", unit: "letter" },
  ]);
  view.unmount();
});

test("the conversion chart link follows showChartLink", async () => {
  const shown = await render(
    React.createElement(SizeValueControl, { config: dressConfig(true), value: "10" })
  );
  assert.equal(shown.host.textContent.includes("View conversion chart"), true);
  shown.unmount();

  const hidden = await render(
    React.createElement(SizeValueControl, {
      config: dressConfig(true),
      value: "10",
      showChartLink: false,
    })
  );
  assert.equal(hidden.host.textContent.includes("View conversion chart"), false);
  hidden.unmount();

  const fromConfig = await render(
    React.createElement(SizeValueControl, { config: dressConfig(false), value: "10" })
  );
  assert.equal(fromConfig.host.textContent.includes("View conversion chart"), false);
  fromConfig.unmount();
});

test("a parent can replace a chart token with a custom value", async () => {
  const config = dressConfig(false);
  config.customValues = ["One Size"];
  let setValue;
  function Harness() {
    const [value, update] = React.useState("10");
    setValue = update;
    return React.createElement(SizeValueControl, { config, value });
  }
  const view = await render(React.createElement(Harness));
  assert.equal(view.input().value, "10");
  await act(async () => {
    setValue("One Size");
    await Promise.resolve();
  });
  assert.equal(view.input().value, "One Size");
  const format = view.host.querySelector("select.size-value__format");
  assert.equal(format.value, "custom");
  view.unmount();
});
