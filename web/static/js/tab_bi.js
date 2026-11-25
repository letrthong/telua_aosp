/* ==============================================================================
   Telua Web - Power BI Interactive Studio & Chart Visualizations
   ============================================================================== */
function biFormatNumber(num) {
  if (num === null || num === undefined || isNaN(num)) return "0";
  const abs = Math.abs(num);
  if (abs >= 1e9) return (num / 1e9).toFixed(1) + "B";
  if (abs >= 1e6) return (num / 1e6).toFixed(1) + "M";
  if (abs >= 1e3) return (num / 1e3).toFixed(1) + "k";
  return Number.isInteger(num) ? num.toLocaleString() : num.toFixed(2);
}

function initBIDashboard() {
  if (biState.isInitialized) return;
  biState.isInitialized = true;

  // Tooltip DOM element
  if (!biState.tooltipEl) {
    let tip = $("#bi-chart-tooltip");
    if (!tip) {
      tip = document.createElement("div");
      tip.id = "bi-chart-tooltip";
      tip.className = "bi-chart-tooltip";
      document.body.appendChild(tip);
    }
    biState.tooltipEl = tip;
  }

  // Upload handlers
  const onFileSelected = (e) => {
    const file = e.target.files?.[0];
    if (file) biUploadFile(file);
    e.target.value = "";
  };
  $("#bi-file-input")?.addEventListener("change", onFileSelected);
  $("#bi-file-input-hero")?.addEventListener("change", onFileSelected);

  // Drag & drop support
  const dropzone = $("#bi-empty-dropzone");
  const container = $("#bi-canvas-container");
  [dropzone, container].forEach((el) => {
    if (!el) return;
    el.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone?.classList.add("dragover");
    });
    el.addEventListener("dragleave", (e) => {
      if (!el.contains(e.relatedTarget)) dropzone?.classList.remove("dragover");
    });
    el.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone?.classList.remove("dragover");
      const file = e.dataTransfer?.files?.[0];
      if (file) biUploadFile(file);
    });
  });

  // Sample dataset dropdown
  $("#bi-sample-select")?.addEventListener("change", (e) => {
    const key = e.target.value;
    if (key) biLoadSample(key);
  });

  // Sheet switcher
  $("#bi-sheet-select")?.addEventListener("change", (e) => {
    const sheet = e.target.value;
    if (sheet && biState.allSheets[sheet]) {
      biSwitchSheet(sheet);
    }
  });

  // Search input
  $("#bi-search-input")?.addEventListener("input", (e) => {
    biState.searchQuery = (e.target.value || "").trim().toLowerCase();
    biApplyFilters();
  });

  // Fields filter search
  $("#bi-fields-search")?.addEventListener("input", (e) => {
    biRenderFieldsList(e.target.value || "");
  });

  // Toggle fields pane
  $("#btn-bi-fields-toggle")?.addEventListener("click", () => {
    const pane = $("#bi-fields-pane");
    if (pane) {
      pane.classList.toggle("collapsed");
      const isCollapsed = pane.classList.contains("collapsed");
      $("#btn-bi-fields-toggle").textContent = isCollapsed ? "▶" : "◀";
    }
  });

  // Reset filters
  $("#btn-bi-reset-filters")?.addEventListener("click", () => {
    biState.activeSlicers = {};
    biState.searchQuery = "";
    if ($("#bi-search-input")) $("#bi-search-input").value = "";
    biApplyFilters();
    toast("Filters reset", "All Power BI slicers and filters cleared.", "info", 2000);
  });

  // Paste table modal handlers
  const openPasteModal = () => {
    const modal = $("#modal-bi-paste");
    if (modal) {
      if (!$("#bi-paste-name")?.value) {
        $("#bi-paste-name").value = "vehicle_fleet_market.csv";
      }
      modal.classList.remove("hidden");
      $("#bi-paste-input")?.focus();
    }
  };
  $("#btn-bi-paste-open")?.addEventListener("click", openPasteModal);
  $("#btn-bi-paste-hero")?.addEventListener("click", openPasteModal);
  $("#btn-bi-paste-cancel")?.addEventListener("click", () => $("#modal-bi-paste")?.classList.add("hidden"));
  $("#btn-bi-paste-submit")?.addEventListener("click", () => biSubmitPaste());

  // Cross-Tab Report modal handlers
  $("#btn-bi-cross-report")?.addEventListener("click", () => biOpenCrossTabReport());
  $("#btn-bi-report-close")?.addEventListener("click", () => $("#modal-bi-cross-report")?.classList.add("hidden"));
  $("#btn-bi-report-copy-md")?.addEventListener("click", () => {
    if (biState._lastCrossReport?.markdown_report) {
      navigator.clipboard.writeText(biState._lastCrossReport.markdown_report).then(() => {
        toast("Report Copied", "Markdown report copied to clipboard.", "ok", 2500);
      });
    }
  });
  $("#btn-bi-report-to-docs")?.addEventListener("click", async () => {
    if (!biState._lastCrossReport?.rst_report) return;
    toast("Saving to Docs…", "Writing report to docs/cross_sheet_report.rst…", "info", 2000);
    try {
      const res = await fetch("/api/bi/save-doc", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          path: "docs/cross_sheet_report.rst",
          content: biState._lastCrossReport.rst_report,
        }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) throw new Error(data.error || "Failed to save doc");
      $("#modal-bi-cross-report")?.classList.add("hidden");
      toast("Saved to Docs", "Report saved to docs/cross_sheet_report.rst. Switching to Docs…", "ok", 3000);
      switchTab("docs");
      refreshDocsFiles("docs/cross_sheet_report.rst");
    } catch (err) {
      toast("Save Error", err.message, "err", 5000);
    }
  });

  // Export filtered Excel
  $("#btn-bi-export-excel")?.addEventListener("click", () => biExportExcel());

  // JSON viewer modal
  $("#btn-bi-view-json")?.addEventListener("click", () => biOpenJsonModal());
  $("#btn-bi-json-close")?.addEventListener("click", () => $("#modal-bi-json")?.classList.add("hidden"));
  $("#btn-bi-json-copy")?.addEventListener("click", () => {
    const content = $("#bi-json-viewer-content")?.textContent || "";
    navigator.clipboard.writeText(content).then(() => {
      toast("JSON Copied", "Dataset JSON copied to clipboard.", "ok", 2500);
    });
  });
  $("#btn-bi-json-download")?.addEventListener("click", () => {
    const content = $("#bi-json-viewer-content")?.textContent || "";
    const blob = new Blob([content], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = (biState.filename ? biState.filename.replace(/\.[^/.]+$/, "") : "dataset") + ".json";
    a.click();
    URL.revokeObjectURL(url);
    toast("JSON Downloaded", "JSON file saved to Downloads.", "ok", 2500);
  });
  $("#btn-bi-json-to-mermaid")?.addEventListener("click", () => {
    $("#modal-bi-json")?.classList.add("hidden");
    switchTab("docs");
    openJsonChartModal();
    const input = $("#json-chart-input");
    if (input && biState.filteredData.length) {
      // Pick top numerical and categorical column for auto mermaid sample
      const numCols = biState.columns.filter((c) => c.type === "number");
      const strCols = biState.columns.filter((c) => c.type !== "number");
      if (strCols.length && numCols.length) {
        const xCol = strCols[0].name;
        const yCol = numCols[0].name;
        const sampleRecords = biState.filteredData.slice(0, 8);
        const jsonPayload = {
          x: sampleRecords.map((r) => String(r[xCol] || "—")),
          y: sampleRecords.map((r) => Number(r[yCol]) || 0),
        };
        input.value = JSON.stringify(jsonPayload, null, 2);
      }
    }
  });

  // Visual Builder modal
  $("#btn-bi-add-visual")?.addEventListener("click", () => biOpenAddVisualModal());
  $("#btn-bi-visual-cancel")?.addEventListener("click", () => $("#modal-bi-add-visual")?.classList.add("hidden"));
  $("#btn-bi-visual-save")?.addEventListener("click", () => biSaveNewVisual());

  // Calculated Column / Measure modal (Mini-DAX)
  $("#btn-bi-calc-col-open")?.addEventListener("click", () => biOpenCalcColModal());
  $("#btn-bi-calc-col-fields")?.addEventListener("click", () => biOpenCalcColModal());
  $("#btn-bi-calc-cancel")?.addEventListener("click", () => $("#modal-bi-calc-col")?.classList.add("hidden"));
  $("#btn-bi-calc-submit")?.addEventListener("click", () => biCreateCalculatedColumn());

  // Dashboard Visuals Config JSON & GUI Manager modal & actions
  $("#btn-bi-config-open")?.addEventListener("click", () => biOpenConfigModal("gui"));
  $("#btn-bi-config-close")?.addEventListener("click", () => $("#modal-bi-config")?.classList.add("hidden"));
  $("#btn-bi-cfg-tab-gui")?.addEventListener("click", () => biSwitchConfigTab("gui"));
  $("#btn-bi-cfg-tab-raw")?.addEventListener("click", () => biSwitchConfigTab("raw"));
  $("#btn-bi-gui-save-item")?.addEventListener("click", () => biSaveConfigItemFromForm());
  $("#btn-bi-gui-cancel-edit")?.addEventListener("click", () => biResetConfigForm());

  // Type chips in Config GUI form
  document.querySelectorAll("#bi-gui-type-chips .term-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      document.querySelectorAll("#bi-gui-type-chips .term-chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const vtype = btn.dataset.vtype;
      const y2Group = $("#bi-gui-y2-group");
      if (y2Group) y2Group.style.display = vtype === "combo" ? "block" : "none";
    });
  });

  $("#btn-bi-config-apply")?.addEventListener("click", () => {
    const isRawActive = $("#btn-bi-cfg-tab-raw")?.classList.contains("active");
    if (isRawActive) {
      const val = $("#bi-config-editor-content")?.value || "";
      biApplyConfigJson(val);
    } else {
      biRenderVisuals();
      $("#modal-bi-config")?.classList.add("hidden");
      toast("Đã áp dụng", `Đã cập nhật ${biState.visuals.length} biểu đồ lên Dashboard.`, "ok", 2500);
      try {
        fetch("/api/bi/visual-config", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            dataset: biState.filename,
            sheet: biState.activeSheet,
            visuals: biState.visuals,
          }),
        }).catch(() => { });
      } catch { }
    }
  });

  $("#btn-bi-config-copy")?.addEventListener("click", () => {
    const val = $("#bi-config-editor-content")?.value || "";
    navigator.clipboard.writeText(val).then(() => {
      toast("JSON Copied", "Config JSON copied to clipboard.", "ok", 2000);
    });
  });
  $("#btn-bi-config-download")?.addEventListener("click", () => biExportConfigJson());
  $("#btn-bi-config-download-btn")?.addEventListener("click", () => biExportConfigJson());
  $("#bi-config-file-input")?.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (file) biImportConfigJson(file);
    e.target.value = "";
  });
  $("#bi-modal-config-upload")?.addEventListener("change", (e) => {
    const file = e.target.files?.[0];
    if (file) biImportConfigJson(file);
    e.target.value = "";
  });
  $("#btn-bi-config-clear")?.addEventListener("click", () => {
    biState.visuals = [];
    biRenderVisuals();
    biRenderConfigGuiList();
    toast("Đã xóa biểu đồ", "Toàn bộ biểu đồ đã được xóa khỏi danh sách cấu hình.", "info", 2000);
  });
  $("#btn-bi-config-sample")?.addEventListener("click", () => {
    const numCols = biState.columns.filter((c) => c.type === "number");
    const strCols = biState.columns.filter((c) => c.type !== "number");
    const cat = strCols[0]?.name || biState.columns[0]?.name || "Category";
    const num = numCols[0]?.name || "Value";
    const sample = {
      version: "1.0",
      generator: "telua_bi_studio",
      dataset: biState.filename || "dataset.xlsx",
      sheet: biState.activeSheet || "Sheet1",
      visuals: [
        {
          id: "vis_1",
          type: "combo",
          title: `Revenue vs Margin by ${cat}`,
          x: cat,
          y: num,
          y2: numCols[1]?.name || num,
          agg: "sum",
          isWide: false
        },
        {
          id: "vis_2",
          type: "pie",
          title: `Phân bố tỷ trọng theo ${cat}`,
          x: cat,
          y: num,
          agg: "sum",
          isWide: false
        },
        {
          id: "vis_3",
          type: "table",
          title: `Bảng dữ liệu chi tiết (${biState.activeSheet || 'Sheet1'})`,
          limit: 15,
          isWide: true
        }
      ]
    };
    biState.visuals = sample.visuals;
    biRenderConfigGuiList();
    toast("Template Loaded", "Đã nạp mẫu 3 biểu đồ chuẩn vào danh sách cấu hình.", "info", 2500);
  });

  // Visual type chip picker in modal
  document.querySelectorAll("#bi-visual-type-select .term-chip").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      document.querySelectorAll("#bi-visual-type-select .term-chip").forEach((b) => b.classList.remove("active"));
      btn.classList.add("active");
      const vtype = btn.dataset.vtype;
      const y2Group = $("#bi-visual-y2-group");
      if (y2Group) y2Group.style.display = vtype === "combo" ? "block" : "none";
    });
  });

  // Multi-select serial dropdown toggle
  const msTrigger = $("#btn-bi-slicer-multiselect-trigger");
  const msMenu = $("#menu-bi-slicer-multiselect");
  const msWrap = $("#wrap-bi-slicer-multiselect");

  msTrigger?.addEventListener("click", (e) => {
    e.stopPropagation();
    const isShown = msMenu?.classList.contains("show");
    if (isShown) {
      msMenu?.classList.remove("show");
      msWrap?.classList.remove("open");
    } else {
      msMenu?.classList.add("show");
      msWrap?.classList.add("open");
    }
  });

  // Prevent closing when clicking inside the multi-select menu
  msMenu?.addEventListener("click", (e) => e.stopPropagation());

  // Close multi-select menu when clicking outside
  document.addEventListener("click", () => {
    msMenu?.classList.remove("show");
    msWrap?.classList.remove("open");
  });

  // Dynamically load available datasets from bi_studio directory
  biFetchAvailableDatasets();
}

async function biFetchAvailableDatasets() {
  const sel = $("#bi-sample-select");
  if (!sel) return;
  try {
    const res = await fetch("/api/bi/samples");
    const data = await res.json();
    if (!res.ok || !data.ok) return;

    // Reset dropdown to only placeholder
    sel.innerHTML = '<option value="">📁 Select Excel Dataset…</option>';

    const samples = data.samples || [];
    samples.forEach((s) => {
      const opt = document.createElement("option");
      opt.value = `ws:${s.filename}`;
      const cleanTitle = s.title.replace(/\.[^/.]+$/, "").replace(/_/g, " ");
      const sheetsCount = s.sheets_count || 1;
      const rowsCount = s.rows_count || 0;
      opt.textContent = `📊 ${cleanTitle} (${sheetsCount} Sheets · ${rowsCount} Rows)`;
      sel.appendChild(opt);
    });

    // Auto-load first dataset if none is loaded yet
    if ((!biState.rawData || biState.rawData.length === 0) && samples.length > 0) {
      biLoadSample(`ws:${samples[0].filename}`);
    }
  } catch (err) {
    console.warn("Failed to fetch available datasets from bi_studio:", err);
  }
}

async function biUploadFile(file) {
  const form = new FormData();
  form.append("file", file);

  toast("Converting Excel…", `Uploading & parsing '${file.name}' into JSON…`, "info", 3000);

  try {
    const res = await fetch("/api/bi/convert", {
      method: "POST",
      body: form,
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || data.description || "Upload failed");
    }
    toast("Excel Converted", `Successfully converted '${file.name}' (${data.rows_count} records).`, "ok", 3500);
    biSetDataset(data);
  } catch (err) {
    toast("Conversion Error", err.message, "err", 6000);
  }
}

async function biSubmitPaste() {
  const text = $("#bi-paste-input")?.value || "";
  const name = $("#bi-paste-name")?.value.trim() || "pasted_data.csv";

  if (!text.trim()) {
    toast("Empty Input", "Please paste CSV or tab-separated text first.", "warn", 3000);
    return;
  }

  toast("Parsing Table Data…", "Converting table text into structured JSON…", "info", 2000);

  try {
    const res = await fetch("/api/bi/paste", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text, filename: name }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || data.description || "Failed to parse pasted data");
    }
    $("#modal-bi-paste")?.classList.add("hidden");
    toast("Table Converted", `Loaded ${data.rows_count} rows across ${data.sheets.length} sheet(s).`, "ok", 3500);
    biSetDataset(data);
  } catch (err) {
    toast("Parse Error", err.message, "err", 6000);
  }
}

async function biOpenCrossTabReport() {
  const modal = $("#modal-bi-cross-report");
  const body = $("#bi-cross-report-body");
  if (!modal || !body) return;

  toast("Generating Report…", "Analyzing relationships and cross-sheet metrics…", "info", 2000);

  try {
    const res = await fetch("/api/bi/cross-report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        all_sheets: biState.allSheets,
        filename: biState.filename,
      }),
    });
    const data = await res.json();
    if (!res.ok || !data.ok) throw new Error(data.error || "Failed to generate cross report");

    biState._lastCrossReport = data;
    $("#bi-report-sheets-badge").textContent = `${data.total_sheets} Tabs Analyzed · ${data.total_records.toLocaleString()} Records`;

    let html = `
      <div class="bi-kpi-row" style="margin-bottom:10px;">
        <div class="bi-kpi-card" style="border-top-color:#1ea7fd;">
          <div class="bi-kpi-label">Analyzed Worksheets</div>
          <div class="bi-kpi-val">${data.total_sheets}</div>
          <div class="bi-kpi-sub">${data.filename}</div>
        </div>
        <div class="bi-kpi-card" style="border-top-color:#3fb950;">
          <div class="bi-kpi-label">Total Combined Records</div>
          <div class="bi-kpi-val">${data.total_records.toLocaleString()}</div>
          <div class="bi-kpi-sub">Across all related tabs</div>
        </div>
        <div class="bi-kpi-card" style="border-top-color:#a371f7;">
          <div class="bi-kpi-label">Shared Common Keys</div>
          <div class="bi-kpi-val">${data.shared_keys.length}</div>
          <div class="bi-kpi-sub">${data.shared_keys.slice(0, 3).join(", ") || "No shared keys"}</div>
        </div>
      </div>

      <div style="background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:12px;">
        <h4 style="margin:0 0 8px 0;font-size:13px;color:var(--accent);">📊 Cross-Tab Comparison Matrix</h4>
        <div class="bi-table-wrap">
          <table class="bi-table">
            <thead>
              <tr>
                <th>Tab Name</th>
                <th>Records</th>
                <th>Columns</th>
                <th>Primary Measure</th>
                <th>Total Value</th>
                <th>Top Categories</th>
              </tr>
            </thead>
            <tbody>
              ${data.matrix.map((m) => `
                <tr>
                  <td><b>${m.sheet_name}</b></td>
                  <td>${m.rows_count.toLocaleString()}</td>
                  <td>${m.columns_count}</td>
                  <td>${m.primary_metric || "—"}</td>
                  <td><b>${m.primary_sum ? biFormatNumber(m.primary_sum) : "—"}</b></td>
                  <td><span class="meta">${m.top_categories.join(", ") || "—"}</span></td>
                </tr>
              `).join("")}
            </tbody>
          </table>
        </div>
      </div>

      <div style="background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:12px;">
        <h4 style="margin:0 0 6px 0;font-size:13px;color:var(--accent);">🔗 Common Dimensions &amp; Relational Keys</h4>
        <p class="meta" style="margin:0 0 8px 0;">The following keys link records across multiple worksheets:</p>
        <div style="display:flex;gap:6px;flex-wrap:wrap;">
          ${data.shared_keys.map((k) => `<span class="chip" style="font-size:11px;">🔑 ${k}</span>`).join("")}
        </div>
      </div>

      <div style="display:grid;grid-template-columns:1fr 1fr;gap:12px;">
        <div style="background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:12px;">
          <h4 style="margin:0 0 6px 0;font-size:12px;">🥧 Record Share by Tab</h4>
          <pre class="mono" style="background:var(--bg-soft,#1e1e2e);padding:8px;font-size:10.5px;border-radius:6px;max-height:160px;overflow:auto;">${data.mermaid_pie}</pre>
        </div>
        <div style="background:var(--panel);border:1px solid var(--border);border-radius:8px;padding:12px;">
          <h4 style="margin:0 0 6px 0;font-size:12px;">📶 Grouped Comparison (xychart)</h4>
          <pre class="mono" style="background:var(--bg-soft,#1e1e2e);padding:8px;font-size:10.5px;border-radius:6px;max-height:160px;overflow:auto;">${data.mermaid_bar}</pre>
        </div>
      </div>
    `;

    body.innerHTML = html;
    modal.classList.remove("hidden");
  } catch (err) {
    toast("Report Error", err.message, "err", 5000);
  }
}

async function biLoadSample(key) {
  if (key.startsWith("ws:")) {
    const relPath = key.slice(3);
    toast("Loading Workspace File…", `Parsing '${relPath}' directly from workspace…`, "info", 2000);
    try {
      const res = await fetch("/api/bi/load-workspace-file", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ path: relPath }),
      });
      const data = await res.json();
      if (!res.ok || !data.ok) {
        throw new Error(data.error || data.description || "Failed to load workspace file");
      }
      toast("Workspace File Loaded", `Loaded '${relPath}' (${data.rows_count} rows, ${data.sheets.length} sheets).`, "ok", 3500);
      biSetDataset(data);
    } catch (err) {
      toast("Load Error", err.message, "err", 6000);
    }
    return;
  }

  toast("Loading Sample…", `Fetching sample dataset '${key}'…`, "info", 2000);
  try {
    const res = await fetch(`/api/bi/samples?key=${encodeURIComponent(key)}`);
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || "Failed to load sample dataset");
    }
    toast("Sample Loaded", `Loaded '${data.title}' (${data.rows_count} rows).`, "ok", 3000);
    biSetDataset(data);
  } catch (err) {
    toast("Load Error", err.message, "err", 5000);
  }
}

function biSetDataset(payload) {
  biState.filename = payload.filename || "dataset.xlsx";
  biState.sheets = payload.sheets || ["Sheet1"];
  biState.activeSheet = payload.active_sheet || biState.sheets[0] || "Sheet1";
  biState.allSheets = payload.all_sheets || {};
  biState.columns = payload.columns || [];
  biState.rawData = payload.data || [];
  biState.filteredData = [...biState.rawData];
  biState.activeSlicers = {};
  biState.searchQuery = "";
  biState.selectedField = null;

  // Update UI header
  const badge = $("#bi-active-file-badge");
  if (badge) {
    badge.textContent = `${biState.filename} (${biState.rawData.length} rows)`;
    badge.title = `Active worksheet: ${biState.activeSheet}`;
  }

  // Update sheets dropdown & tabs bar
  const sheetSelect = $("#bi-sheet-select");
  if (sheetSelect) {
    if (biState.sheets.length > 1) {
      sheetSelect.classList.remove("hidden");
      sheetSelect.innerHTML = biState.sheets
        .map((s) => `<option value="${s}" ${s === biState.activeSheet ? "selected" : ""}>📄 ${s}</option>`)
        .join("");
    } else {
      sheetSelect.classList.add("hidden");
    }
  }

  // Render Power BI Sheet Tabs bar
  const tabsBar = $("#bi-sheet-tabs-bar");
  const tabsList = $("#bi-sheet-tabs-list");
  if (tabsBar && tabsList) {
    if (biState.sheets.length > 1) {
      tabsBar.classList.remove("hidden");
      tabsList.innerHTML = biState.sheets
        .map((s) => {
          const rowCount = biState.allSheets[s]?.rows_count ?? (s === biState.activeSheet ? biState.rawData.length : 0);
          const isActive = s === biState.activeSheet;
          return `
            <button type="button" class="bi-sheet-tab-btn ${isActive ? "active" : ""}" data-sheet="${s}" title="Switch to worksheet '${s}'">
              <span>📄 ${s}</span>
              <span class="bi-sheet-tab-count">${rowCount}</span>
            </button>
          `;
        })
        .join("");

      tabsList.querySelectorAll(".bi-sheet-tab-btn").forEach((btn) => {
        btn.addEventListener("click", () => {
          const s = btn.dataset.sheet;
          if (s && s !== biState.activeSheet) {
            biSwitchSheet(s);
          }
        });
      });
    } else {
      tabsBar.classList.add("hidden");
    }
  }

  // Toggle empty dropzone vs dashboard
  $("#bi-empty-dropzone")?.classList.add("hidden");
  $("#bi-active-dashboard")?.classList.remove("hidden");

  // Render fields list
  biRenderFieldsList();

  // Visuals initialization: prioritize payload.default_visuals, keep existing if already configured, otherwise start empty (waiting for Config JSON)
  if (payload.default_visuals && payload.default_visuals.length > 0) {
    biState.visuals = payload.default_visuals.map((v, idx) => ({ ...v, id: `vis_${idx + 1}` }));
  } else if (!biState.visuals) {
    biState.visuals = [];
  }

  // Render Slicers
  biRenderSlicers();

  // Apply filters and render KPIs + Visuals
  biApplyFilters();
}

function biSwitchSheet(sheetName) {
  if (!biState.allSheets[sheetName]) return;
  const sheetPayload = biState.allSheets[sheetName];
  biState.activeSheet = sheetName;
  biState.columns = sheetPayload.columns || [];
  biState.rawData = sheetPayload.data || [];
  biState.filteredData = [...biState.rawData];
  biState.activeSlicers = {};
  biState.searchQuery = "";

  const badge = $("#bi-active-file-badge");
  if (badge) {
    badge.textContent = `${biState.filename} [${sheetName}] (${biState.rawData.length} rows)`;
  }

  // Sync dropdown and tab buttons
  const sheetSelect = $("#bi-sheet-select");
  if (sheetSelect) sheetSelect.value = sheetName;
  document.querySelectorAll("#bi-sheet-tabs-list .bi-sheet-tab-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.dataset.sheet === sheetName);
  });

  biRenderFieldsList();
  biRenderSlicers();
  biApplyFilters();
  toast("Sheet Switched", `Viewing worksheet '${sheetName}'.`, "info", 2000);
}

function biAutoGenerateVisuals() {
  const numCols = biState.columns.filter((c) => c.type === "number");
  const strCols = biState.columns.filter((c) => c.type === "string" || c.type === "boolean");
  const dateCols = biState.columns.filter((c) => c.type === "date");

  const visuals = [];
  let visId = 1;

  // Primary category column
  const catCol = strCols.length > 0 ? strCols[0].name : (biState.columns[0]?.name || "Item");

  // Visual 1: Combo Chart (or Bar) if at least 2 numbers exist
  if (numCols.length >= 2) {
    visuals.push({
      id: `vis_${visId++}`,
      type: "combo",
      title: `${numCols[0].name} (Bar) vs ${numCols[1].name} (Line) by ${catCol}`,
      x: catCol,
      y: numCols[0].name,
      y2: numCols[1].name,
      agg: "sum",
    });
  } else if (numCols.length === 1) {
    visuals.push({
      id: `vis_${visId++}`,
      type: "bar",
      title: `Total ${numCols[0].name} by ${catCol}`,
      x: catCol,
      y: numCols[0].name,
      agg: "sum",
    });
  }

  // Visual 2: Donut / Pie distribution
  if (strCols.length > 0) {
    const pieCat = strCols.length > 1 ? strCols[1].name : strCols[0].name;
    visuals.push({
      id: `vis_${visId++}`,
      type: "pie",
      title: `Distribution by ${pieCat}`,
      x: pieCat,
      y: numCols[0]?.name || pieCat,
      agg: numCols.length > 0 ? "sum" : "count",
    });
  }

  // Visual 3: Horizontal Ranked Bar
  if (numCols.length > 0) {
    visuals.push({
      id: `vis_${visId++}`,
      type: "hbar",
      title: `Top Rankings: ${numCols[0].name} by ${catCol}`,
      x: catCol,
      y: numCols[0].name,
      agg: "sum",
    });
  }

  // Visual 4: Line Trend Chart
  if (dateCols.length > 0 && numCols.length > 0) {
    visuals.push({
      id: `vis_${visId++}`,
      type: "line",
      title: `${numCols[0].name} Trend Over Time`,
      x: dateCols[0].name,
      y: numCols[0].name,
      agg: "avg",
    });
  } else if (numCols.length > 0) {
    visuals.push({
      id: `vis_${visId++}`,
      type: "line",
      title: `${numCols[0].name} Value Curve`,
      x: catCol,
      y: numCols[0].name,
      agg: "avg",
    });
  }

  // Visual 5: Interactive Data Table
  visuals.push({
    id: `vis_${visId++}`,
    type: "table",
    title: `Raw Records Grid (${biState.activeSheet})`,
    limit: 15,
  });

  biState.visuals = visuals;
  biRenderVisuals();
}

function biGetContextData(excludeCol = null) {
  let filtered = [...biState.rawData];
  if (biState.searchQuery) {
    const q = biState.searchQuery.toLowerCase();
    filtered = filtered.filter((row) =>
      Object.values(row).some((val) => val !== null && val !== undefined && String(val).toLowerCase().includes(q))
    );
  }
  const normExclude = (excludeCol || "").trim().toLowerCase().replace(/[\s_-]+/g, "");
  for (const [col, selectedSet] of Object.entries(biState.activeSlicers)) {
    const normCol = (col || "").trim().toLowerCase().replace(/[\s_-]+/g, "");
    if (normCol !== normExclude && selectedSet && selectedSet.size > 0) {
      filtered = filtered.filter((row) => selectedSet.has(String(row[col] ?? "")));
    }
  }
  return filtered;
}

function biApplyFilters() {
  let filtered = [...biState.rawData];

  // 1. Text search across all fields
  if (biState.searchQuery) {
    const q = biState.searchQuery;
    filtered = filtered.filter((row) =>
      Object.values(row).some((val) => val !== null && val !== undefined && String(val).toLowerCase().includes(q))
    );
  }

  // 2. Slicers
  for (const [col, selectedSet] of Object.entries(biState.activeSlicers)) {
    if (selectedSet && selectedSet.size > 0) {
      filtered = filtered.filter((row) => selectedSet.has(String(row[col] ?? "")));
    }
  }

  biState.filteredData = filtered;

  // Filter indicator badge
  const isFiltered = filtered.length !== biState.rawData.length;
  const ind = $("#bi-active-filter-indicator");
  if (ind) {
    ind.classList.toggle("hidden", !isFiltered);
    ind.textContent = isFiltered ? `${filtered.length} / ${biState.rawData.length}` : "";
  }

  biRenderKPICards();
  biRenderVisuals();
}

function biRenderFieldsList(filterText = "") {
  const container = $("#bi-fields-list");
  if (!container) return;
  const countEl = $("#bi-fields-count");
  if (countEl) countEl.textContent = `${biState.columns.length} fields`;

  const q = filterText.toLowerCase();
  const cols = biState.columns.filter((c) => !q || c.name.toLowerCase().includes(q));

  if (cols.length === 0) {
    container.innerHTML = `<div class="meta" style="padding:12px;text-align:center;">No matching fields found.</div>`;
    return;
  }

  container.innerHTML = cols
    .map((c) => {
      let icon = "🔤";
      let badgeText = "TXT";
      if (c.isCustom) { icon = "fx"; badgeText = "CALC"; }
      else if (c.type === "number") { icon = "🔢"; badgeText = "NUM"; }
      else if (c.type === "date") { icon = "📅"; badgeText = "DATE"; }
      else if (c.type === "boolean") { icon = "🔘"; badgeText = "BOOL"; }

      const isSelected = biState.selectedField === c.name;
      return `
        <div class="bi-field-item ${isSelected ? "active" : ""}" data-field="${c.name}">
          <span class="bi-field-badge">${icon} ${badgeText}</span>
          <span class="bi-field-name" title="${c.name}">${c.name}</span>
        </div>
      `;
    })
    .join("");

  // Click on field to see stats
  container.querySelectorAll(".bi-field-item").forEach((el) => {
    el.addEventListener("click", () => {
      const fieldName = el.dataset.field;
      biState.selectedField = fieldName;
      container.querySelectorAll(".bi-field-item").forEach((b) => b.classList.remove("active"));
      el.classList.add("active");
      biShowFieldDetails(fieldName);
    });
  });
}

function biShowFieldDetails(fieldName) {
  const col = biState.columns.find((c) => c.name === fieldName);
  const card = $("#bi-field-details");
  if (!col || !card) return;

  card.classList.remove("hidden");
  $("#bi-field-details-name").textContent = `${col.name} (${col.type.toUpperCase()})`;

  let statsHtml = `<div>Count: <b>${col.count}</b> (Non-null: ${col.non_null_count})</div>`;
  if (col.type === "number") {
    statsHtml += `
      <div>Sum: <b>${col.sum !== undefined ? biFormatNumber(col.sum) : "—"}</b></div>
      <div>Average: <b>${col.avg !== undefined ? biFormatNumber(col.avg) : "—"}</b></div>
      <div>Min: <b>${col.min !== undefined ? col.min : "—"}</b> | Max: <b>${col.max !== undefined ? col.max : "—"}</b></div>
    `;
  } else if (col.distinct_count !== undefined) {
    statsHtml += `<div>Distinct values: <b>${col.distinct_count}</b></div>`;
    if (col.sample_values && col.sample_values.length > 0) {
      statsHtml += `<div style="font-size:10.5px;color:var(--text-dim);margin-top:2px;">Samples: ${col.sample_values.slice(0, 3).join(", ")}</div>`;
    }
  }
  $("#bi-field-details-stats").innerHTML = statsHtml;
}

function biRenderSlicers() {
  const container = $("#bi-slicers-container");
  if (!container) return;

  // Pick categorical columns with 2 to 12 distinct values, OR columns with an active filter
  const slicerCols = biState.columns.filter((c) => {
    if (biState.activeSlicers[c.name] && biState.activeSlicers[c.name].size > 0) return true;
    if (c.type !== "string" && c.type !== "boolean") return false;
    const distinctVals = new Set(biState.rawData.map((r) => String(r[c.name] ?? ""))).size;
    return distinctVals >= 2 && distinctVals <= 12;
  }).slice(0, 4);

  if (slicerCols.length === 0) {
    container.innerHTML = `<span class="meta" style="font-size:11px;">No categorical slicer fields available for this sheet.</span>`;
    return;
  }

  let html = "";
  slicerCols.forEach((col) => {
    const uniqueVals = Array.from(new Set(biState.rawData.map((r) => String(r[col.name] ?? "")))).filter(Boolean);
    const activeSet = biState.activeSlicers[col.name] || new Set();

    html += `
      <div style="display:flex;align-items:center;gap:4px;background:rgba(255,255,255,0.03);padding:2px 8px;border-radius:6px;border:1px solid var(--border);">
        <span class="meta" style="font-size:11px;font-weight:600;color:var(--accent);">${col.name}:</span>
    `;

    uniqueVals.forEach((val) => {
      const isSelected = activeSet.has(val);
      html += `
        <button type="button" class="bi-slicer-chip ${isSelected ? "active" : ""}" data-col="${col.name}" data-val="${val}">
          ${val}
        </button>
      `;
    });

    html += `</div>`;
  });

  container.innerHTML = html;

  // Slicer chip click toggle
  container.querySelectorAll(".bi-slicer-chip").forEach((btn) => {
    btn.addEventListener("click", () => {
      const col = btn.dataset.col;
      const val = btn.dataset.val;
      if (!biState.activeSlicers[col]) {
        biState.activeSlicers[col] = new Set();
      }
      const set = biState.activeSlicers[col];
      if (set.has(val)) {
        set.delete(val);
      } else {
        set.add(val);
      }
      btn.classList.toggle("active", set.has(val));
      biApplyFilters();
      biUpdateMultiSelectDropdown();
    });
  });

  biPopulateSlicerControls();
  biUpdateMultiSelectDropdown();
}

function biPopulateSlicerControls() {
  const colSelect = $("#bi-slicer-col-select");
  const valInput = $("#bi-slicer-val-input");
  const datalist = $("#bi-slicer-val-datalist");
  const btnApply = $("#btn-bi-slicer-apply-input");
  const btnClear = $("#btn-bi-slicer-clear-input");

  if (!colSelect || !valInput || !datalist) return;

  const strCols = biState.columns.filter((c) => c.type === "string" || c.type === "boolean");
  if (strCols.length === 0) return;

  const prevCol = colSelect.value;
  colSelect.innerHTML = strCols.map((c) => `<option value="${c.name}">${c.name}</option>`).join("");

  if (prevCol && strCols.some((c) => c.name === prevCol)) {
    colSelect.value = prevCol;
  } else {
    const brandCol = strCols.find((c) => /oem|brand|hang|vendor|make|car/i.test(c.name));
    if (brandCol) colSelect.value = brandCol.name;
    else colSelect.value = strCols[0].name;
  }

  const updateDatalist = () => {
    const activeCol = colSelect.value;
    const vals = Array.from(new Set(biState.rawData.map((r) => String(r[activeCol] ?? "")))).filter(Boolean);
    vals.sort();
    datalist.innerHTML = vals.slice(0, 50).map((v) => `<option value="${v}">`).join("");
    valInput.placeholder = `Filter ${activeCol}…`;

    const activeSet = biState.activeSlicers[activeCol];
    if (activeSet && activeSet.size > 0) {
      valInput.value = Array.from(activeSet).join(", ");
      if (btnClear) btnClear.style.display = "inline-block";
    } else {
      valInput.value = "";
      if (btnClear) btnClear.style.display = "none";
    }
  };

  colSelect.onchange = updateDatalist;
  updateDatalist();

  const applyInputFilter = () => {
    const activeCol = colSelect.value;
    const rawText = (valInput.value || "").trim();
    if (!rawText) {
      delete biState.activeSlicers[activeCol];
      if (btnClear) btnClear.style.display = "none";
    } else {
      const exactOrSimilar = Array.from(new Set(biState.rawData.map((r) => String(r[activeCol] ?? ""))))
        .find((v) => v.toLowerCase() === rawText.toLowerCase()) || rawText;
      biState.activeSlicers[activeCol] = new Set([exactOrSimilar]);
      valInput.value = exactOrSimilar;
      if (btnClear) btnClear.style.display = "inline-block";
      toast("Đã lọc", `Lọc ${activeCol} = "${exactOrSimilar}".`, "ok", 2000);
    }
    biApplyFilters();
    biUpdateMultiSelectDropdown();
  };

  if (btnApply) btnApply.onclick = applyInputFilter;
  valInput.onkeydown = (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      applyInputFilter();
    }
  };

  if (btnClear) {
    btnClear.onclick = () => {
      const activeCol = colSelect.value;
      delete biState.activeSlicers[activeCol];
      valInput.value = "";
      btnClear.style.display = "none";
      toast("Đã xóa lọc", `Đã xóa bộ lọc trên '${activeCol}'.`, "info", 1800);
      biApplyFilters();
      biUpdateMultiSelectDropdown();
    };
  }
}

function biUpdateMultiSelectDropdown() {
  const container = $("#bi-multiselect-items");
  const badge = $("#bi-multiselect-badge");
  const title = $("#bi-multiselect-title");
  const searchInput = $("#bi-multiselect-search");
  const btnAll = $("#btn-bi-multiselect-all");
  const btnClear = $("#btn-bi-multiselect-clear");

  if (!container) return;

  const strCols = biState.columns.filter((c) => c.type === "string" || c.type === "boolean");
  const serialColObj = strCols.find((c) => /serial|vin|vehicle|model|series|code|item/i.test(c.name)) || strCols[1] || strCols[0];
  if (!serialColObj) {
    $("#wrap-bi-slicer-multiselect")?.classList.add("hidden");
    return;
  }
  $("#wrap-bi-slicer-multiselect")?.classList.remove("hidden");

  const serialCol = serialColObj.name;
  if (title) title.textContent = `${serialCol}:`;

  const triggerLabel = $("#bi-multiselect-trigger-label");
  if (triggerLabel) triggerLabel.textContent = `☑ ${serialCol}`;

  const contextData = biGetContextData(serialCol);
  const uniqueSerials = Array.from(new Set(contextData.map((r) => String(r[serialCol] ?? "")))).filter(Boolean);
  uniqueSerials.sort();

  const activeSet = biState.activeSlicers[serialCol] || new Set();

  if (badge) {
    badge.textContent = `${activeSet.size} / ${uniqueSerials.length}`;
  }

  if (searchInput) {
    searchInput.placeholder = `🔍 Search ${serialCol}…`;
  }

  const renderItems = (filterQuery = "") => {
    const q = filterQuery.toLowerCase();
    const filteredList = uniqueSerials.filter((s) => !q || s.toLowerCase().includes(q));

    if (filteredList.length === 0) {
      container.innerHTML = `<span class="meta" style="font-size:11px;padding:6px;">No items found.</span>`;
      return;
    }

    container.innerHTML = filteredList.map((val) => {
      const isChecked = activeSet.has(val);
      return `
        <label style="display:flex;align-items:center;gap:6px;font-size:11px;cursor:pointer;padding:3px 6px;border-radius:4px;background:${isChecked ? 'rgba(30,167,253,0.1)' : 'transparent'};">
          <input type="checkbox" class="bi-ms-chk" value="${val}" ${isChecked ? 'checked' : ''} style="cursor:pointer;">
          <span style="${isChecked ? 'font-weight:600;color:var(--accent);' : ''}">${val}</span>
        </label>
      `;
    }).join("");

    container.querySelectorAll(".bi-ms-chk").forEach((chk) => {
      chk.addEventListener("change", () => {
        const val = chk.value;
        if (!biState.activeSlicers[serialCol]) {
          biState.activeSlicers[serialCol] = new Set();
        }
        const set = biState.activeSlicers[serialCol];
        if (chk.checked) set.add(val);
        else set.delete(val);
        if (set.size === 0) delete biState.activeSlicers[serialCol];
        if (badge) badge.textContent = `${set.size} / ${uniqueSerials.length}`;
        biApplyFilters();
      });
    });
  };

  renderItems(searchInput?.value || "");

  if (searchInput) {
    searchInput.oninput = () => renderItems(searchInput.value);
  }

  if (btnAll) {
    btnAll.onclick = () => {
      biState.activeSlicers[serialCol] = new Set(uniqueSerials);
      if (badge) badge.textContent = `${uniqueSerials.length} / ${uniqueSerials.length}`;
      renderItems(searchInput?.value || "");
      biApplyFilters();
    };
  }

  if (btnClear) {
    btnClear.onclick = () => {
      delete biState.activeSlicers[serialCol];
      if (badge) badge.textContent = `0 / ${uniqueSerials.length}`;
      renderItems(searchInput?.value || "");
      biApplyFilters();
    };
  }
}

function biRenderKPICards() {
  const container = $("#bi-kpi-row");
  if (!container) return;

  const data = biState.filteredData;
  const numCols = biState.columns.filter((c) => c.type === "number");
  const strCols = biState.columns.filter((c) => c.type === "string");

  // KPI 1: Total records
  const totalRecords = data.length;
  const isFiltered = totalRecords !== biState.rawData.length;

  // KPI 2: Primary measure SUM
  let kpi2Label = "Primary Metric";
  let kpi2Val = "—";
  let kpi2Sub = "";
  if (numCols.length > 0) {
    const colName = numCols[0].name;
    const sum = data.reduce((acc, r) => acc + (Number(r[colName]) || 0), 0);
    kpi2Label = `Total ${colName}`;
    kpi2Val = biFormatNumber(sum);
    kpi2Sub = `Aggregated SUM across ${totalRecords} records`;
  }

  // KPI 3: Average measure
  let kpi3Label = "Average Metric";
  let kpi3Val = "—";
  let kpi3Sub = "";
  if (numCols.length > 0) {
    const colName = numCols[1] ? numCols[1].name : numCols[0].name;
    const sum = data.reduce((acc, r) => acc + (Number(r[colName]) || 0), 0);
    const avg = totalRecords > 0 ? sum / totalRecords : 0;
    kpi3Label = `Avg ${colName}`;
    kpi3Val = biFormatNumber(avg);
    kpi3Sub = `Average per record`;
  }

  // KPI 4: Top Category / Peak
  let kpi4Label = "Category Peak";
  let kpi4Val = "—";
  let kpi4Sub = "";
  if (strCols.length > 0 && numCols.length > 0) {
    const catCol = strCols[0].name;
    const valCol = numCols[0].name;
    const map = {};
    data.forEach((r) => {
      const c = String(r[catCol] || "Unknown");
      map[c] = (map[c] || 0) + (Number(r[valCol]) || 0);
    });
    let topCat = "—";
    let maxVal = -Infinity;
    for (const [k, v] of Object.entries(map)) {
      if (v > maxVal) { maxVal = v; topCat = k; }
    }
    kpi4Label = `Top ${catCol}`;
    kpi4Val = topCat;
    kpi4Sub = maxVal !== -Infinity ? `Peak: ${biFormatNumber(maxVal)} (${valCol})` : "";
  } else if (strCols.length > 0) {
    const catCol = strCols[0].name;
    const distinct = new Set(data.map((r) => String(r[catCol]))).size;
    kpi4Label = `Unique ${catCol}`;
    kpi4Val = String(distinct);
    kpi4Sub = `Distinct categories`;
  }

  container.innerHTML = `
    <div class="bi-kpi-card" style="border-top-color:#1ea7fd;">
      <div class="bi-kpi-label">Records Count</div>
      <div class="bi-kpi-val">${totalRecords.toLocaleString()}</div>
      <div class="bi-kpi-sub">${isFiltered ? `Filtered from ${biState.rawData.length} total rows` : "Total active records"}</div>
    </div>
    <div class="bi-kpi-card" style="border-top-color:#3fb950;">
      <div class="bi-kpi-label">${kpi2Label}</div>
      <div class="bi-kpi-val">${kpi2Val}</div>
      <div class="bi-kpi-sub">${kpi2Sub}</div>
    </div>
    <div class="bi-kpi-card" style="border-top-color:#a371f7;">
      <div class="bi-kpi-label">${kpi3Label}</div>
      <div class="bi-kpi-val">${kpi3Val}</div>
      <div class="bi-kpi-sub">${kpi3Sub}</div>
    </div>
    <div class="bi-kpi-card" style="border-top-color:#e3b341;">
      <div class="bi-kpi-label">${kpi4Label}</div>
      <div class="bi-kpi-val" style="font-size:20px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${kpi4Val}</div>
      <div class="bi-kpi-sub">${kpi4Sub}</div>
    </div>
  `;
}

function biAggregate(data, xCol, yCol, agg = "sum") {
  const map = {};
  const yColObj = biState.columns.find((c) => c.name === yCol);
  const isNumeric = yColObj ? yColObj.type === "number" : false;
  // If column is text or not numeric, default to 'count' rather than 'sum'
  const effectiveAgg = (!isNumeric && (!agg || agg === "sum")) ? "count" : (agg || "sum");

  data.forEach((r) => {
    const key = String(r[xCol] ?? "—");
    const num = Number(r[yCol]) || 0;
    const rawVal = r[yCol];
    if (!map[key]) map[key] = { key, count: 0, sum: 0, min: Infinity, max: -Infinity, distinctSet: new Set() };
    map[key].count += 1;
    map[key].sum += num;
    if (rawVal !== undefined && rawVal !== null && String(rawVal).trim() !== "") {
      map[key].distinctSet.add(String(rawVal));
    }
    if (num < map[key].min) map[key].min = num;
    if (num > map[key].max) map[key].max = num;
  });

  return Object.values(map).map((g) => {
    let val = 0;
    if (effectiveAgg === "sum") {
      // If sum resulted in 0 but records exist, fall back to record count
      val = g.sum !== 0 ? g.sum : g.count;
    }
    else if (effectiveAgg === "avg") val = g.count > 0 ? (g.sum !== 0 ? g.sum / g.count : 1) : 0;
    else if (effectiveAgg === "count") val = g.count;
    else if (effectiveAgg === "distinct" || effectiveAgg === "distinct_count") val = g.distinctSet.size;
    else if (effectiveAgg === "min") val = g.min !== Infinity ? g.min : 0;
    else if (effectiveAgg === "max") val = g.max !== -Infinity ? g.max : 0;
    return { key: g.key, val: Math.round(val * 100) / 100, count: g.count };
  });
}

function biToggleChartFilter(colName, value) {
  if (!colName || value === undefined || value === null) return;
  const strVal = String(value);

  if (!biState.activeSlicers[colName]) {
    biState.activeSlicers[colName] = new Set();
  }
  const set = biState.activeSlicers[colName];
  if (set.has(strVal)) {
    set.delete(strVal);
    if (set.size === 0) delete biState.activeSlicers[colName];
    toast("Filter Cleared", `Cleared filter on '${colName}'.`, "info", 1800);
  } else {
    // Power BI behavior: clicking a category isolates that category
    set.clear();
    set.add(strVal);
    toast("Cross-Filtered", `Filtered dashboard by ${colName} = "${strVal}"`, "ok", 2200);
  }

  biRenderSlicers();
  biApplyFilters();
}

function biOpenCalcColModal() {
  const modal = $("#modal-bi-calc-col");
  if (!modal) return;
  const nameInput = $("#bi-calc-name");
  const exprInput = $("#bi-calc-expr");
  const chipsContainer = $("#bi-calc-columns-chips");
  if (nameInput) nameInput.value = "";
  if (exprInput) exprInput.value = "";

  if (chipsContainer) {
    chipsContainer.innerHTML = biState.columns.map((c) => {
      const isNum = c.type === "number";
      return `
        <span class="chip" data-col="${c.name}" style="cursor:pointer;font-size:11px;background:${isNum ? 'rgba(30,167,253,0.15)' : 'rgba(255,255,255,0.06)'};color:${isNum ? 'var(--accent)' : 'var(--text)'};">
          ${isNum ? '🔢' : '🔤'} [${c.name}]
        </span>
      `;
    }).join("");

    chipsContainer.querySelectorAll(".chip").forEach((chip) => {
      chip.addEventListener("click", () => {
        const col = chip.dataset.col;
        if (exprInput) {
          exprInput.value += `[${col}]`;
          exprInput.focus();
        }
      });
    });
  }

  // Quick formula template buttons
  $("#bi-calc-templates")?.querySelectorAll("button").forEach((btn) => {
    btn.onclick = () => {
      const numCols = biState.columns.filter((c) => c.type === "number").map((c) => c.name);
      const colA = numCols[0] || "ColA";
      const colB = numCols[1] || numCols[0] || "ColB";
      let tmpl = btn.dataset.template.replace(/\[A\]/g, `[${colA}]`).replace(/\[B\]/g, `[${colB}]`);
      if (exprInput) {
        exprInput.value = tmpl;
        exprInput.focus();
      }
    };
  });

  modal.classList.remove("hidden");
}

function biCreateCalculatedColumn() {
  const nameInput = $("#bi-calc-name");
  const exprInput = $("#bi-calc-expr");
  const colName = (nameInput?.value || "").trim().replace(/\s+/g, "_");
  const expr = (exprInput?.value || "").trim();

  if (!colName) {
    toast("Column Name Required", "Please enter a name for the calculated measure/column.", "err", 3000);
    return;
  }
  if (!expr) {
    toast("Formula Expression Required", "Please enter a valid formula expression (e.g. ([Revenue] - [Cost])).", "err", 3000);
    return;
  }

  // Parse [Column_Name] references
  const usedCols = [];
  const colPattern = /\[([^\]]+)\]/g;
  let match;
  while ((match = colPattern.exec(expr)) !== null) {
    usedCols.push(match[1]);
  }

  if (usedCols.length === 0) {
    toast("Invalid Expression", "Expression must reference at least one [Column_Name].", "err", 3000);
    return;
  }

  for (const c of usedCols) {
    if (!biState.columns.some((col) => col.name === c)) {
      toast("Column Not Found", `Referenced column '[${c}]' does not exist in dataset.`, "err", 3500);
      return;
    }
  }

  const evalRow = (row) => {
    let sanitized = expr;
    for (const c of usedCols) {
      const rawVal = row[c];
      const numVal = (typeof rawVal === "number") ? rawVal : (parseFloat(rawVal) || 0);
      sanitized = sanitized.split(`[${c}]`).join(String(numVal));
    }
    if (!/^[0-9\.\+\-\*\/\(\)\s]+$/.test(sanitized)) {
      throw new Error("Formula contains invalid characters. Only math operators allowed (+, -, *, /, ()).");
    }
    try {
      const res = Function(`"use strict"; return (${sanitized});`)();
      if (!isFinite(res) || isNaN(res)) return 0;
      return Number(res.toFixed(2));
    } catch {
      return 0;
    }
  };

  try {
    let successCount = 0;
    biState.rawData.forEach((row) => {
      row[colName] = evalRow(row);
      successCount++;
    });

    if (biState.activeSheet && biState.allSheets[biState.activeSheet]) {
      const sheetData = biState.allSheets[biState.activeSheet].data || [];
      sheetData.forEach((row) => {
        row[colName] = evalRow(row);
      });
    }

    if (!biState.columns.some((c) => c.name === colName)) {
      biState.columns.push({ name: colName, type: "number", isCustom: true, count: successCount, non_null_count: successCount });
    }

    $("#modal-bi-calc-col")?.classList.add("hidden");
    toast("Measure Created", `Calculated column '${colName}' computed for ${successCount} records.`, "ok", 3500);

    biRenderFieldsList();
    biApplyFilters();
  } catch (err) {
    toast("Calculation Error", err.message, "err", 4000);
  }
}

function biRenderVisuals() {
  const grid = $("#bi-visuals-grid");
  if (!grid) return;

  if (!biState.visuals || biState.visuals.length === 0) {
    grid.innerHTML = `
      <div class="bi-empty-visuals-banner" style="grid-column:1/-1;text-align:center;padding:48px 24px;background:var(--bg-card,rgba(255,255,255,0.02));border:1px dashed var(--border);border-radius:10px;margin:16px 0;">
        <div style="font-size:38px;margin-bottom:12px;">⚙️</div>
        <div style="font-size:16px;font-weight:700;color:var(--text);margin-bottom:6px;">Chưa có cấu hình biểu đồ (No Visuals Configured)</div>
        <div class="meta" style="font-size:12px;max-width:540px;margin:0 auto 18px auto;line-height:1.6;">
          BI Studio không tự ý vẽ biểu đồ ngẫu nhiên. Hãy tải lên file cấu hình JSON của bạn, tự thêm biểu đồ theo ý muốn, hoặc bấm <strong>Gợi ý biểu đồ mẫu</strong> để tạo nhanh bộ biểu đồ.
        </div>
        <div style="display:flex;gap:10px;justify-content:center;flex-wrap:wrap;">
          <label class="btn primary" style="cursor:pointer;font-size:12px;" title="Upload JSON config file">
            📂 Tải lên Config JSON
            <input type="file" id="bi-config-file-input-banner" accept=".json" style="display:none;">
          </label>
          <button type="button" class="btn" id="btn-bi-add-visual-banner" style="font-size:12px;">＋ Thêm biểu đồ tùy biến</button>
          <button type="button" class="btn ghost" id="btn-bi-auto-generate-banner" style="font-size:12px;" title="Gợi ý tự động 4 biểu đồ mẫu theo các cột số và phân loại">🪄 Gợi ý biểu đồ mẫu</button>
        </div>
      </div>
    `;

    // Attach listeners for banner buttons
    $("#bi-config-file-input-banner")?.addEventListener("change", (e) => {
      const file = e.target.files?.[0];
      if (file) biImportConfigJson(file);
    });
    $("#btn-bi-add-visual-banner")?.addEventListener("click", () => biOpenAddVisualModal());
    $("#btn-bi-auto-generate-banner")?.addEventListener("click", () => {
      biAutoGenerateVisuals();
      toast("Đã tạo biểu đồ mẫu", "Tự động sinh 4 biểu đồ mẫu dựa trên dữ liệu hiện tại.", "ok", 2500);
    });
    return;
  }

  grid.innerHTML = biState.visuals.map((vis, idx) => {
    let typeIcon = "📊";
    if (vis.type === "combo") typeIcon = "📊📈";
    else if (vis.type === "hbar") typeIcon = "📶";
    else if (vis.type === "line") typeIcon = "📈";
    else if (vis.type === "pie") typeIcon = "🍩";
    else if (vis.type === "table") typeIcon = "▦";

    const isWide = !!vis.isWide;
    return `
      <div class="bi-visual-card ${isWide ? 'wide' : ''}" id="card-${vis.id}" data-id="${vis.id}" data-idx="${idx}" draggable="true">
        <div class="bi-visual-head">
          <div class="bi-visual-title">
            <span class="bi-drag-handle" title="Drag to reorder card">⋮⋮</span>
            <span>${typeIcon}</span>
            <span>${vis.title || "Visual"}</span>
          </div>
          <div class="bi-visual-actions">
            <button class="btn btn-xs ghost btn-vis-focus" title="Toggle 1-column / 2-column width" data-id="${vis.id}">⤢</button>
            <button class="btn btn-xs ghost btn-vis-del" title="Remove visual" data-id="${vis.id}">✕</button>
          </div>
        </div>
        <div class="bi-visual-body" id="body-${vis.id}">
          <!-- Chart SVG or Table dynamically injected -->
        </div>
        <div class="bi-visual-foot">
          <span>${vis.type.toUpperCase()} · ${vis.agg ? vis.agg.toUpperCase() : "GRID"}</span>
          <span class="meta">${biState.filteredData.length} active records</span>
        </div>
      </div>
    `;
  }).join("");

  // Attach card header actions: toggle 1x / 2x width
  grid.querySelectorAll(".btn-vis-focus").forEach((b) => {
    b.addEventListener("click", () => {
      const vis = biState.visuals.find((v) => v.id === b.dataset.id);
      if (vis) {
        vis.isWide = !vis.isWide;
        const card = $(`#card-${b.dataset.id}`);
        card?.classList.toggle("wide", vis.isWide);
        toast("Card Resized", vis.isWide ? "Expanded visual to full width (2 columns)." : "Collapsed visual to standard width (1 column).", "info", 1500);
      }
    });
  });

  // Delete card
  grid.querySelectorAll(".btn-vis-del").forEach((b) => {
    b.addEventListener("click", () => {
      biState.visuals = biState.visuals.filter((v) => v.id !== b.dataset.id);
      biRenderVisuals();
    });
  });

  // Drag and Drop card reordering
  let draggedCardId = null;
  grid.querySelectorAll(".bi-visual-card").forEach((card) => {
    card.addEventListener("dragstart", (e) => {
      draggedCardId = card.dataset.id;
      card.classList.add("dragging");
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", draggedCardId);
    });

    card.addEventListener("dragend", () => {
      card.classList.remove("dragging");
      grid.querySelectorAll(".bi-visual-card").forEach((c) => c.classList.remove("drag-over"));
    });

    card.addEventListener("dragover", (e) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      card.classList.add("drag-over");
    });

    card.addEventListener("dragleave", () => {
      card.classList.remove("drag-over");
    });

    card.addEventListener("drop", (e) => {
      e.preventDefault();
      card.classList.remove("drag-over");
      const targetId = card.dataset.id;
      if (!draggedCardId || draggedCardId === targetId) return;

      const fromIdx = biState.visuals.findIndex((v) => v.id === draggedCardId);
      const toIdx = biState.visuals.findIndex((v) => v.id === targetId);
      if (fromIdx !== -1 && toIdx !== -1) {
        const [moved] = biState.visuals.splice(fromIdx, 1);
        biState.visuals.splice(toIdx, 0, moved);
        biRenderVisuals();
        toast("Layout Updated", `Reordered '${moved.title}' card.`, "info", 1500);
      }
    });
  });

  // Render each visual
  biState.visuals.forEach((vis) => {
    const el = $(`#body-${vis.id}`);
    if (!el) return;

    if (vis.type === "combo") {
      biRenderComboChart(el, vis);
    } else if (vis.type === "bar") {
      biRenderBarChart(el, vis, false);
    } else if (vis.type === "hbar") {
      biRenderBarChart(el, vis, true);
    } else if (vis.type === "line") {
      biRenderLineChart(el, vis);
    } else if (vis.type === "pie") {
      biRenderDonutChart(el, vis);
    } else if (vis.type === "table") {
      biRenderTable(el, vis);
    }
  });
}

function biPositionTooltip(e, tip) {
  const rect = tip.getBoundingClientRect();
  const tipW = rect.width || 240;
  const tipH = rect.height || 80;
  let left = e.clientX + 14;
  let top = e.clientY + 14;
  if (left + tipW > window.innerWidth - 12) {
    left = Math.max(10, e.clientX - tipW - 14);
  }
  if (top + tipH > window.innerHeight - 12) {
    top = Math.max(10, e.clientY - tipH - 14);
  }
  tip.style.left = `${left}px`;
  tip.style.top = `${top}px`;
}

function biShowTooltip(e, title, val1, val2 = null, extraHtml = "") {
  const tip = biState.tooltipEl;
  if (!tip) return;
  let html = `<div style="font-weight:700;margin-bottom:2px;">${title}</div>`;
  if (val1) html += `<div>${val1}</div>`;
  if (val2) html += `<div>${val2}</div>`;
  if (extraHtml) {
    html += `<div style="margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.15);">${extraHtml}</div>`;
  }
  tip.innerHTML = html;
  tip.style.display = "block";
  biPositionTooltip(e, tip);
}

function biMoveTooltip(e) {
  const tip = biState.tooltipEl;
  if (!tip || tip.style.display === "none") return;
  biPositionTooltip(e, tip);
}

function biHideTooltip() {
  if (biState.tooltipEl) biState.tooltipEl.style.display = "none";
}

function biRenderComboChart(container, vis) {
  const data = biState.filteredData;
  const groups1 = biAggregate(data, vis.x, vis.y, vis.agg);
  const groups2 = vis.y2 ? biAggregate(data, vis.x, vis.y2, vis.agg) : [];
  const map2 = {};
  groups2.forEach((g) => { map2[g.key] = g.val; });

  const categories = groups1.slice(0, 10);
  if (categories.length === 0) {
    container.innerHTML = `<span class="meta">No data matching active filters.</span>`;
    return;
  }

  const maxBar = Math.max(...categories.map((c) => c.val), 1);
  const maxLine = Math.max(...categories.map((c) => map2[c.key] || 0), 1);

  const w = 500;
  const h = 260;
  const pad = { top: 30, right: 40, bottom: 50, left: 50 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;
  const barW = Math.max(12, Math.min(32, (chartW / categories.length) * 0.55));

  let svg = `<svg class="bi-chart-svg" viewBox="0 0 ${w} ${h}">`;

  // Gridlines
  for (let i = 0; i <= 4; i++) {
    const yPos = pad.top + (chartH / 4) * i;
    const valBar = Math.round(maxBar * (1 - i / 4));
    svg += `
      <line x1="${pad.left}" y1="${yPos}" x2="${w - pad.right}" y2="${yPos}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="3"/>
      <text x="${pad.left - 8}" y="${yPos + 4}" fill="var(--text-dim)" font-size="10" text-anchor="end">${biFormatNumber(valBar)}</text>
    `;
  }

  // Bars (Measure 1)
  const linePoints = [];
  const activeFilterSet = biState.activeSlicers[vis.x];
  const isFiltered = activeFilterSet && activeFilterSet.size > 0;

  categories.forEach((cat, idx) => {
    const xCenter = pad.left + (chartW / categories.length) * (idx + 0.5);
    const bHeight = (cat.val / maxBar) * chartH;
    const yTop = pad.top + chartH - bHeight;
    const xBar = xCenter - barW / 2;
    const isSelected = isFiltered && activeFilterSet.has(cat.key);
    const opacity = isFiltered ? (isSelected ? "1.0" : "0.25") : "0.85";
    const strokeAttr = isSelected ? `stroke="#ffffff" stroke-width="2.5"` : "";

    svg += `
      <rect class="bi-bar-rect" x="${xBar}" y="${yTop}" width="${barW}" height="${bHeight}" fill="${BI_PALETTES[0]}" rx="3"
        ${strokeAttr}
        data-cat="${cat.key}" data-val1="${cat.val}" data-val2="${map2[cat.key] || 0}" style="cursor:pointer;transition:all 0.15s;opacity:${opacity};">
      </rect>
      <text x="${xCenter}" y="${h - pad.bottom + 16}" fill="${isSelected ? 'var(--text)' : 'var(--text-dim)'}" font-size="10" font-weight="${isSelected ? '700' : '400'}" text-anchor="middle"
        transform="rotate(0, ${xCenter}, ${h - pad.bottom + 16})">${cat.key.length > 9 ? cat.key.substring(0, 8) + '…' : cat.key}</text>
    `;

    // Measure 2 (Line point)
    const val2 = map2[cat.key] || 0;
    const yLine = pad.top + chartH - (val2 / maxBar) * chartH; // or scale to maxLine
    linePoints.push({ x: xCenter, y: yLine, val2, cat: cat.key });
  });

  // Polyline for Measure 2
  if (linePoints.length > 1) {
    const ptsStr = linePoints.map((p) => `${p.x},${p.y}`).join(" ");
    svg += `<polyline points="${ptsStr}" fill="none" stroke="${BI_PALETTES[2]}" stroke-width="3" stroke-linecap="round"/>`;
  }

  // Circles for line points
  linePoints.forEach((p) => {
    svg += `
      <circle cx="${p.x}" cy="${p.y}" r="4" fill="${BI_PALETTES[2]}" stroke="#fff" stroke-width="1.5"
        data-cat="${p.cat}" data-val2="${p.val2}" style="cursor:pointer;"></circle>
    `;
  });

  svg += `</svg>`;
  container.innerHTML = svg;

  // Tooltip & Cross-Filter click wiring
  container.querySelectorAll(".bi-bar-rect, circle").forEach((el) => {
    el.addEventListener("click", () => {
      if (el.dataset.cat) biToggleChartFilter(vis.x, el.dataset.cat);
    });
    el.addEventListener("mouseenter", (e) => {
      const cat = el.dataset.cat;
      const v1 = el.dataset.val1 ? `${vis.y}: <b>${biFormatNumber(Number(el.dataset.val1))}</b>` : "";
      const v2 = el.dataset.val2 ? `${vis.y2 || "Metric 2"}: <b>${biFormatNumber(Number(el.dataset.val2))}</b>` : "";
      biShowTooltip(e, cat, v1, v2);
    });
    el.addEventListener("mousemove", (e) => {
      if (biState.tooltipEl) {
        biState.tooltipEl.style.left = `${e.clientX + 12}px`;
        biState.tooltipEl.style.top = `${e.clientY + 12}px`;
      }
    });
    el.addEventListener("mouseleave", () => biHideTooltip());
  });
}

function biRenderBarChart(container, vis, isHorizontal = false) {
  const data = biState.filteredData;
  const groups = biAggregate(data, vis.x, vis.y, vis.agg);
  groups.sort((a, b) => b.val - a.val);
  const items = groups.slice(0, isHorizontal ? 8 : 10);

  if (items.length === 0) {
    container.innerHTML = `<span class="meta">No data available.</span>`;
    return;
  }

  const maxVal = Math.max(...items.map((i) => i.val), 1);
  const w = 500;
  const h = 260;

  const activeFilterSet = biState.activeSlicers[vis.x];
  const isFiltered = activeFilterSet && activeFilterSet.size > 0;

  if (isHorizontal) {
    const pad = { top: 20, right: 50, bottom: 20, left: 110 };
    const chartW = w - pad.left - pad.right;
    const barH = Math.max(14, Math.min(24, ((h - pad.top - pad.bottom) / items.length) * 0.7));

    let svg = `<svg class="bi-chart-svg" viewBox="0 0 ${w} ${h}">`;
    items.forEach((item, idx) => {
      const yCenter = pad.top + ((h - pad.top - pad.bottom) / items.length) * (idx + 0.5);
      const bWidth = (item.val / maxVal) * chartW;
      const color = BI_PALETTES[idx % BI_PALETTES.length];
      const isSelected = isFiltered && activeFilterSet.has(item.key);
      const opacity = isFiltered ? (isSelected ? "1.0" : "0.25") : "0.9";
      const strokeAttr = isSelected ? `stroke="#ffffff" stroke-width="2.5"` : "";

      svg += `
        <text x="${pad.left - 8}" y="${yCenter + 4}" fill="${isSelected ? 'var(--text)' : 'var(--text-dim)'}" font-size="10.5" font-weight="${isSelected ? '700' : '400'}" text-anchor="end">${item.key.length > 14 ? item.key.slice(0, 13) + '…' : item.key}</text>
        <rect class="bi-bar-rect" x="${pad.left}" y="${yCenter - barH / 2}" width="${bWidth}" height="${barH}" fill="${color}" rx="3"
          ${strokeAttr}
          data-cat="${item.key}" data-val="${item.val}" style="cursor:pointer;opacity:${opacity};transition:all 0.15s;"></rect>
        <text x="${pad.left + bWidth + 6}" y="${yCenter + 4}" fill="var(--text)" font-size="10" font-weight="600">${biFormatNumber(item.val)}</text>
      `;
    });
    svg += `</svg>`;
    container.innerHTML = svg;
  } else {
    // Vertical Column
    const pad = { top: 30, right: 30, bottom: 50, left: 50 };
    const chartW = w - pad.left - pad.right;
    const chartH = h - pad.top - pad.bottom;
    const barW = Math.max(12, Math.min(32, (chartW / items.length) * 0.6));

    let svg = `<svg class="bi-chart-svg" viewBox="0 0 ${w} ${h}">`;
    for (let i = 0; i <= 4; i++) {
      const yPos = pad.top + (chartH / 4) * i;
      svg += `
        <line x1="${pad.left}" y1="${yPos}" x2="${w - pad.right}" y2="${yPos}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="3"/>
        <text x="${pad.left - 8}" y="${yPos + 4}" fill="var(--text-dim)" font-size="10" text-anchor="end">${biFormatNumber(Math.round(maxVal * (1 - i / 4)))}</text>
      `;
    }

    items.forEach((item, idx) => {
      const xCenter = pad.left + (chartW / items.length) * (idx + 0.5);
      const bHeight = (item.val / maxVal) * chartH;
      const yTop = pad.top + chartH - bHeight;
      const color = BI_PALETTES[idx % BI_PALETTES.length];
      const isSelected = isFiltered && activeFilterSet.has(item.key);
      const opacity = isFiltered ? (isSelected ? "1.0" : "0.25") : "0.9";
      const strokeAttr = isSelected ? `stroke="#ffffff" stroke-width="2.5"` : "";

      svg += `
        <rect class="bi-bar-rect" x="${xCenter - barW / 2}" y="${yTop}" width="${barW}" height="${bHeight}" fill="${color}" rx="3"
          ${strokeAttr}
          data-cat="${item.key}" data-val="${item.val}" style="cursor:pointer;opacity:${opacity};transition:all 0.15s;"></rect>
        <text x="${xCenter}" y="${h - pad.bottom + 16}" fill="${isSelected ? 'var(--text)' : 'var(--text-dim)'}" font-size="10" font-weight="${isSelected ? '700' : '400'}" text-anchor="middle">${item.key.length > 9 ? item.key.slice(0, 8) + '…' : item.key}</text>
      `;
    });
    svg += `</svg>`;
    container.innerHTML = svg;
  }

  // Tooltip & Cross-Filter click wiring
  container.querySelectorAll(".bi-bar-rect").forEach((el) => {
    el.addEventListener("click", () => {
      if (el.dataset.cat) biToggleChartFilter(vis.x, el.dataset.cat);
    });
    el.addEventListener("mouseenter", (e) => {
      biShowTooltip(e, el.dataset.cat, `${vis.y}: <b>${biFormatNumber(Number(el.dataset.val))}</b>`);
    });
    el.addEventListener("mousemove", (e) => {
      if (biState.tooltipEl) {
        biState.tooltipEl.style.left = `${e.clientX + 12}px`;
        biState.tooltipEl.style.top = `${e.clientY + 12}px`;
      }
    });
    el.addEventListener("mouseleave", () => biHideTooltip());
  });
}

function biRenderLineChart(container, vis) {
  const data = biState.filteredData;
  const groups = biAggregate(data, vis.x, vis.y, vis.agg);
  const items = groups.slice(0, 14);

  if (items.length === 0) {
    container.innerHTML = `<span class="meta">No data available.</span>`;
    return;
  }

  const maxVal = Math.max(...items.map((i) => i.val), 1);
  const minVal = Math.min(...items.map((i) => i.val), 0);
  const range = maxVal - minVal || 1;

  const w = 500;
  const h = 260;
  const pad = { top: 30, right: 30, bottom: 50, left: 50 };
  const chartW = w - pad.left - pad.right;
  const chartH = h - pad.top - pad.bottom;

  let svg = `
    <svg class="bi-chart-svg" viewBox="0 0 ${w} ${h}">
      <defs>
        <linearGradient id="lineGrad-${vis.id}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="${BI_PALETTES[0]}" stop-opacity="0.35"/>
          <stop offset="100%" stop-color="${BI_PALETTES[0]}" stop-opacity="0.0"/>
        </linearGradient>
      </defs>
  `;

  // Grid
  for (let i = 0; i <= 4; i++) {
    const yPos = pad.top + (chartH / 4) * i;
    svg += `
      <line x1="${pad.left}" y1="${yPos}" x2="${w - pad.right}" y2="${yPos}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="3"/>
      <text x="${pad.left - 8}" y="${yPos + 4}" fill="var(--text-dim)" font-size="10" text-anchor="end">${biFormatNumber(Math.round(maxVal - (range / 4) * i))}</text>
    `;
  }

  const points = items.map((item, idx) => {
    const x = pad.left + (chartW / (items.length - 1 || 1)) * idx;
    const y = pad.top + chartH - ((item.val - minVal) / range) * chartH;
    return { x, y, item };
  });

  // Area under curve
  const areaPath = `M ${points[0].x} ${pad.top + chartH} ` +
    points.map((p) => `L ${p.x} ${p.y}`).join(" ") +
    ` L ${points[points.length - 1].x} ${pad.top + chartH} Z`;
  svg += `<path d="${areaPath}" fill="url(#lineGrad-${vis.id})"/>`;

  // Main line
  const linePath = `M ` + points.map((p) => `${p.x} ${p.y}`).join(" L ");
  svg += `<path d="${linePath}" fill="none" stroke="${BI_PALETTES[0]}" stroke-width="2.5" stroke-linecap="round"/>`;

  // Dots & Labels
  points.forEach((p) => {
    svg += `
      <circle class="bi-line-point" cx="${p.x}" cy="${p.y}" r="4.5" fill="${BI_PALETTES[0]}" stroke="#fff" stroke-width="1.5"
        data-cat="${p.item.key}" data-val="${p.item.val}" style="cursor:pointer;"></circle>
      <text x="${p.x}" y="${h - pad.bottom + 16}" fill="var(--text-dim)" font-size="10" text-anchor="middle">${p.item.key.length > 8 ? p.item.key.slice(0, 7) + '…' : p.item.key}</text>
    `;
  });

  svg += `</svg>`;
  container.innerHTML = svg;

  container.querySelectorAll(".bi-line-point").forEach((el) => {
    el.addEventListener("mouseenter", (e) => {
      biShowTooltip(e, el.dataset.cat, `${vis.y}: <b>${biFormatNumber(Number(el.dataset.val))}</b>`);
    });
    el.addEventListener("mousemove", (e) => {
      if (biState.tooltipEl) {
        biState.tooltipEl.style.left = `${e.clientX + 12}px`;
        biState.tooltipEl.style.top = `${e.clientY + 12}px`;
      }
    });
    el.addEventListener("mouseleave", () => biHideTooltip());
  });
}

function biRenderDonutChart(container, vis) {
  // Check active filter on vis.x or matching key case-insensitively
  let filterKey = vis.x;
  let activeFilterSet = biState.activeSlicers[vis.x];
  if (!activeFilterSet || activeFilterSet.size === 0) {
    const normX = (vis.x || "").toLowerCase().replace(/[\s_-]+/g, "");
    const k = Object.keys(biState.activeSlicers).find(
      (key) => key.toLowerCase().replace(/[\s_-]+/g, "") === normX
    );
    if (k) {
      filterKey = k;
      activeFilterSet = biState.activeSlicers[k];
    }
  }
  const isFiltered = activeFilterSet && activeFilterSet.size > 0;

  // Context data without the filter on filterKey (e.g. preserves OEM='TOYOTA', but keeps all 14 serials)
  const contextData = biGetContextData(filterKey);
  const contextGroups = biAggregate(contextData, vis.x, vis.y, vis.agg);
  contextGroups.sort((a, b) => b.val - a.val);

  const yColObj = biState.columns.find((c) => c.name === vis.y);
  const isNumericMeasure = yColObj && yColObj.type === "number" && vis.y !== vis.x && vis.agg !== "count" && vis.agg !== "distinct";
  const hasMetric = Boolean(vis.y && vis.y !== vis.x);
  const unitLabel = /serial|series/i.test(vis.x) ? "serials" : (/vin/i.test(vis.x) ? "VINs" : "mục");

  let items = [];
  let total = 0;
  let isSelectionRatioMode = false;
  let selectedVal = 0;
  let remainingVal = 0;

  if (isFiltered && contextGroups.length > activeFilterSet.size) {
    isSelectionRatioMode = true;
    const selectedList = contextGroups.filter((g) => activeFilterSet.has(g.key));
    const remainingList = contextGroups.filter((g) => !activeFilterSet.has(g.key));

    if (hasMetric) {
      selectedVal = selectedList.reduce((acc, i) => acc + i.val, 0);
      remainingVal = remainingList.reduce((acc, i) => acc + i.val, 0);
      total = selectedVal + remainingVal;
    } else {
      // Measuring proportion of distinct items/serials (e.g. 7 selected out of 14 total serials = 50%)
      selectedVal = selectedList.length;
      remainingVal = remainingList.length;
      total = contextGroups.length;
    }

    if (selectedList.length <= 4) {
      items = [
        ...selectedList.map((s, idx) => ({
          ...s,
          val: hasMetric ? s.val : 1,
          isSelected: true,
          color: BI_PALETTES[idx % BI_PALETTES.length],
          subKeys: [s.key],
        })),
        {
          key: `Remaining (${remainingList.length} other ${unitLabel})`,
          val: remainingVal,
          isSelected: false,
          isRemaining: true,
          color: "#475569",
          subKeys: remainingList.map((r) => r.key),
        },
      ];
    } else {
      items = [
        {
          key: `Selected (${selectedList.length} ${unitLabel})`,
          val: selectedVal,
          isSelected: true,
          color: "#10b981",
          subKeys: selectedList.map((s) => s.key),
        },
        {
          key: `Remaining (${remainingList.length} ${unitLabel})`,
          val: remainingVal,
          isSelected: false,
          isRemaining: true,
          color: "#475569",
          subKeys: remainingList.map((r) => r.key),
        },
      ];
    }
  } else {
    // Normal mode (no selection subset): show distribution of all or top items
    if (contextGroups.length <= 7) {
      items = contextGroups.map((item) => ({
        ...item,
        subKeys: [item.key],
      }));
    } else {
      const top6 = contextGroups.slice(0, 6);
      const rest = contextGroups.slice(6);
      const restVal = rest.reduce((acc, i) => acc + i.val, 0);
      items = [
        ...top6.map((item) => ({ ...item, subKeys: [item.key] })),
        {
          key: `Other (${rest.length} ${unitLabel})`,
          val: restVal,
          color: "#475569",
          subKeys: rest.map((r) => r.key),
        },
      ];
    }
    total = contextGroups.reduce((acc, i) => acc + i.val, 0);
  }

  if (total <= 0) {
    container.innerHTML = `<span class="meta" style="display:block;text-align:center;padding:40px 10px;">No distribution data available.</span>`;
    return;
  }

      const cx = 130;
      const cy = 130;
      const r = 90;
      const innerR = 55;

      let currentAngle = -Math.PI / 2;
      let svg = `<svg class="bi-chart-svg" viewBox="0 0 460 260">`;

      // Slices
      items.forEach((item, idx) => {
        const sliceAngle = (item.val / total) * (Math.PI * 2);
        const startAngle = currentAngle;
        const endAngle = currentAngle + sliceAngle;
        currentAngle = endAngle;

        const x1 = cx + r * Math.cos(startAngle);
        const y1 = cy + r * Math.sin(startAngle);
        const x2 = cx + r * Math.cos(endAngle);
        const y2 = cy + r * Math.sin(endAngle);

        const ix1 = cx + innerR * Math.cos(endAngle);
        const iy1 = cy + innerR * Math.sin(endAngle);
        const ix2 = cx + innerR * Math.cos(startAngle);
        const iy2 = cy + innerR * Math.sin(startAngle);

        const largeArc = sliceAngle > Math.PI ? 1 : 0;
        const pathData = `
      M ${x1} ${y1}
      A ${r} ${r} 0 ${largeArc} 1 ${x2} ${y2}
      L ${ix1} ${iy1}
      A ${innerR} ${innerR} 0 ${largeArc} 0 ${ix2} ${iy2}
      Z
    `;

        const color = item.color || BI_PALETTES[idx % BI_PALETTES.length];
        const pct = ((item.val / total) * 100).toFixed(1);
        const isSelected = item.isRemaining ? false : (isFiltered ? activeFilterSet.has(item.key) : false);
        const opacity = isSelectionRatioMode ? (item.isRemaining ? "0.45" : "1.0") : (isFiltered ? (isSelected ? "1.0" : "0.25") : "0.92");
        const strokeAttr = (isSelected || (isSelectionRatioMode && !item.isRemaining)) ? `stroke="#ffffff" stroke-width="2.5"` : `stroke="#1e1e2e" stroke-width="2"`;

        svg += `
      <path class="bi-donut-slice" d="${pathData}" fill="${color}" ${strokeAttr}
        data-cat="${item.key}" data-val="${item.val}" data-pct="${pct}" data-idx="${idx}" style="cursor:pointer;opacity:${opacity};transition:all 0.15s;"></path>
    `;
      });

      // Center text & badge (English labels)
      if (isSelectionRatioMode) {
        const selectedPct = total > 0 ? ((selectedVal / total) * 100).toFixed(0) : 0;
        const centerDisplayVal = hasMetric
          ? `${biFormatNumber(selectedVal)} / ${biFormatNumber(total)}`
          : `${selectedVal} / ${total} ${unitLabel}`;
        svg += `
      <g class="bi-donut-center" style="cursor:pointer;">
        <circle cx="${cx}" cy="${cy}" r="${innerR - 2}" fill="transparent" pointer-events="all"/>
        <text x="${cx}" y="${cy - 4}" fill="#10b981" font-size="11" font-weight="700" text-anchor="middle" pointer-events="none">SELECTED ${selectedPct}%</text>
        <text x="${cx}" y="${cy + 15}" fill="var(--text)" font-size="12" font-weight="700" text-anchor="middle" pointer-events="none">${centerDisplayVal}</text>
      </g>
    `;
      } else {
        svg += `
      <g class="bi-donut-center">
        <text x="${cx}" y="${cy - 2}" fill="var(--text-dim)" font-size="11" text-anchor="middle">TOTAL</text>
        <text x="${cx}" y="${cy + 16}" fill="var(--text)" font-size="14" font-weight="700" text-anchor="middle">${biFormatNumber(total)}</text>
      </g>
    `;
      }

      // Legend on right
      const legendX = 250;
      items.forEach((item, idx) => {
        const ly = 40 + idx * 26;
        const color = item.color || BI_PALETTES[idx % BI_PALETTES.length];
        const pct = ((item.val / total) * 100).toFixed(1);
        const isSelected = item.isRemaining ? false : (isFiltered ? activeFilterSet.has(item.key) : false);
        const opacity = isSelectionRatioMode ? (item.isRemaining ? "0.65" : "1.0") : (isFiltered ? (isSelected ? "1.0" : "0.35") : "1.0");

        svg += `
      <g class="bi-donut-legend-item" data-cat="${item.key}" data-idx="${idx}" style="cursor:pointer;opacity:${opacity};">
        <rect x="${legendX}" y="${ly - 9}" width="12" height="12" rx="3" fill="${color}"/>
        <text x="${legendX + 18}" y="${ly}" fill="var(--text)" font-size="11" font-weight="${isSelected || (isSelectionRatioMode && !item.isRemaining) ? '700' : '500'}">${item.key.length > 17 ? item.key.slice(0, 16) + '…' : item.key}</text>
        <text x="${legendX + 175}" y="${ly}" fill="var(--text-dim)" font-size="10.5" text-anchor="end">${pct}% (${biFormatNumber(item.val)})</text>
      </g>
    `;
      });

      svg += `</svg>`;
      container.innerHTML = svg;

      // Tooltip & Cross-Filter click wiring
      container.querySelectorAll(".bi-donut-slice, .bi-donut-legend-item").forEach((el) => {
        el.addEventListener("click", () => {
          const cat = el.dataset.cat;
          if (cat && !cat.startsWith("Remaining") && !cat.startsWith("Phần còn lại") && !cat.startsWith("Other") && !cat.startsWith("Khác")) {
            biToggleChartFilter(vis.x, cat);
          }
        });

        el.addEventListener("mouseenter", (e) => {
          const idx = Number(el.dataset.idx);
          const item = items[idx];
          if (!item) return;

          const pct = ((item.val / total) * 100).toFixed(1);
          let extraHtml = "";

          if (item.subKeys && item.subKeys.length > 0) {
            const keys = item.subKeys;
            if (item.isRemaining) {
              const maxShow = 20;
              const showKeys = keys.slice(0, maxShow);
              const extraCount = keys.length - maxShow;
              const badges = showKeys
                .map((k) => `<span style="background:rgba(255,255,255,0.12);color:#e2e8f0;padding:2px 6px;border-radius:4px;font-size:10px;font-family:monospace;display:inline-block;">${k}</span>`)
                .join(" ");
              extraHtml = `
            <div style="margin-top:2px;">
              <div style="color:var(--text-dim);font-weight:600;margin-bottom:5px;font-size:10.5px;">Remaining items (${keys.length}):</div>
              <div style="display:flex;flex-wrap:wrap;gap:4px;max-height:160px;overflow-y:auto;padding-right:2px;">
                ${badges}
                ${extraCount > 0 ? `<span style="color:var(--accent);font-size:10px;padding:2px 4px;font-style:italic;">+${extraCount} more…</span>` : ""}
              </div>
            </div>
          `;
            } else if (item.isSelected && keys.length > 1) {
              const badges = keys
                .slice(0, 15)
                .map((k) => `<span style="background:rgba(16,185,129,0.22);color:#34d399;padding:2px 6px;border-radius:4px;font-size:10px;font-family:monospace;display:inline-block;">${k}</span>`)
                .join(" ");
              extraHtml = `
            <div style="margin-top:2px;">
              <div style="color:#10b981;font-weight:600;margin-bottom:5px;font-size:10.5px;">Selected items (${keys.length}):</div>
              <div style="display:flex;flex-wrap:wrap;gap:4px;max-height:140px;overflow-y:auto;padding-right:2px;">${badges}</div>
            </div>
          `;
            }
          }

      const titlePrefix = item.isRemaining ? "⚪ " : "🟢 ";
      biShowTooltip(
        e,
        `${titlePrefix}${item.key}`,
        `Value: <b>${biFormatNumber(item.val)}</b>`,
        `Share: <b>${pct}%</b>`,
        extraHtml
      );
    });

    el.addEventListener("mousemove", (e) => biMoveTooltip(e));
    el.addEventListener("mouseleave", () => biHideTooltip());
  });

  // Center circle tooltip (summary of selected vs remaining)
  const centerEl = container.querySelector(".bi-donut-center");
  if (centerEl && isSelectionRatioMode) {
    centerEl.addEventListener("mouseenter", (e) => {
      const selectedList = contextGroups.filter((g) => activeFilterSet.has(g.key));
      const remainingList = contextGroups.filter((g) => !activeFilterSet.has(g.key));
      const selectedPct = ((selectedVal / total) * 100).toFixed(0);

      const selBadges = selectedList
        .slice(0, 8)
        .map((g) => `<span style="background:rgba(16,185,129,0.22);color:#34d399;padding:2px 5px;border-radius:4px;font-size:10px;font-family:monospace;">${g.key}</span>`)
        .join(" ");
      const remBadges = remainingList
        .slice(0, 12)
        .map((g) => `<span style="background:rgba(255,255,255,0.12);color:#cbd5e1;padding:2px 5px;border-radius:4px;font-size:10px;font-family:monospace;">${g.key}</span>`)
        .join(" ");

      const extra = `
        <div style="margin-top:2px;">
          <div style="color:#10b981;font-weight:600;margin-bottom:4px;font-size:10.5px;">🟢 Selected (${selectedList.length}):</div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;margin-bottom:8px;">${selBadges}${selectedList.length > 8 ? ` <span style="font-size:9.5px;color:var(--text-dim);">+${selectedList.length - 8}…</span>` : ""}</div>
          <div style="color:var(--text-dim);font-weight:600;margin-bottom:4px;font-size:10.5px;">⚪ Remaining (${remainingList.length}):</div>
          <div style="display:flex;flex-wrap:wrap;gap:4px;max-height:120px;overflow-y:auto;">${remBadges}${remainingList.length > 12 ? ` <span style="font-size:9.5px;color:var(--text-dim);">+${remainingList.length - 12}…</span>` : ""}</div>
        </div>
      `;

      biShowTooltip(
        e,
        `📊 Selection Overview (${vis.x})`,
        `Selected: <b>${biFormatNumber(selectedVal)} / ${biFormatNumber(total)} (${selectedPct}%)</b>`,
        `Remaining: <b>${biFormatNumber(remainingVal)} / ${biFormatNumber(total)} (${(100 - Number(selectedPct)).toFixed(0)}%)</b>`,
        extra
      );
    });
    centerEl.addEventListener("mousemove", (e) => biMoveTooltip(e));
    centerEl.addEventListener("mouseleave", () => biHideTooltip());
  }
}

function biRenderTable(container, vis) {
          const records = biState.filteredData.slice(0, vis.limit || 20);
          if (records.length === 0) {
            container.innerHTML = `<span class="meta">No matching records found.</span>`;
            return;
          }

          const cols = biState.columns.slice(0, 7); // show top 7 columns

          let html = `<div class="bi-table-wrap"><table class="bi-table"><thead><tr>`;
          cols.forEach((c) => {
            html += `<th>${c.name}</th>`;
          });
          html += `</tr></thead><tbody>`;

          records.forEach((row) => {
            html += `<tr>`;
            cols.forEach((c) => {
              const val = row[c.name];
              const displayVal = val !== null && val !== undefined ? String(val) : "—";
              html += `<td>${displayVal}</td>`;
            });
            html += `</tr>`;
          });

          html += `</tbody></table></div>`;
          container.innerHTML = html;
        }

        function biOpenJsonModal() {
          const modal = $("#modal-bi-json");
          if (!modal) return;
          const jsonStr = JSON.stringify(biState.filteredData, null, 2);
          const sizeKb = (new Blob([jsonStr]).size / 1024).toFixed(1);

          $("#bi-json-stats-badge").textContent = `${biState.filteredData.length} records · ${biState.columns.length} columns · ${sizeKb} KB`;
          $("#bi-json-viewer-content").textContent = jsonStr;
          modal.classList.remove("hidden");
        }

        function biOpenConfigModal(activeTab = "gui") {
          const modal = $("#modal-bi-config");
          if (!modal) return;

          // Populate column selectors for GUI form
          const xSelect = $("#bi-gui-x-select");
          const ySelect = $("#bi-gui-y-select");
          const y2Select = $("#bi-gui-y2-select");

          const numCols = biState.columns.filter((c) => c.type === "number");
          const strCols = biState.columns.filter((c) => c.type !== "number");
          const allCols = biState.columns;

          if (xSelect) {
            xSelect.innerHTML = allCols.map((c) => `<option value="${c.name}">${c.name} (${c.type})</option>`).join("");
            if (strCols.length > 0) xSelect.value = strCols[0].name;
          }
          if (ySelect) {
            ySelect.innerHTML = numCols.length > 0
              ? numCols.map((c) => `<option value="${c.name}">${c.name} (num)</option>`).join("")
              : allCols.map((c) => `<option value="${c.name}">${c.name}</option>`).join("");
            ySelect.innerHTML = allCols.map((c) => `<option value="${c.name}">${c.name}${c.type === 'number' ? ' (num)' : ''}</option>`).join("");
            if (numCols.length > 0) ySelect.value = numCols[0].name;
          }
          if (y2Select) {
            y2Select.innerHTML = `<option value="">(None)</option>` +
              numCols.map((c) => `<option value="${c.name}">${c.name}</option>`).join("");
          }

          biResetConfigForm();
          biSwitchConfigTab(activeTab);
          biRenderConfigGuiList();

          modal.classList.remove("hidden");
        }

        function biSwitchConfigTab(tabName) {
          const isGui = tabName === "gui";
          const btnGui = $("#btn-bi-cfg-tab-gui");
          const btnRaw = $("#btn-bi-cfg-tab-raw");
          const paneGui = $("#bi-config-pane-gui");
          const paneRaw = $("#bi-config-pane-raw");

          if (isGui) {
            // If switching from Raw to GUI, try to parse raw JSON
            const rawVal = $("#bi-config-editor-content")?.value;
            if (rawVal && rawVal.trim()) {
              try {
                const parsed = JSON.parse(rawVal);
                let rawVisuals = [];
                if (Array.isArray(parsed)) rawVisuals = parsed;
                else if (parsed && typeof parsed === "object" && Array.isArray(parsed.visuals)) rawVisuals = parsed.visuals;
                if (rawVisuals.length > 0) {
                  biState.visuals = rawVisuals.map((v, idx) => ({
                    id: v.id || `vis_${idx + 1}`,
                    type: v.type || "bar",
                    title: v.title || `Visual ${idx + 1}`,
                    x: v.x || "",
                    y: v.y || "",
                    y2: v.y2 || undefined,
                    agg: v.agg || "sum",
                    isWide: !!v.isWide,
                    limit: v.limit || 15,
                  }));
                }
              } catch { }
            }
            btnGui?.classList.add("active");
            btnRaw?.classList.remove("active");
            paneGui?.classList.remove("hidden");
            paneRaw?.classList.add("hidden");
            biRenderConfigGuiList();
          } else {
            // Switching from GUI to Raw, sync latest visuals to JSON textarea
            biSyncVisualsToRawEditor();
            btnRaw?.classList.add("active");
            btnGui?.classList.remove("active");
            paneRaw?.classList.remove("hidden");
            paneGui?.classList.add("hidden");
          }
        }

        function biSyncVisualsToRawEditor() {
          const visuals = biState.visuals || [];
          const configPayload = {
            version: "1.0",
            generator: "telua_bi_studio",
            dataset: biState.filename || "dataset.xlsx",
            sheet: biState.activeSheet || "Sheet1",
            exported_at: new Date().toISOString(),
            visuals: visuals.map((v) => ({
              id: v.id,
              type: v.type,
              title: v.title,
              x: v.x,
              y: v.y,
              ...(v.y2 ? { y2: v.y2 } : {}),
              agg: v.agg || "sum",
              isWide: !!v.isWide,
              ...(v.limit ? { limit: v.limit } : {}),
            })),
          };
          const editor = $("#bi-config-editor-content");
          if (editor) {
            editor.value = JSON.stringify(configPayload, null, 2);
          }
        }

        function biRenderConfigGuiList() {
          const listEl = $("#bi-gui-visuals-list");
          if (!listEl) return;

          const visuals = biState.visuals || [];
          const countEl = $("#bi-gui-list-count");
          if (countEl) countEl.textContent = `${visuals.length} biểu đồ`;

          const badge = $("#bi-config-stats-badge");
          if (badge) badge.textContent = `${visuals.length} visual${visuals.length === 1 ? "" : "s"}`;

          biSyncVisualsToRawEditor();

          if (visuals.length === 0) {
            listEl.innerHTML = `
      <div class="meta" style="text-align:center;padding:24px;border:1px dashed var(--border);border-radius:6px;">
        Chưa có biểu đồ nào trong cấu hình. Hãy điền thông tin vào biểu mẫu ở trên và nhấn <strong>＋ Thêm vào danh sách</strong>, hoặc nhấn <strong>💡 Load Template</strong>.
      </div>
    `;
            return;
          }

          listEl.innerHTML = visuals.map((vis, idx) => {
            let typeIcon = "📊";
            if (vis.type === "combo") typeIcon = "📊📈";
            else if (vis.type === "hbar") typeIcon = "📶";
            else if (vis.type === "line") typeIcon = "📈";
            else if (vis.type === "pie") typeIcon = "🍩";
            else if (vis.type === "table") typeIcon = "▦";

            const widthLabel = vis.isWide ? "2 cột (Full)" : "1 cột";
            const dimMeasure = vis.type === "table"
              ? `Grid · Top ${vis.limit || 15} rows`
              : `X: <strong>${vis.x || '—'}</strong> · Y: <strong>${vis.y || '—'}</strong> (${(vis.agg || 'sum').toUpperCase()})${vis.y2 ? ` · Y2: <strong>${vis.y2}</strong>` : ''}`;

            const isFirst = idx === 0;
            const isLast = idx === visuals.length - 1;

            return `
      <div class="bi-gui-item" data-id="${vis.id}" data-idx="${idx}">
        <div class="bi-gui-item-info">
          <span style="font-size:16px;">${typeIcon}</span>
          <div style="display:flex;flex-direction:column;gap:2px;overflow:hidden;">
            <div style="display:flex;align-items:center;gap:6px;">
              <span class="bi-gui-item-title">${vis.title || "Visual " + (idx + 1)}</span>
              <span class="tag" style="font-size:10px;text-transform:uppercase;padding:1px 5px;background:var(--border);border-radius:3px;">${vis.type}</span>
              <span class="tag" style="font-size:10px;padding:1px 5px;background:rgba(30,167,253,0.12);color:var(--accent);border-radius:3px;">${widthLabel}</span>
            </div>
            <span class="bi-gui-item-meta">${dimMeasure}</span>
          </div>
        </div>
        <div class="bi-gui-item-actions">
          <button type="button" class="btn btn-xs ghost btn-gui-up" title="Move Up (Lên)" data-idx="${idx}" ${isFirst ? 'disabled' : ''}>⬆</button>
          <button type="button" class="btn btn-xs ghost btn-gui-down" title="Move Down (Xuống)" data-idx="${idx}" ${isLast ? 'disabled' : ''}>⬇</button>
          <button type="button" class="btn btn-xs ghost btn-gui-width" title="Toggle 1x/2x Width (Đổi kích thước)" data-id="${vis.id}">⤢</button>
          <button type="button" class="btn btn-xs ghost btn-gui-edit" title="Edit this chart (Sửa)" data-id="${vis.id}">✏️</button>
          <button type="button" class="btn btn-xs ghost danger btn-gui-del" title="Remove this chart (Xóa)" data-id="${vis.id}">🗑️</button>
        </div>
      </div>
    `;
          }).join("");

          // Attach button event listeners in GUI list
          listEl.querySelectorAll(".btn-gui-up").forEach((b) => {
            b.addEventListener("click", () => {
              const idx = parseInt(b.dataset.idx, 10);
              if (idx > 0) {
                const temp = biState.visuals[idx];
                biState.visuals[idx] = biState.visuals[idx - 1];
                biState.visuals[idx - 1] = temp;
                biRenderConfigGuiList();
                biRenderVisuals();
              }
            });
          });

          listEl.querySelectorAll(".btn-gui-down").forEach((b) => {
            b.addEventListener("click", () => {
              const idx = parseInt(b.dataset.idx, 10);
              if (idx < biState.visuals.length - 1) {
                const temp = biState.visuals[idx];
                biState.visuals[idx] = biState.visuals[idx + 1];
                biState.visuals[idx + 1] = temp;
                biRenderConfigGuiList();
                biRenderVisuals();
              }
            });
          });

          listEl.querySelectorAll(".btn-gui-width").forEach((b) => {
            b.addEventListener("click", () => {
              const v = biState.visuals.find((item) => item.id === b.dataset.id);
              if (v) {
                v.isWide = !v.isWide;
                biRenderConfigGuiList();
                biRenderVisuals();
              }
            });
          });

          listEl.querySelectorAll(".btn-gui-edit").forEach((b) => {
            b.addEventListener("click", () => biEditConfigVisual(b.dataset.id));
          });

          listEl.querySelectorAll(".btn-gui-del").forEach((b) => {
            b.addEventListener("click", () => {
              biState.visuals = biState.visuals.filter((item) => item.id !== b.dataset.id);
              biRenderConfigGuiList();
              biRenderVisuals();
              toast("Đã xóa", "Đã xóa biểu đồ khỏi cấu hình.", "info", 1500);
            });
          });
        }

        function biEditConfigVisual(id) {
          const vis = biState.visuals.find((v) => v.id === id);
          if (!vis) return;

          biState._editingVisualId = id;

          // Set type chips
          document.querySelectorAll("#bi-gui-type-chips .term-chip").forEach((chip) => {
            const isMatch = chip.dataset.vtype === vis.type;
            chip.classList.toggle("active", isMatch);
          });
          const y2Group = $("#bi-gui-y2-group");
          if (y2Group) y2Group.style.display = vis.type === "combo" ? "block" : "none";

          const titleInput = $("#bi-gui-title-input");
          if (titleInput) titleInput.value = vis.title || "";

          const wideBox = $("#bi-gui-wide-checkbox");
          if (wideBox) wideBox.checked = !!vis.isWide;

          const xSel = $("#bi-gui-x-select");
          if (xSel && vis.x) xSel.value = vis.x;

          const ySel = $("#bi-gui-y-select");
          if (ySel && vis.y) ySel.value = vis.y;

          const y2Sel = $("#bi-gui-y2-select");
          if (y2Sel && vis.y2) y2Sel.value = vis.y2;

          const aggSel = $("#bi-gui-agg-select");
          if (aggSel && vis.agg) aggSel.value = vis.agg;

          const formTitle = $("#bi-gui-form-title");
          if (formTitle) formTitle.textContent = `✏️ Chỉnh Sửa Biểu Đồ: ${vis.title || 'Chart'}`;

          const saveBtn = $("#btn-bi-gui-save-item");
          if (saveBtn) saveBtn.textContent = "💾 Cập nhật biểu đồ";

          $("#btn-bi-gui-cancel-edit")?.classList.remove("hidden");
        }

        function biResetConfigForm() {
          biState._editingVisualId = null;

          const titleInput = $("#bi-gui-title-input");
          if (titleInput) titleInput.value = "";

          const wideBox = $("#bi-gui-wide-checkbox");
          if (wideBox) wideBox.checked = false;

          // Default to combo or bar
          document.querySelectorAll("#bi-gui-type-chips .term-chip").forEach((chip, idx) => {
            chip.classList.toggle("active", idx === 0);
          });
          const y2Group = $("#bi-gui-y2-group");
          if (y2Group) y2Group.style.display = "block";

          const formTitle = $("#bi-gui-form-title");
          if (formTitle) formTitle.textContent = "＋ Thêm Biểu Đồ Mới (Add Chart)";

          const saveBtn = $("#btn-bi-gui-save-item");
          if (saveBtn) saveBtn.textContent = "＋ Thêm vào danh sách";

          $("#btn-bi-gui-cancel-edit")?.classList.add("hidden");
        }

        function biSaveConfigItemFromForm() {
          const activeChip = $("#bi-gui-type-chips .term-chip.active");
          const type = activeChip?.dataset.vtype || "bar";
          let title = ($("#bi-gui-title-input")?.value || "").trim();
          const isWide = !!$("#bi-gui-wide-checkbox")?.checked;
          const x = $("#bi-gui-x-select")?.value || "";
          const y = $("#bi-gui-y-select")?.value || "";
          const y2 = $("#bi-gui-y2-select")?.value || "";
          const agg = $("#bi-gui-agg-select")?.value || "sum";

          if (!title) {
            if (type === "table") title = `Data Grid (${biState.activeSheet || 'Table'})`;
            else if (type === "combo") title = `${y} vs ${y2 || 'Line'} by ${x}`;
            else title = `${y} by ${x}`;
          }

          if (biState._editingVisualId) {
            const idx = biState.visuals.findIndex((v) => v.id === biState._editingVisualId);
            if (idx !== -1) {
              biState.visuals[idx] = {
                ...biState.visuals[idx],
                type,
                title,
                x,
                y,
                ...(y2 ? { y2 } : { y2: undefined }),
                agg,
                isWide,
              };
              toast("Đã cập nhật", `Đã lưu thay đổi cho biểu đồ '${title}'.`, "ok", 2000);
            }
          } else {
            const newVis = {
              id: `vis_${Date.now()}`,
              type,
              title,
              x,
              y,
              ...(y2 ? { y2 } : {}),
              agg,
              isWide,
              limit: 15,
            };
            biState.visuals.push(newVis);
            toast("Đã thêm biểu đồ", `Đã thêm biểu đồ '${title}' vào danh sách cấu hình.`, "ok", 2000);
          }

          biResetConfigForm();
          biRenderConfigGuiList();
          biRenderVisuals();
        }

        function biApplyConfigJson(jsonStr) {
          if (!jsonStr || !jsonStr.trim()) {
            toast("Config Empty", "Please provide a valid JSON configuration.", "err", 3000);
            return false;
          }

          let parsed;
          try {
            parsed = JSON.parse(jsonStr);
          } catch (err) {
            toast("Invalid JSON", "Syntax error in JSON: " + err.message, "err", 4000);
            return false;
          }

          let rawVisuals = [];
          if (Array.isArray(parsed)) {
            rawVisuals = parsed;
          } else if (parsed && typeof parsed === "object" && Array.isArray(parsed.visuals)) {
            rawVisuals = parsed.visuals;
          } else {
            toast("Invalid Schema", "Config JSON must either be an array of visuals or an object with a 'visuals' array property.", "err", 4500);
            return false;
          }

          biState.visuals = rawVisuals.map((v, idx) => ({
            id: v.id || `vis_${idx + 1}`,
            type: v.type || "bar",
            title: v.title || `Visual ${idx + 1}`,
            x: v.x || "",
            y: v.y || "",
            y2: v.y2 || undefined,
            agg: v.agg || "sum",
            isWide: !!v.isWide,
            limit: v.limit || 15,
          }));

          biRenderVisuals();
          $("#modal-bi-config")?.classList.add("hidden");
          toast("Config Applied", `Successfully loaded ${biState.visuals.length} visual(s) from JSON config.`, "ok", 3000);

          // Optionally persist config to backend
          try {
            fetch("/api/bi/visual-config", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                dataset: biState.filename,
                sheet: biState.activeSheet,
                visuals: biState.visuals,
              }),
            }).catch(() => { });
          } catch { }

          return true;
        }

        function biExportConfigJson() {
          const visuals = biState.visuals || [];
          const configPayload = {
            version: "1.0",
            generator: "telua_bi_studio",
            dataset: biState.filename || "dataset.xlsx",
            sheet: biState.activeSheet || "Sheet1",
            exported_at: new Date().toISOString(),
            visuals: visuals.map((v) => ({
              id: v.id,
              type: v.type,
              title: v.title,
              x: v.x,
              y: v.y,
              ...(v.y2 ? { y2: v.y2 } : {}),
              agg: v.agg || "sum",
              isWide: !!v.isWide,
              ...(v.limit ? { limit: v.limit } : {}),
            })),
          };

          const jsonStr = JSON.stringify(configPayload, null, 2);
          const blob = new Blob([jsonStr], { type: "application/json" });
          const url = URL.createObjectURL(blob);
          const a = document.createElement("a");
          const baseName = biState.filename ? biState.filename.replace(/\.[^/.]+$/, "") : "bi_dashboard";
          a.href = url;
          a.download = `${baseName}_visuals_config.json`;
          a.click();
          URL.revokeObjectURL(url);
          toast("Config Downloaded", `Saved ${a.download} (${visuals.length} visual${visuals.length === 1 ? "" : "s"}).`, "ok", 2500);
        }

        function biImportConfigJson(file) {
          if (!file) return;
          const reader = new FileReader();
          reader.onload = (e) => {
            try {
              const content = e.target.result;
              biApplyConfigJson(content);
            } catch (err) {
              toast("Import Error", "Failed to parse JSON file: " + err.message, "err", 4000);
            }
          };
          reader.readAsText(file);
        }

        function biOpenAddVisualModal() {
          const modal = $("#modal-bi-add-visual");
          if (!modal) return;

          const xSelect = $("#bi-visual-x-select");
          const ySelect = $("#bi-visual-y-select");
          const y2Select = $("#bi-visual-y2-select");

          const numCols = biState.columns.filter((c) => c.type === "number");
          const allCols = biState.columns;

          if (xSelect) {
            xSelect.innerHTML = allCols.map((c) => `<option value="${c.name}">${c.name} (${c.type})</option>`).join("");
          }
          if (ySelect) {
            ySelect.innerHTML = numCols.length > 0
              ? numCols.map((c) => `<option value="${c.name}">${c.name}</option>`).join("")
              : allCols.map((c) => `<option value="${c.name}">${c.name}</option>`).join("");
            ySelect.innerHTML = allCols.map((c) => `<option value="${c.name}">${c.name}${c.type === 'number' ? ' (num)' : ''}</option>`).join("");
            if (numCols.length > 0) ySelect.value = numCols[0].name;
          }
          if (y2Select) {
            y2Select.innerHTML = `<option value="">(None)</option>` +
              numCols.map((c) => `<option value="${c.name}">${c.name}</option>`).join("");
          }

          modal.classList.remove("hidden");
        }

        function biSaveNewVisual() {
          const activeTypeBtn = document.querySelector("#bi-visual-type-select .term-chip.active");
          const type = activeTypeBtn ? activeTypeBtn.dataset.vtype : "bar";
          const title = $("#bi-visual-title-input")?.value.trim() || `${type.toUpperCase()} Visual`;
          const x = $("#bi-visual-x-select")?.value;
          const y = $("#bi-visual-y-select")?.value;
          const y2 = $("#bi-visual-y2-select")?.value || null;
          const agg = $("#bi-visual-agg-select")?.value || "sum";

          biState.visuals.push({
            id: `vis_${Date.now()}`,
            type,
            title,
            x,
            y,
            y2,
            agg,
          });

          $("#modal-bi-add-visual")?.classList.add("hidden");
          biRenderVisuals();
          toast("Visual Added", `Created '${title}' on dashboard canvas.`, "ok", 2500);
        }

        async function biExportExcel() {
          if (biState.filteredData.length === 0) {
            toast("Export Failed", "No records to export.", "warn", 2500);
            return;
          }
          toast("Exporting Excel…", "Generating .xlsx file with active filtered dataset…", "info", 2000);
          try {
            const res = await fetch("/api/bi/export-excel", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({
                data: biState.filteredData,
                sheet_name: biState.activeSheet || "FilteredData",
                filename: `telua_bi_${biState.activeSheet || "export"}.xlsx`,
              }),
            });
            if (!res.ok) throw new Error("Server returned error during Excel export.");

            const blob = await res.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement("a");
            a.href = url;
            a.download = `telua_bi_${biState.activeSheet || "export"}.xlsx`;
            a.click();
            URL.revokeObjectURL(url);
            toast("Excel Exported", "File downloaded successfully.", "ok", 3000);
          } catch (err) {
            toast("Export Error", err.message, "err", 5000);
          }
        }

