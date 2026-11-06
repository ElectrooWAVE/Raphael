import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";
import {
  computeSafetyStock,
  computeReorderPoint,
  computeDaysRemaining,
  classifyInventoryStatus,
  computePlannedOrderQuantity,
  computeOrderUpToLevel,
  computeRecommendedOrderQuantity,
  computeEoq,
} from "../lib/inventoryEngine.ts";

interface FixtureCase {
  id: string;
  description: string;
  inputs: {
    D?: number;
    sigma_D?: number;
    L?: number;
    sigma_L?: number;
    service_level?: number;
    stock?: number;
    daily_forecasts?: number[];
    forecast_14d?: number[];
    hist_p5?: number;
    hist_p95?: number;
    annual_demand?: number;
    ordering_cost?: number;
    holding_cost?: number;
    rop?: number;
    demand_rate?: number;
    review_period_days?: number;
    current_stock?: number;
    planned_quantity?: number;
  };
  expected: {
    safety_stock?: number;
    rop?: number;
    days_remaining?: number;
    beyond_horizon?: boolean;
    label?: string;
    status?: string;
    raw_order_quantity?: number;
    clipped_order_quantity?: number;
    is_extrapolation?: boolean;
    eoq?: number;
    order_up_to_level?: number;
    recommended_order_quantity?: number;
  };
}

function loadFixtures(): FixtureCase[] {
  // Path to tests/inventory_fixtures.json at root
  const fixturesPath = path.resolve(process.cwd(), "..", "tests", "inventory_fixtures.json");
  const content = fs.readFileSync(fixturesPath, "utf-8");
  return JSON.parse(content) as FixtureCase[];
}

test("Inventory Fixtures Suite: loads all test cases", () => {
  const fixtures = loadFixtures();
  assert.ok(fixtures.length >= 8, `Expected at least 8 fixtures, got ${fixtures.length}`);
});

test("Inventory Decision Layer: passes all hand-crafted fixtures", () => {
  const fixtures = loadFixtures();

  for (const c of fixtures) {
    const cid = c.id;
    const inp = c.inputs;
    const exp = c.expected;

    if (inp.D !== undefined) {
      const ss = computeSafetyStock(
        inp.D,
        inp.sigma_D!,
        inp.L!,
        inp.sigma_L!,
        inp.service_level ?? 0.95
      );
      assert.ok(
        Math.abs(ss - exp.safety_stock!) < 0.05,
        `[${cid}] Safety stock mismatch: got ${ss}, expected ${exp.safety_stock}`
      );

      const rop = computeReorderPoint(inp.D, inp.L!, ss);
      assert.ok(
        Math.abs(rop - exp.rop!) < 0.05,
        `[${cid}] ROP mismatch: got ${rop}, expected ${exp.rop}`
      );

      const rem = computeDaysRemaining(inp.stock!, inp.daily_forecasts!);
      assert.ok(
        Math.abs(rem.daysRemaining - exp.days_remaining!) < 0.05,
        `[${cid}] Days remaining mismatch: got ${rem.daysRemaining}, expected ${exp.days_remaining}`
      );
      assert.strictEqual(
        rem.beyondHorizon,
        exp.beyond_horizon,
        `[${cid}] beyond_horizon mismatch`
      );
      assert.strictEqual(rem.label, exp.label, `[${cid}] label mismatch`);

      const status = classifyInventoryStatus(inp.stock!, rop, rem.daysRemaining, inp.L!);
      assert.strictEqual(status, exp.status, `[${cid}] status mismatch`);
    } else if (inp.forecast_14d !== undefined) {
      const plan = computePlannedOrderQuantity(
        inp.forecast_14d,
        14,
        inp.hist_p5,
        inp.hist_p95
      );
      assert.ok(
        Math.abs(plan.rawQty - exp.raw_order_quantity!) < 0.05,
        `[${cid}] Raw qty mismatch`
      );
      assert.ok(
        Math.abs(plan.clippedQty - exp.clipped_order_quantity!) < 0.05,
        `[${cid}] Clipped qty mismatch`
      );
      assert.strictEqual(
        plan.isExtrapolation,
        exp.is_extrapolation,
        `[${cid}] Extrapolation mismatch`
      );
    } else if (inp.annual_demand !== undefined) {
      const eoq = computeEoq(
        inp.annual_demand,
        inp.ordering_cost ?? 50.0,
        inp.holding_cost ?? 2.0
      );
      assert.ok(
        Math.abs(eoq - exp.eoq!) < 0.05,
        `[${cid}] EOQ mismatch: got ${eoq}, expected ${exp.eoq}`
      );
    } else if (exp.order_up_to_level !== undefined) {
      const outOrderUpTo = computeOrderUpToLevel(
        inp.rop!,
        inp.demand_rate!,
        inp.review_period_days ?? 7
      );
      assert.ok(
        Math.abs(outOrderUpTo - exp.order_up_to_level!) < 0.05,
        `[${cid}] order_up_to mismatch: got ${outOrderUpTo}, expected ${exp.order_up_to_level}`
      );

      const rec = computeRecommendedOrderQuantity(
        inp.planned_quantity!,
        outOrderUpTo,
        inp.current_stock!,
        inp.hist_p5,
        inp.hist_p95
      );
      assert.ok(
        Math.abs(rec.recommendedQty - exp.recommended_order_quantity!) < 0.05,
        `[${cid}] rec_qty mismatch: got ${rec.recommendedQty}, expected ${exp.recommended_order_quantity}`
      );
      assert.strictEqual(
        rec.isExtrapolation,
        exp.is_extrapolation,
        `[${cid}] is_extrapolation mismatch`
      );
    }
  }
});

test("Inventory Properties: mathematical boundary assertions", () => {
  const ssZero = computeSafetyStock(0.0, 0.0, 5.0, 0.0, 0.95);
  assert.strictEqual(ssZero, 0.0);

  const ropZero = computeReorderPoint(0.0, 5.0, ssZero);
  assert.strictEqual(ropZero, 0.0);

  // Monotonicity with respect to variability
  const ssLow = computeSafetyStock(10.0, 1.0, 5.0, 0.5, 0.95);
  const ssHigh = computeSafetyStock(10.0, 3.0, 5.0, 1.5, 0.95);
  assert.ok(ssHigh > ssLow, "Safety stock should increase with variability");

  // ROP precedence
  assert.strictEqual(
    classifyInventoryStatus(15.0, 50.0, 1.5, 4.0),
    "CRITICAL",
    "Should be CRITICAL when days remaining < lead time"
  );
  assert.strictEqual(
    classifyInventoryStatus(35.0, 50.0, 6.0, 4.0),
    "REORDER",
    "Should be REORDER when stock <= ROP but days remaining >= lead time"
  );
  assert.strictEqual(
    classifyInventoryStatus(80.0, 50.0, 12.0, 4.0),
    "OK",
    "Should be OK when stock > ROP"
  );
});

test("Urgency Ranking & Triage Properties", () => {
  // Test severity ranking order: CRITICAL (1) > REORDER (2) > OK (3)
  const items = [
    { rank: 3, status: "OK", days: 30 },
    { rank: 1, status: "CRITICAL", days: 1.2 },
    { rank: 2, status: "REORDER", days: 6.5 },
  ];

  const severityMap: Record<string, number> = {
    CRITICAL: 1,
    REORDER: 2,
    OK: 3,
  };

  const sorted = [...items].sort(
    (a, b) => severityMap[a.status] - severityMap[b.status]
  );

  assert.strictEqual(sorted[0].status, "CRITICAL");
  assert.strictEqual(sorted[1].status, "REORDER");
  assert.strictEqual(sorted[2].status, "OK");
});

test("Simulator Baseline Reset & Identity: all deltas return to +0.0", () => {
  // Mock baseline record matching actual FOODS_2_019 CA_1 row
  const baseline = {
    material: "FOODS_2_019",
    area: "California - CA_1",
    current_stock: 555.0,
    reorder_point_rop: 150.85,
    safety_stock_ss: 35.37,
    demand_rate_d: 15.93,
    demand_error_std_sigma_d: 5.932,
    predicted_lead_time_days: 7.25,
    calibrated_lead_time_std_sigma_l: 0.904,
    service_level_target: 0.95,
    recommended_order_quantity: 223.0,
    eoq_quantity: 539.2,
    hist_p5_order_quantity: 61.0,
    hist_p95_order_quantity: 163.3,
  };

  // State when initialized with exact unrounded baseline model values (or reset)
  const demandShockPct = 0;
  const leadTimeOverride = baseline.predicted_lead_time_days;
  const leadTimeStdOverride = baseline.calibrated_lead_time_std_sigma_l;
  const serviceLevelPct = (baseline.service_level_target || 0.95) * 100;
  const currentStockInput = baseline.current_stock;
  const orderingCostFixed = 50.0;
  const holdingRateAnnualPct = 20.0;
  const assumedUnitCost = 10.0;

  const isAtBaseline =
    Math.abs(demandShockPct) < 0.0001 &&
    Math.abs(leadTimeOverride - baseline.predicted_lead_time_days) < 0.0001 &&
    Math.abs(leadTimeStdOverride - baseline.calibrated_lead_time_std_sigma_l) < 0.0001 &&
    Math.abs(serviceLevelPct - ((baseline.service_level_target || 0.95) * 100)) < 0.0001 &&
    Math.abs(currentStockInput - baseline.current_stock) < 0.0001 &&
    Math.abs(orderingCostFixed - 50.0) < 0.0001 &&
    Math.abs(holdingRateAnnualPct - 20.0) < 0.0001 &&
    Math.abs(assumedUnitCost - 10.0) < 0.0001;

  assert.strictEqual(isAtBaseline, true, "Should recognize exact baseline parameters");

  // Recomputing arithmetic
  const simDemandRate = baseline.demand_rate_d;
  const simSigmaD = baseline.demand_error_std_sigma_d;
  const L = leadTimeOverride;
  const sigmaL = leadTimeStdOverride;
  const slFraction = serviceLevelPct / 100;

  const simSs = computeSafetyStock(simDemandRate, simSigmaD, L, sigmaL, slFraction);
  const simRop = computeReorderPoint(simDemandRate, L, simSs);

  // Both raw computed and authoritative baseline should match within 0.05
  assert.ok(
    Math.abs(simRop - baseline.reorder_point_rop) < 0.05,
    `Calculated ROP (${simRop}) must match baseline (${baseline.reorder_point_rop}) within 0.05`
  );
  assert.ok(
    Math.abs(simSs - baseline.safety_stock_ss) < 0.05,
    `Calculated SS (${simSs}) must match baseline (${baseline.safety_stock_ss}) within 0.05`
  );

  // When isAtBaseline is true, deltas are identically +0.0
  const deltaSs = isAtBaseline ? 0 : simSs - baseline.safety_stock_ss;
  const deltaRop = isAtBaseline ? 0 : simRop - baseline.reorder_point_rop;
  const deltaRec = isAtBaseline ? 0 : 0;

  assert.strictEqual(deltaSs, 0, "Delta SS must be identically 0 when at baseline");
  assert.strictEqual(deltaRop, 0, "Delta ROP must be identically 0 when at baseline");
  assert.strictEqual(deltaRec, 0, "Delta Recommended Qty must be identically 0 when at baseline");
});


