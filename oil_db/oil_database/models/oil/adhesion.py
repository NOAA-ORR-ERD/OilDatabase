#
# PyMODM model class for Environment Canada's adhesion
# oil properties.
#
from pymodm import EmbeddedMongoModel, EmbeddedDocumentField
from pymodm.fields import FloatField

from oil_database.models.common.float_unit import AdhesionUnit


class Adhesion(EmbeddedMongoModel):
    adhesion = EmbeddedDocumentField(AdhesionUnit)
    weathering = FloatField(default=0.0)

    # may as well keep the extra stuff
    replicates = FloatField(blank=True)
    standard_deviation = FloatField(blank=True)

    def __init__(self, **kwargs):
        # we will fail on any arguments that are not defined members
        # of this class
        for a, _v in kwargs.items():
            if (a not in self.__class__.__dict__):
                del kwargs[a]

        if 'weathering' not in kwargs or kwargs['weathering'] is None:
            # Seriously?  What good is a default if it can't negotiate
            # None values?
            kwargs['weathering'] = 0.0

        super(Adhesion, self).__init__(**kwargs)

    def __str__(self):
        return self.__repr__()

    def __repr__(self):
        return ('<{}({}, w={})>'
                .format(self.__class__.__name__,
                        self.adhesion, self.weathering))
