# Automatic Capture

MemoryLane can capture eligible webpages automatically while the browser is being used.

The Chrome extension supports two capture modes:

- **Automatic** — eligible pages are captured when loading completes.
- **Manual** — pages are saved explicitly through the extension.

## Automatic capture flow

When automatic mode is enabled, the extension watches for completed page loads.

```text
Page finishes loading
        ↓
Check capture eligibility
        ↓
Extract readable content
        ↓
Send eligible content to /memory
        ↓
Process and store the memory
```

The extension also avoids repeatedly submitting the same URL within a short period and prevents duplicate in-flight captures.

## What automatic capture filters

Automatic capture is deliberately more selective than simply saving every URL.

The eligibility rules exclude categories such as:

- Social-media sites
- Banking and financial services
- Login, authentication, account, checkout, billing, and payment paths
- Browser and internal browser URLs
- Search-engine result pages
- Utility pages such as error, privacy, terms, cookie, and sitemap pages
- Common non-text resources such as images, media, archives, and executable files

YouTube receives special handling because supported video pages can be stored through their transcripts.

## Content threshold

For ordinary webpages, automatic capture requires enough extracted text to be useful. Pages with very little readable content are skipped.

Manual capture can bypass the automatic eligibility filtering when the user explicitly chooses to remember a page.

## Why filtering matters

Automatic capture is intended to make MemoryLane useful without turning every browsing action into a stored memory. Filtering reduces unnecessary content and helps keep sensitive or low-value pages out of the memory collection.
