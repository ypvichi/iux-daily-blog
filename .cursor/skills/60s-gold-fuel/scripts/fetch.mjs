/**
 * 合并 60s /v2/gold-price 与 /v2/fuel-price 为技能约定 JSON。
 * Usage: node fetch.mjs [--region 省或直辖市名]
 */
const base = "https://60s.viki.moe";

function parseArgs() {
  const out = { region: null };
  const argv = process.argv.slice(2);
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === "--region" && argv[i + 1]) {
      out.region = argv[i + 1];
      i++;
    }
  }
  return out;
}

async function main() {
  const { region } = parseArgs();
  const goldRes = await fetch(`${base}/v2/gold-price`);
  const goldJson = await goldRes.json();

  const fuelUrl = new URL(`${base}/v2/fuel-price`);
  if (region) fuelUrl.searchParams.set("region", region);
  const fuelRes = await fetch(fuelUrl);
  const fuelJson = await fuelRes.json();

  if (goldJson.code !== 200 || !goldJson.data?.metals) {
    console.error("gold-price error:", goldJson);
    process.exit(1);
  }
  if (fuelJson.code !== 200 || !fuelJson.data?.items) {
    console.error("fuel-price error:", fuelJson);
    process.exit(1);
  }

  const metals = goldJson.data.metals;
  const spot =
    metals.find((m) => m.name === "今日金价") ||
    metals.find((m) => m.name === "黄金价格");
  if (!spot) {
    console.error("No 今日金价/黄金价格 in metals");
    process.exit(1);
  }
  const 金价 = `${spot.today_price} ${spot.unit}`.replace(/\s+/g, " ").trim();

  const 油价 = {};
  for (const row of fuelJson.data.items) {
    油价[row.name] = row.price;
  }

  const out = { 金价, 油价 };
  process.stdout.write(JSON.stringify(out, null, 2) + "\n");
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
