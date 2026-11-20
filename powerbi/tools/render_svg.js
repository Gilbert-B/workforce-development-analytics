// Render page-background SVGs to PNG with Playwright's Chromium.
// Usage: node render_svg.js '[{"svg": "...svg", "png": "...png"}, ...]'
const { chromium } = require('playwright');
const fs = require('fs');
(async () => {
  const jobs = JSON.parse(process.argv[2]);
  const browser = await chromium.launch();
  const page = await browser.newPage({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  for (const j of jobs) {
    await page.setContent(`<html><body style="margin:0">${fs.readFileSync(j.svg, 'utf8')}</body></html>`);
    await page.screenshot({ path: j.png, clip: { x: 0, y: 0, width: 1920, height: 1080 } });
  }
  await browser.close();
})();
