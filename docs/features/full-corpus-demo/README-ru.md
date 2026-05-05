# Демо полного корпуса

Проигрывает **все** JSON-фикстуры сессий из `e2e/fixtures/sessions/{en,ru}/` через связку компонентов:

1. **FileStateStore** — стартовая идентичность и нарратив  
2. **SessionManager** — по каждой фикстуре: события, ключевые моменты, завершение → опыт + eigenstate + обновление нратива  
3. **MicroReflectionService** — после каждой сессии  
4. **DailyReflectionService** — один UTC-календарный день на сессию  
5. **DeepReflectionService** — один прогон на весь интервал  

Рефлексия — **детерминированный мок** из `e2e/full_loop` (без API). В конце таблица сравнивает начальное состояние с накопленными опытами, касаниями принципов в ключевых моментах, выборкой настроения (eigenstate), паттернами, рефреймингом и текстом **recent** слоя нратива.

## Запуск

```bash
make demo-full-corpus
make demo-full-corpus-fast
PYTHONPATH=. python3 src/demo_full_corpus.py --locale ru --limit 5
```

**Factual Memory (WP-01)** в этом сценарии не задействован; см. `make demo-factual`.

## См. также

- Фикстуры: `e2e/fixtures/sessions/README.md`  
- Короткий интеграционный драйвер: `python -m e2e`  
- [Issue #158](https://github.com/hleserg/atman/issues/158)
