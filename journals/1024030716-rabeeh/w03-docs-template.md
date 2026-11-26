# Week 3: The Documentation Template

*10 – 16 Aug 2026*

## What I did

Adapted the documentation site: theme overrides, the TIET logo, our stylesheet, and the Python project file. Removed the template's sample "criteria for project selection" page.

## Problem

The template's `mkdocs.yml` loaded more plugins than our site needed, including a git-authors plugin.

## Fix

Removed the git-authors plugin and kept the build to the theme and the Markdown extensions we actually use.

## Learned

Documentation is part of the build. Fewer moving parts make it build reliably, both locally and in CI.
