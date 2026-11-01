# Contributing

Issues and pull requests are welcome.

1. Fork the repository and create a branch from `master`.
2. Install the dev requirements and run `pytest` and `ruff check app tests`.
3. Keep routes thin. Rules belong in `app/services`.
4. New errors should be an `AppError`, not an ad-hoc JSON body.
5. If you change a table, add an Alembic revision. Local `create_all` will not update a database that already exists.
6. Do not commit `.env`, `grove.db`, or anything under `media/`.

The demo password and the development `SECRET_KEY` are not secrets. A real secret does not belong in the tree.
