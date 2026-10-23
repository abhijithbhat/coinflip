import fs from "node:fs";
import path from "node:path";

async function main() {
  const rootDir = process.cwd();
  const assetsDir = path.join(rootDir, "assets");
  const publicAssetsDir = path.join(rootDir, ".output", "public", "assets");
  const publicDir = path.join(rootDir, ".output", "public");

  // 1. Ensure assets/ exists and is clean
  if (fs.existsSync(assetsDir)) {
    fs.rmSync(assetsDir, { recursive: true, force: true });
  }
  fs.mkdirSync(assetsDir, { recursive: true });

  // 2. Copy newly built assets from .output/public/assets/ to assets/
  if (fs.existsSync(publicAssetsDir)) {
    const files = fs.readdirSync(publicAssetsDir);
    for (const file of files) {
      fs.copyFileSync(path.join(publicAssetsDir, file), path.join(assetsDir, file));
    }
  }

  // 3. Prerender / from SSR bundle
  const ssrPath = "./.output/server/_ssr/ssr.mjs";
  const ssrMod = await import(ssrPath);
  const res = await ssrMod.default.fetch(new Request("http://localhost/"));
  if (!res.ok) {
    throw new Error(`Prerender failed with status: ${res.status}`);
  }
  const html = await res.text();

  // 4. Write prerendered index.html
  fs.writeFileSync(path.join(rootDir, "index.html"), html, "utf8");
  if (fs.existsSync(publicDir)) {
    fs.writeFileSync(path.join(publicDir, "index.html"), html, "utf8");
  }

  // 5. Clean up any build generator artifacts
  const wranglerDir = path.join(rootDir, ".wrangler");
  if (fs.existsSync(wranglerDir)) {
    fs.rmSync(wranglerDir, { recursive: true, force: true });
  }

  console.log("Prerender & asset sync completed successfully.");
}

main().catch((err) => {
  console.error("Prerender error:", err);
  process.exit(1);
});
