""""
Functions to perform LCA results analysis
"""

import pandas as pd
import numpy as np
import brightway2 as bw
import presamples as ps
import geopandas as gpd
import pycountry
import copy


def multi_lcia(activity, lcia_methods, amount=1):
    """
    Calculate multiple impact categories.
    
    Parameters:
    - activity (object): An activity object representing the product or process being assessed.
    - lcia_methods (dict): A dictionary of impact categories and their corresponding method. 
                           The keys are the names of the impact categories and the values are the methods to be used for each category.
    - amount (float): The functional unit of the assessment. Defaults to 1.
    
    Returns:
    - multi_lcia_results (dict): A dictionary of impact categories and their corresponding scores.
                                 The keys are the names of the impact categories and the values are the scores.
    """
    lca = bw.LCA({activity.key: amount})
    lca.lci()
    multi_lcia_results = dict()
    for impact in lcia_methods:
        lca.switch_method(lcia_methods[impact])
        lca.lcia()
        multi_lcia_results[impact] = lca.score
    return multi_lcia_results


def lcia_system_contribution(activity, lcia_methods, activity_amount=1):
    '''
    This function computes the contribution of each system component to the total impact
    Based on: https://github.com/brightway-lca/brightway2/blob/master/notebooks/Contribution%20analysis%20and%20comparison.ipynb

    Parameters:
    - activity (object): An activity object representing the product or process being assessed.
    - lcia_methods (dict): A dictionary of impact categories and their corresponding method. 
                           The keys are the names of the impact categories and the values are the methods to be used for each category.
    - amount (float): The functional unit of the assessment. Defaults to 1.
    
    Returns:
    - system_contributions (dict): A nested dictionary of impact categories and system components and their corresponding LCIA scores.
                                   The keys are the names of the impact categories and the name of the system components, while the values are the scores.
    '''
    system_components = ['Direct emissions',
                         'Feedstock supply chain',
                         'Heating',
                         'Electricity from grid',
                         'Other',
                         'Total']
    
    # Create am empty dict with the structure
    system_contributions = dict()
    for impact in lcia_methods:
        system_contributions[impact] = {}
        for category in system_components:
            system_contributions[impact][category] = 0
    
    # Add total impact
    multi_lcia_results = multi_lcia(activity, lcia_methods, activity_amount)
    for impact in multi_lcia_results:
        system_contributions[impact]['Total'] = multi_lcia_results[impact]
                
    # Contribution of each system component
    for exc in activity.technosphere():
        exc_amount = activity_amount * exc['amount']
        
        # Feedstock supply chain
        if exc.input['name'] in ['market group for natural gas, high pressure',
                                 'market for biomethane, 24 bar',
                                 'market for biomethane, 24 bar w/ CCS',
                                 'hydrogen production, gaseous, 25 bar, from electrolysis with wind electricity',
                                 'nitrogen gaseous, from cryogenic distillation, without compression']:
            multi_lcia_results = multi_lcia(exc.input, lcia_methods, exc_amount)
            for impact in multi_lcia_results:
                system_contributions[impact]['Feedstock supply chain'] += multi_lcia_results[impact]
        
        # Heating
        elif 'heat production' in exc.input['name'] or 'steam production' in exc.input['name']:
            multi_lcia_results = multi_lcia(exc.input, lcia_methods, exc_amount)
            for impact in multi_lcia_results:
                system_contributions[impact]['Heating'] += multi_lcia_results[impact]            
                        
        # Electricity
        elif 'market group for electricity' in exc.input['name']:
            multi_lcia_results = multi_lcia(exc.input, lcia_methods, exc_amount)
            for impact in multi_lcia_results:
                system_contributions[impact]['Electricity from grid'] += multi_lcia_results[impact]    
        
        # Infrastructure + other utilities
        else:
            multi_lcia_results = multi_lcia(exc.input, lcia_methods, exc_amount)
            for impact in multi_lcia_results:
                system_contributions[impact]['Other'] += multi_lcia_results[impact]
                        
    # Direct emissions
    method_CFs = dict() # First load element flows exchanges and characterization factors into a dictionary
    for impact in lcia_methods:
        method_CFs[impact] = {}
        method_CFs[impact] = {ef[0]: ef[1] for ef in bw.Method(lcia_methods[impact]).load()}
                                 
    for exc in activity.biosphere():
        exc_amount = exc['amount']
        exc_key = bw.get_activity(exc.input).key
        for impact in lcia_methods:
            if exc_key in method_CFs[impact]:
                system_contributions[impact]['Direct emissions'] += exc_amount * method_CFs[impact][exc_key]
    
    return system_contributions


def carbon_footprint_blending(cf_biomethane, cf_fossil):
    """
    This function computes the carbon footprint of ammonia production based on
    the natural gas-biomethane blending strategy as a function of blending ratios 

    - cf_biomethane: carbon footprint of ammonia production from biomethane
    - cf_fossil: carbon footprint of ammonia production from natural gas

    Returns a dictionary as {blending ratio: carbon footprint}
    """
    cf_blending_ratios = {}
    for biomethane_ratio in np.arange(0, 1.1, 0.1):
        cf_blending_ratios[biomethane_ratio*100] = (1-biomethane_ratio) * cf_fossil + biomethane_ratio * cf_biomethane

    return cf_blending_ratios


def countries_iso_match(iso_codes):
    """
    The function returns the full name of countries based on their alpha-2 ISO code (e.g., ES or DE)
    """
    full_names = {}
    for c in iso_codes:
        full_names[c] = pycountry.countries.get(alpha_2=c).name
    
    return full_names


def interpolate(results):
    """
    This function computes the share of biomethane needed in the
    natural gas-biomethane blend to achieve net-zero ammonia production

    - results: e.g., {0:1, 10: 2, ..., 100: 10}
    """
    data_df = pd.DataFrame(results, index=['value']).T.reset_index()
    s = data_df.set_index('value').squeeze()
    s.loc[0] = np.nan
    s = s.sort_index().interpolate(method='index')
    return s.loc[0]


def impacts_geo_data(data):
    """
    This function creates a dataframe with spatial data and impacts per country.

    Parameters:
    - data: A pandas dataframe that contains impacts in columns (one or multiple) per country in rows.
            The index of the dataframe should be the alpha-2 ISO code of the country (e.g., ES or DE).

    Returns:
    - data_regional: A dataframe that contains geo information and impacts per country.
    """
    
    # Map ISO codes to countries names
    COUNTRIES_ISO = list(data.index)
    COUNTRIES_NAME = countries_iso_match(COUNTRIES_ISO)

    # Add countries names to data
    data_copy = copy.deepcopy(data)
    data_copy['name'] = pd.Series(COUNTRIES_NAME)
    data_copy = data_copy.reset_index()

    # Create map object for plotting
    world = gpd.read_file(gpd.datasets.get_path('naturalearth_lowres'))
    
    # Create dataframe with geo information and impacts per country
    data_regional = world[world.name.isin(list(COUNTRIES_NAME.values()))]
    data_regional = data_regional.merge(data_copy, on='name', how='left')

    return data_regional


def map_dbs_keys(dbs):
    """    
    Create mapping of BW codes for involved databases

    :dbs list: list of databases
    """
    if "biosphere 3" not in dbs:
        dbs.append("biosphere3")

    map_bw_keys =  {}

    for db in dbs:
        db_obj = bw.Database(db)
        for ds in db_obj:
            if db == "biosphere3":
                map_bw_keys[(ds['name'], ds["categories"])] = ds.key
            else:
                map_bw_keys[(ds['reference product'], ds['name'], ds['location'])] = ds.key
    return map_bw_keys


def read_ps_scenario_data(scenario_file, dbs):
    """
    This function reads the scenario data from an Excel file and prepares it into a dataframe for being used with presamples.
    Secondly, it adds the bw codes for the involved activities.
    The dictionary map_bw_keys provides these codes, it needs to be generated beforehand with the involved databases.    
    """

    # Create mapping of BW codes for involved databases
    map_bw_keys =  map_dbs_keys(dbs)

    # Import scenario df and remove empty rows
    scenariodata_df = pd.read_excel(scenario_file)
    scenariodata_df = scenariodata_df.dropna(how="all")
    scenario_label = list(scenariodata_df.columns)[10:]

    # add the bw code to scenario df (input = process, output = to_process)
    scenariodata_df["input"] = None
    scenariodata_df["output"] = None
    for index, row in scenariodata_df.iterrows():
        output_key = (row["to_reference product"], row["to_process"], row["to_location"])

        if row["from_type"] == "technosphere":
            input_key = (row["from_reference_product"], row["from_process"], row["from_location"])
        elif row["from_type"] == "biosphere":
            input_key = (row["from_process"], tuple(row["from_categories"].split('::')))

        scenariodata_df.at[index, "input"] = map_bw_keys.get(input_key, None)
        scenariodata_df.at[index, "output"] = map_bw_keys.get(output_key, None)

    return scenario_label, scenariodata_df


def make_ps_package(scenariodata_df, scenario_label, ps_packagename):
    """
    This function prepares a Presamples package out of the scenario data if.
    """
        
    technosphere_flows_df = scenariodata_df[scenariodata_df["from_type"] == "technosphere"]
    technosphere_sample = technosphere_flows_df[scenario_label].values
    technosphere_indices = [(row['input'], row['output'], row['from_type']) for i, row in technosphere_flows_df.iterrows()]
    data_technosphere = (
        technosphere_sample,
        technosphere_indices,
        'technosphere'
        )

    biosphere_flows_df = scenariodata_df[scenariodata_df["from_type"] == "biosphere"]
    biosphere_sample = biosphere_flows_df[scenario_label].values
    biosphere_indices = [(row['input'], row['output'], row['from_type']) for i, row in biosphere_flows_df.iterrows()]

    data_biosphere = (
        biosphere_sample,
        biosphere_indices,
        'biosphere'
        )

    ps_id, ps_filepath = ps.create_presamples_package(
        matrix_data=[
            data_technosphere,
            data_biosphere
            ],
            name=ps_packagename, seed="sequential"
            ) 
        
    print("\n ps_id, filepath:", ps_id, ps_filepath)
    return ps_filepath


def calculate_impacts_with_ps(ps_filepath, scenario_label, ds, lcia_methods):
       """
       This function computes LCA results using presamples
       
       :ps_filepath path: path to the presample file
       :scenario_label list: list of labels for scenarios
       :ds bw object: activity for assessment
       :lcia_methods dict: dictionary with LCIA methods
       """

       # Calculate impacts
       lca = bw.LCA({ds:1}, presamples=[ps_filepath])


       ps_results = {impact: {} for impact in lcia_methods}

       scenario_lca = dict()
       for i in range(len(scenario_label)): # Scenarios
              if i == 0: # Don't update the first time around, since indexer already at 0th column
                     lca.lci() # Builds matrices
                     multi_lcia_results = dict()
                     for impact in lcia_methods:
                            lca.switch_method(lcia_methods[impact])
                            lca.lcia()
                            multi_lcia_results[impact] = lca.score
              else:
                     lca.presamples.update_matrices() # Move to next column and update matrices
                     lca.redo_lci()
                     multi_lcia_results = dict()
                     for impact in lcia_methods:
                            lca.switch_method(lcia_methods[impact])
                            lca.lcia()
                            multi_lcia_results[impact] = lca.score
                     
              scenario_lca[scenario_label[i]] = multi_lcia_results

              for impact in lcia_methods:
                     ps_results[impact][scenario_label[i]] = scenario_lca[scenario_label[i]][impact]

       ps_results_df = pd.DataFrame(ps_results).T

       return ps_results_df


def perturbation_analysis_with_ps(assessed_ds, included_ds, dbs, lcia_method):
    """
    This function performs a perturbation analysis to
    identify the most sensitive LCI flows with respect
    to the impact in a certain category.

    Given a list of datasets, each LCI flow within each dataset
    is varied one-at-a-time +-20% around the default value and the impact is calculated

    :assessed_ds bw object: LCI dataset for which perturbation analysis is assessed
    :included_ds list: list of LCI datasets included in the perturbation analysis
    :dbs list: list of databases included
    :lcia_methods dict: dictionary with the name and assessed LCIA method
    """

    if len(lcia_method) > 1:
        raise ValueError("More than one impact category has been provided.")

    df_columns = (
        "to_reference product",
        "to_process",
        "to_location",
        "to_database",
        "from_reference_product",
        "from_process",
        "from_location",
        "from_categories",
        "from_type",
        "from_database",
        "default"
    )

    # Create mapping of BW codes for involved databases
    map_bw_keys =  map_dbs_keys(dbs)

    # Get only elementary flows relevant to the assessed impact category:
    lcia_method_obj = bw.Method(list(lcia_method.values())[0])
    cfs = lcia_method_obj.load()
    cfs_keys = [key[0] for key in cfs]

    to_from_ds = []
    for ds in included_ds:
        to_ds = ((ds["reference product"], ds["name"], ds["location"], ds["database"]))

        for exc in ds.exchanges():
            if exc["type"] == "technosphere":
                to_from_ds.append(to_ds + (exc["product"], exc["name"], exc["location"], np.nan, exc["type"], exc["database"], exc["amount"]))
            elif exc["type"] == "biosphere":
                if exc.input.key in cfs_keys:
                    to_from_ds.append(to_ds + (np.nan, exc["name"], np.nan, exc["categories"], exc["type"], exc["database"], exc["amount"]))

    scenario_df = pd.DataFrame(to_from_ds, columns=df_columns)

    # add the bw code to scenario df (input = process, output = to_process) and the parameter identifier
    scenario_df["input"] = None
    scenario_df["output"] = None

    count_sc = 0
    for index, row in scenario_df.iterrows():
        output_key = (row["to_reference product"], row["to_process"], row["to_location"])

        if row["from_type"] == "technosphere":
            input_key = (row["from_reference_product"], row["from_process"], row["from_location"])
        elif row["from_type"] == "biosphere":
            input_key = (row["from_process"], tuple(row["from_categories"]))

        scenario_df.at[index, "input"] = map_bw_keys.get(input_key, None)
        scenario_df.at[index, "output"] = map_bw_keys.get(output_key, None)

        scenario_id = "PAR_" + str(count_sc)
        scenario_df.at[index, "param id"] = scenario_id
        count_sc += 1

    scenario_df = scenario_df[[col for col in scenario_df.columns if col != "default"] + ["default"]]

    # Calculate LCI values for +20% variation
    param_scenarios = [param + "_plus_20" for param in scenario_df["param id"]]
    replicated_columns = pd.concat([scenario_df["default"]] * len(param_scenarios), axis=1)
    replicated_columns.columns = param_scenarios
    np.fill_diagonal(replicated_columns.values, replicated_columns.values.diagonal() * (1 + 0.2))
    scenario_df_plus_20 = pd.concat([scenario_df, replicated_columns], axis=1)

    # Calculate LCI values from -20% variation
    param_scenarios = [param + "_minus_20" for param in scenario_df["param id"]]
    replicated_columns = pd.concat([scenario_df["default"]] * len(param_scenarios), axis=1)
    replicated_columns.columns = param_scenarios
    np.fill_diagonal(replicated_columns.values, replicated_columns.values.diagonal() * (1 - 0.2))
    scenario_df_minus_20 = pd.concat([scenario_df, replicated_columns], axis=1)

    ps_packagename = "ps_v1"
    scenario_label = list(scenario_df_plus_20.columns)[13:]

    ps_filepath = make_ps_package(scenario_df_plus_20, scenario_label, ps_packagename)
    lca_plus_20 = calculate_impacts_with_ps(ps_filepath, scenario_label, assessed_ds, lcia_method)

    ps_packagename = "ps_v1"
    scenario_label = list(scenario_df_minus_20.columns)[13:]

    ps_filepath = make_ps_package(scenario_df_minus_20, scenario_label, ps_packagename)
    lca_minus_20 = calculate_impacts_with_ps(ps_filepath, scenario_label, assessed_ds, lcia_method)

    perturbation_analysis_results = {}
    for index, row in scenario_df_plus_20.iterrows():
        activity = row["to_process"]
        param = row["from_process"]
        param_id = row["param id"]

        plus_scenario = [i for i in lca_plus_20.columns if i == param_id + "_plus_20"][0]
        minus_scenario = [i for i in lca_minus_20.columns if i == param_id + "_minus_20"][0]

        param_default = row["default"]
        param_plus_20 = scenario_df_plus_20[scenario_df_plus_20["param id"] == param_id][plus_scenario].values[0]
        param_minus_20 = scenario_df_minus_20[scenario_df_minus_20["param id"] == param_id][minus_scenario].values[0]

        result_default = lca_plus_20["default"].values[0]
        result_plus_20 = lca_plus_20[plus_scenario].values[0]
        result_minus_20 = lca_minus_20[minus_scenario].values[0]

        sensitivity_ratio = ((result_plus_20 - result_minus_20) / result_default) / ((param_plus_20 - param_minus_20) / param_default)

        perturbation_analysis_results.update(
            {
                (activity, param): {"param default": param_default,
                                    "param plus 20": param_plus_20,
                                    "param minus 20": param_minus_20,
                                    "lca default": result_default,
                                    "lca plus 20": result_plus_20,
                                    "lca minus 20": result_minus_20,
                                    "sensitivity ratio": sensitivity_ratio}
            }
        )

    perturbation_analysis_results = pd.DataFrame(perturbation_analysis_results).T

    perturbation_analysis_results = perturbation_analysis_results.reset_index().rename(columns={"level_0": "activity", "level_1": "parameter"}).sort_values(by="sensitivity ratio", ascending=False)

    return perturbation_analysis_results
