import itertools
import random
import unittest
from dataclasses import replace
from collections import Counter
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from src.problem import compatible, GROUP_MODES
from src.planning import generate_tickets_report
from src.models import Question
from src.planning import plan_tickets
from src.reconstruction import restore_tickets
from src.reconstruction import unrank_composition
from src.io import read_questions
from src.problem import balanced_cost, group_questions


def candidates(questions, size, mode):
    return [tuple(group) for group in itertools.combinations(questions, size)
            if all(compatible(a, b, mode) for a, b in itertools.combinations(group, 2))]


def weight_score(tickets, target):
    deviations = [abs(sum(Fraction(str(q.weight)) for q in t.questions) - Fraction(str(target)))
                  for t in tickets]
    return max(deviations), sum(deviations)


class SumSelectionTests(unittest.TestCase):
    def assert_valid(self, questions, result, size, count, mode):
        self.assertEqual(len(result.tickets), count)
        keys = [frozenset(q.id for q in t.questions) for t in result.tickets]
        self.assertEqual(len(set(keys)), count)
        for ticket in result.tickets:
            self.assertEqual(len(ticket.questions), size)
            self.assertEqual(len(set(q.id for q in ticket.questions)), size)
            self.assertTrue(all(compatible(a, b, mode) for a, b in itertools.combinations(ticket.questions, 2)))
        self.assertTrue(result.optimal)
        self.assertEqual(result.proven_objectives, 2)
        self.assertEqual(result.objective_count, 2)
        self.assertEqual(result.objective_mode, 'weight-first')
        self.assertEqual(result.frequency_guarantee, 'within-class')
        usage = Counter(q.id for t in result.tickets for q in t.questions)
        for c in group_questions(questions, mode):
            counts = [usage[questions[i].id] for i in c.members]
            self.assertLessEqual(max(counts) - min(counts), 1)

    def test_all_methods_match_exhaustive_weight_optimum(self):
        rng = random.Random(38)
        for trial in range(8):
            questions = [Question(str(i), str(i), rng.choice((0.1, 0.3, 0.7)), str(rng.randrange(3)))
                         for i in range(6)]
            for mode in GROUP_MODES:
                for size in (1, 2, 3):
                    pool = candidates(questions, size, mode)
                    count = rng.randrange(1, 5)
                    target = rng.choice((0.3, 0.8, 1.2))
                    ordered = sorted(abs(sum(Fraction(str(q.weight)) for q in t) - Fraction(str(target)))
                                     for t in pool)
                    for method in ('auto', 'sum-dp', 'enumerate', 'dp', 'cp-sat-types', 'cp-sat'):
                        with self.subTest(trial=trial, mode=mode, size=size, method=method):
                            if count > len(pool):
                                with self.assertRaises(ValueError):
                                    generate_tickets_report(questions, size, count, mode,
                                                            target_weight=target, algorithm=method)
                                continue
                            result = generate_tickets_report(questions, size, count, mode,
                                                             target_weight=target, algorithm=method)
                            self.assert_valid(questions, result, size, count, mode)
                            self.assertEqual(weight_score(result.tickets, target),
                                             (ordered[count-1], sum(ordered[:count])))

    def test_compressed_counts_and_unranking_match_all_combinations(self):
        # Пять одинаковых профилей: проверяется нечётная степень и исходные темы.
        questions = [Question(f'{g}_{i}', f'{g}_{i}', w, str(g))
                     for g in range(5) for i, w in enumerate((1, 1, 3))]
        for mode in GROUP_MODES:
            for size in (1, 2, 3):
                with self.subTest(mode=mode, size=size):
                    pool = candidates(questions, size, mode)
                    plan = plan_tickets(questions, size, len(pool), mode, target_weight=4)
                    sums = Counter(sum(q.weight for q in t) for t in pool)
                    actual = {total: n for (taken, total), n in plan.selection.sum_plan.root.table.items()
                              if taken == size}
                    self.assertEqual(actual, sums)
                    class_of = {questions[i].id: c for c, item in enumerate(plan.classes) for i in item.members}
                    expected_types = Counter(tuple(sorted(Counter(class_of[q.id] for q in t).items())) for t in pool)
                    actual_types = Counter(unrank_composition(plan.selection.sum_plan, total, rank)
                                           for total, n in sums.items() for rank in range(n))
                    self.assertEqual(actual_types, expected_types)
                    result = restore_tickets(plan)
                    self.assert_valid(questions, result, size, len(pool), mode)
                    self.assertEqual({frozenset(q.id for q in t.questions) for t in result.tickets},
                                     {frozenset(q.id for q in t) for t in pool})

    def test_repeated_profiles_reduce_tables_for_many_topics(self):
        questions = [Question(f'{g}_{i}', f'{g}_{i}', w, str(g))
                     for g in range(64) for i, w in enumerate((1, 2))]
        result = generate_tickets_report(questions, 64, 100, 'different', target_weight=96)
        self.assert_valid(questions, result, 64, 100, 'different')
        self.assertEqual(result.algorithm, 'profile-sum-dp')
        self.assertEqual(result.diagnostics['topic_profiles'], 1)
        self.assertEqual(weight_score(result.tickets, 96), (0, 0))
        # Повторные степени не сохраняют таблицу на каждую из 64 тем.
        self.assertLess(result.diagnostics['sum_states'], 200)

    def test_unranking_skips_large_empty_topic_subtrees(self):
        topic_count, size = 1024, 3
        questions = [Question(str(i), str(i), 1, str(i)) for i in range(topic_count)]
        plan = plan_tickets(questions, size, 1, 'different', target_weight=size)
        sums = plan.selection.sum_plan
        visits = 0
        class CountingTable(dict):
            def items(self):
                nonlocal visits
                visits += 1
                return super().items()
        memo = {}
        def instrument(node):
            if id(node) not in memo:
                memo[id(node)] = replace(node, table=CountingTable(node.table),
                                         children=tuple(instrument(child) for child in node.children))
            return memo[id(node)]
        sums = replace(sums, root=instrument(sums.root))
        capacity = sums.root.table[size, Fraction(size)]
        composition = unrank_composition(sums, Fraction(size), capacity // 2)
        self.assertEqual(sum(amount for _, amount in composition), size)
        # Число посещённых таблиц ограничивается путями выбранных тем,
        # а не всеми исходными темами; без пропуска пустых ветвей их 1023.
        self.assertLessEqual(visits, size * topic_count.bit_length())

    def test_selection_does_not_restore_and_restoration_is_repeatable(self):
        questions = [Question(f'{g}_{i}', f'{g}_{i}', i + 1, str(g))
                     for g in range(4) for i in range(3)]
        with patch('src.reconstruction.materialize_types', side_effect=AssertionError('Раннее восстановление')):
            plan = plan_tickets(questions, 3, 17, 'different', target_weight=5)
        self.assertEqual(plan.selection.types, ())
        self.assertEqual(plan.selection.amounts, ())
        self.assertEqual(restore_tickets(plan), restore_tickets(plan))

    def test_resource_fallbacks_and_explicit_modes(self):
        questions = [Question(str(i), str(i), 1 + i // 2) for i in range(8)]
        with self.assertRaisesRegex(ValueError, 'DP'):
            generate_tickets_report(questions, 3, 4, target_weight=7,
                                    algorithm='sum-dp', max_dp_states=1)
        result = generate_tickets_report(questions, 3, 4, target_weight=7, max_dp_states=1)
        self.assertEqual(result.algorithm, 'weight-types')
        self.assertIn('sum_dp_fallback', result.diagnostics)
        self.assert_valid(questions, result, 3, 4, 'ignore')
        direct = generate_tickets_report(questions, 3, 4, target_weight=7,
                                         max_dp_states=1, max_search_nodes=1)
        self.assertEqual(direct.algorithm, 'cp-sat-direct')
        self.assertIn('sum_dp_fallback', direct.diagnostics)
        self.assertIn('type_enumeration_fallback', direct.diagnostics)
        self.assert_valid(questions, direct, 3, 4, 'ignore')
        self.assertEqual(weight_score(result.tickets, 7), weight_score(direct.tickets, 7))
        with self.assertRaisesRegex(ValueError, 'weight-first'):
            generate_tickets_report(questions, 3, 4, target_weight=7,
                                    algorithm='sum-dp', objective_mode='balanced')
        with self.assertRaisesRegex(ValueError, 'режим целей'):
            generate_tickets_report(questions, 3, 4, target_weight=7, objective_mode='invalid')

    def test_real_bank_uses_sum_dp_in_all_modes(self):
        questions = read_questions(Path(__file__).resolve().parents[1] / 'examples' / 'questions_ma2.json')
        for mode in GROUP_MODES:
            result = generate_tickets_report(questions, 2, 100, mode, target_weight=6)
            self.assert_valid(questions, result, 2, 100, mode)
            self.assertEqual(result.algorithm, 'profile-sum-dp')
            ordered = sorted(abs(sum(Fraction(str(q.weight)) for q in t) - 6)
                             for t in candidates(questions, 2, mode))
            self.assertEqual(weight_score(result.tickets, 6), (ordered[99], sum(ordered[:100])))

    def test_huge_capacity_and_large_nonconstant_ticket_size(self):
        questions = [Question(str(i), str(i), 1) for i in range(100)]
        result = generate_tickets_report(questions, 50, 100, target_weight=50)
        self.assert_valid(questions, result, 50, 100, 'ignore')
        counts = Counter(q.id for t in result.tickets for q in t.questions)
        self.assertEqual(set(counts.values()), {50})

    def test_ignore_diagnostics_preserve_original_topic_count(self):
        questions = [Question('a', 'A', 1, 'A'), Question('b', 'B', 2, 'B')]
        result = generate_tickets_report(questions, 2, 1, 'ignore', target_weight=3)
        self.assertEqual(result.diagnostics['topics'], 2)
        self.assertEqual(result.diagnostics['effective_topics'], 1)
        self.assertEqual(result.diagnostics['topic_profiles'], 1)

    def test_same_mode_does_not_merge_original_topics(self):
        questions = [Question(f'{g}_{i}', str(i), 1, str(g)) for g in range(8) for i in range(2)]
        # У каждой темы лишь 2 вопроса: их нельзя слить в одну тему на 16.
        with self.assertRaises(ValueError):
            generate_tickets_report(questions, 3, 1, 'same', target_weight=3)

    def test_weight_first_timeout_metadata(self):
        from ortools.sat.python import cp_model
        questions = [Question(str(i), str(i), i + 1) for i in range(5)]
        solver = cp_model.CpSolver()
        solve = solver.solve
        def feasible(model):
            self.assertEqual(solve(model), cp_model.OPTIMAL)
            return cp_model.FEASIBLE
        with patch.object(solver, 'solve', side_effect=feasible), patch.object(cp_model, 'CpSolver', return_value=solver):
            result = generate_tickets_report(questions, 2, 3, target_weight=6,
                                             algorithm='cp-sat-types', allow_feasible=True)
        self.assertFalse(result.optimal)
        self.assertEqual(result.objective_count, 2)
        self.assertEqual(result.proven_objectives, 1)
        self.assertEqual(result.frequency_guarantee, 'within-class')


if __name__ == '__main__':
    unittest.main()
