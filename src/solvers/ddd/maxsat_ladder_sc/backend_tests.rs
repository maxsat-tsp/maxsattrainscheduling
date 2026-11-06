use satcoder::{prelude::SymbolicModel, SatInstance, SatResultWithCore, SatSolverWithCore};

#[test]
fn cadical_is_native_and_cores_keep_the_assumption_polarity() {
    let mut solver = satcoder::solvers::cadical::Solver::new();
    assert!(solver.cadical.signature().to_ascii_lowercase().contains("cadical"));
    let a = solver.new_var();
    let b = solver.new_var();
    let c = solver.new_var();
    SatInstance::add_clause(&mut solver, vec![!a,!b]);
    let assumptions = vec![a,b,c];
    let core = match solver.solve_with_assumptions(assumptions.iter().copied()) {
        SatResultWithCore::Sat(_) => panic!("a AND b violates the hard clause"),
        SatResultWithCore::Unsat(core) => core.iter().copied().map(satcoder::Bool::Lit).collect::<Vec<_>>(),
    };
    assert!(!core.is_empty());
    assert!(core.iter().all(|literal| assumptions.contains(literal)));
    assert!(matches!(solver.solve_with_assumptions(core), SatResultWithCore::Unsat(_)));
    match solver.solve_with_assumptions([!a,b,c]) {
        SatResultWithCore::Sat(model) => {
            assert!(!model.value(&a));
            assert!(model.value(&b));
            assert!(model.value(&c));
        }
        SatResultWithCore::Unsat(_) => panic!("feasible assumptions must be SAT"),
    };
}
