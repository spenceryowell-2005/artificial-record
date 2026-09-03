name: Build and deploy

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Install dependencies
        run: pip install markdown
      - name: Build site
        run: python build.py
      - name: Check the build actually produced pages
        run: |
          test -s site/index.html || { echo "::error::index.html missing"; exit 1; }
          test -s site/feed.xml || { echo "::error::feed.xml missing"; exit 1; }
          count=$(find site/editions -name index.html | wc -l)
          echo "Built $count edition page(s)"
          test "$count" -ge 1 || { echo "::error::no edition pages built"; exit 1; }
      - uses: actions/configure-pages@v5
      - uses: actions/upload-pages-artifact@v3
        with:
          path: site

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    steps:
      - id: deployment
        uses: actions/deploy-pages@v4
