"""Запуск: python3 main.py --help."""
import argparse
from collections import Counter
from pathlib import Path

from constraints import GROUP_MODES
from objectives import OBJECTIVES, OBJECTIVE_MODES
from generation import ALGORITHMS, generate_tickets_report
from table_io import read_questions, write_tickets


def main() -> None:
    parser = argparse.ArgumentParser(description="Генерация билетов с выравниванием сложности")
    parser.add_argument("--questions", type=Path, required=True, help="JSON с банком вопросов")
    parser.add_argument("--questions-per-ticket", "-n", type=int, required=True)
    parser.add_argument("--tickets", type=int, required=True, help="Число различных билетов")
    parser.add_argument("--target-weight", type=float, required=True, help="Желаемый суммарный вес одного билета")
    parser.add_argument("--group-mode", choices=GROUP_MODES, default="ignore",
                        help="different: все из разных групп; same: все из одной группы; ignore: без ограничений")
    parser.add_argument("--max-search-nodes", type=int, default=100_000,
                        help="Лимит перечисления типов и планов; auto переключает точный решатель при превышении")
    parser.add_argument("--objective-mode", choices=OBJECTIVE_MODES, default="weight-first",
                        help="weight-first: максимальное и суммарное отклонения, затем мягкие частоты; balanced: прежние три строгие цели")
    parser.add_argument("--algorithm", choices=ALGORITHMS, default="auto",
                        help="Автовыбор, DP по суммам, перебор планов, DP по частотам или CP-SAT; для любого n")
    parser.add_argument("--max-dp-states", type=int, default=100_000,
                        help="Лимит сохранённых состояний DP по суммам или слоя DP по частотам; бюджет переходов — в 10 раз больше")
    parser.add_argument("--time-limit", type=float, default=30, help="Общий лимит решения CP-SAT в секундах (по умолчанию 30)")
    parser.add_argument("--allow-feasible", action="store_true",
                        help="Разрешить допустимый результат без доказанного оптимума; JSON будет помечен optimal=false")
    parser.add_argument("--output", type=Path, default=Path("tickets.json"))
    args = parser.parse_args()
    try:
        if args.output.resolve() == args.questions.resolve():
            raise ValueError("Результат нельзя записывать поверх банка вопросов")
        questions = read_questions(args.questions)
        result = generate_tickets_report(questions, args.questions_per_ticket,
                                   args.tickets, args.group_mode, args.max_search_nodes,
                                   target_weight=args.target_weight, algorithm=args.algorithm,
                                   time_limit=args.time_limit, allow_feasible=args.allow_feasible,
                                   max_dp_states=args.max_dp_states, objective_mode=args.objective_mode)
        tickets = result.tickets
        write_tickets(args.output, tickets, questions=questions, target_weight=args.target_weight,
                      optimization={"algorithm": result.algorithm, "optimal": result.optimal,
                                    "proven_objectives": result.proven_objectives,
                                    "group_mode": args.group_mode,
                                    "weight_classes": result.weight_classes,
                                    "question_classes": result.question_classes,
                                    "ticket_types": result.ticket_types,
                                    "objective_mode": result.objective_mode,
                                    "objective_count": result.objective_count,
                                    "objectives": OBJECTIVES[result.objective_mode],
                                    "frequency_guarantee": result.frequency_guarantee,
                                    "diagnostics": result.diagnostics})
    except (OSError, ValueError, OverflowError) as error:
        parser.error(str(error))
    weights = [ticket.total_weight for ticket in tickets]
    usage = Counter(q.id for ticket in tickets for q in ticket.questions)
    counts = [usage[q.id] for q in questions]
    print(f"Билетов: {len(tickets)}. Целевой вес: {args.target_weight:g}. "
          f"Вес: {min(weights):g}–{max(weights):g}. "
          f"Максимальное отклонение: {max(abs(w - args.target_weight) for w in weights):g}. "
          f"Повторений вопроса: {min(counts)}–{max(counts)}. Файл: {args.output}")
    print(f"Алгоритм: {result.algorithm}. Оптимум доказан: {'да' if result.optimal else 'нет'} "
          f"({result.proven_objectives}/{result.objective_count} строгих критериев).")
    print(f"Цели: {result.objective_mode}. Гарантия частот: {result.frequency_guarantee}.")
    if "sum_states" in result.diagnostics:
        print(f"Профилей тем: {result.diagnostics['topic_profiles']}. "
              f"Состояний DP по суммам: {result.diagnostics['sum_states']}. "
              f"Переходов: {result.diagnostics['sum_transitions']}.")
    print(f"Различных весов: {result.weight_classes}. Классов вопросов: {result.question_classes}. "
          f"Типов билетов после отбора по весу: {result.ticket_types if result.ticket_types is not None else 'не перечислялись'}.")


if __name__ == "__main__":
    main()
