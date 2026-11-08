const fs = require("node:fs");

async function main() {
    const create = require(process.argv[2]);
    const engine = await create();
    const requests = JSON.parse(fs.readFileSync(0, "utf8"));
    process.stdout.write(JSON.stringify(requests.map(input => JSON.parse(engine.runJson(JSON.stringify(input))))));
}

main().catch(error => {
    console.error(error.message);
    process.exitCode = 1;
});
