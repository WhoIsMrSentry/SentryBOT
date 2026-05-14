const $ = (sel) => document.querySelector(sel);

function pretty(obj) {
  try {
    return JSON.stringify(obj, null, 2);
  } catch {
    return String(obj);
  }
}

async function fetchJson(url) {
  const res = await fetch(url, { headers: { Accept: "application/json" } });
  if (!res.ok) throw new Error(`${res.status} ${res.url}`);
  return res.json();
}

function activateTab(id) {
  document.querySelectorAll(".tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === id);
  });
  document.querySelectorAll(".pane").forEach((p) => {
    p.classList.toggle("active", p.id === `pane-${id}`);
  });
}

let sseAbort = null;

function stopSse() {
  if (sseAbort) sseAbort.abort();
  sseAbort = null;
  $("#sse-state").textContent = "SSE idle";
}

function startSse() {
  stopSse();
  sseAbort = new AbortController();
  $("#sse-state").textContent = "SSE connecting…";
  fetch("/admin/api/stream", {
    headers: { Accept: "text/event-stream" },
    signal: sseAbort.signal,
  })
    .then(async (resp) => {
      if (!resp.ok) throw new Error("stream " + resp.status);
      $("#sse-state").textContent = "SSE connected";
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = "";
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const parts = buf.split("\n\n");
        buf = parts.pop() || "";
        for (const chunk of parts) {
          chunk.split("\n").forEach((line) => {
            if (!line.startsWith("data:")) return;
            const raw = line.replace(/^data:\s*/, "").trim();
            try {
              const payload = JSON.parse(raw);
              $("#status-pre").textContent = pretty(payload);
            } catch {}
          });
        }
      }
    })
    .catch(() => {
      $("#sse-state").textContent = "SSE error / stopped";
    });
}

async function refreshAll() {
  try {
    const [status, vision, people, profiles, hw] = await Promise.all([
      fetchJson("/admin/api/status"),
      fetchJson("/admin/api/vision"),
      fetchJson("/admin/api/people"),
      fetchJson("/admin/api/profiles"),
      fetchJson("/admin/api/hardware"),
    ]);
    $("#status-pre").textContent = pretty(status);
    $("#vision-pre").textContent = pretty(vision);
    $("#people-pre").textContent = pretty(people);
    $("#hardware-pre").textContent = pretty(hw);

    $("#slider-subagents").value = profiles.max_subagents || 3;
    $("#slider-subagents-label").textContent = $("#slider-subagents").value;

    const pb = $("#profile-buttons");
    pb.innerHTML = "";
    (profiles.profiles || []).forEach((name) => {
      const btn = document.createElement("button");
      btn.textContent = name;
      btn.addEventListener("click", async () => {
        $("#profile-result").textContent = "Switching…";
        try {
          const resp = await fetch("/admin/api/profile/switch", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ name }),
          });
          const data = await resp.json();
          $("#profile-result").textContent = pretty(data);
          await refreshAll();
        } catch (e) {
          $("#profile-result").textContent = String(e);
        }
      });
      pb.append(btn);
    });
  } catch (e) {
    $("#status-pre").textContent = "Refresh failed: " + e.message;
  }
}

async function refreshLogs() {
  try {
    const data = await fetchJson("/logs/?n=40");
    $("#logs-pre").textContent = pretty(data);
  } catch {
    $("#logs-pre").textContent = "Logs endpoint unavailable.";
  }
}

document.querySelectorAll(".tabs button").forEach((btn) => {
  btn.addEventListener("click", () => activateTab(btn.dataset.tab));
});

$("#sse-toggle").addEventListener("click", () => {
  if (sseAbort) {
    stopSse();
    $("#sse-toggle").textContent = "Start stream";
  } else {
    $("#sse-toggle").textContent = "Stop stream";
    startSse();
  }
});

$("#slider-subagents").addEventListener("input", async (ev) => {
  $("#slider-subagents-label").textContent = ev.target.value;
});

$("#slider-subagents").addEventListener("change", async (ev) => {
  const val = Number(ev.target.value);
  try {
    await fetch("/config/runtime/set", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ key: "agent_core.max_subagents", value: val }),
    });
    $("#profile-result").textContent = `max_subagents ${val} requested`;
    await refreshAll();
  } catch (e) {
    $("#profile-result").textContent = String(e);
  }
});

setInterval(refreshAll, 4000);
setInterval(refreshLogs, 8000);
refreshAll().then(refreshLogs);
