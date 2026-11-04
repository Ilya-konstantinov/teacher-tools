"""Нагрузка при начале проверки через фиксированное время после прихода.

Это спрос без очереди: значение выше 100% означает, что начать все проверки
в плановое время не получится. Расписание студентов этот отчёт не меняет.
"""
import argparse
import csv
from html import escape
from pathlib import Path

from table_io import read_examiners


def clock(minute: int) -> str:
    return f"{minute // 60:02d}:{minute % 60:02d}"


def analyze(schedule: Path, examiners_path: Path, prep_minutes: int, exam_minutes: int):
    if prep_minutes < 0 or exam_minutes < 1:
        raise ValueError("Подготовка должна быть неотрицательной, проверка — положительной")
    examiners = read_examiners(examiners_path)
    intervals = []
    with schedule.open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream, delimiter="\t"):
            if not row["Время прихода"]:
                continue
            h, m = map(int, row["Время прихода"].split(":"))
            start = h * 60 + m + prep_minutes
            intervals.append((start, start + exam_minutes))
    boundaries = {t for interval in intervals for t in interval}
    boundaries.update(t for examiner in examiners for h in examiner.hours for t in (h * 60, (h + 1) * 60))
    boundaries = sorted(boundaries)
    rows = []
    for start, end in zip(boundaries, boundaries[1:]):
        demand = sum(a <= start < b for a, b in intervals)
        available = sum(start // 60 in examiner.hours for examiner in examiners)
        ratio = demand / available if available else (float("inf") if demand else 0)
        rows.append((start, end, demand, available, ratio))
    return rows, len(intervals)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--schedule", type=Path, required=True)
    parser.add_argument("--examiners", type=Path, required=True)
    parser.add_argument("--prep-minutes", type=int, default=40)
    parser.add_argument("--exam-minutes", type=int, default=30)
    parser.add_argument("--output", type=Path, default=Path("workload.tsv"))
    args = parser.parse_args()
    if args.output.resolve() in (args.schedule.resolve(), args.examiners.resolve()):
        parser.error("Отчёт нельзя писать поверх входного файла")
    rows, count = analyze(args.schedule, args.examiners, args.prep_minutes, args.exam_minutes)
    with args.output.open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.writer(stream, delimiter="\t")
        writer.writerow(["С", "До", "Одновременно проверок", "Принимающих", "Нагрузка, %", "Нехватка принимающих"])
        for start, end, demand, available, ratio in rows:
            writer.writerow([clock(start), clock(end), demand, available,
                             round(ratio * 100, 1) if available else ("Нет принимающих" if demand else 0),
                             max(0, demand - available)])
    table = []
    for start, end, demand, available, ratio in rows:
        label = f"{ratio:.0%}" if available else ("∞" if demand else "—")
        color = "#fecaca" if demand > available else "#fef08a" if ratio >= .9 else "#bbf7d0" if demand else "#f3f4f6"
        table.append(f'<tr style="background:{color}"><td>{clock(start)}–{clock(end)}</td>'
                     f'<td>{demand}</td><td>{available}</td><td>{label}</td><td>{max(0,demand-available)}</td></tr>')
    page = ('<!doctype html><html lang="ru"><meta charset="utf-8"><title>Нагрузка на коллоквиуме</title>'
            '<style>body{font:16px system-ui;max-width:960px;margin:32px auto;padding:0 20px}'
            'table{border-collapse:collapse;width:100%}td,th{padding:9px;border:1px solid #ddd;text-align:left}</style>'
            '<h1>Нагрузка на принимающих</h1>'
            f'<p>Студентов: {count}. Подготовка: {args.prep_minutes} мин. Проверка: {args.exam_minutes} мин.</p>'
            '<p>Нагрузка = одновременно запланированные проверки / доступные принимающие. '
            'Красный — спрос выше вместимости. Очередь и переносы в этой модели не учитываются. '
            'Это совокупная нагрузка, конкретные принимающие студентам не назначаются.</p>'
            f'<p>Расписание: {escape(args.schedule.name)}</p>'
            '<table><thead><tr><th>Интервал проверки</th><th>Проверок</th><th>Принимающих</th>'
            '<th>Нагрузка</th><th>Нехватка</th></tr></thead><tbody>' + ''.join(table) + '</tbody></table></html>')
    args.output.with_suffix('.html').write_text(page, encoding="utf-8")
    assert sum((end - start) * demand for start, end, demand, _, _ in rows) == count * args.exam_minutes
    for start, end, demand, available, ratio in rows:
        if demand > available:
            print(f"{clock(start)}–{clock(end)}: {demand}/{available}, {ratio:.1%}")
    required = sum((b-a)*d for a,b,d,_,_ in rows)
    capacity = sum((b-a)*c for a,b,_,c,_ in rows)
    print(f"Студентов: {count}. Средняя нагрузка за всё время доступности: {required/capacity:.1%}. Отчёт: {args.output}")


if __name__ == "__main__":
    main()
