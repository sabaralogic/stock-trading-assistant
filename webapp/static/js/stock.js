const urlParams =
    new URLSearchParams(window.location.search);

const symbol =
    urlParams.get("symbol") ||
    window.location.pathname.split("/").pop();

async function loadAnalysis() {
    try {
        const response =
            await fetch(
                `/static/data/analyze/${encodeURIComponent(symbol)}.json`
            );

        if (!response.ok) {
            throw new Error(
                `Analysis is not available for ${symbol} in the published dataset.`
            );
        }

        const data =
            await response.json();

        renderAnalysis(data);
    } catch (error) {
        renderAnalysisError(
            error?.message ||
            `Analysis is not available for ${symbol}.`
        );
        return;
    }
}

function renderAnalysis(data) {

    document.getElementById("symbol")
        .innerText = symbol;

    document.getElementById("summary")
        .innerHTML = `
            <p>
                Signal:
                <b>${data.summary.signal}</b>
            </p>

            <p>
                Score:
                ${data.summary.score}
            </p>

            <p>
                RSI:
                ${formatNumber(data.summary.rsi)}
            </p>
        `;

    renderExpectedReturnInfo(data.summary || {});

    renderTurningPointChart(
        data.chart_turning_points || data.all_turning_points || [],
        data.predicted_turning_points || [],
        data.heuristic_stages || []
    );

    const insights =
        document.getElementById("insights");

    insights.innerHTML = "";

    data.insights.forEach(i => {

        insights.innerHTML +=
            `<li>${i}</li>`;
    });

    renderRecentDataTable(data.recent_data || []);
    renderHeuristicDataTable(data.predicted_turning_points || []);
    renderHeuristicHistoryTable(data.heuristic_history || []);
}

function renderAnalysisError(message) {

    document.getElementById("symbol")
        .innerText = symbol;

    const safeMessage =
        escapeHtml(message);

    document.getElementById("summary")
        .innerHTML = `
            <div class="chart-empty">
                ${safeMessage}<br><br>
                This page shows only pre-exported stock analysis data that has been published with the site.
            </div>
        `;

    document.getElementById("expectedReturnInfo").innerHTML = "";
    document.getElementById("turningPointChart").innerHTML = "";
    document.getElementById("insights").innerHTML = "";
    document.getElementById("recentData").innerHTML = "";
    document.getElementById("heuristicData").innerHTML = "";
    document.getElementById("heuristicHistory").innerHTML = "";
}

function renderExpectedReturnInfo(summary) {

    const container =
        document.getElementById("expectedReturnInfo");

    if (!container) {
        return;
    }

    const expectedReturn =
        Number(summary.expected_xirr);
    const expectedEntryPrice =
        Number(summary.expected_entry_price);
    const expectedLowPrice =
        Number(summary.expected_low_price);
    const expectedPeakPrice =
        Number(summary.expected_peak_price);
    const daysToPeak =
        Number(summary.expected_peak_days);
    const entryDate =
        summary.expected_entry_date
            ? formatFullDate(new Date(summary.expected_entry_date))
            : "N/A";
    const lowDate =
        summary.expected_low_date
            ? formatFullDate(new Date(summary.expected_low_date))
            : "N/A";
    const peakDate =
        summary.expected_peak_date
            ? formatFullDate(new Date(summary.expected_peak_date))
            : "N/A";

    if (
        !Number.isFinite(expectedReturn) ||
        !Number.isFinite(expectedEntryPrice) ||
        !Number.isFinite(expectedLowPrice) ||
        !Number.isFinite(expectedPeakPrice) ||
        !Number.isFinite(daysToPeak) ||
        daysToPeak <= 0
    ) {
        container.innerHTML = `
            <section class="metric-explainer">
                <h2>Expected Annualized Return - with heuristics</h2>
                <p class="metric-empty">
                    No projected annualized return is available from the current heuristic path.
                </p>
            </section>
        `;
        return;
    }

    const usesCurrentClose =
        expectedEntryPrice < expectedLowPrice;
    const calculationText =
        `((${formatNumber(expectedPeakPrice)} - ${formatNumber(expectedEntryPrice)}) / ${formatNumber(expectedEntryPrice)}) / ${daysToPeak} * 365 * 100 = ${formatPercent(expectedReturn)}`;

    container.innerHTML = `
        <section class="metric-explainer">
            <h2>Expected Annualized Return - with heuristics</h2>
            <p class="metric-value">${formatPercent(expectedReturn)}</p>
            <p class="metric-note">
                Based on the selected projected entry on ${escapeHtml(lowDate)} and the selected later projected exit on ${escapeHtml(peakDate)}.
            </p>
            <p class="metric-note">
                Effective Entry: ${escapeHtml(formatNumber(expectedEntryPrice))} on ${escapeHtml(entryDate)}${usesCurrentClose ? " (current close used because it is lower than the selected projected entry)" : ""} |
            </p>
            <p class="metric-note">
                Selected Entry: ${escapeHtml(formatNumber(expectedLowPrice))} |
                Selected Exit: ${escapeHtml(formatNumber(expectedPeakPrice))} |
                Days: ${escapeHtml(String(daysToPeak))}
            </p>
            <pre class="metric-formula">${escapeHtml(calculationText)}</pre>
        </section>
    `;
}

function renderRecentDataTable(rows) {

    const container =
        document.getElementById("recentData");

    if (!container) {
        return;
    }

    if (!Array.isArray(rows) || rows.length === 0) {
        container.innerHTML =
            '<div class="chart-empty">No recent stock data available.</div>';
        return;
    }

    const orderedRows =
        [...rows].reverse();
    const columns =
        ["Date", "Open", "High", "Low", "Close", "Volume", "RSI", "MA50", "MA200"]
            .filter(column => Object.prototype.hasOwnProperty.call(orderedRows[0], column));

    const headerHtml =
        columns.map(column => `<th>${escapeHtml(column)}</th>`).join("");

    const bodyHtml =
        orderedRows.map(row => {
            const cells = columns.map(column => {
                let value = row[column];

                if (column === "Date") {
                    value = formatFullDate(new Date(value));
                } else if (column === "Volume") {
                    value = formatInteger(value);
                } else {
                    value = formatNumber(value);
                }

                return `<td>${escapeHtml(String(value))}</td>`;
            }).join("");

            return `<tr>${cells}</tr>`;
        }).join("");

    container.innerHTML = `
        <table class="recent-data-table">
            <thead>
                <tr>${headerHtml}</tr>
            </thead>
            <tbody>
                ${bodyHtml}
            </tbody>
        </table>
    `;
}

function renderHeuristicDataTable(rows) {

    const container =
        document.getElementById("heuristicData");

    if (!container) {
        return;
    }

    if (!Array.isArray(rows) || rows.length === 0) {
        container.innerHTML =
            '<div class="chart-empty">No heuristic data available.</div>';
        return;
    }

    const bodyHtml =
        rows.map(row => {
            const date =
                formatFullDate(new Date(row.date));
            const type =
                row.type || "";
            const price =
                formatNumber(row.price);
            const swing =
                formatPercent(row.projected_swing_pct);

            return `
                <tr>
                    <td>${escapeHtml(String(date))}</td>
                    <td>${escapeHtml(String(type))}</td>
                    <td>${escapeHtml(String(price))}</td>
                    <td>${escapeHtml(String(swing))}</td>
                </tr>
            `;
        }).join("");

    container.innerHTML = `
        <table class="heuristic-data-table">
            <thead>
                <tr>
                    <th>Date</th>
                    <th>Type</th>
                    <th>Price</th>
                    <th>Swing</th>
                </tr>
            </thead>
            <tbody>
                ${bodyHtml}
            </tbody>
        </table>
    `;
}

function renderHeuristicHistoryTable(rows) {

    const container =
        document.getElementById("heuristicHistory");

    if (!container) {
        return;
    }

    if (!Array.isArray(rows) || rows.length === 0) {
        container.innerHTML =
            '<div class="chart-empty">No heuristic history available yet.</div>';
        return;
    }

    const bodyHtml =
        rows.map(row => {
            const snapshotDate =
                row.snapshot_date
                    ? formatFullDate(new Date(row.snapshot_date))
                    : "N/A";
            const close =
                formatNumber(row.close);
            const entryDate =
                row.expected_entry_date
                    ? formatFullDate(new Date(row.expected_entry_date))
                    : "N/A";
            const entryPrice =
                formatNumber(row.expected_entry_price);
            const peakDate =
                row.expected_peak_date
                    ? formatFullDate(new Date(row.expected_peak_date))
                    : "N/A";
            const peakPrice =
                formatNumber(row.expected_peak_price);
            const expectedReturn =
                formatPercent(row.expected_xirr);

            return `
                <tr>
                    <td>${escapeHtml(String(snapshotDate))}</td>
                    <td>${escapeHtml(String(close))}</td>
                    <td>${escapeHtml(String(entryDate))}</td>
                    <td>${escapeHtml(String(entryPrice))}</td>
                    <td>${escapeHtml(String(peakDate))}</td>
                    <td>${escapeHtml(String(peakPrice))}</td>
                    <td>${escapeHtml(String(expectedReturn))}</td>
                </tr>
            `;
        }).join("");

    container.innerHTML = `
        <table class="heuristic-history-table">
            <thead>
                <tr>
                    <th>Snapshot</th>
                    <th>Close</th>
                    <th>Expected Buy Date</th>
                    <th>Expected Buy Price</th>
                    <th>Expected Sell Date</th>
                    <th>Expected Sell Price</th>
                    <th>Return</th>
                </tr>
            </thead>
            <tbody>
                ${bodyHtml}
            </tbody>
        </table>
    `;
}

function renderTurningPointChart(turningPoints, predictedTurningPoints, heuristicStages) {

    const container =
        document.getElementById("turningPointChart");
    container.style.position = "relative";

    const actualPoints =
        (turningPoints || [])
            .map(point => toChartPoint(point, false))
            .filter(Boolean);

    const displayedActualPoints =
        limitChartPointsToLastYear(actualPoints);

    const projectedPoints =
        (predictedTurningPoints || [])
            .map(point => toChartPoint(point, true))
            .filter(Boolean);

    const normalizedStages =
        normalizeHeuristicStages(heuristicStages, projectedPoints);
    const finalStage =
        normalizedStages.length > 0
            ? normalizedStages[normalizedStages.length - 1]
            : null;
    const intermediateStages =
        normalizedStages.length > 1
            ? normalizedStages.slice(0, -1)
            : [];
    const finalStageLabel =
        finalStage
            ? finalStage.label
            : "Final";

    if (displayedActualPoints.length < 2) {
        container.innerHTML =
            '<div class="chart-empty">Not enough turning points to draw a chart.</div>';
        return;
    }

    const width = 980;
    const height = 420;
    const marginLeft = 68;
    const marginRight = 28;
    const marginTop = 20;
    const marginBottom = 48;
    const innerWidth = width - marginLeft - marginRight;
    const innerHeight = height - marginTop - marginBottom;
    let selectedStageIndex = -1;

    function renderChartFrame() {
        const selectedStage =
            selectedStageIndex >= 0
                ? intermediateStages[selectedStageIndex]
                : null;
        const visibleProjectedStages =
            [selectedStage, finalStage].filter(Boolean);
        const allPoints =
            [
                ...displayedActualPoints,
                ...visibleProjectedStages.flatMap(stage => stage.points),
            ];

        const minPrice =
            Math.min(...allPoints.map(point => point.price));
        const maxPrice =
            Math.max(...allPoints.map(point => point.price));
        const safeMinPrice =
            minPrice === maxPrice ? minPrice - 1 : minPrice;
        const safeMaxPrice =
            minPrice === maxPrice ? maxPrice + 1 : maxPrice;

        const minDate =
            displayedActualPoints[0].date;
        const maxDate =
            allPoints[allPoints.length - 1].date;
        const totalMs =
            Math.max(maxDate - minDate, 1);

        function xPos(date) {
            const elapsed = date - minDate;
            return marginLeft + (elapsed / totalMs) * innerWidth;
        }

        function yPos(price) {
            return marginTop +
                ((safeMaxPrice - price) / (safeMaxPrice - safeMinPrice)) * innerHeight;
        }

        const actualPolyline =
            displayedActualPoints
                .map(point => `${xPos(point.date).toFixed(2)},${yPos(point.price).toFixed(2)}`)
                .join(" ");

        const intermediatePolyline =
            selectedStage && selectedStage.points.length > 0
                ? [displayedActualPoints[displayedActualPoints.length - 1], ...selectedStage.points]
                    .map(point => `${xPos(point.date).toFixed(2)},${yPos(point.price).toFixed(2)}`)
                    .join(" ")
                : "";

        const finalPolyline =
            finalStage && finalStage.points.length > 0
                ? [displayedActualPoints[displayedActualPoints.length - 1], ...finalStage.points]
                    .map(point => `${xPos(point.date).toFixed(2)},${yPos(point.price).toFixed(2)}`)
                    .join(" ")
                : "";

        const actualMarkers =
            displayedActualPoints.map(point => {
                return `
                    <circle
                        class="chart-point"
                        cx="${xPos(point.date).toFixed(2)}"
                        cy="${yPos(point.price).toFixed(2)}"
                        r="8"
                        fill="transparent"
                        stroke="none"
                        data-type="${escapeAttribute(point.type)}"
                        data-date="${escapeAttribute(formatFullDate(point.date))}"
                        data-price="${escapeAttribute(formatNumber(point.price))}"
                        data-swing="${escapeAttribute(formatSwingText(point.swingPct))}"
                        data-projected="false"
                    ></circle>
                `;
            }).join("");

        const projectedMarkerPoints =
            [
                ...(selectedStage?.points || []),
                ...(finalStage?.points || projectedPoints),
            ];

        const projectedMarkers =
            projectedMarkerPoints.map(point => `
                <circle
                    class="chart-point"
                    cx="${xPos(point.date).toFixed(2)}"
                    cy="${yPos(point.price).toFixed(2)}"
                    r="8"
                    fill="transparent"
                    stroke="none"
                    data-type="${escapeAttribute(point.type)}"
                    data-date="${escapeAttribute(formatFullDate(point.date))}"
                    data-price="${escapeAttribute(formatNumber(point.price))}"
                    data-swing="${escapeAttribute(formatSwingText(point.swingPct))}"
                    data-projected="true"
                ></circle>
            `).join("");

        const priceLabels =
            [0, 0.25, 0.5, 0.75, 1].map(fraction => {
                const price = safeMinPrice + (safeMaxPrice - safeMinPrice) * fraction;
                const y = yPos(price);
                return `
                    <line x1="${marginLeft}" y1="${y.toFixed(2)}" x2="${width - marginRight}" y2="${y.toFixed(2)}" stroke="#e2e8f0" stroke-width="1" />
                    <text x="10" y="${(y + 4).toFixed(2)}" fill="#64748b" font-size="11">${formatNumber(price)}</text>
                `;
            }).join("");

        const tickDates = buildTickDates(minDate, maxDate, displayedActualPoints, finalStage?.points || projectedPoints);
        const dateLabels =
            tickDates.map(date => `
                <text x="${xPos(date).toFixed(2)}" y="${height - 14}" text-anchor="middle" fill="#64748b" font-size="11">
                    ${formatShortDate(date)}
                </text>
            `).join("");

        const stageButtons =
            `
                <button
                    type="button"
                    class="heuristic-stage-button heuristic-stage-button-till-now ${selectedStageIndex === -1 ? "active" : ""}"
                    data-stage-index="-1"
                >
                    ...Till now
                </button>
            ` +
            (intermediateStages.length > 0
                ? intermediateStages.map((stage, index) => `
                    <button
                        type="button"
                        class="heuristic-stage-button ${index === selectedStageIndex ? "active" : ""}"
                        data-stage-index="${index}"
                    >
                        ${escapeHtml(stage.label)}
                    </button>
                `).join("")
                : '<div class="heuristic-stage-empty">No intermediate heuristic stages available.</div>');

        container.innerHTML = `
            <div class="chart-layout">
                <div class="chart-plot-area">
                    <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Turning point chart for ${symbol}">
                        <rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff" />
                        <line x1="${marginLeft}" y1="${marginTop}" x2="${marginLeft}" y2="${height - marginBottom}" stroke="#94a3b8" stroke-width="1.5" />
                        <line x1="${marginLeft}" y1="${height - marginBottom}" x2="${width - marginRight}" y2="${height - marginBottom}" stroke="#94a3b8" stroke-width="1.5" />
                        ${priceLabels}
                        <polyline fill="none" stroke="#2563eb" stroke-width="3" points="${actualPolyline}" />
                        ${intermediatePolyline ? `<polyline fill="none" stroke="#111827" stroke-width="2" stroke-dasharray="4 5" stroke-opacity="0.85" points="${intermediatePolyline}" />` : ""}
                        ${finalPolyline ? `<polyline fill="none" stroke="#16a34a" stroke-width="3" stroke-dasharray="8 6" points="${finalPolyline}" />` : ""}
                        ${actualMarkers}
                        ${projectedMarkers}
                        ${dateLabels}
                    </svg>
                    <div
                        class="chart-tooltip"
                        id="chartTooltip"
                        style="position:absolute; left:-9999px; top:-9999px; display:inline-block; visibility:hidden; width:auto; min-width:0; padding:4px 7px; background:#111827; color:#ffffff; border-radius:3px; border:1px solid #374151; box-shadow:0 6px 16px rgba(15, 23, 42, 0.24); font-size:16px; line-height:1.2; white-space:nowrap; pointer-events:none; z-index:5;"
                    ></div>
                </div>
                <div class="heuristic-stage-panel">
                    <div class="heuristic-stage-heading">Heuristic Stages</div>
                    <div class="heuristic-stage-note">Final heuristic stays visible in green.</div>
                    ${finalStage ? `
                        <div class="heuristic-stage-final-label">
                            Final: ${escapeHtml(finalStageLabel)}
                        </div>
                    ` : ""}
                    <div class="heuristic-stage-buttons">
                        ${stageButtons}
                    </div>
                </div>
            </div>
        `;

        container.querySelectorAll(".heuristic-stage-button").forEach(button => {
            button.addEventListener("click", () => {
                selectedStageIndex = Number(button.dataset.stageIndex);
                renderChartFrame();
            });
        });

        attachChartTooltips(container);
    }

    renderChartFrame();
}

function normalizeHeuristicStages(stages, fallbackProjectedPoints) {

    const normalized =
        (Array.isArray(stages) ? stages : [])
            .map((stage, index) => {
                const points =
                    (stage.points || [])
                        .map(point => toChartPoint(point, true))
                        .filter(Boolean);

                if (!points.length) {
                    return null;
                }

                return {
                    label: stage.label || `Stage ${index + 1}`,
                    points,
                };
            })
            .filter(Boolean);

    if (normalized.length > 0) {
        return normalized;
    }

    if (!Array.isArray(fallbackProjectedPoints) || fallbackProjectedPoints.length === 0) {
        return [];
    }

    return [
        {
            label: "Final",
            points: fallbackProjectedPoints,
        },
    ];
}

function limitChartPointsToLastYear(points) {

    if (!Array.isArray(points) || points.length < 2) {
        return points;
    }

    const latestDate =
        points[points.length - 1].date;
    const oneYearAgo =
        new Date(latestDate);
    oneYearAgo.setFullYear(oneYearAgo.getFullYear() - 1);

    const startIndex =
        points.findIndex(point => point.date >= oneYearAgo);

    if (startIndex <= 0) {
        return points;
    }

    return points.slice(startIndex);
}

function buildTickDates(minDate, maxDate, actualPoints, projectedPoints) {

    const points =
        [...actualPoints, ...projectedPoints];

    if (points.length <= 4) {
        return points.map(point => point.date);
    }

    const candidates = [
        points[0].date,
        points[Math.floor(points.length / 3)].date,
        points[Math.floor((points.length * 2) / 3)].date,
        points[points.length - 1].date
    ];

    const seen = new Set();
    return candidates.filter(date => {
        const key = date.toISOString();
        if (seen.has(key)) {
            return false;
        }
        seen.add(key);
        return true;
    });
}

function toChartPoint(point, projected) {

    const date =
        new Date(point.date);
    const price =
        Number(point.price);

    if (Number.isNaN(date.getTime()) || !Number.isFinite(price)) {
        return null;
    }

    return {
        type: point.type || (projected ? "Projected" : "Latest"),
        date,
        price,
        projected,
        swingPct: projected
            ? Number(point.projected_swing_pct)
            : Number(point.swing_pct)
    };
}

function buildTooltip(point) {

    const typeLabel =
        point.projected ? `${point.type} (Heuristic)` : point.type;
    const swingText =
        Number.isFinite(point.swingPct)
            ? formatPercent(point.swingPct)
            : "N/A";

    return [
        typeLabel,
        formatFullDate(point.date),
        `Price: ${formatNumber(point.price)}`,
        `Swing: ${swingText}`
    ].join("\n");
}

function attachChartTooltips(container) {

    const tooltip =
        container.querySelector("#chartTooltip");

    if (!tooltip) {
        return;
    }

    const points =
        container.querySelectorAll(".chart-point");

    points.forEach(point => {
        point.addEventListener("mouseenter", event => {
            updateTooltipContent(tooltip, event.currentTarget);
            tooltip.style.visibility = "visible";
            positionTooltip(container, tooltip, event);
        });

        point.addEventListener("mousemove", event => {
            updateTooltipContent(tooltip, event.currentTarget);
            positionTooltip(container, tooltip, event);
        });

        point.addEventListener("mouseleave", () => {
            tooltip.style.visibility = "hidden";
            tooltip.style.left = "-9999px";
            tooltip.style.top = "-9999px";
        });
    });
}

function updateTooltipContent(tooltip, pointElement) {
    tooltip.innerHTML = `
        <div>${escapeHtml(pointElement.dataset.date || "")}</div>
        <div>${escapeHtml(pointElement.dataset.price || "")} (${escapeHtml(pointElement.dataset.swing || "N/A")})</div>
    `;
}

function positionTooltip(container, tooltip, event) {

    const containerRect =
        container.getBoundingClientRect();
    const tooltipPadding = 12;
    const offsetX = 14;
    const offsetY = 14;

    let left =
        event.clientX - containerRect.left + offsetX;
    let top =
        event.clientY - containerRect.top - tooltip.offsetHeight - offsetY;

    if (left + tooltip.offsetWidth + tooltipPadding > containerRect.width) {
        left =
            containerRect.width - tooltip.offsetWidth - tooltipPadding;
    }

    if (left < tooltipPadding) {
        left = tooltipPadding;
    }

    if (top < tooltipPadding) {
        top =
            event.clientY - containerRect.top + offsetY;
    }

    const maxTop =
        containerRect.height - tooltip.offsetHeight - tooltipPadding;

    if (top > maxTop) {
        top = Math.max(tooltipPadding, maxTop);
    }

    tooltip.style.left = `${left}px`;
    tooltip.style.top = `${top}px`;
}

function formatNumber(value) {

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
        return "N/A";
    }

    return numericValue.toFixed(2);
}

function formatInteger(value) {

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
        return "N/A";
    }

    return Math.round(numericValue).toString();
}

function formatPercent(value) {

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
        return "N/A";
    }

    return `${numericValue.toFixed(2)}%`;
}

function formatSwingText(value) {

    const numericValue = Number(value);
    if (!Number.isFinite(numericValue)) {
        return "N/A";
    }

    return `${numericValue.toFixed(2)}%`;
}

function formatShortDate(date) {

    const month =
        String(date.getMonth() + 1).padStart(2, "0");
    const day =
        String(date.getDate()).padStart(2, "0");

    return `${day}-${month}`;
}

function formatFullDate(date) {

    const day =
        String(date.getDate()).padStart(2, "0");
    const monthNames = [
        "Jan",
        "Feb",
        "Mar",
        "Apr",
        "May",
        "Jun",
        "Jul",
        "Aug",
        "Sep",
        "Oct",
        "Nov",
        "Dec"
    ];
    const month =
        monthNames[date.getMonth()];
    const year =
        date.getFullYear();

    return `${day}-${month}-${year}`;
}

function escapeAttribute(value) {

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("\"", "&quot;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
}

function escapeHtml(value) {

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;");
}

loadAnalysis();
