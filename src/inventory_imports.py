"""
Functions to create and manipulate a LCI database starting with raw inventories imported
from an Excel file
"""

import numpy as np
import pandas as pd
import wurst
from constructive_geometries import *
import copy


def correct_product_in_exchanges(db):
    '''
    The function ExcelImporter requires that a 'reference product' is defined for every technosphere exchange.
    However, the ecoinvent database imported in BW2 uses 'product' for technosphere exchanges.
    
    This function modifies the datasets in place to replace 'reference product' by 'product' for
    all technosphere exchanges
    
    Arguments:
        - db: list of dictionaries; each dictionary is a dataset/activity
    '''    
    for ds in db:
        for exc in ds["exchanges"]:
            if 'reference product' in exc:
                exc['product'] = exc.pop('reference product')


def link_exchanges_by_code(db, external_db, biosphere_db):
    '''
    This function links in place technosphere exchanges within the database and/or to an external database
    and biosphere exchanges with the biosphere database (only unlinked exchanges)
    
    Returns a dictionary with the linked database
    '''   
    technosphere = lambda x: x["type"] == "technosphere"
    biosphere = lambda x: x["type"] == "biosphere"
    
    for ds in db:
        
        for exc in filter(technosphere, ds["exchanges"]):
            if 'input' not in exc:
                try:
                    exc_lci = wurst.get_one(db + external_db,
                                            wurst.equals("name", exc['name']),
                                            wurst.equals("reference product", exc['product']),
                                            wurst.equals("location", exc['location'])
                                        )
                    exc.update({'input': (exc_lci['database'],
                                        exc_lci['code'])})
                except Exception:
                    print(exc['name'], exc['product'], exc['location'])
                    raise
            
        for exc in filter(biosphere, ds["exchanges"]):
            if 'input' not in exc:
                try:
                    ef_code = [ef['code'] for ef in biosphere_db if ef['name'] == exc['name'] and 
                                                                    ef['unit'] == exc['unit'] and 
                                                                    ef['categories'] == exc['categories']][0]
                    exc.update({'input': ('biosphere3',
                                          ef_code)})   
                except Exception:
                    print(exc['name'], exc['unit'], exc['categories'])
                    raise


def create_dataset_from_df(inventories_df):
    """
    This function converts datasets contained in a dataframe into a list of dictionaries as required by BW2.
    Technosphere and biosphere exchanges are unlinked (by code).

    Arguments:
        - inventories_df: Dataframe with the inventories; rows are exchanges (production/technosphere/biosphere) and
                        columns are name, reference product, database, categories, location, type, and unit followed by
                        each dataset.
    """
    COL_START = 7 # inventory data start at column 7 in the dataframe
    NUMBER_ACTV = len(inventories_df.columns) - COL_START - 1 # number of datasets (rest 1 to substract the 'comment' column)
    
    inventories = []
    for i in range(NUMBER_ACTV):
        col_no = i + COL_START
        id_actv = inventories_df.columns[col_no]
        inv_actv = inventories_df.iloc[:, np.r_[0:COL_START, col_no]].copy()

        exchanges = []
        for exc in list(inv_actv.index):
            if inv_actv.iloc[exc][id_actv] == 0:
                pass
            else:
                if inv_actv.iloc[exc]['type'] == 'production':
                    name_actv = f"{inv_actv.iloc[exc]['name']}, {id_actv}"
                    actv_dict = {'name': name_actv,
                                 'location': inv_actv.iloc[exc]['location'],
                                 'reference product': inv_actv.iloc[exc]['reference product'],
                                 'production amount': inv_actv.iloc[exc][id_actv],
                                 'unit': inv_actv.iloc[exc]['unit'],
                                 'database': inv_actv.iloc[exc]['database'],
                                 'code': wurst.filesystem.get_uuid()
                                 }
                    exchanges.append({'name': name_actv,
                                      'reference product': inv_actv.iloc[exc]['reference product'],
                                      'amount': inv_actv.iloc[exc][id_actv],
                                      'unit': inv_actv.iloc[exc]['unit'],
                                      'database': inv_actv.iloc[exc]['database'],
                                      'location': inv_actv.iloc[exc]['location'],
                                      'type': inv_actv.iloc[exc]['type']
                                      })                    
                    
                elif inv_actv.iloc[exc]['type'] == 'technosphere':
                    exchanges.append({'name': inv_actv.iloc[exc]['name'],
                                      'reference product': inv_actv.iloc[exc]['reference product'],
                                      'amount': inv_actv.iloc[exc][id_actv],
                                      'unit': inv_actv.iloc[exc]['unit'],
                                      'database': inv_actv.iloc[exc]['database'],
                                      'location': inv_actv.iloc[exc]['location'],
                                      'type': inv_actv.iloc[exc]['type']
                                      })
                    
                elif inv_actv.iloc[exc]['type'] == 'biosphere':
                    # Format of categories string needs to be changed:
                    categories = inv_actv.iloc[exc]['categories']
                    categories = tuple(categories.split('::'))
                    exchanges.append({'name': inv_actv.iloc[exc]['name'],
                                      'amount': inv_actv.iloc[exc][id_actv],
                                      'unit': inv_actv.iloc[exc]['unit'],
                                      'categories': categories,
                                      'database': inv_actv.iloc[exc]['database'],
                                      'type': inv_actv.iloc[exc]['type']
                                      })                    

        actv_dict.update({'exchanges': exchanges})
        inventories.append(actv_dict)

    return inventories


def regionalize_inventories(activities, COUNTRIES, dbs, DB_REG):
    """
    This function creates regionalized inventories for multiple activities
    by replicating a list of existing activities for a set of countries/regions and relinking
    technosphere exchanges to suppliers within the new location.

    Arguments:
        - activities (List of tuples): List of tuples, where each tuple contains 3 elements that defines the activity
                                       which is regionalized; (`name`, `reference product`, `location`) 
        - COUNTRIES (List): List of countries/regions that the activity be replicated to.
        - dbs (List): List of databases that contains the data to be used in the function.
        - DB_REG (str): The name of the database where the regionalized data will be stored.
    
    Return:
        - This function returns a list of datasets with regionalized inventory data.
    """

    # Replicate activities to the new locations
    lci_raw = []
    for ds in activities:
        try:
            ds_lci = wurst.get_one(dbs, wurst.equals("name", ds[0]), 
                                        wurst.equals('reference product', ds[1]),
                                        wurst.equals('location', ds[2])
                                )
        except:
            print(ds)
            raise
        
        for loc in COUNTRIES:
            ds_lci_loc = replicate_activity_to_loc(ds_lci, loc, DB_REG)
            lci_raw.append(ds_lci_loc)

    # Change exchange inputs for the new location
    lci_regional = []
    for ds in lci_raw:
        ds_linked = relink_exchange_location(ds, dbs + lci_raw)
        lci_regional.append(ds_linked)

    return lci_regional


def replicate_activity_to_loc(ds, LOC, DB_REG):
    """
    Replicate an activity to new locations and translate it to a regionalized database.
    
    Arguments:
        ds: The existing dataset.
        loc (str): The new location to replicate the activity to.
        DB_REG (str): The name of the regionalized database.
        
    Returns:
        The activity replicated to the new location.
    """
    production = lambda x: x["type"] == "production"

    # Replicate activity to the new locations
    ds_lci_loc = wurst.transformations.geo.copy_to_new_location(ds, LOC)

    # Translate the copy to the regionalized database
    ds_lci_loc['database'] = DB_REG

    # Change input code for production type
    for exc in filter(production, ds_lci_loc["exchanges"]):
        exc.update({'input': (ds_lci_loc['database'], ds_lci_loc['code'])})   

    return ds_lci_loc


def relink_exchange_location(ds, db):
    """
    Find new technosphere suppliers based on the location of the dataset.
    The new supplier is linked by code.

    Based on 'wurst.transformations.geo.relink_technosphere_exchanges'

    Arguments:
        ds: The dataset.
        dbs (List): List of datasets that contains the data to be used in the function.
        
    Returns:
        The activity replicated to the new location.  
    """

    LOCATION = ds['location']
    technosphere = lambda x: x["type"] == "technosphere"
    geomatcher = Geomatcher() # Initialize the geomatcher object     

    for exc in filter(technosphere, ds["exchanges"]):
        exc_filter = {'name': exc['name'],
                      'product': exc['product'],
                      'unit': exc['unit']}

        # Get the list of possible datasets for the exchange

        if 'market group' in exc['name']:
            # Get both "market group" and "market" activities:
            possible_datasets_group = list(wurst.transformations.geo.get_possibles(exc_filter, db)) 

            exc_filter_market = copy.deepcopy(exc_filter)
            exc_filter_market.update({'name': exc['name'].replace('market group', 'market')})
            possible_datasets_market = list(wurst.transformations.geo.get_possibles(exc_filter_market, db))

            possible_datasets = possible_datasets_group + possible_datasets_market
            
        else:
            possible_datasets = list(wurst.transformations.geo.get_possibles(exc_filter, db))
        
        # Check if there is an exact match for the location
        match_dataset = [ds for ds in possible_datasets if ds['location'] == LOCATION]
        if len(match_dataset) == 0:
            # If there is no specific dataset for the location, search for the supraregional locations
            loc_intersection = geomatcher.intersects(LOCATION, biggest_first=False)
            
            for loc in [i[1] if type(i)==tuple else i for i in loc_intersection]:
                match_dataset = [ds for ds in possible_datasets if ds['location'] == loc]
                if len(match_dataset) > 0:
                    break
                else:
                    match_dataset = [ds for ds in possible_datasets if ds['location'] == 'RoW']

        exc.update({
                    'name': match_dataset[0]['name'],
                    'product': match_dataset[0]['reference product'],
                    'unit': match_dataset[0]['unit'],
                    'location': match_dataset[0]['location'],
                    'input': (match_dataset[0]['database'], match_dataset[0]['code'])
                    })

    return ds


def modify_exchange_amount_from_df(db, lci_param_prosp):
    '''
    This function modifies in place exchanges amounts based on data provided in a dataframe
    
    '''
    # Change the format of 'categories':
    lci_param_prosp['from_categories'] = [tuple(i.split('::')) if i != 0 else 0 for i in lci_param_prosp['from_categories']]
    
    # Modify exchanges amount:
    for ds in db:
        for exc in ds['exchanges']:
            if exc['type'] == 'production':
                pass
            else:
                if exc['type'] == 'technosphere':
                    new_amount = lci_param_prosp[(lci_param_prosp['to_process'] == ds['name']) & 
                                                (lci_param_prosp['to_reference_product'] == ds['reference product']) & 
                                                (lci_param_prosp['to_location'] == ds['location']) &
                                                (lci_param_prosp['from_process'] == exc['name']) & 
                                                (lci_param_prosp['from_reference_product'] == exc['product']) & 
                                                (lci_param_prosp['from_location'] == exc['location'])]['2030_avg'].values
                    
                elif exc['type'] == 'biosphere':
                    new_amount = lci_param_prosp[(lci_param_prosp['to_process'] == ds['name']) & 
                                                (lci_param_prosp['to_reference_product'] == ds['reference product']) & 
                                                (lci_param_prosp['to_location'] == ds['location']) &
                                                (lci_param_prosp['from_process'] == exc['name']) & 
                                                (lci_param_prosp['from_categories'] == exc['categories'])]['2030_avg'].values

                if len(new_amount) > 0:
                    exc.update({'amount': new_amount[0]})