# Validation

`make check` validates metadata, exact-source SHA-256 checksums and Python syntax.
A negative test checks rejection of wrong metadata and unrecorded source changes.
Agent behavior, Herdr integration and the SSSF live runtime are not exercised by
this export check. No evaluation transcripts or machine credentials are shipped.
