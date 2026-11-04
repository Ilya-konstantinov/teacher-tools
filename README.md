# Teacher Tools

Инструменты для подготовки коллоквиума: распределение студентов по времени, оценка нагрузки принимающих, генерация билетов и подготовка PDF для печати и разрезания.

| Инструмент | Назначение | Документация |
|---|---|---|
| `colloq_time` | Расписание с приоритетами, временем заявки, дедлайном, подготовкой и доступностью принимающих | [Запуск и правила распределения](colloq_time/README.md) |
| `colloq_tickets` | Различные билеты с целевой сложностью и ограничениями тематических групп | [Запуск и форматы](colloq_tickets/README.md), [алгоритмы](colloq_tickets/ALGORITHMS.md) |

## Требования

Python 3.10+. Распределение студентов работает на стандартной библиотеке. Для резервных решателей генератора билетов и полного набора его тестов нужен OR-Tools. Сборка печатного PDF требует LuaLaTeX или XeLaTeX; генерация JSON и TeX работает без TeX-дистрибутива.

## Получение проекта

```sh
git clone https://github.com/Ilya-konstantinov/teacher-tools.git
cd teacher-tools
```

## Расписание студентов

В `examples/` находятся демонстрационные таблицы с условными именами и временем заявок.

```sh
cd colloq_time
python3 main.py \
  --examiners examples/examiners.tsv \
  --students examples/students.tsv \
  --minutes-per-student 30 \
  --prep-minutes 40 \
  --output schedule.tsv
```

Проверка нагрузки принимающих:

```sh
python3 workload.py \
  --schedule schedule.tsv \
  --examiners examples/examiners.tsv \
  --prep-minutes 40 \
  --exam-minutes 30 \
  --output workload.tsv
```

## Генерация и печать билетов

Из корня репозитория:

```sh
cd colloq_tickets
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
python3 run.py \
  --questions questions_ma2.json \
  -n 2 \
  --tickets 100 \
  --target-weight 6 \
  --group-mode different \
  --output tickets.json
```

В примере каждый билет содержит один вопрос из рядов и один из теории меры. `auto` выбирает алгоритм. По умолчанию строго оптимизируются максимальное и суммарное отклонения от целевого веса; частоты выравниваются внутри взаимозаменяемых классов.

```sh
python3 print_tickets.py tickets.json
lualatex -interaction=nonstopmode -halt-on-error tickets.tex
```

Получится `tickets.pdf`: четыре билета на листе A4 с линиями разреза. Параметры оформления — в [PRINTING.txt](colloq_tickets/PRINTING.txt).

## Проверки

Тесты инструментов запускаются отдельными процессами, поскольку у них самостоятельные модули с одинаковыми именами.

Из `colloq_time`:

```sh
python3 -m unittest -v
```

Из `colloq_tickets`, после установки зависимостей:

```sh
python3 run.py --test
```

[GitHub Actions](.github/workflows/tests.yml) запускает обе группы тестов на Python 3.10 и 3.12. Тесты не требуют личных данных студентов, готовых расписаний или ранее сгенерированных билетов.

## Локальные данные

Для настоящих заявок используйте `.test/` или `local/` внутри инструмента. Эти каталоги, виртуальные окружения, настройки редактора и стандартные результаты генерации исключены через `.gitignore`. В репозитории остаются код, документация, демонстрационные таблицы и банк вопросов МА2.

Генерация нового JSON не обновляет PDF автоматически: после изменения банка повторите генерацию, экспорт TeX и сборку PDF.
