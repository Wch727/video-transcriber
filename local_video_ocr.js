#!/usr/bin/env node
/*
 * Extract visible text/subtitles from a video without API keys.
 *
 * It uses Microsoft Edge/Chrome through Playwright to decode the video, samples
 * frames to PNG, then runs local OCR with tesseract.js. This does not transcribe
 * speech unless the spoken words are visible as captions/subtitles on screen.
 */

const fs = require("fs");
const os = require("os");
const path = require("path");
const { pathToFileURL } = require("url");
const { createRequire } = require("module");

const TESSERACT_LANG_MAP = {
  zh: "chi_sim",
  en: "eng",
  ja: "jpn",
  ko: "kor",
  es: "spa",
  fr: "fra",
  de: "deu",
  it: "ita",
  pt: "por",
  ru: "rus",
  ar: "ara",
  hi: "hin",
  vi: "vie",
  th: "tha",
  tr: "tur",
  nl: "nld",
  sv: "swe",
  pl: "pol",
  uk: "ukr",
  id: "ind",
  ms: "msa",
  bn: "ben",
  ur: "urd",
  fa: "fas",
  he: "heb",
  el: "ell",
  cs: "ces",
  da: "dan",
  fi: "fin",
  hu: "hun",
  ro: "ron",
  no: "nor",
  ca: "cat",
  la: "lat",
  sk: "slk",
  sl: "slv",
  hr: "hrv",
  sr: "srp",
  bg: "bul",
  lt: "lit",
  lv: "lav",
  et: "est",
  sw: "swa",
  ml: "mal",
  ta: "tam",
  te: "tel",
  ka: "kat",
  kk: "kaz",
  ne: "nep",
  am: "amh",
  my: "mya",
  km: "khm",
  lo: "lao",
  mn: "mon",
  az: "aze",
  uz: "uzb",
};

const TESSERACT_LANG_ALIASES = {
  "zh-cn": "chi_sim",
  "zh-sg": "chi_sim",
  "zh-hans": "chi_sim",
  "zh-tw": "chi_tra",
  "zh-hk": "chi_tra",
  "zh-mo": "chi_tra",
  "zh-hant": "chi_tra",
};

function mapOcrLanguagePart(part) {
  let normalized = part.toLowerCase();
  const aliasKey = normalized.replace(/_/g, "-");
  if (TESSERACT_LANG_ALIASES[aliasKey]) {
    return TESSERACT_LANG_ALIASES[aliasKey];
  }
  if (normalized.includes("_")) {
    const baseLanguage = normalized.split("_", 1)[0];
    if (TESSERACT_LANG_MAP[baseLanguage]) {
      return TESSERACT_LANG_MAP[baseLanguage];
    }
  }
  if (normalized.includes("-")) {
    normalized = normalized.split("-", 1)[0];
  }
  return TESSERACT_LANG_MAP[normalized] || normalized;
}

function mapOcrLanguage(lang) {
  return lang
    .trim()
    .split(/[+ ]+/)
    .filter(Boolean)
    .map(mapOcrLanguagePart)
    .join("+");
}

function loadPackage(packageName) {
  try {
    return require(packageName);
  } catch (_error) {
    return bundledRequire(packageName);
  }
}

function bundledRequire(packageName) {
  const nodeModules = path.join(
    os.homedir(),
    ".cache",
    "codex-runtimes",
    "codex-primary-runtime",
    "dependencies",
    "node",
    "node_modules",
    ".pnpm",
  );

  if (!fs.existsSync(nodeModules)) {
    throw new Error(`找不到 Codex Node 依赖目录: ${nodeModules}`);
  }

  const packageDir = fs
    .readdirSync(nodeModules)
    .find((name) => name === packageName || name.startsWith(`${packageName}@`));

  if (!packageDir) {
    throw new Error(`找不到 Node 包: ${packageName}`);
  }

  const packageJson = path.join(nodeModules, packageDir, "node_modules", packageName, "package.json");
  return createRequire(packageJson)(packageName);
}

function optionValue(argv, index, optionName) {
  const value = argv[index + 1];
  if (value === undefined || (value.startsWith("-") && !/^-?\d+(?:\.\d+)?$/.test(value))) {
    throw new Error(`${optionName} requires a value`);
  }
  return value;
}

function parseArgs(argv) {
  const args = {
    interval: 2,
    lang: "eng",
    out: null,
    start: 0,
    end: null,
    cropBottom: 0.42,
    fullFrame: false,
    keepFrames: false,
    minChars: 2,
  };

  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (!args.video && !arg.startsWith("-")) {
      args.video = arg;
      continue;
    }
    if (arg === "--interval") args.interval = Number(optionValue(argv, i++, arg));
    else if (arg === "--lang") args.lang = optionValue(argv, i++, arg);
    else if (arg === "-o" || arg === "--out") args.out = optionValue(argv, i++, arg);
    else if (arg === "--start") args.start = Number(optionValue(argv, i++, arg));
    else if (arg === "--end") args.end = Number(optionValue(argv, i++, arg));
    else if (arg === "--crop-bottom") args.cropBottom = Number(optionValue(argv, i++, arg));
    else if (arg === "--full-frame") args.fullFrame = true;
    else if (arg === "--keep-frames") args.keepFrames = true;
    else if (arg === "--min-chars") args.minChars = Number(optionValue(argv, i++, arg));
    else if (arg === "-h" || arg === "--help") {
      printHelp();
      process.exit(0);
    } else {
      throw new Error(`未知参数: ${arg}`);
    }
  }

  if (!args.video) throw new Error("请提供视频文件，例如: node local_video_ocr.js 4-1.mp4");
  if (!Number.isFinite(args.interval) || args.interval <= 0) throw new Error("--interval 必须大于 0");
  if (!args.lang || typeof args.lang !== "string") throw new Error("--lang 必须是有效语言代码");
  if (!Number.isFinite(args.start) || args.start < 0) throw new Error("--start 必须大于等于 0");
  if (args.end !== null && (!Number.isFinite(args.end) || args.end <= args.start)) {
    throw new Error("--end 必须大于 --start");
  }
  if (!Number.isFinite(args.cropBottom) || args.cropBottom <= 0 || args.cropBottom > 1) {
    throw new Error("--crop-bottom 必须在 0 到 1 之间");
  }
  if (!Number.isFinite(args.minChars) || args.minChars < 0) throw new Error("--min-chars 必须大于等于 0");

  args.lang = mapOcrLanguage(args.lang);
  if (!args.lang) throw new Error("--lang 不能为空");
  args.video = path.resolve(args.video);
  if (!fs.existsSync(args.video)) throw new Error(`找不到视频文件: ${args.video}`);
  if (!fs.statSync(args.video).isFile()) throw new Error(`不是视频文件: ${args.video}`);
  args.out = path.resolve(args.out || defaultOutput(args.video));
  if (fs.existsSync(args.out) && fs.statSync(args.out).isDirectory()) {
    throw new Error(`--out 必须是文件路径，不能是目录: ${args.out}`);
  }
  const outputDir = path.dirname(args.out);
  if (fs.existsSync(outputDir) && !fs.statSync(outputDir).isDirectory()) {
    throw new Error(`输出目录不是文件夹: ${outputDir}`);
  }
  fs.mkdirSync(outputDir, { recursive: true });
  return args;
}

function printHelp() {
  console.log(`用法:
  node local_video_ocr.js 视频文件 [选项]

选项:
  -o, --out 文件         输出文本文件，默认: 视频名_ocr_local.txt
  --interval 秒          每隔多少秒识别一帧，默认 2
  --lang 语言            OCR 语言，默认 eng
  --start 秒             从第几秒开始，默认 0
  --end 秒               到第几秒结束，默认视频结尾
  --crop-bottom 比例     只识别底部区域，默认 0.42，适合字幕
  --full-frame           识别整张画面
  --keep-frames          保留抽帧 PNG，便于排查
  --min-chars 数字       少于该字符数的结果丢弃，默认 2

示例:
  node local_video_ocr.js 4-1.mp4 --interval 1 -o 4-1_ocr.txt
  node local_video_ocr.js 4-1.mp4 --full-frame --interval 3
`);
}

function defaultOutput(videoPath) {
  const parsed = path.parse(videoPath);
  return path.join(parsed.dir, `${parsed.name}_ocr_local.txt`);
}

function localTempDir(parent, prefix) {
  fs.mkdirSync(parent, { recursive: true });
  return fs.mkdtempSync(path.join(parent, prefix));
}

function findBrowserExecutable() {
  const candidates = [
    "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files (x86)\\Google\\Chrome\\Application\\chrome.exe",
    "C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe",
    "C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
  ];
  return candidates.find((candidate) => fs.existsSync(candidate));
}

function normalizeText(text) {
  return text
    .split(/\r?\n/)
    .map((line) => line.replace(/\s+/g, " ").trim())
    .filter(Boolean)
    .join("\n");
}

function compactText(text) {
  return text.replace(/\s+/g, "").replace(/[|_.,，。:：;；"'“”‘’`~\-—…]/g, "");
}

function formatTime(seconds) {
  const total = Math.round(seconds);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  return [h, m, s].map((n) => String(n).padStart(2, "0")).join(":");
}

function waitWithTimeout(pagePromise, seconds, label) {
  return new Promise((resolve, reject) => {
    const timer = setTimeout(() => {
      reject(new Error(`${label} timed out after ${seconds}s`));
    }, seconds * 1000);
    pagePromise.then(
      (value) => {
        clearTimeout(timer);
        resolve(value);
      },
      (error) => {
        clearTimeout(timer);
        reject(error);
      },
    );
  });
}

function escapeHtmlAttribute(value) {
  return value.replace(/&/g, "&amp;").replace(/"/g, "&quot;");
}

async function loadVideoPage(page, videoPath, tempDir) {
  const videoUrl = pathToFileURL(videoPath).href;
  const htmlPath = path.join(tempDir, "video_ocr_page.html");
  fs.writeFileSync(htmlPath, `<!doctype html>
<html>
<body style="margin:0;background:#000">
  <video id="video" muted preload="auto" src="${escapeHtmlAttribute(videoUrl)}"></video>
  <canvas id="canvas"></canvas>
</body>
</html>`, "utf8");
  await page.goto(pathToFileURL(htmlPath).href, { waitUntil: "domcontentloaded" });

  return waitWithTimeout(
    page.evaluate(async () => {
      const video = document.getElementById("video");
      if (video.readyState < HTMLMediaElement.HAVE_METADATA || !Number.isFinite(video.duration)) {
        await new Promise((resolve, reject) => {
          const cleanup = () => {
            video.removeEventListener("loadedmetadata", onLoaded);
            video.removeEventListener("error", onError);
          };
          const onLoaded = () => {
            cleanup();
            resolve();
          };
          const onError = () => {
            cleanup();
            reject(new Error("Browser could not read this video format"));
          };
          video.addEventListener("loadedmetadata", onLoaded, { once: true });
          video.addEventListener("error", onError, { once: true });
          video.load();
        });
      }
      return {
        duration: video.duration,
        width: video.videoWidth,
        height: video.videoHeight,
      };
    }),
    20,
    "Loading video metadata",
  );
}

async function captureFrame(page, second, options) {
  return waitWithTimeout(
    page.evaluate(
      async ({ second, fullFrame, cropBottom }) => {
        const video = document.getElementById("video");
        const canvas = document.getElementById("canvas");
        const ctx = canvas.getContext("2d", { willReadFrequently: true });
        const maxTime = Math.max(0, video.duration - 0.05);
        const targetTime = Math.min(Math.max(second, 0.05), maxTime);

        if (
          Math.abs(video.currentTime - targetTime) > 0.01 ||
          video.readyState < HTMLMediaElement.HAVE_CURRENT_DATA
        ) {
          await new Promise((resolve, reject) => {
            const cleanup = () => {
              video.removeEventListener("seeked", onReady);
              video.removeEventListener("loadeddata", onReady);
              video.removeEventListener("error", onError);
            };
            const onReady = () => {
              cleanup();
              resolve();
            };
            const onError = () => {
              cleanup();
              reject(new Error(`Seeking to ${second}s failed`));
            };
            video.addEventListener("seeked", onReady, { once: true });
            video.addEventListener("loadeddata", onReady, { once: true });
            video.addEventListener("error", onError, { once: true });
            video.currentTime = targetTime;
          });
        }

        const sourceWidth = video.videoWidth;
        const sourceHeight = video.videoHeight;
        const sy = fullFrame ? 0 : Math.floor(sourceHeight * (1 - cropBottom));
        const sh = fullFrame ? sourceHeight : sourceHeight - sy;

        canvas.width = sourceWidth;
        canvas.height = sh;
        ctx.drawImage(video, 0, sy, sourceWidth, sh, 0, 0, sourceWidth, sh);
        return canvas.toDataURL("image/png").split(",")[1];
      },
      { second, fullFrame: options.fullFrame, cropBottom: options.cropBottom },
    ),
    20,
    `Capturing frame at ${second}s`,
  );
}

async function main() {
  const args = parseArgs(process.argv.slice(2));
  const browserPath = findBrowserExecutable();
  if (!browserPath) {
    throw new Error("找不到 Chrome 或 Edge，无法在本地解码视频。");
  }

  const { chromium } = loadPackage("playwright");
  const { createWorker, PSM } = loadPackage("tesseract.js");

  const tempDir = localTempDir(path.dirname(args.out), "video-ocr-");
  const cacheDir = path.join(__dirname, ".video_text_cache", "tesseract_js");
  fs.mkdirSync(cacheDir, { recursive: true });
  let browser = null;
  let worker = null;

  try {
    browser = await chromium.launch({
      executablePath: browserPath,
      headless: true,
      args: ["--allow-file-access-from-files"],
    });
    const page = await browser.newPage();
    const info = await loadVideoPage(page, args.video, tempDir);
    if (!Number.isFinite(info.duration) || info.duration <= 0) {
      throw new Error("Could not determine a positive video duration");
    }
    if (args.start >= info.duration) {
      throw new Error(`--start (${args.start}s) must be earlier than video duration (${info.duration.toFixed(2)}s)`);
    }
    const end = Math.min(args.end ?? info.duration, info.duration);
    if (end <= args.start) {
      throw new Error(`OCR range is empty: ${args.start}s to ${end.toFixed(2)}s`);
    }

    console.log(`视频: ${args.video}`);
    console.log(`时长: ${formatTime(info.duration)}，分辨率: ${info.width}x${info.height}`);
    console.log(`OCR: ${args.fullFrame ? "整帧" : `底部 ${Math.round(args.cropBottom * 100)}%`}，每 ${args.interval}s 一帧`);

    worker = await createWorker(args.lang, 1, {
      cachePath: cacheDir,
      logger: (message) => {
        if (message.status === "recognizing text") {
          process.stdout.write(`\rOCR 进度: ${Math.round((message.progress || 0) * 100)}%   `);
        }
      },
    });
    await worker.setParameters({
      tessedit_pageseg_mode: PSM.SINGLE_BLOCK,
      preserve_interword_spaces: "1",
    });

    const blocks = [];
    let lastCompact = "";
    let frameIndex = 0;
    for (let second = args.start; second <= end; second += args.interval) {
      frameIndex += 1;
      process.stdout.write(`\r抽帧: ${formatTime(second)} / ${formatTime(end)}   `);
      const base64 = await captureFrame(page, second, args);
      const framePath = path.join(tempDir, `frame_${String(frameIndex).padStart(5, "0")}.png`);
      fs.writeFileSync(framePath, Buffer.from(base64, "base64"));

      const result = await worker.recognize(framePath);
      const text = normalizeText(result.data.text || "");
      const compact = compactText(text);
      if (compact.length >= args.minChars && compact !== lastCompact) {
        blocks.push(`[${formatTime(second)}]\n${text}`);
        lastCompact = compact;
      }
    }

    fs.writeFileSync(args.out, `${blocks.join("\n\n")}\n`, "utf8");
    process.stdout.write("\n");
    console.log(`已写入: ${args.out}`);

    if (args.keepFrames) {
      console.log(`抽帧保留在: ${tempDir}`);
    }
  } finally {
    if (worker) {
      await worker.terminate().catch(() => {});
    }
    if (browser) {
      await browser.close().catch(() => {});
    }
    if (!args.keepFrames) {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  }
}

main().catch((error) => {
  console.error(`Error: ${error.message}`);
  process.exit(1);
});
