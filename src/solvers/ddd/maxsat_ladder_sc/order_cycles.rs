//! Separate a positive temporal cycle using only order variables already present.
//! A zero-weight cycle is allowed. With nonnegative edge weights, a strongly
//! connected component containing a positive edge has a forbidden positive cycle.
use satcoder::{Bool, Lit};
use std::collections::VecDeque;

pub(super) struct Topology {
    pub next: Vec<Option<usize>>,
    pub positive: Vec<bool>,
}

#[derive(Clone, Copy)]
pub(super) struct Arc<L: Lit> {
    pub from: usize,
    pub to: usize,
    pub positive: bool,
    /// Literal that enables this edge in the current full SAT model.
    pub guard: Option<Bool<L>>,
}

impl Topology {
    pub fn arcs<L: Lit>(&self) -> Vec<Arc<L>> {
        assert_eq!(self.next.len(), self.positive.len());
        self.next
            .iter()
            .enumerate()
            .filter_map(|(from, &to)| {
                to.map(|to| Arc {
                    from,
                    to,
                    positive: self.positive[from],
                    guard: None,
                })
            })
            .collect()
    }

    pub fn ordered<L: Lit>(&self, first: usize, second: usize, guard: Bool<L>) -> Arc<L> {
        // A nonfinal occupation ends when its train enters the NEXT visit.
        // Using entry(first)+travel(first) here would lose that constraint.
        Arc {
            from: self.next[first].unwrap_or(first),
            to: second,
            positive: self.next[first].is_none() && self.positive[first],
            guard: Some(guard),
        }
    }
}

pub(super) fn separate<L: Lit>(
    n: usize,
    mut arcs: Vec<Arc<L>>,
) -> Result<Option<Vec<Bool<L>>>, String> {
    if arcs
        .iter()
        .any(|e| e.from >= n || e.to >= n || e.guard == Some(false.into()))
    {
        return Err("invalid temporal edge or disabled guard".into());
    }
    arcs.sort_by_key(|e| (e.from, e.to, e.positive, e.guard));
    let mut forward = vec![Vec::new(); n];
    let mut reverse = vec![Vec::new(); n];
    for (i, e) in arcs.iter().enumerate() {
        forward[e.from].push(i);
        reverse[e.to].push(e.from);
    }
    // Iterative Kosaraju: no recursion even on long routes.
    let mut seen = vec![false; n];
    let mut finish = Vec::with_capacity(n);
    for start in 0..n {
        if seen[start] {
            continue;
        }
        seen[start] = true;
        let mut stack = vec![(start, 0)];
        while let Some((node, index)) = stack.last_mut() {
            if *index == forward[*node].len() {
                finish.push(*node);
                stack.pop();
            } else {
                let next = arcs[forward[*node][*index]].to;
                *index += 1;
                if !seen[next] {
                    seen[next] = true;
                    stack.push((next, 0));
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
            for &prev in &reverse[node] {
                if component[prev] == usize::MAX {
                    component[prev] = count;
                    stack.push(prev);
                }
            }
        }
        count += 1;
    }
    let Some((first, edge)) = arcs
        .iter()
        .enumerate()
        .find(|(_, e)| e.positive && component[e.from] == component[e.to])
    else {
        return Ok(None);
    };
    let mut parent = vec![None; n];
    let mut visited = vec![false; n];
    let mut queue = VecDeque::from([edge.to]);
    visited[edge.to] = true;
    while !visited[edge.from] {
        let node = queue.pop_front().ok_or("SCC has no return path")?;
        for &index in &forward[node] {
            let to = arcs[index].to;
            if component[to] == component[edge.from] && !visited[to] {
                visited[to] = true;
                parent[to] = Some(index);
                queue.push_back(to);
            }
        }
    }
    let mut cycle = vec![first];
    let mut node = edge.from;
    while node != edge.to {
        let index = parent[node].ok_or("missing temporal cycle parent")?;
        cycle.push(index);
        node = arcs[index].from;
    }
    let mut clause = cycle
        .iter()
        .filter_map(|&i| arcs[i].guard)
        .filter(|g| g.constant() != Some(true))
        .map(|g| !g)
        .collect::<Vec<_>>();
    clause.sort_unstable();
    clause.dedup();
    if clause.is_empty() {
        return Err("fixed temporal graph contains a positive cycle".into());
    }
    if clause.iter().any(|g| clause.binary_search(&!*g).is_ok()) {
        return Err("temporal cycle has contradictory active guards".into());
    }
    Ok(Some(clause))
}

#[cfg(test)]
mod tests {
    use super::*;
    use satcoder::solvers::minisat::Lit;
    fn guard(i: usize) -> Bool<Lit> {
        let mut solver = minisat::Solver::new();
        (0..i).map(|_| solver.new_lit()).last().unwrap().into()
    }
    fn edge(from: usize, to: usize, positive: bool, guard: Option<Bool<Lit>>) -> Arc<Lit> {
        Arc {
            from,
            to,
            positive,
            guard,
        }
    }

    #[test]
    fn dag_and_zero_cycles_are_allowed_but_positive_cycle_is_separated() {
        let a = guard(1);
        let b = guard(2);
        assert!(
            separate(3, vec![edge(0, 1, true, None), edge(1, 2, false, Some(a))])
                .unwrap()
                .is_none()
        );
        assert!(separate(
            2,
            vec![edge(0, 1, false, Some(a)), edge(1, 0, false, Some(b))]
        )
        .unwrap()
        .is_none());
        assert_eq!(
            separate(
                2,
                vec![edge(0, 1, true, Some(a)), edge(1, 0, false, Some(b))]
            )
            .unwrap(),
            Some(vec![!a, !b])
        );
    }

    #[test]
    fn four_node_cycle_needs_no_triangle_and_is_deterministic() {
        let a = guard(1);
        let b = guard(2);
        let mut edges = vec![
            edge(0, 1, true, None),
            edge(1, 2, false, Some(a)),
            edge(2, 3, true, None),
            edge(3, 0, false, Some(b)),
        ];
        let expected = separate(4, edges.clone()).unwrap();
        edges.reverse();
        assert_eq!(expected, separate(4, edges).unwrap());
        assert_eq!(expected, Some(vec![!a, !b]));
    }

    #[test]
    fn exact_exit_detects_cycle_that_entry_plus_travel_misses() {
        let t = Topology {
            next: vec![Some(1), None, None],
            positive: vec![true, true, true],
        };
        let a = guard(1);
        let b = guard(2);
        let mut edges = t.arcs();
        edges.push(t.ordered(0, 2, a));
        edges.push(t.ordered(2, 1, b));
        assert_eq!(separate(3, edges).unwrap(), Some(vec![!a, !b]));
        let mut weak = t.arcs();
        weak.push(edge(0, 2, true, Some(a)));
        weak.push(t.ordered(2, 1, b));
        assert_eq!(separate(3, weak).unwrap(), None);
    }

    #[test]
    fn invalid_fixed_cycles_and_guards_are_rejected() {
        assert!(separate::<Lit>(1, vec![edge(0, 0, true, None)]).is_err());
        assert!(separate(1, vec![edge(0, 0, true, Some(false.into()))]).is_err());
        assert!(separate(1, vec![edge(0, 0, true, Some(true.into()))]).is_err());
        let a = guard(1);
        assert!(separate(
            2,
            vec![edge(0, 1, true, Some(a)), edge(1, 0, false, Some(!a))]
        )
        .is_err());
    }

    #[test]
    fn every_enumerated_feasible_route_respects_the_cycle_cut() {
        // Routes 0->1 and 2->3. Choices 1 before 2 and 3 before 0
        // would require t0+2<=t1, t1+2<=t2, t2+2<=t3, t3+2<=t0.
        let a = guard(1);
        let b = guard(2);
        let topology = Topology {
            next: vec![Some(1), None, Some(3), None],
            positive: vec![true; 4],
        };
        let mut edges = topology.arcs();
        edges.push(topology.ordered(1, 2, a));
        edges.push(topology.ordered(3, 0, b));
        let clause = separate(4, edges).unwrap().unwrap();
        assert_eq!(clause, vec![!a, !b]);
        let mut feasible = 0;
        for t0 in 0..=6 {
            for t1 in 0..=6 {
                for t2 in 0..=6 {
                    for t3 in 0..=6 {
                        if t1 < t0 + 2 || t3 < t2 + 2 {
                            continue;
                        }
                        let a = t1 + 2 <= t2;
                        let b = t3 + 2 <= t0;
                        if !(a || t3 <= t1) || !(b || t1 <= t3) {
                            continue;
                        }
                        assert!(!a || !b);
                        feasible += 1;
                    }
                }
            }
        }
        assert!(feasible > 0);
    }
}
