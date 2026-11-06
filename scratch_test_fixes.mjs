import { spawn } from "node:child_process";

async function runTests() {
  const edge = spawn("C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe", [
    "--headless=new",
    "--remote-debugging-port=9222",
    "--window-size=1440,900",
    "about:blank",
  ]);

  try {
    let target = null;
    for (let i = 0; i < 20; i++) {
      await new Promise((r) => setTimeout(r, 300));
      try {
        const res = await fetch("http://localhost:9222/json");
        const list = await res.json();
        if (list && list.length > 0) {
          target = list[0];
          break;
        }
      } catch (e) {}
    }

    if (!target) {
      console.error("Could not find Edge target");
      return;
    }

    const ws = new WebSocket(target.webSocketDebuggerUrl);
    let id = 1;
    const callbacks = new Map();

    const consoleLogs = [];
    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data);
      if (msg.method === "Runtime.consoleAPICalled") {
        consoleLogs.push(msg.params);
      }
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
    await send("Runtime.enable");

    // ==========================================
    // TEST 1: 20x Mount / Unmount on /lab/3d
    // ==========================================
    console.log("Navigating to http://localhost:3000/lab/3d...");
    await send("Page.navigate", { url: "http://localhost:3000/lab/3d" });
    await new Promise((r) => setTimeout(r, 3000));

    console.log("Executing 20 mount/unmount cycles on /lab/3d...");
    const cycleResult = await send("Runtime.evaluate", {
      expression: `(async () => {
        const logs = [];
        const warnLogs = [];
        const originalWarn = console.warn;
        console.warn = (...args) => {
          warnLogs.push(args.join(' '));
          originalWarn.apply(console, args);
        };

        for (let i = 1; i <= 20; i++) {
          // Unmount
          const btns = Array.from(document.querySelectorAll('button'));
          const unmountBtn = btns.find(b => b.innerText.includes('Unmount 3D Scene'));
          if (unmountBtn) unmountBtn.click();
          await new Promise(r => setTimeout(r, 120));

          // Remount
          const remountBtns = Array.from(document.querySelectorAll('button'));
          const remountBtn = remountBtns.find(b => b.innerText.includes('Remount Scene') || b.innerText.includes('Mount 3D Scene'));
          if (remountBtn) remountBtn.click();
          await new Promise(r => setTimeout(r, 150));
        }

        const canvasCount = document.querySelectorAll('canvas').length;
        const tiles = Array.from(document.querySelectorAll('.glass-surface')).map(el => el.innerText);

        return {
          cycleCount: 20,
          canvasCount,
          warnLogs,
          tiles: tiles.slice(0, 5)
        };
      })()`,
      awaitPromise: true,
      returnByValue: true,
    });

    console.log("20x Mount/Unmount Result:", JSON.stringify(cycleResult.result?.value, null, 2));

    // Check for any console warnings captured over protocol
    const webglWarnings = consoleLogs.filter(log =>
      JSON.stringify(log).toLowerCase().includes("webgl") ||
      JSON.stringify(log).toLowerCase().includes("context")
    );
    console.log("Navigating to http://localhost:3000 to capture hero fixes...");
    await send("Page.navigate", { url: "http://localhost:3000" });
    await new Promise((r) => setTimeout(r, 2500));
    const shot = await send("Page.captureScreenshot", { format: "png" });
    const fs = await import("node:fs");
    fs.writeFileSync("e:/projects/Raphael/screenshot_hero_step5_fixes.png", Buffer.from(shot.result.data, "base64"));
    console.log("Captured e:/projects/Raphael/screenshot_hero_step5_fixes.png");

    ws.close();
  } finally {
    edge.kill();
  }
}

runTests().catch(console.error);
