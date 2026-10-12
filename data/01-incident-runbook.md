# Hanbit Logistics — Production Incident Runbook

Document owner: Platform Engineering · Version 3.2 · Last review: September 2026

## 1. Purpose and scope

This runbook describes how Hanbit Logistics detects, handles and closes production incidents affecting customer-facing services: the Shipment Tracking API, the Partner Portal and the Warehouse Mobile App. It applies to the on-call engineer, the Incident Commander and the support team.

## 2. Severity levels

| Severity | Definition | Example | First response |
|---|---|---|---|
| SEV1 | Full outage of a customer-facing service, or data loss or security breach | Tracking API returns errors for all customers | 15 minutes, 24/7 |
| SEV2 | Major degradation, a key feature unavailable, no workaround | Partner Portal login fails for one region | 30 minutes, 24/7 |
| SEV3 | Minor degradation with a workaround | Slow CSV exports in the Partner Portal | 4 business hours |
| SEV4 | Cosmetic issue or question | Typo in an email template | 2 business days |

When in doubt, declare the higher severity. Downgrading later is cheap; under-reacting is not.

## 3. Roles

- **On-call engineer**: first responder. Acknowledges the page, assesses severity, starts mitigation.
- **Incident Commander (IC)**: required for SEV1 and SEV2. Coordinates the response, makes decisions, does not debug. The IC rotation is held by senior engineers and engineering managers.
- **Communications lead**: updates the status page and the customer success team. For SEV1, updates are posted every 30 minutes; for SEV2, every 60 minutes.

## 4. Response procedure

1. **Acknowledge** the PagerDuty alert within 5 minutes. If the primary on-call does not acknowledge within 10 minutes, the alert escalates automatically to the secondary on-call, then to the Head of Platform after 20 minutes.
2. **Open an incident channel** in Teams named `inc-YYYYMMDD-short-name` and post the alert link.
3. **Assess severity** using section 2 and announce it in the channel.
4. **Mitigate first, investigate later.** Preferred mitigations, in order: roll back the last deployment, disable the feature flag, scale out the affected service, fail over to the secondary region (Busan).
5. **Verify recovery** using the service dashboards in Grafana: error rate back under the SLO threshold and p95 latency back to normal for at least 15 minutes.
6. **Close the incident** and record the timeline in the incident tracker.

## 5. Rollback

All services are deployed through GitLab CI with Argo CD. A rollback is done by reverting the release commit in the `deploy-config` repository; Argo CD syncs within 3 minutes. A rollback never requires approval during a SEV1 or SEV2 incident.

## 6. Post-incident review

A blameless post-incident review is mandatory for every SEV1 and SEV2, and must be published within 5 business days. It includes a timeline, the root cause, what went well, what went wrong, and action items with owners and due dates. Action items from SEV1 reviews are tracked weekly by the Head of Platform until closed.

## 7. Contacts

- Platform on-call: PagerDuty service "Platform Primary"
- Head of Platform: Ji-won Park
- Security incidents: follow the Security Policy, section 6, and page the Security on-call in addition to Platform.
