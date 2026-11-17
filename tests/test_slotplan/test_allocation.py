import itertools
import random
import tempfile
import unittest
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path

from slotplan.allocation import allocate
from slotplan.data import Examiner, Student
from slotplan.data import read_examiners, read_students, write_assignments


class AllocationTests(unittest.TestCase):
    def student(self, name, priorities=(9, 10, 11), unavailable=(), minute=0):
        return Student(name, "251", priorities, frozenset(unavailable), datetime(2026, 11, 1, 12) + timedelta(minutes=minute))

    def test_check_must_fit_one_examiners_entire_availability(self):
        # Суммарно принимающий есть в каждый момент, но никто не может
        # целиком провести проверку 09:40–10:10, поэтому приход в 09:00 запрещён.
        examiners = [Examiner("До 10", (9,)), Examiner("С 10", (10,))]
        result = allocate([self.student("Студент")], examiners, prep_minutes=40)
        self.assertEqual(result[0].start_minute, 9 * 60 + 30)

    def test_student_unavailable_during_preparation_or_check(self):
        student = self.student("Студент", unavailable=(10,))
        result = allocate([student], [Examiner("П", (9, 10))], prep_minutes=40)
        self.assertIsNone(result[0].start_minute)

    def test_preparation_matches_exhaustive_optimum(self):
        rng = random.Random(81)
        for _ in range(25):
            students = [self.student(str(i), priorities=tuple(rng.sample((9, 10, 11), 3)),
                                     unavailable=[h for h in (9, 10, 11) if rng.random() < .2], minute=i)
                        for i in range(3)]
            examiners = [Examiner(str(i), tuple(h for h in (9, 10, 11) if rng.random() < .6))
                         for i in range(2)]
            caps = {}
            opening = min((h for e in examiners for h in e.hours), default=12) * 60
            for arrival in range(opening, 12 * 60, 30):
                exam_hours = range((arrival + 40) // 60, (arrival + 69) // 60 + 1)
                caps[arrival] = sum(all(h in e.hours for h in exam_hours) for e in examiners)
            times = [a for a, c in caps.items() if c]

            def objective(schedule):
                penalties = [4 if a is None else s.priorities.index(a // 60)
                             for s, a in zip(students, schedule)]
                return (-sum(a is not None for a in schedule), sum(p for p in penalties if p != 4),
                        tuple(penalties), tuple(a if a is not None else 0 for a in schedule))

            possible = []
            for schedule in itertools.product([None, *times], repeat=3):
                loads = Counter(a for a in schedule if a is not None)
                if any(count > caps[a] for a, count in loads.items()):
                    continue
                if any(a is not None and any(h in s.unavailable for h in range(a // 60, (a + 69) // 60 + 1))
                       for s, a in zip(students, schedule)):
                    continue
                possible.append(objective(schedule))
            result = allocate(students, examiners, prep_minutes=40)
            self.assertEqual(objective([a.start_minute for a in result]), min(possible))

    def test_earlier_application_wins_even_when_rows_reversed(self):
        students = [self.student("Позднее", minute=1), self.student("Раньше")]
        result = allocate(students, [Examiner("Преподаватель", (9, 10))], capacity=1)
        self.assertEqual([r.hour for r in result], [10, 9])

    def test_reassigns_to_fit_constrained_student(self):
        students = [self.student("Свободный"), self.student("Ограниченный", unavailable=(10,), minute=1)]
        self.assertEqual([r.hour for r in allocate(students, [Examiner("П", (9, 10))], capacity=1)], [10, 9])

    def test_deadline_and_late_preferences(self):
        deadline = datetime(2026, 11, 1, 12)
        students = [self.student("Опоздал", priorities=(9,), minute=1), self.student("Вовремя", priorities=(10,))]
        result = allocate(students, [Examiner("П", (9,))], capacity=1, deadline=deadline)
        self.assertEqual([r.hour for r in result], [None, 9])
        late = allocate([students[0]], [Examiner("П", (9, 10))], deadline=deadline)[0]
        self.assertIsNone(late.priority)
        self.assertIn("После дедлайна", late.reason)
        blocked = self.student("Запрет", unavailable=(9, 10), minute=2)
        self.assertIsNone(allocate([blocked], [Examiner("П", (9, 10))], deadline=deadline)[0].hour)

    def test_capacity_duplicates_and_empty(self):
        students = [self.student(str(i), priorities=(9, 9, 9)) for i in range(3)]
        result = allocate(students, [Examiner("П", (9,))], capacity=2)
        self.assertEqual([r.priority for r in result], [1, 1, None])
        self.assertEqual(allocate([], []), [])
        self.assertIsNone(allocate(students[:1], [])[0].hour)
        with self.assertRaises(ValueError):
            allocate(students, [], capacity=0)

    def test_matches_exhaustive_optimum(self):
        rng = random.Random(42)
        deadline = datetime(2026, 11, 1, 12, 1)
        for _ in range(100):
            students = [self.student(str(i), tuple(rng.sample([9, 10, 11, 12], 3)),
                                     [h for h in (9, 10, 11) if rng.random() < .3], i) for i in range(4)]
            rng.shuffle(students)
            examiners = [Examiner(str(i), tuple(h for h in (9, 10, 11) if rng.random() < .5))
                         for i in range(rng.randint(1, 3))]
            capacity = rng.randint(1, 2)
            available = Counter(h for e in examiners for h in set(e.hours))
            order = sorted(range(len(students)), key=lambda i: (students[i].submitted_at, i))
            def objective(schedule):
                penalties = [4 if h is None else s.priorities.index(h)
                             if s.submitted_at <= deadline and h in s.priorities else 3
                             for s, h in zip(students, schedule)]
                return (-sum(h is not None for h in schedule),
                        -sum(h is not None and s.submitted_at <= deadline for s, h in zip(students, schedule)),
                        sum(p for p in penalties if p != 4), tuple(penalties[i] for i in order))
            possible = []
            for schedule in itertools.product((None, 9, 10, 11), repeat=4):
                counts = Counter(h for h in schedule if h is not None)
                if any(count > available[h] * capacity for h, count in counts.items()):
                    continue
                if any(h in s.unavailable for h, s in zip(schedule, students)):
                    continue
                possible.append(objective(schedule))
            result = allocate(students, examiners, capacity=capacity, deadline=deadline)
            self.assertEqual(objective([r.hour for r in result]), min(possible))
            loads = Counter(r.hour for r in result if r.hour is not None)
            self.assertTrue(all(count <= available[h] * capacity for h, count in loads.items()))

    def test_sums_hour_capacity(self):
        students = [self.student(str(i), priorities=(9,)) for i in range(7)]
        result = allocate(students, [Examiner("А", (9, 9)), Examiner("Б", (9,)), Examiner("В", (10,))], capacity=2)
        self.assertEqual(Counter(r.hour for r in result if r.hour is not None), {9: 4, 10: 2})
        self.assertIsNone(result[-1].hour)

    def test_unreachable_hours_and_students(self):
        students = [self.student("Нет часов", unavailable=(9, 10, 11)), self.student("Только 9", unavailable=(10, 11))]
        result = allocate(students, [Examiner("П", (9, 10, 11))])
        self.assertEqual([r.hour for r in result], [None, 9])

    def test_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "examiners.tsv").write_text("ФИОВремя прием\nПетров Пётр\t9, 10\n", encoding="utf-8-sig")
            (path / "students.tsv").write_text(
                "Отметка времени\tФИО\tГруппа\tПриоритет 1\tПриоритет 2\tПриоритет 3\tВ какое время вы точно не сможете\n"
                "01.11.2026 12:00:00\tИванов Иван\t2515\t9\t9\t10\t\n", encoding="utf-8")
            students = read_students(path / "students.tsv")
            self.assertEqual(students[0].group, "2515")
            result = allocate(students, read_examiners(path / "examiners.tsv"))
            write_assignments(path / "result.tsv", result)
            output = (path / "result.tsv").read_text(encoding="utf-8-sig")
            self.assertIn("Иванов Иван", output)
            self.assertEqual(output.splitlines()[0], "Время прихода\tФИО\tГруппа\tПриоритет\tПричина")

    def test_arrival_batches_30_and_20_minutes(self):
        students = [self.student(str(i), priorities=(9,), minute=i) for i in range(8)]
        examiners = [Examiner("А", (9,)), Examiner("Б", (9,))]
        for minutes in (30, 20):
            capacity = 60 // minutes
            result = allocate(list(reversed(students)), examiners, capacity=capacity, batch_minutes=minutes)
            assigned = [a for a in result if a.hour is not None]
            self.assertEqual(len(assigned), 2 * capacity)
            loads = Counter(a.start_minute for a in assigned)
            self.assertEqual(loads, {9 * 60 + i * minutes: 2 for i in range(capacity)})
            for a in assigned:
                self.assertEqual(a.start_minute, 9 * 60 + (int(a.student.name) // 2) * minutes)
                self.assertLessEqual(a.start_minute + minutes, 10 * 60)
        with self.assertRaises(ValueError):
            allocate(students, examiners, capacity=3, batch_minutes=30)


if __name__ == "__main__":
    unittest.main()
