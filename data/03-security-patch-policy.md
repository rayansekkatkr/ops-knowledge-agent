# Hanbit Logistics — Information Security and Patch Management Policy

Document owner: Security Team · Version 4.1 · Approved by the CISO, August 2026

## 1. Scope

This policy applies to all employees, contractors and service providers who access Hanbit Logistics systems, including cloud accounts (Azure and AWS), source code repositories, production servers and laptops.

## 2. Access control

- Access follows the principle of least privilege. Production access is granted per team, never per individual exception.
- Multi-factor authentication is mandatory for all accounts. Phishing-resistant MFA (FIDO2 security keys or Windows Hello for Business) is mandatory for administrators.
- Privileged access to production uses just-in-time elevation through Microsoft Entra Privileged Identity Management, limited to 4 hours per activation.
- Access rights are reviewed every quarter by each team manager. Accounts of people who leave the company are disabled on their last working day.

## 3. Secrets management

Secrets (API keys, database passwords, certificates) must be stored in Azure Key Vault. Secrets must never be committed to a Git repository; every repository runs secret scanning in CI, and a detected secret blocks the merge. A leaked secret must be rotated within 24 hours, even if the repository is private.

## 4. Vulnerability and patch management

Vulnerabilities are prioritized by CVSS score and by exposure. The maximum delays to deploy a fix in production are:

| Severity (CVSS v3/v4) | Internet-facing systems | Internal systems |
|---|---|---|
| Critical (9.0–10.0) | 72 hours | 7 days |
| High (7.0–8.9) | 7 days | 30 days |
| Medium (4.0–6.9) | 30 days | 90 days |
| Low (0.1–3.9) | Next regular release | Next regular release |

A vulnerability listed in the CISA Known Exploited Vulnerabilities catalog is always treated as Critical, whatever its CVSS score.

If a fix cannot be deployed within the delay, the system owner must document a risk exception with a compensating control (for example a WAF rule or network isolation). Exceptions are approved by the CISO and last at most 90 days.

Operating system patches for servers are applied automatically every second Tuesday of the month, during the Sunday maintenance window that follows.

## 5. Software supply chain

Container images are rebuilt weekly from approved base images and scanned with Trivy in CI. An image with a Critical vulnerability that has a fix available cannot be deployed to production. Each release produces a Software Bill of Materials (SBOM) in CycloneDX format, stored with the release artifacts for at least 5 years.

## 6. Security incidents

Any suspected security incident (lost laptop, phishing click, leaked secret, unusual access) must be reported immediately to security@hanbit-logistics.example and to the Security on-call through PagerDuty. A confirmed personal data breach must be reported to the Personal Information Protection Commission (PIPC) within 72 hours, as required by the Korean Personal Information Protection Act. The Security Team leads the response; Platform Engineering supports it following the Incident Runbook.

## 7. Training

All employees complete security awareness training when they join and once a year. Engineers also complete secure coding training once a year.
