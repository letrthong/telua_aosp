/* ==============================================================================
   Telua Web - Sphinx Docs & Quill.js WYSIWYG Module
   ============================================================================== */
/* ---------------- Sphinx Docs & Quill.js ---------------- */
let _quill = null;
let _docsFiles = [];
let _currentDoc = null; // { name, rst, html, mtime, readonly }
let _docsEditorType = localStorage.getItem("telua_web_docs_editor") || (localStorage.getItem("telua_web_docs_mode") === "raw" ? "raw" : "wysiwyg"); // "wysiwyg" | "raw"
let _docsSplit = localStorage.getItem("telua_web_docs_split") === "true" || localStorage.getItem("telua_web_docs_mode") === "split";
let _docsMode = _docsSplit ? "split" : _docsEditorType; // legacy sync
let _docsDirty = false;
let _docsCustomDir = localStorage.getItem("telua_web_docs_dir") || "";
let _docsActiveDir = "";
let _docsSyncScroll = localStorage.getItem("telua_web_docs_sync_scroll") !== "false"; // default true
let _syncScrollSource = null;
let _syncScrollTimer = null;

let _mermaidCounter = 0;

const PLANTUML_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz-_";

function getPlantumlUrl(text) {
  if (!text || !text.trim()) return "";
  let clean = text.trim();
  if (!clean.startsWith("@startuml")) {
    clean = `@startuml\n${clean}\n@enduml`;
  }
  return `/api/docs/plantuml/svg?code=${encodeURIComponent(clean)}`;
}

function autoResizeDiagramTextarea(el) {
  if (!el) return;
  el.style.height = "auto";
  el.style.height = Math.max(120, Math.min(el.scrollHeight + 8, 600)) + "px";
}

function registerQuillDiagramBlots() {
  if (!window.Quill || window._quillDiagramBlotsRegistered) return;
  try {
    const BlockEmbed = Quill.import("blots/block/embed");
    if (!BlockEmbed) return;

    class MermaidBlot extends BlockEmbed {
      static blotName = "mermaidBlock";
      static tagName = "div";
      static className = "mermaid-block";

      static create(value) {
        const node = super.create();
        node.setAttribute("contenteditable", "false");
        let code = "";
        if (typeof value === "string") {
          code = value;
        } else if (value && typeof value === "object") {
          code = value.getAttribute ? (value.getAttribute("data-mermaid") || value.querySelector("textarea")?.value || value.querySelector("pre")?.textContent || "") : (value.code || "");
        }
        node.setAttribute("data-mermaid", code);
        const safeCode = (code || "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");

        node.innerHTML = `
          <div class="mermaid-header" contenteditable="false">
            <div class="mermaid-title-wrap">
              <span class="mermaid-label">📊 Mermaid Architecture Diagram</span>
              <span class="mermaid-chip">.. mermaid::</span>
            </div>
            <div class="mermaid-actions">
              <button type="button" class="mermaid-btn btn-view-diag active" title="Show Rendered Diagram">👁 Diagram</button>
              <button type="button" class="mermaid-btn btn-view-code" title="View / Edit Diagram Code">📝 Code</button>
              <button type="button" class="mermaid-btn btn-copy-code" title="Copy Diagram Syntax">📋 Copy</button>
              <button type="button" class="mermaid-btn btn-del-diag danger" title="Delete Diagram">🗑</button>
            </div>
          </div>
          <div class="mermaid-diagram-wrap" contenteditable="false">
            <span class="mermaid-loading" style="color:var(--text-dim);font-size:12px;">⏳ Rendering Mermaid diagram graphic…</span>
          </div>
          <textarea class="mermaid-code-input" spellcheck="false" style="display:none;" title="Click to edit diagram syntax" placeholder="Type Mermaid syntax here…">${safeCode}</textarea>
        `;
        return node;
      }

      static value(node) {
        return node.getAttribute("data-mermaid") || node.querySelector("textarea")?.value || node.querySelector("pre")?.textContent || "";
      }
    }

    class PlantumlBlot extends BlockEmbed {
      static blotName = "plantumlBlock";
      static tagName = "div";
      static className = "plantuml-block";

      static create(value) {
        const node = super.create();
        node.setAttribute("contenteditable", "false");
        let code = "";
        if (typeof value === "string") {
          code = value;
        } else if (value && typeof value === "object") {
          code = value.getAttribute ? (value.getAttribute("data-plantuml") || value.querySelector("textarea")?.value || value.querySelector("pre")?.textContent || "") : (value.code || "");
        }
        node.setAttribute("data-plantuml", code);
        const safeCode = (code || "")
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;")
          .replace(/"/g, "&quot;");

        const umlUrl = getPlantumlUrl(code);

        node.innerHTML = `
          <div class="plantuml-header" contenteditable="false">
            <div class="plantuml-title-wrap">
              <span class="plantuml-label">📐 PlantUML Architecture Diagram</span>
              <span class="plantuml-chip">.. uml::</span>
            </div>
            <div class="plantuml-actions">
              <button type="button" class="plantuml-btn btn-view-diag active" title="Show Rendered Diagram">👁 Diagram</button>
              <button type="button" class="plantuml-btn btn-view-code" title="View / Edit Diagram Code">📝 Code</button>
              <button type="button" class="plantuml-btn btn-copy-uml" title="Copy PlantUML Syntax">📋 Copy</button>
              <button type="button" class="plantuml-btn btn-del-uml danger" title="Delete Diagram">🗑</button>
            </div>
          </div>
          <div class="plantuml-diagram-wrap" contenteditable="false">
            <img class="plantuml-svg-img" src="${umlUrl}" alt="PlantUML Diagram" loading="lazy" />
          </div>
          <textarea class="plantuml-code-input" spellcheck="false" style="display:none;" title="Click to edit diagram syntax" placeholder="Type PlantUML syntax here…">${safeCode}</textarea>
        `;
        return node;
      }

      static value(node) {
        return node.getAttribute("data-plantuml") || node.querySelector("textarea")?.value || node.querySelector("pre")?.textContent || "";
      }
    }

    class TableBlockBlot extends BlockEmbed {
      static blotName = "tableBlock";
      static tagName = "div";
      static className = "doc-table-block";

      static create(value) {
        const node = super.create();
        node.setAttribute("contenteditable", "false");
        const tableHtml = typeof value === "string" ? value : (value?.tableHtml || "");
        buildTableBlockCard(node, tableHtml);
        return node;
      }

      static value(node) {
        const table = node.querySelector("table");
        return table ? table.outerHTML : "";
      }
    }

    Quill.register(MermaidBlot);
    Quill.register(PlantumlBlot);
    Quill.register(TableBlockBlot);
    window._quillDiagramBlotsRegistered = true;
  } catch (err) {
    console.warn("Custom Quill Blots registration skipped:", err);
  }
}

function buildTableBlockCard(node, tableHtml) {
  let tempDiv = document.createElement("div");
  tempDiv.innerHTML = tableHtml || "";
  let table = tempDiv.querySelector("table");
  if (!table) {
    table = document.createElement("table");
    table.className = "doc-table-grid";
    table.innerHTML = `
      <thead>
        <tr><th>Header 1</th><th>Header 2</th><th>Header 3</th></tr>
      </thead>
      <tbody>
        <tr><td>Data 1</td><td>Data 2</td><td>Data 3</td></tr>
      </tbody>
    `;
  }
  table.classList.add("doc-table-grid");

  let captionText = "";
  const cap = table.querySelector("caption");
  if (cap) {
    captionText = cap.textContent.trim();
    cap.remove();
  }

  node.setAttribute("contenteditable", "false");
  node.innerHTML = `
    <div class="doc-table-header" contenteditable="false">
      <div class="doc-table-title-wrap">
        <span class="doc-table-label">▦ List Table</span>
        <span class="doc-table-chip">.. list-table::</span>
        <input type="text" class="doc-table-caption-input" placeholder="Table Title / Caption (optional)" value="${captionText.replace(/"/g, '&quot;')}">
      </div>
      <div class="doc-table-actions">
        <button type="button" class="doc-table-btn btn-table-add-row" title="Add Row at bottom">+ Row</button>
        <button type="button" class="doc-table-btn btn-table-add-col" title="Add Column at right">+ Col</button>
        <button type="button" class="doc-table-btn btn-table-del-row" title="Remove Last Row">- Row</button>
        <button type="button" class="doc-table-btn btn-table-del-col" title="Remove Last Column">- Col</button>
        <button type="button" class="doc-table-btn btn-table-del danger" title="Delete Table">🗑</button>
      </div>
    </div>
    <div class="doc-table-scroll" contenteditable="false"></div>
  `;

  const scrollWrap = node.querySelector(".doc-table-scroll");
  scrollWrap.appendChild(table);

  wireSingleTableBlock(node);
}

function wireSingleTableBlock(blockNode) {
  if (!blockNode || blockNode.dataset.wired) return;
  blockNode.dataset.wired = "true";

  const table = blockNode.querySelector("table");
  const captionInput = blockNode.querySelector(".doc-table-caption-input");

  if (captionInput) {
    captionInput.addEventListener("input", () => setDocsDirty(true));
    captionInput.addEventListener("keydown", (e) => e.stopPropagation());
    captionInput.addEventListener("paste", (e) => e.stopPropagation());
    captionInput.addEventListener("copy", (e) => e.stopPropagation());
    captionInput.addEventListener("cut", (e) => e.stopPropagation());
    captionInput.addEventListener("mousedown", (e) => e.stopPropagation());
  }

  function wireCells() {
    if (!table) return;
    const cells = table.querySelectorAll("th, td");
    for (const cell of cells) {
      if (cell.dataset.wired) continue;
      cell.dataset.wired = "true";
      cell.setAttribute("contenteditable", "true");
      cell.setAttribute("spellcheck", "false");

      cell.addEventListener("input", () => setDocsDirty(true));
      cell.addEventListener("mousedown", (e) => e.stopPropagation());
      cell.addEventListener("mouseup", (e) => e.stopPropagation());
      cell.addEventListener("click", (e) => e.stopPropagation());
      cell.addEventListener("copy", (e) => e.stopPropagation());
      cell.addEventListener("cut", (e) => {
        e.stopPropagation();
        setTimeout(() => setDocsDirty(true), 0);
      });
      cell.addEventListener("paste", (e) => {
        e.stopPropagation();
        setTimeout(() => setDocsDirty(true), 0);
      });
      cell.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Tab") {
          e.preventDefault();
          const allCells = Array.from(table.querySelectorAll("th, td"));
          const idx = allCells.indexOf(cell);
          if (e.shiftKey) {
            if (idx > 0) allCells[idx - 1].focus();
          } else {
            if (idx < allCells.length - 1) {
              allCells[idx + 1].focus();
            } else {
              addRow();
              const newCells = table.querySelectorAll("th, td");
              if (newCells.length > allCells.length) {
                newCells[allCells.length].focus();
              }
            }
          }
        }
      });
    }
  }

  function addRow() {
    if (!table) return;
    const rows = table.querySelectorAll("tr");
    const numCols = rows.length > 0 ? rows[0].querySelectorAll("th, td").length : 3;
    const newTr = document.createElement("tr");
    for (let i = 0; i < numCols; i++) {
      const td = document.createElement("td");
      td.textContent = "";
      newTr.appendChild(td);
    }
    const tbody = table.querySelector("tbody") || table;
    tbody.appendChild(newTr);
    wireCells();
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    const firstTd = newTr.querySelector("td");
    if (firstTd) firstTd.focus();
  }

  function addCol() {
    if (!table) return;
    const rows = table.querySelectorAll("tr");
    for (let r = 0; r < rows.length; r++) {
      const row = rows[r];
      const isHeader = row.parentElement && row.parentElement.tagName.toLowerCase() === "thead" || (r === 0 && row.querySelector("th"));
      const cell = document.createElement(isHeader ? "th" : "td");
      cell.textContent = isHeader ? `Header ${row.children.length + 1}` : "";
      row.appendChild(cell);
    }
    wireCells();
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
  }

  function delRow() {
    if (!table) return;
    const rows = table.querySelectorAll("tr");
    if (rows.length > 2) {
      rows[rows.length - 1].remove();
      setDocsDirty(true);
      if (_docsSplit) updateDocsPreview();
    }
  }

  function delCol() {
    if (!table) return;
    const rows = table.querySelectorAll("tr");
    if (rows.length > 0 && rows[0].children.length > 1) {
      for (const row of rows) {
        if (row.lastElementChild) row.lastElementChild.remove();
      }
      setDocsDirty(true);
      if (_docsSplit) updateDocsPreview();
    }
  }

  blockNode.querySelector(".btn-table-add-row")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    addRow();
  });

  blockNode.querySelector(".btn-table-add-col")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    addCol();
  });

  blockNode.querySelector(".btn-table-del-row")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    delRow();
  });

  blockNode.querySelector(".btn-table-del-col")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    delCol();
  });

  blockNode.querySelector(".btn-table-del")?.addEventListener("click", (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (confirm("Delete this table?")) {
      blockNode.remove();
      setDocsDirty(true);
      if (_docsSplit) updateDocsPreview();
    }
  });

  wireCells();
}

function wireDocTableBlocks(container) {
  if (!container) return;
  const rawTables = container.querySelectorAll("table:not(.doc-table-grid)");
  for (const tbl of rawTables) {
    if (tbl.closest(".doc-table-block")) continue;
    const wrapper = document.createElement("div");
    wrapper.className = "doc-table-block";
    tbl.parentNode.insertBefore(wrapper, tbl);
    buildTableBlockCard(wrapper, tbl.outerHTML);
    tbl.remove();
  }
  const blocks = container.querySelectorAll(".doc-table-block");
  for (const block of blocks) {
    wireSingleTableBlock(block);
  }
}

function wirePlantumlBlocks(container) {
  if (!container) return;
  const blocks = container.querySelectorAll(".plantuml-block");
  for (const block of blocks) {
    let ta = block.querySelector("textarea.plantuml-code-input, textarea");
    const pre = block.querySelector("pre.plantuml, pre.plantuml-code, pre");
    const rawCode = block.getAttribute("data-plantuml") || (ta ? ta.value : (pre ? pre.textContent : ""));
    const trimmedCode = (rawCode || "").trim();

    if (trimmedCode) {
      block.setAttribute("data-plantuml", trimmedCode);
    }

    if (!ta) {
      ta = document.createElement("textarea");
      ta.className = "plantuml-code-input";
      ta.spellcheck = false;
      ta.style.display = "none";
      ta.placeholder = "Type PlantUML syntax here…";
      if (pre) {
        block.replaceChild(ta, pre);
      } else {
        block.appendChild(ta);
      }
    } else if (pre) {
      pre.remove();
    }
    if (trimmedCode) ta.value = trimmedCode;

    // Ensure diagWrap exists
    let diagWrap = block.querySelector(".plantuml-diagram-wrap");
    if (!diagWrap) {
      diagWrap = document.createElement("div");
      diagWrap.className = "plantuml-diagram-wrap";
      diagWrap.setAttribute("contenteditable", "false");
      block.insertBefore(diagWrap, ta);
    }

    // Ensure img exists inside diagWrap
    let img = diagWrap.querySelector("img.plantuml-svg-img, img");
    const expectedUrl = getPlantumlUrl(trimmedCode);
    if (!img) {
      img = document.createElement("img");
      img.className = "plantuml-svg-img";
      img.alt = "PlantUML Diagram";
      img.loading = "lazy";
      if (expectedUrl) img.src = expectedUrl;
      diagWrap.appendChild(img);
    } else if (expectedUrl && img.getAttribute("src") !== expectedUrl) {
      img.src = expectedUrl;
    }

    if (img && !img.dataset.wired) {
      img.dataset.wired = "true";
      img.onload = () => {
        img.style.display = "block";
        diagWrap.querySelector(".plantuml-offline-notice")?.remove();
      };
    }

    // Ensure header exists
    let header = block.querySelector(".plantuml-header");
    if (!header) {
      const origLabel = block.querySelector(".plantuml-label");
      header = document.createElement("div");
      header.className = "plantuml-header";
      header.setAttribute("contenteditable", "false");
      header.innerHTML = `
        <div class="plantuml-title-wrap">
          <span class="plantuml-label">📐 PlantUML Architecture Diagram</span>
          <span class="plantuml-chip">.. uml::</span>
        </div>
        <div class="plantuml-actions">
          <button type="button" class="plantuml-btn btn-view-diag active" title="Show Rendered Diagram">👁 Diagram</button>
          <button type="button" class="plantuml-btn btn-view-code" title="View / Edit Diagram Code">📝 Code</button>
          <button type="button" class="plantuml-btn btn-copy-uml" title="Copy PlantUML Syntax">📋 Copy</button>
          <button type="button" class="plantuml-btn btn-del-uml danger" title="Delete Diagram">🗑</button>
        </div>
      `;
      if (origLabel) {
        block.replaceChild(header, origLabel);
      } else {
        block.insertBefore(header, diagWrap);
      }
    }

    const btnDiag = header.querySelector(".btn-view-diag");
    const btnCode = header.querySelector(".btn-view-code");
    const btnCopy = header.querySelector(".btn-copy-uml");
    const btnDel = header.querySelector(".btn-del-uml");

    if (btnDel && !btnDel.dataset.wired) {
      btnDel.dataset.wired = "true";
      btnDel.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (confirm("Delete this PlantUML diagram?")) {
          block.remove();
          setDocsDirty(true);
          if (_docsSplit) updateDocsPreview();
        }
      });
    }

    if (btnCopy && !btnCopy.dataset.wired) {
      btnCopy.dataset.wired = "true";
      btnCopy.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const codeText = block.getAttribute("data-plantuml") || (ta ? ta.value : "");
        try {
          await navigator.clipboard.writeText(codeText);
          btnCopy.textContent = "✓ Copied!";
          setTimeout(() => { btnCopy.textContent = "📋 Copy"; }, 1500);
        } catch {
          if (typeof toast === "function") toast("Copied to clipboard", codeText, "ok");
        }
      });
    }

    if (btnDiag && btnCode && !header.dataset.wired) {
      header.dataset.wired = "true";

      btnDiag.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        btnDiag.classList.add("active");
        btnCode.classList.remove("active");
        ta.style.display = "none";
        diagWrap.style.display = "flex";

        const currentCode = (ta ? ta.value.trim() : "") || block.getAttribute("data-plantuml") || "";
        if (currentCode && currentCode !== block.getAttribute("data-plantuml-rendered")) {
          block.setAttribute("data-plantuml", currentCode);
          block.setAttribute("data-plantuml-rendered", currentCode);
          const newUrl = getPlantumlUrl(currentCode);
          if (img) img.src = newUrl;
        }
      });

      btnCode.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        btnCode.classList.add("active");
        btnDiag.classList.remove("active");
        diagWrap.style.display = "none";
        ta.style.display = "block";
        autoResizeDiagramTextarea(ta);
        ta.focus();
      });
    }

    if (trimmedCode && !block.getAttribute("data-plantuml-rendered")) {
      block.setAttribute("data-plantuml-rendered", trimmedCode);
    }

    if (ta && !ta.dataset.wired) {
      ta.dataset.wired = "true";

      ta.addEventListener("paste", (e) => {
        e.stopPropagation();
        setTimeout(() => {
          block.setAttribute("data-plantuml", ta.value);
          setDocsDirty(true);
          autoResizeDiagramTextarea(ta);
        }, 0);
      });
      ta.addEventListener("copy", (e) => e.stopPropagation());
      ta.addEventListener("cut", (e) => {
        e.stopPropagation();
        setTimeout(() => {
          block.setAttribute("data-plantuml", ta.value);
          setDocsDirty(true);
          autoResizeDiagramTextarea(ta);
        }, 0);
      });
      ta.addEventListener("mousedown", (e) => e.stopPropagation());
      ta.addEventListener("mouseup", (e) => e.stopPropagation());
      ta.addEventListener("click", (e) => e.stopPropagation());
      ta.addEventListener("keyup", (e) => e.stopPropagation());

      ta.addEventListener("input", () => {
        block.setAttribute("data-plantuml", ta.value);
        setDocsDirty(true);
        autoResizeDiagramTextarea(ta);
      });

      ta.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Tab") {
          e.preventDefault();
          const start = ta.selectionStart;
          const end = ta.selectionEnd;
          ta.value = ta.value.substring(0, start) + "    " + ta.value.substring(end);
          ta.selectionStart = ta.selectionEnd = start + 4;
          block.setAttribute("data-plantuml", ta.value);
          setDocsDirty(true);
          autoResizeDiagramTextarea(ta);
        } else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) {
          e.preventDefault();
          btnDiag?.click();
        }
      });
    }
  }
}

async function renderAllMermaidBlocks(container) {
  if (!window.mermaid || !container) return;
  const blocks = container.querySelectorAll(".mermaid-block");
  if (!blocks || blocks.length === 0) return;

  const isDark = document.documentElement.getAttribute("data-theme") !== "light";
  try {
    mermaid.initialize({
      startOnLoad: false,
      theme: isDark ? "dark" : "default",
      securityLevel: "loose",
    });
  } catch (e) { }

  for (const block of blocks) {
    let ta = block.querySelector("textarea.mermaid-code-input, textarea");
    const pre = block.querySelector("pre.mermaid, pre.mermaid-code, pre");
    const rawCode = block.getAttribute("data-mermaid") || (ta ? ta.value : (pre ? pre.textContent : ""));
    if (!rawCode || !rawCode.trim()) continue;

    const trimmedCode = rawCode.trim();
    block.setAttribute("data-mermaid", trimmedCode);

    // Convert or ensure textarea element exists
    if (!ta) {
      ta = document.createElement("textarea");
      ta.className = "mermaid-code-input";
      ta.spellcheck = false;
      ta.style.display = "none";
      ta.placeholder = "Type Mermaid syntax here…";
      if (pre) {
        block.replaceChild(ta, pre);
      } else {
        block.appendChild(ta);
      }
    } else if (pre) {
      pre.remove();
    }
    ta.value = trimmedCode;

    // Ensure diagWrap exists
    let diagWrap = block.querySelector(".mermaid-diagram-wrap");
    if (!diagWrap) {
      diagWrap = document.createElement("div");
      diagWrap.className = "mermaid-diagram-wrap";
      diagWrap.setAttribute("contenteditable", "false");
      block.insertBefore(diagWrap, ta);
    }

    // Ensure header exists
    let header = block.querySelector(".mermaid-header");
    if (!header) {
      const origLabel = block.querySelector(".mermaid-label");
      header = document.createElement("div");
      header.className = "mermaid-header";
      header.setAttribute("contenteditable", "false");
      header.innerHTML = `
        <div class="mermaid-title-wrap">
          <span class="mermaid-label">📊 Mermaid Architecture Diagram</span>
          <span class="mermaid-chip">.. mermaid::</span>
        </div>
        <div class="mermaid-actions">
          <button type="button" class="mermaid-btn btn-view-diag active" title="Show Rendered Diagram">👁 Diagram</button>
          <button type="button" class="mermaid-btn btn-view-code" title="View / Edit Diagram Code">📝 Code</button>
          <button type="button" class="mermaid-btn btn-copy-code" title="Copy Diagram Syntax">📋 Copy</button>
          <button type="button" class="mermaid-btn btn-del-diag danger" title="Delete Diagram">🗑</button>
        </div>
      `;
      if (origLabel) {
        block.replaceChild(header, origLabel);
      } else {
        block.insertBefore(header, diagWrap);
      }
    }

    const btnDiag = header.querySelector(".btn-view-diag");
    const btnCode = header.querySelector(".btn-view-code");
    const btnCopy = header.querySelector(".btn-copy-code");
    const btnDel = header.querySelector(".btn-del-diag");

    if (btnDel && !btnDel.dataset.wired) {
      btnDel.dataset.wired = "true";
      btnDel.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        if (confirm("Delete this Mermaid diagram?")) {
          block.remove();
          setDocsDirty(true);
          if (_docsSplit) updateDocsPreview();
        }
      });
    }

    if (btnCopy && !btnCopy.dataset.wired) {
      btnCopy.dataset.wired = "true";
      btnCopy.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        const codeText = block.getAttribute("data-mermaid") || ta.value;
        try {
          await navigator.clipboard.writeText(codeText);
          btnCopy.textContent = "✓ Copied!";
          setTimeout(() => { btnCopy.textContent = "📋 Copy"; }, 1500);
        } catch {
          if (typeof toast === "function") toast("Copied to clipboard", codeText, "ok");
        }
      });
    }

    if (btnDiag && btnCode && !header.dataset.wired) {
      header.dataset.wired = "true";

      btnDiag.addEventListener("click", async (e) => {
        e.preventDefault();
        e.stopPropagation();
        btnDiag.classList.add("active");
        btnCode.classList.remove("active");
        ta.style.display = "none";
        diagWrap.style.display = "flex";

        // Re-render diagram if code was edited
        const currentCode = ta.value.trim() || block.getAttribute("data-mermaid") || "";
        if (currentCode && currentCode !== block.getAttribute("data-mermaid-rendered")) {
          block.setAttribute("data-mermaid", currentCode);
          try {
            _mermaidCounter++;
            const id = `mermaid_dyn_${Date.now()}_${_mermaidCounter}`;
            const { svg } = await mermaid.render(id, currentCode);
            diagWrap.innerHTML = svg;
            block.setAttribute("data-mermaid-rendered", currentCode);
          } catch (renderErr) {
            console.warn("Mermaid re-render error:", renderErr);
            diagWrap.innerHTML = `<div style="color:var(--danger, #f87171); padding:10px; font-size:12px;">⚠️ Mermaid Render Error: ${renderErr.message || renderErr}</div>`;
          }
        }
      });

      btnCode.addEventListener("click", (e) => {
        e.preventDefault();
        e.stopPropagation();
        btnCode.classList.add("active");
        btnDiag.classList.remove("active");
        diagWrap.style.display = "none";

        ta.value = block.getAttribute("data-mermaid") || trimmedCode;
        ta.style.display = "block";
        autoResizeDiagramTextarea(ta);
        setTimeout(() => {
          try { ta.focus(); } catch (err) { }
        }, 15);
      });
    }

    // Keep textarea synchronized when user types
    if (ta && !ta.dataset.wired) {
      ta.dataset.wired = "true";

      // Stop propagation of clipboard events so Quill doesn't cancel or hijack paste/copy/cut
      ta.addEventListener("paste", (e) => {
        e.stopPropagation();
        setTimeout(() => {
          block.setAttribute("data-mermaid", ta.value);
          setDocsDirty(true);
          autoResizeDiagramTextarea(ta);
        }, 0);
      });
      ta.addEventListener("copy", (e) => e.stopPropagation());
      ta.addEventListener("cut", (e) => {
        e.stopPropagation();
        setTimeout(() => {
          block.setAttribute("data-mermaid", ta.value);
          setDocsDirty(true);
          autoResizeDiagramTextarea(ta);
        }, 0);
      });

      // Stop mouse and keyboard bubbling to Quill
      ta.addEventListener("mousedown", (e) => e.stopPropagation());
      ta.addEventListener("mouseup", (e) => e.stopPropagation());
      ta.addEventListener("click", (e) => e.stopPropagation());
      ta.addEventListener("keyup", (e) => e.stopPropagation());

      ta.addEventListener("input", () => {
        block.setAttribute("data-mermaid", ta.value);
        setDocsDirty(true);
        autoResizeDiagramTextarea(ta);
      });

      ta.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Tab") {
          e.preventDefault();
          const start = ta.selectionStart;
          const end = ta.selectionEnd;
          ta.value = ta.value.substring(0, start) + "    " + ta.value.substring(end);
          ta.selectionStart = ta.selectionEnd = start + 4;
          block.setAttribute("data-mermaid", ta.value);
          setDocsDirty(true);
        }
      });

      ta.addEventListener("blur", async () => {
        const updated = ta.value.trim();
        block.setAttribute("data-mermaid", updated);
        setDocsDirty(true);
        if (updated && updated !== block.getAttribute("data-mermaid-rendered")) {
          try {
            _mermaidCounter++;
            const id = `mermaid_blur_${Date.now()}_${_mermaidCounter}`;
            const { svg } = await mermaid.render(id, updated);
            diagWrap.innerHTML = svg;
            block.setAttribute("data-mermaid-rendered", updated);
          } catch (e) {
            console.warn("Re-render failed:", e);
          }
        }
      });
    }

    // Initial render of SVG diagram
    try {
      _mermaidCounter++;
      const id = `mermaid_diag_${Date.now()}_${_mermaidCounter}`;
      const { svg } = await mermaid.render(id, trimmedCode);
      diagWrap.innerHTML = svg;
      block.setAttribute("data-mermaid-rendered", trimmedCode);
      ta.style.display = "none";
      diagWrap.style.display = "flex";
    } catch (renderErr) {
      console.warn("Mermaid render error:", renderErr);
      diagWrap.innerHTML = `<div style="color:var(--danger, #f87171); padding:8px; font-size:12px;">⚠️ Mermaid Render Error: ${renderErr.message || renderErr}</div>`;
      ta.style.display = "block";
      autoResizeTextarea(ta);
      btnCode?.classList.add("active");
      btnDiag?.classList.remove("active");
    }
  }
}

function initQuill() {
  if (_quill || !window.Quill || !$("#quill-editor")) return;
  registerQuillDiagramBlots();
  _quill = new Quill("#quill-editor", {
    theme: "snow",
    placeholder: "Write Sphinx documentation here… Format headings, bold, italic, code blocks visually.",
    modules: {
      toolbar: [
        [{ header: [1, 2, 3, 4, false] }],
        ["bold", "italic", "underline", "strike"],
        ["blockquote", "code-block"],
        [{ list: "ordered" }, { list: "bullet" }],
        ["link", "clean"],
      ],
    },
  });

  const Delta = Quill.import("delta");
  if (Delta && _quill.clipboard) {
    _quill.clipboard.addMatcher(".mermaid-block", function (node, delta) {
      const code = node.getAttribute("data-mermaid") || node.querySelector("textarea")?.value || node.querySelector("pre")?.textContent || "";
      return new Delta().insert({ mermaidBlock: code });
    });
    _quill.clipboard.addMatcher(".plantuml-block", function (node, delta) {
      const code = node.getAttribute("data-plantuml") || node.querySelector("textarea")?.value || node.querySelector("pre")?.textContent || "";
      return new Delta().insert({ plantumlBlock: code });
    });
    _quill.clipboard.addMatcher(".doc-table-block", function (node, delta) {
      const tbl = node.querySelector("table");
      return new Delta().insert({ tableBlock: tbl ? tbl.outerHTML : node.innerHTML });
    });
    _quill.clipboard.addMatcher("table", function (node, delta) {
      if (node.closest(".doc-table-block")) return delta;
      return new Delta().insert({ tableBlock: node.outerHTML });
    });
  }

  _quill.on("text-change", (delta, oldDelta, source) => {
    if (source === "user") {
      setDocsDirty(true);
      if (_docsSplit && _docsEditorType === "wysiwyg") {
        updateDocsPreview();
      }
    }
  });

  initSyncScroll();
}

const MERMAID_TEMPLATES = {
  flowchart: {
    title: "Flowchart / Block Diagram",
    code: `graph TD\n    Client["Client / User"] --> Gateway["API Gateway"]\n    Gateway --> Service["Core Service"]\n    Service --> Database[("Database Storage")]`
  },
  sequence: {
    title: "Sequence Diagram",
    code: `sequenceDiagram\n    autonumber\n    actor User\n    participant UI as Frontend App\n    participant API as Backend Service\n    participant DB as Database\n\n    User->>UI: Submit Request\n    UI->>API: POST /api/v1/action\n    API->>DB: Query / Update Records\n    DB-->>API: Return Result Set\n    API-->>UI: 200 OK (JSON Data)\n    UI-->>User: Render Success View`
  },
  class: {
    title: "Class Diagram",
    code: `classDiagram\n    class CarAudioManager {\n        +int volume\n        +requestAudioFocus()\n    }\n    class CarAudioService {\n        -List zones\n        +handleVolumeChange()\n    }\n    class IAudioControlHAL {\n        <<interface>>\n        +setAudioPortConfig()\n    }\n    CarAudioManager --> CarAudioService : AIDL IPC\n    CarAudioService ..|> IAudioControlHAL : Controls Hardware`
  },
  usecase: {
    title: "Use Case Diagram",
    code: `flowchart LR\n    User["👤 Driver / Passenger"]\n    ADAS["🚨 ADAS Safety System"]\n\n    subgraph System ["Car Audio Management"]\n        UC1(["Media & Radio Playback"])\n        UC2(["Arbitrate Audio Focus"])\n        UC3(["Adjust Volume Groups"])\n        UC4(["Emergency Chime Playback"])\n    end\n\n    User --> UC1\n    User --> UC3\n    ADAS --> UC4\n    UC4 -.->|include| UC2\n    UC1 -.->|include| UC2`
  },
  activity: {
    title: "Activity / Workflow Diagram",
    code: `flowchart TD\n    Start([● Start]) --> Req["Receive Audio Focus Request"]\n    Req --> Check{"Is Emergency / ADAS?"}\n\n    Check -->|Yes| Preempt["Preempt Current Focus"]\n    Preempt --> Duck["Apply Dynamic Ducking (-20dB)"]\n    Duck --> Route["Route Audio to Driver Speakers"]\n\n    Check -->|No| CheckZone{"Target Zone Available?"}\n    CheckZone -->|Yes| Grant["Grant Audio Focus"]\n    Grant --> Route\n    CheckZone -->|No| Reject["Reject Focus Request"]\n\n    Route --> Finish([◉ Finish])\n    Reject --> Finish`
  },
  state: {
    title: "State Machine Diagram",
    code: `stateDiagram-v2\n    [*] --> Idle\n    Idle --> Active : Start Event\n    state Active {\n        [*] --> Initializing\n        Initializing --> Running : Ready\n        Running --> Paused : Interrupt\n        Paused --> Running : Resume\n    }\n    Active --> Terminated : Shutdown\n    Terminated --> [*]`
  }
};

const PLANTUML_TEMPLATES = {
  sequence: {
    title: "Sequence Diagram",
    code: `@startuml\nautonumber\nactor User\nparticipant "Frontend" as UI\nparticipant "Backend" as API\ndatabase "Database" as DB\n\nUser -> UI : Submit Action / Request\nactivate UI\nUI -> API : REST / GraphQL API Call\nactivate API\nAPI -> DB : SQL Query / Transaction\nactivate DB\nDB --> API : Result Set\ndeactivate DB\nAPI --> UI : JSON Response (HTTP 200)\ndeactivate API\nUI --> User : Render Success View\ndeactivate UI\n@enduml`
  },
  class: {
    title: "Class Diagram",
    code: `@startuml\nclass CarAudioManager {\n    -int mVolume\n    +requestAudioFocus()\n    +setGroupVolume(int groupId, int volume)\n}\n\nclass CarAudioService {\n    -List<CarAudioZone> mZones\n    +initialize()\n    +handleVolumeChange()\n}\n\ninterface IAudioControlHAL {\n    +setAudioPortConfig()\n    +onVolumeChange(int bus, float gain)\n}\n\nCarAudioManager --> CarAudioService : Binds via AIDL\nCarAudioService ..|> IAudioControlHAL : Controls Hardware\n@enduml`
  },
  usecase: {
    title: "Use Case Diagram",
    code: `@startuml\nleft to right direction\nactor "Driver / User" as Driver\nactor "ADAS System" as ADAS\n\nrectangle "Audio Management Subsystem" {\n    usecase "Stream Media Playback" as UC1\n    usecase "Arbitrate Audio Focus" as UC2\n    usecase "Adjust Volume Group" as UC3\n    usecase "Broadcast ADAS Warning" as UC4\n}\n\nDriver --> UC1\nDriver --> UC3\nADAS --> UC4\nUC4 ..> UC2 : <<include>>\nUC1 ..> UC2 : <<include>>\n@enduml`
  },
  activity: {
    title: "Activity / Workflow Diagram",
    code: `@startuml\nstart\n:Receive Audio Focus Request;\n\nif (Is Emergency / ADAS Stream?) then (yes)\n    :Preempt Current Focus;\n    :Apply Dynamic Ducking (-20dB);\n    :Route Audio to Driver Speakers;\nelse (no)\n    if (Target Audio Zone Available?) then (yes)\n        :Grant AUDIOFOCUS_REQUEST_GRANTED;\n        :Activate Media Audio Bus;\n    else (no)\n        :Reject AUDIOFOCUS_REQUEST_FAILED;\n        stop\n    endif\nendif\n\n:Notify AudioFocusChange Callback;\nstop\n@enduml`
  },
  component: {
    title: "Component / Block Diagram",
    code: `@startuml\npackage "Application Layer" {\n    [Media Player App] as Media\n    [Navigation System] as Nav\n}\n\npackage "Car Framework Services" {\n    [CarAudioService] as AudioSvc\n    [CarPowerManagement] as PowerSvc\n}\n\nnode "Hardware Abstraction (HAL)" {\n    [AudioControl HAL] as AudioHAL\n    [Vehicle HAL] as VHAL\n}\n\nMedia --> AudioSvc : AIDL IPC\nNav --> AudioSvc : AIDL IPC\nAudioSvc --> AudioHAL : Audio Routing\nPowerSvc --> VHAL : Power State\n@enduml`
  },
  state: {
    title: "State Machine Diagram",
    code: `@startuml\n[*] --> Idle\n\nIdle --> Active : Start Request\nstate Active {\n    [*] --> Initializing\n    Initializing --> Running : Ready\n    Running --> Paused : Interrupt\n    Paused --> Running : Resume\n}\n\nActive --> Stopped : Complete / Abort\nStopped --> [*]\n@enduml`
  }
};

function insertMermaidDiagram(diagramType = "flowchart") {
  // JSON → Chart: open the import modal instead of inserting a template
  if (diagramType === "json-chart") {
    openJsonChartModal();
    return;
  }
  const tmpl = MERMAID_TEMPLATES[diagramType] || MERMAID_TEMPLATES.flowchart;
  const defaultCode = tmpl.code;

  if (_docsEditorType === "raw") {
    const ta = $("#docs-raw-rst");
    if (!ta) return;
    const insertText = `\n.. mermaid::\n\n    ${defaultCode.replace(/\n/g, "\n    ")}\n\n`;
    const start = ta.selectionStart != null ? ta.selectionStart : ta.value.length;
    ta.value = ta.value.substring(0, start) + insertText + ta.value.substring(start);
    ta.selectionStart = ta.selectionEnd = start + insertText.length;
    ta.focus();
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("Mermaid Diagram Added 📊", `Inserted ${tmpl.title} into RST source.`, "ok");
  } else {
    initQuill();
    if (!_quill) return;
    const range = _quill.getSelection(true) || { index: _quill.getLength() };
    _quill.insertEmbed(range.index, "mermaidBlock", defaultCode, Quill.sources.USER);
    _quill.setSelection(range.index + 1, Quill.sources.SILENT);
    renderAllMermaidBlocks(_quill.root);
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("Mermaid Diagram Added 📊", `Inserted ${tmpl.title} into Visual editor.`, "ok");
  }
}

// ===== JSON → Mermaid Chart converter (mirrors sphinx/scripts/json_to_chart.py) =====
const JSON_CHART_SAMPLES = {
  combo: {
    title: "Audio Latency (Bar) vs Drops (Line)",
    type: "combo",
    json: {
      x: ["00:00", "04:00", "08:00", "12:00", "16:00", "20:00"],
      bar: [45, 60, 95, 110, 80, 50],
      line: [40, 55, 85, 105, 75, 45],
      y_label: "Latency (ms) / Drops"
    }
  },
  bar: {
    title: "AOSP Module Build Duration (Seconds)",
    type: "bar",
    json: {
      x: ["OemService", "CarAudio", "VehicleSvc", "dlt-daemon", "Settings"],
      y: [35, 75, 48, 22, 60]
    }
  },
  line: {
    title: "CarAudioService RAM Trend (MB)",
    type: "line",
    json: {
      x: ["10m", "20m", "30m", "40m", "50m", "60m"],
      y: [120, 145, 190, 185, 210, 215]
    }
  },
  pie: {
    title: "Audio Routing Context Distribution",
    type: "pie",
    json: {
      media: 45, navigation: 25, phone_call: 15, assistant: 10, chime: 5
    }
  },
  timeline: {
    title: "Automotive Platform Milestones",
    type: "timeline",
    json: {
      "2024 Q3": ["AOSP 13 Baseline", "CarAudio Initial Bringup"],
      "2024 Q4": ["Qualcomm SA8155 BSP", "Vehicle HAL v2.0"],
      "2025 Q1": ["COVESA DLT Logging", "Audio Zone Routing"],
      "2025 Q2": ["Production Release", "OTA Firmware Update"]
    }
  },
  flow: {
    title: "AOSP Audio HAL & CarService Flow",
    type: "flow",
    json: {
      nodes: [
        "CarAudioService", "OemCarService", "AudioControl HAL", "Audio HW HAL", "DSP Driver"
      ],
      edges: [
        ["CarAudioService", "OemCarService", "AIDL evaluate"],
        ["CarAudioService", "AudioControl HAL", "IAudioControl/default"],
        ["AudioControl HAL", "Audio HW HAL", "setParameters()"],
        ["Audio HW HAL", "DSP Driver", "ALSA / TinyALSA"]
      ]
    }
  }
};

function _jsonChartSanitize(text, fallback = "item") {
  if (text === null || text === undefined) text = fallback;
  return String(text).replace(/"/g, "'").replace(/\n/g, " ").trim() || fallback;
}

function _jsonChartPairs(data) {
  if (Array.isArray(data)) {
    return data.map(item => {
      if (!Array.isArray(item) || item.length !== 2) {
        throw new Error("Array form must be [[label, value], ...] pairs");
      }
      return item;
    });
  }
  if (data && typeof data === "object") {
    if (Array.isArray(data.x) && Array.isArray(data.y)) {
      if (data.x.length !== data.y.length) {
        throw new Error("'x' and 'y' arrays must have the same length");
      }
      return data.x.map((x, i) => [x, data.y[i]]);
    }
    return Object.entries(data);
  }
  throw new Error("Unsupported JSON shape for pie/bar/line charts");
}

function jsonToMermaid(data, type, title) {
  const t = type || _jsonChartDetectType(data);

  // 1. Combo chart (Bar + Line together in xychart-beta)
  if (t === "combo") {
    if (!data || typeof data !== "object") {
      throw new Error("Combo chart JSON must be {\"x\": [...], \"bar\": [...], \"line\": [...]}");
    }
    const xLabels = (data.x || []).map(x => `"${_jsonChartSanitize(x)}"`).join(", ");
    const barVals = (data.bar || []).map(v => Number(v) || 0);
    const lineVals = (data.line || []).map(v => Number(v) || 0);
    if (!barVals.length && !lineVals.length) {
      throw new Error("Combo chart must provide 'bar' and/or 'line' numeric arrays");
    }
    const allVals = [...barVals, ...lineVals];
    const yMax = Math.max(...allVals, 1);
    const yMin = Math.min(0, ...allVals);
    const lines = ["xychart-beta"];
    if (title) lines.push(`    title "${_jsonChartSanitize(title)}"`);
    lines.push(`    x-axis [${xLabels}]`);
    lines.push(`    y-axis "${_jsonChartSanitize(data.y_label || 'Value')}" ${yMin} --> ${yMax}`);
    if (barVals.length) lines.push(`    bar [${barVals.join(", ")}]`);
    if (lineVals.length) lines.push(`    line [${lineVals.join(", ")}]`);
    return lines;
  }

  // 2. Timeline Roadmap
  if (t === "timeline") {
    const lines = ["timeline"];
    if (title) lines.push(`    title ${_jsonChartSanitize(title)}`);
    if (Array.isArray(data)) {
      data.forEach(item => {
        if (typeof item === "object") {
          Object.entries(item).forEach(([period, events]) => {
            lines.push(`    section ${_jsonChartSanitize(period)}`);
            const evs = Array.isArray(events) ? events : [events];
            evs.forEach(ev => lines.push(`        ${_jsonChartSanitize(ev)}`));
          });
        }
      });
    } else if (data && typeof data === "object") {
      Object.entries(data).forEach(([period, events]) => {
        lines.push(`    section ${_jsonChartSanitize(period)}`);
        const evs = Array.isArray(events) ? events : [events];
        evs.forEach(ev => lines.push(`        ${_jsonChartSanitize(ev)}`));
      });
    }
    return lines;
  }

  // 3. Flowchart
  if (t === "flow") {
    if (!data || typeof data !== "object" || !Array.isArray(data.nodes) || !Array.isArray(data.edges)) {
      throw new Error("Flow chart JSON must be {\"nodes\": [...], \"edges\": [[src, dst, label?], ...]}");
    }
    const lines = ["flowchart LR"];
    if (title) lines.push(`    %% ${_jsonChartSanitize(title)}`);
    const idByLabel = {};
    data.nodes.forEach((node, idx) => {
      const id = `N${idx}`;
      idByLabel[String(node)] = id;
      lines.push(`    ${id}["${_jsonChartSanitize(node)}"]`);
    });
    data.edges.forEach(edge => {
      if (!Array.isArray(edge) || edge.length < 2) {
        throw new Error(`Edge must be [src, dst] or [src, dst, label]: ${JSON.stringify(edge)}`);
      }
      const srcId = idByLabel[String(edge[0])];
      const dstId = idByLabel[String(edge[1])];
      if (srcId === undefined || dstId === undefined) {
        throw new Error(`Edge references unknown node: ${JSON.stringify(edge)}. All endpoints must be listed in 'nodes'.`);
      }
      if (edge.length >= 3 && edge[2]) {
        lines.push(`    ${srcId} -->|"${_jsonChartSanitize(edge[2])}"| ${dstId}`);
      } else {
        lines.push(`    ${srcId} --> ${dstId}`);
      }
    });
    return lines;
  }

  // 4. Pie chart
  const pairs = _jsonChartPairs(data).map(([label, value]) => {
    const num = Number(value);
    if (value === null || value === "" || Number.isNaN(num)) {
      throw new Error(`Expected numeric value for key '${label}', got: ${JSON.stringify(value)}`);
    }
    return [_jsonChartSanitize(label), num];
  });
  if (t === "pie") {
    const lines = ["pie showData"];
    if (title) lines.push(`    title ${_jsonChartSanitize(title)}`);
    pairs.forEach(([label, value]) => lines.push(`    "${label}" : ${value}`));
    return lines;
  }

  // 5. xychart-beta (single bar or single line)
  const labels = pairs.map(p => `"${p[0]}"`).join(", ");
  const values = pairs.map(p => p[1]);
  const yMax = Math.max(...values, 1);
  const yMin = Math.min(0, ...values);
  const lines = ["xychart-beta"];
  if (title) lines.push(`    title "${_jsonChartSanitize(title)}"`);
  lines.push(`    x-axis [${labels}]`);
  lines.push(`    y-axis "Value" ${yMin} --> ${yMax}`);
  lines.push(`    ${t} [${values.join(", ")}]`);
  return lines;
}

function _jsonChartDetectType(data) {
  if (data && typeof data === "object" && !Array.isArray(data)) {
    if (Array.isArray(data.nodes) && Array.isArray(data.edges)) return "flow";
    if (Array.isArray(data.x) && (Array.isArray(data.bar) || Array.isArray(data.line))) {
      if (Array.isArray(data.bar) && Array.isArray(data.line)) return "combo";
      if (Array.isArray(data.bar)) return "bar";
      if (Array.isArray(data.line)) return "line";
    }
    if (Array.isArray(data.x) && Array.isArray(data.y)) return "bar";
    const values = Object.values(data);
    if (values.length && values.every(v => Array.isArray(v) && v.every(item => typeof item === "string"))) {
      return "timeline";
    }
  }
  return "pie";
}

function openJsonChartModal() {
  const modal = $("#modal-json-chart");
  if (!modal) return;
  const input = $("#json-chart-input");
  const typeSel = $("#json-chart-type");
  const titleIn = $("#json-chart-title");
  const previewWrap = $("#json-chart-preview-wrap");
  if (input) input.value = "";
  if (typeSel) typeSel.value = "auto";
  if (titleIn) titleIn.value = "";
  if (previewWrap) previewWrap.style.display = "none";
  modal.classList.remove("hidden");
  setTimeout(() => input?.focus(), 40);
}

function wireJsonChartModal() {
  const modal = $("#modal-json-chart");
  if (!modal || modal.dataset.wired === "1") return;
  modal.dataset.wired = "1";

  const input = $("#json-chart-input");
  const typeSel = $("#json-chart-type");
  const titleIn = $("#json-chart-title");
  const previewWrap = $("#json-chart-preview-wrap");
  const previewPre = $("#json-chart-preview");

  function buildLines() {
    const raw = input?.value.trim() || "";
    if (!raw) throw new Error("JSON input is empty");
    let data;
    try {
      data = JSON.parse(raw);
    } catch (e) {
      throw new Error("Invalid JSON: " + e.message);
    }
    const type = typeSel?.value === "auto" ? null : typeSel?.value;
    return jsonToMermaid(data, type, titleIn?.value.trim() || null);
  }

  $("#btn-json-chart-cancel")?.addEventListener("click", () => modal.classList.add("hidden"));
  $("#btn-json-chart-preview")?.addEventListener("click", () => {
    try {
      const lines = buildLines();
      if (previewPre) previewPre.textContent = lines.join("\n");
      if (previewWrap) previewWrap.style.display = "block";
    } catch (e) {
      toast("JSON Chart Error ⚠️", e.message, "err");
    }
  });
  $("#btn-json-chart-insert")?.addEventListener("click", () => {
    let lines;
    try {
      lines = buildLines();
    } catch (e) {
      toast("JSON Chart Error ⚠️", e.message, "err");
      return;
    }
    modal.classList.add("hidden");
    insertMermaidCode(lines.join("\n"), "JSON Chart");
  });

  // Ctrl+Enter in textarea inserts directly
  input?.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key === "Enter") {
      e.preventDefault();
      $("#btn-json-chart-insert")?.click();
    }
  });

  // Sample chips: load predefined JSON into the textarea
  modal.querySelectorAll(".btn-json-sample").forEach(chip => {
    chip.addEventListener("click", (e) => {
      e.stopPropagation();
      const key = chip.dataset.sample;
      const sample = JSON_CHART_SAMPLES[key];
      if (!sample || !input) return;
      input.value = JSON.stringify(sample.json, null, 2);
      if (typeSel) typeSel.value = sample.type;
      if (titleIn) titleIn.value = sample.title;
      // Auto-preview so the user immediately sees the mermaid output
      try {
        const lines = jsonToMermaid(sample.json, sample.type, sample.title);
        if (previewPre) previewPre.textContent = lines.join("\n");
        if (previewWrap) previewWrap.style.display = "block";
      } catch { /* ignore preview errors */ }
    });
  });
}

function insertMermaidCode(code, label = "Mermaid Diagram") {
  if (_docsEditorType === "raw") {
    const ta = $("#docs-raw-rst");
    if (!ta) return;
    const insertText = `\n.. mermaid::\n\n    ${code.replace(/\n/g, "\n    ")}\n\n`;
    const start = ta.selectionStart != null ? ta.selectionStart : ta.value.length;
    ta.value = ta.value.substring(0, start) + insertText + ta.value.substring(start);
    ta.selectionStart = ta.selectionEnd = start + insertText.length;
    ta.focus();
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("Mermaid Diagram Added 📊", `Inserted ${label} into RST source.`, "ok");
  } else {
    initQuill();
    if (!_quill) return;
    const range = _quill.getSelection(true) || { index: _quill.getLength() };
    _quill.insertEmbed(range.index, "mermaidBlock", code, Quill.sources.USER);
    _quill.setSelection(range.index + 1, Quill.sources.SILENT);
    renderAllMermaidBlocks(_quill.root);
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("Mermaid Diagram Added 📊", `Inserted ${label} into Visual editor.`, "ok");
  }
}

function insertPlantumlDiagram(diagramType = "sequence") {
  const tmpl = PLANTUML_TEMPLATES[diagramType] || PLANTUML_TEMPLATES.sequence;
  const defaultCode = tmpl.code;

  if (_docsEditorType === "raw") {
    const ta = $("#docs-raw-rst");
    if (!ta) return;
    const insertText = `\n.. uml::\n\n    ${defaultCode.replace(/\n/g, "\n    ")}\n\n`;
    const start = ta.selectionStart != null ? ta.selectionStart : ta.value.length;
    ta.value = ta.value.substring(0, start) + insertText + ta.value.substring(start);
    ta.selectionStart = ta.selectionEnd = start + insertText.length;
    ta.focus();
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("PlantUML Diagram Added 📐", `Inserted ${tmpl.title} into RST source.`, "ok");
  } else {
    initQuill();
    if (!_quill) return;
    const range = _quill.getSelection(true) || { index: _quill.getLength() };
    _quill.insertEmbed(range.index, "plantumlBlock", defaultCode, Quill.sources.USER);
    _quill.setSelection(range.index + 1, Quill.sources.SILENT);
    wirePlantumlBlocks(_quill.root);
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("PlantUML Diagram Added 📐", `Inserted ${tmpl.title} into Visual editor.`, "ok");
  }
}

function insertTableBlock() {
  const defaultTableHtml = `
    <table class="doc-table-grid">
      <caption>Table Title</caption>
      <thead>
        <tr><th>Header 1</th><th>Header 2</th><th>Header 3</th></tr>
      </thead>
      <tbody>
        <tr><td>Data 1</td><td>Data 2</td><td>Data 3</td></tr>
        <tr><td>Data 4</td><td>Data 5</td><td>Data 6</td></tr>
      </tbody>
    </table>
  `;

  if (_docsEditorType === "raw") {
    const ta = $("#docs-raw-rst");
    if (!ta) return;
    const rstTable = `\n.. list-table:: Table Title\n   :widths: 30 35 35\n   :header-rows: 1\n\n   * - Header 1\n     - Header 2\n     - Header 3\n   * - Data 1\n     - Data 2\n     - Data 3\n   * - Data 4\n     - Data 5\n     - Data 6\n\n`;
    const start = ta.selectionStart != null ? ta.selectionStart : ta.value.length;
    ta.value = ta.value.substring(0, start) + rstTable + ta.value.substring(start);
    ta.selectionStart = ta.selectionEnd = start + rstTable.length;
    ta.focus();
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("Table Added ▦", "Inserted .. list-table:: template into RST source.", "ok");
  } else {
    initQuill();
    if (!_quill) return;
    const range = _quill.getSelection(true) || { index: _quill.getLength() };
    _quill.insertEmbed(range.index, "tableBlock", defaultTableHtml, Quill.sources.USER);
    _quill.setSelection(range.index + 1, Quill.sources.SILENT);
    wireDocTableBlocks(_quill.root);
    setDocsDirty(true);
    if (_docsSplit) updateDocsPreview();
    toast("Table Added ▦", "Inserted interactive Table into Visual editor.", "ok");
  }
}

function setDocsDirty(val) {
  _docsDirty = Boolean(val);
  const badge = $("#docs-dirty-badge");
  if (badge) badge.style.display = _docsDirty ? "inline" : "none";
}

async function loadDocsFiles(customDir = _docsCustomDir) {
  const sel = $("#docs-file-select");
  if (sel) sel.innerHTML = '<option value="">Loading .rst files…</option>';
  try {
    const url = `/api/docs/files?dir=${encodeURIComponent(customDir || "")}`;
    const res = await fetch(url);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Failed to scan docs files");
    _docsFiles = data.files || [];
    const activeDir = data.dir || _docsCustomDir || "";
    _docsActiveDir = data.dir || _docsCustomDir || "";
    const dirLabel = $("#docs-dir-label");
    if (dirLabel) {
      if (data.dir) {
        const parts = data.dir.replace(/\\/g, "/").split("/").filter(Boolean);
        dirLabel.textContent = parts.length > 1 ? parts.slice(-2).join("/") : (parts[0] || "docs");
        dirLabel.parentElement.title = `Docs Root: ${data.dir} (Click to change)`;
      } else {
        dirLabel.textContent = "docs";
        dirLabel.parentElement.title = "Default docs root (Click to change)";
      }
      dirLabel.textContent = "docs";
      dirLabel.parentElement.title = data.dir ? `Docs Root: ${data.dir} (Click to change)` : "Default docs root (Click to change)";
    }
    const dirBadge = $("#docs-active-dir-badge");
    if (dirBadge) {
      if (activeDir) {
        dirBadge.style.display = "inline-flex";
        dirBadge.textContent = activeDir;
        dirBadge.title = `Active Docs Root: ${activeDir} (Click to change)`;
      } else {
        dirBadge.style.display = "none";
      }
    }
    renderDocsFileSelect();
    if (_docsFiles.length > 0 && (!_currentDoc || !_docsFiles.some(f => f.name === _currentDoc.name))) {
      const savedDoc = localStorage.getItem("telua_web_docs_last_file");
      const matched = savedDoc ? _docsFiles.find(f => f.name === savedDoc) : null;
      const arch = matched || _docsFiles.find(f => f.name.includes("chapter3_section1") || f.name.includes("chapter1_section1") || f.name.includes("index.rst")) || _docsFiles[0];
      loadDocFile(arch.name);
    }
  } catch (err) {
    if (sel) sel.innerHTML = `<option value="">Error loading docs (${err.message})</option>`;
    toast("Docs Scan Failed", String(err.message || err), "danger");
  }
}

function renderDocsFileSelect() {
  const sel = $("#docs-file-select");
  if (!sel) return;
  if (_docsFiles.length === 0) {
    sel.innerHTML = '<option value="">No .rst files found</option>';
    return;
  }
  const groups = {};
  for (const f of _docsFiles) {
    const cat = f.category || "other";
    if (!groups[cat]) groups[cat] = [];
    groups[cat].push(f);
  }
  let html = '<option value="">— Select an .rst file to edit —</option>';
  for (const [cat, files] of Object.entries(groups)) {
    const label = cat.charAt(0).toUpperCase() + cat.slice(1);
    html += `<optgroup label="Template: ${label}">`;
    for (const f of files) {
      const selected = _currentDoc && _currentDoc.name === f.name ? "selected" : "";
      html += `<option value="${f.name}" ${selected}>${f.title || f.name} (${f.name})</option>`;
    }
    html += `</optgroup>`;
  }
  sel.innerHTML = html;
}

async function loadDocFile(name) {
  if (!name) return;
  if (_docsDirty && !confirm("You have unsaved changes in the current document. Discard and switch file?")) {
    renderDocsFileSelect();
    return;
  }
  initQuill();
  const badge = $("#docs-status-badge");
  if (badge) badge.textContent = "Loading…";
  try {
    const url = `/api/docs/file?name=${encodeURIComponent(name)}&dir=${encodeURIComponent(_docsCustomDir || _docsActiveDir || "")}`;
    const res = await fetch(url);
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Failed to read file");
    _currentDoc = data;
    setDocsDirty(false);

    if (_quill) {
      _quill.setText("");
      if (data.html) {
        _quill.clipboard.dangerouslyPasteHTML(0, data.html);
      }
      renderAllMermaidBlocks(_quill.root);
      wirePlantumlBlocks(_quill.root);
      wireDocTableBlocks(_quill.root);
    }
    const rawTa = $("#docs-raw-rst");
    if (rawTa) rawTa.value = data.rst || "";

    const meta = $("#docs-file-meta");
    if (meta) {
      const fullPath = data.full_path || data.name;
      meta.textContent = `📄 ${fullPath} · ${data.rst.length} chars · format: RST`;
      meta.title = `Full path: ${fullPath}`;
    }
    if (badge) badge.textContent = data.readonly ? "Read-only" : "Ready";
    renderDocsFileSelect();
    try {
      localStorage.setItem("telua_web_docs_last_file", name);
    } catch (e) { }
    applyDocsModeUI();
    if (_docsSplit) updateDocsPreview();
  } catch (err) {
    toast("Failed to open doc", String(err.message || err), "danger");
    if (badge) badge.textContent = "Error";
  }
}

function applyDocsModeUI() {
  const wysiwygPane = $("#docs-pane-wysiwyg");
  const rawPane = $("#docs-pane-raw");
  const previewPane = $("#docs-pane-preview");

  $("#btn-docs-mode-wysiwyg")?.classList.toggle("active", _docsEditorType === "wysiwyg");
  $("#btn-docs-mode-raw")?.classList.toggle("active", _docsEditorType === "raw");
  $("#btn-docs-mode-split")?.classList.toggle("active", _docsSplit);

  if (_docsSplit) {
    previewPane?.classList.remove("hidden");
    if (_docsEditorType === "raw") {
      wysiwygPane?.classList.add("hidden");
      wysiwygPane?.classList.remove("split-left");
      rawPane?.classList.remove("hidden");
      rawPane?.classList.add("split-left");
    } else {
      rawPane?.classList.add("hidden");
      rawPane?.classList.remove("split-left");
      wysiwygPane?.classList.remove("hidden");
      wysiwygPane?.classList.add("split-left");
    }
    updateDocsPreview();
  } else {
    previewPane?.classList.add("hidden");
    if (_docsEditorType === "raw") {
      wysiwygPane?.classList.add("hidden");
      wysiwygPane?.classList.remove("split-left");
      rawPane?.classList.remove("hidden");
      rawPane?.classList.remove("split-left");
    } else {
      rawPane?.classList.add("hidden");
      rawPane?.classList.remove("split-left");
      wysiwygPane?.classList.remove("hidden");
      wysiwygPane?.classList.remove("split-left");
    }
  }

  try {
    localStorage.setItem("telua_web_docs_editor", _docsEditorType);
    localStorage.setItem("telua_web_docs_split", String(_docsSplit));
    localStorage.setItem("telua_web_docs_mode", _docsSplit ? "split" : _docsEditorType);
  } catch (e) { }

  initSyncScroll();
}

function getActiveDocsEditorElement() {
  if (_docsEditorType === "raw") {
    return $("#docs-raw-rst");
  }
  const root = _quill ? _quill.root : $("#quill-editor .ql-editor");
  if (root) return root;
  return $("#quill-editor");
}

function syncScroll(sourceElem, targetElem) {
  if (!_docsSplit || !_docsSyncScroll || !sourceElem || !targetElem) return;
  if (_syncScrollSource && _syncScrollSource !== sourceElem) return;

  _syncScrollSource = sourceElem;
  clearTimeout(_syncScrollTimer);

  const maxSource = sourceElem.scrollHeight - sourceElem.clientHeight;
  const maxTarget = targetElem.scrollHeight - targetElem.clientHeight;

  if (maxSource <= 0 || maxTarget <= 0) {
    if (maxTarget <= 0) targetElem.scrollTop = 0;
  } else {
    if (sourceElem.scrollTop <= 4) {
      targetElem.scrollTop = 0;
    } else if (sourceElem.scrollTop >= maxSource - 4) {
      targetElem.scrollTop = maxTarget;
    } else {
      const ratio = sourceElem.scrollTop / maxSource;
      targetElem.scrollTop = Math.round(ratio * maxTarget);
    }
  }

  _syncScrollTimer = setTimeout(() => {
    _syncScrollSource = null;
  }, 60);
}

function updateSyncScrollButtonUI() {
  const btn = $("#btn-docs-sync-scroll");
  if (!btn) return;
  btn.classList.toggle("active", Boolean(_docsSyncScroll));
  btn.textContent = _docsSyncScroll ? "🔗 Sync On" : "🔓 Sync Off";
  btn.title = _docsSyncScroll
    ? "Synchronized scrolling is ON (Editor & Preview scroll together). Click to toggle."
    : "Synchronized scrolling is OFF. Click to toggle.";
}

function initSyncScroll() {
  updateSyncScrollButtonUI();

  const preview = $("#docs-preview-content");
  if (preview && !preview.dataset.syncBound) {
    preview.dataset.syncBound = "1";
    preview.addEventListener("scroll", () => {
      const target = getActiveDocsEditorElement();
      if (target) syncScroll(preview, target);
    }, { passive: true });
  }

  const rawTa = $("#docs-raw-rst");
  if (rawTa && !rawTa.dataset.syncBound) {
    rawTa.dataset.syncBound = "1";
    rawTa.addEventListener("scroll", () => {
      if (_docsEditorType === "raw" && preview) {
        syncScroll(rawTa, preview);
      }
    }, { passive: true });
  }

  const qlEditor = (_quill && _quill.root) || $("#quill-editor .ql-editor");
  if (qlEditor && !qlEditor.dataset.syncBound) {
    qlEditor.dataset.syncBound = "1";
    qlEditor.addEventListener("scroll", () => {
      if (_docsEditorType === "wysiwyg" && preview) {
        syncScroll(qlEditor, preview);
      }
    }, { passive: true });
  }

  const qlContainer = $("#quill-editor");
  if (qlContainer && !qlContainer.dataset.syncBound) {
    qlContainer.dataset.syncBound = "1";
    qlContainer.addEventListener("scroll", () => {
      if (_docsEditorType === "wysiwyg" && preview) {
        syncScroll(qlContainer, preview);
      }
    }, { passive: true });
  }
}

async function switchToEditorType(type) {
  if (type === _docsEditorType) return;
  initQuill();
  const badge = $("#docs-status-badge");

  if (_docsEditorType === "wysiwyg" && type === "raw") {
    // Convert current Quill HTML to RST
    if (_quill && _docsDirty) {
      if (badge) badge.textContent = "Converting HTML → RST…";
      try {
        const res = await fetch("/api/docs/convert", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: _quill.root.innerHTML, direction: "html2rst" }),
        });
        const data = await res.json();
        if (data.ok && $("#docs-raw-rst")) {
          $("#docs-raw-rst").value = data.rst;
        }
      } catch (err) {
        console.error("HTML2RST conversion failed:", err);
      }
      if (badge) badge.textContent = "Ready";
    }
  } else if (_docsEditorType === "raw" && type === "wysiwyg") {
    // Convert current raw RST to HTML for Quill
    const rst = $("#docs-raw-rst")?.value || "";
    if (badge) badge.textContent = "Converting RST → HTML…";
    try {
      const res = await fetch("/api/docs/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: rst, direction: "rst2html" }),
      });
      const data = await res.json();
      if (data.ok && _quill) {
        _quill.setText("");
        _quill.clipboard.dangerouslyPasteHTML(0, data.html || "<p></p>");
        renderAllMermaidBlocks(_quill.root);
        wirePlantumlBlocks(_quill.root);
        wireDocTableBlocks(_quill.root);
      }
    } catch (err) {
      console.error("RST2HTML conversion failed:", err);
    }
    if (badge) badge.textContent = "Ready";
  }

  _docsEditorType = type;
  _docsMode = _docsSplit ? "split" : _docsEditorType;
  applyDocsModeUI();
}

function toggleDocsSplit() {
  _docsSplit = !_docsSplit;
  _docsMode = _docsSplit ? "split" : _docsEditorType;
  applyDocsModeUI();
}

async function setDocsMode(mode) {
  if (mode === "wysiwyg") {
    await switchToEditorType("wysiwyg");
  } else if (mode === "raw") {
    await switchToEditorType("raw");
  } else if (mode === "split") {
    toggleDocsSplit();
  }
}

let _previewDebounceTimer = null;
async function updateDocsPreview() {
  const preview = $("#docs-preview-content");
  if (!preview) return;

  const editorElem = getActiveDocsEditorElement();
  let prevRatio = 0;
  if (editorElem) {
    const maxSource = editorElem.scrollHeight - editorElem.clientHeight;
    if (maxSource > 0) {
      prevRatio = editorElem.scrollTop / maxSource;
    }
  }

  if (_docsEditorType === "raw") {
    const rawTa = $("#docs-raw-rst");
    if (!rawTa) return;
    clearTimeout(_previewDebounceTimer);
    _previewDebounceTimer = setTimeout(async () => {
      try {
        const res = await fetch("/api/docs/convert", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ content: rawTa.value, direction: "rst2html" }),
        });
        const data = await res.json();
        if (data.ok && data.html) {
          preview.innerHTML = data.html;
          await renderAllMermaidBlocks(preview);
          wirePlantumlBlocks(preview);
          wireDocTableBlocks(preview);
          if (_docsSyncScroll) {
            const maxTarget = preview.scrollHeight - preview.clientHeight;
            if (maxTarget > 0 && prevRatio > 0) {
              preview.scrollTop = Math.round(prevRatio * maxTarget);
            }
          }
        }
      } catch (err) {
        console.warn("Live preview convert error:", err);
      }
    }, 200);
    return;
  }

  if (_quill) {
    preview.innerHTML = _quill.root.innerHTML;
    await renderAllMermaidBlocks(preview);
    wirePlantumlBlocks(preview);
    wireDocTableBlocks(preview);
    if (_docsSyncScroll) {
      const maxTarget = preview.scrollHeight - preview.clientHeight;
      if (maxTarget > 0 && prevRatio > 0) {
        preview.scrollTop = Math.round(prevRatio * maxTarget);
      }
    }
  }
}

async function saveCurrentDoc() {
  if (!_currentDoc || !_currentDoc.name) {
    toast("No file open", "Please select a documentation file first.", "warn");
    return;
  }
  const badge = $("#docs-status-badge");
  if (badge) badge.textContent = "Saving…";

  let content = "";
  let format = "rst";
  if (_docsEditorType === "raw") {
    content = $("#docs-raw-rst")?.value || "";
    format = "rst";
  } else {
    content = _quill ? _quill.root.innerHTML : "";
    format = "html";
  }

  try {
    const res = await fetch("/api/docs/file", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: _currentDoc.name,
        dir: _docsCustomDir || _docsActiveDir || "",
        content: content,
        format: format,
      }),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "Save failed");
    _currentDoc.rst = data.rst;
    _currentDoc.html = data.html;
    if ($("#docs-raw-rst")) $("#docs-raw-rst").value = data.rst;
    setDocsDirty(false);
    if (badge) badge.textContent = "Saved ✔";
    toast("Saved Successfully 💾", `${_currentDoc.name} written (backup .rst.bak created).`, "ok", 3000);
  } catch (err) {
    if (badge) badge.textContent = "Save Failed";
    toast("Save Failed", String(err.message || err), "danger");
  }
}

function getActiveDocsDirHint() {
  if (_docsCustomDir) return _docsCustomDir;
  const badgeText = $("#docs-active-dir-badge")?.textContent;
  if (badgeText) return badgeText;
  if (_docsActiveDir) return _docsActiveDir;
  if (_currentDoc?.full_path) {
    return _currentDoc.full_path.replace(/[\\/][^\\/]+$/, "");
  }
  return "sphinx/templates/architecture";
}

async function buildSphinxDocs() {
  const badge = $("#docs-status-badge");
  const targetDirHint = getActiveDocsDirHint();
  if (badge) {
    badge.textContent = "Building Sphinx…";
    badge.title = `Building docs in: ${targetDirHint}`;
  }
  toast("Building Docs 🔨", `Directory: ${targetDirHint}\nCompiling Sphinx HTML in background…`, "info", 4000);
  try {
    const res = await fetch("/api/docs/build", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dir: _docsCustomDir || _docsActiveDir || "",
        current_file: _currentDoc?.full_path || _currentDoc?.name || "",
      }),
    });
    const data = await res.json();
    if (data.ok) {
      if (badge) {
        badge.textContent = "Build Success ✔";
        badge.title = `Built: ${data.target_dir}\nOutput: ${data.html_dir}`;
      }
      if (data.target_dir) _docsActiveDir = data.target_dir;
      toast("Sphinx Build Succeeded 🎉", `Source: ${data.target_dir}\nOutput: ${data.html_dir}`, "ok", 6000);
    } else {
      if (badge) badge.textContent = "Build Warning";
      const errDetail = data.stderr || data.error || "Build returned non-zero code";
      toast("Sphinx Build Warning", `Directory: ${data.target_dir || targetDirHint}\n${errDetail.slice(0, 160)}`, "warn", 6000);
    }
  } catch (err) {
    if (badge) badge.textContent = "Build Error";
    toast("Build Error", `Directory: ${targetDirHint}\n${String(err.message || err)}`, "danger");
  }
}

async function startSphinxDocs() {
  const badge = $("#docs-status-badge");
  const targetDirHint = getActiveDocsDirHint();
  if (badge) {
    badge.textContent = "Starting Docs Server…";
    badge.title = `Starting HTTP preview server for: ${targetDirHint}`;
  }
  toast("Launching Docs 🚀", `Directory: ${targetDirHint}\nStarting HTTP preview server & opening browser…`, "info", 4000);
  try {
    const res = await fetch("/api/docs/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dir: _docsCustomDir || _docsActiveDir || "",
        current_file: _currentDoc?.full_path || _currentDoc?.name || "",
      }),
    });
    const data = await res.json();
    if (data.ok) {
      if (badge) {
        badge.textContent = `Live :${data.port || 8789} ✔`;
        badge.title = `Directory: ${data.target_dir}\nServing: ${data.html_dir}\nURL: ${data.url}`;
      }
      if (data.target_dir) _docsActiveDir = data.target_dir;
      toast("Docs Server Live 🌐", `Source: ${data.target_dir}\nServing: ${data.html_dir}\nURL: ${data.url}`, "ok", 6000);
      try {
        const previewUrl = data.cache_bust_url || `${data.url}/?_t=${Date.now()}`;
        window.open(previewUrl, "_blank");
      } catch { /* browser popup blocker */ }
    } else {
      if (badge) badge.textContent = "Server Error";
      toast("Failed to start docs server", `Directory: ${data.target_dir || targetDirHint}\n${data.error || "Unknown error"}`, "danger");
    }
  } catch (err) {
    if (badge) badge.textContent = "Server Error";
    toast("Server Error", `Directory: ${targetDirHint}\n${String(err.message || err)}`, "danger");
  }
}

async function cleanSphinxDocs() {
  const badge = $("#docs-status-badge");
  const targetDirHint = getActiveDocsDirHint();
  if (badge) badge.textContent = "Cleaning…";
  toast("Cleaning Cache 🧹", `Removing _build cache in: ${targetDirHint}…`, "info", 3000);
  try {
    const res = await fetch("/api/docs/clean", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        dir: _docsCustomDir || _docsActiveDir || "",
        current_file: _currentDoc?.full_path || _currentDoc?.name || "",
      }),
    });
    const data = await res.json();
    if (data.ok) {
      if (badge) badge.textContent = "Cleaned ✔";
      toast("Cache Cleaned 🧹", `Removed build cache: ${data.cleaned_dir}\nReady for fresh compile.`, "ok", 4000);
    } else {
      if (badge) badge.textContent = "Clean Error";
      toast("Clean Error", data.error || "Failed to remove cache", "danger");
    }
  } catch (err) {
    if (badge) badge.textContent = "Clean Error";
    toast("Clean Error", String(err.message || err), "danger");
  }
}

async function handleDocsFileUpload(file) {
  if (!file) return;
  initQuill();
  const badge = $("#docs-status-badge");
  if (badge) badge.textContent = "Importing…";

  try {
    const rawText = await file.text();
    const fname = file.name.toLowerCase();
    let rstContent = "";
    let htmlContent = "";

    if (fname.endsWith(".html") || fname.endsWith(".htm")) {
      htmlContent = rawText;
      const res = await fetch("/api/docs/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: rawText, direction: "html2rst" }),
      });
      const data = await res.json();
      rstContent = data.ok ? data.rst : rawText;
    } else {
      rstContent = rawText;
      const res = await fetch("/api/docs/convert", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content: rawText, direction: "rst2html" }),
      });
      const data = await res.json();
      htmlContent = data.ok ? data.html : `<p>${rawText}</p>`;
    }

    let saveName = file.name;
    if (!saveName.endsWith(".rst")) {
      saveName = saveName.replace(/\.[^.]+$/, "") + ".rst";
    }
    if (!saveName.includes("/")) {
      saveName = `docs/${saveName}`;
    }

    _currentDoc = {
      name: saveName,
      rst: rstContent,
      html: htmlContent,
      mtime: Math.floor(Date.now() / 1000),
      readonly: false,
    };

    if (_quill) {
      if (htmlContent) {
        _quill.clipboard.dangerouslyPasteHTML(0, htmlContent);
      } else {
        _quill.setText("");
      }
      renderAllMermaidBlocks(_quill.root);
      wirePlantumlBlocks(_quill.root);
      wireDocTableBlocks(_quill.root);
    }
    const rawTa = $("#docs-raw-rst");
    if (rawTa) rawTa.value = rstContent;

    const meta = $("#docs-file-meta");
    if (meta) {
      meta.textContent = `Imported: ${saveName} (${(file.size / 1024).toFixed(1)} KB) · Click '💾 Save RST' to write to disk.`;
    }

    setDocsDirty(true);
    if (badge) badge.textContent = "Imported (Unsaved)";
    toast("File Imported 📤", `${file.name} loaded into editor. Ready to edit and save.`, "ok", 4000);
    if (_docsSplit) updateDocsPreview();
  } catch (err) {
    if (badge) badge.textContent = "Import Failed";
    toast("Import Failed", String(err.message || err), "danger");
  }
}

