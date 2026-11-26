import { Config } from "@remotion/cli/config";
import { existsSync } from "node:fs";

// Remotion's bundled chrome-headless-shell (v158) never fires requestAnimationFrame on
// this Mac, so renders hang at "Waiting for root component". The system Chrome works.
const systemChrome = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
if (existsSync(systemChrome)) {
  Config.setBrowserExecutable(systemChrome);
}
Config.setChromeMode("headless-shell");
Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(92);
