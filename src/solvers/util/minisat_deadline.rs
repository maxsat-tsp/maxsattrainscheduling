//! MiniSAT's native three-way result plus its asynchronous interrupt API.
//! Only the core-reduction experiment uses this adapter; legacy dispatch is
//! unchanged. No UNKNOWN result is ever exposed as an UNSAT core.
use super::cadical_deadline::DeadlineReached;
use minisat::sys;
use satcoder::{
    Bool, SatInstance, SatModel, SatResult, SatResultWithCore, SatSolver, SatSolverWithCore,
};
use std::{
    sync::mpsc,
    thread,
    time::{Duration, Instant},
};

#[derive(Clone, Copy, Debug, PartialEq, Eq, PartialOrd, Ord, Hash)]
pub struct Lit(i32);
impl std::ops::Not for Lit {
    type Output = Self;
    fn not(self) -> Self {
        Self(unsafe { sys::minisat_negate(self.0) })
    }
}
impl satcoder::Lit for Lit {
    type Var = i32;
    fn into_var(self) -> (i32, bool) {
        unsafe { (sys::minisat_var(self.0), sys::minisat_sign(self.0) > 0) }
    }
    fn from_var_sign(variable: i32, negative: bool) -> Self {
        let literal = Self(unsafe { sys::minisat_mkLit(variable) });
        if negative {
            !literal
        } else {
            literal
        }
    }
}

pub struct Solver {
    ptr: *mut sys::minisat_solver_t,
    started: Instant,
    budget: Duration,
    finished: mpsc::Sender<()>,
    watchdog: Option<thread::JoinHandle<()>>,
    signature: &'static str,
}

impl std::fmt::Debug for Solver {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("MiniSatDeadline")
            .field("signature", &self.signature)
            .finish()
    }
}

impl Solver {
    pub fn new(seconds: f64) -> Self {
        assert!(seconds.is_finite() && seconds >= 0.0);
        let started = Instant::now();
        let budget = Duration::from_secs_f64(seconds);
        let signature = minisat::Solver::new().solver_name();
        assert!(
            signature.contains("MiniSAT"),
            "unexpected MiniSAT build backend"
        );
        // Match minisat-rs Solver::new: disable elimination before allocating
        // variables. No decision, restart, polarity or conflict budget changes.
        let ptr = unsafe { sys::minisat_new() };
        assert!(!ptr.is_null());
        unsafe {
            sys::minisat_eliminate(ptr, 1);
            sys::minisat_no_budget(ptr);
        }
        let (finished, notification) = mpsc::channel();
        let address = ptr as usize;
        let wait = budget.saturating_sub(started.elapsed());
        let watchdog = thread::spawn(move || {
            if matches!(
                notification.recv_timeout(wait),
                Err(mpsc::RecvTimeoutError::Timeout)
            ) {
                // MiniSAT explicitly supports interrupt from another thread.
                // Drop joins this watchdog before deleting the native solver,
                // so the pointer remains valid throughout this one API call.
                unsafe {
                    sys::minisat_interrupt(address as *mut sys::minisat_solver_t);
                }
            }
        });
        Self {
            ptr,
            started,
            budget,
            finished,
            watchdog: Some(watchdog),
            signature,
        }
    }

    pub fn signature(&self) -> &str {
        self.signature
    }

    fn check_deadline(&self) {
        if self.started.elapsed() >= self.budget {
            std::panic::resume_unwind(Box::new(DeadlineReached));
        }
    }
}

impl Drop for Solver {
    fn drop(&mut self) {
        let _ = self.finished.send(());
        if let Some(watchdog) = self.watchdog.take() {
            let _ = watchdog.join();
        }
        // No timer thread can touch ptr after this point.
        unsafe {
            sys::minisat_delete(self.ptr);
        }
    }
}

impl SatInstance<Lit> for Solver {
    fn new_var(&mut self) -> Bool<Lit> {
        Bool::Lit(Lit(unsafe { sys::minisat_newLit(self.ptr) }))
    }
    fn add_clause<IL: Into<Bool<Lit>>, I: IntoIterator<Item = IL>>(&mut self, clause: I) {
        let mut literals = Vec::new();
        for term in clause {
            match term.into() {
                Bool::Const(true) => return,
                Bool::Const(false) => {}
                Bool::Lit(literal) => literals.push(literal.0),
            }
        }
        unsafe {
            sys::minisat_addClause_begin(self.ptr);
            for literal in literals {
                sys::minisat_addClause_addLit(self.ptr, literal);
            }
            sys::minisat_addClause_commit(self.ptr);
        }
    }
}

struct Model<'a>(&'a Solver);
impl SatModel for Model<'_> {
    type Lit = Lit;
    fn lit_value(&self, literal: &Lit) -> bool {
        unsafe { sys::minisat_modelValue_Lit(self.0.ptr, literal.0) == sys::minisat_get_l_True() }
    }
}

impl SatSolverWithCore for Solver {
    type Lit = Lit;
    fn solve_with_assumptions(
        &mut self,
        assumptions: impl IntoIterator<Item = Bool<Lit>>,
    ) -> SatResultWithCore<'_, Lit> {
        self.check_deadline();
        unsafe {
            sys::minisat_solve_begin(self.ptr);
        }
        for term in assumptions {
            match term {
                Bool::Const(true) => {}
                Bool::Const(false) => panic!("false assumption is not a supported MaxSAT selector"),
                Bool::Lit(literal) => unsafe {
                    sys::minisat_solve_addLit(self.ptr, literal.0);
                },
            }
        }
        let result = unsafe { sys::minisat_limited_solve_commit(self.ptr) };
        if result == unsafe { sys::minisat_get_l_Undef() } {
            // The native search has returned to Rust before unwinding.
            std::panic::resume_unwind(Box::new(DeadlineReached));
        }
        self.check_deadline();
        if result == unsafe { sys::minisat_get_l_True() } {
            SatResultWithCore::Sat(Box::new(Model(self)))
        } else {
            assert_eq!(result, unsafe { sys::minisat_get_l_False() });
            let core = (0..unsafe { sys::minisat_conflict_len(self.ptr) })
                .map(|index| !Lit(unsafe { sys::minisat_conflict_nthLit(self.ptr, index) }))
                .collect::<Vec<_>>();
            SatResultWithCore::Unsat(core.into_boxed_slice())
        }
    }
}
impl SatSolver for Solver {
    type Lit = Lit;
    fn solve(&mut self) -> SatResult<'_, Lit> {
        match self.solve_with_assumptions([]) {
            SatResultWithCore::Sat(model) => SatResult::Sat(model),
            SatResultWithCore::Unsat(_) => SatResult::Unsat,
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use satcoder::prelude::SymbolicModel;
    use std::panic::{catch_unwind, AssertUnwindSafe};

    #[test]
    fn assumptions_cores_models_and_added_clauses_remain_correct() {
        let mut solver = Solver::new(5.0);
        let a = solver.new_var();
        let b = solver.new_var();
        solver.add_clause([!a, !b]);
        let core = match solver.solve_with_assumptions([a, b]) {
            SatResultWithCore::Unsat(core) => {
                core.iter().copied().map(Bool::Lit).collect::<Vec<_>>()
            }
            _ => panic!("incompatible assumptions must be UNSAT"),
        };
        assert!(!core.is_empty() && core.iter().all(|literal| [a, b].contains(literal)));
        assert!(matches!(
            solver.solve_with_assumptions(core),
            SatResultWithCore::Unsat(_)
        ));
        match solver.solve_with_assumptions([!a, b]) {
            SatResultWithCore::Sat(model) => assert!(!model.value(&a) && model.value(&b)),
            _ => panic!("feasible assumptions must be SAT"),
        };
        solver.add_clause([a]);
        solver.add_clause([b]);
        assert!(matches!(solver.solve(), SatResult::Unsat));
    }

    #[test]
    fn global_deadline_is_not_reset_by_another_query() {
        let mut solver = Solver::new(5.0);
        assert!(matches!(solver.solve(), SatResult::Sat(_)));
        solver.started = Instant::now() - Duration::from_secs(6);
        let result = catch_unwind(AssertUnwindSafe(|| {
            solver.solve();
        }));
        assert!(result.unwrap_err().is::<DeadlineReached>());
    }

    #[test]
    fn a_native_interruption_does_not_become_false_unsat() {
        let mut solver = Solver::new(0.1);
        let variables = (0..20)
            .map(|_| (0..19).map(|_| solver.new_var()).collect::<Vec<_>>())
            .collect::<Vec<_>>();
        for pigeon in &variables {
            solver.add_clause(pigeon.iter().copied());
        }
        for hole in 0..19 {
            for a in 0..20 {
                for b in a + 1..20 {
                    solver.add_clause([!variables[a][hole], !variables[b][hole]]);
                }
            }
        }
        let result = catch_unwind(AssertUnwindSafe(|| {
            solver.solve_with_assumptions([]);
        }));
        assert!(result.unwrap_err().is::<DeadlineReached>());
    }

    #[test]
    fn dropping_a_solver_cancels_its_timer_before_deleting_native_state() {
        let start = Instant::now();
        drop(Solver::new(60.0));
        assert!(start.elapsed() < Duration::from_secs(2));
    }
}
