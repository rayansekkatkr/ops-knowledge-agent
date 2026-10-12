# Hanbit Logistics — Customer Support and Service Level Policy

Document owner: Customer Success · Version 2.0 · Effective: 1 July 2026

## 1. Support plans

Hanbit Logistics offers three support plans to business customers.

| Plan | Support hours | Channels | Monthly price |
|---|---|---|---|
| Standard | Business hours, Monday to Friday, 9:00–18:00 KST | Email, portal | Included |
| Business | 7:00–22:00 KST, seven days a week | Email, portal, phone | 450,000 KRW |
| Enterprise | 24/7 | Email, portal, phone, dedicated Teams channel | Custom contract |

Korean public holidays are not business days for the Standard plan.

## 2. Response time targets

Response time is measured from ticket creation to the first human response.

| Severity | Standard | Business | Enterprise |
|---|---|---|---|
| SEV1 | 4 business hours | 1 hour | 15 minutes |
| SEV2 | 8 business hours | 4 hours | 30 minutes |
| SEV3 | 2 business days | 1 business day | 4 hours |
| SEV4 | 5 business days | 3 business days | 2 business days |

## 3. Service level objectives

| Service | Availability SLO (monthly) | Latency SLO |
|---|---|---|
| Shipment Tracking API | 99.9% | 95% of requests under 300 ms |
| Partner Portal | 99.5% | 95% of page loads under 2 seconds |
| Warehouse Mobile App backend | 99.9% | 95% of requests under 500 ms |

A 99.9% monthly availability SLO corresponds to an error budget of about 43 minutes of downtime per 30-day month. When a service has consumed more than 75% of its monthly error budget, non-urgent feature releases for that service are frozen until the budget recovers or the Head of Platform grants an exception.

Planned maintenance announced at least 72 hours in advance does not count against the SLO. Maintenance windows are Sundays from 2:00 to 5:00 KST.

## 4. Service credits (Enterprise plan only)

If the monthly availability of the Shipment Tracking API falls below the SLO, Enterprise customers are entitled to a service credit on their next invoice:

- Below 99.9% and at least 99.0%: 10% of the monthly fee
- Below 99.0% and at least 95.0%: 25% of the monthly fee
- Below 95.0%: 50% of the monthly fee

Credits must be requested by the customer within 30 days after the end of the affected month. Credits are the customer's sole remedy for missed SLOs.

## 5. Escalation

If a customer considers that a ticket is not handled correctly, they can ask for escalation. Escalation goes first to the Support Team Lead, then to the Customer Success Manager assigned to the account, then to the Head of Customer Success. Enterprise customers can escalate directly to their Customer Success Manager.

## 6. Out of scope

Support does not cover custom integrations developed by the customer, issues caused by the customer's own network, or requests for new features. Feature requests are logged in the product feedback portal and reviewed monthly.
