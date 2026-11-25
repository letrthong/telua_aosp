/* ==============================================================================
   Telua Web - AOSP Command Center & Environment Module
   ============================================================================== */
/* ==============================================================================
   AOSP Command Center & Environment Module
   ============================================================================== */
let _aospRunning = false;
let _aospAbortController = null;
let _aospLoadedData = null;

async function loadAospConfig() {
  try {
    const res = await fetch("/api/aosp/config");
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    if (!data.ok) return;

    _aospLoadedData = data;

    // Compact bar: AOSP Root Path & Status
    const barRoot = $("#aosp-bar-root");
    const pathStatus = $("#aosp-path-status");
    if (barRoot) {
      if (data.aosp_root_dir) {
        barRoot.textContent = data.aosp_root_dir;
        barRoot.title = `AOSP Root Directory: ${data.aosp_root_dir}`;
        if (pathStatus) {
          pathStatus.innerHTML = data.aosp_exists
            ? '<span style="color:#3fb950;font-weight:700;" title="Directory exists on disk">✔</span>'
            : '<span style="color:#f85149;font-weight:700;" title="Directory not found on disk">⚠️</span>';
        }
      } else {
        barRoot.textContent = "Auto-detect (ancestor search)";
        barRoot.title = "Searching parent directories for 'android/'";
        if (pathStatus) pathStatus.innerHTML = "";
      }
    }

    // Compact bar: Active Project Select
    const projSel = $("#aosp-project-select");
    if (projSel) {
      projSel.innerHTML = "";
      (data.profiles || []).forEach(p => {
        const opt = document.createElement("option");
        opt.value = p;
        opt.textContent = p;
        if (p === data.active_project) opt.selected = true;
        projSel.appendChild(opt);
      });
    }

    // Compact bar: Lunch Target (Product & Variant combined)
    const barTarget = $("#aosp-bar-target");
    if (barTarget) {
      const targetStr = (data.target_product && data.target_variant)
        ? `${data.target_product}-${data.target_variant}`
        : "lunch: —";
      barTarget.textContent = targetStr;
    }

    // Compact bar: Meta pills
    if ($("#aosp-meta-module")) $("#aosp-meta-module").textContent = data.module_name || "—";
    if ($("#aosp-meta-apk")) $("#aosp-meta-apk").textContent = data.apk_name || "—";
    if ($("#aosp-meta-source")) {
      const srcEl = $("#aosp-meta-source");
      srcEl.textContent = data.source_path || "—";
      srcEl.title = data.source_dir
        ? `Source dir: ${data.source_dir}${data.apk_config_in_source ? " (apk.config ✔)" : " (apk.config missing — auto-created on project switch)"}`
        : "";
    }
    if ($("#aosp-meta-deploy")) $("#aosp-meta-deploy").textContent = data.deploy_path || "—";
  } catch (err) {
    console.error("Failed to load AOSP config:", err);
  }
}

function openAospConfigModal() {
  const d = _aospLoadedData || {};
  if ($("#aosp-modal-root-input")) $("#aosp-modal-root-input").value = d.aosp_root_dir || "";
  if ($("#aosp-modal-cfg-file")) $("#aosp-modal-cfg-file").textContent = d.config_file || "config/apk.config";

  const modalPathStatus = $("#aosp-modal-path-status");
  if (modalPathStatus) {
    if (d.aosp_root_dir) {
      modalPathStatus.innerHTML = d.aosp_exists
        ? '<span style="color:#3fb950;font-weight:600;">✔ Directory exists on disk</span>'
        : '<span style="color:#f85149;font-weight:600;">⚠️ Directory not found on disk</span>';
    } else {
      modalPathStatus.innerHTML = '<span style="color:var(--text-dim);font-style:italic;">Auto-detect from ancestors</span>';
    }
  }

  const modalProjSel = $("#aosp-modal-project-select");
  if (modalProjSel) {
    modalProjSel.innerHTML = "";
    (d.profiles || []).forEach(p => {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      if (p === d.active_project) opt.selected = true;
      modalProjSel.appendChild(opt);
    });
  }

  if ($("#aosp-modal-target-product")) $("#aosp-modal-target-product").value = d.target_product || "";
  const variantSel = $("#aosp-modal-target-variant");
  if (variantSel) {
    const val = d.target_variant || "userdebug";
    if (![...variantSel.options].some(o => o.value === val)) {
      const opt = document.createElement("option");
      opt.value = val;
      opt.textContent = val;
      variantSel.appendChild(opt);
    }
    variantSel.value = val;
  }

  $("#modal-aosp-config")?.classList.remove("hidden");
  setTimeout(() => $("#aosp-modal-root-input")?.focus(), 50);
}

function closeAospConfigModal() {
  $("#modal-aosp-config")?.classList.add("hidden");
}

async function saveAospConfigFromModal() {
  const saveBtn = $("#btn-aosp-modal-save");
  if (saveBtn) {
    saveBtn.disabled = true;
    saveBtn.textContent = "Saving…";
  }
  try {
    const payload = {
      aosp_root_dir: $("#aosp-modal-root-input")?.value || "",
      active_project: $("#aosp-modal-project-select")?.value || "",
      target_product: $("#aosp-modal-target-product")?.value || "",
      target_variant: $("#aosp-modal-target-variant")?.value || "",
    };
    const res = await fetch("/api/aosp/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    closeAospConfigModal();
    await loadAospConfig();
    refreshStatus();
    toast("AOSP Configuration Saved", "Updated apk.config successfully.", "ok", 3000);
  } catch (err) {
    toast("Save Failed", String(err.message || err), "danger");
  } finally {
    if (saveBtn) {
      saveBtn.disabled = false;
      saveBtn.textContent = "💾 Save Configuration";
    }
  }
}

async function uploadOverlayFile(file, targetName) {
  if (!file) return;
  const formData = new FormData();
  formData.append("file", file);
  if (targetName) formData.append("target", targetName);

  try {
    const res = await fetch("/api/overlay/upload", {
      method: "POST",
      body: formData,
    });
    const data = await res.json();
    if (!res.ok || !data.ok) {
      throw new Error(data.error || data.description || "Upload failed");
    }
    toast("Overlay Uploaded 💾", `Saved ${data.filename} to config/overlay/!`, "ok", 4000);
    if (data.filename === "apk_overlays.config") {
      await loadAospConfig();
      openAospConfigModal();
      refreshStatus();
    } else if (data.filename === "const_my_cli.config") {
      if (state.plSource === "my") {
        await loadPipelines("my");
      }
    }
  } catch (err) {
    toast("Upload Failed ❌", String(err.message || err), "danger", 5000);
  }
}

async function quickSwitchAospProject(projectName) {
  if (!projectName) return;
  try {
    const res = await fetch("/api/aosp/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ active_project: projectName }),
    });
    if (!res.ok) throw new Error("HTTP " + res.status);
    await loadAospConfig();
    refreshStatus();
    toast("Project Switched", `ACTIVE_PROJECT="${projectName}"`, "ok", 2500);
  } catch (err) {
    toast("Switch Failed", String(err.message || err), "danger");
  }
}

/**
 * Upload a locally-built APK to the connected device via the Web backend.
 * Flow: validate filename vs OUTPUT_FILE_NAME -> POST /api/aosp/upload-apk
 *       (backend adb push to DEPLOY_PATH + chmod + rm oat cache) -> framework restart.
 * restartMode: "framework" (stop && start, fast) or "reboot" (full device reboot).
 */
async function uploadAospApk(file, restartMode = "framework") {
  if (_aospRunning) {
    toast("AOSP busy", "Please wait for current command to complete or click ⏹ Stop.", "warn");
    return;
  }
  const outEl = $("#aosp-output");
  const badge = $("#aosp-status-badge");
  const stopBtn = $("#btn-aosp-stop");
  const uploadBtn = $("#btn-aosp-upload-apk");
  const actionBtns = document.querySelectorAll(".aosp-action-btn");

  const appendOut = (html) => {
    if (!outEl) return;
    outEl.innerHTML += html + "\n";
    outEl.scrollTop = outEl.scrollHeight;
  };

  // Client-side pre-check against the loaded AOSP meta (OUTPUT_FILE_NAME)
  const expected = (_aospLoadedData && _aospLoadedData.apk_name) || "";
  if (expected && file.name.toLowerCase() !== expected.toLowerCase()) {
    appendOut(`<span style="color:#f85149;font-weight:700">✕ Filename mismatch:</span> uploaded <b>${esc(file.name)}</b> but active project expects <b>${esc(expected)}</b> (OUTPUT_FILE_NAME).`);
    toast("Filename mismatch", `Expected "${expected}", got "${file.name}".`, "danger", 5000);
    return;
  }

  _aospRunning = true;
  actionBtns.forEach(b => b.disabled = true);
  if (uploadBtn) uploadBtn.classList.add("running-active");
  if (stopBtn) { stopBtn.disabled = false; stopBtn.classList.add("danger-solid"); }
  if (badge) { badge.textContent = "📤 Uploading…"; badge.className = "run-badge running"; }

  appendOut(`<span style="color:#3fb950;font-weight:700">tel:aosp $</span> <span style="color:#c4b5fd;font-weight:700">📤 upload-apk ${esc(file.name)} (${(file.size / 1048576).toFixed(1)} MB) → deploy + ${restartMode === "reboot" ? "reboot" : "restart framework"}</span>`);

  const startedAt = Date.now();
  try {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("restart", restartMode);
    const res = await fetch("/api/aosp/upload-apk", { method: "POST", body: fd });
    const data = await res.json().catch(() => ({}));
    const secs = ((Date.now() - startedAt) / 1000).toFixed(1);

    if (res.ok && data.ok) {
      const sizeMb = data.bytes ? (data.bytes / 1048576).toFixed(2) : null;
      const devMb = data.device_bytes ? (data.device_bytes / 1048576).toFixed(2) : null;
      const ig = data.integrity || {};
      let sizeStr = sizeMb ? ` · 📦 ${sizeMb} MB` : "";
      if (devMb && sizeMb && devMb !== sizeMb) {
        sizeStr += ` <span style="color:#f0883e">(⚠️ on-device: ${devMb} MB)</span>`;
      } else if (devMb) {
        sizeStr += ` <span style="opacity:.75">(on-device ✔ ${devMb} MB)</span>`;
      }
      // Integrity: SHA-256 local vs on-device
      let integrityStr = "";
      if (ig.hash_match === true) {
        const short = (data.sha256 || "").slice(0, 12);
        integrityStr = ` · 🔒 SHA-256 <span style="opacity:.75;font-family:monospace">${esc(short)}…</span> <span style="color:#3fb950">verified ✔</span>`;
      } else if (ig.hash_match === false) {
        integrityStr = ` · 🔒 <span style="color:#f85149">SHA-256 MISMATCH</span>`;
      }
      appendOut(`<pre style="margin:4px 0;white-space:pre-wrap;color:#9aa4b2">${esc(data.output || "")}</pre>`);
      appendOut(`<span style="color:#3fb950;font-weight:700">✔ Deployed in ${secs}s:</span> ${esc(data.filename)}${sizeStr}${integrityStr} → <b>${esc(data.deploy_path)}/</b> · ${esc(data.restart)}`);
      if (badge) { badge.textContent = `✔ Deployed ${sizeMb ? sizeMb + "MB · " : ""}(${secs}s)`; badge.className = "run-badge done"; }
      toast("APK Deployed ✓", `${data.filename}${sizeMb ? " (" + sizeMb + " MB" + (devMb && devMb !== sizeMb ? " → device " + devMb + " MB" : "") + ")" : ""} · SHA-256 verified & ${data.restart}.`, "ok", 4500);
    } else {
      const msg = data.error || data.description || `HTTP ${res.status}`;
      appendOut(`<span style="color:#f85149;font-weight:700">✕ Upload failed:</span> ${esc(msg)}`);
      if (badge) { badge.textContent = "✕ Failed"; badge.className = "run-badge error"; }
      toast("Upload failed", msg, "danger", 6000);
    }
  } catch (err) {
    appendOut(`<span style="color:#f85149;font-weight:700">✕ Upload error:</span> ${esc(String(err.message || err))}`);
    if (badge) { badge.textContent = "✕ Failed"; badge.className = "run-badge error"; }
    toast("Upload error", String(err.message || err), "danger");
  } finally {
    _aospRunning = false;
    actionBtns.forEach(b => b.disabled = false);
    if (uploadBtn) uploadBtn.classList.remove("running-active");
    if (stopBtn) { stopBtn.disabled = true; stopBtn.classList.remove("danger-solid"); }
  }
}

async function runAospCommand(cmd, sourceBtn) {
  cmd = (cmd || "").trim();
  if (!cmd) return;
  if (_aospRunning) {
    toast("AOSP busy", "Please wait for current command to complete or click ⏹ Stop.", "warn");
    return;
  }

  const outEl = $("#aosp-output");
  const badge = $("#aosp-status-badge");
  const stopBtn = $("#btn-aosp-stop");
  const actionBtns = document.querySelectorAll(".aosp-action-btn");

  _aospRunning = true;
  _aospAbortController = new AbortController();
  const signal = _aospAbortController.signal;

  actionBtns.forEach(b => b.disabled = true);
  if (stopBtn) {
    stopBtn.disabled = false;
    stopBtn.classList.add("danger-solid");
  }

  // Highlight the clicked button/chip (amber pulsing glow) so the user can
  // always see WHICH command is currently running.
  let activeBtn = sourceBtn instanceof Element ? sourceBtn : null;
  if (!activeBtn) {
    const sel = `.aosp-action-btn[data-cmd="${CSS.escape(cmd)}"], .aosp-chip[data-cmd="${CSS.escape(cmd)}"]`;
    activeBtn = document.querySelector(sel);
  }
  if (activeBtn) activeBtn.classList.add("running-active");

  const separator = outEl && outEl.innerHTML.trim() ? "\n" : "";
  const runDir = (_aospLoadedData && _aospLoadedData.source_dir_exists && _aospLoadedData.source_dir)
    ? _aospLoadedData.source_dir : "";
  const dirHint = runDir ? `<span style="opacity:.65"> (cd ${esc(runDir)})</span>` : "";
  const headerHtml = `${separator}<span style="color:#3fb950;font-weight:700">tel:aosp $</span> <span style="color:#58a6ff;font-weight:700">${esc(cmd)}</span>${dirHint}\n`;
  if (outEl) {
    outEl.innerHTML += headerHtml + `<span style="opacity:.7">⏳ Running… (click ⏹ Stop to abort)</span>\n`;
    outEl.scrollTop = outEl.scrollHeight;
  }

  let elapsed = 0;
  if (badge) {
    badge.textContent = `⏳ Running… (0s)`;
    badge.className = "run-badge running";
  }
  const timerId = setInterval(() => {
    elapsed++;
    if (badge && _aospRunning) badge.textContent = `⏳ Running… (${elapsed}s)`;
  }, 1000);

  let streamedPreview = "";
  try {
    // Run from the project source directory (<AOSP_TOP>/<SOURCE_CODE_RELATIVE_PATH>)
    // so build_apk.sh discovers the project's own apk.config (profiles,
    // TEST_BUILD_SCRIPT, ...). Falls back to the AOSP root, then the toolkit root.
    const d = _aospLoadedData || {};
    const aospCwd = (d.source_dir_exists && d.source_dir) ? d.source_dir
      : (d.aosp_exists && d.aosp_root_dir) ? d.aosp_root_dir : "";
    const res = await fetch("/api/terminal/stream", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ command: cmd, cwd: aospCwd }),
      signal,
    });

    if (res.ok && res.body) {
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let rawBuffer = "";
      let exitCode = 0;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        const chunk = decoder.decode(value, { stream: true });
        rawBuffer += chunk;

        const lines = rawBuffer.split("\n");
        rawBuffer = lines.pop() || "";
        for (const line of lines) {
          const mExit = line.match(/^__TELUA_EXIT_CODE__:(\d+)/);
          if (mExit) {
            exitCode = parseInt(mExit[1], 10);
            continue;
          }
          if (line.startsWith("__TELUA_PWD__:")) continue;
          streamedPreview += line + "\n";
          if (streamedPreview.length > 150000) {
            streamedPreview = streamedPreview.slice(-120000);
          }
        }
        if (outEl) {
          outEl.innerHTML = headerHtml + ansiToHtml(streamedPreview);
          outEl.scrollTop = outEl.scrollHeight;
        }
      }

      if (rawBuffer) {
        const mExit = rawBuffer.match(/^__TELUA_EXIT_CODE__:(\d+)/);
        if (mExit) {
          exitCode = parseInt(mExit[1], 10);
        } else if (!rawBuffer.startsWith("__TELUA_PWD__:")) {
          streamedPreview += rawBuffer;
          if (outEl) {
            outEl.innerHTML = headerHtml + ansiToHtml(streamedPreview);
            outEl.scrollTop = outEl.scrollHeight;
          }
        }
      }

      clearInterval(timerId);
      if (badge) {
        if (exitCode === 0) {
          badge.textContent = `✔ Finished (${elapsed}s)`;
          badge.className = "run-badge ok";
          toast("AOSP Command Succeeded", `'${cmd}' completed successfully.`, "ok", 3000);
        } else {
          badge.textContent = `❌ Exit ${exitCode} (${elapsed}s)`;
          badge.className = "run-badge error";
          toast("AOSP Command Failed", `'${cmd}' exited with code ${exitCode}.`, "danger", 4000);
        }
      }
    } else {
      throw new Error("HTTP " + res.status);
    }
  } catch (err) {
    clearInterval(timerId);
    if (signal.aborted) {
      if (badge) {
        badge.textContent = `⏹ Stopped (${elapsed}s)`;
        badge.className = "run-badge warn";
      }
      if (outEl) {
        outEl.innerHTML += `<span style="color:#d29922">\n[INTERRUPTED] Command aborted by user.\n</span>`;
      }
    } else {
      if (badge) {
        badge.textContent = `❌ Error (${elapsed}s)`;
        badge.className = "run-badge error";
      }
      if (outEl) {
        outEl.innerHTML += `<span style="color:#f85149">\n[ERROR] ${esc(String(err.message || err))}\n</span>`;
      }
    }
  } finally {
    clearInterval(timerId);
    _aospRunning = false;
    _aospAbortController = null;
    actionBtns.forEach(b => b.disabled = false);
    if (stopBtn) {
      stopBtn.disabled = true;
      stopBtn.classList.remove("danger-solid");
    }
    if (activeBtn) activeBtn.classList.remove("running-active");
    if (outEl) outEl.scrollTop = outEl.scrollHeight;
  }
}

async function stopAospCommand() {
  if (!_aospRunning) return;
  if (_aospAbortController) {
    try { _aospAbortController.abort(); } catch { /* ignore */ }
  }
  try {
    await fetch("/api/terminal/stop", { method: "POST" });
  } catch { /* ignore */ }
}

