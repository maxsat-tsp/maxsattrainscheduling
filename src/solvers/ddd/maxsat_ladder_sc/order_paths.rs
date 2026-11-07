//! Conditional earliest-time propagation through the resource orders selected
//! by a full SAT model. Every learned clause is witnessed by a temporal path.
use satcoder::{Bool, Lit};
use std::collections::{BTreeSet, VecDeque};

pub(super) struct Topology {
    pub next: Vec<Option<usize>>,
    pub travel: Vec<i32>,
    pub earliest: Vec<i32>,
}

#[derive(Clone, Copy)]
pub(super) struct Edge<L: Lit> {
    pub from: usize,
    pub to: usize,
    pub weight: i32,
    pub guard: Option<Bool<L>>,
}

#[derive(Debug, PartialEq, Eq)]
pub(super) enum Cut<L: Lit> {
    Cycle(Vec<Bool<L>>),
    Path {
        visit: usize,
        time: i32,
        prefix: Vec<Bool<L>>,
    },
}

impl Topology {
    pub fn edges<L: Lit>(&self) -> Vec<Edge<L>> {
        self.next
            .iter()
            .enumerate()
            .filter_map(|(from, &to)| {
                to.map(|to| Edge {
                    from,
                    to,
                    weight: self.travel[from],
                    guard: None,
                })
            })
            .collect()
    }

    pub fn ordered<L: Lit>(&self, first: usize, second: usize, guard: Bool<L>) -> Edge<L> {
        Edge {
            from: self.next[first].unwrap_or(first),
            to: second,
            weight: if self.next[first].is_some() {
                0
            } else {
                self.travel[first]
            },
            guard: Some(guard),
        }
    }
}

// Immutable witness links: extending a path never changes another node's proof.
struct Step<L: Lit> {
    previous: Option<usize>,
    guard: Bool<L>,
}

fn extend<L: Lit>(
    steps: &mut Vec<Step<L>>,
    previous: Option<usize>,
    guard: Option<Bool<L>>,
) -> Option<usize> {
    match guard {
        Some(g) if g.constant() != Some(true) => {
            let index = steps.len();
            steps.push(Step { previous, guard: g });
            Some(index)
        }
        _ => previous,
    }
}

fn prefix<L: Lit>(steps: &[Step<L>], mut witness: Option<usize>) -> Result<Vec<Bool<L>>, String> {
    let mut result = Vec::new();
    while let Some(i) = witness {
        result.push(!steps[i].guard);
        witness = steps[i].previous;
    }
    result.sort_unstable();
    result.dedup();
    if result.iter().any(|g| result.binary_search(&!*g).is_ok()) {
        return Err("temporal path contains contradictory active orders".into());
    }
    Ok(result)
}

/// Return one violated path implication, prioritizing objective increase then
/// time increase. A positive cycle is separated before propagating path bounds.
pub(super) fn separate<L: Lit>(
    topology: &Topology,
    mut edges: Vec<Edge<L>>,
    model_times: &[i32],
    priority: impl Fn(usize, i32, i32) -> usize,
) -> Result<Option<Cut<L>>, String> {
    let n = topology.next.len();
    if topology.travel.len() != n
        || topology.earliest.len() != n
        || model_times.len() != n
        || topology.travel.iter().any(|&d| d < 0)
        || edges
            .iter()
            .any(|e| e.from >= n || e.to >= n || e.weight < 0 || e.guard == Some(false.into()))
    {
        return Err("invalid nonnegative temporal graph".into());
    }
    edges.sort_by_key(|e| (e.from, e.to, e.weight, e.guard));
    let cycle = super::order_cycles::separate(
        n,
        edges
            .iter()
            .map(|e| super::order_cycles::Arc {
                from: e.from,
                to: e.to,
                positive: e.weight > 0,
                guard: e.guard,
            })
            .collect(),
    )?;
    if let Some(clause) = cycle {
        return Ok(Some(Cut::Cycle(clause)));
    }

    let mut forward = vec![Vec::new(); n];
    let mut reverse = vec![Vec::new(); n];
    for (i, e) in edges.iter().enumerate() {
        forward[e.from].push(i);
        reverse[e.to].push(e.from);
    }
    let mut visited = vec![false; n];
    let mut finish = Vec::with_capacity(n);
    for start in 0..n {
        if visited[start] {
            continue;
        }
        visited[start] = true;
        let mut stack = vec![(start, 0)];
        while let Some((node, index)) = stack.last_mut() {
            if *index == forward[*node].len() {
                finish.push(*node);
                stack.pop();
            } else {
                let to = edges[forward[*node][*index]].to;
                *index += 1;
                if !visited[to] {
                    visited[to] = true;
                    stack.push((to, 0));
                }
            }
        }
    }
    let mut component = vec![usize::MAX; n];
    let mut count = 0;
    for &start in finish.iter().rev() {
        if component[start] != usize::MAX {
            continue;
        }
        component[start] = count;
        let mut stack = vec![start];
        while let Some(node) = stack.pop() {
            for &from in &reverse[node] {
                if component[from] == usize::MAX {
                    component[from] = count;
                    stack.push(from);
                }
            }
        }
        count += 1;
    }
    // With no positive cycle, all edges internal to an SCC have weight zero.
    let mut members = vec![Vec::new(); count];
    let mut indegree = vec![0usize; count];
    for node in 0..n {
        members[component[node]].push(node);
    }
    for e in &edges {
        if component[e.from] != component[e.to] {
            indegree[component[e.to]] += 1;
        } else if e.weight != 0 {
            return Err("positive edge survived cycle separation".into());
        }
    }
    let mut roots = members
        .iter()
        .map(|nodes| {
            *nodes
                .iter()
                .max_by_key(|&&v| (topology.earliest[v], std::cmp::Reverse(v)))
                .unwrap()
        })
        .collect::<Vec<_>>();
    let mut best = roots
        .iter()
        .map(|&r| topology.earliest[r])
        .collect::<Vec<_>>();
    let mut incoming = vec![None; count];
    let mut witnesses = vec![None; n];
    let mut bounds = vec![0; n];
    let mut steps = Vec::new();
    let mut ready = (0..count)
        .filter(|&c| indegree[c] == 0)
        .collect::<BTreeSet<_>>();
    visited.fill(false);
    let mut processed = 0;
    while let Some(c) = ready.pop_first() {
        processed += 1;
        let root = roots[c];
        let mut queue = VecDeque::from([root]);
        bounds[root] = best[c];
        witnesses[root] = incoming[c];
        visited[root] = true;
        while let Some(node) = queue.pop_front() {
            for &i in &forward[node] {
                let e = edges[i];
                if component[e.to] == c && !visited[e.to] {
                    visited[e.to] = true;
                    bounds[e.to] = best[c];
                    witnesses[e.to] = extend(&mut steps, witnesses[node], e.guard);
                    queue.push_back(e.to);
                }
            }
        }
        for &node in &members[c] {
            if !visited[node] {
                return Err("zero-weight component is not reachable from its root".into());
            }
            for &i in &forward[node] {
                let e = edges[i];
                let target = component[e.to];
                if target == c {
                    continue;
                }
                let candidate = bounds[node]
                    .checked_add(e.weight)
                    .filter(|&t| t < i32::MAX)
                    .ok_or("temporal bound exceeds finite i32 time domain")?;
                if candidate > best[target] {
                    best[target] = candidate;
                    roots[target] = e.to;
                    incoming[target] = extend(&mut steps, witnesses[node], e.guard);
                }
                indegree[target] -= 1;
                if indegree[target] == 0 {
                    ready.insert(target);
                }
            }
        }
    }
    if processed != count {
        return Err("component graph is not acyclic".into());
    }
    let chosen = (0..n)
        .filter(|&v| bounds[v] > model_times[v])
        .max_by_key(|&v| {
            (
                priority(v, bounds[v], model_times[v]),
                i64::from(bounds[v]) - i64::from(model_times[v]),
                std::cmp::Reverse(v),
            )
        });
    if let Some(visit) = chosen {
        Ok(Some(Cut::Path {
            visit,
            time: bounds[visit],
            prefix: prefix(&steps, witnesses[visit])?,
        }))
    } else {
        Ok(None)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use satcoder::solvers::minisat::Lit;
    fn g(n: usize) -> Bool<Lit> {
        let mut s = minisat::Solver::new();
        (0..n).map(|_| s.new_lit()).last().unwrap().into()
    }
    fn e(from: usize, to: usize, weight: i32, guard: Option<Bool<Lit>>) -> Edge<Lit> {
        Edge {
            from,
            to,
            weight,
            guard,
        }
    }
    fn t(earliest: Vec<i32>) -> Topology {
        let n = earliest.len();
        Topology {
            earliest,
            next: vec![None; n],
            travel: vec![0; n],
        }
    }

    #[test]
    fn whole_path_yields_exact_bound_and_only_its_required_guards() {
        let a = g(1);
        let b = g(2);
        let c = g(3);
        let edges = vec![
            e(0, 1, 3, Some(a)),
            e(1, 2, 4, None),
            e(2, 3, 0, Some(b)),
            e(4, 3, 1, Some(c)),
        ];
        let expected = Some(Cut::Path {
            visit: 3,
            time: 12,
            prefix: vec![!a, !b],
        });
        let mut reversed = edges.clone();
        reversed.reverse();
        assert_eq!(
            separate(
                &t(vec![5, 0, 0, 0, 0]),
                edges,
                &[5, 8, 12, 0, 0],
                |_, _, _| 0
            )
            .unwrap(),
            expected
        );
        assert_eq!(
            separate(
                &t(vec![5, 0, 0, 0, 0]),
                reversed,
                &[5, 8, 12, 0, 0],
                |_, _, _| 0
            )
            .unwrap(),
            expected
        );
    }

    #[test]
    fn zero_cycles_propagate_external_and_earliest_bounds_without_false_conflicts() {
        let a = g(1);
        let b = g(2);
        let c = g(3);
        let edges = vec![
            e(0, 1, 0, Some(a)),
            e(1, 0, 0, Some(b)),
            e(2, 0, 3, Some(c)),
        ];
        assert_eq!(
            separate(&t(vec![0, 0, 5]), edges.clone(), &[8, 0, 5], |_, _, _| 0).unwrap(),
            Some(Cut::Path {
                visit: 1,
                time: 8,
                prefix: vec![!a, !c]
            })
        );
        assert_eq!(
            separate(&t(vec![0, 0, 5]), edges, &[8, 8, 5], |_, _, _| 0).unwrap(),
            None
        );
        assert_eq!(
            separate(
                &t(vec![7, 0]),
                vec![e(0, 1, 0, Some(a)), e(1, 0, 0, Some(b))],
                &[7, 0],
                |_, _, _| 0
            )
            .unwrap(),
            Some(Cut::Path {
                visit: 1,
                time: 7,
                prefix: vec![!a]
            })
        );
    }

    #[test]
    fn positive_cycle_is_blocked_before_path_propagation() {
        let a = g(1);
        let b = g(2);
        assert_eq!(
            separate(
                &t(vec![0, 0]),
                vec![e(0, 1, 2, Some(a)), e(1, 0, 0, Some(b))],
                &[0, 0],
                |_, _, _| 0
            )
            .unwrap(),
            Some(Cut::Cycle(vec![!a, !b]))
        );
    }

    #[test]
    fn objective_increase_precedes_large_time_shift_at_a_dummy_visit() {
        let a = g(1);
        assert_eq!(
            separate(
                &t(vec![0, 0, 0]),
                vec![e(0, 1, 3, Some(a)), e(0, 2, 20, None)],
                &[0, 0, 0],
                |v, _, _| usize::from(v == 1)
            )
            .unwrap(),
            Some(Cut::Path {
                visit: 1,
                time: 3,
                prefix: vec![!a]
            })
        );
    }

    #[test]
    fn exact_exit_and_fixed_route_edges_use_actual_travel_weights() {
        let topology = Topology {
            next: vec![Some(1), None, None],
            travel: vec![3, 2, 4],
            earliest: vec![5, 0, 0],
        };
        let a = g(1);
        let mut edges = topology.edges();
        edges.push(topology.ordered(0, 2, a));
        assert_eq!(
            separate(&topology, edges, &[5, 8, 0], |_, _, _| 0).unwrap(),
            Some(Cut::Path {
                visit: 2,
                time: 8,
                prefix: vec![!a]
            })
        );
        let mut edges = topology.edges();
        edges.push(topology.ordered(1, 2, a));
        assert_eq!(
            separate(&topology, edges, &[5, 8, 0], |_, _, _| 0).unwrap(),
            Some(Cut::Path {
                visit: 2,
                time: 10,
                prefix: vec![!a]
            })
        );
    }

    #[test]
    fn path_clause_preserves_every_small_feasible_guarded_assignment() {
        let a = g(1);
        let b = g(2);
        let edges = vec![e(0, 1, 2, Some(a)), e(1, 2, 1, Some(b))];
        let cut = separate(&t(vec![1, 0, 0]), edges, &[1, 3, 0], |_, _, _| 0)
            .unwrap()
            .unwrap();
        assert_eq!(
            cut,
            Cut::Path {
                visit: 2,
                time: 4,
                prefix: vec![!a, !b]
            }
        );
        for mask in 0..4 {
            for x in 1..=6 {
                for y in 0..=6 {
                    for z in 0..=6 {
                        let av = mask & 1 != 0;
                        let bv = mask & 2 != 0;
                        if av && y < x + 2 || bv && z < y + 1 {
                            continue;
                        }
                        assert!(!av || !bv || z >= 4);
                    }
                }
            }
        }
    }

    #[test]
    fn long_chain_uses_iterative_linear_propagation_and_checked_times() {
        let n = 10000;
        let a = g(1);
        let edges = (0..n - 1).map(|i| e(i, i + 1, 1, Some(a))).collect();
        assert_eq!(
            separate(&t(vec![0; n]), edges, &vec![0; n], |_, _, _| 0).unwrap(),
            Some(Cut::Path {
                visit: n - 1,
                time: n as i32 - 1,
                prefix: vec![!a]
            })
        );
        assert!(separate(
            &t(vec![i32::MAX - 1, 0]),
            vec![e(0, 1, 2, None)],
            &[0, 0],
            |_, _, _| 0
        )
        .is_err());
        assert!(separate(
            &t(vec![0, 0]),
            vec![e(0, 1, -1, None)],
            &[0, 0],
            |_, _, _| 0
        )
        .is_err());
    }
}
