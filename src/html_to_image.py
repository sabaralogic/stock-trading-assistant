from pathlib import Path
from playwright.sync_api import sync_playwright


def html_to_png(
    html_file: str,
    output_image: str = "top_opportunities.png"
) -> str:

    html_path = Path(html_file).resolve()

    with sync_playwright() as p:

        browser = p.chromium.launch()

        page = browser.new_page(
            viewport={
                "width": 1200,
                "height": 2000
            }
        )

        page.goto(f"file://{html_path}")

        page.screenshot(
            path=output_image,
            full_page=True
        )

        browser.close()

    return output_image