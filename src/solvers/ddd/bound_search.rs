//! Oracle-free binary search using independently rebuilt SAT-DDD decisions.
use crate::{problem::{Problem,DelayCostType},solvers::SolverError};
use super::{maxsat_ladder_sc as sc,shared::{greedy,precedence}};
use crate::solvers::util::{counting_solver,minisat_deadline,cadical_deadline::DeadlineReached};
use serde::Serialize;
use std::time::Instant;

#[derive(Clone,Copy,Debug)]
pub struct SearchInterval {pub lower:i32,pub upper:i32}
impl SearchInterval {
    pub fn new(lower:i32,upper:i32)->Result<Self,String>{
        if lower<0 || lower>upper {return Err("invalid initial cost interval".into());}
        Ok(Self{lower,upper})
    }
    pub fn target(&self)->Option<i32>{
        (self.lower<self.upper).then(||self.lower+(self.upper-self.lower-1)/2)
    }
    pub fn sat(&mut self,target:i32,cost:i32)->Result<(),String>{
        if self.target()!=Some(target) || cost<self.lower || cost>target {
            return Err("SAT cost does not fit the current search interval".into());
        }
        self.upper=cost;Ok(())
    }
    pub fn unsat(&mut self,target:i32)->Result<(),String>{
        if self.target()!=Some(target){return Err("UNSAT threshold was not selected by the search".into());}
        self.lower=target+1;Ok(())
    }
}

#[derive(Serialize)]
pub struct QueryRecord {
    pub lower_before:i32,pub upper_before:i32,pub target:i32,
    pub remaining_seconds:f64,pub seconds:f64,pub outcome:String,
    pub cost:Option<i32>,pub solution:Option<Vec<Vec<i32>>>,
    pub native_sat_calls:usize,pub native_sat_seconds:f64,
    pub native_budgeted_calls:usize,
    pub variables:usize,pub clauses:usize,
    pub threshold_evidence:serde_json::Map<String,serde_json::Value>,
}

#[derive(Serialize)]
pub struct SearchResult {
    pub schema:&'static str,pub solver_name:&'static str,pub status:&'static str,
    pub uses_optimum_oracle:bool,pub maxsat_backend:&'static str,
    pub maxsat_backend_signature:String,pub timeout_seconds:f64,pub total_time:f64,
    pub lb:i32,pub ub:i32,pub cost:i32,pub solution:Vec<Vec<i32>>,
    pub initial_lb:i32,pub initial_ub:i32,pub initial_solution:Vec<Vec<i32>>,
    pub queries:Vec<QueryRecord>,
}

/// Costs at chain-propagated earliest starts are an input-only lower bound.
pub fn initial_bounds(problem:&Problem,objective:DelayCostType)
    ->Result<(SearchInterval,Vec<Vec<i32>>),SolverError>{
    let earliest=precedence::chain_earliest(problem);
    let mut lower=0i32;
    for (ti,train) in problem.trains.iter().enumerate(){
        for vi in 0..train.visits.len(){
            let cost=i32::try_from(train.visit_delay_cost(objective,vi,earliest[ti][vi]))
                .map_err(|_|SolverError::InvalidSolution("initial cost exceeds i32".into()))?;
            lower=lower.checked_add(cost).ok_or_else(||SolverError::InvalidSolution("cost overflow".into()))?;
        }
    }
    let solution=greedy::greedy_schedule(problem);
    let upper=problem.verify_solution(&solution,objective)
        .ok_or_else(||SolverError::InvalidSolution("greedy initial schedule is invalid".into()))?;
    Ok((SearchInterval::new(lower,upper).map_err(SolverError::InvalidSolution)?,solution))
}

pub fn solve(problem:&Problem,objective:DelayCostType,timeout:f64,
    mut checkpoint:impl FnMut(&QueryRecord,i32,i32))->Result<SearchResult,SolverError>{
    if !timeout.is_finite() || timeout<=0.0 {
        return Err(SolverError::InvalidSolution("search timeout must be finite and positive".into()));
    }
    let started=Instant::now();
    let (mut interval,mut incumbent)=initial_bounds(problem,objective)?;
    let initial_lb=interval.lower;let initial_ub=interval.upper;let initial_solution=incumbent.clone();
    let mut queries=Vec::new();
    let mut signature=minisat::Solver::new().solver_name().to_string();
    while let Some(target)=interval.target(){
        let remaining=timeout-started.elapsed().as_secs_f64();
        if remaining<=0.0 {break;}
        let before=interval;
        counting_solver::reset_counts();
        let query_started=Instant::now();
        let solver=minisat_deadline::Solver::new(remaining);
        signature=solver.signature().to_string();
        let mut settings=sc::MaxSatDddLadderScSettings::default();
        settings.resource_orders=true;settings.order_transitivity=true;
        // These legacy core settings are inert: no RC2 assumptions are used.
        settings.core_minimize_checks=4;settings.core_minimize_conflicts=100;settings.core_exhaust_checks=4;
        let mut evidence=serde_json::Map::new();
        let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||
            sc::solve_cost_threshold(counting_solver::CountingSolver::new(solver),problem,
                remaining,objective,settings,target,|key,value|{evidence.insert(key,value);})));
        let (outcome,cost,solution)=match result {
            Ok(Ok((schedule,_)))=>{
                if evidence.get("threshold_outcome").and_then(|x|x.as_str())!=Some("sat") {
                    return Err(SolverError::InvalidSolution("threshold SAT evidence missing".into()));
                }
                let cost=problem.verify_solution(&schedule,objective)
                    .ok_or_else(||SolverError::InvalidSolution("threshold schedule is invalid".into()))?;
                interval.sat(target,cost).map_err(SolverError::InvalidSolution)?;
                incumbent=schedule.clone();("sat",Some(cost),Some(schedule))
            },
            Ok(Err(SolverError::NoSolution))=>{
                if evidence.get("threshold_outcome").and_then(|x|x.as_str())!=Some("unsat") {
                    return Err(SolverError::InvalidSolution("threshold UNSAT evidence missing".into()));
                }
                interval.unsat(target).map_err(SolverError::InvalidSolution)?;
                ("unsat",None,None)
            },
            Ok(Err(SolverError::Timeout))=>("unknown",None,None),
            Err(payload) if payload.is::<DeadlineReached>()=>("unknown",None,None),
            Ok(Err(error))=>return Err(error),
            Err(payload)=>std::panic::resume_unwind(payload),
        };
        let stats=minisat_deadline::native_stats();let (variables,clauses)=counting_solver::get_counts();
        let record=QueryRecord{lower_before:before.lower,upper_before:before.upper,target,
            remaining_seconds:remaining,seconds:query_started.elapsed().as_secs_f64(),
            outcome:outcome.into(),cost,solution,native_sat_calls:stats.calls,
            native_sat_seconds:stats.sat_time.as_secs_f64(),native_budgeted_calls:stats.budgeted_calls,
            variables,clauses,threshold_evidence:evidence};
        checkpoint(&record,interval.lower,interval.upper);queries.push(record);
        if outcome=="unknown" {break;}
    }
    let elapsed=started.elapsed().as_secs_f64();
    let cost=problem.verify_solution(&incumbent,objective)
        .ok_or_else(||SolverError::InvalidSolution("final incumbent failed validation".into()))?;
    if cost!=interval.upper || interval.lower>cost {
        return Err(SolverError::InvalidSolution("search bounds disagree with incumbent".into()));
    }
    Ok(SearchResult{schema:"sat-bound-search-v1",solver_name:"SAT-Bisect-Restart",
        status:if interval.lower==interval.upper && elapsed<=timeout {"ok"}else{"timeout"},
        uses_optimum_oracle:false,maxsat_backend:"minisat",maxsat_backend_signature:signature,
        timeout_seconds:timeout,total_time:elapsed,lb:interval.lower,ub:interval.upper,cost,solution:incumbent,
        initial_lb,initial_ub,initial_solution,queries})
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::problem::{Train,Visit};
    #[test]
    fn interval_search_handles_holes_boundaries_and_verified_improvements(){
        for lower in 0..15 {for upper in lower..30 {for optimum in lower..=upper {
            let mut s=SearchInterval::new(lower,upper).unwrap();let mut calls=0;
            while let Some(t)=s.target(){
                if t<optimum{s.unsat(t).unwrap();}else{s.sat(t,t).unwrap();}
                assert!(s.lower<=optimum && s.upper>=optimum);calls+=1;assert!(calls<=5);
            }
            assert_eq!(s.lower,optimum);
        }}}
        let mut s=SearchInterval::new(i32::MAX-4,i32::MAX).unwrap();
        assert_eq!(s.target(),Some(i32::MAX-3));s.sat(i32::MAX-3,i32::MAX-4).unwrap();
        assert_eq!(s.lower,s.upper);
    }
    #[test]
    fn interval_search_rejects_unproved_or_inconsistent_updates(){
        assert!(SearchInterval::new(-1,2).is_err());assert!(SearchInterval::new(3,2).is_err());
        let mut s=SearchInterval::new(2,10).unwrap();
        for (target,cost) in [(5,1),(5,6),(6,4)]{assert!(s.sat(target,cost).is_err());}
        assert!(s.unsat(6).is_err());assert_eq!((s.lower,s.upper),(2,10));
    }
    #[test]
    fn bound_search_matches_exhaustive_tiny_schedules_and_zero_cost(){
        for count in 1..=3 {
            let problem=Problem{name:"search-exhaustive".into(),conflicts:vec![(0,0)],
                trains:(0..count).map(|_|Train{visits:vec![Visit{resource_id:0,
                    earliest:0,aimed:Some(0),travel_time:2}]}).collect()};
            for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180]{
                let mut optimum=i32::MAX;
                for a in 0..=6 {for b in 0..=6 {for c in 0..=6 {
                    let schedule=[a,b,c][..count].iter().map(|&t|vec![t,t+2]).collect::<Vec<_>>();
                    if let Some(cost)=problem.verify_solution(&schedule,objective){optimum=optimum.min(cost);}
                }}}
                let result=solve(&problem,objective,5.0,|_,_,_|{}).unwrap();
                assert_eq!(result.status,"ok");assert_eq!(result.cost,optimum);
                assert_eq!(result.lb,result.ub);assert!(!result.uses_optimum_oracle);
                assert_eq!(problem.verify_solution(&result.solution,objective),Some(optimum));
            }
        }
    }
    #[test]
    fn bound_search_improves_a_suboptimal_greedy_incumbent(){
        let problem=Problem{name:"greedy-is-suboptimal".into(),conflicts:vec![(0,0)],trains:vec![
            Train{visits:vec![Visit{resource_id:0,earliest:0,aimed:Some(100),travel_time:4}]},
            Train{visits:vec![Visit{resource_id:0,earliest:0,aimed:Some(0),travel_time:1}]},
        ]};
        for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180]{
            let result=solve(&problem,objective,5.0,|_,_,_|{}).unwrap();
            assert!(result.initial_ub>result.cost);assert_eq!(result.cost,0);
            assert_eq!(result.status,"ok");assert!(result.queries.iter().any(|q|q.outcome=="sat"));
        }
    }
    #[test]
    fn bound_search_timeout_preserves_incumbent_and_never_claims_unknown_unsat(){
        let problem=Problem{name:"timeout".into(),conflicts:vec![(0,0)],
            trains:(0..3).map(|_|Train{visits:vec![Visit{resource_id:0,
                earliest:0,aimed:Some(0),travel_time:2}]}).collect()};
        let result=solve(&problem,DelayCostType::Continuous,f64::MIN_POSITIVE,|_,_,_|{}).unwrap();
        // If the input lower bound already equals the greedy UB, no query is
        // needed. Otherwise the expired budget must preserve both bounds.
        assert_eq!(result.status,"timeout");assert!(result.queries.is_empty());
        assert_eq!(result.lb,result.initial_lb);assert_eq!(result.ub,result.initial_ub);
        assert_eq!(problem.verify_solution(&result.solution,DelayCostType::Continuous),Some(result.ub));
    }
}
