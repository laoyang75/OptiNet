import asyncio
from playwright.async_api import async_playwright
import os

pages_to_capture = [
    ("http://127.0.0.1:47122/flow/overview", "flow_overview.png"),
    ("http://127.0.0.1:47122/runs", "runs.png"),
    ("http://127.0.0.1:47122/objects", "objects.png"),
    ("http://127.0.0.1:47122/objects/cell/460_01_4G_16822_48472661", "object_detail.png"),
    ("http://127.0.0.1:47122/observation", "observation.png"),
    ("http://127.0.0.1:47122/anomalies", "anomalies.png"),
    ("http://127.0.0.1:47122/baseline", "baseline.png"),
    ("http://127.0.0.1:47122/compare", "compare.png"),
    ("http://127.0.0.1:47122/profiles/lac", "profile_lac.png"),
    ("http://127.0.0.1:47122/profiles/bs", "profile_bs.png"),
    ("http://127.0.0.1:47122/profiles/cell", "profile_cell.png"),
    ("http://127.0.0.1:47122/initialization", "initialization.png"),
    ("http://127.0.0.1:47122/governance", "governance.png")
]

async def main():
    os.makedirs("rebuild3/docs/screenshots", exist_ok=True)
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # 1440x1080 viewport
        page = await browser.new_page(viewport={"width": 1440, "height": 1080})
        
        for url, filename in pages_to_capture:
            print(f"Navigating to {url} ...")
            try:
                response = await page.goto(url, wait_until="networkidle", timeout=10000)
                if response and response.status == 404 and filename == "object_detail.png":
                    print("got 404 for object detail, trying object list to find a link...")
                    await page.goto("http://127.0.0.1:47122/objects", wait_until="networkidle")
                    await asyncio.sleep(2)
                    # Try clicking first object link
                    elements = await page.query_selector_all("a[href^='/objects/']")
                    if elements:
                        href = await elements[0].get_attribute("href")
                        print(f"Found alternative object detail url: {href}")
                        if not href.startswith("http"):
                            href = "http://127.0.0.1:47122" + href
                        await page.goto(href, wait_until="networkidle")
                
                await asyncio.sleep(3)
                filepath = os.path.join("rebuild3/docs/screenshots", filename)
                await page.screenshot(path=filepath, full_page=True)
                print(f"Saved {filepath}")
            except Exception as e:
                print(f"Failed to capture {url}: {e}")
                
        await browser.close()

asyncio.run(main())
