import { existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const require = createRequire(path.join(here, "package.json"));
const { selectComposition, renderFrames, openBrowser } = require("@remotion/renderer");

const serveUrl = process.argv[2] || "/tmp/remotion_bundle";
const openerOut = process.argv[3] || "/tmp/remotion_opener";
const checkOut = process.argv[4] || "/tmp/remotion_check";
const concurrency = Number(process.argv[5] || "4");

const systemChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browserExecutable = existsSync(systemChrome) ? systemChrome : null;

const browser = await openBrowser("chrome", {
  browserExecutable,
  chromeMode: "chrome-for-testing",
  logLevel: "error",
});

async function renderComp(compId, outDir) {
  if (existsSync(outDir)) rmSync(outDir, { recursive: true, force: true });
  mkdirSync(outDir, { recursive: true });

  const composition = await selectComposition({
    serveUrl,
    id: compId,
    puppeteerInstance: browser,
    logLevel: "error",
  });
  console.log(
    `Rendering ${composition.id} (${composition.width}x${composition.height} @ ${composition.fps}fps, ${composition.durationInFrames} frames)...`,
  );

  await renderFrames({
    composition,
    serveUrl,
    outputDir: outDir,
    imageFormat: "png",
    puppeteerInstance: browser,
    concurrency,
    logLevel: "error",
    onStart: () => {},
    onFrameUpdate: (done) => {
      if (done % 60 === 0 || done === composition.durationInFrames) {
        console.log(`  ${compId}: ${done}/${composition.durationInFrames}`);
      }
    },
  });
}

const only = process.argv[6] || "both";
try {
  if (only === "both" || only === "opener") await renderComp("ReadmeOpener", openerOut);
  if (only === "both" || only === "check") await renderComp("ReadmeCheck", checkOut);
} finally {
  await browser.close({ silent: true });
}
console.log("Done rendering lossless PNG sequences.");
