import { copyFileSync } from "node:fs";

import * as esbuild from "esbuild";

const externalCss = {
  name: "external-css",
  setup(build) {
    build.onResolve({ filter: /\.css$/ }, () => ({
      path: "./size_value_field.css",
      external: true,
    }));
  },
};

const shared = {
  bundle: true,
  jsx: "automatic",
  minify: true,
  define: { "process.env.NODE_ENV": '"production"' },
};

await esbuild.build({
  ...shared,
  entryPoints: ["size_value_field/mount.jsx"],
  format: "iife",
  outfile: "../src/django_fashion_size/static/django_fashion_size/size_value_field.js",
});

await esbuild.build({
  ...shared,
  entryPoints: ["size_value_field/index.jsx"],
  format: "esm",
  outfile: "../src/django_fashion_size/static/django_fashion_size/size-value-field.js",
  external: ["react", "react-dom", "react/jsx-runtime"],
  plugins: [externalCss],
});

copyFileSync(
  "size_value_field/size_value_field.css",
  "../src/django_fashion_size/static/django_fashion_size/size_value_field.css"
);
