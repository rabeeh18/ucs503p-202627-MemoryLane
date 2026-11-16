*[BM25]: Best Matching 25: a keyword ranking that scores pages by how often they use the query's words, favouring rare words and short passages
*[KNN]: k-nearest neighbours: finds the stored vectors closest to the query's vector, i.e. the passages closest in meaning
*[RRF]: Reciprocal Rank Fusion: combines several ranked lists by adding 1 / (60 + rank) from each list
*[HNSW]: Hierarchical Navigable Small World: the graph index Solr uses to find nearest vectors quickly
*[PKCE]: Proof Key for Code Exchange: protects the sign-in code so only the app that started the sign-in can use it
*[JWKS]: JSON Web Key Set: the public keys Cognito publishes, used to check that a token's signature is genuine
*[JWT]: JSON Web Token: a signed token that says who the user is and when it expires
*[MRR]: Mean Reciprocal Rank: the average of 1 / (rank of the first relevant result); 1.0 means it was always first
*[nDCG]: normalised Discounted Cumulative Gain: a 0 to 1 score for how well a ranking puts relevant results near the top
*[ADR]: Architecture Decision Record: a short note of one design choice, why it was made and what it costs
*[DFD]: Data Flow Diagram: shows what data moves between processes, data stores and outside entities
*[SES]: Amazon Simple Email Service: sends MemoryLane's problem-report emails
*[SMTP]: Simple Mail Transfer Protocol: the standard way to send email
*[CSP]: Content Security Policy: a browser rule set that limits which scripts and connections a page may use
*[HSTS]: HTTP Strict Transport Security: tells browsers to use HTTPS only for this site
*[TLS]: Transport Layer Security: the encryption behind HTTPS
*[CORS]: Cross-Origin Resource Sharing: browser rules for which websites may call an API
*[MV3]: Manifest V3: the current format for Chrome extensions
*[SPA]: single-page app: a site that changes its address and content without reloading the page
*[edismax]: Solr's extended DisMax query parser, used for the keyword search across title and text
*[trafilatura]: the Python library that extracts a page's main text and drops menus, footers and ads
*[chunk]: a passage of up to 150 words from a page; each page is split into overlapping chunks before it's embedded
*[chunks]: passages of up to 150 words from a page; each page is split into overlapping chunks before it's embedded
*[embedding]: a list of 384 numbers that represents the meaning of a passage; similar meanings give nearby embeddings
*[embeddings]: lists of 384 numbers that represent the meaning of passages; similar meanings give nearby embeddings
*[cosine similarity]: how closely two embeddings point the same way, from -1 to 1; higher means closer in meaning
*[relevance floor]: the rule that drops results which are neither a strong keyword match nor close enough in meaning
*[page vector]: the average of a page's chunk embeddings, used to find related pages
