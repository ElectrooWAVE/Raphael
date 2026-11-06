import { spawn } from "node:child_process";
import fs from "node:fs";

async function run() {
  const edge = spawn("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", [
    "--headless=new",
    "--remote-debugging-port=9225",
    "--window-size=1440,900",
    "--enable-webgl",
    "--ignore-gpu-blocklist",
    "about:blank",
  ]);

  try {
    let target = null;
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 200));
      try {
        const res = await fetch("http://localhost:9225/json");
        const list = await res.json();
        if (list && list.length > 0) {
          target = list[0];
          break;
        }
      } catch (e) {}
    }

    if (!target) {
      console.error("Target not found");
      return;
    }

    const ws = new WebSocket(target.webSocketDebuggerUrl);
    let id = 1;
    const callbacks = new Map();
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.id && callbacks.has(msg.id)) {
        const cb = callbacks.get(msg.id);
        callbacks.delete(msg.id);
        cb(msg);
      }
    };

    const send = (method, params = {}) =>
      new Promise((resolve) => {
        const reqId = id++;
        callbacks.set(reqId, resolve);
        ws.send(JSON.stringify({ id: reqId, method, params }));
      });

    await new Promise((r) => (ws.onopen = r));
    await send("Page.enable");
    console.log("Navigating to http://localhost:3000...");
    await send("Page.navigate", { url: "http://localhost:3000" });
    await new Promise((r) => setTimeout(r, 3000));

    const shot = await send("Page.captureScreenshot", { format: "png" });
    fs.writeFileSync("e:/projects/Raphael/screenshot_hero_step5_fixes.png", Buffer.from(shot.result.data, "base64"));
    console.log("Screenshot saved successfully.");
    ws.close();
  } catch (err) {
    console.error(err);
  } finally {
    edge.kill();
  }
}

run().then(() => process.exit(0)).catch(() => process.exit(1));
