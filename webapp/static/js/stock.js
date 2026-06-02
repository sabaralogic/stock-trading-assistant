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
                ${data.summary.rsi}
            </p>
        `;

    const insights =
        document.getElementById("insights");

    insights.innerHTML = "";

    data.insights.forEach(i => {

        insights.innerHTML +=
            `<li>${i}</li>`;
    });

    const tbody =
        document.querySelector(
            "#turningPoints tbody"
        );

    tbody.innerHTML = "";

    data.turning_points.forEach(tp => {

        tbody.innerHTML += `
        <tr>
            <td>${tp.type}</td>
            <td>${tp.date}</td>
            <td>${tp.price}</td>
            <td>${tp.swing_pct}</td>
        </tr>
        `;
    });
}

loadAnalysis();
