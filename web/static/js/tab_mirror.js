/* ==============================================================================
   Telua Web - Screen Mirroring & Android Remote Control Module (Vanilla JS)
   Zero-dependency screen capture and mouse-to-touch event injection.
   ============================================================================== */
"use strict";

let _mirrorRunning = false;
let _mirrorDeviceWidth = 1080;
let _mirrorDeviceHeight = 1920;
let _mirrorFps = 10;
let _mirrorTimer = null;
let _mirrorFetching = false;
let _mirrorOrientation = "auto";
let _mirrorLastFrameTime = 0;
let _mirrorFrameCount = 0;
let _mirrorActualFps = 0;
let _mirrorFpsInterval = null;

// Touch/drag tracking state
let _mirrorIsMouseDown = false;
let _mirrorStartX = 0;
let _mirrorStartY = 0;
let _mirrorStartTime = 0;
let _mirrorInitialized = false;
let _mirrorKeepInBackground = true;
try {
  const savedBg = localStorage.getItem("telua_mirror_keep_bg");
  if (savedBg !== null) _mirrorKeepInBackground = savedBg === "true";
} catch { /* ignore */ }

async function fetchMirrorInfo() {
  try {
    const res = await api("/api/mirror/info");
    if (res && res.ok) {
      if (res.width && res.height) {
        _mirrorDeviceWidth = res.width;
        _mirrorDeviceHeight = res.height;
      }
      renderMirrorMeta(res);
      return res;
    }
  } catch (err) {
    console.warn("[Mirror] Info fetch error:", err);
  }
  return null;
}

function renderMirrorMeta(info) {
  const metaEl = $("#mirror-status-meta");
  const devPill = $("#mirror-device-pill");
  const resPill = $("#mirror-res-pill");
  const offlineBanner = $("#mirror-offline-banner");
  const canvas = $("#mirror-canvas");

  const isConnected = Boolean(info && info.connected);

  if (metaEl) {
    metaEl.innerHTML = isConnected
      ? `<span style="color:var(--green,#3fb950);font-weight:600;">● Online</span> (${esc(info.device)})`
      : `<span style="color:var(--red,#f85149);font-weight:600;">● Offline / No device</span>`;
  }
  if (devPill) devPill.textContent = (info && info.device) ? info.device : "No device";
  if (resPill) {
    resPill.textContent = `${_mirrorDeviceWidth}×${_mirrorDeviceHeight} (${_mirrorDeviceWidth > _mirrorDeviceHeight ? "Landscape" : "Portrait"})`;
  }

  if (offlineBanner) {
    offlineBanner.classList.toggle("hidden", isConnected);
  }
  if (canvas) {
    canvas.classList.toggle("device-offline", !isConnected);
  }
}

function getCanvasCoordinates(e, canvas) {
  const rect = canvas.getBoundingClientRect();
  const scaleX = canvas.width / rect.width;
  const scaleY = canvas.height / rect.height;

  const clientX = e.clientX ?? (e.touches && e.touches[0]?.clientX) ?? 0;
  const clientY = e.clientY ?? (e.touches && e.touches[0]?.clientY) ?? 0;

  const canvasX = (clientX - rect.left) * scaleX;
  const canvasY = (clientY - rect.top) * scaleY;

  // Map to device physical coordinates
  const devX = Math.round((canvasX / canvas.width) * _mirrorDeviceWidth);
  const devY = Math.round((canvasY / canvas.height) * _mirrorDeviceHeight);

  return {
    canvasX,
    canvasY,
    devX: Math.max(0, Math.min(_mirrorDeviceWidth, devX)),
    devY: Math.max(0, Math.min(_mirrorDeviceHeight, devY)),
  };
}

function showTouchRipple(canvas, x, y) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.save();
  ctx.beginPath();
  ctx.arc(x, y, 16, 0, 2 * Math.PI);
  ctx.fillStyle = "rgba(139, 92, 246, 0.4)";
  ctx.fill();
  ctx.lineWidth = 2;
  ctx.strokeStyle = "#c4b5fd";
  ctx.stroke();
  ctx.restore();
}

async function captureMirrorFrame() {
  if (!_mirrorRunning || _mirrorFetching) return;
  _mirrorFetching = true;

  try {
    const res = await fetch("/api/mirror/frame", { cache: "no-store" });
    if (!res.ok) {
      if (res.status === 400 || res.status === 504) {
        // Device offline or temporary timeout
        renderMirrorMeta({ connected: false });
      }
      return;
    }
    const blob = await res.blob();
    const imgUrl = URL.createObjectURL(blob);
    const img = new Image();

    img.onload = () => {
      const canvas = $("#mirror-canvas");
      if (canvas) {
        const ctx = canvas.getContext("2d");
        if (ctx) {
          if (canvas.width !== img.naturalWidth || canvas.height !== img.naturalHeight) {
            canvas.width = img.naturalWidth;
            canvas.height = img.naturalHeight;
            _mirrorDeviceWidth = img.naturalWidth;
            _mirrorDeviceHeight = img.naturalHeight;
            const resPill = $("#mirror-res-pill");
            if (resPill) {
              resPill.textContent = `${canvas.width}×${canvas.height} (${canvas.width > canvas.height ? "Landscape" : "Portrait"})`;
            }
          }
          ctx.drawImage(img, 0, 0);
        }
      }
      URL.revokeObjectURL(imgUrl);
      _mirrorFrameCount++;
    };
    img.src = imgUrl;
  } catch (err) {
    console.debug("[Mirror] frame capture error:", err);
  } finally {
    _mirrorFetching = false;
  }
}

function startMirrorStream() {
  if (_mirrorRunning) return;
  _mirrorRunning = true;
  updateMirrorControls();
  if (typeof syncTopTabs === "function") syncTopTabs();

  const badge = $("#mirror-status-badge");
  if (badge) {
    badge.textContent = "Live";
    badge.className = "run-badge ok";
  }

  // Calculate interval in ms based on target FPS (e.g. 10 FPS -> 100ms)
  const intervalMs = Math.max(50, Math.round(1000 / _mirrorFps));
  _mirrorTimer = setInterval(captureMirrorFrame, intervalMs);

  // FPS monitor
  _mirrorFrameCount = 0;
  _mirrorFpsInterval = setInterval(() => {
    _mirrorActualFps = _mirrorFrameCount;
    _mirrorFrameCount = 0;
    const fpsBadge = $("#mirror-fps-badge");
    if (fpsBadge) {
      fpsBadge.textContent = `${_mirrorActualFps} FPS`;
    }
  }, 1000);

  // Capture first frame immediately
  captureMirrorFrame();
}

function stopMirrorStream() {
  _mirrorRunning = false;
  if (_mirrorTimer) {
    clearInterval(_mirrorTimer);
    _mirrorTimer = null;
  }
  if (_mirrorFpsInterval) {
    clearInterval(_mirrorFpsInterval);
    _mirrorFpsInterval = null;
  }
  updateMirrorControls();
  if (typeof syncTopTabs === "function") syncTopTabs();

  const badge = $("#mirror-status-badge");
  if (badge) {
    badge.textContent = "Paused";
    badge.className = "run-badge";
  }
  const fpsBadge = $("#mirror-fps-badge");
  if (fpsBadge) fpsBadge.textContent = "0 FPS";
}

function updateMirrorControls() {
  const toggleBtn = $("#btn-mirror-toggle");
  if (toggleBtn) {
    if (_mirrorRunning) {
      toggleBtn.textContent = "⏸ Pause";
      toggleBtn.className = "btn jade-btn";
    } else {
      toggleBtn.textContent = "▶ Start Live";
      toggleBtn.className = "btn primary";
    }
  }
}

async function sendMirrorKey(key) {
  try {
    await api("/api/mirror/key", {
      method: "POST",
      body: JSON.stringify({ key }),
    });
    // Trigger quick frame refresh to see visual change
    setTimeout(captureMirrorFrame, 150);
  } catch (err) {
    toast("Key error", err.message, "err");
  }
}

async function sendMirrorText() {
  const input = $("#mirror-text-input");
  const text = (input?.value || "").trim();
  if (!text) return;
  try {
    await api("/api/mirror/text", {
      method: "POST",
      body: JSON.stringify({ text }),
    });
    if (input) input.value = "";
    toast("Text Sent", `Injected "${text}" into device.`, "ok", 2000);
    setTimeout(captureMirrorFrame, 200);
  } catch (err) {
    toast("Text error", err.message, "err");
  }
}

async function downloadMirrorScreenshot() {
  try {
    const canvas = $("#mirror-canvas");
    if (canvas && canvas.width > 0 && canvas.height > 0) {
      const url = canvas.toDataURL("image/png");
      const a = document.createElement("a");
      a.href = url;
      a.download = `telua_screenshot_${Date.now()}.png`;
      a.click();
      toast("Screenshot Saved 📸", "Downloaded PNG image.", "ok", 3000);
    } else {
      window.open("/api/mirror/screenshot", "_blank");
    }
  } catch {
    window.open("/api/mirror/screenshot", "_blank");
  }
}

function initMirror() {
  const canvas = $("#mirror-canvas");
  if (!canvas) return;

  if (_mirrorInitialized) {
    if (!_mirrorRunning) {
      fetchMirrorInfo().then(() => {
        startMirrorStream();
      });
    }
    return;
  }
  _mirrorInitialized = true;

  // Canvas Mouse / Touch handlers for Tap & Swipe
  canvas.addEventListener("mousedown", (e) => {
    if (e.button !== 0) return; // Only left click
    _mirrorIsMouseDown = true;
    _mirrorStartTime = Date.now();
    const coords = getCanvasCoordinates(e, canvas);
    _mirrorStartX = coords.devX;
    _mirrorStartY = coords.devY;
    showTouchRipple(canvas, coords.canvasX, coords.canvasY);
  });

  canvas.addEventListener("mouseup", async (e) => {
    if (!_mirrorIsMouseDown) return;
    _mirrorIsMouseDown = false;
    const duration = Date.now() - _mirrorStartTime;
    const coords = getCanvasCoordinates(e, canvas);
    const endX = coords.devX;
    const endY = coords.devY;

    const dist = Math.hypot(endX - _mirrorStartX, endY - _mirrorStartY);

    if (dist < 15 && duration < 400) {
      // Tap event
      try {
        await api("/api/mirror/touch", {
          method: "POST",
          body: JSON.stringify({ x: endX, y: endY }),
        });
        setTimeout(captureMirrorFrame, 150);
      } catch (err) {
        console.warn("[Mirror] Tap error:", err);
      }
    } else {
      // Swipe event
      try {
        await api("/api/mirror/swipe", {
          method: "POST",
          body: JSON.stringify({
            x1: _mirrorStartX,
            y1: _mirrorStartY,
            x2: endX,
            y2: endY,
            duration: Math.max(100, Math.min(1000, duration)),
          }),
        });
        setTimeout(captureMirrorFrame, 250);
      } catch (err) {
        console.warn("[Mirror] Swipe error:", err);
      }
    }
  });

  // Action Buttons
  $("#btn-mirror-toggle")?.addEventListener("click", () => {
    if (_mirrorRunning) stopMirrorStream();
    else startMirrorStream();
  });

  $("#btn-mirror-screenshot")?.addEventListener("click", downloadMirrorScreenshot);

  $("#mirror-fps-select")?.addEventListener("change", (e) => {
    _mirrorFps = parseInt(e.target.value, 10) || 10;
    if (_mirrorRunning) {
      stopMirrorStream();
      startMirrorStream();
    }
  });

  const chkBg = $("#mirror-chk-background");
  if (chkBg) {
    chkBg.checked = _mirrorKeepInBackground;
    chkBg.addEventListener("change", (e) => {
      _mirrorKeepInBackground = Boolean(e.target.checked);
      try {
        localStorage.setItem("telua_mirror_keep_bg", String(_mirrorKeepInBackground));
      } catch { /* ignore */ }
    });
  }

  // Virtual Key Buttons
  $("#btn-mirror-key-back")?.addEventListener("click", () => sendMirrorKey(4));
  $("#btn-mirror-key-home")?.addEventListener("click", () => sendMirrorKey(3));
  $("#btn-mirror-key-appswitch")?.addEventListener("click", () => sendMirrorKey(187));
  $("#btn-mirror-key-power")?.addEventListener("click", () => sendMirrorKey(26));
  $("#btn-mirror-key-volup")?.addEventListener("click", () => sendMirrorKey(24));
  $("#btn-mirror-key-voldown")?.addEventListener("click", () => sendMirrorKey(25));
  $("#btn-mirror-key-notif")?.addEventListener("click", () => sendMirrorKey("KEYCODE_NOTIFICATION"));
  $("#btn-mirror-key-settings")?.addEventListener("click", async () => {
    try {
      await api("/api/terminal/run", {
        method: "POST",
        body: JSON.stringify({ cmd: "adb shell am start -a android.settings.SETTINGS" }),
      });
      setTimeout(captureMirrorFrame, 400);
    } catch { /* ignore */ }
  });

  // Text Injection
  $("#btn-mirror-send-text")?.addEventListener("click", sendMirrorText);
  $("#mirror-text-input")?.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      sendMirrorText();
    }
  });

  // Fetch initial info and start
  fetchMirrorInfo().then(() => {
    startMirrorStream();
  });
}
