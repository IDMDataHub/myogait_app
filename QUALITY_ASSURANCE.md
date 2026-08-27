# Quality assurance and risk controls

MyoGait App is research software. This file records the engineering controls
used to make analyses reproducible and to prevent misleading derived metrics.
It is not a medical-device risk-management file and does not claim clinical
certification.

## Release evidence

Every change is expected to have a corresponding test. GitHub Actions runs the
application tests on supported Python versions on Linux and Windows, lints the
code, enforces a coverage floor, builds the package, and verifies installed
dependencies. MyoGait is versioned independently and is recorded in each
export's provenance sidecar.

## Risk register

| ID | Risk | Control | Verification |
| --- | --- | --- | --- |
| R-01 | Invalid or malformed pivot is analysed. | Structural validation rejects invalid roots, frames and frame rates before loading. | `tests/test_validation.py` |
| R-02 | Two uploads with the same name overwrite or reuse one another. | Content-addressed, atomic upload storage. | `tests/test_storage.py` |
| R-03 | No gait cycle supports a derived result. | Quality assessment marks the analysis as `rejected`; the UI stops interpretation while retaining raw-data export. | `tests/test_quality_gate.py` |
| R-04 | Low extraction quality is presented without context. | Score thresholds classify analyses as accepted, warning or rejected; the verdict and reasons are written to provenance. | `tests/test_quality_gate.py`, `tests/test_provenance.py` |
| R-05 | A result cannot be reproduced after package or configuration changes. | Export sidecars record package versions, pipeline configuration, input SHA-256, source type, model and quality verdict. | `tests/test_provenance.py` |
| R-06 | Implausible calibration silently shifts angles or distance estimates. | MyoGait calibration bounds, segment cross-checks and UI warnings remain enabled by default. | `tests/test_calibration.py` |
| R-07 | A local installation has incompatible dependencies or an unusable command. | CI installs the project, runs `pip check`, builds a wheel and smoke-tests the installed CLI. | `.github/workflows/tests.yml`, `.github/workflows/publish.yml` |
| R-08 | A derived progression metric is used for a treadmill-like recording. | MyoGait labels image-progression step and stride lengths as not valid for treadmill trials. | MyoGait analysis tests and exported limitation field |

## Operating rules

1. Do not remove a control without updating this register and its automated
   verification.
2. Treat a `rejected` verdict as a stop for interpretation of derived metrics,
   not as a reason to discard the source data.
3. Keep patient identifiers out of provenance files, logs, test fixtures and
   issue reports.
4. Before publishing a validation result, freeze the MyoGait/App versions,
   pipeline configuration, inclusion criteria and acceptance thresholds.
5. Record newly observed failure modes as a risk, then add the smallest
   automated regression test that proves the mitigation.
