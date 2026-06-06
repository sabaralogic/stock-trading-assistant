let stocksData = [];
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

    renderTopBuyStocks(stocksData);
    initializeSorting();
    sortStocks(currentSort.key, currentSort.direction);
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

function renderTopBuyStocks(stocks) {

    const buyStocks =
        [...stocks]
            .filter(stock => String(stock.signal).toUpperCase() === "BUY")
            .sort((left, right) => {
                const expectedXirrDiff =
                    (Number(right.expected_xirr) || 0) - (Number(left.expected_xirr) || 0);
                if (expectedXirrDiff !== 0) {
                    return expectedXirrDiff;
                }

                const scoreDiff = (Number(right.score) || 0) - (Number(left.score) || 0);
                if (scoreDiff !== 0) {
                    return scoreDiff;
                }

                const rsiDiff = (Number(right.rsi) || 0) - (Number(left.rsi) || 0);
                if (rsiDiff !== 0) {
                    return rsiDiff;
                }

                return (Number(right.close) || 0) - (Number(left.close) || 0);
            })
            .slice(0, 25);

    renderStocksTable("#buyStocksTable tbody", buyStocks);
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

loadStocks();
