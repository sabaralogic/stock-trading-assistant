let stocksData = [];
let sectorSummaryData = [];
let currentSort = {
    key: "score",
    direction: "desc"
};

async function loadStocks() {

    let response = await fetch("/static/data/scan/default.json");

    if (!response.ok) {
        response = await fetch("/api/scan", {
            method: "POST",
            headers: {
                "Content-Type": "application/json"
            }
        });
    }

    const data = await response.json();

    stocksData = (data.evaluations || []).map((stock, index) => ({
        ...stock,
        rank: index + 1
    }));
    sectorSummaryData = data.sector_summary || [];

    renderSectorOverview(stocksData, sectorSummaryData);
    initializeSorting();
    sortStocks(currentSort.key, currentSort.direction);
}

function renderSectorOverview(stocks, sectorSummary) {

    const meta =
        document.getElementById("sectorOverviewMeta");
    const sectorLists =
        document.getElementById("sectorLists");

    if (!meta || !sectorLists) {
        return;
    }

    const sectorNames =
        Array.from(
            new Set(
                stocks
                    .map(stock => String(stock.sector || "Unknown"))
                    .filter(Boolean)
            )
        );

    meta.textContent =
        `${sectorNames.length} sectors across ${stocks.length} analyzed stocks`;

    const summaryBySector = new Map(
        (sectorSummary || []).map(item => [String(item.sector || "Unknown"), item])
    );

    const sectorAccentPalette = [
        "#dbeafe",
        "#fef9c3",
        "#ede9fe",
        "#dcfce7",
        "#fed7aa",
        "#ffedd5",
        "#cffafe",
        "#fde68a",
        "#fbcfe8",
        "#c7d2fe",
        "#bbf7d0",
        "#fecaca"
    ];

    const groupedStocks =
        stocks.reduce((groups, stock) => {
            const sector =
                String(stock.sector || "Unknown");
            if (!groups[sector]) {
                groups[sector] = [];
            }
            groups[sector].push(stock);
            return groups;
        }, {});

    const panelData = Object.entries(groupedStocks)
            .sort((left, right) => right[1].length - left[1].length)
            .map(([sector, rows], index) => {
                const orderedRows =
                    [...rows].sort((left, right) => {
                        const signalDiff =
                            signalPriority(right.signal) - signalPriority(left.signal);
                        if (signalDiff !== 0) {
                            return signalDiff;
                        }

                        const scoreDiff =
                            (Number(right.score) || 0) - (Number(left.score) || 0);
                        if (scoreDiff !== 0) {
                            return scoreDiff;
                        }

                        return (Number(right.expected_xirr) || 0) - (Number(left.expected_xirr) || 0);
                    });

                const sectorSummary = summaryBySector.get(sector);
                const buyCountText =
                    sectorSummary && Number.isFinite(sectorSummary.buy_count)
                        ? `${sectorSummary.buy_count} BUY`
                        : "N/A BUY";
                const avgScoreText =
                    sectorSummary && Number.isFinite(sectorSummary.avg_score)
                        ? `${sectorSummary.avg_score.toFixed(1)} avg score`
                        : "N/A avg score";
                const bestReturnText =
                    sectorSummary && Number.isFinite(sectorSummary.best_return)
                        ? `${sectorSummary.best_return.toFixed(2)}%`
                        : "N/A";
                const bestStock = sectorSummary?.best_stock || "N/A";
                const bestSummaryText = `Best: <a href="/stock.html?symbol=${encodeURIComponent(bestStock)}">${escapeHtml(bestStock)}</a> ${escapeHtml(bestReturnText)}`;
                const accentColor = sectorAccentPalette[index % sectorAccentPalette.length];

                return {
                    sector,
                    rows: orderedRows,
                    sectorSummary,
                    accentColor,
                    html: `
                        <article class="sector-panel" data-sector="${escapeHtml(sector)}" data-sector-index="${index}" style="--sector-accent:${accentColor};">
                            <button type="button" class="sector-panel-summary">
                                <div class="sector-panel-heading">
                                    <div class="sector-panel-title-row">
                                        <span class="sector-panel-title">${escapeHtml(sector)}</span>
                                        <span class="sector-panel-count">${rows.length} stocks</span>
                                    </div>
                                    <div class="sector-panel-meta">
                                        <span>${escapeHtml(buyCountText)}</span>
                                        <span>• ${escapeHtml(avgScoreText)}</span>
                                        <span>• ${bestSummaryText}</span>
                                    </div>
                                </div>
                            </button>
                            <div class="sector-panel-body">
                                ${orderedRows.map(stock => {
                                    const returnText =
                                        Number.isFinite(stock.expected_xirr)
                                            ? `${stock.expected_xirr.toFixed(2)}%`
                                            : "N/A";
                                    return `
                                        <a class="sector-stock-row" href="/stock.html?symbol=${encodeURIComponent(stock.stock)}">
                                            <span class="sector-stock-symbol">${escapeHtml(stock.stock)}</span>
                                            <span class="sector-stock-signal ${String(stock.signal).toLowerCase()}">${escapeHtml(stock.signal)}</span>
                                            <span class="sector-stock-score">Score ${escapeHtml(String(stock.score))}</span>
                                            <span class="sector-stock-return">${escapeHtml(returnText)}</span>
                                        </a>
                                    `;
                                }).join("")}
                            </div>
                        </article>
                    `
                };
            });

    sectorLists.innerHTML = panelData.map(item => item.html).join("");

    sectorLists.querySelectorAll(".sector-panel-summary").forEach((summaryButton, index) => {
        const panel = summaryButton.closest(".sector-panel");

        summaryButton.addEventListener("click", () => {
            const isOpen = panel.classList.contains("opened");
            closeAllSectorPanels(sectorLists);
            if (!isOpen) {
                panel.classList.add("opened");
            }
        });
    });
}

function closeAllSectorPanels(container) {
    container.querySelectorAll(".sector-panel.opened").forEach(panel => {
        panel.classList.remove("opened");
    });
}

function initializeSorting() {

    const headers =
        document.querySelectorAll("#stocksTable thead th[data-sort-key]");

    headers.forEach(header => {

        header.addEventListener("click", () => {

            const key = header.dataset.sortKey;
            const defaultDirection =
                key === "score" ||
                key === "rsi" ||
                key === "close" ||
                key === "expected_entry_price" ||
                key === "expected_peak_price" ||
                key === "expected_peak_days" ||
                key === "expected_profit_price" ||
                key === "expected_xirr"
                    ? "desc"
                    : "asc";
            const nextDirection =
                currentSort.key === key
                    ? (currentSort.direction === "asc" ? "desc" : "asc")
                    : defaultDirection;

            sortStocks(key, nextDirection);
        });
    });
}

function sortStocks(sortKey, direction) {

    currentSort = {
        key: sortKey,
        direction: direction
    };

    const sortedStocks = [...stocksData].sort((left, right) => {

        const leftValue = getSortValue(left, sortKey);
        const rightValue = getSortValue(right, sortKey);

        if (typeof leftValue === "number" && typeof rightValue === "number") {
            return direction === "asc"
                ? leftValue - rightValue
                : rightValue - leftValue;
        }

        const comparison =
            String(leftValue).localeCompare(
                String(rightValue),
                undefined,
                { numeric: true, sensitivity: "base" }
            );

        return direction === "asc"
            ? comparison
            : -comparison;
    });

    updateHeaderIndicators();
    renderStocksTable("#stocksTable tbody", sortedStocks);
}

function getSortValue(stock, sortKey) {

    if (sortKey === "rsi") {
        return Number.isFinite(stock.rsi)
            ? stock.rsi
            : Number.NEGATIVE_INFINITY;
    }

    if (sortKey === "expected_entry_date" || sortKey === "expected_peak_date") {
        const timestamp =
            Date.parse(stock[sortKey]);
        return Number.isFinite(timestamp)
            ? timestamp
            : Number.NEGATIVE_INFINITY;
    }

    if (
        sortKey === "score" ||
        sortKey === "rank" ||
        sortKey === "close" ||
        sortKey === "expected_entry_price" ||
        sortKey === "expected_peak_price" ||
        sortKey === "expected_peak_days" ||
        sortKey === "expected_profit_price" ||
        sortKey === "expected_xirr"
    ) {
        return Number(stock[sortKey]) || 0;
    }

    return stock[sortKey] ?? "";
}

function updateHeaderIndicators() {

    const headers =
        document.querySelectorAll("#stocksTable thead th[data-sort-key]");

    headers.forEach(header => {

        const baseLabel =
            header.dataset.sortKey === "rank"
                ? "S.No"
                : header.dataset.sortKey === "stock"
                    ? "Stock"
                    : header.dataset.sortKey === "signal"
                        ? "Signal"
                        : header.dataset.sortKey === "score"
                            ? "Score"
                            : header.dataset.sortKey === "rsi"
                                ? "RSI"
                                : header.dataset.sortKey === "close"
                                    ? "Last Close"
                                    : header.dataset.sortKey === "expected_entry_date"
                                        ? "Buy Date"
                                    : header.dataset.sortKey === "expected_entry_price"
                                        ? "Buy Price"
                                        : header.dataset.sortKey === "expected_peak_date"
                                            ? "Sell Date"
                                        : header.dataset.sortKey === "expected_peak_price"
                                            ? "Sell Price"
                                            : header.dataset.sortKey === "expected_peak_days"
                                                ? "Diff Days"
                                                : header.dataset.sortKey === "expected_profit_price"
                                                    ? "Diff Price"
                                                    : "Expected Annualized Return<br>with heuristics";

        if (header.dataset.sortKey === currentSort.key) {
            const arrow =
                currentSort.direction === "asc" ? "↑" : "↓";
            if (header.dataset.sortKey === "expected_xirr") {
                header.innerHTML = `Expected Annualized Return<br>with heuristics ${arrow}`;
            } else {
                header.textContent = `${baseLabel} ${arrow}`;
            }
            header.classList.add("sorted");
            return;
        }

        if (header.dataset.sortKey === "expected_xirr") {
            header.innerHTML = baseLabel;
        } else {
            header.textContent = baseLabel;
        }
        header.classList.remove("sorted");
    });
}

function renderStocksTable(tbodySelector, stocks) {

    const tbody =
        document.querySelector(tbodySelector);

    if (!tbody) {
        return;
    }

    tbody.innerHTML = "";

    stocks.forEach((stock, index) => {

        const rsiText =
            Number.isFinite(stock.rsi)
                ? stock.rsi.toFixed(2)
                : "N/A";
        const closeText =
            Number.isFinite(stock.close)
                ? stock.close.toFixed(2)
                : "N/A";
        const expectedBuyDateText =
            formatCompactTableDate(stock.expected_entry_date);
        const expectedBuyText =
            Number.isFinite(stock.expected_entry_price)
                ? stock.expected_entry_price.toFixed(2)
                : "N/A";
        const expectedSellDateText =
            formatCompactTableDate(stock.expected_peak_date);
        const expectedSellText =
            Number.isFinite(stock.expected_peak_price)
                ? stock.expected_peak_price.toFixed(2)
                : "N/A";
        const expectedDiffDaysText =
            Number.isFinite(stock.expected_peak_days)
                ? String(Math.round(stock.expected_peak_days))
                : "N/A";
        const expectedDiffPriceValue =
            Number.isFinite(stock.expected_peak_price) && Number.isFinite(stock.expected_entry_price)
                ? (stock.expected_peak_price - stock.expected_entry_price)
                : Number.NaN;
        const expectedDiffPriceText =
            Number.isFinite(expectedDiffPriceValue)
                ? expectedDiffPriceValue.toFixed(2)
                : "N/A";
        const expectedXirrText =
            Number.isFinite(stock.expected_xirr)
                ? `${stock.expected_xirr.toFixed(2)}%`
                : "N/A";

        tbody.innerHTML += `
        <tr>
            <td>${index + 1}</td>

            <td>
                <a href="/stock.html?symbol=${encodeURIComponent(stock.stock)}">
                    ${stock.stock}
                </a>
            </td>

            <td class="${String(stock.signal).toLowerCase()}">
                ${stock.signal}
            </td>

            <td>${stock.score}</td>

            <td>${rsiText}</td>

            <td>${closeText}</td>

            <td>${expectedBuyDateText}</td>

            <td>${expectedBuyText}</td>

            <td>${expectedSellDateText}</td>

            <td>${expectedSellText}</td>

            <td>${expectedDiffDaysText}</td>

            <td>${expectedDiffPriceText}</td>

            <td>${expectedXirrText}</td>
        </tr>
        `;
    });
}

function formatCompactTableDate(value) {

    const timestamp =
        Date.parse(value);
    if (!Number.isFinite(timestamp)) {
        return "N/A";
    }

    const date =
        new Date(timestamp);
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
        String(date.getFullYear()).slice(-2);

    return `${day}-${month}-${year}`;
}

function analyzeStock() {

    const symbol =
        document.getElementById("symbolInput").value.trim();

    if (!symbol)
        return;

    window.location.href =
        `/stock.html?symbol=${encodeURIComponent(symbol)}`;
}

function signalPriority(signal) {

    const normalized =
        String(signal || "").toUpperCase();

    if (normalized === "BUY") {
        return 3;
    }
    if (normalized === "HOLD") {
        return 2;
    }
    if (normalized === "SELL") {
        return 1;
    }
    return 0;
}

function escapeHtml(value) {

    return String(value)
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll("\"", "&quot;");
}

loadStocks();
