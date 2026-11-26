/* ==============================================================================
   Telua Web - Target Power Controls Module (Dual Outputs: Out 1 & Out 2)
   Manages independent hardware switch channels (Main Power & ACC/Ignition).
   ============================================================================== */
"use strict";

let _powerTabInitialized = false;

async function fetchPowerTabStatus() {
  try {
    const res = await api("/api/power/status");
    if (res && res.ok) {
      renderPowerTabUI(res);
      // Also sync compact mirror power controls if visible
      if (typeof renderPowerUI === "function") {
        renderPowerUI(res.state, res);
      }
      return res;
    }
  } catch (err) {
    console.debug("[PowerTab] fetch status error:", err);
  }
  return null;
}

function renderPowerTabUI(data) {
  if (!data || !data.outputs) return;

  const out1 = data.outputs.out1 || {};
  const out2 = data.outputs.out2 || {};
  const isOverallOn = Boolean(data.is_on);

  // Overall Header Badge & Metadata
  const overallBadge = $("#power-overall-badge");
  if (overallBadge) {
    overallBadge.textContent = isOverallOn ? "POWER: ON" : "POWER: OFF";
    overallBadge.className = isOverallOn ? "run-badge ok" : "run-badge err";
  }

  const targetMeta = $("#power-target-meta");
  if (targetMeta && data.target_name) {
    targetMeta.textContent = `${data.target_name} (${data.voltage}V · ${data.current_a}A)`;
  }

  const lastChangedEl = $("#power-last-changed");
  if (lastChangedEl && data.last_changed) {
    try {
      lastChangedEl.textContent = `Cập nhật: ${new Date(data.last_changed).toLocaleTimeString()}`;
    } catch {
      lastChangedEl.textContent = `Cập nhật: ${data.last_changed}`;
    }
  }

  // Render Output 1 (Main Power BATT+)
  const isOut1On = out1.state === "ON";
  const card1 = $("#card-power-out1");
  const led1 = $("#led-out1");
  const btn1On = $("#btn-out1-on");
  const btn1Off = $("#btn-out1-off");
  const valV1 = $("#val-v-out1");
  const valA1 = $("#val-a-out1");
  const stText1 = $("#status-text-out1");

  if (card1) card1.classList.toggle("channel-active", isOut1On);
  if (led1) led1.className = isOut1On ? "power-led on" : "power-led off";
  if (btn1On) {
    btn1On.classList.toggle("active-sw", isOut1On);
    btn1On.disabled = isOut1On;
  }
  if (btn1Off) {
    btn1Off.classList.toggle("active-sw", !isOut1On);
    btn1Off.disabled = !isOut1On;
  }
  if (valV1) valV1.textContent = `${out1.voltage || (isOut1On ? 12.0 : 0.0)} V`;
  if (valA1) valA1.textContent = `${out1.current_a || (isOut1On ? 1.25 : 0.0)} A`;
  if (stText1) {
    stText1.textContent = isOut1On ? "BẬT (ACTIVE 🟢)" : "TẮT (INACTIVE ⚪)";
    stText1.className = isOut1On ? "text-green" : "text-muted";
  }

  // Render Output 2 (ACC / Ignition)
  const isOut2On = out2.state === "ON";
  const card2 = $("#card-power-out2");
  const led2 = $("#led-out2");
  const btn2On = $("#btn-out2-on");
  const btn2Off = $("#btn-out2-off");
  const valV2 = $("#val-v-out2");
  const valA2 = $("#val-a-out2");
  const stText2 = $("#status-text-out2");

  if (card2) card2.classList.toggle("channel-active", isOut2On);
  if (led2) led2.className = isOut2On ? "power-led on" : "power-led off";
  if (btn2On) {
    btn2On.classList.toggle("active-sw", isOut2On);
    btn2On.disabled = isOut2On;
  }
  if (btn2Off) {
    btn2Off.classList.toggle("active-sw", !isOut2On);
    btn2Off.disabled = !isOut2On;
  }
  if (valV2) valV2.textContent = `${out2.voltage || (isOut2On ? 12.0 : 0.0)} V`;
  if (valA2) valA2.textContent = `${out2.current_a || (isOut2On ? 0.08 : 0.0)} A`;
  if (stText2) {
    stText2.textContent = isOut2On ? "BẬT (ACTIVE 🟢)" : "TẮT (INACTIVE ⚪)";
    stText2.className = isOut2On ? "text-green" : "text-muted";
  }

  // Render History Table
  const tbody = $("#tbody-power-history");
  if (tbody && Array.isArray(data.history)) {
    if (data.history.length === 0) {
      tbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:var(--text-muted);">Chưa có sự kiện nào</td></tr>`;
    } else {
      const reversed = [...data.history].reverse();
      tbody.innerHTML = reversed.map(h => {
        const timeStr = h.timestamp ? new Date(h.timestamp).toLocaleTimeString() : "—";
        const isToOn = h.to === "ON";
        const badgeClass = isToOn ? "ok" : "err";
        const outLabel = h.output === "out1" ? "Ngõ ra 1 (BATT+)" : (h.output === "out2" ? "Ngõ ra 2 (ACC/IGN)" : "Tất Cả (ALL)");
        return `
          <tr>
            <td class="mono">${esc(timeStr)}</td>
            <td><b>${esc(outLabel)}</b></td>
            <td><span class="run-badge ${badgeClass}" style="font-size:10px;">${esc(h.to || "—")}</span></td>
            <td class="mono" style="color:var(--text-muted);">${esc(h.client_ip || "127.0.0.1")}</td>
            <td>${esc(h.reason || "Manual action")}</td>
          </tr>
        `;
      }).join("");
    }
  }
}

async function setPowerOutput(outId, state) {
  try {
    const res = await api(`/api/power/output/${outId}`, {
      method: "POST",
      body: JSON.stringify({ state }),
    });
    if (res && res.ok) {
      toast("Target Power", `${outId === "out1" ? "Ngõ ra 1 (BATT+)" : "Ngõ ra 2 (ACC/IGN)"} đã chuyển sang ${state}.`, state === "ON" ? "ok" : "warn", 3000);
      fetchPowerTabStatus();
    }
  } catch (err) {
    toast("Power Error", err.message, "err");
  }
}

async function setMasterPower(state) {
  try {
    const res = await api("/api/power/set", {
      method: "POST",
      body: JSON.stringify({ state, reason: "master_power_button" }),
    });
    if (res && res.ok) {
      toast("Master Power", `Đã bật/tắt toàn bộ ngõ ra sang ${state}.`, state === "ON" ? "ok" : "warn", 3500);
      fetchPowerTabStatus();
    }
  } catch (err) {
    toast("Master Error", err.message, "err");
  }
}

async function cyclePower() {
  const ok = await confirmDialog({
    title: "Xác nhận Power Cycle",
    message: "Bạn có chắc muốn thực hiện chu trình ngắt nguồn trong 3s rồi tự động bật lại không?",
    confirmText: "↻ Power Cycle (3s)",
    icon: "↻",
  });
  if (!ok) return;

  try {
    toast("Power Cycle", "Đang ngắt nguồn toàn bộ ngõ ra...", "warn", 2500);
    await api("/api/power/set", { method: "POST", body: JSON.stringify({ state: "OFF", reason: "power_cycle" }) });
    fetchPowerTabStatus();

    setTimeout(async () => {
      toast("Power Cycle", "Đang cấp lại nguồn cho board...", "ok", 3000);
      await api("/api/power/set", { method: "POST", body: JSON.stringify({ state: "ON", reason: "power_cycle_resume" }) });
      fetchPowerTabStatus();
    }, 3000);
  } catch (err) {
    toast("Cycle Error", err.message, "err");
  }
}

function initPowerTab() {
  fetchPowerTabStatus();
  if (_powerTabInitialized) return;
  _powerTabInitialized = true;

  // Switch 1 Buttons
  $("#btn-out1-on")?.addEventListener("click", () => setPowerOutput("out1", "ON"));
  $("#btn-out1-off")?.addEventListener("click", () => setPowerOutput("out1", "OFF"));

  // Switch 2 Buttons
  $("#btn-out2-on")?.addEventListener("click", () => setPowerOutput("out2", "ON"));
  $("#btn-out2-off")?.addEventListener("click", () => setPowerOutput("out2", "OFF"));

  // Master Actions
  $("#btn-master-power-on")?.addEventListener("click", () => setMasterPower("ON"));
  $("#btn-master-power-off")?.addEventListener("click", () => setMasterPower("OFF"));
  $("#btn-power-refresh")?.addEventListener("click", () => fetchPowerTabStatus());

  // Sub Deck Actions
  $("#btn-tab-power-cycle")?.addEventListener("click", () => cyclePower());
  $("#btn-tab-power-soft-reboot")?.addEventListener("click", async () => {
    toast("Soft Reboot...", "Khởi động lại Zygote Runtime trong 5s...", "info", 3000);
    try {
      await api("/api/terminal/run", {
        method: "POST",
        body: JSON.stringify({ cmd: "adb shell setprop ctl.restart zygote" }),
      });
    } catch { /* ignore */ }
  });
  $("#btn-tab-power-full-reboot")?.addEventListener("click", async () => {
    const ok = await confirmDialog({
      title: "Xác nhận Reboot Toàn Bộ Board",
      message: "Bạn có chắc muốn gửi lệnh adb reboot để khởi động lại phần cứng board mạch?",
      confirmText: "🔄 Full Board Reboot",
      icon: "🔄",
    });
    if (!ok) return;
    toast("Rebooting Target...", "Đang gửi lệnh adb reboot...", "warn", 4000);
    try {
      await api("/api/terminal/run", {
        method: "POST",
        body: JSON.stringify({ cmd: "adb reboot" }),
      });
    } catch { /* ignore */ }
  });
  $("#btn-tab-power-stayon")?.addEventListener("click", async () => {
    toast("Màn hình luôn sáng", "Đang gửi lệnh svc power stayon true...", "ok", 2500);
    try {
      await api("/api/terminal/run", {
        method: "POST",
        body: JSON.stringify({ cmd: "adb shell svc power stayon true" }),
      });
    } catch { /* ignore */ }
  });
  $("#btn-tab-power-bootloader")?.addEventListener("click", async () => {
    const ok = await confirmDialog({
      title: "Vào Chế Độ Fastboot",
      message: "Board sẽ khởi động vào Bootloader / Fastboot để nạp flash phân vùng. Bạn có chắc không?",
      confirmText: "🔌 Reboot Bootloader",
      icon: "🔌",
    });
    if (!ok) return;
    try {
      await api("/api/terminal/run", {
        method: "POST",
        body: JSON.stringify({ cmd: "adb reboot bootloader" }),
      });
    } catch { /* ignore */ }
  });
}
