name: HACS Validation

on:
  push:
  pull_request:

jobs:
  validate:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: HACS validation
        uses: hacs/action@main
        with:
          category: integration

      - name: Hassfest validation
        uses: home-assistant/actions/hassfest@master

      - name: Python lint (ruff)
        run: |
          pip install ruff
          ruff check custom_components/
