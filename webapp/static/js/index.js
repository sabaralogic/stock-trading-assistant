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
                key === "score" || key === "rsi" ? "desc" : "asc";
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
    renderStocks(sortedStocks);
}

function getSortValue(stock, sortKey) {

    if (sortKey === "rsi") {
        return Number.isFinite(stock.rsi)
            ? stock.rsi
            : Number.NEGATIVE_INFINITY;
    }

    if (sortKey === "score" || sortKey === "rank") {
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
                            : "RSI";

        if (header.dataset.sortKey === currentSort.key) {
            const arrow =
                currentSort.direction === "asc" ? "↑" : "↓";
            header.textContent = `${baseLabel} ${arrow}`;
            header.classList.add("sorted");
            return;
        }

        header.textContent = baseLabel;
        header.classList.remove("sorted");
    });
}

function renderStocks(stocks) {

    const tbody =
        document.querySelector("#stocksTable tbody");

    tbody.innerHTML = "";

    stocks.forEach((stock, index) => {

        const rsiText =
            Number.isFinite(stock.rsi)
                ? stock.rsi.toFixed(2)
                : "N/A";

        tbody.innerHTML += `
        <tr>
            <td>${index + 1}</td>

            <td>
                <a href="/templates/stock.html?symbol=${encodeURIComponent(stock.stock)}">
                    ${stock.stock}
                </a>
            </td>

            <td class="${String(stock.signal).toLowerCase()}">
                ${stock.signal}
            </td>

            <td>${stock.score}</td>

            <td>${rsiText}</td>
        </tr>
        `;
    });
}

function analyzeStock() {

    const symbol =
        document.getElementById("symbolInput").value.trim();

    if (!symbol)
        return;

    window.location.href =
        `/templates/stock.html?symbol=${encodeURIComponent(symbol)}`;
}

loadStocks();
