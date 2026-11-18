"""Интерфейс генерации билетов."""
import argparse
from collections import Counter
from pathlib import Path


def main(argv=None, *, pipeline=False) -> None:
    from .config import settings_for_cli
    from .io import read_questions, tickets_data, without_answers, write_json
    from .planning import ALGORITHMS, generate_tickets_report
    from .problem import GROUP_MODES, OBJECTIVES, OBJECTIVE_MODES

    parser = argparse.ArgumentParser(epilog='Другие команды: paperforge print --help.', description="Генерация билетов с выравниванием сложности")
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    config_args = argv[:argv.index('--then')] if not pipeline and '--then' in argv else argv
    settings = settings_for_cli(parser, config_args)
    defaults = settings.generation
    bank = parser.add_mutually_exclusive_group(required=True)
    bank.add_argument("bank", nargs="?", type=Path, help="Файл банка или каталог вопросов")
    bank.add_argument("--questions", type=Path, help="JSON с банком вопросов или каталог *.txt")
    parser.add_argument("--questions-per-ticket", "-n", type=int, required=True)
    parser.add_argument("--tickets", "-t", type=int, required=True, help="Число различных билетов")
    parser.add_argument("--target-weight", type=float, help="Желаемый вес; при одинаковых весах вычисляется автоматически")
    parser.add_argument("--group-mode", choices=GROUP_MODES, default=defaults.group_mode,
                        help="different: все из разных групп; same: все из одной группы; ignore: без ограничений")
    parser.add_argument("--max-search-nodes", type=int, default=defaults.max_search_nodes,
                        help="Лимит перечисления типов и планов; auto переключает точный решатель при превышении")
    parser.add_argument("--objective-mode", choices=OBJECTIVE_MODES, default=defaults.objective_mode,
                        help="weight-first: максимальное и суммарное отклонения, затем мягкие частоты; balanced: прежние три строгие цели")
    parser.add_argument("--algorithm", choices=ALGORITHMS, default=defaults.algorithm,
                        help="Автовыбор, DP по суммам, перебор планов, DP по частотам или CP-SAT; для любого n")
    parser.add_argument("--max-dp-states", type=int, default=defaults.max_dp_states,
                        help="Лимит сохранённых состояний DP по суммам или слоя DP по частотам; множитель бюджета переходов задаётся в config.json")
    parser.add_argument("--time-limit", type=float, default=defaults.time_limit, help="Общий лимит решения CP-SAT в секундах")
    parser.add_argument("--allow-feasible", action=argparse.BooleanOptionalAction, default=defaults.allow_feasible,
                        help="Разрешить допустимый результат без доказанного оптимума; JSON будет помечен optimal=false")
    parser.add_argument("--output", "-o", type=Path, default=Path(defaults.output))
    parser.add_argument("--key-output", type=Path, help="Записать ответы к выбранным вопросам отдельным JSON")
    if pipeline:
        from .documents import add_render_arguments
        add_render_arguments(parser, settings, pipeline=True)
    else:
        from .backends import command_arguments
        runners = parser.add_mutually_exclusive_group()
        runners.add_argument('--then', dest='handler', nargs=argparse.REMAINDER, metavar='COMMAND',
                             help='Запустить программу после генерации. Все следующие аргументы передаются ей.')
        runners.add_argument('--runner', type=command_arguments, metavar='JSON_ARGV',
                            help='Run a command with the absolute tickets JSON path as its last argument')
    args = parser.parse_args(argv)
    if not pipeline and args.handler is not None:
        if not args.handler:
            parser.error('После --then укажите команду, например: --then python render.py')
        args.runner = args.handler
    args.questions = (args.questions or args.bank).expanduser()
    args.output = args.output.expanduser()
    try:
        if args.output.resolve() == args.questions.resolve():
            raise ValueError("Результат нельзя записывать поверх банка вопросов")
        source_paths = []
        questions = read_questions(args.questions, sources=source_paths)
        if args.output.resolve() in {p.resolve() for p in source_paths}:
            raise ValueError('Результат нельзя записывать поверх файлов вопросов')
        if args.target_weight is None:
            if not questions or len({q.weight for q in questions}) != 1:
                raise ValueError('--target-weight обязателен при различных весах вопросов')
            args.target_weight = questions[0].weight * args.questions_per_ticket
        result = generate_tickets_report(questions, args.questions_per_ticket,
                                   args.tickets, args.group_mode, args.max_search_nodes,
                                   target_weight=args.target_weight, algorithm=args.algorithm,
                                   time_limit=args.time_limit, allow_feasible=args.allow_feasible,
                                   max_dp_states=args.max_dp_states, objective_mode=args.objective_mode, settings=settings)
        tickets = result.tickets
        data = tickets_data(tickets, questions=questions, target_weight=args.target_weight,
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
        if args.key_output:
            from .answers import read_key, with_answers
            external_key = read_key(args.answers_key) if pipeline and args.answers_key else None
            keyed = with_answers(data, external_key)
            answer_key = {q['id']: q['answers'] for t in keyed['tickets'] for q in t['questions']}
            protected = [args.output, *source_paths, args.config]
            if pipeline:
                protected.extend([args.answers_key, args.template, args.answers_template])
                from .generators import generator_sources
                for generator in (args.print_generator, args.answers_generator):
                    protected.extend(generator_sources(generator))
            if args.key_output.resolve() in {p.resolve() for p in protected if p is not None}:
                raise ValueError('Файл ключа совпадает с исходными данными или билетами')
            source_paths.append(args.key_output)
        if pipeline:
            from .pipeline import prepare_exports
            documents = prepare_exports(args, settings, data, source_paths=source_paths)
        write_json(args.output, without_answers(data))
        if args.key_output:
            write_json(args.key_output, answer_key)
        if not pipeline and args.runner:
            import subprocess
            from .backends import subprocess_environment
            process = subprocess.run([*args.runner, str(args.output.resolve())],
                                     env=subprocess_environment())
            if process.returncode:
                raise ValueError(f'Runner exited with status {process.returncode}')
        if pipeline:
            from .documents import write_document
            for path, document in documents:
                write_document(path, document, pdf=args.pdf, engine=args.engine, compiler_command=args.compiler_command)
    except (OSError, ValueError, OverflowError, ImportError, TypeError, AttributeError, KeyError) as error:
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
