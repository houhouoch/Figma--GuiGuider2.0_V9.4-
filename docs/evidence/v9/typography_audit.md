# GUI Guider Typography Audit

## Summary

- Figma text nodes: 664
- Baseline GUI labels: 647
- Candidate GUI labels: 664
- Matched baseline/candidate labels: 647
- New candidate labels: 17
- Font family changes on matched labels: 0
- Font size changes on matched labels: 0
- Padding-top changes on matched labels: 4
- Alignment changes on matched labels: 6
- Width changes on matched labels: 0
- Height changes on matched labels: 4
- Position changes on matched labels: 54
- Candidate/Figma family mapping mismatches: 0
- Candidate/Figma size mismatches: 0
- Figma labels with explicit line height: 599
- Missing candidate font files: 0

## Interpretation

Matched labels preserve the baseline GUI Guider font family and size.
Any review workspace must include every referenced file under
`resources/font`; otherwise GUI Guider falls back to a different font and
all width, height, baseline, and clipping comparisons become invalid.

## Per-label Details

See `typography_audit.json` for the complete Figma/baseline/candidate record.
