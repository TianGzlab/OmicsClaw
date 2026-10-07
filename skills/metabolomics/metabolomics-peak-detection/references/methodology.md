# Methodology

scipy.signal.find_peaks uses prominence, optional height and a row-index distance after sorting by rt. Widths are measured at half prominence in row-index units.

`detect_peaks` expects mz and rt plus sample/intensity columns. `distance` and `width` are row positions, not seconds. NaNs follow scipy signal semantics and are not imputed. Empty outputs keep their CSV column schema.
