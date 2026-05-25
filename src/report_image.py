# src/report_image.py

from pathlib import Path
import html


def generate_html_report(top_stocks: list[dict]) -> str:

    stock_cards = []

    for i, r in enumerate(top_stocks[:25], start=1):

        signal = r["signal"]
        score = r["score"]

        rsi = round(r["rsi"], 2) if r["rsi"] is not None else "N/A"

        reasons_html = "".join(
            f"<li>{html.escape(reason)}</li>"
            for reason in r["reasons"]
        )

        signal_color = {
            "BUY": "#16a34a",
            "SELL": "#dc2626",
            "HOLD": "#ca8a04",
        }.get(signal, "#6b7280")

        stock_cards.append(
            f"""
            <div class="card">
                <div class="header">
                    <div class="rank">#{i}</div>

                    <div class="stock-section">
                        <div class="stock">{html.escape(r['stock'])}</div>

                        <div class="badges">
                            <span class="signal"
                                  style="background:{signal_color}">
                                {signal}
                            </span>

                            <span class="score">
                                Score: {score}
                            </span>

                            <span class="rsi">
                                RSI: {rsi}
                            </span>
                        </div>
                    </div>
                </div>

                <div class="reasons">
                    <ul>
                        {reasons_html}
                    </ul>
                </div>
            </div>
            """
        )

    html_content = f"""
    <!DOCTYPE html>
    <html>

    <head>
        <meta charset="UTF-8">

        <style>

            body {{
                background: #0f172a;
                color: white;
                font-family: Arial, sans-serif;
                padding: 30px;
            }}

            h1 {{
                text-align: center;
                margin-bottom: 30px;
                color: #38bdf8;
            }}

            .container {{
                display: grid;
                grid-template-columns: repeat(5, 1fr);
                gap: 16px;
            }}

            .card {{
                min-height: 320px;
                background: #1e293b;
                border-radius: 12px;
                padding: 14px;
                box-shadow: 0 4px 12px rgba(0,0,0,0.3);
            }}

            .header {{
                display: flex;
                align-items: center;
                gap: 16px;
            }}

            .rank {{
                width: 50px;
                height: 50px;
                border-radius: 50%;
                background: #334155;
                display: flex;
                align-items: center;
                justify-content: center;
                font-size: 20px;
                font-weight: bold;
            }}

            .stock-section {{
                flex: 1;
            }}

            .stock {{
                font-size: 18px;
                font-weight: bold;
                margin-bottom: 10px;
            }}

            .badges {{
                display: flex;
                gap: 10px;
                flex-wrap: wrap;
            }}

            .signal,
            .score,
            .rsi {{
                padding: 6px 12px;
                border-radius: 999px;
                font-size: 14px;
                font-weight: bold;
            }}

            .score {{
                background: #2563eb;
            }}

            .rsi {{
                background: #7c3aed;
            }}

            .reasons {{
                margin-top: 16px;
            }}

            .reasons ul {{
                margin: 0;
                padding-left: 20px;
            }}

            .reasons li {{
                margin-bottom: 6px;
                line-height: 1.5;
                font-size: 12px;
            }}

        </style>
    </head>

    <body>

        <h1>🔥 Top Opportunities</h1>

        <div class="container">
            {''.join(stock_cards)}
        </div>

    </body>

    </html>
    """

    return html_content


def save_html_report(top_stocks: list[dict]) -> Path:

    html_content = generate_html_report(top_stocks)

    output_path = Path("top_opportunities.html")

    output_path.write_text(html_content, encoding="utf-8")

    return output_path