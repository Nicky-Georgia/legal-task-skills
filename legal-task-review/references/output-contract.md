# Output contract

Use this contract for both scratch JSON files and the rendered final response.

## Allowed ratings

Each dimension must use exactly one:

- `Looks sound`
- `Minor concerns`
- `Major concerns`
- `Not assessed`

## Dimensions

### Legal workflow

Would a lawyer do this work in practice? Are the scope and requested
deliverables appropriate?

The optional comment identifies any unrealistic role, scope, or deliverable and
explains its practical effect.

### Matter realism

Are the client situation, facts, and materials realistic and coherent, with
sufficient inputs for the assignment?

The optional comment identifies an unrealistic fact or missing input, explains
its impact, and says whether a conditional answer could still satisfy the
assignment. For a large or potentially excessive document pack, include a brief
assessment of the materials' relevance, necessity, and proportionality to the
assignment, even if the volume appears justified. Support concerns with
inspected examples or document groups, explain the practical burden, and state
sampling limits. File count alone is not a defect.

### Reference answer / work product

Does the reference make legal and practical sense and provide a usable answer or
work product? Treat it as reviewable, not authoritative.

The optional comment identifies a passage, calculation, or deliverable and
explains the concern. State when an apparent error still requires verification.

### Task-scoring rubric

Assess the task-scoring rubric, not this review form. Does it test what matters,
align with the assignment, and allow defensible alternatives?

The optional comment gives the criterion ID when one is available and a concrete
example of unfair scoring, overlap, or a defensible alternative the rubric would
reject.

## Allowed recommendations

Use exactly one:

- `Promising`
- `Minor revision`
- `Major revision`
- `Unsuitable`
- `Insufficient information`

This is a provisional recommendation from the short review, not final approval.

The recommendation summary must be 1 to 3 sentences. Give the decisive reason
and say whether local edits can repair the task or substantial redesign is
needed. Refer to the dimension comments instead of repeating them.

Suggestions identify important gaps or changes that would make the task more
realistic, useful, or fair to evaluate. Use exactly `No further suggestions`
when none are needed.

## Estimated work hours

Place this section after Suggestions, at the end of the review:

Active time for a lawyer familiar with this practice area to read, research,
draft, and check the assignment using the supplied materials. Exclude this
review and waiting for outside information. Use Cannot estimate if missing
inputs prevent a reasonable estimate.

Store `estimated_work_hours` as a single positive, finite JSON number of hours
(decimals allowed), or exactly the string `Cannot estimate`. Do not use a range
or store the unit in this field. Render a number as `Estimate: 12 hours`, for
example, or the fallback as `Estimate: Cannot estimate`. The humanizer must
preserve this field unchanged.

## Scratch JSON schema

Both `stage1.json` and `final.json` use this shape:

```json
{
  "legal_workflow": {
    "rating": "Looks sound",
    "comment": ""
  },
  "matter_realism": {
    "rating": "Looks sound",
    "comment": ""
  },
  "reference_answer_work_product": {
    "rating": "Looks sound",
    "comment": ""
  },
  "task_scoring_rubric": {
    "rating": "Looks sound",
    "comment": ""
  },
  "recommendation": "Promising",
  "recommendation_summary": "One to three sentences.",
  "suggestions": "No further suggestions",
  "estimated_work_hours": 12
}
```

All keys are required. Use an empty string for an omitted optional comment. Do
not add keys.
