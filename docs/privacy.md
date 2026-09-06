# Privacy

MemoryLane deals with personal browsing information, so privacy is an important part of the system design.

## Automatic capture filtering

Automatic capture does not blindly submit every browser page to the backend.

The eligibility rules exclude categories such as:

- Social-media pages
- Banking and financial services
- Login and authentication pages
- Account, checkout, billing, payment, and wallet paths
- Internal browser pages
- Search-engine result pages
- Utility pages
- Common non-text resources

The filtering is applied by the browser extension before an automatically captured page is posted to the backend.

## Stored browsing content

A MemoryLane memory can contain the extracted textual content of a webpage, along with metadata such as its URL, title, domain, timestamp, and embeddings.

This means the local MemoryLane data store should be treated as sensitive personal data.

## Gemini summarization

Gemini is optional and is not required for the core retrieval pipeline.

When Gemini-based summarization is enabled, content used for summarization can be sent to an external API. This introduces a privacy consideration that does not apply in the same way to purely local retrieval.

Sensitive pages or content should therefore not be sent to an external summarization service unless the user is comfortable with the associated data-handling implications.

## Privacy direction

A future privacy-oriented direction for MemoryLane is greater local-first processing and storage, reducing the need to send personal browsing content to external services.
