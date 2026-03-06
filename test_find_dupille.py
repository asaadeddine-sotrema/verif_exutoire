import os
import glob
print("Looking for Dupille files in /home/amine/projects/verif_exutoire/data/")
for f in glob.glob("/home/amine/projects/verif_exutoire/data/*.xlsx"):
    print(f)
