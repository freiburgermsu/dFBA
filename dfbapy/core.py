# -*- coding: utf-8 -*-

# import statements
from math import inf
from numpy import nan   
import pandas
import cobra
import json
import re

empty = ['', '-', '', None, nan]

# import enzyme kinetics and rate equations
with open('../scraping/SABIO/scraped_content/sabio_proccessed.json', 'rb') as f:
    reaction_kinetics = json.load(f)
    
# add the units of logarithm to the Magnesium concentration
def isnumber(string):
    string = str(string)
    try:
        string = string.strip()
        if re.sub('([0-9]|\.)', '',string) == '':
            return True
    except:
        return False
    
def average(num_1, num_2 = None):
    if isnumber(num_1): 
        if num_2 is not None:
            numbers = [num_1, num_2]
            average = sum(numbers) / len(numbers)
            return average
        else:
            return num_1
    elif type(num_1) is list:
        average = sum(num_1) / len(num_1)
        return average
    else:
        return None
            
# define chemical concentrations
class dynamicFBA():
    def __init__(self, model, total_time, timestep, initial_concentrations, reaction_kinetics, logging = True, verbose = True):
        self.model = model
        self.verbose = verbose
        self.parameters = {}
        self.variables = {}
        
        self.parameters['timesteps'] = round(total_time/timestep)
        self.parameters['reaction_kinetics'] = reaction_kinetics
        self.parameters['initial_concentrations'] = initial_concentrations
        self.variables['time_series'] = {}
        self.variables['concentrations'] = {}
        for metabolite in self.model.metabolites:
            self.variables['time_series'][metabolite.name] = []
            
        # define the dataframe for the time series content
        if logging:
            indices = [enzyme for enzyme in reaction_kinetics]
            columns = [f'{(time+1)*timestep} (min)' for time in range(self.parameters['timesteps'])]
            self.df = pandas.DataFrame(index = indices, columns = columns)
            self.df.index.name = 'enzymes'

    def simulate(self, temperature = 25, p_h = 7, visualize = True):
        self.variables['elapsed_time'] = 0
        #Simulate for each timestep within total time frame
        first = True
        solutions = []
        for self.timestep in range(1,self.parameters['timesteps']+1):
            print('timestep', self.timestep)
            
            if first:
                self.calculate_kinetics(self.parameters['initial_concentrations'],temperature = 25, p_h = 7)
            else:
                self.calculate_kinetics(self.variables['concentrations'],temperature = 25, p_h = 7)
            
            #Calcuate and parameterize fluxes from michaelis-menten kinetics
            for reaction in self.model.reactions:
                if any(rxn.lower() == reaction.name for rxn in self.parameters['calculated_rate_laws']):
                    kinetic_flux = self.parameters['calculated_rate_laws'][reaction.name]
#                     print(kinetic_flux)
                    self.set_constraints(reaction, reaction.name,kinetic_flux, first)
                else:
                    if self.verbose:
                        print(f'--> ERROR: The {reaction.name} reaction is not defined in the kinetics data.')                    

            # execute the model and update concentrations
            self.solution = self.model.optimize()
            solutions.append(self.solution)
            print(f'\nobjective value for timestep {self.timestep}: ', self.solution.objective_value, '\n\n')
            self.update_concentrations(self.solution, first)
            
            self.variables['elapsed_time'] += self.timestep
        
            if self.timestep == 1:
                first = False
        
        if visualize:
            self.visualize()
        
        return self.df, solutions
    
    def calculate_kinetics(self,concentrations, source = 'sabio', temperature = 25, p_h = 7):
        self.parameters['calculated_rate_laws'] = {}

        for enzyme in self.parameters['reaction_kinetics']:
            if source = 'sabio':
                minimum = inf
                entry = False

                for reaction in self.parameters['reaction_kinetics'][enzyme]:           
                    for entry_id in self.parameters['reaction_kinetics'][enzyme][reaction]:
                        if "SubstitutedRateLaw" in self.parameters['reaction_kinetics'][enzyme][reaction][entry_id]:
                            remainder = re.sub('([0-9]|[ABC]|\/|\(|\)|\+|\.|\*|)', '', self.parameters['reaction_kinetics'][enzyme][reaction][entry_id]["SubstitutedRateLaw"])
                            if remainder == '':
                                A = 0
                                B = 0
                                C = 0

                                if "A" in self.parameters['reaction_kinetics'][enzyme][reaction][entry_id]["Parameters"]:   
                                    if self.parameters['reaction_kinetics'][enzyme][reaction][entry_id]["Parameters"]["A"]["species"] in concentrations: 
                                        A = concentrations[reaction_kinetics[enzyme][reaction][entry_id]["Parameters"]["A"]["species"]]

                                if "B" in self.parameters['reaction_kinetics'][enzyme][reaction][entry_id]["Parameters"]:   
                                    if self.parameters['reaction_kinetics'][enzyme][reaction][entry_id]["Parameters"]["B"]["species"] in concentrations:    
                                        B = concentrations[reaction_kinetics[enzyme][reaction][entry_id]["Parameters"]["B"]["species"]]

                                if "C" in self.parameters['reaction_kinetics'][enzyme][reaction][entry_id]["Parameters"]:   
                                    if self.parameters['reaction_kinetics'][enzyme][reaction][entry_id]["Parameters"]["C"]["species"] in concentrations:    
                                        C = concentrations[reaction_kinetics[enzyme][reaction][entry_id]["Parameters"]["C"]["species"]]

                                try:
                                    flux = eval(reaction_kinetics[enzyme][reaction][entry_id]["SubstitutedRateLaw"])
                                except:
                                    pass

                                # define the closest match of the data to the parameterized conditions
                                if (temperature and self.parameters['reaction_kinetics'][enzyme][reaction][entry_id]["Temperature"]) not in empty:
                                    temperature_deviation = abs(temperature - float(self.parameters['reaction_kinetics'][enzyme][reaction][entry_id]["Temperature"]))/temperature
                                else:
                                    temperature_deviation = 0
                                if (p_h and self.parameters['reaction_kinetics'][enzyme][reaction][entry_id]["pH"]) not in empty:
                                    ph_deviation = abs(p_h - float(self.parameters['reaction_kinetics'][enzyme][reaction][entry_id]["pH"]))/p_h
                                else:
                                    ph_deviation = 0

                                old_minimum = minimum
                                deviation = average(temperature_deviation, ph_deviation)
                                minimum = min(deviation, minimum)
    #                             print('minimum', minimum)
    #                             print('deviation', deviation)

                                if old_minimum == minimum:
                                    fluxes.append(flux)
                                elif deviation == minimum:
                                    fluxes = [flux]
                                entry = True

            if entry:
                if self.verbose:
                    print(enzyme, self.timestep, fluxes)
                self.df.at[enzyme, f'{self.timestep} (min)'] = average(fluxes)

    def set_constraints(self,reaction,reaction_name,constant,first):
        reaction_name = re.sub('\s', '_', reaction_name)
        if first:
            expression = reaction.flux_expression
            constraint = self.model.problem.Constraint(
                    expression,lb=constant,ub=constant,name=f'{reaction_name}_kinetics'
                )
            self.model.add_cons_vars(constraint)
            self.model.solver.update()
        else:
            if not isnumber(constant):
                print(f'--> ERROR: The constant for {reaction_name} is erronenous.')
            else:
                reaction.upper_bound = reaction.lower_bound = constant
                
    def update_concentrations(self, solution,first):
        for metabolite in self.model.metabolites:
            for reaction in self.model.reactions:
                if metabolite in reaction.metabolites:
                    delta_conc = reaction.metabolites[metabolite] * solution.fluxes[reaction.id]
                    if first:
                        self.variables['concentrations'][metabolite.name] = delta_conc
                    else:
                        before = self.variables['concentrations'][metabolite.name]
                        self.variables['concentrations'][metabolite.name] += delta_conc
                        after = self.variables['concentrations'][metabolite.name]
                        if self.verbose:
                            print(before == after)

    def visualize(self):
        print('='*50)
        print(self.df.to_string())