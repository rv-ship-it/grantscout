/* Grant Scout Dashboard – client-side logic */

const PAGE_SIZE = 50;

let allOpportunities = [];
let filteredOpportunities = [];
let currentPage = 1;
let sortField = "final_score";
let sortDir = "desc";
let generatedAt = "";

const GITHUB_REPO = "rv-ship-it/junebiograntscout";
const WORKFLOW_FILE = "weekly.yml";
const TOKEN_KEY = "grant_scout_gh_token";

// --- Bootstrap ---

document.addEventListener("DOMContentLoaded", () => {
  loadData();
  bindEvents();
  initRefresh();
});

async function loadData() {
  const loadingEl = document.getElementById("loadingMsg");
  const errorEl = document.getElementById("errorMsg");

  // Try multiple paths to find the data file (local dev vs GitHub Pages)
  const paths = [
    "../outputs/dashboard_data.json",
    "./data/dashboard_data.json",
    "outputs/dashboard_data.json",
  ];

  let data = null;
  for (const path of paths) {
    try {
      const resp = await fetch(path);
      if (resp.ok) {
        data = await resp.json();
        break;
      }
    } catch (_) {
      // try next path
    }
  }

  if (!data) {
    loadingEl.style.display = "none";
    errorEl.textContent =
      "Could not load opportunity data. Run the pipeline first: python -m grant_scout run";
    errorEl.style.display = "block";
    return;
  }

  allOpportunities = data.opportunities || [];
  generatedAt = data.generated_at || "";

  loadingEl.style.display = "none";
  populateFilters();
  applyFilters();
  updateStats();
  updateLastUpdated();
}

// --- Events ---

function bindEvents() {
  document.getElementById("searchInput").addEventListener("input", debounce(onFilterChange, 250));
  document.getElementById("filterSource").addEventListener("change", onFilterChange);
  document.getElementById("filterAgency").addEventListener("change", onFilterChange);
  document.getElementById("filterTopic").addEventListener("change", onFilterChange);
  document.getElementById("filterDeadline").addEventListener("change", onFilterChange);
  document.getElementById("clearFilters").addEventListener("click", clearFilters);

  document.querySelectorAll("th.sortable").forEach((th) => {
    th.addEventListener("click", () => onSort(th.dataset.sort));
  });

  document.getElementById("prevPage").addEventListener("click", () => changePage(-1));
  document.getElementById("nextPage").addEventListener("click", () => changePage(1));

  // Modal
  document.getElementById("modalOverlay").addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeModal();
  });
  document.getElementById("modalClose").addEventListener("click", closeModal);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") closeModal();
  });
}

// --- Filtering ---

function onFilterChange() {
  currentPage = 1;
  applyFilters();
}

function applyFilters() {
  const search = document.getElementById("searchInput").value.toLowerCase().trim();
  const source = document.getElementById("filterSource").value;
  const agency = document.getElementById("filterAgency").value;
  const topic = document.getElementById("filterTopic").value;
  const deadlineDays = parseInt(document.getElementById("filterDeadline").value) || 0;

  const now = new Date();

  filteredOpportunities = allOpportunities.filter((opp) => {
    if (source && opp.source !== source) return false;
    if (agency && opp.agency !== agency) return false;
    if (topic && !(opp.matched_topics || "").includes(topic)) return false;

    if (deadlineDays && opp.deadline) {
      const dl = new Date(opp.deadline);
      const diffDays = (dl - now) / (1000 * 60 * 60 * 24);
      if (diffDays < 0 || diffDays > deadlineDays) return false;
    }

    if (search) {
      const hay = [opp.title, opp.agency, opp.summary, opp.opportunity_number, opp.matched_topics]
        .join(" ")
        .toLowerCase();
      if (!hay.includes(search)) return false;
    }

    return true;
  });

  sortOpportunities();
  renderTable();
  updatePagination();
  updateFilteredCount();
}

function clearFilters() {
  document.getElementById("searchInput").value = "";
  document.getElementById("filterSource").value = "";
  document.getElementById("filterAgency").value = "";
  document.getElementById("filterTopic").value = "";
  document.getElementById("filterDeadline").value = "";
  currentPage = 1;
  applyFilters();
}

// --- Sorting ---

function onSort(field) {
  if (sortField === field) {
    sortDir = sortDir === "asc" ? "desc" : "asc";
  } else {
    sortField = field;
    sortDir = field === "final_score" ? "desc" : "asc";
  }

  // Update header indicators
  document.querySelectorAll("th.sortable").forEach((th) => {
    th.classList.remove("sorted-asc", "sorted-desc");
    if (th.dataset.sort === sortField) {
      th.classList.add(sortDir === "asc" ? "sorted-asc" : "sorted-desc");
    }
  });

  sortOpportunities();
  renderTable();
}

function sortOpportunities() {
  filteredOpportunities.sort((a, b) => {
    let va = a[sortField] ?? "";
    let vb = b[sortField] ?? "";

    if (typeof va === "number" && typeof vb === "number") {
      return sortDir === "asc" ? va - vb : vb - va;
    }

    va = String(va).toLowerCase();
    vb = String(vb).toLowerCase();

    if (va < vb) return sortDir === "asc" ? -1 : 1;
    if (va > vb) return sortDir === "asc" ? 1 : -1;
    return 0;
  });
}

// --- Rendering ---

function renderTable() {
  const tbody = document.getElementById("tableBody");
  const start = (currentPage - 1) * PAGE_SIZE;
  const page = filteredOpportunities.slice(start, start + PAGE_SIZE);

  if (page.length === 0) {
    tbody.innerHTML = '<tr><td colspan="6" style="text-align:center;padding:2rem;color:var(--text-muted)">No matching opportunities found.</td></tr>';
    return;
  }

  tbody.innerHTML = page
    .map((opp, i) => {
      const scoreClass = opp.final_score >= 20 ? "score-high" : opp.final_score >= 5 ? "score-mid" : "score-low";
      const sourceClass = opp.source === "Grants.gov" ? "source-grants-gov" : opp.source === "EU Portal" ? "source-eu-portal" : "source-nih-guide";
      const hpBadge = opp.high_priority ? '<span class="badge-hp">HP</span>' : "";

      const topics = (opp.matched_topics || "")
        .split(",")
        .map((t) => t.trim())
        .filter(Boolean)
        .slice(0, 3)
        .map((t) => `<span class="topic-tag">${escapeHtml(t)}</span>`)
        .join("");

      const deadlineDisplay = opp.deadline || "Open";
      const deadlineClass = isUrgent(opp.deadline) ? ' style="color:var(--danger);font-weight:600"' : "";

      return `<tr data-index="${start + i}">
        <td><span class="score-badge ${scoreClass}">${opp.final_score.toFixed(1)}</span></td>
        <td class="title-cell">
          <div class="title-text">${escapeHtml(opp.title)}${hpBadge}</div>
          <div class="opp-number">${escapeHtml(opp.opportunity_number)}</div>
        </td>
        <td>${escapeHtml(opp.agency)}</td>
        <td><span class="source-badge ${sourceClass}">${escapeHtml(opp.source)}</span></td>
        <td${deadlineClass}>${escapeHtml(deadlineDisplay)}</td>
        <td><div class="topic-tags">${topics}</div></td>
      </tr>`;
    })
    .join("");

  // Row click -> detail modal
  tbody.querySelectorAll("tr").forEach((tr) => {
    tr.addEventListener("click", () => {
      const idx = parseInt(tr.dataset.index);
      openModal(filteredOpportunities[idx]);
    });
  });
}

function isUrgent(deadline) {
  if (!deadline) return false;
  const dl = new Date(deadline);
  const diff = (dl - new Date()) / (1000 * 60 * 60 * 24);
  return diff >= 0 && diff <= 30;
}

// --- Pagination ---

function updatePagination() {
  const totalPages = Math.max(1, Math.ceil(filteredOpportunities.length / PAGE_SIZE));
  document.getElementById("pageInfo").textContent = `Page ${currentPage} of ${totalPages}`;
  document.getElementById("prevPage").disabled = currentPage <= 1;
  document.getElementById("nextPage").disabled = currentPage >= totalPages;
  document.getElementById("pagination").style.display = filteredOpportunities.length > PAGE_SIZE ? "flex" : "none";
}

function changePage(delta) {
  const totalPages = Math.ceil(filteredOpportunities.length / PAGE_SIZE);
  currentPage = Math.max(1, Math.min(totalPages, currentPage + delta));
  renderTable();
  updatePagination();
  window.scrollTo({ top: document.querySelector(".table-container").offsetTop - 10, behavior: "smooth" });
}

// --- Stats ---

function updateStats() {
  const total = allOpportunities.length;
  const gg = allOpportunities.filter((o) => o.source === "Grants.gov").length;
  const eu = allOpportunities.filter((o) => o.source === "EU Portal").length;
  const nih = allOpportunities.filter((o) => o.source === "NIH Guide").length;
  const hp = allOpportunities.filter((o) => o.high_priority).length;

  document.getElementById("statTotal").textContent = total;
  document.getElementById("statGrantsGov").textContent = gg;
  document.getElementById("statEU").textContent = eu;
  document.getElementById("statNIH").textContent = nih;
  document.getElementById("statHighPriority").textContent = hp;
}

function updateFilteredCount() {
  document.getElementById("statFiltered").textContent = filteredOpportunities.length;
}

function updateLastUpdated() {
  if (generatedAt) {
    const dt = new Date(generatedAt);
    document.getElementById("lastUpdated").textContent = `Last updated: ${dt.toLocaleDateString("en-US", { year: "numeric", month: "long", day: "numeric", hour: "2-digit", minute: "2-digit" })}`;
  }
}

// --- Filter dropdowns ---

function populateFilters() {
  // Agencies
  const agencies = [...new Set(allOpportunities.map((o) => o.agency))].sort();
  const agencySelect = document.getElementById("filterAgency");
  agencies.forEach((a) => {
    const opt = document.createElement("option");
    opt.value = a;
    opt.textContent = a;
    agencySelect.appendChild(opt);
  });

  // Topics
  const topicSet = new Set();
  allOpportunities.forEach((o) => {
    (o.matched_topics || "").split(",").forEach((t) => {
      const trimmed = t.trim();
      if (trimmed) topicSet.add(trimmed);
    });
  });
  const topics = [...topicSet].sort();
  const topicSelect = document.getElementById("filterTopic");
  topics.forEach((t) => {
    const opt = document.createElement("option");
    opt.value = t;
    opt.textContent = t;
    topicSelect.appendChild(opt);
  });
}

// --- Modal ---

function openModal(opp) {
  const content = document.getElementById("modalContent");
  const scoreClass = opp.final_score >= 20 ? "score-high" : opp.final_score >= 5 ? "score-mid" : "score-low";
  const hpBadge = opp.high_priority ? ' <span class="badge-hp">HIGH PRIORITY</span>' : "";

  content.innerHTML = `
    <h2>${escapeHtml(opp.title)}${hpBadge}</h2>
    <div class="detail-grid">
      <span class="detail-label">Score</span>
      <span class="detail-value"><span class="score-badge ${scoreClass}">${opp.final_score.toFixed(1)}</span> (keyword: ${opp.keyword_score.toFixed(1)})</span>

      <span class="detail-label">Source</span>
      <span class="detail-value">${escapeHtml(opp.source)}</span>

      <span class="detail-label">Agency</span>
      <span class="detail-value">${escapeHtml(opp.agency)}</span>

      <span class="detail-label">Opportunity #</span>
      <span class="detail-value">${escapeHtml(opp.opportunity_number)}</span>

      <span class="detail-label">Posted</span>
      <span class="detail-value">${escapeHtml(opp.posted_date || "N/A")}</span>

      <span class="detail-label">Deadline</span>
      <span class="detail-value">${escapeHtml(opp.deadline || "Open / Not specified")}</span>

      <span class="detail-label">Topics</span>
      <span class="detail-value">${escapeHtml(opp.matched_topics || "None")}</span>

      ${opp.url ? `<span class="detail-label">Link</span><span class="detail-value"><a href="${escapeHtml(opp.url)}" target="_blank" rel="noopener">View opportunity</a></span>` : ""}

      ${opp.eligibility ? `<span class="detail-label">Eligibility</span><span class="detail-value">${escapeHtml(opp.eligibility).substring(0, 500)}</span>` : ""}
    </div>

    ${opp.summary ? `<div class="summary-section"><h3>Summary</h3><div class="summary-text">${escapeHtml(opp.summary).substring(0, 2000)}</div></div>` : ""}
  `;

  document.getElementById("modalOverlay").classList.add("active");
  document.body.style.overflow = "hidden";
}

function closeModal() {
  document.getElementById("modalOverlay").classList.remove("active");
  document.body.style.overflow = "";
}

// --- Utilities ---

function escapeHtml(str) {
  if (!str) return "";
  const div = document.createElement("div");
  div.textContent = str;
  return div.innerHTML;
}

function debounce(fn, ms) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  };
}

// --- Refresh / Token Management ---

function initRefresh() {
  const refreshBtn = document.getElementById("refreshBtn");
  const settingsBtn = document.getElementById("settingsBtn");
  const tokenSave = document.getElementById("tokenSave");
  const tokenModalClose = document.getElementById("tokenModalClose");
  const tokenOverlay = document.getElementById("tokenModalOverlay");

  refreshBtn.addEventListener("click", refreshGrants);
  settingsBtn.addEventListener("click", openTokenModal);
  tokenSave.addEventListener("click", saveToken);
  tokenModalClose.addEventListener("click", closeTokenModal);
  tokenOverlay.addEventListener("click", (e) => {
    if (e.target === e.currentTarget) closeTokenModal();
  });

  updateRefreshButton();
}

function getToken() {
  return localStorage.getItem(TOKEN_KEY) || "";
}

function updateRefreshButton() {
  const btn = document.getElementById("refreshBtn");
  const hasToken = !!getToken();
  btn.disabled = !hasToken;
  btn.title = hasToken
    ? "Refresh grants from all sources"
    : "Configure a GitHub token first (click gear icon)";
}

async function refreshGrants() {
  const token = getToken();
  if (!token) {
    openTokenModal();
    return;
  }

  const btn = document.getElementById("refreshBtn");
  const icon = document.getElementById("refreshIcon");
  const label = document.getElementById("refreshLabel");

  btn.disabled = true;
  icon.classList.add("spinning");
  label.textContent = "Triggering...";

  try {
    const resp = await fetch(
      `https://api.github.com/repos/${GITHUB_REPO}/actions/workflows/${WORKFLOW_FILE}/dispatches`,
      {
        method: "POST",
        headers: {
          Authorization: `Bearer ${token}`,
          Accept: "application/vnd.github+json",
          "X-GitHub-Api-Version": "2022-11-28",
        },
        body: JSON.stringify({ ref: "main" }),
      }
    );

    if (resp.status === 204) {
      label.textContent = "Pipeline triggered!";
      btn.classList.add("refresh-success");
    } else if (resp.status === 401 || resp.status === 403) {
      label.textContent = "Invalid token";
      btn.classList.add("refresh-error");
    } else {
      label.textContent = "Failed";
      btn.classList.add("refresh-error");
    }
  } catch (_) {
    label.textContent = "Network error";
    btn.classList.add("refresh-error");
  }

  icon.classList.remove("spinning");

  setTimeout(() => {
    label.textContent = "Refresh Grants";
    btn.classList.remove("refresh-success", "refresh-error");
    btn.disabled = false;
  }, 3000);
}

function openTokenModal() {
  const input = document.getElementById("tokenInput");
  const status = document.getElementById("tokenStatus");
  input.value = getToken();
  status.textContent = getToken() ? "Token saved." : "";
  document.getElementById("tokenModalOverlay").classList.add("active");
}

function closeTokenModal() {
  document.getElementById("tokenModalOverlay").classList.remove("active");
}

function saveToken() {
  const input = document.getElementById("tokenInput");
  const status = document.getElementById("tokenStatus");
  const val = input.value.trim();

  if (val) {
    localStorage.setItem(TOKEN_KEY, val);
    status.textContent = "Token saved.";
    status.style.color = "var(--success)";
  } else {
    localStorage.removeItem(TOKEN_KEY);
    status.textContent = "Token removed.";
    status.style.color = "var(--text-muted)";
  }

  updateRefreshButton();
}
