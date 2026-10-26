<!--
Cadocary proposal template. Modeled on the structure and house style of Doug's past proposals.
How to fill it is in SKILL.md, under "The template". In short:

  {{fact:<id>}}      a value from /mnt/memory/cadocary-facts/. Missing or unknown: write [MISSING: <id>]
                     and add it to open_items.
  {{rfp:<what>}}     from sheet.json (the Reader's sheet) or the RFP, in the buyer's own words.
  {{price:<what>}}   from price_recommendation in research.json. Never computed from anything else.
  <!- WRITE: ... ->  prose to write, following the guidance. Delete the comment when done.
  <!- IF: ... ->     keep the block only when the condition holds.

When the RFP prescribes its own outline, the RFP wins: keep these sections' content and style but
rename, reorder, and renumber them to match the buyer's outline exactly.

The finished proposal has no {{ }} and no comments left. [MISSING: ...] markers stay, so Doug sees
every blank, and each one is in open_items.
-->

{{fact:company.legal_name}} | {{fact:approved_text.tagline}}
Page header on every page. Footer on every page: "Page <n>  {{rfp:solicitation_number}}".

# Table of Contents

<!-- WRITE: generated from the headings below, with page numbers once the page count is known. -->

# Cover Letter

<!-- WRITE: one page at most, five short paragraphs:
1. Cadocary LLC is pleased to submit this proposal in response to {{rfp:solicitation_number}} for
   {{rfp:title}}. Name the full scope proposed, in the buyer's words.
2. "We understand that this project is not simply ..." Name the buyer's two to four real priorities,
   taken from the RFP and addenda, and say the solution is built around them.
3. The experience that makes Cadocary credible, from past_performance and product facts only.
   Frame adjacent work honestly as relevant experience, never as a prior deployment of this system.
4. Who leads delivery ({{fact:team.<lead>}}), that the named team is committed, and that the plan
   fits {{rfp:performance_period}}.
   IF the facts hold approved_text.ai_use_statement, include it word for word.
5. The proposal and pricing are firm for {{rfp:validity_days}} days. Acknowledge every addendum by
   number: "We also acknowledge receipt of and compliance with Addenda {{rfp:addenda_numbers}}."
Close with one line of thanks to {{rfp:buyer}}. -->

Respectfully submitted,

[SIGNATURE: Doug signs]
{{fact:company.bid_signers}}
{{fact:company.legal_name}}

# PART I

## 1. General and Legal Information

### Company Information & Proposal Scope

| Item | Information |
| --- | --- |
| Legal Business Name | {{fact:company.legal_name}} |
| Legal Status | {{fact:company.legal_status}} |
| Business Address | {{fact:company.address}} |
| EIN | {{fact:company.ein}} |
| Washington UBI | {{fact:company.wa_ubi}} |
| UEI | {{fact:company.uei}} |
| CAGE Code | {{fact:company.cage_code}} |
| Primary Contact | {{fact:company.primary_contact}} |
| Website | {{fact:company.website}} |

**Proposal Scope**

<!-- WRITE: two paragraphs. Cadocary LLC proposes to serve as the prime contractor for {{rfp:title}}.
List every scope element proposed, in the buyer's words. Then one sentence on the shape of the
solution and the buyer's priorities it addresses. -->

*"The remainder of this page has been intentionally left blank."*

# PART II

## 2. Proposal Approach

### Understanding of {{rfp:buyer_short_name}}'s Environment

<!-- WRITE:
- The current system and vendor, and when it was put in, only as stated in the RFP, an addendum, or
  research.json (incumbent, with its cite).
- How the buyer operates: agencies, sites, shared databases, users. Use the RFP's numbers.
- "Cadocary's understanding of the replacement centers on <n> closely related priorities:" then one
  paragraph per priority with a bold lead-in ("**Data Conversion.** ..."). Cite clarifications by
  addendum and question number. -->

### Technical Solution & Implementation Approach

<!-- WRITE:
- **Solution Architecture:** hosting ({{fact:security.hosting}}), how the modules share data, and
  what is configurable by the buyer's administrators.
- Security architecture in one paragraph, from security.* facts only.
- A simple text diagram of the layers when it helps.
- One subsection per module or scope element the RFP names ("### <Module> Solution"): core
  capabilities in the buyer's terms, and how it fits the shared architecture.
- End each subsection by pointing to the buyer's response workbook or attachment for line-by-line
  compliance: "Detailed responses are provided in Attachment <x>."
Only claim capabilities the facts support. Anything to be built is described as proposed. -->

<!-- IF: the RFP includes data conversion or migration -->
### Data Conversion & Migration

<!-- WRITE: the source systems and data volumes, in the RFP's numbers. The method as a one-line
pipeline, "Extract → Map → Transform → Validate → Reconcile → Test → Production Migration", then a
paragraph on the multi-cycle process (mapping workbook approved by the buyer, test cycles, exception
and reconciliation reports, user validation, sign-off). Name the hard parts the RFP or addenda
identify. -->

<!-- IF: the RFP lists integrations or interfaces -->
### Integrations & Interoperability

<!-- WRITE: the integration scope, following the authoritative interface list (cite the RFP section or
addendum). Say plainly which interfaces addenda removed or deferred and that they are not included.
Relevant interoperability experience from the facts, framed honestly. How interfaces are tested
before production. -->

### Implementation Methodology

<!-- WRITE: the delivery period ({{rfp:performance_period}}) and how phases overlap. Then one paragraph
per phase, each with a bold lead-in: "**Phase 1 – Discovery & Validation.**" Typical phases:
discovery and validation; architecture and configuration; development and integration; data
conversion and validation; system and agency testing; training and readiness; go-live and
stabilization; ongoing support. Drop phases the scope doesn't need. Put security reviews the RFP
requires (CJIS, penetration testing) in the right phase. -->

### {{rfp:buyer_short_name}} Involvement

<!-- WRITE: one sentence that Cadocary carries primary delivery responsibility. Then short bold-lead-in
paragraphs for what the buyer provides: project stakeholders and decision makers; subject-matter
experts; system and data access (including incumbent coordination); requirements and conversion
validation; interface coordination; testing and UAT; training coordination; acceptance and
sign-off. -->

*"The remainder of this page has been intentionally left blank."*

## 3. Project Team & Management

### Project Organization

<!-- WRITE: the team size and lead, then one line per person: "<Name> – <Role>". People and roles
come only from team.* facts. -->

### Roles & Responsibilities

| Team Member | Role | Primary Responsibilities |
| --- | --- | --- |
| {{fact:team.<person>.name}} | {{fact:team.<person>.role}} | <!-- WRITE: responsibilities on this project --> |

<!-- IF: the RFP involves CJIS or other sensitive data -->
<!-- WRITE: who has production access to sensitive data, from security.* and team.* facts. Others
work with synthetic or de-identified data. -->

### Personnel Commitment

<!-- WRITE: Cadocary commits that the individuals named above will be assigned to this project.
Point to Part III for resumes. -->

### Subcontracting

<!-- WRITE: from the facts. If none: "Cadocary LLC will perform the proposed scope as prime contractor
using the personnel identified herein. No subcontractors or teaming partners are proposed." If the
facts don't say, write [MISSING: team.subcontractors]. -->

## 4. Qualifications & Relevant Experience

<!-- WRITE: an opening paragraph naming the kinds of experience that transfer, and saying plainly what
they are not (for example, not prior deployments of this exact kind of system) when that is true.
Then one paragraph per relevant product or past project, with a bold lead-in:
"**<Product> – <angle relevant to this RFP>.**" Use only past_performance.* and product.* facts,
with numbers from the facts. Close with one paragraph tying the experience to this RFP's needs.
Name a client only when the fact says the client may be named. -->

<!-- IF: the RFP asks for references -->
### References

<!-- WRITE: only references.* facts with a permission_date. Name, title, organization, contact, and
the project they speak to. Fewer than required: [MISSING: references] and an open item. -->

## 5. Schedule & Ability to Meet Deadlines

<!-- WRITE: one paragraph on how the plan fits {{rfp:performance_period}}, then the table. -->

| Workstream | Planned Window |
| --- | --- |
| <!-- WRITE --> | <!-- WRITE --> |

<!-- IF: the RFP has security, CJIS, accessibility, or similar compliance requirements -->
## 6. Security, Compliance & Accessibility

<!-- WRITE: one opening paragraph naming the standards the RFP cites. Then bold-lead-in paragraphs
from security.* facts only, typically: production data protection; personnel security; access control
and authentication; encryption and hosting; audit and monitoring; security and incident procedures;
accessibility (the standard the facts say is met). Never claim a certification, audit, or
authorization the facts don't hold. Point to the buyer's security workbook for line-by-line
answers. -->

*"The remainder of this page has been intentionally left blank."*

# PART III

## 7. Resumes

<!-- WRITE: one resume per named team member, taken from the resume in team.<person> facts. Never
write or extend a resume yourself. A missing resume is [MISSING: team.<person>.resume]. -->

# PART IV

## 8. Responses to Workbooks & Attachments

<!-- WRITE: one paragraph saying the separate submission package includes every buyer-provided
workbook, required form, and contract document, and that references to attachments in this proposal
correspond to those files. List them, from sheet.json required_forms, submission, and requirements. -->

<!-- IF: the RFP does not require a separate cost volume. Otherwise this whole part goes in cost.md. -->
# PART V

## 9. Pricing

### Basis of Estimate

<!-- WRITE: how the price was built, from price_recommendation.rationale: hours by task at the rate
from the facts, the team and schedule it assumes, that pricing is firm for {{rfp:validity_days}}
days, and the price format the RFP asks for (for example, five-year total cost of ownership).
Sales tax: include it only if the RFP asks, at a rate cited in the research or RFP. Otherwise
[MISSING: sales tax rate] and an open item. -->

### One-Time Implementation

<!-- Line items from price_recommendation whose unit is hours or a one-time unit. -->

| Category / Scope | Hours | Rate | Cost |
| --- | --- | --- | --- |
| {{price:line_items[].item}} | {{price:line_items[].quantity}} | {{price:line_items[].rate}} | {{price:line_items[].amount}} |
| **Total One-Time Implementation** | | | **{{price:one_time_total}}** |

<!-- WRITE: hardware and travel, each stated as an amount, with one sentence of reasoning. -->

### Recurring Hosting, Support & Maintenance

<!-- Line items from price_recommendation whose unit is per year. -->

| Recurring Component | Annual Cost |
| --- | --- |
| {{price:line_items[].item}} | {{price:line_items[].amount}} |
| **Total Annual Recurring Cost** | **{{price:annual_total}}** |

<!-- WRITE: what hosting and support include, and from which year recurring fees start. -->

<!-- IF: the RFP asks for a multi-year total -->
### {{rfp:term_years}}-Year Total Cost of Ownership

| Component | Amount |
| --- | --- |
| One-Time Implementation | {{price:one_time_total}} |
| Recurring, Years <x>–<y> | {{price:recurring_term_total}} |
| Subtotal | {{price:subtotal}} |
| Sales Tax (only if the RFP asks) | {{price:tax}} |
| **Total Cost of Ownership** | **{{price:total}}** |

### Pricing Assumptions

<!-- WRITE: bullets. Labor rate; team and schedule; hardware; travel; cooperation needed from the buyer
and the outgoing vendor; how out-of-scope work is priced; proposal validity. -->

### Pricing & Contract Exceptions

<!-- WRITE: every exception comes from calls_for_doug, worded as a request subject to negotiation and
pointing to the buyer's exceptions form. Typical topics: annual adjustment of recurring fees;
intellectual property (the buyer owns its data and buyer-specific deliverables, Cadocary keeps its
pre-existing software and grants a license to use it); payment terms (milestone invoicing, net 30);
indemnification, liability, insurance, termination, and warranty. Include only the ones Doug has
approved in the facts (prefs.unacceptable_terms) or listed as a call for him. -->

## Conclusion

<!-- WRITE: one paragraph: thanks, the solution in one sentence, the committed team, and the
delivery period. -->

Respectfully submitted,

[SIGNATURE: Doug signs]
{{fact:company.bid_signers}}
{{fact:company.legal_name}}
