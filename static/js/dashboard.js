/* dashboard.js – renders KPI cards and all Chart.js charts */

(function () {
    const data = RAW_DATA;
    const kpi = data.kpi;

    // ── Format helpers ─────────────────────────────────────────
    const fmtCurrency = (n) =>
        new Intl.NumberFormat("en-IN", {
            style: "currency", currency: "INR",
            maximumFractionDigits: 0,
        }).format(n);

    const fmtShort = (v) => {
        if (v >= 1e7) return "₹" + (v / 1e7).toFixed(1) + "Cr";
        if (v >= 1e5) return "₹" + (v / 1e5).toFixed(1) + "L";
        if (v >= 1e3) return "₹" + (v / 1e3).toFixed(0) + "K";
        return "₹" + v;
    };

    const riskColor = {
        Low:      "rgba(16,217,126,0.8)",
        Medium:   "rgba(245,197,66,0.8)",
        High:     "rgba(255,122,47,0.8)",
        Critical: "rgba(255,59,92,0.8)",
    };
    const riskBorder = {
        Low:      "rgba(16,217,126,1)",
        Medium:   "rgba(245,197,66,1)",
        High:     "rgba(255,122,47,1)",
        Critical: "rgba(255,59,92,1)",
    };

    // ── KPI Cards ──────────────────────────────────────────────
    document.getElementById("kpiTotalVendors").textContent = kpi.total_vendors.toLocaleString();
    document.getElementById("kpiOverdue").textContent = fmtShort(kpi.total_overdue);
    document.getElementById("kpiHighRisk").textContent = kpi.high_risk.toLocaleString();
    document.getElementById("kpiCritical").textContent = kpi.critical.toLocaleString();

    // ── Chart defaults ─────────────────────────────────────────
    Chart.defaults.color = "#7a8aab";
    Chart.defaults.font.family = "'DM Sans', sans-serif";
    Chart.defaults.font.size = 12;

    const gridColor = "rgba(255,255,255,0.04)";
    const tooltipStyle = {
        backgroundColor: "rgba(8,11,16,0.97)",
        borderColor: "rgba(255,255,255,0.1)",
        borderWidth: 1,
        titleColor: "#edf2fb",
        bodyColor: "#7a8aab",
        padding: 12,
        cornerRadius: 8,
        titleFont: { family: "'Syne', sans-serif", weight: '600', size: 13 },
    };

    // ── 1. Aging Bucket Bar Chart ──────────────────────────────
    const agingBuckets = data.aging_buckets;
    new Chart(document.getElementById("agingChart"), {
        type: "bar",
        data: {
            labels: ["0–30 Days", "31–60 Days", "61–90 Days", "91–120 Days", "120+ Days"],
            datasets: [{
                label: "Overdue Amount",
                data: [
                    agingBuckets["0-30"],
                    agingBuckets["31-60"],
                    agingBuckets["61-90"],
                    agingBuckets["91-120"],
                    agingBuckets["120+"],
                ],
                backgroundColor: [
                    "rgba(16,217,126,0.7)",
                    "rgba(245,197,66,0.7)",
                    "rgba(255,122,47,0.7)",
                    "rgba(255,59,92,0.7)",
                    "rgba(180,20,50,0.85)",
                ],
                borderColor: [
                    "rgba(16,217,126,1)",
                    "rgba(245,197,66,1)",
                    "rgba(255,122,47,1)",
                    "rgba(255,59,92,1)",
                    "rgba(200,30,60,1)",
                ],
                borderWidth: 1,
                borderRadius: 5,
                borderSkipped: false,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...tooltipStyle,
                    callbacks: { label: (ctx) => "  " + fmtCurrency(ctx.parsed.y) },
                },
            },
            scales: {
                x: { grid: { color: gridColor }, border: { color: "transparent" } },
                y: {
                    grid: { color: gridColor },
                    border: { color: "transparent" },
                    ticks: { callback: (v) => fmtShort(v) },
                },
            },
        },
    });

    // ── 2. Risk Distribution Doughnut ─────────────────────────
    const riskDist = data.risk_distribution;
    const riskLabels = ["Low", "Medium", "High", "Critical"];
    new Chart(document.getElementById("riskPieChart"), {
        type: "doughnut",
        data: {
            labels: riskLabels,
            datasets: [{
                data: riskLabels.map((l) => riskDist[l] || 0),
                backgroundColor: riskLabels.map((l) => riskColor[l]),
                borderColor: riskLabels.map((l) => riskBorder[l]),
                borderWidth: 2,
                hoverOffset: 8,
            }],
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: "68%",
            plugins: {
                legend: {
                    position: "right",
                    labels: { padding: 16, usePointStyle: true, pointStyleWidth: 9, font: { size: 12 } },
                },
                tooltip: {
                    ...tooltipStyle,
                    callbacks: { label: (ctx) => `  ${ctx.label}: ${ctx.parsed} vendors` },
                },
            },
        },
    });

    // ── 3. Top 10 Risky Vendors Horizontal Bar ─────────────────
    const top10 = data.top10;
    new Chart(document.getElementById("top10Chart"), {
        type: "bar",
        data: {
            labels: top10.map((r) => r.vendor_name || r.vendor_id),
            datasets: [{
                label: "Overdue Amount",
                data: top10.map((r) => r.overdue_amount),
                backgroundColor: top10.map((r) => riskColor[r.predicted_risk] || "rgba(61,127,255,0.75)"),
                borderColor: top10.map((r) => riskBorder[r.predicted_risk] || "rgba(61,127,255,1)"),
                borderWidth: 1,
                borderRadius: { topRight: 5, bottomRight: 5 },
                borderSkipped: false,
            }],
        },
        options: {
            indexAxis: "y",
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false },
                tooltip: {
                    ...tooltipStyle,
                    callbacks: { label: (ctx) => "  " + fmtCurrency(ctx.parsed.x) },
                },
            },
            scales: {
                x: {
                    grid: { color: gridColor },
                    border: { color: "transparent" },
                    ticks: { callback: (v) => fmtShort(v) },
                },
                y: {
                    grid: { display: false },
                    border: { color: "transparent" },
                    ticks: { font: { size: 11 } },
                },
            },
        },
    });

    // ── 4. Scatter Chart: Risk Score vs Overdue Amount ─────────
    const scatterVendors = data.scatter;
    const scatterDatasets = riskLabels.map((lvl) => ({
        label: lvl,
        data: scatterVendors
            .filter((v) => v.predicted_risk === lvl)
            .map((v) => ({ x: v.risk_score, y: v.overdue_amount, name: v.vendor_name || v.vendor_id })),
        backgroundColor: riskColor[lvl],
        borderColor: riskBorder[lvl],
        borderWidth: 1.5,
        pointRadius: 5,
        pointHoverRadius: 8,
    }));
    new Chart(document.getElementById("scatterChart"), {
        type: "scatter",
        data: { datasets: scatterDatasets },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: "top",
                    labels: { usePointStyle: true, pointStyleWidth: 8, padding: 14, font: { size: 12 } },
                },
                tooltip: {
                    ...tooltipStyle,
                    callbacks: {
                        label: (ctx) => {
                            const d = ctx.raw;
                            return [`  ${d.name}`, `  Score: ${d.x}`, `  Overdue: ${fmtCurrency(d.y)}`];
                        },
                    },
                },
            },
            scales: {
                x: {
                    grid: { color: gridColor },
                    border: { color: "transparent" },
                    title: { display: true, text: "Risk Score", color: "#7a8aab", font: { size: 11 } },
                    min: 0, max: 100,
                },
                y: {
                    grid: { color: gridColor },
                    border: { color: "transparent" },
                    title: { display: true, text: "Overdue Amount (₹)", color: "#7a8aab", font: { size: 11 } },
                    ticks: { callback: (v) => fmtShort(v) },
                },
            },
        },
    });

    // ── Preview Table (Top 10) ─────────────────────────────────
    const previewBody = document.getElementById("previewBody");
    top10.forEach((r) => {
        const lvl = (r.predicted_risk || "").toLowerCase();
        const tr = document.createElement("tr");
        if (lvl === "critical") tr.classList.add("row-critical");
        else if (lvl === "high") tr.classList.add("row-high");
        tr.innerHTML = `
            <td><code>${r.vendor_id}</code></td>
            <td>${r.vendor_name || r.vendor_id}</td>
            <td style="font-weight:600">${fmtCurrency(r.overdue_amount)}</td>
            <td>
                <div class="score-cell">
                    <span style="min-width:36px;font-weight:600;font-family:'DM Mono',monospace;font-size:12px">${r.risk_score.toFixed(1)}</span>
                    <div class="score-bar-bg">
                        <div class="score-bar" style="width:${r.risk_score}%;background:${riskBorder[r.predicted_risk] || '#6fa3ff'}"></div>
                    </div>
                </div>
            </td>
            <td><span class="risk-badge ${lvl}">${r.predicted_risk}</span></td>
        `;
        previewBody.appendChild(tr);
    });
})();