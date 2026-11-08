// Run against a locally served build with Node 22+ and a Chromium executable.
const { spawn } = require("node:child_process");
const fs = require("node:fs/promises");
const os = require("node:os");
const path = require("node:path");

const [browser, pageUrl] = process.argv.slice(2);
if (!browser || !pageUrl || !["127.0.0.1", "localhost"].includes(new URL(pageUrl).hostname)) {
    console.error("Usage: node browser_check.cjs CHROME http://127.0.0.1:8000/index.html");
    process.exit(2);
}

async function until(callback, timeout = 20000) {
    const end = Date.now() + timeout;
    while (Date.now() < end) {
        try {
            const value = await callback();
            if (value) return value;
        } catch (error) {
            if (Date.now() >= end - 100) throw error;
        }
        await new Promise(resolve => setTimeout(resolve, 100));
    }
    throw new Error("Browser condition timed out");
}

async function main() {
    const dir = await fs.mkdtemp(path.join(os.tmpdir(), "pms-rule-demo-"));
    const proc = spawn(browser, [
        "--headless=new", "--disable-gpu", "--no-first-run", "--no-default-browser-check",
        "--disable-background-networking", "--disable-component-update", "--no-proxy-server",
        "--remote-debugging-port=0", "--user-data-dir=" + dir, "about:blank",
    ], { windowsHide: true, stdio: "ignore" });
    const closed = new Promise(resolve => proc.once("close", resolve));
    let socket;
    try {
        const port = await until(async () => (await fs.readFile(path.join(dir, "DevToolsActivePort"), "utf8")).split("\n")[0]);
        const tabs = await (await fetch("http://127.0.0.1:" + port + "/json/list")).json();
        socket = new WebSocket(tabs.find(t => t.type === "page").webSocketDebuggerUrl);
        await new Promise((resolve, reject) => {
            socket.addEventListener("open", resolve, { once: true });
            socket.addEventListener("error", reject, { once: true });
        });
        let next = 0;
        const pending = new Map();
        const requests = [];
        const errors = [];
        socket.addEventListener("message", ({ data }) => {
            const message = JSON.parse(data);
            if (message.id) {
                const call = pending.get(message.id);
                pending.delete(message.id);
                if (message.error) call.reject(Error(message.error.message));
                else call.resolve(message.result);
            }
            if (message.method === "Network.requestWillBeSent") requests.push(message.params.request.url);
            if (message.method === "Runtime.exceptionThrown") errors.push(message.params.exceptionDetails.text);
        });
        function command(method, params = {}) {
            return new Promise((resolve, reject) => {
                const id = ++next;
                pending.set(id, { resolve, reject });
                socket.send(JSON.stringify({ id, method, params }));
            });
        }
        async function evaluate(expression) {
            const answer = await command("Runtime.evaluate", { expression, returnByValue: true, awaitPromise: true });
            if (answer.exceptionDetails) throw new Error(answer.exceptionDetails.text);
            return answer.result.value;
        }
        const ready = () => evaluate("document.querySelector('#status')?.textContent.includes('오프라인 준비 완료') && Boolean(navigator.serviceWorker.controller)");
        await command("Network.enable");
        await command("Runtime.enable");
        await command("Page.enable");
        await command("Page.navigate", { url: pageUrl });
        await until(ready);
        const before = await evaluate("document.querySelector('#rows').innerText");
        if (!before.includes("EX-KR-HOLIDAYS")) throw new Error("Missing KR results");
        await command("Network.emulateNetworkConditions", {
            offline: true, latency: 0, downloadThroughput: 0, uploadThroughput: 0,
        });
        await command("Page.reload");
        await until(ready);
        if (await evaluate("navigator.onLine")) throw new Error("Browser did not go offline");
        if ((await evaluate("document.querySelector('#rows').innerText")) !== before) throw new Error("Reload changed results");
        await new Promise(resolve => setTimeout(resolve, 250));
        const atRun = requests.length;
        const after = await evaluate(`(() => {
            const market = document.querySelector('#market');
            market.value = 'US';
            market.dispatchEvent(new Event('change'));
            const proposed = document.querySelector('#proposed');
            proposed.value = '2';
            proposed.dispatchEvent(new Event('change'));
            document.querySelector('#run').click();
            return document.querySelector('#rows').innerText;
        })()`);
        await new Promise(resolve => setTimeout(resolve, 250));
        if (!after.includes("EX-US-HOLIDAYS") || !after.includes("EX-US-3")) throw new Error("Offline inputs did not update the result");
        const external = requests.filter(url => /^https?:/.test(url) && new URL(url).origin !== new URL(pageUrl).origin);
        if (requests.length !== atRun || external.length || errors.length) {
            throw new Error(JSON.stringify({ comparisonRequests: requests.slice(atRun), external, errors }));
        }
        console.log("Chromium: WASM ran after offline reload, market and version changed, 0 comparison requests, 0 external requests.");
    } finally {
        socket?.close();
        proc.kill();
        await closed;
        const resolved = path.resolve(dir);
        if (path.dirname(resolved) === path.resolve(os.tmpdir()) && /^pms-rule-demo-[A-Za-z0-9]+$/.test(path.basename(resolved))) {
            await fs.rm(resolved, { recursive: true, force: true, maxRetries: 5, retryDelay: 300 });
        }
    }
}

main().catch(error => {
    console.error(error.message);
    process.exitCode = 1;
});
