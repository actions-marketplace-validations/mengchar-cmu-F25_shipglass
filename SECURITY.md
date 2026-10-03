# Security

Shipglass processes local archives and produces local HTML reports. Archive inputs may be untrusted. The code should never execute archive contents or extract their files into the user's project.

The reader rejects unsafe paths and duplicate normalized paths. It records archive links without following them. Scans are limited to 50,000 archive members, including directories, with a 1 GiB limit for both the input archive and expanded payload. Invalid or oversized inputs fail the scan instead of producing a complete-looking partial report.

Reports contain paths and metadata rather than file contents. Those paths can still expose internal project names or other sensitive information. Check reports before publishing or attaching them to a public issue.

Packaging cautions are based on filenames. They are not a complete secret scan, malware scan, or guarantee of package safety.

ZIP payloads support STORE and DEFLATE only and validate expanded size, CRC, and stream completion. Central-directory parsing is bounded before member objects are allocated (50,000 members and 64 MiB of directory data). ZIP64 central directories and other compression methods are rejected. These limits reduce resource abuse; the process is not an operating-system sandbox.

## Report a vulnerability

Use [GitHub's private vulnerability reporting](https://github.com/mengchar-cmu-F25/shipglass/security/advisories/new) if it is available. Include a minimal synthetic reproducer, affected version, platform, and the observed impact. Never send a real credential as a test case.

If private reporting is unavailable, open a minimal issue asking for a private reporting channel. Do not include exploit details or sensitive attachments in that public issue.

Security fixes target the latest release. There is no separate maintenance branch for older versions yet.
