// Lockdown progressive enhancement
// Offline-capable, zero external dependencies.

document.addEventListener("DOMContentLoaded", () => {
  initCountdowns();
  initAutoSubmitFilters();
  initScoreKeyboardNav();
  initScoreCalculator();
  initDraftAutosave();
  initConfirmActions();
});

function initCountdowns() {
  const elements = document.querySelectorAll("[data-countdown]");
  if (!elements.length) return;

  function tick() {
    const now = Date.now();
    elements.forEach(el => {
      const targetStr = el.getAttribute("data-countdown");
      if (!targetStr) return;
      const target = new Date(targetStr).getTime();
      const diff = target - now;
      if (isNaN(diff)) return;

      if (diff <= 0) {
        el.textContent = el.getAttribute("data-countdown-done") || "Closed";
        return;
      }

      const days = Math.floor(diff / 86400000);
      const hours = Math.floor((diff % 86400000) / 3600000);
      const minutes = Math.floor((diff % 3600000) / 60000);
      const seconds = Math.floor((diff % 60000) / 1000);

      const parts = [];
      if (days > 0) parts.push(days + "d");
      parts.push(String(hours).padStart(2, "0") + "h");
      parts.push(String(minutes).padStart(2, "0") + "m");
      parts.push(String(seconds).padStart(2, "0") + "s");
      el.textContent = parts.join(" ");
    });
  }

  tick();
  setInterval(tick, 1000);
}

function initAutoSubmitFilters() {
  document.querySelectorAll("form[data-autosubmit] select").forEach(select => {
    select.addEventListener("change", () => {
      select.form.submit();
    });
  });
}

function initScoreKeyboardNav() {
  // Allow 1-5 number keys to set active rubric score when focused on a criteria block
  document.querySelectorAll(".rubric-criteria").forEach(block => {
    block.addEventListener("keydown", e => {
      if (e.target.tagName === "TEXTAREA" || e.target.tagName === "INPUT") return;
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= 5) {
        const radio = block.querySelector(`input[type="radio"][value="${num}"]`);
        if (radio) {
          radio.checked = true;
          radio.dispatchEvent(new Event("change", { bubbles: true }));
        }
      }
    });
  });
}

function initScoreCalculator() {
  const badge = document.querySelector("#live-score-val");
  if (!badge) return;

  const blocks = Array.from(document.querySelectorAll(".rubric-criteria"));
  if (!blocks.length) return;

  function update() {
    let totalWeightedPct = 0;
    let totalWeight = 0;
    let allSelected = true;

    blocks.forEach(b => {
      const weight = parseFloat(b.getAttribute("data-weight")) || 1.0;
      const min = parseFloat(b.getAttribute("data-min")) || 1.0;
      const max = parseFloat(b.getAttribute("data-max")) || 5.0;
      const checked = b.querySelector('input[type="radio"]:checked');
      if (checked) {
        const val = parseFloat(checked.value);
        const range = max - min;
        const pct = range > 0 ? ((val - min) / range) * 100.0 : 0.0;
        totalWeightedPct += pct * weight;
        totalWeight += weight;
      } else {
        allSelected = false;
      }
    });

    if (totalWeight > 0) {
      const avg = totalWeightedPct / totalWeight;
      badge.textContent = avg.toFixed(1) + "%";
    } else {
      badge.textContent = "—";
    }
  }

  document.querySelectorAll('.rubric-criteria input[type="radio"]').forEach(r => {
    r.addEventListener("change", update);
  });
  update();
}

function initDraftAutosave() {
  const form = document.querySelector("form[data-autosave]");
  if (!form) return;
  const statusEl = document.querySelector("#autosave-status");
  let timeout = null;

  function save() {
    if (statusEl) statusEl.textContent = "Saving draft...";
    const data = new FormData(form);
    data.set("action", "draft");
    fetch(form.action, {
      method: "POST",
      body: data,
      headers: { "X-Requested-With": "fetch" }
    })
      .then(r => {
        if (r.ok && statusEl) {
          const t = new Date().toLocaleTimeString();
          statusEl.textContent = "Draft saved at " + t;
        }
      })
      .catch(() => {
        if (statusEl) statusEl.textContent = "Offline — saved locally";
      });
  }

  form.querySelectorAll("input, textarea").forEach(el => {
    el.addEventListener("input", () => {
      if (timeout) clearTimeout(timeout);
      timeout = setTimeout(save, 1500);
    });
  });
}

function initConfirmActions() {
  document.querySelectorAll("[data-confirm]").forEach(el => {
    el.addEventListener("click", e => {
      const msg = el.getAttribute("data-confirm") || "Are you sure?";
      if (!window.confirm(msg)) {
        e.preventDefault();
        e.stopPropagation();
      }
    });
  });
}
