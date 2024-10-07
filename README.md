# biomethane-to-ammonia

## Overview
Repository to share the data and code associated with the scientific article **Istrate et al. One-tenth of EU’s biomethane potential combined with carbon capture and storage can shift the region’s ammonia production to net-zero. One Earth (2024)**. The repository contains data files and code to import the life cycle inventories (LCIs), reproduce the results, and generate the figures presented in the article.

## Repository structure
The data folder includes:
- `inventories.xlsx` contains the LCI datasets for biomethane and ammonia production formatted for use with [Brightway](https://github.com/brightway-lca).
- `sustainable_biomethane_potential_Europe.xlsx` contains data on the sustainable biomethane potential in Europe disaggregated by feedstock and country.
- `ammonia_production_europe.xlsx` contains ammonia production levels in the EU in 2021.
- `SA_methane leakage_for presample.xlsx` contains data to perform sensitivity analysis on the methane leakage with [presamples](https://github.com/PascalLesage/presamples)
- `SA_upgrading technology_presamples.xlsx` contains data to perform sensitivity analysis on upgrading technologies with [presamples](https://github.com/PascalLesage/presamples)
- `results` folder within data contains csv files with the results, which are used in `05_visualization.ipynb` for analysis and visualization purposes.

The notebooks folder includes:
- `01_project_setup.ipynb` sets up a new Brightway project and imports the ecoinvent database.
- `02_lci.ipynb` imports the LCIs and regionalize some datasets (e.g., biomethane supply based on the bimethane potential).
- `03_lcia.ipynb` calculates life cycle impacts and all the additional results presented in the paper (e.g., calculation of blending ratios).
- `04_sensitivity_analysis.ipynb` performs the sensitivity analysis.
- `05_visualization.ipynb` imports all results and generates the figures presented in the scientific article.

The src folder contains supporting functions required to regionalize LCIs and perform the calculations.

## How to get propertary data

Some of the LCI datasets in the `inventories.xlsx` file are partially based on data from the ecoinvent LCI database. To comply with licensing requirements, 
the file shared in this repository does not include these data points. If you hold a valid ecoinvent license, please contact me directly to receive the full input files containing all ecoinvent data points.

## How to use
To ensure the replication of the results presented in the article, it is highly recommended starting a new environment and installing the `requirements.txt`.

Using Anaconda, create a new environment:
```
conda create -n bio_nh3 python==3.10.2
```

Activate the new environment:
```
conda activate bio_nh3
```

Next, change directory towards the repository directory in your machine:
```
conda cd your/repository
```

And install the requirements
```
pip install -r requirements.txt
```

Once in the new environment, run the notebooks following the indicated order.

Feel free to reach out if you encounter any issues—I'm happy to help!