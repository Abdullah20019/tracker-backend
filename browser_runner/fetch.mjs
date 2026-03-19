import puppeteer from "puppeteer-core";

const targetUrl = process.argv[2];
const executablePath = process.argv[3];

if (!targetUrl || !executablePath) {
  console.error("Missing URL or browser executable path for Chromium runner.");
  process.exit(1);
}

let browser;

try {
  browser = await puppeteer.launch({
    executablePath,
    headless: true,
    pipe: true,
    args: [
      "--disable-gpu",
      "--no-sandbox",
      "--disable-dev-shm-usage",
      "--disable-background-networking",
      "--disable-background-timer-throttling",
      "--blink-settings=imagesEnabled=false",
      "--disable-extensions",
      "--disable-renderer-backgrounding",
      "--disable-sync",
      "--disable-logging",
      "--log-level=3",
      "--disable-features=CalculateNativeWinOcclusion"
    ]
  });

  const page = await browser.newPage();
  await page.setRequestInterception(true);
  page.on("request", (request) => {
    const resourceType = request.resourceType();
    if (["image", "media", "font", "stylesheet"].includes(resourceType)) {
      void request.abort();
      return;
    }
    void request.continue();
  });

  await page.goto(targetUrl, { waitUntil: "domcontentloaded", timeout: 10000 });
  await page.waitForFunction(
    () => {
      const text = document.body?.innerText || "";
      return text.includes("Shipment Booking Details") || text.includes("Shipment Track Summary");
    },
    { timeout: 5000 }
  ).catch(() => {});
  const html = await page.content();
  process.stdout.write(html);
} catch (error) {
  const message = error instanceof Error ? error.message : String(error);
  console.error(`Chromium runner failed: ${message}`);
  process.exitCode = 1;
} finally {
  if (browser) {
    await browser.close().catch(() => {});
  }
}
