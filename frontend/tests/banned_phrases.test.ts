import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";

function getFiles(dir: string, fileList: string[] = []): string[] {
  const files = fs.readdirSync(dir);
  for (const file of files) {
    const filePath = path.join(dir, file);
    const stat = fs.statSync(filePath);
    if (stat.isDirectory()) {
      if (file !== "node_modules" && file !== ".next" && file !== "dist") {
        getFiles(filePath, fileList);
      }
    } else if (file.endsWith(".tsx") || file.endsWith(".ts")) {
      fileList.push(filePath);
    }
  }
  return fileList;
}

test("no banned phrases in frontend page and component code", () => {
  const appDir = path.resolve(import.meta.dirname, "../app");
  const compDir = path.resolve(import.meta.dirname, "../components");
  const files = [...getFiles(appDir), ...getFiles(compDir)];

  const bannedPatterns: { name: string; pattern: RegExp }[] = [
    { name: "multi-echelon", pattern: /multi-echelon/i },
    { name: "real-time", pattern: /real-time/i },
    { name: "industrial materials", pattern: /industrial materials/i },
    { name: "holiday surge", pattern: /holiday surge/i },
    { name: "calibrated on actual retail", pattern: /calibrated on actual retail/i },
    { name: "LightGBM near lead-time", pattern: /(?:LightGBM[\s\S]{0,35}lead[\s-]?time|lead[\s-]?time[\s\S]{0,35}LightGBM)/i },
  ];

  const violations: string[] = [];

  for (const file of files) {
    const content = fs.readFileSync(file, "utf8");
    for (const { name, pattern } of bannedPatterns) {
      if (pattern.test(content)) {
        violations.push(`${path.relative(process.cwd(), file)} matched banned rule: ${name}`);
      }
    }
  }

  assert.deepEqual(violations, [], `Found banned phrases in frontend code:\n${violations.join("\n")}`);
});
