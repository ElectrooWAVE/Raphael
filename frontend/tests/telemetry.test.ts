import test from "node:test";
import assert from "node:assert";
import fs from "node:fs";
import path from "node:path";

test("Telemetry Artifacts Parity: leaderboard & breakdown consistency", () => {
  const lbPath = path.resolve(process.cwd(), "..", "artifacts", "metrics", "demand_leaderboard.json");
  assert.ok(fs.existsSync(lbPath), "demand_leaderboard.json must exist");
  const lb = JSON.parse(fs.readFileSync(lbPath, "utf-8"));

  assert.strictEqual(lb.total_pairs, 75);
  assert.strictEqual(lb.model_selection_breakdown.weekday_mean_8w, 75);

  // Assert disqualification note matches reality
  assert.ok(lb.disqualification_notes["LightGBM Global"].includes("36.92%"));
  assert.ok(lb.disqualification_notes["LightGBM Global"].includes("Weekday Mean 8W (30.52%)"));
});

test("Telemetry Artifacts Parity: lead-time & interval metrics", () => {
  const ltPath = path.resolve(process.cwd(), "..", "artifacts", "metrics", "lead_time_model_evaluation.json");
  assert.ok(fs.existsSync(ltPath), "lead_time_model_evaluation.json must exist");
  const lt = JSON.parse(fs.readFileSync(ltPath, "utf-8"));

  assert.strictEqual(lt.overall.rf_mae, 0.76);
  assert.strictEqual(lt.overall.rf_rmse, 0.993);
  assert.strictEqual(lt.overall.rf_r2, 0.785);
  assert.strictEqual(lt.overall.tree_std_coverage_95, 0.7686);
  assert.strictEqual(lt.overall.calibrated_coverage_95, 0.9586);

  const ivPath = path.resolve(process.cwd(), "..", "artifacts", "metrics", "interval_evaluation.json");
  assert.ok(fs.existsSync(ivPath), "interval_evaluation.json must exist");
  const iv = JSON.parse(fs.readFileSync(ivPath, "utf-8"));

  assert.strictEqual(iv.fleet_coverage.overall_80, 0.8124);
  assert.strictEqual(iv.fleet_coverage.overall_95, 0.943);
});
