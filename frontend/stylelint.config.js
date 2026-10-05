/** @type {import('stylelint').Config} */
export default {
  extends: ["stylelint-config-standard"],
  rules: {
    // Widget markup uses BEM (`size-value__control`, `size-value--left`).
    "selector-class-pattern": null,
    "property-no-vendor-prefix": [
      true,
      {
        ignoreProperties: ["appearance"],
      },
    ],
  },
};
