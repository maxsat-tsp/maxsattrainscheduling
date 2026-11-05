import unittest

from select_core_variant import select


def rows(tag, variant, coverage, par2=10):
    return [dict(tag=tag, objective=o, assumptions=variant, sparse_costs="false",
                 instances="24", proven_optimal=str(n), conference_coverage=str(t),
                 par2_seconds=str(par2))
            for o, n, t in zip(("finsteps123", "infsteps180", "cont"), coverage, (24, 22, 20))]


class SelectionTests(unittest.TestCase):
    def test_sparse_and_order_variants_are_preserved_without_silent_combination(self):
        for field, variant in (("sparse_costs", "sparse"), ("resource_orders", "orders")):
            source = rows(variant, "legacy", (24, 22, 20))
            for row in source:
                row[field] = "true"
            self.assertEqual(select(source, {"errors": []})["selected"]["variant"], variant)
            for row in source:
                row["sparse_costs"] = row["resource_orders"] = "true"
            self.assertEqual(select(source, {"errors": []})["selected"]["variant"], "orders-sparse")

    def test_hybrid_variant_is_explicit(self):
        source = rows("hybrid", "legacy", (24, 22, 20))
        for row in source:
            row["sparse_costs"] = row["resource_orders"] = "true"
        self.assertEqual(select(source, {"errors": []})["selected"]["variant"], "orders-sparse")

    def test_transitivity_requires_orders_and_preserves_the_tested_variant(self):
        source = rows("transitive", "legacy", (24, 22, 20))
        for row in source:
            row["order_transitivity"] = "true"
        with self.assertRaises(ValueError):
            select(source, {"errors": []})
        for row in source:
            row["resource_orders"] = "true"
        self.assertEqual(select(source, {"errors": []})["selected"]["variant"], "orders-transitive")
        for row in source:
            row["sparse_costs"] = "true"
        with self.assertRaises(ValueError):
            select(source, {"errors": []})

    def test_does_not_combine_different_winners_or_promote_regression(self):
        decision = select(rows("full", "full", (24, 21, 21))
                          + rows("geom", "geometric", (24, 22, 19)), {"errors": []})
        self.assertIsNone(decision["selected"])

    def test_coverage_precedes_speed_and_equal_coverage_uses_par2(self):
        result = select(rows("full", "full", (24, 22, 20), 1)
                        + rows("geom", "geometric", (24, 23, 20), 100), {"errors": []})
        self.assertEqual(result["selected"]["variant"], "geometric")
        result = select(rows("full", "full", (24, 22, 20), 100)
                        + rows("geom", "geometric", (24, 22, 20), 1), {"errors": []})
        self.assertEqual(result["selected"]["variant"], "geometric")

    def test_rejects_partial_duplicate_or_failed_audits(self):
        source = rows("full", "full", (24, 22, 20))
        for malformed in (source[:2], source + [source[0]]):
            with self.assertRaises(ValueError):
                select(malformed, {"errors": []})
        with self.assertRaises(ValueError):
            select(source, {"errors": ["wrong cost"]})
