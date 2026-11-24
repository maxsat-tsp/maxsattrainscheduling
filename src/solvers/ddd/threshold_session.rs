use super::{
    bound_search::{QueryRecord, SearchInterval, ThresholdPolicy},
    maxsat_ladder_sc::{solve_threshold_session, MaxSatDddLadderScSettings},
};
use crate::{
    problem::{DelayCostType, Problem},
    solvers::{
        util::{cadical_deadline::DeadlineReached, counting_solver, minisat_deadline},
        SolverError,
    },
};
use serde::Serialize;
use serde_json::{Map, Value};
use std::{cell::RefCell, time::Instant};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Serialize)]
#[serde(rename_all = "kebab-case")]
pub enum ThresholdSession {
    Restart,
    RestartAssumptions,
    Reuse,
    ReuseOffset,
    ReuseOffsetTree,
}

impl ThresholdSession {
    pub fn parse(text: &str) -> Result<Self, String> {
        match text {
            "restart" => Ok(Self::Restart),
            "restart-assumptions" => Ok(Self::RestartAssumptions),
            "reuse" => Ok(Self::Reuse),
            "reuse-offset" => Ok(Self::ReuseOffset),
            "reuse-offset-tree" => Ok(Self::ReuseOffsetTree),
            _ => Err("unsupported threshold session".into()),
        }
    }

    pub(super) fn solver_name(self, warmup: bool) -> &'static str {
        match (self, warmup) {
            (Self::Restart, false) => "SAT-Upper-Restart",
            (Self::Restart, true) => "RC2-Warm-SAT-Upper-Restart",
            (Self::RestartAssumptions, false) => "SAT-Upper-RestartAssumptions",
            (Self::RestartAssumptions, true) => "RC2-Warm-SAT-Upper-RestartAssumptions",
            (Self::Reuse, false) => "SAT-Upper-Reuse",
            (Self::Reuse, true) => "RC2-Warm-SAT-Upper-Reuse",
            (Self::ReuseOffset, false) => "SAT-Upper-ReuseOffset",
            (Self::ReuseOffset, true) => "RC2-Warm-SAT-Upper-ReuseOffset",
            (Self::ReuseOffsetTree, false) => "SAT-Upper-ReuseOffsetTree",
            (Self::ReuseOffsetTree, true) => "RC2-Warm-SAT-Upper-ReuseOffsetTree",
        }
    }
}

struct Decision {
    target: i32,
    started: Instant,
    remaining_seconds: f64,
    native_before: minisat_deadline::NativeStats,
}

impl Decision {
    fn start(target: i32, deadline: Instant) -> Self {
        let started = Instant::now();
        Self {
            target,
            started,
            remaining_seconds: deadline.saturating_duration_since(started).as_secs_f64(),
            native_before: minisat_deadline::native_stats(),
        }
    }

    fn record(
        self,
        before: SearchInterval,
        model_generation: usize,
        outcome: &str,
        witness: Option<(i32, Vec<Vec<i32>>)>,
        mut evidence: Map<String, Value>,
    ) -> QueryRecord {
        let native = minisat_deadline::native_stats();
        let (variables, clauses) = counting_solver::get_counts();
        let (cost, solution) =
            witness.map_or((None, None), |(cost, times)| (Some(cost), Some(times)));
        if outcome == "unknown" {
            evidence.remove("threshold_outcome");
        }
        QueryRecord {
            lower_before: before.lower,
            upper_before: before.upper,
            target: self.target,
            remaining_seconds: self.remaining_seconds,
            seconds: self.started.elapsed().as_secs_f64(),
            outcome: outcome.into(),
            cost,
            solution,
            native_sat_calls: native.calls - self.native_before.calls,
            native_sat_seconds: native
                .sat_time
                .saturating_sub(self.native_before.sat_time)
                .as_secs_f64(),
            native_budgeted_calls: native.budgeted_calls - self.native_before.budgeted_calls,
            variables,
            clauses,
            threshold_evidence: evidence,
            polish: None,
            model_generation: Some(model_generation),
        }
    }
}

pub(super) fn search(
    problem: &Problem,
    objective: DelayCostType,
    deadline: Instant,
    session: ThresholdSession,
    interval: &mut SearchInterval,
    incumbent: &mut Vec<Vec<i32>>,
    queries: &mut Vec<QueryRecord>,
    checkpoint: &mut impl FnMut(&QueryRecord, i32, i32),
) -> Result<usize, SolverError> {
    let policy = ThresholdPolicy::Upper;
    let Some(capacity) = interval.target_for(policy) else {
        return Ok(0);
    };
    let settings = MaxSatDddLadderScSettings {
        resource_orders: true,
        order_transitivity: true,
        core_minimize_checks: 4,
        core_minimize_conflicts: 100,
        core_exhaust_checks: 4,
        extract_initial_cost: matches!(session, ThresholdSession::ReuseOffset | ThresholdSession::ReuseOffsetTree),
        ..Default::default()
    };
    let mut models = 0;
    let mut save = |record, interval: SearchInterval| {
        checkpoint(&record, interval.lower, interval.upper);
        queries.push(record);
    };
    while let Some(target) = interval.target_for(policy) {
        let remaining = deadline
            .saturating_duration_since(Instant::now())
            .as_secs_f64();
        if remaining == 0.0 {
            break;
        }
        counting_solver::reset_counts();
        let solver = minisat_deadline::Solver::new(remaining);
        let decision = Decision::start(target, deadline);
        if decision.remaining_seconds == 0.0 {
            break;
        }
        let mut pending = Some(decision);
        models += 1;
        let evidence = RefCell::new(Map::new());
        let result = std::panic::catch_unwind(std::panic::AssertUnwindSafe(|| {
            solve_threshold_session(
                counting_solver::CountingSolver::new(solver),
                problem,
                remaining,
                objective,
                settings,
                capacity,
                target,
                session == ThresholdSession::ReuseOffsetTree,
                |solved_target, cost, schedule| {
                    let decision = pending.take().expect("active threshold");
                    if decision.target != solved_target {
                        return Err(SolverError::InvalidSolution(
                            "SAT answered a different threshold".into(),
                        ));
                    }
                    let before = *interval;
                    interval
                        .sat_for(policy, solved_target, cost)
                        .map_err(SolverError::InvalidSolution)?;
                    *incumbent = schedule.to_vec();
                    save(
                        decision.record(
                            before,
                            models,
                            "sat",
                            Some((cost, schedule.to_vec())),
                            evidence.borrow().clone(),
                        ),
                        *interval,
                    );
                    if matches!(session, ThresholdSession::Reuse | ThresholdSession::ReuseOffset | ThresholdSession::ReuseOffsetTree) {
                        if let Some(next) = interval.target_for(policy) {
                            let decision = Decision::start(next, deadline);
                            if decision.remaining_seconds > 0.0 {
                                pending = Some(decision);
                                return Ok(Some(next));
                            }
                        }
                    }
                    Ok(None)
                },
                |key, value| {
                    evidence.borrow_mut().insert(key, value);
                },
            )
        }));
        let outcome = match result {
            Ok(Ok(())) => continue,
            Ok(Err(SolverError::NoSolution)) => "unsat",
            Ok(Err(SolverError::Timeout)) => "unknown",
            Err(payload) if payload.is::<DeadlineReached>() => "unknown",
            Ok(Err(error)) => return Err(error),
            Err(payload) => std::panic::resume_unwind(payload),
        };
        let decision = pending.expect("active threshold");
        let before = *interval;
        if outcome == "unsat" {
            interval
                .unsat_for(policy, decision.target)
                .map_err(SolverError::InvalidSolution)?;
        }
        save(
            decision.record(before, models, outcome, None, evidence.into_inner()),
            *interval,
        );
        break;
    }
    Ok(models)
}
