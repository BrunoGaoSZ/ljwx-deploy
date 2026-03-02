(function () {
  const FEED_URL = "./evidence/index.json";
  let allRecords = [];

  const envFilter = document.getElementById("env-filter");
  const testFilter = document.getElementById("test-filter");
  const rowsEl = document.getElementById("rows");
  const metaEl = document.getElementById("meta");

  function text(v) {
    return String(v ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;");
  }

  function digestFromHarbor(harbor) {
    if (!harbor) return "-";
    const idx = harbor.indexOf("@sha256:");
    if (idx === -1) return harbor;
    return "sha256:" + harbor.slice(idx + 8, idx + 8 + 16);
  }

  function smokeStatus(rec) {
    return rec?.tests?.smoke?.status || "unknown";
  }

  function linksHtml(rec) {
    const links = [];
    if (rec?.source?.workflowRun) {
      links.push(`<a href="${text(rec.source.workflowRun)}" target="_blank" rel="noreferrer">run</a>`);
    }
    const approvals = rec?.approvals || {};
    ["specPr", "archPr", "demoPr", "uatPr", "releasePr"].forEach((k) => {
      if (approvals[k]) {
        links.push(`<a href="${text(approvals[k])}" target="_blank" rel="noreferrer">${k}</a>`);
      }
    });
    if (Array.isArray(approvals.prs)) {
      approvals.prs.forEach((pr, i) => {
        if (pr) links.push(`<a href="${text(pr)}" target="_blank" rel="noreferrer">pr${i + 1}</a>`);
      });
    }
    return links.length ? links.join(" ") : "-";
  }

  function render() {
    const env = envFilter.value;
    const test = testFilter.value;
    const filtered = allRecords.filter((r) => {
      if (env && r.env !== env) return false;
      if (test && smokeStatus(r) !== test) return false;
      return true;
    });

    rowsEl.innerHTML = filtered.map((r) => {
      const smoke = smokeStatus(r);
      const klass = ["pass", "fail", "pending", "unknown"].includes(smoke) ? smoke : "unknown";
      return `<tr>
        <td><code>${text(r.evidenceId || "-")}</code></td>
        <td>${text(r.service || "-")}</td>
        <td>${text(r.env || "-")}</td>
        <td><code>${text(digestFromHarbor(r?.image?.harbor || ""))}</code></td>
        <td>${text(r?.deploy?.syncedAt || r?.promotedAt || "-")}</td>
        <td><span class="pill ${klass}">${text(smoke)}</span></td>
        <td>${linksHtml(r)}</td>
      </tr>`;
    }).join("") || '<tr><td colspan="7">No records</td></tr>';

    metaEl.textContent = `records: ${filtered.length} / ${allRecords.length}`;
  }

  function fillEnvOptions() {
    const envs = Array.from(new Set(allRecords.map((r) => r.env).filter(Boolean))).sort();
    envs.forEach((env) => {
      const opt = document.createElement("option");
      opt.value = env;
      opt.textContent = env;
      envFilter.appendChild(opt);
    });
  }

  async function main() {
    const res = await fetch(FEED_URL, { cache: "no-store" });
    if (!res.ok) {
      metaEl.textContent = `failed to load ${FEED_URL}: ${res.status}`;
      return;
    }
    allRecords = await res.json();
    if (!Array.isArray(allRecords)) allRecords = [];
    fillEnvOptions();
    render();
  }

  envFilter.addEventListener("change", render);
  testFilter.addEventListener("change", render);
  main().catch((err) => {
    metaEl.textContent = `error: ${err.message}`;
  });
})();
