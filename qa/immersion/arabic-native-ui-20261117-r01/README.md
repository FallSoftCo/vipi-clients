# Arabic native rendering

The integrated iOS app preserves Arabic orthographic words intact. Both source and learning faces were visually inspected. The existing standalone `شاحن` slot still alternates to `charger`; the unsafe inner-stem slots in `الماء` and `الموسيقى` are suppressed.

This qualifies the observed joining defect only. Boundary behavior and native/JVM cases are recorded separately in `../arabic-source-orthography-20261117-r01/`. No additional provider or account operation was performed.
