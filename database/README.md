# База данных TimeWise

`schema.sql` содержит только структуру PostgreSQL: 12 таблиц, последовательности, ограничения, индексы и внешние ключи. Данные из рабочей базы в файл не включены.

## Создание базы

```powershell
createdb timewise
psql -d timewise -f schema.sql
```

Для подключения приложений используйте строку вида:

```text
postgresql+asyncpg://USER:PASSWORD@localhost:5432/timewise
```

Не добавляйте в Git дампы с данными, локальные `.db`-файлы или резервные копии.
