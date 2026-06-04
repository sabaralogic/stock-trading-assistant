const urlParams =
    new URLSearchParams(window.location.search);

const symbol =
    urlParams.get("symbol") ||
    window.location.pathname.split("/").pop();

async function loadAnalysis() {

    let response =
        await fetch(
            `/static/data/analyze/${encodeURIComponent(symbol)}.json`
        );

    if (!response.ok) {
        response =
            await fetch("/api/analyze", {

                method: "POST",

                headers: {
                    "Content-Type": "application/json"
                },

                body: JSON.stringify({
                    symbol: symbol
                })
            });
    }

    const data =
        await response.json();

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

    renderTurningPointChart(
        data.all_turning_points || [],
        data.predicted_turning_points || []
    );

    const insights =
        document.getElementById("insights");

    insights.innerHTML = "";

    data.insights.forEach(i => {

        insights.innerHTML +=
            `<li>${i}</li>`;
    });
}

function renderTurningPointChart(turningPoints, predictedTurningPoints) {

    const container =
        document.getElementById("turningPointChart");
    container.style.position = "relative";

    const actualPoints =
        (turningPoints || [])
            .map(point => toChartPoint(point, false))
            .filter(Boolean);

    const projectedPoints =
        (predictedTurningPoints || [])
            .map(point => toChartPoint(point, true))
            .filter(Boolean);

    if (actualPoints.length < 2) {
        container.innerHTML =
            '<div class="chart-empty">Not enough turning points to draw a chart.</div>';
        return;
    }

    const allPoints =
        [...actualPoints, ...projectedPoints];

    const width = 980;
    const height = 420;
    const marginLeft = 68;
    const marginRight = 28;
    const marginTop = 20;
    const marginBottom = 48;
    const innerWidth = width - marginLeft - marginRight;
    const innerHeight = height - marginTop - marginBottom;

    const minPrice =
        Math.min(...allPoints.map(point => point.price));
    const maxPrice =
        Math.max(...allPoints.map(point => point.price));
    const safeMinPrice =
        minPrice === maxPrice ? minPrice - 1 : minPrice;
    const safeMaxPrice =
        minPrice === maxPrice ? maxPrice + 1 : maxPrice;

    const minDate =
        actualPoints[0].date;
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
        actualPoints
            .map(point => `${xPos(point.date).toFixed(2)},${yPos(point.price).toFixed(2)}`)
            .join(" ");

    const projectedPolyline =
        projectedPoints.length > 0
            ? [actualPoints[actualPoints.length - 1], ...projectedPoints]
                .map(point => `${xPos(point.date).toFixed(2)},${yPos(point.price).toFixed(2)}`)
                .join(" ")
            : "";

    const actualMarkers =
        actualPoints.map(point => {
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

    const projectedMarkers =
        projectedPoints.map(point => `
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

    const tickDates = buildTickDates(minDate, maxDate, actualPoints, projectedPoints);
    const dateLabels =
        tickDates.map(date => `
            <text x="${xPos(date).toFixed(2)}" y="${height - 14}" text-anchor="middle" fill="#64748b" font-size="11">
                ${formatShortDate(date)}
            </text>
        `).join("");

    container.innerHTML = `
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Turning point chart for ${symbol}">
            <rect x="0" y="0" width="${width}" height="${height}" fill="#ffffff" />
            <line x1="${marginLeft}" y1="${marginTop}" x2="${marginLeft}" y2="${height - marginBottom}" stroke="#94a3b8" stroke-width="1.5" />
            <line x1="${marginLeft}" y1="${height - marginBottom}" x2="${width - marginRight}" y2="${height - marginBottom}" stroke="#94a3b8" stroke-width="1.5" />
            ${priceLabels}
            <polyline fill="none" stroke="#2563eb" stroke-width="3" points="${actualPolyline}" />
            ${projectedPolyline ? `<polyline fill="none" stroke="#16a34a" stroke-width="3" stroke-dasharray="8 6" points="${projectedPolyline}" />` : ""}
            ${actualMarkers}
            ${projectedMarkers}
            ${dateLabels}
        </svg>
        <div
            class="chart-tooltip"
            id="chartTooltip"
            style="position:absolute; left:-9999px; top:-9999px; display:inline-block; visibility:hidden; width:auto; min-width:0; padding:4px 7px; background:#111827; color:#ffffff; border-radius:3px; border:1px solid #374151; box-shadow:0 6px 16px rgba(15, 23, 42, 0.24); font-size:16px; line-height:1.2; white-space:nowrap; pointer-events:none; z-index:5;"
        ></div>
    `;

    attachChartTooltips(container);
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
        type: point.type || (projected ? "Projected" : ""),
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
