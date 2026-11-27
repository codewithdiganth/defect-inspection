# Sample Evaluation Report

Confusion matrix (rows = actual, columns = predicted):

| Actual / Predicted | Normal | Defective |
|---|---:|---:|
| Normal | 30 | 0 |
| Defective | 0 | 30 |

- TP: 30
- FN: 0
- FP: 0
- TN: 30
- Accuracy (correct / successful labeled predictions): 1.0000
- Defect recall (TP / (TP + FN)): 1.0000
- Failed or missing predictions: 0
- Images without a label row: 0

Validation fixture outcomes:
- `not_an_image.jpg`: Rejected: File is not a valid JPEG or PNG image
- `corrupt_image.png`: Rejected: File is not a valid JPEG or PNG image
- `too_small.png`: Rejected: Image is 32x32; each dimension must be between 64 and 4096 pixels

No false negatives were observed, but 60 synthetic samples cannot establish real-world reliability.