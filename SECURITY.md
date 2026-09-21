# Security Policy

## Supported versions

Echoturn is early software: only the latest release on `main` is supported.

## Reporting a vulnerability

Please report suspected vulnerabilities privately through GitHub's
[private vulnerability reporting](https://docs.github.com/en/code-security/security-advisories/guidance-on-reporting-and-writing-information-about-vulnerabilities/privately-reporting-a-security-vulnerability)
on this repository, rather than opening a public issue.

Include what you can: affected version or commit, a minimal reproduction, the
impact you believe it has, and whether it needs a provider key to trigger.

We aim to acknowledge within a few days and to ship a fix or a written
mitigation within 30 days of a confirmed report.

## Scope notes

Things worth reporting here:

* An event that leaks data the caller did not ask for (for example, provider
  error text being forwarded verbatim to an end user instead of a generic
  message).
* A way to make the pipeline keep running after cancellation, or to make two
  turns write into the same transcript at once.
* Audio or transcript content reaching a place the host did not choose.

Things that are **not** vulnerabilities in this project, because they are the
host's decision:

* Which providers you configure, and whether your keys are exposed there.
* Whether your own HTTP layer authenticates callers; Echoturn ships a pipeline,
  not an authentication system.
