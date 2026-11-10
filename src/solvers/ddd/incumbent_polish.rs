//! Retiming and adjacent resource-order swaps of a solver's own SAT witness.
//! This only improves feasible upper bounds; it proves no lower bound.
use crate::{problem::{Problem, DelayCostType}, solvers::SolverError};
use serde::Serialize;
use std::{collections::{BTreeMap, VecDeque}, time::Instant};

#[derive(Serialize)]
pub struct PolishRecord {
    pub source_cost: i32,
    pub source_solution: Vec<Vec<i32>>,
    pub retimed_cost: i32,
    pub checks: usize,
    pub accepted_moves: usize,
    pub seconds: f64,
}

struct Graph {
    offsets: Vec<usize>,
    earliest: Vec<i32>,
    chain: Vec<(usize, usize, i32)>,
    orders: Vec<Vec<(usize, usize)>>,
}

impl Graph {
    fn new(problem: &Problem, solution: &[Vec<i32>]) -> Option<Self> {
        // The TRP dataset has exclusive resources. Do not apply this
        // neighborhood to an instance with cross-resource incompatibilities.
        if problem.conflicts.iter().any(|&(a,b)| a != b) { return None; }
        let mut graph = Self { offsets: Vec::new(), earliest: Vec::new(),
            chain: Vec::new(), orders: Vec::new() };
        let mut groups = BTreeMap::<usize,Vec<(i32,i32,usize,usize)>>::new();
        for (ti, train) in problem.trains.iter().enumerate() {
            let off = graph.earliest.len(); graph.offsets.push(off);
            for (vi, visit) in train.visits.iter().enumerate() {
                graph.earliest.push(visit.earliest);
                graph.chain.push((off+vi,off+vi+1,visit.travel_time));
                if problem.conflicts.contains(&(visit.resource_id,visit.resource_id)) {
                    groups.entry(visit.resource_id).or_default().push(
                        (solution[ti][vi],solution[ti][vi+1],off+vi,off+vi+1));
                }
            }
            let last = train.visits.last()?;
            graph.earliest.push(last.earliest.checked_add(last.travel_time)?);
        }
        for (_,mut group) in groups {
            group.sort();
            graph.orders.push(group.into_iter().map(|(_,_,a,b)|(a,b)).collect());
        }
        Some(graph)
    }

    fn evaluate(&self, problem: &Problem, objective: DelayCostType)
        -> Option<((i32,i32),Vec<Vec<i32>>)> {
        let n=self.earliest.len();let mut outgoing=vec![Vec::new();n];let mut indegree=vec![0usize;n];
        for &(a,b,d) in &self.chain { outgoing[a].push((b,d));indegree[b]+=1; }
        for group in &self.orders { for pair in group.windows(2) {
            let a=pair[0].1;let b=pair[1].0;outgoing[a].push((b,0));indegree[b]+=1;
        }}
        let mut values=self.earliest.clone();let mut seen=0;
        let mut queue:VecDeque<_>=(0..n).filter(|&v|indegree[v]==0).collect();
        while let Some(a)=queue.pop_front() {
            seen+=1;
            for &(b,d) in &outgoing[a] {
                values[b]=values[b].max(values[a].checked_add(d)?);indegree[b]-=1;
                if indegree[b]==0 {queue.push_back(b);}
            }
        }
        // Reject cyclic neighbors, including zero cycles. Keeping the original
        // checked witness is always safe if this conservative test rejects it.
        if seen!=n {return None;}
        let solution:Vec<_>=problem.trains.iter().enumerate().map(|(ti,t)|
            values[self.offsets[ti]..self.offsets[ti]+t.visits.len()+1].to_vec()).collect();
        let mut primary=0i32;let mut secondary=0i32;
        for (ti,train) in problem.trains.iter().enumerate(){for vi in 0..train.visits.len(){
            primary=primary.checked_add(i32::try_from(train.visit_delay_cost(objective,vi,solution[ti][vi])).ok()?)?;
            secondary=secondary.checked_add(i32::try_from(train.visit_delay_cost(DelayCostType::Continuous,vi,solution[ti][vi])).ok()?)?;
        }}
        Some(((primary,secondary),solution))
    }
}

pub fn improve(problem: &Problem, objective: DelayCostType, solution: Vec<Vec<i32>>,
    cost: i32, max_checks: usize, deadline: Instant)
    -> Result<(Vec<Vec<i32>>,i32,PolishRecord),SolverError> {
    let start=Instant::now();
    if solution.len()!=problem.trains.len() || solution.iter().zip(&problem.trains)
        .any(|(times,t)|times.len()!=t.visits.len()+1) || problem.verify_solution(&solution,objective)!=Some(cost) {
        return Err(SolverError::InvalidSolution("polishing requires a checked feasible incumbent".into()));
    }
    let mut record=PolishRecord{source_cost:cost,source_solution:solution.clone(),retimed_cost:cost,
        checks:0,accepted_moves:0,seconds:0.0};
    let mut best_solution=solution;let mut best_cost=cost;
    if max_checks>0 && Instant::now()<deadline {
        if let Some(mut graph)=Graph::new(problem,&best_solution) {
            if let Some((mut best_key,retimed))=graph.evaluate(problem,objective) {
                if best_key.0>cost || problem.verify_solution(&retimed,objective)!=Some(best_key.0) {
                    return Err(SolverError::InvalidSolution("retiming worsened or invalidated the incumbent".into()));
                }
                if Instant::now()<deadline {
                    record.retimed_cost=best_key.0;best_cost=best_key.0;best_solution=retimed;
                    while record.checks<max_checks && Instant::now()<deadline {
                        let mut next_key=best_key;let mut next=None;
                        'neighbors: for gi in 0..graph.orders.len(){
                            for j in 0..graph.orders[gi].len().saturating_sub(1){
                                if record.checks>=max_checks || Instant::now()>=deadline {break 'neighbors;}
                                graph.orders[gi].swap(j,j+1);
                                let candidate=graph.evaluate(problem,objective);record.checks+=1;
                                graph.orders[gi].swap(j,j+1);
                                if let Some((key,times))=candidate {if key<next_key {
                                    next_key=key;next=Some((gi,j,times));
                                }}
                            }
                        }
                        let Some((gi,j,times))=next else {break;};
                        if Instant::now()>=deadline {break;}
                        if problem.verify_solution(&times,objective)!=Some(next_key.0) {
                            return Err(SolverError::InvalidSolution("resource-order swap returned an invalid schedule".into()));
                        }
                        if Instant::now()>=deadline {break;}
                        graph.orders[gi].swap(j,j+1);best_key=next_key;
                        best_cost=next_key.0;best_solution=times;record.accepted_moves+=1;
                    }
                }
            }
        }
    }
    record.seconds=start.elapsed().as_secs_f64();
    Ok((best_solution,best_cost,record))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::problem::{Train,Visit};
    use std::time::Duration;
    fn example()->Problem {Problem{name:"polish".into(),conflicts:vec![(1,1)],trains:vec![
        Train{visits:vec![Visit{resource_id:1,earliest:0,aimed:Some(0),travel_time:10}]},
        Train{visits:vec![Visit{resource_id:1,earliest:0,aimed:Some(0),travel_time:1}]}]}}
    #[test]
    fn retiming_removes_wait_and_swapping_can_improve_primary_cost(){
        let p=example();let s=vec![vec![20,30],vec![30,31]];
        let (s,c,r)=improve(&p,DelayCostType::Continuous,s,50,32,Instant::now()+Duration::from_secs(2)).unwrap();
        assert_eq!(r.retimed_cost,10);assert_eq!(c,1);assert_eq!(p.verify_solution(&s,DelayCostType::Continuous),Some(1));
        assert_eq!(r.accepted_moves,1);assert!(r.checks<=32);
    }
    #[test]
    fn disabled_or_expired_polishing_preserves_the_original_witness(){
        let p=example();let s=vec![vec![0,10],vec![10,11]];
        for (checks,deadline) in [(0,Instant::now()+Duration::from_secs(2)),(32,Instant::now())] {
            let (t,c,r)=improve(&p,DelayCostType::Continuous,s.clone(),10,checks,deadline).unwrap();
            assert_eq!(t,s);assert_eq!(c,10);assert_eq!(r.checks,0);
        }
    }
    #[test]
    fn invalid_schedule_or_claimed_cost_is_rejected(){
        let p=example();let d=Instant::now()+Duration::from_secs(2);
        for (s,c) in [(vec![],0),(vec![vec![0,10],vec![1,2]],1),(vec![vec![0,10],vec![10,11]],9)] {
            assert!(improve(&p,DelayCostType::Continuous,s,c,32,d).is_err());
        }
    }
    #[test]
    fn cross_resource_conflicts_leave_the_checked_witness_unchanged(){
        let mut p=example();p.trains[1].visits[0].resource_id=2;p.conflicts=vec![(1,2),(2,1)];
        let s=vec![vec![0,10],vec![10,11]];
        let (t,c,r)=improve(&p,DelayCostType::Continuous,s.clone(),10,32,Instant::now()+Duration::from_secs(2)).unwrap();
        assert_eq!(t,s);assert_eq!(c,10);assert_eq!(r.checks,0);
    }
    #[test]
    fn feasible_zero_cycle_keeps_the_original_checked_schedule(){
        let make=|a,b|Train{visits:vec![
            Visit{resource_id:a,earliest:0,aimed:Some(0),travel_time:1},
            Visit{resource_id:b,earliest:0,aimed:Some(0),travel_time:1}]};
        let p=Problem{name:"zero-cycle".into(),conflicts:vec![(1,1),(2,2)],trains:vec![make(1,2),make(2,1)]};
        let s=vec![vec![0,1,2],vec![0,1,2]];
        let (t,c,r)=improve(&p,DelayCostType::Continuous,s.clone(),2,32,Instant::now()+Duration::from_secs(2)).unwrap();
        assert_eq!(t,s);assert_eq!(c,2);assert_eq!(r.checks,0);
    }
    #[test]
    fn a_swap_with_a_positive_cycle_is_rejected(){
        let make=|a,b|Train{visits:vec![
            Visit{resource_id:a,earliest:0,aimed:Some(0),travel_time:1},
            Visit{resource_id:b,earliest:0,aimed:Some(0),travel_time:1}]};
        let p=Problem{name:"positive-cycle".into(),conflicts:vec![(1,1),(2,2)],trains:vec![make(1,2),make(2,1)]};
        let s=vec![vec![0,1,2],vec![2,3,4]];
        let mut graph=Graph::new(&p,&s).unwrap();assert!(graph.evaluate(&p,DelayCostType::Continuous).is_some());
        graph.orders[0].swap(0,1);assert!(graph.evaluate(&p,DelayCostType::Continuous).is_none());
    }
    #[test]
    fn check_limit_and_tie_breaking_are_deterministic(){
        let p=example();let s=vec![vec![0,10],vec![10,11]];
        let run=||improve(&p,DelayCostType::Continuous,s.clone(),10,1,Instant::now()+Duration::from_secs(2)).unwrap();
        let (a,c,x)=run();let (b,d,y)=run();assert_eq!(a,b);assert_eq!(c,d);
        assert_eq!(x.checks,1);assert_eq!(x.accepted_moves,y.accepted_moves);
    }
    #[test]
    fn all_objectives_preserve_feasibility_and_exhaustive_optimum_bounds(){
        let mut p=example();p.trains[0].visits[0].travel_time=2;
        for objective in [DelayCostType::Continuous,DelayCostType::FiniteSteps123,DelayCostType::InfiniteSteps180] {
            let optimum=(0..=6).flat_map(|a|(0..=6).map(move|b|(a,b)))
                .filter_map(|(a,b)|p.verify_solution(&[vec![a,a+2],vec![b,b+1]],objective)).min().unwrap();
            for a in 0..=6 {for b in 0..=6 {
                let s=vec![vec![a,a+2],vec![b,b+1]];
                if let Some(cost)=p.verify_solution(&s,objective) {
                    let (t,c,r)=improve(&p,objective,s,cost,32,Instant::now()+Duration::from_secs(2)).unwrap();
                    assert!(optimum<=c && c<=cost);assert!(r.checks<=32);assert_eq!(p.verify_solution(&t,objective),Some(c));
                }
            }}
        }
    }
}
