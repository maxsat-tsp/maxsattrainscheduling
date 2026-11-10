//! Oracle-free binary search using independently rebuilt SAT-DDD decisions.
use crate::{problem::{Problem,DelayCostType},solvers::SolverError};
use super::{maxsat_ladder_sc as sc,incumbent_polish,shared::{greedy,precedence}};
use crate::solvers::util::{counting_solver,minisat_deadline,cadical_deadline::DeadlineReached};
use serde::Serialize;
use std::time::Instant;

#[derive(Clone,Copy,Debug,PartialEq,Serialize)]
pub enum ThresholdPolicy {
    #[serde(rename="bisect")] Bisect,
    #[serde(rename="close-upper")] CloseUpper,
    #[serde(rename="upper")] Upper,
}
impl ThresholdPolicy {
    pub fn parse(value:&str)->Result<Self,String>{
        match value {"bisect"=>Ok(Self::Bisect),"close-upper"=>Ok(Self::CloseUpper),"upper"=>Ok(Self::Upper),
            _=>Err("unsupported threshold policy".into())}
    }
}

#[derive(Clone,Copy,Debug)]
pub struct SearchInterval {pub lower:i32,pub upper:i32}
impl SearchInterval {
    pub fn new(lower:i32,upper:i32)->Result<Self,String>{
        if lower<0 || lower>upper {return Err("invalid initial cost interval".into());}
        Ok(Self{lower,upper})
    }
    pub fn target(&self)->Option<i32>{
        self.target_for(ThresholdPolicy::Bisect)
    }
    pub fn target_for(&self,policy:ThresholdPolicy)->Option<i32>{
        if self.lower>=self.upper{return None;}
        if policy==ThresholdPolicy::Upper{return Some(self.upper-1);}
        // At a relative gap of at most 5%, ask for any strict improvement
        // over the incumbent. All arithmetic remains integral and overflow-safe.
        if policy==ThresholdPolicy::CloseUpper && 100i64*i64::from(self.upper-self.lower)<=5i64*i64::from(self.upper.max(1)) {
            return Some(self.upper-1);
        }
        (self.lower<self.upper).then(||self.lower+(self.upper-self.lower-1)/2)
    }
    pub fn sat(&mut self,target:i32,cost:i32)->Result<(),String>{
        self.sat_for(ThresholdPolicy::Bisect,target,cost)
    }
    pub fn sat_for(&mut self,policy:ThresholdPolicy,target:i32,cost:i32)->Result<(),String>{
        if self.target_for(policy)!=Some(target) || cost<self.lower || cost>target {
            return Err("SAT cost does not fit the current search interval".into());
        }
        self.upper=cost;Ok(())
    }
    pub fn unsat(&mut self,target:i32)->Result<(),String>{
        self.unsat_for(ThresholdPolicy::Bisect,target)
    }
    pub fn unsat_for(&mut self,policy:ThresholdPolicy,target:i32)->Result<(),String>{
        if self.target_for(policy)!=Some(target){return Err("UNSAT threshold was not selected by the search".into());}
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
    pub polish:Option<incumbent_polish::PolishRecord>,
}

#[derive(Serialize)]
pub struct WarmupRecord {
    pub status:&'static str,pub budget_seconds:f64,pub seconds:f64,
    pub lower_before:i32,pub upper_before:i32,pub lb:i32,pub ub:i32,
    pub solution:Vec<Vec<i32>>,pub checkpoints:Vec<sc::Rc2Checkpoint>,
    pub native_sat_calls:usize,pub native_sat_seconds:f64,
    pub evidence:serde_json::Map<String,serde_json::Value>,
}

#[derive(Serialize)]
pub struct SearchResult {
    pub schema:&'static str,pub solver_name:&'static str,pub status:&'static str,
    pub uses_optimum_oracle:bool,pub maxsat_backend:&'static str,
    pub maxsat_backend_signature:String,pub timeout_seconds:f64,pub total_time:f64,
    pub lb:i32,pub ub:i32,pub cost:i32,pub solution:Vec<Vec<i32>>,
    pub initial_lb:i32,pub initial_ub:i32,pub initial_solution:Vec<Vec<i32>>,
    pub queries:Vec<QueryRecord>,
    pub threshold_policy:ThresholdPolicy,
    pub rc2_warmup_seconds:f64,pub warmup:Option<WarmupRecord>,
    pub incumbent_polish_checks:usize,
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
    checkpoint:impl FnMut(&QueryRecord,i32,i32))->Result<SearchResult,SolverError>{
    solve_with_policy(problem,objective,timeout,ThresholdPolicy::Bisect,checkpoint)
}

pub fn solve_with_policy(problem:&Problem,objective:DelayCostType,timeout:f64,policy:ThresholdPolicy,
    checkpoint:impl FnMut(&QueryRecord,i32,i32))->Result<SearchResult,SolverError>{
    solve_with_warmup(problem,objective,timeout,policy,0.0,checkpoint)
}

pub fn solve_with_warmup(problem:&Problem,objective:DelayCostType,timeout:f64,policy:ThresholdPolicy,
    warmup_seconds:f64,
    checkpoint:impl FnMut(&QueryRecord,i32,i32))->Result<SearchResult,SolverError>{
    solve_with_polish(problem,objective,timeout,policy,warmup_seconds,0,checkpoint)
}

pub fn solve_with_polish(problem:&Problem,objective:DelayCostType,timeout:f64,policy:ThresholdPolicy,
    warmup_seconds:f64,polish_checks:usize,
    mut checkpoint:impl FnMut(&QueryRecord,i32,i32))->Result<SearchResult,SolverError>{
    if !timeout.is_finite() || timeout<=0.0 {
        return Err(SolverError::InvalidSolution("search timeout must be finite and positive".into()));
    }
    if !warmup_seconds.is_finite() || warmup_seconds<0.0 {
        return Err(SolverError::InvalidSolution("warmup budget must be finite and nonnegative".into()));
    }
    let started=Instant::now();
    let duration=std::time::Duration::try_from_secs_f64(timeout)
        .map_err(|_|SolverError::InvalidSolution("search timeout exceeds Duration range".into()))?;
    let deadline=started.checked_add(duration)
        .ok_or_else(||SolverError::InvalidSolution("search deadline exceeds Instant range".into()))?;
    let (mut interval,mut incumbent)=initial_bounds(problem,objective)?;
    let initial_lb=interval.lower;let initial_ub=interval.upper;let initial_solution=incumbent.clone();
    let mut queries=Vec::new();
    let mut signature=minisat::Solver::new().solver_name().to_string();
    let budget=warmup_seconds.min((timeout-started.elapsed().as_secs_f64()).max(0.0));
    let warmup=if budget>0.0 && interval.lower<interval.upper {
        let before=interval;let warm_started=Instant::now();
        counting_solver::reset_counts();
        let solver=minisat_deadline::Solver::new(budget);signature=solver.signature().to_string();
        let mut settings=sc::MaxSatDddLadderScSettings::default();
        settings.resource_orders=true;settings.order_transitivity=true;
        settings.core_minimize_checks=4;settings.core_minimize_conflicts=100;settings.core_exhaust_checks=4;
        let mut progress=sc::Rc2Progress::default();let mut evidence=serde_json::Map::new();
        let result=std::panic::catch_unwind(std::panic::AssertUnwindSafe(||
            sc::solve_with_progress(counting_solver::CountingSolver::new(solver),problem,budget,objective,settings,&mut progress,
                |key,value|{evidence.insert(key,value);} )));
        let status=match result {
            Ok(Ok((solution,_)))=>{
                let cost=problem.verify_solution(&solution,objective)
                    .ok_or_else(||SolverError::InvalidSolution("RC2 optimum schedule failed validation".into()))?;
                if evidence.get("lb").and_then(|v|v.as_i64())!=Some(i64::from(cost)) {
                    return Err(SolverError::InvalidSolution("RC2 optimum has no matching proved lower bound".into()));
                }
                progress.observe(problem,objective,cost,Some(&(cost,solution)),warm_started.elapsed().as_secs_f64())?;
                "optimal"
            },
            Ok(Err(SolverError::Timeout))=>"timeout",
            Err(payload) if payload.is::<DeadlineReached>()=>"timeout",
            Ok(Err(error))=>return Err(error),
            Err(payload)=>std::panic::resume_unwind(payload),
        };
        interval.lower=interval.lower.max(progress.lower);
        if progress.upper<interval.upper {
            incumbent=progress.solution.ok_or_else(||SolverError::InvalidSolution("RC2 upper bound has no schedule".into()))?;
            interval.upper=progress.upper;
        }
        if interval.lower>interval.upper{return Err(SolverError::InvalidSolution("warmup contradicts the initial feasible interval".into()));}
        let stats=minisat_deadline::native_stats();
        Some(WarmupRecord{status,budget_seconds:budget,seconds:warm_started.elapsed().as_secs_f64(),
            lower_before:before.lower,upper_before:before.upper,lb:interval.lower,ub:interval.upper,
            solution:incumbent.clone(),checkpoints:progress.checkpoints,native_sat_calls:stats.calls,
            native_sat_seconds:stats.sat_time.as_secs_f64(),evidence})
    }else{None};
    while let Some(target)=interval.target_for(policy){
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
        let mut polish=None;
        let (outcome,cost,solution)=match result {
            Ok(Ok((schedule,_)))=>{
                if evidence.get("threshold_outcome").and_then(|x|x.as_str())!=Some("sat") {
                    return Err(SolverError::InvalidSolution("threshold SAT evidence missing".into()));
                }
                let cost=problem.verify_solution(&schedule,objective)
                    .ok_or_else(||SolverError::InvalidSolution("threshold schedule is invalid".into()))?;
                if cost<before.lower || cost>target {
                    return Err(SolverError::InvalidSolution("raw SAT witness does not fit its search interval".into()));
                }
                let (schedule,cost)=if polish_checks>0 {
                    let (schedule,cost,record)=incumbent_polish::improve(problem,objective,schedule,cost,polish_checks,deadline)?;
                    polish=Some(record);(schedule,cost)
                }else{(schedule,cost)};
                interval.sat_for(policy,target,cost).map_err(SolverError::InvalidSolution)?;
                incumbent=schedule.clone();("sat",Some(cost),Some(schedule))
            },
            Ok(Err(SolverError::NoSolution))=>{
                if evidence.get("threshold_outcome").and_then(|x|x.as_str())!=Some("unsat") {
                    return Err(SolverError::InvalidSolution("threshold UNSAT evidence missing".into()));
                }
                interval.unsat_for(policy,target).map_err(SolverError::InvalidSolution)?;
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
            variables,clauses,threshold_evidence:evidence,polish};
        checkpoint(&record,interval.lower,interval.upper);queries.push(record);
        if outcome=="unknown" {break;}
    }
    let elapsed=started.elapsed().as_secs_f64();
    let cost=problem.verify_solution(&incumbent,objective)
        .ok_or_else(||SolverError::InvalidSolution("final incumbent failed validation".into()))?;
    if cost!=interval.upper || interval.lower>cost {
        return Err(SolverError::InvalidSolution("search bounds disagree with incumbent".into()));
    }
    Ok(SearchResult{schema:"sat-bound-search-v1",solver_name:match (warmup_seconds>0.0,policy) {
        (false,ThresholdPolicy::Bisect)=>"SAT-Bisect-Restart",(false,ThresholdPolicy::CloseUpper)=>"SAT-CloseUpper-Restart",
        (false,ThresholdPolicy::Upper)=>"SAT-Upper-Restart",
        (true,ThresholdPolicy::Bisect)=>"RC2-Warm-SAT-Bisect-Restart",(true,ThresholdPolicy::CloseUpper)=>"RC2-Warm-SAT-CloseUpper-Restart",
        (true,ThresholdPolicy::Upper)=>"RC2-Warm-SAT-Upper-Restart"},
        status:if interval.lower==interval.upper && elapsed<=timeout {"ok"}else{"timeout"},
        uses_optimum_oracle:false,maxsat_backend:"minisat",maxsat_backend_signature:signature,
        timeout_seconds:timeout,total_time:elapsed,lb:interval.lower,ub:interval.upper,cost,solution:incumbent,
        initial_lb,initial_ub,initial_solution,queries,threshold_policy:policy,rc2_warmup_seconds:warmup_seconds,warmup,
        incumbent_polish_checks:polish_checks})
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::problem::{Train,Visit};
    #[test]
    fn polished_search_matches_exhaustive_optima_and_never_raises_a_sat_cost(){
        let p=Problem{name:"polished-search".into(),conflicts:vec![(0,0)],trains:vec![
            Train{visits:vec![Visit{resource_id:0,earliest:0,aimed:Some(0),travel_time:2}]},
            Train{visits:vec![Visit{resource_id:0,earliest:0,aimed:Some(0),travel_time:1}]}]};
        for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180]{
            let expected=(0..=5).flat_map(|a|(0..=5).map(move|b|(a,b)))
                .filter_map(|(a,b)|p.verify_solution(&[vec![a,a+2],vec![b,b+1]],objective)).min().unwrap();
            for policy in [ThresholdPolicy::Bisect,ThresholdPolicy::CloseUpper,ThresholdPolicy::Upper]{
                let r=solve_with_polish(&p,objective,5.0,policy,0.0,32,|q,_,_|{
                    if q.outcome=="sat" {let x=q.polish.as_ref().unwrap();assert!(q.cost.unwrap()<=x.source_cost);}
                    else {assert!(q.polish.is_none());}
                }).unwrap();
                assert_eq!(r.status,"ok");assert_eq!(r.lb,expected);assert_eq!(r.ub,expected);
            }
        }
    }
    #[test]
    fn upper_policy_descends_on_sat_and_closes_the_gap_on_unsat(){
        assert_eq!(SearchInterval::new(0,i32::MAX).unwrap().target_for(ThresholdPolicy::Upper),Some(i32::MAX-1));
        assert_eq!(SearchInterval::new(0,0).unwrap().target_for(ThresholdPolicy::Upper),None);
        for lower in 0..12 {for upper in lower..30 {for optimum in lower..=upper {
            let mut s=SearchInterval::new(lower,upper).unwrap();let mut calls=0;
            while let Some(t)=s.target_for(ThresholdPolicy::Upper){
                let old_upper=s.upper;
                if t<optimum{s.unsat_for(ThresholdPolicy::Upper,t).unwrap();assert_eq!(s.lower,old_upper);}
                else{s.sat_for(ThresholdPolicy::Upper,t,t).unwrap();assert!(s.upper<old_upper);}
                assert!(s.lower<=optimum && optimum<=s.upper);calls+=1;assert!(calls<=30);
            }
            assert_eq!(s.lower,optimum);
        }}}
        let mut s=SearchInterval::new(0,100).unwrap();
        assert!(s.unsat_for(ThresholdPolicy::Upper,49).is_err());
        assert!(s.sat_for(ThresholdPolicy::Upper,99,100).is_err());
    }
    #[test]
    fn rc2_warmup_preserves_exhaustive_optima_for_every_objective(){
        for count in 1..=3 {
            let p=Problem{name:"warmup-exhaustive".into(),conflicts:vec![(0,0)],
                trains:(0..count).map(|_|Train{visits:vec![Visit{resource_id:0,earliest:0,aimed:Some(0),travel_time:2}]}).collect()};
            for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180]{
                let pure=solve_with_policy(&p,objective,5.0,ThresholdPolicy::CloseUpper,|_,_,_|{}).unwrap();
                let warm=solve_with_warmup(&p,objective,5.0,ThresholdPolicy::CloseUpper,1.0,|_,_,_|{}).unwrap();
                assert_eq!(warm.status,"ok");assert_eq!(warm.cost,pure.cost);assert_eq!(warm.lb,warm.ub);
                if let Some(record)=warm.warmup {
                    assert!(record.lb>=warm.initial_lb && record.ub<=warm.initial_ub);
                    assert_eq!(p.verify_solution(&record.solution,objective),Some(record.ub));
                }
            }
        }
    }
    #[test]
    fn interrupted_rc2_warmup_never_claims_an_unproved_optimum(){
        let p=Problem{name:"warmup-timeout".into(),conflicts:vec![(0,0)],
            trains:(0..4).map(|_|Train{visits:vec![Visit{resource_id:0,earliest:0,aimed:Some(0),travel_time:2}]}).collect()};
        let r=solve_with_warmup(&p,DelayCostType::Continuous,1e-9,ThresholdPolicy::CloseUpper,1.0,|_,_,_|{}).unwrap();
        assert_eq!(r.status,"timeout");assert!(r.queries.is_empty());
        assert_eq!(p.verify_solution(&r.solution,DelayCostType::Continuous),Some(r.ub));
        assert!(solve_with_warmup(&p,DelayCostType::Continuous,1.0,ThresholdPolicy::CloseUpper,-1.0,|_,_,_|{}).is_err());
    }
    #[test]
    fn sat_search_continues_after_an_interrupted_short_warmup(){
        let p=Problem{name:"warmup-handoff".into(),conflicts:vec![(0,0)],
            trains:(0..4).map(|_|Train{visits:vec![Visit{resource_id:0,earliest:0,aimed:Some(0),travel_time:2}]}).collect()};
        let r=solve_with_warmup(&p,DelayCostType::Continuous,5.0,ThresholdPolicy::CloseUpper,1e-9,|_,_,_|{}).unwrap();
        assert_eq!(r.status,"ok");assert_eq!(r.cost,12);assert!(!r.queries.is_empty());
        let warm=r.warmup.as_ref().unwrap();assert_eq!(warm.status,"timeout");
        assert!(r.queries[0].remaining_seconds<=5.0-warm.seconds);
    }
    #[test]
    fn close_upper_policy_switches_only_at_small_gap_and_closes_proved_intervals(){
        assert_eq!(SearchInterval::new(8949,9245).unwrap().target_for(ThresholdPolicy::CloseUpper),Some(9244));
        assert_eq!(SearchInterval::new(12,118).unwrap().target_for(ThresholdPolicy::CloseUpper),Some(64));
        assert_eq!(SearchInterval::new(i32::MAX-4,i32::MAX).unwrap().target_for(ThresholdPolicy::CloseUpper),Some(i32::MAX-1));
        assert_eq!(SearchInterval::new(0,0).unwrap().target_for(ThresholdPolicy::CloseUpper),None);
        for lower in 0..40 {for upper in lower..60 {for optimum in lower..=upper {
            let mut s=SearchInterval::new(lower,upper).unwrap();let mut calls=0;
            while let Some(t)=s.target_for(ThresholdPolicy::CloseUpper){
                if t<optimum{s.unsat_for(ThresholdPolicy::CloseUpper,t).unwrap();}
                else{s.sat_for(ThresholdPolicy::CloseUpper,t,t).unwrap();}
                assert!(s.lower<=optimum && s.upper>=optimum);calls+=1;assert!(calls<=60);
            }
            assert_eq!(s.lower,optimum);
        }}}
    }
    #[test]
    fn close_upper_native_queries_handle_both_sat_improvement_and_unsat_optimality(){
        let unavoidable=Problem{name:"close-upper-unsat".into(),conflicts:vec![(0,0)],
            trains:(0..3).map(|_|Train{visits:vec![Visit{resource_id:0,earliest:0,
                aimed:Some(-100),travel_time:2}]}).collect()};
        let result=solve_with_policy(&unavoidable,DelayCostType::Continuous,5.0,ThresholdPolicy::CloseUpper,|_,_,_|{}).unwrap();
        // Each train pays at least 100; three length-two visits must start
        // no earlier than 0,2,4, giving an exhaustive lower bound of 306.
        assert_eq!(result.cost,306);assert_eq!(result.status,"ok");
        assert_eq!(result.queries[0].target,305);assert_eq!(result.queries[0].outcome,"unsat");
        let improve=Problem{name:"close-upper-sat".into(),conflicts:vec![(0,0),(1,1)],trains:vec![
            Train{visits:vec![Visit{resource_id:0,earliest:0,aimed:Some(100),travel_time:4}]},
            Train{visits:vec![Visit{resource_id:0,earliest:0,aimed:Some(0),travel_time:1}]},
            Train{visits:vec![Visit{resource_id:1,earliest:200,aimed:Some(0),travel_time:1}]},
        ]};
        let result=solve_with_policy(&improve,DelayCostType::Continuous,5.0,ThresholdPolicy::CloseUpper,|_,_,_|{}).unwrap();
        assert_eq!(result.initial_ub,204);assert_eq!(result.cost,200);assert_eq!(result.status,"ok");
        assert_eq!(result.queries[0].target,203);assert_eq!(result.queries[0].outcome,"sat");
    }
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
                for policy in [ThresholdPolicy::Bisect,ThresholdPolicy::CloseUpper,ThresholdPolicy::Upper]{
                let result=solve_with_policy(&problem,objective,5.0,policy,|_,_,_|{}).unwrap();
                assert_eq!(result.status,"ok");assert_eq!(result.cost,optimum);
                assert_eq!(result.lb,result.ub);assert!(!result.uses_optimum_oracle);
                assert_eq!(problem.verify_solution(&result.solution,objective),Some(optimum));
                }
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
