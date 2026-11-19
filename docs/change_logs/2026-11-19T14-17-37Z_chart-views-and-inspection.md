# Shared view selection and notebook inspection

- Added `ViewSpec` and shared selection for full, half-open UTC windows and
  candidate focus. Explicit case and activity filters preserve reference order
  and colors. A time window can contain partial traces and blank matched rows.
- Connected `notebooks/review_charts.ipynb` to the production Agg renderer and
  in-memory PNG encoder. The notebook reports role-specific counts and fallback
  provenance and can project candidate intervals and instants for inspection.
  JupyterLab is available through the optional `notebook` dependency group.
- Added filter, region, short-window, empty-panel and overlay tests and updated
  `docs/dotted_chart_rendering.md`. All 30 rendering tests, Ruff format and Ruff
  lint passed. Executed the notebook cells in IPython against the full saved
  BPIC2012 variant with no chart writes. The notebook schema validated and saved
  outputs are clear. Local socket restrictions prevented a separate Jupyter
  kernel launch in the sandbox.
- At the default geometry, 13,087 full-log case rows share 960 vertical pixels.
  Candidate overlays are for exploratory inspection. Export and Phase-4 mapping
  follow in the next stage.
