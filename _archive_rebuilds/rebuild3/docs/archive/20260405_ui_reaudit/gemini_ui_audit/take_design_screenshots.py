import asyncio
from playwright.async_api import async_playwright
import os

pages = [
    "01_flow_overview.html",
    "02_run_batch_center.html",
    "03_objects.html",
    "04_object_detail.html",
    "05_observation_workspace.html",
    "06_anomaly_workspace.html",
    "07_baseline_profile.html",
    "08_validation_compare.html",
    "09_lac_profile.html",
    "10_bs_profile.html",
    "11_cell_profile.html",
    "12_initialization.html",
    "13_data_governance.html"
]

async def main():
    save_dir = "/Users/yangcongan/cursor/WangYou_Data/rebuild3/docs/design_screenshots"
    os.makedirs(save_dir, exist_ok=True)
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={'width': 1920, 'height': 1080})
        
        for filename in pages:
            url = f"file:///Users/yangcongan/cursor/WangYou_Data/rebuild3/docs/UI_v2/pages/{filename}"
            print(f"Screenshotting {url}")
            await page.goto(url, wait_until="networkidle")
            await asyncio.sleep(1) # Extra wait for rendering
            png_name = filename.replace(".html", ".png")
            await page.screenshot(path=os.path.join(save_dir, png_name), full_page=True)
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
