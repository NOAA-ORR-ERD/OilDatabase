import logging

import numpy as np

from ..models.imported_rec import ImportedRecord
from ..models.ec_imported_rec import ECImportedRecord
from ..models.oil import Oil
from ..models.common_props import (Cut, SARAFraction, SARADensity,
                                   MolecularWeight)

from ..util.estimations import api_from_density

from ..data_sources.oil_library import ImportedRecordWithEstimation
from ..data_sources.oil_library import ImportedRecordWithScore


from pprint import PrettyPrinter
pp = PrettyPrinter(indent=2, width=120)

logger = logging.getLogger(__name__)


class OilRejected(Exception):
    '''
        Custom exception for Oil initialization that we can raise if we
        decide we need to reject an oil record for any reason.
    '''
    def __init__(self, message, oil_name, *args):
        # without this you may get DeprecationWarning
        self.message = message

        # Special attribute you desire with your Error,
        # perhaps the value that caused the error?:
        self.oil_name = oil_name

        # allow users initialize misc. arguments as any other builtin Error
        super(OilRejected, self).__init__(message, oil_name, *args)

    def __repr__(self):
        return '{0}(oil={1}, errors={2})'.format(self.__class__.__name__,
                                                 self.oil_name,
                                                 self.message)


class ImportedRecordInitialize(ImportedRecordWithEstimation,
                               ImportedRecordWithScore):
    pass


def pprint_for_one_oil(oil, *args):
    '''
        Just a simple diagnostic printing routine.
        The idea is to print messages for just one oil record
        to reduce verboseness when diagnosing these routines.
    '''
    adios_oil_id = 'AD02434'

    if hasattr(oil, 'adios_oil_id') and oil.adios_oil_id == adios_oil_id:
        pp.pprint(args)


def process_oils():
    '''
        The idea is that an imported record contains data items from a source
        that are presumed to be the measured properties of the petroleum
        product.  We want it to be easy to analyze the original source
        information, so we want to keep this around unmodified.

        We also want to have an oil table that contains all records.
    '''
    logger.info('Adding Oil objects...')
    for rec in ImportedRecord.objects.all():
        try:
            add_oil(rec)
        except OilRejected as e:
            logger.warning(repr(e))

    logger.info('Adding Environment Canada Oil objects...')
    for rec in ECImportedRecord.objects.all():
        try:
            add_oil(rec)
        except OilRejected as e:
            logger.warning(repr(e))


def add_oil(record):
    '''
        Originally, we wanted to populate the oil table with generalized oil
        objects that had rich sets of properties, including estimations of
        any necessary properties that were missing.

        Our strategy has changed a bit, however.  Now we would like to simply
        populate the table with the records directly, for better or worse.

        Later, when we want to use a richly constructed record, we will do so
        on-demand.
    '''
    reject_imported_record_if_requirements_not_met(record)

    oil_collection = Oil._mongometa.collection

    oil_collection.insert_one(record.to_son().to_dict())


def add_oil_old(record):
    '''
        Note: We are no longer doing this during the database initialization,
              but we will keep this function around to document the process.
              We may want to do something similar when a rich oil record
              is requested.
    '''
    reject_imported_record_if_requirements_not_met(record)

    oil = generate_oil(record)

    reject_oil_if_bad(oil)
    oil.imported = record
    oil.save()


def generate_oil(imported_rec):
    '''
        This is the method for creating a rich Oil record from a NOAA filemaker
        imported record.
    '''
    logger.info('Begin estimations for {0}'
                .format(imported_rec.adios_oil_id))
    oil = Oil()
    imp_rec_obj = ImportedRecordInitialize(imported_rec)

    add_demographics(imp_rec_obj, oil)

    # Core estimations
    add_densities(imp_rec_obj, oil)
    add_viscosities(imp_rec_obj, oil)

    # Distillation estimations
    add_inert_fractions(imp_rec_obj, oil)
    add_volatile_fractions(imp_rec_obj, oil)
    add_distillation_cuts(imp_rec_obj, oil)

    # Component Fractional estimations
    add_component_mol_wt(imp_rec_obj, oil)
    add_component_mass_fractions(imp_rec_obj, oil)
    add_component_densities(imp_rec_obj, oil)

    # Miscellaneous estimations
    add_oil_water_interfacial_tension(imp_rec_obj, oil)
    add_oil_seawater_interfacial_tension(imp_rec_obj, oil)
    add_pour_point(imp_rec_obj, oil)
    add_flash_point(imp_rec_obj, oil)
    add_max_water_fraction_of_emulsion(imp_rec_obj, oil)
    add_bullwinkle_fractions(imp_rec_obj, oil)
    add_solubility(imp_rec_obj, oil)
    add_adhesion(imp_rec_obj, oil)
    add_sulphur_mass_fraction(imp_rec_obj, oil)

    # estimations not in the document, but needed
    add_metals(imp_rec_obj, oil)
    add_aggregate_volatile_fractions(oil)
    add_misc_fractions(imp_rec_obj, oil)
    add_product_type(imp_rec_obj, oil)
    add_k0y(imp_rec_obj, oil)

    oil.quality_index = imp_rec_obj.score()

    return oil


def add_demographics(imp_rec_obj, oil):
    oil.name = imp_rec_obj.record.oil_name
    oil.adios_oil_id = imp_rec_obj.record.adios_oil_id


def add_densities(imp_rec_obj, oil):
    try:
        oil.densities = imp_rec_obj.get_densities()
        oil.api = imp_rec_obj.get_api()
    except Exception as e:
        logger.warning('Exception: record {}\n'
                       '{}\n'
                       'check for valid api and densities.'
                       .format(imp_rec_obj.record.adios_oil_id, e))


def add_viscosities(imp_rec_obj, oil):
    kvis, estimated = imp_rec_obj.aggregate_kvis()

    for k in kvis:
        oil.kvis.append(k)

    if any(estimated):
        oil.estimated['viscosities'] = estimated


def add_inert_fractions(imp_rec_obj, oil):
    '''
        Add the resin and asphaltene fractions to our oil
        This does not include the component resins & asphaltenes
    '''
    f_res, f_asph, est_res, est_asph = imp_rec_obj.inert_fractions()

    oil.resins_fraction, oil.asphaltenes_fraction = f_res, f_asph

    if est_res:
        oil.estimated['resins_fraction'] = est_res

    if est_asph:
        oil.estimated['asphaltenes_fraction'] = est_asph


def add_volatile_fractions(imp_rec_obj, oil):
    '''
        Add the saturates and aromatics fractions to our oil
        This does not include the component saturates & aromatics
    '''
    f_sat, f_arom, est_sat, est_arom = imp_rec_obj.volatile_fractions()

    oil.saturates_fraction, oil.aromatics_fraction = f_sat, f_arom

    if est_sat:
        oil.estimated['saturates_fraction'] = est_sat

    if est_arom:
        oil.estimated['aromatics_fraction'] = est_arom


def add_distillation_cuts(imp_rec_obj, oil):
    for T_i, f_evap_i in zip(*imp_rec_obj.normalized_cut_values()):
        oil.cuts.append(Cut(vapor_temp_k=T_i, fraction=f_evap_i))


def add_component_mol_wt(imp_rec_obj, oil):
    temps = imp_rec_obj.component_temps()
    mol_wts = imp_rec_obj.component_mol_wt()
    c_types = imp_rec_obj.component_types()

    for T_i, mol_wt_i, c_type in zip(temps, mol_wts, c_types):
        oil.molecular_weights.append(MolecularWeight(sara_type=c_type,
                                                     g_mol=mol_wt_i,
                                                     ref_temp_k=T_i))


def add_component_mass_fractions(imp_rec_obj, oil):
    temps = imp_rec_obj.component_temps()
    fracs = imp_rec_obj.component_mass_fractions()
    c_types = imp_rec_obj.component_types()

    for T_i, f_i, c_type in zip(temps, fracs, c_types):
        oil.sara_fractions.append(SARAFraction(sara_type=c_type,
                                               fraction=f_i,
                                               ref_temp_k=T_i))


def add_component_densities(imp_rec_obj, oil):
    densities = imp_rec_obj.component_densities()
    fracs = imp_rec_obj.component_mass_fractions()
    temps = imp_rec_obj.component_temps()
    c_types = imp_rec_obj.component_types()

    # we need to scale our densities to match our aggregate density
    rho0_oil = imp_rec_obj.density_at_temp(273.15 + 15)
    Cf_dens = (rho0_oil / np.sum(fracs * densities))

    densities *= Cf_dens

    for T_i, rho, c_type in zip(temps, densities, c_types):
        oil.sara_densities.append(SARADensity(sara_type=c_type,
                                              kg_m_3=rho,
                                              ref_temp_k=T_i))


def add_oil_water_interfacial_tension(imp_rec_obj, oil):
    (ow_st, ref_temp_k, estimated) = imp_rec_obj.oil_water_surface_tension()

    oil.oil_water_interfacial_tension_n_m = ow_st
    oil.oil_water_interfacial_tension_ref_temp_k = ref_temp_k

    if estimated:
        oil.estimated['oil_water_interfacial_tension_n_m'] = estimated
        oil.estimated['oil_water_interfacial_tension_ref_temp_k'] = estimated


def add_oil_seawater_interfacial_tension(imp_rec_obj, oil):
    (osw_st, ref_temp_k, estimated) = imp_rec_obj.oil_seawater_surface_tension()

    oil.oil_seawater_interfacial_tension_n_m = osw_st
    oil.oil_seawater_interfacial_tension_ref_temp_k = ref_temp_k

    if estimated:
        oil.estimated['oil_seawater_interfacial_tension_n_m'] = estimated
        oil.estimated['oil_seawater_interfacial_tension_ref_temp_k'] = estimated


def add_pour_point(imp_rec_obj, oil):
    min_k, max_k, estimated = imp_rec_obj.pour_point()

    oil.pour_point_min_k = min_k
    oil.pour_point_max_k = max_k

    if estimated:
        oil.estimated['pour_point_min_k'] = estimated
        oil.estimated['pour_point_max_k'] = estimated


def add_flash_point(imp_rec_obj, oil):
    min_k, max_k, estimated = imp_rec_obj.flash_point()

    oil.flash_point_min_k = min_k
    oil.flash_point_max_k = max_k

    if estimated:
        oil.estimated['flash_point_min_k'] = estimated
        oil.estimated['flash_point_max_k'] = estimated


def add_max_water_fraction_of_emulsion(imp_rec_obj, oil):
    f_w_max = imp_rec_obj.max_water_fraction_emulsion()

    oil.emulsion_water_fraction_max = f_w_max
    oil.estimated['emulsion_water_fraction_max'] = True


def add_bullwinkle_fractions(imp_rec_obj, oil):
    bull_frac, estimated = imp_rec_obj.bullwinkle_fraction()

    oil.bullwinkle_fraction = bull_frac

    if estimated:
        oil.estimated['bullwinkle_fraction'] = estimated


def add_solubility(imp_rec_obj, oil):
    oil.solubility = imp_rec_obj.solubility()


def add_adhesion(imp_rec_obj, oil):
    omega_a, estimated = imp_rec_obj.adhesion()

    oil.adhesion_kg_m_2 = omega_a

    if estimated:
        oil.estimated['adhesion_kg_m_2'] = estimated


def add_sulphur_mass_fraction(imp_rec_obj, oil):
    oil.sulphur_fraction = imp_rec_obj.sulphur_fraction()


def add_metals(imp_rec_obj, oil):
    oil.nickel_ppm = imp_rec_obj.record.nickel
    oil.vanadium_ppm = imp_rec_obj.record.vanadium


def add_aggregate_volatile_fractions(oil):
    '''
        for this we need an oil record that already has
        the component mass fractions estimated.
        don't estimate if the record has the totals
        or if we already have a 'good' estimate
    '''
    if np.isnan(oil.saturates_fraction):
        oil.saturates_fraction = np.sum([f.fraction
                                         for f in oil.sara_fractions
                                         if f.sara_type == 'Saturates'])
        oil.aromatics_fraction = np.sum([f.fraction
                                         for f in oil.sara_fractions
                                         if f.sara_type == 'Aromatics'])


def add_misc_fractions(imp_rec_obj, oil):
    oil.polars_fraction = imp_rec_obj.record.polars
    oil.benzene_fraction = imp_rec_obj.record.benzene
    oil.paraffins_fraction = imp_rec_obj.record.paraffins
    oil.wax_content_fraction = imp_rec_obj.record.wax_content


def add_product_type(imp_rec_obj, oil):
    oil.product_type = imp_rec_obj.record.product_type


def add_k0y(imp_rec_obj, oil):
    if imp_rec_obj.record.k0y is not None:
        oil.k0y = imp_rec_obj.record.k0y
    else:
        oil.k0y = 2.02e-06


#
#
# ### Oil Quality checks
#
#

def reject_imported_record_if_requirements_not_met(imported_rec):
    '''
        Here, we have an imported oil record for which we would like to
        make estimations.  For this to happen, certain requirements need
        to be met.  Otherwise, we reject the oil without performing
        estimations.
    '''
    errors = []

    if manually_rejected(imported_rec):
        errors.append('Imported Record was manually rejected')

    if not has_product_type(imported_rec):
        errors.append('Imported Record has no product type')

    if not has_api_or_densities(imported_rec):
        errors.append('Imported Record has no density information')

    if not has_viscosities(imported_rec):
        errors.append('Imported Record has no viscosity information')

    if not has_distillation_cuts(imported_rec):
        errors.append('Imported Record has insufficient cut data')

    if len(errors) > 0:
        try:
            oil_id = imported_rec.adios_oil_id
        except AttributeError:
            oil_id = imported_rec.oil_id

        raise OilRejected(errors, oil_id)


def manually_rejected(imported_rec):
    '''
        This list was initially compiled to try and fix some anomalies
        that were showing up in the oil query form.

        When we update the source file that provides our imported record
        data, we should revisit this list.
        We should also revisit this list as we add methods to detect flaws
        in our oil record.
    '''
    try:
        oil_id = imported_rec.adios_oil_id
    except AttributeError:
        oil_id = imported_rec.oil_id

    if oil_id in (None,):
        return True

    return False


def has_product_type(imported_rec):
    '''
        In order to perform estimations, we need to determine if we are
        dealing with a crude or refined oil product.  We cannot continue
        if this information is missing.
    '''
    if (imported_rec.product_type is not None and
            imported_rec.product_type.lower() in ('crude', 'refined')):
        return True

    return False


def has_api_or_densities(imported_rec):
    '''
        In order to perform estimations, we need to have at least one
        density measurement.  We cannot continue if this information
        is missing.
        This is just a primitive test, so we do not evaluate the quantities,
        simply that some kind of value exists.
    '''
    if has_api(imported_rec):
        return True
    elif len(imported_rec.densities) > 0:
        return True
    else:
        return False


def has_api(imported_rec):
    '''
        Env Canada record has multiple weathered APIs, so we need to account
        for that.
    '''
    if (imported_rec.api is not None and imported_rec.api != []):
        return True
    else:
        return False


def has_viscosities(imported_rec):
    '''
        In order to perform estimations, we need to have at least one
        viscosity measurement.  We cannot continue if this information
        is missing.
        This is just a primitive test, so we do not evaluate the quantities,
        simply that some kind of value exists.
    '''
    if hasattr(imported_rec, 'kvis') and len(imported_rec.kvis) > 0:
        return True
    elif hasattr(imported_rec, 'dvis') and len(imported_rec.dvis) > 0:
        return True
    else:
        return False


def has_distillation_cuts(imported_rec):
    '''
        - In order to perform estimations on a refined product, we need to have
          at least three distillation cut measurements.  We cannot continue
          if this information is missing.
        - For crude oil products, we can estimate cut information from its
          API value if the cuts don't exist.
        - If we have no cuts and no API, we can still estimate cuts by
          converting density to API, and then API to cuts.
        - This is just a primitive test, so we do not evaluate the quantities,
          simply that some kind of value exists.
    '''
    if (imported_rec.product_type is not None and
            imported_rec.product_type.lower() == 'crude'):
        if (len(imported_rec.cuts) >= 3 or
                has_api_or_densities(imported_rec)):
            return True  # cuts can be estimated if not present
        else:
            return False
    else:
        if len(imported_rec.cuts) >= 3:
            return True
        else:
            return False


def has_densities_below_pour_point(imported_rec):
    '''
        This may be presumptuous, but I believe the volumetric coefficient
        that we use for calculating densities at temperature are probably for
        oils in the liquid phase.  So we would like to check if any
        densities in our oil fall below the pour point.

        Note: Right now we won't worry about estimating the pour point
              if the pour point data points don't exist for the record,
              then we will assume that our densities are probably fine.
    '''
    try:
        pp_max = imported_rec.pour_point_max_k
        pp_min = imported_rec.pour_point_min_k
        pour_point = min([pp for pp in (pp_min, pp_max) if pp is not None])
    except (ValueError, TypeError):
        pour_point = None

    if pour_point is None:
        return False
    else:
        rho_temps = [d.ref_temp_k for d in imported_rec.densities
                     if d.ref_temp_k is not None]
        if imported_rec.api is not None:
            rho_temps.append(288.15)

        if any([(t < pour_point) for t in rho_temps]):
            try:
                oil_id = imported_rec.adios_oil_id
            except AttributeError:
                oil_id = imported_rec.oil_id

            print ('\toil_id: {}, pour_point: {}, rho_temps: {}, lt: {}'
                   .format(oil_id, pour_point, rho_temps,
                           [(t < pour_point) for t in rho_temps]))
            return True


def reject_oil_if_bad(oil):
    '''
        Here, we have an oil in which all estimations have been made.
        We will now check it to see if there are any detectable flaws.
        If any flaw is detected, we will raise the OilRejected exception.
        All flaws will be compiled into a list of error messages to be passed
        into the exception.
    '''
    errors = []

    if not oil_has_kvis(oil):
        errors.append('Oil has no kinematic viscosities')

    if oil_has_duplicate_cuts(oil):
        errors.append('Oil has duplicate cuts')

    if oil_has_heavy_sa_components(oil):
        errors.append('Oil has heavy SA components')

    if not oil_api_matches_density(oil):
        errors.append('Oil API does not match its density')

    if len(errors) > 0:
        try:
            oil_id = oil.adios_oil_id
        except AttributeError:
            oil_id = oil.oil_id

        raise OilRejected(errors, oil_id)


def oil_has_kvis(oil):
    '''
        Our oil record should have at least one kinematic viscosity when
        estimations are complete.
    '''
    if len(oil.kvis) > 0:
        return True
    else:
        return False


def oil_has_duplicate_cuts(oil):
    '''
        Some oil records have been found to have distillation cuts with
        duplicate vapor temperatures, and the fraction that should be chosen
        at that temperature is ambiguous.
    '''
    unique_temps = set([o.vapor_temp_k for o in oil.cuts])

    if len(oil.cuts) != len(unique_temps):
        return True
    else:
        return False


def oil_has_heavy_sa_components(oil):
    '''
        Some oil records have been found to have Saturate & Asphaltene
        densities that were calculated to be heavier than the Resins &
        Asphaltenes.
        This is highly improbable and indicates the record has problems
        with its imported data values.
    '''
    resin_rho = [d.kg_m_3 for d in oil.sara_densities
                 if d.sara_type == 'Resins']

    if len(resin_rho) == 0:
        resin_rho = 1100.0
    else:
        resin_rho = np.max((resin_rho[0], 1100.0))

    for d in oil.sara_densities:
        if d.sara_type in ('Saturates', 'Aromatics'):
            if d.kg_m_3 > resin_rho:
                return True

    return False


def oil_api_matches_density(oil):
    '''
        The oil API should pretty closely match its density at 15C.
    '''
    oil_estimations = ImportedRecordWithEstimation(oil)

    d_0 = oil_estimations.density_at_temp(273.15 + 15)
    api = api_from_density(d_0)

    if np.isclose(oil.api, api, rtol=0.05):
        return True

    logger.info('(oil.api, api_from_density) = ({}, {}), rtol={:0.3f}'
                .format(oil.api, api, np.abs(oil.api - api) / np.abs(api)))
    return False
