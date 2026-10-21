---
name: New job source
about: Propose a new job portal or careers site to scrape
title: "[source] "
labels: new-source
---

**Portal / site**
- Name:
- URL:
- Country / region covered:

**Access**
- [ ] Public listing pages (no login)
- [ ] Official API (link to docs):
- [ ] Requires login (explain why it is still acceptable)
- [ ] `robots.txt` allows the listing/search paths (checked by `automation/robots_check.py`)

**Search parameters**
<!-- How keywords and location are passed (query params, path, filters). Which location ids does it use,
     and where can a user find them? They must be configurable in `sources.<id>` of jobhunter.yaml. -->

**Fields available on the listing / detail page**
- [ ] Title  - [ ] Company  - [ ] Location  - [ ] Salary  - [ ] Description  - [ ] Posted date

**Willing to implement it?**
- [ ] Yes (see "Adding a New Scraper Source" in CONTRIBUTING.md)
