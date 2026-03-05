/* vendors.js – searchable, sortable, filterable, paginated vendor table */

(function () {
    const data = RAW_DATA;
    let vendors = (data.vendors || []).slice();
    let filtered = vendors.slice();
    let currentPage = 1;
    const PAGE_SIZE = 20;

    let sortCol = "overdue_amount";
    let sortDir = -1;
    let activeFilter = "all";
    let searchTerm = "";

    const tbody = document.getElementById("vendorBody");
    const recordCount = document.getElementById("recordCount");
    const pgInfo = document.getElementById("pgInfo");
    const pageNumbers = document.getElementById("pageNumbers");
    const prevBtn = document.getElementById("prevBtn");
    const nextBtn = document.getElementById("nextBtn");

    const fmtCurrency = (n) =>
        new Intl.NumberFormat("en-IN", { style: "currency", currency: "INR", maximumFractionDigits: 0 }).format(n || 0);

    const riskClass = { Low: "low", Medium: "medium", High: "high", Critical: "critical" };
    const riskColors = {
        Low:      "rgba(16,217,126,1)",
        Medium:   "rgba(245,197,66,1)",
        High:     "rgba(255,122,47,1)",
        Critical: "rgba(255,59,92,1)",
    };

    // ── Apply filters + search ──────────────────────────────────
    function applyFilters() {
        filtered = vendors.filter((v) => {
            const matchFilter = activeFilter === "all" || v.predicted_risk === activeFilter;
            const term = searchTerm.toLowerCase();
            const matchSearch = !term ||
                String(v.vendor_id || "").toLowerCase().includes(term) ||
                String(v.vendor_name || "").toLowerCase().includes(term);
            return matchFilter && matchSearch;
        });
        currentPage = 1;
        applySort();
    }

    // ── Sort ────────────────────────────────────────────────────
    function applySort() {
        filtered.sort((a, b) => {
            const aVal = a[sortCol] ?? "";
            const bVal = b[sortCol] ?? "";
            if (typeof aVal === "number") return (aVal - bVal) * sortDir;
            return String(aVal).localeCompare(String(bVal)) * sortDir;
        });
        renderTable();
    }

    // ── Render table page ───────────────────────────────────────
    function renderTable() {
        tbody.innerHTML = "";
        const start = (currentPage - 1) * PAGE_SIZE;
        const page = filtered.slice(start, start + PAGE_SIZE);

        if (page.length === 0) {
            tbody.innerHTML = `<tr><td colspan="8" style="text-align:center;color:var(--text-muted);padding:36px;font-size:13px">No vendors match your current filters.</td></tr>`;
        } else {
            page.forEach((v) => {
                const lvl = v.predicted_risk || "Low";
                const cls = riskClass[lvl] || "low";
                const rowCls = lvl === "Critical" ? "row-critical" : lvl === "High" ? "row-high" : "";
                const score = Number(v.risk_score || 0);
                const bar = Math.min(score, 100);
                const avgDays = Math.round(v.avg_days_overdue || 0);
                const tr = document.createElement("tr");
                if (rowCls) tr.classList.add(rowCls);
                tr.innerHTML = `
                    <td><code>${v.vendor_id || "—"}</code></td>
                    <td style="max-width:180px;overflow:hidden;text-overflow:ellipsis">${v.vendor_name || "Unknown"}</td>
                    <td style="font-family:'DM Mono',monospace;font-size:12px">${v.total_invoices || 0}</td>
                    <td style="font-weight:600">${fmtCurrency(v.overdue_amount)}</td>
                    <td style="font-family:'DM Mono',monospace;font-size:12px">${Math.round(v.max_days_overdue || 0)}d</td>
                    <td style="font-family:'DM Mono',monospace;font-size:12px">${avgDays}d</td>
                    <td>
                        <div class="score-cell">
                            <span style="min-width:36px;font-weight:600;font-family:'DM Mono',monospace;font-size:12px">${score.toFixed(1)}</span>
                            <div class="score-bar-bg">
                                <div class="score-bar" style="width:${bar}%;background:${riskColors[lvl] || '#6fa3ff'}"></div>
                            </div>
                        </div>
                    </td>
                    <td><span class="risk-badge ${cls}">${lvl}</span></td>
                `;
                tbody.appendChild(tr);
            });
        }

        const total = filtered.length;
        const from = total === 0 ? 0 : start + 1;
        const to = Math.min(start + PAGE_SIZE, total);
        recordCount.textContent = `${from}–${to} of ${total} vendors`;
        renderPagination();
    }

    // ── Pagination ──────────────────────────────────────────────
    function renderPagination() {
        const totalPages = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
        prevBtn.disabled = currentPage <= 1;
        nextBtn.disabled = currentPage >= totalPages;
        pgInfo.textContent = `Page ${currentPage} / ${totalPages}`;

        pageNumbers.innerHTML = "";
        let start = Math.max(1, currentPage - 2);
        let end = Math.min(totalPages, start + 4);
        if (end - start < 4) start = Math.max(1, end - 4);

        for (let i = start; i <= end; i++) {
            const btn = document.createElement("button");
            btn.className = "pg-num" + (i === currentPage ? " active" : "");
            btn.textContent = i;
            btn.addEventListener("click", () => { currentPage = i; renderTable(); });
            pageNumbers.appendChild(btn);
        }
    }

    prevBtn.addEventListener("click", () => { if (currentPage > 1) { currentPage--; renderTable(); } });
    nextBtn.addEventListener("click", () => {
        const totalPages = Math.ceil(filtered.length / PAGE_SIZE);
        if (currentPage < totalPages) { currentPage++; renderTable(); }
    });

    // ── Search ──────────────────────────────────────────────────
    document.getElementById("searchInput").addEventListener("input", (e) => {
        searchTerm = e.target.value;
        applyFilters();
    });

    // ── Filter pills ────────────────────────────────────────────
    document.querySelectorAll(".pill").forEach((btn) => {
        btn.addEventListener("click", () => {
            document.querySelectorAll(".pill").forEach((b) => b.classList.remove("active"));
            btn.classList.add("active");
            activeFilter = btn.dataset.filter;
            applyFilters();
        });
    });

    // ── Sort headers ────────────────────────────────────────────
    document.querySelectorAll("th.sortable").forEach((th) => {
        th.addEventListener("click", () => {
            const col = th.dataset.col;
            if (sortCol === col) {
                sortDir *= -1;
            } else {
                sortCol = col;
                sortDir = -1;
            }
            document.querySelectorAll("th.sortable i").forEach((i) => {
                i.className = "fas fa-sort";
                i.style.opacity = "0.4";
            });
            const icon = th.querySelector("i");
            icon.className = sortDir === -1 ? "fas fa-sort-down" : "fas fa-sort-up";
            icon.style.opacity = "1";
            applySort();
        });
    });

    // ── Initial render ──────────────────────────────────────────
    applyFilters();
})();