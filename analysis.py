import pandas as pd
import numpy as np
import seaborn as sns
import pyfixest as pf
import matplotlib.pyplot as plt
from pathlib import Path

tariff= "tariff_exposure_naics3.csv"

tariff = pd.read_csv(tariff)
print("=== Tariff Exposure Data ===")
print(f"Industries: {len(tariff)}")
print(f"\nTop 5 most exposed industries:")
print(tariff.nlargest(5, 'mean_tariff_increase')[
    ['naics3', 'sector_name', 'mean_tariff_increase']
].to_string(index=False))
print(f"\nBottom 5 least exposed industries:")
print(tariff.nsmallest(5, 'mean_tariff_increase')[
    ['naics3', 'sector_name', 'mean_tariff_increase']
].to_string(index=False))
print(tariff['mean_tariff_increase'].describe())
tariff_sorted = tariff.sort_values('mean_tariff_increase', ascending=True)
plt.figure(figsize=(10, 8))
plt.barh(tariff_sorted['sector_name'], tariff_sorted['mean_tariff_increase'])
plt.xlabel('Mean Tariff Increase')
plt.title('Section 301 Tariff Exposure by Industry (NAICS-3)')
plt.tight_layout()
plt.savefig('tariff_exposure_by_industry.png')
plt.show()


