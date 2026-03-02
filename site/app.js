const FEED_URL = "./evidence/index.json";

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function shortSha(value) {
  if (!value) return "-";
  return String(value).slice(0, 12);
}

function smokeStatus(record) {
  return record.tests?.smoke?.status || record.smoke?.status || "unknown";
}

function renderCards(feed) {
  const container = document.getElementById("summary-cards");
  const tpl = document.getElementById("card-template");
  container.textContent = "";

  const cards = [
    ["Total Records", feed.total_records ?? 0],
    ["Promoted", feed.summary?.by_status?.promoted ?? 0],
    ["Failed", feed.summary?.by_status?.failed ?? 0],
    ["Smoke Pass", feed.records?.filter((r) => smokeStatus(r) === "pass").length ?? 0],
  ];

  cards.forEach(([title, value]) => {
    const node = tpl.content.cloneNode(true);
    node.querySelector("h3").textContent = title;
    node.querySelector("p").textContent = String(value);
    container.appendChild(node);
  });
}

function pill(status) {
  const safe = escapeHtml(status || "unknown");
  return `<span class="status-pill status-${safe}">${safe}</span>`;
}

function renderTable(feed) {
  const tableWrap = document.getElementById("records-table");
  const rows = (feed.records || [])
    .map((record) => {
      const digest = record.image?.digest || record.image?.tag || "-";
      return `
        <tr>
          <td>${escapeHtml(record.service)}</td>
          <td>${escapeHtml(record.environment)}</td>
          <td>${pill(record.status)}</td>
          <td>${pill(smokeStatus(record))}</td>
          <td><code>${escapeHtml(shortSha(record.deploy?.commit))}</code></td>
          <td><code>${escapeHtml(digest)}</code></td>
          <td>${escapeHtml(record.timestamps?.updated_at || "-")}</td>
          <td><code>${escapeHtml(record._record_path || "-")}</code></td>
        </tr>
      `;
    })
    .join("");

  tableWrap.innerHTML = `
    <table>
      <thead>
        <tr>
          <th>Service</th>
          <th>Env</th>
          <th>Promotion</th>
          <th>Smoke</th>
          <th>Commit</th>
          <th>Image</th>
          <th>Updated</th>
          <th>Record Path</th>
        </tr>
      </thead>
      <tbody>${rows || '<tr><td colspan="8">No records found.</td></tr>'}</tbody>
    </table>
  `;
}

async function main() {
  const meta = document.getElementById("meta-line");

  try {
    const response = await fetch(FEED_URL, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`Feed HTTP ${response.status}`);
    }

    const feed = await response.json();
    renderCards(feed);
    renderTable(feed);
    meta.textContent = `Generated at ${feed.generated_at} from ${feed.source?.repository || "local"}`;
  } catch (error) {
    meta.textContent = `Failed to load feed: ${error.message}`;
  }
}

main();
