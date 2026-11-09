//! Oracle-assisted diagnosis only; never reports a submission optimum.
use ddd::{
    parser,
    problem::{DelayCostType, DelayMeasurementType},
    solvers::{ddd::maxsat_ladder_sc::{self as sc, BoundDiagnostic},
        util::{cadical_deadline::DeadlineReached, counting_solver, minisat_deadline}, SolverError},
};
use serde_json::{json, Map, Value};
use std::{fs::{self, File}, io::Write, path::PathBuf, time::Instant};
use structopt::StructOpt;

#[derive(StructOpt)]
struct Opt {
    #[structopt(long, parse(from_os_str))]
    instance: PathBuf,
    #[structopt(long)]
    objective: String,
    #[structopt(long, possible_values=&["control", "oracle-ub", "at-opt", "below-opt"])]
    mode: String,
    #[structopt(long)]
    optimum: i32,
    #[structopt(long, default_value="300")]
    timeout: f64,
    #[structopt(long, parse(from_os_str))]
    oracle_schedule: Option<PathBuf>,
    #[structopt(long, parse(from_os_str))]
    output: PathBuf,
}

fn main() -> Result<(), Box<dyn std::error::Error>> {
    let opt = Opt::from_args();
    if opt.optimum < 0 || !opt.timeout.is_finite() || opt.timeout <= 0.0 {
        return Err("invalid optimum or timeout".into());
    }
    let objective = match opt.objective.as_str() {
        "finsteps123" => DelayCostType::FiniteSteps123,
        "infsteps180" => DelayCostType::InfiniteSteps180,
        "cont" => DelayCostType::Continuous,
        _ => return Err("unsupported objective".into()),
    };
    if (opt.mode == "oracle-ub") != opt.oracle_schedule.is_some() {
        return Err("only oracle-ub requires --oracle-schedule".into());
    }
    let schedule: Option<Vec<Vec<i32>>> = opt.oracle_schedule.as_ref()
        .map(|p| -> Result<_, Box<dyn std::error::Error>> {
            Ok(serde_json::from_slice(&fs::read(p)?)?)
        }).transpose()?;
    let target = match opt.mode.as_str() {
        "at-opt" => Some(opt.optimum),
        "below-opt" => Some(opt.optimum.checked_sub(1).filter(|v| *v >= 0)
            .ok_or("below-opt needs a positive optimum")?),
        _ => None,
    };
    let (named, _) = parser::read_txt_file(opt.instance.to_str().ok_or("invalid path")?,
        DelayMeasurementType::FinalStationArrival, false, None, |_| {});
    let diagnostic = match opt.mode.as_str() {
        "control" => BoundDiagnostic::Control,
        "oracle-ub" => BoundDiagnostic::VerifiedUpper(schedule.as_ref().unwrap()),
        _ => BoundDiagnostic::Decision(target.unwrap()),
    };
    let mut settings = sc::MaxSatDddLadderScSettings::default();
    settings.resource_orders = true;
    settings.order_transitivity = true;
    settings.core_minimize_checks = 4;
    settings.core_minimize_conflicts = 100;
    settings.core_exhaust_checks = 4;
    let mut stats = Map::<String, Value>::new();
    stats.insert("schema".into(), "bound-diagnostic-v1".into());
    stats.insert("mode".into(), opt.mode.clone().into());
    stats.insert("objective".into(), opt.objective.clone().into());
    stats.insert("oracle_optimum".into(), opt.optimum.into());
    stats.insert("submission_eligible".into(), false.into());
    stats.insert("maxsat_backend".into(), "minisat".into());
    if let Some(parent) = opt.output.parent() { fs::create_dir_all(parent)?; }
    let mut trace = File::create(opt.output.with_extension("trace.jsonl"))?;
    counting_solver::reset_counts();
    let started = Instant::now();
    let solver = minisat_deadline::Solver::new(opt.timeout);
    let signature = solver.signature().to_string();
    let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
        sc::solve_bound_diagnostic(|| {
            let mut env = grb::Env::new("").unwrap();
            env.set(grb::parameter::IntParam::OutputFlag, 0).unwrap();
            env
        }, counting_solver::CountingSolver::new(solver), &named.problem,
        opt.timeout, objective, settings, diagnostic, |key, value| {
            let checkpoint = key == "diagnostic_checkpoint";
            stats.insert(key, value);
            if checkpoint {
                let (variables, clauses) = counting_solver::get_counts();
                writeln!(trace, "{}", json!({"seconds": stats["diagnostic_checkpoint"],
                    "lb": stats["diagnostic_lb"], "ub": stats["diagnostic_ub"],
                    "iterations": stats["diagnostic_iterations"],
                    "variables": variables, "clauses": clauses})).unwrap();
                trace.flush().unwrap();
            }
        })
    }));
    let status = match result {
        Ok(Ok((solution, _))) => {
            let cost = named.problem.verify_solution(&solution, objective)
                .ok_or("returned schedule is invalid")?;
            if target.map(|t| cost > t).unwrap_or(cost != opt.optimum) {
                return Err("result disagrees with the independently verified MIP optimum".into());
            }
            stats.insert("cost".into(), cost.into());
            stats.insert("solution".into(), json!(solution));
            if target.is_some() { "sat" } else { "optimal" }
        }
        Ok(Err(SolverError::NoSolution)) if target.is_some()
            && stats.get("diagnostic_outcome").and_then(Value::as_str) == Some("unsat") => "unsat",
        Ok(Err(SolverError::Timeout)) => "timeout",
        Err(payload) if payload.is::<DeadlineReached>() => "timeout",
        Ok(Err(error)) => { stats.insert("error".into(), format!("{:?}", error).into()); "error" }
        Err(payload) => {
            let message = payload.downcast_ref::<String>().map(String::as_str)
                .or_else(|| payload.downcast_ref::<&str>().copied()).unwrap_or("unrecognized panic");
            stats.insert("error".into(), message.into()); "panic"
        }
    };
    let native = minisat_deadline::native_stats();
    let (variables, clauses) = counting_solver::get_counts();
    stats.insert("status".into(), status.into());
    stats.insert("seconds".into(), started.elapsed().as_secs_f64().into());
    stats.insert("timeout_seconds".into(), opt.timeout.into());
    stats.insert("maxsat_backend_signature".into(), signature.into());
    stats.insert("native_sat_calls".into(), native.calls.into());
    stats.insert("native_sat_seconds".into(), native.sat_time.as_secs_f64().into());
    stats.insert("variables".into(), variables.into());
    stats.insert("clauses".into(), clauses.into());
    let temporary = opt.output.with_extension("json.tmp");
    fs::write(&temporary, serde_json::to_vec_pretty(&stats)?)?;
    fs::rename(temporary, &opt.output)?;
    println!("diagnostic mode={} status={} seconds={:.3}", opt.mode, status,
        started.elapsed().as_secs_f64());
    if status == "error" || status == "panic" { std::process::exit(1); }
    Ok(())
}
