import { chromium } from "playwright-core";
import { lightpanda } from "@lightpanda/browser";

const targetUrl = process.argv[2];

if (!targetUrl) {
  console.error("Missing URL argument for Lightpanda fetch runner.");
  process.exit(1);
}

const port = Number(process.env.LIGHTPANDA_PORT || 9222);
const host = "127.0.0.1";
let proc;
let browser;

try {
  proc = await lightpanda.serve({ host, port });
  browser = await chromium.connectOverCDP(`http://${host}:${port}`);
  const page = await browser.newPage();
  await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 15000 });
  await page.waitForTimeout(1200);
  const html = await page.content();
  process.stdout.write(html);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Lightpanda runner failed: ${message}`);
  process.exitCode = 1;
} finally {
  if (browser) {
    await browser.close().catch(() => {});
  }
  if (proc) {
    proc.stdout?.destroy();
    proc.stderr?.destroy();
    proc.kill();
  }
}
