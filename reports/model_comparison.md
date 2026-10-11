# Model Training and Evaluation Report

Models were trained using the saved Phase 2 training split. The Phase 2 test split was not used for fitting, resampling, or selecting the model.
Class weights were applied as per-row balanced sample weights calculated from the relevant training rows only. No resampling was used.
Both test evaluations use the default 0.5 probability threshold; probabilities are model estimates, not calibrated real-world failure probabilities.

## Test set metrics

| Model | Precision | Recall | F1 | Average precision (PR-AUC) | ROC-AUC | Accuracy | False positives | False negatives |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Random Forest | 0.564 | 0.779 | 0.654 | 0.784 | 0.967 | 0.972 | 41 | 15 |
| XGBoost | 0.549 | 0.824 | 0.659 | 0.810 | 0.973 | 0.971 | 46 | 12 |

Confusion matrices use rows = actual `[0, 1]` and columns = predicted `[0, 1]`.

### Random Forest

Confusion matrix: `[[1891, 41], [15, 53]]`.
This model missed **15** failures (false negatives) and raised **41** false alarms (false positives) on the test split.

### XGBoost

Confusion matrix: `[[1886, 46], [12, 56]]`.
This model missed **12** failures (false negatives) and raised **46** false alarms (false positives) on the test split.

## Training-only model selection

The recommended model is **XGBoost**, selected using the higher mean F2 score over 5-fold stratified cross-validation on training data only. F2 weights recall more heavily than precision to reflect the cost of missed failures; PR-AUC is the next tie-breaker.

| Model | CV precision | CV recall | CV F2 | CV average precision (PR-AUC) |
|---|---:|---:|---:|---:|
| Random Forest | 0.593 | 0.764 | 0.722 | 0.747 |
| XGBoost | 0.546 | 0.797 | 0.730 | 0.774 |

## Why accuracy is secondary

Only 3.39% of the full dataset is failures. A classifier that predicts no failures would still achieve about 96.61% accuracy while detecting none of them. Precision, recall, F-scores, PR-AUC, ROC-AUC, and false-positive/false-negative counts provide a more useful view of failure detection and alarm burden.

No prediction horizon is implied by this classification task.
