import itertools
from functools import partial
import json
import random
import subprocess
import sys
import tempfile
import unittest
from collections import Counter
from fractions import Fraction
from pathlib import Path
from unittest.mock import patch

from paperforge.problem import GROUP_MODES, compatible
from paperforge.planning import generate_tickets, generate_tickets_report
from paperforge.models import Question
from paperforge.io import read_questions, write_tickets
from paperforge.reconstruction import realize, restore_tickets
from paperforge.planning import plan_tickets
from paperforge.problem import balanced_cost, enumerate_types, group_questions

# Регрессия прежнего порядка целей; новый режим проверяется отдельно.
generate_tickets = partial(generate_tickets, objective_mode="balanced")
generate_tickets_report = partial(generate_tickets_report, objective_mode="balanced")
plan_tickets = partial(plan_tickets, objective_mode="balanced")


def objective(questions, tickets, target):
    deviations = [abs(sum(Fraction(str(q.weight)) for q in ticket.questions) - Fraction(str(target)))
                  for ticket in tickets]
    counts = Counter(q.id for ticket in tickets for q in ticket.questions)
    return max(deviations), sum(counts[q.id] ** 2 for q in questions), sum(deviations)


class GenerationTests(unittest.TestCase):
    def assert_valid(self, questions, result, size, count, mode):
        self.assertEqual(len(result.tickets), count)
        self.assertEqual(len({frozenset(q.id for q in t.questions) for t in result.tickets}), count)
        for ticket in result.tickets:
            self.assertEqual(len(ticket.questions), size)
            self.assertEqual(len({q.id for q in ticket.questions}), size)
            self.assertTrue(all(compatible(a, b, mode) for a, b in itertools.combinations(ticket.questions, 2)))
        self.assertTrue(result.optimal)
        self.assertEqual(result.proven_objectives, 3)

    def test_all_solvers_match_exhaustive_optimum(self):
        from paperforge.models import Ticket
        rng = random.Random(17)
        for trial in range(12):
            questions = [Question(str(i), str(i), rng.choice((0.1, 0.2, 0.4)), str(rng.randrange(3)))
                         for i in range(6)]
            for mode in GROUP_MODES:
                for size in (1, 2, 3):
                    count = rng.randint(1, 3)
                    target = rng.choice((0.3, 0.5, 0.8))
                    candidates = [Ticket(group) for group in itertools.combinations(questions, size)
                                  if all(compatible(a, b, mode) for a, b in itertools.combinations(group, 2))]
                    algorithms = ['auto', 'enumerate', 'dp', 'cp-sat-types', 'cp-sat']
                    for algorithm in algorithms:
                        with self.subTest(trial=trial, mode=mode, size=size, algorithm=algorithm):
                            if len(candidates) < count:
                                with self.assertRaises(ValueError):
                                    generate_tickets_report(questions, size, count, mode,
                                                            target_weight=target, algorithm=algorithm)
                                continue
                            expected = min(objective(questions, subset, target)
                                           for subset in itertools.combinations(candidates, count))
                            result = generate_tickets_report(questions, size, count, mode,
                                                             target_weight=target, algorithm=algorithm)
                            self.assert_valid(questions, result, size, count, mode)
                            self.assertEqual(objective(questions, result.tickets, target), expected)

    def test_synthetic_bank_all_modes_and_algorithms(self):
        questions = read_questions(Path(__file__).resolve().parent / 'fixtures' / 'questions.json')
        for mode in GROUP_MODES:
            result = generate_tickets_report(questions, 2, 100, mode, target_weight=6)
            self.assert_valid(questions, result, 2, 100, mode)
            candidates = [abs(sum(Fraction(str(q.weight)) for q in pair) - 6)
                          for pair in itertools.combinations(questions, 2) if compatible(*pair, mode)]
            self.assertEqual(objective(questions, result.tickets, 6)[0], sorted(candidates)[99])
            self.assertEqual(result.weight_classes, len({q.weight for q in questions}))
            self.assertEqual(result.question_classes, len(group_questions(questions, mode)))
        triples = generate_tickets_report(questions, 3, 100, 'ignore', target_weight=9)
        self.assert_valid(questions, triples, 3, 100, 'ignore')
        self.assertEqual(max(abs(t.total_weight - 9) for t in triples.tickets), 0)

    def test_hundred_bipartite_pairs_balanced(self):
        questions = [Question(str(i), str(i), 1, 'a' if i < 12 else 'b') for i in range(29)]
        result = generate_tickets_report(questions, 2, 100, 'different', target_weight=2)
        counts = Counter(q.id for t in result.tickets for q in t.questions)
        self.assertEqual(sorted(counts[str(i)] for i in range(12)), [8]*8 + [9]*4)
        self.assertEqual(sorted(counts[str(i)] for i in range(12, 29)), [5]*2 + [6]*15)
        self.assert_valid(questions, result, 2, 100, 'different')

    def test_planning_is_independent_and_restoration_preserves_plan(self):
        questions = [Question(str(i), str(i), 1 + i // 3, str(i % 2)) for i in range(9)]
        for algorithm in ('auto', 'dp', 'cp-sat-types', 'cp-sat'):
            with self.subTest(algorithm=algorithm):
                with patch('paperforge.reconstruction.realize', side_effect=AssertionError('Восстановление на этапе выбора')):
                    plan = plan_tickets(questions, 3, 7, 'ignore', target_weight=6, algorithm=algorithm)
                before = plan.selection
                first = restore_tickets(plan)
                second = restore_tickets(plan)
                self.assertEqual(first, second)
                self.assertEqual(plan.selection, before)
                self.assert_valid(questions, first, 3, 7, 'ignore')
                class_of = {plan.questions[i].id: c for c, item in enumerate(plan.classes) for i in item.members}
                actual = Counter(tuple(sorted(Counter(class_of[q.id] for q in t.questions).items()))
                                 for t in first.tickets)
                expected = Counter({t.composition: amount for t, amount in
                                    zip(plan.selection.types, plan.selection.amounts) if amount})
                self.assertEqual(actual, expected)
                appearances = [0] * len(plan.classes)
                for pattern, amount in zip(plan.selection.types, plan.selection.amounts):
                    for c, multiplicity in pattern.composition:
                        appearances[c] += multiplicity * amount
                self.assertEqual(objective(questions, first.tickets, 6)[1],
                                 sum(balanced_cost(len(c.members), total)
                                     for c, total in zip(plan.classes, appearances)))

    def test_full_generation_restores_only_once(self):
        questions = [Question(str(i), str(i), 1 + i // 2) for i in range(6)]
        with patch('paperforge.planning.restore_tickets', wraps=restore_tickets) as restored:
            generate_tickets_report(questions, 2, 4, target_weight=4, algorithm='cp-sat-types')
        self.assertEqual(restored.call_count, 1)

    def test_all_equal_weights_large_bank_avoids_subsets(self):
        questions = [Question(str(i), str(i), 1) for i in range(100)]
        result = generate_tickets_report(questions, 10, 100, target_weight=10)
        self.assertEqual(result.algorithm, 'fixed-types')
        self.assertEqual(result.ticket_types, 1)
        self.assertEqual(objective(questions, result.tickets, 10), (0, 10000, 0))
        self.assert_valid(questions, result, 10, 100, 'ignore')

    def test_same_mode_decomposes_many_groups(self):
        questions = [Question(f'{g}_{i}', f'{g}_{i}', 1 + i // 2, str(g))
                     for g in range(10) for i in range(4)]
        result = generate_tickets_report(questions, 2, 20, 'same', target_weight=3, algorithm='dp')
        self.assert_valid(questions, result, 2, 20, 'same')
        self.assertEqual(result.algorithm, 'type-dp')
        self.assertEqual(objective(questions, result.tickets, 3), (0, 40, 0))

    def test_type_capacities_and_balancing_all_combinations(self):
        questions = [Question(str(i), str(i), 1 if i < 3 else 2) for i in range(6)]
        classes = group_questions(questions, 'ignore')
        pool = enumerate_types(classes, 3, 20, 'ignore', Fraction(4), 1000)
        self.assertEqual(sum(p.capacity for p in pool), 20)
        amounts = [p.capacity for p in pool]
        tickets = realize(questions, classes, pool, amounts)
        self.assertEqual(len(tickets), 20)
        counts = Counter(q.id for t in tickets for q in t.questions)
        self.assertEqual(list(counts.values()), [10] * 6)

    def test_group_meaning_and_default_group(self):
        questions = [Question('a', 'A', 1, 'x'), Question('b', 'B', 1, 'x'), Question('c', 'C', 1, 'y')]
        same = generate_tickets(questions, 2, 1, 'same', target_weight=2)
        self.assertEqual({q.id for q in same[0].questions}, {'a', 'b'})
        different = generate_tickets(questions, 2, 2, 'different', target_weight=2)
        self.assertEqual({frozenset(q.id for q in t.questions) for t in different},
                         {frozenset(('a', 'c')), frozenset(('b', 'c'))})
        with self.assertRaisesRegex(ValueError, 'недостаточно'):
            generate_tickets(questions, 3, 1, 'different', target_weight=3)
        self.assertEqual(len(group_questions(questions, 'ignore')), 1)
        self.assertEqual(len(group_questions(questions, 'same')), 2)

    def test_single_and_minimax_precedence(self):
        questions = [Question('a', 'A', 1), Question('b', 'B', 1), Question('c', 'C', 100)]
        result = generate_tickets_report(questions, 1, 2, target_weight=1)
        self.assertEqual(result.algorithm, 'fixed-types')
        self.assertEqual({q.id for t in result.tickets for q in t.questions}, {'a', 'b'})

    def test_forced_solvers_and_limits(self):
        questions = [Question(str(i), str(i), 1 + i // 2) for i in range(8)]
        result = generate_tickets_report(questions, 3, 4, target_weight=7, max_search_nodes=1)
        self.assertEqual(result.algorithm, 'cp-sat-direct')
        with self.assertRaisesRegex(ValueError, 'лимит'):
            generate_tickets(questions, 3, 4, target_weight=7, max_search_nodes=1, algorithm='dp')
        with self.assertRaisesRegex(ValueError, 'DP'):
            generate_tickets(questions, 3, 4, target_weight=7, algorithm='dp', max_dp_states=1)
        result = generate_tickets_report(questions, 3, 4, target_weight=7, max_dp_states=1)
        self.assertIn(result.algorithm, ('type-enumeration', 'cp-sat-types'))
        with patch('paperforge.planning.enumeration_bound', return_value=100_001):
            result = generate_tickets_report(questions, 3, 4, target_weight=7, max_dp_states=1)
        self.assertEqual(result.algorithm, 'cp-sat-types')
        for algorithm in ('flow', 'blossom'):
            with self.assertRaisesRegex(ValueError, 'Неизвестный алгоритм'):
                generate_tickets(questions, 2, 4, target_weight=4, algorithm=algorithm)

    def test_solver_timeout_and_feasible_status(self):
        from ortools.sat.python import cp_model
        questions = [Question(str(i), str(i), 1 + i // 2) for i in range(6)]
        with self.assertRaisesRegex(ValueError, 'не доказал оптимальность'):
            generate_tickets(questions, 2, 2, target_weight=4, algorithm='cp-sat', time_limit=1e-9)
        solver = cp_model.CpSolver()
        original = solver.solve
        def feasible(model):
            self.assertEqual(original(model), cp_model.OPTIMAL)
            return cp_model.FEASIBLE
        with patch.object(solver, 'solve', side_effect=feasible), patch.object(cp_model, 'CpSolver', return_value=solver):
            result = generate_tickets_report(questions, 2, 2, target_weight=4,
                                             algorithm='cp-sat-types', allow_feasible=True)
            self.assertFalse(result.optimal)
            self.assertEqual(result.proven_objectives, 1)
            self.assertEqual(result.frequency_guarantee, 'within-class')
            self.assertEqual(len(result.tickets), 2)
            with self.assertRaisesRegex(ValueError, 'не доказал оптимальность'):
                generate_tickets_report(questions, 2, 2, target_weight=4, algorithm='cp-sat-types')

    def test_invalid_inputs(self):
        questions = [Question(str(i), str(i), 1) for i in range(6)]
        for kwargs in ({'questions_per_ticket': 0}, {'questions_per_ticket': 7}, {'ticket_count': 0},
                       {'target_weight': 0}, {'target_weight': float('nan')}, {'target_weight': True},
                       {'group_mode': 'related'}, {'algorithm': 'unknown'}, {'time_limit': 0},
                       {'max_search_nodes': 0}, {'max_dp_states': 0}):
            args = dict(questions_per_ticket=2, ticket_count=2, target_weight=2)
            args.update(kwargs)
            with self.assertRaises(ValueError):
                generate_tickets(questions, **args)
        for bad in ([Question('a', 'A', -1)], [Question('a', 'A', float('nan'))],
                    [Question('a', 'A', True)], [Question('a', 'A', 1, '')],
                    [Question('a', 'A', 1, [])], [questions[0], questions[0]], []):
            with self.assertRaises(ValueError):
                generate_tickets(bad, 1, 1, target_weight=1)

    def test_json_roundtrip_and_old_links_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'questions.json'
            source.write_text(json.dumps([{'id': 'q1', 'text': 'Вопрос', 'weight': 2, 'group': 'Мера'}]))
            questions = read_questions(source)
            tickets = generate_tickets(questions, 1, 1, target_weight=2)
            output = Path(directory) / 'out.json'
            write_tickets(output, tickets, questions=questions, target_weight=2)
            data = json.loads(output.read_text())
            self.assertEqual(data['tickets'][0]['questions'][0]['group'], 'Мера')
            self.assertEqual(data['question_usage'][0]['count'], 1)
            source.write_text(json.dumps([{'id': 'q1', 'text': 'Вопрос', 'weight': 2, 'related': []}]))
            with self.assertRaisesRegex(ValueError, 'related больше не поддерживается'):
                read_questions(source)

    def test_cli_preserves_output_on_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / 'q.json'
            output = Path(directory) / 'out.json'
            source.write_text(json.dumps([{'id': 'a', 'text': 'A', 'weight': 1, 'group': 'a'}]))
            output.write_text('keep')
            result = subprocess.run([sys.executable, '-m', 'paperforge', 'generate',
                                     '--questions', str(source), '-n', '2', '--tickets', '1',
                                     '--target-weight', '2', '--output', str(output)], capture_output=True)
            self.assertNotEqual(result.returncode, 0)
            self.assertEqual(output.read_text(), 'keep')


if __name__ == '__main__':
    unittest.main()
