# Security Policy

## Supported versions

| Version | Supported |
|---|---|
| v1.1.1+ | ✅ |

## Reporting a vulnerability

Please report security issues **privately** (do not open a public issue):

- Use GitHub: **Security → Report a vulnerability** on this repo (creates a private security advisory), or
- Email the maintainer via the privacy-preserving address: `chanyanming-a11y@users.noreply.github.com`

You can expect an initial response within a few days.

## Known considerations

- **Cookies are sensitive.** `fetch_youtube.py` can read cookies via `--cookies <file>` or
  `--cookies-from-browser`. The skill never writes cookies to disk or to the repository.
  Never commit a `cookies.txt` — it contains a valid YouTube session. `.gitignore` excludes it.
- **External transcript fetching (SSRF surface).** `page_fallback.py` follows Substack-style links
  found in a video's description to fetch transcripts. Host validation now blocks IP literals,
  `localhost`, `.local`/`.internal` and cloud-metadata hosts, but the fetch still targets a host chosen
  by the video's uploader. Only run this on videos you trust, and review description links.
- **Reports embed third-party content.** Generated `report.html` / `report.md` contain YouTube captions
  and comments (third-party content). Redistributing large portions publicly may breach YouTube's ToS;
  use `render_report.py --no-transcript` for public sharing.
