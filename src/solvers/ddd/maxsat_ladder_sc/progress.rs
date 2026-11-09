//! Optional RC2 checkpoints for a subsequent optimizer. Legacy calls do not
//! collect snapshots or perform these extra incumbent checks.
use crate::{problem::{Problem,DelayCostType},solvers::SolverError};
use serde::Serialize;

#[derive(Clone,Serialize)]
pub struct Rc2Checkpoint {
    pub seconds:f64,pub lb:i32,pub ub:i32,
    pub cost:Option<i32>,pub solution:Option<Vec<Vec<i32>>>,
}

pub struct Rc2Progress {
    pub lower:i32,pub upper:i32,pub solution:Option<Vec<Vec<i32>>>,
    pub checkpoints:Vec<Rc2Checkpoint>,
}
impl Default for Rc2Progress {
    fn default()->Self{Self{lower:0,upper:i32::MAX,solution:None,checkpoints:Vec::new()}}
}
impl Rc2Progress {
    pub(crate) fn observe(&mut self,problem:&Problem,objective:DelayCostType,
        lower:i32,incumbent:Option<&(i32,Vec<Vec<i32>>)>,seconds:f64)->Result<(),SolverError>{
        if lower<self.lower {return Err(SolverError::InvalidSolution("RC2 checkpoint lower bound decreased".into()));}
        let improved=incumbent.filter(|(cost,_)|*cost<self.upper);
        if let Some((cost,schedule))=improved {
            if problem.verify_solution(schedule,objective)!=Some(*cost){
                return Err(SolverError::InvalidSolution("RC2 checkpoint incumbent is invalid".into()));
            }
        }
        let upper=improved.map_or(self.upper,|(cost,_)|*cost);
        if lower>upper{return Err(SolverError::InvalidSolution("RC2 checkpoint bounds cross".into()));}
        if lower==self.lower && improved.is_none(){return Ok(());}
        self.lower=lower;self.upper=upper;
        if let Some((_,schedule))=improved{self.solution=Some(schedule.clone());}
        self.checkpoints.push(Rc2Checkpoint{seconds,lb:lower,ub:upper,
            cost:improved.map(|(c,_)|*c),solution:improved.map(|(_,s)|s.clone())});
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::problem::{Train,Visit};
    #[test]
    fn checkpoint_keeps_only_proved_bounds_and_verified_incumbents(){
        let p=Problem{name:"checkpoint".into(),conflicts:vec![(0,0)],
            trains:(0..2).map(|_|Train{visits:vec![Visit{resource_id:0,earliest:0,aimed:Some(0),travel_time:2}]}).collect()};
        let good=(2,vec![vec![0,2],vec![2,4]]);let bad=(0,vec![vec![0,2],vec![0,2]]);
        let mut progress=Rc2Progress::default();
        assert!(progress.observe(&p,DelayCostType::Continuous,0,Some(&bad),0.1).is_err());
        progress.observe(&p,DelayCostType::Continuous,0,Some(&good),0.2).unwrap();
        progress.observe(&p,DelayCostType::Continuous,2,Some(&good),0.3).unwrap();
        assert_eq!((progress.lower,progress.upper),(2,2));assert_eq!(progress.checkpoints.len(),2);
        assert!(progress.checkpoints[1].solution.is_none());
        assert!(progress.observe(&p,DelayCostType::Continuous,3,None,0.4).is_err());
        assert!(progress.observe(&p,DelayCostType::Continuous,1,None,0.4).is_err());
    }
}
