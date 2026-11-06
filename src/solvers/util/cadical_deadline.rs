//! CaDiCaL with one wall-clock budget across all incremental queries.
//!
//! satcoder's SAT trait has no UNKNOWN variant. After a native interruption
//! returns to Rust, unwind with a private-purpose payload caught by the CLI.
//! This never converts an interrupted query into SAT or UNSAT and does not
//! invoke the panic hook. No unwinding occurs inside a native callback.
use satcoder::{Bool, SatInstance, SatModel, SatResult, SatResultWithCore, SatSolver, SatSolverWithCore};
use std::time::{Duration, Instant};

#[derive(Debug)]
pub struct DeadlineReached;

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Lit(i32);

impl std::ops::Not for Lit {
    type Output=Self;
    fn not(self)->Self { Self(-self.0) }
}

impl satcoder::Lit for Lit {
    type Var=i32;
    fn into_var(self)->(i32,bool) { (self.0.abs(),self.0<0) }
    fn from_var_sign(variable:i32,negative:bool)->Self {
        assert!(variable>0);
        Self(if negative {-variable} else {variable})
    }
}

#[derive(Debug)]
pub struct Solver {
    // Use the same linked native solver and defaults as the previous adapter.
    inner:satcoder::solvers::cadical::Solver,
    next_variable:i32,
    started:Instant,
    budget:Duration,
    native_interruptions:usize,
}

impl Solver {
    pub fn new(seconds:f64)->Self {
        assert!(seconds.is_finite() && seconds>=0.0);
        Self {inner:satcoder::solvers::cadical::Solver::new(),next_variable:1,
              started:Instant::now(),budget:Duration::from_secs_f64(seconds),native_interruptions:0}
    }

    pub fn signature(&self)->&str { self.inner.cadical.signature() }

    fn arm(&mut self) {
        let remaining=self.budget.saturating_sub(self.started.elapsed());
        if remaining.is_zero() { std::panic::resume_unwind(Box::new(DeadlineReached)); }
        // The native Timeout resets its start time for each query, so pass
        // only the remaining global budget, never the original full timeout.
        self.inner.cadical.set_callbacks(Some(satcoder::solvers::cadical::Timeout::new(remaining.as_secs_f32())));
    }

    fn interrupted(&mut self)->! {
        self.native_interruptions+=1;
        std::panic::resume_unwind(Box::new(DeadlineReached));
    }
}

impl SatInstance<Lit> for Solver {
    fn new_var(&mut self)->Bool<Lit> {
        let literal=Lit(self.next_variable);
        self.next_variable+=1;
        Bool::Lit(literal)
    }
    fn add_clause<IL:Into<Bool<Lit>>,I:IntoIterator<Item=IL>>(&mut self,clause:I) {
        let mut literals=Vec::new();
        for term in clause {
            match term.into() {
                Bool::Const(true)=>return,
                Bool::Const(false)=>{},
                Bool::Lit(literal)=>literals.push(literal.0),
            }
        }
        self.inner.cadical.add_clause(literals);
    }
}

struct Model<'a>(&'a Solver);
impl SatModel for Model<'_> {
    type Lit=Lit;
    fn lit_value(&self,literal:&Lit)->bool { self.0.inner.cadical.value(literal.0).unwrap_or(false) }
}

impl SatSolver for Solver {
    type Lit=Lit;
    fn solve(&mut self)->SatResult<'_,Lit> {
        self.arm();
        match self.inner.cadical.solve() {
            Some(true)=>SatResult::Sat(Box::new(Model(self))),
            Some(false)=>SatResult::Unsat,
            None=>self.interrupted(),
        }
    }
}

impl SatSolverWithCore for Solver {
    type Lit=Lit;
    fn solve_with_assumptions(&mut self,assumptions:impl IntoIterator<Item=Bool<Lit>>)->SatResultWithCore<'_,Lit> {
        let assumptions=assumptions.into_iter().filter_map(|term| match term {
            Bool::Const(true)=>None,
            Bool::Const(false)=>panic!("false assumption is not a supported MaxSAT selector"),
            Bool::Lit(literal)=>Some(literal),
        }).collect::<Vec<_>>();
        self.arm();
        match self.inner.cadical.solve_with(assumptions.iter().map(|literal|literal.0)) {
            Some(true)=>SatResultWithCore::Sat(Box::new(Model(self))),
            Some(false)=>SatResultWithCore::Unsat(assumptions.into_iter()
                .filter(|literal|self.inner.cadical.failed(literal.0)).collect::<Vec<_>>().into_boxed_slice()),
            None=>self.interrupted(),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use satcoder::prelude::SymbolicModel;
    use std::panic::{catch_unwind,AssertUnwindSafe};

    #[test]
    fn models_cores_and_incremental_clauses_match_the_original_adapter() {
        let mut solver=Solver::new(5.0);
        assert!(solver.signature().contains("cadical"));
        let a=solver.new_var(); let b=solver.new_var();
        solver.add_clause([!a,!b]);
        let core=match solver.solve_with_assumptions([a,b]) {
            SatResultWithCore::Unsat(core)=>core.iter().copied().map(Bool::Lit).collect::<Vec<_>>(),
            _=>panic!("incompatible assumptions must be UNSAT"),
        };
        assert!(!core.is_empty() && core.iter().all(|literal|[a,b].contains(literal)));
        assert!(matches!(solver.solve_with_assumptions(core),SatResultWithCore::Unsat(_)));
        match solver.solve_with_assumptions([!a,b]) {
            SatResultWithCore::Sat(model)=>assert!(!model.value(&a) && model.value(&b)),
            _=>panic!("feasible assumptions must be SAT"),
        };
        solver.add_clause([a]); solver.add_clause([b]);
        assert!(matches!(solver.solve(),SatResult::Unsat));
    }

    #[test]
    fn the_budget_is_not_reset_between_sat_queries() {
        let mut solver=Solver::new(5.0);
        assert!(matches!(solver.solve(),SatResult::Sat(_)));
        solver.started=Instant::now()-Duration::from_secs(6);
        let result=catch_unwind(AssertUnwindSafe(|| { solver.solve(); }));
        assert!(result.unwrap_err().is::<DeadlineReached>());
        assert_eq!(solver.native_interruptions,0);
    }

    #[test]
    fn native_unknown_becomes_a_deadline_not_a_false_unsat_core() {
        let mut solver=Solver::new(0.1);
        // An UNSAT pigeonhole formula requiring substantially more than 100 ms.
        let variables=(0..20).map(|_|(0..19).map(|_|solver.new_var()).collect::<Vec<_>>()).collect::<Vec<_>>();
        for pigeon in &variables { solver.add_clause(pigeon.iter().copied()); }
        for hole in 0..19 { for a in 0..20 { for b in a+1..20 {
            solver.add_clause([!variables[a][hole],!variables[b][hole]]);
        }}}
        let result=catch_unwind(AssertUnwindSafe(|| { solver.solve_with_assumptions([]); }));
        assert!(result.unwrap_err().is::<DeadlineReached>());
        assert_eq!(solver.native_interruptions,1);
    }
}
