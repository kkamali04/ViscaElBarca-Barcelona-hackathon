# Source and data attribution

The organiser sources under `more-than-a-hack-2027-main/` are preserved from
Metrica Sports' [More Than A Hack 2027 repository](https://github.com/metrica-sports/more-than-a-hack-2027),
commit `f8f2629ff1e0985f81d7e59d8413678514ee1530`. Their original
[licence](more-than-a-hack-2027-main/LICENSE) and citation file remain alongside
the code. We use their exact possession metric and format validator, and retain
their smooth50 method as a reference/fallback. Our estimator is described in
`SOLUTION.md`; the fallback is not our original method.

The independent training/validation dataset is *An integrated dataset of
spatiotemporal and event data in elite soccer* (Sportec/DFL), described in
[Scientific Data (2025)](https://www.nature.com/articles/s41597-025-04505-y),
with the original [Figshare dataset record](https://springernature.figshare.com/articles/dataset/An_integrated_dataset_of_spatiotemporal_and_event_data_in_elite_soccer/28196177).
It is distributed under **Creative Commons Attribution 4.0**. The acquisition
script uses the public [PySport mirror](https://huggingface.co/datasets/pysport/idsse-data)
and records integrity hashes locally. Original XML and coordinate/label caches
are local and excluded from Git. The bundled small numeric tree model is trained
on the development match J03WOH; its provenance records the source, transformation
and training conditions. Provider positions were translated to a corner origin;
labels map inactive play to D and active home/away control to H/A.

Scikit-learn (BSD-3-Clause) is used only for training and export verification.
NumPy (BSD-3-Clause) supplies numeric inference; pandas (BSD-3-Clause) is used by
the organiser's validator. Other installed dependency notices remain in their
package distributions. No competitor predictions, weights, tuned constants or
implementation modules were copied into this estimator. Public competitor code
was inspected as research context; see `research/COMPARABLES.md`.

The restricted challenge assets have their own participant terms. They are
excluded from the reproducibility package, regardless of file size.
